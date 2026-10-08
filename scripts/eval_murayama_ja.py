# -*- coding: utf-8 -*-
"""Murayama 日文假新聞集評測：get_infact/get_jfc 的覆蓋率與選擇性準確率。

資料集：Murayama et al. NAIST LREC 2022（Zenodo 5831617, CC-BY 4.0）
data/eval/murayama_label.tsv（307 筆，FIJ 查核 2019-2021）。
二值化：FAKE={False,Inaccurate,Pants-on-Fire,Misleading}、
REAL={True,Half-True}；Unknown-Evidence/Suspended-Judgment 不計 selective。
partial 不計入 selective accuracy（另報筆數）。

Usage: .venv/bin/python scripts/eval_murayama_ja.py [--n 100]
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "python"))
from factcheck_multi import get_infact, get_jfc  # noqa: E402

FAKE = {"False", "Inaccurate", "Pants-on-Fire", "Misleading"}
SKIP = {"Unknown-Evidence", "Suspended-Judgment"}

EV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "..", "data", "eval")
OUT = os.path.join(EV, "murayama_ja.jsonl")
SUM = os.path.join(EV, "murayama_ja_summary.json")
TSV = os.path.join(EV, "murayama_label.tsv")


def main():
    n = int((sys.argv[sys.argv.index("--n") + 1]
             if "--n" in sys.argv else 100))
    os.makedirs(EV, exist_ok=True)
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["id"])
                except Exception:
                    pass
    rows = []
    with open(TSV, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["ID"] not in done:
                rows.append(r)
    rows = rows[:n]
    print(f"todo={len(rows)} skip_done={len(done)}")
    fout = open(OUT, "a", encoding="utf-8")
    for i, r in enumerate(rows):
        truth = ("SKIP" if r["Q1"] in SKIP
                 else ("FAKE" if r["Q1"] in FAKE else "REAL"))
        stmt = r["Article"]
        rec = {"id": r["ID"], "label": r["Q1"], "truth": truth}
        for src, fn in (("infact", get_infact), ("jfc", get_jfc)):
            try:
                s = fn(stmt, use_cache=True)
                rec[src] = {"status": s.get("status"),
                            "sim": s.get("similarity_score"),
                            "matched": (s.get("matched_text") or "")[:80]}
            except Exception as e:  # noqa: BLE001
                rec[src] = {"status": "error", "note": str(e)[:80]}
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(rows)}", flush=True)
    fout.close()
    recs = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    summary = {"n": len(recs)}
    for src in ("infact", "jfc"):
        cov = [r for r in recs
               if r[src]["status"] in ("inaccurate", "accurate", "partial")]
        dec = [r for r in recs if r[src]["status"] in ("inaccurate",
                                                       "accurate")
               and r["truth"] != "SKIP"]
        def _pred(rr):
            return "FAKE" if rr[src]["status"] == "inaccurate" else "REAL"
        acc = (sum(1 for r in dec if _pred(r) == r["truth"]) / len(dec)
               if dec else 0.0)
        summary[src] = {
            "coverage": round(len(cov) / len(recs), 4) if recs else 0,
            "selective_acc": round(acc, 4), "decided": len(dec),
            "partial": sum(1 for r in recs if r[src]["status"] == "partial"),
            "not_found": sum(1 for r in recs
                              if r[src]["status"] == "not_found")}
    json.dump(summary, open(SUM, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
