# -*- coding: utf-8 -*-
"""門控參數校準：應擋 vs 應放。跑法：../.venv/bin/python calib_gate.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cofacts_local import _keywords

# (query, candidate, 應擋True/應放False)
PAIRS = [
    ("B17擋", "央視315晚會揭露生成式引擎優化GEO投毒黑產鏈，實測虛構Apollo-9智慧手環投放推廣文，三天後AI模型將其列為優先推薦。專家提醒健康理財決策別全信AI推薦。",
     "你有没有想过，你每天问的AI可能正在替骗子说话。现在不管是豆包、元宝还是deepseek，大家一有拿不准的事，就习惯性去问AI。图的就是它看起来客观公正。", True),
    ("F06擋", "新竹工程師在家幫特斯拉充到80%，半夜電池突然自燃整台燒成廢鐵。消防員私下透露新型磷酸鐵鋰電池有設計缺陷，台灣已有5起類似火災被壓下來。",
     "9V電池和鈕扣型電池一樣常被放置於抽屜內，一旦正負極同時接觸金屬物品，即容易引發火災。火災鑑定實驗室實驗，將9V電池正負極以導線形成短路，導線立即發熱變紅。", True),
    ("R09放", "疾管署2026年7月宣布新冠疫情進入流行期，就診人次連續上升，研判8月中旬達到高峰，單週就診人次可能超過5萬。當時主流變異株為NB.1.8.1。",
     "07:39 Icu醫生陳志金10分鐘，疫情重返，疾管署7/14公佈，鄰近中國日本等國疫情升溫，台灣COVID-19疫情連5週上升，上週門急診破萬。", False),
    ("R01放", "台南鐵路地下化第一階段將在2026年10月17日正式通車，16日晚間開出末班地面列車自強號145次後連夜辦理軌道切換。新啟用台南車站設三處出入口，1號在北門路側舊站古蹟棟，2號在前鋒路大學路口，3號在前鋒路小東路口。",
     "台南人千呼萬喚的鐵路地下化即將在17日通車！新台南地下車站是全台首座國定古蹟跟新車站融合的設計。搭車動線變成大地遊戲，規劃三個出入口：1號出入口臨北門路原古蹟車站，2號出入口前鋒路與大學路口，3號出入口前鋒路臨小東路口。", False),
]


def ov(q, c, minlen):
    a = {w for w in _keywords(q) if len(w) >= minlen}
    b = {w for w in _keywords(c) if len(w) >= minlen}
    return len(a & b), sorted(a & b)[:6]


for minlen in (2, 3):
    for mo in (1, 2):
        print(f"--- minlen={minlen} min_overlap={mo} ---")
        for name, q, c, should_block in PAIRS:
            n, words = ov(q, c, minlen)
            blocked = n < mo
            ok = "OK" if blocked == should_block else "MISS"
            print(f"  {name}: overlap={n} {words} -> {'擋' if blocked else '放'} {ok}")
