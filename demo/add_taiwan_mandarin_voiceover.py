#!/usr/bin/env python3
"""
add_taiwan_mandarin_voiceover.py

Adds a Taiwan Mandarin (zh-TW) voiceover to a demo MP4 using Gemini TTS.
Each narration line is generated as WAV, then mixed over the video with ffmpeg.

Usage:
  export GEMINI_API_KEY="..."
  python add_taiwan_mandarin_voiceover.py \
      --video demo/newsanalyzer_demo_1080p.mp4 \
      --output demo/newsanalyzer_demo_1080p_narrated.mp4 \
      --script narration.json

narration.json format:
  [
    {"t": 5.0,  "text": "歡迎來到 NewsAnalyzer 示範影片"},
    {"t": 25.0, "text": "現在我們輸入一條新聞標題"},
    ...
  ]
  "t" = start time in seconds within the video.
"""

import argparse, base64, json, os, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
VOICE = os.environ.get("NA_TTS_VOICE", "Luna")          # default TTS voice
MODEL = os.environ.get("NA_TTS_MODEL", "gemini-2.5-flash-preview-tts")
CACHE_DIR = Path("tts_cache")

def tts(text: str, voice: str, model: str, api_key: str, cache_key: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    out = CACHE_DIR / f"{cache_key}.wav"
    if out.exists():
        return out

    url = API.format(model=model)
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice}
                }
            }
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  TTS error: {e.code} {e.read().decode()[:200]}", file=sys.stderr)
        raise

    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    audio = None
    for p in parts:
        if "inlineData" in p:
            audio = base64.b64decode(p["inlineData"]["data"])

    if audio is None:
        raise RuntimeError(f"No audio in response: {str(data)[:200]}")

    # Some models return MP3; convert to WAV
    out_raw = CACHE_DIR / f"{cache_key}.raw"
    out_raw.write_bytes(audio)
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(out_raw), "-acodec", "pcm_s16le", "-ar", "24000", str(out)],
        capture_output=True,
    )
    if r.returncode != 0:
        # might already be WAV
        if out.exists():
            pass
        else:
            out_raw.rename(out)
    out_raw.unlink(missing_ok=True)
    return out


def build_mix_filter(lines: list[dict], wavs: list[Path]) -> str:
    """Build an ffmpeg filtergraph: one audio track delayed per narration line."""
    parts = []
    for i, (w, ln) in enumerate(zip(wavs, lines)):
        parts.append(f"[{i}:a]adelay={int(ln['t']*1000)}|{int(ln['t']*1000)}[a{i}]")
    mix_inputs = "".join(f"[a{i}]" for i in range(len(wavs)))
    parts.append(f"{mix_inputs}amix=inputs={len(wavs)}:duration=longest[mix]")
    return ";".join(parts)


def main():
    ap = argparse.ArgumentParser(description="Add Taiwan Mandarin voiceover to a demo video")
    ap.add_argument("--video", required=True, help="Input MP4")
    ap.add_argument("--script", required=True, help="JSON file: [{t: float, text: str}, ...]")
    ap.add_argument("--output", default=None, help="Output MP4 (default: <video>_narrated.mp4)")
    ap.add_argument("--voice", default=VOICE, help=f"TTS voice name (default: {VOICE})")
    ap.add_argument("--model", default=MODEL, help=f"TTS model (default: {MODEL})")
    ap.add_argument("--volume", type=float, default=0.85, help="Narration volume (0-1)")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("ERROR: set GEMINI_API_KEY")

    video = Path(args.video)
    if not video.exists():
        sys.exit(f"ERROR: {video} not found")

    lines = json.loads(Path(args.script).read_text())
    print(f"Narration lines: {len(lines)}")

    # Generate all WAVs
    wavs = []
    for i, ln in enumerate(lines):
        ck = f"line_{i:03d}_{abs(hash(ln['text'])):08x}"
        print(f"  [{i}] t={ln['t']:.1f}s  {ln['text'][:40]}")
        wavs.append(tts(ln["text"], args.voice, args.model, api_key, ck))

    # Build ffmpeg command
    out = Path(args.output or str(video) + "_narrated.mp4")
    inputs = [str(video)]
    for w in wavs:
        inputs.append(str(w))

    filter_str = build_mix_filter(lines, wavs)
    # Volume control on narration mix
    filter_str += f";[mix]volume={args.volume}[vout]"
    # Map: video from input 0, audio = original video audio (input 0) + narration
    filter_str += f";[0:a][vout]amix=inputs=2:duration=first[aout]"

    cmd = (
        ["ffmpeg", "-y", "-loglevel", "warning"]
        + inputs
        + [
            "-filter_complex", filter_str,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(out),
        ]
    )
    print(f"\nffmpeg: {out.name}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-500:], file=sys.stderr)
        sys.exit(r.returncode)

    print(f"Done → {out}")


if __name__ == "__main__":
    main()
