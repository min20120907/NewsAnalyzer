# NewsAnalyzer

Trilingual (zh-TW / en / ja) fake-news reliability analyzer. A Flask web app that scores a headline or article across four orthogonal dimensions and produces a transparent, explainable reliability score (0–100).

**Live demo:** https://satin-jon-etc-uncertainty.trycloudflare.com

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  web/index.html  (Vanilla JS, zh/en/ja i18n)                │
└──────────────────────┬──────────────────────────────────────┘
                       │ POST /analyze  /deep_analyze  /extract_media
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  python/fake_news_server_new.py   (Flask, :5000)            │
│                                                              │
│  D1  Source credibility      (domain blocklist + whitelist) │
│  D2  Textual reliability     (SBERT similarity + sentiment) │
│  D3  Contextual consistency  (cross-article corroboration)  │
│  D4  Title-bait detection    (LLM classifier, Qwen3.8)      │
│                                                              │
│  Transparent weighted score → 0–100                         │
└──────────────────────────────────────────────────────────────┘
```

## Quick start

```bash
# 1. Python venv
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 2. Environment (adjust LLM endpoint to your setup)
export QWEN_URL=http://127.0.0.1:8088/v1/chat/completions
export QWEN_MODEL=qwen3.8-27b-fastmtp
# export GOOGLE_CSE_KEY=your-key   # optional; falls back to Bing / RSS

# 3. Run
.venv/bin/python python/fake_news_server_new.py
# → http://localhost:5000
```

## Project layout

| Path | Contents |
|------|----------|
| `python/fake_news_server_new.py` | Flask server — all endpoints, scoring pipeline, SBERT, LLM calls |
| `python/orthogonal_scorer.py` | D1–D4 scoring logic |
| `web/index.html` | Frontend (single-file Vanilla JS, zh/en/ja i18n) |
| `demo/` | Hybrid demo — Playwright runner + cinematic overlay + scenario engine |
| `data/domains/` | Domain blocklists, whitelist, social blocklist (hot-reloaded) |
| `data/eval/` | Evaluation datasets & baseline results |
| `scripts/` | Utility scripts (metrics collection, i18n verification, etc.) |
| `fb-extension/` | Chrome extension (Facebook fake-news highlighter) |
| `PROJECT_HANDOFF.md` | Full system documentation — single source of truth for external AI |

## Scoring dimensions

- **D1 — Source credibility**
  Domain blocklist (93k+ domains), social blocklist (19 known disinfo accounts), whitelist (43 verified outlets). Hot-reloaded from `data/domains/`.

- **D2 — Textual reliability**
  SBERT semantic similarity against corroborating articles + sentiment pipeline (CPU).

- **D3 — Contextual consistency**
  Cross-article corroboration score.

- **D4 — Title-bait detection**
  LLM classifier (Qwen3.8 via FastMTP) — not regex.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `QWEN_URL` | `http://127.0.0.1:3000/v1/chat/completions` | LLM endpoint for deep analysis |
| `QWEN_MODEL` | `deepseek-chat` | Model name passed to LLM |
| `QWEN_SLOTS_URL` | `http://127.0.0.1:8088/slots` | Slot availability endpoint (skip if LLM busy) |
| `NEWSANALYZER_HOST` | `127.0.0.1` | Bind address |
| `NEWSANALYZER_PORT` | `5000` | Bind port |
| `NEWSANALYZER_DEBUG_USER` | `min20120907` | Debug console username |
| `NEWSANALYZER_DEBUG_PASSWORD` | `jefflin123` | Debug console password |
| `DEEP_ANALYZE_TIMEOUT` | `60` | Timeout (s) for LLM deep analysis |
| `DEEP_ANALYZE_SAMPLES` | `3` | Number of LLM samples for aggregation |
| `GOOGLE_CSE_KEY` | — | Google Custom Search API key (optional) |

## Demo (Hybrid Demo Architecture)

```bash
.venv/bin/python demo/automation_runner.py --mode record \
    --output demo/newsanalyzer_demo_1080p.mp4 --speed 1.2
```

Three modes: `live` (real LLM), `simulation` (mock results, no LLM), `record` (Playwright video, 1920×1080 h264).

## Chrome extension

[Chrome Web Store link](https://chrome.google.com/webstore/detail/news-analyzer/hedmeapammhcjoelaceokinbhgjiiifk)

## Contact

jefflin.je598@gmail.com — issues and PRs welcome.
