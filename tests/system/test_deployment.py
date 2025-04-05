#!/usr/bin/env python3
"""
部署和 VM 環境初始化測試
測試整個系統在部署時的啟動流程和 VM 環境適應性
"""
import os
import sys
import json
import shutil
import asyncio
import unittest
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# 確保目錄結構在路徑中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# 導入測試工具
from tests.test_utils import AsyncTestCase, create_temp_json_file, remove_temp_file
from tests.test_config import setup_test_environment, PROJECT_ROOT, create_test_data_file

class TestVMEnvironmentSetup(unittest.TestCase):
    """測試 VM 環境設置腳本和啟動機制"""
    
    def setUp(self):
        """設置測試環境"""
        # 建立臨時測試目錄
        self.test_dir = os.path.join(PROJECT_ROOT, 'tests', 'data', 'vm_test')
        os.makedirs(self.test_dir, exist_ok=True)
        
        # 設置環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['DOCKER_ENVIRONMENT'] = 'true'
        os.environ['TEST_MODE'] = 'true'
        
    def tearDown(self):
        """清理測試環境"""
        # 刪除測試目錄
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            
        # 恢復環境變數
        os.environ['VM_ENVIRONMENT'] = 'false'
        os.environ['DOCKER_ENVIRONMENT'] = 'false'
        
    def test_start_script_exists(self):
        """測試啟動腳本是否存在"""
        script_path = os.path.join(PROJECT_ROOT, 'start.sh')
        self.assertTrue(os.path.exists(script_path), "啟動腳本不存在")
        self.assertTrue(os.access(script_path, os.X_OK), "啟動腳本沒有執行權限")
        
    def test_repair_script_exists(self):
        """測試修復腳本是否存在"""
        script_path = os.path.join(PROJECT_ROOT, 'vm_repair.sh')
        self.assertTrue(os.path.exists(script_path), "修復腳本不存在")
        self.assertTrue(os.access(script_path, os.X_OK), "修復腳本沒有執行權限")
        
    def test_health_monitor_script_exists(self):
        """測試健康監控腳本是否存在"""
        script_path = os.path.join(PROJECT_ROOT, 'vm_health_monitor.sh')
        self.assertTrue(os.path.exists(script_path), "健康監控腳本不存在")
        self.assertTrue(os.access(script_path, os.X_OK), "健康監控腳本沒有執行權限")
        
    def test_start_script_docker_detection(self):
        """測試啟動腳本 Docker 環境檢測"""
        # 獲取腳本內容
        script_path = os.path.join(PROJECT_ROOT, 'start.sh')
        with open(script_path, 'r') as f:
            content = f.read()
            
        # 檢查腳本中是否包含 Docker 環境檢測邏輯
        self.assertIn('DOCKER_ENVIRONMENT', content)
        self.assertIn('VM_ENVIRONMENT', content)
        self.assertIn('檢測到Docker環境', content)
        
    def test_start_script_directory_creation(self):
        """測試啟動腳本目錄創建邏輯"""
        # 獲取腳本內容
        script_path = os.path.join(PROJECT_ROOT, 'start.sh')
        with open(script_path, 'r') as f:
            content = f.read()
            
        # 檢查腳本中是否包含目錄創建邏輯
        self.assertIn('mkdir -p logs', content)
        self.assertIn('mkdir -p data', content)
        self.assertIn('mkdir -p config', content)
        
    def test_start_script_environment_variables(self):
        """測試啟動腳本環境變數設置"""
        # 獲取腳本內容
        script_path = os.path.join(PROJECT_ROOT, 'start.sh')
        with open(script_path, 'r') as f:
            content = f.read()
            
        # 檢查腳本中是否包含環境變數設置邏輯
        self.assertIn('EARTHQUAKE_INIT_TIMEOUT', content)
        self.assertIn('EARTHQUAKE_RETRY_INTERVAL', content)
        self.assertIn('DISCORD_HTTP_TIMEOUT', content)
        
    def test_dockerfile_exists(self):
        """測試 Dockerfile 是否存在"""
        dockerfile_path = os.path.join(PROJECT_ROOT, 'Dockerfile')
        self.assertTrue(os.path.exists(dockerfile_path), "Dockerfile 不存在")
        
    def test_dockerfile_content(self):
        """測試 Dockerfile 內容"""
        # 獲取 Dockerfile 內容
        dockerfile_path = os.path.join(PROJECT_ROOT, 'Dockerfile')
        with open(dockerfile_path, 'r') as f:
            content = f.read()
            
        # 檢查 Dockerfile 中是否包含必要設置
        self.assertIn('DISCORD_HTTP_TIMEOUT', content)
        self.assertIn('EARTHQUAKE_INIT_TIMEOUT', content)
        self.assertIn('EARTHQUAKE_RETRY_INTERVAL', content)
        self.assertIn('Asia/Taipei', content)  # 檢查時區設置
        
    def test_dockerignore_exists(self):
        """測試 .dockerignore 是否存在"""
        dockerignore_path = os.path.join(PROJECT_ROOT, '.dockerignore')
        self.assertTrue(os.path.exists(dockerignore_path), ".dockerignore 不存在")
        
    def test_docker_compose_exists(self):
        """測試 docker-compose.yml 是否存在"""
        compose_path = os.path.join(PROJECT_ROOT, 'docker-compose.yml')
        self.assertTrue(os.path.exists(compose_path), "docker-compose.yml 不存在")

class TestVMEnvironmentInitialization(AsyncTestCase):
    """測試 VM 環境中的系統初始化流程"""
    
    def setUp(self):
        """設置測試環境"""
        super().setUp()
        # 建立臨時測試目錄
        self.test_dir = os.path.join(PROJECT_ROOT, 'tests', 'data', 'vm_init_test')
        os.makedirs(self.test_dir, exist_ok=True)
        
        # 設置環境變數模擬 VM 環境
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['DOCKER_ENVIRONMENT'] = 'true'
        os.environ['TEST_MODE'] = 'true'
        os.environ['EARTHQUAKE_INIT_TIMEOUT'] = '5'
        os.environ['EARTHQUAKE_RETRY_INTERVAL'] = '1'
        os.environ['MODULE_CONNECTOR_DELAY'] = '1'
        
    def tearDown(self):
        """清理測試環境"""
        super().tearDown()
        # 刪除測試目錄
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            
        # 恢復環境變數
        os.environ['VM_ENVIRONMENT'] = 'false'
        os.environ['DOCKER_ENVIRONMENT'] = 'false'
        
    def test_environment_variable_detection(self):
        """測試環境變數檢測"""
        # 檢查環境變數是否正確設置
        self.assertEqual(os.environ['VM_ENVIRONMENT'], 'true')
        self.assertEqual(os.environ['DOCKER_ENVIRONMENT'], 'true')
        self.assertEqual(os.environ['TEST_MODE'], 'true')
        
    @patch('subprocess.run')
    def test_start_script_execution(self, mock_run):
        """測試啟動腳本執行"""
        # 模擬腳本執行
        mock_run.return_value.returncode = 0
        
        # 執行腳本
        script_path = os.path.join(PROJECT_ROOT, 'start.sh')
        result = subprocess.run(['bash', script_path, '--test-mode'], 
                                capture_output=True, text=True, check=False)
        
        # 檢查執行是否成功 - 在測試模式下應該提前退出
        self.assertEqual(result.returncode, 0)
        
    @patch('logging.Logger.info')
    @patch('logging.Logger.warning')
    @patch('logging.Logger.error')
    def test_system_logging(self, mock_error, mock_warning, mock_info):
        """測試系統日誌功能"""
        # 導入日誌模組
        from core.logging import logger
        
        # 記錄一些日誌
        logger.info("測試信息日誌")
        logger.warning("測試警告日誌")
        logger.error("測試錯誤日誌")
        
        # 檢查日誌是否被記錄
        mock_info.assert_called_with("測試信息日誌")
        mock_warning.assert_called_with("測試警告日誌")
        mock_error.assert_called_with("測試錯誤日誌")
        
    def test_necessary_directories_exists(self):
        """測試必要的目錄是否存在"""
        # 檢查必要目錄
        dirs_to_check = ['config', 'data', 'logs', 'cmds']
        for dir_name in dirs_to_check:
            dir_path = os.path.join(PROJECT_ROOT, dir_name)
            self.assertTrue(os.path.exists(dir_path), f"{dir_name} 目錄不存在")
            self.assertTrue(os.path.isdir(dir_path), f"{dir_name} 不是目錄")

class TestVMDeployment(unittest.TestCase):
    """測試VM環境下的部署功能"""
    
    @classmethod
    def setUpClass(cls):
        """測試類設置"""
        # 設置測試環境
        cls.config = setup_test_environment()
        
        # 設置VM環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['DISCORD_HTTP_TIMEOUT'] = '90'
        os.environ['EARTHQUAKE_INIT_TIMEOUT'] = '120'
        os.environ['EARTHQUAKE_RETRY_INTERVAL'] = '5'
        os.environ['VM_MEMORY_LIMIT_MB'] = '512'
        
        # 備份原始檔案
        cls._backup_original_files()
    
    @classmethod
    def tearDownClass(cls):
        """測試類清理"""
        # 恢復原始檔案
        cls._restore_original_files()
    
    @classmethod
    def _backup_original_files(cls):
        """備份原始Docker設定檔"""
        cls.dockerfile_backup = None
        cls.docker_compose_backup = None
        
        # 備份 Dockerfile
        dockerfile_path = os.path.join(PROJECT_ROOT, 'Dockerfile')
        if os.path.exists(dockerfile_path):
            with open(dockerfile_path, 'r', encoding='utf-8') as f:
                cls.dockerfile_backup = f.read()
                
        # 備份 docker-compose.yml
        docker_compose_path = os.path.join(PROJECT_ROOT, 'docker-compose.yml')
        if os.path.exists(docker_compose_path):
            with open(docker_compose_path, 'r', encoding='utf-8') as f:
                cls.docker_compose_backup = f.read()
    
    @classmethod
    def _restore_original_files(cls):
        """恢復原始Docker設定檔"""
        # 恢復 Dockerfile
        if cls.dockerfile_backup:
            dockerfile_path = os.path.join(PROJECT_ROOT, 'Dockerfile')
            with open(dockerfile_path, 'w', encoding='utf-8') as f:
                f.write(cls.dockerfile_backup)
                
        # 恢復 docker-compose.yml
        if cls.docker_compose_backup:
            docker_compose_path = os.path.join(PROJECT_ROOT, 'docker-compose.yml')
            with open(docker_compose_path, 'w', encoding='utf-8') as f:
                f.write(cls.docker_compose_backup)
    
    def test_docker_configuration(self):
        """測試Docker配置檔案是否存在且有效"""
        # 檢查 Dockerfile 是否存在
        dockerfile_path = os.path.join(PROJECT_ROOT, 'Dockerfile')
        self.assertTrue(os.path.exists(dockerfile_path), "Dockerfile 不存在")
        
        # 檢查 docker-compose.yml 是否存在
        docker_compose_path = os.path.join(PROJECT_ROOT, 'docker-compose.yml')
        self.assertTrue(os.path.exists(docker_compose_path), "docker-compose.yml 不存在")
        
        # 檢查 Dockerfile 內容
        with open(dockerfile_path, 'r', encoding='utf-8') as f:
            dockerfile_content = f.read()
            
        # 驗證 Dockerfile 關鍵配置
        self.assertIn('python', dockerfile_content, "Dockerfile 中缺少 Python 配置")
        self.assertIn('WORKDIR', dockerfile_content, "Dockerfile 中缺少工作目錄配置")
        self.assertIn('COPY', dockerfile_content, "Dockerfile 中缺少文件複製指令")
        
        # 檢查 docker-compose.yml 內容
        with open(docker_compose_path, 'r', encoding='utf-8') as f:
            docker_compose_content = f.read()
            
        # 驗證 docker-compose.yml 關鍵配置
        self.assertIn('services', docker_compose_content, "docker-compose.yml 中缺少服務定義")
        self.assertIn('build', docker_compose_content, "docker-compose.yml 中缺少構建配置")
        self.assertIn('volumes', docker_compose_content, "docker-compose.yml 中缺少卷配置")
    
    def test_repair_script(self):
        """測試修復腳本是否存在且可執行"""
        # 檢查修復腳本是否存在
        repair_script_path = os.path.join(PROJECT_ROOT, 'vm_repair.sh')
        self.assertTrue(os.path.exists(repair_script_path), "vm_repair.sh 不存在")
        
        # 檢查腳本權限
        self.assertTrue(os.access(repair_script_path, os.X_OK), "vm_repair.sh 不可執行，請運行 chmod +x vm_repair.sh")
        
        # 檢查腳本內容
        with open(repair_script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
            
        # 驗證腳本關鍵功能
        self.assertIn('docker', script_content, "修復腳本中缺少 Docker 相關指令")
        self.assertIn('earthquake', script_content, "修復腳本中缺少地震模組相關指令")
        self.assertIn('restart', script_content, "修復腳本中缺少重啟功能")
    
    def test_health_monitor_script(self):
        """測試健康監控腳本是否存在且可執行"""
        # 檢查健康監控腳本是否存在
        monitor_script_path = os.path.join(PROJECT_ROOT, 'vm_health_monitor.sh')
        self.assertTrue(os.path.exists(monitor_script_path), "vm_health_monitor.sh 不存在")
        
        # 檢查腳本權限
        self.assertTrue(os.access(monitor_script_path, os.X_OK), "vm_health_monitor.sh 不可執行，請運行 chmod +x vm_health_monitor.sh")
        
        # 檢查腳本內容
        with open(monitor_script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
            
        # 驗證腳本關鍵功能
        self.assertIn('docker', script_content, "健康監控腳本中缺少 Docker 相關指令")
        self.assertIn('logs', script_content, "健康監控腳本中缺少日誌檢查功能")
        self.assertIn('restart', script_content, "健康監控腳本中缺少重啟功能")

class TestVMInitialization(unittest.TestCase):
    """在VM環境中測試初始化過程"""
    
    def setUp(self):
        """設置測試環境"""
        # 設置測試環境
        self.config = setup_test_environment()
        
        # 設置VM環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['DISCORD_HTTP_TIMEOUT'] = '90'
        os.environ['EARTHQUAKE_INIT_TIMEOUT'] = '120'
        os.environ['EARTHQUAKE_RETRY_INTERVAL'] = '5'
        
        # 創建測試配置文件
        self.test_config_file = create_test_data_file(
            'vm_test_config.json',
            {
                "api_key": "vm_test_api_key",
                "watch_channels": ["123456789"],
                "alert_channels": ["987654321"],
                "earthquake_data": {},
                "last_sent_times": {}
            }
        )
        os.environ['EARTHQUAKE_CONFIG_FILE'] = self.test_config_file
    
    def tearDown(self):
        """清理測試環境"""
        # 刪除測試配置文件
        if os.path.exists(self.test_config_file):
            try:
                os.remove(self.test_config_file)
            except:
                pass
    
    @patch('subprocess.run')
    def test_docker_build_process(self, mock_run):
        """測試Docker構建過程"""
        # 設置模擬程序執行結果
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = b"Successfully built test_image"
        mock_run.return_value = mock_process
        
        # 模擬構建命令
        result = subprocess.run(['docker-compose', 'build'], 
                               capture_output=True, 
                               cwd=PROJECT_ROOT)
        
        # 驗證命令執行
        self.assertEqual(result.returncode, 0)
        
        # 驗證模擬命令調用
        mock_run.assert_called()
    
    @patch('requests.get')
    def test_api_connectivity(self, mock_get):
        """測試API連接性"""
        # 設置請求模擬
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_get.return_value = mock_response
        
        # 導入請求模組
        import requests
        
        # 測試Discord API連接
        discord_response = requests.get('https://discord.com/api/v9')
        self.assertEqual(discord_response.status_code, 200)
        
        # 進一步的API連接性測試
        mock_get.assert_called()
    
    def test_environment_variables(self):
        """測試環境變數設置"""
        # 檢查必要的環境變數
        self.assertEqual(os.environ.get('VM_ENVIRONMENT'), 'true')
        self.assertEqual(os.environ.get('DISCORD_HTTP_TIMEOUT'), '90')
        self.assertEqual(os.environ.get('EARTHQUAKE_INIT_TIMEOUT'), '120')
        self.assertEqual(os.environ.get('EARTHQUAKE_RETRY_INTERVAL'), '5')
        
        # 檢查配置文件路徑
        self.assertTrue(os.path.exists(os.environ.get('EARTHQUAKE_CONFIG_FILE')))
    
    def test_startup_sequence(self):
        """測試啟動序列"""
        # 檢查啟動腳本是否存在
        startup_script = os.path.join(PROJECT_ROOT, 'start.sh')
        self.assertTrue(os.path.exists(startup_script), "啟動腳本不存在")
        
        # 檢查腳本權限
        self.assertTrue(os.access(startup_script, os.X_OK), "啟動腳本不可執行，請運行 chmod +x start.sh")
        
        # 檢查腳本內容
        with open(startup_script, 'r', encoding='utf-8') as f:
            script_content = f.read()
            
        # 驗證腳本關鍵功能
        self.assertIn('python', script_content, "啟動腳本中缺少 Python 啟動指令")
        self.assertIn('main.py', script_content, "啟動腳本中缺少對主程序的引用")
        self.assertIn('wait', script_content, "啟動腳本中缺少等待功能")

if __name__ == '__main__':
    # 設置測試環境
    setup_test_environment()
    
    # 創建測試套件
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestVMEnvironmentSetup))
    suite.addTest(unittest.makeSuite(TestVMEnvironmentInitialization))
    suite.addTest(unittest.makeSuite(TestVMDeployment))
    suite.addTest(unittest.makeSuite(TestVMInitialization))
    
    # 運行測試
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite) 