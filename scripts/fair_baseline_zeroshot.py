# -*- coding: utf-8 -*-
"""實驗一 Fair Baseline：純 Zero-shot Qwen3.8-27B（關閉 SBERT 檢索+Metadata）.

從 data/cofacts/cofacts_cache.db 的 corpus 分層抽樣 500 筆，
直接把原文餵給 :8088 Qwen3.8-27B，只靠 Prompt 輸出 credibility_score。
二值化：score>=55 → REAL（論文 Table 3 的「大致可信」邊界），否則 FAKE。
真值：accurate → REAL；inaccurate/partial → FAKE（同 eval_accuracy.to_binary）。

用法: cd ~/Documents/Web_and_App_Development/NewsAnalyzer && .venv/bin/python scripts/fair_baseline_zeroshot.py
輸出: data/eval/fair_baseline_500.jsonl + data/eval/fair_baseline_summary.json
"""
import json
import os
import random
import re
import sqlite3
import sys
import time

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "cofacts", "cofacts_cache.db")
OUT_JSONL = os.path.join(BASE, "data", "eval", "fair_baseline_500.jsonl")
OUT_SUM = os.path.join(BASE, "data", "eval", "fair_baseline_summary.json")

QWEN_URL = os.environ.get("QWEN_URL", "http://127.0.0.1:8088/v1/chat/completions")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3.8-27b-fastmtp")
N = int(os.environ.get("FAIR_N", "500"))
SEED = int(os.environ.get("FAIR_SEED", "42"))
CUTOFF = 55
TIMEOUT = 180

PROMPT_TMPL = (
    "你是一位事實查核助手。只根據以下文章內容評估其可信度，"
    "輸出0-100的credibility_score（0=完全不可信，100=完全可信）。"
    "只輸出JSON：{\"credibility_score\": <數字>, \"reason\": \"<50字內理由>\"}，"
    "不要輸出其他內容。\n\n文章："
)


def to_binary(label):
    return "FAKE" if label in ("inaccurate", "partial") else "REAL"


def parse_score(content):
    """從 LLM content 萃取 credibility_score，失敗回 None。"""
    if not content:
        return None, "empty"
    try:
        d = json.loads(content.strip())
        return float(d["credibility_score"]), "json"
    except Exception:
        pass
    m = re.search(r"[\"']?credibility_score[\"']?\s*[:=]\s*(\d+(?:\.\d+)?)", content)
    if m:
        return float(m.group(1)), "regex"
    m = re.search(r"(\d+(?:\.\d+)?)\s*分", content)
    if m:
        return float(m.group(1)), "regex_fallback"
    return None, "unparseable"


def main():
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT rowid, text, status FROM corpus").fetchall()
    con.close()
    rows = [(r, t, s) for r, t, s in rows if t and len(t.strip()) >= 20]
    print(f"母體可用筆數: {len(rows)}", flush=True)

    # 分層等比抽樣（seed 固定可重現）
    by_status = {}
    for r in rows:
        by_status.setdefault(r[2], []).append(r)
    rnd = random.Random(SEED)
    sample = []
    for st, lst in sorted(by_status.items()):
        k = max(1, round(len(lst) / len(rows) * N))
        sample.extend(rnd.sample(lst, min(k, len(lst))))
    # 補齊/截斷到 N
    sample_ids = {r[0] for r in sample}
    rest = [r for r in rows if r[0] not in sample_ids]
    rnd.shuffle(rest)
    if len(sample) > N:
        sample = rnd.sample(sample, N)
    elif len(sample) < N:
        sample = sample + rest[: N - len(sample)]
    print(f"抽樣 {len(sample)} 筆: " +
          ", ".join(f"{st}={sum(1 for r in sample if r[2]==st)}" for st in sorted(by_status)), flush=True)

    # 續跑：跳過已完成的 rowid
    done = set()
    if os.path.exists(OUT_JSONL):
        with open(OUT_JSONL, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["rowid"])
                except Exception:
                    pass
    print(f"已完成 {len(done)} 筆，續跑", flush=True)
    todo = [r for r in sample if r[0] not in done]
    print(f"待跑 {len(todo)} 筆", flush=True)

    fout = open(OUT_JSONL, "a", encoding="utf-8")
    lat = []
    t_all = time.perf_counter()
    for i, (rowid, text, status) in enumerate(todo, 1):
        t0 = time.perf_counter()
        score, how, err = None, None, None
        try:
            r = requests.post(
                QWEN_URL,
                json={"model": QWEN_MODEL,
                      "messages": [{"role": "user", "content": PROMPT_TMPL + text[:2000]}],
                      "max_tokens": 4096, "temperature": 0.0},
                timeout=TIMEOUT)
            d = r.json()
            content = d["choices"][0]["message"].get("content") or ""
            score, how = parse_score(content)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        dt = time.perf_counter() - t0
        lat.append(dt)
        pred = "ERROR" if score is None else ("REAL" if score >= CUTOFF else "FAKE")
        fout.write(json.dumps({"rowid": rowid, "true": to_binary(status),
                               "status": status, "pred": pred, "score": score,
                               "parse": how, "error": err,
                               "latency_s": round(dt, 2)}, ensure_ascii=False) + "\n")
        fout.flush()
        if i % 25 == 0 or i == len(todo):
            avg = sum(lat) / len(lat)
            print(f"[{i}/{len(todo)}] avg_lat={avg:.1f}s elapsed={(time.perf_counter()-t_all)/60:.1f}min", flush=True)

    fout.close()
    # 彙總（只算本次抽樣的 500 筆）
    recs = []
    with open(OUT_JSONL, encoding="utf-8") as f:
        for line in f:
            recs.append(json.loads(line))
    recs = [r for r in recs if r["rowid"] in {s[0] for s in sample}]
    valid = [r for r in recs if r["pred"] != "ERROR"]
    tp = sum(1 for r in valid if r["true"] == "FAKE" and r["pred"] == "FAKE")
    tn = sum(1 for r in valid if r["true"] == "REAL" and r["pred"] == "REAL")
    fp = sum(1 for r in valid if r["true"] == "REAL" and r["pred"] == "FAKE")
    fn = sum(1 for r in valid if r["true"] == "FAKE" and r["pred"] == "REAL")
    acc = (tp + tn) / len(valid) if valid else 0
    summary = {
        "n_sample": len(recs), "n_valid": len(valid),
        "cutoff": CUTOFF, "seed": SEED,
        "accuracy": round(acc, 4),
        "TP": tp, "TN": tn, "FP": fp, "FN": fn,
        "precision_fake": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall_fake": round(tp / (tp + fn), 4) if tp + fn else None,
        "avg_latency_s": round(sum(r["latency_s"] for r in valid) / len(valid), 2) if valid else None,
        "model": QWEN_MODEL,
    }
    with open(OUT_SUM, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("SUMMARY: " + json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
