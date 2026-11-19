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

    def test_news(self):
        items = market.parse_cnyes_news(load('cnyes_news.json'))
        self.assertEqual(len(items), 5)
        first = items[0]
        self.assertTrue(first.url.startswith('https://news.cnyes.com/news/id/'))
        self.assertEqual(first.published.tzinfo, market.TPE)

    def test_merge_news_dedupes_sorts_and_limits(self):
        t = lambda h: dt.datetime(2026, 11, 19, h, tzinfo=market.TPE)
        a = market.NewsItem('A', 'u1', t(8))
        a_dup = market.NewsItem('A', 'u2', t(9))
        b = market.NewsItem('B', 'u3', t(10))
        c = market.NewsItem('C', 'u4', t(7))
        merged = market.merge_news([[a, c], [a_dup, b]], limit=2)
        self.assertEqual([i.title for i in merged], ['B', 'A'])
        self.assertEqual(merged[1].url, 'u2')  # 保留較新的那則


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
