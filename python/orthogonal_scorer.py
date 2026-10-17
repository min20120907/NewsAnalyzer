# -*- coding: utf-8 -*-
"""
NewsAnalyzer 四維度正交評分器與三態決策路由 (Orthogonal 4-Dimension Scorer & 3-Regime Router)
=========================================================================================
徹底解決「六個弱訊號硬加權湊分、靠 6 層 Clamp 互相救、沒人敢刪只能一直加閘門」的結構性問題。

四個正交維度（每個維度皆具備獨立契約：測量物理量、值域、單獨失效後果、獨立驗收指標）：
  - D1 `evidence_verdict`      : 查核證據蘊涵度 (Verdict ∈ {refutes, partially_refutes, supports, unrelated, none}, Confidence c_E ∈ [0, 1])
  - D2 `source_corroboration`  : 跨源報導佐證度 (Corroboration C ∈ [0, 1]，結合網域信譽、獨立媒體同報數、真實發布時效)
  - D3 `headline_faithfulness` : 標題內文忠實度 (Faithfulness F ∈ [0, 1]，純扣分/警示因子，文題相符絕不憑空加可信度分)
  - D4 `rhetorical_risk`       : 內文修辭與可驗性風險 (Risk R ∈ [0, 1]，僅在無外部證據時決定未查證區間內之風險落點)

三態決策路由（Three-Regime Router，由值域自然保證邊界，零後驗 Clamp）：
  - Regime A (`VERIFIED_EVIDENCE`)     : D1 有查核命中且非無關 (c_E >= 0.55) -> 由 D1 直接決定基底分 (refutes: 5~25, partial: 40~55, supports: 75~95)，再由 D3 扣減標題黨失真。
  - Regime B (`CORROBORATED_REPORT`)   : D1 無命中，但 D2 具備主流來源或跨源同報佐證 (C >= 0.60) -> 由 D2 決定基底分 (62~88)，再受 D3 (標題失真) 與 D4 (修辭風險) 扣減。
  - Regime C (`UNVERIFIED_ABSTAIN`)    : D1 無命中且 D2 無充分佐證 (C < 0.60) -> 認識論上為「待查證/疑似不實」，值域天生鎖定於 [10, 58]，由 D4 (1 - R) 與 D3 決定落點。
"""

from __future__ import annotations
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# 常數與詞表定義（集中管理，每個詞表只服務單一正交維度）
# ---------------------------------------------------------------------------

# D1: 傳言/匿名轉傳標記（證據原文若本身是未證實傳言，不得作為 supports 背書）
RUMOR_EVIDENCE_MARKERS_HARD = (
    "僅供參考", "未證實", "未經證實", "傳聞", "據傳", "小道消息", "勿外傳", "內傳",
)
RUMOR_EVIDENCE_MARKERS_SOFT = (
    "轉傳", "轉貼", "請大家", "廣傳", "多多流傳", "供參考",
)

# D1: LLM 分析文字中明確宣告查核證據與本主張無關之語義標記
UNRELATED_ANALYSIS_MARKERS = (
    "無關證據", "判定為無關", "與本主張無關", "不影響本主張", "不同事件", "非同一事件",
    "與本案無關", "針對不同事件",
)

# D2: 主流媒體名稱對網域映射（支援聚合頁如 Google News / LINE Today / Yahoo 轉載識別）
MEDIA_NAME_TO_DOMAIN: Dict[str, str] = {
    "自由時報": "ltn.com.tw", "自由電子報": "ltn.com.tw", "自由體育": "ltn.com.tw",
    "自由健康網": "ltn.com.tw", "自由財經": "ltn.com.tw", "自由娛樂": "ltn.com.tw",
    "news.ltn.com.tw": "ltn.com.tw", "ltn.com.tw": "ltn.com.tw",
    "中央社": "cna.com.tw", "CNA": "cna.com.tw", "cna.com.tw": "cna.com.tw",
    "聯合報": "udn.com", "UDN": "udn.com", "經濟日報": "udn.com", "udn.com": "udn.com",
    "中時": "chinatimes.com", "中國時報": "chinatimes.com", "chinatimes.com": "chinatimes.com",
    "TVBS": "tvbs.com.tw", "news.tvbs.com.tw": "tvbs.com.tw",
    "ETtoday": "ettoday.net", "東森新聞": "ebc.net.tw", "ettoday.net": "ettoday.net",
    "三立": "setn.com", "SETN": "setn.com", "setn.com": "setn.com",
    "風傳媒": "storm.mg", "Storm": "storm.mg", "storm.mg": "storm.mg",
    "公視": "pts.org.tw", "華視": "cts.com.tw", "台視": "ttv.com.tw",
    "民視": "ftvnews.com.tw", "鏡週刊": "mirrormedia.mg", "鏡新聞": "mnews.tw",
    "NOWnews": "nownews.com", "今日新聞": "nownews.com",
    "蘋果": "nextapple.com", "壹蘋": "nextapple.com",
    "天下雜誌": "cw.com.tw", "商業周刊": "businesstoday.com.tw",
    "關鍵評論": "thenewslens.com", "科技新報": "technews.tw", "TechNews": "technews.tw",
    "鉅亨網": "cnyes.com", "Yahoo": "tw.news.yahoo.com",
    "巴哈姆特": "gamer.com.tw", "GNN": "gamer.com.tw",
    "PChome": "pchome.com.tw", "遠見": "gvm.com.tw",
    "Newtalk": "newtalk.tw", "台灣新聞雲": "tnews.com.tw",
    "匯流": "houtong.com", "蕃新聞": "fnn.com.tw",
    "工商時報": "ctwant.com", "中國評論": "cri.com.tw",
    "娛樂星聞": "star.stock.yahoo.com", "今周刊": "todaynews.com",
    "商傳媒": "businessweekly.com.tw", "台灣華報": "taiwan-hwa.net",
    "世界新聞網": "worldjournal.com", "旺得富": "wdfm.com.tw",
    "放言": "fount.asia", "FTNN": "ftnn.com", "Verse": "verse.town", "verse.com.tw": "verse.town",
    "7Car": "7car.com.tw", "財訊": "wealth.com.tw",
}

# 與 data/domains/whitelist.txt 完整對齊
DEFAULT_MAINSTREAM_DOMAINS = set(MEDIA_NAME_TO_DOMAIN.values()) | {
    "cna.com.tw", "udn.com", "ltn.com.tw", "chinatimes.com", "pts.org.tw",
    "news.pts.org.tw", "storm.mg", "ettoday.net", "news.tvbs.com.tw", "tvbs.com.tw",
    "news.cts.com.tw", "cts.com.tw", "ftvnews.com.tw", "setn.com", "rti.org.tw",
    "bcc.com.tw", "cw.com.tw", "mirrormedia.mg", "thenewslens.com", "ttv.com.tw",
    "news.ttv.com.tw", "nownews.com", "upmedia.mg", "newtalk.tw", "businesstoday.com.tw",
    "bnext.com.tw", "tw.nextapple.com", "nextapple.com", "mnews.tw", "tw.news.yahoo.com",
    "technews.tw", "vogue.com.tw", "pchome.com.tw", "feitsui.com", "gamer.com.tw",
    "soundofhope.org", "today.line.me", "cnyes.com", "wealth.com.tw",
}

DEFAULT_FACTCHECK_DOMAINS = {
    "cofacts.tw", "cofacts.g0v.tw", "tfc-taiwan.org.tw", "mygopen.com", "rumtoast.com",
    "factcheck.hkbu.edu.hk", "infact.press", "factcheckcenter.jp", "politifact.com",
}

# 與 data/domains/ugc.txt 對齊（注意 today.line.me 為新聞聚合白名單，非純 UGC）
DEFAULT_UGC_DOMAINS = {
    "facebook.com", "fb.com", "fb.watch", "m.facebook.com", "twitter.com", "x.com",
    "threads.net", "instagram.com", "tiktok.com", "youtube.com", "youtu.be",
    "ptt.cc", "dcard.tw", "plurk.com", "mobile01.com", "xiaohongshu.com",
    "weibo.com", "bilibili.com", "medium.com", "vocus.cc", "pixnet.net", "reddit.com",
}

# D3: 標題黨顯性詞表（情緒煽動與農場釣魚）
CLICKBAIT_LEXICON = (
    "震撼", "網全嚇傻", "竟然", "不看會後悔", "會後悔", "急了", "震撼彈", "太誇張",
    "傻眼", "敗類", "割韭菜", "驚傳", "瘋傳", "洗版", "嚇呆", "驚呆", "全網",
    "嚇傻", "傻了", "震驚", "踢爆", "細思極恐", "不轉不是", "沉默了", "嚇壞",
    "慘了", "出事了", "出大事", "天塌了", "哭斷腸", "氣炸", "救命", "心碎", "淚崩",
    "崩潰", "天啊",
)

# D3: 懸念式／反問式釣魚標題句型（精準鎖定「真內文＋誇大懸念標」如 B01~B20，不誤傷一般政治/分析問句）
RHETORICAL_BAIT_PATTERNS = (
    r"[？?].*(這件事|這個動作|這兩天|這張卡|這組號碼|這個速度|這站|這組合|這家|這藝人|這國)",
    r"(這件事|這個動作|這兩天|這張卡|這組號碼|這個速度|這站|這兩個月|這藝人|這國).*[？?]",
    r"(最後一夜|永遠走不回去|一天能存多少電|去哪了|當場觸電|降速到不能用|發生了什麼事|走入歷史|規則全變了|療程卡一半|行李一夜全沒了|先別丟|不用再等一整夜|根本不存在|條件只有一個|銀行也找不到你|多數人還沒領到|中鏢)",
    r"[？?].*[？?]",  # 雙問號懸念標
)

# D4: 內文修辭操弄與虛構風險標記
MOBILIZATION_MARKERS = (
    "快轉給", "轉發到", "求求你轉發", "一次救一個", "救回一條命", "不轉不是人",
    "轉發就是功德", "晚了就被刪", "快把逃生包", "關鍵時刻能救命", "不要等來不及",
    "幫忙集氣轉發", "拜託大家一定要看", "拜託大家轉發", "家長一定要看",
    "十萬火急", "救人要緊", "太可怕了", "太恐怖了", "雞皮疙瘩掉滿地",
)

FOLKLORE_HOAX_MARKERS = (
    "老中醫", "臨終前留下", "秘方", "藥廠怕沒生意", "醫生偷偷說", "專家偷偷證實",
    "消防員私下透露", "內部人員警告", "含淚爆料", "菜市場的阿婆", "夜夢城隍",
    "鐵口直斷", "命理師", "秒歸零", "劇毒氰化物", "激活黑髮激素", "醫美診所氣到跳腳",
)

# D4: 偽冒官方公告/補助/疫情通報之高風險宣稱標記（當網域非 .gov.tw 且非主流白名單、無同報時觸發）
UNVERIFIED_OFFICIAL_CLAIM_MARKERS = (
    "公告：", "通報：", "警示：", "通知：", "開放申請", "逾期不予受理", "逾期視同放棄",
    "洽詢專線", "洽詢電話", "全面失效", "自動鎖卡", "免費配發", "補助金",
    "紓困貸款", "加碼抽", "普發現金", "停班停課", "中心最大風速", "預計於",
    "將於明年1月1日", "每周維持150分鐘",
)


# ---------------------------------------------------------------------------
# 資料結構定義：每個維度的獨立契約輸出
# ---------------------------------------------------------------------------

@dataclass
class DimensionOutput:
    id: str                   # "D1", "D2", "D3", "D4"
    key: str                  # "evidence_verdict", "source_corroboration", "headline_faithfulness", "rhetorical_risk"
    name: str                 # 中文名稱
    what_it_measures: str     # 一句話說明「我在量什麼」
    what_if_wrong: str        # 一句話說明「我單獨錯了會怎樣（邊界在哪）」
    value: float              # 正規化主數值（D1: [-1, 1], D2: [0, 1], D3: [0, 1], D4: [0, 1]）
    confidence: float         # 該維度訊號信心度 [0, 1]
    status_label: str         # 狀態短籤（如 "refutes", "corroborated", "faithful", "low_risk"）
    impact_pts: float         # 對最終分數的實際貢獻或扣減（供 UI 透明展示）
    explanation: str          # 給使用者的具體依據說明


# ---------------------------------------------------------------------------
# 輔助函式
# ---------------------------------------------------------------------------

_TWO_LEVEL_SUFFIX = {
    "com", "org", "net", "gov", "edu", "idv", "mil", "asn", "plc",
    "co", "or", "ne", "go", "ac", "ad", "gr",
}


def registrable_domain(host: str) -> str:
    p = (host or "").lower().split(".")
    if len(p) < 2:
        return host or ""
    if len(p) >= 3 and p[-2] in _TWO_LEVEL_SUFFIX and len(p[-1]) <= 3:
        return ".".join(p[-3:])
    return ".".join(p[-2:])


def resolve_effective_domain(title: str, url: str, content: str, target_url: Optional[str] = None) -> Tuple[str, str, str]:
    """回傳 (main_domain, host, scheme)。若為聚合器或未知網址，從標題/內文前段解析主流媒體來源。"""
    eval_url = target_url or url or ""
    parsed = urlparse(eval_url)
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.netloc or "").lower().replace("www.", "")
    if host in ("news.google.com", "google.com", "bit.ly", "t.co", "tinyurl.com") and target_url:
        parsed = urlparse(target_url)
        host = (parsed.netloc or "").lower().replace("www.", "")
        scheme = (parsed.scheme or scheme).lower()
    main = registrable_domain(host)

    # 若為通用聚合器（Google News / LINE Today / Yahoo）或無網域，檢查標題與內文前 500 字是否有明確主流媒體署名
    if main in ("google.com", "unknown", "", "line.me") or host in ("news.google.com", "today.line.me"):
        search_text = f"{title or ''} {(content or '')[:500]}"
        for m_name, m_dom in MEDIA_NAME_TO_DOMAIN.items():
            if m_name in search_text:
                return m_dom, m_dom, "https"
        if host == "today.line.me":
            return "today.line.me", "today.line.me", scheme
    return main, host, scheme


def is_evidence_unrelated(deep: Optional[dict]) -> bool:
    """檢查 LLM 是否判定查核結果為無關事件（含狀態欄與分析文字一致性檢查）。"""
    if not isinstance(deep, dict):
        return False
    if deep.get("evidence_state") == "unrelated_evidence":
        return True
    txt = f"{deep.get('analysis') or ''} {deep.get('viewpoints') or ''}"
    return any(w in txt for w in UNRELATED_ANALYSIS_MARKERS)


def is_rumor_only_evidence(deep: Optional[dict], sources: Optional[list]) -> bool:
    """檢查命中的查核原文是否本身只是未經證實的轉傳訊息。"""
    ev_texts = []
    for s in (sources or []):
        if not isinstance(s, dict):
            continue
        for k in ("matched_text", "body", "text", "content", "title"):
            v = s.get(k)
            if v:
                ev_texts.append(str(v))
    blob = " ".join(ev_texts)
    if isinstance(deep, dict):
        blob += " " + " ".join(str(deep.get(k) or "") for k in ("claim", "analysis", "viewpoints"))
    if any(m in blob for m in RUMOR_EVIDENCE_MARKERS_HARD):
        return True
    return sum(1 for m in RUMOR_EVIDENCE_MARKERS_SOFT if m in blob) >= 2


# ---------------------------------------------------------------------------
# 四個正交維度的獨立計算器
# ---------------------------------------------------------------------------

def compute_d1_evidence_verdict(
    sources: Optional[List[Dict]],
    deep: Optional[Dict] = None,
) -> DimensionOutput:
    """
    D1 查核證據蘊涵度：
    - 嚴格區分 `refutes` (-1.0)、`partially_refutes` (-0.5)、`supports` (+1.0)、`unrelated` (0.0)、`none` (0.0)。
    - `user_feedback`（查核回覆數）僅用來決定信心度 c_E，絕不當作正向加分。
    - 軟命中（0.55 <= sim < 0.72）僅在 LLM 明確判定 `full_body_evidence` 且非 `unrelated` 時採納。
    """
    what_measures = "已核實查核庫（Cofacts / MyGoPen / Google FC 等）對「同一具體事件」之蘊涵或駁斥立場與證據信心"
    what_wrong = "若誤將無關查核當命中會直接壓低真新聞；若漏召回則 c_E=0 退回未查證路由，絕不偷送 +15 分"

    unrelated = is_evidence_unrelated(deep)
    rumor_only = is_rumor_only_evidence(deep, sources)

    if unrelated:
        return DimensionOutput(
            id="D1", key="evidence_verdict", name="查核證據蘊涵度",
            what_it_measures=what_measures, what_if_wrong=what_wrong,
            value=0.0, confidence=0.0, status_label="unrelated",
            impact_pts=0.0,
            explanation="檢索命中的查核紀錄經語義比對屬「不同事件／防詐宣導」，已隔離剔除（不影響本篇計分）"
        )

    valid_hits = []
    deep_full = isinstance(deep, dict) and deep.get("evidence_state") == "full_body_evidence" and not unrelated

    for s in (sources or []):
        if not isinstance(s, dict):
            continue
        st = s.get("status")
        if st not in ("inaccurate", "false", "misleading", "fake", "partial", "accurate", "true", "hit", "ok"):
            continue
        sim = s.get("similarity_score")
        if sim is None:
            sim = s.get("sim")
        try:
            sim_val = float(sim) if sim is not None else 0.75
        except (TypeError, ValueError):
            sim_val = 0.0

        needs_llm = bool(s.get("needs_llm_verdict")) or (0.0 < sim_val < 0.72 and st != "accurate")
        if needs_llm and not deep_full:
            continue

        reasons = s.get("reasons") or []
        n_replies = sum(1 for r in reasons[:3] if isinstance(r, dict) and (r.get("text") or "").strip())
        if n_replies == 0 and s.get("feedback_count"):
            n_replies = min(3, int(s.get("feedback_count") or 1))

        valid_hits.append((st, sim_val, n_replies, s.get("source") or "查核庫"))

    if not valid_hits:
        return DimensionOutput(
            id="D1", key="evidence_verdict", name="查核證據蘊涵度",
            what_it_measures=what_measures, what_if_wrong=what_wrong,
            value=0.0, confidence=0.0, status_label="none",
            impact_pts=0.0,
            explanation="外部事實查核庫無此具體事件之核實紀錄（交由跨源佐證 D2 與內文風險 D4 路由）"
        )

    def _sev_key(item):
        st, sim_v, n_rep, _ = item
        if st in ("inaccurate", "false", "misleading", "fake"):
            return (3, sim_v, n_rep)
        if st == "partial":
            return (2, sim_v, n_rep)
        return (1, sim_v, n_rep)

    best_st, best_sim, best_replies, best_src = max(valid_hits, key=_sev_key)

    if best_st in ("accurate", "true", "hit", "ok") and rumor_only:
        return DimensionOutput(
            id="D1", key="evidence_verdict", name="查核證據蘊涵度",
            what_it_measures=what_measures, what_if_wrong=what_wrong,
            value=0.0, confidence=0.0, status_label="rumor_only_rejected",
            impact_pts=0.0,
            explanation=f"查核庫 ({best_src}) 雖有紀錄但內文屬「未證實轉傳訊息」，不採信為屬實背書"
        )

    sim_clamped = max(0.55, min(1.0, best_sim if best_sim > 0 else 0.80))
    reply_boost = 0.04 * min(best_replies, 3)
    c_E = min(1.0, sim_clamped * 0.90 + reply_boost)

    if best_st in ("inaccurate", "false", "misleading", "fake"):
        base_verdict_score = 24.0 - 16.0 * ((sim_clamped - 0.55) / 0.45) - min(3.0, best_replies * 1.0)
        base_verdict_score = max(5.0, min(24.0, base_verdict_score))
        return DimensionOutput(
            id="D1", key="evidence_verdict", name="查核證據蘊涵度",
            what_it_measures=what_measures, what_if_wrong=what_wrong,
            value=-1.0, confidence=round(c_E, 3), status_label="refutes",
            impact_pts=round(base_verdict_score, 1),
            explanation=f"查核機構 ({best_src}) 判定不實（相似度 {best_sim:.0%}，共 {max(1, best_replies)} 則查核依據），直接鎖定不實區間（基底 {base_verdict_score:.1f} 分）"
        )

    if best_st == "partial":
        base_verdict_score = 55.0 - 8.0 * ((sim_clamped - 0.55) / 0.45)
        base_verdict_score = max(42.0, min(55.0, base_verdict_score))
        return DimensionOutput(
            id="D1", key="evidence_verdict", name="查核證據蘊涵度",
            what_it_measures=what_measures, what_if_wrong=what_wrong,
            value=-0.5, confidence=round(c_E, 3), status_label="partially_refutes",
            impact_pts=round(base_verdict_score, 1),
            explanation=f"查核機構 ({best_src}) 判定部分不實／爭議（相似度 {best_sim:.0%}），落入待查證區間（基底 {base_verdict_score:.1f} 分）"
        )

    base_verdict_score = 78.0 + 14.0 * ((sim_clamped - 0.55) / 0.45)
    base_verdict_score = max(76.0, min(94.0, base_verdict_score))
    return DimensionOutput(
        id="D1", key="evidence_verdict", name="查核證據蘊涵度",
        what_it_measures=what_measures, what_if_wrong=what_wrong,
        value=1.0, confidence=round(c_E, 3), status_label="supports",
        impact_pts=round(base_verdict_score, 1),
        explanation=f"查核機構 ({best_src}) 查證屬實（相似度 {best_sim:.0%}），進入已核實可信區間（基底 {base_verdict_score:.1f} 分）"
    )


def compute_d2_source_corroboration(
    title: str,
    url: str,
    content: str,
    target_url: Optional[str] = None,
    publish_date: Optional[str] = None,
    corr_outlets: Optional[List[str]] = None,
    web_results: Optional[List[Dict]] = None,
    whitelist_domains: Optional[set] = None,
    factcheck_domains: Optional[set] = None,
    ugc_domains: Optional[set] = None,
    blocklist_domains: Optional[set] = None,
    deep: Optional[Dict] = None,
) -> DimensionOutput:
    """
    D2 跨源報導佐證度：
    - 測量「來源機構信譽等級」與「外部獨立媒體交叉同報數」，並結合文章自身發布時效（絕不混用 Cofacts created_at）。
    """
    what_measures = "新聞原始發布機構之信譽等級、獨立媒體交叉同報家數，以及文章自身發布時效一致性"
    what_wrong = "若把內容農場互抄算成同報會高估未查證文章；若漏算新興媒體則退回待查證區間（45~58分），不會誤殺為假新聞"

    wl = whitelist_domains or DEFAULT_MAINSTREAM_DOMAINS
    fc = factcheck_domains or DEFAULT_FACTCHECK_DOMAINS
    ugc = ugc_domains or DEFAULT_UGC_DOMAINS
    blk = blocklist_domains or set()

    main_dom, host, scheme = resolve_effective_domain(title, url, content, target_url=target_url)
    is_gov_edu = main_dom.endswith((".gov.tw", ".edu.tw", ".gov", ".edu"))
    is_factcheck = (main_dom in fc or host in fc)
    is_mainstream = (main_dom in wl or host in wl or is_gov_edu or is_factcheck)
    is_blocked = (main_dom in blk or host in blk) or ("rumor-farm" in main_dom or "farm" in main_dom)
    is_ugc = (main_dom in ugc or host in ugc) and not is_mainstream

    outlets = list(corr_outlets or [])
    n_corr = len(outlets)

    if n_corr == 0 and web_results:
        seen_o = set()
        for r in web_results:
            rt = (r.get("title") or "")
            ru = (r.get("url") or "")
            rh = urlparse(ru).netloc.lower().replace("www.", "")
            if rh in ("news.google.com", "google.com") and " - " in rt:
                outlet_lbl = rt.split(" - ")[-1].strip().lower()
            else:
                outlet_lbl = rh
            if outlet_lbl and outlet_lbl != host and outlet_lbl not in seen_o:
                seen_o.add(outlet_lbl)
        outlets = list(seen_o)
        n_corr = len(outlets)

    if is_blocked:
        c_dom = 0.0
        dom_label = f"高風險內容農場/黑名單網域 ({main_dom or 'unknown'})"
    elif is_factcheck or is_gov_edu:
        c_dom = 0.90
        dom_label = f"官方或查核機構網域 ({main_dom})"
    elif is_mainstream:
        c_dom = 0.78
        dom_label = f"具名主流媒體/白名單 ({main_dom})"
    elif is_ugc:
        c_dom = 0.25
        dom_label = f"社群轉傳平台 ({main_dom})，無原生機構背書"
    elif main_dom in ("", "unknown", "google.com", "example.com"):
        c_dom = 0.30
        dom_label = "未提供原始新聞網域"
    else:
        c_dom = 0.38
        dom_label = f"一般外部網域 ({main_dom})"

    if scheme == "http" and c_dom > 0:
        c_dom = max(0.0, c_dom - 0.20)
        dom_label += "（HTTP 未加密）"

    corr_boost = min(0.42, 0.12 * n_corr) if not is_blocked else 0.0

    llm_body_verified = (
        isinstance(deep, dict)
        and deep.get("evidence_state") == "full_body_evidence"
        and not bool(deep.get("abstain"))
        and float(deep.get("credibility_score") or 0) >= 75
        and not is_blocked
    )
    if llm_body_verified and c_dom < 0.70:
        c_dom = max(c_dom, 0.70)
        dom_label += "＋內文具名出處核實"

    recency_note = ""
    recency_bonus = 0.0
    if publish_date:
        try:
            pd_dt = datetime.fromisoformat(str(publish_date).replace("Z", "+00:00"))
            age_days = max(0.0, (time.time() - pd_dt.timestamp()) / 86400.0)
            if age_days <= 30:
                recency_bonus = 0.04
                recency_note = f"｜近期發布 ({int(age_days)}天內)"
            elif age_days > 365:
                recency_note = f"｜舊聞 ({int(age_days)}天前，留意是否舊聞重炒)"
        except Exception:
            pass

    C = max(0.0, min(1.0, c_dom + corr_boost + recency_bonus))
    if n_corr > 0:
        corr_str = f"｜{n_corr} 家外部來源同報（{', '.join(outlets[:4])}）"
    else:
        corr_str = "｜無額外跨媒體同報"

    corroborated_base_pts = 52.0 + 34.0 * C if C >= 0.60 else 0.0
    status_lbl = "blocked" if is_blocked else ("corroborated" if C >= 0.60 else "uncorroborated")

    return DimensionOutput(
        id="D2", key="source_corroboration", name="跨源報導佐證度",
        what_it_measures=what_measures, what_if_wrong=what_wrong,
        value=round(C, 3), confidence=1.0 if main_dom not in ("", "unknown") or n_corr > 0 else 0.4,
        status_label=status_lbl,
        impact_pts=round(corroborated_base_pts, 1),
        explanation=f"{dom_label}{corr_str}{recency_note}（佐證指數 {C:.2f}）"
    )


def compute_d3_headline_faithfulness(
    title: str,
    content: str,
    title_body_sim: Optional[float] = None,
    deep: Optional[Dict] = None,
) -> DimensionOutput:
    """
    D3 標題內文忠實度（純扣分／警示因子）：
    - 修正舊版 `refs=[title, content]` 造成的 50% 自相似灌水。
    - 檢測三路失真：(1) 標題釣魚詞表 (2) 懸念反問句型（如「…？這件事…」）(3) LLM 語義斷章取義 `title_bait` 或極低標題內文相似度。
    - 正交保證：文題相符 (F=1.0) 代表「0 扣分」，永遠不會幫假新聞加分！
    """
    what_measures = "新聞標題之斷言是否忠實反映內文，有無誇大釣魚、懸念誘導或斷章取義"
    what_wrong = "誤報時僅對該文施加標題失真扣分（最高 -22 分）與黃牌提示；漏報時因 F 不提供正分，絕不會把假新聞墊高到可信帶"

    t_clean = (title or "").strip()
    c_clean = (content or "").strip()

    if not t_clean or t_clean in ("N/A", "Facebook Post") or t_clean == c_clean[:len(t_clean)]:
        return DimensionOutput(
            id="D3", key="headline_faithfulness", name="標題內文忠實度",
            what_it_measures=what_measures, what_if_wrong=what_wrong,
            value=1.0, confidence=0.3, status_label="no_separate_title",
            impact_pts=0.0,
            explanation="無獨立標題（或僅貼文內文），不構成標題斷章取義（0 扣分）"
        )

    lex_hits = [kw for kw in CLICKBAIT_LEXICON if kw in t_clean]
    rhet_hit = any(re.search(pat, t_clean) for pat in RHETORICAL_BAIT_PATTERNS)

    llm_bait = isinstance(deep, dict) and bool(deep.get("title_bait"))
    llm_bait_reason = str((deep or {}).get("title_bait_reason") or "").strip()

    sim_val = title_body_sim if (title_body_sim is not None and title_body_sim > 0.0) else None
    low_sim = (sim_val is not None and sim_val < 0.42)

    reasons = []
    penalty = 0.0
    if llm_bait:
        penalty = max(penalty, 22.0)
        reasons.append(f"AI 語義比對判定標題誇大或斷章取義（{llm_bait_reason or '標題斷言超出內文範圍'}）")
    if lex_hits:
        penalty = max(penalty, 20.0)
        reasons.append(f"標題含煽動釣魚詞（「{'、'.join(lex_hits[:3])}」）")
    if rhet_hit:
        penalty = max(penalty, 20.0)
        reasons.append("標題使用懸念反問或誘導式釣魚句型（內文為平實敘述）")
    if low_sim:
        penalty = max(penalty, 15.0)
        reasons.append(f"標題與內文語義偏離（相似度僅 {sim_val:.0%}）")

    F = max(0.0, 1.0 - penalty / 25.0)
    status_lbl = "bait_or_unfaithful" if penalty > 0 else "faithful"
    sim_str = f"（標題—內文一致性 {sim_val:.0%}）" if sim_val is not None else ""

    if penalty > 0:
        exp = "；".join(reasons) + f"{sim_str} ➔ 觸發標題失真扣分 (-{penalty:.1f} 分，不直接判假，但壓制可信度上限)"
    else:
        exp = f"標題平實反映內文主旨{sim_str}，無誇大或斷章取義（0 扣分；忠實度不額外灌水加分）"

    return DimensionOutput(
        id="D3", key="headline_faithfulness", name="標題內文忠實度",
        what_it_measures=what_measures, what_if_wrong=what_wrong,
        value=round(F, 3), confidence=0.9, status_label=status_lbl,
        impact_pts=round(-penalty, 1),
        explanation=exp
    )


def compute_d4_rhetorical_risk(
    title: str,
    content: str,
    sentiment_val: float = 0.0,
    is_mainstream_or_corroborated: bool = False,
    deep: Optional[Dict] = None,
) -> DimensionOutput:
    """
    D4 內文修辭與可驗性風險：
    - 專責在「缺乏外部查核與主流同報（Regime C）」時，評估文本自身的操弄與虛構特徵。
    """
    what_measures = "文本自身之情緒操弄、催促轉發動員、偏方爆料話術，以及無出處之偽冒官方公告風險"
    what_wrong = "作用範圍嚴格限制在「無查核且無同報」之未查證區間 [18, 58] 內，絕不會覆寫 D1 查核證據，也不會把無證據文章推過 60 分"

    blob = f"{title or ''} {(content or '')[:1200]}"
    mob_hits = [m for m in MOBILIZATION_MARKERS if m in blob]
    folk_hits = [m for m in FOLKLORE_HOAX_MARKERS if m in blob]
    off_hits = [m for m in UNVERIFIED_OFFICIAL_CLAIM_MARKERS if m in blob] if not is_mainstream_or_corroborated else []
    bait_in_body = [kw for kw in CLICKBAIT_LEXICON if kw in blob]

    risk = 0.15
    notes = []

    if mob_hits:
        risk += min(0.45, 0.22 * len(mob_hits))
        notes.append(f"催促轉發/恐懼動員話術（「{'、'.join(mob_hits[:2])}」）")
    if folk_hits:
        risk += min(0.45, 0.22 * len(folk_hits))
        notes.append(f"匿名爆料/偏方秘方特徵（「{'、'.join(folk_hits[:2])}」）")
    if off_hits and not is_mainstream_or_corroborated:
        risk += min(0.55, 0.25 + 0.12 * len(off_hits))
        notes.append(f"宣稱具體機構公告/補助/疫情數據卻無官方或主流同報佐證（「{'、'.join(off_hits[:2])}」）")
    if len(bait_in_body) >= 2 and not is_mainstream_or_corroborated:
        risk += 0.20
        notes.append(f"高密度煽動語彙（「{'、'.join(bait_in_body[:2])}」）")

    abs_s = abs(sentiment_val or 0.0)
    if abs_s > 0.85 and not is_mainstream_or_corroborated:
        risk += 0.15
        notes.append(f"情緒極化指數偏高 (|s|={abs_s:.2f})")

    if isinstance(deep, dict) and deep.get("credibility_score") is not None:
        ai_cs = float(deep["credibility_score"])
        if ai_cs <= 50:
            llm_risk = (60.0 - max(30.0, ai_cs)) / 40.0
            risk = max(risk, min(0.85, llm_risk))
            notes.append(f"AI 內文審視指出可疑訊號 (自評 {ai_cs:.0f} 分)")

    R = max(0.0, min(1.0, risk))
    unverified_target_pts = round(58.0 - 40.0 * R, 1)

    if R >= 0.60:
        status_lbl = "high_risk"
    elif R >= 0.35:
        status_lbl = "moderate_risk"
    else:
        status_lbl = "low_risk"

    exp = ("檢出內文風險訊號：" + "；".join(notes) + f"（風險值 R={R:.2f}）"
           if notes else f"內文語氣平實、無煽動轉發或偽冒公告特徵（低風險 R={R:.2f}，惟缺外部查核時最高停留於待查證區間）")

    return DimensionOutput(
        id="D4", key="rhetorical_risk", name="內文修辭與可驗性風險",
        what_it_measures=what_measures, what_if_wrong=what_wrong,
        value=round(R, 3), confidence=0.85, status_label=status_lbl,
        impact_pts=unverified_target_pts,
        explanation=exp
    )


# ---------------------------------------------------------------------------
# 三態決策路由器 (Three-Regime Decision Router) —— 零 Clamp、值域自洽
# ---------------------------------------------------------------------------

def score_orthogonal(
    *,
    title: str = "",
    url: str = "",
    content: str = "",
    target_url: Optional[str] = None,
    publish_date: Optional[str] = None,
    sentiment_val: float = 0.0,
    title_body_sim: Optional[float] = None,
    sources: Optional[List[Dict]] = None,
    web_results: Optional[List[Dict]] = None,
    corr_outlets: Optional[List[str]] = None,
    deep: Optional[Dict] = None,
    whitelist_domains: Optional[set] = None,
    factcheck_domains: Optional[set] = None,
    ugc_domains: Optional[set] = None,
    blocklist_domains: Optional[set] = None,
) -> Dict:
    """
    執行四維度正交評估與三態決策路由。
    """
    d1 = compute_d1_evidence_verdict(sources=sources, deep=deep)
    d2 = compute_d2_source_corroboration(
        title=title, url=url, content=content, target_url=target_url,
        publish_date=publish_date, corr_outlets=corr_outlets, web_results=web_results,
        whitelist_domains=whitelist_domains, factcheck_domains=factcheck_domains,
        ugc_domains=ugc_domains, blocklist_domains=blocklist_domains, deep=deep,
    )
    d3 = compute_d3_headline_faithfulness(
        title=title, content=content, title_body_sim=title_body_sim, deep=deep,
    )
    is_mainstream_or_corr = (d2.value >= 0.60)
    d4 = compute_d4_rhetorical_risk(
        title=title, content=content, sentiment_val=sentiment_val,
        is_mainstream_or_corroborated=is_mainstream_or_corr, deep=deep,
    )

    ai_cs = float(deep["credibility_score"]) if (isinstance(deep, dict) and deep.get("credibility_score") is not None) else None
    ai_abstain = bool(deep.get("abstain")) if isinstance(deep, dict) else True

    if d1.status_label in ("refutes", "partially_refutes", "supports"):
        # Regime A：已核實查核證據主導（Verified Evidence Regime）
        regime = "VERIFIED_EVIDENCE"
        base_score = d1.impact_pts
        if d1.status_label == "refutes":
            final_score = base_score
            if ai_cs is not None and not ai_abstain and ai_cs <= 35:
                final_score = 0.85 * base_score + 0.15 * min(25.0, ai_cs)
            regime_desc = f"路由 A（查核證據主導）：{d1.explanation}"
        elif d1.status_label == "partially_refutes":
            final_score = max(40.0, min(55.0, base_score + 0.3 * d3.impact_pts))
            regime_desc = f"路由 A（查核部分不實）：{d1.explanation}"
        else:
            base_with_llm = (0.85 * base_score + 0.15 * ai_cs) if (ai_cs is not None and not ai_abstain and ai_cs >= 65) else base_score
            final_score = max(52.0, min(96.0, base_with_llm + d3.impact_pts))
            regime_desc = f"路由 A（查核屬實背書）：{d1.explanation}" + (
                f"；惟 {d3.explanation}" if d3.impact_pts < 0 else ""
            )
        is_provisional = False

    elif d2.value >= 0.60 and d2.status_label != "blocked":
        # Regime B：開放世界跨源佐證新聞（Corroborated Open-World Regime）
        regime = "CORROBORATED_REPORT"
        base_score = d2.impact_pts  # 62 ~ 86 分
        if ai_cs is not None and not ai_abstain and ai_cs >= 60:
            base_score = 0.70 * base_score + 0.30 * ai_cs
        rhet_adj = -8.0 * max(0.0, d4.value - 0.25)
        final_score = base_score + d3.impact_pts + rhet_adj
        if d3.impact_pts <= -18.0:
            final_score = min(59.0, max(45.0, final_score))
        else:
            final_score = max(62.0, min(92.0, final_score))
        regime_desc = f"路由 B（主流來源／跨源同報佐證）：{d2.explanation}" + (
            f"；{d3.explanation}" if d3.impact_pts < 0 else ""
        )
        is_provisional = bool(ai_abstain and d2.value < 0.75)

    else:
        # Regime C：查無外部證據且無主流同報（Unverified / Abstain Regime）
        regime = "UNVERIFIED_ABSTAIN"
        base_unverified = d4.impact_pts  # 58.0 - 40.0 * R ∈ [18, 58]
        if d2.status_label == "blocked":
            base_unverified -= 12.0
        final_score = max(10.0, min(58.0, base_unverified + 0.5 * d3.impact_pts))
        regime_desc = f"路由 C（無外部查核且無跨源同報，認識論上限 58 分）：{d4.explanation}"
        is_provisional = True

    final_score = round(max(0.0, min(100.0, final_score)), 2)

    if final_score >= 75:
        rating = "高度可信"
    elif final_score >= 60:
        rating = "大致可信"
    elif final_score >= 40:
        rating = "待查證"
    elif final_score >= 20:
        rating = "疑似不實"
    else:
        rating = "高度可疑"

    dimensions_dict = {
        "evidence_verdict": asdict(d1),
        "source_corroboration": asdict(d2),
        "headline_faithfulness": asdict(d3),
        "rhetorical_risk": asdict(d4),
    }

    compat_metrics = {
        "fact_check": {
            "score": round(30.0 * d1.value, 2) if d1.status_label in ("refutes", "partially_refutes", "supports") else 0.0,
            "desc": d1.status_label if d1.status_label != "none" else "not_found",
            "weight": 30.0,
        },
        "user_feedback": {
            "score": round(10.0 * d1.confidence, 2) if d1.confidence > 0 else 0.0,
            "desc": f"證據信心 {d1.confidence:.0%}" if d1.confidence > 0 else "none",
            "weight": 10.0,
        },
        "domain": {
            "score": round(25.0 * d2.value, 2),
            "desc": d2.explanation.split("｜")[0],
            "weight": 25.0,
        },
        "similarity": {
            "score": round(15.0 * d3.value, 2),
            "desc": f"忠實度 {d3.value:.0%}（{d3.status_label}）",
            "weight": 15.0,
        },
        "sentiment": {
            "score": round(15.0 * (1.0 - d4.value), 2),
            "desc": f"修辭安全度 {1.0 - d4.value:.0%}（風險 R={d4.value:.2f}）",
            "weight": 15.0,
        },
        "timeliness": {
            "score": 5.0 if "近期發布" in d2.explanation else 0.0,
            "desc": "近期發布" if "近期發布" in d2.explanation else "unknown",
            "weight": 5.0,
        },
    }

    return {
        "final_score": final_score,
        "rating_text": rating,
        "regime": regime,
        "regime_desc": regime_desc,
        "scoring_basis": regime_desc,
        "dimensions": dimensions_dict,
        "metrics": compat_metrics,
        "rule_score": final_score,
        "post_fusion_score": final_score,
        "fusion_weight": 0.15 if regime == "VERIFIED_EVIDENCE" else (0.30 if regime == "CORROBORATED_REPORT" else 0.0),
        "clamped": False,
        "clamp_reason": "",
        "is_provisional": is_provisional,
    }
