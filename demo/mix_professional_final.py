#!/usr/bin/env python3
"""
mix_professional_final.py
落實「快速收尾方案」：
1. 在 00:46.5 ~ 00:52.9 補上：「最後看到頁面底部的本機 Qwen 模型，給出 95 分的高分評價與深度分析總結。」
2. 全軌底層鋪設輕柔科技感無版權 BGM（-26 dBFS），徹底消除空檔冷場。
3. 全片統一臺灣國語自然女聲（zh-TW-HsiaoChenNeural），零腰斬、零重複、原版音效完整保留。
"""
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
BGM = str(BASE_DIR / "tech_ambient_bgm.wav")
OUT = str(BASE_DIR / "newsanalyzer_demo_1080p_narrated.mp4")

AUDIO_DIR = ROOT_DIR / "tts_cache" / "unified_female"

# 19 條全片精確口播軌道
tracks = [
  # 情境一
  ("s1_01_02",  0.2, "0.0s S1 簡報開場 + 9.8s 點擊分析"),
  ("s1_03",    11.2, "11.4s 叮咚 89 分出爐"),
  ("s1_04",    17.2, "18.0s D1 查無爭議轉 D2 (D1 零沉默)"),
  ("s1_05",    27.5, "28.0s 畫面捲動至 D3 忠實度 92% (D3 準確落拍)"),
  ("s1_06",    34.2, "35.0s 畫面捲動至 D4 修辭安全度 92%"),
  ("s1_07",    39.0, "42.0s 計分管線分解 88.5 分"),
  ("s1_qwen95", 46.5, "46.5s 檢視本地 Qwen 模型 95 分高分評價與深度分析總結"),

  # 情境二
  ("s2_01",    53.5, "54.0s S2 開場, 61.4s 點擊分析"),
  ("s2_02",    62.6, "62.8s 叮咚黃色還原卡片出爐"),
  ("s2_03",    70.0, "73.0s 聚焦 D3 扣 18 分"),
  ("s2_04",    79.5, "80.0s 聚焦 D2 農場 45 分"),

  # 情境三
  ("s3_01",    87.5, "88.0s S3 開場, 94.5s 點擊分析"),
  ("s3_02",    95.8, "95.9s 叮咚黑名單出爐"),
  ("s3_03",   106.5, "107.0s 鎖定 25 分高度可疑"),

  # 情境四
  ("s4_01",   118.0, "118.9s 點擊日文, 125.6s 點擊分析"),
  ("s4_02",   126.8, "127.0s 叮咚日文 91 分出爐"),
  ("s4_03",   140.5, "141.2s 點擊英文, 147.9s 點擊分析"),
  ("s4_04",   149.0, "149.3s 叮咚路透社 88 分 + AI 95 分"),

  # 結尾
  ("end_01",  162.8, "163.4s 總結提示音收尾")
]

voice_files = []
for name, t, desc in tracks:
    wav_path = AUDIO_DIR / f"{name}.wav"
    assert wav_path.exists(), f"Missing file: {wav_path}"
    voice_files.append((t, wav_path, desc))

# 構建 ffmpeg 命令：輸入 0 為原片，輸入 1 為 BGM，輸入 2~20 為語音軌
inputs = ["-i", VIDEO, "-i", BGM]
for t, w, desc in voice_files:
    inputs += ["-i", str(w)]

parts = []
# 語音音軌延遲排列
for i, (t, w, desc) in enumerate(voice_files):
    input_idx = i + 2 # 0: video, 1: bgm
    delay_ms = int(t * 1000)
    parts.append(f"[{input_idx}:a]adelay={delay_ms}|{delay_ms}[v{i}]")

# 語音混音
narr_mix = "".join(f"[v{i}]" for i in range(len(voice_files)))
parts.append(f"{narr_mix}amix=inputs={len(voice_files)}:duration=longest:normalize=0[voice_bus]")

# 音量平衡：原片音效 0.35 + 輕柔 BGM 0.45 (-26 dBFS) + 旁白 1.05 (-3~-6 dBFS)
parts.append("[0:a]volume=0.35[sfx]")
parts.append("[1:a]volume=0.45[bgm]")
parts.append("[voice_bus]volume=1.05[voice]")
parts.append("[sfx][bgm][voice]amix=inputs=3:duration=first:normalize=0[aout]")

filter_complex = ";".join(parts)

cmd = [
    "ffmpeg", "-y", "-loglevel", "warning",
    *inputs,
    "-filter_complex", filter_complex,
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
    OUT
]

print("正在執行終審專業混音...")
subprocess.run(cmd, check=True)
print(f"終審混音完成 → {OUT}")
