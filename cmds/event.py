import discord
import json
import requests
import random
import twstock
import datetime
# import time
# import pandas as pd

from discord.ext import commands
from core.classes import Cog_Extension
from bs4 import BeautifulSoup
from opencc import OpenCC
# from datetime import datetime, timezone, timedelta

# 'r' = read
with open('setting.json', 'r', encoding='utf8') as jFile:
    jData = json.load(jFile)
    print('json load setting.json')


class Event(Cog_Extension):
    @commands.Cog.listener()
    async def on_member_join(self, member):
        channel = self.bot.get_channel(int(jData['CHATROOM01']))

        await channel.send(f'{member} 出現啦!')

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        channel = self.bot.get_channel(int(jData['CHATROOM01']))

        await channel.send(f'{member} 離開了!')

    @commands.Cog.listener()
    async def on_message(self, msg):
        count = 0

        realname = msg.author.nick or msg.author.name

        print(f"{msg.channel.name}-{realname}: {msg.content}")

        if msg.author.bot:
            return  # 忽略其他機器人的消息

        if msg.content.strip() == "!!啟動":
            self.training_mode = True
            await msg.channel.send("好的，已經啟動了。")
            return

        if msg.content.strip() == "!!關閉":
            self.training_mode = False
            await msg.channel.send("好的，已經關閉了。")
            return

        puQian = [
            "assets/img/puqian/large_fierce.png",
            "assets/img/puqian/normal_fierce.png",
            "assets/img/puqian/small_fierce.png",
            "assets/img/puqian/large_lucky.png",
            "assets/img/puqian/medium_lucky.png",
            "assets/img/puqian/normal_lucky.png",
            "assets/img/puqian/small_lucky.png",
            "assets/img/puqian/super_large_lucky.png"
        ]

        beilan = [
            "你認真的嗎？🤨", "這聽起來有點扯。🙄", "你在開玩笑吧？😏", "這真的是你的結論嗎？🤔", "你確定這是真的？😒",
            "這聽起來像是編的。🤥", "你是不是搞錯了？😕", "這樣說有點牽強吧。🤷", "這種說法太過分了吧。😠",
            "你以為我會相信嗎？😑", "你的證據呢？🧐", "這種話你也能說出口？😒", "你在逗我嗎？😂", "這種說法太荒謬了。😲",
            "你是不是故意挑釁我？😡", "這是你聽來的吧？👂", "這麼說太過頭了吧。😤", "你以為這樣我會相信嗎？😏",
            "這話有點站不住腳。🤨", "你在玩哪一出啊？🤔", "這樣也能信？😒", "你認為我會上當嗎？😤", "這真的是你相信的？😳",
            "你的說法有點荒唐。🙄", "你是在騙誰？🤥", "這聽起來完全不合理。🤷", "你是不是在搞笑？😂", "這話也太誇張了吧。😆",
            "你真的相信這個？😒", "這樣說也太牽強了。🙄", "你是在故意激怒我嗎？😡", "這話根本不可信。😑", "你這話沒道理啊。🤨",
            "你以為我會被這種話騙到嗎？😏", "這種說法太牽強。🤷", "你這是在胡說八道嗎？🤥", "你這話太荒謬了。😲",
            "你確定不是在開玩笑？😂", "這話完全站不住腳。🤨", "你這是從哪裡聽來的？👂", "這種說法太離譜了。🙄",
            "你這話太過分了。😠", "你以為這樣我會相信？😑", "你這是在找茬嗎？😒", "這話根本不合邏輯。🤔", "你這是在故意挑釁嗎？😡",
            "這聽起來像是編造的。🤥", "你這話完全不可信。😑", "這種說法太牽強附會。🤷", "你這是在亂說嗎？🤔",
            "你這話太扯了。🙄", "這種說法太誇張。😆", "你這是在逗我吧？😂", "這話根本不合常理。🤔", "你這是在瞎說吧？🤥",
            "這話太不可思議了。😲", "你這話根本沒道理。🤨", "這話完全不合理。🤷", "你這是在開玩笑吧？😂", "這話根本站不住腳。🙄",
            "你這話太過分。😠", "你這是在挑釁我吧？😡", "這話完全不合邏輯。🤔", "你這是在說笑嗎？😆", "你這話太離譜。🙄",
            "這種說法完全不可信。😑", "你這話太荒唐。😲", "這話根本不合常理。🤔", "你這是在瞎編嗎？🤥", "這話完全沒道理。🤨",
            "你這話太誇張。😆", "你這話太扯。🙄", "這話根本不合邏輯。🤔", "你這是在開玩笑嗎？😂", "這話太荒謬。😲",
            "你認為我會信這種鬼話？😏", "這話有點太誇張了吧。🙄", "這種話你也說得出口？😒", "你這是在瞎扯嗎？🤥", "這樣說根本不合理。🤷",
            "你這話根本沒有根據。🤨", "這種說法完全站不住腳。🙄", "你這是在故意搞事吧？😡", "這話聽起來完全不可信。😑",
            "你這是在編故事嗎？📝", "這聽起來像是陰謀論。🕵️", "你是在捉弄我嗎？🙃", "這說法真是匪夷所思。😵", "你這是在吹牛嗎？🤥",
            "這種說法讓人無法相信。😐", "你這是在開大玩笑吧？😜", "這種話誰會信？🤨", "你這是在瞎掰嗎？😅", ":)", ":))", "BAD!", "這簡直錦上添花:)", "尋龍分金看纏山，一重纏是一重關。關門如有八分險，不出陰陽八卦形。勸施主還是回頭是岸吧。🤨", "不要。😡", "😡", "🥵", "HSO🥵"
        ]


        greetings = [
            "嘿！有什麼問題嗎？", "嗨！我可以幫你解答什麼問題？", "Hello！需要我的幫助嗎？", "尊敬的閣下，有什麼需要提問的？",
            "我已經準備好了，說吧。"
        ]

        random_responses = [
            "我只剩下這個答案給你：", "看看這個：", "讓我想想...應該是這樣：", "嗯，我覺得這個比較接近：",
            "你還是面對現實吧:", "或許你會想要這個:", "要來咯！要來咯!", "想不到吧，我的回答是這個:", "聽我一句勸："
        ]

        #浅草签
        if msg.content == '??:':
            await msg.channel.send(random.choice(greetings))
        elif msg.content.startswith('??:'):
            rangeNum = random.randint(1, 10)

            if rangeNum < 9:
                response = random.choice(random_responses)
                await msg.channel.send(response)
                await msg.channel.send(file=discord.File(puQian[rangeNum - 1]))
            else:
                await msg.channel.send(random.choice(beilan))
                # await self.train_model([msg.content])
                # if not self.training_mode:
                #     await msg.channel.send(random.choice(beilan))
                # else:
                #     input_ids = self.tokenizer.encode(msg.content,
                #                                       return_tensors="pt")
                #     reply_ids = self.model.generate(input_ids,
                #                                     max_length=100,
                #                                     num_return_sequences=1)
                #     reply = self.tokenizer.decode(reply_ids[0],
                #                                   skip_special_tokens=True)
                #     await msg.channel.send(reply)

        #台股
        if msg.content == '!twii':
            url = 'https://invest.cnyes.com/index/TWS/TSE01'

            response = requests.get(url).text

            soup = BeautifulSoup(response, 'html.parser')

            twiiTitle = soup.select('.header_second')[0].text
            twiiDateNow = soup.select('.header-time .jsx-2214436525')[0].text
            twiiIndex = soup.select(
                '.header-info .info-price .info-lp span')[0].text
            twiiUpDownIndex = soup.select(
                '.header-info .info-change .change-net span')[0].text
            twiiUpDownPercent = soup.select(
                '.header-info .info-change .change-percent span')[0].text

            twiiBuySellTitle = soup.select('.data-block .block-title')[0].text
            twiiBuySellValue = soup.select('.data-block .block-value')[0].text
            twiiToDayHeighLowTitle = soup.select(
                '.data-block .block-title')[1].text
            twiiToDayHeighLowValue = soup.select(
                '.data-block .block-value')[1].text
            twii52HeighLowTitle = soup.select(
                '.data-block .block-title')[2].text
            twii52HeighLowValue = soup.select(
                '.data-block .block-value')[2].text

            await msg.channel.send(twiiTitle + '\n' + twiiDateNow + '\n' +
                                   '當前指數: ' + str(twiiIndex) + '\n' + '漲跌點: ' +
                                   str(twiiUpDownIndex) + '\n' + '漲跌百分比: ' +
                                   str(twiiUpDownPercent) + '\n' +
                                   twiiBuySellTitle + ': ' + twiiBuySellValue +
                                   '\n' + twiiToDayHeighLowTitle + ': ' +
                                   twiiToDayHeighLowValue + '\n' +
                                   twii52HeighLowTitle + ': ' +
                                   twii52HeighLowValue)

        if msg.content == '!tws' + msg.content.replace('!tws', '').strip():
            targetStock = msg.content.replace('!tws', '').strip()

            stock = twstock.realtime.get(targetStock)

            stockInfo = list(stock['info'].values())
            stockRealtime = list(stock['realtime'].values())

            await msg.channel.send('股票代號:\u0020' + stockInfo[0] + '\n' +
                                   '股票名:\u0020' + stockInfo[2] + '\n' +
                                   '最後揭示買價:\u0020' + stockRealtime[3][0][:-2] +
                                   '\n' + '最後揭示買量:\u0020' +
                                   stockRealtime[4][0] + '\n' +
                                   '最後揭示賣價:\u0020' + stockRealtime[5][0][:-2] +
                                   '\n' + '最後揭示賣量:\u0020' +
                                   stockRealtime[6][0] + '\n' + '成交量:\u0020' +
                                   stockRealtime[1] + '\n' + '累積成交量:\u0020' +
                                   stockRealtime[2] + '\n' + '開盤價:\u0020' +
                                   stockRealtime[7][:-2] + '\n' +
                                   '盤中最高價:\u0020' + stockRealtime[8][:-2] +
                                   '\n' + '盤中最低價:\u0020' +
                                   stockRealtime[9][:-2] + '\n' +
                                   '收盤價:\u0020' + stockRealtime[0][:-2])

        #新聞
        if msg.content == '!焦點新聞':
            url = 'https://www.setn.com/ViewAll.aspx?PageGroupID=0'

            response = requests.get(url).text
            soup = BeautifulSoup(response, 'html.parser')

            for headline in soup.find('div', 'NewsList').find_all(
                    'h3', 'view-li-title'):
                if headline.find('a', 'gt'):
                    title = headline.find('a', 'gt').text
                    await msg.channel.send('標題: ' + title + '\n')
        #財經新聞
        if msg.content == '!財經新聞':
            url = 'https://news.cnyes.com/news/cat/tw_stock'

            response = requests.get(url).text
            soup = BeautifulSoup(response, 'html.parser')

            # time = soup.find('div', '_1Vis')['datetime']

            for headline in soup.find('div', '_2bFl').find_all('a', '_1Zdp'):
                if headline.find('h3'):
                    title = headline.find('h3').text
                    href = headline['href']
                    await msg.channel.send('標題: ' + title + '\n' +
                                           'https://news.cnyes.com' + href +
                                           '\n')

        #天氣
        if msg.content == '!天氣':
            url = 'https://weather.com/zh-TW/weather/today/l/fe7393b7f2c8eed2cf692bd079361df362d9f0c1c0f896e6e46a649295e15c7d'

            response = requests.get(url)

            response.encoding = 'UTF-8'

            hourStatusUrl = 'https://weather.com/zh-TW/weather/hourbyhour/l/fe7393b7f2c8eed2cf692bd079361df362d9f0c1c0f896e6e46a649295e15c7d'

            hourResponse = requests.get(hourStatusUrl)

            hourResponse.encoding = 'UTF-8'

            if response.status_code == requests.codes.ok:
                soup = BeautifulSoup(response.text, 'html.parser')
                name = soup.select(
                    '.region-main .CurrentConditions--location--1YWj_')[0].text
                temper = soup.select(
                    '.region-main .CurrentConditions--tempValue--MHmYY'
                )[0].text
                status = soup.select(
                    '.region-main .CurrentConditions--phraseValue--mZC_p'
                )[0].text
                bodyFeeling = soup.select(
                    '.region-main .TodayDetailsCard--feelsLikeTempValue--2icPt'
                )[0].text
                heighAndLow = soup.select(
                    '.region-main .CurrentConditions--tempHiLoValue--3T1DG'
                )[0].text

                hourSoup = BeautifulSoup(hourResponse.text, 'html.parser')
                date = hourSoup.select(
                    '.region-main .HourlyForecast--longDate--J_Pdh')[0].text

                await msg.channel.send(date + '\n' + '地區: ' + name + '\n' +
                                       heighAndLow + '\n' + '目前溫度: ' + temper +
                                       '\n' + '體感溫度: ' + bodyFeeling + '\n' +
                                       '氣候: ' + status + '\n')

        #農民歷
        # if msg.content == '!農歷' + msg.content.replace('!農歷', '').strip():
        #     nongDate = msg.content.replace('!農歷', '').strip()

        #     nongYears = nongDate[0:4]
        #     nongMouth = nongDate[4:6]
        #     nongDay = nongDate[6:8]

        #     url = f'https://www.yourchineseastrology.com/hk/rili/{nongYears}-{nongMouth}-{nongDay}.htm'

        #     response = requests.get(url).text

        #     soup = BeautifulSoup(response, 'html.parser')

        #     nongbody = soup.select('.bg-white .rounded .p2')[0].text
        # print(nongbody)
        # await msg.channel.send(nongbody)

        #詢問說明
        questionDescription = "[aries]牡羊座 [taurus]金牛座 [gemini]雙子座 [cancer]巨蟹座 [leo]獅子座 [virgo]處女座 [libra]天秤座 [scorpio]天蠍座 [sagittarius]射手座 [capricorn]摩羯座 [aquarius]水瓶座 [pisces]雙魚座，請選擇星座(僅能填英文):"

        if msg.content == '!星座編號':
            await msg.channel.send(questionDescription)

        if msg.content == '!今日運勢':
            await msg.channel.send('想查詢運勢嗎? 請輸入!今日運勢-星座, 如:!今日運勢-天秤座')

        if msg.content == '!今日運勢-' + msg.content.replace('!今日運勢-', ''):
            typeMap = {
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
            star_sign = msg.content.replace('!今日運勢-', '')
            url = f'https://m.xzw.com/fortune/{typeMap[star_sign]}/'
            res = requests.get(url)
            soup = BeautifulSoup(res.text, 'html.parser')
            horoscope = soup.find(class_='cont').text.strip().replace(
                '。', '。\n')
            cc = OpenCC('s2t')

            await msg.channel.send(
                f'今日{star_sign}的運勢：\n{cc.convert(horoscope)}')

        #城隍廟
        if msg.content == '!抽籤A':
            count = 0

            if count == 0:
                qianRandomNum = random.randint(1, 60)

                qianUrl = 'http://www.citygod.tw/fortune.php?ans=' + str(
                    qianRandomNum)

                qianResponse = requests.get(qianUrl)

                qianResponse.encodeing = 'UTF-8'

                await msg.channel.send('抽中第' + str(qianRandomNum) + '籤')

                for select in range(100):
                    randomNum = random.randint(0, 2)
                    if randomNum == 2:
                        count += 1

                        # await msg.channel.send('聖筊')

                        if count == 3:
                            sp = BeautifulSoup(qianResponse.text,
                                               'html.parser')
                            name = sp.select('#wrapper .tittle_two')[0].text
                            qianContent = sp.select('#wrapper div p')[0].text
                            await msg.channel.send(
                                file=discord.File(jData['QIAN'][qianRandomNum - 1]))
                            await msg.channel.send(name + '\n' + qianContent)
                            break
        #淺草寺觀音廟
        if msg.content == '!抽籤B':
            count = 0

            if count == 0:
                qianRandomNum = random.randint(1, 100)

                qianUrl = 'https://qiangua.temple01.com/qianshi.php?t=fs_akt100&s=' + str(
                    qianRandomNum)

                qianResponse = requests.get(qianUrl)

                qianResponse.encodeing = 'UTF-8'

                await msg.channel.send('抽中第' + str(qianRandomNum) + '籤')

                sp = BeautifulSoup(qianResponse.text, 'html.parser')
                name = '解曰:'
                qianContent = sp.select(
                    '.wrapper .qianshi_view_sidebox_right .fs_lang')[0].text
                await msg.channel.send(file=discord.File(
                    f"assets/img/JapanQianCao/{qianRandomNum}.jpg"))
                await msg.channel.send(name)
                await msg.channel.send(qianContent.strip())

        if msg.content == '有一天' or msg.content == '我有一天':
            await msg.channel.send(file=discord.File(jData['YIYAN'][0]))
        elif msg.content == '我意識到' or msg.content == '意識到' or msg.content == '突然意識到':
            await msg.channel.send(file=discord.File(jData['YIYAN'][3]))
        elif msg.content == '叫我嗎' or msg.content == '找我啊?' or msg.content == '叫我嗎?':
            await msg.channel.send(file=discord.File(jData['YIYAN'][4]))
        elif msg.content == '我有個想法':
            await msg.channel.send(file=discord.File(jData['YIYAN'][1]))

        if msg.content == '認真?':
            await msg.channel.send(file=discord.File(jData['YIYAN'][2]))

        xiansongbingList = [
            '起司玉米蔬菜鬆餅', '牛肉漢堡蔬菜鬆餅', '培根起司蔬菜鬆餅', '鮪魚沙拉蔬菜鬆餅', '勁辣雞蔬菜鬆餅',
            '紐奧良雞蔬菜鬆餅', '燻雞蔬菜鬆餅', '碳烤雞腿蔬菜鬆餅', '芝士牛堡蔬菜鬆餅', '墨西哥辣椒牛肉蔬菜鬆餅',
            '韓味香辣雞腿蔬菜鬆餅', '培根花生牛肉堡蔬菜鬆餅', '海陸雙拼(牛堡+鮪魚沙拉)', '海陸雙拼(韓味雞+鮪魚沙拉)'
        ]

        tiansongbingList = [
            '蜂蜜鬆餅', '抹茶鬆餅', '藍莓鬆餅', '鮮奶油鬆餅', '花生鬆餅', '巧克力鬆餅', '榛果巧克力鬆餅',
            '蜂蜜鮮奶油鬆餅', '法式檸檬奶霜鬆餅', '香草卡士達鬆餅', '葡萄奶酥鬆餅', '藍莓巧克力鬆餅', '巧克力鮮奶油鬆餅',
            '巧克力香蕉鬆餅', '巧克力卡士達鬆餅', '抹茶紅豆鬆餅'
        ]

        zhasongbingList = [
            '薯餅起司蔬菜鬆餅', '黃金豬排起司蔬菜鬆餅', '辣味咔啦雞起司蔬菜鬆餅', '原味咔啦雞起司蔬菜鬆餅'
        ]

        if msg.content == '你不懂啦' or msg.content == '你們不懂啦':
            await msg.channel.send(file=discord.File(jData['IMAGE'][24]))

        if msg.content == '說' or msg.content == '说':
            count += 1

            if count == 1:
                await msg.channel.send('嗯? 找本機器人有事?')
            elif count == 2:
                await msg.channel.send('說啥? 本機器人不支援心靈感應')
            elif count == 3:
                count = 0
                await msg.channel.send('本機器人不予理會..')
        elif msg.content == '血流成河':
            await msg.channel.send('我還真的想看到')
        elif msg.content == '快樂星期五':
            await msg.channel.send('今天不適合上班')
        elif msg.content == '下雨' or msg.content == '下大雨':
            await msg.channel.send('雨天, 不適合上班, 可撥天氣')
        elif msg.content == '普渡' or msg.content == '要普渡':
            await msg.channel.send('敢不敢跟好兄弟搶零食')
        elif msg.content == '滾':
            await msg.channel.send('嚶嚶嚶')
        elif msg.content == '畢竟':
            await msg.channel.send('人, 是善變的')
        elif msg.content == '!地震' or msg.content == '!地震消息':
            await msg.channel.send(
                'https://www.youtube.com/watch?v=Owke6Quk7T0&ab_channel=%E5%8F%B0%E7%81%A3%E5%9C%B0%E9%9C%87%E7%9B%A3%E8%A6%96'
            )
        elif msg.content == '!靈動':
            await msg.channel.send('那個在嘗試與你溝通')
        elif msg.content == '!笑話':
            await msg.channel.send('你就是笑話, 自己確認一下')
        elif msg.content == '!唱歌':
            await msg.channel.send('沒有一次到齊過')
        elif msg.content == '是嗎?' or msg.content == '是這樣嗎?' or msg.content == '嗯?' or msg.content == '是嗎' or msg.content == '是這樣嗎':
            await msg.channel.send(file=discord.File(jData['IMAGE'][13]))

        elif msg.content == '!甜味鬆餅':
            await msg.channel.send(tiansongbingList[random.randint(0, 15)])
        elif msg.content == '!鹹味鬆餅':
            await msg.channel.send(xiansongbingList[random.randint(0, 13)])
        elif msg.content == '!炸物鬆餅':
            await msg.channel.send(zhasongbingList[random.randint(0, 3)])
        elif msg.content == '!鬆餅混搭 甜+鹹' or msg.content == '!鬆餅混搭 鹹+甜':
            await msg.channel.send(tiansongbingList[random.randint(0, 15)] +
                                   '+' +
                                   xiansongbingList[random.randint(0, 13)])
        elif msg.content == '!鬆餅混搭 甜+炸' or msg.content == '!鬆餅混搭 炸+甜':
            await msg.channel.send(tiansongbingList[random.randint(0, 15)] +
                                   '+' + zhasongbingList[random.randint(0, 3)])
        elif msg.content == '!鬆餅混搭 鹹+炸' or msg.content == '!鬆餅混搭 炸+鹹':
            await msg.channel.send(xiansongbingList[random.randint(0, 13)] +
                                   '+' + zhasongbingList[random.randint(0, 3)])
        elif msg.content == '!上班':
            await msg.channel.send(jData['ON_WORK'][random.randint(0, 34)])
        elif msg.content == '!下班':
            await msg.channel.send(jData['OFF_WORK'][random.randint(0, 74)])
        elif msg.content == '!下午茶':
            await msg.channel.send('https://dinbendon.net/do/')
        elif msg.content == '!阿希' or msg.content == '!阿希照片':
            await msg.channel.send('叫我幹嘛?')
            await msg.channel.send(file=discord.File(jData['IMAGE'][15]))
        elif msg.content == '你給我小心點' or msg.content == '你給我注意點' or msg.content == '給我小心點' or msg.content == '給我注意點':
            await msg.channel.send(file=discord.File(jData['IMAGE'][16]))
        elif msg.content == '!哈密嘎':
            await msg.channel.send(':melon:')
        elif msg.content == '!魔法少女物理攻擊':
            await msg.channel.send(file=discord.File(jData['IMAGE'][18]))
        elif msg.content == '!過來' or msg.content == '!欠打':
            await msg.channel.send(file=discord.File(jData['IMAGE'][20]))
        elif msg.content == '!各位集合' or msg.content == '!集合':
            await msg.channel.send(file=discord.File(jData['IMAGE'][19]))
        elif msg.content == '!快樂阿C':
            await msg.channel.send(file=discord.File(jData['IMAGE'][21]))
        elif msg.content == '!阿C來勢洶洶':
            await msg.channel.send(file=discord.File(jData['IMAGE'][22]))
        elif msg.content == '!阿C滑倒' or msg.content == '!C->U':
            await msg.channel.send(file=discord.File(jData['IMAGE'][23]))
        elif msg.content == '哦嚯' or msg.content == '哦豁':
            await msg.channel.send(file=discord.File(jData['IMAGE'][24]))
        elif msg.content == '是嗎':
            await msg.channel.send(file=discord.File(jData['IMAGE'][25]))
        elif msg.content == '是這樣嗎':
            await msg.channel.send(file=discord.File(jData['IMAGE'][26]))
        elif msg.content in jData['MATCHLIST']:
            await msg.channel.send(file=discord.File(jData['IMAGE'][28]))


async def setup(bot):
    await bot.add_cog(Event(bot))
