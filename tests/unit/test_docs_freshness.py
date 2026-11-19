#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""README 的指令清單必須與程式碼雙向一致（fail-closed：抓不到段落就紅）。

- 程式有的指令 README 一定要列（新增指令忘了寫文件 → 紅）
- README 列的 `!指令` 程式一定要有（移除指令忘了刪文件 → 紅）
"""
import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock

README = (Path(__file__).resolve().parents[2] / 'README.md').read_text(encoding='utf-8')

# 不經 @commands.command 或完全比對表、而是在 Event.on_message / process_default_responses
# 以前綴或特殊比對處理的指令，以及 discord.py 內建的 help。
PREFIX_DISPATCHED = ('今日運勢-', '鬆餅混搭')
BUILTIN = {'help'}


def _section(title: str, level: int = 3) -> str:
    hashes = '#' * level
    m = re.search(rf'^{hashes} {re.escape(title)}.*?$(.*?)(?=^#{{1,{level}}} )', README, re.M | re.S)
    if not m:
        raise AssertionError(f'README 找不到段落: {hashes} {title}')
    return m.group(1)


def _prefix_command_names() -> set:
    from cmds import event, main as main_cog, music, react, stock
    cogs = [event.Event, main_cog.Main, music.Music, react.React, stock.Stock]
    return {c.name for cog in cogs for c in cog(MagicMock()).get_commands()}


def _all_known_triggers() -> set:
    """所有會被 bot 回應的 `!` 觸發詞（去掉前綴 `!`）。"""
    from cmds.event import Event
    cog = Event(MagicMock())
    exact = set(cog.command_handlers) | set(cog.fixed_responses)
    return _prefix_command_names() | BUILTIN | {t[1:] for t in exact if t.startswith('!')}


class TestReadmeCommands(unittest.TestCase):
    def test_react_commands_listed_match_code(self):
        from cmds.react import REACTIONS
        listed = set(re.findall(r'`!([^`\s]+)`', _section('反應圖片指令')))
        self.assertEqual(listed, set(REACTIONS))

    def test_every_prefix_command_is_documented(self):
        names = _prefix_command_names()
        self.assertGreater(len(names), 15)
        missing = sorted(n for n in names if f'`!{n}' not in README)
        self.assertEqual(missing, [])

    def test_every_documented_command_exists(self):
        """README 指令列表裡的每個 `!xxx` 都要對得到程式；移除功能時文件不能留著。"""
        listed = set(re.findall(r'`!([^`\s<]+)', _section('指令列表', level=2)))
        self.assertGreater(len(listed), 20)  # fail-closed：確認真的有抓到
        known = _all_known_triggers()
        stale = sorted(
            n for n in listed
            if n not in known and not n.startswith(PREFIX_DISPATCHED)
        )
        self.assertEqual(stale, [])


if __name__ == '__main__':
    unittest.main()
