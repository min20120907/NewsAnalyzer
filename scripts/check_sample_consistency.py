"""跨次取樣一致性 → selective prediction（不一致就 abstain）。

2026-10-01。文獻：arXiv 2602.11619 —— 多步驟 agent 的多數決只有 +0~2pp
（錯誤是系統性的），改用「不一致就 abstain」有 +6~14pp。
跑：.venv/bin/python scripts/check_sample_consistency.py
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))


def agg(results):
    """複製 deep_analyze_ensemble 的 aggregation 邏輯（不呼叫 LLM）。"""
    valid = [r for r in results
             if isinstance(r, dict) and r.get("credibility_score") is not None]
    if not valid:
        return None
    scores = [float(r["credibility_score"]) for r in valid]
    avg = sum(scores) / len(scores)
    states = [str(r.get("evidence_state") or "") for r in valid]
    state = max(set(states), key=states.count)
    consistent = (states.count(state) == len(states))
    disputed = len(valid) > 1 and not consistent
    best = min(valid, key=lambda r: (str(r.get("evidence_state") or "") != state,
                                     abs(float(r["credibility_score"]) - avg)))
    abst = bool(best.get("abstain")) or disputed
    return {
        "evidence_state": state,
        "abstain": abst,
        "credibility_score": 60 if abst else int(round(avg)),
        "consistent": consistent, "disputed": disputed, "samples": len(valid),
    }


def r(state, score, abstain=False):
    return {"evidence_state": state, "credibility_score": score,
            "abstain": abstain}


def demo():
    # 三次一致 → 照常給分，不 abstain
    a = agg([r("full_body_evidence", 30), r("full_body_evidence", 40),
             r("full_body_evidence", 35)])
    assert a["consistent"] and not a["disputed"] and not a["abstain"], a
    assert a["credibility_score"] == 35, a          # 3 次平均
    assert a["evidence_state"] == "full_body_evidence"

    # 實測 sw0 的擺動形態：unrelated(對) 與 full_body(錯) 交錯 → 不給結論
    b = agg([r("unrelated_evidence", 60, True), r("full_body_evidence", 30),
             r("unrelated_evidence", 60, True)])
    assert b["disputed"] and b["abstain"], b
    assert b["credibility_score"] == 60, b          # abstain 固定 60，不用平均
    # 多數決選出 unrelated，但因為不一致仍然 abstain
    assert b["evidence_state"] == "unrelated_evidence", b

    # 2:1 也是不一致（門檻是「全部一致」，不是「有過半」）
    c = agg([r("no_evidence", 60, True), r("full_body_evidence", 30),
             r("no_evidence", 55, True)])
    assert c["disputed"] and c["abstain"], c

    # n=1 不強制 abstain（否則全部變暫時分數）
    d = agg([r("no_evidence", 60, True)])
    assert not d["disputed"], d
    assert d["abstain"] is True                     # 沿用樣本自己的 abstain

    e = agg([r("full_body_evidence", 25)])
    assert not e["disputed"] and not e["abstain"], e

    # 單次樣本自己 abstain 就 abstain
    assert agg([r("no_evidence", 60, True)])["abstain"]
    # 全空 → None
    assert agg([]) is None
    assert agg([{"evidence_state": "x"}]) is None   # 缺 credibility_score

    # 2026-10-01：deep 模式不能退回 n=1。上一版靠 systemd override 設
    # DEEP_ANALYZE_SAMPLES=3，override 一拿掉 deep 就靜默變 n=1（實測踩到）。
    import fake_news_server_new as F
    assert F._samples_for("fast") == 1, F._samples_for("fast")
    assert F._samples_for("deep") >= 2, f"deep 退回 n=1：{F._samples_for('deep')}"
    for bad in ("", None, "quick", "深度", "deepest"):
        assert F._samples_for(bad) == 1, f"非法 mode {bad!r} 應退回 fast"
    assert F._samples_for("Deep") >= 2, "大小寫不敏感"
    assert F._samples_for("DEEP") >= 2, "全大寫也要認"

    print("ALL PASS — 跨次不一致就 abstain，一致才給分")


if __name__ == "__main__":
    demo()
