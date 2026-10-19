# -*- coding: utf-8 -*-
"""A/B：網路搜尋結果「相不相干」的前後對照（HEAD 版 vs 修好版）。

量法：SBERT cosine（新聞標題 vs 搜尋結果標題），門檻沿用
      scripts/check_retrieval_agreement.py 的 0.45。

比較三種：
  old.search_bing      HEAD 的 Bing 直爬（free-search 服務；未過濾 → decoy）
  old.search_google_news / new.search_bing_news（新加的 Bing News RSS）
  new.search()         修好後的完整入口（快源表驅動）

跑法：cd python && ../.venv/bin/python ../scripts/probe_web_search_ab.py
"""
import importlib.util
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(os.path.dirname(HERE), "python")
sys.path.insert(0, PY)

from sentence_transformers import SentenceTransformer  # noqa: E402

MODEL = ("/home/min20120907/.cache/huggingface/hub/models--sentence-transformers--"
         "paraphrase-multilingual-MiniLM-L12-v2/snapshots/"
         "e8f8c211226b894fcb81acc59f3b34ba3efd5f42")

_OLD_PATH = "/tmp/opencode/wsc_head.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    import web_search_client as new

    old = load_module("wsc_head", _OLD_PATH) if os.path.exists(_OLD_PATH) else None
    os.environ.pop("NA_WEB_SNAPSHOT", None)
    os.environ["BROWSER_SEARCH"] = "0"

    qs = []
    for f in ("eval_bait60_REAL.jsonl", "eval_bait60_BAIT.jsonl"):
        for line in open(os.path.join(PY, f), encoding="utf-8"):
            line = line.strip()
            if line:
                r = json.loads(line)
                qs.append((r["id"], r["title"]))
    qs = qs[:10]

    print("[model] loading SBERT ...", flush=True)
    m = SentenceTransformer(MODEL, device="cpu")

    def cos(a, b):
        import numpy as np
        v = m.encode([a, b], normalize_embeddings=True, convert_to_numpy=True)
        return float(v[0] @ v[1])

    def measure(tag, query, results, out):
        sims = []
        for r in results:
            t = (r.get("title") or "").strip()
            if not t:
                continue
            s = cos(query, t)
            sims.append(s)
            out.append({"tag": tag, "q": query, "title": t[:80],
                        "url": (r.get("url") or "")[:100],
                        "source": r.get("source"), "sim": round(s, 4)})
        return sims

    rows = []
    old_exc = None
    summary = {}
    for iid, title in qs:
        print(f"== {iid} {title[:40]}", flush=True)
        # (0) HEAD 的入口是否可用
        if old is not None and old_exc is None:
            try:
                old.search(title, max_results=3)
                old_exc = ""
            except Exception as e:
                old_exc = f"{type(e).__name__}: {e}"
        # (1) HEAD 的 bing 直爬
        if old is not None:
            try:
                t0 = time.time()
                rb_old = old.search_bing(query=title, max_results=6)
                print(f"   old.search_bing     -> {len(rb_old)} ({time.time() - t0:.1f}s)")
                s = measure("old_bing", title, rb_old, rows)
                summary.setdefault("old_bing", []).extend(s)
            except Exception as e:
                print(f"   old.search_bing EXC {e}")
        # (2) 新的 bing_news（新來源）
        try:
            t0 = time.time()
            rb_new = new.search_bing_news(title, max_results=6)
            print(f"   new.search_bing_news-> {len(rb_new)} ({time.time() - t0:.1f}s)")
            s = measure("new_bing_news", title, rb_new, rows)
            summary.setdefault("new_bing_news", []).extend(s)
        except Exception as e:
            print(f"   new.search_bing_news EXC {e}")
        # (3) 新入口（整池）
        try:
            t0 = time.time()
            rn = new.search(title, max_results=6)
            print(f"   new.search()        -> {len(rn)} ({time.time() - t0:.1f}s)")
            s = measure("new_search", title, rn, rows)
            summary.setdefault("new_search", []).extend(s)
        except Exception as e:
            print(f"   new.search EXC {e}")

    print()
    if old_exc is not None:
        print(f"[HEAD 入口 search() 實測] {'可用' if not old_exc else 'EXC → ' + old_exc}")
    print(f"\n{'來源':>16s}{'筆數':>6s}{'吻合>=0.45':>11s}{'中位sim':>9s}{'最低':>8s}")
    for tag, sims in summary.items():
        if not sims:
            print(f"{tag:>16s}{0:>6d}          n/a")
            continue
        ok = sum(1 for s in sims if s >= 0.45)
        print(f"{tag:>16s}{len(sims):>6d}{ok / len(sims) * 100:>10.0f}%"
              f"{statistics.median(sims):>9.3f}{min(sims):>8.3f}")
    with open("/tmp/opencode/web_search_ab.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\n明細 -> /tmp/opencode/web_search_ab.jsonl")
    print("\n--- 不相關樣本（sim<0.30，各來源最多 5 筆）---")
    worst = {}
    for r in sorted(rows, key=lambda x: x["sim"]):
        if r["sim"] >= 0.30:
            continue
        worst.setdefault(r["tag"], [])
        if len(worst[r["tag"]]) < 5:
            worst[r["tag"]].append(r)
    for tag, items in worst.items():
        print(f"  [{tag}]")
        for r in items:
            print(f"    sim={r['sim']:.3f} [{r['source']}] {r['title'][:60]}")


if __name__ == "__main__":
    main()
