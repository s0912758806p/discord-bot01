#!/bin/bash
# VM健康監控腳本 - 自動檢查地震模組狀態並恢復
# 可以添加到crontab中，例如: */10 * * * * /path/to/vm_health_monitor.sh >> /var/log/earthquake_monitor.log 2>&1

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 設置腳本目錄
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# 記錄運行時間
echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${BLUE}開始健康檢查${NC}"

# 檢查Docker是否運行
if ! command -v docker &> /dev/null || ! docker info &> /dev/null; then
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${RED}Docker未運行，無法進行檢查${NC}"
    exit 1
fi

# 檢查容器是否存在並運行
CONTAINER_STATUS=$(docker inspect --format='{{.State.Status}}' discord-bot 2>/dev/null)
if [ $? -ne 0 ] || [ "$CONTAINER_STATUS" != "running" ]; then
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${RED}Discord機器人容器未運行 (狀態: $CONTAINER_STATUS)${NC}"
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}嘗試啟動容器...${NC}"
    docker start discord-bot
    sleep 10
    
    # 再次檢查容器狀態
    if [ "$(docker inspect --format='{{.State.Status}}' discord-bot 2>/dev/null)" != "running" ]; then
        echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${RED}無法啟動容器，嘗試重建...${NC}"
        docker-compose down
        docker-compose up -d
        echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}容器已重建，等待30秒初始化...${NC}"
        sleep 30
    else
        echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}容器已成功啟動${NC}"
    fi
else
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}容器運行正常${NC}"
fi

# 檢查地震模組錯誤
EARTHQUAKE_ERRORS=$(docker logs discord-bot --since 5m 2>&1 | grep -i -E "地震模組|earthquake module" | grep -i -E "error|failed|未就緒" | wc -l)
if [ $EARTHQUAKE_ERRORS -gt 5 ]; then
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${RED}檢測到地震模組錯誤 ($EARTHQUAKE_ERRORS 條)${NC}"
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}嘗試重啟容器...${NC}"
    docker restart discord-bot
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}容器已重啟，等待30秒...${NC}"
    sleep 30
else
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}地震模組過去5分鐘無嚴重錯誤${NC}"
fi

# 檢查容器內存使用
MEM_USAGE=$(docker stats discord-bot --no-stream --format "{{.MemPerc}}" | tr -d '%')
if (( $(echo "$MEM_USAGE > 90" | bc -l) )); then
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${RED}容器內存使用率過高 (${MEM_USAGE}%)${NC}"
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}嘗試重啟容器以釋放內存...${NC}"
    docker restart discord-bot
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}容器已重啟${NC}"
else
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}內存使用正常 (${MEM_USAGE}%)${NC}"
fi

# 檢查容器運行時間
UPTIME=$(docker inspect --format='{{.State.StartedAt}}' discord-bot | xargs -I{} date -d {} +%s)
NOW=$(date +%s)
UPTIME_DAYS=$(( (NOW - UPTIME) / 86400 ))

if [ $UPTIME_DAYS -gt 7 ]; then
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}容器運行時間超過7天，執行維護性重啟...${NC}"
    docker restart discord-bot
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}容器已重啟${NC}"
else
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}容器運行時間正常 (${UPTIME_DAYS}天)${NC}"
fi

# 檢查日誌文件大小
LOG_SIZE=$(docker exec discord-bot bash -c "du -sm /app/logs | cut -f1")
if [ $LOG_SIZE -gt 500 ]; then
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}日誌目錄過大 (${LOG_SIZE}MB)，清理舊日誌...${NC}"
    docker exec discord-bot bash -c "find /app/logs -name '*.log' -type f -mtime +7 -delete"
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}已清理7天前的日誌文件${NC}"
else
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}日誌大小正常 (${LOG_SIZE}MB)${NC}"
fi

echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${BLUE}健康檢查完成${NC}"
echo "-----------------------------------" 