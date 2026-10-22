#!/usr/bin/env python3
"""
build_multilingual_scenarios.py
由 scenarios.json 派生出 100% 全日語 (scenarios_ja.json) 與 100% 全英語 (scenarios_en.json) 之情境設定檔。
讓錄製出來的畫面在日文版為純日語 UI 與解說，英文版為純英語 UI 與解說。
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "demo"
src = json.loads((BASE / "scenarios.json").read_text(encoding="utf-8"))

# ==========================================
# 1. 日文版設定 (scenarios_ja.json)
# ==========================================
ja_scenarios = json.loads(json.dumps(src))
for s in ja_scenarios:
    s["lang"] = "ja"
    if "initial" in s:
        s["initial"]["lang"] = "ja"

# 情境 1
ja_scenarios[0]["title"] = "シナリオ1：主要メディアによる報道の分析 (Mainstream Corroboration)"
ja_scenarios[0]["description"] = "公共放送や通信社のニュースを入力し、複数メディアの相互検証とドメイン信頼性を計算します。"
ja_scenarios[0]["briefing_points"] = [
    "主要メディアドメイン (pts.org.tw / nhk.or.jp) の信頼性スコアリング",
    "通信社・独立メディアによる相互検証 (CNA / 共同通信) の一致確認",
    "修辞リスク D4 の評価と透明性の高いスコアリングパイプライン"
]
for step in ja_scenarios[0]["steps"]:
    if "hint" in step:
        step["hint"] = step["hint"].replace("步驟 1：輸入欲分析的主流新聞網址", "ステップ 1：分析対象の主要ニュースURLを入力").replace("步驟 2：點擊「開始分析」啟動多模態判讀管線", "ステップ 2：「分析開始」をクリックしてマルチモーダル検証を起動").replace("步驟 3：檢視 D1~D4 四維度正交分析矩陣", "ステップ 3：D1〜D4の4つの直交指標マトリクスを確認").replace("步驟 4：檢視透明計分管線（加權融合與安全上限）", "ステップ 4：透明なスコアリングパイプラインを確認")

# 情境 2
ja_scenarios[1]["title"] = "シナリオ2：クリックベイト見出しの抑制とファクト復元 (Clickbait Interception)"
ja_scenarios[1]["description"] = "煽り・情報隠蔽型の釣り見出しを検知し、自動で減点して客観的な事実主張を復元します。"
ja_scenarios[1]["briefing_points"] = [
    "高サスペンス・情報隠蔽型見出しの検知",
    "LLM による客観的で中立な真の主張の自動復元",
    "D3 減点ペナルティによる過度な高信頼性の抑制"
]
for step in ja_scenarios[1]["steps"]:
    if "hint" in step:
        step["hint"] = step["hint"].replace("步驟 1：輸入典型的釣魚懸念標題新聞", "ステップ 1：典型的な煽り釣り見出しを入力").replace("步驟 2：點擊開始分析", "ステップ 2：分析開始をクリック").replace("步驟 3：檢視「真實主旨還原卡片」與扣分原因", "ステップ 3：「真の主張復元カード」と減点理由を確認").replace("步驟 4：檢視 D3 標題忠實度扣分", "ステップ 4：D3見出し忠実度の減点を確認")

# 情境 3
ja_scenarios[2]["title"] = "シナリオ3：SNSの偽情報とBotアカウントのフィルタリング (Social Disinformation Routing)"
ja_scenarios[2]["description"] = "警戒リストに登録されたアカウントによる組織的プロパガンダを検知し、裏付けスコアを強制的に無効化します。"
ja_scenarios[2]["briefing_points"] = [
    "ソーシャルブラックリストによる高リスクアカウントの特定",
    "D2 相互検証スコアの強制ゼロ化（0.00 固定）",
    "D4 修辞リスクによる扇動的プロパガンダ検知"
]
for step in ja_scenarios[2]["steps"]:
    if "hint" in step:
        step["hint"] = step["hint"].replace("步驟 1：輸入被列入黑名單的 X (Twitter) 帳號貼文內容", "ステップ 1：警戒リストに登録されたX投稿URLを入力").replace("步驟 2：點擊分析，透過 FixTweet 快速抓取與黑名單核對", "ステップ 2：分析をクリックしブラックリストと照合").replace("步驟 3：檢視 D2 判定為「高風險造謠／機器人帳號黑名單」", "ステップ 3：D2「高リスク・Botアカウント警戒リスト」判定を確認")

# 情境 4
ja_scenarios[3]["title"] = "シナリオ4：多言語による実ニュースの検証 (Multilingual Real News)"
ja_scenarios[3]["description"] = "日本語、英語、繁体字中国語の完全ローカライズと即時UI切り替えを実証します。"
ja_scenarios[3]["briefing_points"] = [
    "リアルタイム多言語UI切り替え (日本語 / English / 繁中)",
    "D1〜D4の定義・判定境界の完全現地語化",
    "国際通信社 (ロイター・共同通信・AP) の自動裏付け検証"
]

(BASE / "scenarios_ja.json").write_text(json.dumps(ja_scenarios, ensure_ascii=False, indent=2), encoding="utf-8")
print("✅ 生成完成: demo/scenarios_ja.json")

# ==========================================
# 2. 英文版設定 (scenarios_en.json)
# ==========================================
en_scenarios = json.loads(json.dumps(src))
for s in en_scenarios:
    s["lang"] = "en"
    if "initial" in s:
        s["initial"]["lang"] = "en"

# Scenario 1
en_scenarios[0]["title"] = "Scenario 1: Mainstream News Corroboration"
en_scenarios[0]["description"] = "Analyzes a mainstream news report with cross-source corroboration and domain credibility weighting."
en_scenarios[0]["briefing_points"] = [
    "Mainstream publisher domain reputation weighting",
    "Cross-source multi-outlet corroboration verification (CNA / UDN)",
    "Rhetorical risk evaluation and transparent scoring pipeline"
]
for step in en_scenarios[0]["steps"]:
    if "hint" in step:
        step["hint"] = step["hint"].replace("步驟 1：輸入欲分析的主流新聞網址", "Step 1: Enter mainstream news report URL").replace("步驟 2：點擊「開始分析」啟動多模態判讀管線", "Step 2: Click Start Analysis to initiate multi-modal pipeline").replace("步驟 3：檢視 D1~D4 四維度正交分析矩陣", "Step 3: Review D1-D4 orthogonal dimension matrix").replace("步驟 4：檢視透明計分管線（加權融合與安全上限）", "Step 4: Review transparent scoring pipeline")

# Scenario 2
en_scenarios[1]["title"] = "Scenario 2: Clickbait Title Suppression & Claim Restoration"
en_scenarios[1]["description"] = "Detects suspense-driven clickbait headlines, penalizes deception, and extracts objective claims."
en_scenarios[1]["briefing_points"] = [
    "High-suspense and clickbait headline detection",
    "Automated factual objective claim restoration via local LLM",
    "Dimension 3 fidelity penalty enforcement"
]
for step in en_scenarios[1]["steps"]:
    if "hint" in step:
        step["hint"] = step["hint"].replace("步驟 1：輸入典型的釣魚懸念標題新聞", "Step 1: Enter typical sensational clickbait title").replace("步驟 2：點擊開始分析", "Step 2: Click Start Analysis").replace("步驟 3：檢視「真實主旨還原卡片」與扣分原因", "Step 3: Inspect Restored Claim card & penalty rationale").replace("步驟 4：檢視 D3 標題忠實度扣分", "Step 4: Verify D3 headline fidelity penalty")

# Scenario 3
en_scenarios[2]["title"] = "Scenario 3: Social Media Disinformation & Bot Blacklist"
en_scenarios[2]["description"] = "Intercepts coordinated malicious propaganda accounts and enforces social blocklists."
en_scenarios[2]["briefing_points"] = [
    "High-risk account identification via social blocklist",
    "Dimension 2 corroboration score forced to zero (0.00)",
    "Dimension 4 rhetorical risk detection for partisan propaganda"
]
for step in en_scenarios[2]["steps"]:
    if "hint" in step:
        step["hint"] = step["hint"].replace("步驟 1：輸入被列入黑名單的 X (Twitter) 帳號貼文內容", "Step 1: Enter flagged high-risk X account post URL").replace("步驟 2：點擊分析，透過 FixTweet 快速抓取與黑名單核對", "Step 2: Click Analyze to match against blocklist").replace("步驟 3：檢視 D2 判定為「高風險造謠／機器人帳號黑名單」", "Step 3: Confirm D2 flagged as High-Risk Disinformation Account")

# Scenario 4
en_scenarios[3]["title"] = "Scenario 4: Multilingual Real News Verification"
en_scenarios[3]["description"] = "Demonstrates real-time multilingual UI and prompt localization across JA, EN, and ZH."
en_scenarios[3]["briefing_points"] = [
    "Seamless real-time multilingual UI switching (Japanese / English / Chinese)",
    "Complete localization of D1-D4 dimension definitions and boundaries",
    "Automated cross-source validation from Reuters, AP, and Kyodo News"
]

(BASE / "scenarios_en.json").write_text(json.dumps(en_scenarios, ensure_ascii=False, indent=2), encoding="utf-8")
print("✅ 生成完成: demo/scenarios_en.json")
