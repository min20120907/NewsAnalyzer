# -*- coding: utf-8 -*-
"""釣魚標題啟發式一次性自測：命中釣魚、放過正常。跑法：python3 test_clickbait.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_news_server_new import _is_clickbait

CLICKBAIT = [
    "驚傳！知名女星深夜送醫，真相竟然是…",
    "不看會後悔！這3招讓你年收多50萬",
    "全網嚇傻！男童一句話讓全車人沉默了",
    "踢爆黑心廠商內幕，網友全看傻了",
    "出大事了！這款泡麵驗出致癌物，天塌了",
    "震撼彈！董事長深夜急了，股價崩盤真相曝光",
    "瘋傳！喝這杯飲料竟能減肥，不轉不是台灣人",
    "洗版了！他只做一件事，細思極恐",
]
NORMAL = [
    "中央氣象署發布颱風警報，週末影響北部地區",
    "立法院三讀通過修正案，明年元旦上路",
    "台積電法說會登場，第三季營收創新高",
    "內政部警政署165全民防騙網提醒：慎防假投資詐騙",
    "高鐵春節加開班次，週五開放訂票",
    "研究：每天步行30分鐘有助心血管健康",
    "央行宣布利率維持不變，符合市場預期",
    "台南古蹟修復完工，假日開放參觀",
]

missed = [t for t in CLICKBAIT if not _is_clickbait(t, "")]
false_hit = [t for t in NORMAL if _is_clickbait(t, "")]
print(f"clickbait recall: {len(CLICKBAIT)-len(missed)}/{len(CLICKBAIT)}", "missed:", missed)
print(f"normal precision: {len(NORMAL)-len(false_hit)}/{len(NORMAL)}", "false_hit:", false_hit)
assert not missed, f"漏網: {missed}"
assert not false_hit, f"誤傷: {false_hit}"
print("ALL PASS")
