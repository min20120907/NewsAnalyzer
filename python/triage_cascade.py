# -*- coding: utf-8 -*-
"""Cascade triage：JEV 優先，laya fallback。

JEV（OpenRouter API）是主引擎，失敗或無 key 才退回 laya（本地 CPU）。
任一引擎返回 DECIDED verdict 就採用，不需要兩個都同意。
都失敗 → None（走 27B 流程）。
"""
import os
import time

import requests

QUESTIONS = {
    "verdict": {
        "type": "choice",
        "instructions": "判斷這則網路傳言的可信度",
        "criteria": {
            "likely_fake": "內容很可能是捏造的謊言或錯誤資訊",
            "likely_real": "內容很可能是真實可信的資訊",
            "need_check": "難以判斷, 需要深入查證",
        },
    }
}
DECIDED = ("likely_fake", "likely_real")

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.13"
JEV_TIMEOUT = 15

_AGENT = None
_LAYA_PY = "/home/min20120907/laya-poc/.venv/bin/python"


def _laya_predict(content):
    """常駐 agent；用 subprocess 跑獨立 venv（main venv 沒裝 laya）。載入失敗回 None。"""
    import subprocess, json as _json
    try:
        t0 = time.time()
        code = (
            "import os, json; os.environ['USE_TF']='0'; os.environ['CUDA_VISIBLE_DEVICES']='';"
            "import laya;"
            "a=laya.load('convaiinnovations/laya-multilingual');"
            f"r=a.predict({{'body':{content!r}}}, {QUESTIONS!r})['answers']['verdict'];"
            "c=r.get('choice') if isinstance(r,dict) else r;"
            "conf=r.get('confidence') if isinstance(r,dict) else None;"
            "print(json.dumps({'choice':c,'conf':conf}))"
        )
        out = subprocess.check_output([_LAYA_PY, "-c", code], stderr=subprocess.DEVNULL,
                                      timeout=30).decode().strip()
        d = _json.loads(out)
        return {**d, "lat_s": round(time.time() - t0, 3)}
    except Exception:
        return None


def _jev_predict(content):
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key or "***" in key:
        return None
    try:
        t0 = time.time()
        d = requests.post(JEV_URL, json={"model": JEV_MODEL,
                                         "state": {"body": content},
                                         "questions": QUESTIONS},
                          headers={"Authorization": f"Bearer {key}"},
                          timeout=JEV_TIMEOUT).json()
        ans = (d.get("answers") or {}).get("verdict")
        if not isinstance(ans, dict):
            return None
        return {"choice": ans.get("choice"), "conf": ans.get("confidence"),
                "lat_s": round(time.time() - t0, 3)}
    except Exception:
        return None


def triage(content):
    """回 {"verdict", "engine", "detail"} 或 None（走 27B）。
    
    JEV 優先；失敗或無 key → fallback laya。
    """
    if not (content or "").strip():
        return None
    # 主引擎：JEV
    j = _jev_predict(content)
    if j and j["choice"] in DECIDED:
        return {"verdict": j["choice"], "engine": "jev", "detail": j}
    # Fallback：laya
    l = _laya_predict(content)
    if l and l["choice"] in DECIDED:
        return {"verdict": l["choice"], "engine": "laya", "detail": l}
    return None
