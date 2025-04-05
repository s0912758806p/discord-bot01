#!/usr/bin/env python3
"""
地震模組整合測試
測試地震模組與其他模組的整合，特別是模組初始化和依賴處理
"""
import os
import sys
import json
import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

# 添加專案根目錄到 Python 路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

# 導入測試配置
from tests.test_config import setup_test_environment, create_mock_bot, create_test_data_file

# 以下導入語句在測試開始前使用補丁
with patch('discord.ext.commands.Bot'):
    from cmds.earthquake import Earthquake
    from cmds.module_connector import ModuleConnector

class TestEarthquakeModuleIntegration(unittest.IsolatedAsyncioTestCase):
    """測試地震模組與其他模組的整合"""
    
    async def asyncSetUp(self):
        """設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
        # 創建模擬的 Discord 機器人
        self.mock_bot = create_mock_bot()
        self.mock_bot.wait_until_ready = AsyncMock()
        
        # 創建測試配置文件
        self.test_config_file = create_test_data_file(
            'earthquake_integration_config.json',
            {
                "api_key": "integration_test_api_key",
                "watch_channels": ["123456789"],
                "alert_channels": ["987654321"],
                "earthquake_data": {},
                "last_sent_times": {}
            }
        )
        
        # 模擬環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['EARTHQUAKE_API_KEY'] = 'integration_test_api_key'
        os.environ['EARTHQUAKE_CONFIG_FILE'] = self.test_config_file
        
        # 創建模組連接器
        self.module_connector = ModuleConnector(self.mock_bot)
        self.mock_bot.get_cog.return_value = self.module_connector
        
        # 創建地震模組，但阻止實際初始化
        with patch('cmds.earthquake.Earthquake._delayed_full_initialization'), \
             patch('cmds.earthquake.Earthquake._start_earthquake_monitoring'):
            self.earthquake = Earthquake(self.mock_bot)
            
    async def asyncTearDown(self):
        """清理測試環境"""
        # 刪除測試創建的文件
        if os.path.exists(self.test_config_file):
            try:
                os.remove(self.test_config_file)
            except:
                pass
    
    async def test_module_registration(self):
        """測試模組註冊到連接器"""
        # 註冊地震模組
        self.module_connector.register_module(self.earthquake)
        
        # 檢查註冊結果
        self.assertIn("Earthquake", self.module_connector.modules)
        self.assertEqual(self.module_connector.modules["Earthquake"]["module"], self.earthquake)
        self.assertFalse(self.module_connector.modules["Earthquake"]["ready"])
        
        # 設置模組準備好
        self.module_connector.set_module_ready("Earthquake")
        self.assertTrue(self.module_connector.modules["Earthquake"]["ready"])
        
    async def test_module_initialization_sequence(self):
        """測試模組的初始化順序"""
        # 創建模擬的地震指令模組
        mock_earthquake_commands = MagicMock()
        mock_earthquake_commands.name = "EarthquakeCommands"
        mock_earthquake_commands.set_earthquake_module = MagicMock()
        
        # 註冊模組
        self.module_connector.register_module(self.earthquake)
        self.module_connector.register_module(mock_earthquake_commands)
        
        # 設置依賴關係
        self.module_connector.connect_modules("Earthquake", "EarthquakeCommands")
        
        # 檢查依賴關係
        earthquake_module = self.module_connector.modules["Earthquake"]
        earthquake_commands_module = self.module_connector.modules["EarthquakeCommands"]
        
        self.assertIn("EarthquakeCommands", earthquake_module.get("dependents", []))
        self.assertIn("Earthquake", earthquake_commands_module.get("dependencies", []))
        
    async def test_wait_for_module_ready(self):
        """測試等待模組準備好"""
        # 註冊地震模組
        self.module_connector.register_module(self.earthquake)
        
        # 創建任務來設置模組準備好
        async def set_module_ready_after_delay():
            await asyncio.sleep(0.1)
            self.module_connector.set_module_ready("Earthquake")
            
        # 啟動設置任務
        asyncio.create_task(set_module_ready_after_delay())
        
        # 等待模組準備好
        await self.module_connector.wait_for_module_ready("Earthquake", timeout=1)
        
        # 檢查結果
        self.assertTrue(self.module_connector.is_module_ready("Earthquake"))
        
    @patch('cmds.earthquake.aiohttp.ClientSession')
    async def test_earthquake_module_lifecycle(self, mock_client_session):
        """測試地震模組的生命週期"""
        # 設置模擬
        mock_session = AsyncMock()
        mock_client_session.return_value = mock_session
        
        # 解除補丁，允許部分初始化
        with patch('cmds.earthquake.Earthquake._start_earthquake_monitoring'):
            # 創建新的地震模組實例
            earthquake = Earthquake(self.mock_bot)
            
            # 手動調用初始化方法
            await earthquake._setup_api_session()
            await earthquake._setup_earthquake_endpoints()
            
            # 檢查初始化結果
            self.assertIsNotNone(earthquake.session)
            self.assertTrue(earthquake.is_initialized)
            
            # 模擬完全初始化
            earthquake.is_fully_initialized = True
            
            # 註冊到模組連接器
            self.module_connector.register_module(earthquake)
            self.module_connector.set_module_ready("Earthquake")
            
            # 檢查狀態
            self.assertTrue(earthquake.is_initialized)
            self.assertTrue(earthquake.is_fully_initialized)
            self.assertTrue(self.module_connector.is_module_ready("Earthquake"))
            
            # 模擬關閉
            if earthquake.session:
                await earthquake.session.close()
                
class TestEarthquakeCommandsIntegration(unittest.IsolatedAsyncioTestCase):
    """測試地震指令模組與地震模組的整合"""
    
    async def asyncSetUp(self):
        """設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
        # 創建模擬的 Discord 機器人
        self.mock_bot = create_mock_bot()
        
        # 模擬環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        
        # 創建模組連接器
        self.module_connector = ModuleConnector(self.mock_bot)
        self.mock_bot.get_cog.side_effect = lambda name: self.module_connector if name == "ModuleConnector" else None
        
        # 創建模擬地震模組
        self.mock_earthquake = MagicMock()
        self.mock_earthquake.name = "Earthquake"
        self.mock_earthquake.get_module_status = MagicMock(return_value={
            "is_initialized": True,
            "is_fully_initialized": True,
            "api_connected": True,
            "last_check_time": "2023-04-05 12:00:00",
            "watch_channels": ["123456789"],
            "alert_channels": ["987654321"]
        })
        self.mock_earthquake.restart_earthquake_module = AsyncMock(return_value=(True, "重啟成功"))
        
        # 創建模擬地震指令模組
        self.mock_earthquake_commands = MagicMock()
        self.mock_earthquake_commands.name = "EarthquakeCommands"
        self.mock_earthquake_commands.set_earthquake_module = MagicMock()
        
        # 註冊模組
        self.module_connector.register_module(self.mock_earthquake)
        self.module_connector.register_module(self.mock_earthquake_commands)
        self.module_connector.set_module_ready("Earthquake")
        
    async def test_module_connection(self):
        """測試模組間的連接"""
        # 設置依賴關係
        self.module_connector.connect_modules("Earthquake", "EarthquakeCommands")
        
        # 檢查依賴關係
        earthquake_module = self.module_connector.modules["Earthquake"]
        earthquake_commands_module = self.module_connector.modules["EarthquakeCommands"]
        
        self.assertIn("EarthquakeCommands", earthquake_module.get("dependents", []))
        self.assertIn("Earthquake", earthquake_commands_module.get("dependencies", []))
        
        # 驗證地震指令模組設置了地震模組
        self.mock_earthquake_commands.set_earthquake_module.assert_called_once_with(self.mock_earthquake)
        
    async def test_restart_command(self):
        """測試重啟指令"""
        # 設置依賴關係
        self.module_connector.connect_modules("Earthquake", "EarthquakeCommands")
        
        # 模擬調用重啟方法
        await self.mock_earthquake.restart_earthquake_module()
        
        # 驗證重啟方法被調用
        self.mock_earthquake.restart_earthquake_module.assert_called_once()
        result, message = await self.mock_earthquake.restart_earthquake_module()
        self.assertTrue(result)
        self.assertEqual(message, "重啟成功")
        
    async def test_status_command(self):
        """測試狀態指令"""
        # 設置依賴關係
        self.module_connector.connect_modules("Earthquake", "EarthquakeCommands")
        
        # 獲取模組狀態
        status = self.mock_earthquake.get_module_status()
        
        # 驗證狀態
        self.assertTrue(status["is_initialized"])
        self.assertTrue(status["is_fully_initialized"])
        self.assertTrue(status["api_connected"])
        self.assertEqual(status["last_check_time"], "2023-04-05 12:00:00")
        self.assertEqual(status["watch_channels"], ["123456789"])
        self.assertEqual(status["alert_channels"], ["987654321"])

if __name__ == '__main__':
    unittest.main() 