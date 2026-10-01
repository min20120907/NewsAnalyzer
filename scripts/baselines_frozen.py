# -*- coding: utf-8 -*-
"""TF-IDF / Domain / Majority 基線重算（凍結語料 2,292、seed 42、5-fold）。

協定（先寫死再看結果）：
- 語料：data/eval/dataset_frozen.json（MISLEADING 2,025 / CREDIBLE 267；fold_record 5-fold）
- 文本：cofacts_cache.db corpus.text（key = record_id）
- 標籤空間統一為 FAKE/REAL（MISLEADING→FAKE、CREDIBLE→REAL）
- Majority：全判 FAKE。
- TF-IDF：jieba 斷詞 unigram（token_pattern=None, lowercase=False, min_df=2,
  sublinear_tf=True）+ LogisticRegression(max_iter=2000, random_state=42)。
  主評：record-level 5-fold；穩健性另報 cluster-level 5-fold（整簇分配，
  消除近重複洩漏；簇→折確定性貪婪平衡）。
- Domain：取 claim 內文「第一個 URL」的主機，套生產線 domain 規則
  （factcheck/白名單=25、UGC/黑名單=0、其他=15；http 再 -10，下限 0；×4 → 0-100），
  協定二值化（>=60 → REAL）。變體：
    A（主）：無 URL → abstain（回報 coverage 與 selective 指標）
    C（嚴）：trusted tier（factcheck/白名單）才 REAL；其餘（含無 URL）→ FAKE。
- 輸出：data/eval/baselines_frozen.json
用法：cd ~/Documents/Web_and_App_Development/NewsAnalyzer && .venv/bin/python scripts/baselines_frozen.py
"""
import json
import os
import re
import sqlite3

import jieba

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(BASE, "data", "eval")
FROZEN = os.path.join(D, "dataset_frozen.json")
CLUSTERS = os.path.join(D, "rumor_clusters.json")
DB = os.path.join(BASE, "data", "cofacts", "cofacts_cache.db")
OUT = os.path.join(D, "baselines_frozen.json")

CUTOFF = 60  # 統一協定：>=60 → REAL


def ybin(label):
    return "FAKE" if label == "MISLEADING" else "REAL"


def load_list(path):
    try:
        return {l.strip().lower() for l in open(path, encoding="utf-8")
                if l.strip() and not l.startswith("#")}
    except FileNotFoundError:
        return set()


WL = load_list(os.path.join(BASE, "data", "domains", "whitelist.txt"))
FC = load_list(os.path.join(BASE, "data", "domains", "factcheck.txt"))
UGC = (load_list(os.path.join(BASE, "data", "domains", "ugc.txt"))
       | load_list(os.path.join(BASE, "data", "domains", "ugc.remote.txt")))
BL = (load_list(os.path.join(BASE, "data", "domains", "blocklist.local.txt"))
      | load_list(os.path.join(BASE, "data", "domains", "blocklist.remote.txt")))

URL_RE = re.compile(r"https?://[^\s\u3000<>\"')\]]+")


def registrable(host):
    h = host.split(":")[0].lower().lstrip(".")
    if h.startswith("www."):
        h = h[4:]
    parts = h.split(".")
    if len(parts) >= 3 and parts[-2] in ("com", "org", "net", "edu", "gov") and len(parts[-3]) <= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else h


def cm_metrics(pairs):
    tp = sum(1 for t, p in pairs if t == "FAKE" and p == "FAKE")
    fp = sum(1 for t, p in pairs if t == "REAL" and p == "FAKE")
    fn = sum(1 for t, p in pairs if t == "FAKE" and p == "REAL")
    tn = sum(1 for t, p in pairs if t == "REAL" and p == "REAL")
    n = len(pairs)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    rec_r = tn / (tn + fp) if tn + fp else 0.0
    return {"n": n, "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "acc": round((tp + tn) / n, 4) if n else 0.0,
            "precision_fake": round(prec, 4), "recall_fake": round(rec, 4),
            "f1_fake": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "recall_credible": round(rec_r, 4)}


def domain_tier(main, host):
    if main in FC or host in FC:
        return "factcheck", 25.0
    if main in WL or host in WL:
        return "mainstream", 25.0
    if main in UGC or host in UGC:
        return "ugc", 0.0
    if main in BL or host in BL:
        return "blacklist", 0.0
    return "unknown", 15.0


def main():
    frozen = json.load(open(FROZEN, encoding="utf-8"))
    recs = frozen["records"]
    clusters = json.load(open(CLUSTERS, encoding="utf-8"))["clusters"]

    con = sqlite3.connect(DB)
    keys = [r["record_id"] for r in recs]
    texts = dict(con.execute(
        f"SELECT key, text FROM corpus WHERE key IN ({','.join('?' * len(keys))})", keys))
    con.close()
    assert len(texts) == len(recs), f"texts {len(texts)} != recs {len(recs)}"

    out = {"n": len(recs), "cutoff": CUTOFF, "seed": frozen["seed"], "variants": {}}

    # ---------- Majority ----------
    m = cm_metrics([(ybin(r["label"]), "FAKE") for r in recs])
    out["variants"]["majority"] = m
    print("majority:", m)

    # ---------- Domain ----------
    tier_rows = []
    for r in recs:
        t = texts[r["record_id"]]
        found = URL_RE.findall(t)
        if not found:
            tier_rows.append((r, None, None, None, None))
            continue
        url = found[0]
        host = re.sub(r"^https?://", "", url).split("/")[0].lower()
        scheme = "https" if url[:5].lower() == "https" else "http"
        tier, pts = domain_tier(registrable(host), host)
        if scheme == "http":
            pts = max(0.0, pts - 10.0)
        norm100 = pts / 25.0 * 100.0
        tier_rows.append((r, host, scheme + ":" + tier, norm100,
                          "REAL" if norm100 >= CUTOFF else "FAKE"))

    resolved = [(ybin(r["label"]), pred) for (r, host, tier, s, pred) in tier_rows if pred]
    a = cm_metrics(resolved)
    a["coverage"] = round(len(resolved) / len(recs), 4)
    a["n_abstain"] = len(recs) - len(resolved)
    out["variants"]["domain_A_selective"] = a
    print("domain A:", a)

    pairs_c = []
    for (r, host, tier, s, pred) in tier_rows:
        if pred is None:
            pairs_c.append((ybin(r["label"]), "FAKE"))
        else:
            pairs_c.append((ybin(r["label"]),
                            "REAL" if "factcheck" in tier or "mainstream" in tier else "FAKE"))
    c = cm_metrics(pairs_c)
    out["variants"]["domain_C_strict"] = c
    print("domain C:", c)

    brk = {}
    dom_pred, dom_tier = {}, {}
    for (r, host, tier, s, pred) in tier_rows:
        dom_pred[r["record_id"]] = pred
        dom_tier[r["record_id"]] = tier
        k = tier or "no_url"
        d = brk.setdefault(k, {"n": 0, "fake": 0, "pred_real_A": 0, "pred_real_C": 0})
        d["n"] += 1
        d["fake"] += 1 if ybin(r["label"]) == "FAKE" else 0
        d["pred_real_A"] += 1 if pred == "REAL" else 0
        d["pred_real_C"] += 1 if (pred is not None and ("factcheck" in tier or "mainstream" in tier)) else 0
    for k, d in brk.items():
        d["pct_fake"] = round(d["fake"] / d["n"], 4)
    out["domain_tiers"] = brk
    print("tiers:", json.dumps(brk, ensure_ascii=False))

    # ---------- TF-IDF ----------
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    X = [texts[r["record_id"]] for r in recs]
    y = [ybin(r["label"]) for r in recs]
    rec_by_id = {r["record_id"]: r for r in recs}

    cl_list = sorted(clusters, key=lambda c: (-c["size"], c["cluster_id"]))
    base_ratio = sum(1 for v in y if v == "FAKE") / len(y)
    cfold = {}
    stats = [{"n": 0, "fake": 0} for _ in range(5)]
    for cl in cl_list:
        best, best_score = 0, None
        for f in range(5):
            n = stats[f]["n"] + cl["size"]
            fake = stats[f]["fake"] + sum(1 for rid in cl["members"] if ybin(rec_by_id[rid]["label"]) == "FAKE")
            ratio = fake / n if n else base_ratio
            score = (n / (len(recs) / 5)) * 0.5 + abs(ratio - base_ratio) * 3.0
            if best_score is None or score < best_score:
                best, best_score = f, score
        for rid in cl["members"]:
            cfold[rid] = best
        stats[best]["n"] += cl["size"]
        stats[best]["fake"] += sum(1 for rid in cl["members"] if ybin(rec_by_id[rid]["label"]) == "FAKE")
    out["cluster_folds"] = {"sizes": [s["n"] for s in stats],
                            "fake_ratio": [round(s["fake"] / s["n"], 4) for s in stats]}
    print("cluster folds:", out["cluster_folds"])

    def run_cv(fold_of):
        pairs, per_fold, predmap = [], [], {}
        for f in range(5):
            tr = [i for i, r in enumerate(recs) if fold_of(r) != f]
            te = [i for i, r in enumerate(recs) if fold_of(r) == f]
            vec = TfidfVectorizer(tokenizer=lambda s: list(jieba.cut(s)),
                                  token_pattern=None, lowercase=False, min_df=2,
                                  sublinear_tf=True)
            Xtr = vec.fit_transform([X[i] for i in tr])
            Xte = vec.transform([X[i] for i in te])
            clf = LogisticRegression(max_iter=2000, random_state=42)
            clf.fit(Xtr, [y[i] for i in tr])
            pred = clf.predict(Xte)
            for j, i in enumerate(te):
                predmap[recs[i]["record_id"]] = pred[j]
            mp = cm_metrics(list(zip([y[i] for i in te], pred)))
            per_fold.append(mp["acc"])
            pairs.extend(zip([y[i] for i in te], pred))
        agg = cm_metrics(pairs)
        agg["per_fold_acc"] = [round(v, 4) for v in per_fold]
        return agg, predmap

    t1, t1_predmap = run_cv(lambda r: r["fold_record"])
    out["variants"]["tfidf_record5fold"] = t1
    print("tfidf record:", t1)

    t2, _ = run_cv(lambda r: cfold[r["record_id"]])
    out["variants"]["tfidf_cluster5fold"] = t2
    print("tfidf cluster:", t2)

    # ---------- 500 樣本口徑（與 paired / zero-shot 同批；cutoff 60） ----------
    fair = [json.loads(l) for l in open(os.path.join(D, "fair_baseline_500.jsonl"),
                                        encoding="utf-8")]
    con = sqlite3.connect(DB)
    rid2key = dict(con.execute("SELECT rowid, key FROM corpus"))
    extra_texts = {r: t for r, t in con.execute(
        f"SELECT rowid, text FROM corpus WHERE rowid IN ({','.join('?' * len(fair))})",
        [s["rowid"] for s in fair])}
    con.close()

    # 全量訓練模型（僅供 32 筆「非凍結集」樣本；它們不在 2292 內，屬天然 held-out）
    vec_all = TfidfVectorizer(tokenizer=lambda s: list(jieba.cut(s)), token_pattern=None,
                              lowercase=False, min_df=2, sublinear_tf=True)
    Xall = vec_all.fit_transform(X)
    clf_all = LogisticRegression(max_iter=2000, random_state=42)
    clf_all.fit(Xall, y)

    def eval500(subset):
        pm, pda, pdc, ptf = [], [], [], []
        extra_feats, extra_pos = [], []
        for s in subset:
            t = s["true"]
            pm.append((t, "FAKE"))
            key = rid2key.get(s["rowid"])
            if key in dom_pred:
                pred, tier = dom_pred[key], dom_tier[key]
            else:
                txt = extra_texts.get(s["rowid"], "") or ""
                found = URL_RE.findall(txt)
                pred, tier = None, None
                if found:
                    url = found[0]
                    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
                    scheme = "https" if url[:5].lower() == "https" else "http"
                    tier, pts = domain_tier(registrable(host), host)
                    if scheme == "http":
                        pts = max(0.0, pts - 10.0)
                    pred = "REAL" if pts / 25.0 * 100.0 >= CUTOFF else "FAKE"
            if pred is None:
                pdc.append((t, "FAKE"))
            else:
                pda.append((t, pred))
                pdc.append((t, "REAL" if (tier and ("factcheck" in tier or "mainstream" in tier))
                            else "FAKE"))
            if key in t1_predmap:
                ptf.append((t, t1_predmap[key]))
            else:
                ptf.append((t, None))
                extra_feats.append(extra_texts.get(s["rowid"], "") or "")
                extra_pos.append(len(ptf) - 1)
        if extra_feats:
            ex = clf_all.predict(vec_all.transform(extra_feats))
            for k, pos in enumerate(extra_pos):
                ptf[pos] = (ptf[pos][0], ex[k])
        return {
            "n": len(subset),
            "majority": cm_metrics(pm),
            "domain_A_selective": {**cm_metrics(pda),
                                   "coverage": round(len(pda) / len(subset), 4),
                                   "n_abstain": len(subset) - len(pda)},
            "domain_C_strict": cm_metrics(pdc),
            "tfidf_record5fold": cm_metrics(ptf),
        }

    out["on_500"] = eval500(fair)
    out["on_498_common"] = eval500([s for s in fair if s.get("score") is not None])
    print("on_500:", json.dumps(out["on_500"], ensure_ascii=False))
    print("on_498_common:", json.dumps(out["on_498_common"], ensure_ascii=False))

    out["params"] = {
        "tfidf": "jieba unigram, min_df=2, sublinear_tf=True",
        "clf": "LogisticRegression(max_iter=2000, random_state=42)",
        "domain_rules": "production (factcheck/wl=25, ugc/bl=0, unknown=15; http -10; norm*4/100)",
        "cutoff": CUTOFF,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("written:", OUT)


if __name__ == "__main__":
    main()
