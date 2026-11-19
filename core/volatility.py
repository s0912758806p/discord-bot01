"""
大盤急劇波動偵測（純邏輯，不依賴 Discord／網路）。

每次輪詢把最新的 IndexQuote 餵給 VolatilityDetector.feed()，回傳要發的 Alert：

1. 門檻穿越：相對昨收的漲跌幅「首次」突破 step、2×step、3×step…%（預設 1%），
   每個方向每個門檻一天只發一次；跳空直接越過多個門檻時只發最高的那一則。
2. 短時間急漲急跌：現價相對最近 rapid_window（預設 5 分鐘）內的最高／最低價
   變動達 rapid_pct（預設 0.7%）就發，同方向 rapid_cooldown（預設 15 分鐘）內不重發。

換交易日（quote.date 改變）自動重置。門檻狀態可存檔（state_path），
bot 當天重啟後不會把已通知過的門檻再發一次。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

from core.market import IndexQuote

log = logging.getLogger('discord_bot')

UP, DOWN = 1, -1


@dataclass(frozen=True)
class Alert:
    kind: str           # 'level' | 'rapid'
    direction: int      # UP / DOWN
    quote: IndexQuote
    threshold_pct: float            # level：突破的門檻；rapid：觸發條件
    move_pct: float = 0.0           # rapid：窗內實際變動幅度（正數）
    from_price: float = 0.0         # rapid：窗內的高／低點
    window_min: int = 0             # rapid：窗長（分鐘）

    def message(self) -> str:
        q = self.quote
        arrow = '🔺' if q.change >= 0 else '🔻'
        today = f'{q.price:,.2f}（{arrow}{abs(q.change):,.2f}，{q.change_pct:+.2f}%）'
        if self.kind == 'level':
            icon, word = ('📈', '漲幅') if self.direction == UP else ('📉', '跌幅')
            return f'{icon} **{q.name}{word}突破 {self.threshold_pct:g}%**\n目前 {today}　{q.time}'
        icon, word = ('🚀', '急漲') if self.direction == UP else ('⚡', '急跌')
        return (f'{icon} **{q.name} {self.window_min} 分鐘內{word} {self.move_pct:.2f}%**\n'
                f'{self.from_price:,.2f} → {q.price:,.2f}　今日 {q.change_pct:+.2f}%　{q.time}')


class VolatilityDetector:
    def __init__(self, step_pct: float = 1.0, rapid_pct: float = 0.7,
                 rapid_window: dt.timedelta = dt.timedelta(minutes=5),
                 rapid_cooldown: dt.timedelta = dt.timedelta(minutes=15),
                 state_path: Optional[Path] = None):
        if step_pct <= 0 or rapid_pct <= 0:
            raise ValueError('step_pct 與 rapid_pct 必須大於 0')
        self.step_pct = step_pct
        self.rapid_pct = rapid_pct
        self.rapid_window = rapid_window
        self.rapid_cooldown = rapid_cooldown
        self.state_path = state_path

        self.date: Optional[dt.date] = None
        self.levels: Dict[int, int] = {UP: 0, DOWN: 0}
        self._window: Deque[Tuple[dt.datetime, float]] = deque()
        self._last_rapid: Dict[int, dt.datetime] = {}
        self._load_state()

    # ---------- 狀態 ----------

    def _reset(self, day: dt.date) -> None:
        self.date = day
        self.levels = {UP: 0, DOWN: 0}
        self._window.clear()
        self._last_rapid.clear()

    def _load_state(self) -> None:
        if not self.state_path or not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding='utf-8'))
            self.date = dt.date.fromisoformat(data['date'])
            self.levels = {UP: int(data['up_level']), DOWN: int(data['down_level'])}
        except (OSError, ValueError, KeyError, TypeError) as e:
            log.warning('無法讀取波動通知狀態檔 %s，從頭開始：%s', self.state_path, e)
            self.date, self.levels = None, {UP: 0, DOWN: 0}

    def _save_state(self) -> None:
        if not self.state_path or self.date is None:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps({
                'date': self.date.isoformat(),
                'up_level': self.levels[UP], 'down_level': self.levels[DOWN],
            }), encoding='utf-8')
        except OSError as e:
            log.warning('無法寫入波動通知狀態檔 %s：%s', self.state_path, e)

    # ---------- 偵測 ----------

    def feed(self, quote: IndexQuote, now: dt.datetime) -> List[Alert]:
        if quote.date != self.date:
            self._reset(quote.date)
            self._save_state()
        alerts = []
        level_alert = self._check_level(quote)
        if level_alert:
            alerts.append(level_alert)
        rapid_alert = self._check_rapid(quote, now)
        if rapid_alert:
            alerts.append(rapid_alert)
        return alerts

    def _check_level(self, quote: IndexQuote) -> Optional[Alert]:
        pct = quote.change_pct
        direction = UP if pct > 0 else DOWN
        # 1e-9：避免 2.0 / 1.0 因浮點誤差算成 1.999…
        level = math.floor(abs(pct) / self.step_pct + 1e-9)
        if level <= self.levels[direction]:
            return None
        self.levels[direction] = level
        self._save_state()
        return Alert('level', direction, quote, threshold_pct=round(level * self.step_pct, 4))

    def _check_rapid(self, quote: IndexQuote, now: dt.datetime) -> Optional[Alert]:
        while self._window and now - self._window[0][0] > self.rapid_window:
            self._window.popleft()
        prices = [p for _, p in self._window]
        self._window.append((now, quote.price))
        if not prices:
            return None

        high, low = max(prices), min(prices)
        candidates = [
            (DOWN, (high - quote.price) / high * 100, high),
            (UP, (quote.price - low) / low * 100, low),
        ]
        for direction, move, base in candidates:
            if move + 1e-9 < self.rapid_pct:
                continue
            last = self._last_rapid.get(direction)
            if last is not None and now - last < self.rapid_cooldown:
                continue
            self._last_rapid[direction] = now
            return Alert('rapid', direction, quote, threshold_pct=self.rapid_pct,
                         move_pct=move, from_price=base,
                         window_min=int(self.rapid_window.total_seconds() // 60))
        return None
