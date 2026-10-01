# -*- coding: utf-8 -*-
"""判決協定對照：desc-based vs score<55 vs score<60（系統）與零樣本 baseline 對齊。

資料：
  system_500.jsonl        — 系統 desc 判定（cm_system_500 版）
  clamp_ablation_500.jsonl— 系統 final_score（生產線 τ=25；含 post_fusion_score）
  metrics_500.jsonl       — 系統分項（供 ablation 重算）
  fair_baseline_500.jsonl — 零樣本 Qwen-27B credibility score
輸出：螢幕對照表（不落檔）。
"""
import json
import math
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(BASE, "data", "eval")


def load(name):
    return [json.loads(l) for l in open(os.path.join(D, name), encoding="utf-8")]


def cm(pairs):
    tp = sum(1 for t, p in pairs if t == "FAKE" and p == "FAKE")
    fp = sum(1 for t, p in pairs if t == "REAL" and p == "FAKE")
    fn = sum(1 for t, p in pairs if t == "FAKE" and p == "REAL")
    tn = sum(1 for t, p in pairs if t == "REAL" and p == "REAL")
    n = len(pairs)
    return {"n": n, "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "acc": round((tp + tn) / n, 4) if n else 0}


def fmt(name, m):
    return (f"{name:<28} n={m['n']:>4}  acc={m['acc']:.4f}  "
            f"TP={m['TP']:>3} FP={m['FP']:>3} FN={m['FN']:>3} TN={m['TN']:>3}")


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2.0 * sum(math.comb(n, i) * 0.5 ** n for i in range(k + 1)))


system = {r["rowid"]: r for r in load("system_500.jsonl")}
clamp = {r["rowid"]: r for r in load("clamp_ablation_500.jsonl")}
fair = {r["rowid"]: r for r in load("fair_baseline_500.jsonl")}

print("=" * 78)
print("A) 系統三種判定（各以自身可得樣本）")
# A1: desc-based（既有協定；UNKNOWN 排除）
pairs = [(r["true"], r["pred"]) for r in system.values()
         if r["pred"] in ("FAKE", "REAL")]
print(fmt("desc-based (UNKNOWN excluded)", cm(pairs)))
# A2/A3: score-based（final < cutoff → FAKE；全筆排除 error）
for cut in (55, 60):
    pairs = [(r["true"], "FAKE" if r["final_score"] < cut else "REAL")
             for r in clamp.values()
             if r.get("final_score") is not None and not r.get("error")]
    print(fmt(f"score<{cut} (final_score)", cm(pairs)))

print("=" * 78)
print("B) 零樣本 Qwen-27B")
for cut in (55, 60):
    pairs = [(r["true"], "FAKE" if r["score"] < cut else "REAL")
             for r in fair.values()
             if r.get("score") is not None]
    print(fmt(f"zero-shot score<{cut}", cm(pairs)))

print("=" * 78)
print("C) Paired（交集 = 兩邊都有分數/判定；同 rowid）")
common = [rid for rid in clamp if rid in fair
          and clamp[rid].get("final_score") is not None
          and not clamp[rid].get("error") and fair[rid].get("score") is not None]
print(f"交集 n={len(common)}（clamp∩fair 皆有值）")
for cut in (55, 60):
    ok_s = [1 if ("FAKE" if clamp[r]["final_score"] < cut else "REAL") == clamp[r]["true"] else 0
            for r in common]
    ok_f = [1 if ("FAKE" if fair[r]["score"] < cut else "REAL") == fair[r]["true"] else 0
            for r in common]
    n = len(common)
    acc_s, acc_f = sum(ok_s) / n, sum(ok_f) / n
    b = sum(1 for a, c in zip(ok_s, ok_f) if a == 1 and c == 0)
    c_ = sum(1 for a, c in zip(ok_s, ok_f) if a == 0 and c == 1)
    print(f"cut<{cut}: sys={acc_s:.4f} fair={acc_f:.4f} "
          f"diff={acc_s-acc_f:+.4f} McNemar b={b} c={c_} p={mcnemar_exact(b, c_):.2e}")
# desc vs (55/60) 的同批一致性
common_d = [rid for rid in system if rid in fair
            and system[rid]["pred"] in ("FAKE", "REAL") and fair[rid].get("score") is not None]
ok_s = [1 if system[r]["pred"] == system[r]["true"] else 0 for r in common_d]
ok_f = [1 if ("FAKE" if fair[r]["score"] < 55 else "REAL") == fair[r]["true"] else 0
        for r in common_d]
n = len(common_d)
b = sum(1 for a, c in zip(ok_s, ok_f) if a == 1 and c == 0)
c_ = sum(1 for a, c in zip(ok_s, ok_f) if a == 0 and c == 1)
print(f"desc(既有) vs zero-shot<55 配對: n={n} sys={sum(ok_s)/n:.4f} fair={sum(ok_f)/n:.4f} "
      f"diff={sum(ok_s)/n-sum(ok_f)/n:+.4f} b={b} c={c_} p={mcnemar_exact(b,c_):.2e}")

print("=" * 78)
print("D) 系統 desc 判定 vs score<55 判定的分歧解剖（同批 clamp∩system）")
both = [rid for rid in system if rid in clamp
        and system[rid]["pred"] in ("FAKE", "REAL")
        and clamp[rid].get("final_score") is not None]
flip = []
for r in both:
    desc_p = system[r]["pred"]
    score_p = "FAKE" if clamp[r]["final_score"] < 55 else "REAL"
    if desc_p != score_p:
        flip.append((r, system[r]["true"], desc_p, score_p,
                     clamp[r]["final_score"], system[r]["desc"]))
print(f"分歧 {len(flip)}/{len(both)} 筆")
import collections
cnt = collections.Counter((f[2], f[3], f[5]) for f in flip)
for k, v in cnt.most_common(12):
    print(f"  desc={k[0]:<5} score={k[1]:<5} 來源={k[2]:<10} ×{v}")

print("=" * 78)
print("E) calibration：P(FAKE|band)，五帶（final_score 與 post_fusion_score）")
BANDS = [(0, 20), (20, 40), (40, 60), (60, 75), (75, 101)]
for field in ("final_score", "post_fusion_score"):
    print(f"-- {field}")
    for lo, hi in BANDS:
        sub = [r for r in clamp.values()
               if r.get(field) is not None and not r.get("error")
               and lo <= r[field] < hi]
        nf = sum(1 for r in sub if r["true"] == "FAKE")
        pf = round(nf / len(sub), 3) if sub else None
        print(f"  [{lo:>3},{hi:>3}): n={len(sub):>3}  FAKE={nf:>3}  P(FAKE)={pf}")
