"""抓 Cofacts 最近 N 天的「真的被查核過」文章——假新聞與真新聞各一組。

2026-10-01。為什麼不用現有 dataset_frozen.json：那是 2026-09-24 凍結的，
而且是同域配對（查核文 vs 查核文），不是線上實際的「新聞報導 → 查核」形狀。
這裡直接取 API 上最新、且真的有人查核過（replyTypes 篩掉貼了沒人查的雜訊）。

抓完餵 /judge（mode=deep）跑，看兩組的精準度差在哪。
用法：.venv/bin/python scripts/fetch_live_cofacts.py [天數] [每組筆數]
"""
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
API = "https://api.cofacts.tw/graphql"
JUDGE = "http://127.0.0.1:5000/judge"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "eval",
                   "live_cofacts_pairs.json")

# CoFacts 的 replyTypes：RUMOR=謠言、NOT_RUMOR=非謠言。假新聞對應 RUMOR。
GROUPS = {"fake": ["RUMOR"], "real": ["NOT_RUMOR"]}


def fetch(reply_types, since, want):
    """撈到 want 筆為止。分頁用 cursor（`after`），排序用 orderBy.createdAt。
    2026-10-01：API 沒有 `offset`，只有 Relay 風格的 `after` cursor。"""
    out, seen = [], set()
    cursor = None
    while len(out) < want:
        after = f', after:"{cursor}"' if cursor else ""
        Q = ("query { ListArticles(filter:{createdAt:{GT:\"%s\"}, "
             "replyTypes:[%s]}, orderBy:{createdAt:DESC}, first:25%s) "
             "{ pageInfo { lastCursor } edges { node { id text "
             "createdAt articleReplies(status:NORMAL){ feedbackCount "
             "reply{ type text } } } } } }"
             % (since, ",".join(reply_types), after))
        r = requests.post(API, json={"query": Q},
                          headers={"User-Agent": UA,
                                   "Content-Type": "application/json"}, timeout=30)
        d = r.json()
        if d.get("errors"):
            print(f"  [err] {json.dumps(d['errors'], ensure_ascii=False)[:160]}")
            break
        la = (d.get("data") or {}).get("ListArticles") or {}
        edges = la.get("edges") or []
        if not edges:
            break
        for e in edges:
            n = e["node"]
            if n["id"] in seen:
                continue
            seen.add(n["id"])
            replies = [a for a in (n.get("articleReplies") or [])
                       if (a.get("reply") or {}).get("text", "").strip()]
            if not replies:      # 沒實質回覆＝沒人真查，不算查核樣本
                continue
            txt = (n.get("text") or "").strip()
            if len(txt) < 20:    # 純連結／單詞雜訊
                continue
            out.append({
                "id": n["id"],
                "text": txt[:1200],
                "created": n["createdAt"][:10],
                "url": f"https://cofacts.tw/article/{n['id']}",
                "feedback_count": sum(a.get("feedbackCount") or 0 for a in replies),
                "replies": [{"type": a["reply"]["type"],
                             "text": a["reply"]["text"][:400]} for a in replies[:3]],
            })
            if len(out) >= want:
                return out
        cursor = (la.get("pageInfo") or {}).get("lastCursor")
        if not cursor:
            break
        time.sleep(0.4)      # 別把 API 打到 rate limit
    return out


def judge(item):
    body = json.dumps({"title": item["text"][:120],
                       "url": item["url"],
                       "postText": item["text"],
                       "mode": "deep"}).encode()
    req = urllib.request.Request(JUDGE, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=400) as r:
        return json.loads(r.read()), time.perf_counter() - t0


def main(days=7, want=20):
    from datetime import date, timedelta
    since = (date.today() - timedelta(days=days)).isoformat()
    pairs = {}
    for label, types in GROUPS.items():
        rows = fetch(types, since, want)
        print(f"[{label}] {since} 起抓到 {len(rows)} 則")
        pairs[label] = rows
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(pairs, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {OUT}")

    print("\n評分中（mode=deep，每則約 40s）…")
    results = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(judge, it): (label, it)
                for label, rows in pairs.items() for it in rows}
        done = 0
        for fut in as_completed(futs):
            label, it = futs[fut]
            done += 1
            try:
                d, dt = fut.result()
            except Exception as e:
                print(f"  [{label}] ERROR {e}")
                continue
            results.setdefault(label, []).append({
                "id": it["id"], "title": it["text"][:90],
                "score": d.get("final_score"), "rating": d.get("rating_text"),
                "basis": (d.get("scoring_basis") or "")[:70],
                "state": (d.get("deep_analysis") or {}).get("evidence_state"),
                "fc": ((d.get("metrics") or {}).get("fact_check") or {}).get("desc"),
                "sim": round(((d.get("sources") or [{}])[0].get("similarity_score") or 0), 3)
                if d.get("sources") else 0,
                "secs": round(dt, 1),
            })
            print(f"  [{done}/{sum(len(r) for r in pairs.values())}] "
                  f"{label:4s} {d.get('final_score'):6.2f} {d.get('rating_text')}")

    out = os.path.join(os.path.dirname(OUT), "live_cofacts_scores.json")
    json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {out}")
    return results


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 7,
         int(sys.argv[2]) if len(sys.argv) > 2 else 20)
