#!/usr/bin/env python3
"""
mix_paced.py
將原展示影片進行 1.3x 舒適節奏重校（畫面降速 30%，擴展呼吸時間至 220.7s），
使每個操作、打字與點擊都能從容配合 Gemini Charon 原生神經講稿，
全片 D1~D4 完整無缺，零趕戲、零死寂空白。
"""
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
RAW_VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
PACED_VIDEO = str(BASE_DIR / "newsanalyzer_demo_paced.mp4")
OUT = str(BASE_DIR / "newsanalyzer_demo_1080p_narrated.mp4")

CACHE = ROOT_DIR / "tts_cache"

# 1. 產生 1.3x 舒適節奏底片（若尚未產生）
if not Path(PACED_VIDEO).exists():
    print("正在校準畫面步調至舒適節奏 (1.3x PTS)...")
    cmd_pace = [
        "ffmpeg", "-y", "-loglevel", "warning",
        "-i", RAW_VIDEO,
        "-filter_complex", "[0:v]setpts=1.3*PTS[v];[0:a]atempo=0.7692[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
        PACED_VIDEO
    ]
    subprocess.run(cmd_pace, check=True)

# 2. 依 1.3x 物理音效與畫面錨點精準掛載講稿
s1 = CACHE / "scenarios" / "scenario_1.wav"
s2 = CACHE / "scenarios" / "scenario_2.wav"
s3_1 = CACHE / "line_008.wav"
s3_2 = CACHE / "line_009.wav"
s3_3 = CACHE / "synced" / "seg_08.wav"

s4_0 = CACHE / "synced" / "seg_09.wav"
s4_1 = CACHE / "line_010.wav"
s4_2 = CACHE / "synced" / "seg_10.wav"
s4_3 = CACHE / "synced" / "seg_11.wav"
s4_4 = CACHE / "line_011.wav"
s4_5 = CACHE / "synced" / "seg_12.wav"
s4_6 = CACHE / "line_012.wav"

tracks = [
  (1.0,   s1),
  (70.0,  s2),
  (115.0, s3_1),
  (125.0, s3_2),
  (136.0, s3_3),
  (154.0, s4_0),
  (165.5, s4_1),
  (176.0, s4_2),
  (185.0, s4_3),
  (194.5, s4_4),
  (204.0, s4_5),
  (212.5, s4_6)
]

inputs = ["-i", PACED_VIDEO]
for t, w in tracks:
    assert w.exists(), f"Missing {w}"
    inputs += ["-i", str(w)]

parts = []
for i, (t, w) in enumerate(tracks):
    idx = i + 1
    delay_ms = int(t * 1000)
    parts.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[v{idx}]")

narr_mix = "".join(f"[v{i+1}]" for i in range(len(tracks)))
parts.append(f"{narr_mix}amix=inputs={len(tracks)}:duration=longest:normalize=0[narr_track]")
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

print("混音輸出至:", OUT)
subprocess.run(cmd, check=True)
print("混音完成！")
