# -*- coding: utf-8 -*-
"""證據採集：日文 FC 站對中文新聞的假命中（jfc/infact 語言閘門的正當性）。

對 R09/R17/B09/B17 的文字，繞過新加的語言閘門，直接跑「舊行為」：
用 jfc/infact 的站內候選（RSS／WP 搜尋）做 SBERT 門控，印出命中的標題與相似度。
再用新路徑（get_jfc/get_infact）確認已放空。

跑法：cd python && ../.venv/bin/python ../scripts/probe_fc_lang_guard.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(os.path.dirname(HERE), "python")
sys.path.insert(0, PY)

import factcheck_multi as fm          # noqa: E402
from cofacts_local import _sbert_sim  # noqa: E402

IDS = ("R09", "R17", "B09", "B17")


def load_texts():
    out = {}
    for f in ("eval_bait60_REAL.jsonl", "eval_bait60_BAIT.jsonl"):
        p = os.path.join(PY, f)
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("id") in IDS:
                out[r["id"]] = (r.get("title") or "") + "。" + (r.get("content") or "")
    return out


def main():
    texts = load_texts()
    for iid in IDS:
        t = texts.get(iid)
        if not t:
            continue
        snippet = t[:120]
        print(f"===== {iid} lang={fm._detect_lang(t)} | {t[:40]}")
        # JFC：RSS 全站最新 15 篇（無關鍵詞篩選），舊行為＝只靠 SBERT 0.50 擋
        try:
            items = fm._rss_titles(fm.JFC_RSS, 15)
        except Exception as e:
            items = []
            print(f"  jfc rss err {e}")
        if items:
            best = None
            for ttl, u in items:
                s = _sbert_sim(snippet, ttl) or 0.0
                if best is None or s > best[0]:
                    best = (s, ttl)
            print(f"  jfc  RSS {len(items)} 篇，最高 sim={best[0]:.3f} → {best[1][:60]}")
            print(f"       （舊門檻 0.50 → {'假命中 inaccurate' if best[0] >= 0.5 else '放空'}）")
        # InFact：WP 搜尋日文關鍵詞
        try:
            cands = fm._wp_search(fm.INFACT_SEARCH, fm._ja_keywords(snippet) or snippet[:30], 15)
        except Exception as e:
            cands = []
            print(f"  infact err {e}")
        if cands:
            best = None
            for _cid, ttl, u in cands:
                s = _sbert_sim(snippet, ttl) or 0.0
                if best is None or s > best[0]:
                    best = (s, ttl, u)
            print(f"  infact WP {len(cands)} 筆，最高 sim={best[0]:.3f} → {best[1][:60]}")
            print(f"       （舊門檻 0.50 → {'假命中 ' + fm._map_infact_title(best[1]) if best[0] >= 0.5 else '放空'}）")
        # 新路徑（語言閘門生效後）
        r1 = fm.get_jfc(t, use_cache=False)
        r2 = fm.get_infact(t, use_cache=False)
        print(f"  新路徑：jfc={r1.get('status')} infact={r2.get('status')}")
        print()


if __name__ == "__main__":
    main()
