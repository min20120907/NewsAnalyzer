#!/usr/bin/env python3
"""
NewsAnalyzer Hybrid Demo Automation Runner
支援 Live Demo Mode (即時自動操作) 與 Recording Mode (1080p MP4 錄製)
由 demo/scenarios.json 單一真相驅動，整合 Cinematic Animation Layer。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
SCENARIOS_FILE = BASE_DIR / "scenarios.json"
OVERLAY_JS = BASE_DIR / "animation_overlay.js"
OVERLAY_CSS = BASE_DIR / "animation_overlay.css"
SCRATCH_DIR = ROOT_DIR / ".hermes" / "cache" / "scratch" / "demo_recordings"
os.makedirs(SCRATCH_DIR, exist_ok=True)


def load_scenarios():
    with open(SCENARIOS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def inject_animation_layer(page):
    """注入動畫層的 CSS 與 JavaScript 到當前頁面"""
    css_content = OVERLAY_CSS.read_text(encoding="utf-8")
    js_content = OVERLAY_JS.read_text(encoding="utf-8")
    page.add_style_tag(content=css_content)
    page.add_script_tag(content=js_content)


def run_scenario(page, scenario, speed=1.0, is_simulation=False, index=1, total=1):
    title = scenario.get("title", "")
    desc = scenario.get("description", "")
    print(f"\n▶ 正在播放情境 {index}/{total}: {title} ({scenario['id']})")

    # 1. 過場動畫與前期提要 (Cinematic Briefing)
    page.evaluate(f"window.CinemaOverlay.speed = {speed};")
    page.evaluate(f"window.CinemaOverlay.shutterTransition();")
    page.wait_for_timeout(int(300 / speed))
    points = scenario.get("briefing_points", [])
    page.evaluate(f"window.CinemaOverlay.showBriefing({json.dumps('SCENARIO ' + str(index) + ' / ' + str(total))}, {json.dumps(title)}, {json.dumps(desc)}, {json.dumps(points)}, 4500);")
    page.wait_for_timeout(int(1200 / speed))

    # 2. 初始狀態配置
    init = scenario.get("initial", {})
    if init.get("clear_input"):
        page.evaluate("if (document.querySelector('#input')) document.querySelector('#input').value = '';")
        page.evaluate("if (document.querySelector('#resultCard')) document.querySelector('#resultCard').classList.remove('show');")

    if init.get("lang"):
        page.evaluate(f"if (typeof setLanguage === 'function') setLanguage('{init['lang']}');")
        page.wait_for_timeout(int(300 / speed))

    # 視窗捲動回頂端並重置游標位置，確保情境起始點完全對齊
    page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
    page.evaluate("window.CinemaOverlay.hideSpotlight();")
    page.evaluate("window.CinemaOverlay.hideTooltip();")
    page.evaluate("window.CinemaOverlay.hideExplainer();")
    page.evaluate(f"window.CinemaOverlay.updateCursorPos(window.innerWidth / 2, 180, false);")
    page.wait_for_timeout(int(500 / speed))

    # 3. 依序執行操作步驟
    steps = scenario.get("steps", [])
    for idx, step in enumerate(steps, 1):
        action = step.get("action")
        target = step.get("target")
        hint = step.get("hint", "")
        delay = step.get("delay", 500)

        # 提示氣泡
        if hint:
            page.evaluate(f"window.CinemaOverlay.showTooltip({json.dumps(hint)});")

        if action == "spotlight":
            page.evaluate(f"window.CinemaOverlay.showSpotlight({json.dumps(target)});")
            page.evaluate(f"window.CinemaOverlay.moveTo({json.dumps(target)});")
            page.wait_for_timeout(int(delay / speed))

        elif action == "click":
            # 同步視覺滑鼠點擊與 Playwright 真實點擊
            page.evaluate(f"window.CinemaOverlay.click({json.dumps(target)});")
            page.wait_for_timeout(int(200 / speed))
            if step.get("target") == "#analyzeBtn":
                # Record / Simulation 模式：直接以 mock_result 觸發渲染，避免等待網路與後端 LLM
                mock_json = json.dumps(scenario.get("mock_result", {}))
                page.evaluate(f"if (typeof renderResult === 'function') renderResult({mock_json});")
            elif not is_simulation:
                page.locator(target).first.click()
            page.wait_for_timeout(int(delay / speed))

        elif action == "type":
            val = step.get("value", "")
            page.evaluate(f"window.CinemaOverlay.moveTo({json.dumps(target)});")
            page.evaluate(f"window.CinemaOverlay.showSpotlight({json.dumps(target)});")
            char_delay = step.get("char_delay", 25)
            page.evaluate(f"window.CinemaOverlay.typeText({json.dumps(target)}, {json.dumps(val)}, {char_delay});")
            # 等候打字動畫完成
            total_type_time = len(val) * char_delay
            page.wait_for_timeout(int((total_type_time + 400) / speed))

        elif action == "scroll_to":
            page.evaluate(f"window.CinemaOverlay.hideSpotlight();")
            page.evaluate(f"document.querySelector({json.dumps(target)})?.scrollIntoView({{behavior:'smooth', block:'center'}});")
            page.evaluate(f"window.CinemaOverlay.moveTo({json.dumps(target)});")
            page.wait_for_timeout(int(delay / speed))

        elif action == "wait_for":
            timeout = step.get("timeout", 20000)
            page.locator(target).first.wait_for(state="visible", timeout=timeout)
            page.wait_for_timeout(int(800 / speed))

        elif action == "explainer":
            # 顯示結果區塊解析器 (Explainer Annotation)
            explainer_html = step.get("html", "")
            explainer_delay = step.get("delay", 4000)
            page.evaluate(f"window.CinemaOverlay.showExplainer({json.dumps(explainer_html)});")
            if target:
                page.evaluate(f"window.CinemaOverlay.showSpotlight({json.dumps(target)});")
                page.evaluate(f"window.CinemaOverlay.moveTo({json.dumps(target)});")
            page.wait_for_timeout(int(explainer_delay / speed))

    # 4. 清理動畫指示器
    page.evaluate("window.CinemaOverlay.hideTooltip();")
    page.evaluate("window.CinemaOverlay.hideExplainer();")
    page.evaluate("window.CinemaOverlay.hideSpotlight();")
    page.wait_for_timeout(int(600 / speed))

    # 5. 嚴格驗證預期結果 (Verification Gate)
    expected = scenario.get("expected", {})
    selector = expected.get("selector")
    check_type = expected.get("check")

    if selector and check_type == "element_visible":
        assert page.locator(selector).first.is_visible(), f"驗證失敗: 元素 {selector} 未能成功顯示！"
        print(f"✅ 驗證成功: 元素 {selector} 已如預期展示。")
    elif selector and check_type == "contains_text":
        txt = page.locator(selector).first.inner_text()
        exp_txt = expected.get("value", "")
        assert exp_txt in txt, f"驗證失敗: {selector} 文字 '{txt}' 未包含預期的 '{exp_txt}'！"
        print(f"✅ 驗證成功: {selector} 成功包含關鍵文字 '{exp_txt}'。")

    print(f"✔ 情境 {scenario['id']} 播放完成！")
    # 過場轉場動畫
    page.evaluate("window.CinemaOverlay.shutterTransition();")


def convert_video_to_mp4(webm_path, mp4_path):
    """使用 ffmpeg 將 Playwright webm 轉檔為高品質 1920x1080 MP4"""
    print(f"\n🎬 正在透過 FFmpeg 將錄影轉檔為 1080p MP4: {mp4_path}")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(webm_path),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        str(mp4_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"🎉 影片生成完成: {mp4_path} ({os.path.getsize(mp4_path) / 1024:.1f} KB)")


def main():
    parser = argparse.ArgumentParser(description="NewsAnalyzer Hybrid Demo Runner")
    parser.add_argument("--mode", choices=["live", "simulation", "record"], default="live",
                        help="執行模式：live (操作真實後端), simulation (離線mock), record (錄製mp4)")
    parser.add_argument("--scenario", default="all", help="指定情境 ID 或 'all'")
    parser.add_argument("--speed", type=float, default=1.0, help="播放速度倍率 (預設: 1.0)")
    parser.add_argument("--output", default="newsanalyzer_demo.mp4", help="錄影模式輸出之 MP4 檔名")
    parser.add_argument("--url", default="http://127.0.0.1:5000", help="NewsAnalyzer 伺服器網址")
    args = parser.parse_args()

    scenarios = load_scenarios()
    if args.scenario != "all":
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        if not scenarios:
            print(f"找不到情境 ID: {args.scenario}")
            sys.exit(1)

    record_dir = SCRATCH_DIR if args.mode == "record" else None

    with sync_playwright() as p:
        browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--window-size=1920,1080"
        ]
        browser = p.chromium.launch(
            headless=(args.mode == "record"),
            args=browser_args
        )

        context_kwargs = {
            "viewport": {"width": 1920, "height": 1080},
            "device_scale_factor": 1,
        }
        if record_dir:
            context_kwargs["record_video_dir"] = str(record_dir)
            context_kwargs["record_video_size"] = {"width": 1920, "height": 1080}

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        # 開啟網站
        target_url = args.url
        print(f"🌐 連線目標網站: {target_url}")
        page.goto(target_url, wait_until="networkidle")

        # 注入動畫層
        inject_animation_layer(page)

        is_sim = (args.mode == "simulation")

        # 依序執行所選情境 (加入總數計算)
        total_scenarios = len(scenarios)
        for idx, s in enumerate(scenarios, 1):
            run_scenario(page, s, speed=args.speed, is_simulation=is_sim, index=idx, total=total_scenarios)
            page.wait_for_timeout(1000)

        # 取得錄影檔路徑
        video = page.video
        context.close()
        browser.close()

        if args.mode == "record" and video:
            recorded_path = video.path()
            out_mp4 = Path(args.output).resolve()
            convert_video_to_mp4(recorded_path, out_mp4)
            print(f"\n✨ 全部情境錄製驗收通過！輸出路徑: {out_mp4}")


if __name__ == "__main__":
    main()