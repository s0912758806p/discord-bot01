import discord
from discord.ext import commands
from core.classes import Cog_Extension

class Music(Cog_Extension):
    @commands.command()
    async def join(self, ctx):
        """加入使用者的語音頻道"""
        if ctx.author.voice is None:
            await ctx.send("你沒有連接到語音頻道！")
            return
        
        voice_channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await voice_channel.connect()
        else:
            await ctx.voice_client.move_to(voice_channel)
        
        await ctx.send(f"已加入 {voice_channel.name} 頻道")
    
    @commands.command()
    async def leave(self, ctx):
        """離開語音頻道"""
        if ctx.voice_client is not None:
            await ctx.voice_client.disconnect()
            await ctx.send("已離開語音頻道")
        else:
            await ctx.send("我目前沒有連接到語音頻道")

async def setup(bot):
    await bot.add_cog(Music(bot)) 