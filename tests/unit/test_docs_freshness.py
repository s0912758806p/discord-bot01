#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""README 的指令清單必須與程式碼一致（fail-closed：抓不到段落就紅）。"""
import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock

README = (Path(__file__).resolve().parents[2] / 'README.md').read_text(encoding='utf-8')


def _section(title: str) -> str:
    m = re.search(rf'^### {re.escape(title)}.*?$(.*?)(?=^##)', README, re.M | re.S)
    if not m:
        raise AssertionError(f'README 找不到段落: ### {title}')
    return m.group(1)


class TestReadmeCommands(unittest.TestCase):
    def test_react_commands_listed_match_code(self):
        from cmds.react import REACTIONS
        listed = set(re.findall(r'`!([^`\s]+)`', _section('反應圖片指令')))
        self.assertEqual(listed, set(REACTIONS))

    def test_every_prefix_command_is_documented(self):
        from cmds import earthquake, event, main as main_cog, music, news, react, stock
        cogs = [earthquake.Earthquake, event.Event, main_cog.Main, music.Music,
                news.News, react.React, stock.Stock]
        names = {c.name for cog in cogs for c in cog(MagicMock()).get_commands()}
        self.assertGreater(len(names), 20)
        missing = sorted(n for n in names if f'`!{n}' not in README)
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main()
