import discord
import asyncio
import aiohttp
import json
import datetime
import os
import time
import random
import hashlib
from typing import Dict, List, Optional, Any, Tuple, Set
from discord.ext import commands, tasks
from core.classes import Cog_Extension
from core.config import load_config, save_config
from core.logging import logger, measure_time
from core.cache import cache
from dotenv import load_dotenv
import dateutil.parser

# 引入指令模組
from cmds.earthquake_commands import EarthquakeCommands

# 載入環境變數
load_dotenv()

class Earthquake(Cog_Extension):
    """地震監測與通知模組"""
    
    category = "資訊"  # 設置模組類別
    max_stored_earthquakes = 500  # 最多儲存的地震ID數量
    earthquake_id_ttl_days = 30  # 地震ID保留天數
    max_earthquake_age_hours = 24  # 最大地震年齡 (小時)
    
    def __init__(self, bot):
        self.bot = bot
        
        # 載入配置文件
        self.config = load_config('setting.json')
        
        # 初始化API請求會話
        self.session = aiohttp.ClientSession()
        
        # 發送鎖，防止重複發送
        self.sending_lock = False
        
        # 地震API設定
        self.cwb_api_url = self._safe_get_env("EARTHQUAKE_API_URL", "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001")
        logger.debug(f"使用地震API URL: {self.cwb_api_url}")
        
        # 嘗試從環境變數獲取API金鑰
        self.cwb_api_key = self._safe_get_env("EARTHQUAKE_API_KEY", "")
        if not self.cwb_api_key:
            # 從磁盤讀取API金鑰
            api_key_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'cwb_api_key.txt')
            if os.path.exists(api_key_path):
                try:
                    with open(api_key_path, 'r') as key_file:
                        self.cwb_api_key = key_file.read().strip()
                        logger.debug("從檔案讀取氣象局 API 金鑰")
                except Exception as e:
                    logger.error(f"讀取氣象局 API 金鑰失敗: {e}")
            logger.debug(f"API金鑰狀態: {'已設置' if self.cwb_api_key else '未設置'}")
                    
        # 用於API條件請求
        self.last_etag = None
        self.last_modified = None
        self.last_data_hash = None
        
        # 輪詢控制參數
        self.min_polling_interval = 6       # 最小輪詢間隔 (秒)
        self.max_polling_interval = 60      # 最大輪詢間隔 (秒)
        self.polling_interval = self.min_polling_interval  # 當前輪詢間隔
        self.backoff_factor = 1.5           # 退避係數
        self.max_consecutive_304 = 5        # 觸發增加輪詢間隔的連續304數量
        self.consecutive_304 = 0            # 連續304響應計數
        
        # 多層緩存設定
        self.memory_cache = {}              # 記憶體緩存
        # 從環境變數讀取緩存TTL，若不存在則使用預設值30秒
        self.cache_ttl = self._safe_get_env("CACHE_TTL", "30", int)
        logger.debug(f"緩存TTL設置為: {self.cache_ttl}秒")
        
        # 性能指標
        self.start_time = time.time()
        self.api_calls_total = 0
        self.api_calls_skipped = 0
        
        # 從環境變數獲取頻道ID
        self.channel_id = self._safe_get_env("EARTHQUAKE_CHANNEL", "0", int)
        logger.info(f"地震通知頻道ID設置為: {self.channel_id}")
        
        # 從環境變數讀取是否自動廣播今日地震
        broadcast_str = self._safe_get_env("EARTHQUAKE_BROADCAST_TODAY", "True")
        self.broadcast_today_earthquakes = broadcast_str.lower() in ('true', 'yes', '1', 't')
        logger.info(f"今日地震自動廣播: {'啟用' if self.broadcast_today_earthquakes else '停用'}")
        
        # 從環境變數讀取最大地震年齡（小時）
        self.max_earthquake_age_hours = self._safe_get_env("EARTHQUAKE_MAX_AGE_HOURS", "24", int)
        logger.info(f"最大地震年齡設置為: {self.max_earthquake_age_hours}小時")
        
        # 其他已發送地震的記錄
        self.last_sent_time = {}            # 發送時間字典 {channel_id: {eq_id: timestamp}}
        self.last_earthquakes = set()       # 已處理的地震ID集合
        self.earthquake_timestamps = {}     # 地震時間戳記錄
        self.sent_earthquakes = set()       # 已發送的地震ID集合
        self.is_task_running = False        # 任務執行狀態
        
        # 加載之前發送的地震ID
        self._load_sent_earthquake_ids()
        
        # 更新任務已啟動狀態
        self.task_started = False
        self.consecutive_errors = 0
        self.last_api_error_time = None
        
        # 建立資料目錄
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        if not os.path.exists(self.data_dir):
            try:
                os.makedirs(self.data_dir)
                logger.debug(f"建立資料目錄: {self.data_dir}")
            except Exception as e:
                logger.error(f"建立資料目錄失敗: {e}")
                
        # 發送監測任務標記和日志清理任務
        self.processing_events = set()  # 正在處理的事件ID
        
        # 設置消息冷卻時間 (5分鐘 = 300秒)
        self.message_cooldown = self._safe_get_env("EARTHQUAKE_MESSAGE_COOLDOWN", "300", int)
        
        # 設置USGS API URL
        self.usgs_api_url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
        
        # 確保先創建這些屬性
        self.last_poll_time = datetime.datetime.now()
        self.polling_active = True
        
        # 初始化指令模組
        self.setup_commands()
        
        # 創建一個異步任務，在所有模組加載完成後設置引用
        self.bot.loop.create_task(self._setup_commands_later())
        
        logger.info("地震監測模組已初始化")
    
    def setup_commands(self):
        """初始化並設置指令模組"""
        try:
            # 確保初始化時創建這些屬性，以便命令能正常工作
            # 創建輪詢時間記錄
            self.last_poll_time = datetime.datetime.now()
            
            # 標記輪詢狀態為活動中
            self.polling_active = True
            
            # 初始化統計計數器
            if not hasattr(self, 'total_api_calls'):
                self.total_api_calls = 0
            if not hasattr(self, 'not_modified_responses'):
                self.not_modified_responses = 0
            if not hasattr(self, 'cache_hits'):
                self.cache_hits = 0
            if not hasattr(self, 'consecutive_304_count'):
                self.consecutive_304_count = 0
            
            # 獲取已經由discord.py加載的EarthquakeCommands實例
            # 這個實例是由earthquake_commands.py的setup函數創建並添加到bot中的
            commands_cog = self.bot.get_cog('EarthquakeCommands')
            
            if commands_cog:
                # 如果找到了cog實例，設置地震模組引用
                commands_cog.set_earthquake_module(self)
                logger.info("已連結地震指令模組到地震監測模組")
            else:
                # 如果找不到cog實例，可能是指令模組尚未加載
                logger.warning("找不到地震指令模組，請確保earthquake_commands.py已被正確加載")
                
        except Exception as e:
            logger.error(f"設置地震指令模組時出錯: {e}", exc_info=True)
        
        logger.info("地震指令模組設置完成")
    
    # 輪詢間隔調整邏輯
    def _adjust_polling_interval(self, success=True, no_change=False):
        """
        智能調整輪詢間隔:
        - 成功且無變化 (304 回應): 逐步增加間隔，減少API負載
        - 成功且有變化 (新數據): 保持快速輪詢
        - 失敗: 指數退避，增加間隔
        """
        if not success:
            # 失敗的情況，使用指數退避
            new_interval = min(self.polling_interval * self.backoff_factor, self.max_polling_interval)
            logger.debug(f"API請求失敗，增加輪詢間隔: {self.polling_interval} → {new_interval}秒")
            self.polling_interval = new_interval
        elif no_change:
            # 成功但數據無變化 (304)，緩慢增加間隔
            if self.polling_interval < self.max_polling_interval:
                # 線性增加，更溫和
                new_interval = min(self.polling_interval + 2, self.max_polling_interval)
                logger.debug(f"數據無變化，緩慢增加輪詢間隔: {self.polling_interval} → {new_interval}秒")
                self.polling_interval = new_interval
        else:
            # 成功且有數據變化，降低間隔但不低於最小值
            if self.polling_interval > self.min_polling_interval:
                new_interval = max(self.polling_interval / self.backoff_factor, self.min_polling_interval)
                logger.debug(f"檢測到數據變化，減少輪詢間隔: {self.polling_interval} → {new_interval}秒")
                self.polling_interval = new_interval
                
    # 計算數據哈希值，用於檢測變化
    def _calculate_data_hash(self, earthquakes):
        """計算數據的哈希值，用於比較數據是否發生變化"""
        if not earthquakes:
            return "empty"
            
        try:
            # 只考慮最新的幾條數據用於哈希計算
            latest_quakes = earthquakes[:5]
            # 將數據轉換為JSON字符串並計算哈希
            data_str = json.dumps(latest_quakes, sort_keys=True)
            return hashlib.md5(data_str.encode()).hexdigest()
        except Exception as e:
            logger.error(f"計算數據哈希值出錯: {e}")
            return str(time.time())  # 出錯時返回時間戳作為唯一值
            
    def _safe_get_env(self, key, default=None, convert_type=None):
        """安全地從環境變數獲取值，處理註釋並轉換類型
        
        Args:
            key: 環境變數名
            default: 默認值
            convert_type: 轉換函數，如int, float等
            
        Returns:
            處理後的環境變數值
        """
        value = os.environ.get(key, default)
        if value is None:
            return default
            
        # 處理可能包含註釋的環境變數
        if isinstance(value, str) and '#' in value:
            value = value.split('#')[0].strip()
            
        # 執行類型轉換
        if convert_type and value is not None:
            try:
                return convert_type(value)
            except (ValueError, TypeError) as e:
                logger.error(f"轉換環境變數 {key} 類型時出錯: {e}, 使用默認值 {default}")
                return default
                
        return value
        
    def get_earthquake_time_field(self, earthquake):
        """從地震對象獲取時間字段
        
        嘗試從不同可能的字段名稱中獲取地震發生時間
        
        Args:
            earthquake: 地震數據對象
            
        Returns:
            時間字符串或None
        """
        if not earthquake:
            return None
            
        # 處理地震對象可能是字符串的情況
        if isinstance(earthquake, str):
            return earthquake
            
        # 嘗試不同的可能字段名稱
        time_field_names = [
            'originTime', 'OriginTime',  # 中央氣象局API常用
            'time', 'Time',              # 常見的時間字段
            'earthquakeTime', 'EarthquakeTime',
            'origin_time', 'eventTime'   # 其他可能的命名
        ]
        
        # 對於CWB API，時間可能在嵌套結構中
        for field in time_field_names:
            if field in earthquake:
                return earthquake[field]
        
        # 嵌套結構的情況
        if 'EarthquakeInfo' in earthquake and isinstance(earthquake['EarthquakeInfo'], dict):
            for field in time_field_names:
                if field in earthquake['EarthquakeInfo']:
                    return earthquake['EarthquakeInfo'][field]
        
        if 'earthquakeInfo' in earthquake and isinstance(earthquake['earthquakeInfo'], dict):
            for field in time_field_names:
                if field in earthquake['earthquakeInfo']:
                    return earthquake['earthquakeInfo'][field]
                    
        # 未找到任何時間字段
        eq_id = earthquake.get('earthquakeNo', earthquake.get('EarthquakeNo', earthquake.get('identifier', 'unknown')))
        logger.warning(f"無法從地震數據中找到時間字段 (ID: {eq_id})")
        return None
        
    def parse_earthquake_time(self, time_str):
        """解析地震時間字符串為datetime對象
        
        支持多種時間格式，包括中央氣象局和其他來源的格式
        
        Args:
            time_str: 時間字符串
            
        Returns:
            datetime對象或None
        """
        if not time_str:
            return None
            
        # 標準化處理
        time_str = str(time_str).strip()
        
        # 嘗試多種時間格式解析
        formats = [
            '%Y-%m-%d %H:%M:%S',  # 標準格式：2023-01-01 12:34:56
            '%Y/%m/%d %H:%M:%S',  # 斜線分隔：2023/01/01 12:34:56
            '%Y-%m-%dT%H:%M:%S',  # ISO格式(無時區)：2023-01-01T12:34:56
            '%Y-%m-%dT%H:%M:%S.%f',  # ISO格式(帶毫秒)：2023-01-01T12:34:56.123
            '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO格式(UTC)：2023-01-01T12:34:56.123Z
            '%Y-%m-%dT%H:%M:%SZ',  # ISO格式(UTC無毫秒)：2023-01-01T12:34:56Z
            '%Y%m%d%H%M%S'  # 緊湊格式：20230101123456
        ]
        
        # 特殊處理時區信息
        if '+' in time_str and 'T' in time_str:
            # ISO格式帶時區：2023-01-01T12:34:56+08:00
            try:
                # 嘗試直接解析帶時區的時間
                return dateutil.parser.isoparse(time_str)
            except (ImportError, Exception) as e:
                # 如果dateutil不可用，手動處理
                logger.warning(f"使用dateutil解析時間失敗，嘗試手動處理: {e}")
                time_parts = time_str.split('+')[0]
                for fmt in formats:
                    try:
                        return datetime.datetime.strptime(time_parts, fmt)
                    except ValueError:
                        continue
        
        # 嘗試所有格式
        for fmt in formats:
            try:
                return datetime.datetime.strptime(time_str, fmt)
            except ValueError:
                continue
                
        # 如果所有格式都失敗，記錄錯誤並返回None
        logger.error(f"無法解析時間字符串: {time_str}")
        return None

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
        """當模組被Discord.py加載後調用"""
        logger.info("地震監測模組正在加載...")
        
        # 確保初始化狀態屬性
        self.last_poll_time = datetime.datetime.now()
        self.polling_active = True
        
        # 統計計數器
        self.total_api_calls = 0
        self.not_modified_responses = 0
        self.cache_hits = 0
        self.consecutive_304_count = 0
        
        # 啟動監測任務
        self._start_earthquake_monitoring()
        
        # 設置指令模組的引用
        # 這將在所有Cog都加載完成後執行
        asyncio.create_task(self._setup_command_reference_later())
        
        logger.info("地震監測模組加載完成")

    async def _setup_command_reference_later(self):
        """在所有Cog加載完成後設置指令模組的引用"""
        # 等待所有模組加載完成
        await asyncio.sleep(3)
        
        # 再次嘗試設置地震模組引用
        try:
            commands_cog = self.bot.get_cog('EarthquakeCommands')
            if commands_cog:
                # 設置地震模組引用
                commands_cog.set_earthquake_module(self)
                logger.info("成功延遲設置地震指令模組引用")
            else:
                logger.warning("延遲設置地震指令模組引用失敗，找不到EarthquakeCommands模組")
        except Exception as e:
            logger.error(f"延遲設置地震指令模組引用時出錯: {e}", exc_info=True)
    
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
        
    # 將固定的輪詢間隔2分鐘改為自適應輪詢
    @tasks.loop(seconds=6)  # 初始間隔6秒
    async def earthquake_monitoring(self):
        """高效率地震監測：自適應輪詢間隔、條件請求和多層緩存"""
        try:
            # 更新最後輪詢時間
            self.last_poll_time = datetime.datetime.now()
            
            # 記錄任務執行時間，用於調試重複執行問題
            exec_id = f"eq_mon_{int(time.time())}"
            logger.debug(f"開始執行地震監測任務 (執行ID: {exec_id}, 當前輪詢間隔: {self.polling_interval}秒)")
            
            # 動態調整下次執行的延遲時間
            self.earthquake_monitoring.change_interval(seconds=self.polling_interval)
            
            # 當前時間
            current_time = datetime.datetime.now()
            today = current_time.date()
            
            # 檢查是否需要調用API
            should_call_api = True
            cache_key = f"earthquake_data_{today.strftime('%Y%m%d')}"
            
            # 1. 檢查記憶體緩存
            if cache_key in self.memory_cache:
                cached_data, cache_timestamp = self.memory_cache[cache_key]
                cache_age = time.time() - cache_timestamp
                
                # 如果緩存未過期，可以使用
                if cache_age < self.cache_ttl:
                    logger.debug(f"使用記憶體緩存數據，緩存年齡: {int(cache_age)}秒")
                    earthquakes = cached_data
                    should_call_api = False
                    self.api_calls_skipped += 1
            
            # 2. 如果需要調用API
            if should_call_api:
                self.api_calls_total += 1
                
                # 準備HTTP頭部進行條件請求
                headers = {
                    "Authorization": self.cwb_api_key,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                }
                
                # 添加條件請求頭部
                if self.last_etag:
                    headers["If-None-Match"] = self.last_etag
                if self.last_modified:
                    headers["If-Modified-Since"] = self.last_modified
                
                logger.debug(f"發送條件請求，ETag: {self.last_etag and self.last_etag[:10]}..., Modified: {self.last_modified}")
                
                url = self.cwb_api_url
                async with self.session.get(url, headers=headers) as response:
                    # 處理304 Not Modified
                    if response.status == 304:
                        self.consecutive_304 += 1
                        self.api_calls_skipped += 1
                        logger.debug(f"API返回304 Not Modified，使用上次的數據 (連續304: {self.consecutive_304})")
                        
                        # 從緩存取數據
                        earthquakes = self.memory_cache.get(cache_key, ([], 0))[0]
                        
                        # 智能調整輪詢間隔：連續多次304後增加間隔
                        if self.consecutive_304 >= self.max_consecutive_304:
                            self._adjust_polling_interval(success=True, no_change=True)
                        
                    # 處理200 OK
                    elif response.status == 200:
                        self.consecutive_304 = 0  # 重置304計數器
                        
                        # 保存ETag和Last-Modified
                        self.last_etag = response.headers.get("ETag")
                        self.last_modified = response.headers.get("Last-Modified")
                        
                        # 解析回應數據
                        try:
                            data = await response.json()
                            
                            if not data.get("success"):
                                logger.error(f"API 回應錯誤: {data}")
                                self._adjust_polling_interval(success=False)
                                return None
                            
                            if "records" not in data:
                                logger.error(f"API 回應中沒有 records: {data}")
                                self._adjust_polling_interval(success=False)
                                return None
                            
                            # 處理API結構
                            records = data["records"]
                            
                            # 檢查小寫或大寫字段
                            if "earthquake" in records:
                                earthquakes = records["earthquake"]
                                logger.debug(f"成功取得 {len(earthquakes)} 筆地震資料 (小寫字段)")
                            elif "Earthquake" in records:
                                earthquakes = records["Earthquake"]
                                logger.debug(f"成功取得 {len(earthquakes)} 筆地震資料 (大寫字段)")
                            else:
                                logger.error(f"API 回應中沒有地震資料: {list(records.keys())}")
                                self._adjust_polling_interval(success=False)
                                return None
                                
                            # 計算數據哈希值，用於檢測變化
                            new_data_hash = self._calculate_data_hash(earthquakes)
                            if new_data_hash == self.last_data_hash:
                                logger.debug("數據內容未變化，但收到了200而非304")
                            else:
                                logger.debug("檢測到新的地震數據")
                                self.last_data_hash = new_data_hash
                                
                            # 更新記憶體緩存
                            self.memory_cache[cache_key] = (earthquakes, time.time())
                            
                            # 成功取得數據，調整輪詢間隔
                            self._adjust_polling_interval(success=True)
                            
                        except ValueError as e:
                            logger.error(f"無法解析 JSON 回應: {e}")
                            self._adjust_polling_interval(success=False)
                            return None
                    
                    # 處理錯誤
                    else:
                        error_text = await response.text()
                        logger.error(f"無法取得地震資料: 狀態碼 {response.status}, 錯誤: {error_text[:200]}")
                        self._adjust_polling_interval(success=False)
                        return None
            
            # 處理地震數據
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
                            
                            # 發送地震警報 - 發現新地震時立即降低輪詢間隔
                            await self.send_earthquake_alert(latest_eq, mention_everyone=mention_everyone)
                            self.polling_interval = self.min_polling_interval
                            
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
                self.consecutive_errors = getattr(self, 'consecutive_errors', 0) + 1
                self.last_api_error_time = current_time
                logger.warning(f"無法獲取地震數據 (連續錯誤次數: {self.consecutive_errors})")
                self._adjust_polling_interval(success=False)
            
            # 計算並記錄性能指標
            api_efficiency = (self.api_calls_skipped / max(1, self.api_calls_total)) * 100
            runtime = time.time() - self.start_time
            if runtime > 60 and self.api_calls_total > 10:  # 只在有足夠樣本時記錄
                hours = runtime / 3600
                calls_per_hour = self.api_calls_total / hours
                logger.info(f"性能指標: API效率 {api_efficiency:.1f}%, 每小時調用 {calls_per_hour:.1f}次, 輪詢間隔 {self.polling_interval}秒")
                
            logger.debug(f"地震監測任務完成 (執行ID: {exec_id})")
                
        except aiohttp.ClientError as e:
            # 網絡錯誤處理
            self.consecutive_errors = getattr(self, 'consecutive_errors', 0) + 1
            self.last_api_error_time = current_time
            logger.error(f"API請求網絡錯誤: {e} (連續錯誤次數: {self.consecutive_errors})")
            self._adjust_polling_interval(success=False)
        except Exception as e:
            # 其他錯誤處理
            logger.error(f"地震監測過程中發生錯誤: {e}", exc_info=True)
            self._adjust_polling_interval(success=False)

    @earthquake_monitoring.before_loop
    async def before_earthquake_monitoring(self):
        """等待機器人準備好後再開始監測"""
        await self.bot.wait_until_ready()
        logger.info("地震監測開始運行，頻率: 每6秒")
        
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

    def _start_earthquake_monitoring(self):
        """啟動地震監測任務"""
        # 初始化會話
        if not self.session:
            self.session = aiohttp.ClientSession()
            logger.debug("已創建 aiohttp.ClientSession 用於 API 請求")
        
        # 啟動地震監測任務
        if not self.task_started:
            # 這邊使用 start() 而不是 start() 是因為要確保沒有任何例外發生
            try:
                self.earthquake_monitoring.start()
                self.task_started = True
                logger.info("地震監測任務已啟動 (間隔: 每6秒)")
            except RuntimeError as e:
                if "Task is already launched" in str(e):
                    logger.warning("地震監測任務已經在運行中，跳過重複啟動")
                    self.task_started = True
                else:
                    logger.error(f"啟動地震監測任務失敗: {e}")
        else:
            logger.debug("地震監測任務已經被標記為啟動，跳過")
            
        # 啟動日誌清理任務
        try:
            self.cleanup_logs.start()
            logger.info("日誌清理任務已啟動 (間隔: 每3天)")
        except RuntimeError as e:
            if "Task is already launched" in str(e):
                logger.warning("日誌清理任務已經在運行中，跳過重複啟動")
            else:
                logger.error(f"啟動日誌清理任務失敗: {e}")
            
        # 記錄初始化完成
        logger.info(f"地震監測任務初始化完成，API KEY: {'已設置' if self.cwb_api_key else '未設置'}")
        
        # 如果 API KEY 未設置，記錄警告
        if not self.cwb_api_key:
            logger.warning("沒有設置中央氣象局 API KEY，可能會導致請求限制")
        
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

    async def _setup_commands_later(self):
        """延遲設置指令模組引用"""
        try:
            # 等待bot準備好
            await self.bot.wait_until_ready()
            # 再等待額外的時間，確保所有cog都已加載
            await asyncio.sleep(3)
            
            commands_cog = self.bot.get_cog('EarthquakeCommands')
            if commands_cog:
                commands_cog.set_earthquake_module(self)
                logger.info("成功延遲設置地震指令模組引用")
            else:
                logger.error("延遲設置地震指令模組引用失敗，找不到EarthquakeCommands模組")
        except Exception as e:
            logger.error(f"延遲設置地震指令模組引用時出錯: {e}", exc_info=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Earthquake(bot)) 