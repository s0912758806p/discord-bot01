"""
測試工具模塊，提供測試所需的通用功能
"""
import os
import sys
import json
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Awaitable

# 添加專案根目錄到Python路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 測試數據目錄
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), 'test_data')

class AsyncTestCase(unittest.TestCase):
    """用於測試異步代碼的測試用例基類"""
    
    def setUp(self):
        """設置測試環境"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
    def tearDown(self):
        """清理測試環境"""
        self.loop.close()
        asyncio.set_event_loop(None)
        
    def run_async(self, coro):
        """運行異步協程並返回結果"""
        return self.loop.run_until_complete(coro)
        
    def create_mock_channel(self, channel_id="123456789"):
        """創建模擬的Discord頻道"""
        channel = MagicMock()
        channel.id = channel_id
        channel.send = AsyncMock()
        return channel
        
    def create_mock_guild(self, guild_id="987654321"):
        """創建模擬的Discord伺服器"""
        guild = MagicMock()
        guild.id = guild_id
        guild.name = "Test Guild"
        return guild
        
    def create_mock_message(self, content="test message", author_id="123456789"):
        """創建模擬的Discord消息"""
        message = MagicMock()
        message.content = content
        
        author = MagicMock()
        author.id = author_id
        author.name = "Test User"
        message.author = author
        
        message.add_reaction = AsyncMock()
        message.delete = AsyncMock()
        return message

class MockData:
    """用於生成測試數據的類"""
    
    @staticmethod
    def generate_config_data():
        """生成模擬配置數據"""
        return {
            "api_key": "test_api_key",
            "watch_channels": ["123456789", "234567890"],
            "alert_channels": ["345678901", "456789012"],
            "min_magnitude": 4.0,
            "check_interval": 60
        }

def create_temp_file(file_path, content=""):
    """創建臨時文件"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return file_path

def create_temp_json_file(file_path, data):
    """創建臨時 JSON 文件"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    return file_path

def remove_temp_file(file_path):
    """刪除臨時文件"""
    if os.path.exists(file_path):
        os.remove(file_path)

def compare_json_files(file1, file2):
    """比較兩個 JSON 文件的內容"""
    if not os.path.exists(file1) or not os.path.exists(file2):
        return False
    
    try:
        with open(file1, 'r', encoding='utf-8') as f1, open(file2, 'r', encoding='utf-8') as f2:
            data1 = json.load(f1)
            data2 = json.load(f2)
            return data1 == data2
    except:
        return False 