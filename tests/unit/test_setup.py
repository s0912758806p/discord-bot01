#!/usr/bin/env python3
"""
測試基本初始化功能
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# 添加專案根目錄到 Python 路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

# 導入測試配置
from tests.test_config import setup_test_environment, create_mock_bot

class TestBotInitialization(unittest.TestCase):
    """測試機器人初始化功能"""
    
    def setUp(self):
        """設置測試環境"""
        # 設置測試環境和測試數據
        self.config = setup_test_environment()
        
        # 設置環境變數
        os.environ['BOT_TOKEN'] = 'test_token'
        os.environ['VM_ENVIRONMENT'] = 'false'
        
        # 創建 mock bot 實例
        self.mock_bot = create_mock_bot()
        # 手動設置 login 和 connect 方法
        self.mock_bot.login = MagicMock()
        self.mock_bot.connect = MagicMock()
        
    def test_environment_variables(self):
        """測試環境變數設置"""
        # 驗證環境變數設置
        self.assertEqual(os.environ.get('BOT_TOKEN'), 'test_token')
        self.assertEqual(os.environ.get('VM_ENVIRONMENT'), 'false')
        
    def test_bot_login(self):
        """測試機器人登入"""
        # 調用登入方法
        from main import login_bot
        login_bot(token='test_token', bot=self.mock_bot)
        
        # 驗證登入嘗試
        self.mock_bot.login.assert_called_once_with('test_token')
        
    def test_bot_connect(self):
        """測試機器人連接"""
        # 調用連接方法
        from main import run_bot
        run_bot(bot=self.mock_bot)
        
        # 驗證連接嘗試
        self.mock_bot.connect.assert_called_once()

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
        self.mock_bot.load_extension('cmds.earthquake')
        
        # 驗證結果
        self.mock_bot.load_extension.assert_called_once_with('cmds.earthquake')
        
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