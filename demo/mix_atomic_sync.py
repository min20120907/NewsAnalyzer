#!/usr/bin/env python3
"""
mix_atomic_sync.py
在原始 169.8 秒未調速的影片上，將原聲神經語音徹底拆解為 20 個原子短音效，
每個短句精確對齊至個別輸入、點擊、卡片彈出與捲動動作，達成零脫節、零搶拍。
"""
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
OUT = str(BASE_DIR / "newsanalyzer_demo_1080p_narrated.mp4")

ATOMIC = ROOT_DIR / "tts_cache" / "atomic"
SFX_DIR = ROOT_DIR / "tts_cache" / "sfx_synced"
SYNCED = ROOT_DIR / "tts_cache" / "synced"

tracks = [
  # 情境一
  (0.5,   ATOMIC / "s1_intro.wav",    1.00, "情境一開場提要"),
  (4.5,   ATOMIC / "s1_input.wav",    1.15, "情境一輸入花蓮報導並點擊（9.8s 點擊）"),
  (12.2,  ATOMIC / "s1_result.wav",   1.00, "分析結果出爐 89 分（11.4s 叮咚響起）"),
  (23.0,  ATOMIC / "s1_d1_d2.wav",    1.00, "D1 查無爭議轉 D2，跨源佐證 88%"),
  (35.0,  ATOMIC / "s1_d3_d4.wav",    1.00, "D3 忠實度 92%，D4 安全度 92%"),
  (45.0,  ATOMIC / "s1_pipeline.wav", 1.00, "透明計分管線融合本地 Qwen 88.5 分"),
  # 情境二
  (54.5,  ATOMIC / "s2_input.wav",    1.15, "情境二輸入釣魚標題並點擊（61.4s 點擊）"),
  (67.5,  ATOMIC / "s2_card.wav",     1.00, "真實主旨還原卡片破梗（62.8s 叮咚響起）"),
  (73.5,  ATOMIC / "s2_d3.wav",       1.00, "D3 標題黨觸發負 18 分重扣"),
  (78.5,  ATOMIC / "s2_d2.wav",       1.00, "D2 單一農場缺乏同報，壓制為 45 分"),
  # 情境三
  (88.5,  SFX_DIR / "line_008.wav",   1.15, "情境三輸入被列管 X 帳號（94.5s 點擊）"),
  (96.2,  SFX_DIR / "line_009.wav",   1.15, "命中黑名單鎖定 25 分（95.9s 叮咚響起）"),
  (104.5, SYNCED / "seg_08.wav",      1.15, "D4 政治宣傳話術與本地 AI 判讀"),
  # 情境四
  (118.5, SYNCED / "seg_09.wav",      1.55, "情境四切換日語並輸入 NHK（118.9s 點擊）"),
  (124.0, SFX_DIR / "line_010.wav",   1.15, "日文新聞獲評 91 分（127.0s 叮咚響起）"),
  (133.0, SYNCED / "seg_10.wav",      1.15, "共同通信與時事通信同報，全日語呈現"),
  (141.5, SYNCED / "seg_11.wav",      1.15, "切換英文模式並輸入路透社（141.2s 點擊）"),
  (147.0, SFX_DIR / "line_011.wav",   1.15, "路透社分析完成獲評 88 分（149.3s 叮咚響起）"),
  (155.0, SYNCED / "seg_12.wav",      1.15, "彭博與美聯社同報佐證，AI 深度分析 95 分"),
  (163.5, SFX_DIR / "line_012.wav",   1.25, "四個情境驗證完成，總結收尾（163.4s 總結音）")
]

# 產生調速後原子音訊
processed = []
for i, (t, w, spd, desc) in enumerate(tracks):
    assert w.exists(), f"Missing {w}"
    out_w = ROOT_DIR / "tts_cache" / "atomic" / f"track_{i:02d}.wav"
    if spd != 1.0:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(w), "-filter:a", f"atempo={spd}", "-ar", "24000", "-ac", "1", str(out_w)], check=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(w), "-ar", "24000", "-ac", "1", str(out_w)], check=True)
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_w)], capture_output=True, text=True)
    dur = float(res.stdout.strip())
    processed.append((t, out_w, dur, desc))
    print(f"[{i:02d}] t={t:5.1f}s | dur={dur:4.2f}s | end={t+dur:5.1f}s | {desc}")

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

print("\n開始精確混音至:", OUT)
subprocess.run(cmd, check=True)
print("混音完成！")
