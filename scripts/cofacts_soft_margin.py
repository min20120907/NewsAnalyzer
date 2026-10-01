"""量 open-world 形狀的 Cofacts 相似度分離度。

query = 真實新聞報導（tw_media_sweep.jsonl 的標題，74 則台灣主流媒體）
pool  = Cofacts 查核庫（本地 corpus+cache 的真實回覆內文）
正樣本 = 人工確認主題相同的命中；負樣本 = 同池其餘全部。

這是門檻真正要用的形狀——線上 /judge 餵的就是「新聞報導」而非「查核原文」。
同域形狀（query==查核原文）恆等 ≈1.0，量不出東西。

跑：.venv/bin/python scripts/cofacts_soft_margin.py
"""
import json, os, sys, sqlite3
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "python"))
from cofacts_local import _get_sbert, CACHE_DB

SWEEP = os.path.join(ROOT, "data/eval/tw_media_sweep.jsonl")


def load_pool(con):
    pool = []
    seen = set()
    for table, col in (("corpus", "text"), ("cache", "matched_text")):
        for aid, txt, reasons in con.execute(
                f"SELECT article_id, {col}, reasons FROM {table} "
                f"WHERE article_id IS NOT NULL"):
            if not aid or aid in seen or not (txt or "").strip():
                continue
            rs = []
            try:
                rs = json.loads(reasons) if reasons else []
            except Exception:
                rs = []
            body = max((r.get("text") or "" for r in rs), key=len) if rs else ""
            t = (body if len(body.strip()) >= 15 else txt)[:200]
            if not t.strip():
                continue
            seen.add(aid)
            pool.append((aid, t))
    return pool


def main():
    con = sqlite3.connect(CACHE_DB)
    pool = load_pool(con)
    con.close()
    queries = [json.loads(l)["title"] for l in open(SWEEP, encoding="utf-8")
               if l.strip() and not json.loads(l).get("error")]
    # 去重
    queries = list(dict.fromkeys(queries))
    print(f"query（真實新聞報導）{len(queries)} 則；pool（Cofacts 查核）{len(pool)} 筆")

    m = _get_sbert()
    qv = m.encode(queries, normalize_embeddings=True, convert_to_numpy=True)
    pv = m.encode([t for _, t in pool], normalize_embeddings=True,
                  convert_to_numpy=True)
    sims = qv @ pv.T                       # (nq, npool)
    best = sims.max(axis=1)
    best_idx = sims.argmax(axis=1)

    print("\n=== 每則新聞的最相似 Cofacts 分數 ===")
    for s in np.percentile(best, [0, 10, 25, 50, 75, 90, 100]):
        print(f"  p{s:5.0f} = {s:.3f}")
    print(f"\n  ≥0.72（現行硬門檻）: {(best>=0.72).sum()} 則")
    print(f"  0.45–0.72（軟命中帶）: {((best>=0.45)&(best<0.72)).sum()} 則")
    print(f"  <0.45（not_found）  : {(best<0.45).sum()} 則")

    print("\n--- 0.45–0.72 軟命中帶（門檻要決定的地方）---")
    band = np.where((best >= 0.45) & (best < 0.72))[0]
    for i in band:
        print(f"  sim={best[i]:.3f}  新聞: {queries[i][:46]}")
        print(f"          查核: {pool[best_idx[i]][1][:66]}")

    print("\n--- ≥0.72 硬命中（檢查是否真相關）---")
    hard = np.where(best >= 0.72)[0]
    for i in hard:
        print(f"  sim={best[i]:.3f}  新聞: {queries[i][:46]}")
        print(f"          查核: {pool[best_idx[i]][1][:66]}")

    # 池內分離度：同一新聞對「最佳命中」與「次佳命中」的落差
    print("\n=== 池內落差（最佳 vs 池內第 5 佳的中位數）===")
    k = min(5, sims.shape[1])
    top5 = np.sort(sims, axis=1)[:, -k:]
    gap = top5[:, -1] - np.median(top5[:, :-1], axis=1)
    print(f"  落差中位 {np.median(gap):.3f}；落差 <0.05 的新聞（命中不顯眼）: "
          f"{(gap < 0.05).sum()} 則")


if __name__ == "__main__":
    main()