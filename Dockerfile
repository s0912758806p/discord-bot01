FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Taipei

# tzdata：讓 TZ=Asia/Taipei 生效（地震通報時間、日誌時間）
# 所有 Python 依賴都有 manylinux wheel，不需要 gcc / *-dev
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r bot && useradd -r -g bot -m -d /home/bot bot

# 先複製 requirements 以利用 layer cache
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=bot:bot . .
RUN mkdir -p /app/logs /app/config /app/data && chown -R bot:bot /app/logs /app/config /app/data

USER bot

CMD ["python", "-u", "main.py"]
