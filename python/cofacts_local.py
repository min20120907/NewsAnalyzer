# -*- coding: utf-8 -*-
"""
Cofacts (g0v) 本地事實查核客戶端 - 三階段混合檢索與雙重比對引擎
===================================================
* 階段一：多源召回 (Cofacts GraphQL API + 本地 SBERT 向量庫 Top-K 候選名單)
* 階段二：二重比對 (實體過濾門控 Entity Gatekeeper + SBERT 交叉相似度計算)
* 階段三：信心度分級 (高相似度強硬鎖定 / 中相似度軟減分衰減 / 低相似度剔除)

傳回結構 (dict)：
    status          : 'inaccurate' | 'partial' | 'accurate' | 'not_found'
    feedback_count  : int
    created_at      : float (epoch seconds) 或 None
    article_id      : str 或 None
    matched_text    : str 或 None
    similarity_score: float (0.0 ~ 1.0)
    reasons         : list[dict]
"""
import os
import re
import json
import time
import sqlite3
import hashlib
import requests
from datetime import datetime, timezone

COFACTS_API_URL = "https://api.cofacts.tw/graphql"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
COFACTS_MIN_SIM = float(os.environ.get("COFACTS_MIN_SIM", "0.72"))

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

SURNAMES = set('陳林黃張李王吳劉蔡楊許鄭謝郭洪曾邱廖賴周葉趙孫蘇莊魏薛范沈柯高郭宋徐馬鍾盧顏彭官何羅蕭潘朱簡江游韓傅段苗王')


def extract_entities(text: str) -> set:
    """從文本中提取關鍵人名與專有名詞（實體過濾用）。"""
    if not text:
        return set()
    entities = set()
    # 1. 姓氏 + 1~2 字人名樣式 (例如：范振宗、鄭麗文、沈伯洋)
    for i in range(len(text) - 1):
        if text[i] in SURNAMES:
            for length in (2, 3):
                if i + length <= len(text):
                    sub = text[i:i + length]
                    if re.match(r'^[\u4e00-\u9fa5]+$', sub):
                        entities.add(sub)
    # 2. 政治/社會熱門專有名詞
    key_terms = ['青鳥', '館長', '台積電', '高虹安', '柯建銘', '莊競程', '徐欣瑩']
    for term in key_terms:
        if term in text:
            entities.add(term)
    return entities


def entity_gatekeeper(query_text: str, candidate_text: str) -> bool:
    """實體門控 (Entity Gatekeeper)：
    如果查詢文本包含明確特定人名/實體，但候選文章完全未包含任何對應實體，
    且包含其他衝突人名，則判定門控不通過 (False)。
    """
    q_ents = extract_entities(query_text[:300])
    # 過濾出長度 >= 3 的人名/專名（精度較高）
    strong_q_ents = {e for e in q_ents if len(e) >= 3 or e in ['館長', '青鳥']}
    if not strong_q_ents:
        return True  # 查詢無明確強實體，放行給 SBERT 判定
    
    c_ents = extract_entities(candidate_text[:400])
    overlap = strong_q_ents.intersection(c_ents)
    if overlap:
        return True  # 有實體交集，通過
    
    # 若候選文案完全無交集，但候選文案本身有其他強實體 -> 視為主題衝突誤匹配
    strong_c_ents = {e for e in c_ents if len(e) >= 3 or e in ['館長', '青鳥']}
    if strong_c_ents and not overlap:
        return False
    
    return True


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
    try:
        con.execute("ALTER TABLE corpus ADD COLUMN reasons TEXT")
    except Exception:
        pass
    con.commit()
    return con


def _cache_get(key):
    try:
        con = _ensure_db()
        row = con.execute("SELECT status,feedback_count,created_at,article_id,"
                          "matched_text,reasons FROM cache WHERE key=?", (key,)).fetchone()
        con.close()
        if row:
            res = {"status": row[0], "feedback_count": row[1],
                   "created_at": row[2], "article_id": row[3],
                   "matched_text": row[4]}
            res["url"] = (f"https://cofacts.tw/article/{row[3]}" if row[3] else None)
            reasons = []
            if len(row) > 5 and row[5]:
                try:
                    reasons = json.loads(row[5])
                except Exception:
                    reasons = []
            res["reasons"] = reasons
            return res
    except Exception:
        pass
    return None


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
    """用 SBERT 算兩段文字 cosine 相似度。無模型時惰性載入。"""
    model = _SBERT_MODEL
    if not model:
        model = _get_sbert()
    if not model:
        return None
    import numpy as np
    a, b = model.encode([text_a, text_b], convert_to_numpy=True,
                        normalize_embeddings=True)
    return float(np.dot(a, b))


def _classify_candidate(node) -> dict:
    """從 GraphQL node 解析查核結構。"""
    replies = node.get("articleReplies") or []
    has_false = has_true = has_opinion = False
    total_fb = 0
    reasons = []
    for ar in replies:
        total_fb += int(ar.get("feedbackCount") or 0)
        rtype = (ar.get("reply") or {}).get("type", "").upper()
        rtext = (ar.get("reply") or {}).get("text") or ""
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
            "matched_text": (node.get("text") or "")[:200],
            "url": url, "reasons": reasons[:3]}


def local_match_candidates(query: str, top_k: int = 5) -> list:
    """本地 SBERT 近鄰 Top-K 檢索。"""
    idx = build_local_index()
    if idx is None:
        return []
    model = _SBERT_MODEL or _get_sbert()
    if not model:
        return []
    import numpy as np
    q = model.encode([query], convert_to_numpy=True,
                     normalize_embeddings=True)[0]
    keys, emb = idx
    sims = emb @ q
    top_indices = np.argsort(sims)[::-1][:top_k]
    
    con = _ensure_db()
    results = []
    for idx_pos in top_indices:
        sim = float(sims[idx_pos])
        if sim < 0.50:  # 粗篩門檻 0.50
            break
        k = keys[idx_pos]
        row = con.execute(
            "SELECT status,feedback_count,created_at,article_id,text,reasons FROM corpus "
            "WHERE key=?", (k,)).fetchone()
        if row:
            reasons = []
            try:
                reasons = json.loads(row[5]) if row[5] else []
            except Exception:
                reasons = []
            results.append({
                "status": row[0], "feedback_count": row[1],
                "created_at": row[2], "article_id": row[3],
                "matched_text": (row[4] or "")[:200], "sim": sim,
                "url": f"https://cofacts.tw/article/{row[3]}" if row[3] else None,
                "reasons": reasons
            })
    con.close()
    return results


def get_fact_check(text: str, use_cache: bool = True,
                   timeout_api: int = 15) -> dict:
    """三階段事實查核入口：
    階段一：雙路召回 (GraphQL + 本地 Top-K)
    階段二：二重比對 (Entity Gatekeeper + SBERT Rerank)
    階段三：精準分數與結果輸出
    """
    default_empty = {"status": "not_found", "feedback_count": 0,
                     "created_at": None, "article_id": None,
                     "matched_text": None, "url": None, "reasons": [],
                     "similarity_score": 0.0}
    if not text or not isinstance(text, str) or len(text.strip()) < 20:
        return default_empty

    snippet = text[:300]
    key = hashlib.sha1(snippet.encode("utf-8")).hexdigest()
    if use_cache:
        c = _cache_get(key)
        if c:
            return c

    candidates = []

    # 1. 階段一召回：Cofacts GraphQL API
    payload = {"query": _GRAPHQL, "variables": {
        "filter": {"moreLikeThis": {"like": snippet}}}}
    try:
        r = requests.post(COFACTS_API_URL, json=payload,
                          headers={"User-Agent": UA, "Content-Type": "application/json"},
                          timeout=timeout_api + 5)
        if r.status_code == 200:
            data = r.json()
            edges = (data.get("data") or {}).get("ListArticles", {}).get("edges") or []
            for edge in edges[:5]:
                node = edge.get("node")
                if node:
                    c_info = _classify_candidate(node)
                    candidates.append(c_info)
    except Exception:
        pass

    # 2. 階段一召回：本地 SBERT Top-K
    local_cands = local_match_candidates(snippet, top_k=5)
    candidates.extend(local_cands)

    if not candidates:
        return default_empty

    # 階段二：精篩比對 (Entity Gatekeeper + SBERT Rerank)
    best_candidate = None
    best_sim = 0.0

    for cand in candidates:
        m_text = cand.get("matched_text") or ""
        if not m_text:
            continue
        
        # 第一重：實體過濾門控 Check
        if not entity_gatekeeper(snippet, m_text):
            continue
            
        # 第二重：SBERT 精準相似度計算
        sim = _sbert_sim(snippet, m_text)
        if sim is None:
            sim = cand.get("sim", 0.0)
            
        cand["similarity_score"] = sim
        if sim > best_sim:
            best_sim = sim
            best_candidate = cand

    # 判定與動態門檻衰減
    if best_candidate and best_sim >= COFACTS_MIN_SIM:
        best_candidate["similarity_score"] = best_sim
        if use_cache:
            _cache_put(key, best_candidate)
        return best_candidate

    return default_empty


def get_fact_check_structured(text: str, use_cache: bool = True,
                              timeout_api: int = 15) -> dict:
    r = get_fact_check(text, use_cache=use_cache, timeout_api=timeout_api)
    r["source"] = "cofacts"
    return r


# ---------------------------------------------------------------------------
# 本地 SBERT 索引與載入
# ---------------------------------------------------------------------------
_SBERT_MODEL = None
_SBERT_PATH = ("/home/min20120907/.cache/huggingface/hub/"
               "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/"
               "snapshots/e8f8c211226b894fcb81acc59f3b34ba3efd5f42")
INDEX_CACHE = os.path.join(os.path.dirname(CACHE_DB), "sbert_index.npz")
_LOCAL_EMB = None


def set_sbert_model(model):
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


def _corpus_all():
    try:
        con = _ensure_db()
        rows = con.execute(
            "SELECT key,text,status,feedback_count,created_at,article_id,reasons "
            "FROM corpus").fetchall()
        con.close()
        return rows
    except Exception:
        return []


def build_local_index(force=False):
    global _LOCAL_EMB
    if _LOCAL_EMB is not None and not force:
        return _LOCAL_EMB
    import numpy as np, hashlib, os
    rows = _corpus_all()
    if not rows:
        return None
    keys = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    h = hashlib.sha1(("||".join("%s:%s" % (k, r[2]) for k, r in zip(keys, rows))[:5000]).encode("utf-8")).hexdigest()
    if not force and os.path.exists(INDEX_CACHE):
        try:
            d = np.load(INDEX_CACHE, allow_pickle=True)
            if d["hash"] == h:
                _LOCAL_EMB = (list(d["keys"]), d["emb"])
                return _LOCAL_EMB
        except Exception:
            pass
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


def local_match(query, threshold=0.72):
    res = get_fact_check(query, use_cache=False)
    if res.get("status") != "not_found" and res.get("similarity_score", 0.0) >= threshold:
        return res
    return None
