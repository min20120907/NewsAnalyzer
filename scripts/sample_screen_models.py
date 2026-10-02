"""50 筆抽樣篩選：候選模型在同一批文章上比 deep_cs 準確度與分離度。

比單一案例有意義（eval_models_real.py 的兩篇只能看趨勢，不能算統計）。
指標：
  MAE   平均絕對誤差（越小越好；本來就有 clamp 到 0-100）
  SEP   真/假平均分差（越大越好，模型分得開真假）
  50d   50 分界的 accuracy / FPR / FNR（FPR 是關鍵：真新聞被冤枉的比例）

50 筆是篩選用的量，不是定案用的量。分數接近時要擴到 500 才可信。

用法：cd NewsAnalyzer && .venv/bin/python scripts/sample_screen_models.py
"""
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = int(os.environ.get("SCREEN_N", "50"))
OUT = os.path.join(BASE, "data", "eval", f"screen_{N}.json")
EVAL_JSON = os.path.join(BASE, "data", "eval", "model_eval.json")

FAKE_MAX = 50


def passing_models():
    """讀 eval_models_real.py 的結果取可用清單；沒有結果就只留 local。

    不重新實測 —— 那是 eval_models_real.py 的事，兩邊各跑一次會浪費額度。
    """
    ok = {"local/qwen3.8-27b-fastmtp"}     # 生產預設，:8088 本機不需雲端額度
    try:
        for r in json.load(open(EVAL_JSON, encoding="utf-8")):
            if r.get("usable"):
                ok.add(r["model"])
    except Exception:
        pass
    return ok


def main():
    import requests
    from llm_registry import model_catalog

    allow = passing_models()
    # 只篩「實測評測通過」的：能活著回話 ≠ 能在評分 prompt 產出 JSON
    models = [m["id"] for m in model_catalog() if m["id"] in allow]
    if not models:
        print("沒有通過 eval_models_real 的模型，先跑 python/eval_models_real.py")
        return
    print(f"篩選模型 {len(models)} 個 × {N} 筆")
    for m in models:
        print(f"  {m}")

    fair = [json.loads(l) for l in
            open(os.path.join(BASE, "data", "eval", "fair_baseline_500.jsonl"),
                 encoding="utf-8")][:N]
    con = sqlite3.connect(os.path.join(BASE, "data", "cofacts", "cofacts_cache.db"))
    ids = [r["rowid"] for r in fair]
    txt = {r: t for r, t in con.execute(
        f"SELECT rowid, text FROM corpus WHERE rowid IN ({','.join('?' * len(ids))})", ids)}
    con.close()

    results = {m: [] for m in models}

    def one(args):
        mid, case = args
        truth = "FAKE" if case["true"] in ("inaccurate", "partial", "FAKE") else "REAL"
        body = "網傳：" + (txt.get(case["rowid"], "") or "")[: int(len(txt.get(case["rowid"], "")) * 0.85)]
        t0 = time.perf_counter()
        try:
            r = requests.post("http://127.0.0.1:5000/judge",
                              json={"content": body, "llm_model": mid}, timeout=120).json()
            da = r.get("deep_analysis") or {}
            return (mid, case["rowid"], truth, da.get("credibility_score"),
                    bool(da.get("abstain")), round(time.perf_counter() - t0, 1))
        except Exception as e:
            return (mid, case["rowid"], truth, None, False,
                    round(time.perf_counter() - t0, 1))

    jobs = [(m, c) for c in fair for m in models]
    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for mid, rid, truth, cs, ab, lat in ex.map(one, jobs):
            results[mid].append({"rowid": rid, "true": truth, "cs": cs,
                                 "abstain": ab, "lat_s": lat})
            done += 1
            if done % 50 == 0:
                print(f"  [{done}/{len(jobs)}]", flush=True)

    print(f"\n{'模型':44} {'n':>3} {'MAE':>6} {'SEP':>5} {'acc':>6} {'FPR':>6} {'秒':>6}")
    print("-" * 90)
    rank = []
    for mid, rows in results.items():
        ok = [r for r in rows if r["cs"] is not None]
        if not ok:
            print(f"{mid:44} {0:>3}  完全沒產出分數")
            continue
        real = [r["cs"] for r in ok if r["true"] == "REAL"]
        fake = [r["cs"] for r in ok if r["true"] == "FAKE"]
        mae = sum(abs(c - (100 if r["true"] == "REAL" else 0)) for r in ok) / len(ok)
        sep = (sum(real) / len(real) - sum(fake) / len(fake)) if real and fake else 0
        tp = sum(1 for r in ok if r["cs"] < FAKE_MAX and r["true"] == "FAKE")
        fp = sum(1 for r in ok if r["cs"] < FAKE_MAX and r["true"] == "REAL")
        tn = sum(1 for r in ok if r["cs"] >= FAKE_MAX and r["true"] == "REAL")
        fn = sum(1 for r in ok if r["cs"] >= FAKE_MAX and r["true"] == "FAKE")
        n = len(ok)
        fpr = fp / (fp + tn) if fp + tn else 0
        acc = (tp + tn) / n
        meanlat = sum(r["lat_s"] for r in rows) / len(rows)
        print(f"{mid:44} {n:>3} {mae:>6.1f} {sep:>5.1f} {acc:>6.3f} {fpr:>6.3f} {meanlat:>6.1f}")
        rank.append((mid, mae, sep, acc, fpr))

    if rank:
        best = min(rank, key=lambda x: x[1])
        print(f"\nMAE 最小: {best[0]}  (MAE={best[1]:.1f} SEP={best[2]:.1f} acc={best[3]:.3f} FPR={best[4]:.3f})")
    json.dump(results, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()