# -*- coding: utf-8 -*-
"""统计检验：配对 Wilcoxon 符号秩检验（不依赖 scipy）

读 results/experiments_100_10x.csv，对同一算例、同一随机种子下的两次运行做配对比较：
    最近邻 vs L3、L0 vs L3、L1 vs L2、L2 vs L3

输出：results/stats_report.md（检验方法、样本量、W 统计量、z、p 值、中位改善幅度）

用法::
    python stats.py                       # 默认读 experiments_100_10x.csv
    python stats.py results/xxx.csv
"""
from __future__ import annotations

import csv
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

PAIRS = [
    ("最近邻(贪心)", "L3 +局部搜索(改进版)"),
    ("L0 基线ACO", "L3 +局部搜索(改进版)"),
    ("L1 +时间窗η", "L2 +MMAS精英"),
    ("L2 +MMAS精英", "L3 +局部搜索(改进版)"),
    ("L0 基线ACO", "L1 +时间窗η"),
]


def load(path: Path) -> dict:
    data: dict[tuple[str, int], dict[str, float]] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                key = ((row["instance"] or "").upper(), int(row["run"]))
                dist = float(row["distance"])
            except (KeyError, TypeError, ValueError):
                continue
            data.setdefault(key, {})[row["method"]] = dist
    return data


def ranks(values: list[float]) -> list[float]:
    """平均秩（处理并列）"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and abs(values[order[j + 1]] - values[order[i]]) < 1e-9:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def wilcoxon(diffs: list[float]) -> tuple[int, float, float, float]:
    """返回 (n, W+, z, p_two_sided)，正态近似（n≥10 足够）"""
    d = [x for x in diffs if abs(x) > 1e-9]
    n = len(d)
    if n == 0:
        return 0, 0.0, 0.0, 1.0
    r = ranks([abs(x) for x in d])
    w_plus = sum(ri for ri, di in zip(r, d) if di > 0)
    mean = n * (n + 1) / 4
    sd = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    z = (w_plus - mean) / sd if sd else 0.0
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return n, w_plus, z, min(p, 1.0)


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS / "experiments_100_10x.csv"
    if not path.exists():
        raise SystemExit(f"没找到实验结果：{path}")
    data = load(path)
    n_runs = len(data)
    instances = sorted({k[0] for k in data})
    print(f"读入 {path.name}：{len(instances)} 个算例，{n_runs} 个（算例, 运行序号）配对样本\n")

    lines = [f"# 统计检验报告（{path.name}）", "",
             f"- 样本：{len(instances)} 个算例 × 每次运行配对，共 **{n_runs}** 组",
             "- 方法：**配对 Wilcoxon 符号秩检验**（双侧，正态近似，零差异样本剔除）",
             "- 显著性：p < 0.05 视为显著；0.05 ≤ p < 0.10 视为边缘显著", "",
             "| 对比（A → B） | n | W+ | z | p 值 | 显著性 | B 相对 A 的中位变化 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]

    for a, b in PAIRS:
        diffs, pcts = [], []
        for key, row in data.items():
            if a in row and b in row:
                diffs.append(row[a] - row[b])
                if row[a]:
                    pcts.append((row[b] - row[a]) / row[a] * 100)
        if not diffs:
            continue
        n, w, z, p = wilcoxon(diffs)
        med = statistics.median(pcts) if pcts else 0.0
        if p < 0.01:
            sig = "**极显著**"
        elif p < 0.05:
            sig = "**显著**"
        elif p < 0.10:
            sig = "边缘"
        else:
            sig = "不显著"
        direction = "下降" if med < 0 else "上升"
        lines.append(f"| {a} → {b} | {n} | {w:.1f} | {z:.2f} | {p:.2e} | {sig} | "
                     f"{abs(med):.1f}% {direction} |")
        print(f"{a} → {b}: n={n}, W+={w:.1f}, z={z:.2f}, p={p:.2e}, 中位 {med:+.1f}%")

    lines += ["", "## 读法", "",
              "1. `p` 越小说明「B 与 A 的差异」越不可能是随机波动造成的；",
              "2. `W+` 是 B 优于 A 的配对样本的秩和（越大越支持 B 更好）；",
              "3. 中位变化用百分数表示，比均值更抗极端值，报告里建议两者都给；",
              "4. 多组比较时可提一句 Bonferroni 校正（0.05/5 = 0.01）作为保守阈值。"]

    out = RESULTS / "stats_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[OK] 已写出：{out}")


if __name__ == "__main__":
    main()
