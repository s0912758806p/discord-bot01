#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""".env.example 必須與程式實際讀取的環境變數雙向一致（fail-closed：抓不到就紅）。

- 程式讀的變數 .env.example 一定要列（新增設定忘了寫範例 → 紅）
- .env.example 列的變數程式一定要讀（移除功能忘了刪範例 → 紅）

讀取方式需符合下面的 READERS 之一；新增別的讀法時要一併加進來，否則這個測試會抓不到。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [ROOT / 'main.py', *sorted((ROOT / 'core').glob('*.py')), *sorted((ROOT / 'cmds').glob('*.py'))]

# os.getenv('X')、os.environ.get('X')、env.get('X')、os.environ['X']、
# core/logging.py 的 _int_env('X', ...)、cmds/stock.py StockSettings.from_env 內的 num('X', ...)
READERS = re.compile(
    r"""(?:\bgetenv|\benviron\.get|\benv\.get|\b_int_env|\bnum)\(\s*['"]([A-Z][A-Z0-9_]+)['"]"""
    r"""|\benviron\[\s*['"]([A-Z][A-Z0-9_]+)['"]\s*\]"""
)


def vars_read_by_code() -> set:
    found = set()
    for path in SOURCES:
        for m in READERS.finditer(path.read_text(encoding='utf-8')):
            found.add(m.group(1) or m.group(2))
    return found


def vars_in_example() -> set:
    text = (ROOT / '.env.example').read_text(encoding='utf-8')
    return set(re.findall(r'^([A-Z][A-Z0-9_]+)=', text, re.M))


class TestEnvExample(unittest.TestCase):
    def test_collects_enough_to_be_meaningful(self):
        self.assertGreater(len(vars_read_by_code()), 10)
        self.assertIn('DISCORD_TOKEN', vars_read_by_code())

    def test_every_variable_read_by_code_is_in_example(self):
        self.assertEqual(sorted(vars_read_by_code() - vars_in_example()), [])

    def test_every_example_variable_is_read_by_code(self):
        self.assertEqual(sorted(vars_in_example() - vars_read_by_code()), [])


if __name__ == '__main__':
    unittest.main()
