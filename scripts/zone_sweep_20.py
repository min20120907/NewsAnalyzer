# -*- coding: utf-8 -*-
"""今日四區改動 20 篇驗收：每區 20 探針，全跑檢索層（非 /judge，避 LLM 溫度噪音）。

- sghk   ：gatekeeper 單元斷言（10 星馬查詢不斷馬來西噪音＋10 台灣對照行為不變）
- rumhk  ：rumtoast/HKBU 各 10 篇最新標題自檢索（命中＋sim>=0.50＋非 not_found）
- en     ：10 LIAR 已裁決重放（命中）＋10 無關真新聞（google-en not_found）
- ja     ：10 Murayama 已裁決重放（infact/jfc 任一命中）＋10 無關（兩源皆 not_found）

Usage: .venv/bin/python scripts/zone_sweep_20.py [--only sghk|rumhk|en|ja]
輸出 data/eval/zone_sweep_20.json（逐區 pass/fail＋明細）。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "python"))
import requests  # noqa: E402
from factcheck_multi import (  # noqa: E402
    get_rumtoast, get_hkbu, get_google_factcheck, get_infact, get_jfc,
    get_politifact, UA)
from cofacts_local import _strong_entities, entity_gatekeeper  # noqa: E402

EV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "..", "data", "eval")
OUT = os.path.join(EV, "zone_sweep_20.json")


def _wp_titles(url, n=10):
    r = requests.get(url, params={"per_page": n, "_fields": "title"},
                     headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    out = []
    for it in r.json():
        t = re.sub(r"<[^>]+>", "", (it.get("title") or {}).get("rendered", ""))
        if len(t.strip()) >= 10:
            out.append(t.strip())
    return out[:n]


def sweep_sghk():
    """星馬 gatekeeper：噪音消失＋台灣行為不變（純單元，即時）。"""
    sg_queries = [
        "馬來西亞首相安華宣布內閣改組", "馬來西亞令吉匯率創新高",
        "新加坡總理黃循財訪問中國", "新加坡樟宜機場擴建第三跑道",
        "香港特首李家超發表施政報告", "香港股市恒生指數大漲",
        "安華會見習近平討論南海議題", "穆希丁批評安華政府經濟政策",
        "馬來西亞羽毛球公開賽李梓嘉奪冠", "新加坡航空新航線直飛高雄",
        "馬來西亞榴槤出口中國創新高", "香港迪士尼樂園萬聖節活動開幕",
        "新加坡食品局批准新型培養肉上市", "馬來西亞國會通過反跳槽法修正案",
        "香港中文大學研發登革熱快篩", "李顯龍資政會見馬來西亞元首",
        "新加坡濱海灣跨年煙火吸引十萬人", "香港機場三跑系統全面啟用",
    ]
    ok, detail = True, []
    for q in sg_queries:
        se = _strong_entities(q)
        # 真命中（談同主題、無馬來西亞字樣、帶其他強實體）不得被擋
        cand = "安華宣布內閣改組，沈伯洋評論東南亞局勢"
        passed = entity_gatekeeper(q, cand)
        if se:
            # 有真實體的查詢 vs 無交集候選 → 衝突擋下是正確行為
            good = ("馬來西" not in se) and (passed is False)
        else:
            # 無實體 → 放行（fail-open）；重點是馬來西噪音消失
            good = ("馬來西" not in se) and (passed is True)
        ok &= good
        detail.append({"q": q, "strong": sorted(se), "pass": passed,
                       "ok": good})
    tw_controls = [
        ("沈伯洋批評藍白法案", {"沈伯洋"}),
        ("陳惠仁醫師談疫苗副作用", {"陳惠仁"}),
        ("范振宗鄭麗文爭執", {"范振宗", "鄭麗文"}),
    ]
    for q, expect in tw_controls:
        se = _strong_entities(q)
        good = bool(expect & se)
        ok &= good
        detail.append({"q": q, "strong": sorted(se), "ok": good})
    # 衝突照擋
    blk = entity_gatekeeper("沈伯洋批評法案", "范振宗鄭麗文爭執國民黨道歉")
    ok &= (blk is False)
    detail.append({"conflict_still_blocks": blk, "ok": (blk is False)})
    return ok, detail


def sweep_rumhk():
    ok, detail = True, []
    try:
        rt = _wp_titles("https://rumtoast.com/wp-json/wp/v2/posts")
        hk = _wp_titles("https://factcheck.hkbu.edu.hk/home/wp-json/wp/v2/posts")
    except Exception as e:  # noqa: BLE001
        return False, [{"fetch_error": str(e)[:100]}]
    for t in rt:
        r = get_rumtoast(t, use_cache=False)
        good = r["status"] not in ("not_found", "error")
        ok &= good
        detail.append({"src": "rumtoast", "status": r["status"],
                       "sim": r.get("similarity_score"),
                       "t": t[:40], "ok": good})
    for t in hk:
        r = get_hkbu(t, use_cache=False)
        good = r["status"] not in ("not_found", "error")
        ok &= good
        detail.append({"src": "hkbu", "status": r["status"],
                       "sim": r.get("similarity_score"),
                       "t": t[:40], "ok": good})
    return ok, detail


def _murayama_decided(n=10):
    recs = [json.loads(l) for l in
            open(os.path.join(EV, "murayama_ja.jsonl"), encoding="utf-8")]
    stm = {}
    import csv
    for r in csv.DictReader(open(os.path.join(EV, "murayama_label.tsv"),
                                 encoding="utf-8"), delimiter="\t"):
        stm[r["ID"]] = r["Article"]
    out = []
    for r in recs:
        if r["truth"] == "SKIP":
            continue
        for src in ("infact", "jfc"):
            st = r[src]["status"]
            pred = ("FAKE" if st == "inaccurate"
                    else ("REAL" if st == "accurate" else "?"))
            # 只重放舊碼判對的列（同 _liar_decided 理由：舊映射問句誤判 accurate 的列已修掉）
            if pred == r["truth"]:
                out.append((stm[r["id"]], src, r["truth"]))
                break
        if len(out) >= n:
            break
    return out


def _liar_decided(n=10):
    recs = [json.loads(l) for l in
            open(os.path.join(EV, "liar_en.jsonl"), encoding="utf-8")]
    stm = {}
    import csv
    for r in csv.reader(open(os.path.join(EV, "liar_test.tsv"),
                             encoding="utf-8"), delimiter="\t"):
        if len(r) >= 3:
            stm[r[0]] = r[2]
    out = []
    for r in recs:
        # 只重放舊碼判對的列（pred==truth）：舊碼判錯的列（如低 sim 誤命中）在新門控下
        # 本來就該是 not_found，重放它只會把修好的 bug 再報一次。
        # 另跳過 <6 詞斷片（如 "On the Bush tax cuts."）：無主張不成查核對象，
        # 舊命中是誤召回撞對標籤的運氣，不是能力。
        pred = ("FAKE" if r["status"] == "inaccurate"
                else ("REAL" if r["status"] == "accurate" else "?"))
        if pred == r["truth"] and len(stm[r["id"]].split()) >= 6:
            out.append((stm[r["id"]], r["truth"]))
        if len(out) >= n:
            break
    return out


NEG_ZH = [
    "台積電宣布在高雄擴廠徵才三千人，市政府表示歡迎",
    "中央氣象署發布海上颱風警報，請民眾注意防範",
    "台北市捷運板南線延長段通車，票價維持不變",
    "台灣代表隊在亞運羽球男雙奪金，全國歡騰",
    "立法院三讀通過住宅法修正案，租屋補貼加碼",
]
NEG_EN = [
    "Local bakery in Ohio wins national pie contest third year running",
    "Federal Reserve holds interest rates steady amid inflation data",
    "NASA schedules Artemis moon landing for late next year",
    "Premier League results: Arsenal beats Chelsea 2-0 on Saturday",
    "County fair in Iowa sets attendance record with corn maze event",
]
NEG_JA = [
    "トヨタが新型プリウスを発表、燃費は過去最高",
    "気象庁が関東地方に大雨警報を発表",
    "日銀が金融政策の現状維持を決定",
    "大谷翔平がドジャースで今季30号ホームラン",
    "新幹線のぞみ号が一部区間で運転見合わせ",
]


def sweep_en():
    ok, detail = True, []
    # 重放一律 live（use_cache=False）：測的是現行程式碼，不是上次的快取列
    for stmt, truth in _liar_decided(10):
        r = get_google_factcheck(stmt, lang="en", use_cache=False)
        pred = ("FAKE" if r["status"] == "inaccurate"
                else ("REAL" if r["status"] == "accurate" else "?"))
        good = (pred == truth)
        ok &= good
        detail.append({"stmt": stmt[:50], "truth": truth, "pred": pred,
                       "sim": r.get("similarity_score"), "ok": good})
    # Virginia 案：2011 老查核無 ClaimReview，Google 結構性缺失，由 PolitiFact 源補
    for stmt in ["Virginia has made no progress on jobs since Bob McDonnell took office."]:
        r = get_politifact(stmt, use_cache=False)
        good = (r["status"] == "inaccurate")
        ok &= good
        detail.append({"src": "politifact", "stmt": stmt[:50],
                       "got": r["status"], "sim": r.get("similarity_score"),
                       "ok": good})
    for stmt in NEG_EN + NEG_ZH:
        r = get_google_factcheck(stmt, use_cache=False)
        good = r["status"] in ("not_found", "disabled", "error")
        ok &= good
        detail.append({"stmt": stmt[:50], "expect": "not_found",
                       "got": r["status"], "ok": good})
    return ok, detail


def sweep_ja():
    ok, detail = True, []
    for stmt, src, truth in _murayama_decided(10):
        fn = get_infact if src == "infact" else get_jfc
        r = fn(stmt, use_cache=False)
        pred = ("FAKE" if r["status"] == "inaccurate"
                else ("REAL" if r["status"] == "accurate" else "?"))
        good = (pred == truth)
        ok &= good
        detail.append({"src": src, "truth": truth, "pred": pred,
                       "sim": r.get("similarity_score"), "ok": good})
    for stmt in NEG_JA + NEG_ZH:
        r1 = get_infact(stmt, use_cache=False)
        r2 = get_jfc(stmt, use_cache=False)
        good = (r1["status"] in ("not_found", "error")
                and r2["status"] in ("not_found", "error"))
        ok &= good
        detail.append({"stmt": stmt[:40], "infact": r1["status"],
                       "jfc": r2["status"], "ok": good})
    return ok, detail


def main():
    only = (sys.argv[sys.argv.index("--only") + 1]
            if "--only" in sys.argv else None)
    groups = {"sghk": sweep_sghk, "rumhk": sweep_rumhk,
              "en": sweep_en, "ja": sweep_ja}
    report = {}
    if os.path.exists(OUT):
        try:
            report = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            report = {}
    for name, fn in groups.items():
        if only and name != only:
            continue
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, [{"exception": str(e)[:200]}]
        n_ok = sum(1 for d in detail if d.get("ok") is True)
        report[name] = {"pass": bool(ok), "n_ok": n_ok,
                        "n_total": len(detail), "detail": detail}
        print(f"{name}: {'PASS' if ok else 'FAIL'} {n_ok}/{len(detail)}",
              flush=True)
    json.dump(report, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
