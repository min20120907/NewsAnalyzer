"""模型實測：每個候選跑真實 deep_analyze，看能不能產出可解析的中文 JSON。

這是選模型的最後一道 gate——/v1/models 有列出、能回答簡單問題 ≠
能在真實評分 prompt 裡產出正確 JSON。實測已證：
  nemotron-ultra → finish=length，3233 token 全在英文推理，JSON 產出 0
  dots-3-note → 回簡體「中央气象局」
所以只探測活著不夠，必須跑真 prompt。

執行：cd python && ../.venv/bin/python eval_models_real.py
"""
import sys, os, time, json, concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_news_server_new as F
from llm_registry import model_catalog

# 真實案例（來自實際謠言，附真實對照證據）
CASE_FAKE = {
    "title": "氣象局緊急通知：北部明起「紫爆」大雨特報，恐有 300 毫米豪雨，務必留在室內",
    "content": "氣象局緊急通知：北部明起「紫爆」大雨特報，恐有 300 毫米豪雨，務必留在室內",
    "web": [{"title": "16縣市豪大雨特報！氣象署：恐有短延時強降雨", "snippet": "氣象署針對16縣市發布大雨特報"},
            {"title": "台南、高屏停班課 氣象署估下週一雨勢趨緩", "snippet": "嘉義以南局部豪雨，東半部雨勢增強"}],
    "truth": "假（機構應為氣象署、地點是南部非北部、300mm 無來源）",
}
CASE_REAL = {
    "title": "台南、高屏停班課 氣象署估下週一雨勢趨緩",
    "content": "受到西南風偏強及低壓帶影響，全台降雨明顯。氣象署表示，這波雨勢將持續到下週二清晨，嘉義以南局部會有豪雨以上等級的降雨。",
    "web": [{"title": "氣象署發「16縣市」大雨特報", "snippet": "氣象署針對16縣市發布大雨特報"}],
    "truth": "真（真實氣象署新聞）",
}
SOURCES = [{"source": "cofacts", "status": "no_evidence"}]


def has_han(s, n=20):
    return sum(1 for c in (s or "") if "一" <= c <= "鿿")


def run_model(mid):
    out = {"model": mid}
    for tag, case in (("fake", CASE_FAKE), ("real", CASE_REAL)):
        t0 = time.perf_counter()
        try:
            r = F.deep_analyze(case["title"], case["web"], SOURCES,
                               timeout=120, content=case["content"], model_id=mid)
        except Exception as e:
            out[tag] = {"error": f"{type(e).__name__}: {str(e)[:80]}"}
            continue
        el = round(time.perf_counter() - t0, 1)
        cs = r.get("credibility_score")
        txt = " ".join(str(r.get(k, "")) for k in
                       ("claim", "analysis", "key_points", "viewpoints"))
        out[tag] = {
            "cs": cs, "lat_s": el, "state": r.get("evidence_state"),
            "abstain": bool(r.get("abstain")),
            "han": has_han(txt), "len": len(txt),
            "sample": (r.get("analysis") or r.get("claim") or "")[:120],
        }
    # 判定
    ok_both = all(out.get(t, {}).get("cs") is not None for t in ("fake", "real"))
    han_ok = all(out.get(t, {}).get("han", 0) >= 20 for t in ("fake", "real"))
    sep = None
    if ok_both:
        sep = abs((out["real"]["cs"] or 0) - (out["fake"]["cs"] or 0))
    out["usable"] = bool(ok_both and han_ok)
    out["separation"] = sep
    return out


def main():
    items = [m["id"] for m in model_catalog(include_disabled=True) if not m["local"]]
    results = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(run_model, items):
            results.append(r)

    print(f"{'模型':44} {'假':>4} {'真':>4} {'差':>4} {'中':>3} {'秒':>6}  狀態")
    print("-" * 96)
    def cell(v, w=4):
        """任何東西都能安全塞進固定寬欄。dict/list 顯示摘要，不炸。"""
        if isinstance(v, dict):
            v = list(v)[:2]
        if isinstance(v, list):
            v = ",".join(map(str, v))
        if v is None:
            return "—".rjust(w)
        return str(v)[:w].rjust(w)


    for r in sorted(results, key=lambda x: -(x.get("separation") or 0)
                    if isinstance(x.get("separation"), (int, float)) else 0):
        f, rl = r.get("fake", {}), r.get("real", {})
        if f.get("error") or rl.get("error"):
            print(f"{str(r['model'])[:44]:44} {'ERR':>4} {'':>4} {'':>4} {'':>3} {'':>6}  "
                  f"{f.get('error') or rl.get('error')}")
            continue
        sep = r.get("separation") if isinstance(r.get("separation"), (int, float)) else None
        tag = "✅ 可用" if r["usable"] else "❌ 不可用"
        why = ""
        if not r["usable"]:
            missing = [t for t in ("fake", "real") if r.get(t, {}).get("cs") is None]
            if missing:
                why = f"{'/'.join(missing)} 沒產出分數"
            elif not all(r.get(t, {}).get("han", 0) >= 20 for t in ("fake", "real")):
                why = "中文太少"
        print(f"{str(r['model'])[:44]:44} {cell(f.get('cs'))} {cell(rl.get('cs'))} "
              f"{cell(sep)} {'✓' if f.get('han',0)>=20 and rl.get('han',0)>=20 else '✗':>3} "
              f"{cell(f.get('lat_s', 0), 6)}  {tag} {why}")
        if r["usable"]:
            print(f"{'':44} └ 假新聞理由: {f.get('sample','')[:88]}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "data", "eval", "model_eval.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    ok = [r for r in results if r["usable"]]
    print(f"\n可用 {len(ok)}/{len(results)}")
    if ok:
        best = max(ok, key=lambda x: x["separation"])
        print(f"分離度最佳: {best['model']} (假{best['fake']['cs']} vs 真{best['real']['cs']})")


if __name__ == "__main__":
    main()