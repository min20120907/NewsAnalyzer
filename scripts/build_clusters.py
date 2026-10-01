# -*- coding: utf-8 -*-
"""實驗 1+3 rumor clusters：SBERT 全庫編碼 → cosine ≥ τ 連通分支（union-find）。

與 retrieval 評測同模型、同截斷（text[:300]），cluster 定義：
  同一 rumor family = 相似度 ≥ CLUSTER_SIM 的連通分支。
輸出 data/eval/rumor_clusters.json：每 cluster 成員 record_id 一覽 +
  統計（cluster 數、最大/最小、singleton 數、size 分布）。
cluster-level 5-fold：整 cluster 分配（stratified by 多數標籤，seed 固定），
  寫回同一 JSON（folds 段），供 retrieval record/cluster 對比用。

用法: .venv/bin/python scripts/build_clusters.py [--sim 0.80]（GPU，約數分鐘）
"""
import argparse
import json
import os
import random
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "python"))
from eval_full_corpus import SBERT_PATH  # 同 retrieval 評測模型，單一來源

FROZEN = os.path.join(BASE, "data", "eval", "dataset_frozen.json")
OUT = os.path.join(BASE, "data", "eval", "rumor_clusters.json")
SEED = 42


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", type=float, default=0.80)
    ap.add_argument("--device", type=str, default="cpu",
                    help="cuda:0 會與 FastMTP 搶 22GB 顯存；背景採集中一律用 cpu")
    args = ap.parse_args()

    frozen = json.load(open(FROZEN, encoding="utf-8"))
    recs = frozen["records"]
    texts = []
    con = __import__("sqlite3").connect(
        os.path.join(BASE, "data", "cofacts", "cofacts_cache.db"))
    key2text = {r[0]: r[1] for r in con.execute(
        "SELECT key, text FROM corpus").fetchall()}
    con.close()
    texts = [key2text[r["record_id"]] for r in recs]
    n = len(recs)
    print(f"載入 {n} 筆；SBERT={SBERT_PATH}；τ_cluster={args.sim}")

    import torch
    from sentence_transformers import SentenceTransformer
    device = args.device
    if device.startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"
    model = SentenceTransformer(SBERT_PATH, device=device)
    t0 = time.time()
    emb = model.encode([t[:300] for t in texts], batch_size=256,
                       normalize_embeddings=True, show_progress_bar=False)
    print(f"編碼完成 {time.time()-t0:.1f}s device={device}")
    emb_t = torch.tensor(emb, device=device)

    uf = UnionFind(n)
    CHUNK = 512
    npairs = 0
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, n, CHUNK):
            sim = emb_t[i:i + CHUNK] @ emb_t.T  # [chunk, n]
            hit = (sim >= args.sim).cpu()
            for a in range(hit.shape[0]):
                row = hit[a].nonzero(as_tuple=True)[0].tolist()
                for b_ in row:
                    if b_ > i + a:  # 上三角去重；排除自環
                        uf.union(i + a, b_)
                        npairs += 1
    print(f"pairwise 完成 {time.time()-t0:.1f}s，sim≥{args.sim} 邊數={npairs}")

    groups = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    clusters = []
    for cid, (root, members) in enumerate(sorted(groups.items())):
        labs = [recs[m]["label"] for m in members]
        maj = max(set(labs), key=labs.count)
        clusters.append({"cluster_id": cid, "size": len(members),
                         "majority_label": maj,
                         "members": [recs[m]["record_id"] for m in members]})
    clusters.sort(key=lambda c: -c["size"])
    sizes = [c["size"] for c in clusters]
    singletons = sum(1 for s in sizes if s == 1)

    # cluster-level 5-fold：整 cluster 分配（多數標籤分層，seed 固定）
    rng = random.Random(SEED)
    by_lab = {}
    for c in clusters:
        by_lab.setdefault(c["majority_label"], []).append(c["cluster_id"])
    fold_of = {}
    for lab, cids in by_lab.items():
        cids = cids[:]
        rng.shuffle(cids)
        for j, cid in enumerate(cids):
            fold_of[cid] = j % 5
    for c in clusters:
        c["fold_cluster"] = fold_of[c["cluster_id"]]

    out = {"seed": SEED, "sim_threshold": args.sim, "n_records": n,
           "n_clusters": len(clusters),
           "stats": {"max_size": max(sizes), "min_size": min(sizes),
                     "n_singletons": singletons,
                     "size_hist": {str(s): sizes.count(s)
                                   for s in sorted(set(sizes))[:20]}},
           "clusters": clusters}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"clusters={len(clusters)} max={max(sizes)} min={min(sizes)} "
          f"singletons={singletons}")
    print(f"已寫入 {OUT}")


if __name__ == "__main__":
    main()
