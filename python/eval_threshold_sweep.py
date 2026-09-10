# -*- coding: utf-8 -*-
"""
eval_threshold_sweep.py — θ_sim 閾值 × 擾動強度 掃描 (純 SBERT，不需 LLM)
=========================================================================
held-out 做法: test items 從 corpus 尾部取出，檢索時排除 test item 自身
（模擬真實場景: 用戶送來的文章不在 corpus 裡）。

三種擾動等級 + 一個「原文 verbatim」基準。

用法:
  cd NewsAnalyzer && source .venv/bin/activate && python3 python/eval_threshold_sweep.py
"""
import os, sys, json, time, random, re
import sqlite3
import numpy as np

CACHE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "cofacts", "cofacts_cache.db")
SBERT_PATH = ("/home/min20120907/.cache/huggingface/hub/"
              "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/"
              "snapshots/e8f8c211226b894fcb81acc59f3b34ba3efd5f42")

HOLDOUT = 200
THRESHOLDS = [0.55, 0.60, 0.65, 0.70, 0.72, 0.75, 0.80, 0.85]

SYNONYM_MAP = {
    "政府": "官方", "表示": "指出", "認為": "覺得", "指出": "聲稱",
    "發現": "查出", "報導": "報道", "研究": "調查", "專家": "學者",
    "民眾": "群眾", "警告": "提醒", "造成": "導致", "影響": "衝擊",
    "疫苗": "針劑", "確認": "證實", "公布": "公告", "宣布": "宣告",
    "呼籲": "呼喊", "透過": "藉由", "顯示": "呈現", "危險": "危害",
    "嚴重": "嚴峻", "健康": "身體", "社會": "社群", "網路": "網絡",
    "聲稱": "宣稱", "調查": "查證", "問題": "議題", "可能": "或許",
    "已經": "已然", "目前": "當前", "國家": "國內", "記者": "媒體人",
}


def perturb_verbatim(txt):
    return (txt or "").strip()[:300]

def perturb_mild(txt):
    txt = (txt or "").strip()
    body = txt[:max(10, int(len(txt) * 0.85))]
    return "網傳：" + body

def _synonym_replace(txt, rate=0.3):
    for old, new in SYNONYM_MAP.items():
        if old in txt and random.random() < rate:
            txt = txt.replace(old, new, 1)
    return txt

def perturb_medium(txt):
    txt = (txt or "").strip()
    body = txt[:max(10, int(len(txt) * 0.60))]
    body = _synonym_replace(body, rate=0.4)
    return "有人說：" + body

def perturb_heavy(txt):
    txt = (txt or "").strip()
    body = txt[:max(10, int(len(txt) * 0.40))]
    body = _synonym_replace(body, rate=0.7)
    sents = re.split(r'[。！？；\n]+', body)
    sents = [s.strip() for s in sents if len(s.strip()) > 5]
    if len(sents) > 2:
        random.shuffle(sents)
    body = "。".join(sents)
    return "據傳：" + body

def to_binary(status):
    return "FAKE" if status in ("inaccurate", "partial") else "REAL"


def main():
    random.seed(42)

    # 1. Load corpus
    con = sqlite3.connect(CACHE_DB)
    rows = con.execute(
        "SELECT key, text, status FROM corpus "
        "WHERE status IN ('inaccurate','partial','accurate') "
        "AND length(text) > 40"
    ).fetchall()
    con.close()

    N = len(rows)
    print(f"Corpus total: {N}")

    # Split: train = first N-HOLDOUT, test = last HOLDOUT
    train_end = N - HOLDOUT
    train_keys = [r[0] for r in rows[:train_end]]
    train_texts = [r[1] for r in rows[:train_end]]
    train_statuses = [r[2] for r in rows[:train_end]]

    test_texts = [r[1] for r in rows[train_end:]]
    test_statuses = [r[2] for r in rows[train_end:]]

    print(f"Train (retrieval corpus): {len(train_texts)}")
    print(f"Test (held-out queries):  {len(test_texts)}")
    fake_n = sum(1 for s in test_statuses if to_binary(s) == "FAKE")
    print(f"  Test FAKE={fake_n}  REAL={len(test_texts)-fake_n}")

    # 2. Load SBERT & encode train corpus
    print("Loading SBERT model...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(SBERT_PATH, device="cpu")

    print("Encoding train corpus (batch)...")
    t0 = time.time()
    train_emb = model.encode(
        [t[:300] for t in train_texts],
        convert_to_numpy=True, normalize_embeddings=True,
        batch_size=128, show_progress_bar=True
    )
    print(f"  Train corpus encoded in {time.time()-t0:.1f}s  shape={train_emb.shape}")

    # 3. Sweep
    perturb_fns = [
        ("verbatim", perturb_verbatim),
        ("mild",     perturb_mild),
        ("medium",   perturb_medium),
        ("heavy",    perturb_heavy),
    ]

    all_results = {}
    for pname, pfn in perturb_fns:
        print(f"\n===== 擾動等級: {pname} =====")

        probes = [pfn(t)[:300] for t in test_texts]
        t0 = time.time()
        probe_emb = model.encode(
            probes, convert_to_numpy=True, normalize_embeddings=True,
            batch_size=128
        )
        print(f"  Probes encoded in {time.time()-t0:.1f}s")

        # sim matrix: [N_test x N_train] — test items excluded from corpus
        sim_matrix = probe_emb @ train_emb.T

        print(f"{'θ_sim':>8} {'cov':>7} {'acc':>7} {'P(F)':>7} {'R(F)':>7} "
              f"{'F1':>7} {'TP':>5} {'FP':>5} {'FN':>5} {'TN':>5} {'abst':>6}")
        print("-" * 80)

        results = []
        for th in THRESHOLDS:
            tp = fp = fn = tn = abstain = 0
            for i in range(len(test_texts)):
                y_true = to_binary(test_statuses[i])
                sims = sim_matrix[i]
                best_idx = np.argmax(sims)
                best_sim = float(sims[best_idx])

                if best_sim < th:
                    abstain += 1
                    continue

                best_status = train_statuses[best_idx]
                y_pred = to_binary(best_status)
                if y_true == "FAKE" and y_pred == "FAKE":
                    tp += 1
                elif y_true == "REAL" and y_pred == "FAKE":
                    fp += 1
                elif y_true == "FAKE" and y_pred == "REAL":
                    fn += 1
                else:
                    tn += 1

            total = len(test_texts)
            decided = tp + fp + fn + tn
            acc = (tp + tn) / decided if decided else 0
            prec = tp / (tp + fp) if (tp + fp) else 0
            rec = tp / (tp + fn) if (tp + fn) else 0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
            cov = decided / total if total else 0

            r = {"threshold": th, "total": total, "decided": decided,
                 "abstain": abstain, "coverage": cov, "accuracy": acc,
                 "precision_fake": prec, "recall_fake": rec, "f1_fake": f1,
                 "tp": tp, "fp": fp, "fn": fn, "tn": tn}
            results.append(r)
            print(f"{th:>8.2f} {r['coverage']:>7.3f} {r['accuracy']:>7.3f} "
                  f"{r['precision_fake']:>7.3f} {r['recall_fake']:>7.3f} "
                  f"{r['f1_fake']:>7.3f} {r['tp']:>5} {r['fp']:>5} {r['fn']:>5} "
                  f"{r['tn']:>5} {r['abstain']:>6}")
        all_results[pname] = results

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "threshold_sweep_results.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(all_results, fh, indent=2, ensure_ascii=False)
    print(f"\n結果已存: {out}")


if __name__ == "__main__":
    main()
