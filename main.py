#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import asyncio
import discord
from dotenv import load_dotenv
from discord.ext import commands
from pathlib import Path

# 設定日誌
LOG_DIR = 'logs'
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)

# 創建日誌文件處理器
from datetime import datetime
log_filename = f"discord_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
file_handler = logging.FileHandler(os.path.join(LOG_DIR, log_filename), encoding='utf-8')
file_handler.setFormatter(logging.Formatter(log_format))

# 設定日誌
logger = logging.getLogger('discord_bot')
logger.addHandler(file_handler)
logger.setLevel(logging.INFO)

logger.info("日誌系統初始化完成，級別: INFO, 文件: %s", os.path.join(LOG_DIR, log_filename))

# 載入環境變數
logger.info("正在載入環境變數...")
load_dotenv()

# 檢查Discord令牌
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN:
    logger.info("已成功載入 Discord Bot Token")
else:
    logger.error("無法載入 Discord Bot Token，請檢查 .env 文件")
    sys.exit(1)

# 設定機器人命令前綴
PREFIX = os.getenv('COMMAND_PREFIX', '!')
logger.info("使用命令前綴: %s", PREFIX)

# 載入配置文件
CONFIG_DIR = 'config'
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)
logger.info("已載入配置文件")

# 設定機器人意圖
intents = discord.Intents.all()  # 啟用所有 intents
logger.info("已啟用所有 Discord 意圖")

# 為測試添加的輔助函數
def is_vm_environment():
    """
    檢查是否在VM環境中運行
    
    Returns:
        bool: 如果是VM環境則返回True，否則返回False
    """
    return os.environ.get('VM_ENVIRONMENT', 'false').lower() == 'true'

def check_system_resources():
    """
    檢查系統資源使用情況
    
    Returns:
        dict: 包含記憶體使用情況的字典
    """
    try:
        import psutil
        memory = psutil.virtual_memory()
        return {
            'total_mb': memory.total // (1024 * 1024),
            'available_mb': memory.available // (1024 * 1024),
            'usage_percent': memory.percent
        }
    except ImportError:
        logger.warning("無法導入psutil模組，無法檢查系統資源")
        return {
            'total_mb': 0,
            'available_mb': 0,
            'usage_percent': 0
        }

def check_cpu_usage():
    """
    檢查CPU使用率
    
    Returns:
        float: CPU使用率百分比
    """
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except ImportError:
        logger.warning("無法導入psutil模組，無法檢查CPU使用率")
        return 0.0

def login_bot(token, bot=None):
    """
    登入Discord機器人
    
    Args:
        token (str): Discord Bot Token
        bot (commands.Bot, optional): 機器人實例
    """
    if bot is None:
        bot = commands.Bot(command_prefix=PREFIX, intents=intents)
    bot.login(token)
    
def run_bot(token=None, bot=None):
    """
    運行Discord機器人
    
    Args:
        token (str, optional): Discord Bot Token
        bot (commands.Bot, optional): 機器人實例
    """
    if bot is None:
        bot = commands.Bot(command_prefix=PREFIX, intents=intents)
    if token is None:
        token = TOKEN
    bot.connect()

# 創建機器人實例
bot = commands.Bot(command_prefix=PREFIX, intents=intents)
logger.info("使用 %s 作為命令前綴初始化機器人", PREFIX)

# 機器人事件
@bot.event
async def on_ready():
    """當機器人登入Discord時執行"""
    logger.info(f'機器人 {bot.user.name} 已連接到 Discord!')

# 加載指令模組
for filename in os.listdir('./cmds'):
    # 僅加載 Python 文件且非 __init__.py
    if filename.endswith('.py') and not filename.startswith('__'):
        try:
            bot.load_extension(f'cmds.{filename[:-3]}')
            logger.info(f'成功加載指令模組: {filename}')
        except Exception as e:
            logger.error(f'加載指令模組 {filename} 時發生錯誤: {str(e)}')

# 運行機器人
if __name__ == '__main__':
    try:
        logger.info("正在啟動 Discord 機器人...")
        bot.run(TOKEN)
    except Exception as e:
        logger.critical(f"啟動機器人時發生錯誤: {str(e)}")
        sys.exit(1)

