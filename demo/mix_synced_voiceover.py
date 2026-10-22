#!/usr/bin/env python3
"""
mix_synced_voiceover.py
產生 100% 精準對齊畫面的臺灣國語旁白，並保留原影片音效混合輸出。
"""
import json, os, subprocess
from pathlib import Path
from gtts import gTTS

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
OUT = str(BASE_DIR / "newsanalyzer_demo_1080p_narrated.mp4")
CACHE_DIR = ROOT_DIR / "tts_cache" / "synced"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

segments = [
  {"t": 2.0,   "text": "情境一，臺灣主流媒體新聞分析。輸入花蓮重建報導網址，點擊開始分析。"},
  {"t": 17.0,  "text": "分析結果出爐，儀表板顯示總分 89 分，評級判定為高度可信。"},
  {"t": 29.0,  "text": "D2 跨源佐證 88%，中央社同步同報。D3 忠實度與 D4 安全度皆達 92%。"},
  {"t": 41.0,  "text": "計分管線完整展開，規則分 85 分加上本地 AI 深度分析，綜合判定 88.5 分。"},
  {"t": 54.0,  "text": "情境二，點擊誘餌標題壓制與還原。輸入典型聳動釣魚標題，開始分析。"},
  {"t": 64.0,  "text": "真實主旨還原卡片啟動，AI 自動破梗提煉客觀事實，D3 標題黨觸發負 18 分重扣。"},
  {"t": 80.0,  "text": "D2 顯示單一內容農場缺乏同報，總分嚴格壓制為 45 分待查證。"},
  {"t": 88.0,  "text": "情境三，社群假新聞與機器人黑名單。輸入被列管之推特帳號貼文，點擊開始分析。"},
  {"t": 100.0, "text": "D2 命中社群黑名單，佐證強制歸零。D4 偵測到情緒宣傳，最終鎖定 25 分高度可疑。"},
  {"t": 118.0, "text": "情境四，多語言新聞實測。在日語介面輸入日本 NHK 報導，獲評 91 分極高信賴。"},
  {"t": 133.0, "text": "D2 偵測到共同通信與時事通信同步報導，四維度定義全日語呈現。"},
  {"t": 142.0, "text": "切換英文介面，輸入路透社報導並點擊分析。"},
  {"t": 153.0, "text": "彭博與美聯社同步同報，英文本地 AI 深度分析給出 95 分。"},
  {"t": 163.5, "text": "NewsAnalyzer 透過四維度分析，提供最可靠的新聞判讀。"}
]

# 儲存更新後的 JSON
(BASE_DIR / "narration_zh_tw.json").write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")

# 生成語音檔
wavs = []
for i, item in enumerate(segments):
    t = item["t"]
    text = item["text"]
    raw_wav = CACHE_DIR / f"raw_{i:02d}.wav"
    out_wav = CACHE_DIR / f"seg_{i:02d}.wav"
    mp3 = CACHE_DIR / f"raw_{i:02d}.mp3"
    
    if not out_wav.exists():
        gTTS(text=text, lang="zh-TW").save(str(mp3))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ar", "24000", "-ac", "1", str(raw_wav)], check=True)
        speed = 1.25 if i != len(segments) - 1 else 1.40
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw_wav), "-filter:a", f"atempo={speed}", "-ar", "24000", "-ac", "1", str(out_wav)], check=True)
        mp3.unlink(missing_ok=True)
        raw_wav.unlink(missing_ok=True)
    wavs.append(out_wav)
    print(f"  [{i:02d}] t={t:5.1f}s | {text}")

# 混音：原影片音效 0:a 降至 0.35 + 旁白音軌 1.0 混合
inputs = ["-i", VIDEO]
for w in wavs:
    inputs += ["-i", str(w)]

parts = []
for i, item in enumerate(segments):
    idx = i + 1
    delay_ms = int(item["t"] * 1000)
    parts.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[v{idx}]")

narr_mix = "".join(f"[v{i+1}]" for i in range(len(wavs)))
parts.append(f"{narr_mix}amix=inputs={len(wavs)}:duration=longest:normalize=0[narr_track]")
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
