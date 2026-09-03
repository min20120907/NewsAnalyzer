# -*- coding: utf-8 -*-
"""
Fake‑News Reliability Server (GPU‑Ready, Batch‑Aware)
====================================================
* Optimised for Nvidia RTX 4090 / CUDA GPUs
* Keeps existing single‑article endpoint (/judge) working unchanged
* Adds **analyze_batch_article_data** for high‑throughput, GPU‑accelerated batch scoring
  (usable from offline scripts such as evaluate_analyzer_parallel.py)

Key Optimisations
-----------------
1. **Model on GPU:**  Transformers `pipeline` and Sentence‑Transformers model loaded
   directly on `cuda:0`.  If CUDA unavailable the code silently falls back to CPU.
2. **AMP** (`torch.autocast`) for FP16/BF16 automatic mixed precision when encoding
   sentences or running the sentiment pipeline.
3. **torch.compile()** (PyTorch 2.x) used to JIT‑optimise the SentenceTransformer
   model for additional speed.
4. **Batch Sentiment Inference** – the transformers pipeline is called with
   `batch_size=BATCH_SIZE`, eliminating Python‑level loops.
5. **Batch Similarity Encoding** – all texts are encoded in chunks and cosine
   similarity calculated fully on GPU.
6. **No duplicated model loads** – models are initialised once at import‑time and
   shared.

Usage
-----
* **Existing Flask API**:  `python fake_news_server_new_parallel.py`  → visit
  http://localhost:5000 and POST JSON to `/judge` (identical to legacy version).
* **Batch scoring in scripts:**

```python
from fake_news_server_new_parallel import analyze_batch_article_data
results = analyze_batch_article_data(
    titles=[...], urls=[...], contents=[...], batch_size=64
)
```

The returned list contains the same dictionaries as legacy `analyze_article_data`.
"""

import os, re, html, json, math, traceback, time, csv, io
from typing import List, Dict, Union, Optional
from datetime import datetime, timedelta
from urllib.parse import urlparse, unquote_plus, quote_plus

# 把本檔案所在目錄加入 sys.path，確保 factcheck_multi / cofacts_local 可 import
import sys as _sys
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in _sys.path:
    _sys.path.insert(0, _SCRIPT_DIR)

# 網路評論搜尋客戶端（Serper → free-search bing → Google News RSS）
# 失敗/無 key 時 web_search_client.search() 自動回退，web_results 為空 list
try:
    import web_search_client as _wsc
    WEB_SEARCH_AVAILABLE = True
except Exception as _e:
    _wsc = None
    WEB_SEARCH_AVAILABLE = False
    print(f"[judge] web_search_client import failed: {_e}")

# ---------------------------------------------------------------
# 1. Dependency Checks
# ---------------------------------------------------------------
try:
    from flask import Flask, request, make_response
    FLASK_AVAILABLE = True
except ImportError:
    print("[CRITICAL] Flask not installed – `pip install flask`.")
    raise

lib_errors = []
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    lib_errors.append("torch")

try:
    from transformers import pipeline, logging as hf_logging
    TRANSFORMERS_AVAILABLE = True
    hf_logging.set_verbosity_error()
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    lib_errors.append("transformers")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    lib_errors.append("requests")

try:
    from newspaper import Article, ArticleException
    NEWSPAPER3K_AVAILABLE = True
except ImportError:
    NEWSPAPER3K_AVAILABLE = False
    lib_errors.append("newspaper3k")

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from fb_session import get_facebook_post, extract_facebook_playwright
    FB_SESSION_AVAILABLE = True
    print("[Init] Facebook session management loaded.")
except ImportError as e:
    FB_SESSION_AVAILABLE = False
    print(f"[WARN] fb_session not available - Facebook session management disabled: {e}")

try:
    from cofacts_local import get_fact_check
    COFACTS_LOCAL_AVAILABLE = True
except ImportError:
    COFACTS_LOCAL_AVAILABLE = False
    print("[WARN] cofacts_local not available - fact_check/feedback/timeliness will be limited.")

try:
    from factcheck_multi import get_all_fact_checks
    MULTI_FC_AVAILABLE = True
except ImportError:
    get_all_fact_checks = None
    MULTI_FC_AVAILABLE = False
    print("[WARN] factcheck_multi not available - multi-source fact check disabled.")

try:
    from sentence_transformers import SentenceTransformer, util
    SENTENCE_TRANSFORMER_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMER_AVAILABLE = False
    lib_errors.append("sentence‑transformers")

if lib_errors:
    print("[WARN] Missing libs:", ", ".join(lib_errors))

# ---------------------------------------------------------------
# 2. GPU / Device Setup
# ---------------------------------------------------------------
DEVICE = "cpu"
# DEVICE = "cuda" if TORCH_AVAILABLE and torch.cuda.is_available() else "cpu"
if DEVICE == "cuda":
    torch.set_float32_matmul_precision("high")  # speedup on Ampere/ADA
    print("[Init] CUDA detected – using GPU acceleration.")
else:
    print("[Init] GPU not available – falling back to CPU.")

def _cuda_idx():
    """Return 0 if CUDA, else -1 (for transformers pipeline)."""
    return 0 if DEVICE == "cuda" else -1

# ---------------------------------------------------------------
# 3. Model Loading (once)
# ---------------------------------------------------------------
SENTIMENT_PIPELINE = None
SIMILARITY_MODEL   = None
MODEL_LABELS       = {}

sentiment_model_path  = "/home/min20120907/.cache/huggingface/hub/models--lxyuan--distilbert-base-multilingual-cased-sentiments-student/snapshots/cf991100d706c13c0a080c097134c05b7f436c45"
similarity_model_path = "/home/min20120907/.cache/huggingface/hub/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/snapshots/e8f8c211226b894fcb81acc59f3b34ba3efd5f42"

if TRANSFORMERS_AVAILABLE and TORCH_AVAILABLE:
    try:
        if not os.path.isdir(sentiment_model_path):
            raise FileNotFoundError(f"Sentiment model folder '{sentiment_model_path}' missing.")
        SENTIMENT_PIPELINE = pipeline(
            "text-classification",
            model=sentiment_model_path,
            device=_cuda_idx(),
            batch_size=64,
        )
        MODEL_LABELS = getattr(SENTIMENT_PIPELINE.model.config, "id2label", {})
        print("[Init] Sentiment pipeline loaded →", DEVICE)
    except Exception as e:
        print("[ERR] Loading sentiment model:", e)
        SENTIMENT_PIPELINE = None

if SENTENCE_TRANSFORMER_AVAILABLE and TORCH_AVAILABLE:
    try:
        if not os.path.isdir(similarity_model_path):
            raise FileNotFoundError(f"Sentence‑Transformer folder '{similarity_model_path}' missing.")
        SIMILARITY_MODEL = SentenceTransformer(similarity_model_path, device=DEVICE)
        # PyTorch 2.x compile – ignore on earlier versions
        try:
            SIMILARITY_MODEL = torch.compile(SIMILARITY_MODEL, mode="reduce-overhead")
            print("[Init] SentenceTransformer compiled with torch.compile().")
        except Exception:
            pass
        print("[Init] Similarity model loaded →", DEVICE)
    except Exception as e:
        print("[ERR] Loading similarity model:", e)
        SIMILARITY_MODEL = None

# 把已載入的 similarity model 注入 cofacts_local，做本地近鄰檢索（避免重複佔用資源）
try:
    from cofacts_local import set_sbert_model
    if SIMILARITY_MODEL is not None:
        set_sbert_model(SIMILARITY_MODEL)
        print("[Init] cofacts_local 注入本地 SBERT 模型 (本地近鄰檢索啟用)")
except Exception as e:
    print("[ERR] cofacts_local model injection:", e)

# ---------------------------------------------------------------
# 4. Utility Functions (redirects, domain checks, etc.)
# ---------------------------------------------------------------
# 新增：加入台視、NOWnews、上報、新頭殼、數位時代、今周刊、鏡新聞、NextApple (壹蘋) 等
TAIWAN_MAINSTREAM_DOMAINS = {
    "cna.com.tw", "udn.com", "ltn.com.tw", "chinatimes.com", "pts.org.tw",
    "news.pts.org.tw", "storm.mg", "ettoday.net", "news.tvbs.com.tw",
    "news.cts.com.tw", "ftvnews.com.tw", "setn.com", "rti.org.tw",
    "bcc.com.tw", "cw.com.tw", "mirrormedia.mg", "thenewslens.com",
    "ttv.com.tw", "news.ttv.com.tw", "nownews.com", "upmedia.mg",
    "newtalk.tw", "businesstoday.com.tw", "bnext.com.tw", "tw.nextapple.com",
    "mnews.tw", "tw.news.yahoo.com", "technews.tw", "vogue.com.tw",
    "pchome.com.tw", "feitsui.com", "gamer.com.tw", "soundofhope.org"
}

# 新增：加入 Mobile01、小紅書、微博、Bilibili、Medium、方格子、痞客邦等
UGC_DOMAINS = {
    "facebook.com", "fb.com", "fb.watch", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "youtu.be", "tiktok.com",
    "ptt.cc", "dcard.tw", "line.me", "plurk.com", "threads.net",
    "mobile01.com", "xiaohongshu.com", "weibo.com", "bilibili.com",
    "medium.com", "vocus.cc", "pixnet.net", "reddit.com"
}

# 新增：事實查核機構 (最高可信度)
FACT_CHECK_DOMAINS = {
    "tfc-taiwan.org.tw", "mygopen.com", "cofacts.tw", "cofacts.g0v.tw",
    "rumtoast.com"
}

_article_cache: Dict[str, Optional[Article]] = {}


def resolve_redirects(url: str, timeout: int = 5) -> Optional[str]:
    if not (url and isinstance(url, str) and url.startswith(("http://", "https://"))):
        return None
    if not REQUESTS_AVAILABLE:
        return url
    try:
        with requests.get(url, allow_redirects=True, stream=True, timeout=timeout) as r:
            return r.url if 200 <= r.status_code < 400 else url
    except Exception:
        return url

# Newspaper helpers -----------------------------------------------------------
if NEWSPAPER3K_AVAILABLE:
    def fetch_article(url: str) -> Optional[Article]:
        if url in _article_cache:
            return _article_cache[url]
        from newspaper import Config as NpConfig
        np_cfg = NpConfig()
        np_cfg.browser_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        np_cfg.fetch_images = False
        np_cfg.request_timeout = 15
        art = Article(url, language="zh", config=np_cfg)
        try:
            art.download(); art.parse(); _article_cache[url] = art; return art
        except Exception:
            _article_cache[url] = None; return None
else:
    def fetch_article(url: str):
        return None

# Sentiment & similarity helpers ---------------------------------------------

def _sentiment_batch(texts: List[str]) -> List[float]:
    """Return mapped scores (‑1 … +1) for each text."""
    if not SENTIMENT_PIPELINE:
        return [0.0] * len(texts)
    # DistilBERT max seq len = 512 tokens. 截斷超長文本避免 tensor size 錯誤。
    # 中文約 1 字 ≈ 1 token，保守截到 480 字元以確保 < 512 tokens。
    clipped = [t[:480] for t in texts]
    with torch.autocast(DEVICE, enabled=(DEVICE == "cuda")):
        outputs = SENTIMENT_PIPELINE(clipped)
    mapped = []
    for out in outputs:
        lab, sc = out["label"], out["score"]
        lab = MODEL_LABELS.get(int(lab.split("_")[-1]), lab) if lab.startswith("LABEL_") else lab
        mapped.append(sc if lab.lower() == "positive" else -sc if lab.lower() == "negative" else 0.0)
    return mapped


def _similarity_batch(contents: List[str], refs: List[str]) -> List[float]:
    if not SIMILARITY_MODEL or not refs:
        return [0.0] * len(contents)
    # Encode refs once
    with torch.autocast(DEVICE, enabled=(DEVICE == "cuda")):
        ref_emb = SIMILARITY_MODEL.encode(refs, convert_to_tensor=True, batch_size=len(refs))
    sims = []
    with torch.autocast(DEVICE, enabled=(DEVICE == "cuda")):
        for chunk_start in range(0, len(contents), 64):
            chunk = contents[chunk_start:chunk_start+64]
            emb = SIMILARITY_MODEL.encode(chunk, convert_to_tensor=True, batch_size=len(chunk))
            cos = util.cos_sim(emb, ref_emb).mean(dim=1).clamp(0, 1).tolist()
            sims.extend(cos)
    return sims


# ---------------------------------------------------------------
# 4.5 Deep Analysis (local LLM via Ollama)
#     把標題 + 網路搜尋結果摘要 + 三源查核結論餵入本機模型，
#     產出結構化深入分析：質疑點 / 正反觀點 / 可信度分數(0-100) / 總結。
#     失敗或超時則回傳空 dict，前端隱藏該區塊（不影響主評分）。
# ---------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:18443/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:12b")
DEEP_ANALYZE_TIMEOUT = float(os.environ.get("DEEP_ANALYZE_TIMEOUT", "20"))

_DEEP_PROMPT_TMPL = """你是一個事實查核分析助手。根據提供的資訊，只輸出一個 JSON 物件（不要任何其他文字），格式：
{{"key_points":["質疑點1","質疑點2"],"viewpoints":"正反觀點摘要(80字內)","credibility_score":0到100的整數,"analysis":"100字內總結"}}
新聞標題：{title}
網路搜尋結果摘要：
{web_summary}
事實查核源結論：
{fc_summary}"""


def _deep_analyze_build_prompt(title: str, web_results: list, sources: list) -> str:
    # 網路搜尋摘要：最多取 5 筆，每筆 title + snippet 截短
    lines = []
    for i, r in enumerate(web_results[:5], 1):
        t = (r.get("title") or "").strip()
        s = (r.get("snippet") or r.get("body") or "").strip()
        if len(s) > 120:
            s = s[:120] + "…"
        lines.append(f"{i}. {t} — {s}" if (t or s) else "")
    web_summary = "\n".join(l for l in lines if l) or "（無網路搜尋結果）"
    # 查核源摘要
    fc_lines = []
    label_map = {"cofacts": "Cofacts", "google": "Google查核", "mygopen": "MyGoPen"}
    for s in sources:
        st = s.get("status", "not_found")
        nm = label_map.get(s.get("source", ""), s.get("source", ""))
        mt = (s.get("matched_text") or "")[:60]
        fc_lines.append(f"  - {nm}: {st}（{mt}）" if mt else f"  - {nm}: {st}")
    fc_summary = "\n".join(fc_lines) or "（無查核源）"
    return _DEEP_PROMPT_TMPL.format(title=title or "（無標題）",
                                    web_summary=web_summary,
                                    fc_summary=fc_summary)


def deep_analyze(title: str, web_results: list, sources: list,
                 timeout: "float | None" = None) -> dict:
    """呼叫本機 Ollama 模型做深入分析。回傳 dict 或空 dict（失敗）。"""
    if not REQUESTS_AVAILABLE:
        return {}
    prompt = _deep_analyze_build_prompt(title, web_results, sources)
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 400},
    }
    to = timeout or DEEP_ANALYZE_TIMEOUT
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=to,
                          headers={"Content-Type": "application/json"})
        r.raise_for_status()
        data = r.json()
        resp = data.get("response", "")
        # resp 可能本身就是 JSON 字串
        parsed = json.loads(resp) if isinstance(resp, str) else resp
        # 正規化
        score = parsed.get("credibility_score", 0)
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 0
        return {
            "key_points": parsed.get("key_points", []),
            "viewpoints": parsed.get("viewpoints", ""),
            "credibility_score": max(0, min(100, score)),
            "analysis": parsed.get("analysis", ""),
            "model": OLLAMA_MODEL,
        }
    except Exception as _e:
        print(f"[judge] deep_analyze failed: {_e}")
        return {}


def deep_analyze_ensemble(title: str, web_results: list, sources: list,
                          samples: int = None, timeout: float = None) -> dict:
    """多次取樣本機 LLM 以降低 7B 模型分數抖動；並回傳 std / 樣本數供前端說明。
    並發呼叫（ThreadPoolExecutor）控制總延遲約等於單次。"""
    import concurrent.futures as _cf
    n = int(samples if samples is not None else os.environ.get("DEEP_ANALYZE_SAMPLES", "3"))
    n = max(1, min(n, 5))
    to = timeout or DEEP_ANALYZE_TIMEOUT

    def _one():
        return deep_analyze(title, web_results, sources, timeout=to)

    results = []
    if n == 1:
        results = [_one()]
    else:
        with _cf.ThreadPoolExecutor(max_workers=n) as ex:
            for fut in _cf.as_completed([ex.submit(_one) for _ in range(n)]):
                try:
                    results.append(fut.result())
                except Exception:
                    pass
    valid = [r for r in results if isinstance(r, dict) and r.get("credibility_score") is not None]
    if not valid:
        return {}
    scores = [float(r["credibility_score"]) for r in valid]
    avg = sum(scores) / len(scores)
    std = (sum((s - avg) ** 2 for s in scores) / len(scores)) ** 0.5
    # 取最靠近平均的那次作為質化內容（key_points/viewpoints/analysis），保持一致性
    best = min(valid, key=lambda r: abs(float(r["credibility_score"]) - avg))
    return {
        "key_points": best.get("key_points", []),
        "viewpoints": best.get("viewpoints", ""),
        "credibility_score": int(round(avg)),
        "analysis": best.get("analysis", ""),
        "model": best.get("model", OLLAMA_MODEL),
        "samples": len(valid),
        "score_std": round(std, 1),
    }


# ---------------------------------------------------------------
# 5. Core Scoring Logic (single article) – kept from original but
#    streamlined for clarity.  Only minimal refactor to reuse helpers.
# ---------------------------------------------------------------
DEFAULT_WEIGHTS = {
    "sentiment": 15.0,
    "domain": 25.0,
    "fact_check": 30.0,
    "feedback": 10.0,
    "similarity": 15.0,
    "timeliness": 5.0,
}


def _score_single(title: str, url: str, content: str, refs: List[str], publish_date=None, target_url: str = None) -> Dict:
    """Return full metric dict for one article (fast, GPU‑ready)."""
    res: Dict[str, Dict] = {}
    total = 0.0; avail = sum(DEFAULT_WEIGHTS.values())

    # Pre-resolve Domain info for downstream metric logic (supports Google News RSS title/content publisher resolution)
    MEDIA_NAME_TO_DOMAIN = {
        "自由時報": "ltn.com.tw", "自由電子報": "ltn.com.tw", "自由體育": "ltn.com.tw", "自由健康網": "ltn.com.tw", "自由財經": "ltn.com.tw",
        "中央社": "cna.com.tw", "CNA": "cna.com.tw",
        "聯合報": "udn.com", "UDN": "udn.com", "經濟日報": "udn.com",
        "中時": "chinatimes.com", "中國時報": "chinatimes.com",
        "TVBS": "tvbs.com.tw", "news.tvbs.com.tw": "tvbs.com.tw",
        "ETtoday": "ettoday.net", "東森新聞": "ebc.net.tw",
        "三立": "setn.com", "SETN": "setn.com",
        "風傳媒": "storm.mg", "Storm": "storm.mg",
        "公視": "pts.org.tw", "華視": "cts.com.tw", "台視": "ttv.com.tw",
        "民視": "ftvnews.com.tw", "鏡週刊": "mirrormedia.mg", "鏡新聞": "mnews.tw",
        "NOWnews": "nownews.com", "今日新聞": "nownews.com",
        "蘋果": "nextapple.com", "壹蘋": "nextapple.com",
        "天下雜誌": "cw.com.tw", "商業周刊": "businesstoday.com.tw",
        "關鍵評論": "thenewslens.com", "科技新報": "technews.tw", "TechNews": "technews.tw",
        "鉅亨網": "cnyes.com", "Yahoo": "tw.news.yahoo.com",
        "巴哈姆特": "gamer.com.tw", "GNN": "gamer.com.tw",
        "PChome": "pchome.com.tw", "遠見": "gvm.com.tw"
    }

    eval_url = target_url or url
    parsed = urlparse(eval_url); host = parsed.netloc.lower().replace("www.", "")
    if host in ("news.google.com", "google.com", "bit.ly", "t.co", "tinyurl.com") and target_url:
        parsed = urlparse(target_url)
        host = parsed.netloc.lower().replace("www.", "")
    parts = host.split(".")
    main = ".".join(parts[-2:]) if len(parts) >= 2 else host

    # If domain is generic google.com aggregator or unknown, resolve media outlet from title/content
    if main in ("google.com", "unknown", "") or host == "news.google.com":
        search_text = (title or "") + " " + (content[:500] if content else "")
        for m_name, m_dom in MEDIA_NAME_TO_DOMAIN.items():
            if m_name in search_text:
                main = m_dom
                host = m_dom
                break

    # 1) Sentiment (Decoupled negative news reporting penalty)
    s = _sentiment_batch([content])[0]
    abs_s = abs(s); sent_pts = DEFAULT_WEIGHTS["sentiment"]
    
    clickbait_keywords = ["震撼", "網全嚇傻", "竟然", "不看會後悔", "急了", "震撼彈", "太誇張", "傻眼", "敗類", "割韭菜"]
    has_clickbait = any(kw in (title + content[:300]) for kw in clickbait_keywords)
    is_mainstream = (main in TAIWAN_MAINSTREAM_DOMAINS or host in TAIWAN_MAINSTREAM_DOMAINS or main in FACT_CHECK_DOMAINS)
    
    if abs_s <= 0.6:
        sent_pts = DEFAULT_WEIGHTS["sentiment"]
    elif abs_s <= 0.85:
        sent_pts = 12.0
    else:
        if is_mainstream and not has_clickbait:
            sent_pts = 10.0
        elif has_clickbait or main in UGC_DOMAINS:
            sent_pts = -DEFAULT_WEIGHTS["sentiment"]
        else:
            sent_pts = 5.0
    total += sent_pts
    res["sentiment"] = {"score": sent_pts, "desc": f"{s:.2f}", "weight": DEFAULT_WEIGHTS["sentiment"]}

    # 2) Domain (simple rules with redirect resolution support)
    
    dom_pts = 15.0  # Default for unknown standard HTTPS sites
    if main in FACT_CHECK_DOMAINS or host in FACT_CHECK_DOMAINS:
        dom_pts = DEFAULT_WEIGHTS["domain"]  # 滿分 (查核機構)
    elif main in TAIWAN_MAINSTREAM_DOMAINS or host in TAIWAN_MAINSTREAM_DOMAINS:
        dom_pts = DEFAULT_WEIGHTS["domain"]
    elif main in UGC_DOMAINS or host in UGC_DOMAINS:
        dom_pts = 0.0  # UGC platforms (social media) have 0 inherent credibility
        
    if parsed.scheme == "http":
        dom_pts -= 10.0  # Penalize plain HTTP
        
    dom_pts = max(0.0, dom_pts)  # Don't go below 0 for this metric to avoid UI weirdness
    total += dom_pts
    res["domain"] = {"score": dom_pts, "desc": main, "weight": DEFAULT_WEIGHTS["domain"]}

    # 3)/4)/6) 多源事實查核（Cofacts + Google + MyGoPen）共用一次查詢
    fc_pts = 0.0; fc_desc = "not_checked"
    fb_pts = 0.0; fb_desc = "none"
    tl_pts = 0.0; tl_desc = "unknown"
    sources = []
    if MULTI_FC_AVAILABLE:
        sources = get_all_fact_checks(content, timeout_api=15)
        # 取最嚴重的查核結論（inaccurate > partial > accurate > not_found/disabled）
        sev = {"inaccurate": 3, "partial": 2, "accurate": 1, "not_found": 0, "disabled": 0, "error": 0}
        worst = None
        for r in sources:
            if r.get("status") in ("inaccurate", "partial", "accurate") and \
               (worst is None or sev[r["status"]] > sev[worst["status"]]):
                worst = r
        if worst:
            fc_desc = worst["status"]
            if worst["status"] == "inaccurate":
                fc_pts = -DEFAULT_WEIGHTS["fact_check"]
            elif worst["status"] == "partial":
                fc_pts = DEFAULT_WEIGHTS["fact_check"] * 0.3
            elif worst["status"] == "accurate":
                fc_pts = DEFAULT_WEIGHTS["fact_check"]
        else:
            # 所有源都是 not_found/disabled/error → 視為查無資料 (即時新聞中性基準分 15.0)
            fc_desc = "not_found"
            fc_pts = DEFAULT_WEIGHTS["fact_check"] * 0.5
        # 4) 用戶回饋（網路評論）→ 改為生成搜尋連結，不依賴回饋數
        #    有任一源命中（inaccurate/partial/accurate）視為有討論度，給部分分
        hit = any(r.get("status") in ("inaccurate", "partial", "accurate") for r in sources)
        if hit:
            fb_pts = DEFAULT_WEIGHTS["feedback"]
            fb_desc = "有查核討論"
        else:
            fb_desc = "none"
        # 6) 時效性：優先文章發布時間 publish_date，其次 Cofacts 命中文章建立時間
        tl_date = None
        tl_src = None
        if publish_date:
            try:
                pd_dt = datetime.fromisoformat(publish_date.replace("Z", "+00:00"))
                tl_date = pd_dt.timestamp()
                tl_src = "article"
            except Exception:
                tl_date = None
        if tl_date is None:
            for r in sources:
                if r.get("created_at"):
                    tl_date = r["created_at"]; tl_src = r.get("source"); break
        if tl_date is not None:
            age_days = (time.time() - tl_date) / 86400.0
            tl_pts = max(0.0, DEFAULT_WEIGHTS["timeliness"] * (1.0 - min(age_days, 365) / 365.0))
            if tl_src == "article":
                tl_desc = (publish_date or "")[:10]
            else:
                tl_desc = f"{age_days:.0f} 天前"
    total += fc_pts + fb_pts + tl_pts
    res["fact_check"] = {"score": fc_pts, "desc": fc_desc, "weight": DEFAULT_WEIGHTS["fact_check"]}
    res["user_feedback"] = {"score": fb_pts, "desc": fb_desc, "weight": DEFAULT_WEIGHTS["feedback"]}

    # 5) Similarity
    sim = _similarity_batch([content], refs)[0]
    sim_pts = sim * DEFAULT_WEIGHTS["similarity"]
    total += sim_pts
    res["similarity"] = {"score": sim_pts, "desc": f"{sim:.2%}", "weight": DEFAULT_WEIGHTS["similarity"]}

    # 6) Timeliness 寫入
    res["timeliness"] = {"score": tl_pts, "desc": tl_desc, "weight": DEFAULT_WEIGHTS["timeliness"]}

    # 網路評論搜尋連結（用戶回饋維度改為此）
    # 優先使用真實標題；標題為空或佔位 'N/A' 時改用內文前段
    _title_clean = (title or "").strip()
    if _title_clean in ("", "N/A"):
        _query_src = content[:80].strip()
    else:
        _query_src = _title_clean
    web_review_query = quote_plus(_query_src)
    review_links = {
        "threads": f"https://www.threads.net/search?q={web_review_query}",
        "duckduckgo": f"https://duckduckgo.com/?q={web_review_query}+評論+討論",
    }

    # 真實網路評論/討論搜尋結果（Serper → free-search bing → Google News RSS 回退）
    # 無 key 或全源失敗時回空 list，前端自動隱藏該區塊
    web_results: List[Dict] = []
    if WEB_SEARCH_AVAILABLE and _wsc is not None:
        try:
            web_results = _wsc.search(_query_src, max_results=6)
        except Exception as _e:
            print(f"[judge] web_search failed: {_e}")
            web_results = []

    final = (total / avail) * 100 if avail > 0 else 0.0
    rule_score = final
    # 深入分析：本機 LLM 把 web_results + 查核源結論轉為結構化分析（多次取樣降抖動）
    deep = {}
    if web_results or sources:
        try:
            deep = deep_analyze_ensemble(_title_clean or content[:60], web_results, sources)
        except Exception as _e:
            print(f"[judge] deep_analyze failed: {_e}", flush=True)
            deep = {}
    # 融合：LLM 可信度分動態加權進總評
    # - 查核命中：規則已強證據，LLM 僅微調 (w=0.10)
    # - 查核全 not_found：規則維度無信號，LLM 成主要依據 (w=0.60)
    ai_cs = deep.get('credibility_score') if isinstance(deep, dict) else None
    fusion_weight = 0.0
    post_fusion_score = final
    clamped = False
    clamp_reason = ""
    if ai_cs is not None:
        try:
            cs = float(ai_cs)
            fc_hit = any((s.get('status') in ('hit', 'ok', 'inaccurate', 'partial'))
                         for s in (sources or []))
            fusion_weight = 0.10 if fc_hit else 0.60
            final = final * (1 - fusion_weight) + cs * fusion_weight
            post_fusion_score = final
        except (TypeError, ValueError):
            pass
    # 階段三：三級動態信心度衰減錨定 (Stage 3 Dynamic Confidence Decay Clamp)
    for _s in (sources or []):
        _st = _s.get('status')
        sim_score = float(_s.get('similarity_score') or 1.0)
        if _st in ('inaccurate', 'false', 'misleading', 'fake'):
            if sim_score >= 0.85:
                if final > 25.0:
                    clamped = True
                    clamp_reason = f"查核機構 ({_s.get('source', '查核庫')}) 高度信心判定不實 (相似度 {int(sim_score*100)}%)，觸發安全上限錨定 (最高 25.0)"
                final = min(final, 25.0)
                break
            elif sim_score >= 0.72:
                if final > 50.0:
                    clamped = True
                    clamp_reason = f"查核機構 ({_s.get('source', '查核庫')}) 中度相關爭議 (相似度 {int(sim_score*100)}%)，觸發軟上限錨定 (最高 50.0)"
                final = min(final, 50.0)
                break
        elif _st == 'partial':
            if final > 55.0:
                clamped = True
                clamp_reason = f"查核機構 ({_s.get('source', '查核庫')}) 判定部分不實，觸發上限錨定 (最高 55.0)"
            final = min(final, 55.0)
    # 5 級評級（PolitiFact-style 序數標籤）- adjusted for higher precision
    if final >= 75:
        rating = "高度可信"
    elif final >= 60:
        rating = "大致可信"
    elif final >= 40:
        rating = "待查證"
    elif final >= 20:
        rating = "疑似不實"
    else:
        rating = "高度可疑"
    # 評分依據說明（前端展示「為什麼給這個等級」）
    fc_statuses = [s.get('status') for s in (sources or [])]
    if any(st in ('inaccurate', 'false', 'misleading', 'fake') for st in fc_statuses):
        basis = "查核機構判定不實，已錨定低分"
    elif any(st == 'partial' for st in fc_statuses):
        basis = "查核機構判定部分不實，已錨定上限"
    elif any(st in ('hit', 'ok', 'accurate', 'true') for st in fc_statuses):
        basis = "查核機構判定屬實，規則分主導"
    elif deep and deep.get('credibility_score') is not None:
        basis = f"無查核證據，由本機 AI 模型補位評分（{deep.get('samples','?')}次取樣）"
    else:
        basis = "無查核證據且 AI 評分失敗，僅依規則分"
    return {
        **res,
        "total_raw_score": total,
        "available_weight": avail,
        "final_score": final,
        "rule_score": rule_score,
        "fusion_weight": fusion_weight,
        "post_fusion_score": post_fusion_score,
        "clamped": clamped,
        "clamp_reason": clamp_reason,
        "rating_text": rating,
        "scoring_basis": basis,
        "sources": sources,
        "review_links": review_links,
        "web_results": web_results,
        "deep_analysis": deep,
    }

# ---------------------------------------------------------------
# 6. Batch API (GPU‑accelerated)
# ---------------------------------------------------------------

def analyze_batch_article_data(
    titles: List[str],
    urls: List[str],
    contents: List[str],
    *,
    batch_size: int = 64,
) -> List[Dict]:
    """High‑throughput batch scoring – returns list[dict] like _score_single."""
    n = len(contents)
    if not (len(titles) == len(urls) == n):
        raise ValueError("titles/urls/contents length mismatch")

    # For similarity we use title + self content as refs
    refs_all = [t for t in titles]

    outputs: List[Dict] = []
    for start in range(0, n, batch_size):
        end = start + batch_size
        chunk_titles   = titles[start:end]
        chunk_urls     = urls[start:end]
        chunk_contents = contents[start:end]

        # Pre‑calc similarities for chunk (batch friendly)
        sims = _similarity_batch(chunk_contents, refs_all)
        sent = _sentiment_batch(chunk_contents)

        for i in range(len(chunk_contents)):
            # Patch into _score_single logic quickly by overriding helpers result
            score_dict = _score_single(chunk_titles[i], chunk_urls[i], chunk_contents[i], refs_all)
            # Replace with already computed sentiment & similarity for accuracy
            score_dict["sentiment"]["score"] = 0.0  # placeholder (could re‑map using sent[i])
            score_dict["similarity"]["desc"] = f"{sims[i]:.2%}"
            outputs.append(score_dict)
    return outputs

# ---------------------------------------------------------------
# 7. Existing single‑article wrapper & Flask API (minimal changes)
# ---------------------------------------------------------------

def analyze_article_data(title: str = "", url: str = "", content: str = "", publish_date=None, target_url: str = None, **_) -> Dict:
    if not content:
        raise ValueError("content required for single analysis")
    if not url:
        url = "https://unknown"
    return _score_single(title or "N/A", url, content, [title, content], publish_date=publish_date, target_url=target_url)

# --------------------------- Flask -----------------------------
app = Flask(__name__)

def _is_facebook_url(url: str) -> bool:
    """Check if URL is a Facebook/Meta link."""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    return any(fb in host for fb in ("facebook.com", "fb.com", "fb.watch", "m.facebook.com"))


def _extract_with_selenium(url: str, timeout: int = 20) -> Optional[Dict]:
    """Headless Chrome fallback for JS-rendered or login-walled pages."""
    if not SELENIUM_AVAILABLE:
        return None
    opts = ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--user-data-dir=/home/min20120907/.config/google-chrome")
    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        import time; time.sleep(2)
        title = driver.title or ""
        body = driver.find_element(By.TAG_NAME, "body").text or ""
        if len(body.strip()) < 30:
            return None
        return {"title": title, "content": body[:4000], "source": url, "publish_date": None}
    except Exception:
        return None
    finally:
        if driver:
            try: driver.quit()
            except Exception: pass


def _extract_facebook_requests(url: str) -> Dict:
    """Extract Facebook post content using requests + BeautifulSoup (no browser)."""
    try:
        import requests
        from bs4 import BeautifulSoup
        import re
        import json
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return {}
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 1) Open Graph
        title = None
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
        
        og_desc = soup.find('meta', property='og:description')
        content = og_desc.get('content', '').strip() if og_desc else ''
        
        # 2) JSON-LD
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') in ['SocialMediaPosting', 'Article']:
                            if not title and item.get('headline'):
                                title = item['headline']
                            if not content and item.get('description'):
                                content = item['description']
                            if item.get('articleBody') and len(item['articleBody']) > len(content):
                                content = item['articleBody']
                elif isinstance(data, dict) and data.get('@type') in ['SocialMediaPosting', 'Article']:
                    if not title and data.get('headline'):
                        title = data['headline']
                    if not content and data.get('description'):
                        content = data['description']
                    if data.get('articleBody') and len(data['articleBody']) > len(content):
                        content = data['articleBody']
            except:
                pass
        
        # 3) Fallback: extract from div with data-testid
        if not content or len(content) < 50:
            post_div = soup.find('div', {'data-testid': 'post_message'})
            if post_div:
                content = post_div.get_text(separator='\n').strip()
        
        # Clean up
        if title and not title.startswith('Facebook'):
            pass
        else:
            # Try to get title from URL
            match = re.search(r'story_fbid=(\d+)', url)
            if match:
                title = f'Facebook Post {match.group(1)}'
            else:
                title = 'Facebook Post'
        
        # If content still empty, try to find any significant text
        if not content or len(content) < 20:
            for tag in soup.find_all(['p', 'div', 'span']):
                text = tag.get_text(strip=True)
                if len(text) > 50 and 'Facebook' not in text[:20]:
                    content = text[:2000]
                    break
        
        if content and len(content) > 20:
            return {"title": title, "content": content[:4000], "publish_date": None}
        return {}
    except Exception as e:
        print(f"[Extract] Facebook requests fallback error: {e}")
        return {}

def _extract_facebook_selenium(url: str) -> Dict:
    """Multi-strategy URL content extractor.

    Fallback chain:
    1. trafilatura (best for news articles, handles many sites newspaper3k can't)
    2. newspaper3k (legacy, still works for some sites)
    3. Selenium headless (JS-rendered pages, paywalls with accessible content)

    For Facebook URLs: gives a clear error message since FB requires login.
    """
    if not (url and url.startswith(("http://", "https://"))):
        return {"error": "無效的網址"}

    
    # --- Strategy 1: trafilatura ---
    if TRAFILATURA_AVAILABLE:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
                if text and len(text.strip()) >= 30:
                    # Extract metadata (title, date) via trafilatura's metadata extractor
                    title = ""
                    pub = None
                    try:
                        from trafilatura.metadata import extract_metadata
                        meta = extract_metadata(downloaded)
                        if meta:
                            title = meta.title or ""
                            pub = meta.date or None
                    except Exception:
                        pass
                    return {"title": title, "content": text[:4000], "source": url, "publish_date": pub}
        except Exception:
            pass

    # --- Strategy 2: newspaper3k ---
    if NEWSPAPER3K_AVAILABLE:
        art = fetch_article(url)
        if art is not None and art.text and len(art.text.strip()) >= 30:
            pub = None
            try:
                pd = getattr(art, "publish_date", None)
                if pd is not None:
                    pub = pd.isoformat() if hasattr(pd, "isoformat") else str(pd)
            except Exception:
                pub = None
            return {
                "title": art.title or "",
                "content": art.text[:4000],
                "source": art.source_url or url,
                "publish_date": pub,
            }

def _extract_from_url(url: str) -> Dict:
    """Multi-strategy URL content extractor.

    Fallback chain:
    1. trafilatura (fast, clean text)
    2. newspaper3k (legacy, still works for some sites)
    3. Playwright (JS-rendered pages, paywalls with accessible content)
    4. Selenium headless (last resort, for heavily JS sites)
    """
    if not (url and url.startswith(("http://", "https://"))):
        return {"error": "無效的網址"}

    # --- Strategy 0: Facebook specific with session management ---
    if "facebook.com" in url.lower():
        # 優先使用帶有 session 管理的 Playwright
        if FB_SESSION_AVAILABLE:
            try:
                print(f"[FB Session] 嘗試使用 session 管理擷取: {url}")
                fb_result = get_facebook_post(url, timeout=25)
                if fb_result and fb_result.get("text"):
                    # 檢查是否為有效的貼文內容（不是登入頁面）
                    text = fb_result.get("text", "")
                    title = fb_result.get("title", "")
                    if len(text.strip()) > 100 and not ("登入" in text and len(text.strip()) < 500):
                        print(f"[FB Session] ✅ 成功擷取貼文，內容長度: {len(text)} 字元")
                        return {
                            "title": title,
                            "content": text[:4000],
                            "source": url,
                            "publish_date": fb_result.get("publish_date"),
                        }
                    else:
                        print(f"[FB Session] ⚠️ 擷取到的內容可能是登入頁面，嘗試 fallback")
            except Exception as e:
                print(f"[FB Session] ❌ 錯誤: {e}")
        
        # Fallback: 原來的 requests 方法
        fb_result = _extract_facebook_requests(url)
        if fb_result and fb_result.get("content"):
            return fb_result

    # --- Strategy 1: trafilatura ---
    if TRAFILATURA_AVAILABLE:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
                if text and len(text.strip()) >= 30:
                    # Extract metadata (title, date) via trafilatura's metadata extractor
                    title = ""
                    pub = None
                    try:
                        from trafilatura.metadata import extract_metadata
                        meta = extract_metadata(downloaded)
                        if meta:
                            title = meta.title or ""
                            pub = meta.date or None
                    except Exception:
                        pass
                    return {"title": title, "content": text[:4000], "source": url, "publish_date": pub}
        except Exception:
            pass

    # --- Strategy 2: newspaper3k ---
    if NEWSPAPER3K_AVAILABLE:
        art = fetch_article(url)
        if art is not None and art.text and len(art.text.strip()) >= 30:
            pub = None
            try:
                pd = getattr(art, "publish_date", None)
                if pd is not None:
                    pub = pd.isoformat() if hasattr(pd, "isoformat") else str(pd)
            except Exception:
                pub = None
            return {
                "title": art.title or "",
                "content": art.text[:4000],
                "source": art.source_url or url,
                "publish_date": pub,
            }

    # --- Strategy 3: Playwright (Optimized for FB/JS-rendered sites) ---
    try:
        from pw_scraper import extract_with_playwright
        pw_result = extract_with_playwright(url)
        if pw_result:
            title = pw_result.get("title", "")
            text = pw_result.get("text", "")
            
            # 檢查 Playwright 是否抓到了無效的 FB 首頁或登入牆
            is_fb_junk = ("facebook.com" in url.lower() and (title == "Facebook" or title.startswith("(1) ") or "登入" in text or "Log In" in text or "パスワード" in text or len(text.strip()) < 50))
            
            if is_fb_junk:
                print(f"Playwright got FB junk (title={title}), falling back to Selenium for content, but keeping publish_date.")
                # We save publish_date and let Selenium try to get the real content
                publish_date = pw_result.get("publish_date")
                sel_result = _extract_with_selenium(url)
                if sel_result:
                    sel_result["publish_date"] = publish_date # Merge the date
                    return sel_result
                else:
                    return {
                        "title": title,
                        "content": text[:4000],
                        "source": url,
                        "publish_date": publish_date
                    }
            else:
                return {
                    "title": title,
                    "content": text[:4000],
                    "source": url,
                    "publish_date": pw_result.get("publish_date")
                }
    except Exception as e:
        print(f"Playwright fallback failed: {e}")

        # --- Strategy 4: Selenium headless (Legacy JS fallback) ---
    selenium_result = _extract_with_selenium(url)
    if selenium_result and len(selenium_result.get("content", "").strip()) >= 50:
        return selenium_result

    # --- Strategy 5: Fact Check Local Archive / Web Search Fallback ---
    if COFACTS_LOCAL_AVAILABLE:
        try:
            print(f"[Archive Fallback] 嘗試從 Cofacts 存檔資料庫補全: {url}")
            cf_match = get_fact_check(url)
            if cf_match and cf_match.get("matched_text"):
                t_match = cf_match.get("matched_text", "").strip()
                if len(t_match) >= 20:
                    first_l = t_match.splitlines()[0][:80]
                    print(f"[Archive Fallback] 成功從 Cofacts 存檔資料庫還原內文 ({len(t_match)} 字元)")
                    return {
                        "title": first_l or "Facebook 存檔貼文",
                        "content": t_match[:4000],
                        "source": url,
                        "publish_date": None
                    }
        except Exception as e:
            print(f"[Archive Fallback] 錯誤: {e}")

    return {"error": "無法從此網址抓取內容。可能原因：需要登入、非新聞頁面、或網站封鎖自動抓取。請嘗試直接貼上文章內容。"}

@app.route("/", methods=["GET"])
def index():
    """Serve the web UI."""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "index.html")
    html_path = os.path.abspath(html_path)
    if os.path.isfile(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return make_response(f.read())
    return make_response("Web UI not found. Expected at " + html_path, 404)

@app.route("/judge", methods=["POST"])
def judge_news():
    data = request.get_json(force=True)
    url = data.get("url", "")
    content = data.get("postText") or data.get("content", "")
    title = data.get("title", "")
    extracted: dict = {}

    # 若只有 URL 沒有內容 → 自動抓取
    if not content and url:
        extracted = _extract_from_url(url)
        print(f"DEBUG_EXTRACT_RESULT: {repr(extracted)}")
        if "error" in extracted:
            return {"error": extracted["error"]}, 422
        content = extracted["content"]
        title = title or extracted["title"]
        # 保留用戶原始文章網址；只有原本就沒有網址時才用抓取到的 source 兜底
        if not url:
            url = extracted.get("source") or url

    if not content:
        return {"error": "請提供貼文內容或新聞網址"}, 422

    print(f"DEBUG_JUDGE: title={repr(title)}, content_len={len(content)}, content={repr(content[:50])}", flush=True)
    # Prevent AI from analyzing the Facebook login wall
    # Only block if title is exactly Facebook (or notification variants) and content is suspiciously short or strictly login text.
    if "facebook.com" in url.lower() or not content or len(content) < 100:
        if title == "Facebook" or title.startswith("(1) ") or title.startswith("(2) ") or "登入 Facebook" in title or len(content) < 300:
            # 嘗試最後防線：從 Cofacts 存檔還原
            if COFACTS_LOCAL_AVAILABLE:
                try:
                    print(f"[Judge Fallback] 嘗試從 Cofacts 資料庫自動還原: {url}")
                    cf_match = get_fact_check(url)
                    if cf_match and cf_match.get("matched_text"):
                        t_match = cf_match.get("matched_text", "").strip()
                        if len(t_match) >= 20:
                            content = t_match[:4000]
                            first_l = t_match.splitlines()[0][:80]
                            title = first_l or "Facebook 存檔貼文"
                            print(f"[Judge Fallback] 成功還原 FB 貼文內容 ({len(content)} 字元)")
                except Exception as e:
                    print(f"[Judge Fallback] 錯誤: {e}")

            if title == "Facebook" or "登入 Facebook" in title or len(content) < 100:
                return {"error": "Facebook 阻擋了自動抓取（無法精確解析，或需要不同登入權限）。\n請直接「複製貼文文字」並貼上來進行分析！"}, 422

    score = analyze_article_data(title=title, url=url, content=content, publish_date=extracted.get("publish_date"), target_url=extracted.get("source"))
    return {
        "rating_text": score["rating_text"],
        "final_score": score["final_score"],
        "title": title,
        "url": url,
        "metrics": {
            "sentiment": score["sentiment"],
            "domain": score["domain"],
            "fact_check": score["fact_check"],
            "user_feedback": score["user_feedback"],
            "similarity": score["similarity"],
            "timeliness": score["timeliness"],
        },
        "sources": score.get("sources", []),
        "review_links": score.get("review_links", {}),
        "web_results": score.get("web_results", []),
        "deep_analysis": score.get("deep_analysis", {}),
        "rule_score": score.get("rule_score"),
        "total_raw_score": score.get("total_raw_score"),
        "available_weight": score.get("available_weight"),
        "fusion_weight": score.get("fusion_weight"),
        "post_fusion_score": score.get("post_fusion_score"),
        "clamped": score.get("clamped"),
        "clamp_reason": score.get("clamp_reason"),
        "scoring_basis": score.get("scoring_basis", ""),
    }

def generate_test_results_page():
    """Generate an interactive HTML page showing test results on the WSDM Chinese fake news title dataset."""
    # Limit rows for speed; adjust as needed
    MAX_ROWS = 50
    dataset_url = "https://docs.google.com/spreadsheets/d/1FZak61ZcNmQRC4s4RixLT2-tgnSjmD4MwyxGF2xxiuA/export?format=csv"
    try:
        resp = requests.get(dataset_url, timeout=20)
        resp.raise_for_status()
        content = resp.content.decode('utf-8')
    except Exception as e:
        return f"<h2>Failed to load dataset: {e}</h2>"
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            break
        rows.append(row)
    # Prepare results
    results = []
    for idx, row in enumerate(rows):
        title = row['news_title'].strip()
        label_str = row['is_fake'].strip().lower()
        is_fake = label_str == 'true'
        # Use internal scoring function (no HTTP overhead)
        try:
            score = analyze_article_data(title=title, url="https://example.com", content=title)
        except Exception as e:
            score = {"error": str(e)}
        # Determine prediction: fake if rating in low trust
        rating = score.get('rating_text', '') if isinstance(score, dict) else ''
        pred_fake = rating in ["疑似不實", "高度可疑"]
        results.append({
            "idx": idx,
            "title": title,
            "actual": "fake" if is_fake else "real",
            "pred": "fake" if pred_fake else "real",
            "rating": rating,
            "score": score.get('final_score') if isinstance(score, dict) else None,
            "full": score  # store full dict for details
        })
    # Compute metrics
    tp = fp = fn = tn = 0
    for r in results:
        if r["actual"] == "fake" and r["pred"] == "fake":
            tp += 1
        elif r["actual"] == "real" and r["pred"] == "fake":
            fp += 1
        elif r["actual"] == "fake" and r["pred"] == "real":
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0.0
    # Build HTML
    html = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>NewsAnalyzer 測試結果</title>
    <style>
        body {{font-family: Arial, sans-serif; margin: 20px; line-height: 1.6;}}
        h1, h2 {{color: #2c3e50;}}
        table {{border-collapse: collapse; width: 100%; max-width: 1000px; margin-bottom: 20px;}}
        th, td {{border: 1px solid #ddd; padding: 8px; text-align: left;}}
        th {{background-color: #f2f2f2;}}
        tr:nth-child(even) {{background-color: #f9f9f9;}}
        .metric {{font-size: 1.2em; margin: 10px 0;}}
        .good {{color: green;}}
        .bad {{color: red;}}
        .note {{font-size: 0.9em; color: #555;}}
        .details {{display: none; margin-top: 10px; padding: 10px; background: #f0f0f0; border-radius: 5px;}}
        button {{cursor: pointer;}}
    </style>
</head>
<body>
    <h1>NewsAnalyzer 假新聞檢測測試結果</h1>
    <p class="note">測試資料集：WSDM Fake News Classification (Chinese title-only) 前 {len(rows)} 筆樣本</p>
    <h2>總體指標</h2>
    <div class="metric">True Positives (TP): <span class="good">{tp}</span></div>
    <div class="metric">False Positives (FP): <span class="good">{fp}</span></div>
    <div class="metric">False Negatives (FN): <span class="bad">{fn}</span></div>
    <div class="metric">True Negatives (TN): <span class="good">{tn}</span></div>
    <div class="metric">精準度 (Precision): <span class="good">{precision:.3f} ({precision*100:.1f}%)</span></div>
    <div class="metric">召回率 (Recall): <span class="{'good' if recall >= 0.5 else 'bad'}">{recall:.3f} ({recall*100:.1f}%)</span></div>
    <div class="metric">準確率 (Accuracy): <span class="{'good' if accuracy >= 0.5 else 'bad'}">{accuracy:.3f} ({accuracy*100:.1f}%)</span></div>
    <h2>混淆矩陣</h2>
    <table>
        <tr><th></th><th colspan="2">預測</th></tr>
        <tr><th></th><th>假新聞 (Fake)</th><th>真新聞 (Real)</th></tr>
        <tr><th>實際 假新聞</th><td>TP = {tp}</td><td>FN = {fn}</td></tr>
        <tr><th>實際 真新聞</th><td>FP = {fp}</td><td>TN = {tn}</td></tr>
    </table>
    <h2>詳細結果（點擊顯示/隱藏）</h2>
    <table>
        <tr><th>#</th><th>標題</th><th>實際</th><th>預測</th><th>評級</th><th>分數</th><th>操作</th></tr>
"""
    for r in results:
        # Escape HTML in title
        title_esc = r['title'].replace("&", "&").replace("<", "<").replace(">", ">")
        actual_class = "good" if r["actual"] == "fake" else "bad"
        pred_class = "good" if r["pred"] == "fake" else "bad"
        rating = r['rating'] if r['rating'] else "-"
        score_val = f"{r['score']:.2f}" if r['score'] is not None else "-"
        html += f"""
        <tr>
            <td>{r['idx']+1}</td>
            <td title=\"{title_esc}\">{title_esc[:80]}{'...' if len(title_esc) > 80 else ''}</td>
            <td class=\"{actual_class}\">{r['actual']}</td>
            <td class=\"{pred_class}\">{r['pred']}</td>
            <td>{rating}</td>
            <td>{score_val}</td>
            <td><button onclick=\"toggleDetails({r['idx']})\">顯示詳情</button></td>
        </tr>
        <tr id=\"details_{r['idx']}\" class=\"details\" colspan=\"7\">
            <div style=\"padding:10px; background:#f8f8f8; border-radius:5px;\">
                <strong>完整回傳：</strong><pre style=\"white-space: pre-wrap; background:#fff; padding:10px; border:1px solid #ccc; max-height:300px; overflow:auto;\">{json.dumps(r['full'], ensure_ascii=False, indent=2)}</pre>
            </div>
        </tr>
"""
    html += """
    </table>
    <hr>
    <p class="note">此頁面由 Hermes Agent 自動生成，僅供內部參考。</p>
    <script>
        function toggleDetails(idx) {
            var el = document.getElementById('details_' + idx);
            if (el.style.display === 'none' || el.style.display === '') {
                el.style.display = 'table-row';
            } else {
                el.style.display = 'none';
            }
        }
    </script>
</body>
</html>
"""
    return html

@app.route('/test_results', methods=['GET'])
def test_results():
    return generate_test_results_page()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

