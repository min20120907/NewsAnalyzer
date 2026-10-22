#!/usr/bin/env python3
"""
mix_professional_unified.py
徹底落實「NewsAnalyzer 演示影片完整剪輯修復計劃書」：
1. 統一音色：全片 100% 採用單一臺灣國語專業自然女聲（zh-TW-HsiaoChenNeural）
2. 消除語音腰斬、口播重複與男女聲混雜
3. D1 零沉默（17.2s 緊接結果出爐切入）
4. D3 準時落拍（27.5s 畫面滑入即落拍）
5. 完整補回 Qwen AI 分數 95 分（39.0s 完整口播）
6. 原片 18 處點擊與叮咚音效 100% 完整保留（音量 0.35）
"""
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
OUT = str(BASE_DIR / "newsanalyzer_demo_1080p_narrated.mp4")

AUDIO_DIR = ROOT_DIR / "tts_cache" / "unified_female"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# 依計劃書第四節乾淨版腳本切分之 18 段精準軌道
tracks = [
  # 情境一：主流媒體新聞剖析
  ('s1_01_02', 0.2, 1.35, '歡迎來到 NewsAnalyzer 完整功能展示。首先進入情境一：臺灣主流媒體新聞分析。在主輸入框貼上花蓮重建報導網址，點擊「開始分析」。', '0.0s S1 簡報開場 + 9.8s 點擊分析'),
  ('s1_03',   11.2, 1.15, '分析結果出爐，儀表板顯示總分 89 分，評級為高度可信。', '11.4s 叮咚 89 分出爐'),
  ('s1_04',   17.2, 1.15, '第一階段查無爭議事實，由第二階段接手，跨來源報導可信度得分 88 分，系統比對多家主流媒體，確認關鍵資訊一致。', '18.0s D1 查無爭議轉 D2 (D1 零沉默)'),
  ('s1_05',   27.5, 1.15, '第三維度標題忠實度得分 92 分，標題與內文高度吻合，無誇大或誤導。', '28.0s 畫面捲動至 D3 忠實度 92% (D3 準確落拍)'),
  ('s1_06',   34.2, 1.15, '第四維度內文修辭安全度達 92%。', '35.0s 畫面捲動至 D4 修辭安全度 92%'),
  ('s1_07',   39.0, 1.15, '透過三階段透明計分管線融合本地 Qwen 模型，AI 綜合評分 95 分，最終判定為高可信度報導。', '42.0s 計分管線 + Qwen AI 評分 95 分 (AI 95 補齊)'),

  # 情境二：點擊誘餌標題壓制與還原
  ('s2_01',   53.5, 1.35, '進入情境二：點擊誘餌標題壓制與客觀事實還原。我們輸入一則典型的懸念釣魚標題，點擊開始分析。', '54.0s S2 開場, 61.4s 點擊分析'),
  ('s2_02',   62.6, 1.15, '系統啟動真實主旨還原卡片，AI 自動破梗，第一時間揭示客觀事實。', '62.8s 叮咚黃色還原卡片出爐'),
  ('s2_03',   70.0, 1.15, '在維度評分中，標題黨指標觸發負 18 分重扣；同時來源特徵判定為搬運型內容農場，缺乏主流媒體佐證。', '73.0s 聚焦 D3 扣 18 分'),
  ('s2_04',   79.5, 1.15, '最終評分被嚴格壓制在 45 分，標記為「待查證」。', '80.0s 聚焦 D2 農場 45 分'),

  # 情境三：社群媒體假新聞與機器人黑名單
  ('s3_01',   87.5, 1.70, '進入情境三：社群媒體假新聞與機器人帳號過濾。我們輸入一篇來自被列管帳號的 X 平台推文網址，點擊開始分析。', '88.0s S3 開場, 94.5s 點擊分析'),
  ('s3_02',   95.8, 1.15, '系統迅速命中社群黑名單，來源佐證強制歸零；同時偵測到強烈的情緒宣傳與操弄痕跡，三重紅線同步觸發。', '95.9s 叮咚黑名單出爐'),
  ('s3_03',  106.5, 1.15, '最終綜合評分鎖定在 25 分，列為「高度可疑」。', '107.0s 鎖定 25 分高度可疑'),

  # 情境四：多語言跨國新聞實測
  ('s4_01',  118.0, 1.65, '進入情境四：多語言新聞實測。首先進行 Part A 日文新聞實測。在日語介面輸入日本 NHK 報導網址，點擊分析。', '118.9s 點擊日文, 125.6s 點擊分析'),
  ('s4_02',  126.8, 1.15, '系統以全日文介面呈現，總分獲得 91 分極高信賴度；偵測到共同通信與時事通信同步報導，語言切換無漏譯。', '127.0s 叮咚日文 91 分出爐'),
  ('s4_03',  140.5, 1.35, '接著進行 Part B 英文新聞實測。切換至英文介面，輸入路透社 Reuters 半導體供應鏈報導，點擊分析。', '141.2s 點擊英文, 147.9s 點擊分析'),
  ('s4_04',  149.0, 1.15, '三維度檢驗全部通過，彭博社與美聯社皆有同步同報，本地 AI 深度分析給出 95 分高分。', '149.3s 叮咚路透社 88 分 + AI 95 分'),

  # 結尾
  ('end_01', 162.8, 1.45, '四項核心情境驗證完成。NewsAnalyzer，三語假新聞與資訊可靠度智能分析系統，感謝您的收看。', '163.4s 總結提示音收尾')
]

processed = []
for name, t, spd, text, desc in tracks:
    raw_mp3 = AUDIO_DIR / f"{name}_raw.mp3"
    out_wav = AUDIO_DIR / f"{name}.wav"
    
    if not out_wav.exists():
        subprocess.run([
            "/home/min20120907/Documents/Web_and_App_Development/NewsAnalyzer/.venv/bin/edge-tts",
            "--voice", "zh-TW-HsiaoChenNeural",
            "--text", text,
            "--write-media", str(raw_mp3)
        ], check=True)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(raw_mp3),
            "-filter:a", f"silenceremove=start_periods=1:start_threshold=-50dB,atempo={spd}",
            "-ar", "24000", "-ac", "1", str(out_wav)
        ], check=True)
        raw_mp3.unlink(missing_ok=True)
    
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_wav)], capture_output=True, text=True)
    dur = float(res.stdout.strip())
    processed.append((t, out_wav, dur, desc))
    print(f"t={t:5.1f}s | dur={dur:4.2f}s | end={t+dur:5.1f}s | {desc}")

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

print("\n開始依計劃書標準混音至:", OUT)
subprocess.run(cmd, check=True)
print("混音完成！")
