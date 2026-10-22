#!/usr/bin/env python3
"""
NewsAnalyzer 演示影片日文與英文版本自動合成與混音腳本
========================================================================
本腳本支援全自動將 NewsAnalyzer 1080p 示範影片（169.8 秒）合成出：
  1. 日文版本：NewsAnalyzer_Demo_JA.mp4 (預設語音: ja-JP-NanamiNeural / Gemini Japanese)
  2. 英文版本：NewsAnalyzer_Demo_EN.mp4 (預設語音: en-US-JennyNeural / Gemini English)

支援兩種合成方式：
  【方式 A】免 API Key、極速的微軟神經語音 (edge-tts)：
      pip install edge-tts
      python3 generate_multilingual_voiceovers.py --lang all

  【方式 B】Google AI Studio 免費 Gemini TTS (gemini-3.8-flash-tts)：
      export GEMINI_API_KEY="您的_API_KEY"
      python3 generate_multilingual_voiceovers.py --lang all
"""

import argparse
import asyncio
import base64
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path

VIDEO_IN_CANDIDATES = [
    "NewsAnalyzer_Demo_100Percent_Master.mp4",
    "demo/NewsAnalyzer_Demo_100Percent_Master.mp4",
    "newsanalyzer_demo_1080p_narrated.mp4",
    "demo/newsanalyzer_demo_1080p_narrated.mp4",
]

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")

# ========================================================================
# 1. 毫秒級對齊的時間軸腳本 (日文版 ja-JP & 英文版 en-US)
# ========================================================================

NARRATION_JA = [
    # 情境一：主流媒體新聞分析
    {"start_sec": 0.0, "text": "NewsAnalyzer の機能デモへようこそ。まずシナリオ1、主要メディアによる報道の分析です。"},
    {"start_sec": 4.27, "text": "メインの入力欄に花蓮復興に関する公共放送のURLを貼り付け、分析開始をクリックします。"},
    {"start_sec": 9.33, "text": "本文抽出、ファクトチェック照合、複数メディアの相互検証、ローカルLLMの深度分析が並行して実行されます。"},
    {"start_sec": 13.5, "text": "分析結果が出ました。総合信頼性スコアは89点、高信頼性と判定されています。"},
    {"start_sec": 18.27, "text": "D1のファクトチェックで虚偽情報は確認されず、安全にD2の相互検証へと引き継がれました。"},
    {"start_sec": 24.1, "text": "D2の相互検証スコアは88点。中央社や連合報など、複数メディアによる重要情報の一致を確認しています。"},
    {"start_sec": 29.93, "text": "D3の見出し忠実度は92点。見出しと本文の内容が完全に一致し、誇張やミスリードはありません。"},
    {"start_sec": 35.67, "text": "D4の修辞リスクは0.08と極めて低く、客観的で冷静な事実報道です。"},
    {"start_sec": 41.57, "text": "透明性の高い計算パイプラインにより、ルール評価とローカルAIの判定が統合され、88.5点が算出されます。"},
    {"start_sec": 46.5, "text": "画面下部のローカルQwenモデルも95点の高評価を与え、詳細な根拠を出力しています。"},

    # 情境二：點擊誘餌標題壓制與還原
    {"start_sec": 53.5, "text": "続いてシナリオ2、クリックベイト見出しの抑制とファクト復元です。"},
    {"start_sec": 57.57, "text": "典型的な煽り見出しを入力し、分析を開始します。"},
    {"start_sec": 63.93, "text": "システムは真の主張復元カードを表示し、AIが要点を先取りして客観的な事実を提示します。"},
    {"start_sec": 70.03, "text": "D3の見出し忠実度で大きな乖離が検知され、18点のペナルティが課されます。"},
    {"start_sec": 75.83, "text": "さらにソースはまとめサイトと判定され、裏付け報道も存在しません。"},
    {"start_sec": 81.63, "text": "これにより総合スコアは45点へと抑制され、要検証に分類されます。"},

    # 情境三：社群媒體假新聞與機器人黑名單
    {"start_sec": 86.73, "text": "シナリオ3は、SNSの偽情報とBotアカウントのフィルタリングです。"},
    {"start_sec": 90.8, "text": "マークされた高リスクなXアカウントの投稿URLを入力し、分析を実行します。"},
    {"start_sec": 97.0, "text": "ソーシャルブラックリストに即座にヒットし、D2の裏付けスコアは強制的にゼロに固定されます。"},
    {"start_sec": 103.03, "text": "D4の修辞リスクは0.70に達し、感情的な扇動と世論操作の兆候が特定されました。"},
    {"start_sec": 109.03, "text": "最終スコアは25点に抑え込まれ、極めて疑わしいと判定されます。"},

    # 情境四：多語言跨國新聞實測
    {"start_sec": 114.13, "text": "最後にシナリオ4、多言語による実ニュースの検証です。"},
    {"start_sec": 118.4, "text": "まず日本語UIに切り替え、NHKの報道URLを入力して分析します。"},
    {"start_sec": 128.1, "text": "全画面が日本語化され、スコア91点を記録。共同通信や時事通信の同時報道も自動検出しています。"},
    {"start_sec": 134.53, "text": "下部には日本語の算出ロジックと、ローカルAIによる日本語の分析サマリーが表示されます。"},
    {"start_sec": 140.7, "text": "続いて英語UIへ切り替え、ロイター通信の半導体サプライチェーン報道を分析します。"},
    {"start_sec": 150.4, "text": "ブルームバーグやAP通信の相互検証を確認し、スコア88点の高信頼性を獲得しました。"},

    # 結尾 (提早至 158.0s 開播，填補空白)
    {"start_sec": 158.0, "text": "4つの主要シナリオの検証が完了しました。NewsAnalyzerは、4つの直交指標、透明なスコアリング、そして多言語対応により、信頼できるファクトチェックを実現します。ご視聴ありがとうございました。"}
]

NARRATION_EN = [
    # Scenario 1: Mainstream News Corroboration
    {"start_sec": 0.0, "text": "Welcome to NewsAnalyzer. In Scenario 1, we analyze a mainstream Taiwanese news report."},
    {"start_sec": 4.27, "text": "We paste a public television report URL regarding reconstruction into the input box and click Start Analysis."},
    {"start_sec": 9.33, "text": "The engine simultaneously executes text extraction, fact-check matching, cross-media corroboration, and local LLM reasoning."},
    {"start_sec": 13.5, "text": "The analysis completes: an overall credibility score of 89 out of 100, rated as Highly Credible."},
    {"start_sec": 18.27, "text": "Dimension 1 confirms no dispute records, safely handing over evaluation to Dimension 2, scoring 88 points."},
    {"start_sec": 24.1, "text": "Multiple independent outlets, including CNA and UDN, corroborate the key facts with consistent reporting."},
    {"start_sec": 29.93, "text": "Dimension 3 headline fidelity scores 92 points, confirming strong alignment without sensational clickbait."},
    {"start_sec": 35.67, "text": "Dimension 4 rhetorical risk is at a minimal 0.08, demonstrating factual objectivity with zero emotional hype."},
    {"start_sec": 41.57, "text": "The transparent pipeline combines rule metrics of 85 at 70% with local AI of 95 at 30%, yielding 88.5 points."},
    {"start_sec": 46.5, "text": "At the bottom, the local Qwen model confirms a 95-point score with detailed reasoning."},

    # Scenario 2: Clickbait Title Suppression & Restoration
    {"start_sec": 53.5, "text": "Scenario 2 demonstrates clickbait headline suppression and claim restoration."},
    {"start_sec": 57.57, "text": "We submit a typical sensational, suspense-driven clickbait title and begin analysis."},
    {"start_sec": 63.93, "text": "The system displays the Restored Claim card, where AI cuts through the hype to reveal the core objective facts."},
    {"start_sec": 70.03, "text": "Severe headline distortion is detected on Dimension 3, triggering an 18-point suppression penalty."},
    {"start_sec": 75.83, "text": "The source is identified as a syndicated content farm lacking independent corroboration."},
    {"start_sec": 81.63, "text": "The final score is strictly capped at 45 points, categorized as Unverified."},

    # Scenario 3: Social Media Disinformation & Bot Blacklist
    {"start_sec": 86.73, "text": "Scenario 3 covers social disinformation routing and bot account interception."},
    {"start_sec": 90.8, "text": "We paste a post URL from a flagged high-risk X account and run the analysis."},
    {"start_sec": 97.0, "text": "The account matches the social blocklist, forcing Dimension 2 corroboration score to zero."},
    {"start_sec": 103.03, "text": "Dimension 4 rhetorical risk surges to 0.70, detecting strong partisan manipulation and propaganda cues."},
    {"start_sec": 109.03, "text": "The overall score is firmly locked down at 25 points, classified as Highly Suspicious."},

    # Scenario 4: Multilingual Real News Verification
    {"start_sec": 114.13, "text": "Finally, Scenario 4 demonstrates multilingual cross-border news verification."},
    {"start_sec": 118.4, "text": "Switching to the Japanese interface, we input an NHK news URL and analyze."},
    {"start_sec": 128.1, "text": "The system presents full Japanese localization, scoring 91 points with Kyodo and Jiji cross-verification."},
    {"start_sec": 134.53, "text": "Scrolling down reveals the localized scoring formula and Japanese deep analysis from the local AI."},
    {"start_sec": 140.7, "text": "Next, we switch to English and test a Reuters semiconductor supply chain report."},
    {"start_sec": 150.4, "text": "Corroboration from Bloomberg and the Associated Press is confirmed, earning an 88-point Highly Credible score."},

    # Conclusion (Advanced to 158.0s)
    {"start_sec": 158.0, "text": "All four core scenarios are successfully verified. Combining four orthogonal dimensions, transparent pipelines, and multilingual AI, NewsAnalyzer delivers trustworthy news credibility intelligence. Thank you for watching."}
]

# ========================================================================
# 2. TTS 語音合成引擎
# ========================================================================

async def synth_edge_tts(segments, lang_code: str, voice_name: str, cache_dir: Path):
    import edge_tts
    cache_dir.mkdir(parents=True, exist_ok=True)
    clip_paths = []
    print(f"🎙️ [Edge-TTS] 正在使用 {voice_name} 合成 {lang_code.upper()} 旁白音軌...")
    for idx, seg in enumerate(segments):
        out_mp3 = cache_dir / f"edge_{lang_code}_{idx:02d}.mp3"
        if not out_mp3.exists() or out_mp3.stat().st_size < 500:
            comm = edge_tts.Communicate(seg["text"], voice_name, rate="+4%")
            await comm.save(str(out_mp3))
        clip_paths.append((seg["start_sec"], out_mp3))
        print(f"  [✔] {seg['start_sec']:6.2f}s | {seg['text'][:38]}...")
    return clip_paths

def synth_gemini_tts(segments, lang_code: str, voice_id: str, cache_dir: Path):
    cache_dir.mkdir(parents=True, exist_ok=True)
    clip_paths = []
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    print(f"🎙️ [Gemini TTS] 正在使用 {GEMINI_MODEL} ({voice_id}) 合成 {lang_code.upper()} 旁白音軌...")
    for idx, seg in enumerate(segments):
        out_wav = cache_dir / f"gemini_{lang_code}_{idx:02d}.wav"
        if out_wav.exists() and out_wav.stat().st_size > 1000:
            clip_paths.append((seg["start_sec"], out_wav))
            continue
        payload = {
            "contents": [{
                "role": "user",
                "parts": [{
                    "text": seg["text"],
                    "speech_metadata": {"style": "professional, warm, clear, crisp pacing"}
                }]
            }],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"voice": voice_id}}
            }
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp_json = json.loads(resp.read().decode("utf-8"))
        b64_audio = resp_json["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        raw = base64.b64decode(b64_audio)
        if raw[:4] == b"RIFF":
            out_wav.write_bytes(raw)
        else:
            with wave.open(str(out_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(raw)
        clip_paths.append((seg["start_sec"], out_wav))
        print(f"  [✔] {seg['start_sec']:6.2f}s | {seg['text'][:38]}...")
        time.sleep(1.5)
    return clip_paths

# ========================================================================
# 3. 視訊混音與漸黑導出 (對齊 169.8 秒與 1.5 秒 Fade to Black)
# ========================================================================

def mux_multilingual_video(video_in: str, video_out: str, clip_paths, bgm_path: str = None):
    inputs = ["-i", video_in]
    filter_parts = []
    mix_labels = []

    # 1. 保留原影片點擊與叮咚音效 (0:a)
    filter_parts.append("[0:a]volume=0.35,afade=t=out:st=168.3:d=1.5[sfx]")
    mix_labels.append("[sfx]")

    # 2. 處理背景音樂 (1:a)
    if bgm_path and Path(bgm_path).exists():
        inputs.extend(["-i", bgm_path])
        filter_parts.append("[1:a]volume=0.45,afade=t=out:st=168.3:d=1.5[bgm]")
        mix_labels.append("[bgm]")
    else:
        filter_parts.append("anoisesrc=d=169.8:c=pink:r=44100:a=0.003,lowpass=f=400,afade=t=out:st=168.3:d=1.5[bgm]")
        mix_labels.append("[bgm]")

    # 3. 鋪排每段語音並進行毫秒級延遲對齊
    for idx, (start_sec, audio_path) in enumerate(clip_paths):
        in_idx = len(inputs) // 2
        inputs.extend(["-i", str(audio_path)])
        delay_ms = int(round(start_sec * 1000))
        lbl = f"[vo{idx}]"
        filter_parts.append(f"[{in_idx}:a]adelay={delay_ms}|{delay_ms},volume=1.05{lbl}")
        mix_labels.append(lbl)

    # 4. 混音總輸出 + 片尾 1.5 秒音畫平滑漸黑淡出 (normalize=0 防止音量除以 N)
    amix_str = "".join(mix_labels) + f"amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0:normalize=0,afade=t=out:st=168.3:d=1.5,alimiter=limit=0.95[aout]"
    vfilter_str = "fade=t=out:st=168.3:d=1.5[vout]"
    filter_complex = ";".join(filter_parts + [amix_str, f"[0:v]{vfilter_str}"])

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "19",
        "-c:a", "aac",
        "-b:a", "192k",
        video_out,
    ]
    print(f"🎬 正在渲染最終影片：{video_out} ...")
    subprocess.run(cmd, check=True)
    print(f"🎉 渲染完成！輸出檔案：{video_out}\n")

# ========================================================================
# 4. 主執行流程
# ========================================================================

def find_input_video():
    for cand in VIDEO_IN_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None

async def main():
    parser = argparse.ArgumentParser(description="NewsAnalyzer 日英多語系示範影片自動化產生器")
    parser.add_argument("--lang", choices=["ja", "en", "all"], default="all", help="選擇產出語言: ja, en, 或 all")
    parser.add_argument("--engine", choices=["edge", "gemini"], default="edge", help="選擇語音引擎: edge 或 gemini (預設: edge)")
    parser.add_argument("--bgm", default="demo/tech_ambient_bgm.wav", help="背景音樂 WAV/MP3 路徑")
    args = parser.parse_args()

    video_in = find_input_video()
    if not video_in:
        print("❌ 錯誤：找不到輸入母帶影片！請將 NewsAnalyzer_Demo_100Percent_Master.mp4 放置於當前目錄。")
        return

    targets = []
    if args.lang in ["ja", "all"]:
        targets.append(("ja", NARRATION_JA, "demo/NewsAnalyzer_Demo_JA.mp4", "ja-JP-NanamiNeural", "Sulafat"))
    if args.lang in ["en", "all"]:
        targets.append(("en", NARRATION_EN, "demo/NewsAnalyzer_Demo_EN.mp4", "en-US-JennyNeural", "Puck"))

    for lang_code, segments, out_name, edge_voice, gemini_voice in targets:
        cache_dir = Path(f"tts_cache_{lang_code}")
        if args.engine == "gemini" and GEMINI_API_KEY:
            clips = synth_gemini_tts(segments, lang_code, gemini_voice, cache_dir)
        else:
            clips = await synth_edge_tts(segments, lang_code, edge_voice, cache_dir)

        bgm = args.bgm if Path(args.bgm).exists() else None
        mux_multilingual_video(video_in, out_name, clips, bgm)

if __name__ == "__main__":
    asyncio.run(main())