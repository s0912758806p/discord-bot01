# Discord Bot 多功能機器人

一個功能豐富的 Discord 機器人專案，提供新聞聚合、台股資訊、抽籤、天氣查詢、音樂功能、地震監測和反應圖片等多種實用功能。

## 功能特性

- **新聞聚合**：獲取最新焦點新聞和財經新聞
- **股票資訊**：查詢台股指數和個股資訊
- **抽籤功能**：提供淺草抽籤和城隍廟抽籤功能
- **天氣查詢**：獲取當前天氣狀況
- **星座運勢**：提供每日星座運勢預測
- **音樂功能**：基本的音樂播放功能
- **反應圖片**：發送有趣的圖片和表情符號
- **地震監測**：即時監測並通報台灣地區地震資訊
- **自動重啟**：每日自動重啟以確保穩定運行
- **環境變數管理**：使用 `.env` 文件保護敏感資訊

## 技術架構

- 使用 Python 和 Discord.py 庫開發
- 模組化設計，易於擴展
- 使用 Docker 容器化部署
- 緩存機制提高性能
- 完整的錯誤處理和日誌記錄
- 背景任務監測資料更新

## 安裝與設定

### 前置需求

- Python 3.12（與 Docker 映像一致；3.9 以上應可執行）
- pip 套件管理器
- Discord 開發者帳號與 Bot Token

### 安裝步驟

1. 複製專案
```bash
git clone <repository-url>
cd discord-bot01
```

2. 建立虛擬環境並安裝依賴
```bash
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt        # 執行期依賴
pip install -r requirements-dev.txt    # 另含測試工具（開發時才需要）
```

3. 配置環境變數
```bash
cp .env.example .env
```
編輯 `.env` 文件，填寫以下資訊（完整清單與說明見 `.env.example`）：
- `DISCORD_TOKEN`：Discord 機器人 Token（必填）
- `COMMAND_PREFIX`：指令前綴，預設為 `!`
- `EARTHQUAKE_CHANNEL`：接收地震通知的頻道 ID

Bot 需在 Developer Portal 開啟 **Message Content** 與 **Server Members** 兩個 Privileged Gateway Intents。

4. 啟動機器人
```bash
python main.py
```

### Docker 部署

使用 Docker Compose 快速部署（映像為 `python:3.12-slim`，只安裝 `requirements.txt`）：
```bash
docker compose up -d --build
```
日誌寫在掛載的 `./logs/discord.log`（自動輪替）。

### 測試

```bash
pytest -q
```

## 指令列表

### 抽籤功能
- `!抽籤A`：城隍廟抽籤功能
- `!抽籤B`：淺草寺觀音廟抽籤功能
- `??:問題`：使用淺草籤進行問答

### 新聞
- `!新聞`：獲取最新焦點新聞
- `!財經新聞`：獲取最新財經新聞

### 股票
- `!指數`：獲取台灣加權指數資訊
- `!股票 <股票代碼>`：獲取特定股票資訊

### 天氣
- `!天氣`：獲取當前天氣資訊

### 地震資訊
- `!地震資訊`：獲取最近地震資訊列表

### 星座運勢
- `!今日運勢-<星座>`：查詢特定星座的今日運勢
- `!星座編號`：顯示星座對應編號

### 音樂指令
- `!join`：加入使用者的語音頻道
- `!leave`：離開當前語音頻道

### 娛樂功能
- `!甜味鬆餅`：隨機推薦甜味鬆餅
- `!鹹味鬆餅`：隨機推薦鹹味鬆餅
- `!炸物鬆餅`：隨機推薦炸物鬆餅
- `!鬆餅混搭 甜+鹹`：推薦甜鹹混搭鬆餅
- `!上班`、`!下班`：隨機回覆上下班相關語句
- `!下午茶`：顯示點餐網站連結

## 貢獻與開發

歡迎提交 Pull Request 或開 Issue 提出建議。

## 授權協議

此專案為個人使用，未指定開源授權。

## 作者與鳴謝

- 最初版本建立於 2021 年
- 感謝所有開源貢獻者和社群