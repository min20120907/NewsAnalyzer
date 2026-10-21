#!/usr/bin/env python3
"""
tts_remaining.py — generate only missing TTS lines with long backoff, then mix.
Run after the quota window resets.
"""
import json, os, subprocess, sys, time, urllib.request, urllib.error, base64
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-lite-tts:generateContent"
KEY = os.environ.get("GEMINI_API_KEY", "")
VOICE = "Charon"
CACHE = Path("/home/min20120907/Documents/Web_and_App_Development/NewsAnalyzer/tts_cache")
VIDEO = "/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4"
OUT   = "/home/min20120907/Documents/Web_and_App_Development/NewsAnalyzer/demo/newsanalyzer_demo_1080p_narrated.mp4"
SCRIPT = "/home/min20120907/Documents/Web_and_App_Development/NewsAnalyzer/demo/narration_zh_tw.json"
VOLUME = 0.85

assert KEY, "set GEMINI_API_KEY"
lines = json.loads(Path(SCRIPT).read_text())
CACHE.mkdir(exist_ok=True)

def gen(i, text):
    wav = CACHE / f"line_{i:03d}.wav"
    if wav.exists():
        print(f"  [{i}] cached")
        return wav
    body = {"contents":[{"parts":[{"text":text}]}],
            "generationConfig":{"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":VOICE}}}}}
    for attempt in range(12):
        req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                     headers={"x-goog-api-key":KEY, "Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            p = d["candidates"][0]["content"]["parts"][0]
            audio = base64.b64decode(p["inlineData"]["data"])
            raw = CACHE / f"line_{i:03d}.raw"
            raw.write_bytes(audio)
            subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(raw),
                            "-acodec","pcm_s16le","-ar","24000",str(wav)])
            raw.unlink(missing_ok=True)
            print(f"  [{i}] OK")
            return wav
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 11:
                wait = min(60, 15 * (attempt + 1))
                print(f"  [{i}] 429, wait {wait}s")
                time.sleep(wait)
                continue
            print(f"  [{i}] FAIL {e.code}")
            raise

# Generate
wavs = []
for i, ln in enumerate(lines):
    print(f"  [{i}] t={ln['t']:.1f}s  {ln['text'][:40]}")
    wavs.append(gen(i, ln["text"]))
    time.sleep(15)

# Mix
inputs = [VIDEO] + [str(w) for w in wavs]
parts = []
for i, ln in enumerate(lines):
    parts.append(f"[{i+1}:a]adelay={int(ln['t']*1000)}|{int(ln['t']*1000)}[a{i}]")
mix = "".join(f"[a{i}]" for i in range(len(wavs)))
f = ";".join(parts + [f"{mix}amix=inputs={len(wavs)}:duration=longest[mix]",
                     f"[mix]volume={VOLUME}[narr]"])
cmd = ["ffmpeg","-y","-loglevel","warning"] + inputs + [
    "-filter_complex", f,
    "-map","0:v","-map","[narr]",
    "-c:v","copy","-c:a","aac","-b:a","192k","-movflags","+faststart",OUT]
print("\nMixing →", Path(OUT).name)
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr[-400:], file=sys.stderr); sys.exit(1)
print("Done →", OUT)
