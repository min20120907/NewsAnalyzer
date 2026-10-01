# -*- coding: utf-8 -*-
"""管線混合比較圖：左=準確率橫條，右=延遲橫條（log）。深色底，無白卡。"""
from matplotlib import font_manager
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _pick_cjk_font():
    avail = {f.name for f in font_manager.fontManager.ttflist}
    for c in ["Noto Sans CJK TC", "Noto Sans TC", "Noto Sans CJK SC",
              "WenQuanYi Zen Hei", "Noto Serif CJK TC"]:
        if c in avail:
            plt.rcParams["font.family"] = c
            return c
    return None


def build_figure(data):
    _pick_cjk_font()
    plt.rcParams["axes.unicode_minus"] = False
    BG, FG, MUT = "#0b1220", "#e2e8f0", "#94a3b8"
    GOLD, CYAN, GRAY = "#fbbf24", "#7dd3fc", "#475569"

    ms = data["methods"]
    labels = [m["label"] for m in ms]
    accs = [m["acc"] for m in ms]
    lms = data.get("lat_methods", ms)
    lat_labels = [m["label"] for m in lms]
    lats = [m["lat_ms"] for m in lms]
    colors = [GOLD if m["key"] == "nasys" else CYAN if m["key"] == "qwen27" else GRAY
              for m in ms]
    lat_colors = [GOLD if m["key"].startswith("nasys") else CYAN if m["key"] == "qwen27"
                  else GRAY for m in lms]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 10), facecolor=BG,
                                   gridspec_kw={"width_ratios": [1.05, 1]})
    for ax in (ax1, ax2):
        ax.set_facecolor(BG)
        ax.tick_params(colors=MUT, labelsize=13)
        for s in ax.spines.values():
            s.set_color("#1e293b")

    y = range(len(ms))
    ax1.barh(list(y), accs, color=colors, edgecolor="none", height=0.62)
    ax1.set_yticks(list(y))
    ax1.set_yticklabels(labels, fontsize=13, color=FG)
    ax1.invert_yaxis()
    ax1.set_xlabel("準確率 Accuracy (%)", fontsize=13, color=MUT)
    ax1.set_xlim(0, 105)
    ax1.set_xticks([0, 20, 40, 60, 80, 100])
    ax1.set_title("準確率：混合架構 95.3% 領先", fontsize=16, color=FG, pad=10)
    for i, m in enumerate(ms):
        ax1.text(m["acc"] + 0.8, i, f'{m["acc"]:.1f}%（F1 {m["f1"]:.3f}）',
                 va="center", fontsize=13, color=FG)

    y2 = range(len(lms))
    ax2.barh(list(y2), lats, color=lat_colors, edgecolor="none", height=0.62)
    ax2.set_xscale("log")
    import matplotlib.ticker as _ticker
    ax2.xaxis.set_minor_formatter(_ticker.NullFormatter())
    ax2.set_yticks(list(y2))
    ax2.set_yticklabels(lat_labels, fontsize=13, color=FG)
    ax2.invert_yaxis()
    ax2.set_xlabel("推論延遲 Latency（ms, log scale）", fontsize=13, color=MUT)
    ax2.set_title("延遲：完整管線 8.0s vs 純LLM 13.35s", fontsize=16, color=FG, pad=10)
    for i, m in enumerate(lms):
        ax2.text(m["lat_ms"] * 1.35, i, m["lat_label"],
                 va="center", fontsize=13, color=FG)

    k = data["kpi"]
    fig.suptitle(data["title"], fontsize=26, color=FG, y=0.97, fontweight="bold")
    fig.text(0.5, 0.915, data["subtitle"], ha="center", fontsize=14, color=MUT)
    fig.text(0.5, 0.855,
             f' NewsAnalyzer {k["sys_acc"]:.1f}%   領先純 27B +{k["gap_pp"]:.1f}pp   完整管線快{k["speedup"]} ',
             ha="center", fontsize=36, color=GOLD, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="#1e293b", edgecolor=GOLD))
    fig.text(0.02, 0.02, data["footer"], fontsize=13, color=MUT, va="bottom", ha="left",
             wrap=True)
    fig.tight_layout(rect=[0, 0.06, 1, 0.78])
    return fig


def main():
    import json, os
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "data.json"), encoding="utf-8") as f:
        data = json.load(f)
    fig = build_figure(data)
    out = os.path.join(base, "baseline_mix.png")
    fig.savefig(out, dpi=100, facecolor=fig.get_facecolor())
    print("saved", out)


if __name__ == "__main__":
    main()
