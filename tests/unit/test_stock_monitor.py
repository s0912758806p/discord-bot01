#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cmds/stock.py 的背景任務：設定解析、交易時段判斷、波動通知發送。"""
import datetime as dt
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.market import IndexQuote, TPE

TODAY = dt.date(2026, 11, 19)  # 週四


def tpe(day: dt.date, h: int, m: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(h, m), TPE)


def quote(pct: float, day: dt.date = TODAY) -> IndexQuote:
    prev = 40000.0
    return IndexQuote('發行量加權股價指數', round(prev * (1 + pct / 100), 2), prev,
                      None, None, None, day, '10:00:00')


def make_cog(channels=(111, 222), **overrides):
    from cmds.stock import Stock, StockSettings
    bot = MagicMock()
    sent = {}

    def get_channel(cid):
        ch = MagicMock()
        ch.send = AsyncMock()
        sent[cid] = ch
        return ch

    bot.get_channel.side_effect = get_channel
    settings = StockSettings(channels=tuple(channels), rapid_pct=99, **overrides)
    return Stock(bot, settings), bot, sent


class TestSettings(unittest.TestCase):
    def test_from_env_parses_channels_and_numbers(self):
        from cmds.stock import StockSettings
        s = StockSettings.from_env({
            'STOCK_CHANNEL': ' 123, 456 ,abc,',
            'STOCK_ALERT_STEP_PCT': '1.5',
            'STOCK_RAPID_PCT': 'oops',
            'STOCK_POLL_SECONDS': '-5',
        })
        self.assertEqual(s.channels, (123, 456))
        self.assertEqual(s.step_pct, 1.5)
        self.assertEqual(s.rapid_pct, 0.7)      # 非數字 → 預設
        self.assertEqual(s.poll_seconds, 30.0)  # 非正數 → 預設

    def test_empty_env_disables_notifications(self):
        from cmds.stock import StockSettings
        self.assertEqual(StockSettings.from_env({}).channels, ())


class TestPollOnce(unittest.IsolatedAsyncioTestCase):
    async def poll(self, cog, now, q=None, holidays=frozenset()):
        with patch('cmds.stock.now_tpe', return_value=now), \
             patch('cmds.stock.market.fetch_holidays', AsyncMock(return_value=set(holidays) or {dt.date(2026, 12, 25)})), \
             patch('cmds.stock.market.fetch_taiex', AsyncMock(return_value=q)) as fetch:
            alerts = await cog.poll_once()
        return alerts, fetch

    async def test_alert_is_sent_to_every_channel(self):
        cog, _, sent = make_cog()
        alerts, _ = await self.poll(cog, tpe(TODAY, 10), quote(-2.1))
        self.assertEqual(len(alerts), 1)
        self.assertEqual(set(sent), {111, 222})
        for ch in sent.values():
            ch.send.assert_awaited_once()
            self.assertIn('跌幅突破 2%', ch.send.await_args.kwargs['content'])

    async def test_same_level_is_not_resent(self):
        cog, _, sent = make_cog()
        await self.poll(cog, tpe(TODAY, 10), quote(-2.1))
        alerts, _ = await self.poll(cog, tpe(TODAY, 10, 1), quote(-2.4))
        self.assertEqual(alerts, [])

    async def test_outside_market_hours_does_not_fetch(self):
        cog, _, _ = make_cog()
        for now in (tpe(TODAY, 8, 59), tpe(TODAY, 13, 36),
                    tpe(dt.date(2026, 11, 21), 10)):  # 週六
            _, fetch = await self.poll(cog, now, quote(-3))
            fetch.assert_not_awaited()

    async def test_holiday_does_not_fetch(self):
        cog, _, _ = make_cog()
        xmas = dt.date(2026, 12, 25)  # 週五休市
        _, fetch = await self.poll(cog, tpe(xmas, 10), quote(-3, xmas), holidays={xmas})
        fetch.assert_not_awaited()

    async def test_stale_quote_from_previous_day_is_ignored(self):
        """臨時休市時 MIS 回前一交易日資料，不能拿來發通知。"""
        cog, _, sent = make_cog()
        alerts, _ = await self.poll(cog, tpe(TODAY, 10), quote(-3, TODAY - dt.timedelta(days=1)))
        self.assertEqual(alerts, [])
        self.assertEqual(sent, {})

    async def test_fetch_error_is_swallowed(self):
        cog, _, _ = make_cog()
        with patch('cmds.stock.now_tpe', return_value=tpe(TODAY, 10)), \
             patch('cmds.stock.market.fetch_holidays', AsyncMock(return_value={dt.date(2026, 12, 25)})), \
             patch('cmds.stock.market.fetch_taiex', AsyncMock(side_effect=TimeoutError)):
            self.assertEqual(await cog.poll_once(), [])

    async def test_one_failing_channel_does_not_block_others(self):
        cog, bot, _ = make_cog()
        good = MagicMock(send=AsyncMock())
        bad = MagicMock(send=AsyncMock(side_effect=RuntimeError('Missing Access')))
        bot.get_channel.side_effect = lambda cid: bad if cid == 111 else good
        await cog.broadcast('hi')
        good.send.assert_awaited_once()


class TestHolidayCache(unittest.IsolatedAsyncioTestCase):
    async def test_failure_falls_back_and_backs_off(self):
        cog, _, _ = make_cog()
        failing = AsyncMock(side_effect=OSError('down'))
        with patch('cmds.stock.now_tpe', return_value=tpe(TODAY, 9)), \
             patch('cmds.stock.market.fetch_holidays', failing):
            self.assertEqual(await cog.holidays_for(2026), set())
            self.assertEqual(await cog.holidays_for(2026), set())
        self.assertEqual(failing.await_count, 1)  # 10 分鐘內不重試

    async def test_success_is_cached(self):
        cog, _, _ = make_cog()
        ok = AsyncMock(return_value={dt.date(2026, 12, 25)})
        with patch('cmds.stock.now_tpe', return_value=tpe(TODAY, 9)), \
             patch('cmds.stock.market.fetch_holidays', ok):
            await cog.holidays_for(2026)
            await cog.holidays_for(2026)
        self.assertEqual(ok.await_count, 1)


def news(n: int, title_len: int = 30):
    from core.market import NewsItem
    base = tpe(TODAY, 8)
    return [NewsItem(f'新聞{i}' + '字' * title_len, f'https://news.cnyes.com/news/id/{i}',
                     base - dt.timedelta(hours=i)) for i in range(n)]


def report(**overrides):
    from cmds.stock import MorningReport
    from core.market import GlobalQuote
    data = dict(
        generated_at=tpe(TODAY, 8, 30),
        news_since=tpe(TODAY - dt.timedelta(days=1), 8, 30),
        indices=[quote(-4.4, TODAY - dt.timedelta(days=1))],
        global_quotes=[GlobalQuote('道瓊指數', 50198.17, -561.25, -1.11),
                       GlobalQuote('台積電ADR', 362.62, 2.93, 0.81)],
        domestic_news=news(8),
        world_news=news(8),
    )
    data.update(overrides)
    return MorningReport(**data)


class TestRenderMorningReport(unittest.TestCase):
    def render(self, **overrides):
        from cmds.stock import render_morning_report
        return render_morning_report(report(**overrides))

    def fields(self, embed):
        return {f.name: f.value for f in embed.fields}

    def test_has_all_four_sections(self):
        embed = self.render()
        names = [f.name for f in embed.fields]
        self.assertEqual(names, ['台股收盤（11/18）', '美股收盤', '國內財經新聞', '國際財經新聞'])
        self.assertIn('2026/11/19（四）', embed.title)
        f = self.fields(embed)
        self.assertIn('加權指數　38,240.00　🔻1,760.00（-4.40%）', f['台股收盤（11/18）'])
        self.assertIn('道瓊指數　50,198.17　🔻561.25（-1.11%）', f['美股收盤'])
        self.assertIn('台積電ADR　362.62　🔺2.93（+0.81%）', f['美股收盤'])
        self.assertEqual(f['國內財經新聞'].count('https://news.cnyes.com/news/id/'), 8)

    def test_fields_stay_within_discord_limit(self):
        embed = self.render(domestic_news=news(30, title_len=80), world_news=news(30, title_len=80))
        for field in embed.fields:
            self.assertLessEqual(len(field.value), 1024, field.name)
        self.assertLessEqual(len(embed), 6000)
        # 截斷是整行捨棄，最後一行仍是完整連結
        self.assertTrue(self.fields(embed)['國內財經新聞'].endswith(')'))

    def test_failed_section_does_not_hide_others(self):
        f = self.fields(self.render(global_quotes=None, world_news=None))
        self.assertEqual(f['美股收盤'], '暫時無法取得')
        self.assertEqual(f['國際財經新聞'], '暫時無法取得')
        self.assertIn('https://', f['國內財經新聞'])

    def test_brackets_in_title_do_not_break_links(self):
        from core.market import NewsItem
        item = NewsItem('【盤前】台積電[ADR]大漲', 'https://x/1', tpe(TODAY, 7))
        f = self.fields(self.render(domestic_news=[item]))
        self.assertEqual(f['國內財經新聞'], '• [【盤前】台積電［ADR］大漲](https://x/1)')


class TestMorningReportTask(unittest.IsolatedAsyncioTestCase):
    def patches(self, now):
        from core.market import GlobalQuote
        return (
            patch('cmds.stock.now_tpe', return_value=now),
            patch('cmds.stock.market.fetch_holidays', AsyncMock(return_value={dt.date(2026, 12, 25)})),
            patch('cmds.stock.market.fetch_indices', AsyncMock(return_value=[quote(-1)])),
            patch('cmds.stock.market.fetch_global_quotes',
                  AsyncMock(return_value=[GlobalQuote('道瓊指數', 1.0, 0.1, 0.1)])),
            patch('cmds.stock.market.fetch_news', AsyncMock(return_value=news(3))),
        )

    async def run_task(self, now):
        cog, _, sent = make_cog()
        p = self.patches(now)
        with p[0], p[1], p[2], p[3], p[4] as fetch_news:
            await cog.morning_report.coro(cog)
        return cog, sent, fetch_news

    async def test_sends_embed_on_trading_day(self):
        _, sent, _ = await self.run_task(tpe(TODAY, 8, 30))
        self.assertEqual(set(sent), {111, 222})
        embed = sent[111].send.await_args.kwargs['embed']
        self.assertIn('台股早盤報告', embed.title)

    async def test_skips_weekend_and_holiday(self):
        for day in (dt.date(2026, 11, 21), dt.date(2026, 12, 25)):
            _, sent, fetch_news = await self.run_task(tpe(day, 8, 30))
            self.assertEqual(sent, {})
            fetch_news.assert_not_awaited()

    async def test_monday_news_window_covers_weekend(self):
        monday = dt.date(2026, 11, 23)
        _, _, fetch_news = await self.run_task(tpe(monday, 8, 30))
        starts = {c.args[2] for c in fetch_news.await_args_list}
        self.assertEqual(starts, {tpe(dt.date(2026, 11, 20), 8, 30)})  # 上週五 08:30
        categories = {c.args[1] for c in fetch_news.await_args_list}
        self.assertEqual(categories, {'tw_stock', 'tw_macro', 'wd_stock', 'us_stock', 'wd_macro'})

    async def test_one_failing_source_still_sends_report(self):
        cog, _, sent = make_cog()
        p = self.patches(tpe(TODAY, 8, 30))
        with p[0], p[1], p[2], p[4], \
             patch('cmds.stock.market.fetch_global_quotes', AsyncMock(side_effect=TimeoutError)):
            await cog.morning_report.coro(cog)
        embed = sent[111].send.await_args.kwargs['embed']
        self.assertEqual({f.name: f.value for f in embed.fields}['美股收盤'], '暫時無法取得')

    def test_report_time_from_env(self):
        from cmds.stock import StockSettings
        self.assertEqual(StockSettings.from_env({'STOCK_REPORT_TIME': '07:45'}).report_time,
                         dt.time(7, 45, tzinfo=TPE))
        self.assertEqual(StockSettings.from_env({'STOCK_REPORT_TIME': '25:99'}).report_time,
                         dt.time(8, 30, tzinfo=TPE))

    def test_report_loop_uses_configured_time(self):
        cog, _, _ = make_cog(report_time=dt.time(7, 45, tzinfo=TPE))
        self.assertEqual(cog.morning_report.time, [dt.time(7, 45, tzinfo=TPE)])


class TestLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_no_channel_means_no_background_task(self):
        cog, _, _ = make_cog(channels=())
        await cog.cog_load()
        self.assertFalse(cog.monitor.is_running())

    async def test_monitor_loop_survives_unexpected_error(self):
        cog, _, _ = make_cog()
        with patch.object(cog, 'poll_once', AsyncMock(side_effect=ValueError('boom'))):
            await cog.monitor.coro(cog)  # 不應拋出

    async def test_poll_interval_comes_from_settings(self):
        cog, _, _ = make_cog(poll_seconds=12)
        self.assertEqual(cog.monitor.seconds, 12)


if __name__ == '__main__':
    unittest.main()
