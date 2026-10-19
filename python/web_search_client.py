"""網路評論搜尋客戶端（多源，優先瀏覽器 Google）。

來源優先順序（2026-10-14：Google cookie 主力，Serper/SerpApi 退役）：
  1. Google 搜尋帶本機 Chrome cookie（免 key、免瀏覽器；見 search_google_cookies）
  2. Google News RSS（免 key，中文備援）
  3. 自架開源 free-search 服務（vandyand/free-search，bing scraping，免 key）
  4. 瀏覽器 Google 搜尋（headless Chrome + Selenium，免 key，僅補位）
  （SerpApi / Serper 保留函式但不在快源：SERPER key 實為 SerpApi key → 403，
    SerpApi 配額燒完。恢復方法：把 search_serper/search_serpapi 加回 search() 並行池）

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
import urllib.error
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


def _is_relevant_to_query(query: str, title: str, snippet: str) -> bool:
    """過濾 Bing 反爬蟲假頁面（Walmart / Docker / 字典等與查詢毫無交集的 decoy SERP）。"""
    blob = ((title or "") + " " + (snippet or "")).lower()
    if not blob.strip():
        return False
    q_cjk = re.findall(r"[\u4e00-\u9fff]{2,}", query or "")
    for seg in q_cjk:
        for i in range(len(seg) - 1):
            if seg[i:i + 2] in blob:
                return True
    q_alnum = [w.lower() for w in re.findall(r"[A-Za-z0-9]{2,}", query or "")]
    if any(w in blob for w in q_alnum):
        return True
    return not q_cjk and not q_alnum


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
    for it in data.get("results", []):
        title = it.get("title", "")
        snip = it.get("snippet", "")
        if not _is_relevant_to_query(query, title, snip):
            continue
        out.append({
            "title": title,
            "url": _decode_bing_url(it.get("url", "")),
            "snippet": snip,
            "source": "bing",
        })
        if len(out) >= max_results:
            break
    return out


def search_bing_news(query: str, max_results: int = MAX_RESULTS,
                     timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
    """Bing News RSS（免 key、附真實媒體直連 URL 與完整摘要，無反爬蟲 decoy）。失敗回空 list。"""
    if not query:
        return []
    params = urllib.parse.urlencode({"q": query, "format": "rss", "setlang": "zh-Hant", "cc": "TW"})
    url = f"https://www.bing.com/news/search?{params}"
    try:
        from xml.etree import ElementTree as ET
        data = _http_get(url, timeout)
        if not data:
            return []
        root = ET.fromstring(data)
        out: List[Dict[str, str]] = []
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = (it.findtext("description") or "").strip()
            if "bing.com/news/apiclick.aspx" in link:
                qp = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                real_u = (qp.get("url") or [""])[0]
                if real_u:
                    link = real_u
            if not (title and link) or not _is_relevant_to_query(query, title, desc):
                continue
            out.append({"title": title, "url": link, "snippet": desc[:300], "source": "bing_news"})
            if len(out) >= max_results:
                break
        return out
    except Exception as e:
        print(f"[web_search_client] bing news rss failed: {e}")
        return []


def search_google_news(query: str, max_results: int = MAX_RESULTS,
                       timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
    """Google News RSS 備援（中文相關性較好，免 key）。失敗回空 list。"""
    if not query:
        return []
    q = urllib.parse.quote(query)
    # hl/gl/ceid=TW 讓 Google News 回台灣繁體中文結果（否則 302 空頁）
    url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
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


# ----------------------------------------------------------------------------
# Google cookie 搜尋（2026-10-14：取代 Serper/SerpApi 的免費主力）
# 從本機 Chrome profile 解密 google.com cookies（復用 fb_session 的金鑰取得），
# 帶 Cookie header 直接 HTTP 打 www.google.com/search —— 不啟動瀏覽器（省 2.8s）、
# 登入態 cookie 大幅降低 sorry/consent 頁機率。純 stdlib + bs4（newspaper3k 已帶）。
# ponytail: cookie 快取 TTL 1h；Chrome 重登/清 cookie 後最多 1h 內自動更新，
# 若要即時就改成 mtime 監聽 Cookies DB。
# ----------------------------------------------------------------------------
_GCOOK_CACHE = {"ts": 0.0, "header": ""}


def _google_cookie_header(ttl: float = 3600.0) -> str:
    now = time.time()
    if _GCOOK_CACHE["header"] and now - _GCOOK_CACHE["ts"] < ttl:
        return _GCOOK_CACHE["header"]
    header = ""
    try:
        import sqlite3, shutil, tempfile
        from hashlib import pbkdf2_hmac
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        # systemd user service 環境沒有 DBUS_SESSION_BUS_ADDRESS → secretstorage
        # 連不到 keyring → 靜默 fallback peanuts → v10 cookie 全解不開。
        # 補預設值（uid 1000）後實測 89/89 解密成功（SID/SSID/SAPISID/NID/AEC）。
        os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
        os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
        from fb_session import _get_chrome_safe_storage_key
        safe_key = _get_chrome_safe_storage_key()
        if safe_key == b'peanuts':
            print("[web_search_client] google cookie: keyring 取得失敗 (peanuts)，"
                  "解密必錯，跳過（確認 user session bus 可用）")
            return ""
        key = pbkdf2_hmac('sha1', safe_key, b'saltysalt', 1, 16)
        for db in ("~/.config/google-chrome/Default/Cookies",
                   "~/.config/google-chrome/Default/Network/Cookies"):
            p = os.path.expanduser(db)
            if not os.path.exists(p):
                continue
            tmp = tempfile.mktemp(prefix="na-gcook-", suffix=".db")
            try:
                shutil.copy2(p, tmp)
                con = sqlite3.connect(tmp)
                rows = con.execute(
                    "SELECT host_key, name, CAST(encrypted_value AS BLOB) FROM cookies "
                    "WHERE host_key LIKE '%google.com'").fetchall()
                con.close()
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            parts = []

            def _printable(b: bytes) -> bool:
                return all(32 <= c < 127 for c in b)

            for host, name, enc in rows:
                if not enc:
                    continue
                plain = b""
                if enc[:3] in (b'v10', b'v11'):
                    try:
                        dec = Cipher(algorithms.AES(key), modes.CBC(b' ' * 16)).decryptor()
                        raw = dec.update(enc[3:]) + dec.finalize()
                        up = padding.PKCS7(128).unpadder()
                        plain = up.update(raw) + up.finalize()
                    except Exception:
                        continue
                else:
                    plain = enc
                # 新版 Chrome 把 SHA256(domain) 32 bytes 前綴進明文（實測 SID/NID/AEC
                # 前 32 bytes 為二進位、其後才是真值 g.a000...）。前綴不可印就剝掉。
                if not _printable(plain[:32]) and _printable(plain[32:]):
                    plain = plain[32:]
                # HTTP header 必須 latin-1；不可印字元會讓整個 header 發不出去
                # （實測 \u07ef/\x1c 炸 urllib）。
                if not plain or not _printable(plain):
                    continue
                parts.append(f"{name}={plain.decode('ascii')}")
            if parts:
                header = "; ".join(parts)
                break
        if header:
            _GCOOK_CACHE.update(ts=now, header=header)
        else:
            print("[web_search_client] google cookie: 解密結果為空")
    except Exception as e:
        print(f"[web_search_client] google cookie extract failed: {e}")
    return header


def search_google_cookies(query: str, max_results: int = MAX_RESULTS,
                          timeout: int = 15) -> List[Dict[str, str]]:
    """帶本機 Chrome cookie 的 Google 搜尋（免 key、免瀏覽器）。失敗回空 list。"""
    if not query or os.environ.get("GOOGLE_COOKIE_SEARCH", "1") == "0":
        return []
    ck = _google_cookie_header()
    if not ck:
        return []
    url = ("https://www.google.com/search?q=" + urllib.parse.quote(query)
           + "&hl=zh-TW&gl=tw&num=10")
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            "Cookie": ck,
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "ignore")
        if "/sorry/" in raw[:3000] or "unusual traffic" in raw[:5000]:
            print("[web_search_client] google cookie: sorry-page, skip")
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw, "lxml")
        out: List[Dict[str, str]] = []
        seen: set = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.match(r"/url\?q=([^&]+)", href)
            if m:
                href = urllib.parse.unquote(m.group(1))
            if not href.startswith("http") or "google.com" in href:
                continue
            h3 = a.find("h3")
            if not h3:
                continue
            title = h3.get_text(strip=True)
            if not title or href in seen:
                continue
            seen.add(href)
            snip = ""
            box = a.find_parent("div")
            for _ in range(4):  # 往外找含摘要文字的容器
                if box is None:
                    break
                txt = box.get_text(" ", strip=True)
                if len(txt) > len(title) + 60:
                    snip = txt[len(title):].strip(" -–|")[:300]
                    break
                box = box.find_parent("div")
            out.append({"title": title, "url": href, "snippet": snip,
                        "source": "google_cookie"})
            if len(out) >= max_results:
                break
        return out
    except Exception as e:
        print(f"[web_search_client] google cookie search failed: {e}")
        return []


def _resolve_google_goto(url: str, timeout: int = 8) -> str:
    """解析 Google 包裝連結（google.com.tw/goto?url=… / google.com/url?q=…）為真實網址。

    SERP 直爬不解包時，下游正文抽取器只會看到 google.com 的轉址頁 → 永遠抓不到內文
    （「查得到卻像查不到」）。先用 query 參數免網路解，解不動才發一次不跟隨轉址的
    請求讀 Location。失敗一律回原 url（絕不吞掉結果）。
    """
    if not url or "google." not in url:
        return url
    try:
        u = urllib.parse.urlparse(url)
        if "/url" not in u.path and "/goto" not in u.path:
            return url
        qp = urllib.parse.parse_qs(u.query)
        for k in ("url", "q", "u"):
            cand = (qp.get(k) or [""])[0]
            if cand.startswith("http") and "google." not in urllib.parse.urlparse(cand).netloc:
                return cand
    except Exception:
        pass
    try:
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
                return None
        opener = urllib.request.build_opener(_NoRedirect)
        req = urllib.request.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")})
        try:
            with opener.open(req, timeout=timeout) as r:
                final = r.geturl()
        except urllib.error.HTTPError as he:
            final = he.headers.get("Location") or ""
        if final.startswith("http") and "google." not in urllib.parse.urlparse(final).netloc:
            return final
    except Exception:
        pass
    return url


# 快源並行表（名稱 → 呼叫；(query, max_results) 兩參數介面）。
# 抽成模組常數：新增來源只需改這裡，不會再出現 submit 了卻沒 result() 的懸空 future
# （2026-10-18 修：search() 曾對未定義的 _serper 取值 → NameError 讓整個入口炸掉）。
_QUICK_SOURCES = [
    ("google_cookie", lambda q, n: search_google_cookies(q, n)),
    ("google_cse", lambda q, n: search_google_cse(q, n)),
    ("google_news", lambda q, n: search_google_news(q, n)),
    ("bing_news", lambda q, n: search_bing_news(q, n)),
    ("bing", lambda q, n: search_bing(query=q, max_results=n)),
    ("duckduckgo", lambda q, n: search_duckduckgo(q, n)),
]


def search(query: str, max_results: int = MAX_RESULTS) -> List[Dict[str, str]]:
    """主入口：快源並行（Google cookie + Google CSE + News RSS + Bing News RSS + bing + duckduckgo，約 1 秒）→ 不足才補瀏覽器 Google。

    瀏覽器啟動一次約 2.8 秒，只當備援。合併順序以「證據可用度」排（見下方註解）：
    Google cookie > Google CSE > Bing News > bing > duckduckgo > Google News RSS > 瀏覽器。
    各源內部已自行吞錯回空 list。
    """
    key = (query or "").strip()
    if _SNAP_PATH and key:
        hit = _snap_load().get(key)
        if hit:
            return [dict(r) for r in hit[:max_results]]
    import concurrent.futures as _cf
    # 2026-10-14：Serper/SerpApi 從快源退役（SERPER key 實為 SerpApi key → 403；
    # SerpApi 配額已燒光）。主力改 search_google_cookies（本機 Chrome cookie，免 key）。
    # 2026-10-18：Bing News RSS 加入快源（免 key、真實媒體 URL、無反爬 decoy）；
    # 快源改由 _QUICK_SOURCES 表驅動，新增來源只需改表，不會再出現 submit 了卻沒
    # result()、或結果沒被排進合併清單的懸空來源。
    with _cf.ThreadPoolExecutor(max_workers=len(_QUICK_SOURCES)) as _ex:
        _futs = [(_name, _ex.submit(_fn, query, max_results))
                 for _name, _fn in _QUICK_SOURCES]
        _got: Dict[str, List[Dict[str, str]]] = {}
        for _name, _f in _futs:
            try:
                _got[_name] = _f.result() or []
            except Exception as _e:
                print(f"[web_search_client] {_name} failed: {_e}")
                _got[_name] = []
    _gck = _got.get("google_cookie", [])
    _cse = _got.get("google_cse", [])
    _news = _got.get("google_news", [])
    _bnews = _got.get("bing_news", [])
    _bing = _got.get("bing", [])
    _ddg = _got.get("duckduckgo", [])
    results: List[Dict[str, str]] = []
    seen: set = set()
    # 2026-10-18 排序改以「證據可用度」為準（原本按來源新舊排，導致 Google News
    # 的 6 筆 wrapper 佔滿名額，把 Bing News 的真實媒體直連＋摘要整批截掉；
    # wrapper 連結下游抽不到正文，等於用不可用的換掉可用的）：
    #   直連＋摘要（google_cookie / cse / bing_news）> 直連（bing / ddg）> wrapper（google_news）
    for _r in _gck + _cse + _bnews + _bing + _ddg + _news:
        if not _r.get("url"):
            continue
        # Google 包裝連結在此一次性解成真實網址：解析後的重複項能正確去重，
        # 下游正文抽取也才抓得到內文。
        _r["url"] = _resolve_google_goto(_r["url"])
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
            _r["url"] = _resolve_google_goto(_r.get("url") or "")
            if not _r["url"] or _r["url"] in seen:
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
