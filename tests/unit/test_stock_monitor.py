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
