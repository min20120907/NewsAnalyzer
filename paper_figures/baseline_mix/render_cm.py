# -*- coding: utf-8 -*-
"""混淆矩陣比較圖：左=NewsAnalyzer（08-27 既有紀錄 n=60），右=Zero-Shot Qwen-27B（今日實測 n=500）。"""
import json
import os
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

    fig, axes = plt.subplots(1, 2, figsize=(16, 10), facecolor=BG)
    for ax in axes:
        ax.set_facecolor(BG)
        for s in ax.spines.values():
            s.set_color("#1e293b")

    for ax, p in zip(axes, data["panels"]):
        cm = p["cm"]  # [[TP, FN], [FP, TN]]
        row_tot = [cm[0][0] + cm[0][1], cm[1][0] + cm[1][1]]
        rates = [[cm[r][c] / row_tot[r] if row_tot[r] else 0 for c in (0, 1)] for r in (0, 1)]
        vmax = max(rates[0][0], rates[0][1], rates[1][0], rates[1][1], 0.01)
        for r in (0, 1):
            for c in (0, 1):
                alpha = 0.15 + 0.85 * (rates[r][c] / vmax)
                ax.add_patch(plt.Rectangle((c, 1 - r), 1, 1, facecolor=(0.25, 0.55, 0.95, alpha),
                                           edgecolor="#1e293b", linewidth=2))
                ax.text(c + 0.5, 1 - r + 0.62, f'{cm[r][c]}',
                        ha="center", va="center", fontsize=36, color="#ffffff", fontweight="bold")
                ax.text(c + 0.5, 1 - r + 0.28, f'同列占比 {rates[r][c]:.1%}',
                        ha="center", va="center", fontsize=13, color=FG)
        ax.set_xlim(0, 2)
        ax.set_ylim(0, 2)
        ax.set_xticks([0.5, 1.5])
        ax.set_xticklabels(["預測 FAKE", "預測 REAL"], fontsize=14, color=FG)
        ax.set_yticks([0.5, 1.5])
        ax.set_yticklabels(["真實 REAL", "真實 FAKE"], fontsize=14, color=FG)
        ax.tick_params(length=0)
        ax.set_title(p["title"], fontsize=20, color=FG, pad=12)
        m = p["metrics"]
        ax.text(1.0, -0.18,
                f'準確率 {m["acc"]:.3f}　FAKE 精確率 {m["precision_fake"]:.3f}　'
                f'召回率 {m["recall_fake"]:.3f}　F1 {m["f1_fake"]:.3f}　有效 {m["n_valid"]}/{m["n"]}',
                ha="center", va="top", fontsize=13, color=MUT, transform=ax.transAxes)

    fig.suptitle(data["title"], fontsize=26, color=FG, y=0.97, fontweight="bold")
    fig.text(0.5, 0.915, data["subtitle"], ha="center", fontsize=14, color=MUT)
    fig.text(0.02, 0.02, data["footer"], fontsize=13, color=MUT, va="bottom", ha="left")
    fig.tight_layout(rect=[0, 0.06, 1, 0.86])
    return fig


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "cm_data.json"), encoding="utf-8") as f:
        data = json.load(f)
    fig = build_figure(data)
    out = os.path.join(base, "cm_compare.png")
    fig.savefig(out, dpi=100, facecolor=fig.get_facecolor())
    print("saved", out)


if __name__ == "__main__":
    main()
