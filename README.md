# Discord Bot 多功能機器人

一個功能豐富的 Discord 機器人專案，提供台股資訊、抽籤、星座運勢、語音頻道進出、關鍵字自動回應和反應圖片等功能。

## 功能特性

- **股票資訊**：查詢台股指數和個股資訊
- **抽籤功能**：提供淺草抽籤和城隍廟抽籤功能
- **星座運勢**：提供每日星座運勢預測
- **語音頻道**：加入／離開語音頻道（目前沒有播放功能）
- **反應圖片**：發送有趣的圖片和表情符號
- **環境變數管理**：使用 `.env` 文件保護敏感資訊

## 技術架構

- 使用 Python 和 Discord.py 庫開發
- 模組化設計，易於擴展
- 使用 Docker 容器化部署
- 全 bot 共用一個帶逾時的 HTTP session（`HTTP_TIMEOUT`，預設 15 秒）
- 日誌集中設定、自動輪替（`logs/discord.log`）

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

指令前綴預設為 `!`（`COMMAND_PREFIX`）。下表以程式碼為準：`cmds/*.py` 的 `@commands.command`，
以及 `cmds/event.py` 的關鍵字回應表（完全比對訊息內容）。

### 抽籤
- `!抽籤A`：城隍廟抽籤（1–60 籤）
- `!抽籤B`：淺草寺觀音籤（1–100 籤）
- `??:`：打招呼；`??:問題`：隨機回覆一張普籤圖或吐槽

### 股票
- `!twii`：台灣加權指數
- `!tws <股票代碼>`：個股即時資訊，例如 `!tws 2330`

### 星座運勢
- `!今日運勢`：使用說明
- `!今日運勢-<星座>`：例如 `!今日運勢-天秤座`
- `!星座編號`：列出星座英文名

### 語音頻道
- `!join`：加入你所在的語音頻道
- `!leave`：離開語音頻道

### 鬆餅與上下班
- `!甜味鬆餅`、`!鹹味鬆餅`、`!炸物鬆餅`：隨機推薦
- `!鬆餅混搭 甜+鹹`、`甜+炸`、`鹹+炸`（前後順序皆可）
- `!上班`、`!下班`：隨機回覆
- `!下午茶`：訂餐網站連結

### 反應圖片指令（`cmds/react.py` 的 `REACTIONS`）
`!我要看到血流成河`、`!開心到跳起來`、`!我的車車`、`!上香`、`!呦呼`、`!沒錢就不要想這些事情`、
`!條件太嚴苛`、`!難以理解`、`!八方雲吉`、`!槍吉要犯`、`!是不是想幹人家`、`!不可能`、`!我2D`

### 關鍵字回應（`cmds/event.py` 的 `_build_fixed_responses`）
訊息內容完全等於觸發詞時回圖或文字，例如 `哦嚯`、`是嗎`、`確實`、`!集合`、`!阿C滑倒`、`!哈密嘎`、`滾`。
另有 `!阿希`、`!ping`。完整清單請看程式碼。

### 其他
- `!help`：discord.py 內建指令說明

## 貢獻與開發

歡迎提交 Pull Request 或開 Issue 提出建議。

## 授權協議

此專案為個人使用，未指定開源授權。

## 作者與鳴謝

- 最初版本建立於 2021 年
- 感謝所有開源貢獻者和社群