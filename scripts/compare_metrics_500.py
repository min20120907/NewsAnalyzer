"""配對比較：舊查詢基線 vs 新查詢基線（同一 500 筆、同一 server）。

用法：
  cd ~/Documents/Web_and_App_Development/NewsAnalyzer
  .venv/bin/python scripts/compare_metrics_500.py
"""
import json, os, statistics as st
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = os.path.join(BASE, "data", "eval", "metrics_500.PREFIX-20261002.jsonl")
NEW = os.path.join(BASE, "data", "eval", "metrics_500.jsonl")
COMPS = ("sentiment", "domain", "fact_check", "user_feedback", "similarity", "timeliness")


def load(p):
    out = {}
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("rowid") is not None:
                    out[r["rowid"]] = r
            except Exception:
                pass
    return out


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def main():
    old, new = load(OLD), load(NEW)
    common = sorted(set(old) & set(new))
    print(f"舊 {len(old)} 筆 / 新 {len(new)} 筆 / 可配對 {len(common)} 筆")
    if not common:
        print("尚無可配對資料"); return

    # 1) 整體分數
    print("\n=== 分數 ===")
    print(f"{'':6} {'n':>4} {'REAL':>7} {'FAKE':>7} {'全體':>7}")
    for tag, d in (("舊", old), ("新", new)):
        real = [d[r]["final_score"] for r in common
                if d[r]["true"] == "REAL" and d[r].get("final_score") is not None]
        fake = [d[r]["final_score"] for r in common
                if d[r]["true"] == "FAKE" and d[r].get("final_score") is not None]
        allf = [d[r]["final_score"] for r in common if d[r].get("final_score") is not None]
        print(f"{tag:6} {len(allf):>4} {mean(real):>7.2f} {mean(fake):>7.2f} {mean(allf):>7.2f}")

    # 2) 分界 50 的準確率（題目核心：真新聞有沒有被冤枉）
    print("\n=== 50 分界 ===")
    for tag, d in (("舊", old), ("新", new)):
        tp = fp = tn = fn = 0
        for r in common:
            fs, t = d[r].get("final_score"), d[r]["true"]
            if fs is None:
                continue
            pred_fake = fs < 50
            true_fake = t == "FAKE"
            tp += pred_fake and true_fake
            fp += pred_fake and not true_fake
            tn += (not pred_fake) and (not true_fake)
            fn += (not pred_fake) and true_fake
        n = tp + fp + tn + fn
        print(f"{tag:6} TP={tp} FP={fp} TN={tn} FN={fn}  "
              f"acc={(tp+tn)/n:.4f} FPR={fp/(fp+tn) if fp+tn else float('nan'):.4f} "
              f"FNR={fn/(tp+fn) if tp+fn else float('nan'):.4f}")

    # 3) 逐筆變化
    deltas = [(new[r]["final_score"] - old[r]["final_score"])
              for r in common
              if new[r].get("final_score") is not None and old[r].get("final_score") is not None]
    if deltas:
        print(f"\n=== 逐筆變化 (n={len(deltas)}) ===")
        print(f"  平均 {mean(deltas):+.2f}  中位數 {st.median(deltas):+.2f}  "
              f"變好 {sum(1 for d in deltas if d > 0)} / 變差 {sum(1 for d in deltas if d < 0)} / "
              f"持平 {sum(1 for d in deltas if d == 0)}")

    # 4) 規則分 vs deep 分：確認改動只動到 deep 那一側
    print("\n=== rule_score（檢索無關的定錨，應該幾乎不變）===")
    for tag, d in (("舊", old), ("新", new)):
        rs = [d[r]["rule_score"] for r in common if d[r].get("rule_score") is not None]
        print(f"{tag:6} mean={mean(rs):.2f}  變動筆數={sum(1 for r in common if old[r].get('rule_score') != new[r].get('rule_score'))}")

    # 5) 各分項
    print("\n=== metrics 分項平均 score ===")
    print(f"{'':6} " + " ".join(f"{c[:9]:>9}" for c in COMPS))
    for tag, d in (("舊", old), ("新", new)):
        row = []
        for c in COMPS:
            xs = [(d[r].get("metrics", {}).get(c) or {}).get("score")
                  for r in common if d[r].get("metrics", {}).get(c)]
            xs = [x for x in xs if isinstance(x, (int, float))]
            row.append(mean(xs))
        print(f"{tag:6} " + " ".join(f"{v:>9.2f}" for v in row))

    # 6) abstain
    print("\n=== abstain ===")
    for tag, d in (("舊", old), ("新", new)):
        # 舊基線（20261002 前）沒有 abstain 欄位，讀不到就是 0，不是 None。
        # None 混進 mean() 會讓整欄變 NaN —— 所以只收 bool 為真的。
        ab = [r for r in common if d[r].get("abstain") is True]
        cs = [x.get("deep_cs") for x in ab if x.get("deep_cs") is not None]
        extra = f"  deep_cs mean={mean(cs):.2f}" if cs else "  （無）"
        print(f"{tag:6} abstain={len(ab)}/{len(common)}{extra}")


if __name__ == "__main__":
    main()