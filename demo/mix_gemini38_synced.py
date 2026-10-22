#!/usr/bin/env python3
"""
mix_gemini38_synced.py
使用 Gemini 3.8 原始高質感神經語音 (Charon) 產出精準對齊且節奏緊湊的展示旁白。
"""
import json, os, subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
OUT = str(BASE_DIR / "newsanalyzer_demo_1080p_narrated.mp4")
CACHE_DIR = ROOT_DIR / "tts_cache"
TUNED_DIR = CACHE_DIR / "gemini38_tuned"
TUNED_DIR.mkdir(parents=True, exist_ok=True)

timeline = [
  (0,   0.5, 1.12, "歡迎來到 news analyzer 完整示範 本影片涵蓋四個實測情境 包含主流媒體 標題黨社群假新聞以及日英3語測試"),
  (1,  10.5, 1.12, "情境一 臺灣主流媒體新聞完整剖析 我們貼上一篇花蓮地震重建的新聞連結 點擊開始分析"),
  (2,  18.5, 1.12, "D2 跨來源報導可信度得分88分 系統比對多家媒體的相關報導 確認資訊一致"),
  (3,  27.5, 1.12, "D3 標題忠實度 得分92分 標題與內容高度吻合沒有誇大或誤導"),
  (4,  42.0, 1.12, "深入分析模式呼叫本地Qwen大語言模型 AI綜合評分95分 結論為高可信度報導"),
  (5,  54.0, 1.12, "情境二 標題黨攔截與還原 我們輸入一篇懸疑感十足的標題 看系統如何拆解它"),
  (6,  64.0, 1.12, "系統啟動真實意圖還原，把誇大標題還原成客觀陳述，並指出哪些詞語構成標題黨"),
  (7,  74.0, 1.12, "評分管線完整展開，從四維度加權到AI深入分析，每個分數都有透明依據"),
  (8,  88.0, 1.12, "情境三 社群媒體假新聞與機器人黑名單 我們輸入一篇來自被列管帳號的X貼文"),
  (9, 100.0, 1.12, "最終得分25分 高度可疑 來源黑名單 情緒操縱缺乏佐證 三重紅線觸發"),
  (10, 124.5, 1.12, "情境四 Part A 日文新聞實測 NHK 系統以日文介面完整分析總分91分 語言切換無漏譯"),
  (11, 147.0, 1.12, "Part B 英文新聞實測 Reuters 半導體供應鏈報導分析完成 三語矩陣全部通過"),
  (12, 162.0, 1.22, "四個情境驗證完成。NewsAnalyzer，三語假新聞可靠度分析系統，謝謝收看。")
]

# 儲存更新後的 JSON
json_data = [{"t": t, "text": text} for idx, t, spd, text in timeline]
(BASE_DIR / "narration_zh_tw.json").write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")

# 調整語速與時間
wavs = []
for idx, t, spd, text in timeline:
    in_wav = CACHE_DIR / f"line_{idx:03d}.wav"
    out_wav = TUNED_DIR / f"line_{idx:03d}.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(in_wav), "-filter:a", f"atempo={spd}", "-ar", "24000", "-ac", "1", str(out_wav)], check=True)
    wavs.append(out_wav)
    print(f"  [{idx:02d}] t={t:5.1f}s | {text[:30]}...")

# 混音：原影片音效 0:a 降至 0.3 + Gemini 3.8 旁白音軌 1.05 混合
inputs = ["-i", VIDEO]
for w in wavs:
    inputs += ["-i", str(w)]

parts = []
for idx, t, spd, text in timeline:
    line_no = idx + 1
    delay_ms = int(t * 1000)
    parts.append(f"[{line_no}:a]adelay={delay_ms}|{delay_ms}[v{line_no}]")

narr_mix = "".join(f"[v{i+1}]" for i in range(len(wavs)))
parts.append(f"{narr_mix}amix=inputs={len(wavs)}:duration=longest:normalize=0[narr_track]")
parts.append("[0:a]volume=0.3[orig_bg]")
parts.append("[narr_track]volume=1.05[narr_norm]")
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
