# -*- coding: utf-8 -*-
"""Cofacts 召回/快取契約測試 —— 2026-10-18「明明查核有、卻找不到」修復的回歸鎖。

跑法：cd python && ../.venv/bin/python ../scripts/test_cofacts_recall_contract.py
（網路測試在 API 不可達時記 SKIP，其餘為純函式斷言，可離線跑。）

鎖住的不變量：
  1. moreLikeThis 必須帶 minimumShouldMatch，且放寬 msm 只會讓召回變多不會變少
     （預設 msm 對長句改寫文實測 0 筆，是「找不到」的主因）
  2. first 上限必須被尊重（不能偷偷回超過要求的筆數）
  3. 比對文本分流：inaccurate/partial 比謠言原文、accurate 比回覆文、純連結比回覆文
  4. 日文查核站（jfc/infact）對非日文輸入一律放空（跨語言假命中的閘門）
  5. 快取負結果必須會過期，正結果 TTL 較長（舊碼 ts 寫了不讀 → 永久 not_found）
"""
import json
import os
import sqlite3
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(os.path.dirname(HERE), "python")
sys.path.insert(0, PY)

import cofacts_local as cl      # noqa: E402
import factcheck_multi as fm    # noqa: E402

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""))
    if not cond:
        FAIL.append(name)


LONG_ZH = ("台南鐵路地下化第一階段將在2026年10月17日正式通車，16日晚間開出末班地面列車"
           "自強號145次後連夜辦理軌道切換。新啟用台南車站設三處出入口，1號在北門路側舊站古蹟棟。")


def t_recall():
    print("[1] moreLikeThis 召回參數")
    try:
        d_def = cl._post_graphql({"moreLikeThis": {"like": LONG_ZH}}, 15)
        d_10 = cl._post_graphql({"moreLikeThis": {"like": LONG_ZH,
                                                  "minimumShouldMatch": "10%"}}, 15, first=25)
        d_20 = cl._post_graphql({"moreLikeThis": {"like": LONG_ZH,
                                                  "minimumShouldMatch": "20%"}}, 15, first=15)
    except Exception as e:
        print(f"  SKIP API 不可達：{e}")
        return
    if d_def is None or d_10 is None:
        print("  SKIP API 回應異常（Cloudflare 等），略過")
        return
    n_def = len(((d_def.get("data") or {}).get("ListArticles", {}) or {}).get("edges") or [])
    n_10 = len(((d_10.get("data") or {}).get("ListArticles", {}) or {}).get("edges") or [])
    n_20 = len(((d_20.get("data") or {}).get("ListArticles", {}) or {}).get("edges") or [])
    check("msm10% 召回 >= 預設 msm", n_10 >= n_def, f"default={n_def} msm10%={n_10}")
    check("msm10% 對長句改寫文仍有召回", n_10 > 0, f"msm10%={n_10}")
    check("first=25 上限被尊重", n_10 <= 25, f"n={n_10}")
    check("first=15 上限被尊重", n_20 <= 15, f"n={n_20}")
    # 三檔召回必須真的併進池子（不是只有第一檔生效）
    nodes = cl._graphql_recall(LONG_ZH, 15)
    check("多檔 msm 合併召回有 node", len(nodes) > 0, f"nodes={len(nodes)}")
    check("合并召回不超過 _RECALL_MAX_NODES",
          len(nodes) <= cl._RECALL_MAX_NODES, f"nodes={len(nodes)}")
    check("召回 node 皆有 id 且去重",
          len({n.get("id") for n in nodes}) == len(nodes) and all(n.get("id") for n in nodes))


def t_sim_text():
    print("[2] 比對文本分流 _pick_sim_text")
    raw = "謠言原文：某飲料喝下去治百病。"
    rep_long = "查核回覆：這是錯誤的。衛福部說明該飲料沒有療效，屬於誇大不實的廣告話術。"
    reasons = [{"type": "RUMOR", "text": rep_long}]
    check("inaccurate 比謠言原文",
          cl._pick_sim_text("inaccurate", raw, reasons) == raw[:200])
    check("partial 比謠言原文",
          cl._pick_sim_text("partial", raw, reasons) == raw[:200])
    check("accurate 比回覆文",
          cl._pick_sim_text("accurate", raw, reasons) == rep_long[:200])
    check("純連結文比回覆文",
          cl._pick_sim_text("inaccurate", "https://example.com only", reasons)
          == rep_long[:200])
    check("無回覆時回原文", cl._pick_sim_text("inaccurate", raw, []) == raw[:200])
    # _classify_candidate 必須同時帶 gate_text 與 sim_text
    node = {"id": "X1", "text": raw, "createdAt": "2026-01-01T00:00:00Z",
            "articleReplies": [{"feedbackCount": 3,
                                "reply": {"type": "RUMOR", "text": rep_long}}]}
    c = cl._classify_candidate(node)
    check("candidate 帶 gate_text", bool(c and c.get("gate_text") == raw[:400]))
    check("candidate 帶 sim_text", bool(c and c.get("sim_text") == raw[:200]))
    check("inaccurate 的 sim_text 不是回覆文",
          bool(c and rep_long not in (c.get("sim_text") or "")))


def t_lang_guard():
    print("[3] 日文查核站語言閘門")
    zh = "台南鐵路地下化將在10月17日正式通車，市府提醒旅客留意動線。"
    ja = "新型コロナの感染が拡大しています。ワクチンについて誤った情報が出回っています。"
    check("_detect_lang 判定中文", fm._detect_lang(zh) == "zh")
    check("_detect_lang 判定日文", fm._detect_lang(ja) == "ja")
    for name, fn in (("jfc", fm.get_jfc), ("infact", fm.get_infact)):
        r = fn(zh, use_cache=False)
        check(f"{name} 對中文放空", r.get("status") == "not_found", r.get("status"))
        check(f"{name} 放空不帶相似度", not r.get("similarity_score"),
              repr(r.get("similarity_score")))
        check(f"{name} 放空不帶 url", not r.get("url"), repr(r.get("url")))


def t_cache_ttl():
    print("[4] 快取 TTL")
    check("負結果 TTL 短於正結果",
          fm._cache_ttl("not_found") < fm._cache_ttl("inaccurate"))
    check("負結果 TTL > 0（仍要快取，避免重複打站台）", fm._cache_ttl("not_found") > 0)
    # 造一個過期的負結果：必須讀不到
    old_db = fm.CACHE_DB
    tmp = tempfile.mktemp(suffix=".db")
    try:
        fm.CACHE_DB = tmp
        fm._mcache_put("mygopen", "k_neg", {"source": "mygopen", "status": "not_found"})
        fm._mcache_put("mygopen", "k_pos", {"source": "mygopen", "status": "inaccurate"})
        check("剛寫入的負結果可讀", bool(fm._mcache_get("mygopen", "k_neg")))
        check("剛寫入的正結果可讀", bool(fm._mcache_get("mygopen", "k_pos")))
        con = sqlite3.connect(tmp)
        con.execute("UPDATE mcache SET ts=? WHERE key='k_neg'",
                    (time.time() - fm._cache_ttl("not_found") - 60,))
        con.execute("UPDATE mcache SET ts=? WHERE key='k_pos'",
                    (time.time() - fm._cache_ttl("not_found") - 60,))
        con.commit()
        con.close()
        check("過期的負結果讀不到（舊碼會永遠回 not_found）",
              fm._mcache_get("mygopen", "k_neg") is None)
        check("未過期的正結果仍可讀", fm._mcache_get("mygopen", "k_pos") is not None)
    finally:
        fm.CACHE_DB = old_db
        if os.path.exists(tmp):
            os.remove(tmp)


def t_gate_stack():
    print("[6] 門控堆疊 _gate_pass（per-text AND）＋數字指紋閘門預設")
    q = ("【台電通知】節電獎勵2.0上路，登錄電號每期回饋800元。為鼓勵全民節電，自9月起實施"
         "節電獎勵2.0專案，用電較去年同期減少一度即回饋50元，每期最高回饋800元，"
         "登錄成功者加贈200元超商禮券，活動至12月31日止。")
    raw = ("2018台電節電獎勵活動今起開放登錄！4月底前登錄享全年節電獎勵金。台電表示，本活動"
           "提供多元且友善的登錄管道，用戶可從台電官網進入登錄報名，輸入電號、基本資料並完成"
           "檢核確認，即登錄成功；比較不習慣上網的民眾，亦可電洽1911台電客服中心。")
    alt = ("自即日起至 107 年 12 月 31 日。台電強調，改以登錄制的節電成效高出一成。參加活動"
           "登錄之電號當期用電每節省一度，可獲得 0.6 元獎勵金，如每期(2 個月)獎勵金低於 84 元者，"
           "按 84 元計算。")
    check("kw 過在原文、num 過在回覆文 → per-text AND 仍要擋",
          not cl._gate_pass(q, [raw, alt]))
    check("單看原文：關鍵詞過、數字不過",
          cl._keyword_overlap_gate(q, raw) and not cl._numeric_gate(q, raw))
    check("單看回覆文：數字過、關鍵詞不過",
          not cl._keyword_overlap_gate(q, alt) and cl._numeric_gate(q, alt))
    no_num = "健保卡如因遺失、毀損之原因，必須申請換補發卡時，可就近至郵局窗口辦理。"
    check("strictd 擋掉零數字指紋候選", not cl._numeric_gate(q, no_num, mode="strictd"))
    check("soft 放行零數字指紋候選", cl._numeric_gate(q, no_num, mode="soft"))
    check("strictd 對數字有交集的候選放行",
          cl._numeric_gate(q, "台電節電獎勵活動依實際用電量計算，每期最高回饋800元。", mode="strictd"))
    # 千分位正規化（2026-10-18 修：CJK 單位前的逗號原本不會被去掉）
    check("千分位正規化 6,000元 → 6000元",
          cl._numeric_tokens("可依廢棄物清理法處6,000元罰鍰") == {"6000元"})
    check("千分位正規化 1,200,000元 → 1200000元",
          cl._numeric_tokens("總額1,200,000元") == {"1200000元"})
    check("無逗號數字不受影響", cl._numeric_tokens("6000元") == {"6000元"})
    check("跨千分位文本可過數字閘門",
          cl._numeric_gate("亂丟可依廢清法處1200元至6000元罰鍰",
                           "可依《廢棄物清理法》處新台幣1,200元以上、6,000元以下罰鍰",
                           mode="strictd"))
    old_env = os.environ.pop("COFACTS_NUM_GATE", None)
    try:
        check("COFACTS_NUM_GATE 未設＝strictd（預設）",
              not cl._numeric_gate(q, no_num))
    finally:
        if old_env is not None:
            os.environ["COFACTS_NUM_GATE"] = old_env


def t_corpus_index():
    print("[5] 本地索引與語料一致")
    idx = cl.build_local_index()
    check("本地索引可建立", idx is not None)
    if idx:
        keys, emb = idx
        check("索引筆數 == corpus 筆數",
              len(keys) == len(cl._corpus_all()), f"{len(keys)}")
        check("向量維度正確", getattr(emb, "shape", (0, 0))[1] > 0,
              str(getattr(emb, "shape", None)))


def t_multisource_and_d1():
    print("[7] 多源標題門控與 D1 硬命中優先")
    import orthogonal_scorer as os_mod
    r09_q = ("新冠進入流行期，疾管署估8月中達高峰單週恐破5萬人次。"
             "疾管署2026年7月宣布新冠疫情進入流行期，就診人次連續上升。")
    check("MyGoPen 門控擋 R09 同領域舊查核",
          fm._title_gate_and_sim(
              r09_q, "【易誤解】網傳新冠又來了？這5種症狀要當心？過期訊息！缺乏時間脈絡的疫情資訊") is None)
    b14_q = ("騎車沒違規就能抽機車和iPhone？交通部公路局配合2026年交通安全月，"
             "推出機車零違規抽獎活動。")
    check("MyGoPen 門控擋 B14 同領域舊查核",
          fm._title_gate_and_sim(
              b14_q, "【查證】又是一條搶錢法規？機車未打方向燈罰1200？交通事件裁決中心解析") is None)
    check("MyGoPen 門控放行同事件標題",
          fm._title_gate_and_sim(
              r09_q, "【查證】疾管署宣布新冠疫情進入流行期，8月中達高峰單週破5萬人次") is not None)
    d1_r09 = os_mod.compute_d1_evidence_verdict(
        [{"source": "cofacts", "status": "accurate", "similarity_score": 0.9257,
          "feedback_count": 1, "reasons": [{"text": "與疾管署公布資訊相符"}]},
         {"source": "mygopen", "status": "inaccurate", "similarity_score": 0.6037,
          "feedback_count": 1, "reasons": [{"text": "網傳新冠又來了"}]}],
        {"evidence_state": "full_body_evidence", "credibility_score": 95, "abstain": False})
    check("D1 硬命中優先：0.93 accurate 不被 0.60 軟命中壓死",
          d1_r09.status_label == "supports", d1_r09.status_label)
    d1_rf = os_mod.compute_d1_evidence_verdict(
        [{"source": "cofacts", "status": "accurate", "similarity_score": 0.8222,
          "feedback_count": 2, "reasons": [{"text": "目前沒有任何研究證明喝熱檸檬水可以抗癌"}]}],
        {"evidence_state": "full_body_evidence", "credibility_score": 15, "abstain": False})
    check("D1 闢謠澄清文反轉：LLM 判 <=30 時轉 refutes",
          d1_rf.status_label == "refutes", d1_rf.status_label)


if __name__ == "__main__":
    t_sim_text()
    t_lang_guard()
    t_cache_ttl()
    t_gate_stack()
    t_multisource_and_d1()
    t_corpus_index()
    t_recall()
    print("=" * 60)
    if FAIL:
        print(f"FAILED {len(FAIL)}: {FAIL}")
        sys.exit(1)
    print("ALL PASS")
