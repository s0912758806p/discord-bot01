# Discord Bot 測試框架

本測試框架用於確保 Discord Bot 在不同環境（包括VM環境）中的穩定性和功能正確性。

## 測試結構

測試框架分為兩個主要部分：

1. **單元測試** - 測試個別組件功能
   - 位於 `tests/unit/` 目錄
   - 測試單獨組件的功能，不依賴其他模組
   - 使用模擬（mock）替代外部依賴
   - `test_regressions.py`：針對實際出過的 bug 的回歸測試（指令重複執行、每則訊息開檔、
     擴充在 on_ready 重複載入、twstock 阻塞 event loop），修改 main.py / cmds/ 時務必保持全綠
   - `test_docs_freshness.py`：README 的指令清單必須與程式碼雙向一致；新增、改名或移除指令時要同步更新 README

2. **系統測試** - 測試完整系統功能
   - 位於 `tests/system/` 目錄
   - 測試整個系統在各種環境下的運行
   - 特別針對VM環境進行測試

## 測試數據

所有測試數據位於 `tests/test_data/` 目錄中：
- `test_config.json`、`save_config.json` - 設定檔讀寫的測試數據

## 運行測試

### 安裝測試依賴

```bash
pip install -r requirements-dev.txt
```

### 運行所有測試

```bash
python run_tests.py
```

### 運行特定類型的測試

```bash
# 運行單元測試
python run_tests.py -t unit

# 運行系統測試
python run_tests.py -t system
```

### 使用Pytest運行測試

```bash
# 運行所有測試
pytest tests/

# 運行特定測試文件
pytest tests/unit/test_regressions.py

# 運行標記的測試
pytest -m "not slow"
```

## 測試環境變數

以下環境變數可用於控制測試行為：

- `TESTING=true` - 指示程序在測試環境中運行
- `VM_ENVIRONMENT=true` - 模擬VM環境
- `DISCORD_HTTP_TIMEOUT=10` - HTTP請求超時設置

## VM環境測試

VM環境測試專注於以下方面：

1. **資源限制** - 測試在有限記憶體和CPU環境下的表現
2. **連接恢復** - 測試網絡連接中斷後的恢復能力
3. **初始化順序** - 測試分段初始化機制
4. **錯誤處理** - 測試在各種錯誤條件下的行為

## 添加新測試

添加新測試時，請遵循以下指南：

1. 根據測試性質選擇正確的目錄（unit/system）
2. 使用與現有測試一致的命名約定
3. 利用共用的測試工具和配置
4. 確保測試獨立性和可重複性

## 測試覆蓋率

測試覆蓋率報告可以使用以下命令生成：

```bash
pytest --cov=cmds tests/
```

目標是達到至少80%的代碼覆蓋率。 