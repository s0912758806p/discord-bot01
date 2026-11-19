"""
台股／國際市場資料層：抓取與解析，不依賴 Discord。

資料來源（皆免 API key，但都是未公開 API，網站改版時只需改這個檔）：
- 證交所 MIS：加權、櫃買指數即時行情
- 鉅亨網 quote API：美股指數與台積電 ADR
- 鉅亨網 news API：新聞標題與連結
- 證交所開休市日期表（www.twse.com.tw 的 holidaySchedule，依年份查詢）

parse_* 為純函式（吃 JSON、吐 dataclass），fetch_* 只負責 HTTP，方便用錄下來的回應測試。
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Set, Tuple
from zoneinfo import ZoneInfo

import aiohttp

TPE = ZoneInfo('Asia/Taipei')

MIS_URL = 'https://mis.twse.com.tw/stock/api/getStockInfo.jsp'
TAIEX = 'tse_t00.tw'
OTC = 'otc_o00.tw'

CNYES_QUOTE_URL = 'https://ws.api.cnyes.com/ws/api/v1/quote/quotes/{symbols}?column=G'
GLOBAL_SYMBOLS: Tuple[str, ...] = (
    'GI:DJI:INDEX',   # 道瓊
    'GI:INX:INDEX',   # S&P 500
    'GI:IXIC:INDEX',  # 那斯達克
    'GI:SOX:INDEX',   # 費城半導體
    'USS:TSM:STOCK',  # 台積電 ADR
)
CNYES_NEWS_URL = 'https://api.cnyes.com/media/api/v1/newslist/category/{category}'
CNYES_NEWS_LINK = 'https://news.cnyes.com/news/id/{news_id}'

HOLIDAY_URL = 'https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule'
# 開休市日期表也列出「開始交易日」「最後交易日」這類照常交易的日子，不能當休市
_TRADING_DAY_MARKERS = ('開始交易', '最後交易')


# ---------- 資料結構 ----------

@dataclass(frozen=True)
class IndexQuote:
    name: str
    price: float
    prev_close: float
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    date: dt.date
    time: str  # 'HH:MM:SS'，交易所時間

    @property
    def change(self) -> float:
        return self.price - self.prev_close

    @property
    def change_pct(self) -> float:
        return self.change / self.prev_close * 100 if self.prev_close else 0.0


@dataclass(frozen=True)
class GlobalQuote:
    name: str
    price: float
    change: float
    change_pct: float


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    published: dt.datetime  # Asia/Taipei


# ---------- 解析（純函式） ----------

def _num(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_mis(data: dict) -> List[IndexQuote]:
    """解析 MIS 回應。尚無成交價（開盤前 z='-'）或欄位缺漏的項目略過。"""
    quotes = []
    for m in data.get('msgArray', []):
        price, prev = _num(m.get('z')), _num(m.get('y'))
        if price is None or prev is None:
            continue
        try:
            day = dt.datetime.strptime(m['d'], '%Y%m%d').date()
        except (KeyError, ValueError):
            continue
        quotes.append(IndexQuote(
            name=m.get('n', m.get('c', '')),
            price=price, prev_close=prev,
            open=_num(m.get('o')), high=_num(m.get('h')), low=_num(m.get('l')),
            date=day, time=m.get('t', ''),
        ))
    return quotes


def parse_cnyes_quotes(data: dict) -> List[GlobalQuote]:
    """鉅亨 quote API：欄位以數字代碼表示（200009 名稱、6 價、11 漲跌、56 漲跌%）。"""
    quotes = []
    for q in data.get('data') or []:
        name, price = q.get('200009'), _num(q.get('6'))
        if not name or price is None:
            continue
        quotes.append(GlobalQuote(
            name=name, price=price,
            change=_num(q.get('11')) or 0.0, change_pct=_num(q.get('56')) or 0.0,
        ))
    return quotes


def parse_cnyes_news(data: dict) -> List[NewsItem]:
    """鉅亨新聞列表。略過外包稿（isOutsource=1，例如第三方分析平台的轉載）。"""
    items = []
    for n in (data.get('items') or {}).get('data') or []:
        title, news_id, ts = n.get('title'), n.get('newsId'), n.get('publishAt')
        if not title or news_id is None or ts is None or n.get('isOutsource'):
            continue
        items.append(NewsItem(
            title=title.strip(),
            url=CNYES_NEWS_LINK.format(news_id=news_id),
            published=dt.datetime.fromtimestamp(ts, TPE),
        ))
    return items


def merge_news(groups: Iterable[Sequence[NewsItem]], limit: int) -> List[NewsItem]:
    """合併多個分類：依標題去重（保留較新的），再沿時間軸平均挑 limit 則，新到舊排列。

    API 沒有「重要性」欄位；只取最新幾則會全是清晨的新聞，
    平均挑選才能涵蓋整段時間窗（前一日盤中、收盤後、美股時段）。
    """
    seen, unique = set(), []
    for item in sorted((i for g in groups for i in g), key=lambda i: i.published, reverse=True):
        if item.title in seen:
            continue
        seen.add(item.title)
        unique.append(item)
    if limit <= 0:
        return []
    if len(unique) <= limit:
        return unique
    if limit == 1:
        return unique[:1]
    step = (len(unique) - 1) / (limit - 1)
    return [unique[round(i * step)] for i in range(limit)]


def parse_holidays(data: dict) -> Set[dt.date]:
    """證交所開休市日期表 → 休市日集合（排除「開始交易日」「最後交易日」）。"""
    closed = set()
    for row in data.get('data') or []:
        if len(row) < 2:
            continue
        date_str, name = row[0], row[1]
        if any(marker in name for marker in _TRADING_DAY_MARKERS):
            continue
        try:
            closed.add(dt.date.fromisoformat(date_str))
        except ValueError:
            continue
    return closed


def is_trading_day(day: dt.date, holidays: Set[dt.date]) -> bool:
    return day.weekday() < 5 and day not in holidays


def previous_trading_day(day: dt.date, holidays: Set[dt.date]) -> dt.date:
    """day 之前（不含 day）最近的交易日；最多往回找 30 天。"""
    d = day
    for _ in range(30):
        d -= dt.timedelta(days=1)
        if is_trading_day(d, holidays):
            return d
    return day - dt.timedelta(days=1)


# ---------- 抓取 ----------

async def _get_json(session: aiohttp.ClientSession, url: str, **params) -> dict:
    async with session.get(url, params=params or None) as resp:
        resp.raise_for_status()
        # MIS 回應前面有大量空白行、content-type 也不一定是 json，自行解析
        return json.loads((await resp.text()).strip())


async def fetch_indices(session: aiohttp.ClientSession,
                        channels: Sequence[str] = (TAIEX, OTC)) -> List[IndexQuote]:
    data = await _get_json(session, MIS_URL, ex_ch='|'.join(channels), json='1', delay='0')
    return parse_mis(data)


async def fetch_taiex(session: aiohttp.ClientSession) -> Optional[IndexQuote]:
    quotes = await fetch_indices(session, (TAIEX,))
    return quotes[0] if quotes else None


async def fetch_global_quotes(session: aiohttp.ClientSession,
                              symbols: Sequence[str] = GLOBAL_SYMBOLS) -> List[GlobalQuote]:
    data = await _get_json(session, CNYES_QUOTE_URL.format(symbols=','.join(symbols)))
    return parse_cnyes_quotes(data)


async def fetch_news(session: aiohttp.ClientSession, category: str,
                     start: dt.datetime, end: dt.datetime, max_pages: int = 8) -> List[NewsItem]:
    """抓 [start, end] 內某分類的全部新聞（每頁 30 則、新到舊，最多 max_pages 頁）。

    API 的 startAt/endAt 不完全可靠（實測會回傳更早的稿），所以本地再過濾一次，
    並在翻到比 start 更早的稿時停止翻頁。
    """
    items: List[NewsItem] = []
    for page in range(1, max_pages + 1):
        data = await _get_json(
            session, CNYES_NEWS_URL.format(category=category),
            limit='30', page=str(page),
            startAt=str(int(start.timestamp())), endAt=str(int(end.timestamp())),
        )
        batch = parse_cnyes_news(data)
        items += [i for i in batch if start <= i.published <= end]
        reached_start = any(i.published < start for i in batch)
        last_page = int((data.get('items') or {}).get('last_page') or 1)
        if reached_start or not batch or page >= last_page:
            break
    return items


async def fetch_holidays(session: aiohttp.ClientSession, year: int) -> Set[dt.date]:
    data = await _get_json(session, HOLIDAY_URL, date=f'{year}0101', response='json')
    return parse_holidays(data)
