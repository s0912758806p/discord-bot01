"""
pytest配置文件
提供pytest測試所需的共用功能和fixtures
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path

# 確保項目根目錄在路徑中
PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 導入測試配置
from tests.test_config import setup_test_environment

@pytest.fixture(scope="session", autouse=True)
def setup_env():
    """設置測試環境"""
    return setup_test_environment()

@pytest.fixture
def mock_bot():
    """創建模擬的Discord機器人"""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.is_ready = MagicMock(return_value=True)
    bot.add_cog = MagicMock()
    bot.get_cog = MagicMock()
    bot.cogs = {}
    return bot

@pytest.fixture
def mock_channel():
    """創建模擬的Discord頻道"""
    channel = MagicMock()
    channel.id = "123456789"
    channel.send = AsyncMock()
    return channel

@pytest.fixture
def mock_message():
    """創建模擬的Discord訊息"""
    message = MagicMock()
    message.content = "!test"
    message.author = MagicMock()
    message.author.id = "123456789"
    message.author.bot = False
    
    mock_channel = MagicMock()
    mock_channel.id = "123456789"
    mock_channel.send = AsyncMock()
    message.channel = mock_channel
    
    message.add_reaction = AsyncMock()
    message.delete = AsyncMock()
    return message

@pytest.fixture
def test_data_dir():
    """獲取測試數據目錄"""
    return os.path.join(os.path.dirname(__file__), 'test_data')

@pytest.fixture
def load_json_test_data():
    """加載JSON測試數據的工具函數"""
    def _load(filename):
        import json
        data_path = os.path.join(os.path.dirname(__file__), 'test_data', filename)
        with open(data_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return _load 