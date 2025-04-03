import discord
from discord.ext import commands
from core.classes import Cog_Extension
from core.config import load_config

# 載入配置文件
jData = load_config('setting.json')

class React(Cog_Extension):
    def __init__(self, bot):
        super().__init__(bot)
        self.images = jData.get('IMAGE', [])
        
    @commands.command(name="我要看到血流成河")
    async def blood_river(self, ctx):
        """發送血流成河的圖片"""
        if not self.images or len(self.images) < 1:
            await ctx.send("找不到圖片資源")
            return
        
        img = discord.File(self.images[0])
        await ctx.send(file=img)

    @commands.command(name="開心到跳起來")
    async def happy_jump(self, ctx):
        """發送開心跳起來的圖片"""
        if not self.images or len(self.images) < 2:
            await ctx.send("找不到圖片資源")
            return
            
        img = discord.File(self.images[1])
        await ctx.send(file=img)

    @commands.command(name="我的車車")
    async def my_car(self, ctx):
        """發送我的車車的圖片"""
        if not self.images or len(self.images) < 3:
            await ctx.send("找不到圖片資源")
            return
            
        img = discord.File(self.images[2])
        await ctx.send(file=img)

    @commands.command(name="上香")
    async def rip(self, ctx):
        """發送上香的圖片"""
        if not self.images or len(self.images) < 4:
            await ctx.send("找不到圖片資源")
            return
            
        img = discord.File(self.images[3])
        await ctx.send(file=img)

    @commands.command(name="呦呼")
    async def yoo_hoo(self, ctx):
        """發送呦呼的圖片"""
        if not self.images or len(self.images) < 5:
            await ctx.send("找不到圖片資源")
            return
            
        img = discord.File(self.images[4])
        await ctx.send(file=img)

    @commands.command(name="沒錢就不要想這些事情")
    async def no_money_no_think(self, ctx):
        """發送沒錢就不要想這些事情的圖片"""
        if not self.images or len(self.images) < 6:
            await ctx.send("找不到圖片資源")
            return
            
        img = discord.File(self.images[5])
        await ctx.send(file=img)

    @commands.command(name="條件太嚴苛")
    async def eat_shit(self, ctx):
        """發送條件太嚴苛的圖片"""
        if not self.images or len(self.images) < 7:
            await ctx.send("找不到圖片資源")
            return
            
        img = discord.File(self.images[6])
        await ctx.send(file=img)

    @commands.command(name="難以理解")
    async def tahw(self, ctx):
        """發送難以理解的圖片"""
        if not self.images or len(self.images) < 8:
            await ctx.send("找不到圖片資源")
            return
            
        img = discord.File(self.images[7])
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
