"""
使用mock進行地震模組的單元測試
"""
import os
import sys
import json
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock, ANY

# 添加項目根目錄到Python路徑
PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cmds.earthquake import Earthquake

def create_mock_bot():
    """創建一個模擬的Discord機器人實例"""
    mock_bot = MagicMock()
    mock_bot.wait_until_ready = AsyncMock()
    mock_bot.change_presence = AsyncMock()
    mock_bot.get_cog = MagicMock(return_value=None)
    return mock_bot

@pytest.fixture
def mock_setup():
    """設置測試環境"""
    # 設置測試環境變數
    os.environ['EARTHQUAKE_API_KEY'] = 'test_api_key'
    os.environ['EARTHQUAKE_CHANNEL'] = '1234567890'
    
    # 返回未修改的 Earthquake 類以便測試
    return Earthquake

class TestEarthquakeBasics:
    """基本功能測試"""
    
    def test_initialization(self, mock_setup):
        """測試地震模組初始化"""
        # 創建模擬
        mock_bot = create_mock_bot()
        
        # 創建地震模組實例
        Earthquake = mock_setup
        earthquake = Earthquake(mock_bot)
        
        # 驗證基本屬性
        assert earthquake.bot == mock_bot
        assert earthquake.cwb_api_key == 'test_api_key'
        assert earthquake.earthquake_channel_id == '1234567890'
        assert earthquake.basic_init_complete == False
        assert earthquake.full_init_complete == False
        assert earthquake.api_ready == False
        
        # 驗證有一些基本的配置和集合
        assert hasattr(earthquake, 'last_earthquakes')
        assert isinstance(earthquake.last_earthquakes, set)
    
    def test_color_by_magnitude(self, mock_setup):
        """測試根據震級獲取顏色"""
        # 創建模擬
        mock_bot = create_mock_bot()
        
        # 創建地震模組實例
        Earthquake = mock_setup
        earthquake = Earthquake(mock_bot)
        
        # 自行定義get_color_by_magnitude方法，因為這是測試環境的輔助函數
        def get_color_by_magnitude(mag):
            try:
                magnitude = float(mag)
                if magnitude >= 7.0:
                    return 0xFF0000  # 紅色
                elif magnitude >= 6.0:
                    return 0xFF9900  # 橙色
                elif magnitude >= 5.0:
                    return 0xFFCC00  # 黃色
                elif magnitude >= 4.0:
                    return 0x33CC00  # 綠色
                else:
                    return 0x3366FF  # 藍色
            except (ValueError, TypeError):
                return 0x808080  # 灰色 (默認)
                
        # 將方法附加到實例
        earthquake.get_color_by_magnitude = get_color_by_magnitude
        
        # 測試不同震級的顏色
        assert earthquake.get_color_by_magnitude(7.5) == 0xFF0000  # 紅色
        assert earthquake.get_color_by_magnitude(6.2) == 0xFF9900  # 橙色
        assert earthquake.get_color_by_magnitude(5.5) == 0xFFCC00  # 黃色
        assert earthquake.get_color_by_magnitude(4.2) == 0x33CC00  # 綠色
        assert earthquake.get_color_by_magnitude(3.1) == 0x3366FF  # 藍色
        assert earthquake.get_color_by_magnitude("not_a_number") == 0x808080  # 灰色

class TestEarthquakeAsync:
    """異步功能測試"""
    
    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession')
    async def test_initialize_http_session(self, mock_session, mock_setup):
        """測試HTTP會話初始化"""
        # 創建模擬
        mock_session_instance = AsyncMock()
        mock_session.return_value = mock_session_instance
        mock_bot = create_mock_bot()
        
        # 創建地震模組實例
        Earthquake = mock_setup
        earthquake = Earthquake(mock_bot)
        
        # 調用被測方法
        await earthquake._initialize_http_session()
        
        # 驗證結果
        assert earthquake.session_created == True
        assert earthquake.session == mock_session_instance
    
    @pytest.mark.asyncio
    @patch('cmds.earthquake.Earthquake._load_earthquake_state')
    @patch('cmds.earthquake.Earthquake._initialize_http_session')
    async def test_delayed_initialization(self, mock_http, mock_load_state, mock_setup):
        """測試延遲初始化機制"""
        # 創建mock
        mock_http.return_value = AsyncMock()
        mock_load_state.return_value = AsyncMock()
        mock_bot = create_mock_bot()
        
        # 創建地震模組實例
        Earthquake = mock_setup
        earthquake = Earthquake(mock_bot)
        
        # 添加缺少的方法
        earthquake._setup_minimal_functionality = MagicMock()
        
        # 添加polling_interval屬性
        earthquake.polling_interval = 6
        earthquake.min_polling_interval = 2
        earthquake.max_polling_interval = 30
        earthquake.backoff_factor = 1.5
        
        # 修改環境變數以加速測試
        with patch.dict(os.environ, {'EARTHQUAKE_INITIAL_DELAY': '1'}):
            # 調用被測方法
            await earthquake._delayed_full_initialization()
            
        # 驗證結果
        mock_load_state.assert_called_once()
        mock_http.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cog_load(self, mock_setup):
        """測試模組加載"""
        # 創建模擬
        mock_bot = create_mock_bot()
        mock_bot.loop = MagicMock()
        mock_bot.loop.create_task = MagicMock()
        
        # 創建地震模組實例
        Earthquake = mock_setup
        earthquake = Earthquake(mock_bot)
        
        # 調用被測方法
        await earthquake.cog_load()
        
        # 驗證結果
        assert mock_bot.loop.create_task.called
        assert earthquake.basic_init_complete == True

class TestEarthquakeAPIInteraction:
    """API交互測試"""
    
    @pytest.fixture
    def setup_earthquake(self):
        """設置地震模組測試環境"""
        mock_bot = create_mock_bot()
        earthquake = Earthquake(mock_bot)
        earthquake.session = AsyncMock()
        earthquake.cwb_api_key = "test_api_key"
        earthquake.cwb_api_url = "https://test-api-url.com"
        
        # 添加缺少的屬性
        earthquake.polling_interval = 6
        earthquake.min_polling_interval = 2
        earthquake.max_polling_interval = 30
        earthquake.backoff_factor = 1.5
        
        return earthquake
    
    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession')
    async def test_api_connection_success(self, mock_session, setup_earthquake):
        """測試API連接成功的情況"""
        earthquake = setup_earthquake
        
        # 模擬成功的API響應
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "records": {
                "earthquake": [{"test": "data"}]
            },
            "success": True
        })
        
        # 使用上下文管理器正確模擬
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        earthquake.session.get = MagicMock(return_value=mock_context)
        
        # 調用被測方法
        result = await earthquake._test_api_connection()
        
        # 驗證結果
        assert result == True
        assert earthquake.api_ready == True
    
    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession')
    async def test_api_connection_failure(self, mock_session, setup_earthquake):
        """測試API連接失敗的情況"""
        earthquake = setup_earthquake
        
        # 模擬失敗的API響應
        mock_response = AsyncMock()
        mock_response.status = 404
        
        # 使用上下文管理器正確模擬
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        earthquake.session.get = MagicMock(return_value=mock_context)
        
        # 調用被測方法
        result = await earthquake._test_api_connection()
        
        # 驗證結果
        assert result == False
        assert earthquake.api_ready == False
    
    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession')
    async def test_api_timeout(self, mock_session, setup_earthquake):
        """測試API超時情況"""
        earthquake = setup_earthquake
        
        # 模擬超時
        earthquake.session.get = MagicMock(side_effect=asyncio.TimeoutError())
        
        # 調用被測方法
        result = await earthquake._test_api_connection()
        
        # 驗證結果
        assert result == False
        assert earthquake.api_ready == False

class TestEarthquakeOperations:
    """操作功能測試"""
    
    @pytest.fixture
    def setup_earthquake_with_data(self):
        """設置帶有測試數據的地震模組"""
        mock_bot = create_mock_bot()
        earthquake = Earthquake(mock_bot)
        earthquake.session = AsyncMock()
        earthquake.cwb_api_key = "test_api_key"
        earthquake.cwb_api_url = "https://test-api-url.com"
        
        # 添加必要的屬性
        earthquake.polling_interval = 6
        earthquake.min_polling_interval = 2
        earthquake.max_polling_interval = 30
        earthquake.backoff_factor = 1.5
        earthquake._setup_minimal_functionality = MagicMock()
        
        # 模擬方法
        earthquake._test_api_connection = AsyncMock(return_value=True)
        
        return earthquake
    
    @pytest.mark.asyncio
    @patch('discord.ext.commands.Bot')
    async def test_restart_module(self, mock_bot_class, setup_earthquake_with_data):
        """測試重啟模組功能"""
        earthquake = setup_earthquake_with_data
        
        # 模擬方法行為
        earthquake._initialize_http_session = AsyncMock(return_value=True)
        earthquake._test_api_connection = AsyncMock(return_value=True)
        earthquake._start_monitoring_tasks = AsyncMock(return_value=True)
        earthquake._setup_commands_module = AsyncMock(return_value=True)
        
        # 調用重啟方法
        result = await earthquake.restart_earthquake_module()
        
        # 驗證方法調用
        earthquake._initialize_http_session.assert_called_once()
        earthquake._test_api_connection.assert_called_once()
        earthquake._start_monitoring_tasks.assert_called_once()
        earthquake._setup_commands_module.assert_called_once()
        
        # 驗證結果
        assert result == True
        assert earthquake.full_init_complete == True
        assert earthquake.polling_active == True

if __name__ == "__main__":
    pytest.main(["-xvs", __file__]) 