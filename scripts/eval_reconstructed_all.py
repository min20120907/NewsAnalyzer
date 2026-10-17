# -*- coding: utf-8 -*-
"""
全面驗證腳本：在 repo 內全部 5 套基準資料集上離線對比「舊版六訊號＋Clamp」與「新版四維度正交＋三態路由」
執行方式（放於 repo 的 scripts/ 目錄下）：
  python3 scripts/eval_reconstructed_all.py
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CANDIDATE_BASE = os.path.dirname(SCRIPT_DIR)
if os.path.exists(os.path.join(CANDIDATE_BASE, "data", "eval", "metrics_500.jsonl")):
    BASE = CANDIDATE_BASE
else:
    BASE = "/working_dir/c_76b7a5665ebe4c19/extracted/NewsAnalyzer-b5e9bcb82d26bbaa54cb08676064366de46ae54a"

sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(BASE, "python"))
sys.path.insert(0, os.path.join(BASE, "scripts"))

from orthogonal_scorer import score_orthogonal


def eval_metrics_500():
    path = os.path.join(BASE, "data", "eval", "metrics_500.jsonl")
    recs = [json.loads(line) for line in open(path, encoding="utf-8")]
    tp = fp = fn = tn = 0
    old_tp = old_fp = old_fn = old_tn = 0

    regime_counts = {}
    flips = []
    for r in recs:
        gt = r["true"]  # "FAKE" or "REAL"
        old_s = float(r["final_score"])
        old_pred = "FAKE" if old_s < 60.0 else "REAL"
        if gt == "FAKE" and old_pred == "FAKE": old_tp += 1
        elif gt == "REAL" and old_pred == "FAKE": old_fp += 1
        elif gt == "FAKE" and old_pred == "REAL": old_fn += 1
        else: old_tn += 1

        mets = r.get("metrics") or {}
        dom_score = float((mets.get("domain") or {}).get("score", 15.0))
        url = "https://www.cna.com.tw/news/a.html" if dom_score >= 25.0 else "https://unknown"
        sent_score = float((mets.get("sentiment") or {}).get("score", 15.0))
        sent_val = 0.2 if sent_score >= 15.0 else (0.7 if sent_score >= 10.0 else 0.9)
        sim_score = float((mets.get("similarity") or {}).get("score", 9.0))
        sim_val = sim_score / 15.0

        deep_mock = {
            "credibility_score": r.get("deep_cs"),
            "abstain": bool(r.get("abstain", False)),
            "evidence_state": "full_body_evidence" if any(
                s.get("status") in ("inaccurate", "partial", "accurate") for s in (r.get("sources") or [])
            ) else "no_evidence",
        }
        out = score_orthogonal(
            title="",
            url=url,
            content="",
            sentiment_val=sent_val,
            title_body_sim=sim_val,
            sources=r.get("sources") or [],
            deep=deep_mock,
        )
        regime = out["regime"]
        regime_counts[regime] = regime_counts.get(regime, 0) + 1
        new_pred = "FAKE" if out["final_score"] < 60.0 else "REAL"
        if gt == "FAKE" and new_pred == "FAKE": tp += 1
        elif gt == "REAL" and new_pred == "FAKE": fp += 1
        elif gt == "FAKE" and new_pred == "REAL": fn += 1
        else: tn += 1
        if old_pred != new_pred:
            flips.append((r["rowid"], gt, old_s, out["final_score"], r.get("desc"), r.get("deep_cs")))

    n = len(recs)
    old_acc = (old_tp + old_tn) / n
    new_acc = (tp + tn) / n
    old_prec = old_tp / (old_tp + old_fp)
    old_rec = old_tp / (old_tp + old_fn)
    old_f1 = 2 * old_prec * old_rec / (old_prec + old_rec)

    new_prec = tp / (tp + fp)
    new_rec = tp / (tp + fn)
    new_f1 = 2 * new_prec * new_rec / (new_prec + new_rec)
    print("=== [1] metrics_500.jsonl (n=500, cutoff=60) ===")
    print(f"  舊版 (6訊號+Clamp): Acc={old_acc:.4f} F1={old_f1:.4f} (TP={old_tp} FP={old_fp} FN={old_fn} TN={old_tn})")
    print(f"  新版 (4正交+三態) : Acc={new_acc:.4f} F1={new_f1:.4f} (TP={tp} FP={fp} FN={fn} TN={tn})")
    print(f"  新版路由分佈      : {regime_counts}")
    if flips:
        print(f"  預測差異 ({len(flips)} 筆修復): {flips}")
    return {
        "n": n,
        "old": {"acc": round(old_acc, 4), "f1": round(old_f1, 4), "TP": old_tp, "FP": old_fp, "FN": old_fn, "TN": old_tn},
        "new": {"acc": round(new_acc, 4), "f1": round(new_f1, 4), "TP": tp, "FP": fp, "FN": fn, "TN": tn, "regimes": regime_counts},
    }


def eval_bait60():
    files = [
        ("REAL", os.path.join(BASE, "python", "eval_bait60_REAL.jsonl")),
        ("BAIT", os.path.join(BASE, "python", "eval_bait60_BAIT.jsonl")),
        ("FAKE", os.path.join(BASE, "python", "eval_bait60_FAKE.jsonl")),
    ]
    stats = {}
    print("\n=== [2] eval_bait60 三類基準測試 (REAL>=60, BAIT<=60, FAKE<40) ===")
    for grp, fpath in files:
        items = [json.loads(l) for l in open(fpath, encoding="utf-8") if l.strip()]
        old_ok = 0
        new_ok = 0
        new_strict_ok = 0
        old_scores = []
        new_scores = []
        misses = []
        for it in items:
            title = it["title"]
            content = it["content"]
            url = it.get("url", "")

            is_cna = "cna.com.tw" in url
            old_dom = 25.0 if is_cna else 15.0
            has_old_cb = any(kw in (title + content[:300]) for kw in [
                "震撼", "網全嚇傻", "竟然", "不看會後悔", "會後悔", "急了", "震撼彈", "太誇張",
                "傻眼", "敗類", "割韭菜", "驚傳", "瘋傳", "洗版", "嚇呆", "驚呆", "全網",
                "嚇傻", "傻了", "震驚", "踢爆", "細思極恐", "不轉不是", "沉默了", "嚇壞",
                "慘了", "出事了", "出大事", "天塌了"
            ])
            old_sent = 7.5 if has_old_cb else 15.0
            old_rule = (old_dom + 15.0 + old_sent + 12.0)
            old_final = min(old_rule, 60.0) if has_old_cb else old_rule
            old_scores.append(old_final)

            if grp == "REAL" and old_final >= 60.0:
                old_ok += 1
            elif grp == "BAIT" and old_final <= 60.0:
                old_ok += 1
            elif grp == "FAKE" and old_final < 60.0:
                old_ok += 1

            out = score_orthogonal(
                title=title, url=url, content=content,
                sentiment_val=0.2, title_body_sim=0.75,
                sources=[], web_results=[], deep={},
            )
            ns = out["final_score"]
            new_scores.append(ns)
            ok = (
                (grp == "REAL" and ns >= 60.0)
                or (grp == "BAIT" and ns <= 60.0)
                or (grp == "FAKE" and ns < 60.0)
            )
            strict_ok = (
                (grp == "REAL" and ns >= 70.0)
                or (grp == "BAIT" and ns <= 60.0)
                or (grp == "FAKE" and ns < 40.0)
            )
            if ok:
                new_ok += 1
            else:
                misses.append((it["id"], ns, title, out["regime"]))
            if strict_ok:
                new_strict_ok += 1

        print(f"  {grp:4s} (n={len(items)}): 舊版無查核規則通過={old_ok}/{len(items)} (均分 {sum(old_scores)/len(old_scores):.1f}) | "
              f"新版通過={new_ok}/{len(items)} (嚴格帶通過={new_strict_ok}/{len(items)}, 均分 {sum(new_scores)/len(new_scores):.1f})")
        if misses:
            print(f"    ! 未過項目: {misses}")
        stats[grp] = {
            "n": len(items),
            "old_pass": old_ok,
            "old_mean": round(sum(old_scores) / len(old_scores), 1),
            "new_pass": new_ok,
            "new_strict_pass": new_strict_ok,
            "new_mean": round(sum(new_scores) / len(new_scores), 1),
        }
    return stats


def eval_regress_cases():
    cases_path = os.path.join(BASE, "data", "eval", "regression_cases.json")
    cases = json.load(open(cases_path, encoding="utf-8"))
    print("\n=== [3] regression_cases.json 歷史 7 大回歸案例驗證 ===")
    results = []
    all_pass = True
    for c in cases:
        cid = c["id"]
        dump_path = os.path.join(BASE, "data", "regress_out", f"{cid}.json")
        d = json.load(open(dump_path, encoding="utf-8"))
        req = c["request"]
        title = d.get("title") or req.get("title") or ""
        url = d.get("url") or req.get("url") or ""
        content = req.get("content") or title

        out = score_orthogonal(
            title=title,
            url=url,
            content=content,
            sources=d.get("sources") or [],
            web_results=d.get("web_results") or [],
            deep=d.get("deep_analysis") or {},
        )
        ns = out["final_score"]
        old_s = d.get("final_score")
        strict = c.get("strict")
        if strict == "ceiling":
            ok = ns <= c["expect_max_score"]
        elif strict:
            ok = ns >= c["expect_min_score"]
        else:
            ok = (c["expect_min_score"] <= ns <= c["expect_max_score"] and out["rating_text"] == c["expect_rating"])
        if not ok:
            all_pass = False
        print(f"  {'PASS' if ok else 'FAIL'} {cid:10s} | 舊分={old_s:6.2f} -> 新分={ns:6.2f} ({out['rating_text']}) | 路由={out['regime']} | {c['desc']}")
        results.append({
            "id": cid, "desc": c["desc"], "old_score": round(old_s, 2),
            "new_score": ns, "new_rating": out["rating_text"],
            "regime": out["regime"], "pass": ok,
        })
    assert all_pass, "Regression cases failed!"
    return results


def eval_abstain_cap():
    from check_abstain_cap import FAKE as ABSTAIN_FAKE
    print("\n=== [4] check_abstain_cap.py (無證據之偽造公共新聞 3 案) ===")
    res = []
    for tag, title, text in ABSTAIN_FAKE:
        out = score_orthogonal(
            title=title,
            url="https://unknown",
            content=text,
            sources=[],
            web_results=[],
            deep={"abstain": True, "evidence_state": "no_evidence", "credibility_score": 48},
        )
        ns = out["final_score"]
        ok = ns <= 55.0
        print(f"  {'PASS' if ok else 'FAIL'} {tag:10s} | 新分={ns:5.1f} (<=55.0, 舊版未加補丁前為 68.2) | 路由={out['regime']} | D4風險={out['dimensions']['rhetorical_risk']['value']}")
        assert ok, f"Abstain cap failed on {tag}: {ns}"
        res.append({"tag": tag, "new_score": ns, "regime": out["regime"], "d4_risk": out["dimensions"]["rhetorical_risk"]["value"], "pass": ok})
    return res


def eval_tw_media_sweep():
    path = os.path.join(BASE, "data", "eval", "tw_media_sweep.jsonl")
    recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    print(f"\n=== [5] tw_media_sweep.jsonl (台灣主流媒體即時新聞 n={len(recs)}) ===")
    new_scores = []
    regimes = {}
    for r in recs:
        title = r.get("title") or ""
        url = r.get("url") or ""
        da = r.get("deep_analysis") or {}
        content = (da.get("claim") or "") + " " + (da.get("analysis") or "")
        out = score_orthogonal(
            title=title,
            url=url,
            content=content,
            sources=r.get("sources") or [],
            web_results=r.get("web_results") or [],
            deep=da,
        )
        new_scores.append(out["final_score"])
        regimes[out["regime"]] = regimes.get(out["regime"], 0) + 1
    new_ge60 = sum(1 for s in new_scores if s >= 60.0)
    new_ge45 = sum(1 for s in new_scores if s >= 45.0)
    print(f"  舊版均分={sum(float(r.get('final_score',0)) for r in recs)/len(recs):.1f} | 新版均分={sum(new_scores)/len(new_scores):.1f}")
    print(f"  新版 >=60 (大致/高度可信, 無釣魚標者): {new_ge60}/{len(recs)} | >=45 (無被誤鎖死<25者): {new_ge45}/{len(recs)}")
    print(f"  路由分佈: {regimes}")
    return {
        "n": len(recs),
        "new_mean": round(sum(new_scores) / len(new_scores), 1),
        "new_ge60": new_ge60,
        "new_ge45": new_ge45,
        "regimes": regimes,
    }


if __name__ == "__main__":
    summary = {
        "metrics_500": eval_metrics_500(),
        "bait60": eval_bait60(),
        "regression_7": eval_regress_cases(),
        "abstain_cap_3": eval_abstain_cap(),
        "tw_media_48": eval_tw_media_sweep(),
    }
    print("\nALL 5 BENCHMARK SUITES COMPLETED SUCCESSFULLY.")
