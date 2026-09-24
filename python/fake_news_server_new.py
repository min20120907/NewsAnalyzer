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
# 名單已搬至 data/domains/*.txt（見下方 load_domain_lists），此處僅保留註解：
# 台灣主流媒體白名單 / UGC / 查核機構 → data/domains/whitelist.txt、ugc.txt、factcheck.txt

# ---------------------------------------------------------------
# 網域名單：本地策展檔 + 社群上游訂閱（cron 每日 pull）
#   data/domains/whitelist.txt         台灣主流媒體（本地策展，無上游）
#   data/domains/ugc.txt               UGC 種子（本地）＋ ugc.remote.txt（StevenBlack social）
#   data/domains/factcheck.txt         查核機構（本地策展，無上游）
#   data/domains/blocklist.local.txt   手動加料 ＋ blocklist.remote.txt
#     （danny0838 終結內容農場 ＋ cobaltdisco x2 ＋ StevenBlack fakenews）
# 優先序：factcheck/whitelist > blocklist（上游誤收白名單時本地勝出）。
# 名單改動免重啟：每請求檢查 mtime，變動才重載。
# ---------------------------------------------------------------
_DOMAIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "data", "domains")
_DOMAIN_MTIMES: dict = {}


def _read_domain_file(fname: str) -> set:
    out = set()
    try:
        with open(os.path.join(_DOMAIN_DIR, fname), encoding="utf-8") as f:
            for line in f:
                line = line.strip().lower()
                if line and not line.startswith("#") and "." in line and "/" not in line:
                    out.add(line)
    except FileNotFoundError:
        pass
    return out


def load_domain_lists() -> bool:
    """mtime 變動才重載；回傳 True 表示本次有重載。"""
    global TAIWAN_MAINSTREAM_DOMAINS, UGC_DOMAINS, FACT_CHECK_DOMAINS
    global DYNAMIC_BLOCKLIST_DOMAINS, _DOMAIN_MTIMES
    files = ["whitelist.txt", "ugc.txt", "ugc.remote.txt", "factcheck.txt",
             "blocklist.local.txt", "blocklist.remote.txt"]
    mt = {}
    for fn in files:
        try:
            mt[fn] = os.path.getmtime(os.path.join(_DOMAIN_DIR, fn))
        except OSError:
            mt[fn] = -1
    if mt == _DOMAIN_MTIMES:
        return False
    wl = _read_domain_file("whitelist.txt")
    fc = _read_domain_file("factcheck.txt")
    ugc = _read_domain_file("ugc.txt") | _read_domain_file("ugc.remote.txt")
    blk = ((_read_domain_file("blocklist.local.txt")
            | _read_domain_file("blocklist.remote.txt"))
           - wl - fc)  # 本地白名單永遠勝出
    if wl:
        TAIWAN_MAINSTREAM_DOMAINS = wl
    if ugc:
        UGC_DOMAINS = ugc
    if fc:
        FACT_CHECK_DOMAINS = fc
    DYNAMIC_BLOCKLIST_DOMAINS = blk
    _DOMAIN_MTIMES = mt
    print(f"[Domains] whitelist={len(wl)} ugc={len(ugc)} "
          f"factcheck={len(fc)} blocklist={len(blk)}", flush=True)
    return True


TAIWAN_MAINSTREAM_DOMAINS: set = set()
UGC_DOMAINS: set = set()
FACT_CHECK_DOMAINS: set = set()
DYNAMIC_BLOCKLIST_DOMAINS: set = set()
load_domain_lists()

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

# 2026-09-24：舊寫法 parts[-2:] 把 cna.com.tw 切成 com.tw（分對、標錯）。
# 以雙層後綴表還原可註冊網域，同時修 desc 與 main 比對。
_TWO_LEVEL_SUFFIX = {
    "com", "org", "net", "gov", "edu", "idv", "mil", "asn", "plc",
    "co", "or", "ne", "go", "ac", "ad", "gr",
}


def _registrable_domain(host: str) -> str:
    p = (host or "").lower().split(".")
    if len(p) < 2:
        return host or ""
    if len(p) >= 3 and p[-2] in _TWO_LEVEL_SUFFIX and len(p[-1]) <= 3:
        return ".".join(p[-3:])
    return ".".join(p[-2:])


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
# 4.4b 搜尋相關性備援：首查結果若與標題無關（突發新聞 RSS 尚未收錄），
#      用縮短查詢（去站台後綴、取首段）再查一次並合併，避免 deep LLM
#      拿到無關證據、被迫用過時內建知識臆斷（實例：日相高市案）。
# ---------------------------------------------------------------
def _web_query_core(query: str) -> str:
    core = (query or "").split("|")[0].strip()
    return core


def _web_relevant_count(web_results: list, query: str) -> int:
    core = _web_query_core(query).replace(" ", "").replace("　", "")
    if len(core) < 8:
        return len(web_results)
    keys = [core[i:i + 4] for i in range(0, len(core) - 3, 2)]
    n = 0
    for r in web_results or []:
        t = (r.get("title") or "").replace(" ", "").replace("　", "")
        if any(k in t for k in keys):
            n += 1
    return n


def _web_search_fallback(query: str, web_results: list, max_results: int = 6) -> list:
    """相關 < 2 筆時觸發：縮短查詢再查並去重合併。失敗回原結果。"""
    if not (WEB_SEARCH_AVAILABLE and _wsc is not None):
        return web_results
    try:
        if _web_relevant_count(web_results, query) >= 2:
            return web_results
        core = _web_query_core(query)
        short = core.split()[0] if core.split() else core
        if len(short) < 6 or short == query:
            return web_results
        extra = _wsc.search(short, max_results=max_results) or []
        seen = {r.get("url") for r in web_results}
        merged = list(web_results)
        for r in extra:
            if r.get("url") in seen:
                continue
            seen.add(r.get("url"))
            merged.append(r)
        print(f"[judge] web fallback query={short[:30]} +{len(merged) - len(web_results)}")
        return merged[:max_results]
    except Exception as _e:
        print(f"[judge] web fallback failed: {_e}")
        return web_results


# ---------------------------------------------------------------
# 4.5 Deep Analysis (local LLM via :8088 Qwen3.8-27B)
#     把標題 + 網路搜尋結果摘要 + 三源查核結論餵入本機模型，
#     產出結構化深入分析：質疑點 / 正反觀點 / 可信度分數(0-100) / 總結。
#     失敗或超時則回傳空 dict，前端隱藏該區塊（不影響主評分）。
# ---------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:18443/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:12b")
# Qwen3.8-27B 常駐推理（llama.cpp FastMTP，OpenAI 相容）與 deep-proxy（DeepSeek Web，OpenAI 相容）
# 二選一：QWEN_URL 指到哪個後端就走哪個。2026-09-23 起預設走 deep-proxy（qwen 慢）。
# Ollama 變數保留僅為相容（gemma 已實測無法在 CPU 時限內交卷）。
QWEN_URL = os.environ.get("QWEN_URL", "http://127.0.0.1:3000/v1/chat/completions")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "deepseek-chat")
DEEP_ANALYZE_TIMEOUT = float(os.environ.get("DEEP_ANALYZE_TIMEOUT", "60"))
QWEN_SLOTS_URL = os.environ.get("QWEN_SLOTS_URL", "http://127.0.0.1:8088/slots")
# 佇列預估等待超過此秒數就跳過深入分析（:8088 單槽，Hermes 長上下文請求一次可佔 100-330s）
QWEN_BUSY_ETA_SKIP = float(os.environ.get("QWEN_BUSY_ETA_SKIP", "5"))


def qwen_queue_eta() -> float:
    """估計 :8088 目前任務還要多久（秒）。閒置或無法判斷時回 0.0。

    依據 /slots 的 is_processing / n_prompt_tokens / n_prompt_tokens_processed / next_token.n_decoded。
    以 300 tok/s prompt 預處理、26 tok/s 生成（2080Ti 22G 實測）估算。
    """
    if not REQUESTS_AVAILABLE:
        return 0.0
    try:
        r = requests.get(QWEN_SLOTS_URL, timeout=2)
        for s in r.json():
            if not s.get("is_processing"):
                continue
            pt = float(s.get("n_prompt_tokens") or 0)
            proc = float(s.get("n_prompt_tokens_processed") or 0)
            n_dec = float((s.get("next_token") or {}).get("n_decoded") or 0)
            return max(0.0, (pt - proc) / 300.0) + max(0.0, (450.0 - n_dec) / 26.0)
    except Exception:
        pass
    return 0.0

_DEEP_PROMPT_TMPL = """你是一個事實查核分析助手。根據提供的資訊，只輸出一個 JSON 物件（不要任何其他文字），格式：
{{"key_points":["質疑點1","質疑點2"],"viewpoints":"正反觀點摘要(80字內)","credibility_score":0到100的整數,"analysis":"100字內總結"}}
【語言】所有欄位一律使用繁體中文完整句子，嚴禁出現英文單字或中英夾雜（外來專有名詞也譯為中文，例如勝肽、糖尿病）。
【時間】今天日期：{today}。你的內建知識可能已過時，人物職稱、時事現況一律以「網路搜尋結果摘要」為準，嚴禁憑內建知識斷言（例如現任首相是誰）。
【查核結論優先】「事實查核源結論」是查核機構的已驗證判定，權重高於網路搜尋片段；sim 是輸入與查核命中標題的語意相似度（1.0 最高，0.50 為命中門檻）：
- 任一源 status 為 inaccurate 且 sim≥0.70：該新聞極可能不實。analysis 必須明確呼應此結論（點名哪家機構、命中哪篇查核文），credibility_score 取 10 到 40，不得洗白、不得寫「可信度中等」。
- inaccurate 但 sim 在 0.50 到 0.70：屬「相鄰主題命中」（查核的是同類謠言家族、非同一指控）。analysis 必須明說命中標題與新聞主題不完全相同，credibility_score 取 40 到 60。
- 任一源為 accurate 且 sim≥0.70：credibility_score 取 60 到 95，並在 analysis 說明查核支持點。
- sim 顯示「未知」時：按 status 字面採信，但在 analysis 加註「相似度未知」。
- 全部 not_found：不可臆斷為假訊息，credibility_score 取 55 到 65，並在 analysis 明說「無相關佐證」。
【搜尋片段用法】網路搜尋結果摘要僅供補充正反觀點（viewpoints）與質疑點（key_points），不得用片段推翻上面的查核結論；若片段與查核結論矛盾，以查核結論為準並在 analysis 指出矛盾。
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
        mt = (s.get("matched_text") or "")[:120]
        url = s.get("url") or ""
        _sim = s.get("similarity_score")
        sim_txt = f"{float(_sim):.2f}" if _sim is not None else "未知"
        if mt:
            fc_lines.append(f"  - {nm}: {st}（sim {sim_txt}；命中：{mt}；{url}）")
        else:
            fc_lines.append(f"  - {nm}: {st}（sim {sim_txt}）")
    fc_summary = "\n".join(fc_lines) or "（無查核源）"
    from datetime import date as _date
    return _DEEP_PROMPT_TMPL.format(title=title or "（無標題）",
                                    web_summary=web_summary,
                                    fc_summary=fc_summary,
                                    today=_date.today().isoformat())


def deep_analyze(title: str, web_results: list, sources: list,
                 timeout: "float | None" = None) -> dict:
    """呼叫 LLM（預設 deep-proxy DeepSeek，QWEN_URL 指到 :8088 則走本機 Qwen3.8-27B）做深入分析。回傳 dict 或空 dict（失敗）。"""
    if not REQUESTS_AVAILABLE:
        return {}
    prompt = _deep_analyze_build_prompt(title, web_results, sources)
    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system",
             "content": "你是一個事實查核分析助手。根據提供的資訊，只輸出一個 JSON 物件（不要任何其他文字）。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 400,
        "stream": False,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    to = timeout or DEEP_ANALYZE_TIMEOUT
    try:
        r = requests.post(QWEN_URL, json=payload, timeout=to,
                          headers={"Content-Type": "application/json"})
        r.raise_for_status()
        data = r.json()
        try:
            resp = data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            resp = ""

        # resp 可能本身就是 JSON 字串，處理可能回傳的 Markdown code block
        parsed = {}
        if isinstance(resp, str):
            import json, re
            try:
                parsed = json.loads(resp)
            except Exception:
                m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", resp, re.DOTALL)
                if m:
                    try:
                        parsed = json.loads(m.group(1))
                    except:
                        pass
                if not parsed:
                    m = re.search(r"\{.*\}", resp, re.DOTALL)
                    if m:
                        try:
                            parsed = json.loads(m.group(0))
                        except:
                            pass
        else:
            parsed = resp or {}
            
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
            "model": QWEN_MODEL,
        }
    except Exception as _e:
        print(f"[judge] deep_analyze failed: {_e}")
        return {}


def deep_analyze_ensemble(title: str, web_results: list, sources: list,
                          samples: int = None, timeout: float = None) -> dict:
    """多次取樣本機 LLM 以降低 7B 模型分數抖動；並回傳 std / 樣本數供前端說明。
    並發呼叫（ThreadPoolExecutor）控制總延遲約等於單次。
    註：27B 單次即穩定，預設單樣本（:8088 單槽下多樣本會互相排隊超時）。"""
    import concurrent.futures as _cf
    if os.environ.get("DEEP_ANALYZE_DISABLE", "0") == "1":
        return {}
    n = int(samples if samples is not None else os.environ.get("DEEP_ANALYZE_SAMPLES", "1"))
    n = max(1, min(n, 5))
    to = timeout or DEEP_ANALYZE_TIMEOUT

    # 排隊感知：只在後端是 :8088（單槽，常被 Hermes 長上下文佔用 100-330s）時才檢查；
    # deep-proxy（DeepSeek Web）走雲端排隊，不適用此邏輯。
    # 硬等只會吃滿逾時後拿到空結果 → 前端「沒有 qwen 回覆」。
    if "8088" in QWEN_URL:
        eta = qwen_queue_eta()
        if eta > QWEN_BUSY_ETA_SKIP:
            print(f"[judge] deep_analyze skipped: :8088 忙碌中 (queue eta≈{eta:.0f}s)", flush=True)
            return {"skipped": "qwen_busy", "queue_eta_s": round(eta, 1)}

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
    timings: Dict[str, float] = {}   # 各階段耗時（ms）：延遲診斷用，隨 /judge 回傳
    _t0 = time.perf_counter()

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
    main = _registrable_domain(host)

    # If domain is generic google.com aggregator or unknown, resolve media outlet from title/content
    if main in ("google.com", "unknown", "") or host == "news.google.com":
        search_text = (title or "") + " " + (content[:500] if content else "")
        for m_name, m_dom in MEDIA_NAME_TO_DOMAIN.items():
            if m_name in search_text:
                main = m_dom
                host = m_dom
                break

    # 1) Sentiment (Decoupled negative news reporting penalty)
    _t = time.perf_counter()
    s = _sentiment_batch([content])[0]
    timings["sentiment"] = round((time.perf_counter() - _t) * 1000, 1)
    abs_s = abs(s); sent_pts = DEFAULT_WEIGHTS["sentiment"]
    
    clickbait_keywords = ["震撼", "網全嚇傻", "竟然", "不看會後悔", "急了", "震撼彈", "太誇張", "傻眼", "敗類", "割韭菜"]
    has_clickbait = any(kw in (title + content[:300]) for kw in clickbait_keywords)
    is_mainstream = (main in TAIWAN_MAINSTREAM_DOMAINS or host in TAIWAN_MAINSTREAM_DOMAINS or main in FACT_CHECK_DOMAINS)
    is_blocked = (main in DYNAMIC_BLOCKLIST_DOMAINS or host in DYNAMIC_BLOCKLIST_DOMAINS)
    
    if abs_s <= 0.6:
        sent_pts = DEFAULT_WEIGHTS["sentiment"]
    elif abs_s <= 0.85:
        sent_pts = 12.0
    else:
        if is_mainstream and not has_clickbait:
            sent_pts = 10.0
        elif has_clickbait or main in UGC_DOMAINS or is_blocked:
            sent_pts = -DEFAULT_WEIGHTS["sentiment"]
        else:
            sent_pts = 5.0
    total += sent_pts
    # 2026-09-24：desc 加注區間語義，免得「-0.53 卻滿分」看起來像 bug（|s|≤0.6 中性不扣分是刻意設計：負面新聞報導≠情緒操弄）
    _sent_note = "（中性區間，不扣分）" if abs_s <= 0.6 else ""
    res["sentiment"] = {"score": sent_pts, "desc": f"{s:.2f}{_sent_note}", "weight": DEFAULT_WEIGHTS["sentiment"]}

    # 2) Domain (simple rules with redirect resolution support)
    
    dom_pts = 15.0  # Default for unknown standard HTTPS sites
    if main in FACT_CHECK_DOMAINS or host in FACT_CHECK_DOMAINS:
        dom_pts = DEFAULT_WEIGHTS["domain"]  # 滿分 (查核機構)
    elif main in TAIWAN_MAINSTREAM_DOMAINS or host in TAIWAN_MAINSTREAM_DOMAINS:
        dom_pts = DEFAULT_WEIGHTS["domain"]
    elif main in UGC_DOMAINS or host in UGC_DOMAINS or is_blocked:
        dom_pts = 0.0  # UGC platforms (social media) have 0 inherent credibility
        
    if parsed.scheme == "http":
        dom_pts -= 10.0  # Penalize plain HTTP
        
    dom_pts = max(0.0, dom_pts)  # Don't go below 0 for this metric to avoid UI weirdness
    total += dom_pts
    res["domain"] = {"score": dom_pts, "desc": main, "weight": DEFAULT_WEIGHTS["domain"]}

    # 查詢詞先算好（只依賴 title/content，供下面並行任務共用）
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

    # 3)/4)/6) 多源事實查核 + 5) Similarity + web_search 並行送出（網路 I/O 與 GPU 推理重疊）
    def _timed(_fn, *_a, **_k):
        _s = time.perf_counter()
        return (_fn(*_a, **_k), round((time.perf_counter() - _s) * 1000, 1))
    import concurrent.futures as _cf
    sources = []
    sim = 0.0
    web_results: List[Dict] = []
    with _cf.ThreadPoolExecutor(max_workers=3) as _ex:
        # 事實查核吃「標題＋內文」：抓取器常把站台宣傳字留在內文開頭，
        # 只傳 content 會讓 snippet[:300] 與關鍵字被垃圾污染（實例：UDN 經濟日報 LINE 烤肉文 → cofacts 誤報 not_found）
        _fc_text = (f"{title}。{content}" if title else content)
        _fu_fc = _ex.submit(_timed, get_all_fact_checks, _fc_text, timeout_api=15) \
            if MULTI_FC_AVAILABLE else None
        _fu_sim = _ex.submit(_timed, _similarity_batch, [content], refs)
        _fu_web = _ex.submit(_timed, _wsc.search, _query_src, max_results=6) \
            if (WEB_SEARCH_AVAILABLE and _wsc is not None) else None
        if _fu_fc is not None:
            sources, timings["fact_check"] = _fu_fc.result()
        _sim_list, timings["similarity"] = _fu_sim.result()
        sim = _sim_list[0]
        if _fu_web is not None:
            try:
                web_results, timings["web_search"] = _fu_web.result()
                _t0 = time.perf_counter()
                web_results = _web_search_fallback(_query_src, web_results)
                timings["web_search"] += round((time.perf_counter() - _t0) * 1000, 1)
            except Exception as _e:
                print(f"[judge] web_search failed: {_e}")

    # 3)/4)/6) 多源事實查核（Cofacts + Google + MyGoPen）共用一次查詢
    fc_pts = 0.0; fc_desc = "not_checked"
    fb_pts = 0.0; fb_desc = "none"
    tl_pts = 0.0; tl_desc = "unknown"
    if MULTI_FC_AVAILABLE:
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

    # 5) Similarity（已在上面並行算好）
    sim_pts = sim * DEFAULT_WEIGHTS["similarity"]
    total += sim_pts
    res["similarity"] = {"score": sim_pts, "desc": f"{sim:.2%}（標題—內文一致性，非真實性）", "weight": DEFAULT_WEIGHTS["similarity"]}

    # 6) Timeliness 寫入
    res["timeliness"] = {"score": tl_pts, "desc": tl_desc, "weight": DEFAULT_WEIGHTS["timeliness"]}

    # web_results 已在上面並行取得（失敗則為空 list，前端自動隱藏該區塊）

    final = (total / avail) * 100 if avail > 0 else 0.0
    rule_score = final
    # 深入分析：本機 LLM 把 web_results + 查核源結論轉為結構化分析（多次取樣降抖動）
    deep = {}
    if web_results or sources:
        try:
            _t = time.perf_counter()
            deep = deep_analyze_ensemble(_title_clean or content[:60], web_results, sources)
            timings["deep_analyze"] = round((time.perf_counter() - _t) * 1000, 1)
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
        # 2026-09-24：缺相似度一律視為 0（未知≠有信心；舊 mygopen/google 結果無此欄，曾被 or 1.0 誤判 100% 硬錨定）
        sim_score = float(_s.get('similarity_score') or 0.0)
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
        "timings": {**timings, "scoring": round((time.perf_counter() - _t0) * 1000, 1)},
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


# FB 登入牆的明確字句（只信這些，不用 title 前綴）
_LOGIN_WALL_PHRASES = (
    "必須登入才能繼續", "You must log in to continue",
    "請先登入", "Log into Facebook", "ログインして続行",
)


def _clean_fb_title(title: str) -> str:
    """清掉 FB 標題的未讀通知前綴 '(N) ' 與 ' | Facebook' 尾綴（避免污染搜尋詞與標題）。"""
    import re as _re
    t = _re.sub(r'^\(\d+\)\s*', '', (title or "").strip())
    t = _re.sub(r'\s*\|\s*Facebook\s*$', '', t).strip()
    return t


def _looks_like_login_wall(title: str, content: str) -> bool:
    """判斷是否為 FB 登入牆/空殼頁。

    舊版用 `title.startswith("(1) ")` 當訊號是錯的——FB 正常登入頁面的標題
    也會帶未讀通知前綴 '(1) '，導致所有 FB 連結被誤判為登入牆。
    改以「內文是否為登入字句 / 標題是否就是 Facebook 且內文極短」判斷。
    """
    t = (title or "").strip()
    c = (content or "").strip()
    if not c:
        return True
    if any(p in c for p in _LOGIN_WALL_PHRASES) and len(c) < 400:
        return True
    if t in ("Facebook", "Facebook - 登入或註冊", "Facebook – log in or sign up") and len(c) < 300:
        return True
    return False


_NA_EXTRACT_PROFILE = os.path.expanduser("~/.config/google-chrome-na-extract")


def _inject_local_cookies(driver, url: str) -> int:
    """導覽到目標網域後，注入本機 Chrome 解密出的 cookie（目前涵蓋 Facebook/Messenger）。

    為什麼要注入：改用專屬 profile 後就沒有使用者的登入狀態，登入牆頁面會讀不到內容。
    回傳注入筆數；失敗不拋例外（fallback 不該讓主流程失敗）。
    """
    try:
        import fb_session
        from urllib.parse import urlparse
        host = (urlparse(url).netloc or "").lower()
        if not host:
            return 0
        cookies = []
        for c in fb_session.extract_facebook_cookies():
            dom = (c.get("domain") or "").lstrip(".").lower()
            if dom and (host == dom or host.endswith("." + dom)):
                cookies.append(c)
        if not cookies:
            return 0
        driver.get(f"https://{host}/")      # 必須先在同網域頁面才能 add_cookie
        n = 0
        for c in cookies:
            try:
                driver.add_cookie({"name": c["name"], "value": c["value"], "path": c.get("path", "/"),
                                   "secure": bool(c.get("secure")), "httpOnly": bool(c.get("httpOnly"))})
                n += 1
            except Exception:
                pass
        return n
    except Exception as e:
        print(f"[extract_selenium] cookie 注入失敗: {type(e).__name__}: {str(e)[:120]}")
        return 0


def _extract_with_selenium(url: str, timeout: int = 20) -> Optional[Dict]:
    """Headless Chrome fallback for JS-rendered or login-walled pages."""
    if not SELENIUM_AVAILABLE:
        return None
    opts = ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    # ⚠️ 不可用使用者的主 profile：桌面 Chrome 常駐佔用 SingletonLock（實測自 9/19 一直被佔），
    # 第二個實例必然起不來，例外又被吞掉 → 這條 fallback 會長期靜默失效。
    # 改用專屬 profile，並注入本機解密的 cookie 來維持登入牆頁面的可讀性。
    opts.add_argument(f"--user-data-dir={_NA_EXTRACT_PROFILE}")
    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(timeout)
        _inject_local_cookies(driver, url)
        driver.get(url)
        import time; time.sleep(2)
        title = driver.title or ""
        body = driver.find_element(By.TAG_NAME, "body").text or ""
        if len(body.strip()) < 30:
            return None
        return {"title": title, "content": body[:4000], "source": url, "publish_date": None}
    except Exception as e:
        print(f"[extract_selenium] 失敗 {url[:70]}: {type(e).__name__}: {str(e)[:120]}")
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
                    text = fb_result.get("text", "")
                    title = fb_result.get("title", "")
                    if fb_result.get("login_wall"):
                        # 真登入牆（session 失效）→ 不硬吞，交給 judge 端的還原/422 邏輯
                        print("[FB Session] ⚠️ 偵測到登入牆，改用 fallback")
                    elif len(text.strip()) >= 100:
                        kind = "貼文本體" if fb_result.get("is_post_body") else "頁面內容"
                        print(f"[FB Session] ✅ 成功擷取{kind}，內容長度: {len(text)} 字元")
                        return {
                            "title": title,
                            "content": text[:4000],
                            "source": url,
                            "publish_date": fb_result.get("publish_date"),
                        }
                    else:
                        print(f"[FB Session] ⚠️ 擷取內容過短 ({len(text.strip())} 字元)，嘗試 fallback")
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
    load_domain_lists()  # 名單檔變動時免重啟重載（mtime 檢查，約毫秒級）
    data = request.get_json(force=True)
    url = data.get("url", "")
    content = data.get("postText") or data.get("content", "")
    title = data.get("title", "")
    extracted: dict = {}
    _t_request = time.perf_counter()
    extract_ms = None

    # 若只有 URL 沒有內容 → 自動抓取
    if not content and url:
        _t_extract = time.perf_counter()
        extracted = _extract_from_url(url)
        extract_ms = round((time.perf_counter() - _t_extract) * 1000, 1)
        print(f"DEBUG_EXTRACT_RESULT: {repr(extracted)[:400]}")
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

    # Facebook 登入牆防護（2026-09-23 重寫）
    # 舊版把 title.startswith("(1) ") 當登入牆訊號 —— 但 FB 正常登入的頁面標題本來就帶未讀通知前綴，
    # 導致「所有」FB 連結被誤判；接著又用 Cofacts 的短匹配覆寫已抓好的內文（2463 → 44 字），
    # 最後必然踩 len(content)<100 → 422。使用者感受到的就是「FB 連結突然不能用」。
    # 新版：① 只信真正的登入牆訊號 ② Cofacts 還原僅在「更長」時採用 ③ 內容足夠就直接分析。
    if _looks_like_login_wall(title, content):
        restored = False
        if COFACTS_LOCAL_AVAILABLE and url:
            try:
                print(f"[Judge Fallback] 嘗試從 Cofacts 資料庫自動還原: {url}")
                cf_match = get_fact_check(url)
                t_match = ((cf_match or {}).get("matched_text") or "").strip()
                if len(t_match) >= 20 and len(t_match) > len(content.strip()):
                    content = t_match[:4000]
                    first_l = t_match.splitlines()[0][:80] if t_match.splitlines() else ""
                    title = first_l or "Facebook 存檔貼文"
                    restored = True
                    print(f"[Judge Fallback] 成功還原 FB 貼文內容 ({len(content)} 字元)")
            except Exception as e:
                print(f"[Judge Fallback] 錯誤: {e}")

        if not restored:
            return {"error": "Facebook 阻擋了自動抓取（偵測到登入牆，或需要不同登入權限）。\n請直接「複製貼文文字」並貼上來進行分析！"}, 422

    if len(content.strip()) < 20:
        return {"error": "擷取到的內容過短（<20 字），無法分析。\n請直接「複製貼文文字」並貼上來進行分析！"}, 422

    # 清掉 FB 標題雜訊（未讀通知前綴 / ' | Facebook' 尾綴），避免污染搜尋詞與情緒判斷
    if "facebook.com" in (url or "").lower():
        title = _clean_fb_title(title) or title

    score = analyze_article_data(title=title, url=url, content=content, publish_date=extracted.get("publish_date"), target_url=extracted.get("source"))
    timings = dict(score.get("timings") or {})
    if extract_ms is not None:
        timings["extract"] = extract_ms
    timings["total"] = round((time.perf_counter() - _t_request) * 1000, 1)
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
        "timings": timings,
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

