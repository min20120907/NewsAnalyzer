#!/usr/bin/env python3
"""
sync_multilingual_scenarios.py
修復 demo/scenarios_ja.json 與 demo/scenarios_en.json 與中文版錄影時間軸不一致的問題。

【核心修復項目】
1. 恆定打字時間校正 (Normalized Typing Duration)：
   在 automation_runner.py 中，打字時間計算公式為 `len(value) * char_delay + 400`。
   由於英文新聞字串長度 (269 字元) 是中文/日文 (110 字元) 的 2.4 倍以上，若固定 `char_delay: 15`，
   英文版每個情境的打字動作會比中文版慢 2.4 ~ 3.5 秒，導致後續所有畫面時間點向後漂移！
   本腳本自動根據中文字串基準耗時，動態反推日文與英文各步驟的專屬 `char_delay`，讓中、日、英三語錄製出的
   Raw 影片每個步驟落點 100% 同步！
2. 修正 Explainer 步驟的 `delay` 欄位：
   修正 update_clean_scenarios.py 誤將停留時間寫在 `duration` 而把 `delay` 設為 300~1000ms 的問題，
   確保 `automation_runner.py` 讀取 `step.get("delay", 4000)` 時維持與基準版一致的 4500ms / 5000ms 停留時長。
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SCENARIOS_ZH = BASE_DIR / "scenarios.json"
SCENARIOS_JA = BASE_DIR / "scenarios_ja.json"
SCENARIOS_EN = BASE_DIR / "scenarios_en.json"


def sync_scenario_timings(base_scenarios: list, target_scenarios: list, lang: str) -> list:
    synced = []
    for s_idx, target_sc in enumerate(target_scenarios):
        sc = dict(target_sc)
        base_sc = base_scenarios[s_idx] if s_idx < len(base_scenarios) else None

        base_steps = base_sc.get("steps", []) if base_sc else []
        target_steps = [dict(st) for st in sc.get("steps", [])]

        for i, st in enumerate(target_steps):
            # 1. 統一動作名稱：確保 type_text 轉為 automation_runner.py 支援的 type
            if st.get("action") == "type_text":
                st["action"] = "type"

            # 2. 若 explainer 使用了 duration 而 delay 過短，將 duration 同步回 delay
            if st.get("action") == "explainer":
                if "duration" in st and st.get("delay", 0) < 2000:
                    st["delay"] = st["duration"]

            # 3. 如有對應的中文基準步驟，強制對齊每個步驟的等待時間與打字總時長
            if i < len(base_steps):
                b_st = base_steps[i]
                action = st.get("action")

                if action == "type" and b_st.get("action") == "type":
                    base_val = b_st.get("value", "")
                    base_cd = b_st.get("char_delay", 15)
                    target_val = st.get("value", "")

                    # 中文基準打字總毫秒數 = len(base_val) * base_cd
                    target_total_ms = max(600, len(base_val) * base_cd)
                    if len(target_val) > 0:
                        # 動態調整日/英文 char_delay，使 len(target_val) * char_delay 恆等於中文打字耗時
                        st["char_delay"] = max(4, round(target_total_ms / len(target_val)))
                else:
                    if "delay" in b_st:
                        st["delay"] = b_st["delay"]

        sc["steps"] = target_steps
        synced.append(sc)

    return synced


def main():
    if not SCENARIOS_ZH.exists():
        raise FileNotFoundError(f"找不到基準檔案：{SCENARIOS_ZH}")

    base_zh = json.loads(SCENARIOS_ZH.read_text(encoding="utf-8"))

    for lang, path in [("ja", SCENARIOS_JA), ("en", SCENARIOS_EN)]:
        if not path.exists():
            print(f"[{lang.upper()}] 找不到 {path.name}，跳過。")
            continue

        target_data = json.loads(path.read_text(encoding="utf-8"))
        synced_data = sync_scenario_timings(base_zh, target_data, lang)
        path.write_text(json.dumps(synced_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{lang.upper()}] ✅ 已同步步驟延遲與打字時間軸：{path}")


if __name__ == "__main__":
    main()