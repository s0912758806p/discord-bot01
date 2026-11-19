#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core/market.py 的解析測試。fixture 是 2026-11-19 實際錄下的 API 回應（tests/test_data/market/）。"""
import datetime as dt
import json
import unittest
from pathlib import Path

from core import market

FIXTURES = Path(__file__).resolve().parents[1] / 'test_data' / 'market'


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class TestParseMis(unittest.TestCase):
    def test_parses_taiex_and_otc(self):
        quotes = market.parse_mis(load('mis_index.json'))
        self.assertEqual([q.name for q in quotes], ['發行量加權股價指數', '櫃買指數'])
        taiex = quotes[0]
        self.assertEqual(taiex.date, dt.date(2026, 11, 19))
        self.assertAlmostEqual(taiex.price, 38426.89)
        self.assertAlmostEqual(taiex.prev_close, 40194.91)
        self.assertAlmostEqual(taiex.change, 38426.89 - 40194.91)
        self.assertAlmostEqual(taiex.change_pct, -4.3987, places=3)

    def test_skips_quote_without_trade_price(self):
        """開盤前 MIS 的成交價 z 是 '-'，不能當成 0 或拋錯。"""
        data = load('mis_index.json')
        data['msgArray'][0]['z'] = '-'
        self.assertEqual([q.name for q in market.parse_mis(data)], ['櫃買指數'])


class TestParseCnyes(unittest.TestCase):
    def test_global_quotes(self):
        quotes = market.parse_cnyes_quotes(load('cnyes_quotes.json'))
        names = [q.name for q in quotes]
        self.assertEqual(len(quotes), len(market.GLOBAL_SYMBOLS))
        self.assertIn('道瓊指數', names)
        self.assertIn('台積電ADR', names)
        dji = quotes[names.index('道瓊指數')]
        self.assertAlmostEqual(dji.price, 50198.17)
        self.assertAlmostEqual(dji.change, -561.25)
        self.assertAlmostEqual(dji.change_pct, -1.11)

    def test_news_skips_outsourced_items(self):
        data = load('cnyes_news.json')
        raw = data['items']['data']
        outsourced = sum(1 for n in raw if n['isOutsource'])
        self.assertGreater(outsourced, 0)  # fixture 確實含外包稿，否則這個測試沒意義
        items = market.parse_cnyes_news(data)
        self.assertEqual(len(items), len(raw) - outsourced)
        first = items[0]
        self.assertTrue(first.url.startswith('https://news.cnyes.com/news/id/'))
        self.assertEqual(first.published.tzinfo, market.TPE)

    def test_merge_news_dedupes_keeping_newer(self):
        t = lambda h: dt.datetime(2026, 11, 19, h, tzinfo=market.TPE)
        a = market.NewsItem('A', 'u1', t(8))
        a_dup = market.NewsItem('A', 'u2', t(9))
        b = market.NewsItem('B', 'u3', t(10))
        merged = market.merge_news([[a], [a_dup, b]], limit=5)
        self.assertEqual([(i.title, i.url) for i in merged], [('B', 'u3'), ('A', 'u2')])

    def test_merge_news_spreads_over_time_window(self):
        """只取最新幾則會全是清晨新聞；要沿時間軸平均挑，涵蓋最早與最新。"""
        t0 = dt.datetime(2026, 11, 18, 8, 30, tzinfo=market.TPE)
        items = [market.NewsItem(f'N{h}', f'u{h}', t0 + dt.timedelta(hours=h)) for h in range(24)]
        merged = market.merge_news([items], limit=4)
        self.assertEqual([i.title for i in merged], ['N23', 'N15', 'N8', 'N0'])
        self.assertEqual(market.merge_news([items], limit=0), [])
        self.assertEqual(len(market.merge_news([items[:3]], limit=8)), 3)


class FakeResponse:
    def __init__(self, payload):
        self._text = json.dumps(payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    async def text(self):
        return self._text


class FakeSession:
    """依序回傳 payloads，並記錄每次請求的 params。"""
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return FakeResponse(self.payloads.pop(0))


def news_page(items, last_page):
    return {'items': {'last_page': last_page, 'data': [
        {'newsId': i, 'title': f'T{i}', 'publishAt': int(ts.timestamp()), 'isOutsource': 0}
        for i, ts in items
    ]}}


class TestFetchNews(unittest.IsolatedAsyncioTestCase):
    async def test_filters_window_and_stops_paging_past_start(self):
        """API 的 startAt 不可靠：本地要濾掉窗外的稿，並在翻到窗外時停止翻頁。"""
        t = lambda d, h: dt.datetime(2026, 11, d, h, tzinfo=market.TPE)
        start, end = t(18, 8), t(19, 8)
        session = FakeSession([
            news_page([(1, t(19, 7)), (2, t(18, 20))], last_page=5),
            news_page([(3, t(18, 9)), (4, t(18, 5))], last_page=5),   # 4 在窗外
            news_page([(5, t(18, 1))], last_page=5),                  # 不應被請求
        ])
        items = await market.fetch_news(session, 'tw_stock', start, end)
        self.assertEqual([i.title for i in items], ['T1', 'T2', 'T3'])
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1][1]['page'], '2')


class TestTradingCalendar(unittest.TestCase):
    def setUp(self):
        self.holidays = market.parse_holidays(load('twse_holidays_2026.json'))

    def test_holidays_exclude_trading_day_markers(self):
        """日期表也列「開始交易日」「最後交易日」，那些天照常交易。"""
        self.assertIn(dt.date(2026, 12, 25), self.holidays)        # 行憲紀念日
        self.assertIn(dt.date(2026, 2, 12), self.holidays)         # 市場無交易
        self.assertNotIn(dt.date(2026, 1, 2), self.holidays)       # 國曆新年開始交易日
        self.assertNotIn(dt.date(2026, 2, 11), self.holidays)      # 農曆春節前最後交易日
        self.assertNotIn(dt.date(2026, 2, 23), self.holidays)      # 農曆春節後開始交易日

    def test_is_trading_day(self):
        self.assertTrue(market.is_trading_day(dt.date(2026, 11, 19), self.holidays))   # 週四
        self.assertFalse(market.is_trading_day(dt.date(2026, 11, 21), self.holidays))  # 週六
        self.assertFalse(market.is_trading_day(dt.date(2026, 12, 25), self.holidays))  # 週五休市

    def test_previous_trading_day_skips_weekend_and_holidays(self):
        prev = lambda d: market.previous_trading_day(d, self.holidays)
        self.assertEqual(prev(dt.date(2026, 11, 23)), dt.date(2026, 11, 20))  # 週一 → 上週五
        self.assertEqual(prev(dt.date(2026, 12, 28)), dt.date(2026, 12, 24))  # 跳過 12/25 與週末
        self.assertEqual(prev(dt.date(2026, 2, 23)), dt.date(2026, 2, 11))    # 春節長假


if __name__ == '__main__':
    unittest.main()
