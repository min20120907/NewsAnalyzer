#!/bin/bash
# Generate remaining TTS lines (9-12) with long backoff, then mix
# Run: GEMINI_API_KEY=xxx bash demo/gen_remaining.sh
cd /home/min20120907/Documents/Web_and_App_Development/NewsAnalyzer

python3 -c "
import json, os, subprocess, time, urllib.request, urllib.error, base64
from pathlib import Path

API = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-lite-tts:generateContent'
KEY = os.environ['GEMINI_API_KEY']
CACHE = Path('tts_cache')
lines = json.loads(Path('demo/narration_zh_tw.json').read_text())

for i in [9, 10, 11, 12]:
    wav = CACHE / f'line_{i:03d}.wav'
    if wav.exists():
        print(f'  [{i}] cached', flush=True); continue
    body = {'contents':[{'parts':[{'text':lines[i]['text']}]}],
            'generationConfig':{'speechConfig':{'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':'Charon'}}}}}
    for attempt in range(40):
        req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                     headers={'x-goog-api-key':KEY,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            p = d['candidates'][0]['content']['parts'][0]
            audio = base64.b64decode(p['inlineData']['data'])
            raw = CACHE / f'line_{i:03d}.raw'
            raw.write_bytes(audio)
            subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(raw),
                            '-acodec','pcm_s16le','-ar','24000',str(wav)])
            raw.unlink(missing_ok=True)
            print(f'  [{i}] OK', flush=True); break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 39:
                wait = min(120, 30*(attempt+1))
                print(f'  [{i}] 429, wait {wait}s', flush=True)
                time.sleep(wait)
                continue
            print(f'  [{i}] FAIL {e.code}', flush=True); break
    time.sleep(20)

print('All lines done', flush=True)

# Now mix
VIDEO = '/home/min20120907/.hermes/cache/videos/video_b4252671ac56.mp4'
OUT = 'demo/newsanalyzer_demo_1080p_narrated.mp4'
wavs = [CACHE/f'line_{i:03d}.wav' for i in range(len(lines))]
wavs = [w for w in wavs if w.exists()]
inputs = ['-i', VIDEO]
for w in wavs: inputs += ['-i', str(w)]
parts = []
mix = ''
for k, ln in enumerate(lines):
    if not (CACHE/f'line_{k:03d}.wav').exists(): continue
    a = k+1
    parts.append(f'[{a}:a]adelay={int(ln[\"t\"]*1000)}|{int(ln[\"t\"]*1000)},volume=0.85[v{a}]')
    mix += f'[v{a}]'
f = ';'.join(parts + [f'{mix}amix=inputs={len([w for w in wavs if w.exists()])}:duration=longest[mix]',
                      '[mix]volume=0.85[narr]'])
cmd = ['ffmpeg','-y','-loglevel','warning'] + inputs + [
    '-filter_complex', f, '-map','0:v','-map','[narr]',
    '-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart', OUT]
subprocess.run(cmd, check=True)
print(f'Mixed {len(wavs)}/{len(lines)} lines -> {OUT}', flush=True)
"
