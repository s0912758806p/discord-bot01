"""
台股指令與背景通知。

指令：
- !twii：加權指數（cnyes 網頁）
- !tws <股票代碼>：個股即時資訊（twstock）
- !早盤報告：立即在目前頻道產生早盤報告（預覽用）

背景任務（需設定 STOCK_CHANNEL，否則不啟動；指令照常可用）：
- 早盤報告：交易日 STOCK_REPORT_TIME（預設 08:30）發一則 embed：台股收盤（加權、櫃買）、
  美股收盤（道瓊、S&P 500、那斯達克、費半、台積電 ADR）、國內與國際新聞各 STOCK_NEWS_LIMIT 則
  （上一個交易日報告時間到現在，沿時間平均挑選，只列標題與連結）。任一段抓不到只顯示「暫時無法取得」。
- 盤中監控：交易日 09:00–13:35 每 STOCK_POLL_SECONDS 秒抓一次加權指數（證交所 MIS），
  交給 core/volatility.py 判斷，「首次突破 ±STOCK_ALERT_STEP_PCT 的倍數」或
  「STOCK_RAPID_WINDOW_MIN 分鐘內急漲急跌 STOCK_RAPID_PCT%」時通知所有 STOCK_CHANNEL 頻道。
  已通知的門檻存在 data/stock_alert_state.json，當天重啟不會重發。

交易日依證交所開休市日期表判斷（core/market.py）；表抓不到時只排除週末。
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Set, Tuple

import discord
import twstock
from bs4 import BeautifulSoup
from discord.ext import commands, tasks

from core import market
from core.assets import PROJECT_ROOT
from core.classes import Cog_Extension
from core.logging import logger
from core.volatility import Alert, VolatilityDetector

MARKET_OPEN = dt.time(9, 0)
MONITOR_END = dt.time(13, 35)  # 13:30 收盤後再多抓幾分鐘，拿到最後一盤
HOLIDAY_RETRY = dt.timedelta(minutes=10)
DEFAULT_REPORT_TIME = dt.time(8, 30, tzinfo=market.TPE)

DOMESTIC_NEWS = ('tw_stock', 'tw_macro')
WORLD_NEWS = ('wd_stock', 'us_stock', 'wd_macro')
FIELD_LIMIT = 1024  # Discord embed field value 上限
SHORT_NAMES = {'發行量加權股價指數': '加權指數'}
WEEKDAYS = '一二三四五六日'


def now_tpe() -> dt.datetime:
    """目前台北時間（測試時 patch 這個函式）。"""
    return dt.datetime.now(market.TPE)


@dataclass(frozen=True)
class StockSettings:
    channels: Tuple[int, ...] = ()
    poll_seconds: float = 30.0
    step_pct: float = 1.0
    rapid_pct: float = 0.7
    rapid_window_min: int = 5
    rapid_cooldown_min: int = 15
    state_path: Optional[Path] = None
    report_time: dt.time = DEFAULT_REPORT_TIME
    news_limit: int = 8

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> 'StockSettings':
        def num(name: str, default: float) -> float:
            raw = (env.get(name) or '').strip()
            if not raw:
                return default
            try:
                value = float(raw)
            except ValueError:
                logger.warning('%s=%r 不是數字，改用預設值 %s', name, raw, default)
                return default
            if value <= 0:
                logger.warning('%s=%r 必須大於 0，改用預設值 %s', name, raw, default)
                return default
            return value

        channels = []
        for part in (env.get('STOCK_CHANNEL') or '').split(','):
            part = part.strip()
            if not part:
                continue
            if part.isdigit():
                channels.append(int(part))
            else:
                logger.warning('STOCK_CHANNEL 中的 %r 不是頻道 ID，已略過', part)

        report_time = DEFAULT_REPORT_TIME
        raw_time = (env.get('STOCK_REPORT_TIME') or '').strip()
        if raw_time:
            try:
                report_time = dt.datetime.strptime(raw_time, '%H:%M').time().replace(tzinfo=market.TPE)
            except ValueError:
                logger.warning('STOCK_REPORT_TIME=%r 不是 HH:MM，改用預設 08:30', raw_time)

        return cls(
            channels=tuple(channels),
            poll_seconds=num('STOCK_POLL_SECONDS', 30.0),
            step_pct=num('STOCK_ALERT_STEP_PCT', 1.0),
            rapid_pct=num('STOCK_RAPID_PCT', 0.7),
            rapid_window_min=int(num('STOCK_RAPID_WINDOW_MIN', 5)),
            rapid_cooldown_min=int(num('STOCK_RAPID_COOLDOWN_MIN', 15)),
            state_path=PROJECT_ROOT / 'data' / 'stock_alert_state.json',
            report_time=report_time,
            news_limit=int(num('STOCK_NEWS_LIMIT', 8)),
        )


# ---------- 早盤報告（資料 + 純函式排版） ----------

@dataclass
class MorningReport:
    """各段資料；None 表示該段抓取失敗（其他段照常顯示）。"""
    generated_at: dt.datetime
    news_since: dt.datetime
    indices: Optional[List[market.IndexQuote]]
    global_quotes: Optional[List[market.GlobalQuote]]
    domestic_news: Optional[List[market.NewsItem]]
    world_news: Optional[List[market.NewsItem]]


def _arrow(change: float) -> str:
    return '🔺' if change > 0 else '🔻' if change < 0 else '—'


def _fit(lines: List[str], limit: int = FIELD_LIMIT) -> str:
    """把行接起來並截到 limit 字內（整行捨棄，不切斷連結）。"""
    kept: List[str] = []
    for line in lines:
        if len('\n'.join(kept + [line])) > limit:
            break
        kept.append(line)
    return '\n'.join(kept)


def _quote_lines(rows) -> List[str]:
    return [f'{SHORT_NAMES.get(name, name)}　{price:,.2f}　{_arrow(change)}{abs(change):,.2f}（{pct:+.2f}%）'
            for name, price, change, pct in rows]


def _news_lines(items: List[market.NewsItem]) -> List[str]:
    # 標題裡的 [ ] 會打斷 Discord 的 [文字](連結) 語法，換成全形
    return [f'• [{i.title.replace("[", "［").replace("]", "］")}]({i.url})' for i in items]


def render_morning_report(report: MorningReport) -> discord.Embed:
    now = report.generated_at
    embed = discord.Embed(
        title=f'☀️ 台股早盤報告　{now:%Y/%m/%d}（{WEEKDAYS[now.weekday()]}）',
        color=discord.Color.gold(),
    )

    unavailable = '暫時無法取得'
    if report.indices is None:
        embed.add_field(name='台股收盤', value=unavailable, inline=False)
    elif not report.indices:
        embed.add_field(name='台股收盤', value='無資料', inline=False)
    else:
        day = report.indices[0].date
        rows = [(q.name, q.price, q.change, q.change_pct) for q in report.indices]
        embed.add_field(name=f'台股收盤（{day:%m/%d}）', value=_fit(_quote_lines(rows)), inline=False)

    if report.global_quotes is None:
        value = unavailable
    else:
        rows = [(q.name, q.price, q.change, q.change_pct) for q in report.global_quotes]
        value = _fit(_quote_lines(rows)) or '無資料'
    embed.add_field(name='美股收盤', value=value, inline=False)

    for title, items in (('國內財經新聞', report.domestic_news), ('國際財經新聞', report.world_news)):
        if items is None:
            value = unavailable
        else:
            value = _fit(_news_lines(items)) or '這段期間沒有新聞'
        embed.add_field(name=title, value=value, inline=False)

    embed.set_footer(text=f'資料來源：臺灣證券交易所、鉅亨網｜新聞期間 {report.news_since:%m/%d %H:%M} 起')
    return embed


class Stock(Cog_Extension):
    def __init__(self, bot, settings: Optional[StockSettings] = None):
        super().__init__(bot)
        self.settings = settings or StockSettings.from_env()
        self.detector = VolatilityDetector(
            step_pct=self.settings.step_pct,
            rapid_pct=self.settings.rapid_pct,
            rapid_window=dt.timedelta(minutes=self.settings.rapid_window_min),
            rapid_cooldown=dt.timedelta(minutes=self.settings.rapid_cooldown_min),
            state_path=self.settings.state_path,
        )
        self._holidays: Dict[int, Set[dt.date]] = {}
        self._holiday_retry_at: Optional[dt.datetime] = None
        self.monitor.change_interval(seconds=self.settings.poll_seconds)
        self.morning_report.change_interval(time=self.settings.report_time)

    # ---------- 生命週期 ----------

    async def cog_load(self) -> None:
        if not self.settings.channels:
            logger.info('未設定 STOCK_CHANNEL，台股盤中監控與早盤報告不啟動')
            return
        self.monitor.start()
        self.morning_report.start()
        logger.info('台股盤中監控與早盤報告（%s）已啟動，通知頻道: %s',
                    self.settings.report_time.strftime('%H:%M'), self.settings.channels)

    async def cog_unload(self) -> None:
        self.monitor.cancel()
        self.morning_report.cancel()

    # ---------- 共用 ----------

    async def holidays_for(self, year: int) -> Set[dt.date]:
        """該年休市日；抓不到時回空集合（只排除週末），10 分鐘後再試。"""
        if year in self._holidays:
            return self._holidays[year]
        now = now_tpe()
        if self._holiday_retry_at and now < self._holiday_retry_at:
            return set()
        try:
            holidays = await market.fetch_holidays(self.session, year)
        except Exception as e:  # 網路、JSON、HTTP 錯誤都一樣處理
            holidays, error = set(), e
        else:
            error = None if holidays else '回傳空的日期表'
        if error is not None:
            logger.warning('無法取得 %s 年休市日，暫時只排除週末：%s', year, error)
            self._holiday_retry_at = now + HOLIDAY_RETRY
            return set()
        self._holidays[year] = holidays
        return holidays

    async def broadcast(self, content: Optional[str] = None,
                        embed: Optional[discord.Embed] = None) -> None:
        for channel_id in self.settings.channels:
            try:
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                await channel.send(content=content, embed=embed)
            except Exception as e:
                logger.warning('無法發送台股通知到頻道 %s：%s', channel_id, e)

    # ---------- 盤中監控 ----------

    async def poll_once(self) -> List[Alert]:
        now = now_tpe()
        if now.weekday() >= 5 or not (MARKET_OPEN <= now.time() <= MONITOR_END):
            return []
        if now.date() in await self.holidays_for(now.year):
            return []
        try:
            quote = await market.fetch_taiex(self.session)
        except Exception as e:
            logger.warning('抓取加權指數失敗：%s', e)
            return []
        # 臨時休市（颱風假等）時 MIS 回的是前一個交易日的資料
        if quote is None or quote.date != now.date():
            return []
        alerts = self.detector.feed(quote, now)
        for alert in alerts:
            logger.info('台股波動通知: %s', alert.message().splitlines()[0])
            await self.broadcast(alert.message())
        return alerts

    @tasks.loop(seconds=30)
    async def monitor(self) -> None:
        try:
            await self.poll_once()
        except Exception:
            # 未捕捉的例外會讓 tasks.loop 停止；記錄後繼續下一輪
            logger.exception('台股盤中監控發生未預期錯誤')

    @monitor.before_loop
    async def _before_monitor(self) -> None:
        await self.bot.wait_until_ready()

    # ---------- 早盤報告 ----------

    async def _news(self, categories: Tuple[str, ...], start: dt.datetime,
                    end: dt.datetime) -> List[market.NewsItem]:
        groups = await asyncio.gather(*(market.fetch_news(self.session, c, start, end)
                                        for c in categories))
        return market.merge_news(groups, self.settings.news_limit)

    async def collect_report(self, now: dt.datetime) -> MorningReport:
        """新聞期間：上一個交易日的報告時間 → now（週一會涵蓋週末）。各段獨立，失敗只影響該段。"""
        holidays = await self.holidays_for(now.year) | await self.holidays_for(now.year - 1)
        prev_day = market.previous_trading_day(now.date(), holidays)
        since = dt.datetime.combine(prev_day, self.settings.report_time)

        results = await asyncio.gather(
            market.fetch_indices(self.session),
            market.fetch_global_quotes(self.session),
            self._news(DOMESTIC_NEWS, since, now),
            self._news(WORLD_NEWS, since, now),
            return_exceptions=True,
        )
        sections = ('台股指數', '美股', '國內新聞', '國際新聞')
        for name, result in zip(sections, results):
            if isinstance(result, BaseException):
                logger.warning('早盤報告：%s 抓取失敗：%s', name, result)
        indices, global_quotes, domestic, world = (
            None if isinstance(r, BaseException) else r for r in results)
        return MorningReport(now, since, indices, global_quotes, domestic, world)

    @tasks.loop(time=DEFAULT_REPORT_TIME)
    async def morning_report(self) -> None:
        try:
            now = now_tpe()
            if not market.is_trading_day(now.date(), await self.holidays_for(now.year)):
                logger.info('今天不是交易日，不發早盤報告')
                return
            embed = render_morning_report(await self.collect_report(now))
            await self.broadcast(embed=embed)
            logger.info('早盤報告已發送')
        except Exception:
            logger.exception('早盤報告發生未預期錯誤')

    @morning_report.before_loop
    async def _before_morning_report(self) -> None:
        await self.bot.wait_until_ready()

    # ---------- 指令 ----------

    @commands.command(name='早盤報告')
    async def morning_report_now(self, ctx):
        """立即在這個頻道產生早盤報告（預覽用，不限交易日）"""
        async with ctx.typing():
            embed = render_morning_report(await self.collect_report(now_tpe()))
        await ctx.send(embed=embed)

    @commands.command()
    async def twii(self, ctx):
        """獲取台灣加權指數資訊"""
        url = 'https://invest.cnyes.com/index/TWS/TSE01'

        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    await ctx.send(f"獲取數據失敗，狀態碼: {response.status}")
                    return

                response_text = await response.text()

                soup = BeautifulSoup(response_text, 'html.parser')

                twiiTitle = soup.select('.header_second')[0].text
                twiiDateNow = soup.select('.header-time .jsx-2214436525')[0].text
                twiiIndex = soup.select('.header-info .info-price .info-lp span')[0].text
                twiiUpDownIndex = soup.select('.header-info .info-change .change-net span')[0].text
                twiiUpDownPercent = soup.select('.header-info .info-change .change-percent span')[0].text

                twiiBuySellTitle = soup.select('.data-block .block-title')[0].text
                twiiBuySellValue = soup.select('.data-block .block-value')[0].text
                twiiToDayHeighLowTitle = soup.select('.data-block .block-title')[1].text
                twiiToDayHeighLowValue = soup.select('.data-block .block-value')[1].text
                twii52HeighLowTitle = soup.select('.data-block .block-title')[2].text
                twii52HeighLowValue = soup.select('.data-block .block-value')[2].text

                await ctx.send(twiiTitle + '\n' + twiiDateNow + '\n' +
                              '當前指數: ' + str(twiiIndex) + '\n' + '漲跌點: ' +
                              str(twiiUpDownIndex) + '\n' + '漲跌百分比: ' +
                              str(twiiUpDownPercent) + '\n' +
                              twiiBuySellTitle + ': ' + twiiBuySellValue +
                              '\n' + twiiToDayHeighLowTitle + ': ' +
                              twiiToDayHeighLowValue + '\n' +
                              twii52HeighLowTitle + ': ' +
                              twii52HeighLowValue)
        except Exception as e:
            await ctx.send(f"獲取台股指數時發生錯誤: {str(e)}")

    @commands.command()
    async def tws(self, ctx, stock_id: str = None):
        """獲取特定股票資訊"""
        if stock_id is None:
            await ctx.send("請提供股票代碼，例如: !tws 2330")
            return

        try:
            # twstock 用同步 requests，丟到 thread 執行以免卡住整個 event loop
            stock = await asyncio.to_thread(twstock.realtime.get, stock_id)

            if stock['success']:
                stockInfo = list(stock['info'].values())
                stockRealtime = list(stock['realtime'].values())

                await ctx.send('股票代號: ' + stockInfo[0] + '\n' +
                              '股票名: ' + stockInfo[2] + '\n' +
                              '最後揭示買價: ' + stockRealtime[3][0][:-2] +
                              '\n' + '最後揭示買量: ' +
                              stockRealtime[4][0] + '\n' +
                              '最後揭示賣價: ' + stockRealtime[5][0][:-2] +
                              '\n' + '最後揭示賣量: ' +
                              stockRealtime[6][0] + '\n' + '成交量: ' +
                              stockRealtime[1] + '\n' + '累積成交量: ' +
                              stockRealtime[2] + '\n' + '開盤價: ' +
                              stockRealtime[7][:-2] + '\n' +
                              '盤中最高價: ' + stockRealtime[8][:-2] +
                              '\n' + '盤中最低價: ' +
                              stockRealtime[9][:-2] + '\n' +
                              '收盤價: ' + stockRealtime[0][:-2])
            else:
                await ctx.send(f"無法獲取股票 {stock_id} 的數據")
        except Exception as e:
            await ctx.send(f"獲取股票信息時發生錯誤: {str(e)}")

async def setup(bot):
    await bot.add_cog(Stock(bot))
