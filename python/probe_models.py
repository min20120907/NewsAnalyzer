"""探測每個候選模型是否真的能回覆（不只 /v1/models 有列出來）。

/models 回 200 不代表能推理——deep-proxy 就是這樣被 ban 的。
回 [ok, latency_s, error]
"""
import sys, os, time, json, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from llm_registry import BACKENDS, model_catalog, api_key_for, request_headers

PROBE = "用一句話回答：台灣的中央氣象署在2023年改制前叫什麼？只回答案。"
TIMEOUT = int(os.environ.get("PROBE_TIMEOUT", "60"))


def probe(item):
    mid = item["id"]
    cfg = BACKENDS[item["backend"]]
    url = cfg["base_url"]
    headers = request_headers(cfg)
    t0 = time.perf_counter()
    # max_tokens 4000：推理模型（如 apodex）reasoning 會吃掉小 budget，
    # 400 會造成 content 全空 (finish=length) 的假陽性（2026-10-03 實測）。
    try:
        r = requests.post(url, headers=headers, json={
            "model": item["model"],
            "messages": [{"role": "user", "content": PROBE}],
            "max_tokens": 4000,         # 太小會被 thinking 吃光（實測）
            "temperature": 0.1,
            "stream": False,
        }, timeout=TIMEOUT)
        el = round(time.perf_counter() - t0, 1)
        if r.status_code != 200:
            return mid, False, el, f"HTTP {r.status_code}: {r.text[:110]}"
        ch = (r.json().get("choices") or [{}])[0]
        txt = (ch.get("message") or {}).get("content") or ""
        if not txt.strip():
            return mid, False, el, f"content 空 (finish={ch.get('finish_reason')})"
        return mid, True, el, txt.strip()[:60]
    except Exception as e:
        return mid, False, round(time.perf_counter() - t0, 1), f"{type(e).__name__}: {str(e)[:100]}"


def main():
    items = model_catalog(include_disabled=True)
    results = []
    # 本機單槽不能併發 → 排除 local，其餘併發
    cloud = [i for i in items if not i["local"]]
    # 2026-10-03：agy 也是單槽（agy_shim 全域鎖，每個請求 spawn 一個 CLI）。
    # 用併發 6 會讓後面 5 個排在鎖裡，超過 client 端 timeout 全部誤判失敗
    # （實測單打 2.0s 成功，併發時 156s read timeout）。改成兩批。
    serial = [i for i in cloud if i["backend"] == "agy"]
    parallel = [i for i in cloud if i["backend"] != "agy"]
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(probe, parallel):
            results.append(res)
    for item in serial:
        results.append(probe(item))
    results.sort()

    ok = [r for r in results if r[1]]
    print(f"{'':46} {'OK':4} {'秒':>6}  說明")
    print("-" * 96)
    for mid, good, el, note in results:
        print(f"{mid:46} {'✅' if good else '❌':4} {el:>6}  {note}")
    print(f"\n可用 {len(ok)}/{len(results)}")
    json.dump([{"model": m, "ok": g, "lat_s": e, "note": n} for m, g, e, n in results],
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "data", "eval", "model_probe.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()