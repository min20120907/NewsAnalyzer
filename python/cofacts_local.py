# -*- coding: utf-8 -*-
"""
Cofacts (g0v) 本地事實查核客戶端
=================================
* 透過 api.cofacts.tw GraphQL 查詢（免費、無 API key；注意 cofacts-api.g0v.tw
  被 Cloudflare 擋，本模組改用 api.cofacts.tw 並帶瀏覽器 UA）
* 本地 sqlite 快取查詢結果，避免重複打 API 與被限流
* 同時提供三個維度的真實數據給 /judge 使用：
    - fact_check   : 查核結論 (inaccurate / partial / accurate / not_found)
    - user_feedback: 該文社群查核回饋數 (Cofacts article_reply_feedbacks)
    - timeliness   : 命中文章的建立時間 → 新鮮度

傳回結構 (dict)：
    status        : 'inaccurate' | 'partial' | 'accurate' | 'not_found'
    feedback_count: int
    created_at    : float (epoch seconds) 或 None
    article_id    : str 或 None
    matched_text  : str 或 None
"""
import os
import json
import time
import sqlite3
import hashlib
import requests
from datetime import datetime, timezone

COFACTS_API_URL = "https://api.cofacts.tw/graphql"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
# Cofacts moreLikeThis 即使相似度極低也會回傳「最像」的一筆，造成錯連結。
# 主路命中後用本地 SBERT 對「用戶輸入 vs 命中文章」算 cosine 相似度，
# 低於此門檻視為 not_found，避免給出不相干文章的連結。
COFACTS_MIN_SIM = float(os.environ.get("COFACTS_MIN_SIM", "0.55"))

CACHE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "cofacts", "cofacts_cache.db")

_GRAPHQL = """
query FactCheck($filter: ListArticleFilter) {
  ListArticles(filter: $filter) {
    edges {
      node {
        id
        text
        createdAt
        articleReplies(status: NORMAL) {
          feedbackCount
          reply {
            type
            text
          }
        }
      }
    }
  }
}
"""


def _ensure_db():
    os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    con = sqlite3.connect(CACHE_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        status TEXT,
        feedback_count INTEGER,
        created_at REAL,
        article_id TEXT,
        matched_text TEXT,
        ts REAL,
        reasons TEXT
    )""")
    # 舊 cache 表可能無 reasons 欄，惰性補齊
    try:
        con.execute("ALTER TABLE cache ADD COLUMN reasons TEXT")
    except Exception:
        pass
    con.commit()
    con.execute("""CREATE TABLE IF NOT EXISTS corpus (
        key TEXT PRIMARY KEY,
        text TEXT,
        status TEXT,
        feedback_count INTEGER,
        created_at REAL,
        article_id TEXT,
        reasons TEXT
    )""")
    # 舊表可能無 reasons 欄，惰性補齊
    try:
        con.execute("ALTER TABLE corpus ADD COLUMN reasons TEXT")
    except Exception:
        pass
    con.commit()
    return con


def _cache_del(key):
    try:
        con = _ensure_db()
        con.execute("DELETE FROM cache WHERE key=?", (key,))
        con.commit()
        con.close()
    except Exception:
        pass


def _cache_put(key, val):
    try:
        con = _ensure_db()
        con.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?,?,?,?)",
                    (key, val.get("status"), val.get("feedback_count", 0),
                     val.get("created_at"), val.get("article_id"),
                     val.get("matched_text"), time.time(),
                     json.dumps(val.get("reasons", []), ensure_ascii=False)))
        con.commit()
        con.close()
    except Exception:
        pass


def _sbert_sim(text_a: str, text_b: str):
    """用 SBERT 算兩段文字 cosine 相似度（已歸一化 → 內積即 cos）。無模型回 None。"""
    model = _SBERT_MODEL
    if not model:
        model = _get_sbert()
    if not model:
        return None
    import numpy as np
    a, b = model.encode([text_a, text_b], convert_to_numpy=True,
                        normalize_embeddings=True)
    return float(np.dot(a, b))


def _classify(edges):
    """從 GraphQL edges 解析查核結論、回饋數、建立時間、理由與連結。"""
    if not edges:
        return {"status": "not_found", "feedback_count": 0,
                "created_at": None, "article_id": None,
                "matched_text": None, "url": None, "reasons": []}
    # 取第一筆命中（API 已按相似度排序）
    node = edges[0]["node"]
    replies = node.get("articleReplies") or []
    has_false = has_true = has_opinion = False
    total_fb = 0
    reasons = []
    for ar in replies:
        total_fb += int(ar.get("feedbackCount") or 0)
        rtype = (ar.get("reply") or {}).get("type", "").upper()
        rtext = (ar.get("reply") or {}).get("text") or ""
        # 理由：取「非謠言/含真相」類型的回覆文字前 200 字
        if rtype in ("FALSE", "RUMOR", "TRUE", "NOT_RUMOR", "OPINIONATED"):
            if rtext.strip():
                reasons.append({"type": rtype, "text": rtext.strip()[:200]})
        if rtype in ("FALSE", "RUMOR"):
            has_false = True
        elif rtype in ("TRUE", "NOT_RUMOR"):
            has_true = True
        elif rtype == "OPINIONATED":
            has_opinion = True
    if has_false:
        status = "inaccurate"
    elif has_true:
        status = "accurate"
    elif has_opinion:
        status = "partial"
    else:
        status = "not_found"
    created_at = None
    try:
        created_at = datetime.fromisoformat(
            node["createdAt"].replace("Z", "+00:00")).timestamp()
    except Exception:
        created_at = None
    article_id = node.get("id")
    url = f"https://cofacts.tw/article/{article_id}" if article_id else None
    return {"status": status, "feedback_count": total_fb,
            "created_at": created_at, "article_id": article_id,
            "matched_text": (node.get("text") or "")[:120],
            "url": url, "reasons": reasons[:3]}


def _row_to_result(row, with_reasons=False):
    res = {"status": row[0], "feedback_count": row[1],
           "created_at": row[2], "article_id": row[3],
           "matched_text": row[4]}
    # cache 表目前未存 url，回補
    res["url"] = (f"https://cofacts.tw/article/{row[3]}" if row[3] else None)
    reasons = []
    if len(row) > 5 and row[5]:
        try:
            reasons = json.loads(row[5])
        except Exception:
            reasons = []
    res["reasons"] = reasons
    return res


def _cache_get(key):
    try:
        con = _ensure_db()
        row = con.execute("SELECT status,feedback_count,created_at,article_id,"
                          "matched_text,reasons FROM cache WHERE key=?", (key,)).fetchone()
        con.close()
        if row:
            return _row_to_result(row)
    except Exception:
        pass
    return None


def get_fact_check(text: str, use_cache: bool = True,
                   timeout_api: int = 15) -> dict:
    """查詢 Cofacts 事實查核。text 太短直接 not_found。"""
    if not text or not isinstance(text, str) or len(text.strip()) < 20:
        return {"status": "not_found", "feedback_count": 0,
                "created_at": None, "article_id": None,
                "matched_text": None, "url": None, "reasons": []}
    snippet = text[:200]
    key = hashlib.sha1(snippet.encode("utf-8")).hexdigest()
    if use_cache:
        c = _cache_get(key)
        if c:
            return c
    payload = {"query": _GRAPHQL, "variables": {
        "filter": {"moreLikeThis": {"like": snippet}}}}
    try:
        r = requests.post(COFACTS_API_URL, json=payload,
                          headers={"User-Agent": UA,
                                   "Content-Type": "application/json"},
                          timeout=timeout_api + 5)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return {"status": "not_found", "feedback_count": 0,
                "created_at": None, "article_id": None,
                "matched_text": None, "url": None, "reasons": []}
    if "errors" in data or not data.get("data"):
        return {"status": "not_found", "feedback_count": 0,
                "created_at": None, "article_id": None,
                "matched_text": None, "url": None, "reasons": []}
    edges = (data["data"].get("ListArticles") or {}).get("edges") or []
    result = _classify(edges)
    # 閘門：Cofacts moreLikeThis 無相似度門檻會回傳不相關文章。
    # 主路命中後再用 SBERT 驗證「用戶輸入 vs 命中文章」相似度，過低則視為 not_found。
    if result["status"] != "not_found" and result.get("matched_text"):
        sim = _sbert_sim(snippet, result["matched_text"])
        if sim is not None and sim < COFACTS_MIN_SIM:
            result = {"status": "not_found", "feedback_count": 0,
                      "created_at": None, "article_id": None,
                      "matched_text": None, "url": None, "reasons": []}
    if use_cache:
        _cache_put(key, result)
    # Cofacts moreLikeThis 檢索閾值較嚴 → 未命中時退化到本地 SBERT 近鄰
    if result["status"] == "not_found":
        lm = local_match(snippet, threshold=0.55)
        if lm:
            aid = lm.get("article_id")
            result = {"status": lm["status"], "feedback_count": lm["feedback_count"],
                      "created_at": lm["created_at"], "article_id": aid,
                      "matched_text": lm["matched_text"],
                      "url": (f"https://cofacts.tw/article/{aid}" if aid else None),
                      "reasons": lm.get("reasons", [])}
    return result


def get_fact_check_structured(text: str, use_cache: bool = True,
                              timeout_api: int = 15) -> dict:
    """與 get_fact_check 相同，但包成多源統一格式：
    {source: 'cofacts', status, feedback_count, created_at,
     article_id, matched_text, url, reasons}。"""
    r = get_fact_check(text, use_cache=use_cache, timeout_api=timeout_api)
    r["source"] = "cofacts"
    return r


def seed_from_cofacts(limit: int = 200, cursor: str = None):
    """從 Cofacts 大量拉取「已有查核回覆」的文章，作為台灣假新聞標記集 + 本地快取種子。
    回傳 [(text, truth_label), ...]，truth_label ∈ {'inaccurate','partial','accurate'}。
    """
    Q = """
    query Seed($first: Int, $after: String) {
      ListArticles(filter: {replyCount: {GT: 0}}, first: $first, after: $after) {
        pageInfo { lastCursor }
        edges {
          cursor
          node {
            id
            text
            articleReplies(status: NORMAL) {
              feedbackCount
              reply { type }
            }
          }
        }
      }
    }
    """
    out = []
    after = cursor
    fetched = 0
    while fetched < limit:
        batch = min(50, limit - fetched)
        payload = {"query": Q, "variables": {"first": batch, "after": after}}
        try:
            r = requests.post(COFACTS_API_URL, json=payload,
                              headers={"User-Agent": UA,
                                       "Content-Type": "application/json"},
                              timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception:
            break
        if "errors" in data or not data.get("data"):
            break
        conn = data["data"]["ListArticles"]
        edges = conn.get("edges") or []
        if not edges:
            break
        for e in edges:
            node = e["node"]
            txt = (node.get("text") or "").strip()
            if len(txt) < 20:
                continue
            res = _classify([e])
            if res["status"] in ("inaccurate", "partial", "accurate"):
                out.append((txt, res["status"]))
                key = hashlib.sha1(txt[:200].encode("utf-8")).hexdigest()
                _cache_put(key, res)
                _corpus_put(key, txt, res)
        fetched += len(edges)
        # 用最後一筆 edge 的 cursor 翻頁（pageInfo.lastCursor 在本 schema 不可靠）
        after = edges[-1].get("cursor")
        if not after or len(edges) < batch:
            break
    return out


def _corpus_put(key, text, res):
    try:
        con = _ensure_db()
        con.execute("INSERT OR REPLACE INTO corpus VALUES (?,?,?,?,?,?,?)",
                    (key, text, res.get("status"), res.get("feedback_count", 0),
                     res.get("created_at"), res.get("article_id"),
                     json.dumps(res.get("reasons", []), ensure_ascii=False)))
        con.commit()
        con.close()
    except Exception:
        pass


def _corpus_all():
    """回傳本地語料庫 [(key, text, status, feedback_count, created_at, article_id, reasons_json)]"""
    try:
        con = _ensure_db()
        rows = con.execute(
            "SELECT key,text,status,feedback_count,created_at,article_id,reasons "
            "FROM corpus").fetchall()
        con.close()
        return rows
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 本地 SBERT 近鄰檢索（覆蓋 Cofacts moreLikeThis 檢索閾值造成的 not_found）
# 預設複用 fake_news_server_new 已載入的 SIMILARITY_MODEL；若無則惰性 CPU 載入。
# ---------------------------------------------------------------------------
_SBERT_MODEL = None
_SBERT_PATH = ("/home/min20120907/.cache/huggingface/hub/"
               "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/"
               "snapshots/e8f8c211226b894fcb81acc59f3b34ba3efd5f42")
INDEX_CACHE = os.path.join(os.path.dirname(CACHE_DB), "sbert_index.npz")
_LOCAL_EMB = None  # (keys, matrix np.ndarray)


def set_sbert_model(model):
    """由服務端注入已載入的 SentenceTransformer，避免重複佔用 GPU/記憶體。"""
    global _SBERT_MODEL
    _SBERT_MODEL = model


def _get_sbert():
    global _SBERT_MODEL
    if _SBERT_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            _SBERT_MODEL = SentenceTransformer(_SBERT_PATH, device="cpu")
        except Exception:
            _SBERT_MODEL = False
    return _SBERT_MODEL or None


def build_local_index(force=False):
    """建立/重建本地語料 SBERT 向量索引。

    索引 (keys + embeddings) 會快取到 INDEX_CACHE（.npz），
    只要 corpus 內容（text + status）沒變就直接載快取，省去 CPU 重編 2066 筆的 13 分鐘。
    命中快取時不會去載入 SentenceTransformer（避免 108s 冷啟動），只有真要編碼才載模型。
    """
    global _LOCAL_EMB
    if _LOCAL_EMB is not None and not force:
        return _LOCAL_EMB
    import numpy as np, hashlib, os
    rows = _corpus_all()
    if not rows:
        return None
    keys = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    # 用 (text+status) 的雜湊決定快取有效性
    h = hashlib.sha1(("||".join("%s:%s" % (k, r[2]) for k, r in zip(keys, rows))[:5000]).encode("utf-8")).hexdigest()
    if not force and os.path.exists(INDEX_CACHE):
        try:
            d = np.load(INDEX_CACHE, allow_pickle=True)
            if d["hash"] == h:
                _LOCAL_EMB = (list(d["keys"]), d["emb"])
                return _LOCAL_EMB
        except Exception:
            pass
    # 只有快取失效、確實要編碼時才載模型
    model = _get_sbert()
    if model is None:
        return None
    emb = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    _LOCAL_EMB = (keys, emb)
    try:
        np.savez(INDEX_CACHE, keys=np.array(keys, dtype=object),
                 emb=emb, hash=h)
    except Exception:
        pass
    return _LOCAL_EMB


def local_match(query, threshold=0.55):
    """本地近鄰檢索。回傳 dict 或 None。

    優先用服務注入的模型（_SBERT_MODEL），否則惰性 CPU 自載（standalone 評測用，
    僅首次付 ~108s 冷啟動，同進程內後續呼叫皆快）。
    """
    idx = build_local_index()
    if idx is None:
        return None
    model = _SBERT_MODEL
    if not model:
        model = _get_sbert()
    if not model:
        return None
    import numpy as np
    q = model.encode([query], convert_to_numpy=True,
                     normalize_embeddings=True)[0]
    keys, emb = idx
    sims = emb @ q
    best = int(np.argmax(sims))
    sim = float(sims[best])
    if sim < threshold:
        return None
    con = _ensure_db()
    row = con.execute(
        "SELECT status,feedback_count,created_at,article_id,text,reasons FROM corpus "
        "WHERE key=?", (keys[best],)).fetchone()
    con.close()
    if not row:
        return None
    reasons = []
    try:
        reasons = json.loads(row[5]) if row[5] else []
    except Exception:
        reasons = []
    return {"status": row[0], "feedback_count": row[1],
            "created_at": row[2], "article_id": row[3],
            "matched_text": (row[4] or "")[:120], "sim": sim,
            "reasons": reasons}


if __name__ == "__main__":
    tests = [
        "網傳喝漂白水可以治百病，這是真的嗎？",
        "地震後千萬不要先開燈、不要開瓦斯，這是真的嗎？",
        "台積電今日股價上漲創新高，法人看好後市。",
    ]
    for t in tests:
        print(t, "→", get_fact_check(t))
