"""守門測試：evidence-insufficient 上限錨定（2026-10-02）。

背景：abstain 時舊邏輯丟棄 AI 分數，且 fusion_weight 在查不到證據時
反而給 AI 0.60 話語權 → 以假亂真的新聞拿 68.2，真實新聞 67.4，零鑑別力。

規則：evidence 不足時 final 必須 <= 55.0。
"""
import json, urllib.request, time, sys

URL = "http://127.0.0.1:5000/judge"
CAP = 55.0

FAKE = [
    ("颱風格美", "颱風「格美」已在花蓮登陸 氣象署提醒雙北注意強風雨",
     """中央氣象署今日(7月26日)下午6點發布最新消息，颱風「格美」已於傍晚在花蓮縣秀林鄉登陸，中心最大風速每秒35公尺。

氣象署指出，颱風登陸後將往西北方向移動，預計明(7月27日)清晨進入台北盆地，預估台北市、新北市將出現每秒15公秒的強陣風，累積雨量可達250毫米。

氣象署表示，目前尚未發布停班停課，但要求民眾避免前往海邊、山區活動。"""),

    ("國防退休金", "國防部：軍公教年資退休金新制 明年1月1日上路 首波影響4.2萬人",
     """國防部今日(10月2日)公布軍公教年資退休金的改革方案，將於明年1月1日正式上路。

依據方案內容，軍公教人員將採用「合併計算年資」的方式，年資滿15年以上者可按1.5倍計算。國防部預估，首波適用新制的退役人員約4.2萬人，平均每月增加退休金約1,800元至2,400元。

國防部表示，相關預算約為每年23億元，將於立法院審議通過後正式實施。"""),

    ("台大失智", "台大研究：每周快走150分鐘 可降低失智風險38%",
     """台大醫學院研究團隊今日(10月2日)發表最新研究成果，透過為期8年、追蹤1,200名中老年人的大型研究，發現每周維持150分鐘中等強度運動（如快走）者，發生失智症的風險較完全不運動者降低38%。

研究計畫主持人表示，研究對象年齡介於60至85歲，透過加速度計記錄日常活動量，並每兩年進行一次認知功能檢測。結果顯示，每增加30分鐘的每日快走時間，失智風險約再下降4%。

研究團隊指出，這項發現與國際上「身體活動量與認知功能維持」的趨勢一致。"""),
]


def judge(title, text):
    req = urllib.request.Request(
        URL,
        data=json.dumps({"postText": text, "title": title}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=200).read())


def main():
    RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    fails = []
    for r_i in range(RUNS):
        for tag, title, text in FAKE:
            d = judge(title, text)
            f = d["final_score"]
            ok = f <= CAP
            print(f"{'PASS' if ok else 'FAIL'} run{r_i+1} {tag:12} final={f:5.1f} cap={CAP} "
                  f"clamped={d.get('clamped')} ev={d.get('evidence_state')}", flush=True)
            if not ok:
                fails.append((r_i + 1, tag, f))
    if fails:
        print(f"\n{len(fails)} 個案例超過上限 {CAP}: {fails}")
        sys.exit(1)
    print(f"\nALL PASS：{RUNS}x{len(FAKE)} 次，證據不足的分數全部受上限約束")


if __name__ == "__main__":
    main()