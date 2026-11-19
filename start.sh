#!/bin/bash
# Discord Bot 啟動腳本：檢查環境與依賴後執行 main.py
# 版本: 1.0.0

# 顏色定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 設置工作目錄
cd "$(dirname "$0")"
ROOT_DIR=$(pwd)
echo -e "${BLUE}工作目錄: $ROOT_DIR${NC}"

# 確保目錄結構
echo -e "${BLUE}確保目錄結構...${NC}"
mkdir -p logs
mkdir -p data

# 檢查是否在Docker環境中
if [ -f /.dockerenv ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    echo -e "${GREEN}檢測到Docker環境${NC}"
    export DOCKER_ENVIRONMENT=true
    export VM_ENVIRONMENT=true
    
    # 在Docker中等待更長時間以確保系統穩定
    WAIT_TIME=30
    echo -e "${YELLOW}等待${WAIT_TIME}秒以確保系統資源初始化...${NC}"
    sleep $WAIT_TIME
    
    # 確保網絡連接
    echo -e "${BLUE}檢查網絡連接...${NC}"
    for i in {1..5}; do
        if ping -c 1 discord.com > /dev/null 2>&1; then
            echo -e "${GREEN}網絡連接正常${NC}"
            break
        else
            echo -e "${YELLOW}網絡連接測試失敗，等待5秒後重試...${NC}"
            sleep 5
            if [ $i -eq 5 ]; then
                echo -e "${RED}網絡連接測試失敗，但仍繼續啟動${NC}"
            fi
        fi
    done
else
    echo -e "${GREEN}本地環境${NC}"
    export DOCKER_ENVIRONMENT=false
    export VM_ENVIRONMENT=false
fi

# 檢查Python和依賴
echo -e "${BLUE}檢查Python環境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}找不到Python3，請確保已安裝${NC}"
    exit 1
fi

# 檢查虛擬環境
if [ -d "venv" ]; then
    echo -e "${GREEN}使用現有虛擬環境${NC}"
    source venv/bin/activate
else
    echo -e "${YELLOW}創建新的虛擬環境${NC}"
    python3 -m venv venv
    source venv/bin/activate
    
    echo -e "${BLUE}安裝依賴...${NC}"
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# 檢查.env文件
if [ ! -f .env ]; then
    echo -e "${YELLOW}未找到.env文件，從示例複製${NC}"
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${YELLOW}請編輯.env文件設置您的TOKEN和其他配置${NC}"
    else
        echo -e "${RED}未找到.env.example，創建基本.env文件${NC}"
        cat > .env << EOL
# Discord 機器人設置
DISCORD_TOKEN=
COMMAND_PREFIX=!

# 日誌設置
LOG_LEVEL=INFO
EOL
        echo -e "${YELLOW}已創建基本.env文件，請編輯設置您的TOKEN和其他配置${NC}"
    fi
    exit 1
fi

# 設定環境變數檢查
echo -e "${BLUE}檢查關鍵環境變數...${NC}"
if grep -q "DISCORD_TOKEN=" .env && ! grep -q "DISCORD_TOKEN=$" .env && ! grep -q "DISCORD_TOKEN=\"\"" .env; then
    echo -e "${GREEN}找到Discord Token${NC}"
else
    echo -e "${RED}未找到有效的Discord Token，請編輯.env文件${NC}"
    exit 1
fi

# 清理過時的日誌文件
echo -e "${BLUE}清理過時日誌文件...${NC}"
find logs -name "*.log*" -type f -mtime +7 -delete 2>/dev/null || true

# 檢查是否是測試模式
if grep -q "TEST_MODE=true" .env; then
    echo -e "${YELLOW}檢測到測試模式，將跳過實際啟動${NC}"
    echo -e "${GREEN}所有測試準備工作已完成！${NC}"
    echo -e "${BLUE}在實際運行中，接下來會執行: python3 main.py${NC}"
    exit 0
fi

# 顯示啟動信息
echo -e "${GREEN}準備啟動Discord Bot...${NC}"
echo -e "${YELLOW}啟動時間: $(date)${NC}"
echo -e "${YELLOW}Python版本: $(python3 --version)${NC}"
echo -e "${YELLOW}Discord.py版本: $(pip show discord.py | grep Version || echo 'Not installed')${NC}"
echo -e "${YELLOW}運行環境: $([ "$VM_ENVIRONMENT" = "true" ] && echo 'VM/Docker' || echo '本地')${NC}"

# 啟動Bot
echo -e "${GREEN}啟動Discord Bot...${NC}"
python3 main.py

# 捕捉退出碼
EXIT_CODE=$?

# 處理退出
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Discord Bot正常退出${NC}"
    exit 0
else
    echo -e "${RED}Discord Bot異常退出，代碼: $EXIT_CODE${NC}"
    
    # 記錄錯誤
    echo "Bot異常退出，時間: $(date), 代碼: $EXIT_CODE" >> logs/crash_log.txt
    
    exit $EXIT_CODE
fi 