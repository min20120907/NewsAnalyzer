# -*- coding: utf-8 -*-
"""Exp5 component ablation（純離線）：同一 500 筆，重算 7 種分項組合的 verdict。

原料：data/eval/metrics_500.jsonl。
變體（kept 分項）：
  full / evidence-only（fact_check+user_feedback）/ metadata-only
  （sentiment+domain+similarity+timeliness）/ −domain / −sentiment /
  −timeliness / −clamp（Stage-3 全關，其餘走 full）。
重算鏈（= 生產線原樣）：rule' = Σkept分/Σkept權重×100 → fusion
  （有 fact_check：fc_hit?0.10:0.60；無 fact_check 變體一律 0.60 無證據 regime；
  deep_cs 缺失則不融合）→ Stage-3（τhigh=25＋軟50＋partial55；−clamp 跳過）
  → final<55 → FAKE。
一致性自檢：full 重算 == 採集 final_score（容差 1e-6），否則整組作廢。
輸出：data/eval/component_ablation.json；印 Table 4 草稿（含 Δacc vs full）。

用法：原料採集完成後 .venv/bin/python scripts/component_ablation.py
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_JSONL = os.path.join(BASE, "data", "eval", "metrics_500.jsonl")
CUTOFF = int(os.environ.get("CUTOFF", "60"))  # 二值化：final < CUTOFF → FAKE（REAL = 大致可信 ≥60）
OUT_JSON = os.path.join(BASE, "data", "eval", f"component_ablation_c{CUTOFF}.json")
EVIDENCE = ("fact_check", "user_feedback")
METADATA = ("sentiment", "domain", "similarity", "timeliness")
VARIANTS = {
    "full": ("sentiment", "domain", "fact_check", "user_feedback",
             "similarity", "timeliness"),
    "evidence-only": EVIDENCE,
    "metadata-only": METADATA,
    "minus-domain": ("sentiment", "fact_check", "user_feedback",
                     "similarity", "timeliness"),
    "minus-sentiment": ("domain", "fact_check", "user_feedback",
                        "similarity", "timeliness"),
    "minus-timeliness": ("sentiment", "domain", "fact_check", "user_feedback",
                         "similarity"),
    "minus-clamp": ("sentiment", "domain", "fact_check", "user_feedback",
                    "similarity", "timeliness"),
}
FC_HIT_STATUS = ("hit", "ok", "inaccurate", "partial")


def stage3(post, sources, tau=25.0):
    final = post
    for s in (sources or []):
        st = s.get("status")
        try:
            sim = float(s.get("sim") or 0.0)
        except (TypeError, ValueError):
            sim = 0.0
        if st in ("inaccurate", "false", "misleading", "fake"):
            if sim >= 0.85:
                final = min(final, tau)
                break
            elif sim >= 0.72:
                final = min(final, 50.0)
                break
        elif st == "partial":
            final = min(final, 55.0)
    return final


def verdict_of(rec, kept, use_clamp=True):
    mets = rec["metrics"]
    num = sum(float(mets[c]["score"]) for c in kept)
    den = sum(float(mets[c]["weight"]) for c in kept)
    rule = num / den * 100.0
    cs = rec.get("deep_cs")
    if cs is not None:
        if "fact_check" in kept:
            fc_hit = any(s.get("status") in FC_HIT_STATUS
                         for s in (rec.get("sources") or []))
            w = 0.10 if fc_hit else 0.60
        else:
            w = 0.60  # 無證據 regime：LLM 主導
        post = rule * (1 - w) + float(cs) * w
    else:
        post = rule
    final = stage3(post, rec.get("sources")) if use_clamp else post
    return "FAKE" if final < CUTOFF else "REAL"


def metrics_of(pairs):
    tp = sum(1 for t, p in pairs if t == "FAKE" and p == "FAKE")
    fp = sum(1 for t, p in pairs if t == "REAL" and p == "FAKE")
    fn = sum(1 for t, p in pairs if t == "FAKE" and p == "REAL")
    tn = sum(1 for t, p in pairs if t == "REAL" and p == "REAL")
    n = len(pairs)
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    return {"n": n, "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "acc": round((tp + tn) / n, 4),
            "precision_fake": round(prec, 4), "recall_fake": round(rec, 4),
            "f1_fake": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0}


def main():
    recs = [json.loads(l) for l in open(IN_JSONL, encoding="utf-8")]
    valid = [r for r in recs if not r.get("error")]
    print(f"採集 {len(recs)} 筆，有效 {len(valid)} 筆")
    # 一致性自檢：full 重算 == 生產線 final_score
    bad = 0
    for r in valid:
        kept = VARIANTS["full"]
        mets = r["metrics"]
        rule = sum(float(mets[c]["score"]) for c in kept) / \
            sum(float(mets[c]["weight"]) for c in kept) * 100.0
        if abs(rule - float(r["rule_score"])) > 1e-6:
            bad += 1
            if bad <= 3:
                print(f"  ! rowid={r['rowid']} rule重算={rule} 生產線={r['rule_score']}")
    assert bad == 0, f"rule 一致性自檢失敗：{bad} 筆不符"
    print("一致性自檢通過：rule 離線重算 == 生產線 rule_score（全筆）")

    out = {"cutoff": CUTOFF, "n_valid": len(valid), "variants": {}}
    for name, kept in VARIANTS.items():
        pairs = [(r["true"], verdict_of(r, kept, use_clamp=(name != "minus-clamp")))
                 for r in valid]
        out["variants"][name] = metrics_of(pairs)
    acc_full = out["variants"]["full"]["acc"]
    print(f"\n{'variant':<15} {'Acc':>6} {'Δacc':>7} {'P':>6} {'R':>6} "
          f"{'F1':>6} | {'TP':>4} {'FP':>3} {'FN':>3} {'TN':>3}")
    for name in VARIANTS:
        m = out["variants"][name]
        print(f"{name:<15} {m['acc']:6.3f} {m['acc']-acc_full:+7.3f} "
              f"{m['precision_fake']:6.3f} {m['recall_fake']:6.3f} {m['f1_fake']:6.3f} | "
              f"{m['TP']:4d} {m['FP']:3d} {m['FN']:3d} {m['TN']:3d}")
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"已寫入 {OUT_JSON}")


if __name__ == "__main__":
    main()
