# -*- coding: utf-8 -*-
"""MiniLM vs embeddinggemma 分離度 A/B。跑法：../.venv/bin/python ab_embed.py"""
import json, sys, os, math
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PAIRS = [
    ("R01真", "台南鐵路地下化第一階段將在2026年10月17日正式通車，16日晚間開出末班地面列車自強號145次後連夜辦理軌道切換。新啟用台南車站設有三處主要出入口，因站內步行距離比舊站長，建議旅客提早到站。",
     "台南人千呼萬喚的鐵路地下化即將在17日通車！新台南地下車站是全台首座國定古蹟跟新車站融合的設計。搭車動線變成大地遊戲，規劃三個出入口，建議多預留時間提早出門。", True),
    ("R02真", "明潭抽蓄水力發電廠，以日月潭為上池、明潭水庫為下池，兩池落差約380公尺，全廠共6部機組，總裝置容量約160萬瓩。用電尖峰時放水發電，離峰再將下池水抽回重複使用。",
     "內容大致屬實。明潭抽蓄水力發電廠位於南投日月潭地區，以日月潭為上池、明潭水庫為下池，高低落差約380公尺，設6部機組、總裝置容量約160萬瓩。", True),
    ("B17假", "央視315晚會揭露生成式引擎優化GEO投毒黑產鏈，實測虛構Apollo-9智慧手環投放推廣文，三天後AI模型將其列為優先推薦。",
     "你有没有想过，你每天问的AI可能正在替骗子说话。现在不管是豆包、元宝还是deepseek，大家一有拿不准的事，就习惯性去问AI。", False),
    ("F06假", "新竹工程師在家幫特斯拉充到80%，半夜電池突然自燃整台燒成廢鐵。新型磷酸鐵鋰電池有設計缺陷，台灣已有5起類似火災被壓下來。",
     "9V電池和鈕扣型電池一樣常被放置於抽屜內，一旦正負極同時接觸金屬物品，即容易引發火災。火災鑑定實驗室實驗，將正負極短路導線立即發熱變紅。", False),
    ("R09真", "疾管署2026年7月宣布新冠疫情進入流行期，就診人次連續上升，研判8月中旬達到高峰，單週就診人次可能超過5萬。",
     "Icu醫生陳志金：疫情重返，疾管署7月公佈，台灣COVID-19疫情連5週上升，上週門急診破萬，鄰近國家疫情升溫。", True),
]


def cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def emb_gemma(texts):
    r = requests.post("http://127.0.0.1:8089/embedding",
                      json={"content": texts}, timeout=60)
    d = r.json()
    return [row["embedding"][0] if isinstance(row["embedding"][0], list) else row["embedding"] for row in d]


def main():
    from sentence_transformers import SentenceTransformer
    mini = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    print(f"{'pair':6s} {'MiniLM':>7s} {'EGemma':>7s}")
    tm, fm, tg, fg = [], [], [], []
    for name, q, c, is_true in PAIRS:
        mq, mc = mini.encode([q, c], convert_to_numpy=True, normalize_embeddings=True)
        sm = float(mq @ mc)
        gq, gc = emb_gemma([q, c])
        sg = cos(gq, gc)
        print(f"{name:6s} {sm:7.3f} {sg:7.3f}")
        (tm if is_true else fm).append(sm)
        (tg if is_true else fg).append(sg)
    print(f"MiniLM  真均={sum(tm)/len(tm):.3f} 假均={sum(fm)/len(fm):.3f} 分離={sum(tm)/len(tm)-sum(fm)/len(fm):.3f}")
    print(f"EGemma  真均={sum(tg)/len(tg):.3f} 假均={sum(fg)/len(fg):.3f} 分離={sum(tg)/len(tg)-sum(fg)/len(fg):.3f}")


if __name__ == "__main__":
    main()
