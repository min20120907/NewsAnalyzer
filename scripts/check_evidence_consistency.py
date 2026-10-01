"""LLM 自相矛盾時以分析文字為準，不讓錯誤的狀態欄鎖死真新聞。

2026-10-01 regression。跑：.venv/bin/python scripts/check_evidence_consistency.py
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))


def demo():
    import fake_news_server_new as F
    U = F._evidence_is_unrelated

    # 真實 regression 案例（景氣燈號連9紅）：狀態欄填錯，分析判斷完全正確
    contradiction = {
        "evidence_state": "full_body_evidence",
        "analysis": "財訊新聞提供了完整的官方數據來源…Cofacts 的查核結果因針對不同事件"
                     "（投資詐騙）而被判定為無關證據，不影響本主張的可信度。",
        "viewpoints": "",
    }
    assert U(contradiction), "狀態說有證據、分析說無關 → 應視為 unrelated"

    # 正常升級：狀態與分析一致 → 不視為無關（否則真命中會被誤殺）
    aligned = {
        "evidence_state": "full_body_evidence",
        "analysis": "Cofacts 查核指出衛福部明確表示無醫學研究證實，與主張直接矛盾。",
        "viewpoints": "官方與查核機構一致。",
    }
    assert not U(aligned), "狀態與分析一致時不該覆寫"

    # 直接判無關（原本的行為）
    assert U({"evidence_state": "unrelated_evidence", "analysis": ""})
    assert U({"evidence_state": "search_hit_body_missing", "analysis": ""}) is False
    assert U(None) is False
    assert U("不是 dict") is False

    print("ALL PASS — LLM 狀態欄與分析矛盾時以分析為準")


if __name__ == "__main__":
    demo()
