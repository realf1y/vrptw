# -*- coding: utf-8 -*-
"""M1 自检脚本：解析算例 → 距离矩阵 → 构造一个解 → 评价 → 验证约束检查有效

用法::

    python demo.py                  # 自动生成一个示例算例并跑通全流程
    python demo.py data/C101.txt    # 跑真实的 Solomon 算例
"""
from __future__ import annotations

import sys
from pathlib import Path

from instance import generate_sample, parse_solomon
from solution import evaluate, format_report, nearest_neighbor

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"


def main() -> None:
    if len(sys.argv) > 1:
        inst = parse_solomon(sys.argv[1])
        print(f"[1] 读入算例文件：{sys.argv[1]}")
    else:
        sample = DATA / "sample_clustered_25.txt"
        # 每次都重新生成（seed 固定 → 结果可复现），避免用到旧版本生成的脏数据
        inst = generate_sample(sample, seed=1)
        print(f"[1] 示例算例（每次重新生成）：{sample.relative_to(HERE)}")

    print("   ", inst.describe())
    print("    距离矩阵前 5x5（含仓库）：")
    for row in inst.dist_matrix[:5]:
        print("      " + " ".join(f"{v:7.2f}" for v in row[:5]))

    routes = nearest_neighbor(inst)
    ev = evaluate(inst, routes)
    print("\n[2] 最近邻构造解（M1 只为验证数据层；M2 会换成蚁群算法）")
    print(format_report(inst, ev))

    bad = [list(range(1, min(inst.n_customers, 12) + 1))]      # 故意把一堆客户塞进一辆车
    ev_bad = evaluate(inst, bad)
    print("\n[3] 负例自检（故意超载 / 违反时间窗）")
    print(format_report(inst, ev_bad))
    assert not ev_bad["feasible"], "约束检查失效：这种情况应该被判为不可行"
    assert ev_bad["overload"] > 0 or ev_bad["tw_violation"] > 0, "没有检出任何违反，检查逻辑有问题"

    print("\n✅ M1 自检通过：算例解析、距离矩阵、约束检查、评价函数均正常工作。")
    print("   下一步（M2）：把 nearest_neighbor 换成蚁群算法，其余部分不用改。")


if __name__ == "__main__":
    main()
