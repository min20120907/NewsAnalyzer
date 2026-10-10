# -*- coding: utf-8 -*-
"""四區準確度：各區最可信資料集分層抽 100（日文 85），打 /judge 全管線，cutoff 60 二值化。

- tw：本地 Cofacts corpus 50 FAKE＋50 REAL（擾動：網傳前綴＋截尾85%，避原文快取直中；
  同域索引內檢索，數字解讀見誠實註記）
- en：LIAR test 6 標籤各~17（pants/false/barely→FAKE；half/mostly/true→REAL）
- ja：Murayama 4 假標籤各20＋全 REAL（僅 5 筆，n=85）
- cn：WSDM 簡體 50/50（is_fake，限 ≥20 字；跨域遷移分數，非主用途）

Usage: .venv/bin/python scripts/zone_accuracy_100.py [--only tw|en|ja|cn]
輸出 data/eval/zone_acc_<zone>.jsonl（續跑）＋ zone_acc_summary.json。
單筆約 13s，四區約 85 分鐘 → 背景跑。
"""
import csv
import json
import os
import random
import sqlite3
import sys

import requests

SERVER = "http://127.0.0.1:5000"
EV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "..", "data", "eval")
SEED = 42
# 單筆上限 300s：病態輸入會疊滿萃取＋deep 逾時（實測 CN 探針撞過 150s 牆）；
# 逾時記 error 排除，不重試（重試只會再燒一次配額與 slot）
TIMEOUT = 300
# deep 模式要 X-Debug-Token（/debug_login 取；帳密見服務端 NEWSANALYZER_DEBUG_*
# env，無則為源碼預設值）。非 debug 一律 fast（n=1），回應掛 mode=deep 也一樣。
_DEBUG_TOKEN = ""


def _debug_login():
    global _DEBUG_TOKEN
    user = os.environ.get("NEWSANALYZER_DEBUG_USER", "min20120907")
    pw = os.environ.get("NEWSANALYZER_DEBUG_PASSWORD", "jefflin123")
    try:
        r = requests.post(f"{SERVER}/debug_login",
                          json={"account": user, "password": pw}, timeout=20)
        if r.status_code == 200 and r.json().get("ok"):
            _DEBUG_TOKEN = r.json().get("token", "")
            print("debug login ok")
            return True
    except Exception as e:  # noqa: BLE001
        print(f"debug login failed: {e}")
    return False


def _post(title, content, mode="fast"):
    headers = {}
    if mode == "deep":
        if not _DEBUG_TOKEN and not _debug_login():
            return {"error": "debug login failed, cannot run deep mode"}
        headers = {"X-Debug-Token": _DEBUG_TOKEN}
    try:
        r = requests.post(f"{SERVER}/judge",
                          json={"title": title, "content": content,
                                "mode": mode},
                          headers=headers, timeout=TIMEOUT)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:100]}


def _verdict(d):
    if "final_score" not in d:
        return None
    return "REAL" if d["final_score"] >= 60 else "FAKE"


def _sample_tw():
    rnd = random.Random(SEED)
    con = sqlite3.connect(os.path.join(EV, "..", "cofacts",
                                       "cofacts_cache.db"))
    fake = [r[0] for r in con.execute(
        "SELECT text FROM corpus WHERE status IN ('inaccurate','partial')")]
    real = [r[0] for r in con.execute(
        "SELECT text FROM corpus WHERE status='accurate'")]
    out = []
    for t in rnd.sample(fake, 50):
        body = t[:max(10, int(len(t) * 0.85))]
        out.append(("網傳：" + body, "FAKE"))
    for t in rnd.sample(real, 50):
        body = t[:max(10, int(len(t) * 0.85))]
        out.append(("網傳：" + body, "REAL"))
    rnd.shuffle(out)
    return out


def _sample_en():
    rnd = random.Random(SEED)
    rows = list(csv.reader(open(os.path.join(EV, "liar_test.tsv"),
                                encoding="utf-8"), delimiter="\t"))
    by_label: dict = {}
    for r in rows:
        if len(r) >= 3 and len(r[2].strip()) >= 20:
            by_label.setdefault(r[1], []).append(r[2])
    out = []
    per = {k: 17 for k in by_label}
    per["true"] = 15  # 17*5+15=100
    for lab, n in per.items():
        truth = ("FAKE" if lab in ("pants-fire", "false", "barely-true")
                 else "REAL")
        for t in rnd.sample(by_label[lab], min(n, len(by_label[lab]))):
            out.append((t, truth))
    rnd.shuffle(out)
    return out


def _sample_ja():
    rnd = random.Random(SEED)
    rows = list(csv.DictReader(open(os.path.join(EV, "murayama_label.tsv"),
                                    encoding="utf-8"), delimiter="\t"))
    fake_labels = ["False", "Misleading", "Inaccurate", "Pants-on-Fire"]
    out = []
    for lab in fake_labels:
        pool = [r["Article"] for r in rows if r["Q1"] == lab
                and len(r["Article"].strip()) >= 20]
        for t in rnd.sample(pool, min(20, len(pool))):
            out.append((t, "FAKE"))
    for r in rows:
        if r["Q1"] in ("True", "Half-True"):
            out.append((r["Article"], "REAL"))
    rnd.shuffle(out)
    return out


def _gnews_titles(query, hl="ja", gl="JP", ceid="JP:ja", limit=40):
    """Google News RSS 標題（主流媒體即時新聞，視為 REAL——同 48 篇掃描方法學）。"""
    import urllib.parse
    import xml.etree.ElementTree as ET
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote_plus(query)
           + f"&hl={hl}&gl={gl}&ceid={ceid}")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                     timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip()
        if len(t) >= 20:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def _sample_ja_real(n=50):
    rnd = random.Random(SEED)
    pool, seen = [], set()
    for q in ["日本 政治", "日本 経済", "国際 ニュース", "スポーツ",
              "科学 テクノロジー", "社会"]:
        try:
            for t in _gnews_titles(q):
                if t not in seen:
                    seen.add(t)
                    pool.append(t)
        except Exception:
            pass
    return [(t, "REAL") for t in rnd.sample(pool, min(n, len(pool)))]


def _sample_cn():
    rnd = random.Random(SEED)
    rows = [r for r in csv.DictReader(
        open(os.path.join(EV, "wsdm_fake_news_2000.csv"), encoding="utf-8"))
        if len((r.get("news_title") or "").strip()) >= 20]
    fake = [r["news_title"] for r in rows if r.get("is_fake") == "true"]
    real = [r["news_title"] for r in rows if r.get("is_fake") == "false"]
    out = [(t, "FAKE") for t in rnd.sample(fake, 50)]
    out += [(t, "REAL") for t in rnd.sample(real, 50)]
    rnd.shuffle(out)
    return out


SAMPLERS = {"tw": _sample_tw, "en": _sample_en,
            "ja": _sample_ja, "cn": _sample_cn,
            "ja_real": lambda: _sample_ja_real(50)}


def run_zone(zone, mode="fast"):
    os.makedirs(EV, exist_ok=True)
    suffix = "" if mode == "fast" else f"_{mode}"
    out_path = os.path.join(EV, f"zone_acc_{zone}{suffix}.jsonl")
    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["idx"])
                except Exception:
                    pass
    samples = SAMPLERS[zone]()
    fout = open(out_path, "a", encoding="utf-8")
    n_new = 0
    for i, (text, truth) in enumerate(samples):
        if i in done:
            continue
        d = _post(text[:60], text, mode=mode)
        v = _verdict(d)
        src_map = None
        if isinstance(d.get("sources"), list):
            src_map = {s.get("source"): s.get("status")
                       for s in d["sources"] if isinstance(s, dict)}
        fs = d.get("final_score")
        rec = {"idx": i, "truth": truth, "pred": v,
               "final": (round(float(fs), 1)
                         if isinstance(fs, (int, float)) else None),
               "sources": src_map,
               "error": d.get("error")}
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()
        n_new += 1
        if n_new % 10 == 0:
            print(f"[{zone}] {n_new} done", flush=True)
    fout.close()
    # 汇总
    recs = [json.loads(l) for l in open(out_path, encoding="utf-8")]
    valid = [r for r in recs if r["pred"]]
    tp = sum(1 for r in valid if r["pred"] == "FAKE" and r["truth"] == "FAKE")
    tn = sum(1 for r in valid if r["pred"] == "REAL" and r["truth"] == "REAL")
    fp = sum(1 for r in valid if r["pred"] == "FAKE" and r["truth"] == "REAL")
    fn = sum(1 for r in valid if r["pred"] == "REAL" and r["truth"] == "FAKE")
    acc = (tp + tn) / len(valid) if valid else 0.0
    p_fake = tp / (tp + fp) if tp + fp else 0.0
    r_fake = tp / (tp + fn) if tp + fn else 0.0
    return {"n": len(recs), "valid": len(valid),
            "skipped": len(recs) - len(valid),
            "accuracy": round(acc, 4),
            "P_fake": round(p_fake, 4), "R_fake": round(r_fake, 4),
            "TP": tp, "TN": tn, "FP": fp, "FN": fn}


def main():
    only = (sys.argv[sys.argv.index("--only") + 1]
            if "--only" in sys.argv else None)
    mode = (sys.argv[sys.argv.index("--mode") + 1]
            if "--mode" in sys.argv else "fast")
    summary_path = os.path.join(EV, "zone_acc_summary.json")
    summary = {}
    if os.path.exists(summary_path):
        try:
            summary = json.load(open(summary_path, encoding="utf-8"))
        except Exception:
            summary = {}
    for zone in SAMPLERS:
        if only and zone != only:
            continue
        s = run_zone(zone, mode=mode)
        summary[zone if mode == "fast" else f"{zone}_{mode}"] = s
        print(zone, json.dumps(s, ensure_ascii=False), flush=True)
        json.dump(summary, open(summary_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
