#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core/volatility.py：門檻穿越與短時間急漲急跌的通知規則。"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from core.market import IndexQuote, TPE
from core.volatility import DOWN, UP, VolatilityDetector

DAY = dt.date(2026, 11, 19)
PREV = 40000.0


def q(pct: float, day: dt.date = DAY) -> IndexQuote:
    price = round(PREV * (1 + pct / 100), 2)
    return IndexQuote('發行量加權股價指數', price, PREV, None, None, None, day, '10:00:00')


def at(minute: int) -> dt.datetime:
    return dt.datetime(2026, 11, 19, 9, 0, tzinfo=TPE) + dt.timedelta(minutes=minute)


def levels_only(alerts):
    return [(a.direction, a.threshold_pct) for a in alerts if a.kind == 'level']


class TestLevelCrossing(unittest.TestCase):
    def setUp(self):
        # rapid_pct 設很大，只測門檻
        self.d = VolatilityDetector(step_pct=1.0, rapid_pct=99)

    def test_first_cross_alerts_once(self):
        self.assertEqual(levels_only(self.d.feed(q(-0.5), at(0))), [])
        self.assertEqual(levels_only(self.d.feed(q(-1.1), at(1))), [(DOWN, 1.0)])
        self.assertEqual(levels_only(self.d.feed(q(-1.5), at(2))), [])
        self.assertEqual(levels_only(self.d.feed(q(-0.8), at(3))), [])
        self.assertEqual(levels_only(self.d.feed(q(-1.2), at(4))), [])  # 回到 -1% 以下不重發

    def test_gap_across_levels_sends_only_highest(self):
        self.assertEqual(levels_only(self.d.feed(q(-2.3), at(0))), [(DOWN, 2.0)])
        self.assertEqual(levels_only(self.d.feed(q(-2.9), at(1))), [])

    def test_exact_threshold_counts(self):
        self.assertEqual(levels_only(self.d.feed(q(1.0), at(0))), [(UP, 1.0)])

    def test_directions_are_independent(self):
        self.assertEqual(levels_only(self.d.feed(q(1.2), at(0))), [(UP, 1.0)])
        self.assertEqual(levels_only(self.d.feed(q(-1.2), at(1))), [(DOWN, 1.0)])

    def test_new_trading_day_resets(self):
        self.d.feed(q(-1.5), at(0))
        self.assertEqual(levels_only(self.d.feed(q(-1.5, DAY + dt.timedelta(days=1)), at(1))),
                         [(DOWN, 1.0)])

    def test_replay_of_2026_11_19_selloff(self):
        """11/19 加權從 40,194 跌到 38,426（約 -4.4%）：應依序發 -1/-2/-3/-4% 各一則。"""
        path = [-0.3, -0.9, -1.2, -1.8, -2.1, -2.6, -3.4, -3.1, -4.1, -4.4, -4.2]
        sent = []
        for i, pct in enumerate(path):
            sent += levels_only(self.d.feed(q(pct), at(i * 20)))
        self.assertEqual(sent, [(DOWN, 1.0), (DOWN, 2.0), (DOWN, 3.0), (DOWN, 4.0)])

    def test_state_file_prevents_resend_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data' / 'state.json'
            first = VolatilityDetector(rapid_pct=99, state_path=path)
            first.feed(q(-2.2), at(0))
            restarted = VolatilityDetector(rapid_pct=99, state_path=path)
            self.assertEqual(levels_only(restarted.feed(q(-2.5), at(1))), [])
            self.assertEqual(levels_only(restarted.feed(q(-3.1), at(2))), [(DOWN, 3.0)])

    def test_corrupt_state_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            path.write_text('{not json', encoding='utf-8')
            d = VolatilityDetector(rapid_pct=99, state_path=path)
            self.assertEqual(levels_only(d.feed(q(-1.1), at(0))), [(DOWN, 1.0)])


class TestRapidMove(unittest.TestCase):
    def setUp(self):
        # step_pct 設很大，只測急漲急跌
        self.d = VolatilityDetector(step_pct=99, rapid_pct=0.7,
                                    rapid_window=dt.timedelta(minutes=5),
                                    rapid_cooldown=dt.timedelta(minutes=15))

    def rapid(self, pct, minute):
        return [(a.direction, round(a.move_pct, 2)) for a in self.d.feed(q(pct), at(minute))
                if a.kind == 'rapid']

    def test_drop_from_window_high_triggers(self):
        self.assertEqual(self.rapid(0.0, 0), [])
        self.assertEqual(self.rapid(0.3, 2), [])   # 先漲到高點
        hits = self.rapid(-0.5, 4)                 # 從高點跌 ~0.8%
        self.assertEqual([h[0] for h in hits], [DOWN])
        self.assertGreaterEqual(hits[0][1], 0.7)

    def test_slow_drift_does_not_trigger(self):
        for i, pct in enumerate([0, -0.3, -0.6, -0.9, -1.2]):  # 每 4 分鐘跌 0.3%
            self.assertEqual(self.rapid(pct, i * 4), [])

    def test_cooldown_per_direction(self):
        self.rapid(0.0, 0)
        self.assertEqual([h[0] for h in self.rapid(-0.8, 1)], [DOWN])
        self.rapid(-0.8, 3)
        self.assertEqual(self.rapid(-1.6, 5), [])              # 冷卻中
        self.assertEqual([h[0] for h in self.rapid(-0.6, 7)], [UP])  # 反方向不受冷卻影響
        self.rapid(-0.6, 12)
        self.assertEqual([h[0] for h in self.rapid(-1.5, 17)], [DOWN])  # 冷卻結束

    def test_message_mentions_move_and_window(self):
        self.d.feed(q(0.0), at(0))
        alert = [a for a in self.d.feed(q(-1.0), at(3)) if a.kind == 'rapid'][0]
        msg = alert.message()
        self.assertIn('5 分鐘內急跌', msg)
        self.assertIn('-1.00%', msg)


class TestMessages(unittest.TestCase):
    def test_level_message(self):
        d = VolatilityDetector(rapid_pct=99)
        msg = d.feed(q(-2.1), at(0))[0].message()
        self.assertIn('跌幅突破 2%', msg)
        self.assertIn('-2.10%', msg)
        self.assertIn('🔻', msg)


if __name__ == '__main__':
    unittest.main()
