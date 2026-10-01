#!/usr/bin/env python3
"""qa_baseline.py — 管線混合圖確定性驗收 gate（天氣 gate 不適用此圖，故另立）。

檢查項（全部確定性）:
  [1] TEXT OVERLAP — 真實 matplotlib 幾何兩兩比對所有 Text（含 tick/ylabel）
  [2] DATA ACC     — 左圖 bar 寬 == data.json acc；標註文字含正確數值
  [3] DATA LAT     — 右圖 bar 寬 == data.json lat_ms；標註文字 == lat_label
  [4] GLYPH        — 渲染期任何 "Glyph ... missing" 即 FAIL
  [5] PNG SANITY   — 存在、尺寸合理、非空白
Exit: 0=ALL PASS  1=FAIL  2=TEXT OVERLAP
"""
import io, json, os, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_baseline import build_figure

OVERLAP_AREA_PX = 25.0
OVERLAP_RATIO = 0.20


def _texts(fig, axes):
    out = []
    for t in list(fig.texts):
        if t.get_text().strip():
            out.append(("text", t))
    for a in axes:
        for t in list(a.texts):
            if t.get_text().strip():
                out.append(("text", t))
    for a in axes:
        out.append(("ylabel", a.yaxis.label))
        out.append(("xlabel", a.xaxis.label))
        out.append(("title", a.title))
    for a in axes:
        for t in a.get_yticklabels() + a.get_xticklabels():
            if t.get_text().strip():
                out.append(("tick", t))
    return out


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "data.json"), encoding="utf-8") as f:
        data = json.load(f)
    fails = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig = build_figure(data)
        axes = fig.axes
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        glyph_missing = [str(w.message) for w in caught if "Glyph" in str(w.message)]
    if glyph_missing:
        fails.append(f"GLYPH FAIL: {glyph_missing[:3]}")

    # [1] overlap
    items = _texts(fig, axes)
    boxes = []
    for kind, t in items:
        try:
            boxes.append((kind, t.get_text()[:30], t.get_window_extent(renderer)))
        except Exception:
            pass
    overlap = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            b1, b2 = boxes[i][2], boxes[j][2]
            inter = b1.intersection(b2, b1)
            if inter is None:
                continue
            area = inter.width * inter.height
            small = min(b1.width * b1.height, b2.width * b2.height)
            if area >= OVERLAP_AREA_PX and small > 0 and area / small >= OVERLAP_RATIO:
                overlap.append((boxes[i][:2], boxes[j][:2], round(area, 1)))
    # [2] acc bars
    ax1 = axes[0]
    bars1 = ax1.patches
    if len(bars1) != len(data["methods"]):
        fails.append(f"DATA ACC FAIL: bars {len(bars1)} != methods {len(data['methods'])}")
    else:
        for b, m in zip(bars1, data["methods"]):
            if abs(b.get_width() - m["acc"]) > 1e-6:
                fails.append(f"DATA ACC FAIL: {m['key']} width {b.get_width()} != {m['acc']}")
    need = [f'{m["acc"]:.1f}%' for m in data["methods"]]
    alltxt = " ".join(t.get_text() for _, t in items)
    for n in need:
        if n not in alltxt:
            fails.append(f"DATA ACC FAIL: label {n} missing")
    # [3] lat bars
    lms = data.get("lat_methods", data["methods"])
    ax2 = axes[1]
    bars2 = ax2.patches
    if len(bars2) != len(lms):
        fails.append(f"DATA LAT FAIL: bars {len(bars2)} != lat_methods {len(lms)}")
    else:
        for b, m in zip(bars2, lms):
            if abs(b.get_width() - m["lat_ms"]) > 1e-6:
                fails.append(f"DATA LAT FAIL: {m['key']} width {b.get_width()} != {m['lat_ms']}")
    for m in lms:
        if m["lat_label"] not in alltxt:
            fails.append(f"DATA LAT FAIL: label {m['lat_label'][:20]} missing")
    # [5] png
    out = os.path.join(base, "baseline_mix.png")
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
