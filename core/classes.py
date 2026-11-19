import aiohttp
from discord.ext import commands


class Cog_Extension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def session(self) -> aiohttp.ClientSession:
        """全 bot 共用的 aiohttp session（main.Bot.setup_hook 建立、Bot.close 關閉）。

        cog 不要自行建立 ClientSession：共用連線池，且統一套用 timeout 與 User-Agent。
        """
        return self.bot.http_session
