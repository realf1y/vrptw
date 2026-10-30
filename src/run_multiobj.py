# -*- coding: utf-8 -*-
"""多目标实验入口：每组权重跑多个种子，取该组目标最优的一次，再生成对比页。

用法：
    python run_multiobj.py --instance data/solomon/100/r101.txt --iters 40 --seeds 2
    python run_multiobj.py --instance data/solomon/100/c101.txt --iters 40 --seeds 1
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from aco import ACOConfig
from compare import build_page, scheme_summary
from instance import parse_solomon
from multiobjective import WeightedSolver, presets, solve_weighted

HERE = Path(__file__).resolve().parent


def objective(solver: WeightedSolver, routes) -> float:
    return solver._solution_cost([list(r) for r in routes])


def main() -> None:
    args = sys.argv[1:]
    instance = "data/solomon/100/r101.txt"
    iters, n_seeds = 40, 2
    out = "results/viz/cost_carbon.html"
    i = 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else None
        if a == "--instance" and nxt:
            instance = nxt; i += 1
        elif a.startswith("--instance="):
            instance = a.split("=", 1)[1]
        elif a == "--iters" and nxt:
            iters = int(nxt); i += 1
        elif a.startswith("--iters="):
            iters = int(a.split("=", 1)[1])
        elif a == "--seeds" and nxt:
            n_seeds = int(nxt); i += 1
        elif a == "--out" and nxt:
            out = nxt; i += 1
        i += 1

    inst = parse_solomon(instance)
    print(inst.describe())
    schemes, best_routes = [], {}
    for name, w in presets().items():
        best = None
        for s in range(1, n_seeds + 1):
            print("求解 %s（种子 %d）..." % (name, s), flush=True)
            res = solve_weighted(inst, name, w, iters=iters, seed=s)
            solver = WeightedSolver(inst, ACOConfig(max_iter=iters, seed=s), w)
            val = objective(solver, res["routes"])
            if best is None or val < best[0]:
                best = (val, res)
        res = best[1]
        schemes.append(scheme_summary(inst, res["routes"], name))
        best_routes[name] = [list(r) for r in res["routes"]]

    page = build_page(inst, schemes, "成本与碳排对比",
                      "%s｜%d 代 × 每组 %d 个种子" % (inst.describe(), iters, n_seeds))
    path = Path(out)
    if not path.is_absolute():
        path = HERE / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")

    rj = Path("results/multiobj_routes.json")
    rj.write_text(json.dumps({"instance": inst.name, "schemes": best_routes,
                              "summary": schemes}, ensure_ascii=False, indent=1),
                  encoding="utf-8")
    print("对比页：" + str(path))
    print("%-8s%8s%6s%10s%10s%10s%10s" % ("方案", "里程", "车辆", "里程成本", "固定成本", "碳排(kg)", "总成本"))
    for s in schemes:
        print("%-8s%8.2f%6d%10.1f%10.1f%10.1f%10.1f"
              % (s["name"], s["distance"], s["vehicles"], s["dist_cost"],
                 s["fixed_cost"], s["carbon_kg"], s["total_cost"]))


if __name__ == "__main__":
    main()
