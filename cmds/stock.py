import discord
import aiohttp
import twstock
import datetime
from bs4 import BeautifulSoup
from discord.ext import commands
from core.classes import Cog_Extension
from core.cache import cache
from core.config import load_config

# 載入配置
jData = load_config('setting.json')

class Stock(Cog_Extension):
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
            
    @commands.command()
    @cache(ttl=300)  # 緩存5分鐘
    async def twii(self, ctx):
        """獲取台灣加權指數資訊"""
        url = 'https://invest.cnyes.com/index/TWS/TSE01'
        
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    await ctx.send(f"獲取數據失敗，狀態碼: {response.status}")
                    return
                    
                response_text = await response.text()
                
                soup = BeautifulSoup(response_text, 'html.parser')
                
                twiiTitle = soup.select('.header_second')[0].text
                twiiDateNow = soup.select('.header-time .jsx-2214436525')[0].text
                twiiIndex = soup.select('.header-info .info-price .info-lp span')[0].text
                twiiUpDownIndex = soup.select('.header-info .info-change .change-net span')[0].text
                twiiUpDownPercent = soup.select('.header-info .info-change .change-percent span')[0].text
                
                twiiBuySellTitle = soup.select('.data-block .block-title')[0].text
                twiiBuySellValue = soup.select('.data-block .block-value')[0].text
                twiiToDayHeighLowTitle = soup.select('.data-block .block-title')[1].text
                twiiToDayHeighLowValue = soup.select('.data-block .block-value')[1].text
                twii52HeighLowTitle = soup.select('.data-block .block-title')[2].text
                twii52HeighLowValue = soup.select('.data-block .block-value')[2].text
                
                await ctx.send(twiiTitle + '\n' + twiiDateNow + '\n' +
                              '當前指數: ' + str(twiiIndex) + '\n' + '漲跌點: ' +
                              str(twiiUpDownIndex) + '\n' + '漲跌百分比: ' +
                              str(twiiUpDownPercent) + '\n' +
                              twiiBuySellTitle + ': ' + twiiBuySellValue +
                              '\n' + twiiToDayHeighLowTitle + ': ' +
                              twiiToDayHeighLowValue + '\n' +
                              twii52HeighLowTitle + ': ' +
                              twii52HeighLowValue)
        except Exception as e:
            await ctx.send(f"獲取台股指數時發生錯誤: {str(e)}")
            
    @commands.command()
    @cache(ttl=300)  # 緩存5分鐘
    async def tws(self, ctx, stock_id: str = None):
        """獲取特定股票資訊"""
        if stock_id is None:
            await ctx.send("請提供股票代碼，例如: !tws 2330")
            return
            
        try:
            stock = twstock.realtime.get(stock_id)
            
            if stock['success']:
                stockInfo = list(stock['info'].values())
                stockRealtime = list(stock['realtime'].values())
                
                await ctx.send('股票代號:\u0020' + stockInfo[0] + '\n' +
                              '股票名:\u0020' + stockInfo[2] + '\n' +
                              '最後揭示買價:\u0020' + stockRealtime[3][0][:-2] +
                              '\n' + '最後揭示買量:\u0020' +
                              stockRealtime[4][0] + '\n' +
                              '最後揭示賣價:\u0020' + stockRealtime[5][0][:-2] +
                              '\n' + '最後揭示賣量:\u0020' +
                              stockRealtime[6][0] + '\n' + '成交量:\u0020' +
                              stockRealtime[1] + '\n' + '累積成交量:\u0020' +
                              stockRealtime[2] + '\n' + '開盤價:\u0020' +
                              stockRealtime[7][:-2] + '\n' +
                              '盤中最高價:\u0020' + stockRealtime[8][:-2] +
                              '\n' + '盤中最低價:\u0020' +
                              stockRealtime[9][:-2] + '\n' +
                              '收盤價:\u0020' + stockRealtime[0][:-2])
            else:
                await ctx.send(f"無法獲取股票 {stock_id} 的數據")
        except Exception as e:
            await ctx.send(f"獲取股票信息時發生錯誤: {str(e)}")

async def setup(bot):
    await bot.add_cog(Stock(bot)) 