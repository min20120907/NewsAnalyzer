# -*- coding: utf-8 -*-
"""實驗 3 Cofacts 資料集審計 (Data Audit)：用 Pandas 重現論文 2,292 筆的篩選流程並輸出品質報告。

篩選邏輯（與 python/eval_full_corpus.py 完全一致）：
  WHERE status IN ('inaccurate','partial','accurate') AND length(text) > 40
標籤來源：status 由 Cofacts 回覆類型規則產生（python/cofacts_local.py
  _classify_candidate：RUMOR/FALSE→inaccurate；NOT_RUMOR/TRUE→accurate；
  OPINIONATED→partial），非人工隨意標註。
稽核點：每筆 article_id 可回鏈 https://cofacts.tw/article/{id} 原文頁；
  feedback_count 為群眾認同訊號（分布一併輸出）。

用法: cd NewsAnalyzer && .venv/bin/python scripts/audit_cofacts.py
輸出: data/eval/cofacts_audit.json（Appendix / 補充 repo 用）
"""
import json
import os
import sqlite3

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "cofacts", "cofacts_cache.db")
OUT_JSON = os.path.join(BASE, "data", "eval", "cofacts_audit.json")

MIN_LEN = 40
VALID_STATUS = ("inaccurate", "partial", "accurate")


def main():
    con = sqlite3.connect(DB)
    df = pd.read_sql_query(
        "SELECT key, text, status, feedback_count, created_at, article_id "
        "FROM corpus", con)
    con.close()
    n_raw = len(df)

    # --- 論文篩選流程（1:1 重現） ---
    df = df[df["status"].isin(VALID_STATUS)]
    n_status = len(df)
    df = df[df["text"].str.len() > MIN_LEN].copy()
    n_final = len(df)
    assert n_final == 2292, f"審計失敗：篩後 {n_final} 筆 ≠ 論文 2,292 筆"

    df["label"] = df["status"].map(
        {"inaccurate": "FAKE", "partial": "FAKE", "accurate": "REAL"})
    df["url"] = "https://cofacts.tw/article/" + df["article_id"].astype(str)

    report = {
        "n_raw_corpus": int(n_raw),
        "n_after_status_filter": int(n_status),
        "n_final_len_gt_40": int(n_final),
        "class_dist": df["label"].value_counts().to_dict(),
        "status_dist": df["status"].value_counts().to_dict(),
        "text_len": {"min": int(df["text"].str.len().min()),
                     "median": float(df["text"].str.len().median()),
                     "mean": round(float(df["text"].str.len().mean()), 1)},
        "feedback_count": {"min": int(df["feedback_count"].min()),
                           "median": float(df["feedback_count"].median()),
                           "mean": round(float(df["feedback_count"].mean()), 1),
                           "zero_n": int((df["feedback_count"] == 0).sum())},
        "provenance_url_coverage": round(float(df["article_id"].notna().mean()), 4),
        "label_rule": ("RUMOR/FALSE->inaccurate(FAKE); NOT_RUMOR/TRUE->accurate(REAL); "
                       "OPINIONATED->partial(FAKE); see python/cofacts_local.py::_classify_candidate"),
    }
    json.dump(report, open(OUT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"審計通過：篩後 {n_final} 筆 == 論文 2,292 筆；報告已寫入 {OUT_JSON}")


if __name__ == "__main__":
    main()
