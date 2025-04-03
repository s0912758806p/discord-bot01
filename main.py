import discord
import os
import keep_alive
import asyncio
import schedule
import time
import logging

from discord.ext import commands
from dotenv import load_dotenv
from core.config import load_config
from core.logging import logger
from core.cache import start_cleanup_task

# 載入環境變數
load_dotenv()
TOKEN = os.getenv('TOKEN')

# 載入配置
jData = load_config('setting.json')

# 設置意圖
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# 實例化機器人
bot = commands.Bot(command_prefix='/', intents=intents)

# 記錄未處理的異常
@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"未處理的錯誤: {event}", exc_info=True)

# 機器人就緒事件
@bot.event
async def on_ready():
    logger.info(f"機器人已啟動: {bot.user.name} ({bot.user.id})")
    await load_cogs()
    logger.info("已加載所有Cogs")
    
    # 啟動緩存清理任務
    asyncio.create_task(cache_cleanup_task())

# 緩存清理任務
async def cache_cleanup_task():
    """定期運行緩存清理"""
    try:
        # 啟動緩存清理任務
        cleanup_task = start_cleanup_task()
        logger.info("緩存清理任務已啟動")
        await cleanup_task
    except Exception as e:
        logger.error(f"緩存清理任務出錯: {e}")

# 載入擴展模組
async def load_cogs():
    # 加載命令模組目錄中的所有模組
    for fileName in os.listdir('./cmds'):
        if fileName.endswith('.py'):
            try:
                await bot.load_extension(f'cmds.{fileName[:-3]}')
                logger.info(f"已加載模組: {fileName}")
            except Exception as e:
                logger.error(f"加載模組 {fileName} 失敗: {str(e)}")

# 運行機器人
async def run_bot():
    async with bot:
        await bot.start(TOKEN)

# 定時重啟任務
def scheduled_restart():
    logger.info("執行計劃任務: 重新啟動機器人...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(run_bot())
    loop.run_until_complete(asyncio.sleep(5))
    loop.stop()

# 設置定時任務
def setup_schedule():
    # 每天凌晨3點重啟機器人
    schedule.every().day.at("03:00").do(scheduled_restart)
    logger.info("已設置定時重啟任務")

if __name__ == '__main__':
    try:
        # 啟動網頁服務保持機器人在線
        keep_alive.keep_alive()
        logger.info("已啟動保活服務")
        
        # 設置定時任務
        setup_schedule()
        
        # 運行機器人
        loop = asyncio.get_event_loop()
        
        try:
            loop.run_until_complete(run_bot())
        except KeyboardInterrupt:
            logger.info("接收到中斷信號，關閉機器人...")
            loop.run_until_complete(bot.close())
            
        # 運行定時任務循環
        try:
            logger.info("開始運行定時任務循環")
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("接收到中斷信號，關閉定時任務...")
    except Exception as e:
        logger.critical(f"主程序出現異常: {str(e)}", exc_info=True)

