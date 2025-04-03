import discord
import os
import asyncio
import schedule
import time
import logging
import socket

from discord.ext import commands
from dotenv import load_dotenv
from core.config import load_config
from core.logging import logger
from core.cache import start_cleanup_task

# 載入環境變數
logger.info("正在載入環境變數...")
load_dotenv()
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    logger.critical("未設置 Discord Bot Token，請在 .env 文件中設置 TOKEN 變數")
    raise ValueError("Discord Bot Token 未設置")
else:
    logger.info("已成功載入 Discord Bot Token")

# 載入命令前綴
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '/')
logger.info(f"使用命令前綴: {COMMAND_PREFIX}")

# 載入配置
jData = load_config('setting.json')
logger.info("已載入配置文件")

# 設置完整的意圖
intents = discord.Intents.all()  # 啟用所有意圖
logger.info("已啟用所有 Discord 意圖")

# 實例化機器人
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
logger.info(f"使用 {COMMAND_PREFIX} 作為命令前綴初始化機器人")

# 記錄未處理的異常
@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"未處理的錯誤: {event}", exc_info=True)

# 添加消息處理錯誤處理
@bot.event
async def on_command_error(ctx, error):
    logger.error(f"命令錯誤: {error}", exc_info=True)
    try:
        await ctx.send(f"命令執行錯誤: {error}")
    except:
        pass
        
# 添加更詳細的消息處理調試
@bot.event
async def on_message(message):
    # 確保機器人不會響應自己的消息
    if message.author.id == bot.user.id:
        return
        
    # 記錄收到的消息
    logger.debug(f"主程序收到消息: {message.content} 從 {message.author}")
    
    # 讓命令處理器有機會處理這條消息
    await bot.process_commands(message)

# 機器人就緒事件
@bot.event
async def on_ready():
    logger.info(f"機器人已啟動: {bot.user.name} ({bot.user.id})")
    await load_cogs()
    logger.info("已加載所有Cogs")
    
    # 設置機器人狀態
    try:
        activity = discord.Activity(type=discord.ActivityType.watching, name="大家的消息")
        await bot.change_presence(activity=activity)
        logger.info("已設置機器人狀態")
    except Exception as e:
        logger.error(f"設置機器人狀態失敗: {e}")
    
    # 啟動緩存清理任務
    try:
        cleanup_interval_str = os.getenv('CACHE_CLEANUP_INTERVAL', '3600')
        # 確保值是數字，去除可能的註釋或空格
        if '#' in cleanup_interval_str:
            cleanup_interval_str = cleanup_interval_str.split('#')[0].strip()
        cleanup_interval = int(cleanup_interval_str)
        cache_cleanup_task = start_cleanup_task(cleanup_interval)
        logger.info(f"緩存清理任務已啟動，間隔: {cleanup_interval}秒")
    except (ValueError, TypeError) as e:
        # 使用默認值
        cleanup_interval = 3600
        cache_cleanup_task = start_cleanup_task(cleanup_interval)
        logger.warning(f"無法解析CACHE_CLEANUP_INTERVAL值，使用預設值 {cleanup_interval} 秒: {e}")
    
    # 列出已加載的命令
    commands_list = [cmd.name for cmd in bot.commands]
    logger.info(f"已加載的命令: {', '.join(commands_list)}")
    
    # 列出所有連接的伺服器
    guilds = [guild.name for guild in bot.guilds]
    logger.info(f"已連接的伺服器: {', '.join(guilds)}")

# 載入擴展模組
async def load_cogs():
    # 加載命令模組目錄中的所有模組
    cog_count = 0
    for fileName in os.listdir('./cmds'):
        if fileName.endswith('.py'):
            try:
                await bot.load_extension(f'cmds.{fileName[:-3]}')
                logger.info(f"已加載模組: {fileName}")
                cog_count += 1
            except Exception as e:
                logger.error(f"加載模組 {fileName} 失敗: {str(e)}", exc_info=True)
    
    logger.info(f"成功加載 {cog_count} 個模組")
    return cog_count > 0

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
    try:
        # 從環境變數讀取重啟時間
        restart_time = os.getenv('RESTART_TIME', '03:00')
        
        # 確保時間格式正確 (HH:MM)
        if restart_time and not restart_time.strip() == "":
            # 處理可能的註釋
            if '#' in restart_time:
                restart_time = restart_time.split('#')[0].strip()
                
            # 簡單格式檢查
            parts = restart_time.split(':')
            if len(parts) >= 2:
                hour = int(parts[0])
                minute = int(parts[1])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    formatted_time = f"{hour:02d}:{minute:02d}"
                    # 每天指定時間重啟機器人
                    schedule.every().day.at(formatted_time).do(scheduled_restart)
                    logger.info(f"已設置定時重啟任務，時間: {formatted_time}")
                    return
        
        # 如果時間格式不正確，使用預設值
        logger.warning(f"重啟時間格式不正確: '{restart_time}'，使用預設值 03:00")
        schedule.every().day.at("03:00").do(scheduled_restart)
        logger.info("已設置定時重啟任務，時間: 03:00 (預設值)")
    except Exception as e:
        logger.error(f"設置定時任務出錯: {e}，使用預設值 03:00")
        try:
            schedule.every().day.at("03:00").do(scheduled_restart)
            logger.info("已設置定時重啟任務，時間: 03:00 (預設值)")
        except Exception as ex:
            logger.critical(f"無法設置定時任務: {ex}")
            # 繼續執行不中斷主程序

if __name__ == '__main__':
    try:
        # 檢查是否有其他實例在運行
        try:
            # 嘗試綁定到一個特定端口，用於檢測重複實例
            instance_check_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            instance_check_socket.bind(('localhost', 5123))
            # 釋放端口
            instance_check_socket.close()
        except socket.error:
            logger.critical("另一個機器人實例已經在運行。請先關閉現有實例。")
            exit(1)
        
        # 啟動網頁服務保持機器人在線 (如果啟用)
        if os.environ.get('NO_WEB_SERVER', '').lower() != 'true':
            try:
                import keep_alive
                keep_alive.keep_alive()
                logger.info("已啟動保活服務")
            except Exception as e:
                logger.warning(f"keep_alive 模組錯誤: {e}，以無 Web 服務模式運行")
        else:
            logger.info("以無 Web 服務模式運行 (NO_WEB_SERVER=True)")
        
        # 設置定時任務
        setup_schedule()
        
        # 運行機器人
        loop = asyncio.new_event_loop()  # 創建新的事件循環
        asyncio.set_event_loop(loop)
        
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

