#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Bot 進入點。

- 日誌設定集中在 core/logging.py，這裡只取用 logger。
- 指令模組（cmds/*.py）在 setup_hook 載入：只會在登入前執行一次，
  不像 on_ready 會在斷線重連時重複觸發。
- 全 bot 共用一個 aiohttp session（bot.http_session，cog 以 self.session 取用），
  帶 HTTP_TIMEOUT 秒的總逾時與瀏覽器 User-Agent，於 Bot.close() 關閉。
- import 本模組不會檢查 token 或結束程式；只有 `python main.py` 才會。
"""

import os
import sys
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

from core.logging import logger  # noqa: E402  (需在 load_dotenv 之後，才吃得到 LOG_LEVEL)

CMDS_DIR = Path(__file__).parent / 'cmds'
PREFIX = os.getenv('COMMAND_PREFIX', '!')
HTTP_TIMEOUT = float(os.getenv('HTTP_TIMEOUT', '15'))
# 新聞/天氣/籤詩網站會擋掉 aiohttp 預設的 User-Agent
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'
)


def build_intents() -> discord.Intents:
    """只開需要的 intents：message_content（讀指令/關鍵字）與 members（成員加入/離開通知）。"""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    return intents


class Bot(commands.Bot):
    http_session: aiohttp.ClientSession

    async def setup_hook(self) -> None:
        self.http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            headers={'User-Agent': USER_AGENT},
        )
        await load_extensions(self)

    async def close(self) -> None:
        await super().close()  # 先卸載 cog，再關 session
        session = getattr(self, 'http_session', None)
        if session is not None and not session.closed:
            await session.close()

    async def on_ready(self) -> None:
        logger.info('機器人 %s 已連接到 Discord!', self.user)


async def load_extensions(bot: commands.Bot) -> None:
    for path in sorted(CMDS_DIR.glob('*.py')):
        if path.name.startswith('__'):
            continue
        name = f'cmds.{path.stem}'
        try:
            await bot.load_extension(name)
            logger.info('成功加載指令模組: %s', path.name)
        except Exception:
            logger.exception('加載指令模組 %s 時發生錯誤', path.name)


def create_bot() -> Bot:
    return Bot(command_prefix=PREFIX, intents=build_intents())


def main() -> None:
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error('找不到 DISCORD_TOKEN，請檢查 .env 文件')
        sys.exit(1)

    logger.info('正在啟動 Discord 機器人，命令前綴: %s', PREFIX)
    # log_handler=None：沿用 core/logging.py 的設定，不讓 discord.py 再加一組 handler
    create_bot().run(token, log_handler=None)


if __name__ == '__main__':
    main()
