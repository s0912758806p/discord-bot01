FROM python:3.9-slim

WORKDIR /app

# 安裝編譯依賴
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 複製 requirements.txt
COPY requirements.txt .

# 清理 pip 緩存並強制重新安裝精確指定的版本
RUN pip uninstall -y flask werkzeug && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir werkzeug==2.0.3 flask==2.0.1

# 複製應用程式代碼
COPY . .

# 創建日誌目錄
RUN mkdir -p logs

# 設置時區
ENV TZ=Asia/Taipei
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 運行應用
CMD ["python", "main.py"] 