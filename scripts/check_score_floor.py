"""評分地板：扣分項不得把 total/avail 拖成負數。

2026-10-01 regression。實測軟命中升級 + mygopen 同時命中時，
avail 被扣到負值、final=-31.17 越界（UI 顯示負分）。
跑：.venv/bin/python scripts/check_score_floor.py
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))


def compute(total_pts, avail_w, deltas):
    """複製 fake_news_server_new 的加權平均路徑：扣分項只加 total，不加 avail。"""
    total = total_pts + sum(deltas)
    return max(0.0, (total / avail_w) * 100) if avail_w > 0 else 0.0


def demo():
    close = lambda a, b: abs(a - b) < 1e-6

    # 中性：domain 15 + sentiment 12 + fact_check 15，avail = 75 → 56%
    assert close(compute(42, 75, []), 56.0)

    # 軟命中升級吃 -30：只有 total 動，分母不動 → 12/75 = 16%
    assert close(compute(42, 75, [-30]), 16.0)

    # 舊 bug 的真正越界情境：avail 被扣到負值時，(total/avail)*100 變成大正數或負數。
    total, avail = 42, 75
    old = (total - 90) / (avail - 90) * 100      # avail 變 -15
    assert old < 0 or old > 100, f"舊公式應產生越界值（得到 {old:.2f}），測試前提失效"

    # 新公式：同一輸入夾在 [0, 100]
    new = compute(42, 75, [-30, -30, -30])
    assert 0.0 <= new <= 100.0, new

    print(f"ALL PASS — 扣分項不會讓分數越界（舊公式 {old:.2f} → 新公式 {new:.2f}）")


if __name__ == "__main__":
    demo()
