# -*- coding: utf-8 -*-
"""LIAR test 集英文證據源評測：get_google_factcheck(lang=en) 的覆蓋率與選擇性準確率。

Usage: .venv/bin/python scripts/eval_liar_en.py [--n 200] [--in /tmp/liar_ds/test.tsv]
輸出 data/eval/liar_en.jsonl（逐筆續跑）+ liar_en_summary.json。
二值化：FAKE={pants-fire,false,barely-true}，REAL={half-true,mostly-true,true}。
partial 不計入 selective accuracy（另報筆數）。
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "python"))
from factcheck_multi import get_google_factcheck  # noqa: E402

FAKE = {"pants-fire", "false", "barely-true"}

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "data", "eval", "liar_en.jsonl")
SUM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "data", "eval", "liar_en_summary.json")


def main():
    n = int((sys.argv[sys.argv.index("--n") + 1]
             if "--n" in sys.argv else 200))
    tsv = (sys.argv[sys.argv.index("--in") + 1]
           if "--in" in sys.argv else "/tmp/liar_ds/test.tsv")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["id"])
                except Exception:
                    pass
    rows = []
    with open(tsv, encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t"):
            if len(r) >= 3 and r[0] not in done:
                rows.append((r[0], r[1], r[2]))
    rows = rows[:n]
    print(f"todo={len(rows)} skip_done={len(done)}")
    fout = open(OUT, "a", encoding="utf-8")
    for i, (rid, label, stmt) in enumerate(rows):
        truth = "FAKE" if label in FAKE else "REAL"
        try:
            r = get_google_factcheck(stmt, lang="en", use_cache=True)
            rec = {"id": rid, "label": label, "truth": truth,
                   "status": r.get("status"),
                   "sim": r.get("similarity_score"),
                   "matched": (r.get("matched_text") or "")[:100],
                   "url": r.get("url")}
        except Exception as e:  # noqa: BLE001
            rec = {"id": rid, "label": label, "truth": truth,
                   "status": "error", "note": str(e)[:100]}
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(rows)}", flush=True)
    fout.close()
    # 汇总（全量 jsonl 重算，含之前续跑的）
    recs = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    cov = [r for r in recs if r["status"] in ("inaccurate", "accurate",
                                              "partial")]
    dec = [r for r in recs if r["status"] in ("inaccurate", "accurate")]
    pred = lambda r: "FAKE" if r["status"] == "inaccurate" else "REAL"  # noqa: E731
    tp = sum(1 for r in dec if pred(r) == "FAKE" and r["truth"] == "FAKE")
    sel_acc = (sum(1 for r in dec if pred(r) == r["truth"]) / len(dec)
               if dec else 0.0)
    summary = {"n": len(recs),
               "coverage": round(len(cov) / len(recs), 4) if recs else 0,
               "selective_acc": round(sel_acc, 4),
               "decided": len(dec),
               "partial": sum(1 for r in recs if r["status"] == "partial"),
               "tp_fake": tp,
               "not_found": sum(1 for r in recs
                                if r["status"] == "not_found"),
               "error": sum(1 for r in recs if r["status"] == "error")}
    json.dump(summary, open(SUM, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
