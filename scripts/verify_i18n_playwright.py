import os
import sys
import json
import re
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = "/home/min20120907/.hermes/cache/scratch/i18n_test"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# 測試用資料：涵蓋各維度與情境
TEST_DATA = {
    "url": "https://news.yahoo.co.jp/articles/c49172ee2e0f271af7d052cef4541dc7b123e789",
    "title": "脚本家・麻枝准氏、咽頭がんを公表 緩和ケア選択 「CLANNAD」「AIR」“泣きゲー”パイオニア",
    "final_score": 84.4,
    "rating": "高度可信",
    "rule_score": 81.2,
    "fusion_weight": 0.3,
    "post_fusion_score": 84.4,
    "scoring_basis": "路由 B（主流來源／跨源同報佐證）：一般外部網域 (yahoo.co.jp)＋內文具名出處核實｜1 家外部來源同報（msn.com）｜近期發布 (1天內)（佐證指數 0.86）",
    "dimensions": {
        "evidence_verdict": {
            "id": "D1", "key": "evidence_verdict", "name": "查核證據蘊涵度",
            "value": 0.0, "confidence": 0.0, "status_label": "none", "impact_pts": 0.0,
            "explanation": "外部事實查核庫無此具體事件之核實紀錄（交由跨源佐證 D2 與內文風險 D4 路由）",
            "what_it_measures": "已核實查核庫對「同一具體事件」之蘊涵或駁斥立場與證據信心",
            "what_if_wrong": "若誤將無關查核當命中會直接壓低真新聞"
        },
        "source_corroboration": {
            "id": "D2", "key": "source_corroboration", "name": "跨源報導佐證度",
            "value": 0.86, "confidence": 1.0, "status_label": "corroborated", "impact_pts": 81.2,
            "explanation": "一般外部網域 (yahoo.co.jp)＋內文具名出處核實｜1 家外部來源同報（msn.com）｜近期發布 (1天內)（佐證指數 0.86）",
            "what_it_measures": "新聞原始發布機構之信譽等級、獨立媒體交叉同報家數",
            "what_if_wrong": "若把內容農場互抄算成同報會高估未查證文章"
        },
        "headline_faithfulness": {
            "id": "D3", "key": "headline_faithfulness", "name": "標題內文忠實度",
            "value": 0.79, "confidence": 0.8, "status_label": "faithful", "impact_pts": 0.0,
            "explanation": "標題平實反映內文主旨（標題—內文一致性 79%），無誇大或斷章取義（0 扣分；忠實度不額外灌水加分）",
            "what_it_measures": "新聞標題之斷言是否忠實反映內文",
            "what_if_wrong": "誤報時僅對該文施加標題失真扣分"
        },
        "rhetorical_risk": {
            "id": "D4", "key": "rhetorical_risk", "name": "內文修辭與可驗性風險",
            "value": 0.15, "confidence": 0.85, "status_label": "low_risk", "impact_pts": 0.0,
            "explanation": "內文語氣平實、無煽動轉發或偽冒公告特徵（低風險 R=0.15，惟缺外部查核時最高停留於待查證區間）",
            "what_it_measures": "文本自身之情緒操弄、催促轉發動員",
            "what_if_wrong": "作用範圍嚴格限制在未查證區間內"
        }
    },
    "metrics": {
        "sentiment": {"name": "情緒傾向", "score": 12.8, "desc": "修辭安全度 85%（風險 R=0.15）", "weight": 15},
        "domain": {"name": "來源可信度", "score": 21.5, "desc": "一般外部網域 (yahoo.co.jp)＋內文具名出處核實", "weight": 25},
        "similarity": {"name": "內容相似度", "score": 15.0, "desc": "忠實度 100%（faithful）", "weight": 15},
        "fact_check": {"name": "事實查核", "score": 0.0, "desc": "not_found", "weight": 30},
        "user_feedback": {"name": "查核庫回報", "score": 0.0, "desc": "none", "weight": 10},
        "timeliness": {"name": "時效性", "score": 5.0, "desc": "近期發布", "weight": 5}
    },
    "sources": [
        {"source": "cofacts", "status": "not_found"},
        {"source": "google", "status": "not_found"},
        {"source": "jfc", "status": "not_found"},
        {"source": "infact", "status": "not_found"}
    ],
    "deep_analysis": {
        "claim": "麻枝准氏公表咽頭がん、緩和ケア選択",
        "key_points": ["Key公式発表で咽頭がん診断が確認", "本人意向で積極治療せず緩和ケア選択"],
        "viewpoints": "客観的事実：知名ゲーム脚本家麻枝准が健康状況を公表。",
        "analysis": "スポニチアネックス報道がKey公式発表を引用し、診断事実と治療方針を明確に裏付けており、信頼性が高い。",
        "credibility_score": 92,
        "score_std": 0,
        "samples": 1,
        "model": "qwen3.8-27b-fastmtp",
        "evidence_state": "no_evidence",
        "evidence_used": ["スポニチアネックス", "Key公式発表"],
        "title_bait": True,
        "neutral_title": "麻枝准氏、咽頭がん公表と緩和ケア療養の選択",
        "title_bait_reason": "元見出しの一部に誇張表現の疑いあり"
    }
}

ZH_LEAK_PATTERNS = [
    r"查核", r"佐證", r"忠實度", r"內文", r"來源", r"規則", r"取樣", r"判定根拠：外部事實",
    r"一般外部網域", r"近期發布", r"點擊誘餌", r"暫時分數", r"未載入正文"
]

def run_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.goto("http://127.0.0.1:5000", wait_until="networkidle")

        langs = ["zh", "en", "ja"]
        reports = {}

        for lang in langs:
            print(f"=== Testing language: {lang} ===")
            page.click(f'[data-lang-btn="{lang}"]')
            page.wait_for_timeout(300)

            # 注入測試資料調用 renderResult
            page.evaluate(f"renderResult({json.dumps(TEST_DATA)})")
            page.wait_for_timeout(500)

            shot_path = os.path.join(SCREENSHOT_DIR, f"result_{lang}.png")
            page.screenshot(path=shot_path, full_page=True)
            print(f"Saved screenshot: {shot_path}")

            # 抓取 resultCard 裡面的所有文字
            result_card_text = page.inner_text("#resultCard")
            
            leaks = []
            if lang == "en":
                # 英文模式下，除日文原文標題及模型名稱外，尋找任何中文
                # 先過濾掉麻枝准的標題與日文分析
                filtered_text = result_card_text.replace(TEST_DATA["title"], "")
                for k in TEST_DATA["deep_analysis"]["key_points"]:
                    filtered_text = filtered_text.replace(k, "")
                filtered_text = filtered_text.replace(TEST_DATA["deep_analysis"]["analysis"], "")
                filtered_text = filtered_text.replace(TEST_DATA["deep_analysis"]["viewpoints"], "")
                filtered_text = filtered_text.replace(TEST_DATA["deep_analysis"]["claim"], "")
                
                # 檢查剩餘文字是否有中文字
                matches = re.findall(r"[\u4e00-\u9fff]{2,}", filtered_text)
                if matches:
                    leaks = list(set(matches))
            elif lang == "ja":
                # 日文模式下，檢查是否殘留繁體中文特有詞彙
                for pat in ZH_LEAK_PATTERNS:
                    found = re.findall(pat, result_card_text)
                    if found:
                        leaks.extend(found)
                leaks = list(set(leaks))

            reports[lang] = {
                "screenshot": shot_path,
                "leaks": leaks,
                "sample_text": result_card_text[:300].replace("\n", " ")
            }

        browser.close()
        print("\n=== FINAL REPORT ===")
        print(json.dumps(reports, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    run_test()
