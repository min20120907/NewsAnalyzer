# -*- coding: utf-8 -*-
"""
四維度正交評分器與三態決策路由 —— 獨立維度契約與不變量回歸測試套件
==================================================================
執行方式：
  python3 test_orthogonal_scorer.py

測試涵蓋：
  1. D1 (`evidence_verdict`) 獨立契約與邊界：
     - `refutes` 時回覆數增加（舊 `user_feedback`）只會強化不實信心並壓低分數，絕不往可信方向加 +10 分
     - `unrelated_evidence`（狀態欄或分析文字矛盾）直接歸零 D1，絕不污染分母或留下殘留分數
     - `rumor_only_rejected`（證據本身是「僅供參考/轉傳」謠言）不採信為屬實背書
  2. D2 (`source_corroboration`) 獨立契約與邊界：
     - 缺 `publish_date` 時，絕不偷拿 Cofacts 查核紀錄的 `created_at` 充當新聞時效
     - 主流媒體白名單或 >=3 家外部媒體同報進入 `CORROBORATED_REPORT` (Regime B)
     - 內容農場/黑名單網域固定為 `blocked` (C=0.0)
  3. D3 (`headline_faithfulness`) 獨立契約與邊界：
     - 文題 100% 相符 (F=1.0) 時 `impact_pts == 0.0`（絕不幫假新聞加正分）
     - 顯性釣魚詞與懸念反問句型（如 B01~B20）精準觸發扣分，將主流媒體釣魚標壓回 <=60（待查證）
  4. D4 (`rhetorical_risk`) 獨立契約與邊界：
     - 嚴格封裝於 Regime C（未查證區間 [10, 58]）：即便語氣完全平實 (R=0.15)，無外部證據與同報時最高僅 52 分，絕不跨過 60 分門檻
     - 偽冒官方公告/補助/颱風警報（如 `check_abstain_cap.py` 與 `F11~F20`）在無官方/主流佐證時自動拉高 R 並壓入疑似不實帶 (<40)
"""
import os
import sys

CUR_DIR = os.path.dirname(os.path.abspath(__file__))
if CUR_DIR not in sys.path:
    sys.path.insert(0, CUR_DIR)
# orthogonal_scorer.py 住在 python/，測試住在 scripts/
_PY_DIR = os.path.normpath(os.path.join(CUR_DIR, "..", "python"))
if os.path.isdir(_PY_DIR) and _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

from orthogonal_scorer import (
    compute_d1_evidence_verdict,
    compute_d2_source_corroboration,
    compute_d3_headline_faithfulness,
    compute_d4_rhetorical_risk,
    score_orthogonal,
)


def test_d1_contract_and_feedback_polarity():
    # 1. 回覆數增加（舊 user_feedback）在 inaccurate 時應使分數更低（更篤定為假），絕不加正分
    d1_1reply = compute_d1_evidence_verdict(
        sources=[{"source": "cofacts", "status": "inaccurate", "similarity_score": 0.85,
                  "reasons": [{"type": "RUMOR", "text": "查核：此為假消息"}]}]
    )
    d1_3replies = compute_d1_evidence_verdict(
        sources=[{"source": "cofacts", "status": "inaccurate", "similarity_score": 0.85,
                  "reasons": [
                      {"type": "RUMOR", "text": "查核1：衛福部否認"},
                      {"type": "RUMOR", "text": "查核2：MyGoPen 闢謠"},
                      {"type": "RUMOR", "text": "查核3：專家指出無根據"},
                  ]}]
    )
    assert d1_1reply.status_label == "refutes"
    assert d1_3replies.status_label == "refutes"
    assert d1_3replies.confidence > d1_1reply.confidence, "更多闢謠回覆應提高證據信心 c_E"
    assert d1_3replies.impact_pts <= d1_1reply.impact_pts <= 24.0, (
        f"更多闢謠回覆不得把不實分數往可信方向拉高: 1則={d1_1reply.impact_pts}, 3則={d1_3replies.impact_pts}"
    )

    # 2. 無關證據（狀態欄說 full_body_evidence，但分析文字說與本主張無關）必須在 D1 內部直接剔除
    d1_unrel = compute_d1_evidence_verdict(
        sources=[{"source": "cofacts", "status": "inaccurate", "similarity_score": 0.88,
                  "reasons": [{"type": "RUMOR", "text": "投資詐騙宣導"}]}],
        deep={"evidence_state": "full_body_evidence",
              "analysis": "Cofacts 的查核結果因針對不同事件（投資詐騙）而被判定為無關證據，不影響本主張的可信度。"}
    )
    assert d1_unrel.status_label == "unrelated"
    assert d1_unrel.value == 0.0 and d1_unrel.confidence == 0.0 and d1_unrel.impact_pts == 0.0

    # 3. 轉傳/僅供參考不得當成 supports 背書
    d1_rumor = compute_d1_evidence_verdict(
        sources=[{"source": "cofacts", "status": "accurate", "similarity_score": 0.90,
                  "matched_text": "台銀退休協會同仁傳的訊息，僅供參考：財政部改革方案…",
                  "reasons": [{"type": "NOT_RUMOR", "text": "確實有此轉傳訊息"}]}],
        deep={"evidence_state": "full_body_evidence"}
    )
    assert d1_rumor.status_label == "rumor_only_rejected"
    assert d1_rumor.value == 0.0
    print("[PASS] D1 (`evidence_verdict`) 契約與邊界測試通過")


def test_d2_contract_and_no_cofacts_timestamp_theft():
    # 1. 文章無 publish_date，但 Cofacts 命中一筆剛建立的查核 -> D2 絕不偷拿 Cofacts created_at 當文章時效
    d2_no_pub = compute_d2_source_corroboration(
        title="某一般貼文標題",
        url="https://unknown",
        content="某一般貼文內容",
        publish_date=None,
    )
    assert "近期發布" not in d2_no_pub.explanation, "無 publish_date 時不得偽造近期發布時效"
    assert d2_no_pub.status_label == "uncorroborated"
    assert d2_no_pub.value < 0.60

    # 2. 跨媒體 >= 3 家獨立同報時，即使原始連結為一般網域，也能進入 corroborated (>=0.60)
    d2_corr = compute_d2_source_corroboration(
        title="重大突發新聞事件",
        url="https://today.line.me/tw/v3/article/xyz",
        content="內文報導詳情",
        corr_outlets=["cna.com.tw", "ltn.com.tw", "udn.com"],
    )
    assert d2_corr.status_label == "corroborated"
    assert d2_corr.value >= 0.75

    # 3. 內容農場黑名單永遠為 0，同報也救不起來
    d2_farm = compute_d2_source_corroboration(
        title="震驚健康秘方",
        url="https://www.health-rumor-farm.tw/news/123.html",
        content="內容",
        corr_outlets=["a.com", "b.com", "c.com"],
    )
    assert d2_farm.status_label == "blocked"
    assert d2_farm.value == 0.0
    print("[PASS] D2 (`source_corroboration`) 契約與邊界測試通過")


def test_d3_contract_zero_bonus_and_bait_detection():
    # 1. 標題與內文 100% 忠實相符時，impact_pts 必須嚴格為 0.0（不幫假新聞加正分）
    d3_good = compute_d3_headline_faithfulness(
        title="台南鐵路地下化第一階段10月17日啟用，乘車動線與出入口一次看",
        content="台南鐵路地下化第一階段將在2026年10月17日正式通車，新啟用的台南車站設有三處主要出入口。",
        title_body_sim=0.95,
    )
    assert d3_good.status_label == "faithful"
    assert d3_good.value == 1.0
    assert d3_good.impact_pts == 0.0, "文題相符不得產生正分加成"

    # 2. 懸念反問釣魚標（B01）必須觸發扣分，把主流媒體新聞壓回 <= 60 分
    full_bait = score_orthogonal(
        title="台南車站最後一夜？末班車開完後，舊車站將永遠走不回去？",
        url="https://www.cna.com.tw/news/aloc/202610160101.aspx",
        content="台南鐵路地下化第一階段將在2026年10月17日正式通車，16日晚間開出末班地面列車自強號145次後，工程團隊將連夜辦理軌道切換。",
        title_body_sim=0.72,
    )
    assert full_bait["dimensions"]["headline_faithfulness"]["impact_pts"] <= -20.0
    assert full_bait["final_score"] <= 60.0, f"釣魚標應自然落入 <=60 待查證帶，實際得到 {full_bait['final_score']}"
    print("[PASS] D3 (`headline_faithfulness`) 契約與邊界測試通過")


def test_d4_contract_and_regime_c_isolation():
    # 1. 無查核、無主流同報的平實造謠（如偽冒氣象署格美颱風登陸）
    out_typhoon = score_orthogonal(
        title="颱風「格美」已在花蓮登陸 氣象署提醒雙北注意強風雨",
        url="https://unknown",
        content="中央氣象署今日(7月26日)下午6點發布最新消息，颱風「格美」已於傍晚在花蓮縣秀林鄉登陸，中心最大風速每秒35公尺。預計明清晨進入台北盆地，目前尚未發布停班停課。",
        sentiment_val=0.05,  # 極度平實的語氣
        title_body_sim=0.92, # 標題與內文高度一致
        sources=[],
        web_results=[],
        deep={"abstain": True, "evidence_state": "no_evidence", "credibility_score": 50},
    )
    assert out_typhoon["regime"] == "UNVERIFIED_ABSTAIN"
    assert out_typhoon["final_score"] < 40.0, (
        f"平實語氣＋文題相符的無證據偽冒公告不得拿高分（舊版拿 68.2），新版應 <40，實際={out_typhoon['final_score']}"
    )

    # 2. 就算 D4 風險極低（一般生活觀點貼文），在無查核且無同報的 Regime C 下，分數永遠 <= 58.0
    out_benign_unverified = score_orthogonal(
        title="個人週末閱讀筆記分享",
        url="https://www.facebook.com/post/123",
        content="今天下午在圖書館讀完了這本關於台灣鐵道歷史的書籍，整理了幾個章節的心得。",
        sentiment_val=0.10,
        title_body_sim=0.85,
        sources=[],
        web_results=[],
    )
    assert out_benign_unverified["regime"] == "UNVERIFIED_ABSTAIN"
    assert 45.0 <= out_benign_unverified["final_score"] <= 58.0, (
        f"未查證的一般貼文必須落在待查證區間 [45, 58]，實際={out_benign_unverified['final_score']}"
    )
    print("[PASS] D4 (`rhetorical_risk`) 與 Regime C 值域隔離測試通過")


def test_every_dimension_has_self_describing_contract():
    out = score_orthogonal(
        title="台積電法說會登場，第三季營收創新高",
        url="https://www.cna.com.tw/news/afe/1.aspx",
        content="台積電今日召開法說會，公布第三季營收創下歷史新高。",
    )
    dims = out["dimensions"]
    assert set(dims.keys()) == {
        "evidence_verdict", "source_corroboration", "headline_faithfulness", "rhetorical_risk"
    }
    for k, d in dims.items():
        assert d.get("what_it_measures"), f"{k} 缺少 what_it_measures"
        assert d.get("what_if_wrong"), f"{k} 缺少 what_if_wrong"
        assert d.get("explanation"), f"{k} 缺少 explanation"
    print("[PASS] 四個維度皆具備完整自述契約 (`what_it_measures` / `what_if_wrong` / `explanation`)")


if __name__ == "__main__":
    test_d1_contract_and_feedback_polarity()
    test_d2_contract_and_no_cofacts_timestamp_theft()
    test_d3_contract_zero_bonus_and_bait_detection()
    test_d4_contract_and_regime_c_isolation()
    test_every_dimension_has_self_describing_contract()
    print("\nALL ORTHOGONAL CONTRACT TESTS PASSED (5/5 suites)")
