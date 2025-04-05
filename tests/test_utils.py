"""
測試工具模組
提供單元測試和整合測試中共用的工具函數和類
"""
import os
import sys
import json
import asyncio
import logging
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

# 添加專案根目錄到 Python 路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

# 設置測試記錄器
logger = logging.getLogger('test_utils')

class AsyncTestCase(unittest.TestCase):
    """用於異步測試的測試用例基類"""
    
    def setUp(self):
        """設置測試環境"""
        # 設置事件循環
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # 設置防止測試超時
        self.MAX_WAIT = 3  # 最大等待秒數
        
    def tearDown(self):
        """清理測試環境"""
        # 關閉事件循環
        self.loop.close()
        
    def run_async(self, coro):
        """運行異步協程並等待結果"""
        return self.loop.run_until_complete(coro)
    
    def create_mock_channel(self, channel_id="123456789"):
        """創建模擬的 Discord 頻道"""
        mock_channel = MagicMock()
        mock_channel.id = channel_id
        mock_channel.send = AsyncMock()
        return mock_channel
    
    def create_mock_guild(self, guild_id="987654321"):
        """創建模擬的 Discord 伺服器"""
        mock_guild = MagicMock()
        mock_guild.id = guild_id
        mock_guild.name = "TestGuild"
        return mock_guild
    
    def create_mock_message(self, content="test message", author_id="123456789"):
        """創建模擬的 Discord 訊息"""
        mock_message = MagicMock()
        mock_message.content = content
        mock_message.author = MagicMock()
        mock_message.author.id = author_id
        mock_message.author.bot = False
        mock_message.channel = self.create_mock_channel()
        mock_message.guild = self.create_mock_guild()
        mock_message.add_reaction = AsyncMock()
        mock_message.delete = AsyncMock()
        return mock_message

class MockData:
    """用於生成測試數據的類"""
    
    @staticmethod
    def generate_earthquake_data(count=5):
        """生成模擬地震數據"""
        now = datetime.now()
        data = []
        
        for i in range(count):
            days_ago = i * 0.5  # 每隔半天一筆資料
            time = (now - timedelta(days=days_ago)).isoformat()
            
            # 產生隨機震級 (3.0 到 6.5 之間)
            magnitude = 3.0 + (i % 7) / 2
            
            data.append({
                "id": f"eq{i+1}",
                "time": time,
                "magnitude": magnitude,
                "depth": 10 + i * 2,
                "location": f"測試位置 {i+1}",
                "description": f"這是第 {i+1} 筆測試地震資料",
                "latitude": 23.5 + (i * 0.1),
                "longitude": 121.0 + (i * 0.1),
                "intensity": i % 6
            })
        
        return data
    
    @staticmethod
    def generate_config_data():
        """生成模擬配置數據"""
        return {
            "api_key": "test_api_key",
            "watch_channels": ["123456789", "234567890"],
            "alert_channels": ["345678901", "456789012"],
            "earthquake_data": {},
            "last_sent_times": {},
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