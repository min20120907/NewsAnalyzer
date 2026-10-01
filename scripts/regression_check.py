"""固定回歸集 —— 每次改 Cofacts/評分邏輯後跑一次，取代 25 分鐘的全掃描。

跑：.venv/bin/python scripts/regression_check.py

7 則涵蓋每一個修過的 bug。⚠️ LLM 有溫度，同一輸入的 evidence_state 會在
`full_body_evidence` / `unrelated_evidence` 之間擺動（實測 0052 案同一份輸入
跑出 26.76 與 64.18 兩次，t19 擺動 54.02～78.61），所以**只卡評級邊界，不卡精確分數**：

- `strict=true`     真新聞不得跨進扣分類（<26）。bug 回歸會讓假命中鎖死它。
- `strict=ceiling`  假新聞不得升高（>25）。反方向的 bug：被誤判成查核命中而給高分。
- `strict=false`    完整比對（含評級字串）。給本來就會擺動的案例用。

判定「是否引入新 bug」看有沒有 ✗；✗ 只出現在 strict/ceiling 那幾則才算真問題。
"""
import json, os, sys, time, urllib.request

JUDGE = "http://127.0.0.1:5000/judge"
CASES = os.path.join(os.path.dirname(__file__), "..", "data", "eval",
                     "regression_cases.json")


def main(timeout_each=200):
    cases = json.load(open(CASES, encoding="utf-8"))
    bad = []
    for c in cases:
        # 2026-10-01：回歸集一律用 deep 模式。fast（n=1）有 58 分擺動（實測 sw0
        # 23.83 vs 81.37），會偶發誤報；回歸集要驗的是「修好的東西沒被弄壞」，
        # 那只有在穩定模式下才測得到。deep 的延遲由串行取樣換來。
        body = json.dumps({**c["request"], "mode": "deep"}).encode()
        req = urllib.request.Request(JUDGE, data=body,
                                     headers={"Content-Type": "application/json"})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout_each) as r:
                d = json.loads(r.read())
        except Exception as e:
            print(f"  {c['id']:10s} ERROR {e}")
            bad.append(c["id"])
            continue
        s, rating = d.get("final_score", 0), d.get("rating_text", "?")
        strict = c.get("strict")
        if strict == "ceiling":
            # 真假新聞對照：假新聞必須維持低分（bug 回歸會讓它被誤判成查核命中而升高）
            ok = s <= c["expect_max_score"]
            note = f"不得高於 {c['expect_max_score']:.0f}"
        elif strict:
            # 這則的 bug 一旦回歸，分數會掉進扣分類。只卡「不該跨進去」。
            ok = s >= c["expect_min_score"]
            note = f"不得低於 {c['expect_min_score']:.0f}"
        else:
            ok = (c["expect_min_score"] <= s <= c["expect_max_score"]
                  and rating == c["expect_rating"])
            note = f"期望 {c['expect_min_score']:.0f}~{c['expect_max_score']:.0f} {c['expect_rating']}"
        mark = "  " if ok else "✗ "
        flag = "S" if strict else " "
        print(f"{mark}{flag}{c['id']:10s} {s:6.2f} {rating:6s} "
              f"({time.perf_counter() - t0:5.1f}s)  {c['desc']}")
        dump = os.path.join(os.path.dirname(CASES), "..", "regress_out")
        os.makedirs(dump, exist_ok=True)
        json.dump(d, open(os.path.join(dump, f"{c['id']}.json"), "w"),
                  ensure_ascii=False, indent=1)
        if not ok:
            bad.append(c["id"])
            print(f"             {note}")
    print()
    if bad:
        print(f"FAIL — {len(bad)}/{len(cases)} 不符: {', '.join(bad)}")
        return 1
    print(f"ALL PASS — {len(cases)} 則回歸案例全部符合預期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
