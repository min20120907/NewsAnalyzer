# -*- coding: utf-8 -*-
"""
eval_full_corpus.py — 全量 2,292 筆 Cofacts 語料庫評測
=====================================================
包含兩大評測維度：
1. Task 1: 全庫抗擾動檢索評測 (Full-Corpus Retrieval Robustness, N=2,292)
   - 測試已建立於知識庫中的闢謠條目，在面對民眾轉傳引發之 4 級擾動時的命中率與標籤正確率。
2. Task 2: 全庫 5-Fold 交叉驗證評測 (5-Fold Stratified Cross-Validation, N=2,292)
   - 嚴格 held-out：每折 458 筆作為測試查詢，完全自檢索庫排除。
   - 評估面對未收錄全新假訊息時的保守拒答率與近鄰泛化能力。
"""

import os, sys, json, time, random, re, sqlite3
import numpy as np

# Use RTX GPU
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
import torch
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DB = os.path.join(BASE_DIR, "data", "cofacts", "cofacts_cache.db")
SBERT_PATH = ("/home/min20120907/.cache/huggingface/hub/"
              "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/"
              "snapshots/e8f8c211226b894fcb81acc59f3b34ba3efd5f42")

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

def compute_metrics(y_true_list, sim_matrix, cand_labels, thresholds, exact_keys=None, cand_keys=None):
    """
    y_true_list: list of 'FAKE'/'REAL'
    sim_matrix: [N_test, N_cand]
    cand_labels: list of 'FAKE'/'REAL' of candidates
    thresholds: list of float
    exact_keys: optional [N_test]
    cand_keys: optional [N_cand]
    """
    N = len(y_true_list)
    results = {}
    
    for th in thresholds:
        tp = fp = fn = tn = abstain = 0
        exact_hit = 0
        decided = 0
        
        for i in range(N):
            y_t = y_true_list[i]
            sims = sim_matrix[i]
            best_idx = np.argmax(sims)
            best_sim = float(sims[best_idx])
            
            if best_sim < th:
                abstain += 1
                continue
                
            decided += 1
            pred = cand_labels[best_idx]
            
            if exact_keys is not None and cand_keys is not None:
                if exact_keys[i] == cand_keys[best_idx]:
                    exact_hit += 1
            
            if pred == "FAKE" and y_t == "FAKE":
                tp += 1
            elif pred == "FAKE" and y_t == "REAL":
                fp += 1
            elif pred == "REAL" and y_t == "FAKE":
                fn += 1
            elif pred == "REAL" and y_t == "REAL":
                tn += 1
                
        cov = decided / N
        acc = (tp + tn) / decided if decided > 0 else 0.0
        p_fake = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r_fake = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1_fake = 2 * p_fake * r_fake / (p_fake + r_fake) if (p_fake + r_fake) > 0 else 0.0
        exact_acc = exact_hit / decided if (decided > 0 and exact_keys is not None) else 0.0
        
        results[th] = {
            "cov": cov,
            "acc": acc,
            "p_fake": p_fake,
            "r_fake": r_fake,
            "f1_fake": f1_fake,
            "exact_recall": exact_acc,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "abstain": abstain,
            "decided": decided
        }
    return results

def main():
    random.seed(42)
    np.random.seed(42)
    
    print("=== 全量 2,292 筆 Cofacts 語料庫評測啟動 ===")
    
    con = sqlite3.connect(CACHE_DB)
    rows = con.execute(
        "SELECT key, text, status FROM corpus "
        "WHERE status IN ('inaccurate','partial','accurate') "
        "AND length(text) > 40 ORDER BY key ASC"
    ).fetchall()
    con.close()
    
    N = len(rows)
    print(f"總計有效條目: {N}")
    keys = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    statuses = [r[2] for r in rows]
    labels = [to_binary(s) for s in statuses]
    
    fake_cnt = sum(1 for l in labels if l == "FAKE")
    real_cnt = N - fake_cnt
    print(f"類別分佈: FAKE = {fake_cnt} ({fake_cnt/N*100:.1f}%), REAL = {real_cnt} ({real_cnt/N*100:.1f}%)")
    
    print(f"載入 SentenceTransformer 模型 ({SBERT_PATH})...")
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(SBERT_PATH, device=device)
    
    # 預編碼基準語料庫向量
    print("編碼全庫文本 (N=2,292)...")
    t0 = time.time()
    corpus_emb = model.encode([t[:300] for t in texts], batch_size=256, normalize_embeddings=True, show_progress_bar=False)
    print(f"編碼完成，耗時 {time.time()-t0:.2f}s，維度 {corpus_emb.shape}")
    
    perturb_fns = [
        ("verbatim", perturb_verbatim),
        ("mild",     perturb_mild),
        ("medium",   perturb_medium),
        ("heavy",    perturb_heavy),
    ]
    
    # 預編碼所有擾動查詢
    probes_dict = {}
    probe_emb_dict = {}
    for pname, pfn in perturb_fns:
        t0 = time.time()
        p_texts = [pfn(t)[:300] for t in texts]
        probes_dict[pname] = p_texts
        p_emb = model.encode(p_texts, batch_size=256, normalize_embeddings=True, show_progress_bar=False)
        probe_emb_dict[pname] = p_emb
        print(f"擾動 [{pname:>8}] 編碼完成 ({time.time()-t0:.2f}s)")
        
    print("\n" + "="*80)
    print("【TASK 1: 全庫抗擾動檢索評測 (Full-Corpus Retrieval Robustness, N=2,292)】")
    print("="*80)
    
    task1_summary = {}
    for pname, _ in perturb_fns:
        p_emb = probe_emb_dict[pname]
        # sim matrix: [2292, 2292]
        sim_mat = p_emb @ corpus_emb.T
        res = compute_metrics(labels, sim_mat, labels, THRESHOLDS, exact_keys=keys, cand_keys=keys)
        task1_summary[pname] = res
        
        print(f"\n--- 擾動等級: {pname} ---")
        print(f"{'θ_sim':>7} | {'Cov':>6} {'Acc':>6} {'ExactRec':>9} {'P(Fake)':>8} {'R(Fake)':>8} {'F1':>6} | {'TP':>5} {'FP':>4} {'FN':>4} {'TN':>4} {'Abst':>5}")
        print("-" * 80)
        for th in THRESHOLDS:
            m = res[th]
            print(f"{th:7.2f} | {m['cov']*100:5.1f}% {m['acc']*100:5.1f}% {m['exact_recall']*100:8.1f}% {m['p_fake']*100:7.1f}% {m['r_fake']*100:7.1f}% {m['f1_fake']:6.3f} | {m['tp']:5d} {m['fp']:4d} {m['fn']:4d} {m['tn']:4d} {m['abstain']:5d}")
            
    print("\n" + "="*80)
    print("【TASK 2: 全庫 5-Fold 交叉驗證評測 (5-Fold Stratified CV, N=2,292, Held-Out)】")
    print("="*80)
    
    # 建立 5-Fold Stratified Split
    indices = np.arange(N)
    fake_indices = [i for i, l in enumerate(labels) if l == "FAKE"]
    real_indices = [i for i, l in enumerate(labels) if l == "REAL"]
    random.shuffle(fake_indices)
    random.shuffle(real_indices)
    
    K = 5
    folds = [[] for _ in range(K)]
    for i, idx in enumerate(fake_indices):
        folds[i % K].append(idx)
    for i, idx in enumerate(real_indices):
        folds[i % K].append(idx)
        
    task2_summary = {pname: {th: {"cov": [], "acc": [], "p_fake": [], "r_fake": [], "f1_fake": []} for th in THRESHOLDS} for pname, _ in perturb_fns}
    
    for k in range(K):
        test_idx = np.array(folds[k])
        train_idx = np.array([idx for fold_i in range(K) if fold_i != k for idx in folds[fold_i]])
        
        train_emb_fold = corpus_emb[train_idx]
        train_labels_fold = [labels[i] for i in train_idx]
        test_labels_fold = [labels[i] for i in test_idx]
        
        for pname, _ in perturb_fns:
            p_emb_fold = probe_emb_dict[pname][test_idx]
            sim_mat_fold = p_emb_fold @ train_emb_fold.T
            fold_res = compute_metrics(test_labels_fold, sim_mat_fold, train_labels_fold, THRESHOLDS)
            
            for th in THRESHOLDS:
                for metric in ["cov", "acc", "p_fake", "r_fake", "f1_fake"]:
                    task2_summary[pname][th][metric].append(fold_res[th][metric])
                    
    print("\n5-Fold 平均評測結果 (Out-of-Distribution Held-Out):")
    for pname, _ in perturb_fns:
        print(f"\n--- 5-Fold Held-Out 平均: {pname} ---")
        print(f"{'θ_sim':>7} | {'Cov':>7} {'Acc':>7} {'P(Fake)':>8} {'R(Fake)':>8} {'F1':>7}")
        print("-" * 55)
        for th in THRESHOLDS:
            m = task2_summary[pname][th]
            cov_avg = np.mean(m["cov"])
            acc_avg = np.mean(m["acc"])
            p_avg = np.mean(m["p_fake"])
            r_avg = np.mean(m["r_fake"])
            f1_avg = np.mean(m["f1_fake"])
            print(f"{th:7.2f} | {cov_avg*100:6.1f}% {acc_avg*100:6.1f}% {p_avg*100:7.1f}% {r_avg*100:7.1f}% {f1_avg:7.3f}")
            
    # Save results to json for paper integration
    out_file = os.path.join(BASE_DIR, "data", "eval_full_2292_results.json")
    save_data = {
        "N": N,
        "task1_retrieval_robustness": task1_summary,
        "task2_5fold_cross_validation": {
            pname: {
                th: {
                    metric: float(np.mean(task2_summary[pname][th][metric]))
                    for metric in ["cov", "acc", "p_fake", "r_fake", "f1_fake"]
                }
                for th in THRESHOLDS
            }
            for pname, _ in perturb_fns
        }
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    print(f"\n評測完成！數據已儲存至: {out_file}")

if __name__ == "__main__":
    main()
