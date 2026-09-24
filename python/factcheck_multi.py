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

MYGOPEN_FEED = "https://www.mygopen.com/feeds/posts/default"
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
    # key 前綴 g2：2026-09-24 起回傳 similarity_score（舊 g: 快取無此欄，會讓錨定誤判 100%）
    key = hashlib.sha1(("g2:" + snippet).encode("utf-8")).hexdigest()
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
    # 2026-09-24：回傳輸入與命中 claim 的語意相似度，供錨定用真實信心（缺此欄會被當 100%）
    try:
        from cofacts_local import _sbert_sim
        _gs = _sbert_sim(snippet, claim.get("text") or "")
        res["similarity_score"] = round(float(_gs), 4) if _gs is not None else None
    except Exception:
        res["similarity_score"] = None
    _mcache_put("google", key, res)
    return res


# ----------------------------------------------------------------------------
# MyGoPen 站內搜尋爬蟲
# ----------------------------------------------------------------------------
def _map_mygopen_title(title: str):
    """MyGoPen 標題通常含【易誤解】【詐騙】【是真的嗎】等，粗略對映。"""
    t = (title or "")
    if any(k in t for k in ["詐騙", "假", "謠言", "不實", "易誤解", "誤導", "錯誤"]):
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
    # key 前綴 m3：2026-09-24 起回傳 similarity_score（舊 m2: 快取無此欄，會讓錨定誤判 100%）
    key = hashlib.sha1(("m3:" + snippet).encode("utf-8")).hexdigest()
    if use_cache:
        c = _mcache_get("mygopen", key)
        if c:
            return c
    # feed 的 q 是嚴格片語比對：整句 120 字查永遠 0 筆，必須斷成空白分隔關鍵字
    try:
        import jieba as _jieba
        _STOP = {"網傳", "宣稱", "真的", "請問", "消息", "影片", "圖片",
                 "可以", "這是", "那是", "是否", "今天", "昨天"}
        _toks, _seen = [], set()
        for _t in _jieba.cut(snippet):
            _t = _t.strip("，。、；：『』「」！？!?,. \t")
            if 2 <= len(_t) <= 6 and _t not in _seen and _t not in _STOP and any(
                    "一" <= _c <= "鿿" for _c in _t):
                _seen.add(_t)
                _toks.append(_t)
            if len(_toks) >= 4:
                break
        query = " ".join(_toks) or snippet[:30]
    except Exception:
        query = snippet[:30]
    try:
        # 舊版爬 /search HTML，但該站主題改 JS 渲染後頁面無內文連結（200 空殼），一律 not_found；
        # 改打 Blogger 公開 feed（免 key、伺服器端回 JSON）：/feeds/posts/default?q=&alt=json
        r = requests.get(MYGOPEN_FEED, params={"q": query, "alt": "json",
                                               "max-results": 6},
                         headers={"User-Agent": UA,
                                  "Accept-Language": "zh-TW,zh;q=0.9"},
                         timeout=timeout_api)
        r.raise_for_status()
        feed = (r.json().get("feed") or {})
        entries = feed.get("entry") or []
    except Exception as e:
        res = {"source": "mygopen", "status": "error",
               "feedback_count": 0, "created_at": None,
               "article_id": None, "matched_text": None, "url": None,
               "reasons": [], "note": f"爬蟲錯誤: {e}"}
        return res
    # 解析 feed 條目：title.$t + rel=alternate 連結（形如 /2026/09/xxx.html）
    links, titles = [], []
    for e in entries:
        t = ((e.get("title") or {}).get("$t") or "").strip()
        u = ""
        for l in (e.get("link") or []):
            if l.get("rel") == "alternate" and (l.get("href") or "").startswith(MYGOPEN_BASE):
                u = l["href"]
                break
        if t and u:
            titles.append(t)
            links.append(u)
    if not links:
        res = _empty("mygopen")
        _mcache_put("mygopen", key, res)
        return res
    # 相似度門控（2026-09 反向驗證抓到誤判：真實抽獎活動撞上「交通違規罰鍰詐騙簡訊」，
    # 只因共享 交通/違規 關鍵字就被掛 inaccurate）：逐條驗證，取首條通過者。
    # 實測同謠言家族 sim≈0.68+、無關主題≈0.33，閾值取 0.50。
    top_url, top_title, win_sim = None, "", None
    try:
        from cofacts_local import _sbert_sim
        for u, t in zip(links, titles):
            _s = _sbert_sim(snippet, t) or 0.0
            if _s >= 0.50:
                top_url, top_title, win_sim = u, t, round(float(_s), 4)
                break
    except Exception:
        top_url, top_title = links[0], titles[0] if titles else ""
    if not top_url:
        res = _empty("mygopen")
        _mcache_put("mygopen", key, res)
        return res
    status = _map_mygopen_title(top_title)
    res = {"source": "mygopen", "status": status,
           "feedback_count": len(links), "created_at": None,
           "article_id": None, "matched_text": top_title[:120],
           "url": top_url, "similarity_score": win_sim,
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
            "url": None, "similarity_score": None, "reasons": []}


def get_all_fact_checks(text: str, use_cache: bool = True,
                        timeout_api: int = 15) -> list:
    """並行查詢所有源，回傳結果清單（含 disabled/error 狀態的源也列出）。

    三源皆為 requests 呼叫＋各自 try/except，自行吞錯；快取每次開新連線，
    例外同樣吞掉，因此 ThreadPool 並行安全。順序固定 [cofacts, google, mygopen]。
    """
    import concurrent.futures as _cf

    def _run_cofacts():
        try:
            return get_fact_check_structured(text, use_cache=use_cache,
                                             timeout_api=timeout_api)
        except Exception as e:
            return {**_empty("cofacts"), "status": "error", "note": str(e)}

    def _run_google():
        try:
            return get_google_factcheck(text, use_cache=use_cache,
                                        timeout_api=timeout_api)
        except Exception as e:
            return {**_empty("google"), "status": "error", "note": str(e)}

    def _run_mygopen():
        try:
            return get_mygopen(text, use_cache=use_cache,
                               timeout_api=timeout_api)
        except Exception as e:
            return {**_empty("mygopen"), "status": "error", "note": str(e)}

    with _cf.ThreadPoolExecutor(max_workers=3) as _ex:
        _fu = [_ex.submit(_run_cofacts), _ex.submit(_run_google),
               _ex.submit(_run_mygopen)]
        results = [_f.result() for _f in _fu]
    return results


if __name__ == "__main__":
    import sys
    probe = sys.argv[1] if len(sys.argv) > 1 else "萊豬进口政府說明"
    out = get_all_fact_checks(probe)
    print(json.dumps(out, ensure_ascii=False, indent=2))
