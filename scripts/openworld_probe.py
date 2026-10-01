#!/usr/bin/env python3
"""open-world 檢索品質：真實貼文（不在 RSS 庫裡）看 web_results 是否真吻合。

輸入放 data/eval/openworld_probes.json，每筆 {title, url, postText, expect_relevant:[關鍵詞]}
"""
import json, sys, time, urllib.request, os

JUDGE = "http://127.0.0.1:5000/judge"
HERE = os.path.dirname(os.path.abspath(__file__))
PROBES = os.path.join(HERE, "..", "data", "eval", "openworld_probes.json")
OUT = os.path.join(HERE, "..", "data", "eval", "openworld_results.jsonl")


def judge(p):
    body = json.dumps({"title": p["title"], "url": p.get("url", ""),
                       "postText": p.get("postText", "")}).encode()
    req = urllib.request.Request(JUDGE, data=body,
                                headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=200) as r:
            d = json.loads(r.read())
        out = {**p, **{k: d.get(k) for k in
                       ("final_score", "rating_text", "metrics", "deep_analysis",
                        "scoring_basis", "sources", "web_results")},
               "lat_s": round(time.perf_counter() - t0, 1)}
    except Exception as e:
        out = {**p, "error": f"{type(e).__name__}: {e}",
               "lat_s": round(time.perf_counter() - t0, 1)}
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":
    probes = json.load(open(PROBES, encoding="utf-8"))
    print(f"[openworld] {len(probes)} 則探針", flush=True)
    for i, p in enumerate(probes, 1):
        d = judge(p)
        if d.get("error"):
            print(f"  [{i}] ERR {d['error'][:70]}", flush=True)
        else:
            n = len(d.get("web_results") or [])
            print(f"  [{i}] {d['final_score']:6.2f} {d['rating_text']:6s} "
                  f"web={n}  {p['title'][:40]}", flush=True)
    print(f"→ {OUT}")