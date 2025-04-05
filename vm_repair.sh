#!/bin/bash
# VM環境下地震模組修復腳本
# 使用方法: ./vm_repair.sh

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}===== 地震模組VM環境修復工具 =====${NC}"
echo -e "${BLUE}開始診斷Docker容器問題...${NC}"

# 檢查Docker是否運行
echo -e "${YELLOW}1. 檢查Docker狀態...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}錯誤: Docker未安裝${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}錯誤: Docker服務未運行${NC}"
    echo "請運行: sudo systemctl start docker"
    exit 1
fi
echo -e "${GREEN}Docker狀態正常${NC}"

# 檢查容器是否存在
echo -e "${YELLOW}2. 檢查Discord機器人容器...${NC}"
if ! docker ps -a | grep -q discord-bot; then
    echo -e "${RED}錯誤: 找不到discord-bot容器${NC}"
    echo "請確認容器名稱是否正確"
    exit 1
fi

# 檢查容器狀態
CONTAINER_STATUS=$(docker inspect --format='{{.State.Status}}' discord-bot 2>/dev/null)
if [ "$CONTAINER_STATUS" != "running" ]; then
    echo -e "${RED}警告: Discord機器人容器未運行 (狀態: $CONTAINER_STATUS)${NC}"
    echo -e "嘗試啟動容器..."
    docker start discord-bot
    sleep 3
    if [ "$(docker inspect --format='{{.State.Status}}' discord-bot 2>/dev/null)" != "running" ]; then
        echo -e "${RED}錯誤: 無法啟動容器${NC}"
        echo "請檢查docker-compose.yml配置和日誌"
        exit 1
    fi
    echo -e "${GREEN}容器成功啟動${NC}"
else
    echo -e "${GREEN}容器狀態正常${NC}"
fi

# 檢查容器日誌中的錯誤
echo -e "${YELLOW}3. 分析容器日誌...${NC}"
echo -e "搜索關鍵錯誤..."
ERROR_COUNT=$(docker logs discord-bot --tail 200 2>&1 | grep -i -E "error|exception|traceback|failed" | wc -l)
EARTHQUAKE_MODULE_ERRORS=$(docker logs discord-bot --tail 200 2>&1 | grep -i -E "地震模組|earthquake module" | grep -i -E "error|failed|未就緒" | wc -l)

if [ $ERROR_COUNT -gt 10 ]; then
    echo -e "${RED}發現大量錯誤 ($ERROR_COUNT 條)${NC}"
elif [ $EARTHQUAKE_MODULE_ERRORS -gt 0 ]; then
    echo -e "${RED}發現地震模組相關錯誤 ($EARTHQUAKE_MODULE_ERRORS 條)${NC}"
else
    echo -e "${GREEN}日誌分析: 未發現嚴重錯誤${NC}"
fi

# 檢查網絡連接
echo -e "${YELLOW}4. 檢查網絡連接...${NC}"
if ! ping -c 2 discord.com &> /dev/null; then
    echo -e "${RED}警告: 無法連接到Discord服務器${NC}"
else
    echo -e "${GREEN}網絡連接正常${NC}"
fi

# 檢查資源使用情況
echo -e "${YELLOW}5. 檢查容器資源使用情況...${NC}"
docker stats discord-bot --no-stream --format "CPU: {{.CPUPerc}}, 記憶體: {{.MemUsage}}"

# 顯示修復選項
echo -e "\n${BLUE}===== 修復選項 =====${NC}"
echo -e "${YELLOW}1. 重啟容器${NC}"
echo -e "${YELLOW}2. 重建容器${NC}"
echo -e "${YELLOW}3. 強制初始化地震模組${NC}"
echo -e "${YELLOW}4. 顯示最近日誌${NC}"
echo -e "${YELLOW}5. 退出${NC}"

read -p "請選擇操作 [1-5]: " option

case $option in
    1)
        echo -e "${BLUE}正在重啟容器...${NC}"
        docker restart discord-bot
        echo -e "${GREEN}容器已重啟${NC}"
        echo -e "${YELLOW}請等待約30秒讓機器人完成初始化...${NC}"
        sleep 5
        echo -e "顯示最近日誌:"
        docker logs discord-bot --tail 20
        ;;
    2)
        echo -e "${BLUE}正在重建容器...${NC}"
        echo -e "${RED}警告: 這將重建整個容器，所有未保存到掛載卷的數據將丟失${NC}"
        read -p "確定要繼續嗎? [y/N]: " confirm
        if [[ $confirm == [Yy]* ]]; then
            cd "$(dirname "$(realpath "$0")")"
            docker-compose down
            docker-compose build --no-cache
            docker-compose up -d
            echo -e "${GREEN}容器已重建並啟動${NC}"
            echo -e "${YELLOW}請等待約1分鐘讓機器人完成初始化...${NC}"
            sleep 10
            echo -e "顯示最近日誌:"
            docker logs discord-bot --tail 20
        else
            echo -e "${BLUE}操作已取消${NC}"
        fi
        ;;
    3)
        echo -e "${BLUE}正在強制初始化地震模組...${NC}"
        echo "嘗試在容器內執行地震模組重啟命令..."
        # 在容器中執行Python代碼，嘗試重啟地震模組
        docker exec discord-bot python3 -c "
import asyncio
import sys

async def restart_earthquake():
    try:
        # 動態導入Discord庫
        import discord
        from discord.ext import commands
        
        # 創建一個虛擬bot實例
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())
        
        # 在這裡，我們調用main.py中的setup_commands函數
        import importlib.util
        import os
        
        print('嘗試強制初始化地震模組...')
        
        # 導入地震模組
        try:
            from cmds.earthquake import Earthquake
            from cmds.earthquake_commands import EarthquakeCommands
            print('成功導入模組類')
            
            # 檢查模組文件
            if os.path.exists('./cmds/earthquake.py') and os.path.exists('./cmds/earthquake_commands.py'):
                print('模組文件存在')
            else:
                print('警告: 模組文件不存在')
            
            # 打印模組屬性
            print(f'Earthquake模組屬性: {dir(Earthquake)}')
            print(f'EarthquakeCommands模組屬性: {dir(EarthquakeCommands)}')
            
            print('初始化完成')
            print('請在Discord中執行!重啟地震模組命令以完成修復')
            
        except ImportError as e:
            print(f'模組導入失敗: {e}')
            sys.exit(1)
            
    except Exception as e:
        print(f'強制初始化失敗: {e}')
        sys.exit(1)

if __name__ == '__main__':
    print('開始強制初始化流程...')
    try:
        asyncio.run(restart_earthquake())
        print('強制初始化完成')
    except Exception as e:
        print(f'運行失敗: {e}')
        sys.exit(1)
"
        ;;
    4)
        echo -e "${BLUE}顯示最近日誌...${NC}"
        docker logs discord-bot --tail 100
        ;;
    5)
        echo -e "${BLUE}退出${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}無效選項${NC}"
        exit 1
        ;;
esac

echo -e "\n${BLUE}===== 修復完成 =====${NC}"
echo -e "${YELLOW}提示: 如果問題仍然存在，請嘗試:${NC}"
echo "1. 使用docker-compose.yml中的network_mode: \"host\"設置"
echo "2. 增加retry次數和等待時間"
echo "3. 檢查VM環境的資源限制和網絡連接"
echo "4. 在Discord中執行!重啟地震模組命令"
echo -e "${GREEN}完成${NC}" 