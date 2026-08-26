# -*- coding: utf-8 -*-
"""
Fake‑News Reliability Engine – RTX 4090 Parallel (完整版)
========================================================
• **真正計算六大指標**
  0 sentiment   — HF pipeline (CUDA)
  1 domain      — 台灣主流/HTTPS 判斷
  2 fact_check  — Cofacts API (GraphQL)
  3 user_feedback — 可接真實 DB；預設 None → skip
  4 similarity  — SBERT 與標題/語料參考文本餘弦
  5 timeliness  — newspaper3k 發布日計分
• 沒資料 → `weight = 0` → 不影響分母，`metric_scores = 0.5`（中立）
• 提供 `analyze_article_data()` 與 GPU batch `analyze_batch_article_data()`
"""
###############################################################################
# 0. Imports & global models                                                 #
###############################################################################
import os, math, warnings, datetime, json
from typing import List, Dict, Optional
from collections import defaultdict

import torch, requests
from transformers import pipeline
from sentence_transformers import SentenceTransformer, util
from newspaper import Article
from urllib.parse import urlparse

device_str = "cuda" if torch.cuda.is_available() else "cpu"
TORCH_FP16 = torch.cuda.is_available()
if TORCH_FP16:
    torch.set_float32_matmul_precision("high")

# ---------------- Sentiment -------------------------------------------------
SENTIMENT_PIPELINE = pipeline(
    "text-classification",
    model="distilbert-base-multilingual-cased-sentiments-student",
    device=0 if device_str == "cuda" else -1,
    batch_size=64,
)

# ---------------- Similarity ------------------------------------------------
SIMILARITY_MODEL = SentenceTransformer(
    "paraphrase-multilingual-MiniLM-L12-v2", device=device_str
)

###############################################################################
# 1. Config, weights, helper tables                                          #
###############################################################################
TAIWAN_MAINSTREAM = {
    "cna.com.tw",
    "udn.com",
    "ltn.com.tw",
    "chinatimes.com",
    "ettoday.net",
}

DEFAULT_W = {
    "sentiment": 15.0,
    "domain": 25.0,
    "fact_check": 30.0,
    "feedback": 10.0,
    "similarity": 15.0,
    "timeliness": 5.0,
}

# Cofacts --------------------------------------------------------------------
COFACTS_API = "https://cofacts-api.g0v.tw/graphql"
CO_Q = """query($text:String!){GetArticle(title:$text){replyCount,replyConnections{reply{type}}}}"""

###############################################################################
# 2. Heavy batch helpers                                                     #
###############################################################################

def _sentiment_batch(texts: List[str]) -> List[float]:
    """signed sentiment −1..1"""
    if not texts:
        return []
    with torch.autocast(device_str, enabled=TORCH_FP16):
        outs = SENTIMENT_PIPELINE(texts, truncation=True, max_length=512)
    vals: List[float] = []
    for o in outs:
        lab, sc = o["label"].lower(), o["score"]
        vals.append(sc if lab.endswith("positive") else -sc if lab.endswith("negative") else 0.0)
    return vals

def _similarity_list(contents: List[str], refs: List[str]):
    if not refs:
        return [0.0] * len(contents)
    with torch.autocast(device_str, enabled=TORCH_FP16):
        ref_emb = SIMILARITY_MODEL.encode(refs, convert_to_tensor=True, batch_size=len(refs))
        emb = SIMILARITY_MODEL.encode(contents, convert_to_tensor=True, batch_size=len(contents))
        return util.cos_sim(emb, ref_emb).mean(dim=1).clamp(0, 1).tolist()

# Fact‑check single ----------------------------------------------------------

def _cofacts_status(text: str) -> Optional[str]:
    if not text or len(text) < 20:
        return None
    try:
        payload = {"query": CO_Q, "variables": {"text": text[:200]}}
        r = requests.post(COFACTS_API, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        conns = data.get("data", {}).get("GetArticle", {}).get("replyConnections", [])
        types = [c["reply"]["type"].upper() for c in conns if c.get("reply")]
        if any(t in ["FALSE", "RUMOR"] for t in types):
            return "inaccurate"
        if any(t in ["TRUE", "NOT_RUMOR"] for t in types):
            return "accurate"
        if any(t == "OPINIONATED" for t in types):
            return "partial"
    except Exception:
        pass
    return None

# Timeliness single ----------------------------------------------------------

def _publish_days(url: str) -> Optional[int]:
    try:
        art = Article(url=url, language="zh")
        art.download(); art.parse()
        if art.publish_date:
            dt = art.publish_date
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return max(0, (datetime.datetime.now() - dt).days)
    except Exception:
        pass
    return None

###############################################################################
# 3. Core single scoring                                                     #
###############################################################################

def _score_single(title: str, url: str, content: str, refs: List[str]) -> Dict:
    res: Dict = {}
    total = 0.0
    avail = 0.0  # active weights

    # 0  Sentiment -----------------------------------------------------------
    s_val = _sentiment_batch([content])[0]
    abs_s = abs(s_val)
    pts = DEFAULT_W["sentiment"] if abs_s <= 0.4 else 5.0 if abs_s < 0.8 else -DEFAULT_W["sentiment"]
    total += pts; avail += DEFAULT_W["sentiment"]
    res["sentiment"] = {"score": pts, "desc": f"{s_val:.2f}", "weight": DEFAULT_W["sentiment"]}

    # 1  Domain --------------------------------------------------------------
    host = urlparse(url).netloc.replace("www.", "").lower()
    if not host:
        dom_w = 0.0; dom_pts = 0.0; desc = "unknown"
    else:
        dom_w = DEFAULT_W["domain"]
        desc = host
        if host in TAIWAN_MAINSTREAM:
            dom_pts = dom_w
        elif urlparse(url).scheme == "https":
            dom_pts = 15.0
        else:
            dom_pts = -5.0
        total += dom_pts; avail += dom_w
    res["domain"] = {"score": dom_pts, "desc": desc, "weight": dom_w}

    # 2  Fact‑check ----------------------------------------------------------
    fc_status = _cofacts_status(content)
    fc_w = DEFAULT_W["fact_check"] if fc_status else 0.0
    fc_pts = 0.0
    if fc_status:
        if fc_status == "accurate":
            fc_pts = fc_w
        elif fc_status == "partial":
            fc_pts = fc_w / 2
        elif fc_status == "inaccurate":
            fc_pts = -fc_w
        total += fc_pts; avail += fc_w
    res["fact_check"] = {"score": fc_pts, "desc": fc_status or "not_checked", "weight": fc_w}

    # 3  User feedback -------------------------------------------------------
    fb_score = None  # integrate DB later
    fb_w = DEFAULT_W["feedback"] if fb_score is not None else 0.0
    fb_pts = 0.0
    if fb_score is not None:
        fb_pts = fb_score * fb_w
        total += fb_pts; avail += fb_w
    res["user_feedback"] = {"score": fb_pts, "desc": fb_score or "none", "weight": fb_w}

    # 4  Similarity ----------------------------------------------------------
    sim_val = _similarity_list([content], refs)[0]
    sim_w = DEFAULT_W["similarity"]
    sim_pts = sim_val * sim_w
    total += sim_pts; avail += sim_w
    res["similarity"] = {"score": sim_pts, "desc": f"{sim_val:.2%}", "weight": sim_w}

    # 5  Timeliness ----------------------------------------------------------
    days = _publish_days(url)
    time_w = DEFAULT_W["timeliness"] if days is not None else 0.0
    time_pts = 0.0
    if days is not None:
        time_pts = max(0.0, time_w - 0.5 * max(0, days - 1))
        total += time_pts; avail += time_w
    res["timeliness"] = {"score": time_pts, "desc": f"{days} days" if days is not None else "unknown", "weight": time_w}

    # ---------- Final -------------------------------------------------------
    final = (total / avail) * 100 if avail else 0.0
    rating = "相對可靠" if final >= 70 else "可靠度中等" if final >= 50 else "可靠度較低"

    metric_scores = []
    for k in ["sentiment", "domain", "fact_check", "user_feedback", "similarity", "timeliness"]:
        w = res[k]["weight"]
        if w == 0:
            metric_scores.append(0.5)
        else:
            metric_scores.append(max(0.0, min(1.0, (res[k]["score"] + w) / (2 * w))))

    return {**res, "metric_scores": metric_scores, "final_score": final, "rating_text": rating}

###############################################################################
# 4. Batch                                                                   #
###############################################################################

def analyze_batch_article_data(titles: List[str], urls: List[str], contents: List[str], batch_size: int = 64):
    if not (len(titles) == len(urls) == len(contents)):
        raise ValueError("Lengths mismatch")
    refs_all = titles or []

    sims_all = _similarity_list(contents, refs_all)
    sents_all = _sentiment_batch(contents)

    outs = []
    for i in range(len(contents)):
        res = _score_single(titles[i], urls[i], contents[i], refs_all)
        res["sentiment"]["desc"] = f"{sents_all[i]:.2f}"
        res["similarity"]["desc"] = f"{sims_all[i]:.2%}"
        outs.append(res)
    return outs

###############################################################################
# 5. Convenience single wrapper                                              #
###############################################################################

def analyze_article_data(title: str = "", url: str = "", content: str = ""):
    if not content:
        raise ValueError("content required")
    return _score_single(title or "N/A", url or "https://unknown", content, [title, content])

