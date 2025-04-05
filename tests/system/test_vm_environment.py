"""
測試VM環境下的運行狀況
檢查在VM資源限制環境中的功能
"""
import os
import sys
import json
import time
import unittest
import subprocess
from unittest.mock import patch, MagicMock

# 添加專案根目錄到 Python 路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

# 導入測試配置
from tests.test_config import setup_test_environment

class TestVMStartupSequence(unittest.TestCase):
    """測試VM環境啟動序列"""
    
    def setUp(self):
        """設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
        # 設置 VM 環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['DISCORD_HTTP_TIMEOUT'] = '90'
        os.environ['EARTHQUAKE_INIT_TIMEOUT'] = '120'
        os.environ['EARTHQUAKE_RETRY_INTERVAL'] = '5'
        
    def test_startup_script_exists(self):
        """測試啟動腳本是否存在"""
        startup_script = os.path.join(PROJECT_ROOT, 'start.sh')
        self.assertTrue(os.path.exists(startup_script), "啟動腳本不存在")
        self.assertTrue(os.access(startup_script, os.X_OK), "啟動腳本沒有執行權限")
    
    @patch('subprocess.run')
    def test_startup_script_execution(self, mock_run):
        """測試啟動腳本執行"""
        # 設置模擬結果
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = b"Discord Bot starting..."
        mock_run.return_value = mock_process
        
        # 執行啟動腳本
        result = subprocess.run(
            ['./start.sh'],
            capture_output=True,
            cwd=PROJECT_ROOT,
            text=True
        )
        
        # 驗證結果
        self.assertEqual(result.returncode, 0)
        mock_run.assert_called()
    
    def test_vm_environment_detection(self):
        """測試VM環境檢測"""
        # 導入環境檢測功能
        from main import is_vm_environment
        
        # 檢查環境檢測結果
        self.assertTrue(is_vm_environment())

class TestVMResourceManagement(unittest.TestCase):
    """測試VM資源管理"""
    
    def setUp(self):
        """設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
        # 設置 VM 環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['VM_MEMORY_LIMIT_MB'] = '512'
        
    @patch('psutil.virtual_memory')
    def test_memory_limit_detection(self, mock_virtual_memory):
        """測試記憶體限制檢測"""
        # 設置模擬的記憶體信息
        mock_memory = MagicMock()
        mock_memory.total = 512 * 1024 * 1024  # 512 MB
        mock_memory.available = 256 * 1024 * 1024  # 256 MB
        mock_memory.percent = 50.0
        mock_virtual_memory.return_value = mock_memory
        
        # 導入並執行記憶體檢測函數
        from main import check_system_resources
        memory_info = check_system_resources()
        
        # 驗證結果
        self.assertEqual(memory_info['total_mb'], 512)
        self.assertEqual(memory_info['available_mb'], 256)
        self.assertEqual(memory_info['usage_percent'], 50.0)
    
    @patch('psutil.cpu_percent')
    def test_cpu_usage_monitoring(self, mock_cpu_percent):
        """測試CPU使用率監控"""
        # 設置模擬的CPU使用率
        mock_cpu_percent.return_value = 30.0
        
        # 導入並執行CPU監控函數
        from main import check_cpu_usage
        cpu_usage = check_cpu_usage()
        
        # 驗證結果
        self.assertEqual(cpu_usage, 30.0)

class TestVMRepairTools(unittest.TestCase):
    """測試VM修復工具"""
    
    def setUp(self):
        """設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
    def test_repair_script_exists(self):
        """測試修復腳本是否存在"""
        repair_script = os.path.join(PROJECT_ROOT, 'vm_repair.sh')
        self.assertTrue(os.path.exists(repair_script), "修復腳本不存在")
        self.assertTrue(os.access(repair_script, os.X_OK), "修復腳本沒有執行權限")
    
    def test_health_monitor_script_exists(self):
        """測試健康監控腳本是否存在"""
        monitor_script = os.path.join(PROJECT_ROOT, 'vm_health_monitor.sh')
        self.assertTrue(os.path.exists(monitor_script), "健康監控腳本不存在")
        self.assertTrue(os.access(monitor_script, os.X_OK), "健康監控腳本沒有執行權限")
    
    @patch('subprocess.run')
    def test_repair_script_error_detection(self, mock_run):
        """測試修復腳本錯誤檢測功能"""
        # 設置模擬結果
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = b"[ERROR] Found 3 errors in earthquake module\n[ACTION] Restarting module"
        mock_run.return_value = mock_process
        
        # 執行修復腳本
        result = subprocess.run(
            ['./vm_repair.sh', '--diagnose-only'],
            capture_output=True,
            cwd=PROJECT_ROOT,
            text=True
        )
        
        # 驗證結果
        self.assertEqual(result.returncode, 0)
        mock_run.assert_called()

if __name__ == '__main__':
    unittest.main() 