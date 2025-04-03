import discord
import asyncio
import aiohttp
import json
import datetime
import os
from typing import Dict, List, Optional, Any, Tuple, Set
from discord.ext import commands, tasks
from core.classes import Cog_Extension
from core.config import load_config, save_config
from core.logging import logger, measure_time
from core.cache import cache
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

class Earthquake(Cog_Extension):
    """地震監測與通知模組"""
    
    category = "資訊"  # 設置模組類別
    max_stored_earthquakes = 100  # 最多儲存的地震ID數量
    
    def __init__(self, bot):
        super().__init__(bot)
        self.session = None
        self.config = load_config('setting.json')
        
        # 優先使用環境變數中的頻道ID，再使用配置文件中的ID
        self.channel_id = int(os.environ.get('EARTHQUAKE_CHANNEL') or self.config.get('CHATROOM01', '0'))
        
        self.last_earthquakes: Set[str] = set()
        self.earthquake_monitoring.start()
        
        # 台灣中央氣象局地震 API
        self.cwb_api_url = os.environ.get('EARTHQUAKE_API_URL') or "https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0016-001"
        # 優先使用環境變數中的API密鑰，環境變數不存在時則使用配置文件中的密鑰
        self.cwb_api_key = os.environ.get('EARTHQUAKE_API_KEY') or self.config.get('CWB_API_KEY', '')
        
        # USGS 地震 API (作為備用)
        self.usgs_api_url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
        
        # 確保配置中有地震紀錄
        if 'LAST_EARTHQUAKES' not in self.config:
            self.config['LAST_EARTHQUAKES'] = []
            save_config('setting.json', self.config)
        else:
            self.last_earthquakes = set(self.config['LAST_EARTHQUAKES'])
            
    async def cog_load(self):
        """加載模組時調用"""
        self.session = aiohttp.ClientSession()
        logger.info("地震監測模組已加載")
        
    async def cog_unload(self):
        """卸載模組時調用"""
        self.earthquake_monitoring.cancel()
        if self.session:
            await self.session.close()
        logger.info("地震監測模組已卸載")
        
    @tasks.loop(minutes=2.0)
    async def earthquake_monitoring(self):
        """每2分鐘檢查一次地震資訊"""
        try:
            # 添加簡單的API呼叫頻率限制，記錄最後呼叫時間
            current_time = datetime.datetime.now()
            last_call_time = getattr(self, 'last_api_call_time', None)
            
            # 如果上次API呼叫在30秒內，則跳過本次呼叫
            if last_call_time and (current_time - last_call_time).total_seconds() < 30:
                logger.info("API呼叫過於頻繁，跳過本次檢查")
                return
                
            self.last_api_call_time = current_time
            
            earthquakes = await self.fetch_taiwan_earthquakes()
            if not earthquakes:
                # 如果中央氣象局 API 無法獲取數據，嘗試使用 USGS API
                earthquakes = await self.fetch_usgs_earthquakes()
                
            if earthquakes:
                await self.process_earthquakes(earthquakes)
        except Exception as e:
            logger.error(f"地震監測過程中發生錯誤: {e}")
            
    @earthquake_monitoring.before_loop
    async def before_earthquake_monitoring(self):
        """等待機器人準備好後再開始監測"""
        await self.bot.wait_until_ready()
        logger.info("地震監測開始運行，頻率: 每2分鐘")
        
    @measure_time
    async def fetch_taiwan_earthquakes(self) -> List[Dict[str, Any]]:
        """從台灣中央氣象局獲取地震資訊"""
        if not self.cwb_api_key:
            logger.warning("未設置中央氣象局 API 密鑰")
            return []
            
        try:
            params = {
                'Authorization': self.cwb_api_key,
                'limit': 10,  # 獲取最近的10筆資料
                'format': 'JSON',
                'timeFrom': (datetime.datetime.now() - datetime.timedelta(hours=12)).strftime('%Y-%m-%dT%H:%M:%S')
            }
            
            async with self.session.get(self.cwb_api_url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"從中央氣象局獲取地震數據失敗，狀態碼: {response.status}")
                    return []
                    
                data = await response.json()
                
                if 'records' not in data or 'earthquake' not in data['records']:
                    return []
                    
                return data['records']['earthquake']
        except Exception as e:
            logger.error(f"獲取台灣地震數據時出錯: {e}")
            return []
            
    @measure_time
    async def fetch_usgs_earthquakes(self) -> List[Dict[str, Any]]:
        """從USGS獲取地震資訊，並過濾台灣區域"""
        try:
            async with self.session.get(self.usgs_api_url) as response:
                if response.status != 200:
                    logger.warning(f"從USGS獲取地震數據失敗，狀態碼: {response.status}")
                    return []
                    
                data = await response.json()
                
                # 過濾亞洲區域的地震
                filtered_earthquakes = []
                for feature in data.get('features', []):
                    coords = feature['geometry']['coordinates']
                    # 台灣經緯度範圍大致為: 經度 120-122，緯度 22-25
                    lon, lat = coords[0], coords[1]
                    if 119 <= lon <= 123 and 21 <= lat <= 26:
                        filtered_earthquakes.append({
                            'earthquakeNo': feature['id'],
                            'reportContent': feature.get('properties', {}).get('title', '未知地震'),
                            'originTime': datetime.datetime.fromtimestamp(
                                feature.get('properties', {}).get('time', 0) / 1000
                            ).strftime('%Y-%m-%d %H:%M:%S'),
                            'magnitudeValue': feature.get('properties', {}).get('mag', 0),
                            'depth': {
                                'value': coords[2],
                                'unit': 'km'
                            },
                            'location': {
                                'coordinateX': lon,
                                'coordinateY': lat
                            },
                            'source': 'USGS'
                        })
                        
                return filtered_earthquakes
        except Exception as e:
            logger.error(f"獲取USGS地震數據時出錯: {e}")
            return []
            
    async def process_earthquakes(self, earthquakes: List[Dict[str, Any]]) -> None:
        """處理地震數據並發送通知"""
        new_earthquake_ids = set()
        
        for eq in earthquakes:
            eq_id = eq.get('earthquakeNo', '')
            if not eq_id:
                continue
                
            new_earthquake_ids.add(eq_id)
            
            # 檢查是否是新地震
            if eq_id not in self.last_earthquakes:
                await self.send_earthquake_alert(eq)
                
        # 更新已知地震清單
        self.last_earthquakes = new_earthquake_ids
        
        # 限制地震ID儲存數量，避免無限增長
        if len(self.last_earthquakes) > self.max_stored_earthquakes:
            self.last_earthquakes = set(list(self.last_earthquakes)[-self.max_stored_earthquakes:])
            
        self.config['LAST_EARTHQUAKES'] = list(self.last_earthquakes)
        save_config('setting.json', self.config)
        
    async def send_earthquake_alert(self, earthquake: Dict[str, Any]) -> None:
        """發送地震警報到頻道"""
        try:
            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                logger.error(f"無法找到頻道 ID: {self.channel_id}")
                return
                
            # 構建訊息
            source = earthquake.get('source', '中央氣象局')
            
            if source == 'USGS':
                # USGS 格式
                embed = discord.Embed(
                    title="🌋 地震警報 [USGS資料]",
                    description=earthquake.get('reportContent', '未知地震事件'),
                    color=self.get_color_by_magnitude(earthquake.get('magnitudeValue', 0))
                )
                
                embed.add_field(name="發生時間", value=earthquake.get('originTime', '未知'), inline=True)
                embed.add_field(name="規模", value=str(earthquake.get('magnitudeValue', '未知')), inline=True)
                embed.add_field(name="深度", value=f"{earthquake.get('depth', {}).get('value', '未知')} km", inline=True)
                
                location = earthquake.get('location', {})
                embed.add_field(name="位置", value=f"經度: {location.get('coordinateX', '未知')}, 緯度: {location.get('coordinateY', '未知')}", inline=False)
                
                map_url = f"https://maps.google.com/maps?q={location.get('coordinateY', 0)},{location.get('coordinateX', 0)}&z=9"
                embed.add_field(name="地圖", value=f"[查看地圖]({map_url})", inline=False)
                
            else:
                # 中央氣象局格式
                embed = discord.Embed(
                    title="🌋 地震警報 [氣象局資料]",
                    description=earthquake.get('reportContent', '未知地震事件'),
                    color=self.get_color_by_magnitude(earthquake.get('earthquakeInfo', {}).get('magnitude', {}).get('magnitudeValue', 0))
                )
                
                embed.add_field(name="地震編號", value=earthquake.get('earthquakeNo', '未知'), inline=True)
                embed.add_field(name="發生時間", value=earthquake.get('originTime', '未知'), inline=True)
                
                magnitude = earthquake.get('earthquakeInfo', {}).get('magnitude', {})
                embed.add_field(name="規模", value=str(magnitude.get('magnitudeValue', '未知')), inline=True)
                
                depth = earthquake.get('earthquakeInfo', {}).get('depth', {})
                embed.add_field(name="深度", value=f"{depth.get('value', '未知')} {depth.get('unit', 'km')}", inline=True)
                
                location = earthquake.get('earthquakeInfo', {}).get('epiCenter', {}).get('location', '未知位置')
                embed.add_field(name="震央", value=location, inline=False)
                
                # 添加地圖資訊
                coord = earthquake.get('earthquakeInfo', {}).get('epiCenter', {}).get('coordinate', {})
                if coord:
                    lon = coord.get('coordinateX', 0)
                    lat = coord.get('coordinateY', 0)
                    map_url = f"https://maps.google.com/maps?q={lat},{lon}&z=9"
                    embed.add_field(name="地圖", value=f"[查看地圖]({map_url})", inline=False)
                    
            embed.set_footer(text=f"資料來源: {source} | 時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            await channel.send(embed=embed)
            logger.info(f"已發送地震警報: {earthquake.get('earthquakeNo', '未知ID')}")
            
        except Exception as e:
            logger.error(f"發送地震警報時出錯: {e}")
            
    def get_color_by_magnitude(self, magnitude: float) -> int:
        """根據地震規模設置顏色"""
        try:
            magnitude = float(magnitude)
            if magnitude >= 7.0:
                return 0xFF0000  # 紅色
            elif magnitude >= 6.0:
                return 0xFF5733  # 橙紅色
            elif magnitude >= 5.0:
                return 0xFFC300  # 橙黃色
            elif magnitude >= 4.0:
                return 0xFFFF00  # 黃色
            else:
                return 0x00FF00  # 綠色
        except (ValueError, TypeError):
            return 0x808080  # 灰色，表示無法解析規模
            
    @commands.command(name="手動地震測試")
    @commands.has_permissions(administrator=True)
    async def manual_earthquake_test(self, ctx):
        """管理員用於測試地震警報的命令"""
        await ctx.send("正在進行地震警報測試...")
        
        test_earthquake = {
            'earthquakeNo': 'TEST-001',
            'reportContent': '這是一條測試地震警報',
            'originTime': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'earthquakeInfo': {
                'magnitude': {
                    'magnitudeValue': 5.6
                },
                'depth': {
                    'value': 10,
                    'unit': 'km'
                },
                'epiCenter': {
                    'location': '台灣台北市附近',
                    'coordinate': {
                        'coordinateX': 121.5,
                        'coordinateY': 25.0
                    }
                }
            },
            'source': '測試資料'
        }
        
        await self.send_earthquake_alert(test_earthquake)
        await ctx.send("地震警報測試完成!")
        
    @manual_earthquake_test.error
    async def manual_earthquake_test_error(self, ctx, error):
        """手動地震測試命令的錯誤處理"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ 你沒有權限執行此命令，需要管理員權限。")
        else:
            await ctx.send(f"❌ 執行命令時出錯: {str(error)}")
            logger.error(f"手動地震測試命令錯誤: {error}")
            
    @commands.command(name="設置地震頻道")
    @commands.has_permissions(administrator=True)
    async def set_earthquake_channel(self, ctx, channel: discord.TextChannel):
        """設置地震警報發送的頻道"""
        self.channel_id = channel.id
        self.config['CHATROOM01'] = str(channel.id)
        save_config('setting.json', self.config)
        
        await ctx.send(f"地震警報頻道已設置為: {channel.mention}")
        logger.info(f"地震警報頻道已更新為: {channel.name} ({channel.id})")
        
    @set_earthquake_channel.error
    async def set_earthquake_channel_error(self, ctx, error):
        """設置地震頻道命令的錯誤處理"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ 你沒有權限執行此命令，需要管理員權限。")
        elif isinstance(error, commands.ChannelNotFound):
            await ctx.send("❌ 找不到指定的頻道。")
        else:
            await ctx.send(f"❌ 執行命令時出錯: {str(error)}")
            logger.error(f"設置地震頻道命令錯誤: {error}")
            
    @commands.command(name="設置氣象局API密鑰")
    @commands.has_permissions(administrator=True)
    async def set_cwb_api_key(self, ctx, api_key: str):
        """設置中央氣象局 API 密鑰"""
        # 為了安全考慮，立即刪除命令消息
        await ctx.message.delete()
        
        try:
            # 更新當前環境變數
            os.environ['EARTHQUAKE_API_KEY'] = api_key
            self.cwb_api_key = api_key
            
            # 更新配置文件
            self.config['CWB_API_KEY'] = api_key
            save_config('setting.json', self.config)
            
            # 將API密鑰寫入.env文件
            env_path = '.env'
            env_exists = os.path.exists(env_path)
            
            if env_exists:
                # 讀取現有的.env文件
                with open(env_path, 'r', encoding='utf-8') as file:
                    lines = file.readlines()
                
                # 檢查並更新EARTHQUAKE_API_KEY環境變數
                key_found = False
                for i, line in enumerate(lines):
                    if line.startswith('EARTHQUAKE_API_KEY='):
                        lines[i] = f'EARTHQUAKE_API_KEY={api_key}\n'
                        key_found = True
                        break
                
                # 如果未找到密鑰，則添加
                if not key_found:
                    lines.append(f'EARTHQUAKE_API_KEY={api_key}\n')
                
                # 寫回.env文件
                with open(env_path, 'w', encoding='utf-8') as file:
                    file.writelines(lines)
            else:
                # 創建新的.env文件
                with open(env_path, 'w', encoding='utf-8') as file:
                    file.write(f'EARTHQUAKE_API_KEY={api_key}\n')
            
            await ctx.send("✅ 中央氣象局 API 密鑰已更新並保存到環境變數中!")
            logger.info("中央氣象局 API 密鑰已更新並保存到環境變數中")
        except Exception as e:
            await ctx.send(f"❌ 設置API密鑰時出錯: {str(e)}")
            logger.error(f"設置API密鑰時出錯: {e}")
            
    @set_cwb_api_key.error
    async def set_cwb_api_key_error(self, ctx, error):
        """設置氣象局API密鑰命令的錯誤處理"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ 你沒有權限執行此命令，需要管理員權限。")
        else:
            await ctx.send(f"❌ 執行命令時出錯: {str(error)}")
            logger.error(f"設置氣象局API密鑰命令錯誤: {error}")
            
    @commands.command(name="檢查氣象局密鑰")
    @commands.has_permissions(administrator=True)
    async def check_cwb_api_key(self, ctx):
        """檢查當前使用的中央氣象局 API 密鑰 (僅顯示前5位和後3位字符)"""
        try:
            # 獲取當前使用的密鑰
            current_key = os.environ.get('EARTHQUAKE_API_KEY') or self.config.get('CWB_API_KEY', '')
            
            if not current_key:
                await ctx.send("⚠️ 未設置中央氣象局 API 密鑰!")
                return
                
            # 混淆顯示密鑰 (僅顯示前5位和後3位，中間用*代替)
            masked_key = current_key[:5] + '*' * (len(current_key) - 8) + current_key[-3:] if len(current_key) > 8 else "***"
            
            # 確認密鑰來源
            source = "環境變數" if os.environ.get('EARTHQUAKE_API_KEY') else "配置文件"
            
            embed = discord.Embed(
                title="中央氣象局 API 密鑰檢查",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="當前密鑰", value=f"`{masked_key}`", inline=False)
            embed.add_field(name="密鑰來源", value=source, inline=True)
            embed.add_field(name="密鑰長度", value=f"{len(current_key)} 字符", inline=True)
            
            # DM發送給請求的管理員
            await ctx.author.send(embed=embed)
            await ctx.send("✅ API密鑰資訊已通過私信發送給您!")
            
        except Exception as e:
            await ctx.send(f"❌ 檢查API密鑰時出錯: {str(e)}")
            logger.error(f"檢查API密鑰時出錯: {e}")
            
    @check_cwb_api_key.error
    async def check_cwb_api_key_error(self, ctx, error):
        """檢查氣象局密鑰命令的錯誤處理"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ 你沒有權限執行此命令，需要管理員權限。")
        else:
            await ctx.send(f"❌ 執行命令時出錯: {str(error)}")
            logger.error(f"檢查氣象局密鑰命令錯誤: {error}")
            
    @commands.command(name="地震監測狀態")
    async def earthquake_status(self, ctx):
        """檢查地震監測系統狀態"""
        embed = discord.Embed(
            title="地震監測系統狀態",
            color=discord.Color.blue()
        )
        
        # 確認API密鑰來源
        has_env_key = bool(os.environ.get('EARTHQUAKE_API_KEY'))
        has_config_key = bool(self.config.get('CWB_API_KEY', ''))
        
        if has_env_key:
            api_status = "✅ 已設置 (環境變數)"
        elif has_config_key:
            api_status = "✅ 已設置 (配置文件)"
        else:
            api_status = "❌ 未設置"
        
        embed.add_field(name="監測狀態", value="✅ 正在運行" if self.earthquake_monitoring.is_running() else "❌ 未運行", inline=False)
        embed.add_field(name="監測頻道", value=f"<#{self.channel_id}>" if self.channel_id else "未設置", inline=True)
        embed.add_field(name="已知地震數量", value=str(len(self.last_earthquakes)), inline=True)
        embed.add_field(name="中央氣象局 API", value=api_status, inline=True)
        embed.add_field(name="檢查頻率", value="每 2 分鐘", inline=True)
        
        embed.set_footer(text=f"上次檢查: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        await ctx.send(embed=embed)
        
    @earthquake_status.error
    async def earthquake_status_error(self, ctx, error):
        """地震監測狀態命令的錯誤處理"""
        await ctx.send(f"❌ 檢查地震監測狀態時出錯: {str(error)}")
        logger.error(f"地震監測狀態命令錯誤: {error}")

    @commands.command(name="重新載入環境變數")
    @commands.has_permissions(administrator=True)
    async def reload_env_vars(self, ctx):
        """從.env文件重新載入環境變數設定"""
        try:
            # 重新載入環境變數
            load_dotenv(override=True)
            
            # 更新頻道ID
            old_channel_id = self.channel_id
            self.channel_id = int(os.environ.get('EARTHQUAKE_CHANNEL') or self.config.get('CHATROOM01', '0'))
            
            # 更新API網址
            old_api_url = self.cwb_api_url
            self.cwb_api_url = os.environ.get('EARTHQUAKE_API_URL') or "https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0016-001"
            
            # 更新API密鑰
            old_api_key = self.cwb_api_key
            self.cwb_api_key = os.environ.get('EARTHQUAKE_API_KEY') or self.config.get('CWB_API_KEY', '')
            
            # 準備回應訊息
            embed = discord.Embed(
                title="環境變數已重新載入",
                description="地震監測模組設定已從環境變數更新",
                color=discord.Color.green()
            )
            
            # 檢查頻道ID是否變更
            if old_channel_id != self.channel_id:
                new_channel = self.bot.get_channel(self.channel_id)
                channel_name = new_channel.name if new_channel else "未知頻道"
                embed.add_field(
                    name="頻道已更新",
                    value=f"從 <#{old_channel_id}> 更改為 <#{self.channel_id}> ({channel_name})",
                    inline=False
                )
            
            # 檢查API網址是否變更
            if old_api_url != self.cwb_api_url:
                embed.add_field(
                    name="API網址已更新",
                    value=f"從 `{old_api_url}` 更改為 `{self.cwb_api_url}`",
                    inline=False
                )
            
            # 檢查API密鑰是否變更 (不顯示完整密鑰)
            if old_api_key != self.cwb_api_key:
                # 混淆顯示密鑰
                old_masked = "未設置" if not old_api_key else (old_api_key[:5] + '***' + old_api_key[-3:] if len(old_api_key) > 8 else "***")
                new_masked = self.cwb_api_key[:5] + '***' + self.cwb_api_key[-3:] if len(self.cwb_api_key) > 8 else "***"
                
                embed.add_field(
                    name="API密鑰已更新",
                    value=f"從 `{old_masked}` 更改為 `{new_masked}`",
                    inline=False
                )
                
            await ctx.send(embed=embed)
            logger.info("已從環境變數重新載入地震監測設定")
            
        except Exception as e:
            await ctx.send(f"❌ 重新載入環境變數時出錯: {str(e)}")
            logger.error(f"重新載入環境變數時出錯: {e}")
    
    @reload_env_vars.error
    async def reload_env_vars_error(self, ctx, error):
        """重新載入環境變數命令的錯誤處理"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ 你沒有權限執行此命令，需要管理員權限。")
        else:
            await ctx.send(f"❌ 執行命令時出錯: {str(error)}")
            logger.error(f"重新載入環境變數命令錯誤: {error}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Earthquake(bot)) 