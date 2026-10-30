# -*- coding: utf-8 -*-
"""M7｜动态重优化（插单后局部重排）

业务背景
--------
车已经派出去、路线已经排好，这时来了新订单。全量重算要几十秒，而且会打乱所有司机的安排；
工程上的做法是**只动必要的部分**：把新订单插到增量最小的位置，再对受影响的路线做局部重排。

算法（三选一，按“先可行性、再里程”排序）
--------------------------------------
1. 直接插入：枚举“每条路线 × 每个插入位置”，算插入后的增量里程与时间窗违反量，
   载重装得下的才算候选；
2. 新开一台车：车还没派完（路线数 < 车辆上限）时，把新订单单独成线；
3. 局部重排：选定方案后，对受影响路线做 2-opt / Or-opt，并与其他路线做 relocate，
   直到总代价不再下降。

排序规则：(是否新增时间窗违反, 违反量, 增量里程) —— 不能为了省几公里把客户送晚。

对外接口
--------
    from dynamic import Order, insert_new_order, reoptimize_existing, holdout_eval

    inst2, routes2, plan = insert_new_order(inst, routes, Order(x, y, demand, ready, due, service))
    routes2, res = reoptimize_existing(inst, routes, cid)      # cid 已在算例里（“撤单再插回”）
    out = holdout_eval(inst, routes, k=3)                      # 抽掉 k 个客户再插回，测重排代价

命令行
------
    python dynamic.py demo                      # C101 上插 3 个新订单
    python dynamic.py holdout --k 5             # 抽掉 5 个客户再插回，输出对比
    python dynamic.py --instance data/solomon/25/c101.txt --iters 20 demo
"""
from __future__ import annotations

import random
import sys
import time
from dataclasses import dataclass

from instance import Customer, Instance, parse_solomon
from solution import DEPOT, evaluate, evaluate_route


@dataclass
class Order:
    """一张新订单（客户坐标、需求、时间窗、服务时长）"""
    x: float
    y: float
    demand: float
    ready: float = 0.0
    due: float = 1e9
    service: float = 10.0
    label: str = "新订单"

    def as_customer(self, cid: int) -> Customer:
        return Customer(cid, self.x, self.y, self.demand, self.ready, self.due, self.service)


def extend_instance(inst, order: Order):
    """把新订单追加进算例，返回（新算例，新客户号）。距离矩阵重建一次。"""
    cid = len(inst.customers)
    inst2 = Instance(inst.name + "+插单", inst.capacity, inst.vehicle_count,
                     list(inst.customers) + [order.as_customer(cid)],
                     speed=inst.speed, tw_hard=inst.tw_hard)
    inst2.priority = dict(inst.priority)
    inst2.depots = list(inst.depots)
    inst2.vehicle_types = list(inst.vehicle_types)
    return inst2, cid


# --------------------------------------------------------------------------
# 评价工具
# --------------------------------------------------------------------------
def _route_cost(inst, route, lam: float, reserve: float = 0.0) -> float:
    """路线代价 = 里程 + 时间窗惩罚 + 预留装载余量的软惩罚。

    reserve=0.08 表示“装载率超过 92% 就开始加罚”——重排时给后续插单留出装货空间，
    否则局部搜索会把某辆车塞满，再过 10 分钟来一单就只能新开一辆车。
    """
    rep = evaluate_route(inst, route)
    cost = rep.distance + lam * rep.tw_violation
    capacity = getattr(inst, "capacity", 0) or 0
    if capacity and reserve > 0:
        spare = capacity * (1.0 - reserve)
        if rep.load > spare:
            cost += 5.0 * (rep.load - spare)
    if rep.load > capacity + 1e-9:
        cost += 1e6 * (rep.load - capacity)
    return cost


def _solution_cost(inst, routes, lam: float, reserve: float = 0.0) -> float:
    return sum(_route_cost(inst, r, lam, reserve) for r in routes if r)


def _lam(inst, lam):
    """硬时间窗默认用极大惩罚（违约=不可接受），软时间窗才用温和系数。"""
    if lam is not None:
        return lam
    return 1e4 if getattr(inst, "tw_hard", True) else 10.0


# --------------------------------------------------------------------------
# 局部重排（不依赖蚁群，单独实现，便于 Web 端快速调用）
# --------------------------------------------------------------------------
def _two_opt(inst, route, lam, reserve=0.0):
    best, best_cost = list(route), _route_cost(inst, route, lam, reserve)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                c = _route_cost(inst, cand, lam, reserve)
                if c < best_cost - 1e-9:
                    best, best_cost, improved = cand, c, True
                    break
            if improved:
                break
    return best


def _or_opt(inst, route, lam, max_seg=2, reserve=0.0):
    best, best_cost = list(route), _route_cost(inst, route, lam, reserve)
    improved = True
    while improved:
        improved = False
        for seg_len in range(1, min(max_seg, len(best)) + 1):
            for i in range(len(best) - seg_len + 1):
                seg = best[i:i + seg_len]
                rest = best[:i] + best[i + seg_len:]
                for k in range(len(rest) + 1):
                    if k == i:
                        continue
                    cand = rest[:k] + seg + rest[k:]
                    c = _route_cost(inst, cand, lam, reserve)
                    if c < best_cost - 1e-9:
                        best, best_cost, improved = cand, c, True
                        break
                if improved:
                    break
            if improved:
                break
    return best


def _relocate(inst, routes, lam, reserve=0.0):
    """路线间搬一个客户，返回（新路线组, 是否改进）"""
    routes = [list(r) for r in routes if r]
    if len(routes) < 2:
        return routes, False
    costs = [_route_cost(inst, r, lam, reserve) for r in routes]
    best_gain, best_move = 1e-9, None
    for a, ra in enumerate(routes):
        if len(ra) <= 1:
            continue
        for idx, cid in enumerate(ra):
            new_a = ra[:idx] + ra[idx + 1:]
            if evaluate_route(inst, new_a).load > inst.capacity + 1e-9:
                continue
            gain_a = costs[a] - _route_cost(inst, new_a, lam, reserve)
            if gain_a <= 0:
                continue
            for b, rb in enumerate(routes):
                if b == a:
                    continue
                for k in range(len(rb) + 1):
                    new_b = rb[:k] + [cid] + rb[k:]
                    if evaluate_route(inst, new_b).load > inst.capacity + 1e-9:
                        continue
                    gain = gain_a + costs[b] - _route_cost(inst, new_b, lam, reserve)
                    if gain > best_gain:
                        best_gain, best_move = gain, (a, new_a, b, new_b)
    if best_move is None:
        return routes, False
    a, new_a, b, new_b = best_move
    routes[a], routes[b] = new_a, new_b
    return [r for r in routes if r], True


def improve(inst, routes, lam=None, rounds=2, reserve=0.08):
    """对整组路线做局部重排（2-opt + Or-opt + relocate），返回更优的路线组。

    reserve 默认 0.08：给后续插单留 8% 的装货余量（见 _route_cost 的说明）。
    """
    lam = _lam(inst, lam)
    routes = [list(r) for r in routes if r]
    for _ in range(max(1, rounds)):
        before = _solution_cost(inst, routes, lam, reserve)
        routes = [_or_opt(inst, _two_opt(inst, r, lam, reserve), lam, reserve=reserve)
                  for r in routes]
        routes, _ = _relocate(inst, routes, lam, reserve)
        if _solution_cost(inst, routes, lam, reserve) >= before - 1e-9:
            break
    return [r for r in routes if r]


# --------------------------------------------------------------------------
# 插单
# --------------------------------------------------------------------------
def _delay_table(inst, old_route, new_route):
    """受影响路线上，各客户到达时刻的前后差异"""
    if not old_route:
        return []
    old = evaluate_route(inst, old_route).arrivals
    new = evaluate_route(inst, new_route)
    pos = {cid: i for i, cid in enumerate(old_route)}
    npos = {cid: i for i, cid in enumerate(new_route)}
    rows = []
    for cid, i in pos.items():
        j = npos.get(cid)
        if j is None or j >= len(new.arrivals):
            continue
        rows.append((cid, round(old[i], 2), round(new.arrivals[j], 2),
                     round(new.arrivals[j] - old[i], 2)))
    return rows


def insert_customer(inst, routes, cid, lam=None, rounds=2):
    """把已在算例中的客户 cid 插进现有路线组，返回插单结果。"""
    lam = _lam(inst, lam)
    t0 = time.perf_counter()
    routes = [list(r) for r in routes if r]
    base_ev = evaluate(inst, routes)
    base_dist = base_ev["total_distance"]
    base_tw = base_ev["tw_violation"]
    capacity = inst.capacity
    vehicle_limit = inst.vehicle_count

    cands = []
    for ri, route in enumerate(routes):
        rep = evaluate_route(inst, route)
        for pos in range(len(route) + 1):
            cand = route[:pos] + [cid] + route[pos:]
            nrep = evaluate_route(inst, cand)
            if nrep.load > capacity + 1e-9:
                continue
            tw_delta = nrep.tw_violation - rep.tw_violation
            cands.append((1 if tw_delta > 1e-9 else 0, round(tw_delta, 4),
                          round(nrep.distance - rep.distance, 2), ri, pos, cand))
    if len(routes) < vehicle_limit:
        solo = [cid]
        rep = evaluate_route(inst, solo)
        cands.append((1 if rep.tw_violation > 1e-9 else 0, round(rep.tw_violation, 4),
                      round(rep.distance, 2), -1, 0, solo))

    if not cands:
        raise ValueError("没有任何可插入的位置：载重上限过小，建议新开车辆或放宽载重")

    cands.sort(key=lambda x: (x[0], x[1], x[2]))
    _flag, _tw, _dd, ri, pos, new_route = cands[0]

    routes2 = [list(r) for r in routes]
    if ri == -1:
        routes2.append(new_route)
        action = "新开车辆"
    else:
        routes2[ri] = new_route
        action = "插入路线 " + str(ri + 1) + " 第 " + str(pos + 1) + " 位"

    delays = []
    if ri >= 0:
        delays = [d for d in _delay_table(inst, routes[ri], new_route) if d[0] != cid]

    # ---- 局部重排：只改受影响的路线，并允许与其他路线互搬客户 ----
    improved = improve(inst, routes2, lam=lam, rounds=rounds) if rounds else routes2
    after_ev = evaluate(inst, improved)
    plain_ev = evaluate(inst, routes2)
    if (after_ev["tw_violation"], after_ev["total_distance"]) > (plain_ev["tw_violation"],
                                                                plain_ev["total_distance"]):
        improved, after_ev = routes2, plain_ev

    if ri >= 0:
        best_route = next((r for r in improved if cid in r), new_route)
        delays = [d for d in _delay_table(inst, routes[ri], best_route) if d[0] != cid]

    return {
        "customer": cid,
        "action": action,
        "route_index": ri,
        "position": pos,
        "routes": improved,
        "before": {"distance": base_dist, "vehicles": base_ev["vehicles"],
                   "tw_violation": base_tw, "on_time_rate": base_ev["on_time_rate"]},
        "after": {"distance": after_ev["total_distance"], "vehicles": after_ev["vehicles"],
                  "tw_violation": after_ev["tw_violation"],
                  "on_time_rate": after_ev["on_time_rate"]},
        "delta_distance": round(after_ev["total_distance"] - base_dist, 2),
        "delta_tw": round(after_ev["tw_violation"] - base_tw, 2),
        "delays": delays,
        "seconds": round(time.perf_counter() - t0, 3),
    }


def insert_new_order(inst, routes, order: Order, lam=None, rounds=2):
    """插入一张真正的新订单（不在算例里），返回（新算例, 新路线组, 结果）"""
    inst2, cid = extend_instance(inst, order)
    res = insert_customer(inst2, routes, cid, lam=lam, rounds=rounds)
    res["label"] = order.label
    return inst2, res["routes"], res


def reoptimize_existing(inst, routes, cid, lam=None, rounds=2):
    """撤掉 cid 再插回（模拟订单改约/临时撤单再派），返回（路线组, 结果）"""
    routes = [[c for c in r if c != cid] for r in routes]
    routes = [r for r in routes if r]
    return insert_customer(inst, routes, cid, lam=lam, rounds=rounds)


# --------------------------------------------------------------------------
# 实验：抽掉 k 个客户再插回，衡量“重排”相对“全量重算”的代价
# --------------------------------------------------------------------------
def holdout_eval(inst, base_routes, k=3, seed=1, lam=None):
    """从已解方案里抽掉 k 个客户，再逐个作为“新订单”插回，记录里程与耗时。"""
    rng = random.Random(seed)
    base_ev = evaluate(inst, base_routes)
    pool = [cid for r in base_routes for cid in r if len(r) >= 3]
    chosen = rng.sample(pool, min(k, len(pool)))

    routes = [list(r) for r in base_routes]
    for cid in chosen:
        routes = [[c for c in r if c != cid] for r in routes]
    routes = [r for r in routes if r]

    no_reopt = [list(r) for r in routes]
    rows = []
    for cid in chosen:
        res = insert_customer(inst, routes, cid, lam=lam, rounds=2)
        routes = res["routes"]
        rows.append({"order": cid, "action": res["action"],
                     "delta_distance": res["delta_distance"],
                     "delta_tw": res["delta_tw"], "seconds": res["seconds"],
                     "delays": len([d for d in res["delays"] if d[3] > 1e-6])})
        # 对照组：只做最便宜插入，不做局部重排
        best = None
        for ri, route in enumerate(no_reopt):
            rep = evaluate_route(inst, route)
            for pos in range(len(route) + 1):
                cand = route[:pos] + [cid] + route[pos:]
                nrep = evaluate_route(inst, cand)
                if nrep.load > inst.capacity + 1e-9:
                    continue
                key = (1 if nrep.tw_violation > rep.tw_violation else 0,
                       nrep.tw_violation - rep.tw_violation, nrep.distance - rep.distance)
                if best is None or key < best[0]:
                    best = (key, ri, cand)
        if best is not None:
            no_reopt[best[1]] = best[2]

    after_ev = evaluate(inst, routes)
    plain_ev = evaluate(inst, no_reopt)
    return {
        "customers": chosen,
        "base": {"distance": base_ev["total_distance"], "vehicles": base_ev["vehicles"],
                 "on_time_rate": base_ev["on_time_rate"]},
        "rerouted": {"distance": after_ev["total_distance"], "vehicles": after_ev["vehicles"],
                     "on_time_rate": after_ev["on_time_rate"],
                     "tw_violation": after_ev["tw_violation"]},
        "plain_insert": {"distance": plain_ev["total_distance"], "vehicles": plain_ev["vehicles"],
                         "on_time_rate": plain_ev["on_time_rate"],
                         "tw_violation": plain_ev["tw_violation"]},
        "rows": rows,
        "seconds": round(sum(r["seconds"] for r in rows), 3),
    }


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------
def _print_plan(title, res):
    print()
    print("[" + title + "] 客户 " + str(res["customer"]) + "｜" + res["action"])
    print("    里程 %.2f → %.2f（%+.2f）｜车辆 %d → %d｜准时率 %.1f%%" % (
        res["before"]["distance"], res["after"]["distance"], res["delta_distance"],
        res["before"]["vehicles"], res["after"]["vehicles"],
        res["after"]["on_time_rate"] * 100))
    late = [d for d in res["delays"] if d[3] > 1e-6]
    print("    受影响客户 %d 个，其中延后 %d 个｜重排耗时 %.3fs" % (
        len(res["delays"]), len(late), res["seconds"]))
    for cid, a0, a1, d in res["delays"][:5]:
        print("      · 客户 %d：%.1f → %.1f（%+.1f）" % (cid, a0, a1, d))


def cmd_demo(inst, iters: int, n_orders: int, seed: int) -> None:
    from aco import ACOConfig, solve_aco

    t0 = time.perf_counter()
    res = solve_aco(inst, ACOConfig(max_iter=iters, seed=seed))
    base_sec = time.perf_counter() - t0
    routes = [list(r) for r in res["routes"]]
    print("基础方案：%s｜里程 %.2f｜车辆 %d｜%d 代 %.1fs" % (
        inst.name, res["distance"], res["vehicles"], iters, base_sec))

    horizon = inst.depot.due
    rng = random.Random(seed + 7)
    for k in range(n_orders):
        order = Order(x=round(rng.uniform(10, 90), 2), y=round(rng.uniform(10, 90), 2),
                      demand=float(rng.choice([10, 15, 20, 25])),
                      ready=0.0, due=round(min(horizon, rng.uniform(600, 1100)), 2),
                      service=10.0, label="新订单" + str(k + 1))
        inst, routes, res1 = insert_new_order(inst, routes, order)
        _print_plan(order.label, res1)


def cmd_holdout(inst, iters: int, k: int, seed: int) -> None:
    from aco import ACOConfig, solve_aco

    t0 = time.perf_counter()
    base = solve_aco(inst, ACOConfig(max_iter=iters, seed=seed))
    print("基础方案（%d 代，全量求解 %.1fs）：里程 %.2f｜车辆 %d" % (
        iters, time.perf_counter() - t0, base["distance"], base["vehicles"]))

    out = holdout_eval(inst, base["routes"], k=k, seed=seed)
    print()
    print("抽掉客户 " + str(out["customers"]) + " 后逐个插回：")
    print("%-6s%-18s%9s%8s%9s%9s" % ("订单", "动作", "Δ里程", "Δ违反", "延后客户", "耗时(s)"))
    for r in out["rows"]:
        print("%-6d%-18s%+9.2f%8.2f%9d%9.3f" % (r["order"], r["action"], r["delta_distance"],
                                                r["delta_tw"], r["delays"], r["seconds"]))
    b, rr, pi = out["base"], out["rerouted"], out["plain_insert"]
    print()
    print("原始方案      里程 %8.2f｜车辆 %2d｜准时率 %5.1f%%" % (b["distance"], b["vehicles"], b["on_time_rate"] * 100))
    print("插单+局部重排 里程 %8.2f（%+.2f%%）｜车辆 %2d｜准时率 %5.1f%%｜违反 %.2f" % (
        rr["distance"], 100 * (rr["distance"] - b["distance"]) / b["distance"], rr["vehicles"],
        rr["on_time_rate"] * 100, rr["tw_violation"]))
    print("插单不重排    里程 %8.2f（%+.2f%%）｜车辆 %2d｜准时率 %5.1f%%｜违反 %.2f" % (
        pi["distance"], 100 * (pi["distance"] - b["distance"]) / b["distance"], pi["vehicles"],
        pi["on_time_rate"] * 100, pi["tw_violation"]))
    print("重排总耗时 %.3fs" % out["seconds"])


def main() -> None:
    args = sys.argv[1:]
    instance = "data/solomon/100/c101.txt"
    iters, k, n_orders, seed = 40, 3, 3, 1
    cmd = "demo"
    if args and args[0] in {"demo", "holdout"}:
        cmd = args.pop(0)
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
        elif a == "--k" and nxt:
            k = int(nxt); i += 1
        elif a.startswith("--k="):
            k = int(a.split("=", 1)[1])
        elif a == "--n" and nxt:
            n_orders = int(nxt); i += 1
        elif a.startswith("--n="):
            n_orders = int(a.split("=", 1)[1])
        elif a == "--seed" and nxt:
            seed = int(nxt); i += 1
        i += 1

    inst = parse_solomon(instance)
    print(inst.describe())
    if cmd == "holdout":
        cmd_holdout(inst, iters, k, seed)
    else:
        cmd_demo(inst, iters, n_orders, seed)


if __name__ == "__main__":
    main()
