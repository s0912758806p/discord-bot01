"""
模組連接器 - 協調不同模組之間的通信與互動
用於解決模組間依賴和初始化順序問題
"""

import asyncio
import logging
import os
import datetime
from typing import Optional, Dict, Any, Callable, Awaitable, List, Tuple

# 設置日誌
from core.logging import logger

class ModuleConnector:
    """模組連接器類，用於協調不同模組之間的通信與相依關係"""
    
    def __init__(self, bot):
        """初始化模組連接器
        
        Args:
            bot: Discord Bot實例
        """
        self.bot = bot
        # 模組註冊表，儲存所有已註冊的模組 {模組名稱: 模組實例}
        self.modules = {}
        # 模組狀態表，記錄每個模組的狀態
        self.module_states = {}
        # 等待模組就緒的任務列表
        self.pending_tasks = []
        # 模組間通信的事件列表
        self.events = {}
        # 初始化完成標記
        self.init_complete = False
        # 創建初始化任務
        self.bot.loop.create_task(self._delayed_init())
        
        logger.info("模組連接器初始化完成")
        
    async def _delayed_init(self):
        """延遲初始化，等待機器人就緒後執行"""
        await self.bot.wait_until_ready()
        
        # 獲取環境變數中設置的延遲時間，預設為5秒
        delay = int(os.environ.get('MODULE_CONNECTOR_DELAY', '5'))
        logger.info(f"模組連接器延遲初始化等待 {delay} 秒...")
        await asyncio.sleep(delay)
        
        # 發現並註冊所有模組
        self._discover_modules()
        
        # 啟動模組狀態監控
        self.bot.loop.create_task(self._monitor_module_states())
        
        self.init_complete = True
        logger.info("模組連接器初始化完成，發現 %d 個模組", len(self.modules))
        
    def _discover_modules(self):
        """發現並註冊所有已加載的模組"""
        for cog_name, cog in self.bot.cogs.items():
            logger.info(f"發現Cog: {cog_name}")
            self.register_module(cog_name, cog)
            
        # 特別檢查地震監測模組和地震指令模組
        earthquake_module = self.bot.get_cog('Earthquake')
        earthquake_commands = self.bot.get_cog('EarthquakeCommands')
        
        # 檢查這兩個模組是否都存在
        if earthquake_module and earthquake_commands:
            logger.info("發現地震監測模組和地震指令模組，嘗試連接")
            self.connect_modules('Earthquake', 'EarthquakeCommands')
            
    def register_module(self, module_name: str, module_instance: Any) -> bool:
        """註冊一個模組
        
        Args:
            module_name: 模組名稱
            module_instance: 模組實例
            
        Returns:
            bool: 註冊是否成功
        """
        if module_name in self.modules:
            logger.warning(f"模組 {module_name} 已被註冊，忽略重複註冊請求")
            return False
            
        self.modules[module_name] = module_instance
        
        # 初始化模組狀態
        self.module_states[module_name] = {
            'registered_at': datetime.datetime.now(),
            'ready': False,
            'error': None,
            'last_status_check': datetime.datetime.now(),
            'dependencies': [],
            'dependents': []
        }
        
        logger.info(f"成功註冊模組: {module_name}")
        return True
        
    def get_module(self, module_name: str) -> Optional[Any]:
        """獲取已註冊的模組
        
        Args:
            module_name: 模組名稱
            
        Returns:
            Optional[Any]: 模組實例，若不存在則返回None
        """
        if module_name not in self.modules:
            logger.warning(f"嘗試獲取未註冊的模組: {module_name}")
            return None
            
        return self.modules.get(module_name)
        
    def set_module_ready(self, module_name: str, is_ready: bool = True, error: str = None) -> bool:
        """設置模組就緒狀態
        
        Args:
            module_name: 模組名稱
            is_ready: 是否就緒
            error: 錯誤信息，若有
            
        Returns:
            bool: 設置是否成功
        """
        if module_name not in self.module_states:
            logger.warning(f"嘗試設置未註冊模組的狀態: {module_name}")
            return False
            
        self.module_states[module_name]['ready'] = is_ready
        self.module_states[module_name]['error'] = error
        self.module_states[module_name]['last_status_check'] = datetime.datetime.now()
        
        logger.info(f"模組 {module_name} 狀態已更新: ready={is_ready}, error={error}")
        
        # 檢查是否有等待這個模組的任務需要處理
        self._process_pending_tasks(module_name)
        
        return True
        
    def _process_pending_tasks(self, module_name: str):
        """處理等待該模組就緒的任務
        
        Args:
            module_name: 模組名稱
        """
        tasks_to_remove = []
        for i, (task_module, future) in enumerate(self.pending_tasks):
            if task_module == module_name:
                is_ready = self.module_states[module_name]['ready']
                error = self.module_states[module_name]['error']
                
                if is_ready:
                    # 模組就緒，解決Future
                    future.set_result(self.modules[module_name])
                elif error:
                    # 模組出錯，設置異常
                    future.set_exception(Exception(f"模組 {module_name} 發生錯誤: {error}"))
                    
                tasks_to_remove.append(i)
                
        # 移除已處理的任務
        for i in sorted(tasks_to_remove, reverse=True):
            self.pending_tasks.pop(i)
        
    async def wait_for_module(self, module_name: str, timeout: float = 30.0) -> Any:
        """等待模組就緒
        
        Args:
            module_name: 模組名稱
            timeout: 超時時間（秒）
            
        Returns:
            Any: 模組實例
            
        Raises:
            asyncio.TimeoutError: 如果等待超時
            Exception: 如果模組初始化失敗
        """
        # 檢查模組是否已註冊
        if module_name not in self.modules:
            logger.warning(f"等待未註冊的模組: {module_name}")
            raise ValueError(f"模組 {module_name} 未註冊")
            
        # 檢查模組是否已就緒
        if self.module_states[module_name]['ready']:
            return self.modules[module_name]
            
        # 建立Future用於等待模組就緒
        future = asyncio.Future()
        self.pending_tasks.append((module_name, future))
        
        try:
            # 等待模組就緒或超時
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            self.pending_tasks = [(m, f) for m, f in self.pending_tasks if m != module_name]
            logger.error(f"等待模組 {module_name} 就緒超時")
            raise
            
    def connect_modules(self, source_module: str, target_module: str) -> bool:
        """連接兩個模組，建立依賴關係
        
        Args:
            source_module: 源模組名稱
            target_module: 目標模組名稱
            
        Returns:
            bool: 連接是否成功
        """
        # 檢查模組是否已註冊
        if source_module not in self.modules:
            logger.warning(f"嘗試連接未註冊的源模組: {source_module}")
            return False
            
        if target_module not in self.modules:
            logger.warning(f"嘗試連接未註冊的目標模組: {target_module}")
            return False
            
        # 更新依賴關係
        if target_module not in self.module_states[source_module]['dependencies']:
            self.module_states[source_module]['dependencies'].append(target_module)
            
        if source_module not in self.module_states[target_module]['dependents']:
            self.module_states[target_module]['dependents'].append(source_module)
            
        logger.info(f"模組 {source_module} 和 {target_module} 已連接")
        
        # 如果是地震監測模組和地震指令模組，則嘗試設置引用
        if source_module == 'Earthquake' and target_module == 'EarthquakeCommands':
            earthquake_module = self.modules[source_module]
            commands_module = self.modules[target_module]
            
            if hasattr(commands_module, 'set_earthquake_module'):
                logger.info("嘗試設置地震指令模組引用")
                commands_module.set_earthquake_module(earthquake_module)
                logger.info("✅ 通過模組連接器成功設置地震指令模組引用")
                
                # 檢查地震監測模組是否有重啟方法，確保兩者正確連接
                if hasattr(earthquake_module, 'restart_earthquake_module'):
                    logger.info("確認地震監測模組具有重啟方法")
                
        # 或者反向
        elif source_module == 'EarthquakeCommands' and target_module == 'Earthquake':
            earthquake_module = self.modules[target_module]
            commands_module = self.modules[source_module]
            
            if hasattr(commands_module, 'set_earthquake_module'):
                logger.info("嘗試設置地震指令模組引用")
                commands_module.set_earthquake_module(earthquake_module)
                logger.info("✅ 通過模組連接器成功設置地震指令模組引用")
        
        return True
        
    async def _monitor_module_states(self):
        """監控模組狀態的任務"""
        while True:
            await asyncio.sleep(60)  # 每分鐘檢查一次
            
            for module_name, state in self.module_states.items():
                # 檢查模組是否仍然存在
                if module_name not in self.bot.cogs:
                    logger.warning(f"模組 {module_name} 不再存在，標記為非就緒")
                    state['ready'] = False
                    state['error'] = "模組不再存在"
                else:
                    # 檢查地震監測模組的特殊狀態
                    if module_name == 'Earthquake':
                        module = self.modules[module_name]
                        # 檢查輪詢狀態
                        if hasattr(module, 'polling_active') and not module.polling_active:
                            logger.warning(f"地震監測模組輪詢非活動狀態，嘗試重啟")
                            # 嘗試重啟
                            if hasattr(module, 'restart_earthquake_module'):
                                try:
                                    await module.restart_earthquake_module()
                                    logger.info("✅ 地震監測模組重啟成功")
                                except Exception as e:
                                    logger.error(f"地震監測模組重啟失敗: {e}")
                                    
            # 重新檢查並連接地震相關模組
            earthquake_module = self.bot.get_cog('Earthquake')
            earthquake_commands = self.bot.get_cog('EarthquakeCommands')
            
            if earthquake_module and earthquake_commands:
                # 檢查指令模組是否已設置地震模組引用
                if (hasattr(earthquake_commands, 'earthquake') and 
                    earthquake_commands.earthquake is None):
                    logger.warning("發現地震指令模組未設置地震模組引用，嘗試重新連接")
                    earthquake_commands.set_earthquake_module(earthquake_module)
                    logger.info("✅ 通過監控任務重新設置地震指令模組引用")
                    
    def get_module_state(self, module_name: str) -> Dict[str, Any]:
        """獲取模組狀態
        
        Args:
            module_name: 模組名稱
            
        Returns:
            Dict[str, Any]: 模組狀態信息
        """
        if module_name not in self.module_states:
            return {
                'exists': False,
                'registered': False,
                'ready': False,
                'error': "模組未註冊"
            }
            
        state = self.module_states[module_name].copy()
        state['exists'] = module_name in self.bot.cogs
        state['registered'] = True
        
        return state
        
    def get_all_module_states(self) -> Dict[str, Dict[str, Any]]:
        """獲取所有模組的狀態
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有模組的狀態信息
        """
        result = {}
        for module_name in self.modules:
            result[module_name] = self.get_module_state(module_name)
            
        return result
        
    async def reconnect_modules(self, source_module: str, target_module: str) -> bool:
        """重新連接兩個模組，用於錯誤恢復
        
        Args:
            source_module: 源模組名稱
            target_module: 目標模組名稱
            
        Returns:
            bool: 重連是否成功
        """
        # 先刪除舊連接
        if target_module in self.module_states[source_module]['dependencies']:
            self.module_states[source_module]['dependencies'].remove(target_module)
            
        if source_module in self.module_states[target_module]['dependents']:
            self.module_states[target_module]['dependents'].remove(source_module)
            
        # 然後重新建立連接
        return self.connect_modules(source_module, target_module)

async def setup(bot):
    """設置模組連接器
    
    Args:
        bot: Discord Bot實例
    """
    connector = ModuleConnector(bot)
    bot._module_connector = connector
    logger.info("模組連接器已註冊到機器人實例")
    return None  # 明確返回 None 