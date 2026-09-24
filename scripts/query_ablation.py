#!/usr/bin/env python3
"""查詢詞策略消融測試：同樣 4 個真實案例 × 6 種查詢組裝法 → 同一 _wsc.search → 同一相關性尺。

策略：
  A full_title  現行線上（整串標題直送）
  B core_first  現行 fallback（去站台後綴、取首段）
  C jieba_top5  jieba TF-IDF 風格關鍵詞（stop 過濾，取 5）
  D keybert     KeyBERT + 本地 SBERT（paraphrase-multilingual），候選＝jieba 1-2gram
  E yake        YAKE（先 jieba 斷詞轉空格文本，無中文停用詞、如實測弱點）
  F gliner      GLiNER zero-shot 實體（人/組織/作品/地/事件），無實體則回退 C
  G qwen        :8088 把標題改寫成一句短查詢（單槽忙則跳過，非必測）

指標（每組打 _wsc.search(q, 6)，Bing scrape＋GoogleNewsRSS 與線上同管線）：
  n_rel   = 結果標題 vs 原標題 SBERT sim ≥ 0.55 的筆數（同事件通常 0.7+，無關 0.2-0.4）
  max_sim = 最高 sim
  sec     = 查詢組裝＋搜尋秒數
  query   = 實際送出的查詢字串（供目視）
結果 append 到 scratch/query_ablation.jsonl，中斷可續跑（同 case+strategy 略過）。

用法：.venv/bin/python scripts/query_ablation.py
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "python"))
SCRATCH = "/home/min20120907/.hermes/cache/scratch"
OUT = os.path.join(SCRATCH, "query_ablation.jsonl")

CASES = [
    {"id": "cna_emi",
     "title": "高雄囡仔陳人豪奪艾美獎 老三台卡通啟蒙動畫之路 | 娛樂 | 中央社 CNA",
     "content": ""},
    {"id": "bitter",
     "title": "苦瓜胜肽真的能有效降血糖嗎？ - Medical News",
     "content": ""},
    {"id": "udn_scooter",
     "title": "交通安全月機車健檢破99萬台 零違規抽獎逾145萬人報名 | 熱門話題 | 要聞 | 經濟日報",
     "content_file": "scooter_body.txt"},
    {"id": "sangye",
     "title": "桑葉茶治糖尿病等各種功效的影片？勿過度解讀效果！",
     "content": ""},
]
for c in CASES:
    if c.get("content_file"):
        try:
            with open(os.path.join(SCRATCH, c["content_file"]), encoding="utf-8") as f:
                c["content"] = f.read()[:600]
        except OSError:
            pass

STOP = {"網傳", "宣稱", "真的", "請問", "消息", "影片", "圖片", "可以", "這是",
        "那是", "是否", "今天", "昨天", "什麼", "如何", "為何", "真的嗎",
        "中央社", "娛樂", "要聞", "熱門話題", "經濟日報", "CNA", "Medical", "News"}


def seg(text):
    import jieba
    return [t.strip("，。、；：『』「」！？!?,. \t|｜-") for t in jieba.cut(text or "")]


def toks_zh(text):
    return [t for t in seg(text)
            if 2 <= len(t) <= 8 and t not in STOP
            and any("一" <= c <= "鿿" for c in t)]


def q_core_first(title):
    core = (title or "").split("|")[0].strip()
    return core.split()[0] if core.split() else core


def q_jieba(title, content, n=5):
    seen, out = set(), []
    for t in toks_zh(title) + toks_zh(content):
        if t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= n:
            break
    return " ".join(out)


_SBERT = None


def sbert():
    global _SBERT
    if _SBERT is None:
        from sentence_transformers import SentenceTransformer
        _SBERT = SentenceTransformer(
            "/home/min20120907/.cache/huggingface/hub/"
            "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/"
            "snapshots/e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
            device="cpu")
    return _SBERT


def q_keybert(title, content, n=5):
    from keybert import KeyBERT
    spaced = " ".join(seg(title + "。" + (content or "")))
    kw = KeyBERT(model=sbert())
    pairs = kw.extract_keywords(spaced, keyphrase_ngram_range=(1, 2),
                                top_n=n, use_mmr=True, diversity=0.5)
    out = [k for k, _ in pairs if k.replace(" ", "") not in STOP]
    return " ".join(out) or q_jieba(title, content)


def q_yake(title, content, n=5):
    import yake
    spaced = " ".join(seg(title + "。" + (content or "")))
    ex = yake.KeywordExtractor(lan="en", n=2, top=n)  # 無中文停用詞：如實測其弱點
    kws = ex.extract_keywords(spaced)
    out = [k.replace(" ", "") for k, _ in kws
           if 1 < len(k.replace(" ", "")) <= 10]
    return " ".join(out) or q_jieba(title, content)


_GLINER = None


def q_gliner(title, content):
    global _GLINER
    try:
        from gliner import GLiNER
        if _GLINER is None:
            _GLINER = GLiNER.from_pretrained("urchade/gliner_multi-v2.1")
        ents = _GLINER.predict_entities(
            (title or "")[:200], ["人物", "組織", "作品", "地點", "事件"])
        keep = []
        for e in sorted(ents, key=lambda x: -x.get("score", 0)):
            t = (e.get("text") or "").strip()
            if t and len(t) >= 2 and t not in keep:
                keep.append(t)
            if len(keep) >= 4:
                break
        return " ".join(keep) or q_jieba(title, content)
    except Exception as e:
        return f"GLINER_FAIL:{e}"


def q_qwen(title):
    import re
    import requests
    p = ("把下列新聞標題改寫成一句 8 到 12 字的網路搜尋查詢，只輸出查詢本身：\n" + title + "\n/no_think")
    r = requests.post("http://127.0.0.1:8088/v1/chat/completions",
                      json={"model": "qwen3.8-27b-fastmtp",
                            "messages": [{"role": "user", "content": p}],
                            "max_tokens": 1024, "temperature": 0.1,
                            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
                      timeout=90)
    r.raise_for_status()
    txt = r.json()["choices"][0]["message"]["content"] or ""
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    return (lines[-1] if lines else txt).strip()[:40]


STRATS = ["A", "B", "C", "D", "E", "F", "G"]


def build(strategy, case):
    t, c = case["title"], case.get("content", "")
    if strategy == "A":
        return t
    if strategy == "B":
        return q_core_first(t)
    if strategy == "C":
        return q_jieba(t, c)
    if strategy == "D":
        return q_keybert(t, c)
    if strategy == "E":
        return q_yake(t, c)
    if strategy == "F":
        return q_gliner(t, c)
    if strategy == "G":
        return q_qwen(t)
    raise ValueError(strategy)


def sim(a, b):
    from sentence_transformers import util
    import torch
    m = sbert()
    with torch.no_grad():
        e = m.encode([a, b], convert_to_tensor=True)
    return float(util.cos_sim(e[0], e[1]).item())


def done():
    have = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    have.add((r["case"], r["strategy"]))
                except Exception:
                    pass
    return have


def main():
    import web_search_client as wsc
    have = done()
    for case in CASES:
        for st in STRATS:
            if (case["id"], st) in have:
                print(f"skip {case['id']}/{st}", flush=True)
                continue
            t0 = time.perf_counter()
            rec = {"case": case["id"], "strategy": st}
            try:
                q = build(st, case)
                rec["query"] = q
                if q.startswith("GLINER_FAIL:"):
                    rec["error"] = q
                else:
                    res = wsc.search(q, max_results=6) or []
                    sims = [round(sim(case["title"], (r.get("title") or "")), 3)
                            for r in res]
                    rec["n_results"] = len(res)
                    rec["sims"] = sims
                    rec["n_rel"] = sum(1 for s in sims if s >= 0.55)
                    rec["max_sim"] = max(sims) if sims else 0.0
                    rec["titles"] = [(r.get("title") or "")[:40] for r in res]
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"[:200]
            rec["sec"] = round(time.perf_counter() - t0, 1)
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"{case['id']}/{st}: q={rec.get('query', '')[:30]} "
                  f"n_rel={rec.get('n_rel')} max={rec.get('max_sim')} "
                  f"{rec.get('sec')}s {rec.get('error', '')}", flush=True)


if __name__ == "__main__":
    main()
