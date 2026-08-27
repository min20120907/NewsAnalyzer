"""網路評論搜尋客戶端（多源，優先 SerpApi）。

來源優先順序：
  1. SerpApi（Google SERP JSON API，需 key：SERPAPI_API_KEY）
  2. Serper.dev（Google SERP JSON API，需 key：SERPER_API_KEY）
  3. 自架開源 free-search 服務（vandyand/free-search，bing scraping，免 key）
  4. Google News RSS（免 key，中文備援）

所有來源失敗時回傳空 list，由呼叫方決定要給搜尋連結。

環境變數：
  SERPAPI_API_KEY   SerpApi 金鑰（無則跳過該源）
  SERPER_API_KEY    Serper 金鑰（無則跳過該源）
  WEB_SEARCH_BASE   free-search 服務網址（預設 http://127.0.0.1:3030）
  WEB_SEARCH_ENGINE free-search 引擎（預設 bing）
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.parse
import urllib.request
from typing import List, Dict, Optional

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
SERPER_ENDPOINT = "https://google.serper.dev/search"
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "")
SERPAPI_ENDPOINT = "https://serpapi.com/search"
DEFAULT_BASE = os.environ.get("WEB_SEARCH_BASE", "http://127.0.0.1:3030")
DEFAULT_ENGINE = os.environ.get("WEB_SEARCH_ENGINE", "bing")
DEFAULT_TIMEOUT = 20
MAX_RESULTS = 8


def _decode_bing_url(raw: str) -> str:
    """bing 重導連結 https://www.bing.com/ck/a?...&u=a1<base64url> 解回真實 URL。"""
    if not raw:
        return raw
    try:
        m = re.search(r"[?&]u=a1([^&]+)", raw)
        if m:
            b = m.group(1)
            b = b.replace("-", "+").replace("_", "/")
            b += "=" * (-len(b) % 4)
            return base64.b64decode(b).decode("utf-8", "ignore")
    except Exception:
        pass
    return raw


def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NewsAnalyzer)"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def search_serper(query: str, max_results: int = MAX_RESULTS,
                  timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
    """Serper.dev Google SERP。需 SERPER_API_KEY。失敗回空 list。"""
    if not SERPER_API_KEY or not query:
        return []
    try:
        req = urllib.request.Request(
            SERPER_ENDPOINT,
            data=json.dumps({"q": query}).encode("utf-8"),
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (NewsAnalyzer)",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        out: List[Dict[str, str]] = []
        for it in data.get("organic", [])[:max_results]:
            out.append({
                "title": it.get("title", ""),
                "url": it.get("link", ""),
                "snippet": it.get("snippet", ""),
                "source": "serper",
            })
        return out
    except Exception as e:
        print(f"[web_search_client] serper failed: {e}")
        return []


def search_serpapi(query: str, max_results: int = MAX_RESULTS,
                   timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
    """SerpApi.com Google SERP。需 SERPAPI_API_KEY。失敗回空 list。"""
    if not SERPAPI_API_KEY or not query:
        return []
    try:
        params = {
            "engine": "google",
            "q": query,
            "hl": "zh-tw",
            "gl": "tw",
            "google_domain": "google.com.tw",
            "api_key": SERPAPI_API_KEY,
        }
        url = SERPAPI_ENDPOINT + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NewsAnalyzer)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        if data.get("error"):
            print(f"[web_search_client] serpapi error: {data['error']}")
            return []
        out: List[Dict[str, str]] = []
        for it in data.get("organic_results", [])[:max_results]:
            link = it.get("link", "")
            # unwrap google 重導包裝（google.com.tw/goto?url= / google.com/url?q=）
            if "google.com" in link and "url" in link:
                qp = urllib.parse.urlparse(link).query
                for k in ("url", "q"):
                    v = urllib.parse.parse_qs(qp).get(k, [""])[0]
                    if v:
                        link = v
                        break
            out.append({
                "title": it.get("title", ""),
                "url": link,
                "snippet": it.get("snippet", ""),
                "source": "serpapi",
            })
        return out
    except Exception as e:
        print(f"[web_search_client] serpapi failed: {e}")
        return []


def search_bing(base: str = DEFAULT_BASE, engine: str = DEFAULT_ENGINE,
                query: str = "", max_results: int = MAX_RESULTS,
                timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
    """free-search 服務（bing scraping）。失敗回空 list。"""
    if not query:
        return []
    q = urllib.parse.urlencode({"q": query, "engine": engine, "usePuppeteer": "false", "safe": "false"})
    url = f"{base.rstrip('/')}/api/search?{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 NewsAnalyzer"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception as e:
        print(f"[web_search_client] bing search failed: {e}")
        return []

    out: List[Dict[str, str]] = []
    for it in data.get("results", [])[:max_results]:
        out.append({
            "title": it.get("title", ""),
            "url": _decode_bing_url(it.get("url", "")),
            "snippet": it.get("snippet", ""),
            "source": "bing",
        })
    return out


def search_google_news(query: str, max_results: int = MAX_RESULTS,
                       timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
    """Google News RSS 備援（中文相關性較好，免 key）。失敗回空 list。"""
    if not query:
        return []
    q = urllib.parse.quote(query)
    # hl/gl/ceid=TW 讓 Google News 回台灣中文結果（否則 302 空頁）
    url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hans"
    try:
        from xml.etree import ElementTree as ET
        data = _http_get(url, timeout)
        if not data:
            return []
        root = ET.fromstring(data)
        out: List[Dict[str, str]] = []
        for it in root.findall(".//item")[:max_results]:
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            out.append({"title": title, "url": link, "snippet": "", "source": "google_news"})
        return out
    except Exception as e:
        print(f"[web_search_client] google news rss failed: {e}")
        return []


def search(query: str, max_results: int = MAX_RESULTS) -> List[Dict[str, str]]:
    """主入口：SerpApi → Serper → Google News RSS → free-search bing。"""
    results: List[Dict[str, str]] = []
    results += search_serpapi(query, max_results=max_results)
    if len(results) < max_results:
        results += search_serper(query, max_results=max_results - len(results))
    if len(results) < max_results:
        results += search_google_news(query, max_results=max_results - len(results))
    if len(results) < max_results:
        results += search_bing(query=query, max_results=max_results - len(results))
    seen, dedup = set(), []
    for r in results:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        dedup.append(r)
    return dedup[:max_results]


def has_serpapi() -> bool:
    return bool(SERPAPI_API_KEY)


def has_serper() -> bool:
    return bool(SERPER_API_KEY)


def has_service(base: str = DEFAULT_BASE, timeout: int = 5) -> bool:
    try:
        req = urllib.request.Request(f"{base.rstrip('/')}/health")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "萬坪新商場 大直 AI百貨"
    res = search(q)
    print(f"serper enabled: {has_serper()} | found {len(res)} results for: {q}")
    for i, r in enumerate(res[:8], 1):
        print(f"{i}. [{r['source']}] {r['title']}\n   {r['url']}")
