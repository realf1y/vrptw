# -*- coding: utf-8 -*-
"""M1-1｜Solomon 算例解析 + 距离矩阵

设计原则：**只用标准库**，不引入任何第三方依赖 —— 换任何机器上直接能跑。

支持两种格式
------------
1) Solomon 标准格式（网上下载的真实算例就是这种）::

       C101

       VEHICLE
       NUMBER     CAPACITY
         25         200

       CUSTOMER
       CUST NO.   XCOORD.   YCOORD.   DEMAND   READY TIME   DUE DATE   SERVICE TIME
            0        40        50         0           0        1236           0
            1        45        68        10         912         967          90

2) 简化 CSV：每行 ``x,y,demand,ready,due,service``；第一行是仓库。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VehicleType:
    """车型：不同载重、数量与固定成本（多车型场景用）"""

    name: str
    capacity: float
    count: int
    fixed_cost: float = 0.0


@dataclass(frozen=True)
class Customer:
    """一个客户点（id=0 表示仓库）。"""

    id: int
    x: float
    y: float
    demand: float
    ready: float
    due: float
    service: float


class Instance:
    """VRPTW 算例：仓库是 customers[0]，其余是客户。"""

    def __init__(self, name: str, capacity: float, vehicle_count: int,
                 customers: list[Customer], speed: float = 1.0,
                 tw_hard: bool = True) -> None:
        if len(customers) < 2:
            raise ValueError("算例至少需要 1 个仓库 + 1 个客户")
        self.name = name
        self.capacity = float(capacity)
        self.vehicle_count = int(vehicle_count)
        self.customers = customers
        self.speed = float(speed)          # 车速：行驶时间 = 距离 / 车速
        self.tw_hard = bool(tw_hard)       # True=硬时间窗（违反即不可行）
        self.priority: dict[int, float] = {}   # 客户优先级（由 M5 场景配置写入）
        self.depots: list[int] = [0]           # 仓库列表（客户 id，默认单仓库）
        self.vehicle_types: list[VehicleType] = []   # 空 = 单一车型
        self._build_distance_matrix()

    def _build_distance_matrix(self) -> None:
        n = len(self.customers)
        m = [[0.0] * n for _ in range(n)]
        for i in range(n):
            ci = self.customers[i]
            for j in range(i + 1, n):
                cj = self.customers[j]
                d = round(math.hypot(ci.x - cj.x, ci.y - cj.y), 2)  # Solomon 惯例：保留 2 位
                m[i][j] = d
                m[j][i] = d
        self.dist_matrix = m

    # ---- 便捷属性 ----
    @property
    def n_customers(self) -> int:
        return len(self.customers) - 1

    @property
    def depot(self) -> Customer:
        return self.customers[0]

    @property
    def total_demand(self) -> float:
        return sum(c.demand for c in self.customers)

    def dist(self, i: int, j: int) -> float:
        return self.dist_matrix[i][j]

    def time(self, i: int, j: int) -> float:
        """行驶时间 = 距离 / 车速（车速默认 1.0，即直接把距离当时间用）"""
        return self.dist_matrix[i][j] / self.speed

    def effective_types(self) -> list[VehicleType]:
        """没配多车型时，退化成单一车型（载重/数量取算例自带值）"""
        if self.vehicle_types:
            return list(self.vehicle_types)
        return [VehicleType("默认", self.capacity, self.vehicle_count, 0.0)]

    def max_capacity(self) -> float:
        return max(t.capacity for t in self.effective_types())

    def customer_ids(self) -> list[int]:
        return list(range(1, len(self.customers)))

    def describe(self) -> str:
        extra = f"｜车速 {self.speed:g}" if self.speed != 1.0 else ""
        return (f"算例 {self.name}：客户 {self.n_customers} 个｜车辆上限 {self.vehicle_count}｜"
                f"载重上限 {self.capacity:g}｜总需求 {self.total_demand:g}{extra}")


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
def _numeric_tokens(line: str) -> list[float]:
    """整行都是数字才返回数字列表，否则返回空列表（用于跳过表头/噪声行）。"""
    out: list[float] = []
    for tok in line.replace(",", " ").split():
        try:
            out.append(float(tok))
        except ValueError:
            return []
    return out


def parse_solomon(path: str | Path, default_capacity: float = 200.0,
                  default_vehicles: int | None = None, speed: float = 1.0,
                  tw_hard: bool = True) -> Instance:
    """读入 Solomon 标准格式（或简化 CSV）算例，返回 Instance。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"算例文件不存在：{path}")

    text = path.read_text(encoding="utf-8", errors="ignore")
    section: str | None = None
    name: str | None = None
    vehicle_count: int | None = None
    capacity: float | None = None
    customers: list[Customer] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        key = line.upper()
        if key.startswith("VEHICLE"):
            section = "vehicle"
            continue
        if key.startswith("CUSTOMER"):
            section = "customer"
            continue

        nums = _numeric_tokens(line)
        if not nums:
            if name is None and section is None:
                name = line                      # 第一行通常是算例名，如 C101
            continue

        if section == "vehicle":
            if vehicle_count is None and len(nums) >= 2:
                vehicle_count, capacity = int(nums[0]), float(nums[1])
            continue

        if section == "customer":
            if len(nums) >= 7:
                customers.append(Customer(
                    id=int(nums[0]), x=nums[1], y=nums[2], demand=nums[3],
                    ready=nums[4], due=nums[5], service=nums[6],
                ))
            continue

        # 没有段落标记 → 按简化 CSV 处理
        if len(nums) >= 6:
            customers.append(Customer(
                id=len(customers), x=nums[0], y=nums[1], demand=nums[2],
                ready=nums[3], due=nums[4], service=nums[5],
            ))

    if not customers:
        raise ValueError(f"{path.name}：没解析到客户数据。"
                         "预期是 Solomon 标准格式（含 VEHICLE / CUSTOMER 两段）")

    if vehicle_count is None:
        vehicle_count = default_vehicles or len(customers)
    if capacity is None:
        capacity = default_capacity

    return Instance(name or path.stem, capacity, vehicle_count, customers,
                    speed=speed, tw_hard=tw_hard)


# --------------------------------------------------------------------------
# 生成示例算例
# --------------------------------------------------------------------------
def write_solomon(inst: Instance, path: str | Path) -> Path:
    """把内存里的算例写回 Solomon 标准格式（能被 parse_solomon 原样读回）"""
    path = Path(path)
    lines = [
        inst.name, "",
        "VEHICLE", "NUMBER     CAPACITY",
        f"{inst.vehicle_count:>3d}      {inst.capacity:>7g}", "",
        "CUSTOMER",
        "CUST NO.   XCOORD.    YCOORD.    DEMAND   READY TIME   DUE DATE   SERVICE TIME", "",
    ]
    for c in inst.customers:
        lines.append(f"{c.id:>7d}  {c.x:>9.2f} {c.y:>9.2f} {c.demand:>10.2f} "
                     f"{c.ready:>11.2f} {c.due:>10.2f} {c.service:>11.2f}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def generate_sample(path: str | Path, n_customers: int = 25, capacity: float = 200,
                    vehicle_count: int = 25, seed: int = 1, clustered: bool = True,
                    min_width: float = 90, max_width: float = 180) -> Instance:
    """生成一个 Solomon 格式的**可行**示例算例（聚类型，带时间窗）。

    关键做法：**先用容量约束造一个参考解，再照着参考解的到达时间开时间窗**。
    这样生成出来的数据一定存在可行解 —— 否则分不清"算法差"还是"数据烂"，
    调试时会白白浪费好几天。

    真实算例请直接下载 Solomon Benchmark，这个函数只用于本地先把流程跑通。
    """
    rng = random.Random(seed)
    depot = (40.0, 50.0)

    # ---- 1) 坐标（聚类型 / 随机型） ----
    if clustered:
        centers = [(rng.uniform(10, 90), rng.uniform(10, 90))
                   for _ in range(max(2, n_customers // 6))]
        coords = []
        for k in range(n_customers):
            cx, cy = centers[k % len(centers)]
            coords.append((min(100.0, max(0.0, cx + rng.gauss(0, 8))),
                           min(100.0, max(0.0, cy + rng.gauss(0, 8)))))
    else:
        coords = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n_customers)]

    demands = [float(rng.choice([10, 15, 20, 25, 30])) for _ in range(n_customers)]
    services = [float(rng.choice([10, 20, 30])) for _ in range(n_customers)]

    def d(a, b):                       # 与 Instance 用同一种距离定义，保证一致
        return round(math.hypot(a[0] - b[0], a[1] - b[1]), 2)

    # ---- 2) 参考解：容量约束下的最近邻 ----
    unvisited = set(range(n_customers))
    routes: list[list[int]] = []
    while unvisited:
        route: list[int] = []
        load = 0.0
        prev = depot
        while True:
            cand = [k for k in unvisited if load + demands[k] <= capacity]
            if not cand:
                break
            k = min(cand, key=lambda k: d(prev, coords[k]))
            route.append(k)
            load += demands[k]
            prev = coords[k]
            unvisited.discard(k)
        if not route:
            route = [unvisited.pop()]
        routes.append(route)

    # ---- 3) 沿参考路线推进时间，得到每个客户的到达时刻 ----
    arrivals: dict[int, float] = {}
    for route in routes:
        t, prev = 0.0, depot
        for k in route:
            t += d(prev, coords[k])         # 到达
            arrivals[k] = t
            t += services[k]                # 服务结束
            prev = coords[k]

    # ---- 4) 按到达时刻前后开窗 → 参考解必然可行 ----
    rows: list[tuple] = [(0, depot[0], depot[1], 0.0, 0.0, 0.0, 0.0)]
    for k in range(n_customers):
        a = arrivals[k]
        ready = max(0.0, a - rng.uniform(20, 80))
        due = a + rng.uniform(min_width, max_width)
        rows.append((k + 1, round(coords[k][0], 2), round(coords[k][1], 2), demands[k],
                     round(ready, 2), round(due, 2), services[k]))

    horizon = round(max(r[5] for r in rows[1:]) + 120.0, 2)
    rows[0] = (0, depot[0], depot[1], 0.0, 0.0, horizon, 0.0)

    lines = [
        Path(path).stem, "",
        "VEHICLE", "NUMBER     CAPACITY",
        f"{vehicle_count:>3d}      {capacity:>7g}", "",
        "CUSTOMER",
        "CUST NO.   XCOORD.    YCOORD.    DEMAND   READY TIME   DUE DATE   SERVICE TIME", "",
    ]
    for (i, x, y, dm, r, du, s) in rows:
        lines.append(f"{i:>7d}  {x:>9.2f} {y:>9.2f} {dm:>10.2f} {r:>11.2f} {du:>10.2f} {s:>11.2f}")

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return parse_solomon(p)
