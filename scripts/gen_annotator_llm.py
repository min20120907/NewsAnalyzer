#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生標註工作表用 LLM 輸出（30 篇台灣新聞 × Qwen3.8-27B :8088）。
提示詞 = 生產線 deep_analyze 同源（4 欄 JSON schema），改為【新聞全文】單一材料 + 任務提示。
輸出：data/eval/annotator_llm_30.jsonl（逐筆：編號/任務/完整JSON原文/解析後4欄/J欄文字）。可續跑。
用法：~/.venvs/plots/bin/python scripts/gen_annotator_llm.py
（需 :8088 閒置；與 cm_system_500 背景任務互斥，sequential 執行）
"""
import json
import os
import re
import time

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JSONL = os.path.join(BASE, "data", "eval", "annotator_llm_30.jsonl")
SRC_XLSX = "/home/min20120907/.hermes/cache/documents/doc_104615147af2_台灣新聞可信度測試資料集.xlsx"

QWEN_URL = os.environ.get("QWEN_URL", "http://127.0.0.1:8088/v1/chat/completions")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3.8-27b-fastmtp")
TIMEOUT = 180

TASK_HINT = {
    "credibility": "本次任務重點：綜合判斷整篇的可信度，analysis 須明確給出可信/可疑的結論與理由。",
    "viewpoints": "本次任務重點：充實 viewpoints，正反雙方立場都要呈現，不可只寫單方說法。",
    "analysis": "本次任務重點：充實 analysis，100字內講清核心事實、爭議點與你的判斷。",
    "key_points": "本次任務重點：充實 key_points，至少列出2個值得質疑的點（證據、來源、邏輯任選）。",
}

PROMPT_TMPL = """你是一個事實查核分析助手。根據以下【新聞文本】，只輸出一個 JSON 物件（不要任何其他文字），格式：
{{"key_points":["質疑點1","質疑點2"],"viewpoints":"正反觀點摘要(80字內)","credibility_score":0到100的整數,"analysis":"100字內總結"}}
【語言】所有欄位一律使用繁體中文完整句子，嚴禁出現英文單字或中英夾雜（外來專有名詞也譯為中文）。
【忠實】只能依據【新聞文本】所給內容分析；若文本開頭標示「搜尋摘要」，代表非完整原文，不可腦補原文沒有的細節，並在 analysis 加註「僅依摘要判斷」。
【評分】credibility_score：文本證據充足、來源明確取高分（70-95）；有誇張標題、證據不足、來源不明取低分（10-40）；資訊過少無法判斷取 50-65 並明說原因。
{task_hint}
【新聞文本】
{text}
"""


def parse_json(resp):
    try:
        return json.loads(resp)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", resp, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"\{.*\}", resp, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def to_j(task, p):
    score = p.get("credibility_score", "")
    kp = p.get("key_points", []) or []
    if task == "credibility":
        return f"可信度分數：{score}/100\n{p.get('analysis', '')}"
    if task == "viewpoints":
        return p.get("viewpoints", "")
    if task == "analysis":
        return p.get("analysis", "")
    if task == "key_points":
        return "\n".join(f"{i+1}. {k}" for i, k in enumerate(kp))
    return p.get("analysis", "")


def main():
    import openpyxl
    wb = openpyxl.load_workbook(SRC_XLSX, read_only=True, data_only=True)
    rows = list(wb["新聞資料"].iter_rows(values_only=True))[1:]
    assert len(rows) == 30

    done = {}
    if os.path.exists(OUT_JSONL):
        for line in open(OUT_JSONL, encoding="utf-8"):
            try:
                r = json.loads(line)
                done[r["編號"]] = r
            except Exception:
                pass
    print(f"30 篇，已完成 {len(done)} 篇", flush=True)
    fout = open(OUT_JSONL, "a", encoding="utf-8")
    t_all = time.perf_counter()
    for r in rows:
        cat, code, title, media, url, text, prompt, task = r[:8]
        if code in done:
            continue
        t0 = time.perf_counter()
        raw, err = "", None
        try:
            resp = requests.post(
                QWEN_URL,
                json={"model": QWEN_MODEL,
                      "messages": [
                          {"role": "system",
                           "content": "你是一個事實查核分析助手。根據提供的資訊，只輸出一個 JSON 物件（不要任何其他文字）。"},
                          {"role": "user",
                           "content": PROMPT_TMPL.format(
                               task_hint=TASK_HINT.get(task, ""),
                               text=f"標題：{title}\n媒體：{media}\n{text}")}],
                      "temperature": 0.2, "max_tokens": 800, "stream": False,
                      "response_format": {"type": "json_object"},
                      "chat_template_kwargs": {"enable_thinking": False}},
                timeout=TIMEOUT)
            raw = resp.json()["choices"][0]["message"].get("content") or ""
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        p = parse_json(raw) if raw else {}
        try:
            score = max(0, min(100, int(p.get("credibility_score", 0))))
        except (TypeError, ValueError):
            score = 0
        parsed = {"key_points": p.get("key_points", []),
                  "viewpoints": p.get("viewpoints", ""),
                  "credibility_score": score,
                  "analysis": p.get("analysis", "")}
        rec = {"編號": code, "類別": cat, "任務": task, "lat_s": round(time.perf_counter() - t0, 1),
               "raw": raw, "parsed": parsed, "J": to_j(task, parsed), "error": err}
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()
        print(f"[{code}] {task} {rec['lat_s']}s score={score} err={err}", flush=True)
    fout.close()
    print(f"完成，總耗時 {(time.perf_counter()-t_all)/60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
