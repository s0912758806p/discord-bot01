#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
針對實際出過的 bug 的回歸測試。每個測試的 docstring 說明它擋住的是哪個 bug。
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_msg(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.author.bot = False
    msg.author.nick = None
    msg.author.name = "tester"
    msg.channel.name = "general"
    msg.channel.send = AsyncMock()
    return msg


def _make_event_cog():
    from cmds.event import Event
    bot = MagicMock()
    bot.process_commands = AsyncMock()
    return Event(bot), bot


class TestEventOnMessage(unittest.IsolatedAsyncioTestCase):
    async def test_on_message_does_not_process_commands_again(self):
        """commands.Bot 預設 on_message 已處理指令；cog listener 再呼叫一次會讓每個指令回兩次。"""
        cog, bot = _make_event_cog()
        await cog.on_message(_make_msg("!ping"))
        bot.process_commands.assert_not_awaited()

    async def test_plain_chat_message_opens_no_files(self):
        """固定回應表曾在每則訊息都建立 discord.File（開檔），未送出的檔案 handle 會洩漏。"""
        cog, _ = _make_event_cog()
        with patch("cmds.event.discord.File") as file_cls:
            await cog.on_message(_make_msg("今天午餐吃什麼"))
        file_cls.assert_not_called()

    async def test_matching_fixed_response_sends_one_file(self):
        cog, _ = _make_event_cog()
        msg = _make_msg("你不懂啦")
        with patch("cmds.event.discord.File") as file_cls:
            await cog.on_message(msg)
        file_cls.assert_called_once()
        msg.channel.send.assert_awaited_once()

    async def test_matching_text_response(self):
        cog, _ = _make_event_cog()
        msg = _make_msg("滾")
        await cog.on_message(msg)
        msg.channel.send.assert_awaited_once_with("嚶嚶嚶")


class TestBotStartup(unittest.IsolatedAsyncioTestCase):
    async def test_extensions_load_in_setup_hook_not_on_ready(self):
        """在 on_ready 載入擴充時，斷線重連會重觸發 on_ready → ExtensionAlreadyLoaded。"""
        import main
        bot = main.create_bot()
        bot.load_extension = AsyncMock()
        with patch("aiohttp.ClientSession"):
            await bot.setup_hook()
        loaded = {c.args[0] for c in bot.load_extension.await_args_list}
        self.assertIn("cmds.event", loaded)
        self.assertNotIn("cmds.module_connector", loaded)

        bot.load_extension.reset_mock()
        with patch.object(type(bot), "user", new=MagicMock()):
            await bot.on_ready()
        bot.load_extension.assert_not_awaited()

    def test_importing_main_does_not_exit_without_token(self):
        """main.py 在 import 時檢查 token 並 sys.exit，導致無法測試。"""
        import importlib
        import main
        with patch.dict("os.environ", {"DISCORD_TOKEN": ""}):
            importlib.reload(main)  # 不應拋 SystemExit


class TestStock(unittest.IsolatedAsyncioTestCase):
    async def test_tws_runs_blocking_twstock_off_the_event_loop(self):
        """twstock.realtime.get 是同步 requests 呼叫，直接在 coroutine 內呼叫會卡住整個 bot。"""
        from cmds.stock import Stock
        cog = Stock(MagicMock())
        ctx = MagicMock()
        ctx.send = AsyncMock()
        with patch("cmds.stock.asyncio.to_thread", new=AsyncMock(return_value={"success": False})) as to_thread:
            await Stock.tws.callback(cog, ctx, "2330")
        to_thread.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
