"""
測試虛擬機環境相關功能
這些測試檢查系統在VM環境中的行為
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock, call
import subprocess
import asyncio

# 添加項目根目錄到Python路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 導入測試工具
from tests.test_config import setup_test_environment, create_mock_bot

class TestVMEnvironment(unittest.TestCase):
    """測試VM環境特定功能"""
    
    def setUp(self):
        """設置測試環境"""
        setup_test_environment()
        
        # 設置VM相關環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['DISCORD_HTTP_TIMEOUT'] = '10'
        
        # 創建模擬機器人
        self.mock_bot = create_mock_bot()
    
    @patch('subprocess.run')
    def test_system_health_check(self, mock_run):
        """測試系統健康檢查功能"""
        # 模擬執行系統命令的回傳
        mock_run.return_value = MagicMock(
            stdout=b"Memory: 50%\nCPU: 30%\nDisk: 60%\n",
            stderr=b"",
            returncode=0
        )
        
        # 導入模塊 (這裡只進行導入測試)
        try:
            from utils.system_health import check_system_health
            # 執行健康檢查
            health_status = check_system_health()
            
            # 驗證是否調用了系統命令
            mock_run.assert_called()
            
            # 檢查健康狀態結果
            self.assertIn('memory', health_status)
            self.assertIn('cpu', health_status)
            self.assertIn('disk', health_status)
        except ImportError:
            self.skipTest("system_health 模組不存在，跳過測試")
    
    @patch('subprocess.Popen')
    def test_error_detection(self, mock_popen):
        """測試錯誤檢測功能"""
        # 模擬進程輸出
        mock_process = MagicMock()
        mock_process.stdout = b"[ERROR] Database connection failed\n[ACTION] Retrying"
        mock_process.poll.return_value = 0
        mock_popen.return_value = mock_process
        
        # 導入並測試錯誤檢測功能
        try:
            from utils.error_detector import detect_critical_errors
            errors = detect_critical_errors(['database', 'connection'])
            
            # 驗證是否檢測到錯誤
            self.assertTrue(errors)
            self.assertEqual(len(errors), 1)
            self.assertIn('Database connection failed', errors[0])
        except ImportError:
            self.skipTest("error_detector 模組不存在，跳過測試")
            
    @patch('os.path.exists')
    @patch('builtins.open')
    def test_config_management(self, mock_open, mock_exists):
        """測試配置文件管理"""
        # 模擬文件存在和讀寫
        mock_exists.return_value = True
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        
        # 導入並測試配置管理功能
        try:
            from utils.config_manager import load_config, save_config
            
            # 執行測試
            config = load_config('test_config.json')
            self.assertIsNotNone(config)
            
            save_config('test_config.json', {'test': 'data'})
            mock_file.write.assert_called_once()
        except ImportError:
            self.skipTest("config_manager 模組不存在，跳過測試")

if __name__ == '__main__':
    unittest.main() 