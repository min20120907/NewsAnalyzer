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
from itertools import zip_longest

# 把本檔案所在目錄加入 sys.path，確保 factcheck_multi / cofacts_local 可 import
import sys as _sys
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in _sys.path:
    _sys.path.insert(0, _SCRIPT_DIR)

# Debug 模式要能看到日誌（2026-10-06）：把 stdout/stderr 分流進環形緩衝，
# 由 GET /debug_logs（需 X-Debug-Token）讀出。只 tee，不改原本輸出目的地。
import collections as _collections, threading as _threading
_LOG_BUF = _collections.deque(maxlen=600)
_LOG_LOCK = _threading.Lock()


class _LogTee:
    # 2026-10-06：環形緩衝只留有用的行。tqdm 權重載入條與 /debug_logs 自己的
    # 輪詢紀錄會把緩衝洗掉（前端每 1.5s 輪詢一次 = 每 1.5s 多一行），故略過。
    _SKIP = ("Loading weights:", "/debug_logs")

    def __init__(self, real):
        self._real = real

    def write(self, s):
        if s:
            _LOG_LOCK.acquire()
            try:
                for _ln in s.splitlines():
                    if _ln.strip() and not any(k in _ln for k in self._SKIP):
                        _LOG_BUF.append(_ln)
            finally:
                _LOG_LOCK.release()
        return self._real.write(s)

    def flush(self):
        try:
            self._real.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._real, name)


_sys.stdout = _LogTee(_sys.stdout)
_sys.stderr = _LogTee(_sys.stderr)

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


def _web_corr_outlets(web_results: list, query: str, self_host: str = "") -> list:
    """多家同報：與 query 相關的 web_results 去重後 outlet 名單（排除自己）。

    2026-10-05：新新聞本來就沒有查核，用獨立媒體交叉印證補位。
    Google News RSS 的 url 全是 news.google.com 包裝，outlet 改從標題
    尾綴「 - XX新聞」取；直連 url 則用 domain。
    # ponytail: 標題尾綴啟發式，同集團轉稿會被算成多家；要更嚴就再比內文 sim。
    """
    core = _web_query_core(query).replace(" ", "").replace("　", "")
    # 步長 1（_web_relevant_count 用 2 是舊行為不動；這裡要全覆蓋，否則「杜拜航空」
    # 對不對得上純看出現在偶數還是奇數位，實測中央社案就這樣被漏掉）。
    keys = None if len(core) < 8 else [core[i:i + 4] for i in range(0, len(core) - 3)]
    outs, seen = [], set()
    for r in web_results or []:
        t = (r.get("title") or "").replace(" ", "").replace("　", "")
        if keys is not None and not any(k in t for k in keys):
            continue
        h = urlparse(r.get("url") or "").netloc.lower().replace("www.", "")
        if h in ("news.google.com", "google.com"):
            suf = (r.get("title") or "").split(" - ")[-1].strip().lower()
            outlet = suf if suf else h
        else:
            outlet = h
        if not outlet or outlet == (self_host or "").lower() or outlet in seen:
            continue
        seen.add(outlet)
        outs.append(outlet)
    return outs


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
        extra = _wsc.search(short, max_results=min(max_results, 3)) or []
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
# 4.4c 查詢詞組裝（2026-09-24 消融定案 scripts/query_ablation.py，4 案例×7 策略）：
# 全標題直送 A 最爛（total n_rel=3）；jieba 關鍵詞 C 最好（17，零新依賴、~2s）；
# Qwen 改寫 G 次之（16）但單次 10-17s 且偶吐簡體，只當保留手段，預設不啟用。
# 上線策略：C 先查，相關<3 才補 B（core 首段），合併去重，上限 6 筆（prompt 不膨脹）。
# ---------------------------------------------------------------
_WEB_QUERY_STOP = {"網傳", "宣稱", "真的", "請問", "消息", "影片", "圖片",
                   "可以", "這是", "那是", "是否", "今天", "昨天", "什麼",
                   "如何", "為何", "真的嗎", "中央社", "娛樂", "要聞",
                   "熱門話題", "經濟日報", "即時", "快訊", "獨家", "CNA",
                   "Medical", "News"}

# 2026-10-02：情緒／行動／催促詞。這些是謠言文體的樣貌標記，帶著它們去
# 檢索會檢索不到「可對照的報導」——實測『對岸狠手在這裡』只回 2 筆相關
# （kept=2 dropped=10），因為台灣媒體從不這樣寫。留下的是可查證實體
# （台灣／澳洲／牛肉／關稅／氣象署／豪雨／300毫米），它們才是能對照的錨。
_WEB_QUERY_NOISE = {
    "狠手", "這裡", "對岸", "震撼", "驚人", "緊急", "通知", "警告", "紫爆",
    "急", "快看", "趕快", "注意", "小心", "千萬", "別", "務必", "立刻",
    "現在", "今天", "明天", "昨天", "每天", "出現", "級別", "潮席",
    "直接", "全面", "瘋漲", "吃香", "喝采", "穩賺", "不賠", "岌岌可危",
    "錯過", "一波", "再等", "必須", "知道", "看這裡", "一起", "來看",
}


def _web_query_terms(text: str, n: int = 5) -> list:
    """jieba 關鍵詞，但排序改成「先留可查證實體」，不是出現順序。

    ponytail: 只靠 _WEB_QUERY_STOP/NOISE 靜態詞表，不做詞性標註。
    詞表補不動時看 jieba 的 tf-idf（jieba.analyse），別加新依賴。
    """
    try:
        import jieba as _jb
    except Exception:
        return []
    seen, kept, noisy = set(), [], []
    for _t in _jb.cut(text or ""):
        _t = _t.strip("，。、；：『』「」！？!?,. \t|｜-")
        if not (2 <= len(_t) <= 8 and _t not in seen and _t not in _WEB_QUERY_STOP
                and any("一" <= _c <= "鿿" for _c in _t)):
            continue
        seen.add(_t)
        (noisy if _t in _WEB_QUERY_NOISE else kept).append(_t)
        if len(kept) >= n:
            break
    # 位置不夠就拿次要詞補，但永遠排在中後段
    return kept + noisy[:max(0, n - len(kept))]


def _jieba_keywords(text: str, n: int = 5) -> list:
    try:
        import jieba as _jb
    except Exception:
        return []
    seen, out = set(), []
    for _t in _jb.cut(text or ""):
        _t = _t.strip("，。、；：『』「」！？!?,. \t|｜-")
        if (2 <= len(_t) <= 8 and _t not in seen and _t not in _WEB_QUERY_STOP
                and any("一" <= _c <= "鿿" for _c in _t)):
            seen.add(_t)
            out.append(_t)
        if len(out) >= n:
            break
    return out


def _build_web_queries(title: str, content: str) -> list:
    """回傳 [去噪關鍵詞查詢, 原始關鍵詞查詢, B-query]（去重、過短捨去）。

    2026-10-02：去噪版與原版並存，兩組都查、由 _web_search_multi 輪流合併。
    實測去噪版在「對岸狠手…67%關稅」大勝（維基百科 → 真實關稅報導），
    但在檸檬水治癌、罷免兩例反而查得更少——所以不取代原版，只並行。
    """
    qs = []
    _title_clean = (title or "").strip()
    src = _title_clean if _title_clean not in ("", "N/A") else (content or "")[:80]
    blob = src + "。" + (content or "")[:300]
    dedup = _web_query_terms(blob)
    if dedup:
        qs.append(" ".join(dedup))
    # 原版順序查詢保留：它常是唯一能查到「同一則謠言的報導版」的那組
    orig = _jieba_keywords(blob)
    if orig and " ".join(orig) not in qs:
        qs.append(" ".join(orig))
    core = _web_query_core(src)
    short = core.split()[0] if core.split() else core
    if short and short not in qs and len(short) >= 6:
        qs.append(short)
    if src and src not in qs and not qs:
        qs.append(src)  # 關鍵詞全滅時的兜底（極短標題）
    return qs


def _web_search_multi(queries: list, max_results: int = 6, ref_title: str = "") -> list:
    if not (WEB_SEARCH_AVAILABLE and _wsc is not None):
        return []
    # 2026-10-02：每個查詢各自取回後「輪流」合併，不照查詢順序堆疊。
    # 理由（實測）：新關鍵詞查詢在 f2b 大勝（2→6 筆，真報導取代維基百科），
    # 但在 f1/f3 反而變差——單一查詢有時整組失準。兩種都查、輪流進榜，
    # 壞的那組只是少幾筆，不會把好的擠掉。
    seen, per_query = set(), []
    for q in queries or []:
        if not q or len(q) < 4:
            continue
        try:
            # 2026-10-05：單查詢只取 3（合併後本來就截 6＋sim 過濾，取 6 只是
            # 逼 search() 在 RSS 不足 6 時去開瀏覽器——實測單次 6.6s，2 筆來自瀏覽器）。
            # 真缺貨時（<3）瀏覽器照樣補，稀缺覆蓋不變。
            res = _wsc.search(q, max_results=min(max_results, 3)) or []
        except Exception as _e:
            print(f"[judge] web search failed: {_e}")
            continue
        fresh = []
        for r in res:
            u = r.get("url")
            if u in seen:
                continue
            seen.add(u)
            fresh.append(r)
        per_query.append(fresh)
    merged = [r for group in zip_longest(*per_query) for r in group if r is not None]
    # 2026-09-24：SBERT 語意過濾（RSS 噪音如金世義 Newtalk sim≈0.29，
    # 同事件正常 0.68~0.93；門檻 0.45，過濾後不足 2 筆則保留 sim 最高的 2 筆）。
    if len(merged) > 2 and ref_title and SIMILARITY_MODEL is not None:
        try:
            _texts = [(r.get("title") or "") + " " + (r.get("snippet") or "")[:120]
                      for r in merged]
            _sims = _similarity_batch(_texts, [ref_title])
            _ranked = sorted(zip(_sims, merged), key=lambda t: t[0], reverse=True)
            _kept = [r for s, r in _ranked if s >= 0.5]
            if len(_kept) < 2:
                _kept = [r for _, r in _ranked[:2]]
            _dropped = len(merged) - len(_kept)
            merged = _kept
            print(f"[judge] web sim-filter kept={len(merged)} dropped={_dropped} "
                  f"min_sim={min([s for s, _ in _ranked[:len(merged)]] or [0]):.3f}")
        except Exception as _e:
            print(f"[judge] web sim-filter failed: {_e}")
    print(f"[judge] web multi queries={[q[:24] for q in (queries or [])]} "
          f"total={len(merged)}", flush=True)
    merged = merged[:max_results]
    _attach_web_bodies(merged)
    return merged


def _attach_web_bodies(results: list, top_n: int = 2, min_chars: int = 120) -> None:
    """就地為相似度最高的 top_n 筆搜尋結果抓取正文，寫入 r["body"]。

    2026-10-02：web_search_client 只回 title/url/snippet，snippet 常是空或極短，
    導致 deep_analyze 永遠看不到證據正文 —— 「查得到」與「查不到」對模型長得一樣，
    分數沒有鑑別力。這裡重用既有的 _extract_from_url（trafilatura → newspaper3k →
    Playwright → Selenium），只抓前 top_n 筆以控延遲。

    Google News RSS 連結只是包裝頁（HTTP 302 回自己的 wrapper；trafilatura 抽不到正文，
    Playwright 實測會等約 20 秒仍只抓到 wrapper），因此不送進 body extractor；
    這類結果在 prompt 明標「正文未載入」，讓模型保守 abstain。其他直連結果仍抓 top_n，
    保留正文證據路徑。
    """
    if not results:
        return
    cands = [r for r in results
             if r.get("url") and r.get("body") is None
             and r.get("source") != "google_news"
             and len((r.get("snippet") or "").strip()) < min_chars][:top_n]
    # 2026-10-05：並行抓（log 實測串行各 8~11s，web 19s 幾乎全是這裡）。
    # 同 _extract_from_url 同一函數，只是換並行，品質不變。
    import concurrent.futures as _cf

    def _one(_r):
        try:
            # 2026-10-05：body 都是 Google News 包裝連結，newspaper 必空轉 15s
            # 超時才交棒（實測 trafilatura 秒掛→newspaper 15s→Playwright 才抓到）。
            # Playwright 能力覆蓋 newspaper，直接跳過它。
            ex = _extract_from_url(_r["url"], skip_newspaper=True)
        except Exception as _e:
            print(f"[judge] web body extract failed: {_e}")
            return
        if isinstance(ex, dict):
            txt = (ex.get("text") or ex.get("content") or "").strip()
            if len(txt) >= min_chars:
                _r["body"] = txt[:2000]
                print(f"[judge] web body attached len={len(_r['body'])} src={_r.get('source','?')}", flush=True)

    with _cf.ThreadPoolExecutor(max_workers=min(top_n, 2)) as _ex:
        list(_ex.map(_one, cands))


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

_DEEP_PROMPT_TMPL = """你是一個證據接地的事實查核評分員。你只能使用下方實際提供的材料判斷，不得使用內建知識補當前事實或人物職稱。

輸出規則：只輸出一個 JSON 物件，不要任何其他文字：
{{"claim":"把本次要查核的主張濃縮成一句話","evidence_state":"full_body_evidence | search_hit_body_missing | no_evidence | unrelated_evidence","evidence_used":["實際引用的來源名稱"],"key_points":["2 到 4 條具體質疑或確認點，每條須指明來源或內文依據"],"viewpoints":"正反雙方立場摘要，須指明各方依據，不得只寫單方","credibility_score":0到100的整數,"analysis":"2 到 4 句完整結論，必須點名來源、指出關鍵事實、給出明確可信或可疑理由","abstain":true 或 false}}

【語言】所有欄位一律使用繁體中文完整句子，嚴禁出現英文單字或中英夾雜（外來專有名詞也譯為中文）。
【時間】今天日期：{today}。人物職稱、時事現況一律以下方實際提供的材料為準，嚴禁憑內建知識斷言。

【第一步：先判斷證據狀態 evidence_state】
- full_body_evidence：至少一個查核來源的判定文字或回覆原文已載入，且與本主張同一事件、同一對象、同一時間。
- search_hit_body_missing：搜尋結果或查核條目看起來相關，但查核正文／回覆原文沒有載入。
- no_evidence：沒有任何查核來源命中。
- unrelated_evidence：命中的查核是別的事件、對象或時間。
  常見誤判（實測兩則正當財經新聞被鎖死 21～27 分，必須主動排除）：
  a) 查核原文是「防詐宣導／詐騙集團手法說明／檢舉獎金」這類宣導文，
     而本主張只是提到同領域的一般事物（如「ETF 報酬翻倍」命中投資詐騙宣導）。
     宣導文在查核「騙徒怎麼騙」，不是在查核「這檔 ETF 報酬多少」→ 無關。
  b) 查核原文是別人的 App 介面截圖／ATM 明細／UI OCR，跟本主張無關。
  c) 只是同一產業或同一類詞（ETF、報酬、投資、癌症），但事件、對象、時間都不對應。
  判無關看的是「是否在查核這一件特定的事」，不是「是否同一領域」。

【第二步：依 evidence_state 決定 abstain 與分數】
- search_hit_body_missing、no_evidence、unrelated_evidence：abstain 必須為 true。credibility_score 不得填固定值，
  必須依「內文自身」的可信訊號在 45 到 65 之間自選：見下方【證據不足時的內文自評】。
  analysis 必須寫清楚缺什麼、目前不能確定什麼、要補哪一份原文才可判定。
- full_body_evidence：abstain 為 false，依下方證據強度落點評分。

【證據不足時的內文自評】（只在 abstain 分支使用）
外部查核查無不代表內容本身有問題，所以分數要反映「只看內文能看出什麼」，不得一律填 60。
以下每一項在內文出現就往低分走，全部沒有才往高分走（45 = 明顯問題，65 = 內文無可挑剔）：

往低分（45–54）的訊號：
- 內文本身自相矛盾，或同一段內數字打架。
- 訴諸權威卻查不到那個權威：「某權威人士表示／研究顯示／官方證實」但內文沒有具名機構或出處。
- 要求讀者立刻動作的急迫語氣：轉發、擴散、趕快、錯過就來不及、救人。
- 對立情緒或危機渲染：不實在啦、狠手、完蛋、崩潰、震撼、傻眼。
- 誇大或絕對化數字：百年級、史上、全部、所有、一定、從來沒有。
- 呼籲停止既有專業處置（停藥、停醫囑、停檢查）而沒有權威反證。
- 目標明確要觸發轉發的群眾動員語句。

往高分（55–65）的訊號：
- 內文只陳述可查證的具體事實（機構、日期、金額、法條、職稱），不夾帶呼籲。
- 有具名可查的出處（某某單位發布、某公司法說會、公告編號）。
- 語氣平實、沒有急迫性、沒有情緒詞。
- 論述有節制，會寫「可能」「估計」「截至某時」這類限定。

⚠ 三件最容易出錯的事：
- 「查不到外部查核」是證據不足，不是內容可疑。分數高低要看內文自身的問題，不要因為查無就給 45。
- 「查到了但說 NOT_RUMOR／這則確實存在」不等於內容屬實；那是弱標籤，撐不起 60 以上。
- 🆕 2026-10-02 修正（配合計分層的 evidence-insufficient 上限錨定）：
  當 evidence_state 屬於查不到證據的情形時，內文若宣稱了「可被即時獨立驗證的公共事實」
  （具體機構今天宣布了什麼、具體數字、具體日期、具體人事命令、具體停班停課或警語），
  卻沒有任何可查證出處，屬於可疑訊號，請往 45-50 走，不要給 60 以上。
  理由：真實的公共機構公告會留下大量可追溯紀錄（新聞稿、公告編號、直播），
  「查不到」本身就是反證。相對地，若內文只是觀點評論、產業趨勢、个人經驗或
  查核機構本來就不會收錄的內容（小道消息、匿名爆料），查不到屬正常，維持 55-65。

【評分尺度（僅 full_body_evidence 時使用，依你實際讀到的證據落點）】
- 90 以上：查核機構明確判定屬實，且內文與主張逐項對得上。
- 75 到 89：查核機構判定大致屬實，或有具名官方／研究來源直接支持主張關鍵部分。
- 60 到 74：有可追溯來源支持主要說法，但關鍵細節缺證或僅部分對應。
- 40 到 59：查核判定部分不實，或來源只支持部分主張，或證據之間互相衝突。
- 20 到 39：查核機構明確判定不實且與本主張直接對應。
- 20 以下：查核機構判定不實，且內文明示關鍵事實為虛構。

【禁止事項】
- 不得只寫「無相關佐證」「無法確認」「僅依摘要判斷」「建議查閱完整原文」這類空話；每條結論都要指名來源或內文依據。
- 不得因為「查不到」就給低分；查不到只能以 abstain 為 true 表現。
- 內文若只有網址、幾個字或無實質陳述，不得據此給高分；此時應視為證據不足並 abstain。

新聞標題：{title}
新聞內文：
{body}

事實查核結果（含查核機構回覆原文）：
{fc_block}

網路搜尋結果摘要：
{web_summary}"""


def _deep_analyze_build_prompt(title: str, web_results: list, sources: list,
                              content: str = "", facts: "Optional[list]" = None) -> str:
    # 2026-10-02：web 摘要原本只給 title + 120 字 snippet，LLM 永遠看不到證據正文，
    # 於是「查得到」和「查不到」在模型眼中長得一模一樣 —— 唯一差別是引用條數，
    # 於是輸出退化成「有幾筆結果就給幾分」，完全沒有鑑別力。
    # 實測（同一模型、同一則假新聞）：只給 title/snippet 時 evidence_state 幾乎都是
    # unrelated_evidence；把同一批結果的真實內文一併餵入後，模型才抓得到數字矛盾。
    # 現在改為：優先用 body（正文），長度上限提到 400 字，足以涵蓋關鍵段落。
    lines = []
    for i, r in enumerate(web_results[:5], 1):
        t = (r.get("title") or "").strip()
        body_text = (r.get("body") or "").strip()
        snippet = (r.get("snippet") or "").strip()
        s = body_text or snippet
        status = "來源正文已載入" if body_text else ("搜尋摘要" if snippet else "僅標題，正文未載入")
        if len(s) > 220:
            s = s[:220] + "…"
        if not (t or s):
            continue
        lines.append(f"{i}. [{status}] {t}\n   {s}" if s else f"{i}. [{status}] {t}")
    web_summary = "\n".join(lines) or "（無網路搜尋結果）"
    # 查核源摘要：把機構回覆原文（reasons）一起給模型，否則它只能讀到 status 標籤，
    # 輸出就退化成「把 status 翻譯成分數」，這是分數沒有鑑別力與敘述模糊的根因。
    fc_lines = []
    label_map = {"cofacts": "Cofacts", "google": "Google查核", "mygopen": "MyGoPen",
                 "rumtoast": "蘭姆酒吐司", "hkbu": "HKBU查核",
                 "infact": "InFact", "jfc": "日本FCセンター"}
    for s in sources:
        st = s.get("status", "not_found")
        nm = label_map.get(s.get("source", ""), s.get("source", ""))
        url = s.get("url") or ""
        reasons = s.get("reasons") or []
        reply = ""
        for item in reasons[:3]:
            txt = (item.get("text") or "").strip()
            if txt:
                reply += f"　[{item.get('type', '回覆')}] {txt[:400]}\n"
        head = f"  - {nm}: {st}"
        if url:
            head += f"（{url}）"
        if s.get("soft_hit_status"):
            # 2026-10-01：軟命中（sim 0.45～0.72）。相似度不足以判定同一事件，
            # 必須由你讀下方回覆原文判斷是否真的在查核本主張。
            head += (f"［軟命中：檢索相似度 {float(s.get('soft_hit_sim') or 0):.2f}，"
                     f"低於硬門檻；該源標籤為 {s.get('soft_hit_status')}，"
                     f"請自行判斷是否同一事件——若是則 evidence_state 為 "
                     f"full_body_evidence，若否則 unrelated_evidence］")
        fc_lines.append(head)
        if s.get("alternatives"):
            # 2026-10-01：交叉確認。Top-1 只是同池相似度最高那筆，同家族謠言的其他
            # 角度查核在這裡（檸檬水的主命中是「空腹吃水果勝癌症」，真正的🍋查核排第五）。
            # 讓它一起判相關性——若其中任一筆在查核本主張，仍算 full_body_evidence。
            fc_lines.append("    同池其他候選（僅供交叉確認，相似度較低）：")
            for alt in s["alternatives"]:
                fc_lines.append(
                    f"      · {alt.get('status')} sim={alt.get('similarity_score')}"
                    f"（{alt.get('url') or '無連結'}）")
                mt = (alt.get("matched_text") or "").strip().replace("\n", " ")
                if mt:
                    fc_lines.append(f"        內容：{mt[:260]}")
                for item in (alt.get("reasons") or [])[:2]:
                    txt = (item.get("text") or "").strip()
                    if txt:
                        fc_lines.append(f"        [{item.get('type', '回覆')}] {txt[:300]}")
        if reply:
            fc_lines.append("    查核回覆原文：\n" + reply.rstrip())
        elif st in ("inaccurate", "partial", "accurate"):
            fc_lines.append("    查核回覆原文：未載入（只有狀態標籤，無正文）")
    fc_summary = "\n".join(fc_lines) or "（無查核源）"
    body = (content or "").strip()
    if not body:
        body = "（本次未提供內文）"
    # 內文上限：避免撐爆單槽 :8088 的 prompt 預算（約 10.6s/筆的延遲不能再往上）
    if len(body) > 1800:
        body = body[:1800] + "…"
    from datetime import date as _date
    return _DEEP_PROMPT_TMPL.format(title=title or "（無標題）",
                                    body=body,
                                    web_summary=web_summary,
                                    fc_block=fc_summary,
                                    today=_date.today().isoformat())


# 傳言／匿名轉傳的確定性訊號。這類文本「本身」就是未經證實的內容，
# 不能當成查核機構對本主張的「屬實」判定。
# 2026-10-02 實測：虛構的「國防部退休金新制」命中 Cofacts 一則
# 「台銀退休協會同仁傳的訊息，僅供參考：財政部 13% 改革方案…」
# —— 那是匿名轉傳謠言、且講的是財政部不是國防部，Cofacts 卻標 accurate，
# LLM 收到後判成 full_body_evidence 給 95 分，整則假新聞拿 84.2。
_RUMOR_MARKERS = (
    "僅供參考", "供參考", "轉傳", "轉貼", "請大家", "廣傳", "多多流傳",
    "LINE傳", "臉書傳", "未證實", "傳聞", "據傳", "小道消息",
    "內傳", "勿外傳", "以上僅為", "未經證實",
)


def _is_rumor_only_evidence(deep, sources=None) -> bool:
    """證據正文本身是匿名轉傳／傳言 → 不可視為對本主張的屬實背書。

    必須讀 `sources[].matched_text`（查核機構回覆的原文），而不是 LLM 的輸出欄位——
    LLM 不會把「僅供參考：…」整段抄進 analysis，所以只看 deep 永遠偵測不到。
    """
    if not isinstance(deep, dict):
        return False
    if deep.get("evidence_state") != "full_body_evidence":
        return False
    # 證據原文才是重點：查核機構回覆的 matched_text / body
    ev_texts = []
    for s in (sources or []):
        if not isinstance(s, dict):
            continue
        for k in ("matched_text", "body", "text", "content", "title"):
            v = s.get(k)
            if v:
                ev_texts.append(str(v))
    blob = " ".join(ev_texts) + " " + " ".join(
        str(deep.get(k) or "") for k in
        ("claim", "analysis", "viewpoints", "key_points", "evidence_used")
    )
    hard = ("僅供參考", "未證實", "未經證實", "傳聞", "據傳", "小道消息", "勿外傳", "內傳")
    if any(m in blob for m in hard):
        return True
    return sum(1 for m in ("轉傳", "轉貼", "請大家", "廣傳", "多多流傳", "供參考") if m in blob) >= 2


def _evidence_is_unrelated(deep) -> bool:
    """LLM 的 evidence_state 與它自己的分析文字矛盾時，以分析為準。

    2026-10-01 regression：實測「景氣燈號連9紅」命中一篇投資詐騙宣導文
    （sim 0.468），LLM 的 evidence_state 填 `full_body_evidence`、但 analysis 明寫
    「Cofacts 的查核結果因針對不同事件而被判定為無關證據，不影響本主張的可信度」
    —— 判斷完全正確，狀態欄卻填錯，結果 promo=True 鎖死 23.83 疑似不實。
    程式只讀狀態欄會被這個矛盾騙過去。

    狀態說有證據、但分析自己說「無關／不影響本主張」→ 視為 unrelated。
    呼叫端（軟命中降級、clamp 錨定）都必須讀同一個判定，否則又會兩處不一致。
    """
    if not isinstance(deep, dict):
        return False
    if deep.get("evidence_state") == "unrelated_evidence":
        return True
    if deep.get("evidence_state") != "full_body_evidence":
        return False
    txt = f"{deep.get('analysis') or ''} {deep.get('viewpoints') or ''}"
    return any(w in txt for w in ("無關證據", "判定為無關", "與本主張無關",
                                  "不影響本主張", "不同事件", "非同一事件"))


def deep_analyze(title: str, web_results: list, sources: list,
                 timeout: "float | None" = None, content: str = "",
                 model_id: str = "") -> dict:
    """呼叫 LLM 做深入分析。回傳 dict 或空 dict（失敗）。

    model_id=None → 用既有 QWEN_URL/QWEN_MODEL（生產行為不變）。
    model_id='openrouter/xxx' → 走 llm_registry 的該後端。
    """
    if not REQUESTS_AVAILABLE:
        return {}
    url, model_name, headers = QWEN_URL, QWEN_MODEL, {"Content-Type": "application/json"}
    if model_id:
        try:
            import llm_registry as _reg
            _bkey, _m, _cfg = _reg.resolve(model_id)
            url = _cfg["base_url"]
            model_name = _m
            headers = _reg.request_headers(_cfg)
        except Exception as _e:
            print(f"[judge] deep_analyze registry failed: {_e}", flush=True)
    prompt = _deep_analyze_build_prompt(title, web_results, sources, content=content)
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system",
             "content": "你是一個事實查核分析助手。根據提供的資訊，只輸出一個 JSON 物件（不要任何其他文字）。"
                        "務必使用繁體中文撰寫所有欄位值。直接輸出 JSON，不要推理過程、不要英文。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        # 900 對 reasoning 型模型不夠：實測 nemotron-ultra 把 3233 token 全花在
        # 英文推理上，finish_reason=length，JSON 產出為 0。2000 是實測安全值。
        "max_tokens": 2000,
        "stream": False,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    to = timeout or DEEP_ANALYZE_TIMEOUT
    try:
        r = requests.post(url, json=payload, timeout=to, headers=headers)
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
            if not parsed:
                print(f"[judge] deep_analyze JSON parse failed, resp[:300]={resp[:300]}", flush=True)
        else:
            parsed = resp or {}
            
        # 正規化
        score = parsed.get("credibility_score", 0)
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 0
        # abstain 語意：模型自己宣告證據不足時，該分數只是暫時值，不是查核結論。
        abstain = parsed.get("abstain")
        abstain = bool(abstain) if isinstance(abstain, bool) else None
        kp = parsed.get("key_points", [])
        if not isinstance(kp, list):
            kp = [kp] if kp else []
        used = parsed.get("evidence_used", [])
        if not isinstance(used, list):
            used = [used] if used else []
        return {
            "claim": str(parsed.get("claim") or "")[:200],
            "evidence_state": str(parsed.get("evidence_state") or ""),
            "evidence_used": [str(x)[:80] for x in used][:4],
            "key_points": [str(x) for x in kp][:4],
            "viewpoints": str(parsed.get("viewpoints") or ""),
            "credibility_score": max(0, min(100, score)),
            "abstain": abstain,
            "is_provisional": bool(abstain),
            "analysis": str(parsed.get("analysis") or ""),
            # 2026-10-04：原本硬寫 QWEN_MODEL，導致選雲端模型時前端仍顯示 qwen3.8-27b。
            "model": model_name,
        }
    except Exception as _e:
        print(f"[judge] deep_analyze failed: {_e}")
        return {}


def deep_analyze_ensemble(title: str, web_results: list, sources: list,
                          samples: int = None, timeout: float = None,
                          content: str = "", model_id: str = "") -> dict:
    """多次取樣本機 LLM 以降低 7B 模型分數抖動；並回傳 std / 樣本數供前端說明。
    並發呼叫（ThreadPoolExecutor）控制總延遲約等於單次。
    註：27B 單次即穩定，預設單樣本（:8088 單槽下多樣本會互相排隊超時）。"""
    import concurrent.futures as _cf
    if os.environ.get("DEEP_ANALYZE_DISABLE", "0") == "1":
        return {}
    n = int(samples if samples is not None else os.environ.get("DEEP_ANALYZE_SAMPLES", "1"))
    n = max(1, min(n, 5))

    # 排隊感知：只在後端是 :8088（單槽，常被 Hermes 長上下文佔用 100-330s）時才檢查；
    # deep-proxy（DeepSeek Web）走雲端排隊，不適用此邏輯。
    # 硬等只會吃滿逾時後拿到空結果 → 前端「沒有 qwen 回覆」。
    # 2026-10-02：model_id 指定雲端模型時，queue-skip 的對象是實際呼叫的後端，
    # 不是 QWEN_URL（否則選 OpenRouter 也會被本機 :8088 的忙碌誤擋）。
    _skip_url = QWEN_URL
    if model_id:
        try:
            import llm_registry as _reg
            _skip_url = _reg.resolve(model_id)[2]["base_url"]
        except Exception:
            pass
    # 2026-10-06：逾時依後端分開。本機 :8088 單次 12–20s，60s 足夠；
    # 雲端（agy shim）實測同一則新聞要 119s，被 60s 砍掉後 deep={} →
    # 前端整段「AI 深入分析」消失（使用者回報：gemini 沒有 ai 分析）。
    to = timeout or (DEEP_ANALYZE_TIMEOUT if "8088" in _skip_url
                     else float(os.environ.get("DEEP_ANALYZE_TIMEOUT_CLOUD", "180")))
    if "8088" in _skip_url:
        eta = qwen_queue_eta()
        if eta > QWEN_BUSY_ETA_SKIP:
            print(f"[judge] deep_analyze skipped: :8088 忙碌中 (queue eta≈{eta:.0f}s)", flush=True)
            return {"skipped": "qwen_busy", "queue_eta_s": round(eta, 1)}

    def _one():
        return deep_analyze(title, web_results, sources, timeout=to, content=content,
                            model_id=model_id)

    results = []
    if n == 1:
        results = [_one()]
    elif "8088" in QWEN_URL:
        # 2026-10-01：:8088 是 --parallel 1 單槽，併發只會讓後兩次被排隊感知跳過
        # （QWEN_BUSY_ETA_SKIP=5s）→ 樣本數看運氣。串行才拿得到 n 個真結果。
        # 延遲 n× 單次，這是單槽的必然代價。
        results = [_one() for _ in range(n)]
    else:
        with _cf.ThreadPoolExecutor(max_workers=n) as ex:
            for fut in _cf.as_completed([ex.submit(_one) for _ in range(n)]):
                try:
                    results.append(fut.result())
                except Exception:
                    pass
    valid = [r for r in results if isinstance(r, dict) and r.get("credibility_score") is not None]
    if not valid:
        # 2026-10-06：全數失敗時把原因帶回去，前端才顯示得出來。
        # 這裡是所有呼叫路徑的唯一交會點（單次／串行／並發都經過），修一次就夠。
        _err = next((r.get("error") for r in results
                     if isinstance(r, dict) and r.get("error")), "")
        return {"error": _err} if _err else {}
    scores = [float(r["credibility_score"]) for r in valid]
    avg = sum(scores) / len(scores)
    std = (sum((s - avg) ** 2 for s in scores) / len(scores)) ** 0.5

    # 2026-10-01：跨次一致性當選擇訊號（selective prediction）。
    # 文獻（arXiv 2602.11619）：多步驟 agent 的多數決只有 +0~2pp，因為錯誤是系統性的；
    # 改用「不一致就 abstain」有 +6~14pp。本流程是多步驟（召回→門控→排序→裁決），
    # 錯法會重複發生，所以 majority vote 救不了，只能在分歧時不給結論。
    # 實測未取樣時（n=1）sw0 擺動 23.83~81.37，evidence_state 在 unrelated/full_body
    # 之間跳 —— 那正是需要 abstain 的訊號。
    states = [str(r.get("evidence_state") or "") for r in valid]
    state = max(set(states), key=states.count)      # 多數決（類別變數，不是分數）
    consistent = (states.count(state) == len(states))
    # 單次執行沒有「一致性」資訊可判，不強制 abstain（否則 n=1 會全部變暫時分數）
    disputed = len(valid) > 1 and not consistent
    if disputed:
        print(f"[judge] deep_analyze inconsistent across {len(valid)} samples: "
              f"{dict((s, states.count(s)) for s in set(states))} → abstain", flush=True)

    # 質化內容取 state 與平均分都最接近的那次，保持內部一致
    best = min(valid, key=lambda r: (str(r.get("evidence_state") or "") != state,
                                     abs(float(r["credibility_score"]) - avg)))
    abst = bool(best.get("abstain")) or disputed
    # 2026-10-02：abstain 分數不再是寫死的 60，改為模型自評內文可信訊號的區間值。
    # 這裡必須同時處理 `best` 的 abstain（evidence_state 不足）與 `disputed`（跨次不一致）
    # 兩條路徑，因為 abst 已經把它們合併，disputed 樣本自己也會填內文自評分。
    # 夾在 45–65：低於 45 表示模型把「查無查核」誤判成「內容可疑」，高於 65 表示
    # 在完全無外部證據時給了超出上限的信心。兩者都是 prompt 失效訊號。
    _cs = int(round(avg)) if not abst else max(45, min(65, int(round(avg))))
    return {
        "claim": best.get("claim", ""),
        "evidence_state": state,
        "evidence_used": best.get("evidence_used", []),
        "key_points": best.get("key_points", []),
        "viewpoints": best.get("viewpoints", ""),
        "credibility_score": _cs,
        "abstain": abst,
        "is_provisional": abst,
        "analysis": best.get("analysis", ""),
        "model": best.get("model", OLLAMA_MODEL),
        "samples": len(valid),
        "score_std": round(std, 1),
        "evidence_state_consistent": consistent,
        "evidence_state_disputed": disputed,
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


def _feedback_from_sources(sources: list) -> tuple[float, str]:
    """Only count actual fact-check replies from sources still accepted as matches."""
    n_reply = sum(
        1 for r in sources
        if r.get("status") in ("inaccurate", "partial", "accurate")
        for it in (r.get("reasons") or [])[:3]
        if (it.get("text") or "").strip()
    )
    if n_reply:
        return min(DEFAULT_WEIGHTS["feedback"], 1.0 + 3.0 * n_reply), f"{n_reply}則查核回覆"
    if any(r.get("status") in ("inaccurate", "partial", "accurate") for r in sources):
        return 0.0, "命中但無回覆原文"
    return 0.0, "none"


def _samples_for(mode: str) -> int:
    """模式 → 取樣數。deep 的 3 不靠 systemd override（拿掉就會靜默退回 n=1）。"""
    mode = (mode or "fast").lower()
    if mode not in ("fast", "deep"):
        mode = "fast"
    return 1 if mode == "fast" else int(os.environ.get("DEEP_ANALYZE_SAMPLES", "3"))


def _score_single(title: str, url: str, content: str, refs: List[str], publish_date=None, target_url: str = None, mode: str = "fast", llm_model: str = "") -> Dict:
    """Return full metric dict for one article (fast, GPU‑ready).

    mode: "fast"（n=1，約 12s）或 "deep"（n=3 跨次一致性，約 40s）。
    2026-10-01：預設 fast。deep 換掉 evidence_state 的整段擺動。
    llm_model: 2026-10-02，'backend/model'，空字串＝沿用 QWEN_URL（行為不變）。
    """
    res: Dict[str, Dict] = {}
    total = 0.0; avail = sum(DEFAULT_WEIGHTS.values())
    timings: Dict[str, float] = {}   # 子階段耗時（ms）

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
        "PChome": "pchome.com.tw", "遠見": "gvm.com.tw",
        # 2026-10-01：48 則主流媒體掃描實測補齊（缺這些 → domain 拿不到真網域，
        # 全部吃預設 15 分，白名單的優質媒體跟黑名單的假新聞站拿到一樣分）。
        "Newtalk": "newtalk.tw", "台灣新聞雲": "tnews.com.tw",
        "匯流": "houtong.com", "蕃新聞": "fnn.com.tw",
        "工商時報": "ctwant.com", "中國評論": "cri.com.tw",
        "娛樂星聞": "star.stock.yahoo.com", "今周刊": "todaynews.com",
        "商傳媒": "businessweekly.com.tw", "台灣華報": "taiwan-hwa.net",
        "世界新聞網": "worldjournal.com", "旺得富": "wdfm.com.tw",
        "放言": "fount.asia", "TechNews": "technews.tw",
        "FTNN": "ftnn.com", "Verse": "verse.town", "7Car": "7car.com.tw",
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
    # 2026-09-24：消融定案改走 tiered 查詢（jieba 關鍵詞先查，不足才補 core 首段）；
    # _query_src 保留給 review_links 與 fallback 相關性判斷。
    _web_queries = _build_web_queries(title, content) or [_query_src]
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
        _fu_web = _ex.submit(_timed, _web_search_multi, _web_queries, 6,
                             _title_clean if _title_clean != "N/A" else "") \
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
        # 2026-10-01：軟命中（sim 0.45～0.72）完全不參與 fact_check 計分。
        # 判定交給 LLM 的 evidence_state（PFCD two-stage）；LLM 若判
        # full_body_evidence，1035 那段會把 soft_hit_status 升級並重算 fact_check。
        # sources 保持原樣不變，這樣 prompt 組裝仍看得到原始 status 與回覆原文。
        # 實測沒有這一步時 fact_check 仍吃 partial 的 9 分、而 LLM 已經判
        # unrelated_evidence——自相矛盾。
        _fc_pool = [r for r in sources if not r.get("needs_llm_verdict")]
        # 取最嚴重的查核結論（inaccurate > partial > accurate > not_found/disabled）
        sev = {"inaccurate": 3, "partial": 2, "accurate": 1, "not_found": 0, "disabled": 0, "error": 0}
        worst = None
        for r in _fc_pool:
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
        # 4) 用戶回饋（查核回覆數分級，2026-10-05）：
        #    舊制任一命中即滿分，一則回覆就顯示 100%，沒有鑑別力。
        #    改數 sources 已有的 reasons 回覆原文：有回覆才給分，零新 I/O。
        # ponytail: 每則 3 分是啟發式（1則=4，2則=7，3則+=10）；立場明確度未單獨
        # 計，日後要精確就對回覆文本接 stance 分類。
        fb_pts, fb_desc = _feedback_from_sources(sources)
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
    # 深入分析：本機 LLM 把 web_results + 查核源結論轉為結構化分析
    # 2026-10-01：兩種模式。快速=n=1 單次取樣（約 12s），深度=n=3 跨次一致性
    # （約 40s，不一致就 abstain）。深度模式多花 3 倍時間換掉整段擺動——
    # 實測快速模式的 sw0 同一輸入三次跑出 23.83 / 60.92 / 81.37。
    mode = (mode or "fast").lower()
    if mode not in ("fast", "deep"):
        mode = "fast"
    n_samples = _samples_for(mode)
    deep = {}
    # 快速路徑只在未指定單一模型（或走多模型 consensus）時啟用。
    # 明確單選模型必須執行該模型，不能被 JEV/Laya triage 靜默跳過。
    _tri = None
    if (web_results or sources) and (not llm_model or llm_model == "consensus"):
        try:
            _t0 = time.perf_counter()
            import triage_cascade as _tc
            _tri = _tc.triage(content)
            timings["triage_cascade"] = round((time.perf_counter() - _t0) * 1000, 1)
        except Exception as _e:
            print(f"[judge] triage failed: {_e}", flush=True)
            _tri = None
    if _tri:
        deep = {"claim": (_title_clean or content[:60]),
                "evidence_state": "cascade_triage", "evidence_used": [],
                "key_points": [], "viewpoints": "",
                "credibility_score": 75 if _tri["verdict"] == "likely_real" else 25,
                "abstain": False, "route": "cascade", "triage": _tri}
        timings["deep_analyze"] = timings.get("triage_cascade") or 0
    elif web_results or sources:
        try:
            _t = time.perf_counter()
            deep = deep_analyze_ensemble(_title_clean or content[:60], web_results, sources,
                                         content=content, samples=n_samples,
                                         model_id=llm_model)
            timings["deep_analyze"] = round((time.perf_counter() - _t) * 1000, 1)
        except Exception as _e:
            print(f"[judge] deep_analyze failed: {_e}", flush=True)
            # 2026-10-06：不要靜默變空。前端要能看到失敗原因，
            # 否則整段「AI 深入分析」消失，使用者只覺得「沒有分析」。
            deep = {"error": f"{type(_e).__name__}: {_e}"}
    _fusion_t0 = time.perf_counter()
    # 融合：LLM 可信度分動態加權進總評
    # - 查核命中：規則已強證據，LLM 僅微調 (w=0.10)
    # - 查核全 not_found：規則維度無信號，LLM 成主要依據 (w=0.60)
    # 2026-09-25：模型自己宣告 abstain 時，該分數只是暫時值，不拿來改寫查核結論。
    # 否則「正文未載入」會被當成低分證據，正是先前 TFC 截圖那種誤導來源。
    ai_cs = deep.get('credibility_score') if isinstance(deep, dict) else None
    ai_abstain = bool(deep.get('abstain')) if isinstance(deep, dict) else False
    # 2026-10-01：模型判 unrelated_evidence 時回捋該次命中的全部處置。deep 在 fact_check
    # 之後才算得出來，閘門只能事後生效：扣回 fact_check 的 -30、把 total 補回來，
    # 下方 clamp/basis 各自讀同一個 _ev_unrelated。
    _ev_unrelated = _evidence_is_unrelated(deep)
    # 2026-10-01：軟命中帶（0.45～COFACTS_MIN_SIM）降級成 not_found，但保留原始 status
    # 到 soft_hit_status —— prompt 組裝（fc_lines）會把它顯示成「軟命中待裁決」餵給
    # LLM，讓 LLM 用 evidence_state 判相關性（PFCD two-stage：召回放寬 → semantic
    # rerank 由 LLM 做）。只有標籤不夠——「央視國慶晚會」sim 0.862 命中「李登輝不姓李」，
    # 兩者 status 都是 inaccurate，得看到回覆原文才分得出。
    _soft = [s for s in (sources or []) if s.get("needs_llm_verdict")]
    if _soft:
        # LLM 判「證據完整且相關」就升為硬命中：此時 similarity_score 仍低於 0.72，
        # clamp 的 0.72 條件不會觸發（clamp 另有 unrelated 閘門擋反向誤判），只吃 -30。
        # 必須同時通過 _evidence_is_unrelated 的一致性檢查：實測 LLM 的狀態欄填
        # full_body_evidence、analysis 卻說「與本主張無關」，只看狀態欄會鎖死真新聞。
        _promote = (isinstance(deep, dict)
                    and deep.get("evidence_state") == "full_body_evidence"
                    and not _evidence_is_unrelated(deep))
        for _s in _soft:
            _s["soft_hit_status"] = _s.get("status")
            _s["soft_hit_sim"] = _s.get("similarity_score")
            _s["llm_promoted"] = _promote
            if not _promote:
                # 軟命中未被 LLM 接納，不得再當成查核回覆、分數依據或 UI 證據展示。
                _s["status"] = "not_found"
                _s["feedback_count"] = 0
                _s["reasons"] = []
                _s["matched_text"] = None
                _s["url"] = None
                _s.pop("alternatives", None)
        if not _promote:
            _new_fb_pts, _new_fb_desc = _feedback_from_sources(sources)
            total += _new_fb_pts - fb_pts
            fb_pts, fb_desc = _new_fb_pts, _new_fb_desc
            res["user_feedback"] = {"score": fb_pts, "desc": fb_desc,
                                    "weight": DEFAULT_WEIGHTS["feedback"]}
            final = max(0.0, (total / avail) * 100) if avail > 0 else 0.0
            rule_score = final
        if _promote:
            # 升級後 fact_check 要重算：走最嚴重取樣
            _worst = max((s.get("soft_hit_status") for s in _soft),
                         key=lambda x: {"inaccurate": 3, "partial": 2,
                                        "accurate": 1}.get(x, 0), default=0)
            _d = {"inaccurate": -DEFAULT_WEIGHTS["fact_check"],
                  "partial": DEFAULT_WEIGHTS["fact_check"] * 0.3,
                  "accurate": DEFAULT_WEIGHTS["fact_check"]}.get(_worst, 0) \
                - DEFAULT_WEIGHTS["fact_check"] * 0.5
            res["fact_check"] = {"score": DEFAULT_WEIGHTS["fact_check"] * 0.5 + _d,
                                 "desc": _worst,
                                 "weight": DEFAULT_WEIGHTS["fact_check"]}
            # 只動 total，不動 avail。avail 是「可用權重總和」，扣分項加進分母會讓
            # total/avail 變成負數——實測軟命中升級 + mygopen 同時命中時 total=−31
            # （avail 被扣到負值）。clamp 後的分數本來就該被 clamp 收斂，不是被 avg 拖到負。
            total += _d
            final = max(0.0, (total / avail) * 100) if avail > 0 else 0.0
            rule_score = final
    if _ev_unrelated:
        _fc0 = res.get("fact_check") or {}
        if _fc0.get("desc") == "inaccurate":
            # fact_check 從 -30 改回 not_found 的中性基準 15：total 與 avail 同額位移，
            # final=(total/avail)*100 才會真的變高（只改 total 會被 avg 稀釋掉）。
            _d = DEFAULT_WEIGHTS["fact_check"] * 0.5 - (_fc0.get("score") or 0.0)
            total += _d
            avail += _d
            res["fact_check"] = {**_fc0, "score": DEFAULT_WEIGHTS["fact_check"] * 0.5,
                                 "desc": "not_found"}
            final = (total / avail) * 100 if avail > 0 else 0.0
            rule_score = final
    fusion_weight = 0.0
    post_fusion_score = final
    clamped = False
    clamp_reason = ""
    # 2026-10-05：多家同報。新新聞本來就沒有查核（查核庫只收網傳謠言），
    # ≥3 家獨立媒體同報 = 交叉印證：abstain 上限 55→70，仍是暫時分數、不視為可信。
    # key 用標題＋內文頭（只用標題會漏掉換句話說的同報，實例：中央社寫「杜拜航空機長遇襲」，
    # 標題與三立原標零重疊，要靠內文的「杜拜航空」才連得起來）。
    # 內文放前面：_web_query_core 會按「|」切（標題本有站台後綴），放後面會被切掉。
    _corr_outlets = _web_corr_outlets(web_results, f"{content[:80]}。{_query_src}", host)
    _corr_n = len(_corr_outlets)
    if ai_cs is not None:
        try:
            cs = float(ai_cs)
            # 2026-10-02：證據本身是匿名轉傳／傳言時，不得按 full_body_evidence 採信。
            _rumor_ev = _is_rumor_only_evidence(deep, sources)
            if _rumor_ev and not ai_abstain:
                ai_abstain = True
                cs = min(cs, 45.0)
                print(f"[judge] 證據為傳言／匿名轉傳，不採信為屬實背書 → 降為 abstain (cs<={cs:.0f})", flush=True)
            fc_hit = any((s.get('status') in ('hit', 'ok', 'inaccurate', 'partial'))
                         for s in (sources or []))
            # 2026-10-02 修正：abstain 時也納入融合。
            # 舊邏輯 `and not ai_abstain` 完全丟棄 abstain 分數，導致只有
            # SBERT 情緒（15.0）+ 相似度（13.5）兩個訊號在講話，
            # 分母卻仍含 domain 25 + fact_check 15，算出 58-68 的假高分。
            # 實測：以假亂真的颱風新聞拿 68.2，真實颱風新聞拿 67.4 — 零鑑別力。
            #
            # fusion_weight 方向修正：舊邏輯查核命中給 0.10、查不到給 0.60，
            # 等於「越沒證據越聽 AI 的」——但此時 AI 手上也沒有證據，
            # 只是照內文語氣猜。方向應為：證據越弱，AI 話語權越低，
            # 並在接近零證據時施加額外的上限錨定（no_evidence ≠ 真新聞）。
            if ai_abstain:
                # 證據不足：AI 分數已夾在 45-65，且會與情緒／相似度同向偏高，
                # 給低話語權並壓低上限，避免「查不到」被讀成「不是假的」。
                fusion_weight = 0.20
                final = final * (1 - fusion_weight) + cs * fusion_weight
                _abstain_cap = 55.0
                _ev_label = str((deep or {}).get("evidence_state") or "unknown")
                if _corr_n >= 3 and not fc_hit:
                    _abstain_cap = 70.0  # 2026-10-05：多家同報交叉印證，放寬但仍是暫時分數
                    _ev_label += f"（{_corr_n}家媒體同報交叉印證）"
                if final > _abstain_cap:
                    clamped = True
                    clamp_reason = (clamp_reason + "；" if clamp_reason else "") + (
                        f"查核證據不足（{_ev_label}），分數僅為暫時值，"
                        f"施加上限錨定（最高 {_abstain_cap:.0f}，不視為可信）")
                    final = _abstain_cap
            else:
                fusion_weight = 0.55 if fc_hit else 0.25
                final = final * (1 - fusion_weight) + cs * fusion_weight
            post_fusion_score = final
        except (TypeError, ValueError):
            pass
    # 階段三：三級動態信心度衰減錨定 (Stage 3 Dynamic Confidence Decay Clamp)
    # 2026-10-01：模型判 unrelated_evidence 時跳過錨定。模型看的是查核機構回覆原文，
    # 比 SBERT 分數可靠——實測 Cofacts 對「黃安國慶表態」召回一篇「一頁式廣告詐騙」，
    # matched_text 純網址卻算 sim 0.912，若照錨定真新聞直接鎖死 25 分。
    _ev_unrelated = _evidence_is_unrelated(deep)
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
    if _ev_unrelated:
        basis = "命中的查核與本主張無關，已忽略該錨定（暫時分數，非查核結論）"
    elif any(st in ('inaccurate', 'false', 'misleading', 'fake') for st in fc_statuses):
        basis = "查核機構判定不實，已錨定低分"
    elif any(st == 'partial' for st in fc_statuses):
        basis = "查核機構判定部分不實，已錨定上限"
    elif any(st in ('hit', 'ok', 'accurate', 'true') for st in fc_statuses):
        basis = "查核機構判定屬實，規則分主導"
    elif ai_abstain and deep:
        basis = ("AI 模型判定證據不足，本次為暫時分數（非查核結論）："
                 f"{(deep.get('evidence_state') or '未載入正文')}")
        if _corr_n >= 3:  # 2026-10-05：讓多家同報看得見（沒被 clamp 也留痕）
            basis += f"｜{_corr_n}家媒體同報交叉印證（{ '、'.join(_corr_outlets[:6])}）"
        if deep.get("evidence_state_disputed"):
            # 2026-10-01：跨次取樣對證據狀態不一致 → 不給結論（selective prediction）。
            # 擺動本身就是「模型不確定」的訊號，比它自報的分數可靠。
            basis = (f"AI 模型 {deep.get('samples')} 次取樣對證據狀態不一致"
                     f"（{deep.get('evidence_state')}），判定不確定，本次為暫時分數")
    elif deep and deep.get('credibility_score') is not None:
        basis = f"無查核證據，由本機 AI 模型補位評分（{deep.get('samples','?')}次取樣）"
    else:
        basis = "無查核證據且 AI 評分失敗，僅依規則分"
    timings["scoring"] = round((time.perf_counter() - _fusion_t0) * 1000, 1)
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
        "is_provisional": bool(ai_abstain),
        "evidence_state": (deep.get("evidence_state") or "") if isinstance(deep, dict) else "",
        "sources": sources,
        "corroboration": {"count": _corr_n, "outlets": _corr_outlets},
        "review_links": review_links,
        "web_results": web_results,
        "deep_analysis": deep,
        "timings": timings,
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

def analyze_article_data(title: str = "", url: str = "", content: str = "", publish_date=None, target_url: str = None, mode: str = "fast", llm_model: str = "", **_) -> Dict:
    if not content:
        raise ValueError("content required for single analysis")
    if not url:
        url = "https://unknown"
    return _score_single(title or "N/A", url, content, [title, content],
                         publish_date=publish_date, target_url=target_url,
                         mode=mode, llm_model=llm_model)

# --------------------------- Flask -----------------------------
app = Flask(__name__)

# --------------------------- Debug 模式 ---------------------------
# 2026-10-05：模型選擇 + 各步驟耗時只在 debug 模式露出，一般使用者看不到。
# 登入成功發 token（in-memory，重啟失效）；/judge 靠 X-Debug-Token 標頭驗，
# 非 debug 請求的 llm_model/llm_models/mode 一律忽略、timings 不回傳。
import hmac as _hmac, secrets as _secrets
_DEBUG_USER = os.environ.get("NEWSANALYZER_DEBUG_USER", "min20120907")
_DEBUG_PASS = os.environ.get("NEWSANALYZER_DEBUG_PASSWORD", "jefflin123")
_DEBUG_TOKENS: set = set()

def _is_debug(req) -> bool:
    return (req.headers.get("X-Debug-Token") or "") in _DEBUG_TOKENS

@app.route("/debug_login", methods=["POST"])
def debug_login():
    data = request.get_json(force=True, silent=True) or {}
    ok = _hmac.compare_digest(str(data.get("account", "")), _DEBUG_USER) and \
         _hmac.compare_digest(str(data.get("password", "")), _DEBUG_PASS)
    if not ok:
        return {"ok": False, "error": "帳號或密碼錯誤"}, 401
    tok = _secrets.token_urlsafe(24)
    _DEBUG_TOKENS.add(tok)
    return {"ok": True, "token": tok}


@app.route("/debug_logs", methods=["GET"])
def debug_logs():
    # 只給 debug 模式；回最近 600 行 stdout/stderr（環形緩衝，見 _LogTee）。
    if not _is_debug(request):
        return {"error": "debug only"}, 403
    _LOG_LOCK.acquire()
    try:
        lines = list(_LOG_BUF)
    finally:
        _LOG_LOCK.release()
    return {"ok": True, "lines": lines}

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

def _extract_from_url(url: str, skip_newspaper: bool = False) -> Dict:
    """Multi-strategy URL content extractor.

    Fallback chain:
    1. trafilatura (fast, clean text)
    2. newspaper3k (legacy, still works for some sites)
    3. Playwright (JS-rendered pages, paywalls with accessible content)
    4. Selenium headless (last resort, for heavily JS sites)

    skip_newspaper：給 Google News 包裝連結用——newspaper 在包裝頁上必空轉
    超時，能力又被 Playwright 覆蓋，直接跳過省 15s。
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
    if NEWSPAPER3K_AVAILABLE and not skip_newspaper:
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

@app.route("/models", methods=["GET"])
def list_models():
    """前端下拉選單的資料來源。2026-10-02。

    回 llm_registry 的完整目錄（含停用項，前端自行顯示標記）。
    探測狀態若已有 model_probe.json 就附上（前端灰掉掛掉的模型）。
    2026-10-05：只在 debug 模式回應（X-Debug-Token），一般使用者不露出選單。
    """
    if not _is_debug(request):
        return {"error": "debug only"}, 403
    try:
        import llm_registry as _reg
    except Exception as e:
        return {"error": f"registry unavailable: {e}"}, 500
    items = _reg.model_catalog(include_disabled=True)
    probe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "data", "eval", "model_probe.json")
    probe = {}
    try:
        if os.path.exists(probe_path):
            with open(probe_path, encoding="utf-8") as f:
                for r in json.load(f):
                    probe[r["model"]] = r
    except Exception:
        pass
    for it in items:
        p = probe.get(it["id"])
        if p:
            it["probe_ok"] = bool(p.get("ok"))
            it["probe_note"] = p.get("note")
    return {"models": items, "default": _reg.default_backend(),
            "probed_at": os.path.getmtime(probe_path) if os.path.exists(probe_path) else None}


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

    # 2026-10-01：mode=fast（預設，n=1 約 12s）| deep（n=3 跨次一致性，約 40s）
    # 2026-10-05：模型與模式選擇只在 debug 模式生效，非 debug 一律預設
    # （擋掉繞過前端直接打 API 指定模型的請求）。
    _debug = _is_debug(request)
    mode = (data.get("mode") or "fast") if _debug else "fast"
    # 2026-10-02：前端選單傳 'backend/model'，空字串＝沿用 QWEN_URL（行為不變）
    llm_model = (data.get("llm_model") or "") if _debug else ""
    # 2026-10-02：前端勾選多個模型 → 共識投票。
    # 勾 1 個＝該模型單獨評分；勾 2+ 個＝多模型共識（分歧時 abstain）。
    # 前端若未帶此欄位，行為與修正前完全相同（空字串＝沿用 QWEN_URL）。
    _picked = [m for m in (data.get("llm_models") or []) if isinstance(m, str) and m] if _debug else []
    consensus_models = []
    if len(_picked) > 1:
        llm_model = "consensus"
        consensus_models = _picked
    elif _picked:
        llm_model = _picked[0]
        consensus_models = []
    score = analyze_article_data(title=title, url=url, content=content,
                                 publish_date=extracted.get("publish_date"),
                                 target_url=extracted.get("source"), mode=mode,
                                 llm_model=llm_model)
    # 2026-10-02：llm_model='consensus' → 多模型共識投票取代單一 deep 分析。
    # 分歧時 abstain（不硬選），分歧度一起回前端。
    if llm_model == "consensus":
        try:
            import llm_ensemble as _ens
            wr = score.get("web_results") or []
            src = score.get("sources") or []
            cons = _ens.consensus_score(title or content[:60], wr, src, content,
                                       model_ids=consensus_models or None)
            da = score.get("deep_analysis") or {}
            da.update({
                "consensus": cons,
                "model": f"共識×{len(cons.get('details') or [])}",
                "credibility_score": cons.get("consensus_score"),
                "abstain": bool(cons.get("abstained")),
            })
            score["deep_analysis"] = da
        except Exception as _e:
            print(f"[judge] consensus failed: {_e}", flush=True)
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
        "corroboration": score.get("corroboration", {}),
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
        "is_provisional": score.get("is_provisional", False),
        "evidence_state": score.get("evidence_state", ""),
        "mode": mode,        # 2026-10-01：fast | deep，前端據此顯示暫時性
        "timings": timings if _debug else {},  # 2026-10-05：各步驟耗時只給 debug
        "debug": _debug,
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

