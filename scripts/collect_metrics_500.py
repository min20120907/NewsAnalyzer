# -*- coding: utf-8 -*-
"""Exp5 原料：重採同一 500 筆 /judge，存完整 metrics 分項（供離線 component ablation）。

樣本/擾動：與 collect_clamp_500.py 完全一致（fair_baseline_500.jsonl 的 rowid + _perturb）。
輸出：data/eval/metrics_500.jsonl（逐筆：metrics[6分項 score/weight]、rule_score、
fusion_weight、deep_cs、sources[status/sim]、final/post、clamped、desc）。
約 74 分鐘，背景跑；與 Exp8 latency 不可並行（都會打爆 server queue）。

用法: .venv/bin/python scripts/collect_metrics_500.py
"""
import json
import os
import sqlite3
import time

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "cofacts", "cofacts_cache.db")
FAIR_JSONL = os.path.join(BASE, "data", "eval", "fair_baseline_500.jsonl")
OUT_JSONL = os.path.join(BASE, "data", "eval", "metrics_500.jsonl")

SERVER = os.environ.get("JUDGE_URL", "http://localhost:5000")
TIMEOUT = 120
COMPS = ("sentiment", "domain", "fact_check", "user_feedback",
         "similarity", "timeliness")


def _perturb(txt):
    txt = (txt or "").strip()
    body = txt[:max(10, int(len(txt) * 0.85))]
    return "網傳：" + body


def main():
    with open(FAIR_JSONL, encoding="utf-8") as f:
        fair = [json.loads(l) for l in f]
    rowids = [r["rowid"] for r in fair]
    con = sqlite3.connect(DB)
    txtmap = {r: t for r, t in con.execute(
        f"SELECT rowid, text FROM corpus WHERE rowid IN ({','.join('?' * len(rowids))})", rowids)}
    con.close()
    truemap = {}
    for r in fair:
        truemap[r["rowid"]] = ("FAKE" if r["true"] in ("inaccurate", "partial", "FAKE")
                               else "REAL")

    done = set()
    if os.path.exists(OUT_JSONL):
        with open(OUT_JSONL, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["rowid"])
                except Exception:
                    pass
    print(f"樣本 {len(rowids)} 筆，已完成 {len(done)} 筆", flush=True)
    fout = open(OUT_JSONL, "a", encoding="utf-8")
    t_all = time.perf_counter()
    for i, r in enumerate(fair, 1):
        rid = r["rowid"]
        if rid in done:
            continue
        probe = _perturb(txtmap.get(rid, ""))
        rec = {"rowid": rid, "true": truemap[rid], "error": None}
        try:
            t0 = time.perf_counter()
            d = requests.post(f"{SERVER}/judge", json={"content": probe},
                              timeout=TIMEOUT).json()
            rec["lat_s"] = round(time.perf_counter() - t0, 1)
            mets = d.get("metrics") or {}
            rec["metrics"] = {c: {"score": (mets.get(c) or {}).get("score"),
                                  "weight": (mets.get(c) or {}).get("weight")}
                              for c in COMPS}
            rec["rule_score"] = d.get("rule_score")
            rec["fusion_weight"] = d.get("fusion_weight")
            deep = d.get("deep_analysis") or {}
            rec["deep_cs"] = deep.get("credibility_score")
            rec["sources"] = [
                {"source": s.get("source"), "status": s.get("status"),
                 "sim": s.get("similarity_score")} for s in (d.get("sources") or [])]
            rec["post_fusion_score"] = d.get("post_fusion_score")
            rec["final_score"] = d.get("final_score")
            rec["clamped"] = d.get("clamped")
            fc = mets.get("fact_check", {})
            rec["desc"] = fc.get("desc", "not_found")
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()
        if i % 25 == 0 or i == len(fair):
            print(f"[{i}/{len(fair)}] elapsed={(time.perf_counter()-t_all)/60:.1f}min",
                  flush=True)
    fout.close()
    print(f"完成，總耗時 {(time.perf_counter()-t_all)/60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
