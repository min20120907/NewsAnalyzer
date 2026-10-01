"""驗證 (a) 查核命中 (b) web_results 是否真的與新聞主題吻合。

量法：SBERT cosine，新聞標題 vs 查核 matched_text / web_results title。
門檻沿用 skill 已驗證的 0.45（RSS 噪音過濾）。
"""
import json, sys, collections, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from sentence_transformers import SentenceTransformer

MODEL = ("/home/min20120907/.cache/huggingface/hub/models--sentence-transformers--"
         "paraphrase-multilingual-MiniLM-L12-v2/snapshots/"
         "e8f8c211226b894fcb81acc59f3b34ba3efd5f42")  # 與後端硬編碼路徑一致
m = SentenceTransformer(MODEL, device="cpu")


def cos(a, b):
    import numpy as np
    v = m.encode([a, b], normalize_embeddings=True, convert_to_numpy=True)
    return float(v[0] @ v[1])


def main():
    rows = [json.loads(l) for l in open(
        os.path.join(os.path.dirname(__file__), "..", "data/eval/tw_media_sweep.jsonl"),
        encoding="utf-8") if l.strip()]
    ok = [r for r in rows if not r.get("error")]

    # (a) 查核吻合度
    print("=== (a) 查核命中 vs 主題吻合 ===")
    for r in ok:
        for s in (r.get("sources") or []):
            st = s.get("status")
            if st in ("not_found", "disabled", "error"):
                continue
            mt = (s.get("matched_text") or "").strip()
            if not mt:
                print(f"  [無比對文本] {st:10s} {r['title'][:40]}")
                continue
            sim = cos(r["title"], mt)
            flag = "OK " if sim >= 0.45 else "✗不吻合"
            print(f"  {flag} sim={sim:.3f} {st:10s} {r['title'][:38]}")
            print(f"          matched: {mt[:70]}")

    # (b) web_results 吻合度
    print("\n=== (b) web_results 主題吻合 ===")
    buckets = collections.defaultdict(list)
    for r in ok:
        for w in (r.get("web_results") or []):
            t = (w.get("title") or "").strip()
            if t:
                buckets[cos(r["title"], t)].append((r["title"][:34], t[:44], w.get("source")))
    if not buckets:
        print("  無資料"); return
    sims = sorted(buckets)
    pairs = [x for v in buckets.values() for x in v]
    lo = [x for s, v in buckets.items() if s < 0.45 for x in v]
    hi = [x for s, v in buckets.items() if s >= 0.45 for x in v]
    print(f"  筆數 {len(pairs)}  吻合(>=0.45) {len(hi)}  不吻合 {len(lo)}"
          f"  ({len(hi)/len(pairs)*100:.0f}% 吻合)")
    print(f"  sim 分位: p10={sims[len(sims)//10]:.3f} 中位={sims[len(sims)//2]:.3f} "
          f"p90={sims[len(sims)*9//10]:.3f}")
    print("\n  --- 最低 8 筆（可疑）---")
    for s in sorted(buckets)[:8]:
        for t, wt, src in buckets[s]:
            print(f"   sim={s:.3f} [{src}]\n     新聞: {t}\n     結果: {wt}")
    print("\n  --- 最高 3 筆 ---")
    for s in sorted(buckets)[-3:]:
        for t, wt, src in buckets[s]:
            print(f"   sim={s:.3f} [{src}] {t} ←→ {wt}")


if __name__ == "__main__":
    main()