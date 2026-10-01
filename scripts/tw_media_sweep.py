#!/usr/bin/env python3
"""抓台灣主流媒體今日新聞跑 /judge，找可疑評分。

Google News RSS 每類別前 N 筆 → POST /judge → 存 jsonl。
Usage: python3 scripts/tw_media_sweep.py [per_cat] [categories...]
"""
import json, sys, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET

JUDGE = "http://127.0.0.1:5000/judge"
OUT = "data/eval/tw_media_sweep.jsonl"
CATS = {
    "tw": "台灣", "biz": "台灣 經濟", "tech": "台灣 科技",
    "soc": "台灣 社會", "pol": "台灣 政治", "world": "台灣 國際",
}
# 白名單網域（照 data/domains/whitelist.txt 的策展口徑）
DOMAINS = ["cna.com.tw", "udn.com", "ltn.com.tw", "chinatimes.com", "pts.org.tw",
           "ettoday.net", "tvbs.com.tw", "cts.com.tw", "ftvnews.com.tw", "setn.com",
           "mirrormedia.mg", "thenewslens.com", "ttv.com.tw", "nownews.com", "newtalk.tw"]


def fetch(cat_key, q, n):
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote_plus(q)
           + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hans")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    out = []
    for it in root.iterfind(".//item"):
        t = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        # 2026-10-01：<source url> 才是真媒體網域；<link> 是 news.google.com 轉址。
        # 送轉址給 /judge 會讓 domain 指標全部吃預設分（實測 48 則裡 22 則 domain
        # <25，CNA/自由時報/UDN 這些白名單媒體跟假新聞站拿一樣分）。
        src_el = it.find("source")
        real = (src_el.get("url") or "").strip() if src_el is not None else ""
        src = t.rsplit("|", 1)[-1].strip() if "|" in t else ""
        if any(d.split(".")[0] in src.lower() or src.lower() in d for d in DOMAINS):
            out.append({"title": t, "url": real or link, "cat": cat_key,
                        "outlet": src, "rss_link": link})
        if len(out) >= n:
            break
    return out


def judge(item):
    body = json.dumps({"title": item["title"], "url": item["url"],
                       "postText": ""}).encode()
    req = urllib.request.Request(
        JUDGE, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read())
        d = {**item, **{k: d.get(k) for k in
                        ("final_score", "rating_text", "metrics", "rule_score",
                         "deep_analysis", "clamped", "clamp_reason",
                         "scoring_basis", "sources", "web_results")},
             "lat_s": round(time.perf_counter() - t0, 1)}
    except Exception as e:
        d = {**item, "error": f"{type(e).__name__}: {e}",
             "lat_s": round(time.perf_counter() - t0, 1)}
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return d


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    cats = sys.argv[2:] or list(CATS)
    items = []
    for k in cats:
        items += fetch(k, CATS[k], n)
    # 去重：2026-10-01 改用標題（url 現在是真網域，同一則新聞不同媒體轉載會重複）
    seen, uniq = set(), []
    for it in items:
        k = it["title"].split("|")[0].split(" - ")[0].strip()
        if k not in seen:
            seen.add(k); uniq.append(it)
    print(f"[sweep] {len(uniq)} 則 (每類別 {n} 筆)", flush=True)
    ok = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        for i, fut in enumerate(as_completed([ex.submit(judge, it) for it in uniq]), 1):
            d = fut.result()
            if d.get("error"):
                print(f"  [{i}/{len(uniq)}] ERR {d['error'][:60]}", flush=True)
            else:
                ok += 1
                print(f"  [{i}/{len(uniq)}] {d['final_score']:6.2f} "
                      f"{d['rating_text']:6s} {d['title'][:44]}", flush=True)
    print(f"[sweep] 完成 {ok}/{len(uniq)} → {OUT}")