"""
使用pytest測試地震模組的功能
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# 添加專案根目錄到 Python 路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

# 以下導入語句在測試開始前使用補丁
with patch('discord.ext.commands.Bot'):
    from cmds.earthquake import Earthquake

@pytest.fixture
def earthquake_config():
    """地震模組配置"""
    return {
        "api_key": "test_api_key",
        "watch_channels": ["123456789"],
        "alert_channels": ["987654321"],
        "earthquake_data": {},
        "last_sent_times": {}
    }

@pytest.fixture
def create_earthquake_module(mock_bot, tmpdir):
    """創建地震模組測試實例"""
    def _create(config=None):
        if config is None:
            config = {
                "api_key": "test_api_key",
                "watch_channels": ["123456789"],
                "alert_channels": ["987654321"],
                "earthquake_data": {},
                "last_sent_times": {}
            }
        
        # 創建測試配置文件
        config_file = tmpdir.join("test_earthquake_config.json")
        config_file.write(json.dumps(config))
        
        # 設置環境變數
        os.environ['VM_ENVIRONMENT'] = 'true'
        os.environ['EARTHQUAKE_API_KEY'] = 'test_api_key'
        os.environ['EARTHQUAKE_CONFIG_FILE'] = str(config_file)
        
        # 創建地震模組實例
        with patch('cmds.earthquake.Earthquake._delayed_full_initialization'), \
             patch('cmds.earthquake.Earthquake._start_earthquake_monitoring'):
            earthquake = Earthquake(mock_bot)
            return earthquake, str(config_file)
    
    return _create

class TestEarthquakeModule:
    """測試地震模組基本功能"""
    
    def test_initialization(self, create_earthquake_module):
        """測試地震模組初始化"""
        earthquake, _ = create_earthquake_module()
        
        # 檢查基本屬性
        assert earthquake.bot is not None
        assert not earthquake.is_fully_initialized
        assert earthquake.api_key == "test_api_key"
    
    def test_color_by_magnitude(self, create_earthquake_module):
        """測試根據震級獲取顏色"""
        earthquake, _ = create_earthquake_module()
        
        # 測試不同震級獲取不同顏色
        green = earthquake.get_color_by_magnitude(2.0)
        yellow = earthquake.get_color_by_magnitude(4.0)
        orange = earthquake.get_color_by_magnitude(5.5)
        red = earthquake.get_color_by_magnitude(7.0)
        
        # 驗證顏色
        assert green != yellow
        assert yellow != orange
        assert orange != red
    
    @patch('aiohttp.ClientSession')
    @pytest.mark.asyncio
    async def test_initialize_http_session(self, mock_client_session, create_earthquake_module):
        """測試HTTP會話初始化"""
        earthquake, _ = create_earthquake_module()
        
        # 設置模擬
        mock_session = AsyncMock()
        mock_client_session.return_value = mock_session
        
        # 調用方法
        result = await earthquake._initialize_http_session()
        
        # 驗證結果
        assert result
        assert earthquake.session is not None
    
    @pytest.mark.asyncio
    async def test_restart_module(self, create_earthquake_module):
        """測試重啟模組功能"""
        earthquake, _ = create_earthquake_module()
        
        # 模擬相關方法
        earthquake._start_earthquake_monitoring = AsyncMock(return_value=True)
        earthquake.session = AsyncMock()
        earthquake.session.close = AsyncMock()
        
        # 調用重啟方法
        success, message = await earthquake.restart_earthquake_module()
        
        # 驗證結果
        assert success
        assert "成功" in message or "成功" in message

@pytest.mark.integration
class TestEarthquakeIntegration:
    """測試地震模組與其他組件的整合"""
    
    @pytest.mark.asyncio
    async def test_module_connector_integration(self, mock_bot, create_earthquake_module):
        """測試與模組連接器的整合"""
        earthquake, _ = create_earthquake_module()
        
        # 創建模擬的模組連接器
        mock_connector = MagicMock()
        mock_connector.register_module = MagicMock(return_value=True)
        mock_connector.set_module_ready = MagicMock()
        mock_bot.get_cog.return_value = mock_connector
        
        # 調用連接方法
        with patch('cmds.earthquake.Earthquake._connect_to_module_connector', 
                   wraps=earthquake._connect_to_module_connector):
            await earthquake._connect_to_module_connector()
        
        # 驗證調用
        mock_bot.get_cog.assert_called_with('ModuleConnector')
    
    @pytest.mark.asyncio
    async def test_command_module_integration(self, mock_bot, create_earthquake_module, 
                                                mock_earthquake_module):
        """測試與指令模組的整合"""
        earthquake, _ = create_earthquake_module()
        
        # 創建模擬的模組連接器
        mock_connector = MagicMock()
        mock_connector.register_module = MagicMock(return_value=True)
        mock_connector.connect_modules = MagicMock(return_value=True)
        mock_bot.get_cog.side_effect = lambda name: mock_connector if name == 'ModuleConnector' else None
        
        # 創建模擬的指令模組
        mock_commands = MagicMock()
        mock_commands.name = "EarthquakeCommands"
        mock_commands.set_earthquake_module = MagicMock()
        mock_bot.cogs = {'ModuleConnector': mock_connector, 'EarthquakeCommands': mock_commands}
        
        # 調用連接方法
        await earthquake._connect_to_module_connector()
        
        # 驗證連接模組被調用
        mock_connector.connect_modules.assert_called() 