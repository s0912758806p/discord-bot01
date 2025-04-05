"""
測試模組間的整合功能
這個測試檢查不同模組之間是否能正確協作
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
from tests.test_config import setup_test_environment, create_mock_bot
from tests.test_data import load_json_data

# 導入被測試的模組
with patch('discord.ext.commands.Bot'):
    from cmds.module_connector import ModuleConnector

class TestModuleCommunication(unittest.IsolatedAsyncioTestCase):
    """測試模組間通信功能"""
    
    async def asyncSetUp(self):
        """設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
        # 創建模擬的 Discord 機器人
        self.mock_bot = create_mock_bot()
        self.mock_bot.wait_until_ready = AsyncMock()
        
        # 載入測試配置
        self.test_configs = load_json_data('module_configs.json')
        
        # 創建模組連接器
        self.module_connector = ModuleConnector(self.mock_bot)
        
        # 創建模擬的模組
        self.mock_module1 = MagicMock()
        self.mock_module1.name = "Module1"
        self.mock_module1.get_status = MagicMock(return_value={"ready": True})
        
        self.mock_module2 = MagicMock()
        self.mock_module2.name = "Module2"
        self.mock_module2.process_data = MagicMock()
        self.mock_module2.get_status = MagicMock(return_value={"ready": False})
        
    async def test_module_registration(self):
        """測試模組註冊功能"""
        # 註冊模擬模組
        self.module_connector.register_module(self.mock_module1)
        self.module_connector.register_module(self.mock_module2)
        
        # 檢查模組是否成功註冊
        self.assertIn("Module1", self.module_connector.modules)
        self.assertIn("Module2", self.module_connector.modules)
        
    async def test_module_dependency(self):
        """測試模組依賴關係"""
        # 註冊模擬模組
        self.module_connector.register_module(self.mock_module1)
        self.module_connector.register_module(self.mock_module2)
        
        # 設置依賴關係
        self.module_connector.connect_modules("Module1", "Module2")
        
        # 檢查依賴關係
        module1_data = self.module_connector.modules["Module1"]
        module2_data = self.module_connector.modules["Module2"]
        
        self.assertIn("Module2", module1_data.get("dependents", []))
        self.assertIn("Module1", module2_data.get("dependencies", []))
        
    async def test_module_readiness_propagation(self):
        """測試模組準備狀態傳播"""
        # 註冊模擬模組
        self.module_connector.register_module(self.mock_module1)
        self.module_connector.register_module(self.mock_module2)
        
        # 設置依賴關係
        self.module_connector.connect_modules("Module1", "Module2")
        
        # 設置第一個模組為準備好狀態
        self.module_connector.set_module_ready("Module1")
        
        # 檢查第一個模組的狀態
        self.assertTrue(self.module_connector.modules["Module1"]["ready"])
        
        # 檢查第二個模組的依賴是否滿足
        dependencies_ready = all(
            self.module_connector.modules.get(dep, {}).get("ready", False)
            for dep in self.module_connector.modules["Module2"].get("dependencies", [])
        )
        self.assertTrue(dependencies_ready)

class TestEarthquakeIntegration(unittest.IsolatedAsyncioTestCase):
    """測試地震模組的整合功能"""
    
    async def asyncSetUp(self):
        """設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
        # 創建模擬的 Discord 機器人
        self.mock_bot = create_mock_bot()
        
        # 載入測試配置
        self.test_configs = load_json_data('module_configs.json')
        
        # 創建模擬的地震模組
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
        
        # 創建模擬的地震指令模組
        self.mock_commands = MagicMock()
        self.mock_commands.name = "EarthquakeCommands"
        self.mock_commands.set_earthquake_module = MagicMock()
        
        # 創建模組連接器並註冊模組
        self.module_connector = ModuleConnector(self.mock_bot)
        self.module_connector.register_module(self.mock_earthquake)
        self.module_connector.register_module(self.mock_commands)
        
    async def test_earthquake_commands_connection(self):
        """測試地震指令模組與地震模組的連接"""
        # 建立連接
        self.module_connector.connect_modules("Earthquake", "EarthquakeCommands")
        
        # 檢查地震指令模組是否設置了地震模組引用
        self.mock_commands.set_earthquake_module.assert_called_once_with(self.mock_earthquake)
        
    async def test_earthquake_restart(self):
        """測試地震模組重啟功能"""
        # 模擬透過指令模組重啟地震模組
        result, message = await self.mock_earthquake.restart_earthquake_module()
        
        # 檢查結果
        self.assertTrue(result)
        self.assertEqual(message, "重啟成功")
        self.mock_earthquake.restart_earthquake_module.assert_called_once()
        
    async def test_module_status_check(self):
        """測試模組狀態檢查功能"""
        # 獲取模組狀態
        status = self.mock_earthquake.get_module_status()
        
        # 檢查狀態信息
        self.assertTrue(status["is_initialized"])
        self.assertTrue(status["is_fully_initialized"])
        self.assertTrue(status["api_connected"])
        self.assertEqual(status["last_check_time"], "2023-04-05 12:00:00")
        self.assertEqual(status["watch_channels"], ["123456789"])
        self.assertEqual(status["alert_channels"], ["987654321"])

if __name__ == '__main__':
    unittest.main() 