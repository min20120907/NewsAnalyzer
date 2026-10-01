# -*- coding: utf-8 -*-
"""實驗 2+3 Retrieval：record-level vs cluster-level 5-fold held-out 對比。

同一 SBERT、同一閾值組 {0.55..0.85}、同一 top-1、同一 4 種擾動、同一標籤映射；
唯一差別：fold 指派（record 隨機 vs 整 rumor-cluster 分配）。
每折：test queries 自索引排除 → top-1 cosine ≥ th 才決策。
指標：Coverage、SelectiveAcc、CAA(=Cov×Sel)、F1(MISLEADING)、
  FPR、FNR、Abstention(=1−Cov)。註：FMR ≡ 1−SelectiveAcc，故以 FPR/FNR 代之。
預設 CPU（GPU 留給背景採集的 FastMTP）。

用法: .venv/bin/python scripts/retrieval_record_vs_cluster.py
輸出: data/eval/retrieval_record_vs_cluster.json；θ=0.72 印 Table 2 草稿
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "python"))
from eval_full_corpus import (SBERT_PATH, THRESHOLDS, perturb_verbatim,
                              perturb_mild, perturb_medium, perturb_heavy)

FROZEN = os.path.join(BASE, "data", "eval", "dataset_frozen.json")
CLUSTERS = os.path.join(BASE, "data", "eval", "rumor_clusters.json")
OUT = os.path.join(BASE, "data", "eval", "retrieval_record_vs_cluster.json")

PERTURBS = [("verbatim", perturb_verbatim), ("mild", perturb_mild),
            ("medium", perturb_medium), ("heavy", perturb_heavy)]


def fold_metrics(y_true, sim_mat, cand_labels, th):
    tp = fp = fn = tn = abst = 0
    n = len(y_true)
    for i in range(n):
        s = sim_mat[i]
        b = int(s.argmax())
        if float(s[b]) < th:
            abst += 1
            continue
        pred, yt = cand_labels[b], y_true[i]
        if pred == "FAKE" and yt == "FAKE":
            tp += 1
        elif pred == "FAKE":
            fp += 1
        elif yt == "FAKE":
            fn += 1
        else:
            tn += 1
    dec = tp + fp + fn + tn
    cov = dec / n
    sel = (tp + tn) / dec if dec else 0.0
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"cov": cov, "sel": sel, "caa": cov * sel,
            "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "fpr": fp / (fp + tn) if fp + tn else 0.0,
            "fnr": fn / (fn + tp) if fn + tp else 0.0,
            "abst": abst / n, "n_test": n}


def run_split(name, fold_of_idx, labels, corpus_emb, probe_embs):
    res = {}
    for pname, _ in PERTURBS:
        res[pname] = {th: [] for th in THRESHOLDS}
    import numpy as np
    for k in range(5):
        test = np.array([i for i in range(len(labels)) if fold_of_idx[i] == k])
        train = np.array([i for i in range(len(labels)) if fold_of_idx[i] != k])
        yt = [labels[i] for i in test]
        cl = [labels[i] for i in train]
        cemb = corpus_emb[train]
        for pname, _ in PERTURBS:
            pemb = probe_embs[pname][test]
            sim = pemb @ cemb.T
            for th in THRESHOLDS:
                res[pname][th].append(fold_metrics(yt, sim, cl, th))
    return res


def main():
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    frozen = json.load(open(FROZEN, encoding="utf-8"))
    recs = frozen["records"]
    labels = ["FAKE" if r["label"] == "MISLEADING" else "REAL" for r in recs]
    fold_record = [r["fold_record"] for r in recs]

    cl = json.load(open(CLUSTERS, encoding="utf-8"))
    rid2cfold = {}
    for c in cl["clusters"]:
        for m in c["members"]:
            rid2cfold[m] = c["fold_cluster"]
    fold_cluster = [rid2cfold[r["record_id"]] for r in recs]

    con = __import__("sqlite3").connect(
        os.path.join(BASE, "data", "cofacts", "cofacts_cache.db"))
    key2text = {r[0]: r[1] for r in con.execute("SELECT key, text FROM corpus")}
    con.close()
    texts = [key2text[r["record_id"]] for r in recs]

    t0 = time.time()
    model = SentenceTransformer(SBERT_PATH, device="cpu")
    corpus_emb = model.encode([t[:300] for t in texts], batch_size=256,
                              normalize_embeddings=True, show_progress_bar=False)
    probe_embs = {}
    for pname, pfn in PERTURBS:
        probe_embs[pname] = model.encode(
            [pfn(t)[:300] for t in texts], batch_size=256,
            normalize_embeddings=True, show_progress_bar=False)
    print(f"編碼完成 {time.time()-t0:.0f}s（corpus + 4 擾動，cpu）")

    out = {"seed": 42, "thresholds": THRESHOLDS, "splits": {}}
    for name, folds in (("record", fold_record), ("cluster", fold_cluster)):
        t0 = time.time()
        res = run_split(name, folds, labels, corpus_emb, probe_embs)
        agg = {}
        for pname in res:
            agg[pname] = {}
            for th in THRESHOLDS:
                fr = res[pname][th]
                agg[pname][str(th)] = {
                    m: round(float(np.mean([f[m] for f in fr])), 4)
                    for m in ("cov", "sel", "caa", "f1", "fpr", "fnr", "abst")}
        out["splits"][name] = agg
        print(f"{name} split 完成 {time.time()-t0:.0f}s")

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"已寫入 {OUT}\n\nTable 2 草稿（θ=0.72，5-fold 平均）：")
    print(f"{'split':<8} {'perturb':<8} {'Cov':>6} {'SelAcc':>7} {'CAA':>6} {'F1':>6} {'FPR':>6} {'FNR':>6}")
    for name in ("record", "cluster"):
        for pname, _ in PERTURBS:
            m = out["splits"][name][pname]["0.72"]
            print(f"{name:<8} {pname:<8} {m['cov']*100:5.1f}% {m['sel']*100:6.1f}% "
                  f"{m['caa']*100:5.1f}% {m['f1']:6.3f} {m['fpr']:6.3f} {m['fnr']:6.3f}")


if __name__ == "__main__":
    main()
