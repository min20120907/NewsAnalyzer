# -*- coding: utf-8 -*-
"""
NewsAnalyzer 完整評測與正交消融實驗腳本 (Full Evaluation, Ablation & Confusion Matrix Suite)
=============================================================================================
一次跑完並輸出所有詳細指標：
  1. E1: Cofacts 500 探針集 — 舊版 7 變體消融 vs 新版 D1~D4 正交消融（含完整 Confusion Matrix、P/R/F1_fake、P/R/F1_real、Macro-F1、Balanced Acc、MCC、FPR、FNR、Loss L）
  2. E2: 跨場景全維度必要性消融矩陣與全集混淆矩陣（N=614：500 Cofacts + 20 REAL + 20 BAIT + 23 Unverified Hoax + 44 TWMedia + 7 Regression）
  3. E3: Paired Baseline 與競爭範式對比（n=498 配對交集 & N=2,292 全語料：Majority / TF-IDF / Domain-Only / Zero-Shot Qwen3.8-27B / 舊版 Hybrid / 新版 4-Dim Orthogonal，含 10,000 次 Bootstrap 95% CI 與 McNemar 精確檢定）
  4. E4: Dev / Test 分層切分驗證（seed=42，n=250 / n=250，對照舊版 Stage-3 Clamp Sweep 與新版零 Clamp 三態路由）
  5. E5: 五級評分帶校準與分佈對照（Calibration 5 Bands：<20 / 20-40 / 40-60 / 60-75 / 75-100，含 P(FAKE|band)、ECE、Brier Score 與分數極值檢查）
"""

from __future__ import annotations
import json
import math
import os
import random
import sys
from typing import Dict, List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = "/working_dir/c_76b7a5665ebe4c19"
CANDIDATE_BASE = os.path.dirname(SCRIPT_DIR)
if os.path.exists(os.path.join(CANDIDATE_BASE, "data", "eval", "metrics_500.jsonl")):
    BASE = CANDIDATE_BASE
else:
    BASE = os.path.join(WORK_DIR, "extracted", "NewsAnalyzer-b5e9bcb82d26bbaa54cb08676064366de46ae54a")

OUT_DIR = os.path.join(CANDIDATE_BASE, "data", "eval")
sys.path.insert(0, OUT_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(BASE, "python"))
sys.path.insert(0, os.path.join(BASE, "scripts"))

from orthogonal_scorer import (
    DimensionOutput,
    compute_d1_evidence_verdict,
    compute_d2_source_corroboration,
    compute_d3_headline_faithfulness,
    compute_d4_rhetorical_risk,
)

CUTOFF = 60
SEED = 42
BOOT = 10000


def detailed_cm_metrics(pairs: List[Tuple[str, str]]) -> Dict:
    tp = sum(1 for t, p in pairs if t == "FAKE" and p == "FAKE")
    fp = sum(1 for t, p in pairs if t == "REAL" and p == "FAKE")
    fn = sum(1 for t, p in pairs if t == "FAKE" and p == "REAL")
    tn = sum(1 for t, p in pairs if t == "REAL" and p == "REAL")
    n = len(pairs)

    acc = (tp + tn) / n if n else 0.0

    p_fake = tp / (tp + fp) if (tp + fp) else 0.0
    r_fake = tp / (tp + fn) if (tp + fn) else 0.0
    f1_fake = 2 * p_fake * r_fake / (p_fake + r_fake) if (p_fake + r_fake) else 0.0

    p_real = tn / (tn + fn) if (tn + fn) else 0.0
    r_real = tn / (tn + fp) if (tn + fp) else 0.0
    f1_real = 2 * p_real * r_real / (p_real + r_real) if (p_real + r_real) else 0.0

    macro_f1 = 0.5 * (f1_fake + f1_real)
    bal_acc = 0.5 * (r_fake + r_real)

    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (fn + tp) if (fn + tp) else 0.0

    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = ((tp * tn) - (fp * fn)) / denom if denom > 0 else 0.0

    loss_l = 2 * fn + fp

    return {
        "n": n,
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "acc": round(acc, 4),
        "p_fake": round(p_fake, 4),
        "r_fake": round(r_fake, 4),
        "f1_fake": round(f1_fake, 4),
        "p_real": round(p_real, 4),
        "r_real": round(r_real, 4),
        "f1_real": round(f1_real, 4),
        "macro_f1": round(macro_f1, 4),
        "balanced_acc": round(bal_acc, 4),
        "mcc": round(mcc, 4),
        "fpr": round(fpr, 4),
        "fnr": round(fnr, 4),
        "L": loss_l,
    }


def score_orthogonal_ablated(
    *,
    title: str = "",
    url: str = "",
    content: str = "",
    sentiment_val: float = 0.0,
    title_body_sim: float | None = None,
    sources: list | None = None,
    web_results: list | None = None,
    corr_outlets: list | None = None,
    deep: dict | None = None,
    disable_dims: Tuple[str, ...] = (),
) -> Dict:
    d1 = compute_d1_evidence_verdict(sources=sources, deep=deep)
    d2 = compute_d2_source_corroboration(
        title=title, url=url, content=content,
        corr_outlets=corr_outlets, web_results=web_results, deep=deep,
    )
    d3 = compute_d3_headline_faithfulness(
        title=title, content=content, title_body_sim=title_body_sim, deep=deep,
    )
    d4 = compute_d4_rhetorical_risk(
        title=title, content=content, sentiment_val=sentiment_val,
        is_mainstream_or_corroborated=(d2.value >= 0.60 and "D2" not in disable_dims),
        deep=deep,
    )

    if "D1" in disable_dims:
        d1 = DimensionOutput(
            id="D1", key="evidence_verdict", name="查核證據蘊涵度",
            what_it_measures=d1.what_it_measures, what_if_wrong=d1.what_if_wrong,
            value=0.0, confidence=0.0, status_label="none", impact_pts=0.0,
            explanation="[消融關閉 D1]"
        )
    if "D2" in disable_dims:
        d2 = DimensionOutput(
            id="D2", key="source_corroboration", name="跨源報導佐證度",
            what_it_measures=d2.what_it_measures, what_if_wrong=d2.what_if_wrong,
            value=0.0, confidence=0.0, status_label="uncorroborated", impact_pts=0.0,
            explanation="[消融關閉 D2]"
        )
    if "D3" in disable_dims:
        d3 = DimensionOutput(
            id="D3", key="headline_faithfulness", name="標題內文忠實度",
            what_it_measures=d3.what_it_measures, what_if_wrong=d3.what_if_wrong,
            value=1.0, confidence=0.0, status_label="faithful", impact_pts=0.0,
            explanation="[消融關閉 D3]"
        )
    if "D4" in disable_dims:
        d4 = DimensionOutput(
            id="D4", key="rhetorical_risk", name="內文修辭與可驗性風險",
            what_it_measures=d4.what_it_measures, what_if_wrong=d4.what_if_wrong,
            value=0.0, confidence=0.0, status_label="low_risk", impact_pts=58.0,
            explanation="[消融關閉 D4]"
        )

    ai_cs = float(deep["credibility_score"]) if (isinstance(deep, dict) and deep.get("credibility_score") is not None) else None
    ai_abstain = bool(deep.get("abstain")) if isinstance(deep, dict) else True

    if d1.status_label in ("refutes", "partially_refutes", "supports"):
        regime = "VERIFIED_EVIDENCE"
        base_score = d1.impact_pts
        if d1.status_label == "refutes":
            final_score = base_score
            if ai_cs is not None and not ai_abstain and ai_cs <= 35:
                final_score = 0.85 * base_score + 0.15 * min(25.0, ai_cs)
        elif d1.status_label == "partially_refutes":
            final_score = max(40.0, min(55.0, base_score + 0.3 * d3.impact_pts))
        else:
            base_with_llm = (0.85 * base_score + 0.15 * ai_cs) if (ai_cs is not None and not ai_abstain and ai_cs >= 65) else base_score
            final_score = max(52.0, min(96.0, base_with_llm + d3.impact_pts))
    elif d2.value >= 0.60 and d2.status_label != "blocked":
        regime = "CORROBORATED_REPORT"
        base_score = d2.impact_pts
        if ai_cs is not None and not ai_abstain and ai_cs >= 60:
            base_score = 0.70 * base_score + 0.30 * ai_cs
        rhet_adj = -8.0 * max(0.0, d4.value - 0.25)
        final_score = base_score + d3.impact_pts + rhet_adj
        if d3.impact_pts <= -18.0:
            final_score = min(59.0, max(45.0, final_score))
        else:
            final_score = max(62.0, min(92.0, final_score))
    else:
        regime = "UNVERIFIED_ABSTAIN"
        base_unverified = d4.impact_pts
        if d2.status_label == "blocked":
            base_unverified -= 12.0
        final_score = max(10.0, min(58.0, base_unverified + 0.5 * d3.impact_pts))

    return {
        "final_score": round(max(0.0, min(100.0, final_score)), 2),
        "regime": regime,
        "d1": d1, "d2": d2, "d3": d3, "d4": d4,
    }


OLD_VARIANTS = {
    "legacy_full": ("sentiment", "domain", "fact_check", "user_feedback", "similarity", "timeliness"),
    "legacy_evidence_only": ("fact_check", "user_feedback"),
    "legacy_metadata_only": ("sentiment", "domain", "similarity", "timeliness"),
    "legacy_minus_domain": ("sentiment", "fact_check", "user_feedback", "similarity", "timeliness"),
    "legacy_minus_sentiment": ("domain", "fact_check", "user_feedback", "similarity", "timeliness"),
    "legacy_minus_timeliness": ("sentiment", "domain", "fact_check", "user_feedback", "similarity"),
    "legacy_minus_clamp": ("sentiment", "domain", "fact_check", "user_feedback", "similarity", "timeliness"),
}

FC_HIT_STATUS = ("hit", "ok", "inaccurate", "partial")


def legacy_stage3(post: float, sources: list, tau: float = 25.0) -> float:
    final = post
    for s in (sources or []):
        st = s.get("status")
        try:
            sim = float(s.get("sim") or 0.0)
        except (TypeError, ValueError):
            sim = 0.0
        if st in ("inaccurate", "false", "misleading", "fake"):
            if sim >= 0.85:
                final = min(final, tau)
                break
            elif sim >= 0.72:
                final = min(final, 50.0)
                break
        elif st == "partial":
            final = min(final, 55.0)
    return final


def legacy_score_of(rec: dict, kept: tuple, use_clamp: bool = True) -> float:
    mets = rec["metrics"]
    num = sum(float(mets[c]["score"]) for c in kept)
    den = sum(float(mets[c]["weight"]) for c in kept)
    rule = num / den * 100.0
    cs = rec.get("deep_cs")
    if cs is not None and not rec.get("abstain"):
        if "fact_check" in kept:
            fc_hit = any(s.get("status") in FC_HIT_STATUS for s in (rec.get("sources") or []))
            w = 0.10 if fc_hit else 0.60
        else:
            w = 0.60
        post = rule * (1 - w) + float(cs) * w
    else:
        post = rule
    return legacy_stage3(post, rec.get("sources")) if use_clamp else post


def orth_score_on_m500_rec(rec: dict, disable_dims: Tuple[str, ...] = ()) -> Dict:
    mets = rec.get("metrics") or {}
    dom_score = float((mets.get("domain") or {}).get("score", 15.0))
    url = "https://www.cna.com.tw/news/a.html" if dom_score >= 25.0 else "https://unknown"
    sent_score = float((mets.get("sentiment") or {}).get("score", 15.0))
    sent_val = 0.2 if sent_score >= 15.0 else (0.7 if sent_score >= 10.0 else 0.9)
    sim_score = float((mets.get("similarity") or {}).get("score", 9.0))
    sim_val = sim_score / 15.0

    has_fc_hit = any(s.get("status") in ("inaccurate", "partial", "accurate") for s in (rec.get("sources") or []))
    deep_mock = {
        "credibility_score": rec.get("deep_cs"),
        "abstain": bool(rec.get("abstain", False)),
        "evidence_state": "full_body_evidence" if has_fc_hit else "no_evidence",
    }
    return score_orthogonal_ablated(
        title="", url=url, content="",
        sentiment_val=sent_val, title_body_sim=sim_val,
        sources=rec.get("sources") or [], deep=deep_mock,
        disable_dims=disable_dims,
    )


def run_e1_ablation_500():
    path = os.path.join(BASE, "data", "eval", "metrics_500.jsonl")
    recs = [json.loads(l) for l in open(path, encoding="utf-8") if not json.loads(l).get("error")]

    out = {"legacy_variants": {}, "orthogonal_variants": {}}
    for vname, kept in OLD_VARIANTS.items():
        use_clamp = (vname != "legacy_minus_clamp")
        pairs = [(r["true"], "FAKE" if legacy_score_of(r, kept, use_clamp=use_clamp) < CUTOFF else "REAL") for r in recs]
        out["legacy_variants"][vname] = detailed_cm_metrics(pairs)

    orth_configs = {
        "orth_full": (),
        "orth_minus_D1_evidence": ("D1",),
        "orth_minus_D2_source": ("D2",),
        "orth_minus_D3_faithfulness": ("D3",),
        "orth_minus_D4_risk": ("D4",),
        "orth_D1_only": ("D2", "D3", "D4"),
    }
    for vname, dis in orth_configs.items():
        pairs = []
        for r in recs:
            res = orth_score_on_m500_rec(r, disable_dims=dis)
            pairs.append((r["true"], "FAKE" if res["final_score"] < CUTOFF else "REAL"))
        out["orthogonal_variants"][vname] = detailed_cm_metrics(pairs)

    return out


def run_e2_cross_scenario_ablation():
    path_500 = os.path.join(BASE, "data", "eval", "metrics_500.jsonl")
    recs_500 = [json.loads(l) for l in open(path_500, encoding="utf-8")]

    real_20 = [json.loads(l) for l in open(os.path.join(BASE, "python", "eval_bait60_REAL.jsonl"), encoding="utf-8") if l.strip()]
    bait_20 = [json.loads(l) for l in open(os.path.join(BASE, "python", "eval_bait60_BAIT.jsonl"), encoding="utf-8") if l.strip()]
    fake_20 = [json.loads(l) for l in open(os.path.join(BASE, "python", "eval_bait60_FAKE.jsonl"), encoding="utf-8") if l.strip()]

    from check_abstain_cap import FAKE as ABSTAIN_3
    tw_48 = [json.loads(l) for l in open(os.path.join(BASE, "data", "eval", "tw_media_sweep.jsonl"), encoding="utf-8") if l.strip()]
    reg_7 = json.load(open(os.path.join(BASE, "data", "eval", "regression_cases.json"), encoding="utf-8"))

    configs = [
        ("Full Orthogonal (D1+D2+D3+D4)", ()),
        ("w/o D1 (Evidence Verdict)", ("D1",)),
        ("w/o D2 (Source & Corroboration)", ("D2",)),
        ("w/o D3 (Headline Faithfulness)", ("D3",)),
        ("w/o D4 (Rhetorical Risk)", ("D4",)),
    ]

    matrix = {}
    for label, dis in configs:
        all_614_pairs: List[Tuple[str, str]] = []

        # 1. Cofacts 500 (cutoff 60)
        p500 = []
        for r in recs_500:
            pred = "FAKE" if orth_score_on_m500_rec(r, dis)["final_score"] < 60 else "REAL"
            p500.append((r["true"], pred))
            all_614_pairs.append((r["true"], pred))
        m500 = detailed_cm_metrics(p500)

        # 2. eval_bait60_REAL (n=20, truth="REAL", pass: >=60)
        r_pass = 0
        for it in real_20:
            sc = score_orthogonal_ablated(
                title=it["title"], url=it.get("url", ""), content=it["content"],
                sentiment_val=0.2, title_body_sim=0.75, disable_dims=dis
            )["final_score"]
            if sc >= 60.0:
                r_pass += 1
            all_614_pairs.append(("REAL", "REAL" if sc >= 60.0 else "FAKE"))

        # 3. eval_bait60_BAIT (n=20, should be flagged <=60 -> treated as positive for gate check)
        b_pass = 0
        for it in bait_20:
            sc = score_orthogonal_ablated(
                title=it["title"], url=it.get("url", ""), content=it["content"],
                sentiment_val=0.2, title_body_sim=0.75, disable_dims=dis
            )["final_score"]
            if sc <= 60.0:
                b_pass += 1
            all_614_pairs.append(("FAKE", "FAKE" if sc <= 60.0 else "REAL"))

        # 4. eval_bait60_FAKE + check_abstain_cap (n=23, strict <40)
        f_strict = 0
        for it in fake_20:
            sc = score_orthogonal_ablated(
                title=it["title"], url=it.get("url", ""), content=it["content"],
                sentiment_val=0.2, title_body_sim=0.75, disable_dims=dis
            )["final_score"]
            if sc < 40.0:
                f_strict += 1
            all_614_pairs.append(("FAKE", "FAKE" if sc < 40.0 else "REAL"))

        a_strict = 0
        for _, title, text in ABSTAIN_3:
            sc = score_orthogonal_ablated(
                title=title, url="https://unknown", content=text,
                deep={"abstain": True, "evidence_state": "no_evidence", "credibility_score": 48},
                disable_dims=dis
            )["final_score"]
            if sc <= 40.0:
                a_strict += 1
            all_614_pairs.append(("FAKE", "FAKE" if sc <= 40.0 else "REAL"))

        # 5. Open-world Mainstream (tw_media_sweep 44 non-bait >=60 + regression_cases 7/7)
        tw_nonbait_pass = 0
        tw_nonbait_total = 0
        for r in tw_48:
            da = r.get("deep_analysis") or {}
            content = (da.get("claim") or "") + " " + (da.get("analysis") or "")
            full_ref = score_orthogonal_ablated(
                title=r.get("title") or "", url=r.get("url") or "", content=content,
                sources=r.get("sources") or [], web_results=r.get("web_results") or [], deep=da,
                disable_dims=()
            )
            if full_ref["d3"].impact_pts == 0 and full_ref["d2"].value >= 0.60:
                tw_nonbait_total += 1
                sc = score_orthogonal_ablated(
                    title=r.get("title") or "", url=r.get("url") or "", content=content,
                    sources=r.get("sources") or [], web_results=r.get("web_results") or [], deep=da,
                    disable_dims=dis
                )["final_score"]
                if sc >= 60.0:
                    tw_nonbait_pass += 1
                all_614_pairs.append(("REAL", "REAL" if sc >= 60.0 else "FAKE"))

        reg_pass = 0
        for c in reg_7:
            cid = c["id"]
            d = json.load(open(os.path.join(BASE, "data", "regress_out", f"{cid}.json"), encoding="utf-8"))
            req = c["request"]
            title = d.get("title") or req.get("title") or ""
            url = d.get("url") or req.get("url") or ""
            content = req.get("content") or title
            ns = score_orthogonal_ablated(
                title=title, url=url, content=content,
                sources=d.get("sources") or [], web_results=d.get("web_results") or [],
                deep=d.get("deep_analysis") or {}, disable_dims=dis
            )["final_score"]
            strict = c.get("strict")
            ok = (ns <= c["expect_max_score"]) if strict == "ceiling" else (ns >= c["expect_min_score"])
            if ok:
                reg_pass += 1
            gt_reg = "FAKE" if strict == "ceiling" else "REAL"
            pred_reg = "FAKE" if ns < 60.0 else "REAL"
            all_614_pairs.append((gt_reg, pred_reg))

        combined_cm = detailed_cm_metrics(all_614_pairs)
        matrix[label] = {
            "cofacts_500_acc": m500["acc"],
            "cofacts_500_f1": m500["f1_fake"],
            "cofacts_500_r_real": m500["r_real"],
            "bait60_REAL_pass": f"{r_pass}/20 ({r_pass/20:.0%})",
            "bait60_BAIT_pass": f"{b_pass}/20 ({b_pass/20:.0%})",
            "unverified_hoax_strict_pass": f"{f_strict + a_strict}/23 ({(f_strict + a_strict)/23:.0%})",
            "openworld_mainstream_pass": f"{tw_nonbait_pass}/{tw_nonbait_total} ({tw_nonbait_pass/max(1,tw_nonbait_total):.0%})",
            "regression_7_pass": f"{reg_pass}/7 ({reg_pass/7:.0%})",
            "combined_614_cm": combined_cm,
        }
    return matrix


def binom_pmf(n: int, k: int) -> float:
    return math.comb(n, k) * (0.5 ** n)


def mcnemar_exact_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2.0 * sum(binom_pmf(n, i) for i in range(k + 1)))


def run_e3_paired_baselines():
    m500 = {json.loads(l)["rowid"]: json.loads(l) for l in open(os.path.join(BASE, "data", "eval", "metrics_500.jsonl"), encoding="utf-8")}
    clamp = {json.loads(l)["rowid"]: json.loads(l) for l in open(os.path.join(BASE, "data", "eval", "clamp_ablation_500.jsonl"), encoding="utf-8")}
    fair = {json.loads(l)["rowid"]: json.loads(l) for l in open(os.path.join(BASE, "data", "eval", "fair_baseline_500.jsonl"), encoding="utf-8")}
    bf = json.load(open(os.path.join(BASE, "data", "eval", "baselines_frozen.json"), encoding="utf-8"))

    common = [
        rid for rid in clamp
        if rid in fair and fair[rid].get("score") is not None and not fair[rid].get("error")
    ]

    pairs_orth = []
    pairs_legacy_clamp = []
    pairs_legacy_m500 = []
    pairs_fair = []

    for rid in common:
        gt = clamp[rid]["true"]
        orth_res = orth_score_on_m500_rec(m500[rid])
        pairs_orth.append((gt, "FAKE" if orth_res["final_score"] < CUTOFF else "REAL"))
        pairs_legacy_clamp.append((gt, "FAKE" if float(clamp[rid]["final_score"]) < CUTOFF else "REAL"))
        pairs_legacy_m500.append((gt, "FAKE" if float(m500[rid]["final_score"]) < CUTOFF else "REAL"))
        pairs_fair.append((gt, "FAKE" if float(fair[rid]["score"]) < CUTOFF else "REAL"))

    cm_orth = detailed_cm_metrics(pairs_orth)
    cm_leg_clamp = detailed_cm_metrics(pairs_legacy_clamp)
    cm_leg_m500 = detailed_cm_metrics(pairs_legacy_m500)
    cm_fair = detailed_cm_metrics(pairs_fair)

    ok_orth = [1 if t == p else 0 for t, p in pairs_orth]
    ok_fair = [1 if t == p else 0 for t, p in pairs_fair]
    b_zf = sum(1 for a, c in zip(ok_orth, ok_fair) if a == 1 and c == 0)
    c_zf = sum(1 for a, c in zip(ok_orth, ok_fair) if a == 0 and c == 1)
    p_zf = mcnemar_exact_p(b_zf, c_zf)

    rng = random.Random(SEED)
    n = len(common)
    diffs = []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append((sum(ok_orth[i] for i in idx) - sum(ok_fair[i] for i in idx)) / n)
    diffs.sort()
    ci_zf = [round(diffs[int(0.025 * BOOT)], 4), round(diffs[int(0.975 * BOOT)], 4)]

    b498 = bf["on_498_common"]
    def _from_counts(d):
        pairs = ([("FAKE", "FAKE")] * d["TP"] + [("REAL", "FAKE")] * d["FP"] +
                 [("FAKE", "REAL")] * d["FN"] + [("REAL", "REAL")] * d["TN"])
        return detailed_cm_metrics(pairs)

    return {
        "n_common": n,
        "majority_498": _from_counts(b498["majority"]),
        "tfidf_498": _from_counts(b498["tfidf_record5fold"]),
        "domain_strict_498": _from_counts(b498["domain_C_strict"]),
        "domain_selective_91": _from_counts(b498["domain_A_selective"]),
        "zeroshot_qwen27b_498": cm_fair,
        "legacy_m500_498": cm_leg_m500,
        "legacy_clamp500_498": cm_leg_clamp,
        "orthogonal_498": cm_orth,
        "orth_vs_zeroshot": {
            "delta_acc": round(cm_orth["acc"] - cm_fair["acc"], 4),
            "bootstrap_95_ci": ci_zf,
            "mcnemar_b": b_zf,
            "mcnemar_c": c_zf,
            "mcnemar_p": p_zf,
        },
    }


def run_e4_dev_test_split():
    m500 = {json.loads(l)["rowid"]: json.loads(l) for l in open(os.path.join(BASE, "data", "eval", "metrics_500.jsonl"), encoding="utf-8")}
    recs = [json.loads(l) for l in open(os.path.join(BASE, "data", "eval", "clamp_ablation_500.jsonl"), encoding="utf-8")]
    valid = [r for r in recs if not r.get("error") and r.get("post_fusion_score") is not None]

    rng = random.Random(SEED)
    fake = [r for r in valid if r["true"] == "FAKE"]
    real = [r for r in valid if r["true"] == "REAL"]
    rng.shuffle(fake)
    rng.shuffle(real)
    dev = fake[:len(fake) // 2] + real[:len(real) // 2]
    test = fake[len(fake) // 2:] + real[len(real) // 2:]

    def _eval_split(split_recs):
        p_off = [(r["true"], "FAKE" if float(r["post_fusion_score"]) < CUTOFF else "REAL") for r in split_recs]
        p_tau25 = [(r["true"], "FAKE" if float(r["final_score"]) < CUTOFF else "REAL") for r in split_recs]
        p_orth = [(r["true"], "FAKE" if orth_score_on_m500_rec(m500[r["rowid"]])["final_score"] < CUTOFF else "REAL") for r in split_recs]
        return {
            "legacy_stage3_off": detailed_cm_metrics(p_off),
            "legacy_stage3_tau25": detailed_cm_metrics(p_tau25),
            "orthogonal_zero_clamp": detailed_cm_metrics(p_orth),
        }

    return {"dev": _eval_split(dev), "test": _eval_split(test)}


BANDS = [
    (-1e9, 20.0, "<20", "高度可疑 (Highly suspicious)"),
    (20.0, 40.0, "20–40", "疑似不實 (Suspected fake)"),
    (40.0, 60.0, "40–60", "待查證 (Unverified)"),
    (60.0, 75.0, "60–75", "大致可信 (Likely credible)"),
    (75.0, 101.0, "75–100", "高度可信 (Highly credible)"),
]


def compute_calibration_table(scored_items: List[Tuple[str, float]]) -> Dict:
    n_total = len(scored_items)
    scores = [s for _, s in scored_items]
    n_neg = sum(1 for s in scores if s < 0)

    brier_sum = 0.0
    for truth, sc in scored_items:
        y_real = 1.0 if truth == "REAL" else 0.0
        p_real = max(0.0, min(1.0, sc / 100.0))
        brier_sum += (p_real - y_real) ** 2
    brier = brier_sum / n_total if n_total else 0.0

    bins = []
    ece = 0.0
    for lo, hi, bname, blabel in BANDS:
        inbin = [(t, s) for t, s in scored_items if lo <= s < hi]
        nb = len(inbin)
        n_fake = sum(1 for t, _ in inbin if t == "FAKE")
        n_real = nb - n_fake
        p_fake = n_fake / nb if nb else None
        p_real_emp = n_real / nb if nb else None
        mean_conf_real = (sum(max(0.0, min(1.0, s / 100.0)) for _, s in inbin) / nb) if nb else None
        if nb and p_real_emp is not None and mean_conf_real is not None:
            ece += (nb / n_total) * abs(p_real_emp - mean_conf_real)
        bins.append({
            "bin": bname,
            "label": blabel,
            "n": nb,
            "n_fake": n_fake,
            "n_real": n_real,
            "p_fake": round(p_fake, 4) if p_fake is not None else None,
            "p_real": round(p_real_emp, 4) if p_real_emp is not None else None,
            "mean_score": round(sum(s for _, s in inbin) / nb, 2) if nb else None,
        })

    return {
        "n": n_total,
        "min_score": round(min(scores), 2),
        "max_score": round(max(scores), 2),
        "n_negative": n_neg,
        "brier_score": round(brier, 4),
        "ece": round(ece, 4),
        "bins": bins,
    }


def run_e5_calibration():
    m500 = [json.loads(l) for l in open(os.path.join(BASE, "data", "eval", "metrics_500.jsonl"), encoding="utf-8")]
    c500 = [json.loads(l) for l in open(os.path.join(BASE, "data", "eval", "clamp_ablation_500.jsonl"), encoding="utf-8")]

    legacy_items = [(r["true"], float(r["final_score"])) for r in c500]
    orth_items = [(r["true"], orth_score_on_m500_rec(r)["final_score"]) for r in m500]

    return {
        "legacy_calibration": compute_calibration_table(legacy_items),
        "orthogonal_calibration": compute_calibration_table(orth_items),
    }


def main():
    e1 = run_e1_ablation_500()
    e2 = run_e2_cross_scenario_ablation()
    e3 = run_e3_paired_baselines()
    e4 = run_e4_dev_test_split()
    e5 = run_e5_calibration()

    full_report = {
        "E1_ablation_500": e1,
        "E2_cross_scenario_ablation_614": e2,
        "E3_paired_baselines_498": e3,
        "E4_dev_test_split_250_250": e4,
        "E5_calibration_500": e5,
    }
    out_path = os.path.join(OUT_DIR, "full_evaluation_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, ensure_ascii=False, indent=2)

    print("================================================================================")
    print("2B. [E2-CM] 全基準集 614 筆消融混淆矩陣 (N=614: 500 Cofacts + 20 REAL + 20 BAIT + 23 Hoax + 44 TWMedia + 7 Reg)")
    print("================================================================================")
    base_acc_614 = e2["Full Orthogonal (D1+D2+D3+D4)"]["combined_614_cm"]["acc"]
    for k, v in e2.items():
        cm = v["combined_614_cm"]
        d_acc = cm["acc"] - base_acc_614
        print(f"  {k:<32} | Acc={cm['acc']:.4f} ({d_acc:+.4f}) | F1_fk={cm['f1_fake']:.4f} F1_rl={cm['f1_real']:.4f} MacF1={cm['macro_f1']:.4f} BalAc={cm['balanced_acc']:.4f} MCC={cm['mcc']:.4f} | TP={cm['TP']} FP={cm['FP']} FN={cm['FN']} TN={cm['TN']} | L={cm['L']}")


if __name__ == "__main__":
    main()
