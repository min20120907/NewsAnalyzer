#!/usr/bin/env python3
"""
mix_scenarios_gemini.py
以 4 次大段落請求（每情境 1 次）產出極高質感 Gemini 3.1/3.8 神經語音，
並以精準時間戳混音至 169.8s 展示影片。
"""
import json, os, subprocess, time, urllib.request, base64
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
OUT = str(BASE_DIR / "newsanalyzer_demo_1080p_narrated.mp4")
CACHE_DIR = ROOT_DIR / "tts_cache" / "scenarios"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

KEY = os.environ.get("GEMINI_API_KEY", "")
API = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-tts-preview:generateContent"
VOICE = "Charon"

scenarios = [
  {
    "id": 1,
    "t": 1.0,
    "text": "歡迎來到 NewsAnalyzer 完整展示。本系統結合多模態規則引擎與本地大語言模型，提供四維度透明計分。首先進入情境一，臺灣主流媒體新聞分析。輸入花蓮重建報導網址，點擊開始分析。分析結果出爐，儀表板顯示總分 89 分，評級為高度可信。D1 查無爭議由 D2 接手，跨源佐證 88%，中央社同步同報。D3 標題忠實度零扣分，D4 內文修辭安全度達 92%。三階段透明計分管線融合本地 Qwen 模型，最終綜合判定 88.5 分。"
  },
  {
    "id": 2,
    "t": 54.0,
    "text": "情境二，點擊誘餌標題壓制與還原，展示系統如何識破聳動釣魚標題，並自動還原客觀事實。輸入典型懸念釣魚標題，點擊開始分析。真實主旨還原卡片啟動，AI 自動破梗還原客觀事實，D3 標題黨觸發負 18 分重扣。D2 判定為單一內容農場缺乏主流同報，最終評分被嚴格壓制為 45 分待查證。"
  },
  {
    "id": 3,
    "t": 88.0,
    "text": "情境三，社群假新聞與機器人黑名單，展示系統如何攔截惡意協同宣傳帳號。輸入被列管之高風險推特帳號貼文與網址，點擊開始分析。D2 命中社群黑名單，跨源佐證指數強制歸零。D4 偵測到強烈情緒引導話術，計分管線結合本地 AI 判讀，最終鎖定 25 分高度可疑。"
  },
  {
    "id": 4,
    "t": 117.0,
    "text": "情境四，多語言真實新聞實測。切換為日語介面，輸入日本 NHK 新聞與網址，點擊分析開始。日文新聞獲評 91 分極高信賴，D2 偵測到共同通信與時事通信同步同報，四維度全日語呈現。接著切換至英文模式，輸入路透社報導並點擊分析。獲評 88 分高度可信，檢視彭博與美聯社同報佐證，英文本地 AI 深度分析給出 95 分。NewsAnalyzer 透過四維度透明計分與多語模型路由，提供最可靠的新聞判讀。"
  }
]

# 儲存劇本供檢閱
(BASE_DIR / "narration_scenarios.json").write_text(json.dumps(scenarios, ensure_ascii=False, indent=2), encoding="utf-8")

wavs = []
for sc in scenarios:
    idx = sc["id"]
    t = sc["t"]
    text = sc["text"]
    wav = CACHE_DIR / f"scenario_{idx}.wav"
    
    if not wav.exists():
        print(f"Synthesizing Scenario {idx} (t={t}s)...")
        body = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": VOICE}
                    }
                }
            }
        }
        req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                     headers={"x-goog-api-key": KEY, "Content-Type": "application/json"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read())
                cand = data["candidates"][0]
                audio_b64 = cand["content"]["parts"][0]["inlineData"]["data"]
                raw_bin = CACHE_DIR / f"raw_{idx}.bin"
                raw_bin.write_bytes(base64.b64decode(audio_b64))
                # 轉為 24000Hz 16-bit mono wav
                subprocess.run(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw_bin), str(wav)], check=True)
                raw_bin.unlink(missing_ok=True)
                print(f"  Scenario {idx} OK!")
                break
            except Exception as e:
                print(f"  Attempt {attempt} failed: {e}, waiting 25s...")
                time.sleep(25)
        # 遵循 3 RPM 限制
        time.sleep(22)
    
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(wav)], capture_output=True, text=True)
    dur = float(res.stdout.strip())
    print(f"Scenario {idx} | start: {t}s | dur: {dur:.2f}s | end: {t+dur:.2f}s")
    wavs.append((t, wav))

# 混音
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
