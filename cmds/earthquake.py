import discord
import asyncio
import aiohttp
import json
import datetime
import os
import time
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
    earthquake_id_ttl_days = 7  # 地震ID在列表中的保存天數
    max_earthquake_age_hours = 24  # 最多處理多少小時前的地震
    
    def __init__(self, bot):
        super().__init__(bot)
        self.session = None
        self.config = load_config('setting.json')
        
        # 初始化已發送的地震ID集合
        self.sent_earthquake_ids = set()
        
        # 優先使用環境變數中的頻道ID，再使用配置文件中的ID
        try:
            channel_value = os.environ.get('EARTHQUAKE_CHANNEL')
            if channel_value:
                # 處理可能的註釋
                if '#' in channel_value:
                    channel_value = channel_value.split('#')[0].strip()
                self.channel_id = int(channel_value)
            else:
                # 使用配置文件中的ID
                chatroom_value = self.config.get('CHATROOM01', '0')
                if isinstance(chatroom_value, str):
                    if '#' in chatroom_value:
                        chatroom_value = chatroom_value.split('#')[0].strip()
                    if not chatroom_value or chatroom_value == '':
                        chatroom_value = '0'
                self.channel_id = int(chatroom_value)
                
            logger.info(f"已設置地震通知頻道ID: {self.channel_id}")
        except (ValueError, TypeError) as e:
            logger.error(f"無法解析地震通知頻道ID: {e}，使用預設值 0")
            self.channel_id = 0  # 使用預設值
            
        # 設置地震時間窗口 (小時)
        try:
            age_value = os.environ.get('EARTHQUAKE_MAX_AGE_HOURS', str(self.max_earthquake_age_hours))
            # 處理可能的註釋
            if '#' in age_value:
                age_value = age_value.split('#')[0].strip()
            self.max_earthquake_age_hours = int(age_value)
            logger.info(f"已設置最大地震年齡 (小時): {self.max_earthquake_age_hours}")
        except (ValueError, TypeError) as e:
            logger.error(f"無法解析最大地震年齡: {e}，使用預設值 {self.max_earthquake_age_hours}")
            # 保持預設值不變
        
        # 初始化數據結構
        self.last_earthquakes: Set[str] = set()
        self.earthquake_timestamps: Dict[str, float] = {}
        
        # 初始化監控性能指標
        self._api_call_count = 0
        self._successful_api_calls = 0
        self._last_api_call_time = None
        self._cached_earthquake_data = None
        self._cached_earthquake_timestamp = None
        self.consecutive_errors = 0
        self.last_api_error_time = None
        
        # 台灣中央氣象局地震 API
        api_url = os.environ.get('EARTHQUAKE_API_URL')
        if api_url:
            if '#' in api_url:
                api_url = api_url.split('#')[0].strip()
            # 修復可能包含多餘空格的URL
            api_url = api_url.strip()
            self.cwb_api_url = api_url
        else:
            # 使用默認的 API URL
            self.cwb_api_url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0016-001"
        
        # 優先使用環境變數中的API密鑰，環境變數不存在時則使用配置文件中的密鑰
        api_key = os.environ.get('EARTHQUAKE_API_KEY')
        if api_key:
            if '#' in api_key:
                api_key = api_key.split('#')[0].strip()
            self.cwb_api_key = api_key.strip()
        else:
            self.cwb_api_key = self.config.get('CWB_API_KEY', '').strip()
        
        # USGS 地震 API (作為備用)
        self.usgs_api_url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
        
        # 從配置文件加載數據
        self._load_earthquake_data()
        # 載入已發送的地震ID
        self._load_sent_earthquake_ids()
        
        # 設置監測任務
        self.earthquake_monitoring.start()
        
    def _load_earthquake_data(self) -> None:
        """從配置文件載入地震數據"""
        # 載入地震ID
        if 'LAST_EARTHQUAKES' not in self.config:
            self.config['LAST_EARTHQUAKES'] = []
            save_config('setting.json', self.config)
        else:
            self.last_earthquakes = set(self.config['LAST_EARTHQUAKES'])
            
        # 載入地震時間戳記錄
        if 'EARTHQUAKE_TIMESTAMPS' not in self.config:
            self.config['EARTHQUAKE_TIMESTAMPS'] = {}
            save_config('setting.json', self.config)
        else:
            self.earthquake_timestamps = self.config.get('EARTHQUAKE_TIMESTAMPS', {})
        
        logger.info(f"已從配置文件載入 {len(self.last_earthquakes)} 個地震ID記錄")
        
    async def cog_load(self):
        """加載模組時調用"""
        # 創建連接池並設置合適的連接參數
        conn_limit = 10  # 最大連接數
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=10)
        
        # 使用 TCP_NODELAY 來減少延遲
        tcp_connector = aiohttp.TCPConnector(
            limit=conn_limit,
            enable_cleanup_closed=True,
            force_close=True,
            ssl=False  # 如果需要HTTPS，則設為None或適當的SSL上下文
        )
        
        self.session = aiohttp.ClientSession(
            connector=tcp_connector,
            timeout=timeout,
            raise_for_status=False,  # 不自動拋出HTTP錯誤，使我們可以更好地處理它們
            headers={
                'User-Agent': 'Discord-Earthquake-Bot/1.0'
            }
        )
        
        logger.info("地震監測模組已加載，設置為最大 %d 個連接", conn_limit)
        
    async def cog_unload(self):
        """卸載模組時調用"""
        # 先取消任務
        if self.earthquake_monitoring.is_running():
            self.earthquake_monitoring.cancel()
            logger.info("地震監測任務已取消")
        
        # 保存當前狀態
        self._save_earthquake_state()
        
        # 最後關閉會話
        if self.session:
            pending_requests = not self.session.closed
            if pending_requests:
                try:
                    await asyncio.wait_for(self.session.close(), timeout=5.0)
                    logger.info("成功關閉HTTP會話")
                except asyncio.TimeoutError:
                    logger.warning("關閉HTTP會話超時")
            else:
                logger.info("HTTP會話已關閉")
                
        logger.info("地震監測模組已完全卸載")
        
    @tasks.loop(minutes=2.0)
    async def earthquake_monitoring(self):
        """每2分鐘檢查一次地震資訊"""
        try:
            # 智能頻率限制 - 使用指數回退策略
            current_time = datetime.datetime.now()
            last_call_time = getattr(self, 'last_api_call_time', None)
            last_error_time = getattr(self, 'last_api_error_time', None)
            consecutive_errors = getattr(self, 'consecutive_errors', 0)
            
            # 計算基於錯誤次數的等待時間 (指數回退)
            min_wait_seconds = 30  # 最短等待時間
            if consecutive_errors > 0 and last_error_time:
                # 計算指數回退等待時間: 30秒 * 2^錯誤次數 (最多10分鐘)
                wait_seconds = min(min_wait_seconds * (2 ** consecutive_errors), 600)
                time_since_error = (current_time - last_error_time).total_seconds()
                
                if time_since_error < wait_seconds:
                    logger.info(f"API呼叫後退中，跳過本次檢查 (連續錯誤: {consecutive_errors}, 等待: {wait_seconds}秒)")
                    return
            
            # 一般頻率限制
            elif last_call_time and (current_time - last_call_time).total_seconds() < min_wait_seconds:
                logger.info("API呼叫過於頻繁，跳過本次檢查")
                return
                
            # 更新最後呼叫時間並執行API請求
            self.last_api_call_time = current_time
            
            # 使用快取策略減少API調用
            cache_key = f"earthquake_data_{current_time.strftime('%Y-%m-%d_%H')}"
            cached_data = getattr(self, '_cached_earthquake_data', None)
            cache_timestamp = getattr(self, '_cached_earthquake_timestamp', None)
            cache_ttl = 300  # 5分鐘快取
            
            # 快取有效則使用快取資料
            if (cached_data and cache_timestamp and 
                (current_time - cache_timestamp).total_seconds() < cache_ttl):
                logger.debug("使用快取的地震資料")
                earthquakes = cached_data
            else:
                # 不使用快取，重新獲取資料
                earthquakes = await self.fetch_earthquake_data()
                
                if not earthquakes:
                    # 如果中央氣象局 API 無法獲取數據，嘗試使用 USGS API
                    earthquakes = await self.fetch_usgs_earthquakes()
                
                # 更新快取
                if earthquakes:
                    self._cached_earthquake_data = earthquakes
                    self._cached_earthquake_timestamp = current_time
            
            if earthquakes:
                # 重設連續錯誤計數
                self.consecutive_errors = 0
                # 處理地震數據
                await self.process_earthquakes(earthquakes)
            else:
                # 更新錯誤計數和時間
                self.consecutive_errors = consecutive_errors + 1
                self.last_api_error_time = current_time
                logger.warning(f"無法獲取地震數據 (連續錯誤次數: {self.consecutive_errors})")
                
        except aiohttp.ClientError as e:
            # 網絡錯誤處理
            self.consecutive_errors = getattr(self, 'consecutive_errors', 0) + 1
            self.last_api_error_time = current_time
            logger.error(f"API請求網絡錯誤: {e} (連續錯誤次數: {self.consecutive_errors})")
        except Exception as e:
            # 其他錯誤處理
            logger.error(f"地震監測過程中發生錯誤: {e}", exc_info=True)
            
    @earthquake_monitoring.before_loop
    async def before_earthquake_monitoring(self):
        """等待機器人準備好後再開始監測"""
        await self.bot.wait_until_ready()
        logger.info("地震監測開始運行，頻率: 每2分鐘")
        
    async def fetch_earthquake_data(self):
        """從中央氣象署取得地震資訊"""
        logger.info(f"正在從 {self.cwb_api_url} 取得地震資訊 使用API金鑰: {self.cwb_api_key[:5]}...")
        try:
            url = self.cwb_api_url
            headers = {
                "Authorization": self.cwb_api_key,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"無法取得地震資料: 狀態碼 {response.status}")
                    error_text = await response.text()
                    logger.error(f"錯誤回應內容: {error_text[:500]}")
                    return None
                
                try:
                    data = await response.json()
                    
                    if not data.get("success"):
                        logger.error(f"API 回應錯誤: {data}")
                        return None
                    
                    if "records" not in data:
                        logger.error(f"API 回應中沒有 records: {data}")
                        return None
                    
                    if "Earthquake" not in data["records"]:
                        logger.error(f"API 回應中沒有 Earthquake: {data['records']}")
                        return None
                    
                    earthquakes = data["records"]["Earthquake"]
                    logger.info(f"成功取得 {len(earthquakes)} 筆地震資料")
                    return earthquakes
                except ValueError as e:
                    logger.error(f"無法解析 JSON 回應: {e}")
                    return None
                
        except aiohttp.ClientError as e:
            logger.error(f"連線到地震 API 時發生錯誤: {e}")
            return None
        except asyncio.TimeoutError:
            logger.error("連線到地震 API 超時")
            return None
        except Exception as e:
            logger.error(f"取得地震資料時發生未知錯誤: {e}")
            return None
            
    @measure_time
    async def fetch_usgs_earthquakes(self) -> List[Dict[str, Any]]:
        """從USGS獲取地震資訊，並過濾台灣區域"""
        try:
            # 使用超時設置
            timeout = aiohttp.ClientTimeout(total=10)  # 10秒總超時
            retry_count = 0
            max_retries = 2
            
            while retry_count <= max_retries:
                try:
                    async with self.session.get(self.usgs_api_url, timeout=timeout) as response:
                        if response.status != 200:
                            logger.warning(f"從USGS獲取地震數據失敗，狀態碼: {response.status}")
                            if 500 <= response.status < 600 and retry_count < max_retries:
                                # 服務器錯誤可重試
                                retry_count += 1
                                await asyncio.sleep(1 * (2 ** retry_count))  # 指數退避
                                continue
                            return []
                        
                        try:
                            data = await response.json()
                        except json.JSONDecodeError:
                            logger.error("解析USGS JSON響應失敗")
                            return []
                        
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
                
                except asyncio.TimeoutError:
                    logger.warning(f"從USGS獲取數據超時 (嘗試 {retry_count+1}/{max_retries+1})")
                    retry_count += 1
                    if retry_count <= max_retries:
                        await asyncio.sleep(1 * (2 ** retry_count))  # 指數退避
                    else:
                        return []
                except aiohttp.ClientError as e:
                    logger.error(f"USGS API請求錯誤: {e}")
                    return []
                
        except Exception as e:
            logger.error(f"獲取USGS地震數據時出錯: {e}", exc_info=True)
            return []
            
    async def process_earthquakes(self, earthquakes: List[Dict[str, Any]]) -> None:
        """處理地震數據並發送通知"""
        if not earthquakes:
            logger.debug("沒有地震數據可處理")
            return
            
        current_time = time.time()
        
        # 一次性清理過期的地震ID和時間戳記錄
        await self._cleanup_expired_earthquake_records(current_time)
        
        # 將地震按發生時間排序，確保最新的地震在前面
        # 只排序一次，避免重複操作
        sorted_earthquakes = sorted(
            earthquakes,
            key=lambda eq: datetime.datetime.strptime(
                eq.get('originTime', '1970-01-01 00:00:00'), 
                '%Y-%m-%d %H:%M:%S'
            ),
            reverse=True
        )
        
        # 記錄最新處理的地震時間，用於日誌
        newest_eq_time = None
        if sorted_earthquakes:
            try:
                newest_eq_time = datetime.datetime.strptime(
                    sorted_earthquakes[0].get('originTime', '1970-01-01 00:00:00'),
                    '%Y-%m-%d %H:%M:%S'
                )
                logger.debug(f"最新地震發生時間: {newest_eq_time.strftime('%Y-%m-%d %H:%M:%S')}")
            except (ValueError, IndexError):
                pass
        
        # 只處理最新的一個尚未發送過的地震
        for eq in sorted_earthquakes:
            eq_id = eq.get('earthquakeNo', '')
            if not eq_id:
                continue
                
            # 檢查這個地震是否是新的
            if eq_id not in self.last_earthquakes:
                # 獲取地震發生時間
                try:
                    eq_time = datetime.datetime.strptime(
                        eq.get('originTime', '1970-01-01 00:00:00'), 
                        '%Y-%m-%d %H:%M:%S'
                    )
                    
                    # 只處理最近設定時間內的地震
                    time_diff = datetime.datetime.now() - eq_time
                    max_age_seconds = self.max_earthquake_age_hours * 3600
                    if time_diff.total_seconds() > max_age_seconds:
                        logger.info(f"跳過舊地震: {eq_id}, 發生時間: {eq.get('originTime')}, {time_diff.total_seconds()/3600:.1f}小時前 (超過{self.max_earthquake_age_hours}小時)")
                        continue
                        
                    # 發送地震警報
                    await self.send_earthquake_alert(eq)
                    logger.info(f"發送地震警報: {eq_id}, 發生時間: {eq.get('originTime')}")
                    
                    # 將地震加入已處理列表和時間戳記錄
                    self.last_earthquakes.add(eq_id)
                    self.earthquake_timestamps[eq_id] = current_time
                    
                    # 由於我們只發送最新的地震，因此處理完一個後就可以中斷循環
                    break
                    
                except ValueError:
                    logger.error(f"解析地震時間失敗: {eq.get('originTime')}")
        
        # 保存狀態到配置文件，但不需要每次都保存，只有在ID集合有變化時才保存
        if getattr(self, '_last_save_ids', None) != self.last_earthquakes:
            self._save_earthquake_state()
            self._last_save_ids = set(self.last_earthquakes)
            
    async def _cleanup_expired_earthquake_records(self, current_time: float) -> None:
        """清理過期的地震記錄，減少內存佔用"""
        # 移除過期的地震ID (超過ttl天數的記錄)
        expiry_time = current_time - (self.earthquake_id_ttl_days * 24 * 60 * 60)
        expired_ids = {eq_id for eq_id, timestamp in self.earthquake_timestamps.items() 
                      if timestamp < expiry_time}
                      
        if expired_ids:
            logger.info(f"移除 {len(expired_ids)} 個過期的地震ID記錄")
            # 從紀錄中移除過期ID
            for eq_id in expired_ids:
                self.last_earthquakes.discard(eq_id)
                del self.earthquake_timestamps[eq_id]
                
        # 限制地震ID儲存數量，避免無限增長
        if len(self.last_earthquakes) > self.max_stored_earthquakes:
            # 根據時間戳排序，保留最新的記錄
            sorted_ids = sorted(
                [(eq_id, self.earthquake_timestamps.get(eq_id, 0)) 
                 for eq_id in self.last_earthquakes],
                key=lambda x: x[1], reverse=True
            )
            # 保留最新的max_stored_earthquakes個ID
            self.last_earthquakes = {id_tuple[0] for id_tuple in sorted_ids[:self.max_stored_earthquakes]}
            # 清理對應的時間戳記錄
            self.earthquake_timestamps = {
                eq_id: timestamp for eq_id, timestamp in self.earthquake_timestamps.items()
                if eq_id in self.last_earthquakes
            }
            logger.info(f"地震ID數量已限制在 {self.max_stored_earthquakes} 以內")
            
    def _save_earthquake_state(self) -> None:
        """保存地震狀態到配置文件"""
        self.config['LAST_EARTHQUAKES'] = list(self.last_earthquakes)
        self.config['EARTHQUAKE_TIMESTAMPS'] = self.earthquake_timestamps
        save_config('setting.json', self.config)
        logger.debug(f"已保存地震狀態，當前地震ID數量: {len(self.last_earthquakes)}")
        
    async def send_earthquake_alert(self, earthquake: Dict[str, Any]) -> None:
        """發送地震警報到頻道"""
        # 獲取地震ID
        eq_id = earthquake.get('earthquakeNo', '未知ID')
        
        try:
            # 嘗試獲取頻道，使用緩存減少API調用
            channel_id = self.channel_id
            if not channel_id:
                logger.error("未設置地震通知頻道ID")
                return
                
            channel = self.bot.get_channel(channel_id)
            if not channel:
                # 如果緩存無效，嘗試重新獲取（很少需要）
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.NotFound:
                    logger.error(f"地震通知頻道不存在: {channel_id}")
                    return
                except discord.Forbidden:
                    logger.error(f"無權訪問地震通知頻道: {channel_id}")
                    return
                except Exception as e:
                    logger.error(f"獲取地震通知頻道失敗: {e}", exc_info=True)
                    return
            
            # 構建訊息
            source = earthquake.get('source', '中央氣象局')
            embed = None
            
            if source == 'USGS':
                # 獲取USGS數據的地震規模
                magnitude_value = earthquake.get('magnitudeValue', 0)
                # USGS 格式
                embed = await self._create_usgs_earthquake_embed(earthquake, magnitude_value, eq_id, source)
            else:
                # 中央氣象局格式 - 獲取實際的規模值
                magnitude_value = earthquake.get('earthquakeInfo', {}).get('magnitude', {}).get('magnitudeValue', 0)
                embed = await self._create_cwb_earthquake_embed(earthquake, magnitude_value, eq_id, source)
            
            # 設置時間戳和頁腳
            if embed:
                embed.timestamp = datetime.datetime.now()
                embed.set_footer(text=f"ID: {eq_id} | 資料來源: {source}")
                
                # 使用重試機制發送消息
                max_retries = 3
                retry_count = 0
                last_error = None
                
                while retry_count < max_retries:
                    try:
                        await channel.send(embed=embed)
                        logger.info(f"成功發送地震警報 {eq_id} 到頻道 {channel.name} ({channel.id})")
                        # 發送成功就退出循環
                        break
                    except discord.HTTPException as e:
                        # HTTP錯誤可能是暫時的，可以重試
                        retry_count += 1
                        wait_time = 2 ** retry_count  # 指數退避
                        last_error = e
                        logger.warning(f"發送地震警報嘗試 {retry_count}/{max_retries} 失敗: {e}，將在 {wait_time} 秒後重試")
                        await asyncio.sleep(wait_time)
                    except Exception as e:
                        # 其他錯誤不重試
                        last_error = e
                        logger.error(f"發送地震警報時發生不可恢復錯誤: {e}", exc_info=True)
                        break
                
                if retry_count == max_retries:
                    logger.error(f"發送地震警報失敗，已達最大重試次數: {last_error}")
            else:
                logger.error(f"無法創建地震警報嵌入消息: {eq_id}")
                
        except discord.DiscordException as e:
            logger.error(f"Discord API異常，無法發送地震警報 {eq_id}: {e}")
        except Exception as e:
            logger.error(f"發送地震警報時出錯: {e}", exc_info=True)
            
    async def _create_usgs_earthquake_embed(self, earthquake: Dict[str, Any], magnitude_value: float, eq_id: str, source: str) -> discord.Embed:
        """創建USGS格式的地震嵌入消息"""
        try:
            embed = discord.Embed(
                title="🌋 地震警報 [USGS資料]",
                description=earthquake.get('reportContent', '未知地震事件'),
                color=self.get_color_by_magnitude(magnitude_value)
            )
            
            embed.add_field(name="發生時間", value=earthquake.get('originTime', '未知'), inline=True)
            embed.add_field(name="規模", value=str(magnitude_value), inline=True)
            embed.add_field(name="深度", value=f"{earthquake.get('depth', {}).get('value', '未知')} km", inline=True)
            
            location = earthquake.get('location', {})
            coords = (location.get('coordinateY', 0), location.get('coordinateX', 0))
            embed.add_field(name="位置", value=f"經度: {coords[1]}, 緯度: {coords[0]}", inline=False)
            
            map_url = f"https://maps.google.com/maps?q={coords[0]},{coords[1]}&z=9"
            embed.add_field(name="地圖", value=f"[查看地圖]({map_url})", inline=False)
            
            return embed
        except Exception as e:
            logger.error(f"創建USGS地震嵌入消息時出錯: {e}", exc_info=True)
            return None
            
    async def _create_cwb_earthquake_embed(self, earthquake: Dict[str, Any], magnitude_value: float, eq_id: str, source: str) -> discord.Embed:
        """創建中央氣象局格式的地震嵌入消息"""
        try:
            embed = discord.Embed(
                title="🌋 地震警報 [氣象局資料]",
                description=earthquake.get('reportContent', '未知地震事件'),
                color=self.get_color_by_magnitude(magnitude_value)
            )
            
            embed.add_field(name="地震編號", value=eq_id, inline=True)
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
                
            return embed
        except Exception as e:
            logger.error(f"創建中央氣象局地震嵌入消息時出錯: {e}", exc_info=True)
            return None
            
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
        
        # 使用當前時間作為測試ID，避免重複
        current_time = datetime.datetime.now()
        test_id = f"TEST-{current_time.strftime('%Y%m%d%H%M%S')}"
        
        test_earthquake = {
            'earthquakeNo': test_id,
            'reportContent': '這是一條測試地震警報',
            'originTime': current_time.strftime('%Y-%m-%d %H:%M:%S'),
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
        
        try:
            await self.send_earthquake_alert(test_earthquake)
            # 不要將測試數據添加到實際地震ID列表中
            await ctx.send(f"地震警報測試完成! 測試ID: {test_id}")
            logger.info(f"管理員 {ctx.author.name} 執行了地震警報測試，ID: {test_id}")
        except Exception as e:
            await ctx.send(f"❌ 地震警報測試失敗: {str(e)}")
            logger.error(f"地震警報測試失敗: {e}", exc_info=True)
        
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
        try:
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
                
            # 計算API性能指標
            api_success_rate = "N/A"
            if getattr(self, '_api_call_count', 0) > 0:
                success_rate = (getattr(self, '_successful_api_calls', 0) / self._api_call_count) * 100
                api_success_rate = f"{success_rate:.1f}% ({self._successful_api_calls}/{self._api_call_count})"
            
            embed.add_field(name="監測狀態", value="✅ 正在運行" if self.earthquake_monitoring.is_running() else "❌ 未運行", inline=False)
            embed.add_field(name="監測頻道", value=f"<#{self.channel_id}>" if self.channel_id else "未設置", inline=True)
            embed.add_field(name="已知地震數量", value=str(len(self.last_earthquakes)), inline=True)
            embed.add_field(name="中央氣象局 API", value=api_status, inline=True)
            embed.add_field(name="檢查頻率", value="每 2 分鐘", inline=True)
            embed.add_field(name="地震ID保存期限", value=f"{self.earthquake_id_ttl_days} 天", inline=True)
            embed.add_field(name="地震最大年齡", value=f"{self.max_earthquake_age_hours} 小時", inline=True)
            
            if hasattr(self, '_api_call_count'):
                embed.add_field(name="API成功率", value=api_success_rate, inline=True)
                
            if hasattr(self, 'consecutive_errors') and self.consecutive_errors > 0:
                embed.add_field(name="連續API錯誤", value=str(self.consecutive_errors), inline=True)
                
            embed.set_footer(text=f"上次檢查: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            await ctx.send(embed=embed)
            logger.debug(f"用戶 {ctx.author.name} 查看了地震監測狀態")
        except Exception as e:
            await ctx.send(f"❌ 獲取地震監測狀態時出錯: {str(e)}")
            logger.error(f"獲取地震監測狀態出錯: {e}", exc_info=True)

    @commands.command(name="地震歷史")
    @commands.has_permissions(administrator=True)
    async def earthquake_history(self, ctx, limit: int = 10):
        """顯示最近的地震ID記錄 (僅限管理員使用)"""
        try:
            if not self.earthquake_timestamps:
                await ctx.send("⚠️ 沒有地震歷史記錄")
                return
                
            # 使用列表解析而不是字典推導，更高效
            items = list(self.earthquake_timestamps.items())
            
            # 排序一次，然後限制數量
            items.sort(key=lambda x: x[1], reverse=True)
            history_to_show = items[:min(limit, len(items))]
            
            embed = discord.Embed(
                title="地震歷史記錄",
                description=f"最近 {len(history_to_show)} 個地震ID (共 {len(self.earthquake_timestamps)} 個記錄)",
                color=discord.Color.blue()
            )
            
            # 批量處理字段添加
            for i, (eq_id, timestamp) in enumerate(history_to_show, 1):
                time_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                time_ago = datetime.datetime.now() - datetime.datetime.fromtimestamp(timestamp)
                days, seconds = time_ago.days, time_ago.seconds
                hours = days * 24 + seconds // 3600
                minutes = (seconds % 3600) // 60
                
                time_ago_str = f"{days}天" if days > 0 else f"{hours}小時{minutes}分鐘前"
                embed.add_field(
                    name=f"{i}. {eq_id}",
                    value=f"記錄時間: {time_str}\n{time_ago_str}",
                    inline=True if i % 2 == 0 else False
                )
                
            embed.set_footer(text=f"地震ID保存期限: {self.earthquake_id_ttl_days} 天 | 最大記錄數: {self.max_stored_earthquakes}")
            await ctx.send(embed=embed)
            logger.info(f"管理員 {ctx.author.name} 查看了地震歷史記錄")
            
        except Exception as e:
            await ctx.send(f"❌ 獲取地震歷史記錄時出錯: {str(e)}")
            logger.error(f"獲取地震歷史記錄時出錯: {e}", exc_info=True)

    @commands.command(name="清理地震記錄")
    @commands.has_permissions(administrator=True)
    async def clear_earthquake_history(self, ctx, days: int = None):
        """清理指定天數以前的地震記錄 (僅限管理員使用)
        
        Args:
            days: 要保留的天數，指定數字將刪除X天前的記錄，不指定則完全清空
        """
        try:
            if days is None:
                # 完全清空
                old_count = len(self.last_earthquakes)
                self.last_earthquakes.clear()
                self.earthquake_timestamps.clear()
                self._save_earthquake_state()
                await ctx.send(f"✅ 已清空所有地震記錄 (共清除 {old_count} 個記錄)")
                logger.warning(f"管理員 {ctx.author.name} 清空了所有地震記錄")
                return
                
            # 根據天數清理
            current_time = time.time()
            cutoff_time = current_time - (days * 24 * 60 * 60)
            
            old_count = len(self.earthquake_timestamps)
            # 找出所有需要刪除的ID - 優化為列表推導
            to_delete = [eq_id for eq_id, timestamp in self.earthquake_timestamps.items() 
                        if timestamp < cutoff_time]
                        
            # 從記錄中刪除
            for eq_id in to_delete:
                self.last_earthquakes.discard(eq_id)
                del self.earthquake_timestamps[eq_id]
                
            # 保存到配置
            self._save_earthquake_state()
            
            new_count = len(self.earthquake_timestamps)
            await ctx.send(f"✅ 已清理 {days} 天前的地震記錄 (從 {old_count} 減少至 {new_count}，刪除了 {old_count - new_count} 個記錄)")
            logger.info(f"管理員 {ctx.author.name} 清理了 {days} 天前的地震記錄，刪除了 {old_count - new_count} 個記錄")
            
        except Exception as e:
            await ctx.send(f"❌ 清理地震記錄時出錯: {str(e)}")
            logger.error(f"清理地震記錄時出錯: {e}", exc_info=True)

    @commands.command(name="重新載入環境變數")
    @commands.has_permissions(administrator=True)
    async def reload_env_vars(self, ctx):
        """從.env文件重新載入環境變數設定"""
        try:
            # 記錄舊值用於對比
            old_values = {
                'channel_id': self.channel_id,
                'api_url': self.cwb_api_url,
                'api_key': self.cwb_api_key,
                'max_age': self.max_earthquake_age_hours
            }
            
            # 重新載入環境變數
            load_dotenv(override=True)
            
            # 更新設置 - 處理頻道ID
            try:
                channel_value = os.environ.get('EARTHQUAKE_CHANNEL')
                if channel_value:
                    # 處理可能的註釋
                    if '#' in channel_value:
                        channel_value = channel_value.split('#')[0].strip()
                    self.channel_id = int(channel_value)
                else:
                    # 使用配置文件中的ID
                    chatroom_value = self.config.get('CHATROOM01', '0')
                    if isinstance(chatroom_value, str):
                        if '#' in chatroom_value:
                            chatroom_value = chatroom_value.split('#')[0].strip()
                        if not chatroom_value or chatroom_value == '':
                            chatroom_value = '0'
                    self.channel_id = int(chatroom_value)
                logger.info(f"已重新加載地震通知頻道ID: {self.channel_id}")
            except (ValueError, TypeError) as e:
                logger.error(f"重新加載時無法解析地震通知頻道ID: {e}，保持原值")
                # 頻道ID保持不變
                
            # 更新API URL，處理註釋
            new_api_url = os.environ.get('EARTHQUAKE_API_URL')
            if new_api_url:
                if '#' in new_api_url:
                    new_api_url = new_api_url.split('#')[0].strip()
                # 修復可能包含多餘空格的URL
                new_api_url = new_api_url.strip()
                self.cwb_api_url = new_api_url
            else:
                self.cwb_api_url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0016-001"
                
            # 更新API密鑰，處理註釋
            new_api_key = os.environ.get('EARTHQUAKE_API_KEY')
            if new_api_key:
                if '#' in new_api_key:
                    new_api_key = new_api_key.split('#')[0].strip()
                # 確保API密鑰不包含空格
                new_api_key = new_api_key.strip()
                self.cwb_api_key = new_api_key
            else:
                self.cwb_api_key = self.config.get('CWB_API_KEY', '').strip()
                
            # 更新最大地震年齡，處理註釋
            try:
                age_value = os.environ.get('EARTHQUAKE_MAX_AGE_HOURS', str(self.max_earthquake_age_hours))
                # 處理可能的註釋
                if '#' in age_value:
                    age_value = age_value.split('#')[0].strip()
                self.max_earthquake_age_hours = int(age_value)
                logger.info(f"已重新加載最大地震年齡 (小時): {self.max_earthquake_age_hours}")
            except (ValueError, TypeError) as e:
                logger.error(f"重新加載時無法解析最大地震年齡: {e}，保持原值")
            
            # 準備回應訊息
            embed = discord.Embed(
                title="環境變數已重新載入",
                description="地震監測模組設定已從環境變數更新",
                color=discord.Color.green()
            )
            
            # 檢測變更並添加到嵌入消息
            changes_made = False
            
            # 頻道ID變更
            if old_values['channel_id'] != self.channel_id:
                changes_made = True
                channel_info = ""
                try:
                    new_channel = self.bot.get_channel(self.channel_id)
                    channel_name = new_channel.name if new_channel else "未知頻道"
                    channel_info = f"<#{self.channel_id}> ({channel_name})"
                except:
                    channel_info = f"<#{self.channel_id}>"
                    
                embed.add_field(
                    name="頻道已更新",
                    value=f"從 <#{old_values['channel_id']}> 更改為 {channel_info}",
                    inline=False
                )
            
            # API網址變更
            if old_values['api_url'] != self.cwb_api_url:
                changes_made = True
                # 截斷過長的URL
                old_url = old_values['api_url']
                new_url = self.cwb_api_url
                
                if len(old_url) > 30:
                    old_url = old_url[:27] + "..."
                if len(new_url) > 30:
                    new_url = new_url[:27] + "..."
                    
                embed.add_field(
                    name="API網址已更新",
                    value=f"從 `{old_url}` 更改為 `{new_url}`",
                    inline=False
                )
            
            # API密鑰變更 (不顯示完整密鑰)
            if old_values['api_key'] != self.cwb_api_key:
                changes_made = True
                # 混淆顯示密鑰
                old_masked = "未設置" if not old_values['api_key'] else (old_values['api_key'][:3] + '***' + old_values['api_key'][-2:] if len(old_values['api_key']) > 8 else "***")
                new_masked = "未設置" if not self.cwb_api_key else (self.cwb_api_key[:3] + '***' + self.cwb_api_key[-2:] if len(self.cwb_api_key) > 8 else "***")
                
                embed.add_field(
                    name="API密鑰已更新",
                    value=f"從 `{old_masked}` 更改為 `{new_masked}`",
                    inline=False
                )
                
            # 地震最大年齡變更
            if old_values['max_age'] != self.max_earthquake_age_hours:
                changes_made = True
                embed.add_field(
                    name="地震最大年齡已更新",
                    value=f"從 `{old_values['max_age']}小時` 更改為 `{self.max_earthquake_age_hours}小時`",
                    inline=False
                )
            
            # 如果沒有變更，顯示提示
            if not changes_made:
                embed.add_field(
                    name="沒有變更",
                    value="沒有檢測到配置變更",
                    inline=False
                )
                
            # 重置API錯誤計數
            if hasattr(self, 'consecutive_errors') and self.consecutive_errors > 0:
                old_count = self.consecutive_errors
                self.consecutive_errors = 0
                embed.add_field(
                    name="API錯誤計數已重置",
                    value=f"從 {old_count} 重置為 0",
                    inline=False
                )
            
            # 發送回應
            embed.set_footer(text=f"更新時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await ctx.send(embed=embed)
            logger.info(f"管理員 {ctx.author.name} 已從環境變數重新載入地震監測設定")
            
            # 清除連續API錯誤
            self.consecutive_errors = 0
            self.last_api_error_time = None
            
        except Exception as e:
            await ctx.send(f"❌ 重新載入環境變數時出錯: {str(e)}")
            logger.error(f"重新載入環境變數時出錯: {e}", exc_info=True)

    @measure_time
    async def check_earthquakes(self):
        """定時檢查是否有新地震"""
        try:
            earthquakes = await self.fetch_earthquake_data()
            if not earthquakes:
                logger.warning(f"無法取得地震資料，此為第 {self.consecutive_errors} 次連續錯誤")
                self.consecutive_errors += 1
                if self.consecutive_errors > 5:
                    logger.error("連續錯誤超過 5 次，暫時暫停地震監測")
                    # 暫時延長下次檢查時間，避免頻繁請求
                    await asyncio.sleep(600)  # 10 分鐘後再試
                return
            
            self.consecutive_errors = 0  # 重置錯誤計數
            
            current_time = datetime.datetime.now()
            max_age_hours = self.max_earthquake_age_hours
            
            # 查找未發送的地震通知
            new_earthquakes = []
            for earthquake in earthquakes:
                eq_id = self._generate_earthquake_id(earthquake)
                
                # 跳過已發送的地震
                if eq_id in self.sent_earthquake_ids:
                    continue
                
                # 檢查地震時間是否在允許範圍內
                eq_time = self._parse_earthquake_time(earthquake)
                if eq_time:
                    time_diff = current_time - eq_time
                    hours_diff = time_diff.total_seconds() / 3600
                    
                    if hours_diff <= max_age_hours:
                        new_earthquakes.append(earthquake)
                        self.sent_earthquake_ids.add(eq_id)
            
            # 發送新地震通知
            if new_earthquakes:
                logger.info(f"發現 {len(new_earthquakes)} 筆新地震")
                for earthquake in new_earthquakes:
                    await self.send_earthquake_notification(earthquake)
                
                # 保存已發送地震ID到配置文件
                self._save_sent_earthquake_ids()
            
        except Exception as e:
            logger.error(f"檢查地震時發生錯誤: {e}")

    def _generate_earthquake_id(self, earthquake):
        """生成地震唯一ID"""
        try:
            # 優先使用EarthquakeNo和OriginTime組合作為ID
            if "EarthquakeNo" in earthquake:
                eq_no = earthquake["EarthquakeNo"]
                if "EarthquakeInfo" in earthquake and "OriginTime" in earthquake["EarthquakeInfo"]:
                    origin_time = earthquake["EarthquakeInfo"]["OriginTime"]
                    return f"{eq_no}_{origin_time}"
                return str(eq_no)
            
            # 備用方案：使用震央位置和發生時間
            if "EarthquakeInfo" in earthquake:
                info = earthquake["EarthquakeInfo"]
                parts = []
                
                if "OriginTime" in info:
                    parts.append(info["OriginTime"])
                
                if "Epicenter" in info and "Location" in info["Epicenter"]:
                    # 取位置中的座標部分
                    location = info["Epicenter"]["Location"]
                    parts.append(location)
                
                if parts:
                    return "_".join(parts)
            
            # 最後方案：直接使用字符串表示
            return str(hash(str(earthquake)))
        except Exception as e:
            logger.error(f"生成地震ID時出錯: {e}")
            return str(hash(str(earthquake)))

    def _parse_earthquake_time(self, earthquake):
        """解析地震發生時間"""
        try:
            if "EarthquakeInfo" in earthquake and "OriginTime" in earthquake["EarthquakeInfo"]:
                time_str = earthquake["EarthquakeInfo"]["OriginTime"]
                # 格式為 "2025-04-01 19:26:02"
                return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            return None
        except Exception as e:
            logger.error(f"解析地震時間時出錯: {e}")
            return None

    def _load_sent_earthquake_ids(self):
        """從配置文件加載已發送的地震ID"""
        try:
            config_dir = "config"
            config_file = os.path.join(config_dir, "earthquake_sent_ids.json")
            
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.sent_earthquake_ids = set(data)
                        logger.info(f"已載入 {len(self.sent_earthquake_ids)} 筆地震ID記錄")
        except Exception as e:
            logger.error(f"載入地震ID記錄時出錯: {e}")
            self.sent_earthquake_ids = set()

    def _save_sent_earthquake_ids(self):
        """保存已發送的地震ID到配置文件"""
        try:
            config_dir = "config"
            # 確保目錄存在
            os.makedirs(config_dir, exist_ok=True)
            
            config_file = os.path.join(config_dir, "earthquake_sent_ids.json")
            
            # 限制保存的ID數量，只保留最近的200個
            ids_to_save = list(self.sent_earthquake_ids)
            if len(ids_to_save) > 200:
                ids_to_save = ids_to_save[-200:]
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(ids_to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存地震ID記錄時出錯: {e}")

    @measure_time
    async def send_earthquake_notification(self, earthquake):
        """發送地震通知到指定頻道"""
        try:
            if not self.channel_id:
                logger.warning("未設置地震通知頻道，無法發送通知")
                return
            
            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                logger.warning(f"找不到頻道 ID: {self.channel_id}，無法發送地震通知")
                return
            
            embed = discord.Embed(
                title="🔴 地震通報",
                description=earthquake.get("ReportContent", "無內容"),
                color=0xFF0000,
                timestamp=datetime.datetime.now()
            )
            
            # 添加地震資訊
            if "EarthquakeInfo" in earthquake:
                info = earthquake["EarthquakeInfo"]
                
                # 添加發生時間
                if "OriginTime" in info:
                    embed.add_field(name="發生時間", value=info["OriginTime"], inline=True)
                
                # 添加震源深度
                if "FocalDepth" in info:
                    embed.add_field(name="震源深度", value=f"{info['FocalDepth']} 公里", inline=True)
                
                # 添加規模資訊
                if "EarthquakeMagnitude" in info:
                    mag = info["EarthquakeMagnitude"]
                    if "MagnitudeValue" in mag:
                        embed.add_field(name="規模", value=mag["MagnitudeValue"], inline=True)
                
                # 添加震央位置
                if "Epicenter" in info and "Location" in info["Epicenter"]:
                    embed.add_field(name="位置", value=info["Epicenter"]["Location"], inline=False)
            
            # 添加最大震度資訊
            if "Intensity" in earthquake and "ShakingArea" in earthquake["Intensity"]:
                areas = earthquake["Intensity"]["ShakingArea"]
                max_intensity_areas = [area for area in areas if area.get("AreaDesc", "").startswith("最大震度")]
                
                if max_intensity_areas:
                    for area in max_intensity_areas:
                        embed.add_field(
                            name=area.get("AreaDesc", "震度資訊"), 
                            value=area.get("CountyName", "未知地區"), 
                            inline=False
                        )
            
            # 添加報告連結
            if "Web" in earthquake:
                embed.add_field(name="詳細資訊", value=earthquake["Web"], inline=False)
            
            # 添加地震圖片
            if "ReportImageURI" in earthquake:
                embed.set_image(url=earthquake["ReportImageURI"])
            
            # 添加頁腳
            embed.set_footer(text="資料來源: 中央氣象署")
            
            # 發送通知
            await channel.send(embed=embed)
            logger.info(f"已發送地震通知: {earthquake.get('ReportContent', '無內容')[:30]}...")
            
        except Exception as e:
            logger.error(f"發送地震通知時出錯: {e}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Earthquake(bot)) 