#!/usr/bin/env python3
"""
mix_multilingual_gemini.py (Studio Master Dynamic Sync Edition)
修復 NewsAnalyzer 日文版 (NewsAnalyzer_Demo_JA.mp4) 與英文版 (NewsAnalyzer_Demo_EN.mp4)
音軌、畫面與劇本內容的完全對齊。

【核心修復項目】
1. 劇本真實對齊 (Ground-Truth Script Alignment)：
   - S1：嚴格對齊畫面 NHK 能登半島地震 (JA) / PBS NewsHour 災後重建 (EN) 與 AP / Reuters / 共同通信，
     徹底根除指著日本/美國新聞講「花蓮與中央社」的嚴重指鹿為馬錯誤。
   - S2：點擊誘餌標題壓制、真主張復元卡片、D3 減點 18 分與 45 分要驗證壓制。
   - S3：X 平台機器人黑名單攔截、D2 強制歸零、D4 煽動修辭檢測、鎖定 25 分極度懷疑。
   - S4：無刷新多語言即時切換展示，對齊畫面點擊切換與四正交契約本地化，徹底根除講述「輸入 NHK/路透社新聞」的錯誤旁白。
2. 文本變更自動重新合成 (Hash-Validated TTS Synthesis)：
   - 記錄每個語音片段的文本，若劇本更新則自動清除快取重新合成，絕不沿用舊版錯誤錄音。
3. 物理音效真實合成 (Physical SFX Overlaid to Visual Events)：
   - 捨棄生硬正弦波嗶嗶聲，採用 24kHz 高質感 UI 音效（快門、點擊、結果叮咚、還原卡片提示、警報音）。
   - 音效錨點嚴格對齊畫面事件的真實觸發秒數。
4. 動態視窗語速調節 (Dynamic Tempo Fitting) 與結尾淡出：
   - 依據畫面各步驟視窗動態調節語速，畫面到哪、聲音講到哪，結尾 1.5 秒平滑淡出。
"""

import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
BGM_PATH = BASE_DIR / "tech_ambient_bgm.wav"

# ==============================================================================
# 19 個原子級真實時間軸定義（100% 嚴格匹配畫面視覺動作與步驟）
# ==============================================================================
JA_ATOMIC_CUES = [
    # --- Scenario 1: 能登半島地震復興 NHK 報道分析 ---
    {
        "id": "ja_s1_01_intro",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S1 簡報開場",
        "text": "シナリオ一、主要メディアによる報道の分析です。公共放送の信頼性を多次元から検証します。"
    },
    {
        "id": "ja_s1_02_input",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S1 輸入能登半島地震 NHK 報導網址",
        "text": "能登半島地震の復旧に関するNHKの報道URLを入力し、分析を開始します。"
    },
    {
        "id": "ja_s1_03_result",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S1 結果卡片出爐 (88.5分 高信頼性)",
        "text": "分析結果が出力され、総合スコアは88.5点、高信頼性と判定されました。"
    },
    {
        "id": "ja_s1_04_d1_d2",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S1 檢視 D1 與 D2 相互佐證",
        "text": "D1で虚偽はなく、D2では通信社による裏付けを検知しています。"
    },
    {
        "id": "ja_s1_05_d3_d4",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S1 D3 見出し忠実度 & D4 修辞安全性 92%",
        "text": "D3の見出し忠実度とD4の表現安全性は、ともに92パーセントを維持しています。"
    },
    {
        "id": "ja_s1_06_pipeline",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S1 透明計分管線融合 (規則 85 + AI 95)",
        "text": "透明な計算パイプラインにより、客観ルールとローカルAI推論が融合され、明確な根拠が示されます。"
    },

    # --- Scenario 2: 釣り見出しの抑制とファクト復元 ---
    {
        "id": "ja_s2_01_intro",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S2 簡報開場",
        "text": "シナリオ二、クリックベイト見出しの抑制と真の主張の復元です。"
    },
    {
        "id": "ja_s2_02_input",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S2 輸入煽動健康點擊誘餌標題",
        "text": "典型的な煽り釣り記事を入力し、分析を開始します。"
    },
    {
        "id": "ja_s2_02_card",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S2 黃色真主張復元卡片展開",
        "text": "真の主張復元カードが起動し、AIが誇張表現を排して客観的な事実を抽出します。"
    },
    {
        "id": "ja_s2_03_d3_d2",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S2 D3 見出し減點 18 分與 45 分要驗證壓制",
        "text": "D3見出し忠実度で18点減点され、まとめサイトの警告により総合スコアは45点に抑制されました。"
    },

    # --- Scenario 3: SNS偽情報とボットブラックリスト ---
    {
        "id": "ja_s3_01_intro",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S3 簡報開場",
        "text": "シナリオ三、SNSの偽情報とBotアカウントのフィルタリングです。"
    },
    {
        "id": "ja_s3_02_input",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S3 輸入警戒 X 貼文",
        "text": "警戒リストに登録されたXの投稿URLを入力し、照合を実行します。"
    },
    {
        "id": "ja_s3_03_result",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S3 命中黑名單佐證強制歸零",
        "text": "ソーシャルブラックリストに即座に一致しました。"
    },
    {
        "id": "ja_s3_03_d4",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S3 D4 扇動修辭檢測與 25 分極度懷疑鎖定",
        "text": "D2裏付けスコアはゼロに固定され、感情扇動プロパガンダにより25点と判定されました。"
    },

    # --- Scenario 4: 即時多言語切換與契約定義 ---
    {
        "id": "ja_s4_01_intro",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S4 簡報開場",
        "text": "シナリオ四、リアルタイム多言語切り替えと定義の実証です。"
    },
    {
        "id": "ja_s4_scroll_dimensions",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S4 檢視日語四直交指標",
        "text": "日本語化された4つの直交指標マトリクスを確認します。"
    },
    {
        "id": "ja_s4_02_switch",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S4 點擊切換為英語介面 (無刷新)",
        "text": "続いて英語UIへと瞬時に切り替えます。再読み込みなしで即座に反映されます。"
    },
    {
        "id": "ja_s4_03_matrix",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S4 檢視英語矩陣",
        "text": "英語化された指標マトリクスを確認後、再び日本語UIへと復帰します。"
    },
    {
        "id": "ja_s4_04_outro",
        "voice": "ja-JP-NanamiNeural",
        "desc": "S4 總結收尾與淡出",
        "text": "NewsAnalyzerは、透明な多次元分析と多言語対応により確かな情報環境を支えます。ご視聴ありがとうございました。"
    },
]

EN_ATOMIC_CUES = [
    # --- Scenario 1: PBS NewsHour Reconstruction Report ---
    {
        "id": "en_s1_01_intro",
        "voice": "en-US-ChristopherNeural",
        "desc": "S1 Briefing Intro",
        "text": "Scenario One: Mainstream news corroboration. Analyzing public broadcast credibility across orthogonal dimensions."
    },
    {
        "id": "en_s1_02_input",
        "voice": "en-US-ChristopherNeural",
        "desc": "S1 Input PBS Report URL & Click Analyze",
        "text": "We enter a news report URL from PBS NewsHour and click analyze."
    },
    {
        "id": "en_s1_03_result",
        "voice": "en-US-ChristopherNeural",
        "desc": "S1 Result Card Reveal (Score 88.5 Highly Credible)",
        "text": "The analysis completes: an overall credibility score of 88.5, rated Highly Credible."
    },
    {
        "id": "en_s1_04_d1_d2",
        "voice": "en-US-ChristopherNeural",
        "desc": "S1 D1 Fact-Check & D2 AP/Reuters Corroboration 88%",
        "text": "Dimension 1 confirms no dispute records, and Dimension 2 verifies simultaneous corroboration from AP and Reuters."
    },
    {
        "id": "en_s1_05_d3_d4",
        "voice": "en-US-ChristopherNeural",
        "desc": "S1 Focus D3 Fidelity & D4 Rhetorical Safety 92%",
        "text": "Both Dimension 3 headline fidelity and Dimension 4 rhetorical safety achieved 92 percent."
    },
    {
        "id": "en_s1_06_pipeline",
        "voice": "en-US-ChristopherNeural",
        "desc": "S1 Score Pipeline Breakdown (Rules 85 + AI 95)",
        "text": "The transparent scoring pipeline fuses rule metrics with on-device AI reasoning for clear explainability."
    },

    # --- Scenario 2: Clickbait Title Suppression & Claim Restoration ---
    {
        "id": "en_s2_01_intro",
        "voice": "en-US-ChristopherNeural",
        "desc": "S2 Briefing Intro",
        "text": "Scenario Two: Clickbait headline suppression and claim restoration."
    },
    {
        "id": "en_s2_02_input",
        "voice": "en-US-ChristopherNeural",
        "desc": "S2 Input Sensational Clickbait Article",
        "text": "We submit a sensational clickbait article and analyze."
    },
    {
        "id": "en_s2_02_card",
        "voice": "en-US-ChristopherNeural",
        "desc": "S2 Yellow Restored Claim Card Reveal",
        "text": "The restored claim card immediately activates, stripping away sensational hooks to present objective core facts."
    },
    {
        "id": "en_s2_03_d3_d2",
        "voice": "en-US-ChristopherNeural",
        "desc": "S2 D3 -18 Penalty & Score Capped at 45 (Unverified)",
        "text": "Dimension 3 applies an 18-point penalty for distortion, strictly capping the final rating at 45 as Unverified."
    },

    # --- Scenario 3: Social Media Disinformation & Bot Blacklist ---
    {
        "id": "en_s3_01_intro",
        "voice": "en-US-ChristopherNeural",
        "desc": "S3 Briefing Intro",
        "text": "Scenario Three: Social media disinformation and bot blacklist filtering."
    },
    {
        "id": "en_s3_02_input",
        "voice": "en-US-ChristopherNeural",
        "desc": "S3 Input Flagged X Post URL",
        "text": "We enter a post URL from a monitored propaganda account on X."
    },
    {
        "id": "en_s3_03_result",
        "voice": "en-US-ChristopherNeural",
        "desc": "S3 Blacklist Match Zeroes Corroboration",
        "text": "The account hits the social blocklist immediately."
    },
    {
        "id": "en_s3_03_d4",
        "voice": "en-US-ChristopherNeural",
        "desc": "S3 D4 Rhetorical Risk & Locked to 25 Highly Suspicious",
        "text": "The corroboration index is forced to zero, locking the final rating at 25 as Highly Suspicious."
    },

    # --- Scenario 4: Instant Multilingual UI Switch ---
    {
        "id": "en_s4_01_intro",
        "voice": "en-US-ChristopherNeural",
        "desc": "S4 Briefing Intro",
        "text": "Scenario Four: Instant multilingual localization."
    },
    {
        "id": "en_s4_scroll_dimensions",
        "voice": "en-US-ChristopherNeural",
        "desc": "S4 Review English Dimensions",
        "text": "Reviewing the four orthogonal dimensions in the English interface."
    },
    {
        "id": "en_s4_02_switch",
        "voice": "en-US-ChristopherNeural",
        "desc": "S4 Switch Seamlessly to Japanese UI",
        "text": "We switch seamlessly to Japanese, updating all dimension metrics in real time."
    },
    {
        "id": "en_s4_03_matrix",
        "voice": "en-US-ChristopherNeural",
        "desc": "S4 Verify Japanese Matrix & Return to English",
        "text": "After verifying the Japanese matrix and failure boundaries, we return to the English interface."
    },
    {
        "id": "en_s4_04_outro",
        "voice": "en-US-ChristopherNeural",
        "desc": "S4 Concluding Summary & Outro",
        "text": "NewsAnalyzer delivers transparent, trustworthy news verification across languages. Thank you for watching."
    },
]

CONFIGS = [
    {
        "lang": "ja",
        "video_in": BASE_DIR / "NewsAnalyzer_Video_JA_Raw.mp4",
        "fallback_video_in": BASE_DIR / "newsanalyzer_demo_1080p.mp4",
        "video_out": BASE_DIR / "NewsAnalyzer_Demo_JA.mp4",
        "audio_dir": ROOT_DIR / "tts_cache_gemini_ja",
        "timestamp_log": BASE_DIR / "timestamps_ja.json",
        "cues": JA_ATOMIC_CUES,
    },
    {
        "lang": "en",
        "video_in": BASE_DIR / "NewsAnalyzer_Video_EN_Raw.mp4",
        "fallback_video_in": BASE_DIR / "newsanalyzer_demo_1080p.mp4",
        "video_out": BASE_DIR / "NewsAnalyzer_Demo_EN.mp4",
        "audio_dir": ROOT_DIR / "tts_cache_gemini_en",
        "timestamp_log": BASE_DIR / "timestamps_en.json",
        "cues": EN_ATOMIC_CUES,
    },
]


def probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def has_audio_stream(path: Path) -> bool:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return bool(res.stdout.strip())


def build_atempo_chain(speed: float) -> str:
    filters = []
    curr = float(speed)
    while curr > 2.0:
        filters.append("atempo=2.0")
        curr /= 2.0
    while curr < 0.5:
        filters.append("atempo=0.5")
        curr /= 0.5
    filters.append(f"atempo={curr:.4f}")
    return ",".join(filters)


def synthesize_tts_if_needed(cue: dict, raw_wav: Path):
    """
    合成語音檔，並以文字快取檔 (.txt) 比對內容。
    若劇本文字有所變更，自動重新合成，徹底杜絕舊版殘留。
    """
    txt_file = raw_wav.with_suffix(".txt")
    if raw_wav.exists() and txt_file.exists():
        if txt_file.read_text(encoding="utf-8").strip() == cue["text"].strip():
            return

    raw_wav.parent.mkdir(parents=True, exist_ok=True)
    raw_wav.unlink(missing_ok=True)
    tmp_mp3 = raw_wav.with_suffix(".mp3")

    print(f"  [TTS] 正在合成原子語音 {cue['id']} ({cue['desc']})...")
    edge_bin = shutil.which("edge-tts") or shutil.which("edge-tts", path=str(Path(sys.executable).parent))
    tts_cmd = [edge_bin] if edge_bin else [sys.executable, "-m", "edge_tts"]
    try:
        subprocess.run(
            [
                *tts_cmd,
                "--voice", cue["voice"],
                "--text", cue["text"],
                "--write-media", str(tmp_mp3),
            ],
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(tmp_mp3),
                "-ar", "24000", "-ac", "1",
                str(raw_wav),
            ],
            check=True,
        )
        tmp_mp3.unlink(missing_ok=True)
        txt_file.write_text(cue["text"].strip(), encoding="utf-8")
    except Exception as e:
        raise RuntimeError(
            f"無法合成語音檔 {raw_wav} ({e})。請確認已安裝 edge-tts：`pip install edge-tts`"
        ) from e


def apply_recorded_timestamps(cues: list, timestamp_log: Path, video_duration: float, is_ja: bool = True) -> list:
    """
    從 automation_runner 輸出的真實步驟時間戳記與 SFX 點擊記錄，
    精確計算 19 個原子步驟的畫面觸發秒數與視窗長度。
    """
    data = json.loads(timestamp_log.read_text(encoding="utf-8"))
    ts_map = data.get("timestamps", {})
    sfx_list = data.get("sfx", [])

    # 找出情境 4 語系切換與復原點擊時刻 (第 1 次點擊為切換，第 2 次點擊為復原)
    lang_clicks = [s["t"] for s in sfx_list if "data-lang-btn" in s.get("desc", "")]
    if len(lang_clicks) >= 2:
        switch_click_t = lang_clicks[0]
        return_click_t = lang_clicks[1]
    else:
        switch_click_t = 134.14 if is_ja else 140.58
        return_click_t = 145.83 if is_ja else 151.84

    time_anchors = {
        "s1_01_intro": ts_map["s1_01_intro"] + 0.20,
        "s1_02_input": ts_map["s1_02_input"] + 0.20,
        "s1_03_result": ts_map["s1_03_result"] + 0.30,
        "s1_04_d1_d2": ts_map["s1_04_d1_d2"] + 0.20,
        "s1_05_d3_d4": ts_map["s1_05_d3_d4"] + 0.20,
        "s1_06_pipeline": ts_map["s1_06_pipeline"] + 0.20,
        "s2_01_intro": ts_map["s2_01_intro"] + 0.20,
        "s2_02_input": ts_map["s2_02_input"] + 0.20,
        "s2_02_card": ts_map["s2_02_card"] + 0.30,
        "s2_03_d3_d2": ts_map["s2_03_d3_d2"] + 0.20,
        "s3_01_intro": ts_map["s3_01_intro"] + 0.20,
        "s3_02_input": ts_map["s3_02_input"] + 0.20,
        "s3_03_result": ts_map["s3_03_result"] + 0.30,
        "s3_03_d4": ts_map["s3_03_d4"] + 0.20,
        "s4_01_intro": ts_map["s4_01_intro"] + 0.20,
        "s4_scroll_dimensions": ts_map["s4_scroll_dimensions"] + 0.20,
        "s4_02_switch": switch_click_t + 0.20,
        "s4_03_matrix": ts_map["s4_03_matrix"] + 0.20,
        "s4_04_outro": return_click_t + 0.30,
    }

    updated = []
    for c in cues:
        uc = dict(c)
        cid = uc["id"]
        short_id = cid[3:] if cid.startswith(("ja_", "en_")) else cid
        if short_id in time_anchors:
            uc["t"] = round(time_anchors[short_id], 2)
        else:
            raise KeyError(f"未定義的時間錨點 ID: {short_id} (完整 ID: {cid})")
        updated.append(uc)

    print(f"  [Sync] 已成功由真實錄影時間戳記 ({timestamp_log.name}) 對齊 19 個原子步驟")

    for i in range(len(updated) - 1):
        assert updated[i]["t"] < updated[i+1]["t"], (
            f"時間軸順序錯誤！{updated[i]['id']} (t={updated[i]['t']}) >= {updated[i+1]['id']} (t={updated[i+1]['t']})"
        )
        next_t = updated[i+1]["t"]
        updated[i]["max_window"] = max(2.0, round(next_t - updated[i]["t"] - 0.20, 2))

    updated[-1]["max_window"] = max(4.0, round(video_duration - updated[-1]["t"] - 1.5, 2))
    return updated


def prepare_atomic_voice(cue: dict, audio_dir: Path) -> tuple[float, Path, float, float, str]:
    """
    1. 驗證快取並合成語音
    2. 去除開頭與結尾靜音
    3. 依據步驟可用視窗 (max_window) 動態調節語速 (atempo)
    """
    raw_wav = audio_dir / f"{cue['id']}_raw.wav"
    trimmed_wav = audio_dir / f"{cue['id']}_trimmed.wav"
    proc_wav = audio_dir / f"{cue['id']}_synced.wav"

    synthesize_tts_if_needed(cue, raw_wav)

    # 移除前後空白靜音
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(raw_wav),
            "-filter:a", (
                "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.04,"
                "areverse,"
                "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.06,"
                "areverse"
            ),
            "-ar", "24000", "-ac", "1",
            str(trimmed_wav),
        ],
        check=True,
    )

    raw_dur = probe_duration(trimmed_wav)
    max_win = float(cue["max_window"])

    target_max_dur = max(1.8, max_win - 0.15)
    if raw_dur > target_max_dur:
        optimal_speed = round(raw_dur / target_max_dur, 3)
    else:
        optimal_speed = 1.00

    optimal_speed = max(1.0, min(optimal_speed, 1.60))
    atempo_filter = build_atempo_chain(optimal_speed)

    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(trimmed_wav),
            "-filter:a", atempo_filter,
            "-ar", "24000", "-ac", "1",
            str(proc_wav),
        ],
        check=True,
    )

    final_dur = probe_duration(proc_wav)
    return cue["t"], proc_wav, final_dur, optimal_speed, cue["desc"]


def generate_physical_sfx_track(sfx_events: list, out_path: Path, duration: float, sr: int = 24000):
    """
    合成專業級真實物理音效軌道 (UI Click, Ding, Chime, Alert, Shutter)
    """
    n = int((duration + 2.0) * sr)
    audio = np.zeros(n, dtype=np.float32)

    def make_click():
        dur = 0.030
        tt = np.linspace(0, dur, int(sr * dur), endpoint=False)
        return (np.sin(2 * np.pi * 2400 * tt) * np.exp(-tt * 180) * 0.6 +
                np.sin(2 * np.pi * 1200 * tt) * np.exp(-tt * 90) * 0.3).astype(np.float32)

    def make_ding():
        dur = 0.550
        tt = np.linspace(0, dur, int(sr * dur), endpoint=False)
        return ((np.sin(2 * np.pi * 1318.5 * tt) * 0.5 +
                 np.sin(2 * np.pi * 1568.0 * tt) * 0.4 +
                 np.sin(2 * np.pi * 1975.5 * tt) * 0.1) * np.exp(-tt * 5.0)).astype(np.float32)

    def make_chime():
        dur = 0.420
        tt = np.linspace(0, dur, int(sr * dur), endpoint=False)
        return ((np.sin(2 * np.pi * 880.0 * tt) * 0.6 +
                 np.sin(2 * np.pi * 1108.7 * tt) * 0.4) * np.exp(-tt * 6.5)).astype(np.float32)

    def make_alert():
        dur = 0.400
        tt = np.linspace(0, dur, int(sr * dur), endpoint=False)
        return ((np.sin(2 * np.pi * 440.0 * tt) * 0.5 +
                 np.sin(2 * np.pi * 523.2 * tt) * 0.5) * np.exp(-tt * 5.5)).astype(np.float32)

    def make_shutter():
        dur = 0.250
        n_pts = int(sr * dur)
        tt = np.linspace(0, dur, n_pts, endpoint=False)
        noise = np.random.uniform(-1, 1, n_pts)
        env = np.sin(np.pi * (tt / dur)) ** 2
        filtered = np.convolve(noise, np.ones(8) / 8.0, mode='same')
        return (filtered * env * 0.35).astype(np.float32)

    generators = {
        "click": make_click,
        "ding": make_ding,
        "chime": make_chime,
        "alert": make_alert,
        "shutter": make_shutter,
    }

    for ev in sfx_events:
        etype = ev.get("type", "click")
        t = float(ev.get("t", 0.0))
        gen_fn = generators.get(etype, make_click)
        waveform = gen_fn()
        start = int(t * sr)
        if start < 0 or start >= n:
            continue
        end = min(start + len(waveform), n)
        audio[start:end] += waveform[:end - start]

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio / peak * 0.45

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((audio * 32767).astype(np.int16).tobytes())
    print(f"  [SFX] 成功生成高質感物理音效軌道：{out_path.name} ({len(sfx_events)} 處音效錨點)")


def render_language(cfg: dict):
    lang = cfg["lang"].upper()
    v_in = cfg["video_in"]
    if not v_in.exists() and cfg.get("fallback_video_in") and cfg["fallback_video_in"].exists():
        print(f"[{lang}] 找不到 {v_in.name}，使用備用輸入 {cfg['fallback_video_in'].name}")
        v_in = cfg["fallback_video_in"]

    if not v_in.exists():
        print(f"[{lang}] 錯誤：找不到輸入影片 {v_in}，跳過。")
        return

    v_out = cfg["video_out"]
    audio_dir = cfg["audio_dir"]
    audio_dir.mkdir(parents=True, exist_ok=True)

    video_dur = probe_duration(v_in)
    has_bgm = BGM_PATH.exists()

    print(f"\n==========================================")
    print(f"[{lang}] 開始處理國際版母帶混音：{v_in.name} (時長: {video_dur:.2f}s)")
    print(f"==========================================")

    cues = apply_recorded_timestamps(cfg["cues"], cfg["timestamp_log"], video_dur, is_ja=(lang == "ja"))

    processed_voices = []
    running_end_time = 0.0
    for cue in cues:
        t, proc_wav, dur, spd, desc = prepare_atomic_voice(cue, audio_dir)
        effective_t = max(t, round(running_end_time + 0.12, 2))
        running_end_time = effective_t + dur
        processed_voices.append((effective_t, proc_wav, dur, spd, desc))
        print(
            f"  ✓ [{cue['id']}] 落點: {effective_t:6.2f}s ~ {running_end_time:6.2f}s "
            f"(時長: {dur:4.2f}s, 語速: {spd:4.2f}x) | {desc}"
        )

    # 讀取或建立物理音效錨點
    sfx_events = []
    if cfg["timestamp_log"].exists():
        try:
            data = json.loads(cfg["timestamp_log"].read_text(encoding="utf-8"))
            sfx_events = data.get("sfx", [])
        except Exception:
            pass

    if not sfx_events:
        # 預設物理音效錨點
        sfx_events = [
            {"type": "shutter", "t": 0.0},
            {"type": "click", "t": 10.8},
            {"type": "ding", "t": 12.0},
            {"type": "shutter", "t": 39.0},
            {"type": "click", "t": 48.8},
            {"type": "chime", "t": 51.0},
            {"type": "shutter", "t": 72.0},
            {"type": "click", "t": 82.8},
            {"type": "alert", "t": 85.0},
            {"type": "shutter", "t": 97.0},
            {"type": "click", "t": 110.2},
            {"type": "chime", "t": 112.0},
            {"type": "click", "t": 124.6},
            {"type": "ding", "t": 126.0},
        ]

    sfx_path = audio_dir / "sfx_track.wav"
    generate_physical_sfx_track(sfx_events, sfx_path, video_dur)
    has_sfx_track = sfx_path.exists()

    inputs = ["-i", str(v_in)]
    bgm_input_idx = None
    if has_bgm:
        bgm_input_idx = len(inputs) // 2
        inputs.extend(["-i", str(BGM_PATH)])

    voice_start_idx = len(inputs) // 2
    for _, proc_wav, _, _, _ in processed_voices:
        inputs.extend(["-i", str(proc_wav)])

    sfx_input_idx = None
    if has_sfx_track:
        sfx_input_idx = len(inputs) // 2
        inputs.extend(["-i", str(sfx_path)])

    parts = []
    voice_labels = []
    for i, (t, _, _, _, _) in enumerate(processed_voices):
        input_idx = voice_start_idx + i
        delay_ms = int(round(t * 1000))
        parts.append(f"[{input_idx}:a]adelay={delay_ms}|{delay_ms}[v{i}];")
        voice_labels.append(f"[v{i}]")

    num_voices = len(processed_voices)
    parts.append(
        f"{''.join(voice_labels)}amix=inputs={num_voices}:duration=longest:dropout_transition=0:normalize=0[voice_bus];"
    )
    parts.append("[voice_bus]volume=1.20[voice];")

    mix_streams = []
    if has_sfx_track and sfx_input_idx is not None:
        parts.append(f"[{sfx_input_idx}:a]volume=0.35[sfx];")
        mix_streams.append("[sfx]")
    if has_bgm and bgm_input_idx is not None:
        parts.append(f"[{bgm_input_idx}:a]volume=0.35[bgm];")
        mix_streams.append("[bgm]")
    mix_streams.append("[voice]")

    parts.append(
        f"{''.join(mix_streams)}amix=inputs={len(mix_streams)}:duration=first:dropout_transition=2:normalize=0[amixed];"
    )

    fade_start = max(1.0, round(video_dur - 1.5, 2))
    parts.append(f"[amixed]afade=t=out:st={fade_start}:d=1.5[aout];")
    parts.append(f"[0:v]fade=t=out:st={fade_start}:d=1.5[vout]")

    filter_complex = "".join(parts)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "warning",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(v_out),
    ]

    print(f"[{lang}] 正在執行 FFmpeg 終審混音與母帶輸出 -> {v_out.name} ...")
    subprocess.run(cmd, check=True)
    print(f"[{lang}] 🎉 渲染完成！輸出檔案：{v_out} ({v_out.stat().st_size / 1024 / 1024:.1f} MB)")


def main():
    for cfg in CONFIGS:
        render_language(cfg)


if __name__ == "__main__":
    main()
