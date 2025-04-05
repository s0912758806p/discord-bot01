FROM python:3.9-slim

# 設置工作目錄
WORKDIR /app

# 設置環境變量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONASYNCIODEBUG=0 \
    TZ=Asia/Taipei \
    DOCKER_ENVIRONMENT=true \
    # Discord連接超時時間
    DISCORD_HTTP_TIMEOUT=90 \
    # 地震模組初始化等待時間
    EARTHQUAKE_INIT_TIMEOUT=120 \
    # 地震模組重試間隔
    EARTHQUAKE_RETRY_INTERVAL=5

# 安裝系統依賴和診斷工具
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    procps \
    net-tools \
    iputils-ping \
    curl \
    htop \
    vim \
    dnsutils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 創建非root用戶運行應用
RUN groupadd -r bot && useradd -r -g bot -m -d /home/bot bot

# 設置時區
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 創建必要的目錄結構
RUN mkdir -p /app/logs /app/config /app/data /app/assets \
    && chown -R bot:bot /app

# 安裝Python依賴
# 先複製requirements.txt
COPY requirements.txt .

# 建立虛擬環境並安裝依賴，減少層數
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir psutil && \
    pip install --no-cache-dir -r requirements.txt && \
    # 確保使用特定版本避免兼容性問題
    pip install --no-cache-dir werkzeug==2.0.3 flask==2.0.1 && \
    # 安裝監控和診斷工具
    pip install --no-cache-dir py-spy memory-profiler

# 複製代碼
COPY . .

# 添加啟動腳本
RUN echo '#!/bin/bash\n\
echo "等待系統資源穩定 (5秒)..."\n\
sleep 5\n\
echo "正在啟動Discord機器人..."\n\
python -u main.py\n\
' > /app/start.sh && chmod +x /app/start.sh

# 確保目錄權限
RUN chown -R bot:bot /app

# 切換到非root用戶
USER bot

# 運行啟動腳本
CMD ["./start.sh"] 