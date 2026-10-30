# -*- coding: utf-8 -*-
"""M11｜订单 Excel 导入（Orders from xlsx）

业务里订单不是 Solomon 算例，而是一张 Excel：客户名、坐标、需求、时间窗、服务时长。
本模块把它读成系统内部的算例对象，校验字段与取值，并写回 Solomon 格式，之后就能直接求解。

表头（中文或英文均可，顺序无所谓）
--------------------------------
    名称 / name      客户名（可空）
    经度 / x          x 坐标（数值）
    纬度 / y          y 坐标（数值）
    需求 / demand     需求量（>= 0）
    最早 / ready      最早到达时间（默认 0）
    最晚 / due        最晚到达时间（必须 >= 最早）
    服务 / service    服务时长（默认 10）
    类型 / type       仓库 / depot 或 客户 / customer（可选；不填则第一行当仓库）

用法
----
    python orders.py template --out data/orders_template.xlsx
    python orders.py import --xlsx data/orders_template.xlsx --out data/solomon/orders/demo.txt
    python orders.py import --xlsx 订单.xlsx --capacity 200 --vehicles 10 --name 校园配送
"""
from __future__ import annotations

import sys
from pathlib import Path

from instance import Customer, Instance, parse_solomon, write_solomon

HERE = Path(__file__).resolve().parent

ALIASES = {
    "name": {"名称", "客户名", "客户", "name", "customer", "id"},
    "x": {"经度", "x", "xcoord", "x坐标", "lon", "lng", "longitude"},
    "y": {"纬度", "y", "ycoord", "y坐标", "lat", "latitude"},
    "demand": {"需求", "需求量", "demand", "qty", "数量"},
    "ready": {"最早", "最早到达", "ready", "ready time", "开始"},
    "due": {"最晚", "最晚到达", "due", "due date", "截止"},
    "service": {"服务", "服务时长", "service", "service time", "停留"},
    "type": {"类型", "type", "kind", "类别"},
}


class OrderImportError(ValueError):
    """导入失败（字段缺失、取值非法等），消息可直接展示给用户。"""


def _norm(text) -> str:
    return str(text or "").strip().lower().replace(" ", "")


def _match(header: str) -> str | None:
    h = _norm(header)
    for key, names in ALIASES.items():
        if h in {_norm(n) for n in names}:
            return key
    return None


def _num(value, label: str, row: int, default=None) -> float:
    if value is None or str(value).strip() == "":
        if default is None:
            raise OrderImportError("第 %d 行的「%s」为空" % (row, label))
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise OrderImportError("第 %d 行的「%s」不是数字：%r" % (row, label, value))


def read_orders(path: str | Path) -> tuple[dict, list[dict]]:
    """读取 xlsx，返回（仓库行, 客户行列表）。字段名按别名匹配。"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise OrderImportError("缺少 openpyxl，请先 pip install openpyxl")

    path = Path(path)
    if not path.exists():
        raise OrderImportError("文件不存在：" + str(path))
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise OrderImportError("只支持 .xlsx（可先用 Excel 另存为 xlsx）")

    wb = load_workbook(str(path), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        raise OrderImportError("表格是空的")

    header_idx, mapping = None, {}
    for i, row in enumerate(rows[:10]):
        found = {}
        for j, cell in enumerate(row):
            key = _match(cell) if cell is not None else None
            if key:
                found[key] = j
        if {"x", "y", "demand"} <= set(found):
            header_idx, mapping = i, found
            break
    if header_idx is None:
        raise OrderImportError("没找到表头：至少需要 经度(x)、纬度(y)、需求(demand) 三列")

    orders, depot = [], None
    for r, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue
        rec = {}
        for key, col in mapping.items():
            rec[key] = row[col] if col < len(row) else None
        kind = _norm(rec.get("type"))
        item = {
            "name": str(rec.get("name") or ("仓库" if not orders else "客户%d" % (len(orders) + 1))),
            "x": _num(rec.get("x"), "经度", r),
            "y": _num(rec.get("y"), "纬度", r),
            "demand": _num(rec.get("demand"), "需求", r),
            "ready": _num(rec.get("ready"), "最早", r, default=0.0),
            "due": _num(rec.get("due"), "最晚", r, default=1e9),
            "service": _num(rec.get("service"), "服务", r, default=10.0),
        }
        if item["demand"] < 0:
            raise OrderImportError("第 %d 行需求为负数" % r)
        if item["due"] < item["ready"]:
            raise OrderImportError("第 %d 行最晚时间早于最早时间" % r)
        if kind in {"仓库", "depot", "warehouse", "仓"} or (depot is None and not orders and kind == ""):
            if depot is not None:
                raise OrderImportError("出现了两个仓库行（第 %d 行）" % r)
            depot = item
        else:
            orders.append(item)

    if not orders:
        raise OrderImportError("没有读到客户行")
    if depot is None:
        cx = sum(o["x"] for o in orders) / len(orders)
        cy = sum(o["y"] for o in orders) / len(orders)
        depot = {"name": "默认仓库", "x": round(cx, 2), "y": round(cy, 2),
                 "demand": 0.0, "ready": 0.0, "due": max(o["due"] for o in orders), "service": 0.0}
    return depot, orders


def build_instance(depot: dict, orders: list[dict], name: str = "订单导入",
                   capacity: float = 200.0, vehicles: int | None = None,
                   speed: float = 1.0) -> Instance:
    """把订单行变成 Instance（0 号是仓库，客户从 1 开始编号）。"""
    customers = [Customer(0, depot["x"], depot["y"], 0.0, 0.0,
                          float(depot["due"] if depot["due"] < 1e8 else max(o["due"] for o in orders)),
                          0.0)]
    for i, o in enumerate(orders, start=1):
        customers.append(Customer(i, o["x"], o["y"], o["demand"], o["ready"], o["due"], o["service"]))
    if vehicles is None:
        total = sum(o["demand"] for o in orders)
        vehicles = max(1, int(-(-total // capacity))) if capacity else len(orders)
    return Instance(name, capacity, vehicles, customers, speed=speed)


def import_xlsx(path, out: str | Path | None = None, name: str | None = None,
                capacity: float = 200.0, vehicles: int | None = None) -> tuple[Instance, Path]:
    depot, orders = read_orders(path)
    inst = build_instance(depot, orders, name=name or Path(path).stem,
                          capacity=capacity, vehicles=vehicles)
    out = Path(out) if out else HERE / "data" / "solomon" / "orders" / (inst.name + ".txt")
    write_solomon(inst, out)
    # 回读校验：确保写出去的文件能被主流程原样读回
    again = parse_solomon(out)
    if again.n_customers != inst.n_customers:
        raise OrderImportError("导出后回读客户数不一致：%d vs %d" % (again.n_customers, inst.n_customers))
    return inst, out


def make_template(path: str | Path) -> Path:
    """生成一份可直接填写的订单模板（1 个仓库 + 8 个客户）。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "订单"
    ws.append(["名称", "经度", "纬度", "需求", "最早", "最晚", "服务", "类型"])
    ws.append(["仓库", 40, 50, 0, 0, 1200, 0, "仓库"])
    rows = [
        ("校园超市", 45, 68, 10, 0, 300, 10),
        ("图书馆", 52, 42, 15, 0, 400, 10),
        ("一号楼", 30, 30, 20, 60, 360, 15),
        ("二号楼", 70, 25, 10, 120, 480, 10),
        ("食堂", 62, 60, 25, 180, 540, 20),
        ("体育馆", 20, 70, 10, 240, 600, 10),
        ("实验楼", 78, 72, 15, 300, 660, 15),
        ("宿舍区", 35, 15, 30, 360, 720, 20),
        ("行政楼", 55, 80, 10, 420, 780, 10),
    ]
    for r in rows:
        ws.append([r[0], r[1], r[2], r[3], r[4], r[5], r[6], "客户"])
    for col, width in zip("ABCDEFGH", [12, 10, 10, 10, 10, 10, 10, 10]):
        ws.column_dimensions[col].width = width
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "template"
    opts = {}
    i = 1
    while i < len(args):
        a = args[i]
        if a.startswith("--") and i + 1 < len(args):
            opts[a[2:]] = args[i + 1]
            i += 2
        else:
            i += 1

    if cmd == "template":
        p = make_template(opts.get("out", "data/orders_template.xlsx"))
        print("模板已生成：" + str(p))
        return
    if cmd == "import":
        src = opts.get("xlsx")
        if not src:
            raise SystemExit("用法：python orders.py import --xlsx 文件名.xlsx [--out ...] [--capacity 200] [--vehicles 10]")
        inst, out = import_xlsx(src, opts.get("out"), opts.get("name"),
                                float(opts.get("capacity", 200)),
                                int(opts["vehicles"]) if opts.get("vehicles") else None)
        print("导入成功：" + inst.describe())
        print("已写出：" + str(out))
        print("车辆数（按总需求/载重估算）：%d" % inst.vehicle_count)
        return
    raise SystemExit("未知命令：" + cmd)


if __name__ == "__main__":
    main()
