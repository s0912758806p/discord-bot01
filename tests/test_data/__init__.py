"""
測試數據包初始化文件
包含測試使用的各種測試數據和模擬響應
"""

import os
import json
from pathlib import Path

# 測試數據目錄
TEST_DATA_DIR = Path(__file__).parent.absolute()

def get_data_file_path(filename):
    """
    獲取測試數據文件的完整路徑
    
    Args:
        filename (str): 要獲取的文件名
        
    Returns:
        str: 文件的完整路徑
    """
    return os.path.join(TEST_DATA_DIR, filename)

def load_json_data(filename):
    """
    載入JSON測試數據
    
    Args:
        filename (str): JSON文件名
        
    Returns:
        dict: 載入的JSON數據
    """
    file_path = get_data_file_path(filename)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {} 