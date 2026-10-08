"""網路評論搜尋客戶端（多源，優先瀏覽器 Google）。

來源優先順序：
  1. 瀏覽器 Google 搜尋（headless Chrome + Selenium，免 key）
  2. Google News RSS（免 key，中文備援）
  3. 自架開源 free-search 服務（vandyand/free-search，bing scraping，免 key）
  （SerpApi / Serper 保留函式但預設停用：配額燒完且 key 失效，見 search()）

所有來源失敗時回傳空 list，由呼叫方決定要給搜尋連結。

環境變數：
  SERPAPI_API_KEY   SerpApi 金鑰（保留，未使用）
  SERPER_API_KEY    Serper 金鑰（保留，未使用）
  BROWSER_SEARCH    設為 0 停用瀏覽器搜尋（預設啟用）
  BROWSER_MIN_GAP   瀏覽器搜尋最小間隔秒數（預設 2.0，防 Google 節流）
  WEB_SEARCH_BASE   free-search 服務網址（預設 http://127.0.0.1:3030）
  WEB_SEARCH_ENGINE free-search 引擎（預設 bing）
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from typing import List, Dict, Optional

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
SERPER_ENDPOINT = "https://google.serper.dev/search"
GOOGLE_CSE_KEY = os.environ.get("GOOGLE_CSE_KEY", "")
GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")
GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "")
SERPAPI_ENDPOINT = "https://serpapi.com/search"
DEFAULT_BASE = os.environ.get("WEB_SEARCH_BASE", "http://127.0.0.1:3030")
DEFAULT_ENGINE = os.environ.get("WEB_SEARCH_ENGINE", "bing")
DEFAULT_TIMEOUT = 20
MAX_RESULTS = 8

# 瀏覽器搜尋節流鎖（模組級全域，避免併發觸發 Google bot 偵測）
_BROWSER_LOCK = threading.Lock()
_BROWSER_LAST = 0.0

# eval 語料凍結：NA_WEB_SNAPSHOT 指向 jsonl 快照檔時，search() 對同一 query
# 直接回快照（read-through write-back：miss 才打 live，打到非空才寫檔）。
# production 不設此變數 → 全 live，不受影響。只快取非空，避免單次網路抖動
# 把空結果凍進去污染後續重跑。
_SNAP_PATH = os.environ.get("NA_WEB_SNAPSHOT", "")
_SNAP_LOCK = threading.Lock()
_SNAP_CACHE: Optional[Dict[str, List[Dict[str, str]]]] = None


def _snap_load() -> Dict[str, List[Dict[str, str]]]:
    global _SNAP_CACHE
    if _SNAP_CACHE is not None:
        return _SNAP_CACHE
    d: Dict[str, List[Dict[str, str]]] = {}
    if _SNAP_PATH:
        try:
            with open(_SNAP_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("query") and isinstance(rec.get("results"), list):
                            d[rec["query"]] = rec["results"]
                    except Exception:
                        continue
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[web_search_client] snapshot load failed: {e}")
    _SNAP_CACHE = d
    return d


def _snap_save(query: str, results: List[Dict[str, str]]) -> None:
    if not _SNAP_PATH or not results:
        return
    with _SNAP_LOCK:
        cache = _snap_load()
        if query in cache:
            return
        cache[query] = results
        try:
            with open(_SNAP_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({"query": query, "results": results},
                                   ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[web_search_client] snapshot save failed: {e}")


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


def search_google_cse(query: str, max_results: int = MAX_RESULTS,
                       timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
    """Google Custom Search JSON API（每天 100 次免費，需 GOOGLE_CSE_KEY/CX）。失敗回空。"""
    if not GOOGLE_CSE_KEY or not GOOGLE_CSE_CX or not query:
        return []
    try:
        params = {"key": GOOGLE_CSE_KEY, "cx": GOOGLE_CSE_CX, "q": query,
                  "hl": "zh-TW", "gl": "tw", "num": min(max_results, 10)}
        url = GOOGLE_CSE_ENDPOINT + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NewsAnalyzer)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        return [{"title": it.get("title", ""), "url": it.get("link", ""),
                 "snippet": it.get("snippet", ""), "source": "google_cse"}
                for it in data.get("items", [])[:max_results]]
    except Exception as e:
        print(f"[web_search_client] google cse failed: {e}")
        return []


def search_duckduckgo(query: str, max_results: int = MAX_RESULTS,
                       timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
    """DuckDuckGo html 端點（免 key、無配額）。被擋（202/空）回空 list。"""
    if not query:
        return []
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NewsAnalyzer)"})
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
        out: List[Dict[str, str]] = []
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                             raw, re.S):
            href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            um = re.search(r"[?&]uddg=([^&]+)", href)
            link = urllib.parse.unquote(um.group(1)) if um else href
            if link.startswith("http") and title:
                out.append({"title": html.unescape(title), "url": link,
                            "snippet": "", "source": "duckduckgo"})
            if len(out) >= max_results:
                break
        return out
    except Exception as e:
        print(f"[web_search_client] duckduckgo failed: {e}")
        return []


def search(query: str, max_results: int = MAX_RESULTS) -> List[Dict[str, str]]:
    """主入口：快源並行（Google CSE + News RSS + bing + duckduckgo，約 1 秒）→ 不足才補瀏覽器 Google。

    瀏覽器啟動一次約 2.8 秒，只當備援；合併順序為 Google CSE > News RSS > bing > duckduckgo > 瀏覽器
    （去重後截斷，快源優先）。
    SerpApi / Serper 已停用（配額燒完、key 失效），函式保留以備未來恢復。
    各源內部已自行吞錯回空 list。
    """
    key = (query or "").strip()
    if _SNAP_PATH and key:
        hit = _snap_load().get(key)
        if hit:
            return [dict(r) for r in hit[:max_results]]
    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=4) as _ex:
        _f_c = _ex.submit(search_google_cse, query, max_results)
        _f_n = _ex.submit(search_google_news, query, max_results)
        _f_g = _ex.submit(search_bing, query=query, max_results=max_results)
        _f_d = _ex.submit(search_duckduckgo, query, max_results)
        try:
            _cse = _f_c.result() or []
        except Exception as _e:
            print(f"[web_search_client] cse failed: {_e}")
            _cse = []
        try:
            _news = _f_n.result() or []
        except Exception as _e:
            print(f"[web_search_client] news failed: {_e}")
            _news = []
        try:
            _bing = _f_g.result() or []
        except Exception as _e:
            print(f"[web_search_client] bing failed: {_e}")
            _bing = []
        try:
            _ddg = _f_d.result() or []
        except Exception as _e:
            print(f"[web_search_client] ddg failed: {_e}")
            _ddg = []
    results: List[Dict[str, str]] = []
    seen: set = set()
    for _r in _cse + _news + _bing + _ddg:
        if _r["url"] in seen:
            continue
        seen.add(_r["url"])
        results.append(_r)
    # 2026-10-08：數量夠但可抓正文的來源不足時也補瀏覽器——包裝連結
    # （Google News RSS wrapper）永遠解析不出正文，有摘要也只算半個；
    # 短標題薄證據輸入永遠翻不了案（日文 28 FP、簡體 42 FP 的主因）。
    # 有 2 筆以上帶摘要才算夠（正常查詢零成本）。
    _n_snip = sum(1 for r in results if (r.get("snippet") or "").strip())
    _b = []
    if ((len(results) < max_results or _n_snip < 2)
            and os.environ.get("BROWSER_SEARCH", "1") != "0"):
        try:
            _b = search_browser_google(query, max_results=max_results) or []
        except Exception as _e:
            print(f"[web_search_client] browser failed: {_e}")
            _b = []
        for _r in _b:
            if _r["url"] in seen:
                continue
            seen.add(_r["url"])
            _r["source"] = "browser_google"
            results.append(_r)
    if _SNAP_PATH and key and results:
        _snap_save(key, results)
    # 瀏覽器補位不被截斷（否則快源填滿時補的全被切掉＝白跑 2.8s）；
    # 下游 sim-filter 會重排＋截斷，無瀏覽器結果時維持舊截斷。
    return results if _b else results[:max_results]


def search_browser_google(query: str, max_results: int = MAX_RESULTS,
                          timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
    """headless Chrome 直搜 Google（免 key）。失敗回空 list。

    節流保護：全域鎖 + 最小間隔（BROWSER_MIN_GAP，預設 2 秒），避免併發觸發
    Google bot 偵測。每次呼叫用獨立 profile 目錄（避開 SingletonLock 衝突）。
    """
    if not query or os.environ.get("BROWSER_SEARCH", "1") == "0":
        return []
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
    except Exception as e:
        print(f"[web_search_client] browser search: no selenium ({e})")
        return []
    import tempfile
    global _BROWSER_LAST
    gap = float(os.environ.get("BROWSER_MIN_GAP", "2.0"))
    out: List[Dict[str, str]] = []
    profdir = tempfile.mkdtemp(prefix="na-chrome-")
    driver = None
    try:
        with _BROWSER_LOCK:
            wait = gap - (time.time() - _BROWSER_LAST)
            if wait > 0:
                time.sleep(wait)
            o = Options()
            o.add_argument("--headless=new")
            o.add_argument("--no-sandbox")
            o.add_argument("--disable-gpu")
            o.add_argument("--disable-blink-features=AutomationControlled")
            o.add_argument("--lang=zh-TW")
            o.add_argument(f"--user-data-dir={profdir}")
            o.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
            driver = webdriver.Chrome(options=o)
            url = ("https://www.google.com.tw/search?q="
                   + urllib.parse.quote(query) + "&hl=zh-TW&gl=tw&num=10")
            driver.get(url)
            try:
                WebDriverWait(driver, timeout).until(
                    lambda d: d.find_elements(By.CSS_SELECTOR, "div.MjjYud")
                    or "sorry" in d.current_url or "consent" in d.current_url)
            except Exception:
                pass
            if "sorry" in driver.current_url:
                print("[web_search_client] browser search: sorry-page, skip")
            elif "consent" in driver.current_url:
                print("[web_search_client] browser search: consent-page, skip")
            else:
                for b in driver.find_elements(By.CSS_SELECTOR, "div.MjjYud")[:max_results + 2]:
                    try:
                        h3s = b.find_elements(By.CSS_SELECTOR, "h3")
                        if not h3s:
                            continue
                        href = h3s[0].find_element(By.XPATH, "./ancestor::a[1]").get_attribute("href") or ""
                        snip = ""
                        for el in b.find_elements(By.CSS_SELECTOR, "div.VwiC3b"):
                            if len(el.text) > 30:
                                snip = el.text
                                break
                        if h3s[0].text and href.startswith("http"):
                            out.append({"title": h3s[0].text, "url": href,
                                        "snippet": snip, "source": "browser_google"})
                    except Exception:
                        continue
            _BROWSER_LAST = time.time()
    except Exception as e:
        print(f"[web_search_client] browser search failed: {e}")
    finally:
        try:
            if driver is not None:
                driver.quit()
        except Exception:
            pass
        import shutil
        try:
            shutil.rmtree(profdir, ignore_errors=True)
        except Exception:
            pass
    return out[:max_results]


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
