#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval_wsdm.py — 用 WSDM / ByteDance 2019 中文假新聞標題集 (wsdm_fake_news_2000.csv)
測 NewsAnalyzer 的準確度。

資料集特性（先講清楚，避免誤讀）：
  - 來源：中國大陸 ByteDance 2019 假新聞標題，與台灣 Cofacts 分布不同。
  - 標籤：is_fake=true   → 假新聞
          is_fake=false  → 真新聞
  - /judge 原生輸出：inaccurate / partial / accurate / not_found，不是 0/1 真假。
    因此「直接打 /judge」對 WSDM 標題大部分會 not_found（Cofacts 沒收陸版謠言），
    這本身就是一個誠實結論，不代表 /judge 壞掉。

兩種測法：
  [A] /judge 直接打（走 gemma4:12b + Cofacts）：
        inaccurate/partial → 判為 假 (fake)
        accurate           → 判為 真 (real)
        not_found          → 無結論（計入 coverage 缺口）
      這測的是系統「原生」對陸版標題的覆蓋與判斷。

  [B] 本地 SBERT 近鄰跨域遷移（不調 gemma4，純檢索）：
        把 WSDM 標題對映到種子 Cofacts 語料最近鄰，取鄰居 status 轉真假。
        這測的是「跨域零樣本遷移」上限，非系統主用途，僅供參考。

用法：
  python eval_wsdm.py --mode A        # 只跑 /judge 直接打
  python eval_wsdm.py --mode B        # 只跑本地近鄰遷移
  python eval_wsdm.py                 # 兩者都跑
"""
import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cofacts_local import local_match

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "eval", "wsdm_fake_news_2000.csv")

# /judge 端點（本機服務）
import requests

JUDGE_URL = "http://127.0.0.1:5000/judge"


def load_wsdm(path):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            title = (row.get("news_title") or "").strip().strip('"').strip()
            lab = (row.get("is_fake") or "").strip().lower()
            if not title or lab not in ("true", "false"):
                continue
            out.append((title, lab))  # lab: 'true'=fake, 'false'=real
    return out


def judge_to_binary(r):
    """把 /judge 回傳 verdict 映到 0/1 (1=fake)。"""
    s = r.get("fact_check", {}).get("status") or r.get("status")
    if s in ("inaccurate", "partial"):
        return 1
    if s == "accurate":
        return 0
    return None  # not_found / unknown


def mode_a(items):
    """直接打 /judge。"""
    tp = fp = fn = tn = unk = 0
    samples = []
    for title, lab in items:
        y_true = 1 if lab == "true" else 0
        try:
            resp = requests.post(JUDGE_URL, json={"text": title}, timeout=60)
            r = resp.json()
        except Exception as e:
            unk += 1
            samples.append({"title": title, "true": "FAKE" if y_true else "REAL",
                            "pred": "ERROR", "desc": str(e), "sim": None})
            continue
        pred = judge_to_binary(r)
        samples.append({"title": title, "true": "FAKE" if y_true else "REAL",
                        "pred": ("FAKE" if pred == 1 else "REAL") if pred is not None else "UNKNOWN",
                        "desc": r.get("fact_check", {}).get("status"), "sim": None})
        if pred is None:
            unk += 1
            continue
        if pred == 1 and y_true == 1:
            tp += 1
        elif pred == 1 and y_true == 0:
            fp += 1
        elif pred == 0 and y_true == 1:
            fn += 1
        else:
            tn += 1
    total = len(items)
    decided = tp + fp + fn + tn
    acc = (tp + tn) / decided if decided else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    cov = decided / total if total else 0.0
    return {
        "mode": "A (/judge 直接打)",
        "total": total, "decided": decided, "not_found": unk,
        "coverage": cov, "accuracy": acc,
        "precision(fake)": prec, "recall(fake)": rec, "f1(fake)": f1,
        "confusion": {"TP": tp, "FP": fp, "FN": fn, "TN": tn},
        "samples": samples,
    }


def mode_b(items):
    """本地 SBERT 近鄰遷移（不調 LLM）。"""
    tp = fp = fn = tn = unk = 0
    sims = []
    samples = []
    for title, lab in items:
        y_true = 1 if lab == "true" else 0
        m = local_match(title, threshold=0.55)
        if not m:
            unk += 1
            samples.append({"title": title, "true": "FAKE" if y_true else "REAL",
                            "pred": "UNKNOWN", "sim": None,
                            "matched": None, "nn_status": None})
            continue
        sims.append(m["sim"])
        pred = 1 if m["status"] in ("inaccurate", "partial") else 0
        samples.append({"title": title, "true": "FAKE" if y_true else "REAL",
                        "pred": "FAKE" if pred else "REAL", "sim": round(m["sim"], 3),
                        "matched": m.get("matched_text"), "nn_status": m["status"]})
        if pred == 1 and y_true == 1:
            tp += 1
        elif pred == 1 and y_true == 0:
            fp += 1
        elif pred == 0 and y_true == 1:
            fn += 1
        else:
            tn += 1
    total = len(items)
    decided = tp + fp + fn + tn
    acc = (tp + tn) / decided if decided else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    cov = decided / total if total else 0.0
    avg_sim = sum(sims) / len(sims) if sims else 0.0
    return {
        "mode": "B (本地 SBERT 近鄰遷移)",
        "total": total, "decided": decided, "not_found": unk,
        "coverage": cov, "accuracy": acc,
        "precision(fake)": prec, "recall(fake)": rec, "f1(fake)": f1,
        "avg_sim": avg_sim,
        "confusion": {"TP": tp, "FP": fp, "FN": fn, "TN": tn},
        "samples": samples,
    }


def fmt(r):
    return (
        f"\n=== {r['mode']} ===\n"
        f"total={r['total']}  decided={r['decided']}  not_found={r['not_found']}  "
        f"coverage={r['coverage']:.3f}\n"
        f"accuracy={r['accuracy']:.3f}  "
        f"P(fake)={r['precision(fake)']:.3f}  R(fake)={r['recall(fake)']:.3f}  "
        f"F1(fake)={r['f1(fake)']:.3f}\n"
        f"confusion TP={r['confusion']['TP']} FP={r['confusion']['FP']} "
        f"FN={r['confusion']['FN']} TN={r['confusion']['TN']}\n"
        + (f"avg_sim={r['avg_sim']:.3f}\n" if "avg_sim" in r else "")
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["A", "B", "both"], default="both")
    ap.add_argument("--limit", type=int, default=0, help="只取前 N 筆（除錯用）")
    args = ap.parse_args()

    items = load_wsdm(CSV_PATH)
    if args.limit:
        items = items[: args.limit]
    print(f"WSDM 樣本數: {len(items)}")

    def dump_samples(name, res):
        import json as _j
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
        with open(p, "w", encoding="utf-8") as fh:
            for s in res["samples"]:
                fh.write(_j.dumps(s, ensure_ascii=False) + "\n")
        wrong = [s for s in res["samples"]
                 if s["pred"] in ("FAKE", "REAL") and s["pred"] != s["true"]]
        correct = [s for s in res["samples"]
                   if s["pred"] in ("FAKE", "REAL") and s["pred"] == s["true"]]
        unk = sum(1 for s in res["samples"] if s["pred"] in ("UNKNOWN", "ERROR"))
        print("=" * 60)
        print(f"[{res['mode']}] 誤判 {len(wrong)} / 判對 {len(correct)} / 無結論 {unk}")
        print("【誤判範例 (true→pred, sim, 命中台灣語料)】")
        for s in wrong[:10]:
            sc = f" sim={s['sim']}" if s.get("sim") else ""
            print(f"  [{s['true']}→{s['pred']}]{sc} | {s['title'][:45]}")
            if s.get("matched"):
                print(f"       ↳ NN命中: {s['matched']} (status={s.get('nn_status')})")
        print("【判對範例】")
        for s in correct[:10]:
            sc = f" sim={s['sim']}" if s.get("sim") else ""
            print(f"  [{s['true']}]{sc} | {s['title'][:45]}")
            if s.get("matched"):
                print(f"       ↳ NN命中: {s['matched']} (status={s.get('nn_status')})")
        print("=" * 60)

    if args.mode in ("A", "both"):
        t = time.time()
        ra = mode_a(items)
        print(fmt(ra), f"[用時 {time.time()-t:.1f}s]")
        dump_samples("wsdm_modeA_samples.jsonl", ra)
    if args.mode in ("B", "both"):
        t = time.time()
        rb = mode_b(items)
        print(fmt(rb), f"[用時 {time.time()-t:.1f}s]")
        dump_samples("wsdm_modeB_samples.jsonl", rb)

