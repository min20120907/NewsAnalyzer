# -*- coding: utf-8 -*-
"""離線評估門控組合對 60 筆測資的影響（不碰網路）。

輸入：scripts/cofacts_recall_replay.py --dump-cands 產出的候選池 JSONL。
維度：
  gate text 策略：raw（只比轉傳原文，舊行為）/ alt（只比狀態感知文本）/ union（任一通過）
  numeric 模式  ：off / soft / strict / softd / strictd（見 cofacts_local._numeric_gate）
  sim 文本策略  ：alt（狀態感知，現行）/ raw
輸出：每組的 REAL/BAIT/FAKE status 分布、風險清單，以及相對基準的變動。

風險定義（依 downstream 語意）：
  FAKE + accurate（sim>=0.72 硬命中）= 捏造新聞被查核「屬實」→ 高分風險（最壞）
  REAL + inaccurate                  = 真新聞被判不實 → -30 鎖死（最壞）
  REAL + partial                     = 真新聞落 partially_refutes（40-55）→ 中風險
  FAKE + inaccurate/partial          = 假新聞被判不實 → 正確方向（好事）

跑法：python scripts/eval_numeric_gate.py /tmp/opencode/cands_dump2.jsonl
"""
import json
import sys

SOFT_MIN = 0.55
HARD_MIN = 0.72


def tok_set(c, txt, d):
    v = c.get("per", {}).get(txt)
    if not v:
        return None
    return set(v["tok_d"] if d else v["tok"])


def gate_pass(c, q_set, txt, num_mode):
    v = c.get("per", {}).get(txt)
    if not v or not (v["entity"] and v["kw"]):
        return False
    if num_mode == "off":
        return True
    d = num_mode.endswith("d")
    q = set(q_set["d"] if d else q_set["plain"])
    ct = set(v["tok_d"] if d else v["tok"])
    if len(q) < 2:
        return True
    if not ct:
        return not num_mode.startswith("strict")
    return bool(q & ct)


def outcome(rec, txt_policy, num_mode, sim_policy="alt"):
    q_set = {"plain": rec["q_tok"], "d": rec["q_tok_d"]}
    best = None
    for c in rec["cands"]:
        texts = [k for k in ("raw", "alt") if k in c.get("per", {})]
        if txt_policy == "raw":
            texts = [k for k in texts if k == "raw"]
        elif txt_policy == "alt":
            texts = [k for k in texts if k == "alt"]
        if not any(gate_pass(c, q_set, k, num_mode) for k in texts):
            continue
        sim = c.get("sim") if sim_policy == "alt" else c.get("sim_raw")
        if sim is None or sim < SOFT_MIN:
            continue
        if best is None or sim > best[1]:
            best = (c["status"], sim, c.get("article_id"))
    return best


def fmt(agg):
    parts = []
    for st in ("accurate", "partial", "inaccurate", "not_found"):
        if agg.get(st):
            hard = sum(1 for s in agg[st] if s >= HARD_MIN)
            parts.append(f"{st}={len(agg[st])}" + (f"(硬{hard})" if hard else ""))
    return "  ".join(parts)


COMBOS = [
    ("raw/off", "raw", "off"),
    ("union/off", "union", "off"),
    ("union/soft", "union", "soft"),
    ("union/strict", "union", "strict"),
    ("union/softd", "union", "softd"),
    ("union/strictd", "union", "strictd"),
    ("alt/off", "alt", "off"),
]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/cands_dump2.jsonl"
    recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    print(f"測資 {len(recs)} 筆｜軟門檻 {SOFT_MIN}｜硬門檻 {HARD_MIN}")
    print("欄位＝status 筆數；「硬」＝sim>=0.72（不經 LLM 直接採信）\n")
    base = None
    summary = []
    for label, pol, nm in COMBOS:
        aggby = {}
        hard_fake_ok = []
        fake_acc = []
        real_bad = []
        for r in recs:
            b = outcome(r, pol, nm)
            st, sim = (b[0], b[1]) if b else ("not_found", 0.0)
            aggby.setdefault(r["group"], {}).setdefault(st, []).append(sim)
            if r["group"] == "FAKE" and st == "accurate":
                fake_acc.append(f"{r['id']}({sim:.3f})")
                if sim >= HARD_MIN:
                    hard_fake_ok.append(r["id"])
            if r["group"] == "REAL" and st in ("inaccurate",):
                real_bad.append(f"{r['id']}({st} {sim:.3f})")
        row = {g: {st: len(v) for st, v in d.items()} for g, d in aggby.items()}
        if base is None:
            base = {r["id"]: (outcome(r, pol, nm) or ("not_found", 0.0))[0] for r in recs}
        chg = []
        for r in recs:
            st = (outcome(r, pol, nm) or ("not_found", 0.0))[0]
            if st != base[r["id"]]:
                chg.append(f"{r['id']}:{base[r['id']][:4]}→{st[:4]}")
        hit_real = sum(1 for v in aggby.get("REAL", {}).items() if v[0] != "not_found" for _ in v[1])
        print(f"===== {label} =====")
        for g in ("REAL", "BAIT", "FAKE"):
            print(f"  {g:5s} {fmt(aggby.get(g, {}))}")
        print(f"  FAKE→accurate {len(fake_acc)}（硬 {len(hard_fake_ok)}）：{', '.join(fake_acc)}")
        print(f"  REAL→inaccurate {len(real_bad)}：{', '.join(real_bad) if real_bad else '（無）'}")
        print(f"  變動 {len(chg)}：{', '.join(chg)}\n")
        summary.append((label, hit_real, len(hard_fake_ok), len(real_bad), len(fake_acc)))
    print("===== 總結 =====")
    print(f"{'組合':14s}{'REAL有命中':>10s}{'FAKE硬命中':>10s}{'REAL不實':>10s}{'FAKE屬實':>10s}")
    for label, hr, hf, rb, fa in summary:
        print(f"{label:14s}{hr:>10d}{hf:>10d}{rb:>10d}{fa:>10d}")


if __name__ == "__main__":
    main()
