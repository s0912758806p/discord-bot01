#!/usr/bin/env python3
"""
測試模組連接器的單元測試
"""
import os
import sys
import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# 添加專案根目錄到 Python 路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

# 導入測試配置
from tests.test_config import setup_test_environment, create_mock_bot

# 導入被測試的模組
from cmds.module_connector import ModuleConnector, setup

class TestModuleConnector(unittest.TestCase):
    """測試 ModuleConnector 類的基本功能"""
    
    def setUp(self):
        """設置測試環境"""
        # 設置測試環境
        setup_test_environment()
        
        # 創建模擬的 Discord 機器人
        self.mock_bot = create_mock_bot()
        
        # 創建 ModuleConnector 實例
        self.connector = ModuleConnector(self.mock_bot)
        
    def test_module_connector_initialization(self):
        """測試 ModuleConnector 初始化"""
        # 檢查 ModuleConnector 是否正確初始化
        self.assertIsNotNone(self.connector)
        self.assertEqual(self.connector.bot, self.mock_bot)
        self.assertIsNotNone(self.connector.modules)
        self.assertIsInstance(self.connector.modules, dict)
        self.assertEqual(len(self.connector.modules), 0)  # 初始狀態下沒有註冊模組
        
    def test_register_module(self):
        """測試註冊模組功能"""
        # 創建模擬模組
        mock_module = MagicMock()
        mock_module.name = "test_module"
        
        # 註冊模組
        self.connector.register_module(mock_module)
        
        # 驗證模組是否成功註冊
        self.assertIn("test_module", self.connector.modules)
        self.assertEqual(self.connector.modules["test_module"]["module"], mock_module)
        self.assertFalse(self.connector.modules["test_module"]["ready"])
        
    def test_register_duplicate_module(self):
        """測試註冊重複的模組"""
        # 創建模擬模組
        mock_module = MagicMock()
        mock_module.name = "test_module"
        
        # 註冊模組
        self.connector.register_module(mock_module)
        
        # 再次註冊相同名稱的模組
        # 應該覆蓋先前的註冊
        mock_module2 = MagicMock()
        mock_module2.name = "test_module"
        self.connector.register_module(mock_module2)
        
        # 驗證模組是否成功更新
        self.assertIn("test_module", self.connector.modules)
        self.assertEqual(self.connector.modules["test_module"]["module"], mock_module2)
        
    def test_set_module_ready(self):
        """測試設置模組已準備好"""
        # 創建模擬模組
        mock_module = MagicMock()
        mock_module.name = "test_module"
        
        # 註冊模組
        self.connector.register_module(mock_module)
        
        # 設置模組為準備好狀態
        self.connector.set_module_ready("test_module")
        
        # 驗證模組狀態是否已更新
        self.assertTrue(self.connector.modules["test_module"]["ready"])
        
    def test_set_nonexistent_module_ready(self):
        """測試設置不存在的模組為準備好狀態"""
        # 嘗試設置未註冊的模組為準備好狀態
        # 不應導致錯誤，但應該記錄警告
        with self.assertLogs(level='WARNING'):
            self.connector.set_module_ready("nonexistent_module")
        
    def test_is_module_ready(self):
        """測試檢查模組是否準備好"""
        # 創建模擬模組
        mock_module = MagicMock()
        mock_module.name = "test_module"
        
        # 註冊模組
        self.connector.register_module(mock_module)
        
        # 檢查初始狀態
        self.assertFalse(self.connector.is_module_ready("test_module"))
        
        # 設置模組為準備好狀態
        self.connector.set_module_ready("test_module")
        
        # 檢查更新後的狀態
        self.assertTrue(self.connector.is_module_ready("test_module"))
        
    def test_is_nonexistent_module_ready(self):
        """測試檢查不存在的模組是否準備好"""
        # 檢查未註冊的模組狀態
        # 應該返回 False
        self.assertFalse(self.connector.is_module_ready("nonexistent_module"))

class TestModuleConnectorAsync(unittest.IsolatedAsyncioTestCase):
    """測試 ModuleConnector 類的異步功能"""
    
    async def asyncSetUp(self):
        """異步設置測試環境"""
        # 設置測試環境
        setup_test_environment()
        
        # 創建模擬的 Discord 機器人
        self.mock_bot = create_mock_bot()
        
        # 創建 ModuleConnector 實例
        self.connector = ModuleConnector(self.mock_bot)
        
    async def test_wait_for_module_ready(self):
        """測試等待模組準備好的功能"""
        # 創建模擬模組
        mock_module = MagicMock()
        mock_module.name = "async_test_module"
        
        # 註冊模組
        self.connector.register_module(mock_module)
        
        # 創建獨立的任務來設置模組為準備好狀態
        async def set_module_ready_after_delay():
            await asyncio.sleep(0.1)  # 短暫延遲
            self.connector.set_module_ready("async_test_module")
            
        # 啟動設置任務
        asyncio.create_task(set_module_ready_after_delay())
        
        # 等待模組準備好
        await self.connector.wait_for_module_ready("async_test_module", timeout=1)
        
        # 驗證模組狀態
        self.assertTrue(self.connector.is_module_ready("async_test_module"))
        
    async def test_wait_for_module_ready_timeout(self):
        """測試等待模組準備好超時的情況"""
        # 創建模擬模組
        mock_module = MagicMock()
        mock_module.name = "timeout_test_module"
        
        # 註冊模組
        self.connector.register_module(mock_module)
        
        # 等待模組準備好，應該會超時
        with self.assertRaises(asyncio.TimeoutError):
            await self.connector.wait_for_module_ready("timeout_test_module", timeout=0.1)
        
        # 驗證模組狀態仍然為未準備好
        self.assertFalse(self.connector.is_module_ready("timeout_test_module"))
    
    async def test_wait_for_nonexistent_module(self):
        """測試等待不存在的模組"""
        # 等待未註冊的模組準備好，應該會超時
        with self.assertRaises(asyncio.TimeoutError):
            await self.connector.wait_for_module_ready("nonexistent_async_module", timeout=0.1)

    @patch('cmds.module_connector.setup')
    async def test_setup_function(self, mock_setup):
        """測試 setup 函數"""
        # 創建模擬的 bot 實例
        mock_bot = create_mock_bot()
        
        # 調用實際的 setup 函數
        real_setup = setup
        await real_setup(mock_bot)
        
        # 驗證 bot.add_cog 是否被調用
        mock_bot.add_cog.assert_called_once()

if __name__ == '__main__':
    unittest.main() 