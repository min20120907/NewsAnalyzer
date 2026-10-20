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
import concurrent.futures as _cf
from typing import List, Dict, Union, Optional
from datetime import datetime, timedelta
from urllib.parse import urlparse, unquote_plus, quote_plus
from itertools import zip_longest

# 把本檔案所在目錄加入 sys.path，確保 factcheck_multi / cofacts_local 可 import
import sys as _sys
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in _sys.path:
    _sys.path.insert(0, _SCRIPT_DIR)

try:
    from orthogonal_scorer import (
        score_orthogonal,
        compute_d1_evidence_verdict,
        compute_d2_source_corroboration,
        compute_d3_headline_faithfulness,
        compute_d4_rhetorical_risk,
        is_evidence_unrelated as _orth_is_evidence_unrelated,
    )
except ImportError:
    import importlib.util as _ilu
    _orth_spec = _ilu.spec_from_file_location(
        "orthogonal_scorer",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "orthogonal_scorer.py")
    )
    if _orth_spec and _orth_spec.loader:
        _orth_mod = _ilu.module_from_spec(_orth_spec)
        _orth_spec.loader.exec_module(_orth_mod)
        score_orthogonal = _orth_mod.score_orthogonal
        compute_d1_evidence_verdict = _orth_mod.compute_d1_evidence_verdict
        compute_d2_source_corroboration = _orth_mod.compute_d2_source_corroboration
        compute_d3_headline_faithfulness = _orth_mod.compute_d3_headline_faithfulness
        compute_d4_rhetorical_risk = _orth_mod.compute_d4_rhetorical_risk
        _orth_is_evidence_unrelated = _orth_mod.is_evidence_unrelated


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
    FLASK_AVAILABLE = False
    class _DummyFlask:
        def route(self, *_a, **_k):
            return lambda fn: fn
        def run(self, *_a, **_k):
            raise RuntimeError("Flask not installed")
    Flask = lambda *_a, **_k: _DummyFlask()
    request = None
    make_response = lambda x, *a: (x, *a)

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
    Article = object
    ArticleException = Exception
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
        # 排除社群轉貼（UGC）、內容農場，不可當作獨立新聞媒體同報佐證
        if h in UGC_DOMAINS or any(u in h for u in ("facebook", "fb.com", "instagram", "threads.net", "youtube", "tiktok", "ptt.cc", "dcard")):
            continue
        if h in ("news.google.com", "google.com"):
            suf = (r.get("title") or "").split(" - ")[-1].strip().lower()
            outlet = suf if suf else h
        else:
            outlet = h
        if not outlet or outlet in seen:
            continue
        # 排除社群轉貼（UGC），不能當獨立新聞媒體同報佐證
        if any(u in outlet for u in ("facebook", "fb", "threads", "ptt", "dcard", "instagram", "youtube", "tiktok", "twitter", "x.com")):
            continue
        self_clean = (self_host or "").lower().replace("www.", "")
        self_root = self_clean.split(".")[0] if "." in self_clean else self_clean
        if outlet == self_clean or (len(self_root) >= 3 and self_root in outlet):
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
    _valid = [q for q in (queries or []) if q and len(q) >= 4]
    if _valid:
        with _cf.ThreadPoolExecutor(max_workers=len(_valid)) as _ex:
            _futs = [_ex.submit(_wsc.search, q, min(max_results, 3)) for q in _valid]
            for _f in _futs:
                try:
                    res = _f.result() or []
                except Exception as _e:
                    print(f"[judge] web search failed: {_e}")
                    res = []
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
    # 包裝連結永遠解析不出正文，直連優先，別把 top_n 名額浪費在 wrapper 上
    from urllib.parse import urlparse as _up
    def _is_wrapper(_r):
        try:
            return _up(_r.get("url") or "").netloc.lower().endswith(
                ("news.google.com", "google.com"))
        except Exception:
            return True
    cands = [r for r in results
             if r.get("url") and r.get("body") is None
             and r.get("source") != "google_news"
             and len((r.get("snippet") or "").strip()) < min_chars]
    cands.sort(key=lambda r: (1 if _is_wrapper(r) else 0))
    cands = cands[:top_n]
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

_DEEP_PROMPT_TMPL = """你是一個證據接地的事實查核評分員。你只能使用下方實際提供的材料判斷，不得腦補事實。

只輸出一個 JSON 物件，所有文字一律使用繁體中文，精簡扼要：
{{"claim":"本次主張濃縮(25字內)","neutral_title":"還原之客觀真實標題(20字內，去除釣魚懸念)","evidence_state":"full_body_evidence | search_hit_body_missing | no_evidence | unrelated_evidence","evidence_used":["引用的來源名稱"],"key_points":["2條重點(每條30字內，須指明依據)"],"viewpoints":"正反立場或客觀事實(50字內)","credibility_score":0到100整數,"analysis":"結論(60字內，必須點名來源、關鍵事實與明確理由)","abstain":true或false,"title_bait":true或false,"title_bait_reason":"一句話(title_bait為true時必填)"}}

【規則】
1. 今天：{today}。
2. 證據狀態 (evidence_state)：
   - full_body_evidence: 查核原文已載入，且與本主張同事件、同對象、同時間。
   - search_hit_body_missing: 搜尋/查核看似相關，但正文未載入。
   - no_evidence: 無查核來源命中。
   - unrelated_evidence: 命中的查核非本事件（如防詐宣導、不相干截圖、同產業但不同事件）。
3. 判定與分數：
   - 非 full_body_evidence：abstain=true。依內文自評 45~65（煽動/矛盾/無來源之公共公告走 45~50；平實具名走 55~65；查無不得逕給極端低分）。
   - full_body_evidence：abstain=false。明確屬實 85~95、大致屬實 70~84、部分不實或衝突 40~69、明確不實 10~35。
4. 標題檢查 (title_bait)：只要符合任一即判 true 並填寫 reason（平實客觀才判 false）：
   (a) 點擊誘餌/刻意遮蔽關鍵結果（如「醫揭真相」「原因曝光」「真實身分」「做了這件事」等懸念遮蔽）
   (b) 聳動驚嘆或誇張衝突（如「起火變50人吵架」「全場鼻酸」「大顆洋蔥」「崩潰」等情緒操弄）
   (c) 斷章取義或標題斷言超出內文範圍

新聞標題：{title}
新聞內文：
{body}

事實查核結果（含查核回覆原文）：
{fc_block}

網路搜尋結果摘要：
{web_summary}"""


def _deep_analyze_build_prompt(title: str, web_results: list, sources: list,
                              content: str = "", facts: "Optional[list]" = None) -> str:
    lines = []
    for i, r in enumerate(web_results[:4], 1):
        t = (r.get("title") or "").strip()
        body_text = (r.get("body") or "").strip()
        snippet = (r.get("snippet") or "").strip()
        s = body_text or snippet
        status = "正文" if body_text else ("摘要" if snippet else "標題")
        if len(s) > 160:
            s = s[:160] + "…"
        if not (t or s):
            continue
        lines.append(f"{i}. [{status}] {t}\n   {s}" if s else f"{i}. [{status}] {t}")
    web_summary = "\n".join(lines) or "（無網路搜尋結果）"

    fc_lines = []
    label_map = {"cofacts": "Cofacts", "google": "Google查核", "mygopen": "MyGoPen",
                 "rumtoast": "蘭姆酒吐司", "hkbu": "HKBU查核",
                 "infact": "InFact", "jfc": "日本FCセンター",
                 "politifact": "PolitiFact"}
    for s in sources:
        st = s.get("status", "not_found")
        nm = label_map.get(s.get("source", ""), s.get("source", ""))
        url = s.get("url") or ""
        reasons = s.get("reasons") or []
        reply = ""
        for item in reasons[:2]:
            txt = (item.get("text") or "").strip()
            if txt:
                reply += f"　[{item.get('type', '回覆')}] {txt[:200]}\n"
        head = f"  - {nm}: {st}"
        if url:
            head += f"（{url}）"
        if s.get("soft_hit_status"):
            head += f"［軟命中 sim={float(s.get('soft_hit_sim') or 0):.2f}，標籤 {s.get('soft_hit_status')}］"
        fc_lines.append(head)
        if s.get("alternatives"):
            for alt in s["alternatives"][:2]:
                fc_lines.append(f"    · 候選 {alt.get('status')} sim={alt.get('similarity_score')}（{alt.get('url') or ''}）")
                for item in (alt.get("reasons") or [])[:1]:
                    txt = (item.get("text") or "").strip()
                    if txt:
                        fc_lines.append(f"      [{item.get('type', '回覆')}] {txt[:160]}")
        if reply:
            fc_lines.append("    回覆原文：\n" + reply.rstrip())
    fc_summary = "\n".join(fc_lines) or "（無查核源）"
    body = (content or "").strip() or "（未提供內文）"
    if len(body) > 1000:
        body = body[:1000] + "…"
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
                        "務必使用繁體中文撰寫所有欄位值。各欄位結論與重點務必精簡扼要（60字內），直接輸出 JSON，不要推理過程、不要英文。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        # 2026-10-14(A2)：固定 seed＋收緊 top_p/top_k。/slots 實測沿用 server
        # seed=4294967295（隨機），同一輸入跑出 23.83/60.92/81.37 的 58 分擺動。
        # ponytail: llama.cpp prompt cache 本身不保證 bit-for-bit，固定 seed
        # 只能縮小變異、不能保證分數完全一致，日後要更穩就加多次取樣聚合。
        "seed": 0,
        "top_p": 0.9,
        "top_k": 20,
        # 600 token 足以容納結構化 JSON 輸出（約 300 繁中字元），避免長輸出拖垮延遲
        "max_tokens": 600,
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
            # 2026-10-16：標題黨語義判定透傳（斷章取義是語義問題，關鍵詞攔不住）。
            # 新欄位預設 false，舊模型沒輸出也不影響。
            "title_bait": bool(parsed.get("title_bait")) if isinstance(parsed.get("title_bait"), bool) else False,
            "title_bait_reason": str(parsed.get("title_bait_reason") or "")[:200],
            "neutral_title": str(parsed.get("neutral_title") or parsed.get("claim") or "")[:120],
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
        # 2026-10-16：多樣本任一判 bait 就採信（recall 導向）；理由取 best 的。
        "title_bait": any(bool(r.get("title_bait")) for r in valid),
        "title_bait_reason": str(best.get("title_bait_reason") or "")[:200],
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


CLICKBAIT_KEYWORDS = [
    "震撼", "網全嚇傻", "竟然", "不看會後悔", "會後悔", "急了", "震撼彈", "太誇張",
    "傻眼", "敗類", "割韭菜",
    # 2026-10-16：釣魚標題拿高分，擴表。只收釣魚味濃的（寧小漏不大誤傷，
    # 「崩潰」「打臉」「真相」等正常新聞也常用，不收）。
    "驚傳", "瘋傳", "洗版", "嚇呆", "驚呆", "全網", "嚇傻", "傻了", "震驚",
    "踢爆", "細思極恐", "不轉不是", "沉默了", "嚇壞", "慘了", "出事了",
    "出大事", "天塌了",
]


def _is_clickbait(title: str, content: str) -> bool:
    """釣魚標題啟發式：標題＋內文前300字掃關鍵詞。"""
    # ponytail: 子字串掃描，中文無詞邊界；誤傷靠「只收濃詞」控制，要精確就接分類器。
    return any(kw in ((title or "") + (content or "")[:300]) for kw in CLICKBAIT_KEYWORDS)


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
    """Return full orthogonal 4-dimension + 3-regime verdict dict for one article.

    架構升級（四維度正交評分＋三態路由）：
      - D1 `evidence_verdict`      : 查核證據蘊涵度（直接整合回覆數信心與無關證據剔除，不再做 total/avail 事後回補）
      - D2 `source_corroboration`  : 跨源報導佐證度（網域信譽＋獨立媒體同報數＋文章自身 publish_date，絕不混用 Cofacts created_at）
      - D3 `headline_faithfulness` : 標題內文忠實度（純扣分/警示因子，修正 [title, content] 自相似灌水，文題相符不額外加分）
      - D4 `rhetorical_risk`       : 內文修辭與可驗性風險（僅在無查核且無同報的 Regime C 內決定 [10, 58] 落點）
    """
    timings: Dict[str, float] = {}

    eval_url = target_url or url
    parsed = urlparse(eval_url)
    host = parsed.netloc.lower().replace("www.", "")
    if host in ("news.google.com", "google.com", "bit.ly", "t.co", "tinyurl.com") and target_url:
        parsed = urlparse(target_url)
        host = parsed.netloc.lower().replace("www.", "")

    # 1) Sentiment 原始特徵抽取（供 D4 修辭風險使用）
    _t = time.perf_counter()
    s_val = _sentiment_batch([content])[0]
    timings["sentiment"] = round((time.perf_counter() - _t) * 1000, 1)

    # 查詢詞組裝（供多源查核與 web_search 共用）
    _title_clean = (title or "").strip()
    _query_src = content[:80].strip() if _title_clean in ("", "N/A") else _title_clean
    _web_queries = _build_web_queries(title, content) or [_query_src]
    web_review_query = quote_plus(_query_src)
    review_links = {
        "threads": f"https://www.threads.net/search?q={web_review_query}",
        "duckduckgo": f"https://duckduckgo.com/?q={web_review_query}+評論+討論",
    }

    # 修正舊版 refs=[title, content] 自相似 50% 保底 Bug：只比對 title vs content
    title_refs = [_title_clean] if _title_clean not in ("", "N/A") else []

    # 2) 多源事實查核 + 標題內文語義相似度 + web_search 並行執行
    def _timed(_fn, *_a, **_k):
        _s = time.perf_counter()
        return (_fn(*_a, **_k), round((time.perf_counter() - _s) * 1000, 1))

    import concurrent.futures as _cf
    sources: List[Dict] = []
    title_body_sim: Optional[float] = None
    web_results: List[Dict] = []

    with _cf.ThreadPoolExecutor(max_workers=3) as _ex:
        _fc_text = (f"{title}。{content}" if title else content)
        _fu_fc = _ex.submit(_timed, get_all_fact_checks, _fc_text, timeout_api=15) if MULTI_FC_AVAILABLE else None
        _fu_sim = _ex.submit(_timed, _similarity_batch, [content], title_refs) if title_refs else None
        _fu_web = _ex.submit(
            _timed, _web_search_multi, _web_queries, 6,
            _title_clean if _title_clean != "N/A" else ""
        ) if (WEB_SEARCH_AVAILABLE and _wsc is not None) else None

        if _fu_fc is not None:
            sources, timings["fact_check"] = _fu_fc.result()
        if _fu_sim is not None:
            _sim_list, timings["similarity"] = _fu_sim.result()
            title_body_sim = _sim_list[0] if _sim_list else None
        else:
            timings["similarity"] = 0.0
        if _fu_web is not None:
            try:
                web_results, timings["web_search"] = _fu_web.result()
                _t0 = time.perf_counter()
                web_results = _web_search_fallback(_query_src, web_results)
                timings["web_search"] += round((time.perf_counter() - _t0) * 1000, 1)
            except Exception as _e:
                print(f"[judge] web_search failed: {_e}")

    # 預標記軟命中（0.55 <= sim < 0.72），讓 _deep_analyze_build_prompt 能顯示軟命中提示給 LLM 審核
    for _s in (sources or []):
        if _s.get("needs_llm_verdict"):
            _s["soft_hit_status"] = _s.get("status")
            _s["soft_hit_sim"] = _s.get("similarity_score")

    # 3) 本機 LLM 深入分析（證據接地與觀點抽取）
    mode = (mode or "fast").lower()
    if mode not in ("fast", "deep"):
        mode = "fast"
    n_samples = _samples_for(mode)
    deep: Dict = {}
    if web_results or sources:
        try:
            _t = time.perf_counter()
            deep = deep_analyze_ensemble(
                _title_clean or content[:60], web_results, sources,
                content=content, samples=n_samples, model_id=llm_model
            )
            timings["deep_analyze"] = round((time.perf_counter() - _t) * 1000, 1)
        except Exception as _e:
            print(f"[judge] deep_analyze failed: {_e}", flush=True)
            deep = {"error": f"{type(_e).__name__}: {_e}"}

    # 4) 四維度正交評分與三態決策路由
    _fusion_t0 = time.perf_counter()
    _corr_outlets = _web_corr_outlets(web_results, f"{content[:80]}。{_query_src}", host)
    orth = score_orthogonal(
        title=title,
        url=url,
        content=content,
        target_url=target_url,
        publish_date=publish_date,
        sentiment_val=s_val,
        title_body_sim=title_body_sim,
        sources=sources,
        web_results=web_results,
        corr_outlets=_corr_outlets,
        deep=deep,
        whitelist_domains=TAIWAN_MAINSTREAM_DOMAINS or None,
        factcheck_domains=FACT_CHECK_DOMAINS or None,
        ugc_domains=UGC_DOMAINS or None,
        blocklist_domains=DYNAMIC_BLOCKLIST_DOMAINS or None,
    )

    # 若 D1 判定為 unrelated 或軟命中未獲採納，清理 sources 的展示狀態以免誤導前端使用者
    d1_status = orth["dimensions"]["evidence_verdict"]["status_label"]
    for _s in (sources or []):
        if d1_status in ("unrelated", "none", "rumor_only_rejected") and _s.get("needs_llm_verdict"):
            _s["llm_promoted"] = False
            _s["status"] = "not_found"
            _s["feedback_count"] = 0
            _s["reasons"] = []
            _s["matched_text"] = None
            _s["url"] = None
            _s.pop("alternatives", None)
        elif _s.get("needs_llm_verdict"):
            _s["llm_promoted"] = True

    timings["scoring"] = round((time.perf_counter() - _fusion_t0) * 1000, 1)
    compat_mets = orth["metrics"]

    return {
        **compat_mets,
        "metrics": compat_mets,
        "dimensions": orth["dimensions"],
        "regime": orth["regime"],
        "regime_desc": orth["regime_desc"],
        "total_raw_score": orth["final_score"],
        "available_weight": 100.0,
        "final_score": orth["final_score"],
        "rule_score": orth["rule_score"],
        "fusion_weight": orth["fusion_weight"],
        "post_fusion_score": orth["post_fusion_score"],
        "clamped": orth["clamped"],
        "clamp_reason": orth["clamp_reason"],
        "rating_text": orth["rating_text"],
        "scoring_basis": orth["scoring_basis"],
        "is_provisional": orth["is_provisional"],
        "evidence_state": (deep.get("evidence_state") or "") if isinstance(deep, dict) else "",
        "sources": sources,
        "corroboration": {"count": len(_corr_outlets), "outlets": _corr_outlets},
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
    return _score_single(title or "N/A", url, content, [title] if title else [],
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
                # 標籤雲樣板頁（如 MyGoPen 的 Blogger 樣板）：預設模式會把整片
                # 「中文詞,數字,」標籤雲當成正文（實測 1033 組），改用 precision
                # 重新抽取（實測 1033→3 組、正文 1197 字元、標題內文相似度 0.33→0.83）。
                if text and len(re.findall(r"[^,\s]{1,12},\d{1,4}", text)) > 100:
                    _text_prec = trafilatura.extract(
                        downloaded, include_comments=False, include_tables=True, favor_precision=True
                    )
                    if _text_prec and len(_text_prec.strip()) >= 30:
                        text = _text_prec
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

    # --- Strategy 6: archive.today 付費牆 fallback (2026-10-14 C2) ---
    # 只在前面全失敗時跑：archive.ph/newest/{url} 實測 NYT 回 200 全文。
    # ponytail: 14.6s 比抽取慢，只當最後手段；公開服務只取標題摘要、不重製全文（ToS）。
    try:
        import urllib.request as _urlreq
        _areq = _urlreq.Request(
            "https://archive.ph/newest/" + url,
            headers={"User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) "
                                     "AppleWebKit/537.36 Chrome/126 Safari/537.36")})
        with _urlreq.urlopen(_areq, timeout=30) as _arp:
            _ahtml = _arp.read().decode("utf-8", "ignore")
        if _ahtml and len(_ahtml) > 5000 and TRAFILATURA_AVAILABLE:
            _atext = trafilatura.extract(_ahtml, include_comments=False,
                                         include_tables=True)
            if _atext and len(_atext.strip()) >= 100:
                _atitle = ""
                try:
                    from trafilatura.metadata import extract_metadata as _xmeta
                    _am = _xmeta(_ahtml)
                    if _am:
                        _atitle = _am.title or ""
                except Exception:
                    pass
                print(f"[Archive.today] 成功還原內文 ({len(_atext.strip())} 字元)")
                return {"title": _atitle, "content": _atext[:4000],
                        "source": url, "publish_date": None}
    except Exception as _ae:
        print(f"[Archive.today] fallback failed: {_ae}")

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
        "regime": score.get("regime", ""),
        "regime_desc": score.get("regime_desc", ""),
        "dimensions": score.get("dimensions", {}),
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

