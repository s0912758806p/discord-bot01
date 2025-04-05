import discord
import asyncio
import datetime
import time
import os
from typing import Dict, Any, Tuple, Optional, Union
from discord.ext import commands
from core.logging import logger
from core.config import save_config


class EarthquakeCommands(commands.Cog):
    """地震相關指令模組"""
    
    def __init__(self, bot, earthquake_module=None):
        """初始化地震指令模組
        
        Args:
            bot: Discord Bot 實例
            earthquake_module: 地震監測模組實例，如果沒提供則需稍後設置
        """
        self.bot = bot
        self.earthquake = earthquake_module
        # 紀錄最近發送的訊息，用於防止重複回覆 {channel_id: {message_content_hash: timestamp}}
        self.recent_messages = {}
        # 訊息防重複發送冷卻時間（秒）
        self.message_cooldown = 5
        # 內部處理事件集合，在地震模組不可用時使用
        self._internal_processing_events = set()
        # 初始化基本屬性，即使地震模組未準備好時也可使用
        self._initalize_default_properties()
        
    def _initalize_default_properties(self):
        """初始化默認屬性，以便在地震模組不可用時也能使用部分功能"""
        # 輪詢狀態相關
        if not hasattr(self, '_internal_last_poll_time'):
            self._internal_last_poll_time = datetime.datetime.now()
        if not hasattr(self, '_internal_polling_active'):
            self._internal_polling_active = False
        # 統計數據相關
        if not hasattr(self, '_internal_api_calls'):
            self._internal_api_calls = 0
        if not hasattr(self, '_internal_skipped_calls'):
            self._internal_skipped_calls = 0
        if not hasattr(self, '_internal_not_modified'):
            self._internal_not_modified = 0
        if not hasattr(self, '_internal_cache_hits'):
            self._internal_cache_hits = 0
        
    def set_earthquake_module(self, earthquake_module):
        """設置地震監測模組
        
        Args:
            earthquake_module: 地震監測模組實例
        """
        # 添加Docker環境診斷信息
        try:
            import platform
            logger.info(f"==== 設置地震監測模組引用 (Docker環境) ====")
            logger.info(f"環境: {platform.node()} | Python: {platform.python_version()}")
            logger.info(f"引用類型: {type(earthquake_module).__name__}")
        except ImportError:
            pass
            
        logger.info(f"正在嘗試設置地震監測模組引用，模組類型：{type(earthquake_module)}")
        
        # 保存舊引用，以便比較
        old_earthquake = self.earthquake
        
        # 更新模組引用
        self.earthquake = earthquake_module
        
        # 如果地震模組不為None，同步一些基本屬性
        if earthquake_module is not None:
            # 更新輪詢狀態
            self._internal_polling_active = getattr(earthquake_module, 'polling_active', False)
            # 記錄最後輪詢時間
            self._internal_last_poll_time = getattr(earthquake_module, 'last_poll_time', datetime.datetime.now())
            # 同步統計數據
            self._internal_api_calls = getattr(earthquake_module, 'total_api_calls', 0)
            self._internal_skipped_calls = getattr(earthquake_module, 'api_calls_skipped', 0)
            self._internal_not_modified = getattr(earthquake_module, 'not_modified_responses', 0)
            self._internal_cache_hits = getattr(earthquake_module, 'cache_hits', 0)
            
            # 檢查processing_events屬性
            if hasattr(earthquake_module, 'processing_events'):
                has_processing = True
                events_count = len(earthquake_module.processing_events)
            else:
                has_processing = False
                events_count = 0
                
            # 輸出詳細日誌，協助調試
            logger.info(f"地震監測模組設置完成！舊引用：{old_earthquake}，新引用：{earthquake_module}")
            logger.info(f"模組屬性檢查:")
            logger.info(f"- 輪詢狀態：{self._internal_polling_active}")
            logger.info(f"- 最後輪詢時間：{self._internal_last_poll_time}")
            logger.info(f"- 處理事件集合：{'有效' if has_processing else '無效'} (包含{events_count}個事件)")
            logger.info(f"- API調用次數：{self._internal_api_calls}")
            logger.info(f"==== 地震監測模組引用設置完成 ====")
        else:
            logger.warning("嘗試設置的地震監測模組為None，可能會導致指令無法正常運作")
        
        return self
        
    def _check_earthquake_module(self, ctx):
        """檢查地震模組是否已設置
        
        Args:
            ctx: 指令上下文
            
        Returns:
            bool: 地震模組是否可用
        """
        if self.earthquake is None:
            asyncio.create_task(ctx.send("⚠️ 地震監測模組尚未就緒，請稍後再試"))
            logger.warning(f"使用者 {ctx.author.name} 嘗試執行指令，但地震模組尚未就緒")
            
            # 在Docker環境中增強重試機制
            logger.info(f"在Docker環境中嘗試主動獲取地震模組引用...")
            
            # 列出所有已加載的cogs，用於診斷
            loaded_cogs = list(self.bot.cogs.keys())
            logger.info(f"已加載的cogs: {', '.join(loaded_cogs)}")
            
            # 首先直接嘗試獲取Earthquake模組
            earthquake_cog = self.bot.get_cog('Earthquake')
            if earthquake_cog:
                logger.info(f"找到地震模組: {earthquake_cog}")
                self.set_earthquake_module(earthquake_cog)
                # 如果成功設置，再次檢查
                if self.earthquake is not None:
                    logger.info("✅ 成功自動獲取地震模組引用")
                    return True
            
            # 如果直接獲取失敗，嘗試從所有cogs中找出可能的地震模組
            for cog_name, cog in self.bot.cogs.items():
                # 檢查這個cog是否有地震模組的特性
                if hasattr(cog, 'processing_events') and hasattr(cog, 'polling_active'):
                    logger.info(f"找到可能的地震模組: {cog_name}")
                    self.set_earthquake_module(cog)
                    if self.earthquake is not None:
                        logger.info(f"✅ 成功從{cog_name}獲取地震模組引用")
                        return True
            
            # 如果所有嘗試都失敗
            logger.error("🔄 所有自動獲取地震模組引用的嘗試都失敗")
            return False
        return True
        
    def _get_processing_events(self):
        """獲取處理事件集合
        
        如果地震模組可用，則使用地震模組的集合，否則使用內部集合
        
        Returns:
            set: 正在處理的事件集合
        """
        if self.earthquake is not None:
            return self.earthquake.processing_events
        return self._internal_processing_events
    
    def _message_recently_sent(self, channel_id: int, content: str) -> bool:
        """檢查是否最近已經發送過相同的訊息到同一個頻道
        
        Args:
            channel_id: 頻道ID
            content: 訊息內容
            
        Returns:
            bool: 如果最近已發送過相同訊息，則返回True，否則返回False
        """
        current_time = time.time()
        
        # 初始化頻道的訊息記錄（如果不存在）
        if channel_id not in self.recent_messages:
            self.recent_messages[channel_id] = {}
            
        # 計算訊息內容的雜湊值
        msg_hash = hash(content)
        
        # 檢查是否最近發送過同樣內容的訊息
        if msg_hash in self.recent_messages[channel_id]:
            last_sent_time = self.recent_messages[channel_id][msg_hash]
            if current_time - last_sent_time < self.message_cooldown:
                logger.debug(f"防止重複發送訊息到頻道 {channel_id}：{content[:30]}...")
                return True
                
        # 更新最近發送的訊息記錄
        self.recent_messages[channel_id][msg_hash] = current_time
        
        # 清理過期的訊息記錄
        self._cleanup_message_records(channel_id)
        
        return False
    
    def _cleanup_message_records(self, channel_id: int) -> None:
        """清理指定頻道的過期訊息記錄"""
        if channel_id not in self.recent_messages:
            return
            
        current_time = time.time()
        expired_hashes = []
        
        # 找出過期的訊息雜湊值
        for msg_hash, sent_time in self.recent_messages[channel_id].items():
            if current_time - sent_time > self.message_cooldown * 3:  # 使用三倍冷卻時間作為過期時間
                expired_hashes.append(msg_hash)
                
        # 刪除過期的記錄
        for msg_hash in expired_hashes:
            del self.recent_messages[channel_id][msg_hash]
    
    async def _safe_send(self, ctx, content: str) -> discord.Message:
        """安全發送訊息，防止重複發送相同內容
        
        Args:
            ctx: 指令上下文
            content: 訊息內容
            
        Returns:
            Message: 發送的訊息物件，如果沒有發送則返回None
        """
        channel_id = ctx.channel.id
        
        # 添加請求時間戳確保不同請求有不同的訊息內容
        request_id = f"req_{int(time.time() * 1000) % 10000:04d}"
        
        # 檢查是否最近已發送過相同訊息
        if self._message_recently_sent(channel_id, content):
            logger.debug(f"跳過重複訊息 [{request_id}]: {content[:30]}...")
            return None
            
        try:
            # 在實際顯示的訊息中隱藏請求ID (實際傳送時不包含ID)
            return await ctx.send(content)
        except Exception as e:
            logger.error(f"發送訊息時出錯 [{request_id}]: {e}")
            return None
    
    async def _safe_edit(self, message: discord.Message, content: str) -> Tuple[bool, discord.Message]:
        """安全編輯訊息，防止重複設置相同內容
        
        Args:
            message: 要編輯的訊息物件
            content: 新的訊息內容
            
        Returns:
            Tuple[bool, Message]: (是否編輯成功, 編輯後的訊息物件)
        """
        if not message:
            return False, None
            
        channel_id = message.channel.id
        
        # 如果內容完全相同，跳過編輯
        if message.content == content:
            return False, message
            
        # 檢查是否最近已發送過相同訊息
        if self._message_recently_sent(channel_id, content):
            logger.debug(f"跳過重複編輯: {content[:30]}...")
            return False, message
            
        try:
            return True, await message.edit(content=content)
        except Exception as e:
            logger.error(f"編輯訊息時出錯: {e}")
            return False, message
        
    # === 指令部分 ===
    
    @commands.command(name="手動地震測試全體")
    @commands.has_permissions(administrator=True)
    async def manual_earthquake_test_everyone(self, ctx):
        """測試地震廣播功能（包含全體通知）"""
        # 檢查地震模組是否可用
        if not self._check_earthquake_module(ctx):
            return
            
        # 取得處理事件集合
        processing_events = self._get_processing_events()
            
        # 避免重複執行
        cmd_key = f"manual_test_{ctx.author.id}"
        if cmd_key in processing_events:
            await self._safe_send(ctx, "⚠️ 指令處理中，請稍候再試")
            return
            
        processing_events.add(cmd_key)
        try:
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
            
            await self.earthquake.send_earthquake_alert(test_earthquake, mention_everyone=True)
            # 不要將測試數據添加到實際地震ID列表中
            await self._safe_send(ctx, f"地震警報測試完成! 測試ID: {test_id}")
            logger.info(f"管理員 {ctx.author.name} 執行了全體通知地震警報測試，ID: {test_id}")
        except Exception as e:
            await self._safe_send(ctx, f"❌ 地震警報測試失敗: {str(e)}")
            logger.error(f"地震警報測試失敗: {e}", exc_info=True)
        finally:
            # 確保完成後移除處理標記
            processing_events.discard(cmd_key)

    @commands.command(name="今日地震")
    async def today_earthquake(self, ctx):
        """顯示今日最新地震資訊"""
        # 檢查地震模組是否可用
        if not self._check_earthquake_module(ctx):
            return
            
        # 取得處理事件集合
        processing_events = self._get_processing_events()
        
        # 避免重複執行
        cmd_key = f"today_eq_{ctx.author.id}"
        if cmd_key in processing_events:
            await self._safe_send(ctx, "⚠️ 指令處理中，請稍候再試")
            return
            
        processing_events.add(cmd_key)
        response_msg = await self._safe_send(ctx, "正在查詢今日最新地震資訊...")
        
        try:
            # 獲取今日日期
            today = datetime.datetime.now().date()
            
            # 獲取最新地震資料
            earthquakes = await self.earthquake.fetch_earthquake_data()
            
            if not earthquakes:
                await self._safe_edit(response_msg, "❌ 無法獲取地震資料")
                processing_events.discard(cmd_key)
                return
            
            # 過濾出今日地震
            today_earthquakes = []
            for eq in earthquakes:
                try:
                    # 使用幫助方法獲取和解析時間
                    time_str = self.earthquake.get_earthquake_time_field(eq)
                    if not time_str:
                        continue
                    
                    eq_time = self.earthquake.parse_earthquake_time(time_str)
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
                    time_str = self.earthquake.get_earthquake_time_field(earthquake)
                    eq_time = self.earthquake.parse_earthquake_time(time_str)
                    return eq_time if eq_time else datetime.datetime(1970, 1, 1)
                
                today_earthquakes.sort(key=get_earthquake_time_for_sorting, reverse=True)
            except Exception as e:
                logger.error(f"排序地震時間出錯: {e}")
            
            if not today_earthquakes:
                await self._safe_edit(response_msg, "🔍 今日尚無地震資料")
                processing_events.discard(cmd_key)
                return
            
            # 獲取最新的一個地震
            latest_eq = today_earthquakes[0]
            
            # 獲取地震ID (嘗試不同的字段名稱)
            eq_id = latest_eq.get('earthquakeNo', latest_eq.get('EarthquakeNo', latest_eq.get('identifier', '未知ID')))
            
            # 發送地震警報
            await self.earthquake.send_earthquake_alert(latest_eq)
            
            await self._safe_edit(response_msg, f"✅ 已發送今日最新地震資訊 (ID: {eq_id})")
            logger.info(f"使用者 {ctx.author.name} 使用今日地震指令，發送了ID為 {eq_id} 的地震資訊")
            
        except Exception as e:
            await self._safe_edit(response_msg, f"❌ 查詢今日地震失敗: {str(e)}")
            logger.error(f"查詢今日地震失敗: {e}", exc_info=True)
        finally:
            # 確保完成後移除處理標記
            processing_events.discard(cmd_key)
    
    @commands.command(name="今日地震廣播")
    @commands.has_permissions(administrator=True)
    async def today_earthquake_broadcast(self, ctx):
        """廣播今日最新地震資訊（包含全體通知）"""
        # 檢查地震模組是否可用
        if not self._check_earthquake_module(ctx):
            return
            
        # 取得處理事件集合
        processing_events = self._get_processing_events()
            
        # 避免重複執行
        cmd_key = f"today_eq_broadcast_{ctx.author.id}"
        if cmd_key in processing_events:
            await self._safe_send(ctx, "⚠️ 指令處理中，請稍候再試")
            return
            
        processing_events.add(cmd_key)
        response_msg = await self._safe_send(ctx, "正在獲取今日最新地震資訊，準備廣播...")
        
        try:
            # 獲取今日日期
            today = datetime.datetime.now().date()
            
            # 獲取最新地震資料
            earthquakes = await self.earthquake.fetch_earthquake_data()
            
            if not earthquakes:
                await self._safe_edit(response_msg, "❌ 無法獲取地震資料")
                processing_events.discard(cmd_key)
                return
            
            # 過濾出今日地震
            today_earthquakes = []
            for eq in earthquakes:
                try:
                    # 使用幫助方法獲取時間字段
                    time_str = self.earthquake.get_earthquake_time_field(eq)
                    if not time_str:
                        logger.warning(f"無法找到地震時間字段，跳過: {eq.get('earthquakeNo', eq.get('EarthquakeNo', eq.get('identifier', 'unknown')))}")
                        continue
                    
                    # 使用幫助方法解析時間
                    eq_time = self.earthquake.parse_earthquake_time(time_str)
                    if not eq_time:
                        continue
                        
                    if eq_time.date() == today:
                        today_earthquakes.append(eq)
                except Exception as e:
                    logger.error(f"解析地震時間出錯: {e}")
                    continue
            
            if not today_earthquakes:
                await self._safe_edit(response_msg, "🔍 今日尚無地震資料")
                processing_events.discard(cmd_key)
                return
            
            # 按時間排序 (使用幫助方法)
            try:
                def get_earthquake_time_for_sorting(earthquake):
                    time_str = self.earthquake.get_earthquake_time_field(earthquake)
                    eq_time = self.earthquake.parse_earthquake_time(time_str)
                    return eq_time if eq_time else datetime.datetime(1970, 1, 1)
                
                today_earthquakes.sort(key=get_earthquake_time_for_sorting, reverse=True)
            except Exception as e:
                logger.error(f"排序地震資料出錯: {e}")
            
            # 獲取最新的一個地震
            latest_eq = today_earthquakes[0]
            
            # 獲取地震ID (嘗試不同的字段名稱)
            eq_id = latest_eq.get('earthquakeNo', latest_eq.get('EarthquakeNo', latest_eq.get('identifier', '未知ID')))
            
            # 發送地震警報，包含全體通知
            await self.earthquake.send_earthquake_alert(latest_eq, mention_everyone=True)
            
            await self._safe_edit(response_msg, f"✅ 已廣播今日最新地震資訊 (ID: {eq_id})")
            logger.info(f"管理員 {ctx.author.name} 使用今日地震廣播命令，發送了ID為 {eq_id} 的全體通知地震資訊")
            
        except Exception as e:
            await self._safe_edit(response_msg, f"❌ 廣播今日地震失敗: {str(e)}")
            logger.error(f"廣播今日地震失敗: {e}", exc_info=True)
        finally:
            # 確保完成後移除處理標記
            processing_events.discard(cmd_key)

    @commands.command(name="立即地震監測")
    @commands.has_permissions(administrator=True)
    async def immediate_earthquake_check(self, ctx):
        """立即執行一次地震監測並發送最新資訊 (僅限管理員)"""
        # 檢查地震模組是否可用
        if not self._check_earthquake_module(ctx):
            return
            
        # 取得處理事件集合
        processing_events = self._get_processing_events()
            
        # 避免重複執行
        cmd_key = f"immediate_check_{ctx.author.id}"
        if cmd_key in processing_events:
            await self._safe_send(ctx, "⚠️ 指令處理中，請稍候再試")
            return
            
        processing_events.add(cmd_key)
        response_msg = await self._safe_send(ctx, "🔍 正在立即執行地震監測...")
        
        try:
            # 避免頻率限制檢查，直接獲取最新地震資料
            earthquakes = await self.earthquake.fetch_earthquake_data()
            
            if not earthquakes:
                await self._safe_edit(response_msg, "❌ 無法獲取地震資料")
                processing_events.discard(cmd_key)
                return
                
            current_time = datetime.datetime.now()
            today = current_time.date()
            
            # 過濾今日地震
            today_earthquakes = []
            for eq in earthquakes:
                try:
                    # 使用幫助方法獲取時間字段
                    time_str = self.earthquake.get_earthquake_time_field(eq)
                    if not time_str:
                        continue
                    
                    # 使用幫助方法解析時間
                    eq_time = self.earthquake.parse_earthquake_time(time_str)
                    if not eq_time:
                        continue
                        
                    if eq_time.date() == today:
                        today_earthquakes.append(eq)
                except Exception as e:
                    logger.error(f"解析地震時間出錯: {e}")
                    continue
            
            if not today_earthquakes:
                await self._safe_edit(response_msg, "🔍 今日尚無地震資料")
                processing_events.discard(cmd_key)
                return
                
            # 按時間排序
            try:
                def get_earthquake_time_for_sorting(earthquake):
                    time_str = self.earthquake.get_earthquake_time_field(earthquake)
                    eq_time = self.earthquake.parse_earthquake_time(time_str)
                    return eq_time if eq_time else datetime.datetime(1970, 1, 1)
                
                today_earthquakes.sort(key=get_earthquake_time_for_sorting, reverse=True)
            except Exception as e:
                logger.error(f"排序地震資料出錯: {e}")
            
            # 獲取最新的地震
            latest_eq = today_earthquakes[0]
            
            # 取得地震ID
            eq_id = latest_eq.get('earthquakeNo', latest_eq.get('EarthquakeNo', latest_eq.get('identifier', '未知ID')))
            
            # 檢查是否已經發送過
            already_sent = eq_id in self.earthquake.sent_earthquakes
            status_msg = f"ID: {eq_id}, 發生時間: {latest_eq.get('originTime', latest_eq.get('time', '未知'))}\n"
            status_msg += f"已處理狀態: {'✅ 已發送過' if already_sent else '❌ 未發送過'}\n"
            
            # 無論是否已發送過，都發送一次
            await self.earthquake.send_earthquake_alert(latest_eq, mention_everyone=False)
            
            if not already_sent:
                # 將新地震加入已處理集合
                self.earthquake.last_earthquakes.add(eq_id)
                self.earthquake.sent_earthquakes.add(eq_id)
                self.earthquake.earthquake_timestamps[eq_id] = current_time.timestamp()
                
                # 保存已發送的地震ID
                self.earthquake._save_sent_earthquake_ids()
                self.earthquake._save_earthquake_state()
                
                status_msg += "該地震現已加入已處理記錄。"
                
            await self._safe_edit(response_msg, f"✅ 立即監測完成！\n{status_msg}")
            logger.info(f"管理員 {ctx.author.name} 執行了立即地震監測，發送了ID為 {eq_id} 的地震資訊")
            
        except Exception as e:
            await self._safe_edit(response_msg, f"❌ 立即監測失敗: {str(e)}")
            logger.error(f"立即監測失敗: {e}", exc_info=True)
        finally:
            # 確保完成後移除處理標記
            processing_events.discard(cmd_key)

    @commands.command(name="測試地震API")
    @commands.has_permissions(administrator=True)
    async def test_earthquake_api(self, ctx):
        """測試地震API連接和數據解析"""
        # 取得處理事件集合
        processing_events = self._get_processing_events()
        
        # 避免重複執行
        cmd_key = f"test_api_{ctx.author.id}"
        if cmd_key in processing_events:
            await self._safe_send(ctx, "⚠️ 指令處理中，請稍候再試")
            return
        
        processing_events.add(cmd_key)
        
        # 檢查地震模組是否可用
        if self.earthquake is None:
            response_msg = await self._safe_send(ctx, "⚠️ 地震監測模組尚未就緒，但仍嘗試進行API測試...")
            
            try:
                # 使用內部方法測試連接
                await ctx.send("⚠️ 無法測試API，地震監測模組不可用。")
                await ctx.send("請等待地震監測模組完成初始化後再試。")
                logger.warning(f"使用者 {ctx.author.name} 嘗試測試地震API，但地震模組尚未就緒")
            except Exception as e:
                await self._safe_send(ctx, f"❌ API測試失敗: {str(e)}")
                logger.error(f"API測試失敗: {e}", exc_info=True)
            finally:
                processing_events.discard(cmd_key)
            return
        
        response_msg = await self._safe_send(ctx, "🔍 正在測試中央氣象局地震API連接...")
        
        try:
            # 測試連接
            start_time = time.time()
            earthquakes = await self.earthquake.fetch_earthquake_data()
            api_time = time.time() - start_time
            
            if not earthquakes:
                await self._safe_edit(response_msg, "❌ 無法獲取地震資料")
                processing_events.discard(cmd_key)
                return
            
            # 測試數據解析
            parse_success = 0
            parse_failed = 0
            
            for eq in earthquakes:
                try:
                    # 測試時間解析
                    time_str = self.earthquake.get_earthquake_time_field(eq)
                    eq_time = self.earthquake.parse_earthquake_time(time_str)
                    
                    if eq_time:
                        parse_success += 1
                    else:
                        parse_failed += 1
                except Exception:
                    parse_failed += 1
            
            # 格式化響應
            result = [
                "✅ **中央氣象局地震API測試結果**",
                f"📡 API響應時間: {api_time:.2f}秒",
                f"📊 獲取的地震數量: {len(earthquakes)}",
                f"🔢 成功解析: {parse_success}，失敗: {parse_failed}",
                f"🔑 API金鑰狀態: {'已設置' if self.earthquake.cwb_api_key else '未設置'}"
            ]
            
            # 顯示最新的地震
            if earthquakes:
                latest = earthquakes[0]
                eq_id = latest.get('earthquakeNo', latest.get('EarthquakeNo', latest.get('identifier', '未知ID')))
                origin_time = self.earthquake.get_earthquake_time_field(latest) or "未知時間"
                
                # 取得規模
                magnitude = 0.0
                try:
                    if 'magnitudeValue' in latest:
                        magnitude = float(latest['magnitudeValue'])
                    elif 'MagnitudeValue' in latest:
                        magnitude = float(latest['MagnitudeValue'])
                    elif 'earthquakeMagnitude' in latest and 'magnitudeValue' in latest['earthquakeMagnitude']:
                        magnitude = float(latest['earthquakeMagnitude']['magnitudeValue'])
                    elif 'EarthquakeMagnitude' in latest and 'MagnitudeValue' in latest['EarthquakeMagnitude']:
                        magnitude = float(latest['EarthquakeMagnitude']['MagnitudeValue'])
                except (ValueError, TypeError):
                    magnitude = 0.0
                    
                result.append("\n**最新地震資訊**")
                result.append(f"🆔 地震ID: {eq_id}")
                result.append(f"🕒 發生時間: {origin_time}")
                result.append(f"📏 規模: {magnitude}")
            
            await self._safe_edit(response_msg, "\n".join(result))
            logger.info(f"管理員 {ctx.author.name} 執行了地震API測試")
            
        except Exception as e:
            await self._safe_edit(response_msg, f"❌ API測試失敗: {str(e)}")
            logger.error(f"API測試失敗: {e}", exc_info=True)
        finally:
            # 確保完成後移除處理標記
            processing_events.discard(cmd_key)

    @commands.command(name="檢查API資訊")
    @commands.has_permissions(administrator=True)
    async def check_api_details(self, ctx):
        """詳細檢查API連接和回應結構"""
        # 檢查地震模組是否可用
        if not self._check_earthquake_module(ctx):
            return
            
        # 取得處理事件集合
        processing_events = self._get_processing_events()
            
        # 避免重複執行
        cmd_key = f"check_api_{ctx.author.id}"
        if cmd_key in processing_events:
            await self._safe_send(ctx, "⚠️ 指令處理中，請稍候再試")
            return
            
        processing_events.add(cmd_key)
        response_msg = await self._safe_send(ctx, "🔍 正在詳細檢查API連接和回應結構...")
        
        try:
            # 獲取API URL和Key
            api_url = self.earthquake.cwb_api_url
            api_key = self.earthquake.cwb_api_key
            
            # 構建詳細信息字符串
            details = f"**API基本信息**\n"
            details += f"- URL: `{api_url}`\n"
            details += f"- API Key: `{api_key[:5]}...`\n\n"
            
            # 發送API請求
            headers = {
                "Authorization": api_key,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            
            # 更新狀態消息
            await self._safe_edit(response_msg, "發送API請求中...")
            
            async with self.earthquake.session.get(api_url, headers=headers) as response:
                # 更新HTTP狀態碼
                details += f"**HTTP響應**\n"
                details += f"- 狀態碼: {response.status}\n"
                
                # 檢查內容類型
                content_type = response.headers.get('Content-Type', '未知')
                details += f"- 內容類型: {content_type}\n"
                
                # 更新狀態消息
                await self._safe_edit(response_msg, f"{details}\n正在解析響應數據...")
                
                if response.status != 200:
                    error_text = await response.text()
                    details += f"- 錯誤響應: ```{error_text[:300]}...```\n"
                    await self._safe_edit(response_msg, details)
                    processing_events.discard(cmd_key)
                    return
                
                # 解析JSON響應
                try:
                    data = await response.json()
                    
                    # 更新狀態消息
                    await self._safe_edit(response_msg, f"{details}\n解析JSON成功，正在分析數據結構...")
                    
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
                        else:
                            details += f"- 無地震記錄\n"
                    else:
                        details += f"- Records字段: 不存在\n"
                
                except ValueError as e:
                    details += f"\n**解析錯誤**\n- JSON解析失敗: {str(e)}\n"
            
            # 發送完整的詳細信息
            details += f"\n[檢查時間: {datetime.datetime.now().strftime('%H:%M:%S')}]"
            await self._safe_edit(response_msg, details)
            
        except Exception as e:
            await self._safe_edit(response_msg, f"❌ API詳情檢查失敗: {str(e)}")
            logger.error(f"API詳情檢查失敗: {e}", exc_info=True)
        finally:
            # 確保完成後移除處理標記
            processing_events.discard(cmd_key)

    @commands.command(name="設置地震廣播")
    @commands.has_permissions(administrator=True)
    async def set_earthquake_broadcast(self, ctx, enabled: bool = None):
        """設置是否自動廣播今日地震 (需要管理員權限)
        
        參數:
            enabled: 是否啟用 (True/False)，不提供則顯示當前狀態
        """
        # 檢查地震模組是否可用
        if not self._check_earthquake_module(ctx):
            return
            
        # 取得處理事件集合
        processing_events = self._get_processing_events()
            
        # 避免重複執行
        cmd_key = f"set_broadcast_{ctx.author.id}"
        if cmd_key in processing_events:
            await self._safe_send(ctx, "⚠️ 指令處理中，請稍候再試")
            return
            
        processing_events.add(cmd_key)
        
        try:
            if enabled is None:
                # 顯示當前狀態
                status = "啟用" if self.earthquake.broadcast_today_earthquakes else "停用"
                await self._safe_send(ctx, f"🔊 自動廣播今日地震功能目前為: **{status}**")
                processing_events.discard(cmd_key)
                return
                
            # 更新設置
            self.earthquake.broadcast_today_earthquakes = enabled
            status = "啟用" if enabled else "停用"
            
            # 更新環境變數 (僅記憶體中，不持久化到.env文件)
            os.environ['EARTHQUAKE_BROADCAST_TODAY'] = str(enabled)
            
            # 更新配置文件
            self.earthquake.config['EARTHQUAKE_BROADCAST_TODAY'] = str(enabled)
            save_config('setting.json', self.earthquake.config)
            
            await self._safe_send(ctx, f"✅ 已{status}自動廣播今日地震功能")
            logger.info(f"管理員 {ctx.author.name} 已{status}自動廣播今日地震功能")
        except Exception as e:
            await self._safe_send(ctx, f"❌ 設置地震廣播失敗: {str(e)}")
            logger.error(f"設置地震廣播失敗: {e}", exc_info=True)
        finally:
            # 確保完成後移除處理標記
            processing_events.discard(cmd_key)

    @commands.command(name="地震輪詢狀態")
    async def earthquake_polling_status(self, ctx):
        """顯示地震輪詢狀態"""
        # 創建輪詢狀態訊息
        if self.earthquake is None:
            # 如果地震模組尚未就緒，顯示基本狀態
            embed = discord.Embed(
                title="⚠️ 地震監測狀態",
                description="地震監測模組尚未完全就緒",
                color=0xFFA500
            )
            embed.add_field(name="狀態", value="初始化中", inline=True)
            embed.add_field(name="指令可用性", value="部分功能可能不可用", inline=True)
            embed.set_footer(text=f"執行時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await ctx.send(embed=embed)
            logger.info(f"使用者 {ctx.author.name} 查詢地震輪詢狀態，但模組尚未就緒")
            return
        
        # 取得處理事件集合
        processing_events = self._get_processing_events()
        
        # 避免重複執行
        cmd_key = f"status_{ctx.author.id}"
        if cmd_key in processing_events:
            await self._safe_send(ctx, "⚠️ 指令處理中，請稍候再試")
            return
        
        processing_events.add(cmd_key)
        try:
            # 取得最後輪詢時間
            last_poll_time = getattr(self.earthquake, 'last_poll_time', None)
            if last_poll_time:
                last_poll_str = last_poll_time.strftime('%Y-%m-%d %H:%M:%S')
                time_diff = datetime.datetime.now() - last_poll_time
                time_diff_str = f"{time_diff.seconds} 秒前"
            else:
                last_poll_str = "未知"
                time_diff_str = "無法計算"
            
            # 輪詢狀態
            polling_active = getattr(self.earthquake, 'polling_active', False)
            polling_status = "✅ 正在運行" if polling_active else "❌ 未運行"
            
            # 輪詢間隔
            polling_interval = getattr(self.earthquake, 'polling_interval', 0)
            
            # API統計
            total_api_calls = getattr(self.earthquake, 'api_calls_total', 0)
            skipped_calls = getattr(self.earthquake, 'api_calls_skipped', 0)
            not_modified = getattr(self.earthquake, 'not_modified_responses', 0)
            cache_hits = getattr(self.earthquake, 'cache_hits', 0)
            
            # 計算效率
            if total_api_calls > 0:
                efficiency = (skipped_calls / total_api_calls) * 100
                efficiency_str = f"{efficiency:.1f}%"
            else:
                efficiency_str = "N/A"
            
            # 建立嵌入訊息
            embed = discord.Embed(
                title="📊 地震監測狀態",
                description="地震即時監測系統狀態報告",
                color=0x00FF00 if polling_active else 0xFF0000,
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(name="輪詢狀態", value=polling_status, inline=True)
            embed.add_field(name="最後輪詢時間", value=last_poll_str, inline=True)
            embed.add_field(name="距離現在", value=time_diff_str, inline=True)
            
            embed.add_field(name="當前輪詢間隔", value=f"{polling_interval} 秒", inline=True)
            embed.add_field(name="API請求總數", value=str(total_api_calls), inline=True)
            embed.add_field(name="已跳過請求", value=str(skipped_calls), inline=True)
            
            embed.add_field(name="304響應數", value=str(not_modified), inline=True)
            embed.add_field(name="緩存命中數", value=str(cache_hits), inline=True)
            embed.add_field(name="系統效率", value=efficiency_str, inline=True)
            
            if hasattr(self.earthquake, 'consecutive_errors') and self.earthquake.consecutive_errors > 0:
                embed.add_field(
                    name="⚠️ 錯誤警告", 
                    value=f"連續出錯次數: {self.earthquake.consecutive_errors}",
                    inline=False
                )
            
            embed.set_footer(text=f"API 金鑰狀態: {'已設置' if getattr(self.earthquake, 'cwb_api_key', None) else '未設置'}")
            
            # 發送訊息
            await ctx.send(embed=embed)
            logger.info(f"使用者 {ctx.author.name} 查詢地震輪詢狀態")
            
        except Exception as e:
            logger.error(f"顯示地震輪詢狀態時出錯: {e}", exc_info=True)
            await self._safe_send(ctx, f"❌ 顯示地震輪詢狀態時出錯: {e}")
        finally:
            # 移除處理標記
            processing_events.discard(cmd_key)


def setup(bot):
    """設置指令模組，連接至Discord Bot
    
    Args:
        bot: Discord Bot 實例
        
    Returns:
        EarthquakeCommands: 地震指令模組實例
    """
    # 創建指令模組實例，但暫時不設置地震模組
    commands_cog = EarthquakeCommands(bot)
    
    # 非同步函數中不能直接返回，所以我們需要將返回值存儲在命名空間中
    async def _async_setup():
        # 讓bot先添加這個cog
        await bot.add_cog(commands_cog)
        return commands_cog
        
    # 返回協程以便discord.py可以正確等待它完成
    return _async_setup() 