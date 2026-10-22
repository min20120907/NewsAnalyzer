#!/usr/bin/env python3
"""
mix_multilingual_gemini.py
 NewsAnalyzer 國際版本（全日語 UI + 全日語解說 / 全英語 UI + 全英語解說）母帶混音：
1. 日文版：
   - 畫面：demo/NewsAnalyzer_Video_JA_Raw.mp4（100% 全日文 UI 與文字）
   - 語音：Gemini 3.8 Flash TTS 原生高品質日語（Sulafat）
   - 輸出：demo/NewsAnalyzer_Demo_JA.mp4
2. 英文版：
   - 畫面：demo/NewsAnalyzer_Video_EN_Raw.mp4（100% 全英文 UI 與文字）
   - 語音：Gemini 3.8 Flash TTS 原生高品質英語（Puck）
   - 輸出：demo/NewsAnalyzer_Demo_EN.mp4
3. 零聲音重疊：底片為純視訊軌，絕無任何前版中文殘留
4. 全軌鋪設 -26 dBFS 科技襯樂，片尾 1.5 秒平滑 Fade to Black
"""
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
BGM_PATH = BASE_DIR / "tech_ambient_bgm.wav"

CONFIGS = [
    {
        "lang": "ja",
        "video_in": BASE_DIR / "NewsAnalyzer_Video_JA_Raw.mp4",
        "video_out": BASE_DIR / "NewsAnalyzer_Demo_JA.mp4",
        "audio_dir": ROOT_DIR / "tts_cache_gemini_ja",
        "tracks": [
            ( 0.5, "ja_sc_1.wav", 1.25, "シナリオ1：主要メディアによる報道の分析"),
            (53.5, "ja_sc_2.wav", 1.15, "シナリオ2：クリックベイト見出しの抑制とファクト復元"),
            (86.5, "ja_sc_3.wav", 1.15, "シナリオ3：SNSの偽情報とBotアカウントのフィルタリング"),
            (114.0, "ja_sc_4.wav", 1.25, "シナリオ4：多言語実ニュース検証と総括")
        ]
    },
    {
        "lang": "en",
        "video_in": BASE_DIR / "NewsAnalyzer_Video_EN_Raw.mp4",
        "video_out": BASE_DIR / "NewsAnalyzer_Demo_EN.mp4",
        "audio_dir": ROOT_DIR / "tts_cache_gemini_en",
        "tracks": [
            ( 0.5, "en_sc_1.wav", 1.15, "Scenario 1: Mainstream News Corroboration"),
            (53.5, "en_sc_2.wav", 1.05, "Scenario 2: Clickbait Title Suppression & Restoration"),
            (86.5, "en_sc_3.wav", 1.05, "Scenario 3: Social Media Disinformation & Bot Blacklist"),
            (114.0, "en_sc_4.wav", 1.15, "Scenario 4: Multilingual Real News Verification & Conclusion")
        ]
    }
]

def render_language(cfg):
    lang = cfg["lang"].upper()
    v_in = str(cfg["video_in"])
    v_out = str(cfg["video_out"])
    audio_dir = cfg["audio_dir"]

    assert Path(v_in).exists(), f"Missing input video: {v_in}"
    print(f"\n=======================================================")
    print(f"🎬 正在渲染 {lang} 版（全 {lang} UI + Gemini 3.8 語音）...")
    print(f"   輸入視訊: {v_in}")
    print(f"   輸出目標: {v_out}")
    print(f"=======================================================")

    inputs = ["-i", v_in, "-i", str(BGM_PATH)]
    processed_voices = []

    for t, fname, spd, desc in cfg["tracks"]:
        src_wav = audio_dir / fname
        assert src_wav.exists(), f"Missing audio: {src_wav}"
        proc_wav = audio_dir / f"proc_{fname}"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(src_wav),
            "-filter:a", f"silenceremove=start_periods=1:start_threshold=-50dB,atempo={spd}",
            "-ar", "24000", "-ac", "1", str(proc_wav)
        ], check=True)
        res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(proc_wav)], capture_output=True, text=True)
        dur = float(res.stdout.strip())
        processed_voices.append((t, proc_wav, dur, desc))
        print(f"  [✔] t={t:5.1f}s | dur={dur:5.2f}s | end={t+dur:5.1f}s | {desc}")

    for t, w, dur, desc in processed_voices:
        inputs += ["-i", str(w)]

    parts = []
    # 鋪排各語音延遲
    for i, (t, w, dur, desc) in enumerate(processed_voices):
        idx = i + 2 # 0: video, 1: bgm
        delay_ms = int(t * 1000)
        parts.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[v{i}]")

    narr_mix = "".join(f"[v{i}]" for i in range(len(processed_voices)))
    parts.append(f"{narr_mix}amix=inputs={len(processed_voices)}:duration=longest:normalize=0[voice_bus]")
    # 襯樂控制在 -26 dBFS，語音飽滿突出，無任何原聲中文疊加
    parts.append("[1:a]volume=0.45[bgm]")
    parts.append("[voice_bus]volume=1.15[voice]")
    parts.append("[bgm][voice]amix=inputs=2:duration=first:normalize=0[amixed]")
    parts.append("[amixed]afade=t=out:st=162.0:d=1.5[aout]")
    parts.append("[0:v]fade=t=out:st=162.0:d=1.5[vout]")

    filter_complex = ";".join(parts)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "warning",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        v_out
    ]

    subprocess.run(cmd, check=True)
    print(f"🎉 渲染完成！輸出檔案：{v_out}")

def main():
    for cfg in CONFIGS:
        render_language(cfg)

if __name__ == "__main__":
    main()
