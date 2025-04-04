import discord
import asyncio
import aiohttp
import json
import datetime
import os
import time
import random
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
    max_stored_earthquakes = 500  # 最多儲存的地震ID數量
    earthquake_id_ttl_days = 30  # 地震ID保留天數
    max_earthquake_age_hours = 24  # 最大地震年齡 (小時)
    
    def __init__(self, bot):
        super().__init__(bot)
        self.session = None
        self.config = load_config('setting.json')
        
        # 初始化已發送的地震ID集合
        self.sent_earthquakes = set()
        
        # 新增: 發送鎖定機制，防止重複發送
        self.sending_lock = False
        self.last_sent_time = {}  # 記錄最近發送時間，格式 {earthquake_id: timestamp}
        self.message_cooldown = 300  # 同一個地震最少間隔發送時間（秒）
        
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
            
        # 設置是否自動廣播今日地震 (預設啟用)
        try:
            broadcast_value = os.environ.get('EARTHQUAKE_BROADCAST_TODAY', 'True')
            # 處理可能的註釋
            if '#' in broadcast_value:
                broadcast_value = broadcast_value.split('#')[0].strip()
            self.broadcast_today_earthquakes = broadcast_value.lower() in ('true', 'yes', '1', 't', 'y')
            logger.info(f"自動廣播今日地震功能: {'啟用' if self.broadcast_today_earthquakes else '停用'}")
        except Exception as e:
            logger.error(f"無法解析自動廣播設定: {e}，使用預設值 True")
            self.broadcast_today_earthquakes = True
        
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
            # 使用正確的 API URL (地震API)
            self.cwb_api_url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001"
        
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
        
        # 設置監測任務 - 確保不會重複啟動
        if not hasattr(self, '_monitoring_started') or not self._monitoring_started:
            self.earthquake_monitoring.start()
            self._monitoring_started = True
            logger.info("已啟動地震監測任務")
        else:
            logger.warning("地震監測任務已經在運行中，跳過重複啟動")
        
        # 啟動日誌清理任務
        if not hasattr(self, '_cleanup_started') or not self._cleanup_started:
            self.cleanup_logs.start()
            self._cleanup_started = True
            logger.info("日誌清理任務已啟動，每三天執行一次")
        else:
            logger.warning("日誌清理任務已經在運行中，跳過重複啟動")
        
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
        if hasattr(self, 'earthquake_monitoring') and self.earthquake_monitoring.is_running():
            self.earthquake_monitoring.cancel()
            self._monitoring_started = False
            logger.info("地震監測任務已取消")
        
        # 取消日誌清理任務
        if hasattr(self, 'cleanup_logs') and self.cleanup_logs.is_running():
            self.cleanup_logs.cancel()
            self._cleanup_started = False
            logger.info("日誌清理任務已取消")
        
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
            # 記錄任務執行時間，用於調試重複執行問題
            exec_id = f"eq_mon_{int(time.time())}"
            logger.debug(f"開始執行地震監測任務 (執行ID: {exec_id})")
            
            # 智能頻率限制 - 使用指數回退策略
            current_time = datetime.datetime.now()
            today = current_time.date()
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
                
                # 過濾出今日地震
                today_earthquakes = []
                for eq in earthquakes:
                    try:
                        # 使用幫助方法獲取時間字段
                        time_str = self.get_earthquake_time_field(eq)
                        if not time_str:
                            logger.warning(f"無法找到地震時間字段，跳過: {eq.get('earthquakeNo', eq.get('EarthquakeNo', eq.get('identifier', 'unknown')))}")
                            continue
                        
                        # 使用幫助方法解析時間
                        eq_time = self.parse_earthquake_time(time_str)
                        if not eq_time:
                            continue
                            
                        if eq_time.date() == today:
                            today_earthquakes.append(eq)
                    except Exception as e:
                        logger.error(f"解析地震時間出錯: {e}")
                        continue
                
                # 如果有今日地震資料，處理並廣播
                if today_earthquakes:
                    # 按時間排序 (使用幫助方法)
                    try:
                        def get_earthquake_time_for_sorting(earthquake):
                            time_str = self.get_earthquake_time_field(earthquake)
                            eq_time = self.parse_earthquake_time(time_str)
                            return eq_time if eq_time else datetime.datetime(1970, 1, 1)
                        
                        today_earthquakes.sort(key=get_earthquake_time_for_sorting, reverse=True)
                    except Exception as e:
                        logger.error(f"排序地震資料出錯: {e}")
                    
                    # 獲取最新的一個地震
                    latest_eq = today_earthquakes[0]
                    
                    # 取得地震ID，嘗試不同的字段名稱
                    eq_id = latest_eq.get('earthquakeNo', latest_eq.get('EarthquakeNo', latest_eq.get('identifier', '')))
                    
                    # 檢查是否已經發送過
                    if eq_id and eq_id not in self.last_earthquakes and eq_id not in self.sent_earthquakes:
                        # 檢查是否啟用自動廣播功能
                        if self.broadcast_today_earthquakes:
                            # 解析規模
                            magnitude_value = 0.0
                            try:
                                # 嘗試從不同位置獲取規模值
                                if 'magnitudeValue' in latest_eq:
                                    magnitude_value = float(latest_eq['magnitudeValue'])
                                elif 'MagnitudeValue' in latest_eq:
                                    magnitude_value = float(latest_eq['MagnitudeValue'])
                                # 處理嵌套結構
                                elif 'EarthquakeMagnitude' in latest_eq:
                                    magnitude_value = float(latest_eq['EarthquakeMagnitude'].get('MagnitudeValue', 0))
                                elif 'earthquakeMagnitude' in latest_eq:
                                    magnitude_value = float(latest_eq['earthquakeMagnitude'].get('magnitudeValue', 0))
                            except (TypeError, ValueError):
                                magnitude_value = 0.0
                            
                            # 僅在規模大於一定值時添加@everyone提及
                            mention_everyone = magnitude_value >= 4.0
                            
                            # 發送地震警報
                            await self.send_earthquake_alert(latest_eq, mention_everyone=mention_everyone)
                            
                            # 獲取時間顯示用於日誌
                            time_display = self.get_earthquake_time_field(latest_eq) or "未知時間"
                            logger.info(f"自動廣播今日最新地震: {eq_id}, 發生時間: {time_display}, 規模: {magnitude_value}")
                        else:
                            # 僅記錄，不廣播
                            time_display = self.get_earthquake_time_field(latest_eq) or "未知時間"
                            logger.info(f"檢測到今日最新地震: {eq_id}, 發生時間: {time_display}, 自動廣播功能已停用")
                        
                        # 將地震加入已處理集合和時間戳記錄
                        self.last_earthquakes.add(eq_id)
                        self.sent_earthquakes.add(eq_id)
                        self.earthquake_timestamps[eq_id] = current_time.timestamp()
                        
                        # 保存已發送的地震ID
                        self._save_sent_earthquake_ids()
                        self._save_earthquake_state()
                    else:
                        # 記錄為什麼沒有發送此地震
                        if eq_id in self.last_earthquakes or eq_id in self.sent_earthquakes:
                            sent_time = self.earthquake_timestamps.get(eq_id, 0)
                            time_ago = (current_time.timestamp() - sent_time) if sent_time else 0
                            logger.debug(f"跳過已處理的地震: {eq_id}, 之前已發送過 ({int(time_ago)}秒前)")
                else:
                    logger.debug("監測中，今日暫無地震資料")
            else:
                # 更新錯誤計數和時間
                self.consecutive_errors = consecutive_errors + 1
                self.last_api_error_time = current_time
                logger.warning(f"無法獲取地震數據 (連續錯誤次數: {self.consecutive_errors})")
                
            logger.debug(f"地震監測任務完成 (執行ID: {exec_id})")
                
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
                    
                    # 顯示API響應數據結構以便調試
                    logger.debug(f"API響應數據結構: {list(data['records'].keys())}")
                    
                    # 處理 E-A0015-001 API 結構 (地震API) - 同時處理大小寫
                    records = data["records"]
                    
                    # 檢查小寫 "earthquake" 字段
                    if "earthquake" in records:
                        earthquakes = records["earthquake"]
                        logger.info(f"成功取得 {len(earthquakes)} 筆地震資料 (小寫字段)")
                        return earthquakes
                    # 檢查大寫 "Earthquake" 字段
                    elif "Earthquake" in records:
                        earthquakes = records["Earthquake"]
                        logger.info(f"成功取得 {len(earthquakes)} 筆地震資料 (大寫字段)")
                        return earthquakes
                    else:
                        logger.error(f"API 回應中沒有地震資料: {list(records.keys())}")
                        return None
                    
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
        """處理地震數據並發送通知 (向後兼容方法)"""
        logger.warning("process_earthquakes方法已棄用，請使用earthquake_monitoring替代")
        
        if not earthquakes:
            logger.debug("沒有地震數據可處理")
            return
            
        current_time = datetime.datetime.now()
        today = current_time.date()
        
        # 過濾今日地震
        today_earthquakes = []
        for eq in earthquakes:
            try:
                # 使用新的幫助方法獲取時間字段
                time_str = self.get_earthquake_time_field(eq)
                if not time_str:
                    continue
                
                # 使用新的解析方法
                eq_time = self.parse_earthquake_time(time_str)
                if not eq_time:
                    continue
                    
                if eq_time.date() == today:
                    today_earthquakes.append(eq)
            except Exception as e:
                logger.error(f"解析地震時間出錯: {e}")
                continue
        
        if not today_earthquakes:
            logger.debug("今日沒有地震資料")
            return
            
        # 按時間排序 (使用新的解析方法)
        try:
            def get_earthquake_time_for_sorting(earthquake):
                time_str = self.get_earthquake_time_field(earthquake)
                eq_time = self.parse_earthquake_time(time_str)
                return eq_time if eq_time else datetime.datetime(1970, 1, 1)
            
            today_earthquakes.sort(key=get_earthquake_time_for_sorting, reverse=True)
        except Exception as e:
            logger.error(f"排序地震資料出錯: {e}")
        
        # 獲取最新的一個地震
        latest_eq = today_earthquakes[0]
        
        # 取得地震ID
        eq_id = latest_eq.get('earthquakeNo', latest_eq.get('EarthquakeNo', latest_eq.get('identifier', '')))
        
        # 檢查是否已經發送過
        if eq_id and eq_id not in self.last_earthquakes and eq_id not in self.sent_earthquakes:
            # 檢查是否啟用自動廣播功能
            if self.broadcast_today_earthquakes:
                # 發送地震警報 (全體通知)
                await self.send_earthquake_alert(latest_eq, mention_everyone=True)
                logger.info(f"自動廣播今日最新地震: {eq_id}, 發生時間: {latest_eq.get('originTime', latest_eq.get('time'))}")
            else:
                # 僅記錄，不廣播
                logger.info(f"檢測到今日最新地震: {eq_id}, 發生時間: {latest_eq.get('originTime', latest_eq.get('time'))}, 自動廣播功能已停用")
            
            # 將地震加入已處理集合和時間戳記錄
            self.last_earthquakes.add(eq_id)
            self.sent_earthquakes.add(eq_id)
            self.earthquake_timestamps[eq_id] = current_time.timestamp()
            
            # 保存已發送的地震ID
            self._save_sent_earthquake_ids()
            self._save_earthquake_state()
    
    def _generate_earthquake_id(self, earthquake):
        """生成地震唯一ID"""
        try:
            # 使用EarthquakeNo作為主要ID
            if "earthquakeNo" in earthquake or "EarthquakeNo" in earthquake:
                eq_no = earthquake.get("earthquakeNo", earthquake.get("EarthquakeNo", ""))
                return str(eq_no)
            
            # 備用方案：使用震央位置和發生時間
            parts = []
            
            # 嘗試獲取時間
            origin_time = earthquake.get("originTime", earthquake.get("OriginTime", ""))
            if origin_time:
                parts.append(origin_time)
            
            # 嘗試獲取震央位置
            location = earthquake.get("location", earthquake.get("Location", ""))
            if location:
                parts.append(location)
            
            if parts:
                return "_".join(parts)
            
            # 最後方案：直接使用字符串表示
            return str(hash(str(earthquake)))
        except Exception as e:
            logger.error(f"生成地震ID時出錯: {e}")
            return str(hash(str(earthquake)))

    def _parse_earthquake_time(self, earthquake):
        """解析地震發生時間 (已棄用，請使用 parse_earthquake_time 方法)"""
        logger.warning("_parse_earthquake_time 方法已棄用，請使用 parse_earthquake_time 方法")
        # 獲取時間字段
        time_str = None
        if isinstance(earthquake, str):
            time_str = earthquake
        else:
            time_str = earthquake.get("originTime", 
                      earthquake.get("OriginTime", 
                      earthquake.get("time", "")))
        
        # 使用新方法解析時間
        return self.parse_earthquake_time(time_str)

    def _load_sent_earthquake_ids(self):
        """從配置文件加載已發送的地震ID"""
        try:
            config_dir = "config"
            config_file = os.path.join(config_dir, "earthquake_sent_ids.json")
            
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.sent_earthquakes = set(data)
                        logger.info(f"已載入 {len(self.sent_earthquakes)} 筆地震ID記錄")
        except Exception as e:
            logger.error(f"載入地震ID記錄時出錯: {e}")
            self.sent_earthquakes = set()

    def _save_sent_earthquake_ids(self):
        """保存已發送的地震ID到配置文件"""
        try:
            config_dir = "config"
            # 確保目錄存在
            os.makedirs(config_dir, exist_ok=True)
            
            config_file = os.path.join(config_dir, "earthquake_sent_ids.json")
            
            # 限制保存的ID數量，只保留最近的200個
            ids_to_save = list(self.sent_earthquakes)
            if len(ids_to_save) > 200:
                ids_to_save = ids_to_save[-200:]
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(ids_to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存地震ID記錄時出錯: {e}")

    @measure_time
    async def send_earthquake_alert(self, earthquake: Dict[str, Any], mention_everyone: bool = False) -> None:
        """發送地震警報到頻道"""
        # 獲取地震ID，嘗試不同的字段名稱
        eq_id = earthquake.get('earthquakeNo', earthquake.get('EarthquakeNo', earthquake.get('identifier', '未知ID')))
        
        # 檢查鎖定機制和冷卻時間，防止重複發送
        current_time = time.time()
        
        # 同一個ID短時間內不重複發送 - 使用更短的時間窗口（5秒）來防止任何形式的重複發送
        if eq_id in self.last_sent_time:
            time_since_last_send = current_time - self.last_sent_time[eq_id]
            if time_since_last_send < 5:  # 5秒內絕對不重複發送
                logger.warning(f"防止重複發送: 地震ID {eq_id} 在 {int(time_since_last_send)} 秒前剛剛發送過")
                return
            elif time_since_last_send < self.message_cooldown:  # 正常冷卻時間
                logger.info(f"忽略重複的地震警報 (ID: {eq_id})，距上次發送僅 {int(time_since_last_send)} 秒")
                return
        
        # 檢查全局鎖定
        if self.sending_lock:
            logger.info("忽略地震警報：另一個發送操作正在進行")
            return
            
        # 設置鎖定 - 但先更新發送時間，以防止並發調用
        self.last_sent_time[eq_id] = current_time
        self.sending_lock = True
        
        try:
            # 嘗試獲取頻道，使用緩存減少API調用
            channel_id = self.channel_id
            if not channel_id:
                logger.error("未設置地震通知頻道ID")
                self.sending_lock = False  # 釋放鎖定
                return
                
            channel = self.bot.get_channel(channel_id)
            if not channel:
                # 如果緩存無效，嘗試重新獲取（很少需要）
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.NotFound:
                    logger.error(f"地震通知頻道不存在: {channel_id}")
                    self.sending_lock = False  # 釋放鎖定
                    return
                except discord.Forbidden:
                    logger.error(f"無權訪問地震通知頻道: {channel_id}")
                    self.sending_lock = False  # 釋放鎖定
                    return
                except Exception as e:
                    logger.error(f"獲取地震通知頻道失敗: {e}", exc_info=True)
                    self.sending_lock = False  # 釋放鎖定
                    return
            
            # 構建訊息
            source = earthquake.get('source', '中央氣象局')
            embed = None
            
            # 處理地震規模信息，嘗試不同的字段名稱
            magnitude_value = 0.0
            try:
                # 嘗試從不同位置獲取規模值
                if 'magnitudeValue' in earthquake:
                    magnitude_value = float(earthquake['magnitudeValue'])
                elif 'MagnitudeValue' in earthquake:
                    magnitude_value = float(earthquake['MagnitudeValue'])
                # 處理嵌套結構
                elif 'EarthquakeMagnitude' in earthquake:
                    magnitude_value = float(earthquake['EarthquakeMagnitude'].get('MagnitudeValue', 0))
                elif 'earthquakeMagnitude' in earthquake:
                    magnitude_value = float(earthquake['earthquakeMagnitude'].get('magnitudeValue', 0))
            except (TypeError, ValueError) as e:
                logger.warning(f"無法解析地震規模: {e}")
                magnitude_value = 0.0
            
            try:
                embed = await self._create_cwb_earthquake_embed(earthquake, magnitude_value, eq_id, source)
            except Exception as e:
                logger.error(f"創建地震嵌入消息失敗: {e}", exc_info=True)
                embed = None
            
            # 如果失敗，創建一個基本的嵌入消息
            if embed is None:
                logger.warning(f"無法創建地震嵌入消息，使用通用格式")
                # 獲取基本信息，嘗試不同的字段名稱
                time_str = earthquake.get('originTime', earthquake.get('OriginTime', '未知時間'))
                location = earthquake.get('location', earthquake.get('Location', '未知位置'))
                report = earthquake.get('reportContent', earthquake.get('ReportContent', ''))
                
                # 創建顏色
                color = self.get_color_by_magnitude(magnitude_value)
                
                # 創建標題
                title = f"🔴 地震通報 規模 {magnitude_value}"
                
                # 創建描述
                description = report if report else f"震央位置：{location}，規模：{magnitude_value}"
                
                # 創建嵌入消息
                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=color,
                    timestamp=datetime.datetime.now()
                )
                
                # 添加基本字段
                embed.add_field(name="發生時間", value=time_str, inline=True)
                embed.add_field(name="震央位置", value=location, inline=True)
                
                # 處理深度信息，嘗試不同的字段名稱
                depth_value = "未知"
                depth_unit = "公里"
                if 'depth' in earthquake:
                    depth_value = earthquake['depth'].get('value', "未知")
                    depth_unit = earthquake['depth'].get('unit', "公里")
                elif 'Depth' in earthquake:
                    depth_value = earthquake['Depth'].get('Value', "未知")
                    depth_unit = earthquake['Depth'].get('Unit', "公里")
                elif 'FocalDepth' in earthquake:
                    depth_value = earthquake['FocalDepth']
                
                embed.add_field(name="震源深度", value=f"{depth_value} {depth_unit}", inline=True)
                embed.set_footer(text=f"資料來源: {source} | ID: {eq_id}")
            
            # 添加@everyone提及
            content = "@everyone 注意！發生地震！" if mention_everyone else None
            
            # 發送消息
            await channel.send(content=content, embed=embed)
            logger.info(f"已發送地震警報到頻道 {channel.name} (ID: {channel.id})")
            
            # 更新最後發送時間
            self.last_sent_time[eq_id] = current_time
            
        except Exception as e:
            logger.error(f"發送地震警報失敗: {e}", exc_info=True)
        finally:
            # 確保鎖定最終會被釋放
            self.sending_lock = False

    async def _create_cwb_earthquake_embed(self, earthquake: Dict[str, Any], magnitude_value: float, eq_id: str, source: str) -> discord.Embed:
        """創建中央氣象局地震嵌入消息 (支持不同API格式)"""
        try:
            # 獲取基本信息，嘗試不同的字段名稱
            origin_time = earthquake.get('originTime', earthquake.get('OriginTime', '未知時間'))
            location = earthquake.get('location', earthquake.get('Location', '未知位置'))
            
            # 防止location是字典而非字符串
            if isinstance(location, dict):
                if 'locationName' in location:
                    location = location['locationName']
                elif 'name' in location:
                    location = location['name']
                else:
                    location = '未知位置'
            
            # 處理深度信息
            focal_depth = "未知"
            depth_unit = "公里"
            
            try:
                if 'depth' in earthquake:
                    if isinstance(earthquake['depth'], dict):
                        focal_depth = earthquake['depth'].get('value', "未知")
                        depth_unit = earthquake['depth'].get('unit', "公里")
                    else:
                        # 直接使用數值
                        focal_depth = earthquake['depth']
                elif 'Depth' in earthquake:
                    if isinstance(earthquake['Depth'], dict):
                        focal_depth = earthquake['Depth'].get('Value', "未知")
                        depth_unit = earthquake['Depth'].get('Unit', "公里")
                    else:
                        focal_depth = earthquake['Depth']
                elif 'FocalDepth' in earthquake:
                    focal_depth = earthquake['FocalDepth']
            except Exception as e:
                logger.warning(f"處理深度信息時出錯: {e}")
                focal_depth = "未知"
                
            # 獲取報告內容
            report_content = earthquake.get('reportContent', earthquake.get('ReportContent', ''))
            if not report_content:
                report_content = f"震央位置：{location}，規模：{magnitude_value}，深度：{focal_depth}{depth_unit}"
            
            # 處理經緯度
            lon = None
            lat = None
            
            try:
                # 不同API可能有不同的經緯度字段結構
                if 'epicenter' in earthquake:
                    lon = earthquake['epicenter'].get('lon')
                    lat = earthquake['epicenter'].get('lat')
                elif 'Epicenter' in earthquake:
                    lon = earthquake['Epicenter'].get('Longitude')
                    lat = earthquake['Epicenter'].get('Latitude')
                elif 'location' in earthquake:
                    if isinstance(earthquake['location'], dict):
                        loc_data = earthquake['location']
                        lon = loc_data.get('longitude') or loc_data.get('lon') or loc_data.get('coordinateX')
                        lat = loc_data.get('latitude') or loc_data.get('lat') or loc_data.get('coordinateY')
                    elif isinstance(earthquake['location'], str) and 'coordinateX' in earthquake and 'coordinateY' in earthquake:
                        # 如果location是字符串但有單獨的坐標字段
                        lon = earthquake.get('coordinateX')
                        lat = earthquake.get('coordinateY')
            except Exception as e:
                logger.warning(f"處理經緯度信息時出錯: {e}")
                lon = None
                lat = None
            
            # 創建嵌入消息的顏色基於地震規模
            color = self.get_color_by_magnitude(magnitude_value)
            
            # 計算相對時間文本
            time_display = origin_time
            try:
                eq_time = self.parse_earthquake_time(origin_time)
                if eq_time:
                    now = datetime.datetime.now()
                    time_diff = now - eq_time
                    
                    if time_diff.total_seconds() < 60:
                        time_ago = f"{int(time_diff.total_seconds())}秒前"
                    elif time_diff.total_seconds() < 3600:
                        time_ago = f"{int(time_diff.total_seconds() / 60)}分鐘前"
                    else:
                        time_ago = f"{int(time_diff.total_seconds() / 3600)}小時前"
                    
                    time_display = f"{origin_time} ({time_ago})"
            except Exception as e:
                logger.warning(f"計算相對時間時出錯: {e}")
            
            # 創建嵌入消息
            embed = discord.Embed(
                title=f"🔴 地震通報 規模 {magnitude_value}",
                description=report_content,
                color=color,
                timestamp=datetime.datetime.now()
            )
            
            # 添加地震資訊
            embed.add_field(name="發生時間", value=time_display, inline=True)
            embed.add_field(name="震央位置", value=location, inline=True)
            embed.add_field(name="震源深度", value=f"{focal_depth} {depth_unit}", inline=True)
            
            # 添加最大震度資訊
            try:
                # 處理不同的震度字段結構
                max_intensity = None
                max_intensity_location = None
                
                if 'intensity' in earthquake:
                    intensity_data = earthquake['intensity']
                    if isinstance(intensity_data, dict) and 'shakingArea' in intensity_data:
                        shaking_areas = intensity_data['shakingArea']
                        if isinstance(shaking_areas, list) and len(shaking_areas) > 0:
                            for area in shaking_areas:
                                if area.get('areaDesc', '').startswith('最大震度'):
                                    max_intensity = area.get('areaDesc', '')
                                    max_intensity_location = area.get('areaName', '')
                                    break
                
                elif 'Intensity' in earthquake:
                    intensity_data = earthquake['Intensity']
                    if isinstance(intensity_data, dict) and 'ShakingArea' in intensity_data:
                        shaking_areas = intensity_data['ShakingArea']
                        if isinstance(shaking_areas, list) and len(shaking_areas) > 0:
                            for area in shaking_areas:
                                if area.get('AreaDesc', '').startswith('最大震度'):
                                    max_intensity = area.get('AreaDesc', '')
                                    max_intensity_location = area.get('CountyName', '')
                                    break
                
                # 如果找到最大震度信息，添加到嵌入消息
                if max_intensity and max_intensity_location:
                    embed.add_field(
                        name=max_intensity,
                        value=max_intensity_location,
                        inline=False
                    )
            except Exception as e:
                logger.warning(f"處理震度資訊時出錯: {e}")
            
            # 添加外部鏈接
            try:
                if 'web' in earthquake:
                    embed.add_field(
                        name="詳細資訊",
                        value=f"[中央氣象局官網]({earthquake['web']})",
                        inline=False
                    )
                elif 'Web' in earthquake:
                    embed.add_field(
                        name="詳細資訊",
                        value=f"[中央氣象局官網]({earthquake['Web']})",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="詳細資訊",
                        value=f"[中央氣象局]({self._get_cwb_earthquake_url(eq_id)})",
                        inline=False
                    )
            except Exception as e:
                logger.warning(f"添加外部鏈接時出錯: {e}")
                embed.add_field(
                    name="詳細資訊",
                    value=f"[中央氣象局]({self._get_cwb_earthquake_url(eq_id)})",
                    inline=False
                )
            
            # 設置頁腳
            embed.set_footer(text=f"資料來源: {source} | ID: {eq_id}")
            
            # 添加地震圖片
            try:
                if 'reportImageURI' in earthquake and earthquake['reportImageURI']:
                    embed.set_image(url=earthquake['reportImageURI'])
                elif 'ReportImageURI' in earthquake and earthquake['ReportImageURI']:
                    embed.set_image(url=earthquake['ReportImageURI'])
                # 如果沒有報告圖片但有震央經緯度，添加地圖
                elif lon and lat:
                    map_url = self._get_google_maps_url(lat, lon)
                    embed.set_image(url=map_url)
            except Exception as e:
                logger.warning(f"添加地震圖片時出錯: {e}")
            
            return embed
            
        except Exception as e:
            logger.error(f"創建地震嵌入消息失敗: {e}", exc_info=True)
            # 返回一個非常基本的嵌入消息
            basic_embed = discord.Embed(
                title=f"🔴 地震通報",
                description=f"收到地震通報，但無法解析完整資訊，ID: {eq_id}",
                color=0xFF0000,
                timestamp=datetime.datetime.now()
            )
            basic_embed.set_footer(text=f"資料來源: {source} | ID: {eq_id}")
            return basic_embed

    def _get_google_maps_url(self, lat: float, lon: float, zoom: int = 9) -> str:
        """生成Google Maps靜態地圖URL"""
        # 使用Google Maps Static API
        return f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom={zoom}&size=600x300&maptype=roadmap&markers=color:red%7C{lat},{lon}&key=YOUR_KEY"
        
    def _get_cwb_earthquake_url(self, eq_id: str) -> str:
        """生成中央氣象局地震詳情頁面URL"""
        # 實際的URL格式可能需要根據中央氣象局網站調整
        return f"https://www.cwb.gov.tw/V8/C/E/EQ/EQ_list.html"

    @commands.command(name="手動地震測試全體")
    @commands.has_permissions(administrator=True)
    async def manual_earthquake_test_everyone(self, ctx):
        """測試地震廣播功能（包含全體通知）"""
        test_id = f"TEST-{int(time.time())}"
        
        # 創建測試資料
        test_earthquake = {
            'earthquakeNo': test_id,
            'reportContent': '這是一則測試地震警報，請勿驚慌',
            'originTime': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'magnitudeValue': 4.5,
            'location': '測試位置',
            'depth': {
                'value': 10.0,
                'unit': 'km'
            },
            'coordinate': {
                'longitude': 121.5,
                'latitude': 25.0
            },
            'source': '測試資料'
        }
        
        try:
            await self.send_earthquake_alert(test_earthquake, mention_everyone=True)
            # 不要將測試數據添加到實際地震ID列表中
            await ctx.send(f"地震警報測試完成! 測試ID: {test_id}")
            logger.info(f"管理員 {ctx.author.name} 執行了全體通知地震警報測試，ID: {test_id}")
        except Exception as e:
            await ctx.send(f"❌ 地震警報測試失敗: {str(e)}")
            logger.error(f"地震警報測試失敗: {e}", exc_info=True)

    @commands.command(name="今日地震")
    async def today_earthquake(self, ctx):
        """顯示今日最新地震資訊"""
        await ctx.send("正在查詢今日最新地震資訊...")
        
        try:
            # 獲取今日日期
            today = datetime.datetime.now().date()
            
            # 獲取最新地震資料
            earthquakes = await self.fetch_earthquake_data()
            
            if not earthquakes:
                await ctx.send("❌ 無法獲取地震資料")
                return
            
            # 過濾出今日地震
            today_earthquakes = []
            for eq in earthquakes:
                try:
                    # 使用幫助方法獲取和解析時間
                    time_str = self.get_earthquake_time_field(eq)
                    if not time_str:
                        continue
                    
                    eq_time = self.parse_earthquake_time(time_str)
                    if not eq_time:
                        continue
                        
                    if eq_time.date() == today:
                        today_earthquakes.append(eq)
                except Exception as e:
                    logger.error(f"解析地震時間出錯: {e}")
                    continue
            
            # 按時間排序 (使用幫助方法)
            try:
                def get_earthquake_time_for_sorting(earthquake):
                    time_str = self.get_earthquake_time_field(earthquake)
                    eq_time = self.parse_earthquake_time(time_str)
                    return eq_time if eq_time else datetime.datetime(1970, 1, 1)
                
                today_earthquakes.sort(key=get_earthquake_time_for_sorting, reverse=True)
            except Exception as e:
                logger.error(f"排序地震時間出錯: {e}")
            
            if not today_earthquakes:
                await ctx.send("🔍 今日尚無地震資料")
                return
            
            # 獲取最新的一個地震
            latest_eq = today_earthquakes[0]
            
            # 獲取地震ID (嘗試不同的字段名稱)
            eq_id = latest_eq.get('earthquakeNo', latest_eq.get('EarthquakeNo', latest_eq.get('identifier', '未知ID')))
            
            # 發送地震警報
            await self.send_earthquake_alert(latest_eq)
            
            await ctx.send(f"✅ 已發送今日最新地震資訊 (ID: {eq_id})")
            logger.info(f"使用者 {ctx.author.name} 使用今日地震命令查詢，發送了ID為 {eq_id} 的地震資訊")
            
        except Exception as e:
            await ctx.send(f"❌ 查詢今日地震失敗: {str(e)}")
            logger.error(f"查詢今日地震失敗: {e}", exc_info=True)
    
    @commands.command(name="今日地震廣播")
    @commands.has_permissions(administrator=True)
    async def today_earthquake_broadcast(self, ctx):
        """廣播今日最新地震資訊（包含全體通知）"""
        await ctx.send("正在獲取今日最新地震資訊，準備廣播...")
        
        try:
            # 獲取今日日期
            today = datetime.datetime.now().date()
            
            # 獲取最新地震資料
            earthquakes = await self.fetch_earthquake_data()
            
            if not earthquakes:
                await ctx.send("❌ 無法獲取地震資料")
                return
            
            # 過濾出今日地震
            today_earthquakes = []
            for eq in earthquakes:
                try:
                    # 使用幫助方法獲取時間字段
                    time_str = self.get_earthquake_time_field(eq)
                    if not time_str:
                        logger.warning(f"無法找到地震時間字段，跳過: {eq.get('earthquakeNo', eq.get('EarthquakeNo', eq.get('identifier', 'unknown')))}")
                        continue
                    
                    # 使用幫助方法解析時間
                    eq_time = self.parse_earthquake_time(time_str)
                    if not eq_time:
                        continue
                        
                    if eq_time.date() == today:
                        today_earthquakes.append(eq)
                except Exception as e:
                    logger.error(f"解析地震時間出錯: {e}")
                    continue
            
            # 如果有今日地震資料，處理並廣播
            if today_earthquakes:
                # 按時間排序 (使用幫助方法)
                try:
                    def get_earthquake_time_for_sorting(earthquake):
                        time_str = self.get_earthquake_time_field(earthquake)
                        eq_time = self.parse_earthquake_time(time_str)
                        return eq_time if eq_time else datetime.datetime(1970, 1, 1)
                    
                    today_earthquakes.sort(key=get_earthquake_time_for_sorting, reverse=True)
                except Exception as e:
                    logger.error(f"排序地震資料出錯: {e}")
                
                # 獲取最新的一個地震
                latest_eq = today_earthquakes[0]
                
                # 取得地震ID，嘗試不同的字段名稱
                eq_id = latest_eq.get('earthquakeNo', latest_eq.get('EarthquakeNo', latest_eq.get('identifier', '')))
                
                # 檢查是否已經發送過
                if eq_id and eq_id not in self.last_earthquakes and eq_id not in self.sent_earthquakes:
                    # 檢查是否啟用自動廣播功能
                    if self.broadcast_today_earthquakes:
                        # 解析規模
                        magnitude_value = 0.0
                        try:
                            # 嘗試從不同位置獲取規模值
                            if 'magnitudeValue' in latest_eq:
                                magnitude_value = float(latest_eq['magnitudeValue'])
                            elif 'MagnitudeValue' in latest_eq:
                                magnitude_value = float(latest_eq['MagnitudeValue'])
                            # 處理嵌套結構
                            elif 'EarthquakeMagnitude' in latest_eq:
                                magnitude_value = float(latest_eq['EarthquakeMagnitude'].get('MagnitudeValue', 0))
                            elif 'earthquakeMagnitude' in latest_eq:
                                magnitude_value = float(latest_eq['earthquakeMagnitude'].get('magnitudeValue', 0))
                        except (TypeError, ValueError):
                            magnitude_value = 0.0
                        
                        # 僅在規模大於一定值時添加@everyone提及
                        mention_everyone = magnitude_value >= 4.0
                        
                        # 發送地震警報
                        await self.send_earthquake_alert(latest_eq, mention_everyone=mention_everyone)
                        
                        # 獲取時間顯示用於日誌
                        time_display = self.get_earthquake_time_field(latest_eq) or "未知時間"
                        logger.info(f"自動廣播今日最新地震: {eq_id}, 發生時間: {time_display}, 規模: {magnitude_value}")
                    else:
                        # 僅記錄，不廣播
                        time_display = self.get_earthquake_time_field(latest_eq) or "未知時間"
                        logger.info(f"檢測到今日最新地震: {eq_id}, 發生時間: {time_display}, 自動廣播功能已停用")
                    
                    # 將地震加入已處理集合和時間戳記錄
                    self.last_earthquakes.add(eq_id)
                    self.sent_earthquakes.add(eq_id)
                    self.earthquake_timestamps[eq_id] = current_time.timestamp()
                    
                    # 保存已發送的地震ID
                    self._save_sent_earthquake_ids()
                    self._save_earthquake_state()
                else:
                    # 記錄為什麼沒有發送此地震
                    if eq_id in self.last_earthquakes or eq_id in self.sent_earthquakes:
                        sent_time = self.earthquake_timestamps.get(eq_id, 0)
                        time_ago = (current_time.timestamp() - sent_time) if sent_time else 0
                        logger.debug(f"跳過已處理的地震: {eq_id}, 之前已發送過 ({int(time_ago)}秒前)")
            else:
                logger.debug("監測中，今日暫無地震資料")
            
            if not today_earthquakes:
                await ctx.send("🔍 今日尚無地震資料")
                return
            
            # 獲取最新的一個地震
            latest_eq = today_earthquakes[0]
            
            # 獲取地震ID (嘗試不同的字段名稱)
            eq_id = latest_eq.get('earthquakeNo', latest_eq.get('EarthquakeNo', latest_eq.get('identifier', '未知ID')))
            
            # 發送地震警報，包含全體通知
            await self.send_earthquake_alert(latest_eq, mention_everyone=True)
            
            await ctx.send(f"✅ 已廣播今日最新地震資訊 (ID: {eq_id})")
            logger.info(f"管理員 {ctx.author.name} 使用今日地震廣播命令，發送了ID為 {eq_id} 的全體通知地震資訊")
            
        except Exception as e:
            await ctx.send(f"❌ 廣播今日地震失敗: {str(e)}")
            logger.error(f"廣播今日地震失敗: {e}", exc_info=True)

    @commands.command(name="設置地震廣播")
    @commands.has_permissions(administrator=True)
    async def set_earthquake_broadcast(self, ctx, enabled: bool = None):
        """設置是否自動廣播今日地震 (需要管理員權限)
        
        參數:
            enabled: 是否啟用 (True/False)，不提供則顯示當前狀態
        """
        if enabled is None:
            # 顯示當前狀態
            status = "啟用" if self.broadcast_today_earthquakes else "停用"
            await ctx.send(f"🔊 自動廣播今日地震功能目前為: **{status}**")
            return
            
        # 更新設置
        self.broadcast_today_earthquakes = enabled
        status = "啟用" if enabled else "停用"
        
        # 更新環境變數 (僅記憶體中，不持久化到.env文件)
        os.environ['EARTHQUAKE_BROADCAST_TODAY'] = str(enabled)
        
        # 更新配置文件
        self.config['EARTHQUAKE_BROADCAST_TODAY'] = str(enabled)
        save_config('setting.json', self.config)
        
        await ctx.send(f"✅ 已{status}自動廣播今日地震功能")
        logger.info(f"管理員 {ctx.author.name} 已{status}自動廣播今日地震功能")
        
    @set_earthquake_broadcast.error
    async def set_earthquake_broadcast_error(self, ctx, error):
        """設置地震廣播命令的錯誤處理"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ 你沒有權限執行此命令，需要管理員權限。")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ 參數格式錯誤。請使用 `True` 或 `False`")
        else:
            await ctx.send(f"❌ 執行命令時出錯: {str(error)}")
            logger.error(f"設置地震廣播命令錯誤: {error}")

    @tasks.loop(hours=72)  # 每三天運行一次
    async def cleanup_logs(self):
        """定期清理舊日誌文件，保留當天的日誌"""
        try:
            logger.info("開始執行日誌清理任務")
            
            # 確保logs目錄存在
            if not os.path.exists('logs'):
                logger.warning("logs目錄不存在，跳過清理")
                return
                
            # 獲取當前日期
            today = datetime.datetime.now().strftime('%Y%m%d')
            
            # 列出所有日誌文件
            deleted_count = 0
            for filename in os.listdir('logs'):
                if filename.endswith('.log'):
                    # 檢查是否為當天的日誌
                    if today not in filename:
                        try:
                            file_date = filename.split('_')[1][:8]  # 提取日期部分 YYYYMMDD
                            file_datetime = datetime.datetime.strptime(file_date, '%Y%m%d')
                            
                            # 計算日誌文件的年齡（天數）
                            age_days = (datetime.datetime.now() - file_datetime).days
                            
                            # 如果超過3天，則刪除
                            if age_days >= 3:
                                os.remove(os.path.join('logs', filename))
                                deleted_count += 1
                                logger.debug(f"已刪除舊日誌: {filename}, 年齡: {age_days}天")
                        except (ValueError, IndexError) as e:
                            logger.warning(f"無法解析日誌文件日期: {filename}, 錯誤: {e}")
                            continue
            
            logger.info(f"日誌清理完成，共刪除 {deleted_count} 個舊日誌文件")
            
        except Exception as e:
            logger.error(f"清理日誌時發生錯誤: {e}", exc_info=True)
    
    @cleanup_logs.before_loop
    async def before_cleanup_logs(self):
        """等待機器人準備好後再開始清理日誌"""
        await self.bot.wait_until_ready()
        # 隨機延遲1-10分鐘，避免所有任務同時啟動
        await asyncio.sleep(random.randint(60, 600))
        
    @cleanup_logs.error
    async def cleanup_logs_error(self, error):
        """處理日誌清理任務的錯誤"""
        logger.error(f"日誌清理任務出錯: {error}", exc_info=True)

    @commands.command(name="立即地震監測")
    @commands.has_permissions(administrator=True)
    async def immediate_earthquake_check(self, ctx):
        """立即執行一次地震監測並發送最新資訊 (僅限管理員)"""
        await ctx.send("🔍 正在立即執行地震監測...")
        
        try:
            # 避免頻率限制檢查，直接獲取最新地震資料
            earthquakes = await self.fetch_earthquake_data()
            
            if not earthquakes:
                await ctx.send("❌ 無法獲取地震資料")
                return
                
            current_time = datetime.datetime.now()
            today = current_time.date()
            
            # 過濾今日地震
            today_earthquakes = []
            for eq in earthquakes:
                try:
                    time_str = eq.get('originTime', eq.get('time', ''))
                    if not time_str:
                        continue
                    
                    eq_time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                    if eq_time.date() == today:
                        today_earthquakes.append(eq)
                except Exception as e:
                    logger.error(f"解析地震時間出錯: {e}")
                    continue
            
            if not today_earthquakes:
                await ctx.send("🔍 今日尚無地震資料")
                return
                
            # 按時間排序
            today_earthquakes.sort(
                key=lambda eq: datetime.datetime.strptime(
                    eq.get('originTime', eq.get('time', '1970-01-01 00:00:00')), 
                    '%Y-%m-%d %H:%M:%S'
                ),
                reverse=True
            )
            
            # 獲取最新的地震
            latest_eq = today_earthquakes[0]
            
            # 取得地震ID
            eq_id = latest_eq.get('earthquakeNo', latest_eq.get('identifier', '未知ID'))
            
            # 檢查是否已經發送過
            already_sent = eq_id in self.sent_earthquakes
            status_msg = f"ID: {eq_id}, 發生時間: {latest_eq.get('originTime', latest_eq.get('time', '未知'))}\n"
            status_msg += f"已處理狀態: {'✅ 已發送過' if already_sent else '❌ 未發送過'}\n"
            
            # 無論是否已發送過，都發送一次
            await self.send_earthquake_alert(latest_eq, mention_everyone=False)
            
            if not already_sent:
                # 將新地震加入已處理集合
                self.last_earthquakes.add(eq_id)
                self.sent_earthquakes.add(eq_id)
                self.earthquake_timestamps[eq_id] = current_time.timestamp()
                
                # 保存已發送的地震ID
                self._save_sent_earthquake_ids()
                self._save_earthquake_state()
                
                status_msg += "該地震現已加入已處理記錄。"
                
            await ctx.send(f"✅ 立即監測完成！\n{status_msg}")
            logger.info(f"管理員 {ctx.author.name} 執行了立即地震監測，發送了ID為 {eq_id} 的地震資訊")
            
        except Exception as e:
            await ctx.send(f"❌ 立即監測失敗: {str(e)}")
            logger.error(f"立即監測失敗: {e}", exc_info=True)

    @commands.command(name="測試地震API")
    @commands.has_permissions(administrator=True)
    async def test_earthquake_api(self, ctx):
        """測試地震API連接和數據解析"""
        await ctx.send("🔍 正在測試地震API連接...")
        
        try:
            # 獲取API URL
            api_url = self.cwb_api_url
            message = f"使用API端點: {api_url}\n"
            
            # 發送請求
            headers = {
                "Authorization": self.cwb_api_key,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            
            async with self.session.get(api_url, headers=headers) as response:
                message += f"HTTP狀態碼: {response.status}\n"
                
                if response.status != 200:
                    message += f"❌ API返回錯誤: {response.status}\n"
                    error_text = await response.text()
                    message += f"錯誤內容: {error_text[:500]}...\n"
                    await ctx.send(message)
                    return
                
                # 解析JSON回應
                try:
                    data = await response.json()
                    message += "✅ 成功解析JSON回應\n"
                    
                    # 檢查API回應結構
                    if data.get("success"):
                        message += "✅ API返回success=true\n"
                    else:
                        message += "❌ API返回success=false\n"
                        
                    if "records" in data:
                        message += "✅ 找到records字段\n"
                        message += f"records中的字段: {', '.join(data['records'].keys())}\n"
                        
                        records = data["records"]
                        
                        # 檢查地震數據字段 (同時檢查大小寫)
                        earthquake_field = None
                        if "earthquake" in records:
                            earthquake_field = "earthquake"
                            message += "✅ 找到 earthquake 字段 (小寫)\n"
                        elif "Earthquake" in records:
                            earthquake_field = "Earthquake"
                            message += "✅ 找到 Earthquake 字段 (大寫)\n"
                        
                        if earthquake_field:
                            earthquakes = records[earthquake_field]
                            count = len(earthquakes)
                            message += f"✅ 找到{count}個地震記錄\n"
                            
                            # 檢查最新的地震
                            if count > 0:
                                latest = earthquakes[0]
                                # 嘗試不同的ID字段名稱
                                eq_no = latest.get("earthquakeNo", latest.get("EarthquakeNo", "未知"))
                                message += f"最新地震ID: {eq_no}\n"
                                
                                # 嘗試不同的時間字段名稱
                                origin_time = latest.get('originTime', latest.get('OriginTime', '未知'))
                                message += f"發震時間: {origin_time}\n"
                                
                                # 嘗試不同的規模字段名稱
                                magnitude = latest.get('magnitudeValue', latest.get('MagnitudeValue', '未知'))
                                message += f"規模: {magnitude}\n"
                                
                                # 嘗試不同的深度字段名稱
                                depth_value = '未知'
                                depth_unit = ''
                                if 'depth' in latest:
                                    depth_value = latest['depth'].get('value', '未知')
                                    depth_unit = latest['depth'].get('unit', '')
                                elif 'Depth' in latest:
                                    depth_value = latest['Depth'].get('Value', '未知')
                                    depth_unit = latest['Depth'].get('Unit', '')
                                elif 'FocalDepth' in latest:
                                    depth_value = latest['FocalDepth']
                                    depth_unit = '公里'
                                message += f"深度: {depth_value} {depth_unit}\n"
                                
                                # 嘗試不同的報告內容字段名稱
                                report_content = latest.get("reportContent", latest.get("ReportContent", ""))
                                if report_content:
                                    message += f"報告內容: {report_content[:100]}...\n"
                                    
                                # 顯示完整結構供參考
                                message += f"完整數據字段: {', '.join(latest.keys())}\n"
                        else:
                            message += "❌ 未找到地震相關字段\n"
                            message += f"可用字段: {', '.join(records.keys())}\n"
                    else:
                        message += "❌ 未找到records字段\n"
                        
                except ValueError as e:
                    message += f"❌ JSON解析錯誤: {e}\n"
                
            # 使用我們修改後的函數獲取地震數據
            message += "\n--- 使用 fetch_earthquake_data 測試 ---\n"
            earthquakes = await self.fetch_earthquake_data()
            if earthquakes:
                message += f"✅ 成功獲取{len(earthquakes)}筆地震資料\n"
                
                # 過濾今日地震並顯示
                current_time = datetime.datetime.now()
                today = current_time.date()
                today_earthquakes = []
                
                # 處理各種可能的日期字段格式
                for eq in earthquakes:
                    try:
                        # 嘗試不同的時間字段
                        time_str = eq.get('originTime', eq.get('OriginTime', eq.get('time', '')))
                        if not time_str:
                            continue
                        
                        eq_time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                        if eq_time.date() == today:
                            today_earthquakes.append(eq)
                    except Exception as e:
                        message += f"解析地震時間出錯: {e}\n"
                        continue
                
                message += f"今日地震數: {len(today_earthquakes)}\n"
                
                # 顯示今日最新地震
                if today_earthquakes:
                    # 按時間排序
                    try:
                        today_earthquakes.sort(
                            key=lambda eq: datetime.datetime.strptime(
                                eq.get('originTime', eq.get('OriginTime', eq.get('time', '1970-01-01 00:00:00'))),
                                '%Y-%m-%d %H:%M:%S'
                            ),
                            reverse=True
                        )
                        
                        latest = today_earthquakes[0]
                        # 嘗試不同的ID字段
                        eq_id = latest.get('earthquakeNo', latest.get('EarthquakeNo', '未知ID'))
                        # 嘗試不同的時間字段
                        origin_time = latest.get('originTime', latest.get('OriginTime', '未知時間'))
                        message += f"今日最新地震: ID={eq_id}, 時間={origin_time}\n"
                    except Exception as e:
                        message += f"排序地震數據時出錯: {e}\n"
                
            else:
                message += f"❌ fetch_earthquake_data無法獲取地震資料\n"
                
            # 發送測試結果
            await ctx.send(message)
        
        except Exception as e:
            await ctx.send(f"❌ API測試失敗: {str(e)}")
            logger.error(f"API測試失敗: {e}", exc_info=True)

    def _save_earthquake_state(self) -> None:
        """保存地震狀態到配置文件"""
        self.config['LAST_EARTHQUAKES'] = list(self.last_earthquakes)
        self.config['EARTHQUAKE_TIMESTAMPS'] = self.earthquake_timestamps
        save_config('setting.json', self.config)
        logger.debug(f"已保存地震狀態，當前地震ID數量: {len(self.last_earthquakes)}")
        
        # 清理過期的最後發送時間記錄，保持字典大小不會無限增長
        self._cleanup_last_sent_times()
        
    def _cleanup_last_sent_times(self) -> None:
        """清理過期的最後發送時間記錄"""
        if not hasattr(self, 'last_sent_time') or not self.last_sent_time:
            return
            
        current_time = time.time()
        expired_ids = []
        
        # 找出過期的ID
        for eq_id, sent_time in self.last_sent_time.items():
            if current_time - sent_time > self.message_cooldown * 2:  # 使用兩倍冷卻時間作為過期時間
                expired_ids.append(eq_id)
                
        # 刪除過期的ID
        for eq_id in expired_ids:
            del self.last_sent_time[eq_id]
            
        if expired_ids:
            logger.debug(f"已清理 {len(expired_ids)} 個過期的發送時間記錄")

    def get_color_by_magnitude(self, magnitude: float) -> int:
        """根據地震規模獲取對應的顏色"""
        try:
            magnitude = float(magnitude)
            if magnitude < 3.0:
                return 0x00FF00  # 綠色 - 小型地震
            elif magnitude < 4.0:
                return 0xFFFF00  # 黃色 - 輕微地震
            elif magnitude < 5.0:
                return 0xFFA500  # 橙色 - 中型地震
            elif magnitude < 6.0:
                return 0xFF6347  # 番茄紅 - 中強地震
            elif magnitude < 7.0:
                return 0xFF0000  # 紅色 - 強烈地震
            else:
                return 0x8B0000  # 深紅色 - 極強地震
        except (ValueError, TypeError):
            return 0xFF0000  # 默認紅色

    @commands.command(name="檢查API資訊")
    @commands.has_permissions(administrator=True)
    async def check_api_details(self, ctx):
        """詳細檢查API連接和回應結構"""
        await ctx.send("🔍 正在詳細檢查API連接和回應結構...")
        
        try:
            # 獲取API URL和Key
            api_url = self.cwb_api_url
            api_key = self.cwb_api_key
            
            # 構建詳細信息字符串
            details = f"**API基本信息**\n"
            details += f"- URL: `{api_url}`\n"
            details += f"- API Key: `{api_key[:5]}...`\n\n"
            
            # 發送API請求
            headers = {
                "Authorization": api_key,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            
            # 首先發送一條消息，稍後更新
            status_msg = await ctx.send("發送API請求中...")
            
            async with self.session.get(api_url, headers=headers) as response:
                # 更新HTTP狀態碼
                details += f"**HTTP響應**\n"
                details += f"- 狀態碼: {response.status}\n"
                
                # 檢查內容類型
                content_type = response.headers.get('Content-Type', '未知')
                details += f"- 內容類型: {content_type}\n"
                
                # 更新狀態消息
                await status_msg.edit(content=f"{details}\n正在解析響應數據...")
                
                if response.status != 200:
                    error_text = await response.text()
                    details += f"- 錯誤響應: ```{error_text[:300]}...```\n"
                    await status_msg.edit(content=details)
                    return
                
                # 解析JSON響應
                try:
                    data = await response.json()
                    
                    # 更新狀態消息
                    await status_msg.edit(content=f"{details}\n解析JSON成功，正在分析數據結構...")
                    
                    # 檢查API響應結構
                    details += "\n**API響應結構**\n"
                    if "success" in data:
                        details += f"- Success: {data['success']}\n"
                    
                    if "records" in data:
                        records = data["records"]
                        details += f"- Records字段: 存在\n"
                        
                        # 列出records中的所有字段
                        record_fields = list(records.keys())
                        details += f"- Records包含字段: {', '.join(record_fields)}\n"
                        
                        # 檢查earthquake字段
                        if "earthquake" in records:
                            earthquakes = records["earthquake"]
                            details += f"- 地震記錄數: {len(earthquakes)}\n"
                            
                            # 獲取一個樣本地震數據的結構
                            if len(earthquakes) > 0:
                                sample_eq = earthquakes[0]
                                eq_fields = list(sample_eq.keys())
                                details += f"- 地震數據字段: {', '.join(eq_fields)}\n"
                                
                                # 顯示一個樣本地震的詳細信息
                                eq_no = sample_eq.get("earthquakeNo", "未知")
                                origin_time = sample_eq.get("originTime", "未知時間")
                                magnitude = sample_eq.get("magnitudeValue", "未知")
                                depth = f"{sample_eq.get('depth', {}).get('value', '未知')} {sample_eq.get('depth', {}).get('unit', '')}"
                                location = sample_eq.get("location", "未知位置")
                                
                                details += f"\n**樣本地震數據**\n"
                                details += f"- ID: {eq_no}\n"
                                details += f"- 時間: {origin_time}\n"
                                details += f"- 規模: {magnitude}\n"
                                details += f"- 深度: {depth}\n"
                                details += f"- 位置: {location}\n"
                        else:
                            details += f"- 無地震記錄\n"
                    else:
                        details += f"- Records字段: 不存在\n"
                    
                    # 檢測是否有今日的地震
                    if "records" in data and "earthquake" in data["records"]:
                        today = datetime.datetime.now().date()
                        today_earthquakes = []
                        
                        for eq in data["records"]["earthquake"]:
                            try:
                                time_str = eq.get('originTime', '')
                                if time_str:
                                    eq_time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                                    if eq_time.date() == today:
                                        today_earthquakes.append(eq)
                            except Exception as e:
                                continue
                        
                        details += f"\n**今日地震資訊**\n"
                        details += f"- 今日地震數量: {len(today_earthquakes)}\n"
                        
                        # 顯示今日所有地震的基本信息
                        if today_earthquakes:
                            # 按時間排序
                            today_earthquakes.sort(
                                key=lambda eq: datetime.datetime.strptime(eq.get('originTime', '1970-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S'),
                                reverse=True
                            )
                            
                            details += "- 今日地震列表:\n"
                            for idx, eq in enumerate(today_earthquakes[:5], 1):  # 最多顯示5個
                                eq_time = eq.get("originTime", "未知時間")
                                eq_mag = eq.get("magnitudeValue", "未知")
                                eq_loc = eq.get("location", "未知位置")
                                details += f"  {idx}. {eq_time} 規模{eq_mag} - {eq_loc}\n"
                            
                            if len(today_earthquakes) > 5:
                                details += f"  ... 以及其他 {len(today_earthquakes)-5} 個地震\n"
                        else:
                            details += "- 今日尚無地震記錄\n"
                
                except ValueError as e:
                    details += f"\n**解析錯誤**\n- JSON解析失敗: {str(e)}\n"
            
            # 發送完整的詳細信息
            await status_msg.edit(content=details)
            
        except Exception as e:
            await ctx.send(f"❌ API詳情檢查失敗: {str(e)}")
            logger.error(f"API詳情檢查失敗: {e}", exc_info=True)

    def parse_earthquake_time(self, time_str: str) -> Optional[datetime.datetime]:
        """解析地震時間字符串為datetime對象，支持多種格式
        
        Args:
            time_str: 時間字符串
            
        Returns:
            datetime對象，如果解析失敗則返回None
        """
        if not time_str:
            return None
            
        # 嘗試各種可能的時間格式
        formats = [
            "%Y-%m-%d %H:%M:%S",  # 2023-01-01 12:34:56
            "%Y/%m/%d %H:%M:%S",  # 2023/01/01 12:34:56
            "%Y-%m-%dT%H:%M:%S",  # 2023-01-01T12:34:56
            "%Y%m%d%H%M%S",       # 20230101123456
            "%Y-%m-%d %H:%M",     # 2023-01-01 12:34
            "%Y/%m/%d %H:%M",     # 2023/01/01 12:34
            "%Y-%m-%dT%H:%M",     # 2023-01-01T12:34
            "%Y-%m-%d",           # 2023-01-01 (僅日期)
            "%Y/%m/%d",           # 2023/01/01 (僅日期)
            "%Y%m%d"              # 20230101 (僅日期)
        ]
        
        for fmt in formats:
            try:
                return datetime.datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        
        # 如果標準格式都失敗，嘗試ISO格式解析
        try:
            return datetime.datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
            
        # 嘗試使用時間戳解析
        try:
            timestamp = float(time_str)
            return datetime.datetime.fromtimestamp(timestamp)
        except (ValueError, TypeError):
            pass
        
        # 記錄更多詳細信息以便診斷
        logger.warning(f"無法解析地震時間格式: '{time_str}' (類型: {type(time_str).__name__}, 長度: {len(str(time_str))})")
        return None
        
    def get_earthquake_time_field(self, earthquake: Dict[str, Any]) -> Optional[str]:
        """從地震數據中獲取時間字段
        
        Args:
            earthquake: 地震數據字典
            
        Returns:
            時間字符串，如果找不到則返回None
        """
        if not earthquake or not isinstance(earthquake, dict):
            logger.warning(f"無效的地震數據: {type(earthquake).__name__}")
            return None
            
        # 支持更多的時間字段名稱
        time_field_names = ['originTime', 'OriginTime', 'time', 'Time', 'earthquakeInfo', 'EarthquakeInfo', 'createTime']
        
        # 直接在頂層查找時間字段
        for field in time_field_names:
            if field in earthquake:
                # 檢查是否為嵌套結構
                if field in ['earthquakeInfo', 'EarthquakeInfo'] and isinstance(earthquake[field], dict):
                    # 嘗試從嵌套結構中獲取時間
                    info = earthquake[field]
                    for time_field in ['originTime', 'OriginTime', 'time', 'Time', 'createTime']:
                        if time_field in info:
                            return info[time_field]
                # 如果是直接的時間字段
                elif isinstance(earthquake[field], (str, int, float)):
                    return str(earthquake[field])
        
        # 嘗試檢查其他可能包含時間的嵌套結構
        for struct_field in ['earthquake', 'Earthquake', 'EarthquakeInfo', 'earthquakeInfo', 'origin', 'Origin']:
            if struct_field in earthquake and isinstance(earthquake[struct_field], dict):
                nested = earthquake[struct_field]
                for time_field in ['originTime', 'OriginTime', 'time', 'Time', 'createTime']:
                    if time_field in nested:
                        return nested[time_field]
        
        # 記錄更詳細的調試信息
        eq_id = earthquake.get('earthquakeNo', earthquake.get('EarthquakeNo', earthquake.get('identifier', 'unknown')))
        available_fields = list(earthquake.keys())
        logger.debug(f"無法找到時間字段，ID: {eq_id}, 可用字段: {available_fields}")
        
        # 檢查常見嵌套結構中的字段
        nested_fields = ['earthquakeInfo', 'EarthquakeInfo', 'earthquake', 'Earthquake', 'origin', 'Origin']
        for field in nested_fields:
            if field in earthquake and isinstance(earthquake[field], dict):
                logger.debug(f"{field}內容: {list(earthquake[field].keys())}")
        
        return None

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Earthquake(bot)) 