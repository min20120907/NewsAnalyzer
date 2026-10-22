#!/usr/bin/env python3
"""
mix_atomic_sync.py
在 169.8 秒原版影片上，消除音訊前端靜音（silenceremove），
並將語音時間點全面提前 0.5s~1.2s，讓聲音精確「領先/同步」動作，
徹底解決慢半拍問題。
"""
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
OUT = str(BASE_DIR / "newsanalyzer_demo_1080p_narrated.mp4")

CACHE = ROOT_DIR / "tts_cache"
ATOMIC = CACHE / "atomic"
SFX_DIR = CACHE / "sfx_synced"
SYNCED = CACHE / "synced"
TRIMMED = CACHE / "trimmed"
TRIMMED.mkdir(exist_ok=True)

# 零延遲校準時間軸：消除慢半拍，提前 0.5~1.2s 領先動作觸發
calibrated_tracks = [
  ( 0.2, ATOMIC / "s1_intro.wav",    1.00, "0.0s S1 簡報開場"),
  ( 3.8, ATOMIC / "s1_input.wav",    1.25, "4.8s 輸入網址, 9.8s 點擊分析"),
  (11.2, ATOMIC / "s1_result.wav",   1.00, "11.4s 叮咚 89 分出爐"),
  (21.8, ATOMIC / "s1_d1_d2.wav",    1.00, "22.0s 畫面捲動至 D1, 28.0s 至 D2"),
  (33.8, ATOMIC / "s1_d3_d4.wav",    1.00, "34.0s 畫面捲動至 D3/D4"),
  (43.8, ATOMIC / "s1_pipeline.wav", 1.00, "44.0s 畫面捲動至計分管線"),
  (54.0, ATOMIC / "s2_input.wav",    1.65, "54.0s S2 開場, 58.0s 輸入, 61.4s 點擊"),
  (62.8, ATOMIC / "s2_card.wav",     1.00, "62.8s 叮咚黃色還原卡片出爐"),
  (72.5, ATOMIC / "s2_d3.wav",       1.00, "73.0s 聚焦 D3 扣 18 分"),
  (78.0, ATOMIC / "s2_d2.wav",       1.00, "79.0s 聚焦 D2/D4 農場 45 分"),
  (88.0, SFX_DIR / "line_008.wav",   1.15, "88.0s S3 開場, 91.3s 輸入, 94.5s 點擊"),
  (95.8, SFX_DIR / "line_009.wav",   1.15, "95.9s 叮咚黑名單 25 分出爐"),
  (103.5, SYNCED / "seg_08.wav",     1.15, "104.0s 聚焦 D4 宣傳話術與 AI 判讀"),
  (118.0, SYNCED / "seg_09.wav",     1.85, "118.9s 點擊切換日文"),
  (124.0, SFX_DIR / "line_010.wav",  1.15, "125.6s 點擊分析, 127.0s 叮咚 91 分"),
  (133.0, SYNCED / "seg_10.wav",     1.15, "134.0s 聚焦共同通信/時事通信全日語"),
  (140.8, SYNCED / "seg_11.wav",     1.15, "141.2s 點擊切換英文"),
  (147.0, SFX_DIR / "line_011.wav",  1.15, "147.9s 點擊分析, 149.3s 叮咚 88 分"),
  (154.5, SYNCED / "seg_12.wav",     1.15, "156.0s 聚焦彭博/美聯社與 AI 95 分"),
  (163.0, SFX_DIR / "line_012.wav",  1.25, "163.4s 叮咚總結畫面出爐")
]

processed = []
for i, (t, w, spd, desc) in enumerate(calibrated_tracks):
    out_w = TRIMMED / f"trim_{i:02d}.wav"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(w),
        "-filter:a", f"silenceremove=start_periods=1:start_threshold=-50dB,atempo={spd}",
        "-ar", "24000", "-ac", "1", str(out_w)
    ], check=True)
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_w)], capture_output=True, text=True)
    dur = float(res.stdout.strip())
    processed.append((t, out_w, dur, desc))

inputs = ["-i", VIDEO]
for t, w, dur, desc in processed:
    inputs += ["-i", str(w)]

parts = []
for i, (t, w, dur, desc) in enumerate(processed):
    idx = i + 1
    delay_ms = int(t * 1000)
    parts.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[v{idx}]")

narr_mix = "".join(f"[v{i+1}]" for i in range(len(processed)))
parts.append(f"{narr_mix}amix=inputs={len(processed)}:duration=longest:normalize=0[narr_track]")
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

print("\n開始依零延遲校準軸混音至:", OUT)
subprocess.run(cmd, check=True)
print("混音完成！")
