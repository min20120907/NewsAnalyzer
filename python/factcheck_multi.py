# -*- coding: utf-8 -*-
"""
多來源事實查核聚合器
====================
統一介面查詢多個事實查核源，回傳一致結構的清單：

    [ {source, status, feedback_count, created_at,
       article_id, matched_text, url, reasons: [ {type, text} ] }, ... ]

支援來源：
  - cofacts : g0v Cofacts（GraphQL，免 key）            [always on]
  - google  : Google Fact Check Tools API（需免費 key）[有 key 才啟用]
  - mygopen : MyGoPen 站內搜尋爬蟲（免 key，處理反爬）  [always on]

status 對映（統一到 Cofacts 四類）：
  inaccurate | partial | accurate | not_found

注意：Google Fact Check API 的 claimReview 用 rating 文字，需做關鍵字對映。
MyGoPen 站內搜尋是爬蟲，可能偶爾被反爬擋住 → 失敗時該源回 not_found 不影響其他源。
"""
import os
import re
import json
import time
import sqlite3
import hashlib
import requests
from datetime import datetime, timezone

from cofacts_local import get_fact_check_structured

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

GOOGLE_API_KEY = os.environ.get("GOOGLE_FACTCHECK_API_KEY", "")
GOOGLE_EP = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

MYGOPEN_SEARCH = "https://www.mygopen.com/search"
MYGOPEN_BASE = "https://www.mygopen.com"

CACHE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "cofacts", "multifc_cache.db")


# ----------------------------------------------------------------------------
# 快取（多源共用，按 source+text hash）
# ----------------------------------------------------------------------------
def _ensure_db():
    os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    con = sqlite3.connect(CACHE_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS mcache (
        key TEXT PRIMARY KEY, source TEXT, payload TEXT, ts REAL
    )""")
    con.commit()
    return con


def _mcache_get(source, key):
    try:
        con = _ensure_db()
        row = con.execute("SELECT payload FROM mcache WHERE key=? AND source=?",
                          (key, source)).fetchone()
        con.close()
        if row:
            return json.loads(row[0])
    except Exception:
        pass
    return None


def _mcache_put(source, key, payload):
    try:
        con = _ensure_db()
        con.execute("INSERT OR REPLACE INTO mcache VALUES (?,?,?,?)",
                    (key, source, json.dumps(payload, ensure_ascii=False), time.time()))
        con.commit()
        con.close()
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Google Fact Check Tools API
# ----------------------------------------------------------------------------
def _map_google_rating(text: str):
    """把 Google claimReview 的 rating text 對映到四類。"""
    t = (text or "").lower()
    if any(k in t for k in ["false", "fake", "錯誤", "不實", "謠言", "假"]):
        return "inaccurate"
    if any(k in t for k in ["true", "correct", "正確", "屬實", "真"]):
        return "accurate"
    if any(k in t for k in ["partial", "mixed", "部分", "混合"]):
        return "partial"
    # 含 'satire'/'opinion' 等也視為 partial
    if any(k in t for k in ["satire", "opinion", "諷刺", "意見"]):
        return "partial"
    return "not_found"


def get_google_factcheck(text: str, use_cache: bool = True,
                         timeout_api: int = 15) -> dict:
    if not GOOGLE_API_KEY:
        return {"source": "google", "status": "disabled",
                "feedback_count": 0, "created_at": None,
                "article_id": None, "matched_text": None, "url": None,
                "reasons": [], "note": "未設定 GOOGLE_FACTCHECK_API_KEY"}
    if not text or len(text.strip()) < 10:
        return _empty("google")
    snippet = text[:300]
    key = hashlib.sha1(("g:" + snippet).encode("utf-8")).hexdigest()
    if use_cache:
        c = _mcache_get("google", key)
        if c:
            return c
    try:
        r = requests.get(GOOGLE_EP, params={"key": GOOGLE_API_KEY,
                                            "query": snippet,
                                            "languageCode": "zh"},
                         headers={"User-Agent": UA}, timeout=timeout_api)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"source": "google", "status": "error",
                "feedback_count": 0, "created_at": None,
                "article_id": None, "matched_text": None, "url": None,
                "reasons": [], "note": f"API 錯誤: {e}"}
    claims = data.get("claims", [])
    if not claims:
        res = _empty("google")
        _mcache_put("google", key, res)
        return res
    # 取第一筆 claim 的第一個 review
    claim = claims[0]
    reviews = claim.get("claimReview", [])
    reasons = []
    status = "not_found"
    url = None
    if reviews:
        rv = reviews[0]
        rating = rv.get("textualRating") or ""
        status = _map_google_rating(rating)
        url = (rv.get("url") or
               (rv.get("publisher") or {}).get("site") or None)
        reasons.append({"type": "GOOGLE_RATING",
                        "text": f"{rating} — {(rv.get('publisher') or {}).get('name', '未知來源')}"})
    res = {"source": "google", "status": status,
           "feedback_count": len(claims), "created_at": None,
           "article_id": None,
           "matched_text": (claim.get("text") or "")[:120],
           "url": url, "reasons": reasons}
    _mcache_put("google", key, res)
    return res


# ----------------------------------------------------------------------------
# MyGoPen 站內搜尋爬蟲
# ----------------------------------------------------------------------------
def _map_mygopen_title(title: str):
    """MyGoPen 標題通常含【易誤解】【詐騙】【是真的嗎】等，粗略對映。"""
    t = (title or "")
    if any(k in t for k in ["詐騙", "假", "謠言", "不實", "易誤解", "錯誤"]):
        return "inaccurate"
    if any(k in t for k in ["是真的", "正確", "屬實", "破解"]):
        return "accurate"
    return "partial"


def get_mygopen(text: str, use_cache: bool = True,
                timeout_api: int = 15) -> dict:
    if not text or len(text.strip()) < 10:
        return _empty("mygopen")
    # 取前兩句關鍵字做搜尋（避免整段太長抓不到）
    snippet = text[:120]
    key = hashlib.sha1(("m:" + snippet).encode("utf-8")).hexdigest()
    if use_cache:
        c = _mcache_get("mygopen", key)
        if c:
            return c
    try:
        r = requests.get(MYGOPEN_SEARCH, params={"q": snippet},
                         headers={"User-Agent": UA,
                                  "Accept-Language": "zh-TW,zh;q=0.9"},
                         timeout=timeout_api)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        res = {"source": "mygopen", "status": "error",
               "feedback_count": 0, "created_at": None,
               "article_id": None, "matched_text": None, "url": None,
               "reasons": [], "note": f"爬蟲錯誤: {e}"}
        return res
    # 解析搜尋結果：MyGoPen 站內搜尋結果是 <article> 含 <a href> 與 <h2>/<h3> 標題
    links = re.findall(r'<a[^>]+href="(' + re.escape(MYGOPEN_BASE) +
                       r'/[\d]{4}/[\d]{2}/[^"]+)"[^>]*>', html)
    titles = re.findall(r'<h[23][^>]*>(?:<a[^>]*>)?\s*(.*?)\s*(?:</a>)?</h[23]>',
                        html, re.S)
    clean = lambda s: re.sub(r"<[^>]+>", "", s).strip()
    if not links:
        res = _empty("mygopen")
        _mcache_put("mygopen", key, res)
        return res
    top_url = links[0]
    top_title = clean(titles[0]) if titles else ""
    status = _map_mygopen_title(top_title)
    res = {"source": "mygopen", "status": status,
           "feedback_count": len(links), "created_at": None,
           "article_id": None, "matched_text": top_title[:120],
           "url": top_url,
           "reasons": [{"type": "MYGOPEN_TITLE",
                        "text": top_title or top_url}]}
    _mcache_put("mygopen", key, res)
    return res


# ----------------------------------------------------------------------------
# 統一彙總
# ----------------------------------------------------------------------------
def _empty(source):
    return {"source": source, "status": "not_found", "feedback_count": 0,
            "created_at": None, "article_id": None, "matched_text": None,
            "url": None, "reasons": []}


def get_all_fact_checks(text: str, use_cache: bool = True,
                        timeout_api: int = 15) -> list:
    """並行查詢所有源，回傳結果清單（含 disabled/error 狀態的源也列出）。"""
    results = []
    # Cofacts（含本地 SBERT fallback）
    try:
        results.append(get_fact_check_structured(text, use_cache=use_cache,
                                                 timeout_api=timeout_api))
    except Exception as e:
        results.append({**_empty("cofacts"), "status": "error",
                        "note": str(e)})
    # Google（無 key 自動 disabled）
    try:
        results.append(get_google_factcheck(text, use_cache=use_cache,
                                            timeout_api=timeout_api))
    except Exception as e:
        results.append({**_empty("google"), "status": "error", "note": str(e)})
    # MyGoPen（爬蟲）
    try:
        results.append(get_mygopen(text, use_cache=use_cache,
                                   timeout_api=timeout_api))
    except Exception as e:
        results.append({**_empty("mygopen"), "status": "error", "note": str(e)})
    return results


if __name__ == "__main__":
    import sys
    probe = sys.argv[1] if len(sys.argv) > 1 else "萊豬进口政府說明"
    out = get_all_fact_checks(probe)
    print(json.dumps(out, ensure_ascii=False, indent=2))
