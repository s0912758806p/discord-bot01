from flask import Flask, jsonify
from threading import Thread
import logging
import os
import socket
from core.logging import logger  # 使用全局日誌

# 設置一個全局變數來跟踪服務是否已啟動
_web_service_running = False

# 配置 Flask 應用
app = Flask('')
# 禁用 Flask 默認的日誌處理器
app.logger.handlers.clear()

# 使用現有的日誌系統
flask_logger = logger

VERSION = '1.0.0'

@app.route('/')
def home():
    return "Discord Bot 運行中!"

@app.route('/health')
def health():
    """健康檢查端點，返回服務狀態和版本信息"""
    return jsonify({
        'status': 'up',
        'version': VERSION
    })

def run():
    """運行 Flask 服務器"""
    try:
        # 嘗試使用不同端口，從8080開始嘗試
        for port in range(8080, 8090):
            try:
                app.run(host='0.0.0.0', port=port)
                break  # 如果成功則跳出循環
            except OSError:
                logger.warning(f"端口{port}被佔用，嘗試下一個端口")
                if port == 8089:  # 最後一個嘗試的端口
                    logger.error("所有嘗試的端口都被佔用")
                    return
    except Exception as e:
        logger.error(f"啟動 Web 服務失敗: {e}")

def keep_alive():
    """在守護線程中啟動 Flask 服務"""
    global _web_service_running
    
    # 檢查服務是否已經在運行
    if _web_service_running:
        logger.warning("Web服務已經在運行，不再重複啟動")
        return
        
    # 標記服務為已運行
    _web_service_running = True
    
    # 在新線程中啟動服務
    t = Thread(target=run, daemon=True)
    t.start()
    logger.info("Web 服務已在後台啟動 (嘗試端口: 8080-8089)")
