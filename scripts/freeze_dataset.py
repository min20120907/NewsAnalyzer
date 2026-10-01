# -*- coding: utf-8 -*-
"""實驗 1 凍結資料集 (Corpus freeze)：2,292 筆 + 論文標籤映射，seed 固定。

label mapping（論文用名）：
  inaccurate / partial → MISLEADING；accurate → CREDIBLE。
每筆保存：record_id、來源 URL、label、原始 status、建立日期、文字長度。
附 record-level stratified 5-fold 指派（seed=42，可重現）。
cluster-level folds 由 scripts/build_clusters.py 另行產生。

用法: .venv/bin/python scripts/freeze_dataset.py
輸出: data/eval/dataset_frozen.json
"""
import json
import os
import random
import sqlite3
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "cofacts", "cofacts_cache.db")
OUT = os.path.join(BASE, "data", "eval", "dataset_frozen.json")

SEED = 42
FREEZE_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
LABEL_MAP = {"inaccurate": "MISLEADING", "partial": "MISLEADING",
             "accurate": "CREDIBLE"}


def main():
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT key, text, status, feedback_count, created_at, article_id "
        "FROM corpus WHERE status IN ('inaccurate','partial','accurate') "
        "AND length(text) > 40 ORDER BY key ASC").fetchall()
    con.close()
    assert len(rows) == 2292, f"凍結失敗：{len(rows)} ≠ 2292"

    recs = []
    for key, text, status, fb, ts, aid in rows:
        recs.append({
            "record_id": key,
            "url": f"https://cofacts.tw/article/{aid}",
            "label": LABEL_MAP[status],
            "status_orig": status,
            "created_date": (datetime.fromtimestamp(ts, tz=timezone.utc)
                             .strftime("%Y-%m-%d") if ts else None),
            "text_len": len(text),
            "feedback_count": fb,
            "freeze_date": FREEZE_DATE,
        })

    # record-level stratified 5-fold（seed 固定）
    rng = random.Random(SEED)
    by_label = {}
    for i, r in enumerate(recs):
        by_label.setdefault(r["label"], []).append(i)
    folds = [[] for _ in range(5)]
    for lab, idxs in by_label.items():
        idxs = idxs[:]
        rng.shuffle(idxs)
        for j, i in enumerate(idxs):
            folds[j % 5].append(i)
    for f, idxs in enumerate(folds):
        for i in idxs:
            recs[i]["fold_record"] = f

    out = {"seed": SEED, "freeze_date": FREEZE_DATE, "n": len(recs),
           "label_map": LABEL_MAP, "records": recs}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    dist = {}
    for r in recs:
        dist[r["label"]] = dist.get(r["label"], 0) + 1
    print(f"凍結 {len(recs)} 筆（seed={SEED}）：{dist}")
    print(f"fold sizes: {[len(f) for f in folds]}")
    print(f"已寫入 {OUT}")


if __name__ == "__main__":
    main()
