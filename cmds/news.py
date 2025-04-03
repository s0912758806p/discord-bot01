import discord
import aiohttp
from bs4 import BeautifulSoup
from discord.ext import commands
from core.classes import Cog_Extension
from core.cache import cache

class News(Cog_Extension):
    def __init__(self, bot):
        super().__init__(bot)
        self.session = None
        
    async def cog_load(self):
        # 創建aiohttp會話
        self.session = aiohttp.ClientSession()
        
    async def cog_unload(self):
        # 關閉aiohttp會話
        if self.session is not None:
            await self.session.close()
    
    @commands.command(name="焦點新聞")
    @cache(ttl=600)  # 緩存10分鐘
    async def focus_news(self, ctx):
        """獲取三立新聞網焦點新聞"""
        url = 'https://www.setn.com/ViewAll.aspx?PageGroupID=0'
        
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    await ctx.send(f"獲取新聞失敗，狀態碼: {response.status}")
                    return
                    
                response_text = await response.text()
                
                soup = BeautifulSoup(response_text, 'html.parser')
                
                # 發送一條訊息表示正在處理
                await ctx.send("正在獲取最新焦點新聞...")
                
                # 創建一個空的新聞列表
                news_list = []
                
                # 獲取所有新聞標題
                for headline in soup.find('div', 'NewsList').find_all('h3', 'view-li-title'):
                    if headline.find('a', 'gt'):
                        title = headline.find('a', 'gt').text
                        news_list.append(title)
                
                # 每次發送5條新聞，避免訊息過長
                for i in range(0, min(15, len(news_list)), 5):
                    batch = news_list[i:i+5]
                    message = "\n".join([f"{j+1+i}. {title}" for j, title in enumerate(batch)])
                    await ctx.send(message)
        
        except Exception as e:
            await ctx.send(f"獲取焦點新聞時發生錯誤: {str(e)}")
    
    @commands.command(name="財經新聞")
    @cache(ttl=600)  # 緩存10分鐘
    async def financial_news(self, ctx):
        """獲取財經新聞"""
        url = 'https://ec.ltn.com.tw/list/international'
        
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    await ctx.send(f"獲取新聞失敗，狀態碼: {response.status}")
                    return
                    
                response_text = await response.text()
                
                soup = BeautifulSoup(response_text, 'html.parser')
                
                # 發送一條訊息表示正在處理
                await ctx.send("正在獲取最新財經新聞...")
                
                # 創建一個空的新聞列表
                news_list = []
                
                # 獲取所有新聞標題 (根據網站結構調整選擇器)
                for headline in soup.select('div.list a'):
                    title = headline.get('title')
                    if title:
                        news_list.append(title)
                
                # 每次發送5條新聞，避免訊息過長
                for i in range(0, min(15, len(news_list)), 5):
                    batch = news_list[i:i+5]
                    message = "\n".join([f"{j+1+i}. {title}" for j, title in enumerate(batch)])
                    await ctx.send(message)
        
        except Exception as e:
            await ctx.send(f"獲取財經新聞時發生錯誤: {str(e)}")

async def setup(bot):
    await bot.add_cog(News(bot)) 