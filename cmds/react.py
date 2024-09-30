import discord
import json

from discord.ext import commands
from core.classes import Cog_Extension

# 'r' = read
with open('setting.json', 'r', encoding='utf8') as jFile:
    jData = json.load(jFile)


class React(Cog_Extension):
    @commands.command()
    async def 我要看到血流成河(self, ctx):
        img = discord.File(jData['IMAGE'][0])

        await ctx.send(file=img)

    @commands.command()
    async def 開心到跳起來(self, ctx):
        img = discord.File(jData['IMAGE'][1])

        await ctx.send(file=img)

    @commands.command()
    async def 我的車車(self, ctx):
        img = discord.File(jData['IMAGE'][2])

        await ctx.send(file=img)

    @commands.command()
    async def 上香(self, ctx):
        img = discord.File(jData['IMAGE'][3])

        await ctx.send(file=img)

    @commands.command()
    async def 呦呼(self, ctx):
        img = discord.File(jData['IMAGE'][4])

        await ctx.send(file=img)

    @commands.command()
    async def 沒錢就不要想這些事情(self, ctx):
        img = discord.File(jData['IMAGE'][5])

        await ctx.send(file=img)

    @commands.command()
    async def 條件太嚴苛(self, ctx):
        img = discord.File(jData['IMAGE'][6])

        await ctx.send(file=img)

    @commands.command()
    async def 難以理解(self, ctx):
        img = discord.File(jData['IMAGE'][7])

        await ctx.send(file=img)

    @commands.command()
    async def 八方雲吉(self, ctx):
        img = discord.File(jData['IMAGE'][8])

        await ctx.send(file=img)

    @commands.command()
    async def 槍吉要犯(self, ctx):
        img = discord.File(jData['IMAGE'][9])

        await ctx.send(file=img)

    @commands.command()
    async def 是不是想幹人家(self, ctx):
        img = discord.File(jData['IMAGE'][10])

        await ctx.send(file=img)

    @commands.command()
    async def 不可能(self, ctx):
        img = discord.File(jData['IMAGE'][11])

        await ctx.send(file=img)

    @commands.command()
    async def 我2D(self, ctx):
        img = discord.File(jData['IMAGE'][12])

        await ctx.send(file=img)


async def setup(bot):
    await bot.add_cog(React(bot))
