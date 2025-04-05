"""
測試包初始化文件
Discord Bot 測試套件說明

包含以下測試類型:
- 單元測試 (unit): 測試個別組件功能
- 整合測試 (integration): 測試組件之間的通信和交互
- 系統測試 (system): 測試完整系統功能和VM環境下的部署

測試數據存放在 test_data 目錄
共用配置工具在 test_config.py

相依性:
- pytest
- pytest-asyncio (用於測試異步功能)
- pytest-mock (用於模擬功能)
"""

import os
import sys

# 確保項目根目錄在路徑中
PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 版本信息
__version__ = '0.1.0' 