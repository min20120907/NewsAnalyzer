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
import threading
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
query FactCheck($filter: ListArticleFilter, $first: Int) {
  ListArticles(filter: $filter, first: $first) {
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

# 2026-10-18：moreLikeThis 召回分檔參數。
# 病徵：正確條目「明明存在」卻回 not_found。實測（R01-R20）主因是預設
# minimumShouldMatch 過嚴＋只收前幾筆：同主題噪音排在正確條目之前，
# 正確條目常落在 idx 8-12（如 R03 sim 0.908 在 idx=10），被 per-query 上限切掉。
# 對策：同一個 query 用三檔 msm 各查一次（msm 放寬＝召回池變大，正確條目才進得來），
#       同時把 first 放大到 25。三檔排名不同、互補，不是單純重複查詢。
_RECALL_PASSES = (("10%", 25), ("20%", 15), ("30%", 10))
# 單次召回的節點總量上限（含各檔 msm 與備援查詢）。50 筆 node 的文字量約 250KB、
# 下游門控是純 CPU，超量只是白做；真正的正確條目在最上面各檔就已進來。
_RECALL_MAX_NODES = 40
# 召回總時間預算（秒）。多檔 msm 讓請求數變多，遇到 Cloudflare 403/timeout 時
# 舊碼會一路重試（實測單筆 worst case 37-47s，把 /judge 的延遲預算吃光）。
# 逾時就用手上已有的節點往下走——召回是機會主義，不該綁住整個請求。
_RECALL_BUDGET_S = float(os.environ.get("COFACTS_RECALL_BUDGET", "25"))

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
    # 2026-10-16：只信出現≥2 次的實體。單次出現的多半是切詞噪音（「路段將在」→
    # 「段將在」），拿它判主題衝突會丟掉 sim 0.81 的真命中。短查詢無重複實體就
    # 放行，後面還有關鍵詞門控＋SBERT 雙保險。
    q_ents = {e for e in q_ents if query_text.count(e) >= 2}
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
                          "matched_text,reasons,ts FROM cache WHERE key=?",
                          (key,)).fetchone()
        con.close()
        if row:
            # 2026-10-18：ts 欄位原本寫了卻沒人讀 → 快取永不過期（同 multifc_cache，
            # 見 factcheck_multi._cache_ttl 的說明）。判定類長存、空結果短存。
            _st = row[0]
            _neg = _st in (None, "", "not_found", "unrelated", "error", "disabled")
            _ttl = float(os.environ.get("COFACTS_CACHE_TTL_NEG", "21600") if _neg
                         else os.environ.get("COFACTS_CACHE_TTL", "604800"))
            if os.environ.get("COFACTS_CACHE_DISABLE", "") == "1":
                _ttl = 0.0
            if _ttl <= 0 or (time.time() - float(row[6] or 0.0)) > _ttl:
                return None
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


_SBERT_WARNED = False


def _warn_sbert_missing() -> None:
    """SBERT 不可用只警告一次（否則每個候選印一行，log 會被洗掉）。"""
    global _SBERT_WARNED
    if _SBERT_WARNED:
        return
    _SBERT_WARNED = True
    print("[cofacts_local] WARN: SBERT 不可用（模型未載入/未注入），"
          "候選改用門控下限分並標記待 LLM 裁決 —— 請檢查 sentence-transformers "
          "是否裝在當前 interpreter（server 用 .venv/bin/python）", flush=True)


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


def _pick_sim_text(status: str, raw_text: str, reasons: list) -> str:
    """決定 SBERT 要拿哪段文字跟查詢比對（2026-10-18）。

    病徵：查核明明有對應條目，卻因「比錯文本」而 sim 偏低 → not_found 或判錯。
    三種文本各有語域：
      raw_text（轉傳原文）＝謠言本體，口語轉傳語域；
      reply（查核回覆）＝查核員寫的正式說明；反駁型（RUMOR/OPINIONATED）
        會整篇在講「這是錯的／正確的是…」，跟新聞本體語域不同。
    規則：
      inaccurate / partial → 比 raw_text（新聞若在傳同一則謠言，文字最接近謠言本體）；
      accurate（NOT_RUMOR/TRUE）→ 比回覆文（回覆才是「正確版本」的正式重述，
        實測明潭案對轉傳文 0.527、對回覆文 0.926）；
      純連結文（raw_text 只有 URL）→ 只能比回覆文，否則 SBERT 必死。
    對應的門控仍一律用 gate_text（事件本體），不受此影響。
    """
    best = max(((r.get("text") or "") for r in (reasons or [])), key=len, default="")
    if _is_bare_url(raw_text):
        return (best or raw_text or "")[:200]
    if status == "accurate" and len(best) >= 20:
        return best[:200]
    return (raw_text or best or "")[:200]


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
    # 2026-10-16：比對文本優先用最長的查核回覆原文（查核員正式重述事件），
    # 轉傳原文多半是口語粉專文，改寫查詢（正式語域）對它 sim 系統性偏低
    # （明潭案：對轉傳文 0.527、對回覆文 0.926）。短回覆(<20字)無事件資訊，
    #  fallback 回轉傳原文。
    _best_reply = max((r.get("text") or "" for r in reasons), key=len, default="")
    if len(_best_reply) >= 20:
        matched = _best_reply[:200]
    elif _is_bare_url(raw_text) and reasons:
        # 純連結文：用最長的回覆內文當比對文本（內文本體是 URL，SBERT 無法比）
        matched = max((r.get("text") or "" for r in reasons), key=len)
    else:
        matched = raw_text[:200]
    return {"status": status, "feedback_count": total_fb,
            "created_at": created_at, "article_id": article_id,
            "matched_text": matched[:200],
            # 2026-10-18：SBERT 比對文本（依 status 選謠言原文或回覆文，見 _pick_sim_text）。
            # matched_text 保持原義（最長回覆優先）供下游顯示；sim_text 才是比對用。
            "sim_text": _pick_sim_text(status, raw_text, reasons),
            # 2026-10-16：門控專用文本＝轉傳原文（事件本體）。matched 已換成
            # 查核回覆文（語域匹配用），拿它跑門控會放行同領域不同事件。
            "gate_text": raw_text[:400],
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
            _sim_text = _pick_sim_text(row[0], row[4] or "", reasons)
            # 2026-10-01：實體門控也要擋這條路徑。GraphQL 那條（get_fact_check
            # 第 527 行）有擋，本地近鄲沒有 → 主動門控形同虛設。
            # 實測「藍優先法案列普發2萬 王婉諭批評」命中 corpus 裡「香蕉鳳梨謠言
            # 國民黨道歉」（NOT_RUMOR → accurate），兩者只共用「國民黨」就過了，
            # 拿到 89.61 高度可信。
            # 2026-10-16：本地路徑同步加關鍵詞交集門控（同上）。
            # 2026-10-18：兩道門控都比「原文＋狀態感知文本」兩份，同一份文本三層全過
            # 才算過（_gate_pass；per-text AND，見該函式 docstring）。
            _gts = _gate_texts({"gate_text": row[4] or "", "sim_text": _sim_text,
                                "matched_text": m_text})
            if _gts and not _gate_pass(query, _gts):
                continue
            results.append({
                "status": row[0], "feedback_count": row[1],
                "created_at": row[2], "article_id": row[3],
                "matched_text": m_text, "sim": sim,
                # 2026-10-18：與 GraphQL 路徑同一套文本選擇（見 _pick_sim_text），
                # 否則兩條召回路徑對同一篇文章會給出不同的 sim。
                "gate_text": (row[4] or "")[:400],
                "sim_text": _sim_text,
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


def _keywords(snippet: str, limit: int = 200) -> list:
    """jieba 切關鍵詞（2-6 字實體詞，去停用詞），最長的排前面。失敗回 []。

    limit：只取前 N 字做切詞（預設 200，維持既有查詢產生行為不變）。
    門控用 limit=1200 —— 查核文章的事件本體常出現在開場白之後（實例 R04：正確條目
    開頭是「500cc 的瓶裝水一罐賣 120 元？…米其林餐廳…」，國防部／戰備／飲用水
    在更後面），只切前 200 字等於看不到事件本體。
    """
    try:
        import jieba as _jieba
        _STOP = {"推出", "符合", "資格", "表示", "指出", "認為", "今天", "昨天",
                 "今年", "記者", "報導", "中央社", "綜合", "開跑", "大獎",
                 "活動", "事項", "相關", "進行", "造成", "導致", "呼籲", "強調"}
        toks, seen = [], set()
        for t in _jieba.cut(snippet[:limit] if limit else snippet):
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
        return toks
    except Exception:
        return []


def _keyword_overlap_gate(query_text: str, candidate_text: str, min_overlap: int = 1,
                          q_limit: int = 500, c_limit: int = 1200) -> bool:
    """關鍵詞交集門控（補實體門控只看人名的缺口）。

    無人名查詢門控全放行，同領域不同事件（GEO投毒 vs AI詐騙話術 sim 0.76、
    特斯拉自燃 vs 9V電池 sim 0.56）一路殺到 LLM 還判 full。
    實體詞交集 < min_overlap 直接丟，SBERT 都不跑。
    """
    # ponytail: 只看 3 字以上詞＋交集≥1（calib_gate.py 4 組全對）。
    # 2 字通用詞（推薦/模型/電池）到處都是會誤放；要精確就看 ROC 挑。
    # 2026-10-18：視窗放大（q 500 / c 1200 字）。原本 300/400 只看到開場白，
    # 正確條目常在更後面才講到事件本體 → 假 not_found（見 _keywords 的 R04 實例）。
    q = {w for w in _keywords(query_text, limit=q_limit) if len(w) >= 3}
    if not q:
        return True
    c = {w for w in _keywords(candidate_text, limit=c_limit) if len(w) >= 3}
    return len(q & c) >= min_overlap


_NUM_QTY_UNITS = ("萬元", "億元", "萬人", "萬", "億", "元", "%", "％", "折", "歲",
                  "人次", "人", "名", "家", "倍", "度", "點", "瓶", "箱", "包",
                  "小時", "分鐘", "秒", "公里", "公尺", "公分", "公斤", "公克",
                  "cc", "CC", "期", "名額", "級")
# 日期指紋（年/月/日）可選納入：同一事件的新聞與謠言有時寫不同日期
# （「10月31日」vs「10月底」），拿日期當交集條件會把真命中一起擋掉，
# 所以預設不納入，由 mode 決定（見 _numeric_gate 的 *d 模式）。
_NUM_DATE_UNITS = ("日", "號", "月", "年")
# 不用日期當指紋（預設）。
_NUM_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(" + "|".join(
        re.escape(u) for u in sorted(_NUM_QTY_UNITS + _NUM_DATE_UNITS,
                                     key=len, reverse=True)) + r")")


def _normalize_numerals(text: str) -> str:
    """全形數字轉半形、去千分位（1,200→1200、6,000元→6000元）。

    2026-10-18 修：原用 (?<=\d),(?=\d{3}\\b) 判斷千分位——Python 的 \\b 認 CJK 為
    word char，所以「6,000元」的「000」後面接「元」時 \\b 不成立 → 逗號留著 →
    指紋變成「6,000元」對不上查詢的「6000元」→ 數字閘門把 0.87 的正確命中擋掉
    （實測 R06 廢電池：查核回覆文寫 6,000元、新聞寫 6000元，被 strictd 誤擋）。
    改用 (?=\d{3}(?!\d))：只看「後面是不是剛好三位數字」，不管後面接什麼字。
    """
    t = text or ""
    t = t.translate(str.maketrans("０１２３４５６７８９％", "0123456789%"))
    return re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)


def _numeric_tokens(text: str, include_dates: bool = False) -> set:
    """事件指紋：抽出「數字＋量詞單位」對（1200元/0.5%/20萬/1800點…）。

    include_dates=True 時一併納入日期指紋（10月31日/2026年）。用途見 _numeric_gate。
    純字串處理、無網路無模型，成本可忽略。
    """
    t = _normalize_numerals(text or "")
    out = set()
    for m in _NUM_RE.finditer(t):
        unit = m.group(2)
        if not include_dates and unit in _NUM_DATE_UNITS:
            continue
        num = m.group(1).rstrip(".")
        out.add(f"{num}{unit}")
    return out


def _numeric_gate(query_text: str, candidate_text: str, mode: str = None) -> bool:
    """數字指紋閘門：兩個「同領域不同事件」的文本，用字往往相同、數字不會相同。

    背景（2026-10-18 實測）：放寬 moreLikeThis 召回後，正確條目回來了，但同領域
    不同事件的老查核也一起回來，而且能撞上 0.72 硬命中線——實例（皆為捏造新聞）：
      F12「台電節電獎勵2.0 每期800元」撞 2018 年「每度0.6元、每期84元」的 NOT_RUMOR
      F17「健保卡10月底全面換發、逾期鎖卡」撞「健保卡遺失毀損可到郵局補發」的 NOT_RUMOR
    兩者共同點：領域詞（台電/節電/健保卡）相同、關鍵數字全不同。實體門控與關鍵詞
    交集都只看詞，擋不住；數字指紋是這類假命中最直接的判準。

    mode（預設讀 COFACTS_NUM_GATE；未設＝strictd）：
      off      ：不擋（舊行為，供離線對照）
      soft     ：查詢有 >=2 個數字指紋、且候選也有 >=1 個時，必須至少交集 1 個
                 （候選完全沒數字者放行，避免擋掉純文字敘述的查核）
      strict   ：查詢有 >=2 個數字指紋時，候選必須至少交集 1 個
      softd/strictd：同上，但指紋含日期（10月31日 這種）
    預設 strictd 是實測選出來的（scripts/eval_numeric_gate.py，60 筆離線矩陣）：
      raw/off   REAL 11、FAKE 硬命中 2（未過閘門就自動採信）
      union/off REAL 13、FAKE 硬命中 3
      union/strictd REAL 13、FAKE 硬命中 0  ← 取這個
    也就是：把「捏造新聞被查核判屬實且直接採信」這條最危險的路徑收乾淨，
    代價是少數假新聞也不再被查核判不實（改走其他維度）。
    """
    m = (mode or os.environ.get("COFACTS_NUM_GATE", "strictd") or "strictd").lower()
    if m == "off":
        return True
    d = m.endswith("d")
    q = _numeric_tokens(query_text, include_dates=d)
    if len(q) < 2:
        return True
    c = _numeric_tokens(candidate_text, include_dates=d)
    if not c:
        return not m.startswith("strict")
    return bool(q & c)


def _gate_texts(cand: dict) -> list:
    """門控要比對的文本集合（去重保序）。

    2026-10-18：原本只比 gate_text（轉傳原文）。實測 R04（國防部戰備飲用水）正確條目
    就在池子裡（accurate，120元/650萬/8億元都在），卻因轉傳原文只是口語開場
    「500cc 的瓶裝水一罐賣 120 元？你可能會以為這是米其林餐廳的氣泡水…」而跟新聞
    （國防部採購案）沒有 3 字詞交集 → 門控直接擋掉，SBERT 從沒跑過。
    查核回覆文是查核員對同一事件的正式重述，語域與關鍵詞都貼近新聞，本來就該拿來
    當第二個門控文本；語域不符的風險由數字指紋閘門（_numeric_gate）承擔。
    """
    out = []
    for t in (cand.get("gate_text") or "", cand.get("sim_text") or "",
              cand.get("matched_text") or ""):
        if t and t not in out:
            out.append(t)
    return out


def _gate_pass(snippet: str, texts: list) -> bool:
    """三層門控：實體 ∧ 關鍵詞 ∧ 數字指紋，**同一份文本**全過才算過；任一文本過即放行。

    2026-10-18 修（語意 bug，實測）：舊碼是三層各自 any(文本)——
      any(entity) and any(kw) and any(num)
    只要「轉傳原文」過關鍵詞、「查核回覆文」過數字，就整體放行。F12 實測：
    raw 過關鍵詞（台電/節電獎勵）、回覆文過數字（12月/31日）→ 2018 年舊查核
    （0.6元/84元）被判與 2026 捏造文（800元/50元）同事件，sim 0.763 硬命中直接採信。
    改成 per-text AND 後，離線矩陣（scripts/eval_numeric_gate.py，60 筆）
    union/strictd：REAL 命中 13、FAKE 硬命中 0（見 _numeric_gate docstring）。
    """
    for gt in texts:
        if not gt:
            continue
        if (entity_gatekeeper(snippet, gt)
                and _keyword_overlap_gate(snippet, gt)
                and _numeric_gate(snippet, gt)):
            return True
    return False


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
    return _keywords(snippet)[:5]


def _post_graphql(filter_obj: dict, timeout_api: int, first: int = None):
    """GraphQL POST 交會點：403/429/5xx 或壞 JSON 就退避重試兩次。

    2026-10-16：連打會吃 Cloudflare 間歇 403，舊碼非 200 直接 continue，
    備援請求被靜默丟掉 → 召回池縮水 → not_found 假結果。成功路徑零成本。
    2026-10-18：加 first 參數（ListArticles(first: N)）。moreLikeThis 的預設回傳
    筆數太少，正確條目常排在同主題噪音之後，只有放大 first 才撈得到。
    """
    # ponytail: 固定退避 1s/3s，不是 exponential——Cofacts 限流是短窗口，夠用就好。
    variables: dict = {"filter": filter_obj}
    if first:
        variables["first"] = int(first)
    payload = {"query": _GRAPHQL, "variables": variables}
    headers = {"User-Agent": UA, "Content-Type": "application/json"}
    _dbg = os.environ.get("COFACTS_DEBUG", "") == "1"
    _t0 = time.time()
    for wait in (0, 1, 3):
        if wait:
            time.sleep(wait)
        try:
            r = requests.post(COFACTS_API_URL, json=payload,
                              headers=headers, timeout=timeout_api + 5)
            if r.status_code != 200:
                if _dbg:
                    print(f"[cofacts] gql HTTP {r.status_code} "
                          f"({time.time() - _t0:.1f}s) like={str(filter_obj)[:60]}",
                          flush=True)
                continue
            data = r.json()
            if (data.get("data") or {}).get("ListArticles") is None:
                if _dbg:
                    print(f"[cofacts] gql no-data ({time.time() - _t0:.1f}s) "
                          f"like={str(filter_obj)[:60]}", flush=True)
                continue
            if _dbg:
                _n = len((data.get("data") or {}).get("ListArticles", {}).get("edges") or [])
                print(f"[cofacts] gql ok {_n} edges in {time.time() - _t0:.2f}s "
                      f"like={str(filter_obj)[:60]}", flush=True)
            return data
        except Exception as _e:
            if _dbg:
                print(f"[cofacts] gql EXC {type(_e).__name__} "
                      f"({time.time() - _t0:.1f}s) like={str(filter_obj)[:60]}", flush=True)
            continue
    return None


def _graphql_recall(snippet: str, timeout_api: int) -> list:
    """多檔 msm 主查＋短查＋jieba 關鍵字備援，合併去重（by id），最多 _RECALL_MAX_NODES 個 node。

    2026-10-01：每個備援 query 各自只收 2 筆（原本第一個 query 就能塞滿 8 筆上限，
    後續短查與關鍵詞備援全被跳過）。moreLikeThis 對短輸入敏感，合併召回要靠多樣本。
    2026-10-18：主查改三檔 minimumShouldMatch（見 _RECALL_PASSES）。舊碼單一主查
    （預設 msm）＋每 query 收 2 筆，正確條目若排在同主題噪音之後就永遠進不了池子
    ——60 筆評測 R03-R20 幾乎全滅的主因。主查各檔不再限 2 筆（排名深度就是重點），
    短查與關鍵詞備援仍限 2 筆（維持多樣性、避免單一 query 洗榜）。
    """
    seen, nodes = set(), []

    def _collect(edges, limit: int = 0, require_reply: bool = False) -> int:
        """收 node；limit>0 時本 query 最多收 limit 筆。回傳本 query 實際新增數。"""
        added = 0
        for edge in edges:
            if len(nodes) >= _RECALL_MAX_NODES:
                break
            node = edge.get("node") or {}
            nid = node.get("id")
            if not nid or nid in seen:
                continue
            if require_reply and not any(
                    (rp.get("reply") or {}).get("text", "").strip()
                    for rp in (node.get("articleReplies") or [])):
                # 沒有回覆的文章不構成查核判定（_classify_candidate 會丟），
                # 進來只是佔額度
                continue
            seen.add(nid)
            nodes.append(node)
            added += 1
            if limit and added >= limit:
                break
        return added

    _t_start = time.time()
    _fails = 0

    def _budget_ok() -> bool:
        # 兩次連續失敗（Cloudflare 403／timeout）就放棄剩下的查詢：再打也是白打，
        # 而且會把 /judge 的延遲預算吃光。單次成功即歸零（允許偶發失敗）。
        return _fails < 2 and (time.time() - _t_start) < _RECALL_BUDGET_S

    try:
        # 主查：同一 snippet、三檔 msm（廣→窄），各檔取回自己的排名前 N 筆
        for _msm, _first in _RECALL_PASSES:
            if len(nodes) >= _RECALL_MAX_NODES or not _budget_ok():
                break
            data = _post_graphql(
                {"moreLikeThis": {"like": snippet, "minimumShouldMatch": _msm}},
                timeout_api, first=_first)
            if not data:
                _fails += 1
                continue
            _fails = 0
            _collect(((data.get("data") or {}).get("ListArticles", {}).get("edges") or []))
        # 短查備援（首句／去標點壓縮）
        for q in _recall_queries(snippet):
            if len(nodes) >= _RECALL_MAX_NODES or not _budget_ok():
                break
            data = _post_graphql(
                {"moreLikeThis": {"like": q, "minimumShouldMatch": "20%"}},
                timeout_api, first=15)
            if not data:
                _fails += 1
                continue
            _fails = 0
            _collect(((data.get("data") or {}).get("ListArticles", {}).get("edges") or []),
                     limit=2)
    except Exception:
        pass
    # 2026-10-01：條件從「召回筆數」改成「有實質回覆的筆數」。原本用 len(nodes)<N，
    # 但長句主查常撈滿 8 筆無關文章（實測檸檬水案撈到沙拉油／台糖／蘋果藥殘），
    # 讓「筆數夠」的條件成立，關鍵詞備援整段被跳過。改用 _classify_candidate 有回覆
    # 者計數才對——沒有回覆的文章本來就會被丟掉，佔著額度沒意義。
    _usable = sum(1 for nd in nodes
                  if any((r.get("reply") or {}).get("text", "").strip()
                         for r in (nd.get("articleReplies") or [])))
    # 2026-10-16：改寫查詢撈到的 usable 常是別的文章（同主題噪音），真文排不上，
    # usable>=3 讓關鍵詞備援整段被跳過 → 改寫後召回率 40%。實體詞不受改寫影響，
    # 前 2 個最長關鍵詞總是跑（+2 請求約 +1s），剩下的仍只在 usable<3 跑。
    _kws = [k for k in filter(None, _keyword_queries(snippet))]
    _must = _kws[:2] if _usable >= 3 else _kws
    if _must:
        # 最後備援：jieba 關鍵字查詢（lazy，只在前面撈不到時觸發）
        try:
            for kq in _must:
                if len(nodes) >= _RECALL_MAX_NODES or not _budget_ok():
                    break
                data = _post_graphql(
                    {"moreLikeThis": {"like": kq, "minimumShouldMatch": "30%"}},
                    timeout_api, first=10)
                if not data:
                    _fails += 1
                    continue
                _fails = 0
                _collect(((data.get("data") or {}).get("ListArticles", {}).get("edges") or []),
                         limit=2, require_reply=True)
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
        
        # 第一重：實體＋關鍵詞＋數字指紋門控，同一份文本三層全過才算過；比對文本見
        # _gate_texts（轉傳原文＋狀態感知回覆文），任一文本過即放行（_gate_pass）。
        _gts = _gate_texts(cand) or [m_text]
        if not _gate_pass(snippet, _gts):
            continue

        # 第二重：SBERT 精準相似度計算（比對文本見 _pick_sim_text）
        s_text = cand.get("sim_text") or cand.get("gate_text") or m_text
        sim = _sbert_sim(snippet, s_text)
        if sim is None:
            # SBERT 不可用（模型載入失敗／未注入）。舊碼這裡直接吃 cand.get("sim", 0.0)
            # → 所有候選 0 分 → 永遠 not_found：查核庫明明有資料卻系統性回「查不到」，
            # 而且沒有任何跡象。改成：門控已過的候選給保守下限分並標記待 LLM 裁決，
            # 同時把「SBERT 掛了」明確印出來（一次性）。
            _warn_sbert_missing()
            sim = cand.get("sim", 0.0)
            if not sim and COFACTS_SOFT_MIN_SIM:
                # 沒模型時 sim 形同未知；用召回相似度或門檻下緣墊底，交給下游 LLM 判
                sim = max(float(cand.get("sim") or 0.0), COFACTS_SOFT_MIN_SIM)

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
_SBERT_LOCK = threading.Lock()
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
        with _SBERT_LOCK:
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
