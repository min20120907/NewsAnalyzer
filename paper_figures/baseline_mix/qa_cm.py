#!/usr/bin/env python3
"""qa_cm.py — 混淆矩陣圖確定性驗收 gate。
  [1] SOURCE — cm_data.json 的 TP/FP/FN/TN == 逐筆 jsonl 重算結果
  [2] TEXT OVERLAP — 真實幾何兩兩比對
  [3] GLYPH — 渲染期缺字即 FAIL
  [4] PNG SANITY
Exit: 0=ALL PASS  1=FAIL  2=TEXT OVERLAP
"""
import json
import os
import sys
import warnings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_cm import build_figure

OVERLAP_AREA_PX = 25.0
OVERLAP_RATIO = 0.20
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def recompute(path):
    """來源若是 paired_baseline.json（彙總 JSON）：直接取雙方 CM；
    否則視為逐筆 jsonl 重算。"""
    full = os.path.join(BASE, path)
    with open(full, encoding="utf-8") as f:
        first = f.read(1)
    if path.endswith("paired_baseline.json"):
        d = json.load(open(full, encoding="utf-8"))
        out = {}
        for key in ("newsanalyzer", "zeroshot_qwen27"):
            m = d[key]
            out[key] = {"n": m["n"], "n_valid": m["n"], "TP": m["TP"],
                        "FP": m["FP"], "FN": m["FN"], "TN": m["TN"]}
        return out
    recs = [json.loads(l) for l in open(full, encoding="utf-8")]
    v = [r for r in recs if r.get("pred") in ("FAKE", "REAL")]
    tp = sum(1 for r in v if r["true"] == "FAKE" and r["pred"] == "FAKE")
    fp = sum(1 for r in v if r["true"] == "REAL" and r["pred"] == "FAKE")
    fn = sum(1 for r in v if r["true"] == "FAKE" and r["pred"] == "REAL")
    tn = sum(1 for r in v if r["true"] == "REAL" and r["pred"] == "REAL")
    return {"n": len(recs), "n_valid": len(v), "TP": tp, "FP": fp, "FN": fn, "TN": tn}


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "cm_data.json"), encoding="utf-8") as f:
        data = json.load(f)
    fails = []
    for p in data["panels"]:
        got = recompute(p["source"])
        if isinstance(got, dict) and "TP" not in got:
            got = got[p["key"]]
        for k in ("n", "n_valid", "TP", "FP", "FN", "TN"):
            if got[k] != p["metrics"][k]:
                fails.append(f"SOURCE FAIL: {p['key']}.{k} json={p['metrics'][k]} != recompute={got[k]}")
        cm = p["cm"]
        if [cm[0][0], cm[0][1], cm[1][0], cm[1][1]] != [got["TP"], got["FN"], got["FP"], got["TN"]]:
            fails.append(f"SOURCE FAIL: {p['key']}.cm != recompute")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig = build_figure(data)
        axes = fig.axes
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        glyph_missing = [str(w.message) for w in caught if "Glyph" in str(w.message)]
    if glyph_missing:
        fails.append(f"GLYPH FAIL: {glyph_missing[:3]}")

    items = []
    for t in list(fig.texts):
        if t.get_text().strip():
            items.append(t)
    for a in axes:
        items.extend([t for t in list(a.texts) if t.get_text().strip()])
        items.extend([t for t in a.get_xticklabels() + a.get_yticklabels() if t.get_text().strip()])
    boxes = []
    for t in items:
        try:
            boxes.append((t.get_text()[:24], t.get_window_extent(renderer)))
        except Exception:
            pass
    overlap = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            b1, b2 = boxes[i][1], boxes[j][1]
            inter = b1.intersection(b2, b1)
            if inter is None:
                continue
            area = inter.width * inter.height
            small = min(b1.width * b1.height, b2.width * b2.height)
            if area >= OVERLAP_AREA_PX and small > 0 and area / small >= OVERLAP_RATIO:
                overlap.append((boxes[i][0], boxes[j][0], round(area, 1)))

    out = os.path.join(base, "cm_compare.png")
    fig.savefig(out, dpi=100, facecolor=fig.get_facecolor())
    import matplotlib.image as mpimg
    img = mpimg.imread(out)
    h, w = img.shape[:2]
    if h < 400 or w < 600:
        fails.append(f"PNG FAIL: too small {w}x{h}")
    if float(img.std()) < 1e-3:
        fails.append("PNG FAIL: blank image")

    if overlap:
        print(f"TEXT OVERLAP ({len(overlap)}):")
        for a, b, area in overlap[:10]:
            print(f"  {a} <> {b} area={area}")
        return 2
    if fails:
        print("FAIL:")
        for f in fails:
            print("  " + f)
        return 1
    print(f"ALL PASS (texts={len(items)} png={w}x{h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
