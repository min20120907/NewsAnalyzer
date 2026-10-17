# -*- coding: utf-8 -*-
"""60 筆三類評測：REAL 改寫真新聞 / BAIT 真內容釣魚標題 / FAKE 憑空捏造。
跑法：cd python && ../.venv/bin/python eval_bait60.py
輸出 eval_bait60_results.jsonl + 結尾印正確度（定義見 CORRECT）。
(需 fake-news-server.service 在 :5000，約 1-3 小時，建議 background 跑)
"""
import json, os, sys, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
SERVER = "http://localhost:5000"
TIMEOUT = 170
FILES = ["eval_bait60_REAL.jsonl", "eval_bait60_BAIT.jsonl", "eval_bait60_FAKE.jsonl"]
OUT = os.path.join(BASE, "eval_bait60_results.jsonl")


def correct(group, final):
    if group == "REAL":
        return final >= 60.0
    if group == "BAIT":
        return final <= 60.0
    return final < 60.0  # FAKE：沒被當可信就算對（<40 記優，另計）


def main():
    items = []
    for f in FILES:
        with open(os.path.join(BASE, f), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
    print(f"[eval60] 共 {len(items)} 筆", flush=True)
    ok = {"REAL": [0, 0], "BAIT": [0, 0], "FAKE": [0, 0]}
    bait_hit = [0, 0]  # title_bait 觸發率（BAIT 組）
    with open(OUT, "w", encoding="utf-8") as out:
        for i, it in enumerate(items, 1):
            final, fc, tb, clamp = None, "ERR", None, ""
            for attempt in range(2):
                try:
                    r = requests.post(
                        f"{SERVER}/judge",
                        json={"title": it["title"], "content": it["content"],
                              "url": it.get("url", ""), "mode": "fast"},
                        timeout=TIMEOUT)
                    d = r.json()
                    final = float(d.get("final_score", -1))
                    m = d.get("metrics", {})
                    fc = (m.get("fact_check") or {}).get("desc", "?")
                    da = d.get("deep_analysis") or {}
                    tb = da.get("title_bait")
                    clamp = d.get("clamp_reason") or ""
                    break
                except Exception as e:
                    print(f"  ! {it['id']} attempt{attempt}: {e}", flush=True)
                    time.sleep(5)
            good = correct(it["group"], final if final is not None else -1)
            ok[it["group"]][1] += 1
            ok[it["group"]][0] += 1 if good else 0
            if it["group"] == "BAIT":
                bait_hit[1] += 1
                bait_hit[0] += 1 if tb else 0
            out.write(json.dumps({
                "id": it["id"], "group": it["group"], "gt_band": it.get("gt_band"),
                "final": round(final, 1) if final is not None else None,
                "fact_check": fc, "title_bait": tb,
                "clamped": bool(clamp), "correct": bool(good),
            }, ensure_ascii=False) + "\n")
            out.flush()
            # 2026-10-16：連打會吃 Cofacts 間歇 403，自己節流 2s（退避是接住，
            # 節流是預防）。
            time.sleep(2)
            print(f"[{i}/{len(items)}] {it['id']} {it['group']} final={final} "
                  f"fc={fc} bait={tb} {'OK' if good else 'MISS'}", flush=True)
    print("==== 正確度 ====")
    tot_ok = tot_n = 0
    for g, (a, b) in ok.items():
        print(f"{g}: {a}/{b} = {a/b:.1%}" if b else f"{g}: 0/0")
        tot_ok += a
        tot_n += b
    print(f"TOTAL: {tot_ok}/{tot_n} = {tot_ok/tot_n:.1%}" if tot_n else "無資料")
    print(f"BAIT 組 title_bait 觸發率: {bait_hit[0]}/{bait_hit[1]}")


if __name__ == "__main__":
    main()
