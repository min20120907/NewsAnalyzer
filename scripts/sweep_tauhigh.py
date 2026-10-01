# -*- coding: utf-8 -*-
"""τhigh 離線掃描：對 clamp_ablation_500.jsonl 逐筆重算 Stage-3 Clamp，掃描上限取值。

重算邏輯 = 生產線 fake_news_server_new.py Stage 3 原樣（硬上限 τhigh 可調；
中度相關軟上限 50.0、partial 上限 55.0 保持固定；缺 sim 視為 0）。
判定：final < CUTOFF(55) → FAKE，否則 REAL（與 fair_baseline 一致）。
輸出：data/eval/tauhigh_sweep.json（各 τ 的 CM + 指標 + 觸發數）。
另做一致性自檢：τ=25 重算值必須 == 採集的 final_score（容差 1e-6）。

用法: .venv/bin/python scripts/sweep_tauhigh.py
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_JSONL = os.path.join(BASE, "data", "eval", "clamp_ablation_500.jsonl")
TAUS = [None, 10, 15, 20, 25, 30, 35, 40, 45, 50]  # None = No Clamp
CUTOFF = int(os.environ.get("CUTOFF", "60"))  # 二值化：final < CUTOFF → FAKE（REAL = 大致可信 ≥60）
OUT_JSON = os.path.join(BASE, "data", "eval", f"tauhigh_sweep_c{CUTOFF}.json")
SEED = 42  # dev/test 分層切分種子（與 corpus 凍結一致）


def apply_clamp(post, sources, tau):
    final = post
    hit = None
    for s in (sources or []):
        st = s.get("status")
        try:
            sim = float(s.get("sim") or 0.0)
        except (TypeError, ValueError):
            sim = 0.0
        if st in ("inaccurate", "false", "misleading", "fake"):
            if sim >= 0.85:
                if tau is not None and final > tau:
                    hit = "hard"
                    final = min(final, float(tau))
                elif tau is None:
                    pass
                break
            elif sim >= 0.72:
                if final > 50.0:
                    if hit is None:
                        hit = "soft"
                    final = min(final, 50.0)
                break
        elif st == "partial":
            if final > 55.0:
                if hit is None:
                    hit = "partial"
                final = min(final, 55.0)
    return final, hit


def metrics_of(pairs):
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


def sweep(rs):
    d = {}
    # off = 整個 Stage-3 全關（final = post），真正的消融對照
    pairs = [(r["true"], "FAKE" if float(r["post_fusion_score"]) < CUTOFF else "REAL")
             for r in rs]
    m = metrics_of(pairs)
    m["n_clamped"] = 0
    m["L"] = 2 * m["FN"] + m["FP"]
    d["off"] = m
    for tau in TAUS:
        pairs, hits = [], 0
        for r in rs:
            f, hit = apply_clamp(r["post_fusion_score"], r["sources"], tau)
            if hit:
                hits += 1
            pairs.append((r["true"], "FAKE" if f < CUTOFF else "REAL"))
        m = metrics_of(pairs)
        m["n_clamped"] = hits
        m["L"] = 2 * m["FN"] + m["FP"]  # 漏判 FAKE 代價加權
        d["none" if tau is None else str(tau)] = m
    return d


def show(tag, sw):
    print(f"\n[{tag}]")
    print(f"{'τhigh':>6} | {'Acc':>6} {'P':>6} {'R':>6} {'F1':>6} | "
          f"{'TP':>4} {'FP':>3} {'FN':>3} {'TN':>3} | {'L':>4} 觸發")
    for k in ["off"] + ["none" if tau is None else str(tau) for tau in TAUS]:
        m = sw[k]
        print(f"{k:>6} | {m['acc']:6.3f} {m['precision_fake']:6.3f} "
              f"{m['recall_fake']:6.3f} {m['f1_fake']:6.3f} | "
              f"{m['TP']:4d} {m['FP']:3d} {m['FN']:3d} {m['TN']:3d} | "
              f"{m['L']:4d} {m['n_clamped']:4d}")


def main():
    import random
    recs = [json.loads(l) for l in open(IN_JSONL, encoding="utf-8")]
    valid = [r for r in recs
             if not r.get("error") and r.get("post_fusion_score") is not None]
    print(f"採集 {len(recs)} 筆，有效 {len(valid)} 筆")
    # 一致性自檢：τ=25 重算 == 生產線 final_score
    bad = 0
    for r in valid:
        f25, _ = apply_clamp(r["post_fusion_score"], r["sources"], 25)
        if abs(f25 - float(r["final_score"])) > 1e-6:
            bad += 1
            if bad <= 3:
                print(f"  ! rowid={r['rowid']} 重算={f25} 生產線={r['final_score']}")
    assert bad == 0, f"一致性自檢失敗：{bad} 筆不符"
    print("一致性自檢通過：τ=25 離線重算 == 生產線 final_score（全筆）")

    # 分層 dev/test（FAKE/REAL 各半切，seed=42）
    rng = random.Random(SEED)
    fake = [r for r in valid if r["true"] == "FAKE"]
    real = [r for r in valid if r["true"] == "REAL"]
    rng.shuffle(fake)
    rng.shuffle(real)
    dev = fake[:len(fake) // 2] + real[:len(real) // 2]
    test = fake[len(fake) // 2:] + real[len(real) // 2:]
    ndf = sum(1 for r in dev if r["true"] == "FAKE")
    ntf = sum(1 for r in test if r["true"] == "FAKE")
    print(f"dev={len(dev)}（FAKE {ndf}）, test={len(test)}（FAKE {ntf}）")

    dev_sw, test_sw = sweep(dev), sweep(test)
    show("dev", dev_sw)
    show("test", test_sw)

    # dev 上以 L=2·FN+FP 選 τ*（平手取較大 τ = 干預最弱）
    cands = [(t, dev_sw[t]["L"]) for t in dev_sw if t not in ("none", "off")]
    tau_star = min(cands, key=lambda x: (x[1], -float(x[0])))[0]
    m = test_sw[tau_star]
    print(f"\nτ*={tau_star}（dev L 最小）→ test: acc={m['acc']} "
          f"P={m['precision_fake']} R={m['recall_fake']} F1={m['f1_fake']} "
          f"TP={m['TP']} FP={m['FP']} FN={m['FN']} TN={m['TN']}")

    out = {"cutoff": CUTOFF, "seed": SEED, "n_total": len(recs),
           "n_valid": len(valid), "n_dev": len(dev), "n_test": len(test),
           "tau_star": tau_star, "dev": dev_sw, "test": test_sw}
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"已寫入 {OUT_JSON}")


if __name__ == "__main__":
    main()
