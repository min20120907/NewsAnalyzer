# -*- coding: utf-8 -*-
"""Exp8 latency：/judge 分項計時（warm-up 50＋正式 500 次，median/P95/P99）。

注意：會獨佔 server queue，不可與任何背景採集並行。跑前確認
data/eval/metrics_500.jsonl、clamp_ablation_500.jsonl 已完成。
探針：corpus 隨機 200 筆原文（seed=42），短文本，避開 deep_analyze 長文本極端值；
另記 deep 有/無命中的分層中位數。timings 取自 /judge 回傳（server 端實測），
client 端另記 total round-trip 供交叉驗證。
輸出：data/eval/latency.json；印 Table 5 草稿。

用法: .venv/bin/python scripts/measure_latency.py [--n 2000] [--warmup 50]
"""
import argparse
import json
import os
import random
import sqlite3
import time

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "cofacts", "cofacts_cache.db")
OUT_JSON = os.path.join(BASE, "data", "eval", "latency.json")
SERVER = os.environ.get("JUDGE_URL", "http://localhost:5000")
TIMEOUT = 180
STAGES = ("extract", "sentiment", "fact_check", "similarity", "web_search",
          "deep_analyze", "scoring", "total")


def pct(xs, q):
    if not xs:
        return None
    ys = sorted(xs)
    i = min(len(ys) - 1, int(q / 100 * len(ys)))
    return round(ys[i], 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--warmup", type=int, default=50)
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    texts = [t for (t,) in con.execute(
        "SELECT text FROM corpus WHERE length(text) BETWEEN 60 AND 600")]
    con.close()
    rng = random.Random(42)
    probes = rng.sample(texts, min(200, len(texts)))
    print(f"候選探針池 {len(texts)} 筆，取 {len(probes)} 筆輪流打", flush=True)

    def one(txt):
        t0 = time.perf_counter()
        d = requests.post(f"{SERVER}/judge", json={"content": txt},
                          timeout=TIMEOUT).json()
        rt = (time.perf_counter() - t0) * 1000
        return d, rt

    for i in range(args.warmup):
        one(probes[i % len(probes)])
    print(f"warm-up {args.warmup} 次完成", flush=True)

    stage_vals = {s: [] for s in STAGES}
    rts, deep_hit, deep_miss = [], [], []
    t_all = time.perf_counter()
    for i in range(args.n):
        try:
            d, rt = one(probes[i % len(probes)])
            rts.append(rt)
            tm = d.get("timings") or {}
            for s in STAGES:
                if tm.get(s) is not None:
                    stage_vals[s].append(float(tm[s]))
            deep = (d.get("deep_analysis") or {}).get("credibility_score")
            (deep_hit if deep is not None else deep_miss).append(rt)
        except Exception as e:
            print(f"  ! #{i} {type(e).__name__}: {e}", flush=True)
        if (i + 1) % 200 == 0:
            print(f"[{i+1}/{args.n}] elapsed={(time.perf_counter()-t_all)/60:.1f}min",
                  flush=True)
    out = {"n": args.n, "warmup": args.warmup, "ok": len(rts),
           "stages": {s: {"n": len(v), "median": pct(v, 50),
                          "p95": pct(v, 95), "p99": pct(v, 99)}
                      for s, v in stage_vals.items()},
           "roundtrip_ms": {"median": pct(rts, 50), "p95": pct(rts, 95),
                            "p99": pct(rts, 99)},
           "deep_hit_ms": {"n": len(deep_hit), "median": pct(deep_hit, 50)},
           "deep_miss_ms": {"n": len(deep_miss), "median": pct(deep_miss, 50)}}
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{'stage':<12} {'n':>5} {'median':>8} {'P95':>8} {'P99':>8} (ms)")
    for s in STAGES:
        m = out["stages"][s]
        print(f"{s:<12} {m['n']:5d} {str(m['median']):>8} {str(m['p95']):>8} {str(m['p99']):>8}")
    print(f"round-trip median={out['roundtrip_ms']['median']}ms "
          f"P95={out['roundtrip_ms']['p95']}ms P99={out['roundtrip_ms']['p99']}ms")
    print(f"已寫入 {OUT_JSON}")


if __name__ == "__main__":
    main()
