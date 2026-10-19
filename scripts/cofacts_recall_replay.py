# -*- coding: utf-8 -*-
"""Cofacts 召回/比對離線重放器（確定性驗證工具）。

用途：對固定測資（預設 60 筆 REAL/BAIT/FAKE）逐筆呼叫 cofacts_local.get_fact_check，
      輸出 status / similarity_score / article_id，用來比對「改召回前後」的差異。
      只看 Cofacts 這條路，不經 :5000 server、不經 LLM，所以結果可重現。

跑法：
  cd python && python ../scripts/cofacts_recall_replay.py --out /tmp/x.jsonl
  cd python && python ../scripts/cofacts_recall_replay.py --files eval_bait60_REAL.jsonl

輸出：JSONL，每筆 {id, group, status, sim, article_id, matched_head, ms, n_cands}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(os.path.dirname(HERE), "python")
if PY not in sys.path:
    sys.path.insert(0, PY)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*",
                    default=["eval_bait60_REAL.jsonl", "eval_bait60_BAIT.jsonl",
                             "eval_bait60_FAKE.jsonl"])
    ap.add_argument("--ids", nargs="*", default=None, help="只跑指定 id（如 R03 F06）")
    ap.add_argument("--out", default="/tmp/opencode/cofacts_recall_replay.jsonl")
    ap.add_argument("--tag", default="", help="寫進每筆記錄的標籤（如 before/after）")
    ap.add_argument("--dump-cands", default="",
                    help="同時把每個候選（含門控與 sim）寫到這個 JSONL，供離線調門控")
    args = ap.parse_args()

    import cofacts_local as cl

    items = []
    for f in args.files:
        p = f if os.path.isabs(f) else os.path.join(PY, f)
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
    if args.ids:
        want = set(args.ids)
        items = [it for it in items if it.get("id") in want]
    print(f"[replay] {len(items)} 筆", flush=True)

    dump_fh = open(args.dump_cands, "w", encoding="utf-8") if args.dump_cands else None

    def _dump_candidates(iid, group, snippet):
        """獨立重跑召回並記錄每個候選的門控/sim（供離線調門控用；生產路徑不變）。"""
        rec = {"id": iid, "group": group, "snippet": snippet, "cands": [],
           "q_tok": sorted(cl._numeric_tokens(snippet)),
           "q_tok_d": sorted(cl._numeric_tokens(snippet, include_dates=True))}
        nodes = cl._graphql_recall(snippet, 15)
        cands = [c for c in (cl._classify_candidate(n) for n in nodes) if c]
        for c in cands:
            c["_src"] = "graphql"
        cands.extend({**c, "_src": "local"}
                     for c in cl.local_match_candidates(snippet, top_k=5))
        for c in cands:
            _texts = []
            for _t in (c.get("gate_text") or "", c.get("sim_text") or ""):
                if _t and _t not in _texts:
                    _texts.append(_t)
            _per = {}
            for _i, _t in enumerate(_texts):
                _per[("raw" if _i == 0 else "alt")] = {
                    "entity": bool(cl.entity_gatekeeper(snippet, _t)),
                    "kw": bool(cl._keyword_overlap_gate(snippet, _t)),
                    "tok": sorted(cl._numeric_tokens(_t)),
                    "tok_d": sorted(cl._numeric_tokens(_t, include_dates=True)),
                    "head": _t[:200],
                }
            # 任何一份文本過得了實體+關鍵詞門控，就有機會進榜 → 算 sim（兩份都算，
            # 供離線比較「比原文」vs「比狀態感知文本」兩種策略）
            sim_alt = sim_raw = None
            if any(v["entity"] and v["kw"] for v in _per.values()):
                try:
                    sim_alt = round(float(cl._sbert_sim(
                        snippet, c.get("sim_text") or c.get("gate_text") or "") or 0.0), 4)
                except Exception:
                    sim_alt = 0.0
                if (c.get("gate_text") or "") != (c.get("sim_text") or ""):
                    try:
                        sim_raw = round(float(cl._sbert_sim(
                            snippet, c.get("gate_text") or "") or 0.0), 4)
                    except Exception:
                        sim_raw = 0.0
                else:
                    sim_raw = sim_alt
            rec["cands"].append({
                "src": c.get("_src"), "status": c.get("status"),
                "article_id": c.get("article_id"),
                "per": _per, "sim": sim_alt, "sim_raw": sim_raw,
                "sim_text": (c.get("sim_text") or "")[:400],
                "gate_text": (c.get("gate_text") or "")[:400],
            })
        dump_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        dump_fh.flush()
        return rec

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    hit = {"found": 0, "n": 0}
    by_group: dict = {}
    with open(args.out, "w", encoding="utf-8") as out:
        for it in items:
            text = ((it.get("title") or "") + "。" + (it.get("content") or ""))
            rec = None
            if dump_fh is not None:
                try:
                    rec = _dump_candidates(it.get("id"), it.get("group"), text[:300])
                except Exception as _e:
                    print(f"  ! dump failed {it.get('id')}: {_e}", flush=True)
            t0 = time.time()
            if rec is not None:
                # 有 dump 時不重跑一次 get_fact_check（省一半 API 請求）：結果直接由
                # 候選池推導——與生產路徑同規則（門控通過者取 sim 最高，且需 >= 軟門檻）。
                _ok = [c for c in rec["cands"]
                       if c.get("sim") is not None
                       and c["sim"] >= cl.COFACTS_SOFT_MIN_SIM]
                _best = max(_ok, key=lambda c: c["sim"]) if _ok else None
                r = ({"status": _best["status"], "similarity_score": _best["sim"],
                      "article_id": _best["article_id"],
                      "matched_text": _best.get("sim_text")} if _best
                     else {"status": "not_found", "similarity_score": 0.0})
                ms = round((time.time() - t0) * 1000, 1)
            else:
                try:
                    r = cl.get_fact_check(text, use_cache=False)
                except Exception as e:
                    r = {"status": "error", "note": f"{type(e).__name__}: {e}"}
                ms = round((time.time() - t0) * 1000, 1)
            st = r.get("status")
            sim = r.get("similarity_score") or 0.0
            rec = {
                "tag": args.tag, "id": it.get("id"), "group": it.get("group"),
                "status": st, "sim": round(float(sim), 4),
                "article_id": r.get("article_id"),
                "matched_head": (r.get("matched_text") or "")[:60],
                "n_alt": len(r.get("alternatives") or []),
                "ms": ms,
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            g = it.get("group") or "?"
            by_group.setdefault(g, [0, 0])
            by_group[g][1] += 1
            if st and st not in ("not_found", "error"):
                by_group[g][0] += 1
                hit["found"] += 1
            hit["n"] += 1
            print(f"[{hit['n']}/{len(items)}] {rec['id']} {g} {st} "
                  f"sim={rec['sim']:.3f} {ms:.0f}ms {rec['article_id'] or ''}", flush=True)
    print("==== 有命中（Cofacts 回 status）====")
    for g, (a, b) in sorted(by_group.items()):
        print(f"{g}: {a}/{b} = {a / b:.1%}" if b else f"{g}: 0/0")
    print(f"TOTAL: {hit['found']}/{hit['n']}")
    print(f"out -> {args.out}")


if __name__ == "__main__":
    main()
