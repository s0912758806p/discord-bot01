#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import discord
import asyncio
import unittest
from unittest.mock import Mock, patch, AsyncMock
from cmds.event import Event

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
        
async def test_commands():
    print("Testing Event module commands...")
    
    # Create mock bot and event module
    bot = MockBot()
    event_cog = Event(bot)
    
    # Test all command handlers
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
    
    # Test basic commands with mock messages
    for cmd, handler in commands_to_test.items():
        print(f"Testing command: {cmd}")
        mock_msg = MockMessage(cmd)
        try:
            await handler(mock_msg)
            print(f"✅ Command {cmd} executed without errors")
        except Exception as e:
            print(f"❌ Command {cmd} failed: {e}")
            
    # Test special prefix commands
    special_commands = [
        "!今日運勢-牡羊座",
        "!今日運勢-金牛座",
        "??:",
        "??:我今天會有好運嗎"
    ]
    
    for cmd in special_commands:
        print(f"Testing special command: {cmd}")
        mock_msg = MockMessage(cmd)
        try:
            await event_cog.on_message(mock_msg)
            print(f"✅ Special command {cmd} executed without errors")
        except Exception as e:
            print(f"❌ Special command {cmd} failed: {e}")
    
    # Test waffle mix commands
    waffle_commands = [
        "!鬆餅混搭 甜+鹹",
        "!鬆餅混搭 甜+炸",
        "!鬆餅混搭 鹹+炸"
    ]
    
    for cmd in waffle_commands:
        print(f"Testing waffle mix command: {cmd}")
        mock_msg = MockMessage(cmd)
        try:
            await event_cog.process_default_responses(mock_msg)
            print(f"✅ Waffle mix command {cmd} executed without errors")
        except Exception as e:
            print(f"❌ Waffle mix command {cmd} failed: {e}")
            
    # Test other default responses
    default_responses = [
        "你不懂啦",
        "是嗎?",
        "哦嚯",
        "血流成河",
        "!各位集合"
    ]
    
    for cmd in default_responses:
        print(f"Testing default response: {cmd}")
        mock_msg = MockMessage(cmd)
        try:
            await event_cog.process_default_responses(mock_msg)
            print(f"✅ Default response {cmd} executed without errors")
        except Exception as e:
            print(f"❌ Default response {cmd} failed: {e}")
            
    print("Testing completed!")

if __name__ == "__main__":
    asyncio.run(test_commands()) 