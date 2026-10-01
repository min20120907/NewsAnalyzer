# -*- coding: utf-8 -*-
"""混淆矩陣比較：同一 500 筆樣本跑 NewsAnalyzer /judge（擾動輸入，強制即時檢索）。

樣本：data/eval/fair_baseline_500.jsonl 的 rowid（與 Zero-shot Qwen-27B 同一樣本）。
擾動與判定規則：與 python/eval_accuracy.py 完全一致（_perturb + desc 映射）。
輸出：data/eval/system_500.jsonl（逐筆）+ data/eval/cm_compare.json（雙方混淆矩陣）。

用法: cd ~/Documents/Web_and_App_Development/NewsAnalyzer && .venv/bin/python scripts/cm_system_500.py
（需 fake-news-server.service 於 :5000 運行中）
"""
import json
import os
import sqlite3
import time

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "cofacts", "cofacts_cache.db")
FAIR_JSONL = os.path.join(BASE, "data", "eval", "fair_baseline_500.jsonl")
OUT_JSONL = os.path.join(BASE, "data", "eval", "system_500.jsonl")
OUT_CM = os.path.join(BASE, "data", "eval", "cm_compare.json")

SERVER = os.environ.get("JUDGE_URL", "http://localhost:5000")
TIMEOUT = 120


def to_binary(label):
    return "FAKE" if label in ("inaccurate", "partial") else "REAL"


def _perturb(txt):
    txt = (txt or "").strip()
    body = txt[:max(10, int(len(txt) * 0.85))]
    return "網傳：" + body


def judge(probe):
    r = requests.post(f"{SERVER}/judge", json={"content": probe}, timeout=TIMEOUT)
    d = r.json()
    m = d.get("metrics", {})
    fc = m.get("fact_check", {})
    desc = fc.get("desc", "not_found")
    pred = ("FAKE" if desc in ("inaccurate", "partial")
            else "REAL" if desc == "accurate" else "UNKNOWN")
    return pred, desc, fc.get("sim")


def cm_of(recs):
    pairs = [(r["true"], r["pred"]) for r in recs if r["pred"] in ("FAKE", "REAL")]
    tp = sum(1 for t, p in pairs if t == "FAKE" and p == "FAKE")
    fp = sum(1 for t, p in pairs if t == "REAL" and p == "FAKE")
    fn = sum(1 for t, p in pairs if t == "FAKE" and p == "REAL")
    tn = sum(1 for t, p in pairs if t == "REAL" and p == "REAL")
    n = len(pairs)
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    return {"n": len(recs), "n_valid": n, "n_unknown": len(recs) - n,
            "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "acc": round((tp + tn) / n, 4) if n else 0,
            "precision_fake": round(prec, 4), "recall_fake": round(rec, 4),
            "f1_fake": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0}


def main():
    with open(FAIR_JSONL, encoding="utf-8") as f:
        fair = [json.loads(l) for l in f]
    rowids = [r["rowid"] for r in fair]
    con = sqlite3.connect(DB)
    txtmap = {r: t for r, t in con.execute(
        f"SELECT rowid, text FROM corpus WHERE rowid IN ({','.join('?' * len(rowids))})", rowids)}
    con.close()

    done = {}
    if os.path.exists(OUT_JSONL):
        with open(OUT_JSONL, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done[r["rowid"]] = r
                except Exception:
                    pass
    print(f"樣本 {len(rowids)} 筆，已完成 {len(done)} 筆", flush=True)
    fout = open(OUT_JSONL, "a", encoding="utf-8")
    t_all = time.perf_counter()
    for i, r in enumerate(fair, 1):
        if r["rowid"] in done:
            continue
        probe = _perturb(txtmap.get(r["rowid"], ""))
        try:
            pred, desc, sim = judge(probe)
            err = None
        except Exception as e:
            pred, desc, sim, err = "ERROR", None, None, f"{type(e).__name__}: {e}"
        fout.write(json.dumps({"rowid": r["rowid"], "true": to_binary(r["status"]),
                               "status": r["status"], "pred": pred, "desc": desc,
                               "sim": sim, "error": err}, ensure_ascii=False) + "\n")
        fout.flush()
        if i % 25 == 0 or i == len(fair):
            print(f"[{i}/{len(fair)}] elapsed={(time.perf_counter()-t_all)/60:.1f}min", flush=True)
    fout.close()

    sys_recs = list(done.values())
    with open(OUT_JSONL, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["rowid"] not in done:
                sys_recs.append(r)
    sys_recs = [r for r in sys_recs if r["pred"] != "ERROR"]
    result = {"newsanalyzer": cm_of(sys_recs),
              "zeroshot_qwen27": cm_of(
                  [{**r, "pred": ("ERROR" if r["pred"] == "ERROR" else r["pred"])}
                   for r in fair if r["pred"] != "ERROR"])}
    with open(OUT_CM, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("CM: " + json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
