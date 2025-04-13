import os
import logging
import aiohttp
import discord
import asyncio
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from discord.ext import commands, tasks
from core.classes import Cog_Extension
from core.config import load_config

# 設定日誌
logger = logging.getLogger('discord_bot.earthquake')

class Earthquake(Cog_Extension):
    def __init__(self, bot):
        super().__init__(bot)
        self.session = None
        self.earthquake_channel_id = int(os.getenv('EARTHQUAKE_CHANNEL', '0'))
        self.check_interval = 60  # 每分鐘檢查一次
        self.earthquake_url = 'https://www.cwa.gov.tw/V8/C/E/index.html'
        self.last_earthquakes = set()  # 用於存儲已報告的地震ID
        self.max_age_hours = int(os.getenv('EARTHQUAKE_MAX_AGE_HOURS', '24'))
        self.monitor_task = None
        logger.info("地震監測模組初始化完成")
        
    async def cog_load(self):
        # 創建aiohttp會話
        self.session = aiohttp.ClientSession()
        # 啟動地震監測任務
        self.monitor_earthquakes.start()
        logger.info("地震監測任務已啟動")
        
    async def cog_unload(self):
        # 關閉aiohttp會話
        if self.session is not None:
            await self.session.close()
        # 停止地震監測任務
        self.monitor_earthquakes.cancel()
        logger.info("地震監測任務已停止")
    
    @tasks.loop(seconds=60)
    async def monitor_earthquakes(self):
        """定期檢查地震資訊並發送通知"""
        if self.earthquake_channel_id == 0:
            logger.warning("未設置地震通知頻道ID，跳過地震檢查")
            return
            
        try:
            new_earthquakes = await self.fetch_earthquake_data()
            if new_earthquakes:
                channel = self.bot.get_channel(self.earthquake_channel_id)
                if channel:
                    for eq in new_earthquakes:
                        embed = self.create_earthquake_embed(eq)
                        await channel.send(embed=embed)
                        logger.info(f"已發送地震通知: {eq['title']}")
                else:
                    logger.error(f"無法找到地震通知頻道 ID: {self.earthquake_channel_id}")
        except Exception as e:
            logger.error(f"地震監測過程中發生錯誤: {str(e)}")
    
    @monitor_earthquakes.before_loop
    async def before_monitor(self):
        """等待機器人就緒後再開始監測任務"""
        await self.bot.wait_until_ready()
        
    async def fetch_earthquake_data(self):
        """從氣象局網站獲取地震資訊"""
        try:
            async with self.session.get(self.earthquake_url) as response:
                if response.status != 200:
                    logger.error(f"獲取地震數據失敗，狀態碼: {response.status}")
                    return []
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # 取得最近地震列表
                earthquake_table = soup.select_one('table:contains("最近地震列表")')
                if not earthquake_table:
                    logger.warning("未找到地震資料表格")
                    return []
                
                new_earthquakes = []
                # 解析表格獲取地震數據
                rows = earthquake_table.select('tbody tr')
                for row in rows:
                    # 解析每行地震數據
                    cells = row.select('td')
                    if len(cells) < 3:
                        continue
                        
                    eq_id = cells[0].text.strip()
                    max_intensity = cells[1].text.strip()
                    
                    # 獲取詳細資訊連結
                    details_cell = cells[2]
                    details_link = details_cell.select_one('a')
                    if not details_link:
                        continue
                        
                    # 解析地震標題、時間等資訊
                    info_text = details_cell.text.strip()
                    info_parts = info_text.split('\n')
                    
                    if len(info_parts) < 3:
                        continue
                        
                    title = info_parts[0].strip()
                    time_str = info_parts[1].strip()
                    location = info_parts[2].strip() if len(info_parts) > 2 else "未知位置"
                    
                    # 解析時間
                    try:
                        eq_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        # 嘗試其他可能的時間格式
                        try:
                            eq_time = datetime.strptime(time_str, "%Y年%m月%d日 %H時%M分")
                        except ValueError:
                            logger.warning(f"無法解析地震時間: {time_str}")
                            eq_time = datetime.now()
                    
                    # 檢查是否是新地震（不在已報告列表中且在設定的時間範圍內）
                    time_threshold = datetime.now() - timedelta(hours=self.max_age_hours)
                    if eq_id not in self.last_earthquakes and eq_time > time_threshold:
                        earthquake_data = {
                            'id': eq_id,
                            'title': title,
                            'time': eq_time,
                            'location': location,
                            'max_intensity': max_intensity
                        }
                        new_earthquakes.append(earthquake_data)
                        self.last_earthquakes.add(eq_id)
                
                # 保持緩存大小合理
                while len(self.last_earthquakes) > 100:
                    self.last_earthquakes.pop()
                    
                return new_earthquakes
                
        except Exception as e:
            logger.error(f"獲取地震數據時發生錯誤: {str(e)}")
            return []
    
    def create_earthquake_embed(self, earthquake_data):
        """創建地震資訊的嵌入消息"""
        embed = discord.Embed(
            title=f"🚨 地震通報 - {earthquake_data['title']}",
            description=f"發生時間: {earthquake_data['time'].strftime('%Y-%m-%d %H:%M:%S')}",
            color=0xFF5733  # 紅色系表示警報
        )
        
        embed.add_field(name="地震編號", value=earthquake_data['id'], inline=True)
        embed.add_field(name="最大震度", value=earthquake_data['max_intensity'], inline=True)
        embed.add_field(name="發生位置", value=earthquake_data['location'], inline=False)
        
        embed.set_footer(text="資料來源: 中央氣象署")
        embed.timestamp = datetime.now()
        
        return embed
    
    @commands.command(name="地震資訊")
    async def earthquake_info(self, ctx):
        """獲取最新地震資訊"""
        await ctx.send("正在獲取最新地震資訊...")
        
        try:
            async with self.session.get(self.earthquake_url) as response:
                if response.status != 200:
                    await ctx.send(f"獲取地震資訊失敗，狀態碼: {response.status}")
                    return
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # 獲取最近地震列表
                earthquake_table = soup.select_one('table:contains("最近地震列表")')
                if not earthquake_table:
                    await ctx.send("未找到地震資料")
                    return
                
                # 解析表格獲取前5筆地震數據
                rows = earthquake_table.select('tbody tr')[:5]  # 只取前5筆
                
                if not rows:
                    await ctx.send("目前沒有地震資料")
                    return
                
                for row in rows:
                    # 解析每行地震數據
                    cells = row.select('td')
                    if len(cells) < 3:
                        continue
                        
                    eq_id = cells[0].text.strip()
                    max_intensity = cells[1].text.strip()
                    
                    # 獲取詳細資訊
                    details_cell = cells[2]
                    info_text = details_cell.text.strip()
                    info_parts = info_text.split('\n')
                    
                    if len(info_parts) < 2:
                        continue
                        
                    title = info_parts[0].strip()
                    time_str = info_parts[1].strip()
                    location = info_parts[2].strip() if len(info_parts) > 2 else "未知位置"
                    
                    # 創建嵌入消息
                    embed = discord.Embed(
                        title=f"🌋 {title}",
                        description=f"發生時間: {time_str}",
                        color=0xFF5733
                    )
                    
                    embed.add_field(name="地震編號", value=eq_id, inline=True)
                    embed.add_field(name="最大震度", value=max_intensity, inline=True)
                    embed.add_field(name="發生位置", value=location, inline=False)
                    
                    embed.set_footer(text="資料來源: 中央氣象署")
                    
                    await ctx.send(embed=embed)
        
        except Exception as e:
            await ctx.send(f"獲取地震資訊時發生錯誤: {str(e)}")

async def setup(bot):
    await bot.add_cog(Earthquake(bot)) 