# -*- coding: utf-8 -*-
"""M1-2｜解的结构、约束检查与评价函数

解（solution）表示为一组路径 routes::

    routes = [[1, 5, 3], [2, 4]]     # 两辆车：第一辆依次访问 1→5→3

约束与指标
----------
- 载重约束：每条路径的客户需求之和 ≤ 车辆载重上限
- 时间窗约束：到达客户后若早于 ready 则等待；若晚于 due 则记**违反量**（软时间窗）
- 指标：车辆数、总里程、载重超限、时间窗违反量、客户覆盖、是否可行

这一层是 M2（蚁群算法）的地基：算法每构造一个解，都要靠这里的评价函数打分。
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEPOT = 0


@dataclass
class RouteReport:
    """单条路径的运行明细与指标。"""

    route: list[int]
    distance: float
    load: float
    tw_violation: float
    arrivals: list[float] = field(default_factory=list)
    wait_time: float = 0.0
    late_customers: int = 0        # 晚到的客户数
    on_time_rate: float = 1.0      # 准时率 = 准时客户数 / 总客户数
    depot: int = 0                 # 这条路线选用的仓库（多车场时不同）

    @property
    def feasible(self) -> bool:
        return self.tw_violation <= 1e-9


def evaluate_route(inst, route: list[int]) -> RouteReport:
    """沿路径逐点推进时间，算出里程 / 载重 / 等待 / 时间窗违反量。

    - 里程用 ``inst.dist()``，时间推进用 ``inst.time()``（= 距离 / 车速）
    - 客户优先级 ``inst.priority``〔客户号: 权重〕会放大该客户的违约惩罚
    - **多车场**：对 ``inst.depots`` 里每个仓库各算一遍，取（违约量，里程）最优的那个
    """
    best = None
    for depot in (getattr(inst, "depots", None) or [DEPOT]):
        rep = _evaluate_from(inst, route, depot)
        key = (rep.tw_violation, rep.distance)
        if best is None or key < (best.tw_violation, best.distance):
            best = rep
    return best


def _evaluate_from(inst, route: list[int], depot: int) -> RouteReport:
    load = 0.0
    distance = 0.0
    tw_violation = 0.0
    wait_total = 0.0
    late = 0
    arrivals: list[float] = []
    priority = getattr(inst, "priority", None) or {}

    prev = depot
    t = 0.0
    for cid in route:
        c = inst.customers[cid]
        distance += inst.dist(prev, cid)
        travel = inst.time(prev, cid)
        arrival = t + travel
        start = max(arrival, c.ready)          # 到早了要等
        wait_total += start - arrival
        if start > c.due:                      # 到晚了 → 软时间窗违反
            late += 1
            tw_violation += (start - c.due) * float(priority.get(cid, 1.0))
        arrivals.append(start)
        t = start + c.service
        load += c.demand
        prev = cid

    distance += inst.dist(prev, depot)         # 回仓库
    n = len(route)
    return RouteReport(list(route), round(distance, 2), load, round(tw_violation, 2),
                       arrivals, round(wait_total, 2), late,
                       round((n - late) / n, 4) if n else 1.0, depot)


def evaluate(inst, routes: list[list[int]]) -> dict:
    """整体评价：返回指标字典（含每条路径的明细）。"""
    reports = [evaluate_route(inst, r) for r in routes if r]

    total_distance = round(sum(r.distance for r in reports), 2)
    overload = sum(max(0.0, r.load - inst.capacity) for r in reports)
    tw_violation = round(sum(r.tw_violation for r in reports), 2)
    wait_time = round(sum(r.wait_time for r in reports), 2)

    visited = [cid for r in reports for cid in r.route]
    duplicated = len(visited) - len(set(visited))
    missing = inst.n_customers - len(set(visited))

    routed = sum(len(r.route) for r in reports)
    late_customers = sum(r.late_customers for r in reports)
    on_time_rate = round((routed - late_customers) / routed, 4) if routed else 1.0
    capacity = getattr(inst, "capacity", 0) or 0
    load_rate = (round(inst.total_demand / (len(reports) * capacity), 4)
                 if reports and capacity else 0.0)

    used_types, fixed_cost, type_ok = _assign_vehicle_types(inst, reports)

    tw_hard = bool(getattr(inst, "tw_hard", True))
    feasible = (overload <= 1e-9 and duplicated == 0 and missing == 0
                and (tw_violation <= 1e-9 or not tw_hard) and type_ok)

    return {
        "vehicles": len(reports),
        "total_distance": total_distance,
        "overload": round(overload, 2),
        "tw_violation": tw_violation,
        "wait_time": wait_time,
        "visited": len(set(visited)),
        "duplicated": duplicated,
        "missing": missing,
        "late_customers": late_customers,
        "on_time_rate": on_time_rate,
        "load_rate": load_rate,
        "used_types": used_types,
        "fixed_cost": round(fixed_cost, 2),
        "total_cost": round(total_distance + fixed_cost, 2),
        "feasible": feasible,
        "routes": reports,
    }


def _assign_vehicle_types(inst, reports):
    """按载重从大到小分配车型（够装且还有余量），返回（各车型用量、固定成本、是否全部装得下）"""
    types = sorted(inst.effective_types(), key=lambda t: t.capacity)
    left = {t.name: t.count for t in types}
    used: dict[str, int] = {}
    fixed = 0.0
    ok = True
    for rep in sorted(reports, key=lambda r: r.load, reverse=True):
        chosen = None
        for t in types:
            if t.capacity + 1e-9 >= rep.load and left[t.name] > 0:
                chosen = t
                break
        if chosen is None:
            ok = False
            continue
        left[chosen.name] -= 1
        used[chosen.name] = used.get(chosen.name, 0) + 1
        fixed += chosen.fixed_cost
    return used, fixed, ok


def format_report(inst, ev: dict) -> str:
    """把评价结果排版成能直接看的文本。"""
    return "\n".join([
        f"    车辆数        : {ev['vehicles']}",
        f"    总里程        : {ev['total_distance']:.2f}",
        f"    载重超限      : {ev['overload']:.2f}",
        f"    时间窗违反    : {ev['tw_violation']:.2f}",
        f"    等待时间合计  : {ev['wait_time']:.2f}",
        f"    客户覆盖      : {ev['visited']}/{inst.n_customers}"
        f"（重复 {ev['duplicated']}，遗漏 {ev['missing']}）",
        f"    准时率        : {ev.get('on_time_rate', 1.0) * 100:.1f}%"
        f"（晚到 {ev.get('late_customers', 0)} 个）",
        f"    装载率        : {ev.get('load_rate', 0.0) * 100:.1f}%",
        f"    可行解        : {'是 ✅' if ev['feasible'] else '否 ❌'}",
    ])


def nearest_neighbor(inst, allow_time_window_violation: bool = True) -> list[list[int]]:
    """最近邻构造启发式——M1 阶段用来验证数据层，M2 会换成蚁群。

    每次在"装得下 + 时间窗允许"的未访问客户里挑最近的一个；没有可选的就把车开回仓库换下一辆。
    """
    unvisited = set(inst.customer_ids())
    routes: list[list[int]] = []

    while unvisited:
        route: list[int] = []
        load = 0.0
        prev = DEPOT
        t = 0.0

        while True:
            best: int | None = None
            best_dist = float("inf")
            for cid in unvisited:
                c = inst.customers[cid]
                if load + c.demand > inst.capacity:
                    continue                                   # 装不下
                travel = inst.time(prev, cid)
                if not allow_time_window_violation and t + travel > c.due:
                    continue                                   # 赶不上时间窗
                if inst.dist(prev, cid) < best_dist:
                    best, best_dist = cid, inst.dist(prev, cid)
            if best is None:
                break

            c = inst.customers[best]
            t = max(t + inst.time(prev, best), c.ready) + c.service
            load += c.demand
            route.append(best)
            prev = best
            unvisited.discard(best)

        if not route:                                          # 兜底：避免死循环
            route.append(unvisited.pop())
        routes.append(route)

    return routes
