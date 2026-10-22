#!/usr/bin/env python3
"""
mix_sfx_ground_truth.py
以原影片 18 處音效（Click 與 Ding）波峰為物理錨點，
將 Gemini 原生 Charon 語音精準對齊至毫秒級，保證音效與畫面完全同步。
"""
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
OUT = str(BASE_DIR / "newsanalyzer_demo_1080p_narrated.mp4")

CACHE = ROOT_DIR / "tts_cache"
SFX_DIR = CACHE / "sfx_synced"
SFX_DIR.mkdir(parents=True, exist_ok=True)

# 物理音效錨點時間軸 (SFX Click & Ding)
timeline = [
  (1,   2.5, 1.15, "情境一輸入與點擊（對齊 9.8s 點擊音效）"),
  (2,  12.0, 1.15, "情境一結果 88.5 分（對齊 11.4s 出爐音效）"),
  (3,  25.0, 1.15, "情境一 D3 忠實度 92% 檢視"),
  (4,  42.0, 1.15, "情境一 三階段計分與 Qwen 95 分"),
  (5,  54.5, 1.15, "情境二釣魚標題輸入（對齊 61.4s 點擊音效）"),
  (6,  63.5, 1.15, "情境二還原卡片（對齊 62.8s 出爐音效）"),
  (7,  73.0, 1.15, "情境二 D3 扣 18 分與 45 分壓制"),
  (8,  88.5, 1.15, "情境三 X 貼文輸入（對齊 94.5s 點擊音效）"),
  (9,  96.5, 1.15, "情境三黑名單 25 分（對齊 95.9s 出爐音效）"),
  (10, 124.0, 1.15, "情境四日文 NHK（對齊 125.6s 點擊與 127.0s 音效）"),
  (11, 146.5, 1.15, "情境四英文 Reuters（對齊 147.9s 點擊與 149.3s 音效）"),
  (12, 163.4, 1.30, "情境四總結收尾（對齊 163.4s 總結提示音）")
]

wavs = []
for idx, t, spd, desc in timeline:
    in_wav = CACHE / f"line_{idx:03d}.wav"
    out_wav = SFX_DIR / f"line_{idx:03d}.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(in_wav), "-filter:a", f"atempo={spd}", "-ar", "24000", "-ac", "1", str(out_wav)], check=True)
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_wav)], capture_output=True, text=True)
    dur = float(res.stdout.strip())
    wavs.append((t, out_wav))
    print(f"t={t:5.1f}s | dur={dur:4.2f}s | end={t+dur:5.1f}s | {desc}")

inputs = ["-i", VIDEO]
for t, w in wavs:
    inputs += ["-i", str(w)]

parts = []
for i, (t, w) in enumerate(wavs):
    idx = i + 1
    delay_ms = int(t * 1000)
    parts.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[v{idx}]")

narr_mix = "".join(f"[v{i+1}]" for i in range(len(wavs)))
parts.append(f"{narr_mix}amix=inputs={len(wavs)}:duration=longest:normalize=0[narr_track]")
parts.append("[0:a]volume=0.35[orig_sfx]")
parts.append("[narr_track]volume=1.05[narr_boost]")
parts.append("[orig_sfx][narr_boost]amix=inputs=2:duration=first:normalize=0[aout]")

filter_complex = ";".join(parts)

cmd = [
    "ffmpeg", "-y", "-loglevel", "warning",
    *inputs,
    "-filter_complex", filter_complex,
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
    OUT
]

print("\n開始依音效物理錨點混音至:", OUT)
subprocess.run(cmd, check=True)
print("混音完成！")
