# -*- coding: utf-8 -*-
"""M2 运行脚本：跑蚁群算法，并与最近邻基线对比

用法::

    python run_aco.py                       # 用示例算例跑
    python run_aco.py data/C101.txt         # 跑真实 Solomon 算例
    python run_aco.py data/C101.txt 5       # 连跑 5 次，报均值 ± 标准差

注意：蚁群是随机算法，**同一算例要跑多次报均值**才算数（报告里的实验规范）。
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

from aco import baseline_config, improved_config, solve_aco
from instance import generate_sample, parse_solomon
from solution import evaluate, nearest_neighbor

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
RESULTS = HERE / "results"


def load_instance(arg: str | None):
    if arg:
        return parse_solomon(arg), Path(arg).stem
    sample = DATA / "sample_clustered_25.txt"
    return generate_sample(sample, seed=1), "sample_clustered_25"


def export_history(history: list[float], name: str) -> Path:
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"convergence_{name}.csv"
    lines = ["iteration,best_distance"]
    lines += [f"{i + 1},{v:.2f}" for i, v in enumerate(history)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    inst, name = load_instance(path)
    print(f"[1] 算例：{name}｜{inst.describe()}")

    # 基线：最近邻
    nn_routes = nearest_neighbor(inst)
    nn = evaluate(inst, nn_routes)
    print(f"\n[2] 最近邻基线（贪心）")
    print(f"    里程 {nn['total_distance']:.2f}｜车辆 {nn['vehicles']}｜可行 {nn['feasible']}")

    # 基线 ACO
    base = solve_aco(inst, baseline_config(seed=1, max_iter=60))
    print(f"\n[3] 基线 ACO（标准蚁群：无 η 改进 / 无 MMAS / 无局部搜索）")
    print(f"    里程 {base['distance']:.2f}｜车辆 {base['vehicles']}｜可行 {base['feasible']}"
          f"｜用时 {base['seconds']}s")

    # 改进 ACO
    imp = solve_aco(inst, improved_config(seed=1))
    print(f"\n[4] 改进 ACO（+ 时间窗 η + 精英/MMAS + 混合局部搜索）")
    print(f"    里程 {imp['distance']:.2f}｜车辆 {imp['vehicles']}｜可行 {imp['feasible']}"
          f"｜用时 {imp['seconds']}s")
    hist = imp["history"]
    marks = [0, min(9, len(hist) - 1), len(hist) // 2, len(hist) - 1]
    conv = "｜".join(f"第 {i + 1} 代 {hist[i]:.2f}" for i in sorted(set(marks)))
    print(f"    收敛：{conv}")

    if nn["total_distance"] > 0:
        gain = (nn["total_distance"] - imp["distance"]) / nn["total_distance"] * 100
        print(f"    相对最近邻提升：{gain:.1f}%")
    if base["distance"] > 0:
        gain2 = (base["distance"] - imp["distance"]) / base["distance"] * 100
        print(f"    相对基线 ACO 提升：{gain2:.1f}%   ← 这就是消融实验里的“改进版 vs 基线”")

    csv = export_history(hist, name)
    print(f"    收敛数据已导出：{csv.relative_to(HERE)}（可直接画收敛曲线）")

    # 多次重复
    if runs > 1:
        print(f"\n[5] 重复运行 {runs} 次（蚁群是随机算法，必须报均值 ± 标准差）")
        values = []
        for k in range(runs):
            r = solve_aco(inst, improved_config(seed=100 + k))
            values.append(r["distance"])
        print(f"    均值 {statistics.mean(values):.2f} ± {statistics.pstdev(values):.2f}"
              f"｜最好 {min(values):.2f}｜最差 {max(values):.2f}")
        print(f"    各次结果：{', '.join(f'{v:.2f}' for v in values)}")


if __name__ == "__main__":
    main()
