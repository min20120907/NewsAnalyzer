#!/usr/bin/env python3
"""每日拉取社群維護的網域名單 → data/domains/*.remote.txt（原子寫入，失敗保留舊檔）.

訂閱源：
  blocklist.remote.txt ← 終結內容農場 danny0838（中文內容農場）
                        ＋ cobaltdisco 中文 SEO 垃圾網域 x2
                        ＋ StevenBlack fakenews extension（英文假新聞聚合）
  ugc.remote.txt       ← StevenBlack social extension（社群平台聚合）
白名單 / 查核機構無機器可讀上游，維持 data/domains/whitelist.txt、factcheck.txt 本地策展。

用法：python3 scripts/pull_domain_lists.py  （由系統 crontab 每日 03:30 執行）
"""
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "data", "domains")

SOURCES = {
    "blocklist.remote.txt": {
        "urls": [
            "https://danny0838.github.io/content-farm-terminator/files/blocklist/content-farms.txt",
            "https://raw.githubusercontent.com/cobaltdisco/Google-Chinese-Results-Blocklist/master/uBlacklist_subscription.txt",
            "https://raw.githubusercontent.com/cobaltdisco/Google-Chinese-Results-Blocklist/master/uBlacklist_subscription_extra.txt",
            "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/fakenews/hosts",
        ],
        "min_domains": 5000,
    },
    "ugc.remote.txt": {
        "urls": [
            "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/social/hosts",
        ],
        "min_domains": 500,
    },
}

UA = "NewsAnalyzer-Bot/1.0 (domain-list-pull)"
SKIP_HOSTS = {"localhost", "localhost.localdomain", "local", "broadcasthost",
              "localdomain", "ip6-localhost", "ip6-loopback"}


def normalize(line: str):
    """各種格式（hosts / uBlacklist / adblock ||）→ bare domain；不行回 None。"""
    line = (line or "").strip()
    if not line or line.startswith(("#", "!", "[", "/")):
        return None
    tok = line.split()[0]  # 去掉 hosts 行尾註解
    if tok in ("0.0.0.0", "127.0.0.1", "::1"):
        # hosts 格式：IP 在前、domain 在第二欄
        _toks = line.split()
        if len(_toks) < 2:
            return None
        tok = _toks[1]
    for prefix in ("0.0.0.0", "127.0.0.1", "::1", "||"):
        if tok == prefix:
            return None
        if tok.startswith(prefix):
            tok = tok[len(prefix):].lstrip()
            break
    tok = (tok.replace("*://*.", "").replace("*://", "")
              .replace("/*", "").lstrip("*.")
              .rstrip("^/.").strip())
    tok = tok.lower()
    if (not tok or "/" in tok or "*" in tok or " " in tok
            or "." not in tok or tok.startswith(("-", "."))
            or len(tok) > 253 or tok in SKIP_HOSTS):
        return None
    try:
        tok.encode("idna")
    except Exception:
        return None
    return tok


def fetch(url: str, timeout=60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    ok = True
    for fname, spec in SOURCES.items():
        domains: set = set()
        for url in spec["urls"]:
            try:
                raw = fetch(url)
            except Exception as e:
                print(f"[pull] FAIL {url}: {e}", flush=True)
                ok = False
                continue
            n0 = len(domains)
            for line in raw.splitlines():
                d = normalize(line)
                if d:
                    domains.add(d)
            print(f"[pull] {url.split('/')[-2] + '/' + url.split('/')[-1]}: +{len(domains) - n0}",
                  flush=True)
        if len(domains) < spec["min_domains"]:
            print(f"[pull] ABORT {fname}: only {len(domains)} domains "
                  f"(min {spec['min_domains']}), keep old file", flush=True)
            ok = False
            continue
        tmp = os.path.join(OUT_DIR, fname + ".tmp")
        final = os.path.join(OUT_DIR, fname)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(f"# auto-pulled {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                    f"UTC, {len(domains)} domains\n")
            for src in spec["urls"]:
                f.write(f"# src: {src}\n")
            for d in sorted(domains):
                f.write(d + "\n")
        os.replace(tmp, final)  # 原子寫入
        print(f"[pull] WROTE {fname}: {len(domains)} domains", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
