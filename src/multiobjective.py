# -*- coding: utf-8 -*-
"""M9｜多目标优化（里程 / 车辆固定成本 / 碳排 / 时间窗）

业务背景
--------
企业不只关心“跑得短”：多派一辆车要多一份司机与折旧成本，跑得远则碳排高；
有些客户对时效敏感，晚到要赔钱。把这些折算成钱以后，路线选择就变成一个**加权多目标**问题：

    总代价 = 里程成本 + 车辆固定成本 + 碳排成本 + 晚到罚金

    · 里程成本：3.5 元/km（油费 + 保养 + 司机分摊）
    · 车辆固定成本：300 元/车（司机日薪 + 车辆折旧，按趟计）
    · 碳排：空载 0.25 kg/km，满载再加 0.25 kg/km（按装载率线性）
    · 碳价：0.5 元/kg（约 70 欧元/吨，接近当前碳市场价）
    · 晚到罚金：50 元/单位时间（软时间窗场景）

调不同的权重就得到不同的方案：成本优先会压车辆数，低碳优先会压总里程，
两者往往冲突——这正是要展示的取舍。

对外接口
--------
    from multiobjective import Weights, presets, solve_weighted, breakdown
    res = solve_weighted(inst, "低碳优先", presets()["低碳优先"], iters=40)
    print(res["breakdown"])

命令行
------
    python multiobjective.py --instance data/solomon/100/c101.txt --iters 40
    python multiobjective.py --instance data/solomon/100/r101.txt --iters 40 --out results/multiobj_r101.csv
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from aco import ACOConfig, AntColonySolver
from instance import parse_solomon
from solution import evaluate, evaluate_route

DIST_RATE = 3.5        # 元/km
FIXED_PER_VEHICLE = 300.0
CARBON_PRICE = 0.5     # 元/kg
LATE_RATE = 50.0       # 元/单位时间窗违反
EMPTY_FACTOR = 0.25    # kg/km（空载）
LOAD_FACTOR = 0.25     # kg/km（满载附加）


@dataclass(frozen=True)
class Weights:
    name: str
    dist_cost: float = DIST_RATE
    fixed_cost: float = FIXED_PER_VEHICLE
    carbon_price: float = CARBON_PRICE
    late_rate: float = LATE_RATE

    def describe(self) -> str:
        return ("%s｜里程 %.1f 元/km｜固定 %.0f 元/车｜碳价 %.2f 元/kg｜晚到 %.0f 元/单位"
                % (self.name, self.dist_cost, self.fixed_cost, self.carbon_price, self.late_rate))


def presets() -> dict[str, Weights]:
    """三组典型偏好：成本优先 / 均衡 / 低碳优先"""
    return {
        "成本优先": Weights("成本优先", carbon_price=0.0),
        "均衡": Weights("均衡", carbon_price=CARBON_PRICE),
        "低碳优先": Weights("低碳优先", carbon_price=6.0),
    }


# --------------------------------------------------------------------------
# 碳排与成本
# --------------------------------------------------------------------------
def route_carbon(inst, route) -> float:
    """单条路线的碳排（kg）：空载系数 + 按装载率线性增加"""
    rep = evaluate_route(inst, route)
    capacity = getattr(inst, "capacity", 0) or 1.0
    ratio = min(1.0, rep.load / capacity)
    return rep.distance * (EMPTY_FACTOR + LOAD_FACTOR * ratio)


def carbon_kg(inst, routes) -> float:
    return round(sum(route_carbon(inst, r) for r in routes if r), 2)


def breakdown(inst, routes) -> dict:
    """成本构成（元）与碳排（kg），报表与看板共用同一口径。"""
    ev = evaluate(inst, routes)
    n_vehicles = len([r for r in routes if r])
    fixed = ev["fixed_cost"] if ev["fixed_cost"] > 0 else n_vehicles * FIXED_PER_VEHICLE
    dist_cost = ev["total_distance"] * DIST_RATE
    carbon = carbon_kg(inst, routes)
    carbon_cost = carbon * CARBON_PRICE
    late_penalty = ev["tw_violation"] * LATE_RATE
    total = dist_cost + fixed + carbon_cost + late_penalty
    return {
        "distance": ev["total_distance"],
        "vehicles": ev["vehicles"],
        "dist_cost": round(dist_cost, 2),
        "fixed_cost": round(fixed, 2),
        "carbon_kg": carbon,
        "carbon_cost": round(carbon_cost, 2),
        "late_penalty": round(late_penalty, 2),
        "total_cost": round(total, 2),
        "on_time_rate": ev["on_time_rate"],
        "load_rate": ev["load_rate"],
        "tw_violation": ev["tw_violation"],
        "feasible": ev["feasible"],
    }


# --------------------------------------------------------------------------
# 加权多目标求解：复用蚁群骨架，只换目标函数
# --------------------------------------------------------------------------
class WeightedSolver(AntColonySolver):
    """把“里程 + 固定成本 + 碳排 + 晚到”折成一个可比较的数，其余流程与改进版蚁群完全一致。"""

    def __init__(self, inst, config: ACOConfig, weights: Weights) -> None:
        super().__init__(inst, config)
        self.w = weights

    def _route_cost(self, route: list[int]) -> float:
        if not route:
            return 0.0
        rep = evaluate_route(self.inst, route)
        capacity = getattr(self.inst, "capacity", 0) or 1.0
        ratio = min(1.0, rep.load / capacity)
        carbon = rep.distance * (EMPTY_FACTOR + LOAD_FACTOR * ratio)
        cost = (self.w.dist_cost * rep.distance
                + self.w.carbon_price * carbon
                + self.w.late_rate * rep.tw_violation)
        if rep.load > capacity + 1e-9:
            cost += 1e6 * (rep.load - capacity)
        return cost

    def _solution_cost(self, routes: list[list[int]]) -> float:
        used = [r for r in routes if r]
        return sum(self._route_cost(r) for r in used) + self.w.fixed_cost * len(used)


def solve_weighted(inst, name: str, weights: Weights, iters: int = 40, seed: int = 1) -> dict:
    cfg = ACOConfig(max_iter=iters, seed=seed, lambda_tw=weights.late_rate)
    if str(getattr(inst, "tw_mode", "hard")) != "soft":
        cfg.lambda_tw = 1e4
    solver = WeightedSolver(inst, cfg, weights)
    res = solver.solve()
    res["name"] = name
    res["weights"] = weights
    res["breakdown"] = breakdown(inst, res["routes"])
    return res


# --------------------------------------------------------------------------
# 命令行：跑三组权重，打印对比
# --------------------------------------------------------------------------
def main() -> None:
    args = sys.argv[1:]
    instance = "data/solomon/100/c101.txt"
    iters, seed = 40, 1
    out = "results/multiobj.csv"
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
        elif a == "--seed" and nxt:
            seed = int(nxt); i += 1
        elif a == "--out" and nxt:
            out = nxt; i += 1
        elif a.startswith("--out="):
            out = a.split("=", 1)[1]
        i += 1

    inst = parse_solomon(instance)
    print(inst.describe())
    results = []
    for name, w in presets().items():
        print("求解 " + name + " ...", flush=True)
        results.append(solve_weighted(inst, name, w, iters=iters, seed=seed))

    hdr = "%-8s%8s%6s%10s%10s%10s%10s%10s" % ("方案", "里程", "车辆", "里程成本", "固定成本",
                                             "碳排(kg)", "碳成本", "总成本")
    print()
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        b = r["breakdown"]
        print("%-8s%8.2f%6d%10.1f%10.1f%10.1f%10.1f%10.1f" % (
            r["name"], b["distance"], b["vehicles"], b["dist_cost"], b["fixed_cost"],
            b["carbon_kg"], b["carbon_cost"], b["total_cost"]))

    path = Path(out)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["scheme", "distance", "vehicles", "dist_cost", "fixed_cost",
                     "carbon_kg", "carbon_cost", "late_penalty", "total_cost",
                     "on_time_rate", "load_rate"])
        for r in results:
            b = r["breakdown"]
            wr.writerow([r["name"], b["distance"], b["vehicles"], b["dist_cost"],
                         b["fixed_cost"], b["carbon_kg"], b["carbon_cost"],
                         b["late_penalty"], b["total_cost"], b["on_time_rate"], b["load_rate"]])
    print("\n明细已写入 " + str(path))


if __name__ == "__main__":
    main()
