"""反應圖片指令：`!<指令名>` 回傳對應的圖片（assets/img/）。

新增指令只要在 REACTIONS 加一行；指令由 _make_command 產生並放進 Cog 類別命名空間。
"""
import os

import discord
from discord.ext import commands

from core.assets import img
from core.classes import Cog_Extension

# 指令名 → assets/img/ 底下的檔名
REACTIONS = {
    '我要看到血流成河': 'blood_river.gif',
    '開心到跳起來': 'happy_jump.gif',
    '我的車車': 'my_car.gif',
    '上香': 'rip.gif',
    '呦呼': 'yoo_hoo.gif',
    '沒錢就不要想這些事情': 'no_money_no_think.gif',
    '條件太嚴苛': 'eat_shit.jpg',
    '難以理解': 'tahw.jpg',
    '八方雲吉': '8fangyunji.jpg',
    '槍吉要犯': 'qiangjiyaofan.jpg',
    '是不是想幹人家': 'xiangganrenjia.jpg',
    '不可能': 'bukeneng.jpg',
    '我2D': 'wu2d.jpg',
}


def _make_command(name: str, filename: str) -> commands.Command:
    path = img(filename)

    @commands.command(name=name, help=f'發送「{name}」圖片')
    async def _send_image(self, ctx: commands.Context) -> None:
        if not os.path.exists(path):
            await ctx.send('找不到圖片資源')
            return
        await ctx.send(file=discord.File(path))

    return _send_image


class React(Cog_Extension):
    # CogMeta 在類別建立時收集命名空間裡的 Command，所以要在類別本體內放入
    locals().update({
        f'_react_{i}': _make_command(name, filename)
        for i, (name, filename) in enumerate(REACTIONS.items())
    })


async def setup(bot):
    await bot.add_cog(React(bot))
