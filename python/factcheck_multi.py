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
  - rumtoast: 蘭姆酒吐司 WP REST 搜尋＋內文 verdict（免 key）[always on]
  - hkbu    : HKBU Fact Check WP REST 搜尋＋標題 verdict（免 key）[always on]

status 對映（統一到 Cofacts 四類）：
  inaccurate | partial | accurate | not_found

注意：Google Fact Check API 的 claimReview 用 rating 文字，需做關鍵字對映。
MyGoPen 站內搜尋是爬蟲，可能偶爾被反爬擋住 → 失敗時該源回 not_found 不影響其他源。
"""
import os
import re
import html
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


def _detect_lang(text: str) -> str:
    """語言路由（免依賴）：CJK 字佔比 >10% 視為中文，否則走英文。
    英文不換 SBERT 模型——現役 paraphrase-multilingual-MiniLM 本就含英文；
    換 all-MiniLM 必須重算全部門控 margin（見 embedding-margin-bench 教訓），
    v1 先只切證據源語言。"""
    t = text or ""
    if not t.strip():
        return "zh"
    cjk = sum(1 for c in t if "一" <= c <= "鿿")
    return "zh" if cjk / max(len(t), 1) > 0.10 else "en"


_EN_STOP = {"the", "a", "an", "in", "on", "of", "to", "is", "are",
            "was", "were", "be", "been", "and", "or", "for", "with",
            "that", "this", "it", "as", "by", "from", "says", "said",
            "say", "claim", "claims", "claimed", "new", "over", "amid",
            "will", "would", "has", "have", "had", "do", "does", "did"}


def _en_keywords(text: str, limit: int = 6) -> str:
    """英文 Claim Search 查詢詞：去停用詞取前 N 實詞。
    實測整句直送 0 筆（"CDC cover-up" 尾巴殺掉召回），前 5 實詞回 10 筆。"""
    toks = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text or "")
    out = [t for t in toks if t.lower() not in _EN_STOP and len(t) > 1]
    return " ".join(out[:limit])


def get_google_factcheck(text: str, use_cache: bool = True,
                         timeout_api: int = 15, lang: str = None) -> dict:
    if not GOOGLE_API_KEY:
        return {"source": "google", "status": "disabled",
                "feedback_count": 0, "created_at": None,
                "article_id": None, "matched_text": None, "url": None,
                "reasons": [], "note": "未設定 GOOGLE_FACTCHECK_API_KEY"}
    if not text or len(text.strip()) < 10:
        return _empty("google")
    # g2 前綴沿用（帶 similarity_score 世代）；再帶語言，中英查不同庫不可共用快取
    lang = lang or _detect_lang(text)
    snippet = ((_en_keywords(text) or text[:120]) if lang == "en"
               else text[:300])
    key = hashlib.sha1((f"g2:{lang}:" + snippet).encode("utf-8")).hexdigest()
    if use_cache:
        c = _mcache_get("google", key)
        if c:
            return c
    try:
        r = requests.get(GOOGLE_EP, params={"key": GOOGLE_API_KEY,
                                            "query": snippet,
                                            "languageCode": lang},
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


def _jieba_keywords(snippet: str, limit: int = 4) -> str:
    """jieba 斷詞取空白分隔關鍵字（feed/站內搜尋用，整句直送會 0 筆）。"""
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
            if len(_toks) >= limit:
                break
        return " ".join(_toks)
    except Exception:
        return ""


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
    query = _jieba_keywords(snippet) or snippet[:30]
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
# 蘭姆酒吐司 + HKBU Fact Check（WordPress REST 搜尋，免 key）
# ----------------------------------------------------------------------------
RUMTOAST_SEARCH = "https://rumtoast.com/wp-json/wp/v2/search"
RUMTOAST_POST = "https://rumtoast.com/wp-json/wp/v2/posts"
HKBU_SEARCH = "https://factcheck.hkbu.edu.hk/home/wp-json/wp/v2/search"

# 兩站標題/內文都是 verdict-bearing（HKBU 標題、rumtoast 內文），沿用 mygopen
# 的「標題關鍵詞映射 + SBERT 0.50 門控」形狀；粵語口語命中偏低只會 not_found，
# 不會誤判（保守方向），閾值待粵語標註集重校。


def _map_hkbu_title(title: str):
    """HKBU 標題多半自帶 verdict（【錯誤】/…不實/實為…/並非…）；無標記的
    專欄/評論（如【假新聞面面觀】問句、立法評論）落 partial，不硬判。"""
    t = title or ""
    if any(k in t for k in ["錯誤", "不實", "闢謠", "實為", "實際", "並非", "並未",
                            "實經", "查無此事", "子虛烏有"]):
        return "inaccurate"
    if any(k in t for k in ["屬實", "是真的", "確實發生", "證實為真"]):
        return "accurate"
    return "partial"


def _map_rumtoast_content(content: str):
    """rumtoast verdict 在內文（破解段）。注意每篇頁尾固定有
    「…對於謠言查證的努力」 boilerplate，單獨「謠言」二字不算數。"""
    t = content or ""
    if any(k in t for k in ["假消息", "是假的", "假的！", "錯誤的", "沒有這回事",
                            "別信", "是錯誤", "誤導", "假訊息"]):
        return "inaccurate"
    if any(k in t for k in ["是真的", "確實如此", "真的有", "確有其事"]):
        return "accurate"
    return "partial"


def _wp_search(url: str, query: str, timeout_api: int):
    r = requests.get(url, params={"search": query, "per_page": 6},
                     headers={"User-Agent": UA,
                              "Accept-Language": "zh-TW,zh;q=0.9"},
                     timeout=timeout_api)
    r.raise_for_status()
    items = r.json()
    out = []
    for it in items if isinstance(items, list) else []:
        t = (it.get("title") or "").strip()
        u = (it.get("url") or "").strip()
        if t and u:
            out.append((it.get("id"), t, u))
    return out


def _sbert_gate(snippet: str, candidates, threshold: float = 0.50):
    """逐條 SBERT 驗、取首條通過者（同 mygopen 門控）；返回 (id, title, url, sim)。"""
    try:
        from cofacts_local import _sbert_sim
    except Exception:
        return candidates[0] + (None,) if candidates else None
    for cid, t, u in candidates:
        try:
            _s = _sbert_sim(snippet, t) or 0.0
        except Exception:
            _s = 0.0
        if _s >= threshold:
            return (cid, t, u, round(float(_s), 4))
    return None


def get_hkbu(text: str, use_cache: bool = True,
             timeout_api: int = 15) -> dict:
    if not text or len(text.strip()) < 10:
        return _empty("hkbu")
    snippet = text[:120]
    key = hashlib.sha1(("hkbu:" + snippet).encode("utf-8")).hexdigest()
    if use_cache:
        c = _mcache_get("hkbu", key)
        if c:
            return c
    try:
        cands = _wp_search(HKBU_SEARCH, _jieba_keywords(snippet) or snippet[:30],
                           timeout_api)
    except Exception as e:
        return {"source": "hkbu", "status": "error",
                "feedback_count": 0, "created_at": None,
                "article_id": None, "matched_text": None, "url": None,
                "reasons": [], "note": f"爬蟲錯誤: {e}"}
    if not cands:
        res = _empty("hkbu")
        _mcache_put("hkbu", key, res)
        return res
    win = _sbert_gate(snippet, cands)
    if not win:
        res = _empty("hkbu")
        _mcache_put("hkbu", key, res)
        return res
    _cid, top_title, top_url, win_sim = win
    res = {"source": "hkbu", "status": _map_hkbu_title(top_title),
           "feedback_count": len(cands), "created_at": None,
           "article_id": None, "matched_text": top_title[:120],
           "url": top_url, "similarity_score": win_sim,
           "reasons": [{"type": "HKBU_TITLE",
                        "text": top_title or top_url}]}
    _mcache_put("hkbu", key, res)
    return res


def get_rumtoast(text: str, use_cache: bool = True,
                 timeout_api: int = 15) -> dict:
    if not text or len(text.strip()) < 10:
        return _empty("rumtoast")
    snippet = text[:120]
    key = hashlib.sha1(("rt:" + snippet).encode("utf-8")).hexdigest()
    if use_cache:
        c = _mcache_get("rumtoast", key)
        if c:
            return c
    try:
        cands = _wp_search(RUMTOAST_SEARCH, _jieba_keywords(snippet) or snippet[:30],
                           timeout_api)
    except Exception as e:
        return {"source": "rumtoast", "status": "error",
                "feedback_count": 0, "created_at": None,
                "article_id": None, "matched_text": None, "url": None,
                "reasons": [], "note": f"爬蟲錯誤: {e}"}
    if not cands:
        res = _empty("rumtoast")
        _mcache_put("rumtoast", key, res)
        return res
    win = _sbert_gate(snippet, cands)
    if not win:
        res = _empty("rumtoast")
        _mcache_put("rumtoast", key, res)
        return res
    cid, top_title, top_url, win_sim = win
    # rumtoast 標題多半是問句、無 verdict，抓內文映射（多一次 GET，約 +0.5s）
    try:
        r = requests.get(f"{RUMTOAST_POST}/{cid}",
                         headers={"User-Agent": UA}, timeout=timeout_api)
        r.raise_for_status()
        raw = ((r.json().get("content") or {}).get("rendered") or "")
        content = re.sub(r"<[^>]+>", "", html.unescape(raw))
    except Exception:
        content = ""
    status = _map_rumtoast_content(content)
    res = {"source": "rumtoast", "status": status,
           "feedback_count": len(cands), "created_at": None,
           "article_id": None, "matched_text": top_title[:120],
           "url": top_url, "similarity_score": win_sim,
           "reasons": [{"type": "RUMTOAST_CONTENT",
                        "text": (content[:400] or top_title) or top_url}]}
    _mcache_put("rumtoast", key, res)
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

    各源皆為 requests 呼叫＋各自 try/except，自行吞錯；快取每次開新連線，
    例外同樣吞掉，因此 ThreadPool 並行安全。順序固定
    [cofacts, google, mygopen, rumtoast, hkbu]。
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

    def _run_rumtoast():
        try:
            return get_rumtoast(text, use_cache=use_cache,
                                timeout_api=timeout_api)
        except Exception as e:
            return {**_empty("rumtoast"), "status": "error", "note": str(e)}

    def _run_hkbu():
        try:
            return get_hkbu(text, use_cache=use_cache,
                            timeout_api=timeout_api)
        except Exception as e:
            return {**_empty("hkbu"), "status": "error", "note": str(e)}

    with _cf.ThreadPoolExecutor(max_workers=5) as _ex:
        _fu = [_ex.submit(_run_cofacts), _ex.submit(_run_google),
               _ex.submit(_run_mygopen), _ex.submit(_run_rumtoast),
               _ex.submit(_run_hkbu)]
        results = [_f.result() for _f in _fu]
    return results


if __name__ == "__main__":
    import sys
    probe = sys.argv[1] if len(sys.argv) > 1 else "萊豬进口政府說明"
    out = get_all_fact_checks(probe)
    print(json.dumps(out, ensure_ascii=False, indent=2))
