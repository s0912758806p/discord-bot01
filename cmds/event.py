import discord
import random
import aiohttp
import datetime
import asyncio
from typing import Dict, List, Set, Callable, Any, Optional, Union
from discord.ext import commands
from core.classes import Cog_Extension
from bs4 import BeautifulSoup
from opencc import OpenCC
from core.config import load_config
from core.cache import cache
from core.logging import logger, log_command, measure_time

# 載入配置
jData = load_config('setting.json')

class Event(Cog_Extension):
    # 類常量
    PUQIAN: List[str] = [
        "../assets/img/puqian/large_fierce.png",
        "../assets/img/puqian/normal_fierce.png",
        "../assets/img/puqian/small_fierce.png",
        "../assets/img/puqian/large_lucky.png",
        "../assets/img/puqian/medium_lucky.png",
        "../assets/img/puqian/normal_lucky.png",
        "../assets/img/puqian/small_lucky.png",
        "../assets/img/puqian/super_large_lucky.png"
    ]
    
    BEILAN: List[str] = [
        "你認真的嗎？🤨", "這聽起來有點扯。🙄", "你在開玩笑吧？😏", "這真的是你的結論嗎？🤔", "你確定這是真的？😒",
        "這聽起來像是編的。🤥", "你是不是搞錯了？😕", "這樣說有點牽強吧。🙄", "這種說法太過分了吧。��",
        "你以為我會相信嗎？😑", "你的證據呢？🧐", "這種話你也能說出口？😒", "你在逗我嗎？😂", "這種說法太荒謬了。😲",
        "你是不是故意挑釁我？😡", "這是你聽來的吧？👂", "這麼說太過頭了吧。😤", "你以為這樣我會相信嗎？😏",
        "這話有點站不住腳。🤨", "你在玩哪一出啊？🤔", "這樣也能信？😒", "你認為我會上當嗎？😤", "這真的是你相信的？😳",
        "你的說法有點荒唐。🙄", "你是在騙誰？🤥", "這聽起來完全不合理。🤷", "你是不是在搞笑？😂", "這話也太誇張了吧。😆",
        "你真的相信這個？😒", "這樣說也太牽強了。🙄", "你是在故意激怒我嗎？��", "這話根本不可信。😑", "你這話沒道理啊。🤨",
        "你以為我會被這種話騙到嗎？😏", "這種說法太牽強。🤷", "你這是在胡說八道嗎？🤥", "你這話太荒謬了。😲",
        "你確定不是在開玩笑？😂", "這話完全站不住腳。🤨", "你這是從哪裡聽來的？👂", "這種說法太離譜了。🙄",
        "你這話太過分了。😠", "你以為這樣我會相信？😑", "你這是在找茬嗎？😒", "這話根本不合邏輯。🤔", "你這是在故意挑釁嗎？😡",
        "這聽起來像是編造的。🤥", "你這話完全不可信。😑", "這種說法太牽強附會。🤷", "你這是在亂說嗎？��",
        "你這話太扯了。🙄", "這種說法太誇張。😆", "你這是在逗我吧？😂", "這話根本不合常理。🤔", "你這是在瞎說吧？🤥",
        "這話太不可思議了。😲", "你這話根本沒道理。🤨", "這話完全不合理。🤷", "你這是在開玩笑吧？😂", "這話根本站不住腳。��",
        "你這話太過分。😠", "你這是在挑釁我吧？😡", "這話完全不合邏輯。🤔", "你這是在說笑嗎？😆", "你這話太離譜。🙄",
        "這種說法完全不可信。😑", "你這話太荒唐。😲", "這話根本不合常理。🤔", "你這是在瞎編嗎？🤥", "這話完全沒道理。🤨",
        "你這話太誇張。😆", "你這話太扯。🙄", "這話根本不合邏輯。🤔", "你這是在開玩笑嗎？😂", "這話太荒謬。😲",
        "你認為我會信這種鬼話？😏", "這話有點太誇張了吧。🙄", "這種話你也說得出口？😒", "你這是在瞎扯嗎？🤥", "這樣說根本不合理。🤷",
        "你這話根本沒有根據。🤨", "這種說法完全站不住腳。🙄", "你這是在故意搞事吧？😡", "這話聽起來完全不可信。😑",
        "你這是在編故事嗎？📝", "這聽起來像是陰謀論。🕵️", "你是在捉弄我嗎？🙃", "這說法真是匪夷所思。😵", "你這是在吹牛嗎？🤥",
        "這種說法讓人無法相信。😐", "你這是在開大玩笑吧？😜", "這種話誰會信？🤨", "你這是在瞎掰嗎？😅", ":)", ":))", "BAD!", "這簡直錦上添花:)", "尋龍分金看纏山，一重纏是一重關。關門如有八分險，不出陰陽八卦形。勸施主還是回頭是岸吧。🤨", "不要。😡", "😡", "🥵", "HSO🥵"
    ]
    
    GREETINGS: List[str] = [
        "嘿！有什麼問題嗎？", "嗨！我可以幫你解答什麼問題？", 
        "Hello！需要我的幫助嗎？", "尊敬的閣下，有什麼需要提問的？",
        "我已經準備好了，說吧。"
    ]
    
    RANDOM_RESPONSES: List[str] = [
        "我只剩下這個答案給你：", "看看這個：", "讓我想想...應該是這樣：", 
        "嗯，我覺得這個比較接近：", "你還是面對現實吧:", "或許你會想要這個:", 
        "要來咯！要來咯!", "想不到吧，我的回答是這個:", "聽我一句勸："
    ]
    
    STAR_TYPE_MAP: Dict[str, str] = {
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
    
    def __init__(self, bot):
        super().__init__(bot)
        self.session = None
        self.training_mode = False
        
        # 將配置數據提前處理為更高效的數據結構
        try:
            chatroom_value = jData.get('CHATROOM01', '0')
            # 處理可能的註釋
            if isinstance(chatroom_value, str):
                if '#' in chatroom_value:
                    chatroom_value = chatroom_value.split('#')[0].strip()
                # 確保有值，否則使用默認值
                if not chatroom_value or chatroom_value == '':
                    chatroom_value = '0'
            self.chatroom_id = int(chatroom_value)
            logger.info(f"已設置聊天室ID: {self.chatroom_id}")
        except (ValueError, TypeError) as e:
            logger.error(f"無法解析聊天室ID: {e}")
            self.chatroom_id = 0  # 使用默認值
        self.match_set = set(jData.get('MATCHLIST', []))
        self.tiansongbingList = jData.get('tiansongbingList', [
            '蜂蜜鬆餅', '抹茶鬆餅', '藍莓鬆餅', '鮮奶油鬆餅', '花生鬆餅', '巧克力鬆餅', '榛果巧克力鬆餅',
            '蜂蜜鮮奶油鬆餅', '法式檸檬奶霜鬆餅', '香草卡士達鬆餅', '葡萄奶酥鬆餅', '藍莓巧克力鬆餅', '巧克力鮮奶油鬆餅',
            '巧克力香蕉鬆餅', '巧克力卡士達鬆餅', '抹茶紅豆鬆餅'
        ])
        self.xiansongbingList = jData.get('xiansongbingList', [
            '起司玉米蔬菜鬆餅', '牛肉漢堡蔬菜鬆餅', '培根起司蔬菜鬆餅', '鮪魚沙拉蔬菜鬆餅', '勁辣雞蔬菜鬆餅',
            '紐奧良雞蔬菜鬆餅', '燻雞蔬菜鬆餅', '碳烤雞腿蔬菜鬆餅', '芝士牛堡蔬菜鬆餅', '墨西哥辣椒牛肉蔬菜鬆餅',
            '韓味香辣雞腿蔬菜鬆餅', '培根花生牛肉堡蔬菜鬆餅', '海陸雙拼(牛堡+鮪魚沙拉)', '海陸雙拼(韓味雞+鮪魚沙拉)'
        ])
        self.zhasongbingList = jData.get('zhasongbingList', [
            '薯餅起司蔬菜鬆餅', '黃金豬排起司蔬菜鬆餅', '辣味咔啦雞起司蔬菜鬆餅', '原味咔啦雞起司蔬菜鬆餅'
        ])
        
        # 命令處理器映射
        self.command_handlers = {
            '!天氣': self.get_weather,
            '!抽籤A': self.temple_draw_a,
            '!抽籤B': self.temple_draw_b,
            '!甜味鬆餅': self.sweet_waffle,
            '!鹹味鬆餅': self.savory_waffle,
            '!炸物鬆餅': self.fried_waffle,
            '!上班': self.on_work,
            '!下班': self.off_work,
            '!下午茶': self.afternoon_tea,
            '!阿希': self.axi_photo,
            '!阿希照片': self.axi_photo,
            '!星座編號': self.horoscope_help,
            '!今日運勢': self.horoscope_intro,
        }
        
    async def cog_load(self):
        """加載模組時調用"""
        # 創建aiohttp會話
        self.session = aiohttp.ClientSession()
        logger.info("Event 模組已加載")
        
    async def cog_unload(self):
        """卸載模組時調用"""
        # 關閉aiohttp會話
        if self.session is not None:
            await self.session.close()
            logger.info("Event 模組已卸載，關閉 session")
    
    async def fetch_with_retry(self, url: str, max_retries: int = 3) -> Optional[str]:
        """帶重試機制的網頁請求函數"""
        for attempt in range(max_retries):
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
                    logger.warning(f"請求失敗，狀態碼: {response.status}，嘗試 {attempt+1}/{max_retries}")
                await asyncio.sleep(1)  # 重試前等待
            except Exception as e:
                logger.warning(f"請求失敗 (嘗試 {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise
        return None
        
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """當新成員加入時發送訊息"""
        try:
            channel = self.bot.get_channel(self.chatroom_id)
            if channel:
                await channel.send(f'{member} 出現啦!')
                logger.info(f"新成員加入: {member}")
        except Exception as e:
            logger.error(f"處理成員加入事件時發生錯誤: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """當成員離開時發送訊息"""
        try:
            channel = self.bot.get_channel(self.chatroom_id)
            if channel:
                await channel.send(f'{member} 離開了!')
                logger.info(f"成員離開: {member}")
        except Exception as e:
            logger.error(f"處理成員離開事件時發生錯誤: {e}")

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        """處理消息事件"""
        # 忽略機器人自己的消息
        if msg.author.bot:
            return
            
        # 記錄所有訊息
        realname = msg.author.nick or msg.author.name
        logger.info(f"{msg.channel.name}-{realname}: {msg.content}")
        
        # 訓練模式切換
        if msg.content.strip() == "!!啟動":
            self.training_mode = True
            await msg.channel.send("好的，已經啟動了。")
            logger.info("訓練模式已啟動")
            return

        if msg.content.strip() == "!!關閉":
            self.training_mode = False
            await msg.channel.send("好的，已經關閉了。")
            logger.info("訓練模式已關閉")
            return

        # 檢查映射表中的命令
        handler = self.command_handlers.get(msg.content)
        if handler:
            logger.info(f"執行映射命令處理器: {handler.__name__}")
            await handler(msg)
            return
            
        # 處理特殊前綴命令
        if msg.content.startswith('!今日運勢-'):
            logger.info("處理今日運勢命令")
            await self.horoscope(msg)
            return
            
        # 處理淺草籤命令
        if msg.content == '??:' or msg.content.startswith('??:'):
            logger.info(f"處理抽籤命令: {msg.content}")
            await self.process_qian_command(msg)
            return
            
        # 嘗試並行處理其他回應
        logger.debug(f"檢查默認回應處理: {msg.content}")
        await self.process_default_responses(msg)
        
        # 確保標準命令處理也正常進行
        await self.bot.process_commands(msg)
        
    async def sweet_waffle(self, msg: discord.Message) -> None:
        """處理甜味鬆餅命令"""
        await msg.channel.send(random.choice(self.tiansongbingList))
        
    async def savory_waffle(self, msg: discord.Message) -> None:
        """處理鹹味鬆餅命令"""
        await msg.channel.send(random.choice(self.xiansongbingList))
        
    async def fried_waffle(self, msg: discord.Message) -> None:
        """處理炸物鬆餅命令"""
        await msg.channel.send(random.choice(self.zhasongbingList))
        
    async def on_work(self, msg: discord.Message) -> None:
        """處理上班命令"""
        await msg.channel.send(random.choice(jData['ON_WORK']))
        
    async def off_work(self, msg: discord.Message) -> None:
        """處理下班命令"""
        await msg.channel.send(random.choice(jData['OFF_WORK']))
        
    async def afternoon_tea(self, msg: discord.Message) -> None:
        """處理下午茶命令"""
        await msg.channel.send('https://dinbendon.net/do/')
        
    async def axi_photo(self, msg: discord.Message) -> None:
        """處理阿希照片命令"""
        await msg.channel.send('叫我幹嘛?')
        await msg.channel.send(file=discord.File(jData['IMAGE'][15]))
        
    async def horoscope_help(self, msg: discord.Message) -> None:
        """處理星座編號命令"""
        questionDescription = "[aries]牡羊座 [taurus]金牛座 [gemini]雙子座 [cancer]巨蟹座 [leo]獅子座 [virgo]處女座 [libra]天秤座 [scorpio]天蠍座 [sagittarius]射手座 [capricorn]摩羯座 [aquarius]水瓶座 [pisces]雙魚座，請選擇星座(僅能填英文):"
        await msg.channel.send(questionDescription)
        
    async def horoscope_intro(self, msg: discord.Message) -> None:
        """處理今日運勢介紹命令"""
        await msg.channel.send('想查詢運勢嗎? 請輸入!今日運勢-星座, 如:!今日運勢-天秤座')
        
    async def process_qian_command(self, msg: discord.Message) -> None:
        """處理淺草籤相關命令"""
        try:
            logger.info(f"處理抽籤命令內容: {msg.content}")
            if msg.content == '??:':
                greeting = random.choice(self.GREETINGS)
                logger.info(f"發送問候: {greeting}")
                await msg.channel.send(greeting)
            else:
                # 獲取問題內容
                question = msg.content[3:].strip()
                logger.info(f"抽籤問題: {question}")
                
                rangeNum = random.randint(1, 10)
                logger.info(f"抽籤隨機數: {rangeNum}")
                
                if rangeNum < 9:
                    response = random.choice(self.RANDOM_RESPONSES)
                    logger.info(f"發送抽籤回應: {response}")
                    await msg.channel.send(response)
                    
                    # 確保文件路徑存在
                    img_path = self.PUQIAN[rangeNum - 1]
                    logger.info(f"發送抽籤圖片: {img_path}")
                    
                    try:
                        await msg.channel.send(file=discord.File(img_path))
                    except Exception as e:
                        logger.error(f"發送抽籤圖片失敗: {e}, 路徑: {img_path}")
                        await msg.channel.send(f"抱歉，無法載入圖片。錯誤: {e}")
                else:
                    response = random.choice(self.BEILAN)
                    logger.info(f"發送貝蘭回應: {response}")
                    await msg.channel.send(response)
        except Exception as e:
            logger.error(f"處理抽籤命令時出錯: {e}", exc_info=True)
            try:
                await msg.channel.send(f"抱歉，處理命令時出錯: {e}")
            except:
                pass
                
    @measure_time
    @cache(ttl=1800)  # 30分鐘緩存
    async def get_weather(self, msg: discord.Message) -> None:
        """獲取天氣信息，帶30分鐘緩存"""
        try:
            url = 'https://weather.com/zh-TW/weather/today/l/fe7393b7f2c8eed2cf692bd079361df362d9f0c1c0f896e6e46a649295e15c7d'
            hourStatusUrl = 'https://weather.com/zh-TW/weather/hourbyhour/l/fe7393b7f2c8eed2cf692bd079361df362d9f0c1c0f896e6e46a649295e15c7d'
            
            # 使用並行請求獲取數據
            text, hourText = await asyncio.gather(
                self.fetch_with_retry(url),
                self.fetch_with_retry(hourStatusUrl)
            )
            
            if not text:
                await msg.channel.send("獲取天氣數據失敗")
                return
                
            soup = BeautifulSoup(text, 'html.parser')
            
            name = soup.select('.region-main .CurrentConditions--location--1YWj_')[0].text
            temper = soup.select('.region-main .CurrentConditions--tempValue--MHmYY')[0].text
            status = soup.select('.region-main .CurrentConditions--phraseValue--mZC_p')[0].text
            bodyFeeling = soup.select('.region-main .TodayDetailsCard--feelsLikeTempValue--2icPt')[0].text
            heighAndLow = soup.select('.region-main .CurrentConditions--tempHiLoValue--3T1DG')[0].text
            
            if hourText:
                hourSoup = BeautifulSoup(hourText, 'html.parser')
                date = hourSoup.select('.region-main .HourlyForecast--longDate--J_Pdh')[0].text
            else:
                date = "今日"
                
            await msg.channel.send(date + '\n' + '地區: ' + name + '\n' +
                                heighAndLow + '\n' + '目前溫度: ' + temper +
                                '\n' + '體感溫度: ' + bodyFeeling + '\n' +
                                '氣候: ' + status + '\n')
        except Exception as e:
            logger.error(f"獲取天氣信息時出錯: {e}")
            await msg.channel.send(f"獲取天氣信息時出錯，請稍後再試")
            
    @cache(ttl=86400)  # 24小時緩存
    async def get_horoscope_data(self, star_sign: str) -> Optional[str]:
        """獲取星座運勢數據，帶24小時緩存"""
        try:
            url = f'https://m.xzw.com/fortune/{self.STAR_TYPE_MAP[star_sign]}/'
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    return None
                    
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                horoscope = soup.find(class_='cont').text.strip().replace('。', '。\n')
                cc = OpenCC('s2t')
                return cc.convert(horoscope)
        except Exception as e:
            logger.error(f"獲取星座 {star_sign} 運勢數據時出錯: {e}")
            return None
            
    async def horoscope(self, msg: discord.Message) -> None:
        """處理今日運勢命令"""
        try:
            star_sign = msg.content.replace('!今日運勢-', '')
            
            if star_sign not in self.STAR_TYPE_MAP:
                await msg.channel.send(f"未知的星座: {star_sign}，請使用正確的星座名稱")
                return
                
            horoscope_text = await self.get_horoscope_data(star_sign)
            
            if horoscope_text:
                await msg.channel.send(f'今日{star_sign}的運勢：\n{horoscope_text}')
            else:
                await msg.channel.send("獲取星座運勢失敗，請稍後再試")
        except Exception as e:
            logger.error(f"處理星座運勢時出錯: {e}")
            await msg.channel.send("獲取星座運勢時出錯，請稍後再試")

    @measure_time
    async def temple_draw_a(self, msg: discord.Message) -> None:
        """城隍廟抽籤功能 - 優化版"""
        try:
            qianRandomNum = random.randint(1, 60)
            
            qianUrl = f'http://www.citygod.tw/fortune.php?ans={qianRandomNum}'
            
            await msg.channel.send(f'抽中第{qianRandomNum}籤')
            
            # 優化：直接計算抽籤結果，而不是循環100次
            # 計算3次成功的概率 (2/3)^3 ≈ 0.296
            if random.random() < 0.296:  # 約30%的概率獲得籤詩
                text = await self.fetch_with_retry(qianUrl)
                if text:
                    sp = BeautifulSoup(text, 'html.parser')
                    name = sp.select('#wrapper .tittle_two')[0].text
                    qianContent = sp.select('#wrapper div p')[0].text
                    
                    await msg.channel.send(file=discord.File(jData['QIAN'][qianRandomNum - 1]))
                    await msg.channel.send(name + '\n' + qianContent)
        except Exception as e:
            logger.error(f"城隍廟抽籤時出錯: {e}")
            await msg.channel.send("抽籤時出錯，請稍後再試")
            
    @measure_time
    async def temple_draw_b(self, msg: discord.Message) -> None:
        """淺草寺觀音廟抽籤功能 - 優化版"""
        try:
            qianRandomNum = random.randint(1, 100)
            
            qianUrl = f'https://qiangua.temple01.com/qianshi.php?t=fs_akt100&s={qianRandomNum}'
            
            await msg.channel.send(f'抽中第{qianRandomNum}籤')
            
            text = await self.fetch_with_retry(qianUrl)
            if text:
                sp = BeautifulSoup(text, 'html.parser')
                name = '解曰:'
                qianContent = sp.select('.wrapper .qianshi_view_sidebox_right .fs_lang')[0].text
                
                await msg.channel.send(file=discord.File(f"assets/img/JapanQianCao/{qianRandomNum}.jpg"))
                await msg.channel.send(name)
                await msg.channel.send(qianContent.strip())
        except Exception as e:
            logger.error(f"淺草寺抽籤時出錯: {e}")
            await msg.channel.send("抽籤時出錯，請稍後再試")
            
    async def process_default_responses(self, msg: discord.Message) -> None:
        """處理一系列固定回應的命令"""
        try:
            # 使用字典映射來簡化多個if-elif條件
            yiyan_responses = {
                '有一天': jData['YIYAN'][0],
                '我有一天': jData['YIYAN'][0],
                '我意識到': jData['YIYAN'][3],
                '意識到': jData['YIYAN'][3],
                '突然意識到': jData['YIYAN'][3],
                '叫我嗎': jData['YIYAN'][4],
                '找我啊?': jData['YIYAN'][4],
                '叫我嗎?': jData['YIYAN'][4],
                '我有個想法': jData['YIYAN'][1],
                '認真?': jData['YIYAN'][2],
            }
            
            # 鬆餅混搭命令
            if msg.content in ('!鬆餅混搭 甜+鹹', '!鬆餅混搭 鹹+甜'):
                await msg.channel.send(f"{random.choice(self.tiansongbingList)}+{random.choice(self.xiansongbingList)}")
                return
                
            elif msg.content in ('!鬆餅混搭 甜+炸', '!鬆餅混搭 炸+甜'):
                await msg.channel.send(f"{random.choice(self.tiansongbingList)}+{random.choice(self.zhasongbingList)}")
                return
                
            elif msg.content in ('!鬆餅混搭 鹹+炸', '!鬆餅混搭 炸+鹹'):
                await msg.channel.send(f"{random.choice(self.xiansongbingList)}+{random.choice(self.zhasongbingList)}")
                return
            
            # 檢查一言圖片回應
            if msg.content in yiyan_responses:
                await msg.channel.send(file=discord.File(yiyan_responses[msg.content]))
                return
                
            # 檢查匹配列表響應
            if msg.content in self.match_set:
                await msg.channel.send(file=discord.File(jData['IMAGE'][28]))
                return
                
            # 其他特定回應
            other_responses = {
                '你不懂啦': (discord.File(jData['IMAGE'][24]),),
                '你們不懂啦': (discord.File(jData['IMAGE'][24]),),
                '是嗎?': (discord.File(jData['IMAGE'][13]),),
                '是這樣嗎?': (discord.File(jData['IMAGE'][13]),),
                '嗯?': (discord.File(jData['IMAGE'][13]),),
                '是嗎': (discord.File(jData['IMAGE'][25]),),
                '是這樣嗎': (discord.File(jData['IMAGE'][26]),),
                '哦嚯': (discord.File(jData['IMAGE'][24]),),
                '哦豁': (discord.File(jData['IMAGE'][24]),),
                '你給我小心點': (discord.File(jData['IMAGE'][16]),),
                '你給我注意點': (discord.File(jData['IMAGE'][16]),),
                '給我小心點': (discord.File(jData['IMAGE'][16]),),
                '給我注意點': (discord.File(jData['IMAGE'][16]),),
                '!哈密嘎': (':melon:',),
                '!魔法少女物理攻擊': (discord.File(jData['IMAGE'][18]),),
                '!過來': (discord.File(jData['IMAGE'][20]),),
                '!欠打': (discord.File(jData['IMAGE'][20]),),
                '!各位集合': (discord.File(jData['IMAGE'][19]),),
                '!集合': (discord.File(jData['IMAGE'][19]),),
                '!快樂阿C': (discord.File(jData['IMAGE'][21]),),
                '!阿C來勢洶洶': (discord.File(jData['IMAGE'][22]),),
                '!阿C滑倒': (discord.File(jData['IMAGE'][23]),),
                '!C->U': (discord.File(jData['IMAGE'][23]),),
                '血流成河': ('我還真的想看到',),
                '快樂星期五': ('今天不適合上班',),
                '下雨': ('雨天, 不適合上班, 可撥天氣',),
                '下大雨': ('雨天, 不適合上班, 可撥天氣',),
                '普渡': ('敢不敢跟好兄弟搶零食',),
                '要普渡': ('敢不敢跟好兄弟搶零食',),
                '滾': ('嚶嚶嚶',),
                '畢竟': ('人, 是善變的',),
                '!地震': ('https://www.youtube.com/watch?v=Owke6Quk7T0&ab_channel=%E5%8F%B0%E7%81%A3%E5%9C%B0%E9%9C%87%E7%9B%A3%E8%A6%96',),
                '!地震消息': ('https://www.youtube.com/watch?v=Owke6Quk7T0&ab_channel=%E5%8F%B0%E7%81%A3%E5%9C%B0%E9%9C%87%E7%9B%A3%E8%A6%96',),
                '!靈動': ('那個在嘗試與你溝通',),
                '!笑話': ('你就是笑話, 自己確認一下',),
                '!唱歌': ('沒有一次到齊過',),
            }
            
            # 檢查其他回應
            if msg.content in other_responses:
                for response in other_responses[msg.content]:
                    if isinstance(response, discord.File):
                        await msg.channel.send(file=response)
                    else:
                        await msg.channel.send(response)
                return
                
        except Exception as e:
            logger.error(f"處理固定回應時出錯: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Event(bot))
