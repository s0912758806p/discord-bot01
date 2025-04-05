#!/usr/bin/env python3
"""
測試地震模組的單元測試
"""
import os
import sys
import json
import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

# 添加專案根目錄到 Python 路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

# 導入測試配置
from tests.test_config import setup_test_environment, create_mock_bot, create_test_data_file

# 導入被測試的模組
from cmds.earthquake import Earthquake

class TestEarthquakeUnit(unittest.TestCase):
    """測試 Earthquake 類的基本功能"""
    
    def setUp(self):
        """設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
        # 創建模擬的 Discord 機器人
        self.mock_bot = create_mock_bot()
        
        # 創建測試配置文件
        self.test_config_file = create_test_data_file(
            'earthquake_config.json',
            {
                "api_key": "test_api_key",
                "watch_channels": ["123456789"],
                "alert_channels": ["987654321"],
                "earthquake_data": {},
                "last_sent_times": {}
            }
        )
        
        # 模擬環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['EARTHQUAKE_API_KEY'] = 'test_api_key'
        os.environ['EARTHQUAKE_CONFIG_FILE'] = self.test_config_file
        
        # 創建測試對象，但對類打補丁，防止異步函數實際運行
        with patch('cmds.earthquake.Earthquake._delayed_full_initialization'), \
             patch('cmds.earthquake.Earthquake._start_earthquake_monitoring'):
            self.earthquake = Earthquake(self.mock_bot)
            
    def tearDown(self):
        """清理測試環境"""
        # 刪除測試創建的文件
        if os.path.exists(self.test_config_file):
            try:
                os.remove(self.test_config_file)
            except:
                pass
    
    def test_earthquake_initialization(self):
        """測試地震模組初始化"""
        # 檢查基本屬性是否正確初始化
        self.assertEqual(self.earthquake.bot, self.mock_bot)
        self.assertIsNotNone(self.earthquake.name)
        self.assertEqual(self.earthquake.name, "Earthquake")
        self.assertFalse(self.earthquake.is_initialized)
        self.assertFalse(self.earthquake.is_fully_initialized)
        self.assertEqual(self.earthquake.api_key, "test_api_key")
        
    def test_load_config(self):
        """測試加載配置功能"""
        # 使用臨時測試配置
        test_config = {
            "api_key": "new_test_api_key",
            "watch_channels": ["111222333"],
            "alert_channels": ["444555666"],
            "earthquake_data": {"test": "data"},
            "last_sent_times": {"test": "time"}
        }
        
        # 創建配置文件
        test_file = create_test_data_file('test_config.json', test_config)
        
        # 模擬函數
        with patch('cmds.earthquake.Earthquake._validate_config', return_value=True):
            self.earthquake.config_file = test_file
            result = self.earthquake._load_config()
        
        # 驗證結果
        self.assertTrue(result)
        self.assertEqual(self.earthquake.api_key, "new_test_api_key")
        self.assertEqual(self.earthquake.watch_channels, ["111222333"])
        self.assertEqual(self.earthquake.alert_channels, ["444555666"])
        self.assertEqual(self.earthquake.earthquake_data, {"test": "data"})
        self.assertEqual(self.earthquake.last_sent_times, {"test": "time"})
        
        # 刪除測試文件
        if os.path.exists(test_file):
            os.remove(test_file)
    
    def test_save_config(self):
        """測試保存配置功能"""
        # 設置測試數據
        self.earthquake.api_key = "save_test_api_key"
        self.earthquake.watch_channels = ["save_test_channel"]
        self.earthquake.alert_channels = ["save_alert_channel"]
        self.earthquake.earthquake_data = {"save_test": "data"}
        self.earthquake.last_sent_times = {"save_test": "time"}
        
        # 調用保存函數
        test_file = create_test_data_file('save_config.json', {})
        self.earthquake.config_file = test_file
        result = self.earthquake._save_config()
        
        # 驗證結果
        self.assertTrue(result)
        
        # 讀取保存的文件
        with open(test_file, 'r', encoding='utf-8') as f:
            saved_config = json.load(f)
        
        # 檢查保存的數據
        self.assertEqual(saved_config["api_key"], "save_test_api_key")
        self.assertEqual(saved_config["watch_channels"], ["save_test_channel"])
        self.assertEqual(saved_config["alert_channels"], ["save_alert_channel"])
        self.assertEqual(saved_config["earthquake_data"], {"save_test": "data"})
        self.assertEqual(saved_config["last_sent_times"], {"save_test": "time"})
        
        # 刪除測試文件
        if os.path.exists(test_file):
            os.remove(test_file)
            
    def test_get_color_by_magnitude(self):
        """測試根據震級獲取顏色功能"""
        # 測試不同震級的顏色
        self.assertEqual(self.earthquake.get_color_by_magnitude(2.0), 0x3CB043)  # 綠色
        self.assertEqual(self.earthquake.get_color_by_magnitude(4.0), 0xFFD700)  # 黃色
        self.assertEqual(self.earthquake.get_color_by_magnitude(5.5), 0xFFA500)  # 橙色
        self.assertEqual(self.earthquake.get_color_by_magnitude(7.0), 0xFF0000)  # 紅色
        
    def test_cleanup_last_sent_times(self):
        """測試清理過期的最後發送時間記錄"""
        # 設置測試數據
        current_time = datetime.now()
        older_time = (current_time - timedelta(days=2)).timestamp()
        much_older_time = (current_time - timedelta(days=10)).timestamp()
        recent_time = (current_time - timedelta(hours=1)).timestamp()
        
        self.earthquake.last_sent_times = {
            "recent": recent_time,
            "older": older_time,
            "much_older": much_older_time
        }
        
        # 調用清理函數
        self.earthquake._cleanup_last_sent_times()
        
        # 檢查結果 - 3天前的應該被清理
        self.assertIn("recent", self.earthquake.last_sent_times)
        self.assertIn("older", self.earthquake.last_sent_times)
        self.assertNotIn("much_older", self.earthquake.last_sent_times)

class TestEarthquakeAsync(unittest.IsolatedAsyncioTestCase):
    """測試 Earthquake 類的異步功能"""
    
    async def asyncSetUp(self):
        """異步設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
        # 創建模擬的 Discord 機器人
        self.mock_bot = create_mock_bot()
        self.mock_bot.wait_until_ready = AsyncMock()
        
        # 創建測試配置文件
        self.test_config_file = create_test_data_file(
            'earthquake_async_config.json',
            {
                "api_key": "async_test_api_key",
                "watch_channels": ["123456789"],
                "alert_channels": ["987654321"],
                "earthquake_data": {},
                "last_sent_times": {}
            }
        )
        
        # 模擬環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['EARTHQUAKE_API_KEY'] = 'async_test_api_key'
        os.environ['EARTHQUAKE_CONFIG_FILE'] = self.test_config_file
        
        # 創建測試對象，但對類打補丁，防止異步函數實際運行
        with patch('cmds.earthquake.Earthquake._delayed_full_initialization'), \
             patch('cmds.earthquake.Earthquake._start_earthquake_monitoring'):
            self.earthquake = Earthquake(self.mock_bot)
        
    async def asyncTearDown(self):
        """異步清理測試環境"""
        # 刪除測試創建的文件
        if os.path.exists(self.test_config_file):
            try:
                os.remove(self.test_config_file)
            except:
                pass
    
    async def test_delayed_initialization(self):
        """測試延遲初始化功能"""
        # 設置模擬
        self.earthquake._setup_api_session = AsyncMock(return_value=True)
        self.earthquake._setup_earthquake_endpoints = AsyncMock(return_value=True)
        self.mock_bot.wait_until_ready = AsyncMock()
        
        # 手動設置初始化狀態
        self.earthquake.is_initialized = True
        self.earthquake.is_fully_initialized = False
        
        # 調用延遲初始化
        with patch('asyncio.sleep', AsyncMock()):
            await self.earthquake._delayed_full_initialization()
        
        # 驗證結果
        self.assertTrue(self.earthquake.is_fully_initialized)
        self.mock_bot.wait_until_ready.assert_called()
        self.earthquake._setup_api_session.assert_called_once()
        self.earthquake._setup_earthquake_endpoints.assert_called_once()
        
    async def test_delayed_initialization_with_retry(self):
        """測試延遲初始化重試功能"""
        # 設置模擬
        self.earthquake._setup_api_session = AsyncMock()
        self.earthquake._setup_api_session.side_effect = [Exception("Test error"), True]
        self.earthquake._setup_earthquake_endpoints = AsyncMock(return_value=True)
        self.mock_bot.wait_until_ready = AsyncMock()
        
        # 手動設置初始化狀態
        self.earthquake.is_initialized = True
        self.earthquake.is_fully_initialized = False
        
        # 調用延遲初始化
        with patch('asyncio.sleep', AsyncMock()):
            await self.earthquake._delayed_full_initialization()
        
        # 驗證結果
        self.assertTrue(self.earthquake.is_fully_initialized)
        self.assertEqual(self.earthquake._setup_api_session.call_count, 2)  # 應該調用了2次
        
    @patch('cmds.earthquake.aiohttp.ClientSession')
    async def test_setup_api_session(self, mock_client_session):
        """測試設置API會話"""
        # 設置模擬
        mock_session = AsyncMock()
        mock_client_session.return_value = mock_session
        
        # 調用函數
        result = await self.earthquake._setup_api_session()
        
        # 驗證結果
        self.assertTrue(result)
        self.assertEqual(self.earthquake.session, mock_session)
        
    @patch('cmds.earthquake.aiohttp.ClientSession')
    async def test_setup_api_session_error(self, mock_client_session):
        """測試設置API會話發生錯誤的情況"""
        # 設置模擬
        mock_client_session.side_effect = Exception("API session error")
        
        # 調用函數
        result = await self.earthquake._setup_api_session()
        
        # 驗證結果
        self.assertFalse(result)
        self.assertIsNone(self.earthquake.session)

if __name__ == '__main__':
    unittest.main() 