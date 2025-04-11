"""
測試配置文件 - 為所有測試提供共用的配置和工具函數
"""
import os
import sys
import json
import logging
import tempfile
from typing import Dict, Any, Optional
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# 添加項目根目錄到Python路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 設置日誌記錄
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('discord_bot_tests')

# 測試數據目錄
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), 'test_data')

def setup_test_environment() -> None:
    """設置測試環境，包括必要的環境變數和目錄"""
    # 確保測試數據目錄存在
    if not os.path.exists(TEST_DATA_DIR):
        os.makedirs(TEST_DATA_DIR)
    
    # 設置測試環境變數
    os.environ['TESTING'] = 'true'
    os.environ['VM_ENVIRONMENT'] = 'true'
    os.environ['DISCORD_HTTP_TIMEOUT'] = '10'
    
    logger.info("測試環境設置完成")

def create_mock_bot():
    """創建模擬的 Discord Bot 實例
    
    Returns:
        MagicMock: 模擬的機器人實例
    """
    mock_bot = MagicMock()
    mock_bot.is_ready.return_value = True
    mock_bot.wait_until_ready = AsyncMock()
    mock_bot.add_cog = MagicMock()
    mock_bot.get_cog = MagicMock()
    mock_bot.cogs = {}
    return mock_bot

def create_temp_config_file(config: Dict[str, Any]) -> str:
    """創建臨時配置文件並返回其路徑"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp:
        json.dump(config, temp)
        return temp.name

def load_test_data(filename: str) -> Dict[str, Any]:
    """從測試數據目錄加載JSON測試數據"""
    file_path = os.path.join(TEST_DATA_DIR, filename)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"測試數據文件 {filename} 不存在")
        return {}
    except json.JSONDecodeError:
        logger.error(f"測試數據文件 {filename} 不是有效的JSON")
        return {}

def create_test_data_file(filename: str, data: Dict[str, Any]) -> str:
    """創建測試數據文件
    
    Args:
        filename (str): 文件名稱
        data (dict): 要寫入的數據
        
    Returns:
        str: 文件的完整路徑
    """
    file_path = os.path.join(TEST_DATA_DIR, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        if isinstance(data, dict) or isinstance(data, list):
            json.dump(data, f, indent=4)
        else:
            f.write(str(data))
    return file_path

def get_project_path(subpath: Optional[str] = None) -> str:
    """獲取項目中特定路徑的絕對路徑"""
    if subpath:
        return os.path.join(PROJECT_ROOT, subpath)
    return PROJECT_ROOT

def clean_temp_files() -> None:
    """清理測試過程中創建的臨時文件"""
    temp_dir = tempfile.gettempdir()
    for file in os.listdir(temp_dir):
        if file.endswith('.json') and 'test_' in file:
            try:
                os.remove(os.path.join(temp_dir, file))
            except (OSError, PermissionError):
                pass  # 忽略無法刪除的文件 