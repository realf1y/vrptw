# -*- coding: utf-8 -*-
"""M2｜蚁群算法引擎（带时间窗的车辆路径问题 VRPTW）—— 整个项目的心脏

给定算例，用蚁群算法求出一组路线，使总里程最小。

一次迭代里发生什么
------------------
1. **构造解**：每只蚂蚁从仓库出发，按概率选下一个客户
       p(prev → j) ∝ τ[prev][j]^α · η(prev, j)^β
   其中 η 是启发式因子（考虑距离 + 等待时间 + 时间窗裕度）；
   装不下 / 赶不上时间窗的客户直接不许选（约束在构造时即时拦住）。
2. **局部搜索**：对本代最优解做 2-opt / Or-opt / 路线间 relocate，把路线捋顺。
3. **评价**：用 M1 的 evaluate() 打分（里程 + 时间窗惩罚）。
4. **更新信息素**：挥发，然后往本代最优 / 全局最优路径上加浓；
   可选 MMAS 上下界限制（防止早熟）。

基线 vs 改进
------------
- 基线：eta=1/距离，无精英、无 MMAS、无局部搜索
- 改进：时间窗启发式 η + 精英/MMAS 信息素 + 混合局部搜索

对外接口
--------
    from aco import ACOConfig, baseline_config, improved_config, solve_aco
    res = solve_aco(inst)                                 # 默认=改进版
    res = solve_aco(inst, baseline_config(seed=1))        # 基线
    res["routes"] / ["distance"] / ["vehicles"] / ["history"] / ["seconds"]
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from solution import evaluate, evaluate_route

DEPOT = 0


@dataclass
class ACOConfig:
    # ---- 基本参数 ----
    n_ants: int = 20            # 蚂蚁数（每代构造多少个解）
    max_iter: int = 100         # 迭代代数
    alpha: float = 1.0          # 信息素重要度 α
    beta: float = 3.0           # 启发式重要度 β
    rho: float = 0.1            # 信息素挥发率 ρ
    q: float = 100.0            # 信息素强度 Q
    tau0: float = 1.0           # 初始信息素
    seed: int = 1               # 随机种子（固定 → 结果可复现）
    vehicle_penalty: float = 0.0  # 多派一辆车的惩罚（默认不惩罚，纯比里程）

    # ---- 创新点②：带时间窗的启发式因子 η ----
    w_wait: float = 0.5         # 等待时间权重
    w_slack: float = 5.0        # 时间窗裕度权重

    # ---- 创新点③：信息素策略 ----
    elitist: bool = True        # 精英策略：全局最优额外加浓
    elite_weight: float = 2.0
    mmas: bool = True           # 信息素上下界（MMAS）

    # ---- 创新点④：局部搜索 ----
    local_search: bool = True
    ls_rounds: int = 3          # 局部搜索最多做几轮

    # ---- 目标函数 ----
    lambda_tw: float = 10.0     # 时间窗违反量的惩罚系数


def baseline_config(**overrides) -> ACOConfig:
    """标准蚁群（对照组）：η=1/距离，无精英、无 MMAS、无局部搜索。"""
    cfg = ACOConfig(**overrides)
    cfg.w_wait = 0.0
    cfg.w_slack = 0.0
    cfg.elitist = False
    cfg.mmas = False
    cfg.local_search = False
    return cfg


def improved_config(**overrides) -> ACOConfig:
    """改进版：全部创新点打开。"""
    return ACOConfig(**overrides)


class AntColonySolver:
    def __init__(self, inst, config: ACOConfig | None = None) -> None:
        self.inst = inst
        self.cfg = config or improved_config()
        self.rng = random.Random(self.cfg.seed)
        self.n = len(inst.customers)
        self.history: list[float] = []
        self.tau: list[list[float]] = []
        self.tau_max = self.cfg.tau0
        self.tau_min = self.cfg.tau0 * 0.1

    # ---------------- 目标函数（越小越好） ----------------
    def _route_cost(self, route: list[int]) -> float:
        if not route:
            return 0.0
        rep = evaluate_route(self.inst, route)
        cost = rep.distance + self.cfg.lambda_tw * rep.tw_violation
        if rep.load > self.inst.capacity + 1e-9:            # 载重超限 → 重罚
            cost += 1e6 * (rep.load - self.inst.capacity)
        return cost

    def _solution_cost(self, routes: list[list[int]]) -> float:
        used = [r for r in routes if r]
        return sum(self._route_cost(r) for r in used) + self.cfg.vehicle_penalty * len(used)

    # ---------------- 启发式因子 η（创新点②） ----------------
    def _eta(self, d: float, wait: float, slack: float) -> float:
        """d 距离、wait 需等待多久、slack 距截止还剩多少时间。"""
        penalty = self.cfg.w_wait * wait + self.cfg.w_slack / (slack + 1.0)
        return 1.0 / (d + penalty + 1e-6)

    # ---------------- 构造解 ----------------
    def _roulette(self, cands: list[tuple], weights: list[float]) -> tuple:
        total = sum(weights)
        if total <= 0:
            return self.rng.choice(cands)
        r = self.rng.random() * total
        acc = 0.0
        for c, w in zip(cands, weights):
            acc += w
            if r <= acc:
                return c
        return cands[-1]

    def _construct(self) -> list[list[int]]:
        inst, cfg = self.inst, self.cfg
        unvisited = set(inst.customer_ids())
        routes: list[list[int]] = []

        while unvisited:
            route: list[int] = []
            load = 0.0
            t = 0.0
            prev = DEPOT

            while True:
                cands: list[tuple] = []
                for cid in unvisited:
                    c = inst.customers[cid]
                    if load + c.demand > inst.capacity:
                        continue                                    # 装不下
                    d = inst.dist(prev, cid)                        # 里程（用于启发式因子 η）
                    trav = inst.time(prev, cid)                     # 行驶时间 = 里程 / 车速
                    arrival = t + trav
                    start = max(arrival, c.ready)
                    if start > c.due:
                        continue                                    # 赶不上时间窗
                    cands.append((cid, d, trav, start - arrival, c.due - start))

                if not cands:
                    if route:
                        break                                       # 这辆车送完了
                    # 空车也装不下 / 赶不上 → 强选"违反最小"的客户，保证算法终止
                    cid = min(
                        unvisited,
                        key=lambda x: max(0.0, max(t + inst.time(prev, x),
                                                    inst.customers[x].ready)
                                          - inst.customers[x].due),
                    )
                    c = inst.customers[cid]
                    t = max(t + inst.time(prev, cid), c.ready) + c.service
                    load += c.demand
                    route.append(cid)
                    unvisited.discard(cid)
                    prev = cid
                    continue

                tau_row = self.tau[prev]
                weights = [
                    (tau_row[cid] ** cfg.alpha) * (self._eta(d, wait, slack) ** cfg.beta)
                    for (cid, d, trav, wait, slack) in cands
                ]
                cid, d, trav, wait, slack = self._roulette(cands, weights)

                c = inst.customers[cid]
                t = max(t + trav, c.ready) + c.service
                load += c.demand
                route.append(cid)
                unvisited.discard(cid)
                prev = cid

            if route:
                routes.append(route)

        return routes

    # ---------------- 局部搜索（创新点④） ----------------
    def _two_opt(self, route: list[int]) -> list[int]:
        best = list(route)
        best_cost = self._route_cost(best)
        improved = True
        while improved:
            improved = False
            for i in range(len(best) - 1):
                for j in range(i + 2, len(best)):
                    cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                    c = self._route_cost(cand)
                    if c < best_cost - 1e-9:
                        best, best_cost, improved = cand, c, True
                        break
                if improved:
                    break
        return best

    def _or_opt(self, route: list[int], max_seg: int = 3) -> list[int]:
        best = list(route)
        best_cost = self._route_cost(best)
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
                        c = self._route_cost(cand)
                        if c < best_cost - 1e-9:
                            best, best_cost, improved = cand, c, True
                            break
                    if improved:
                        break
                if improved:
                    break
        return best

    def _relocate(self, routes: list[list[int]]) -> tuple[list[list[int]], bool]:
        """路线间搬移客户（最优改进，一次一步）。"""
        routes = [list(r) for r in routes if r]
        if len(routes) < 2:
            return routes, False
        costs = [self._route_cost(r) for r in routes]
        best_gain, best_move = 1e-9, None

        for a, ra in enumerate(routes):
            if len(ra) <= 1:
                continue
            for idx in range(len(ra)):
                cid = ra[idx]
                new_a = ra[:idx] + ra[idx + 1:]
                gain_a = costs[a] - self._route_cost(new_a)
                if gain_a <= 0:
                    continue
                for b, rb in enumerate(routes):
                    if b == a:
                        continue
                    for k in range(len(rb) + 1):
                        new_b = rb[:k] + [cid] + rb[k:]
                        gain = gain_a + costs[b] - self._route_cost(new_b)
                        if gain > best_gain:
                            best_gain, best_move = gain, (a, new_a, b, new_b)

        if best_move is None:
            return routes, False
        a, new_a, b, new_b = best_move
        routes[a], routes[b] = new_a, new_b
        return [r for r in routes if r], True

    def _local_search(self, routes: list[list[int]]) -> list[list[int]]:
        routes = [list(r) for r in routes if r]
        for _ in range(self.cfg.ls_rounds):
            before = self._solution_cost(routes)
            routes = [self._or_opt(self._two_opt(r)) for r in routes]
            routes, _ = self._relocate(routes)
            if self._solution_cost(routes) >= before - 1e-9:
                break
        return [r for r in routes if r]

    # ---------------- 信息素（创新点③） ----------------
    def _init_pheromone(self) -> None:
        n = self.n
        self.tau = [[self.cfg.tau0] * n for _ in range(n)]
        self.tau_max = self.cfg.tau0
        self.tau_min = self.cfg.tau0 * 0.1

    def _deposit(self, routes: list[list[int]], amount: float) -> None:
        for route in routes:
            prev = DEPOT
            for cid in route:
                self.tau[prev][cid] += amount
                self.tau[cid][prev] += amount
                prev = cid
            self.tau[prev][DEPOT] += amount
            self.tau[DEPOT][prev] += amount

    def _update_pheromone(self, iter_best, iter_cost, global_best, global_cost) -> None:
        cfg = self.cfg
        rho = cfg.rho
        for i in range(self.n):
            row = self.tau[i]
            for j in range(self.n):
                if i != j:
                    row[j] *= (1.0 - rho)

        if iter_best:
            self._deposit(iter_best, cfg.q / max(iter_cost, 1e-9))
        if cfg.elitist and global_best:
            self._deposit(global_best, cfg.elite_weight * cfg.q / max(global_cost, 1e-9))

        if cfg.mmas:
            best = max(global_cost, 1e-9)
            self.tau_max = 1.0 / (rho * best)
            self.tau_min = self.tau_max / (2.0 * self.n)
            for i in range(self.n):
                row = self.tau[i]
                for j in range(self.n):
                    if i == j:
                        continue
                    if row[j] > self.tau_max:
                        row[j] = self.tau_max
                    elif row[j] < self.tau_min:
                        row[j] = self.tau_min

    # ---------------- 主循环 ----------------
    def solve(self) -> dict:
        cfg = self.cfg
        self.progress_cb = None          # 可选：每代结束回调 (已做代数, 总代数, 当前最优代价)
        self._init_pheromone()
        self.history = []
        t0 = time.perf_counter()

        best_routes: list[list[int]] | None = None
        best_cost = float("inf")

        for _ in range(cfg.max_iter):
            iter_best_routes, iter_best_cost = None, float("inf")
            for _ in range(cfg.n_ants):
                routes = self._construct()
                cost = self._solution_cost(routes)
                if cost < iter_best_cost:
                    iter_best_routes, iter_best_cost = routes, cost

            if cfg.local_search and iter_best_routes is not None:
                ls_routes = self._local_search(iter_best_routes)
                ls_cost = self._solution_cost(ls_routes)
                if ls_cost < iter_best_cost:
                    iter_best_routes, iter_best_cost = ls_routes, ls_cost

            if iter_best_routes is not None and iter_best_cost < best_cost:
                best_routes = [list(r) for r in iter_best_routes]
                best_cost = iter_best_cost

            self.history.append(evaluate(self.inst, best_routes)["total_distance"])
            if self.progress_cb is not None:
                self.progress_cb(len(self.history), cfg.max_iter, best_cost)
            self._update_pheromone(iter_best_routes, iter_best_cost, best_routes, best_cost)

        elapsed = time.perf_counter() - t0
        metrics = evaluate(self.inst, best_routes)
        return {
            "routes": best_routes,
            "distance": metrics["total_distance"],
            "vehicles": metrics["vehicles"],
            "feasible": metrics["feasible"],
            "tw_violation": metrics["tw_violation"],
            "history": self.history,
            "iterations": cfg.max_iter,
            "seconds": round(elapsed, 2),
            "metrics": metrics,
        }


def solve_aco(inst, config: ACOConfig | None = None, **kwargs) -> dict:
    """便捷入口：不传 config 时用改进版参数。"""
    if config is None:
        config = ACOConfig(**kwargs) if kwargs else improved_config()
    return AntColonySolver(inst, config).solve()
