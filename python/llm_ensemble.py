"""多模型共識評分：同一篇文章跑 N 個模型，用多數決決定分數。

不做複雜加權——證據是「不同模型的判斷分歧度」本身，而不是分數平均。
文獻（arXiv 2602.11619）：多數決對系統性錯誤只有 +0~2pp；真正有效的是
「分歧就 abstain」。所以這裡同時回傳 agree_ratio，前端可據此提示不確定。

用法：
  from llm_ensemble import consensus_score
  r = consensus_score(title, web_results, sources, content, model_ids=[...])
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_MODELS = [
    "local/qwen3.8-27b-fastmtp",
    "antigravity/claude-sonnet-4-6",
    "antigravity/claude-opus-4-6-thinking",
    "openrouter/qwen/qwen3.8-27b:free",
]

# 分數帶（低於這個區間算「假」、高於算「真」）。中間地帶不投票，避免
# 「所有人都說不確定」被多數決硬逼成某一邊。
FAKE_MAX = 50
BUCKET = 10   # 只比較分數落在哪個十位帶，不比精確值——模型間分數尺度不可比


def _bucket(score: float):
    if score < FAKE_MAX:
        return "fake"
    if score >= 80:
        return "real"
    return None          # 中間地帶：觀察但不投票


def consensus_score(title, web_results, sources, content="",
                    model_ids=None, timeout=90):
    """回傳 {consensus_score, votes, agree_ratio, details[], abstained}"""
    import fake_news_server_new as F
    ids = model_ids or DEFAULT_MODELS
    details, votes = [], {"fake": 0, "real": 0}
    scores = []

    for mid in ids:
        try:
            r = F.deep_analyze(title, web_results, sources,
                               timeout=timeout, content=content, model_id=mid)
        except Exception as e:
            details.append({"model": mid, "error": f"{type(e).__name__}: {e}"})
            continue
        cs = r.get("credibility_score")
        if cs is None:
            details.append({"model": mid, "error": r.get("skipped") or "no score"})
            continue
        cs = float(cs)
        scores.append(cs)
        b = _bucket(cs)
        if b:
            votes[b] += 1
        details.append({
            "model": mid, "credibility_score": int(round(cs)),
            "bucket": b or "middle", "evidence_state": r.get("evidence_state"),
            "abstain": bool(r.get("abstain")),
            "reason": (r.get("summary") or r.get("analysis") or "")[:200],
        })

    total = votes["fake"] + votes["real"]
    if not total:
        return {"consensus_score": None, "votes": votes, "agree_ratio": 0.0,
                "details": details, "abstained": True,
                "reason": "沒有任何模型給出可用分數"}

    if votes["fake"] == votes["real"]:
        # 平手：這正是系統性錯誤的訊號 → abstain，不是硬選一邊
        return {"consensus_score": None, "votes": votes,
                "agree_ratio": votes["fake"] / total,
                "details": details, "abstained": True,
                "reason": f"平手（{votes['fake']}:{votes['real']}），模型分歧大"}

    winner = "fake" if votes["fake"] > votes["real"] else "real"
    agree = max(votes["fake"], votes["real"]) / total
    # 投票決定真偽，分數取投該邊的模型的中位數（尺度不可比，不平均全體）
    side = [s for s, b in zip(scores, [d.get("bucket") for d in details]) if b == winner]
    cs = sorted(side)[len(side) // 2] if side else None

    return {"consensus_score": int(round(cs)) if cs is not None else None,
            "votes": votes, "agree_ratio": round(agree, 3),
            "verdict": winner, "details": details,
            # 同意率低 = 分歧 = 該提示使用者這題不可靠
            "abstained": agree < 0.6,
            "reason": f"{votes['fake']}票假 / {votes['real']}票真"}


def _demo():
    """自檢：投票邏輯。這是會決定使用者看到什麼分數的路徑。
    執行：.venv/bin/python llm_ensemble.py"""
    from llm_ensemble import _bucket
    assert _bucket(10) == "fake"
    assert _bucket(49) == "fake"
    assert _bucket(50) is None, "50 分不該算假新聞"
    assert _bucket(65) is None, "中間地帶不投票"
    assert _bucket(85) == "real"
    print("  ok  分桶邊界")

    # 模擬平手 → 必須 abstain，不能硬選
    import fake_news_server_new as F
    calls = []
    def fake_da(title, web, src, timeout=None, content="", model_id=""):
        calls.append(model_id)
        return {"credibility_score": {"a": 10, "b": 90}[model_id]}
    orig = F.deep_analyze
    F.deep_analyze = fake_da
    try:
        r = consensus_score("t", [], [], "", model_ids=["a", "b"])
        assert r["consensus_score"] is None and r["abstained"], r
        assert r["votes"] == {"fake": 1, "real": 1}, r
        print("  ok  平手 → abstain（不硬選）")

        # 一致 → 給分
        F.deep_analyze = lambda t, w, s, timeout=None, content="", model_id="": \
            {"credibility_score": 88 if model_id in ("a", "b", "c") else 30}
        r = consensus_score("t", [], [], "", model_ids=["a", "b", "c", "d"])
        assert r["verdict"] == "real" and not r["abstained"], r
        assert r["consensus_score"] == 88, r
        print(f"  ok  3:1 一致 → {r['consensus_score']} (agree={r['agree_ratio']})")

        # 分歧 → abstain
        F.deep_analyze = lambda t, w, s, timeout=None, content="", model_id="": \
            {"credibility_score": {"a": 10, "b": 88, "c": 30, "d": 85}[model_id]}
        r = consensus_score("t", [], [], "", model_ids=["a", "b", "c", "d"])
        assert r["abstained"], r
        print(f"  ok  分歧 → abstain (agree={r['agree_ratio']})")

        # 全部失敗
        F.deep_analyze = lambda *a, **k: {}
        r = consensus_score("t", [], [], "", model_ids=["a"])
        assert r["consensus_score"] is None and r["abstained"], r
        print("  ok  全失敗 → abstain + 回原因")
    finally:
        F.deep_analyze = orig
    print("ALL PASS")


if __name__ == "__main__":
    _demo()