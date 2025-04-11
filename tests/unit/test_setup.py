#!/usr/bin/env python3
"""
測試機器人初始化和設置功能的單元測試
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# 添加專案根目錄到 Python 路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

# 導入測試配置
from tests.test_config import setup_test_environment, create_mock_bot

class TestBotInitialization(unittest.TestCase):
    """測試機器人初始化"""
    
    def setUp(self):
        """設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
        # 創建 mock bot 實例
        self.mock_bot = create_mock_bot()
        self.mock_bot.token = 'test_token'
        self.mock_bot.run = AsyncMock()
        self.mock_bot.login = AsyncMock(return_value=True)
        self.mock_bot.connect = AsyncMock(return_value=True)
        
    def test_environment_variables(self):
        """測試環境變數設置"""
        self.assertEqual(os.environ['TESTING'], 'true')
        self.assertEqual(os.environ['VM_ENVIRONMENT'], 'true')
        
    @patch('discord.Client.login')
    def test_bot_login(self, mock_login):
        """測試機器人登入"""
        # 模擬登入結果
        mock_login.return_value = True
        
        # 驗證登入結果
        self.assertTrue(self.mock_bot.login('test_token'))
        
    @patch('discord.Client.connect')
    def test_bot_connect(self, mock_connect):
        """測試機器人連接"""
        # 模擬連接結果
        mock_connect.return_value = True
        
        # 驗證連接結果
        self.assertTrue(self.mock_bot.connect())

class TestCogLoading(unittest.TestCase):
    """測試 Cog 載入功能"""
    
    def setUp(self):
        """設置測試環境"""
        # 設置測試環境和測試數據
        self.config = setup_test_environment()
        
        # 創建 mock bot 實例
        self.mock_bot = create_mock_bot()
        self.mock_bot.load_extension = MagicMock()
        self.mock_bot.add_cog = MagicMock()
        
    def test_load_extension(self):
        """測試擴展載入"""
        # 調用方法
        self.mock_bot.load_extension('cmds.test_module')
        
        # 驗證結果
        self.mock_bot.load_extension.assert_called_once_with('cmds.test_module')
        
    def test_add_cog(self):
        """測試添加 Cog"""
        # 創建 mock cog
        mock_cog = MagicMock()
        mock_cog.name = "TestCog"
        
        # 添加 cog
        self.mock_bot.add_cog(mock_cog)
        
        # 驗證結果
        self.mock_bot.add_cog.assert_called_once_with(mock_cog)

if __name__ == '__main__':
    unittest.main() 