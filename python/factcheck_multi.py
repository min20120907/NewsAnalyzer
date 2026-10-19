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
  - infact  : InFact WP REST 搜尋＋標題 verdict（免 key）[always on]
  - jfc     : 日本FCセンター RSS＋本地 SBERT 比對（免 key）[always on]

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


# 2026-10-18：快取 TTL。舊碼有 ts 欄位但讀取時完全不管 → 快取永不過期。
# 實測 mcache 累積 9179 筆 not_found（最舊 52 天），意思是「查不到」一旦寫入就永久
# 生效：來源修好、召回改好、站方補了查核，使用者還是看到同一個 not_found。
# 這就是「明明查核有、卻找不到」的第二個獨立成因（跟召回無關）。
# 正/負結果分開 TTL：判定（inaccurate/accurate…）幾乎不變，可長存；
# 空結果是「這次沒撈到」，必須會過期才會重試。
_CACHE_NEG_STATUS = {"not_found", "unrelated", "error", "disabled", None, ""}


def _cache_ttl(status) -> float:
    """回傳該筆 payload 的快取壽命（秒）。<=0 表示不快取（一律視為過期）。"""
    if os.environ.get("FC_CACHE_DISABLE", "") == "1":
        return 0.0
    if status in _CACHE_NEG_STATUS:
        return float(os.environ.get("FC_CACHE_TTL_NEG", "21600"))   # 6h
    return float(os.environ.get("FC_CACHE_TTL", "604800"))          # 7d


def _mcache_get(source, key):
    try:
        con = _ensure_db()
        row = con.execute("SELECT payload, ts FROM mcache WHERE key=? AND source=?",
                          (key, source)).fetchone()
        con.close()
        if row:
            try:
                d = json.loads(row[0])
            except Exception:
                return None
            if not isinstance(d, dict):
                return None
            ttl = _cache_ttl(d.get("status"))
            if ttl <= 0 or (time.time() - float(row[1] or 0.0)) > ttl:
                return None
            return d
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
    if any(k in t for k in ["false", "fake", "pants on fire", "pants-fire",
                            "錯誤", "不實", "謠言", "假"]):
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
    """語言路由（免依賴）：假名→日文；CJK 佔比 >10%→中文；否則英文。
    英文不換 SBERT 模型——現役 paraphrase-multilingual-MiniLM 本就含英文；
    換 all-MiniLM 必須重算全部門控 margin（見 embedding-margin-bench 教訓），
    v1 先只切證據源語言。日文同理（多語言模型含日文；sup-simcse-ja 是優化項）。"""
    t = text or ""
    if not t.strip():
        return "zh"
    if re.search(r"[ぁ-んァ-ヶ]", t):
        return "ja"
    cjk = sum(1 for c in t if "一" <= c <= "鿿")
    return "zh" if cjk / max(len(t), 1) > 0.10 else "en"


_EN_STOP = {"the", "a", "an", "in", "on", "of", "to", "is", "are",
            "was", "were", "be", "been", "and", "or", "for", "with",
            "that", "this", "it", "as", "by", "from", "says", "said",
            "say", "claim", "claims", "claimed", "new", "over", "amid",
            "will", "would", "has", "have", "had", "do", "does", "did",
            "not", "no", "nor", "s", "t", "nt"}


def _en_keywords(text: str, limit: int = 6) -> str:
    """英文 Claim Search 查詢詞：去停用詞取前 N 實詞。
    實測整句直送 0 筆（"CDC cover-up" 尾巴殺掉召回），前 5 實詞回 10 筆。"""
    toks = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text or "")
    out = [t for t in toks if t.lower() not in _EN_STOP and len(t) > 1]
    return " ".join(out[:limit])


def _ja_keywords(text: str, limit: int = 4) -> str:
    """日文查詢詞：漢字 2 字以上 run＋片假名 3 字以上 run＋英數。
    平假名多半是助詞、跳過；jieba 不懂日文，不走 _jieba_keywords。"""
    toks = re.findall(r"[一-鿿]{2,}|[ァ-ヶー]{3,}|[A-Za-z0-9][A-Za-z0-9'\-]*",
                      text or "")
    out, seen = [], set()
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= limit:
            break
    return " ".join(out)


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
    # g5 世代（2026-10-08）：en 改 Top-K 自選＋0.60 門控，選 claim 不同故全換；
    # 舊 g2 欄缺門控語義會讓錨定誤判（同 2026-09-24 g→g2 教訓）
    key = hashlib.sha1((f"g5:{lang}:" + snippet).encode("utf-8")).hexdigest()
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
    # Top-K 自選函式（2026-10-08，僅 en 用）：逐條 SBERT 比全文取最高者。
    # API 排序會抖（同查詢不同時間 claims[0] 不同），只取首筆等於賭運氣。
    # 中文沿用 claims[0]，行為不動。
    def _pick_best(cands):
        try:
            from cofacts_local import _sbert_sim as _gsim
        except Exception:
            _gsim = None
        ranked = []
        for cl in cands[:10]:
            ct = cl.get("text") or ""
            try:
                s = float(_gsim(text[:300], ct)) if _gsim else None
            except Exception:
                s = None
            ranked.append((s if s is not None else -1.0, cl))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[0] if ranked else (None, None)
    if lang == "en":
        best_sim, claim = _pick_best(claims)
        if snippet != text[:300] and (best_sim is None or best_sim < 0.60):
            # tier-2 全文查詢：關鍵詞路最佳 <0.60 才付第二次成本；
            # 兩路贏面不同（關鍵詞救長尾、全文救斷片），取兩路最佳者
            try:
                r2 = requests.get(
                    GOOGLE_EP, params={"key": GOOGLE_API_KEY,
                                       "query": text[:300],
                                       "languageCode": lang},
                    headers={"User-Agent": UA}, timeout=timeout_api)
                r2.raise_for_status()
                claims2 = r2.json().get("claims", [])
            except Exception:
                claims2 = []
            if claims2:
                best2, claim2 = _pick_best(claims2)
                if best2 is not None and best2 > (best_sim or -1.0):
                    best_sim, claim = best2, claim2
        if claim is None:
            res = _empty("google")
            _mcache_put("google", key, res)
            return res
    else:
        if not claims:
            res = _empty("google")
            _mcache_put("google", key, res)
            return res
        claim = claims[0]
        best_sim = None
    # 取選定 claim 的第一個 review（沿用舊語義）
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
    # similarity_score：en 用 Top-K 自選的全文比；zh 沿用舊算法（claims[0] 全文比），
    # 兩邊缺模型時為 None（下游視為 0 信心，保守方向）
    if lang == "en":
        _bs = best_sim if best_sim is not None and best_sim >= 0.0 else None
    else:
        try:
            from cofacts_local import _sbert_sim
            _bs = _sbert_sim(text[:300], claim.get("text") or "")
        except Exception:
            _bs = None
    res["similarity_score"] = round(float(_bs), 4) if _bs is not None else None
    # 2026-10-08：英文短查詢常召回無關 claim（LIAR 斷片），sim<0.60 降為
    # not_found（小樣本定值：真命中 0.74+／誤召回 0.41~0.54，待大樣本重校）。
    # 只擋 en，中文行為不動。
    if (lang == "en" and res["similarity_score"] is not None
            and res["similarity_score"] < 0.60):
        res = _empty("google")
        res["note"] = "英文命中相似度不足（<0.60），視為無相關查核"
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


def _title_gate_and_sim(query_text: str, title: str,
                        threshold: float = 0.50):
    """標題型中文查核站（MyGoPen / HKBU / 蘭姆酒吐司）共用門控＋SBERT。

    2026-10-19 修：原本只看 _sbert_sim(snippet[:120], title) >= 0.50，未過
    實體門控、關鍵詞交集門控與數字指紋門控 → 同領域不同事件的舊查核（sim 0.51~0.64）
    長驅直入：
      · R09（疾管署估8月中新冠高峰單週破5萬）撞 MyGoPen「網傳新冠又來了？這5種症狀要當心？」
        sim 0.604 → 把 Cofacts 0.926 accurate 硬命中壓掉，真新聞鎖 21.1 分
      · B14（公路局機車零違規抽獎）撞 MyGoPen「機車未打方向燈罰1200」sim 0.588
      · B19（366萬電話詐騙）撞 MyGoPen「緬北騙局手機號碼植入病毒」sim 0.580
    這裡對齊 cofacts_local 的三層門控（標題常不帶數字，故數字閘門用 softd：
    雙方都有數字時才要求交集），並取全池最高分而非首筆通過者。
    """
    from cofacts_local import (_sbert_sim, entity_gatekeeper,
                               _keyword_overlap_gate, _numeric_gate)
    q = (query_text or "")[:300]
    t = (title or "").strip()
    if not q or not t:
        return None
    if not (entity_gatekeeper(q, t)
            and _keyword_overlap_gate(q, t)
            and _numeric_gate(q, t, mode="softd")):
        return None
    _s = _sbert_sim(q, t) or 0.0
    if _s < threshold:
        return None
    return round(float(_s), 4)


def get_mygopen(text: str, use_cache: bool = True,
                timeout_api: int = 15) -> dict:
    if not text or len(text.strip()) < 10:
        return _empty("mygopen")
    # 取前兩句關鍵字做搜尋（避免整段太長抓不到）
    snippet = text[:120]
    # key 前綴 m4：2026-10-19 補齊實體＋關鍵詞交集＋softd 數字門控（舊 m3: 含同領域假命中）
    key = hashlib.sha1(("m4:" + snippet).encode("utf-8")).hexdigest()
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
    top_url, top_title, win_sim = None, "", None
    try:
        for u, t in zip(links, titles):
            _s = _title_gate_and_sim(text, t, threshold=0.50)
            if _s is not None and (win_sim is None or _s > win_sim):
                top_url, top_title, win_sim = u, t, _s
    except Exception:
        top_url, top_title = None, ""
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


def _zh_title_gate(text: str, candidates, threshold: float = 0.50):
    """中文標題型查核（HKBU / 蘭姆酒吐司）：走三層門控＋SBERT，取全池最高分。"""
    best = None
    for cid, t, u in candidates:
        try:
            _s = _title_gate_and_sim(text, t, threshold=threshold)
        except Exception:
            _s = None
        if _s is not None and (best is None or _s > best[3]):
            best = (cid, t, u, _s)
    return best


def get_hkbu(text: str, use_cache: bool = True,
             timeout_api: int = 15) -> dict:
    if not text or len(text.strip()) < 10:
        return _empty("hkbu")
    snippet = text[:120]
    key = hashlib.sha1(("hkbu2:" + snippet).encode("utf-8")).hexdigest()
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
    win = _zh_title_gate(text, cands)
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
    key = hashlib.sha1(("rt2:" + snippet).encode("utf-8")).hexdigest()
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
    win = _zh_title_gate(text, cands)
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
# 日文區：InFact（WP REST 搜尋）＋ JFC（RSS 本地 SBERT 比對，免 key）
# JFC 無 REST（404），RSS 15 篇；verdict 都在標題（は誤り／偽情報／詐欺…）。
# ----------------------------------------------------------------------------
INFACT_SEARCH = "https://infact.press/wp-json/wp/v2/search"
JFC_RSS = "https://www.factcheckcenter.jp/rss/"


def _map_infact_title(title: str):
    """InFact verdict 在標題末（は誤り／は正しい…）。
    問句（は本当か？）與否定形（正しくない／とは言えない）不算肯定，
    落 partial——裸「本当」「正しい」會把問句誤判 accurate（Murayama 實測）。"""
    t = title or ""
    if any(k in t for k in ["誤り", "誤解", "デマ", "虚偽", "捏造", "間違い",
                            "不正確", "事実ではない", "正しくない",
                            "とは言えない", "とはいえない"]):
        return "inaccurate"
    if any(k in t for k in ["は正しい", "が正しい", "正しいです", "は事実です",
                            "本当です", "本当でした"]):
        return "accurate"
    return "partial"


def _map_jfc_title(title: str):
    t = title or ""
    if any(k in t for k in ["偽サイト", "偽情報", "誤情報", "詐欺", "デマ",
                            "根拠不明", "虚偽", "捏造", "誤り"]):
        return "inaccurate"
    if any(k in t for k in ["は正しい", "が正しい", "正しいです", "正確です",
                            "事実です"]):
        return "accurate"
    return "partial"


_JFC_FEED_TTL = 3600
_jfc_feed_cache = {"ts": 0.0, "items": []}


def _rss_titles(url: str, timeout_api: int, limit: int = 20):
    """抓 RSS 列出 (title, link)。解析失敗回空（上游轉址/改版不炸管線）。"""
    import xml.etree.ElementTree as ET
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout_api)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip()
        u = (it.findtext("link") or "").strip()
        if t and u:
            out.append((t, u))
        if len(out) >= limit:
            break
    return out


def get_infact(text: str, use_cache: bool = True,
               timeout_api: int = 15) -> dict:
    if not text or len(text.strip()) < 10:
        return _empty("infact")
    # 2026-10-18：日文站只吃日文。日文 FC 站台與台/中新聞毫無共同事件，
    # 靠多語言 SBERT 的跨語言殘餘相似度（≥0.50）就能掛上 inaccurate
    # （實測 R09／R17／B09／B17 都被日文站誤報 refutes）。語言閘門是零成本正解，
    # 與 politifact 的 en 閘門同形狀。
    if _detect_lang(text) != "ja":
        return _empty("infact")
    snippet = text[:120]
    # infact3: 2026-10-18 加日文語言閘門（非日文輸入一律放空），舊前綴快取作廢
    key = hashlib.sha1(("infact3:" + snippet).encode("utf-8")).hexdigest()
    if use_cache:
        c = _mcache_get("infact", key)
        if c:
            return c
    try:
        cands = _wp_search(INFACT_SEARCH,
                           _ja_keywords(snippet) or snippet[:30],
                           timeout_api)
    except Exception as e:
        return {"source": "infact", "status": "error",
                "feedback_count": 0, "created_at": None,
                "article_id": None, "matched_text": None, "url": None,
                "reasons": [], "note": f"爬蟲錯誤: {e}"}
    if not cands:
        res = _empty("infact")
        _mcache_put("infact", key, res)
        return res
    win = _sbert_gate(snippet, cands)
    if not win:
        res = _empty("infact")
        _mcache_put("infact", key, res)
        return res
    _cid, top_title, top_url, win_sim = win
    res = {"source": "infact", "status": _map_infact_title(top_title),
           "feedback_count": len(cands), "created_at": None,
           "article_id": None, "matched_text": top_title[:120],
           "url": top_url, "similarity_score": win_sim,
           "reasons": [{"type": "INFACT_TITLE",
                        "text": top_title or top_url}]}
    _mcache_put("infact", key, res)
    return res


def get_jfc(text: str, use_cache: bool = True,
            timeout_api: int = 15) -> dict:
    if not text or len(text.strip()) < 10:
        return _empty("jfc")
    # 2026-10-18：日文站只吃日文（同 infact，見該處說明）。jfc 的 RSS 是全站最新
    # 15 篇、完全沒有關鍵詞篩選，任何語言的輸入都只能靠 SBERT 門控擋——
    # 跨語言的殘餘相似度不足以當閘門，語言判準才是。
    if _detect_lang(text) != "ja":
        return _empty("jfc")
    snippet = text[:120]
    # jfc3: 2026-10-18 加日文語言閘門（非日文輸入一律放空），舊前綴快取作廢
    key = hashlib.sha1(("jfc3:" + snippet).encode("utf-8")).hexdigest()
    if use_cache:
        c = _mcache_get("jfc", key)
        if c:
            return c
    try:
        now = time.time()
        if now - _jfc_feed_cache["ts"] > _JFC_FEED_TTL:
            _jfc_feed_cache["items"] = _rss_titles(JFC_RSS, timeout_api)
            _jfc_feed_cache["ts"] = now
        items = _jfc_feed_cache["items"]
    except Exception as e:
        return {"source": "jfc", "status": "error",
                "feedback_count": 0, "created_at": None,
                "article_id": None, "matched_text": None, "url": None,
                "reasons": [], "note": f"爬蟲錯誤: {e}"}
    if not items:
        res = _empty("jfc")
        _mcache_put("jfc", key, res)
        return res
    win = _sbert_gate(snippet, [(None, t, u) for t, u in items])
    if not win:
        res = _empty("jfc")
        _mcache_put("jfc", key, res)
        return res
    _cid, top_title, top_url, win_sim = win
    res = {"source": "jfc", "status": _map_jfc_title(top_title),
           "feedback_count": len(items), "created_at": None,
           "article_id": None, "matched_text": top_title[:120],
           "url": top_url, "similarity_score": win_sim,
           "reasons": [{"type": "JFC_TITLE",
                        "text": top_title or top_url}]}
    _mcache_put("jfc", key, res)
    return res


# ----------------------------------------------------------------------------
# 英文 P1：PolitiFact 站內搜尋（Google Claim Search 補不上的老查核）
# 背景：2011 年 PolitiFact 頁無 ClaimReview 標記 → Google 索引結構性缺失，
# 任何 query 寫法都召回不到（virginia 案實測）。站內搜尋是服務端渲染，
# 結果卡（div.py-4.border-bottom）自帶 meter verdict（alt="False" 等）。
# ----------------------------------------------------------------------------
POLITIFACT_SEARCH = "https://politifact.com/search/"


def _parse_politifact_cards(html_text: str):
    """拆搜尋結果卡，回 [(claim, url, verdict_alt)]。"""
    cards = re.split(r'<div class="py-4 border-bottom">', html_text or "")
    out = []
    for c in cards[1:]:
        m = re.search(
            r'<a href="(https://politifact\.com/factchecks/[^"]+)"'
            r'[^>]*alt="([^"]+)"', c)
        if not m:
            m = re.search(
                r'<a href="(https://politifact\.com/factchecks/[^"]+)"[^>]*>\s*'
                r'([^<]{10,200})', c)
        v = re.search(r'meter-[a-z-]+\.jpg" alt="([^"]+)"', c)
        if m:
            claim = (m.group(2) or "").replace("&quot;", '"').strip()
            if claim and v:
                out.append((claim, m.group(1),
                            v.group(1).strip().rstrip("!")))
        if len(out) >= 6:
            break
    return out


def get_politifact(text: str, use_cache: bool = True,
                   timeout_api: int = 15) -> dict:
    if not text or len(text.strip()) < 10:
        return _empty("politifact")
    if _detect_lang(text) != "en":
        return _empty("politifact")
    snippet = text[:120]
    key = hashlib.sha1(("pf:" + snippet).encode("utf-8")).hexdigest()
    if use_cache:
        c = _mcache_get("politifact", key)
        if c:
            return c
    try:
        r = requests.get(POLITIFACT_SEARCH,
                         params={"q": _en_keywords(snippet) or snippet[:60]},
                         headers={"User-Agent": UA,
                                  "Accept-Language": "en-US,en;q=0.9"},
                         timeout=timeout_api)
        r.raise_for_status()
        cards = _parse_politifact_cards(r.text)
    except Exception as e:
        return {"source": "politifact", "status": "error",
                "feedback_count": 0, "created_at": None,
                "article_id": None, "matched_text": None, "url": None,
                "reasons": [], "note": f"爬蟲錯誤: {e}"}
    if not cards:
        res = _empty("politifact")
        _mcache_put("politifact", key, res)
        return res
    win = _sbert_gate(snippet,
                      [(None, t, u) for t, u, _v in cards])
    if not win:
        res = _empty("politifact")
        _mcache_put("politifact", key, res)
        return res
    _cid, top_title, top_url, win_sim = win
    verdict = next((v for t, u, v in cards if u == top_url), "")
    res = {"source": "politifact", "status": _map_google_rating(verdict),
           "feedback_count": len(cards), "created_at": None,
           "article_id": None, "matched_text": top_title[:120],
           "url": top_url, "similarity_score": win_sim,
           "reasons": [{"type": "POLITIFACT_METER",
                        "text": f"{verdict} — {top_title}" or top_url}]}
    _mcache_put("politifact", key, res)
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
    [cofacts, google, mygopen, rumtoast, hkbu, infact, jfc, politifact]。
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

    def _run_infact():
        try:
            return get_infact(text, use_cache=use_cache,
                              timeout_api=timeout_api)
        except Exception as e:
            return {**_empty("infact"), "status": "error", "note": str(e)}

    def _run_jfc():
        try:
            return get_jfc(text, use_cache=use_cache,
                           timeout_api=timeout_api)
        except Exception as e:
            return {**_empty("jfc"), "status": "error", "note": str(e)}

    def _run_politifact():
        try:
            return get_politifact(text, use_cache=use_cache,
                                  timeout_api=timeout_api)
        except Exception as e:
            return {**_empty("politifact"), "status": "error",
                    "note": str(e)}

    with _cf.ThreadPoolExecutor(max_workers=8) as _ex:
        _fu = [_ex.submit(_run_cofacts), _ex.submit(_run_google),
               _ex.submit(_run_mygopen), _ex.submit(_run_rumtoast),
               _ex.submit(_run_hkbu), _ex.submit(_run_infact),
               _ex.submit(_run_jfc), _ex.submit(_run_politifact)]
        results = [_f.result() for _f in _fu]
    return results


if __name__ == "__main__":
    import sys
    probe = sys.argv[1] if len(sys.argv) > 1 else "萊豬进口政府說明"
    out = get_all_fact_checks(probe)
    print(json.dumps(out, ensure_ascii=False, indent=2))
