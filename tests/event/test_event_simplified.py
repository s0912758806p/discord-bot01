#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import discord
import asyncio
import json
import os
from unittest.mock import Mock, AsyncMock

# Create a mock version of the Event class to test commands
class MockBot:
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.cogs = {}
        self.get_channel = Mock(return_value=MockChannel())
        
class MockChannel:
    def __init__(self):
        self.name = "test-channel"
        self.send = AsyncMock()
        
class MockUser:
    def __init__(self):
        self.bot = False
        self.nick = "TestUser"
        self.name = "TestUser"
        
class MockMessage:
    def __init__(self, content=""):
        self.author = MockUser()
        self.content = content
        self.channel = MockChannel()
        
class SimplifiedEvent:
    def __init__(self, bot):
        self.bot = bot
        # Load settings
        if os.path.exists('setting.json'):
            with open('setting.json', 'r', encoding='utf-8') as f:
                self.jData = json.load(f)
        else:
            # Create minimal default settings
            self.jData = {
                "IMAGE": ["test.png"] * 30,
                "QIAN": ["test.png"] * 60,
                "YIYAN": ["test.png"] * 5,
                "ON_WORK": ["Test on work message"],
                "OFF_WORK": ["Test off work message"],
                "MATCHLIST": ["確實"]
            }
            
        # Mocked session for HTTP requests
        self.session = Mock()
        self.session.get = AsyncMock()
        response_mock = AsyncMock()
        response_mock.status = 200
        response_mock.text = AsyncMock(return_value="<html><body><div class='CurrentConditions--location--1YWj_'>Test Location</div><div class='CurrentConditions--tempValue--MHmYY'>20°C</div><div class='CurrentConditions--phraseValue--mZC_p'>Sunny</div><div class='TodayDetailsCard--feelsLikeTempValue--2icPt'>22°C</div><div class='CurrentConditions--tempHiLoValue--3T1DG'>18°C/24°C</div></body></html>")
        response_context = AsyncMock()
        response_context.__aenter__ = AsyncMock(return_value=response_mock)
        response_context.__aexit__ = AsyncMock(return_value=None)
        self.session.get.return_value = response_context
        
        # Setup waffle lists
        self.tiansongbingList = [
            '蜂蜜鬆餅', '抹茶鬆餅', '藍莓鬆餅', '鮮奶油鬆餅', '花生鬆餅'
        ]
        self.xiansongbingList = [
            '起司玉米蔬菜鬆餅', '牛肉漢堡蔬菜鬆餅', '培根起司蔬菜鬆餅'
        ]
        self.zhasongbingList = [
            '薯餅起司蔬菜鬆餅', '黃金豬排起司蔬菜鬆餅'
        ]
        
        # Define star types
        self.STAR_TYPE_MAP = {
            '牡羊座': 'aries',
            '金牛座': 'taurus',
            '雙子座': 'gemini',
            '巨蟹座': 'cancer',
            '獅子座': 'leo',
            '處女座': 'virgo',
            '天秤座': 'libra',
            '天蠍座': 'scorpio',
            '射手座': 'sagittarius',
            '摩羯座': 'capricorn',
            '水瓶座': 'aquarius',
            '雙魚座': 'pisces',
        }
        
    async def get_weather(self, msg):
        """獲取天氣信息 Mock 實現"""
        await msg.channel.send("模擬天氣信息: 臺北市, 溫度: 25°C, 晴天")
        print("✅ 天氣命令已執行")
        
    async def temple_draw_a(self, msg):
        """城隍廟抽籤功能 Mock 實現"""
        await msg.channel.send("模擬抽中第5籤")
        print("✅ 抽籤A命令已執行")
        
    async def temple_draw_b(self, msg):
        """淺草寺觀音廟抽籤功能 Mock 實現"""
        await msg.channel.send("模擬抽中第38籤")
        print("✅ 抽籤B命令已執行")
        
    async def sweet_waffle(self, msg):
        """處理甜味鬆餅命令"""
        await msg.channel.send(self.tiansongbingList[0])
        print("✅ 甜味鬆餅命令已執行")
        
    async def savory_waffle(self, msg):
        """處理鹹味鬆餅命令"""
        await msg.channel.send(self.xiansongbingList[0])
        print("✅ 鹹味鬆餅命令已執行")
        
    async def fried_waffle(self, msg):
        """處理炸物鬆餅命令"""
        await msg.channel.send(self.zhasongbingList[0])
        print("✅ 炸物鬆餅命令已執行")
        
    async def on_work(self, msg):
        """處理上班命令"""
        await msg.channel.send(self.jData['ON_WORK'][0])
        print("✅ 上班命令已執行")
        
    async def off_work(self, msg):
        """處理下班命令"""
        await msg.channel.send(self.jData['OFF_WORK'][0])
        print("✅ 下班命令已執行")
        
    async def afternoon_tea(self, msg):
        """處理下午茶命令"""
        await msg.channel.send('https://dinbendon.net/do/')
        print("✅ 下午茶命令已執行")
        
    async def axi_photo(self, msg):
        """處理阿希照片命令"""
        await msg.channel.send('叫我幹嘛?')
        print("✅ 阿希照片命令已執行")
        
    async def horoscope_help(self, msg):
        """處理星座編號命令"""
        await msg.channel.send("[aries]牡羊座 [taurus]金牛座...")
        print("✅ 星座編號命令已執行")
        
    async def horoscope_intro(self, msg):
        """處理今日運勢介紹命令"""
        await msg.channel.send('想查詢運勢嗎? 請輸入!今日運勢-星座, 如:!今日運勢-天秤座')
        print("✅ 今日運勢命令已執行")
        
    async def horoscope(self, msg):
        """處理今日運勢命令"""
        star_sign = msg.content.replace('!今日運勢-', '')
        await msg.channel.send(f'模擬今日{star_sign}的運勢：\n今天適合...')
        print(f"✅ 今日運勢-{star_sign}命令已執行")
    
    async def process_qian_command(self, msg):
        """處理淺草籤相關命令"""
        if msg.content == '??:':
            await msg.channel.send("嘿！有什麼問題嗎？")
        else:
            question = msg.content[3:].strip()
            await msg.channel.send(f"對於問題「{question}」的回答：\n讓我想想...應該是這樣：")
        print("✅ 抽籤命令已執行")
        
    async def process_default_responses(self, msg):
        """處理一系列固定回應的命令"""
        # 鬆餅混搭命令
        if msg.content in ('!鬆餅混搭 甜+鹹', '!鬆餅混搭 鹹+甜'):
            await msg.channel.send(f"{self.tiansongbingList[0]}+{self.xiansongbingList[0]}")
            print("✅ 鬆餅混搭甜+鹹命令已執行")
            return True
            
        elif msg.content in ('!鬆餅混搭 甜+炸', '!鬆餅混搭 炸+甜'):
            await msg.channel.send(f"{self.tiansongbingList[0]}+{self.zhasongbingList[0]}")
            print("✅ 鬆餅混搭甜+炸命令已執行")
            return True
            
        elif msg.content in ('!鬆餅混搭 鹹+炸', '!鬆餅混搭 炸+鹹'):
            await msg.channel.send(f"{self.xiansongbingList[0]}+{self.zhasongbingList[0]}")
            print("✅ 鬆餅混搭鹹+炸命令已執行")
            return True
            
        # 檢查匹配列表響應
        if msg.content in self.jData.get('MATCHLIST', []):
            await msg.channel.send("匹配列表回應")
            print("✅ 匹配列表回應已執行")
            return True
        
        # 其他特定回應
        other_responses = {
            '你不懂啦': "你不懂回應",
            '是嗎?': "是嗎回應",
            '哦嚯': "哦嚯回應",
            '血流成河': "血流成河回應",
            '!各位集合': "集合回應"
        }
        
        if msg.content in other_responses:
            await msg.channel.send(other_responses[msg.content])
            print(f"✅ {msg.content}命令已執行")
            return True
            
        return False
    
    async def on_message(self, msg):
        """處理消息事件"""
        # 忽略機器人自己的消息
        if msg.author.bot:
            return
            
        # 處理特殊前綴命令
        if msg.content.startswith('!今日運勢-'):
            print("處理今日運勢命令")
            await self.horoscope(msg)
            return
            
        # 處理淺草籤命令
        if msg.content == '??:' or msg.content.startswith('??:'):
            print(f"處理抽籤命令: {msg.content}")
            await self.process_qian_command(msg)
            return
            
        # 嘗試處理其他回應
        processed = await self.process_default_responses(msg)
        if processed:
            return
            
        print(f"未處理的命令: {msg.content}")

async def test_commands():
    print("\n====== 開始測試簡化版Event命令 ======\n")
    
    # 創建模擬機器人和事件模組
    bot = MockBot()
    event_cog = SimplifiedEvent(bot)
    
    # 測試所有命令處理器
    commands_to_test = {
        "!天氣": event_cog.get_weather,
        "!抽籤A": event_cog.temple_draw_a,
        "!抽籤B": event_cog.temple_draw_b,
        "!甜味鬆餅": event_cog.sweet_waffle,
        "!鹹味鬆餅": event_cog.savory_waffle,
        "!炸物鬆餅": event_cog.fried_waffle,
        "!上班": event_cog.on_work,
        "!下班": event_cog.off_work,
        "!下午茶": event_cog.afternoon_tea,
        "!阿希": event_cog.axi_photo,
        "!阿希照片": event_cog.axi_photo,
        "!星座編號": event_cog.horoscope_help,
        "!今日運勢": event_cog.horoscope_intro,
    }
    
    # 測試基本命令
    print("\n----- 測試基本命令 -----\n")
    for cmd, handler in commands_to_test.items():
        print(f"測試命令: {cmd}")
        mock_msg = MockMessage(cmd)
        try:
            await handler(mock_msg)
        except Exception as e:
            print(f"❌ 命令 {cmd} 失敗: {e}")
            
    # 測試特殊前綴命令
    print("\n----- 測試特殊前綴命令 -----\n")
    special_commands = [
        "!今日運勢-牡羊座",
        "!今日運勢-金牛座",
        "??:",
        "??:我今天會有好運嗎"
    ]
    
    for cmd in special_commands:
        print(f"測試特殊命令: {cmd}")
        mock_msg = MockMessage(cmd)
        try:
            await event_cog.on_message(mock_msg)
        except Exception as e:
            print(f"❌ 特殊命令 {cmd} 失敗: {e}")
    
    # 測試鬆餅混搭命令
    print("\n----- 測試鬆餅混搭命令 -----\n")
    waffle_commands = [
        "!鬆餅混搭 甜+鹹",
        "!鬆餅混搭 甜+炸",
        "!鬆餅混搭 鹹+炸"
    ]
    
    for cmd in waffle_commands:
        print(f"測試鬆餅混搭命令: {cmd}")
        mock_msg = MockMessage(cmd)
        try:
            await event_cog.process_default_responses(mock_msg)
        except Exception as e:
            print(f"❌ 鬆餅混搭命令 {cmd} 失敗: {e}")
            
    # 測試其他默認回應
    print("\n----- 測試其他默認回應 -----\n")
    default_responses = [
        "你不懂啦",
        "是嗎?",
        "哦嚯",
        "血流成河",
        "!各位集合"
    ]
    
    for cmd in default_responses:
        print(f"測試默認回應: {cmd}")
        mock_msg = MockMessage(cmd)
        try:
            await event_cog.process_default_responses(mock_msg)
        except Exception as e:
            print(f"❌ 默認回應 {cmd} 失敗: {e}")
            
    print("\n====== 測試完成 ======\n")

if __name__ == "__main__":
    asyncio.run(test_commands()) 