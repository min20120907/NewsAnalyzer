# -*- coding: utf-8 -*-
"""分數校準分析 v2（cutoff 60 協定）：Sfinal 五帶 → P(FAKE|band)。

帶界 = 系統自身評級帶（<20 高度可疑 / 20-40 疑似不實 / 40-60 待查證 /
60-75 大致可信 / ≥75 高度可信）；REAL = Sfinal ≥ 60（≈「大致可信」起點）。
輸入：data/eval/clamp_ablation_500.jsonl（final_score + true，500 筆）。
輸出：data/eval/calibration.json；另印 LaTeX 列。
用法：.venv/bin/python scripts/calibration.py
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_JSONL = os.path.join(BASE, "data", "eval", "clamp_ablation_500.jsonl")
OUT_JSON = os.path.join(BASE, "data", "eval", "calibration.json")

BANDS = [(-1e9, 20, "<20", "Highly suspicious"),
         (20, 40, "20--40", "Suspected fake"),
         (40, 60, "40--60", "Unverified"),
         (60, 75, "60--75", "Likely credible"),
         (75, 101, "75--100", "Highly credible")]


def main():
    recs = [json.loads(l) for l in open(IN_JSONL, encoding="utf-8")]
    valid = [r for r in recs
             if not r.get("error") and r.get("final_score") is not None]
    print(f"採集 {len(recs)} 筆，有效 {len(valid)} 筆"
          f"（FAKE {sum(1 for r in valid if r['true']=='FAKE')}）")
    out = {"n_total": len(recs), "n_valid": len(valid),
           "cutoff": 60, "bins": []}
    n_neg = sum(1 for r in valid if float(r["final_score"]) < 0)
    out["n_negative"] = n_neg
    if n_neg:
        print(f"注意：{n_neg} 筆 final_score < 0（已併入 <20 帶）")
    for lo, hi, name, label in BANDS:
        inbin = [r for r in valid if lo <= float(r["final_score"]) < hi]
        n = len(inbin)
        nf = sum(1 for r in inbin if r["true"] == "FAKE")
        row = {"bin": name, "band": label, "n": n, "n_fake": nf,
               "p_fake": round(nf / n, 4) if n else None}
        out["bins"].append(row)
        print(f"Sfinal {name:>8}: n={n:>4}  FAKE={nf:>4}  P(FAKE|S)={row['p_fake']}")
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"已寫入 {OUT_JSON}")
    print("LaTeX rows:")
    for b in out["bins"]:
        pf = "0.000" if b["p_fake"] == 0 else b["p_fake"]
        print(f"  {b['bin']} & {b['n']} & {pf} \\\\")


if __name__ == "__main__":
    main()
