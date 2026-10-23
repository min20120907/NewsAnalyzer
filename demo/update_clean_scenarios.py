#!/usr/bin/env python3
"""
Fix all Chinese text in scenarios_ja.json and scenarios_en.json
Ensures 100% pure localized content (typed inputs, mock results, Qwen deep analysis, cards).
"""
import json
from pathlib import Path

BASE = Path("/home/min20120907/Documents/Web_and_App_Development/NewsAnalyzer/demo")

# ==============================================================================
# JAPANESE SCENARIOS
# ==============================================================================
ja_scenarios = [
    {
        "id": "scenario_1",
        "title": "シナリオ1：主要メディアによる報道の分析 (Mainstream Corroboration)",
        "description": "公共放送の報道URLを入力し、四直交指標とローカルAIモデルによる高信頼性評価を検証します。",
        "briefing_points": [
            "主要公共放送（NHK）の報道URLを入力",
            "ファクトチェック照合・複数メディア相互検証の実行",
            "ローカルQwenモデルによる95点の高信頼性判定"
        ],
        "lang": "ja",
        "initial": {"url": ""},
        "steps": [
            {"action": "spotlight", "target": "#newsUrl", "duration": 800, "delay": 200},
            {
                "action": "type",
                "target": "#newsUrl",
                "value": "【NHKニュース】能登半島地震の復旧進捗 内閣府：仮設住宅の建設は11月までに完了予定。内閣府の担当者は、復旧工事が順調に進んでおり、被災者の入居を予定通り進めると述べた。https://www3.nhk.or.jp/news/article/20240901.html",
                "delay": 300
            },
            {"action": "spotlight", "target": "#analyzeBtn", "duration": 500, "delay": 200},
            {"action": "click", "target": "#analyzeBtn", "delay": 100},
            {"action": "wait_for", "target": "#resultsSection", "timeout": 8000, "delay": 1500},
            {
                "action": "explainer",
                "title": "総合スコア：89点（高信頼性）",
                "body": "NHKの公式報道に基づき、複数メディア（共同通信・時事通信）との裏付け一致を確認。D1虚偽なし、D2相互検証88点を記録。",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            },
            {"action": "scroll_to", "target": "#evidenceVerdictCard", "delay": 300},
            {
                "action": "explainer",
                "title": "D1 & D2：ファクト照合と相互検証",
                "body": "D1で既存の偽情報データベースと照合し反証なし。D2で他社報道の一致度を検証し、高い事実性を確立。",
                "position": "bottom-right",
                "duration": 3000,
                "delay": 200
            },
            {
                "action": "explainer",
                "title": "D3 & D4：見出し忠実度と修辞リスク",
                "body": "D3見出し忠実度92点（誇張なし）、D4修辞リスク0.08（客観的報道）を確認。",
                "position": "bottom-right",
                "duration": 3000,
                "delay": 200
            },
            {"action": "scroll_to", "target": "#deepAnalysisCard", "delay": 400},
            {
                "action": "explainer",
                "title": "ローカルLLM深度分析（95点）",
                "body": "本機で稼働するQwenモデルが独立検証を行い、95点の高評価と客観的な論拠を出力。",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 300
            }
        ],
        "expected": {"overall_min": 85, "verdict": "高信頼性"},
        "mock_result": {
            "title": "能登半島地震の復旧進捗 内閣府：仮設住宅の建設は11月までに完了予定",
            "url": "https://www3.nhk.or.jp/news/article/20240901.html",
            "credibility_score": 89,
            "rule_score": 85,
            "llm_score": 95,
            "overall_score": 88.5,
            "rating": "高信頼性",
            "confidence": 0.92,
            "domain_weight": 0.3,
            "corroboration_score": 88,
            "cross_source_count": 2,
            "scoring_basis": "ルーティング B（主要メディア／複数社による裏付け報道）：公共放送メディア (nhk.or.jp) ＋ 署名入り情報源確認｜2社による同時報道（共同通信, 時事通信）｜最近の報道（裏付けスコア 0.88）",
            "scoring_route": "B",
            "source_reputation": "公共放送・主要メディア",
            "dimensions": {
                "evidence_verdict": {
                    "id": "D1",
                    "key": "evidence_verdict",
                    "name": "ファクトチェック照合",
                    "value": 0.0,
                    "confidence": 0.95,
                    "verdict": "verified_safe",
                    "label": "虚偽情報・反証の記録なし",
                    "badge_color": "green",
                    "penalty": 0.0,
                    "desc": "ファクトチェック機関のデータベースと照合し、虚偽や誤りの報告は確認されませんでした。"
                },
                "cross_corroboration": {
                    "id": "D2",
                    "key": "cross_corroboration",
                    "name": "複数メディア相互検証",
                    "value": 0.88,
                    "confidence": 0.92,
                    "verdict": "corroborated",
                    "label": "88%（複数社の一致報道あり）",
                    "badge_color": "green",
                    "penalty": 0.0,
                    "desc": "共同通信および時事通信による同一事実の同時報道を確認しました。"
                },
                "headline_fidelity": {
                    "id": "D3",
                    "key": "headline_fidelity",
                    "name": "見出し忠実度",
                    "value": 0.92,
                    "confidence": 0.95,
                    "verdict": "supported",
                    "label": "忠実度 92%（誇張なし）",
                    "badge_color": "green",
                    "penalty": 0.0,
                    "desc": "見出しと本文の内容が完全に一致しており、ミスリードは見られません。"
                },
                "rhetorical_risk": {
                    "id": "D4",
                    "key": "rhetorical_risk",
                    "name": "修辞リスク評価",
                    "value": 0.08,
                    "confidence": 0.95,
                    "verdict": "objective",
                    "label": "リスク 0.08（極めて客観的）",
                    "badge_color": "green",
                    "penalty": 0.0,
                    "desc": "感情的扇動や主観的な表現は含まれず、事実に基づいた冷静な記述です。"
                }
            },
            "metrics": {
                "sentiment": {"score": 14.0, "desc": "修辞安全性 92%（リスク R=0.08）", "weight": 15},
                "domain": {"score": 24.0, "desc": "主要報道機関ドメイン nhk.or.jp", "weight": 25},
                "tfc": {"score": 20.0, "desc": "ファクトチェック照合完了（反証なし）", "weight": 20},
                "corroboration": {"score": 30.5, "desc": "共同通信・時事通信の一致報道を確認", "weight": 40}
            },
            "deep_analysis": {
                "claim": "内閣府が能登半島地震の仮設住宅を11月までに完成予定と発表",
                "key_points": [
                    "内閣府担当者が被災地を視察",
                    "予定通り11月に被災者へ引き渡し予定"
                ],
                "viewpoints": ["行政による公式発表と復旧スケジュールの確認"],
                "evidence_strength": "十分な裏付けあり",
                "fallacies": "論理的誤謬なし",
                "llm_score": 95,
                "overall_verdict": "信頼性の高い公式事実報道",
                "summary": "主要メディアによる公式発表の取材報道であり、論理構成および客観性に優れ、高い信頼性が担保されています。"
            }
        }
    },
    {
        "id": "scenario_2",
        "title": "シナリオ2：クリックベイト見出しの抑制とファクト復元 (Clickbait Interception)",
        "description": "誇張された釣り見出しを検知し、見出しペナルティの適用とAIによる事実復元カードを表示します。",
        "briefing_points": [
            "典型的な煽り見出し（クリックベイト）を入力",
            "見出し忠実度乖離による -18 点ペナルティの発動",
            "AI真の主張復元カードによる客観的事実の提示"
        ],
        "lang": "ja",
        "initial": {"url": ""},
        "steps": [
            {"action": "spotlight", "target": "#newsUrl", "duration": 800, "delay": 200},
            {
                "action": "type",
                "target": "#newsUrl",
                "value": "毎日これを飲むと命の危機！？名医が明かす驚きの真相！ネット騒然：もう二度と飲めない…健康情報まとめブログ https://health-buzz-summary.jp/archives/12345",
                "delay": 300
            },
            {"action": "spotlight", "target": "#analyzeBtn", "duration": 500, "delay": 200},
            {"action": "click", "target": "#analyzeBtn", "delay": 100},
            {"action": "wait_for", "target": "#resultsSection", "timeout": 8000, "delay": 1500},
            {
                "action": "explainer",
                "title": "真の主張復元カード",
                "body": "AIが見出しの煽り文句を排除し、「過度なカフェイン摂取への注意喚起」という客観的な事実を瞬時に要約・提示します。",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            },
            {"action": "scroll_to", "target": "#headlineFidelityCard", "delay": 300},
            {
                "action": "explainer",
                "title": "D3 見出し忠実度のペナルティ (-18点)",
                "body": "見出しと本文の重大な乖離（D3=0.32）を検出し、18点の減点ペナルティを課して45点（要検証）へ抑制。",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            }
        ],
        "expected": {"overall_max": 50, "verdict": "要検証"},
        "mock_result": {
            "title": "毎日これを飲むと命の危機！？名医が明かす驚きの真相！ネット騒然：もう二度と飲めない",
            "url": "https://health-buzz-summary.jp/archives/12345",
            "credibility_score": 45,
            "rule_score": 45,
            "llm_score": 45,
            "overall_score": 45.0,
            "rating": "要検証",
            "confidence": 0.88,
            "scoring_basis": "D3見出し忠実度の大幅な乖離を検出（ペナルティ -18点）｜まとめサイト判定・裏付け報道なし",
            "clickbait_analysis": {
                "is_clickbait": True,
                "penalty": -18,
                "restored_claim": "過度なカフェイン摂取に関する健康上の注意喚起であり、適量であれば致命的な健康被害を及ぼす根拠はない。",
                "original_title": "毎日これを飲むと命の危機！？名医が明かす驚きの真相！ネット騒然：もう二度と飲めない",
                "neutral_title": "医師によるカフェイン摂取量の目安と健康への影響解説"
            },
            "dimensions": {
                "headline_fidelity": {
                    "id": "D3",
                    "key": "headline_fidelity",
                    "name": "見出し忠実度",
                    "value": 0.32,
                    "confidence": 0.90,
                    "verdict": "clickbait_suppressed",
                    "label": "忠実度 32%（誇張ペナルティ -18点）",
                    "badge_color": "yellow",
                    "penalty": -18.0,
                    "desc": "煽り見出しと本文の内容に顕著な乖離があり、クリック誘導と判定されました。"
                }
            },
            "deep_analysis": {
                "claim": "特定飲料の日常的摂取が即座に生命の危機につながるという主張",
                "key_points": ["極端な過剰摂取時のリスクを日常摂取にすり替えている"],
                "fallacies": "恐怖心煽動・過度の一般化",
                "llm_score": 45,
                "overall_verdict": "典型的なクリックベイト記事"
            }
        }
    },
    {
        "id": "scenario_3",
        "title": "シナリオ3：SNSの偽情報とBotアカウントのフィルタリング (Social Disinformation Routing)",
        "description": "ソーシャルブラックリストに登録されたアカウントを検知し、裏付けスコアを強制ゼロ化します。",
        "briefing_points": [
            "要注意Xアカウントの投稿URLを入力",
            "ソーシャルブラックリスト強制ヒット（D2スコア=0）",
            "修辞リスク急上昇（D4=0.70）による25点（極めて疑わしい）判定"
        ],
        "lang": "ja",
        "initial": {"url": ""},
        "steps": [
            {"action": "spotlight", "target": "#newsUrl", "duration": 800, "delay": 200},
            {
                "action": "type",
                "target": "#newsUrl",
                "value": "https://x.com/suspicious_bot_net/status/1839201928374",
                "delay": 300
            },
            {"action": "spotlight", "target": "#analyzeBtn", "duration": 500, "delay": 200},
            {"action": "click", "target": "#analyzeBtn", "delay": 100},
            {"action": "wait_for", "target": "#resultsSection", "timeout": 8000, "delay": 1500},
            {
                "action": "explainer",
                "title": "ソーシャルブラックリスト検知",
                "body": "監視対象のBotネットワークに即座に一致。D2の相互検証スコアは無条件で 0 に固定されます。",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            },
            {"action": "scroll_to", "target": "#rhetoricalRiskCard", "delay": 300},
            {
                "action": "explainer",
                "title": "修辞リスク高（R=0.70）",
                "body": "煽動的な語彙や世論操作の特徴を検知。総合信頼性スコアは 25点（極めて疑わしい）へ抑え込まれます。",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            }
        ],
        "expected": {"overall_max": 30, "verdict": "極めて疑わしい"},
        "mock_result": {
            "title": "@suspicious_bot_net による X (Twitter) 投稿",
            "url": "https://x.com/suspicious_bot_net/status/1839201928374",
            "credibility_score": 25,
            "rule_score": 25,
            "llm_score": 25,
            "overall_score": 25.0,
            "rating": "極めて疑わしい",
            "confidence": 0.95,
            "scoring_basis": "ソーシャルブラックリスト検知（D2強制ゼロ固定）｜煽動的修辞リスク高（R=0.70）",
            "dimensions": {
                "cross_corroboration": {
                    "id": "D2",
                    "key": "cross_corroboration",
                    "name": "複数メディア相互検証",
                    "value": 0.0,
                    "confidence": 0.99,
                    "verdict": "blacklisted",
                    "label": "ブラックリスト検知（0点固定）",
                    "badge_color": "red",
                    "penalty": -40.0,
                    "desc": "要注意アカウントに該当するため、信頼性検証スコアは無条件でゼロとなります。"
                },
                "rhetorical_risk": {
                    "id": "D4",
                    "key": "rhetorical_risk",
                    "name": "修辞リスク評価",
                    "value": 0.70,
                    "confidence": 0.92,
                    "verdict": "high_risk",
                    "label": "修辞リスク 0.70（感情的煽動）",
                    "badge_color": "red",
                    "penalty": -20.0,
                    "desc": "敵対的感情や世論分断を意図した扇動的な表現が多数検出されました。"
                }
            },
            "deep_analysis": {
                "claim": "特定組織に対する根拠不明な陰謀的主張",
                "evidence_strength": "根拠なし",
                "llm_score": 25,
                "overall_verdict": "協調的世論操作の疑いが極めて高い"
            }
        }
    },
    {
        "id": "scenario_4",
        "title": "シナリオ4：多言語による実ニュースの検証 (Multilingual Real News)",
        "description": "国際ニュース通信社（ロイター通信）の実報道を分析し、グローバル報道の相互検証を確認します。",
        "briefing_points": [
            "ロイター通信の最新テクノロジー報道URLを入力",
            "ブルームバーグ・AP通信との国際相互検証（88点）",
            "ローカルAIによる多言語深度分析サマリーの出力"
        ],
        "lang": "ja",
        "initial": {"url": ""},
        "steps": [
            {"action": "spotlight", "target": "#newsUrl", "duration": 800, "delay": 200},
            {
                "action": "type",
                "target": "#newsUrl",
                "value": "https://jp.reuters.com/technology/article/semiconductor-supply-chain-2024",
                "delay": 300
            },
            {"action": "spotlight", "target": "#analyzeBtn", "duration": 500, "delay": 200},
            {"action": "click", "target": "#analyzeBtn", "delay": 100},
            {"action": "wait_for", "target": "#resultsSection", "timeout": 8000, "delay": 1500},
            {
                "action": "explainer",
                "title": "国際報道の相互検証：88点",
                "body": "ブルームバーグやAP通信との同時報道を自動照合し、88点の高信頼性を確認。",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            },
            {"action": "scroll_to", "target": "#deepAnalysisCard", "delay": 300},
            {
                "action": "explainer",
                "title": "多言語AI推論完了",
                "body": "多言語環境下でも日本語UIとローカルモデルがシームレスに機能し、信頼できるファクトチェックを実現します。",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 300
            }
        ],
        "expected": {"overall_min": 85, "verdict": "高信頼性"},
        "mock_result": {
            "title": "ロイター：半導体サプライチェーンの最新動向と投資拡大",
            "url": "https://jp.reuters.com/technology/article/semiconductor-supply-chain-2024",
            "credibility_score": 88,
            "overall_score": 88.0,
            "rating": "高信頼性",
            "scoring_basis": "国際通信社 (Reuters) ＋ ブルームバーグ・AP通信との国際相互検証確認",
            "dimensions": {
                "cross_corroboration": {
                    "id": "D2",
                    "key": "cross_corroboration",
                    "name": "複数メディア相互検証",
                    "value": 0.88,
                    "confidence": 0.94,
                    "verdict": "corroborated",
                    "label": "88%（ブルームバーグ等の一致報道あり）",
                    "badge_color": "green",
                    "penalty": 0.0,
                    "desc": "主要海外通信社による同一事実の同時報道を確認しました。"
                }
            },
            "deep_analysis": {
                "claim": "半導体業界におけるサプライチェーン強化と国際的投資の動向",
                "llm_score": 92,
                "overall_verdict": "国際的に検証された高信頼性報道"
            }
        }
    }
]

# ==============================================================================
# ENGLISH SCENARIOS
# ==============================================================================
en_scenarios = [
    {
        "id": "scenario_1",
        "title": "Scenario 1: Mainstream News Corroboration",
        "description": "Enter a public broadcast report URL to verify high credibility scores across four orthogonal dimensions and local AI reasoning.",
        "briefing_points": [
            "Input public broadcast news report URL (PBS / BBC / AP)",
            "Execute fact-check entailment & cross-source corroboration",
            "Local Qwen model awards 95-point high credibility rating"
        ],
        "lang": "en",
        "initial": {"url": ""},
        "steps": [
            {"action": "spotlight", "target": "#newsUrl", "duration": 800, "delay": 200},
            {
                "action": "type",
                "target": "#newsUrl",
                "value": "【PBS NewsHour】Infrastructure Rebuild Progress: Officials announce modular housing completed by November. Federal authorities report smooth progress with disaster relief efforts proceeding on schedule. https://www.pbs.org/newshour/nation/infrastructure-rebuild-update-2024",
                "delay": 300
            },
            {"action": "spotlight", "target": "#analyzeBtn", "duration": 500, "delay": 200},
            {"action": "click", "target": "#analyzeBtn", "delay": 100},
            {"action": "wait_for", "target": "#resultsSection", "timeout": 8000, "delay": 1500},
            {
                "action": "explainer",
                "title": "Overall Score: 89 (Highly Credible)",
                "body": "Based on public broadcasting sources, confirmed corroboration across AP and Reuters. D1 zero disputes, D2 corroboration 88 points.",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            },
            {"action": "scroll_to", "target": "#evidenceVerdictCard", "delay": 300},
            {
                "action": "explainer",
                "title": "D1 & D2: Fact Entailment & Corroboration",
                "body": "D1 matches against global fact-check databases with zero refutations. D2 corroborates multi-source consistency.",
                "position": "bottom-right",
                "duration": 3000,
                "delay": 200
            },
            {
                "action": "explainer",
                "title": "D3 & D4: Headline Fidelity & Rhetoric Risk",
                "body": "D3 headline fidelity scores 92 points (no clickbait), D4 rhetorical risk scores 0.08 (highly objective).",
                "position": "bottom-right",
                "duration": 3000,
                "delay": 200
            },
            {"action": "scroll_to", "target": "#deepAnalysisCard", "delay": 400},
            {
                "action": "explainer",
                "title": "Local LLM Deep Analysis (95 Points)",
                "body": "On-device Qwen model provides independent verification, scoring 95 points with transparent factual justification.",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 300
            }
        ],
        "expected": {"overall_min": 85, "verdict": "Highly Credible"},
        "mock_result": {
            "title": "Infrastructure Rebuild Progress: Modular Housing on Track for November",
            "url": "https://www.pbs.org/newshour/nation/infrastructure-rebuild-update-2024",
            "credibility_score": 89,
            "rule_score": 85,
            "llm_score": 95,
            "overall_score": 88.5,
            "rating": "Highly Credible",
            "confidence": 0.92,
            "domain_weight": 0.3,
            "corroboration_score": 88,
            "cross_source_count": 2,
            "scoring_basis": "Route B (Mainstream Source / Cross-source Corroboration): Named public broadcaster (pbs.org) + verified bylines | 2 independent outlets corroborated (AP, Reuters) | Corroboration index 0.88",
            "scoring_route": "B",
            "source_reputation": "Public Broadcaster / Mainstream News",
            "dimensions": {
                "evidence_verdict": {
                    "id": "D1",
                    "key": "evidence_verdict",
                    "name": "Fact-Check Entailment",
                    "value": 0.0,
                    "confidence": 0.95,
                    "verdict": "verified_safe",
                    "label": "Zero Disputes Found",
                    "badge_color": "green",
                    "penalty": 0.0,
                    "desc": "Cross-referenced against verified fact-checking registries; no conflicting claims or debunk alerts found."
                },
                "cross_corroboration": {
                    "id": "D2",
                    "key": "cross_corroboration",
                    "name": "Cross-Source Corroboration",
                    "value": 0.88,
                    "confidence": 0.92,
                    "verdict": "corroborated",
                    "label": "88% (Multiple Independent Outlets)",
                    "badge_color": "green",
                    "penalty": 0.0,
                    "desc": "AP News and Reuters independently corroborate key factual claims simultaneously."
                },
                "headline_fidelity": {
                    "id": "D3",
                    "key": "headline_fidelity",
                    "name": "Headline Fidelity",
                    "value": 0.92,
                    "confidence": 0.95,
                    "verdict": "supported",
                    "label": "Fidelity 92% (No Sensationalism)",
                    "badge_color": "green",
                    "penalty": 0.0,
                    "desc": "Headline aligns directly with core article claims without misleading hyperbole."
                },
                "rhetorical_risk": {
                    "id": "D4",
                    "key": "rhetorical_risk",
                    "name": "Rhetorical Risk",
                    "value": 0.08,
                    "confidence": 0.95,
                    "verdict": "objective",
                    "label": "Risk 0.08 (Highly Objective)",
                    "badge_color": "green",
                    "penalty": 0.0,
                    "desc": "Neutral, matter-of-fact journalistic tone with no emotional manipulation signals."
                }
            },
            "metrics": {
                "sentiment": {"score": 14.0, "desc": "Rhetorical Safety 92% (Risk R=0.08)", "weight": 15},
                "domain": {"score": 24.0, "desc": "Mainstream News Domain pbs.org", "weight": 25},
                "tfc": {"score": 20.0, "desc": "Fact-Check Registry Matched (Clean)", "weight": 20},
                "corroboration": {"score": 30.5, "desc": "AP & Reuters Corroboration Verified", "weight": 40}
            },
            "deep_analysis": {
                "claim": "Federal officials announce modular disaster housing on track for November completion",
                "key_points": [
                    "Officials inspected modular housing sites in disaster zones",
                    "Relief delivery proceeding on schedule for November move-in"
                ],
                "viewpoints": ["Official government administrative briefing and recovery timeline verification"],
                "evidence_strength": "Robust Cross-Corroborated Evidence",
                "fallacies": "No logical fallacies detected",
                "llm_score": 95,
                "overall_verdict": "Highly Credible Official News Report",
                "summary": "Direct factual reporting with official named sources and strong multi-agency cross-corroboration."
            }
        }
    },
    {
        "id": "scenario_2",
        "title": "Scenario 2: Clickbait Title Suppression & Claim Restoration",
        "description": "Detect sensational clickbait headlines, enforce suppression penalties, and generate an AI-restored claim card.",
        "briefing_points": [
            "Submit typical high-suspense clickbait headline",
            "Trigger -18 point headline distortion penalty",
            "Present AI Restored Claim card with factual summary"
        ],
        "lang": "en",
        "initial": {"url": ""},
        "steps": [
            {"action": "spotlight", "target": "#newsUrl", "duration": 800, "delay": 200},
            {
                "action": "type",
                "target": "#newsUrl",
                "value": "Drinking this everyday is DEADLY?! Doctor reveals shocking truth! Netizens horrified: Never touching it again! https://viral-buzz-health.com/articles/deadly-drink-shocking",
                "delay": 300
            },
            {"action": "spotlight", "target": "#analyzeBtn", "duration": 500, "delay": 200},
            {"action": "click", "target": "#analyzeBtn", "delay": 100},
            {"action": "wait_for", "target": "#resultsSection", "timeout": 8000, "delay": 1500},
            {
                "action": "explainer",
                "title": "Restored Claim Card",
                "body": "AI bypasses clickbait suspense to present objective facts: standard caffeine intake limits with zero lethal risk under normal use.",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            },
            {"action": "scroll_to", "target": "#headlineFidelityCard", "delay": 300},
            {
                "action": "explainer",
                "title": "D3 Headline Penalty (-18 Points)",
                "body": "Severe distortion detected (D3=0.32), triggering an 18-point penalty and capping overall score at 45 (Unverified).",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            }
        ],
        "expected": {"overall_max": 50, "verdict": "Unverified"},
        "mock_result": {
            "title": "Drinking this everyday is DEADLY?! Doctor reveals shocking truth! Netizens horrified: Never touching it again!",
            "url": "https://viral-buzz-health.com/articles/deadly-drink-shocking",
            "credibility_score": 45,
            "rule_score": 45,
            "llm_score": 45,
            "overall_score": 45.0,
            "rating": "Unverified",
            "confidence": 0.88,
            "scoring_basis": "D3 Headline distortion detected (-18 penalty) | Content farm source with zero corroboration",
            "clickbait_analysis": {
                "is_clickbait": True,
                "penalty": -18,
                "restored_claim": "Medical guideline regarding excessive caffeine intake. Moderate consumption poses no documented fatal risk.",
                "original_title": "Drinking this everyday is DEADLY?! Doctor reveals shocking truth! Netizens horrified: Never touching it again!",
                "neutral_title": "Physician Guidelines on Caffeine Consumption and Health Effects"
            },
            "dimensions": {
                "headline_fidelity": {
                    "id": "D3",
                    "key": "headline_fidelity",
                    "name": "Headline Fidelity",
                    "value": 0.32,
                    "confidence": 0.90,
                    "verdict": "clickbait_suppressed",
                    "label": "Fidelity 32% (-18 Pt Penalty)",
                    "badge_color": "yellow",
                    "penalty": -18.0,
                    "desc": "Severe discrepancy between headline and body content designed to induce unwarranted anxiety."
                }
            },
            "deep_analysis": {
                "claim": "Daily beverage consumption causes immediate fatal health hazards",
                "key_points": ["Extreme overdose risks conflated with normal dietary intake"],
                "fallacies": "Fearmongering & Hastened Generalization",
                "llm_score": 45,
                "overall_verdict": "Typical Clickbait Content Farm Article"
            }
        }
    },
    {
        "id": "scenario_3",
        "title": "Scenario 3: Social Media Disinformation & Bot Blacklist",
        "description": "Intercept high-risk bot network accounts on social platforms and force cross-source corroboration score to zero.",
        "briefing_points": [
            "Input suspicious bot account post URL on X (Twitter)",
            "Enforce immediate social blocklist match (D2 = 0)",
            "Rhetoric risk surges to 0.70, locking score at 25 (Highly Suspicious)"
        ],
        "lang": "en",
        "initial": {"url": ""},
        "steps": [
            {"action": "spotlight", "target": "#newsUrl", "duration": 800, "delay": 200},
            {
                "action": "type",
                "target": "#newsUrl",
                "value": "https://x.com/suspicious_disinfo_bot/status/987654321098",
                "delay": 300
            },
            {"action": "spotlight", "target": "#analyzeBtn", "duration": 500, "delay": 200},
            {"action": "click", "target": "#analyzeBtn", "delay": 100},
            {"action": "wait_for", "target": "#resultsSection", "timeout": 8000, "delay": 1500},
            {
                "action": "explainer",
                "title": "Social Blocklist Interception",
                "body": "Matches flagged bot propaganda registry. D2 corroboration score is unconditionally locked to 0.",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            },
            {"action": "scroll_to", "target": "#rhetoricalRiskCard", "delay": 300},
            {
                "action": "explainer",
                "title": "High Rhetorical Risk (R=0.70)",
                "body": "Heavy partisan polarization and emotional manipulation detected. Credibility locked at 25 (Highly Suspicious).",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            }
        ],
        "expected": {"overall_max": 30, "verdict": "Highly Suspicious"},
        "mock_result": {
            "title": "Post on X (Twitter) by @suspicious_disinfo_bot",
            "url": "https://x.com/suspicious_disinfo_bot/status/987654321098",
            "credibility_score": 25,
            "rule_score": 25,
            "llm_score": 25,
            "overall_score": 25.0,
            "rating": "Highly Suspicious",
            "confidence": 0.95,
            "scoring_basis": "Social blocklist match (D2 locked to 0) | High rhetorical risk (R=0.70)",
            "dimensions": {
                "cross_corroboration": {
                    "id": "D2",
                    "key": "cross_corroboration",
                    "name": "Cross-Source Corroboration",
                    "value": 0.0,
                    "confidence": 0.99,
                    "verdict": "blacklisted",
                    "label": "Blocklisted (Locked to 0)",
                    "badge_color": "red",
                    "penalty": -40.0,
                    "desc": "Source account identified on coordinated propaganda registry; corroboration score forced to 0."
                },
                "rhetorical_risk": {
                    "id": "D4",
                    "key": "rhetorical_risk",
                    "name": "Rhetorical Risk",
                    "value": 0.70,
                    "confidence": 0.92,
                    "verdict": "high_risk",
                    "label": "Risk 0.70 (Emotional Manipulation)",
                    "badge_color": "red",
                    "penalty": -20.0,
                    "desc": "Heavy use of divisive language and narrative manipulation tactics."
                }
            },
            "deep_analysis": {
                "claim": "Unsubstantiated conspiracy claims targeting public institutions",
                "evidence_strength": "No Verifiable Evidence",
                "llm_score": 25,
                "overall_verdict": "Coordinated Inauthentic Behavior Detected"
            }
        }
    },
    {
        "id": "scenario_4",
        "title": "Scenario 4: Multilingual Real News Verification",
        "description": "Analyze an international wire service report (Reuters) to demonstrate global multi-source corroboration.",
        "briefing_points": [
            "Input Reuters global technology supply chain report URL",
            "Corroborate reporting with Bloomberg and Associated Press (88 pts)",
            "Deliver on-device AI multilingual analysis summary"
        ],
        "lang": "en",
        "initial": {"url": ""},
        "steps": [
            {"action": "spotlight", "target": "#newsUrl", "duration": 800, "delay": 200},
            {
                "action": "type",
                "target": "#newsUrl",
                "value": "https://www.reuters.com/technology/semiconductor-supply-chain-expansion-2024",
                "delay": 300
            },
            {"action": "spotlight", "target": "#analyzeBtn", "duration": 500, "delay": 200},
            {"action": "click", "target": "#analyzeBtn", "delay": 100},
            {"action": "wait_for", "target": "#resultsSection", "timeout": 8000, "delay": 1500},
            {
                "action": "explainer",
                "title": "International Corroboration: 88 Points",
                "body": "Automatically matched simultaneous coverage across Bloomberg and AP, achieving 88-point high credibility.",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 200
            },
            {"action": "scroll_to", "target": "#deepAnalysisCard", "delay": 300},
            {
                "action": "explainer",
                "title": "Multilingual AI Verification Complete",
                "body": "NewsAnalyzer delivers seamless localized UX and robust factual reasoning across international languages.",
                "position": "bottom-right",
                "duration": 3500,
                "delay": 300
            }
        ],
        "expected": {"overall_min": 85, "verdict": "Highly Credible"},
        "mock_result": {
            "title": "Reuters: Global Semiconductor Supply Chain Expands with New Fab Investments",
            "url": "https://www.reuters.com/technology/semiconductor-supply-chain-expansion-2024",
            "credibility_score": 88,
            "overall_score": 88.0,
            "rating": "Highly Credible",
            "scoring_basis": "International wire service (Reuters) + Corroborated by Bloomberg & Associated Press",
            "dimensions": {
                "cross_corroboration": {
                    "id": "D2",
                    "key": "cross_corroboration",
                    "name": "Cross-Source Corroboration",
                    "value": 0.88,
                    "confidence": 0.94,
                    "verdict": "corroborated",
                    "label": "88% (Corroborated by Bloomberg & AP)",
                    "badge_color": "green",
                    "penalty": 0.0,
                    "desc": "Simultaneous corroboration from major international news agencies verified."
                }
            },
            "deep_analysis": {
                "claim": "Semiconductor manufacturing resilience expands via coordinated global investments",
                "llm_score": 92,
                "overall_verdict": "Internationally Corroborated High-Credibility Report"
            }
        }
    }
]

with open(BASE / "scenarios_ja.json", "w", encoding="utf-8") as f:
    json.dump(ja_scenarios, f, ensure_ascii=False, indent=2)

with open(BASE / "scenarios_en.json", "w", encoding="utf-8") as f:
    json.dump(en_scenarios, f, ensure_ascii=False, indent=2)

print("Saved scenarios_ja.json and scenarios_en.json cleanly!")
