FROM python:3.9-slim

WORKDIR /app

# 安裝編譯依賴和診斷工具
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    procps \
    net-tools \
    iputils-ping \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 複製 requirements.txt
COPY requirements.txt .

# 添加診斷包
RUN pip install --no-cache-dir psutil && \
    pip uninstall -y flask werkzeug && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir werkzeug==2.0.3 flask==2.0.1

# 複製應用程式代碼
COPY . .

# 創建日誌目錄
RUN mkdir -p logs

# 設置時區
ENV TZ=Asia/Taipei
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 設置Python不緩存輸出
ENV PYTHONUNBUFFERED=1

# 特定Docker環境的設置
ENV DOCKER_ENVIRONMENT=true
ENV PYTHON_CACHE_SIZE=1024

# 增加Discord API連接超時時間
ENV DISCORD_API_TIMEOUT=60

# 運行應用
CMD ["python", "main.py"] 