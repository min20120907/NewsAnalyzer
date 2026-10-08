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
# 2026-10-01：召回下界。COFACTS_MIN_SIM 仍是「硬命中」線（clamp 只認它），
# 低於這條才真的 not_found。中間那段交給 LLM rerank 裁決。
# 2026-10-05：召回下限從 0.45 提高到 0.55。
# 理由：0.45 帶進太多同主題但不同事件的東西（檸檬水 0.518、空腹水果 0.648 都是噪音），
# 用戶說「常給不相干的」就是這裡。0.55 砍掉低相關，只留真正相關的查核。
# 同謠言家族實測 0.68+，0.55 不會砍掉真命中。
COFACTS_SOFT_MIN_SIM = float(os.environ.get("COFACTS_SOFT_MIN_SIM", "0.55"))
# 交叉確認：Top-N 候選一起給 LLM 讀（同家族謠言的不同角度查核）。
COFACTS_TOP_K = int(os.environ.get("COFACTS_TOP_K", "4"))
# 只帶與 Top-1 差距小於此值的候選（家族內）。0.15 只排除明顯掉隊者。
COFACTS_FAMILY_DELTA = float(os.environ.get("COFACTS_FAMILY_DELTA", "0.15"))

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
    # 2026-10-01：只保留 3 字變體。2 字版（何醫／許多／簡訊）幾乎全是從動詞、
    # 形容詞切出來的假實體。去噪交給 _strong_entities 的虛詞字判準，這裡只做形狀過濾。
    for i in range(len(text) - 1):
        if text[i] in SURNAMES:
            if i + 3 <= len(text):
                sub = text[i:i + 3]
                if re.match(r'^[一-鿿]+$', sub):
                    entities.add(sub)
    # 2. 政治/社會熱門專有名詞
    key_terms = ['青鳥', '館長', '台積電', '高虹安', '柯建銘', '莊競程', '徐欣瑩']
    for term in key_terms:
        if term in text:
            entities.add(term)
    return entities


def _strong_entities(text: str) -> set:
    """高置信實體。

    2026-10-01：改用「詞典命中」而非「姓氏比對 + 數量」。姓氏比對必然產噪音
    （何+醫學、許+多癌），而任何去噪規則都會漏——實測「任何醫學證據」＋
    「任何醫學研究」讓「何醫學」出現兩次，重複法也被騙過。黑名單只會無限追。
    改判準：3 字候選必須**不含常用虛詞字**（醫/多/新/大/小/老/好/真/全…），
    那是人名不會用的字；真名如「陳惠仁」「沈伯洋」「范振宗」不含這類字。
    """
    VIRTUAL = set("醫多新大小老好真全前後本該個些們等再又更沒不很最第來西")
    # ponytail: 來/西只為擋「馬來西(亞)」地名噪音；若未來真人名含此二字，改走逐名白名單
    ents = extract_entities(text)
    known = {'青鳥', '館長', '台積電', '高虹安', '柯建銘', '莊競程', '徐欣瑩'}
    return {e for e in ents
            if e in known or (len(e) == 3 and not (set(e) & VIRTUAL))}


def entity_gatekeeper(query_text: str, candidate_text: str) -> bool:
    """實體門控 (Entity Gatekeeper)：
    如果查詢文本包含明確特定人名/實體，但候選文章完全未包含任何對應實體，
    且包含其他衝突人名，則判定門控不通過 (False)。

    2026-10-01：判「真實體」用重複出現而非字典長度。純姓氏比對必然有噪音
    ——「任何醫學證據」會切出「何醫學」、「許多癌患者」切出「許多癌」，
    單數量門檻擋不住（實測兩者同時出現 → 誤判主題衝突 → 真檸檬水查核被丟）。
    真人名在正文通常出現 2 次以上，噪音詞只出現一次。
    """
    q_ents = _strong_entities(query_text[:300])
    if not q_ents:
        return True  # 查詢無明確強實體，放行給 SBERT 判定
    
    c_ents = extract_entities(candidate_text[:400])
    overlap = q_ents.intersection(c_ents)
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


def _is_bare_url(text: str) -> bool:
    """文章內文若只是純連結（無實質中文），相似度比對須改用回覆內文，否則 SBERT 必死（實測 URL vs 新聞 = -0.05）。"""
    import re as _re
    t = (text or "").strip()
    if len(t) > 120:
        return False
    nospace = _re.sub(r"\s+", "", t)
    if not (nospace.startswith("http://") or nospace.startswith("https://")):
        return False
    rest = _re.sub(r"https?://\S+", "", t)
    cjk = sum(1 for ch in rest if "\u4e00" <= ch <= "\u9fff")
    return cjk < 10


_HEDGE_ONLY = ("無從判斷", "無法判斷", "查不到", "未載明", "不完整",
               "沒有附上", "無從確認", "不確定", "請點開", "點開連結")


def _is_hedge_only(text: str) -> bool:
    """Cofacts 的 NOT_ARTICLE 回覆若只是說「我無從判斷」，就不算一次查核。

    2026-10-01 regression：實測「小笠原欣辛拜會新北市長」（正當選情新聞）命中
    一篇 matched_text 只有「資料來源：中時新聞網 + Google 轉址」的文章，回覆明說
    「無從判斷真假」卻被判 accurate → 87.99 高度可信。舊邏輯只看字數 >=15 就放行。
    """
    return any(n in text for n in _HEDGE_ONLY)


def _classify_candidate(node) -> "dict | None":
    """從 GraphQL node 解析查核結構。"""
    replies = node.get("articleReplies") or []
    has_false = has_true = has_opinion = False
    has_verified_link = False  # NOT_ARTICLE 但回覆內含實質查證（如：新聞連結＋確認活動存在）
    total_fb = 0
    reasons = []
    for ar in replies:
        total_fb += int(ar.get("feedbackCount") or 0)
        rtype = (ar.get("reply") or {}).get("type", "").upper()
        rtext = (ar.get("reply") or {}).get("text") or ""
        if rtype in ("FALSE", "RUMOR", "TRUE", "NOT_RUMOR", "OPINIONATED", "NOT_ARTICLE"):
            if rtext.strip():
                # NOT_ARTICLE 的「無從判斷」型回覆不是判定，不進 reasons——
                # 否則 reasons 非空會讓後面的 `if not reasons: return None` 閘門放行。
                if rtype != "NOT_ARTICLE" or not _is_hedge_only(rtext):
                    reasons.append({"type": rtype, "text": rtext.strip()[:200]})
        if rtype in ("FALSE", "RUMOR"):
            has_false = True
        elif rtype in ("TRUE", "NOT_RUMOR"):
            has_true = True
        elif rtype == "OPINIONATED":
            has_opinion = True
        elif rtype == "NOT_ARTICLE":
            # 2026-10-01：NOT_ARTICLE 有兩種，必須分開：
            #  a) 機構真的查了 → 「這則內容雖非事實查核對象，但已確認 X 存在」→ accurate。
            #  b) 機構只是說「這是轉發連結／沒寫主張，我無從判斷」→ **不算任何判定**。
            # 見 _is_hedge_only 的 regression 說明。
            if len(rtext.strip()) >= 15 and not _is_hedge_only(rtext):
                has_verified_link = True
    if has_false:
        status = "inaccurate"
    elif has_true:
        status = "accurate"
    elif has_opinion:
        status = "partial"
    elif has_verified_link:
        status = "accurate"
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
    # 2026-10-01：無回覆＝查核機構沒給任何理由，那篇只是「貼了內容、沒人查」。
    # 帶 status 進下游會讓 fact_check=-30 並觸發 clamp，實測兩則主流媒體新聞因此被鎖死
    # 19～25 分（命中一篇 Telegram 社群公告垃圾文／一頁式廣告詐騙文）。
    if not reasons:
        return None
    raw_text = node.get("text") or ""
    if _is_bare_url(raw_text) and reasons:
        # 純連結文：用最長的回覆內文當比對文本（內文本體是 URL，SBERT 無法比）
        matched = max((r.get("text") or "" for r in reasons), key=len)
    else:
        matched = raw_text[:200]
    return {"status": status, "feedback_count": total_fb,
            "created_at": created_at, "article_id": article_id,
            "matched_text": matched[:200],
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
            # 2026-10-01：無回覆的語料不構成查核判定。seed 早期寫進 corpus 時 reasons
            # 幾乎全空（實測 2469 筆有 2468 筆是空），帶著 inaccurate 進下游會讓
            # fact_check=-30 鎖死真新聞。過濾掉，讓它們退回 not_found。
            if not reasons:
                continue
            m_text = (row[4] or "")[:200]
            # 2026-10-01：實體門控也要擋這條路徑。GraphQL 那條（get_fact_check
            # 第 527 行）有擋，本地近鄲沒有 → 主動門控形同虛設。
            # 實測「藍優先法案列普發2萬 王婉諭批評」命中 corpus 裡「香蕉鳳梨謠言
            # 國民黨道歉」（NOT_RUMOR → accurate），兩者只共用「國民黨」就過了，
            # 拿到 89.61 高度可信。
            if m_text and not entity_gatekeeper(query, m_text):
                continue
            results.append({
                "status": row[0], "feedback_count": row[1],
                "created_at": row[2], "article_id": row[3],
                "matched_text": m_text, "sim": sim,
                "url": f"https://cofacts.tw/article/{row[3]}" if row[3] else None,
                "reasons": reasons
            })
    con.close()
    return results


def _recall_queries(snippet: str) -> list:
    """moreLikeThis 召回的多查詢備援：整段 snippet 常回 0 筆（標題太長太具體），
    退回首句 / 去標點壓縮關鍵字再查（實例：機車抽獎案整句 0 筆，短查 2-4 筆）。"""
    import re as _re
    qs = []
    s1 = snippet.split("。")[0].strip()
    if s1 and len(s1) >= 8 and s1 != snippet.strip():
        qs.append(s1[:100])
    compact = _re.sub(r"[，。、；：『』「」！？!?,.\s]", "", snippet)
    if len(compact) >= 12:
        qs.append(compact[:60])
    return qs[:2]


def _keyword_queries(snippet: str) -> list:
    """jieba 關鍵字查詢（最後備援）：回傳多個**各自獨立**的短查詢詞。

    2026-10-01（實測對照，同一則檸檬水查核）：
      '檸檬水' → 8 usable    '治癌' → 7    '癌症' → 6
      '檸檬水 癌症' → 6      '檸檬水 治癌' → 1
      '檸檬水 癌症 治癌' → 1  '檸檬水治癌' → 0  ← 詞一多/一長就失配
    moreLikeThis 對短輸入最敏感、對多詞 AND 語義最脆弱，所以逐詞各打一次再合併，
    而不是拼成一個查詢。取最長的 5 個（實體詞訊息量最高，「水能」這種黏邊
    殘渣長度短會自然排後面）。lazy 載入 jieba，失敗回 []。
    """
    try:
        import jieba as _jieba
        _STOP = {"推出", "符合", "資格", "表示", "指出", "認為", "今天", "昨天",
                 "今年", "記者", "報導", "中央社", "綜合", "開跑", "大獎",
                 "活動", "事項", "相關", "進行", "造成", "導致", "呼籲", "強調"}
        toks, seen = [], set()
        for t in _jieba.cut(snippet[:200]):
            t = t.strip()
            if len(t) < 2 or len(t) > 6 or t in seen:
                continue
            if not any("一" <= ch <= "鿿" for ch in t):
                continue
            if t in _STOP:
                continue
            seen.add(t)
            toks.append(t)
        toks.sort(key=len, reverse=True)
        return toks[:5]
    except Exception:
        return []


def _graphql_recall(snippet: str, timeout_api: int) -> list:
    """主查＋短查＋jieba 關鍵字備援，合併去重（by id），最多 8 個 node。

    2026-10-01：每個 query 各自只收 2 筆（原本第一個 query 就能塞滿 8 筆上限，
    後續短查與關鍵詞備援全被跳過）。實測檸檬水案：長句主查撈到 8 筆無關
    （沙拉油／台糖／蘋果藥殘）就收手，沒去查「檸檬水」這個真詞，而單獨查
    「檸檬水」有 8 usable。moreLikeThis 對短輸入敏感，合併召回要靠多樣本，
    靠單一長句撈滿是錯的。"""
    seen, nodes = set(), []
    queries = [snippet] + _recall_queries(snippet)
    try:
        for q in queries:
            if len(nodes) >= 16:
                break
            before = len(nodes)
            r = requests.post(COFACTS_API_URL, json={
                "query": _GRAPHQL, "variables": {
                    "filter": {"moreLikeThis": {"like": q}}}},
                headers={"User-Agent": UA, "Content-Type": "application/json"},
                timeout=timeout_api + 5)
            if r.status_code != 200:
                continue
            data = r.json()
            edges = (data.get("data") or {}).get("ListArticles", {}).get("edges") or []
            for edge in edges:
                node = edge.get("node") or {}
                nid = node.get("id")
                if nid and nid not in seen:
                    seen.add(nid)
                    nodes.append(node)
                if len(nodes) - before >= 2:
                    break
    except Exception:
        pass
    # 2026-10-01：條件從「召回筆數」改成「有實質回覆的筆數」。原本用 len(nodes)<N，
    # 但長句主查常撈滿 8 筆無關文章（實測檸檬水案撈到沙拉油／台糖／蘋果藥殘），
    # 讓「筆數夠」的條件成立，關鍵詞備援整段被跳過。改用 _classify_candidate 有回覆
    # 者計數才對——沒有回覆的文章本來就會被丟掉，佔著額度沒意義。
    _usable = sum(1 for nd in nodes
                  if any((r.get("reply") or {}).get("text", "").strip()
                         for r in (nd.get("articleReplies") or [])))
    if _usable < 3:
        # 最後備援：jieba 關鍵字查詢（lazy，只在前面撈不到時觸發）
        try:
            for kq in filter(None, _keyword_queries(snippet)):
                before_k = len(nodes)
                r = requests.post(COFACTS_API_URL, json={
                    "query": _GRAPHQL, "variables": {
                        "filter": {"moreLikeThis": {"like": kq}}}},
                    headers={"User-Agent": UA, "Content-Type": "application/json"},
                    timeout=timeout_api + 5)
                if r.status_code != 200:
                    continue
                data = r.json()
                edges = (data.get("data") or {}).get("ListArticles", {}).get("edges") or []
                for edge in edges:
                    node = edge.get("node") or {}
                    nid = node.get("id")
                    if not nid or nid in seen:
                        continue
                    # 有實質回覆才收（與 _usable 同一判準）——沒回覆的文章
                    # 進來也會被 _classify_candidate 丟掉，只是佔額度
                    if not any((rp.get("reply") or {}).get("text", "").strip()
                               for rp in (node.get("articleReplies") or [])):
                        continue
                    seen.add(nid)
                    nodes.append(node)
                    if len(nodes) - before_k >= 2:
                        break
        except Exception:
            pass
    return nodes


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
        # 2026-09-24：舊快取列若無 similarity_score（舊版寫入），命中時強制重算，
        # 否則錨定/prompt 會把高信心命中當「未知」
        if c and c.get("status") != "not_found" and "similarity_score" not in c:
            c = None
        if c:
            return c

    candidates = []

    # 1. 階段一召回：Cofacts GraphQL API（主查＋短查備援合併）
    for node in _graphql_recall(snippet, timeout_api):
        c = _classify_candidate(node)
        if c:
            candidates.append(c)

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

    # 2026-10-01：交叉確認。Top-1 只是同主題家族裡相似度最高的那筆，單靠它裁決會
    # 錯過同家族其他角度的查核（檸檬水 →「空腹吃水果勝癌症」sim 0.648 排第一，
    # 真正的🍋 檸檬水查核 sim 0.518 排第五）。回傳 Top-N 讓 LLM 一次看完。
    # 只帶與 Top-1 差距小的（家族內），不帶掉出很遠的——實測柚子配優酪奶 sim 0.595
    # 跟檸檬水毫無關係，只是池子裡碰巧排在前面。
    # ponytail: N=4、相對落差 0.15。pool 內整體落差中位 0.037，0.15 只排除明顯掉隊者。
    _fam = sorted(
        (c for c in candidates if c.get("matched_text")
         and (c.get("similarity_score") or 0) >= COFACTS_SOFT_MIN_SIM),
        key=lambda c: -(c.get("similarity_score") or 0))
    topn = [c for c in _fam[:COFACTS_TOP_K]
            if (c.get("similarity_score") or 0) >= best_sim - COFACTS_FAMILY_DELTA]

    if best_candidate and best_sim >= COFACTS_SOFT_MIN_SIM:
        best_candidate["similarity_score"] = best_sim
        best_candidate["needs_llm_verdict"] = best_sim < COFACTS_MIN_SIM
        # 交叉確認：把同池其餘候選的原文一併給下游 LLM。它已經能看到 Top-1 的
        # reasons，這幾筆是同一段 fc_lines 裡的額外證據，零額外網路請求。
        best_candidate["alternatives"] = [
            {"status": c.get("status"), "url": c.get("url"),
             "similarity_score": c.get("similarity_score"),
             "reasons": (c.get("reasons") or [])[:2],
             "matched_text": (c.get("matched_text") or "")[:300]}
            for c in topn if c is not best_candidate]
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
