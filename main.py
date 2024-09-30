import discord
import json
import os
import keep_alive
import asyncio
import schedule
import time

from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('TOKEN')

# 'r' = read
with open('setting.json', 'r', encoding='utf8') as jFile:
    jData = json.load(jFile)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# 實例化 commands.Bot 而不是 discord.Client
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    # await self.load_model()
    print('BOT is online, 模型加载完成！')
    await load_cogs()
    print('Cogs loaded.')


async def run_bot():
    await bot.start(TOKEN)


async def load_cogs():
    for fileName in os.listdir('./cmds'):
        if fileName.endswith('.py'):
            try:
                await bot.load_extension(f'cmds.{fileName[:-3]}')
                print(f'Loaded cog: {fileName}')
            except Exception as e:
                print(f'Failed to load cog {fileName}: {e}')

    # 檢查 Event 是否已加載
    if hasattr(bot, 'get_cog'):
        event_cog = bot.get_cog('Event')
        if event_cog is None:
            print('Event Cog is not loaded.')
        else:
            print('Event Cog is loaded.')


def job():
    print("重新啟動機器人...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(run_bot())
    loop.run_until_complete(asyncio.sleep(5))
    loop.stop()


if __name__ == '__main__':
    keep_alive.keep_alive()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_bot())
    
    # 這裡只需運行定時任務的循環
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        loop.run_until_complete(bot.close())  # 確保關閉機器人

