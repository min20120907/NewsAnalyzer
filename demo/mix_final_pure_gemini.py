#!/usr/bin/env python3
"""
mix_final_pure_gemini.py
100% 使用 Gemini 原生神經聲線 (Charon)，包含單次大請求產出的完整情境 1 與 2，
以及已緩存之情境 3 與 4，零機械音，完整對齊 169.8s 影片。
"""
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
OUT = str(BASE_DIR / "newsanalyzer_demo_1080p_narrated.mp4")

SCENARIOS_DIR = ROOT_DIR / "tts_cache" / "scenarios"
TUNED_DIR = ROOT_DIR / "tts_cache" / "gemini38_tuned"

tracks = [
  (1.0,   SCENARIOS_DIR / "scenario_1.wav", "情境一完整段落（主流媒體新聞分析）"),
  (54.0,  SCENARIOS_DIR / "scenario_2.wav", "情境二完整段落（點擊誘餌標題壓制與還原）"),
  (88.0,  TUNED_DIR / "line_008.wav",       "情境三步驟 1（社群假新聞與被列管推特帳號輸入）"),
  (100.0, TUNED_DIR / "line_009.wav",       "情境三步驟 2（D2 黑名單歸零與 25 分鎖定）"),
  (124.5, TUNED_DIR / "line_010.wav",       "情境四 Part A（日文 NHK 實測與 91 分極高信賴）"),
  (147.0, TUNED_DIR / "line_011.wav",       "情境四 Part B（英文 Reuters 實測與同報佐證）"),
  (162.0, TUNED_DIR / "line_012.wav",       "總結結尾畫面（四維度透明計分與多語路由）")
]

inputs = ["-i", VIDEO]
for t, w, desc in tracks:
    assert w.exists(), f"Missing file: {w}"
    inputs += ["-i", str(w)]
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(w)], capture_output=True, text=True)
    dur = float(res.stdout.strip())
    print(f"t={t:5.1f}s | dur={dur:5.2f}s | end={t+dur:5.2f}s | {desc}")

parts = []
for i, (t, w, desc) in enumerate(tracks):
    idx = i + 1
    delay_ms = int(t * 1000)
    parts.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[v{idx}]")

narr_mix = "".join(f"[v{i+1}]" for i in range(len(tracks)))
parts.append(f"{narr_mix}amix=inputs={len(tracks)}:duration=longest:normalize=0[narr_track]")
parts.append("[0:a]volume=0.3[orig_bg]")
parts.append("[narr_track]volume=1.0[narr_norm]")
parts.append("[orig_bg][narr_norm]amix=inputs=2:duration=first:normalize=0[aout]")

filter_complex = ";".join(parts)

cmd = [
    "ffmpeg", "-y", "-loglevel", "warning",
    *inputs,
    "-filter_complex", filter_complex,
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
    OUT
]

print("\n開始混音至:", OUT)
subprocess.run(cmd, check=True)
print("混音完成！")
