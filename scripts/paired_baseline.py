# -*- coding: utf-8 -*-
"""Paired baseline v2（cutoff 協定，兩側同門檻）：同一批樣本、同一輸入。

協定：REAL = 分數 ≥ CUTOFF（預設 60 = 系統「大致可信」帶起點），否則 FAKE。
  系統側 = clamp_ablation_500.jsonl 的 final_score（生產線 τ=25）。
  基線側 = fair_baseline_500.jsonl 的 score（zero-shot Qwen3.8-27B）。
交集：兩側分數皆可得（≈498/500）。
指標：雙方 CM、paired accuracy difference、McNemar exact test（two-sided）、
      10,000 次 bootstrap 95% CI（seed 42）。
輸出：data/eval/paired_baseline_c{CUTOFF}.json。

用法: CUTOFF=60 .venv/bin/python scripts/paired_baseline.py（純離線，秒級）
"""
import json
import math
import os
import random

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAMP = os.path.join(BASE, "data", "eval", "clamp_ablation_500.jsonl")
FAIR = os.path.join(BASE, "data", "eval", "fair_baseline_500.jsonl")
CUTOFF = int(os.environ.get("CUTOFF", "60"))
OUT = os.path.join(BASE, "data", "eval", f"paired_baseline_c{CUTOFF}.json")

BOOT = 10000
SEED = 42


def binom_pmf(n, k):
    return math.comb(n, k) * (0.5 ** n)


def mcnemar_exact_p(b, c):
    """Two-sided exact p：discordant 對中 system 對、baseline 錯 = b；反之 = c。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2.0 * sum(binom_pmf(n, i) for i in range(k + 1)))


def cm_of(pairs):
    tp = sum(1 for t, p in pairs if t == "FAKE" and p == "FAKE")
    fp = sum(1 for t, p in pairs if t == "REAL" and p == "FAKE")
    fn = sum(1 for t, p in pairs if t == "FAKE" and p == "REAL")
    tn = sum(1 for t, p in pairs if t == "REAL" and p == "REAL")
    n = len(pairs)
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    return {"n": n, "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "acc": round((tp + tn) / n, 4) if n else 0,
            "precision_fake": round(prec, 4), "recall_fake": round(rec, 4),
            "f1_fake": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0}


def main():
    clamp = {json.loads(l)["rowid"]: json.loads(l)
             for l in open(CLAMP, encoding="utf-8")}
    fair = {json.loads(l)["rowid"]: json.loads(l)
            for l in open(FAIR, encoding="utf-8")}
    common = [rid for rid in clamp
              if rid in fair
              and clamp[rid].get("final_score") is not None
              and not clamp[rid].get("error")
              and fair[rid].get("score") is not None
              and not fair[rid].get("error")]
    print(f"系統有效={len(clamp)} fair 有效="
          f"{sum(1 for r in fair.values() if r.get('score') is not None)} "
          f"交集 n={len(common)}（排除 {500 - len(common)} 筆）")

    def side(rec, key):
        return "FAKE" if rec[key] < CUTOFF else "REAL"

    pairs_sys = [(clamp[r]["true"], side(clamp[r], "final_score")) for r in common]
    pairs_fair = [(fair[r]["true"], side(fair[r], "score")) for r in common]
    mism = [r for r in common if clamp[r]["true"] != fair[r]["true"]]
    assert not mism, f"true 標籤不一致: {mism[:5]}"

    cm_sys = cm_of(pairs_sys)
    cm_fair = cm_of(pairs_fair)
    acc_sys, acc_fair = cm_sys["acc"], cm_fair["acc"]
    diff = round(acc_sys - acc_fair, 4)

    ok_sys = [1 if t == p else 0 for t, p in pairs_sys]
    ok_fair = [1 if t == p else 0 for t, p in pairs_fair]
    b = sum(1 for a, c in zip(ok_sys, ok_fair) if a == 1 and c == 0)
    c = sum(1 for a, c in zip(ok_sys, ok_fair) if a == 0 and c == 1)
    p_val = mcnemar_exact_p(b, c)

    rng = random.Random(SEED)
    n = len(common)
    diffs = []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        a = sum(ok_sys[i] for i in idx) / n
        f = sum(ok_fair[i] for i in idx) / n
        diffs.append(a - f)
    diffs.sort()
    ci = [round(diffs[int(0.025 * BOOT)], 4), round(diffs[int(0.975 * BOOT)], 4)]

    out = {"cutoff": CUTOFF, "n_common": n, "n_excluded": 500 - n,
           "newsanalyzer": cm_sys, "zeroshot_qwen27": cm_fair,
           "paired_acc_diff": diff, "mcnemar_b": b, "mcnemar_c": c,
           "mcnemar_exact_p": round(p_val, 6),
           "bootstrap95_ci": ci, "bootstrap_n": BOOT, "seed": SEED}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"交集 n={n}（cutoff={CUTOFF}）：hybrid acc={acc_sys}  "
          f"zero-shot acc={acc_fair}  paired diff={diff} 95%CI={ci}")
    print(f"McNemar：b(hybrid對/對手錯)={b} c={c} exact p={p_val:.2e}")
    print(f"系統 CM: TP={cm_sys['TP']} FP={cm_sys['FP']} FN={cm_sys['FN']} TN={cm_sys['TN']}")
    print(f"基線 CM: TP={cm_fair['TP']} FP={cm_fair['FP']} FN={cm_fair['FN']} TN={cm_fair['TN']}")
    print(f"已寫入 {OUT}")


if __name__ == "__main__":
    main()
