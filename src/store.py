# -*- coding: utf-8 -*-
"""数据库层（SQLite / MySQL 双后端）—— 支撑报告第三章「项目系统的数据库设计」

四张表：`instance`（算例）/ `scene`（场景）/ `experiment`（实验记录）/ `solution`（方案路线），
外加 KPI 汇总视图 `kpi_view`。建表 SQL 由 `db.py` 提供。

用法::

    python store.py status                       # 当前连哪个库、各表多少行
    python store.py init                         # 建库建表（默认 SQLite）
    python store.py init --mysql                 # 建库建表（MySQL，需先配好 mysql_config.json）
    python store.py import results/experiments_100_10x.csv
    python store.py kpi 100                      # KPI 汇总
    python store.py save data/solomon/100/c101.txt --iters=20
    python store.py schema [--mysql]             # 打印建表 SQL（写报告用）
    python store.py example-config               # 生成 mysql_config.example.json
"""
from __future__ import annotations

import csv as _csv
import json
import sys
from pathlib import Path

from aco import ACOConfig, solve_aco
from db import connect, schema, write_example_config
from instance import parse_solomon
from solution import evaluate_route

HERE = Path(__file__).resolve().parent
TABLES = ["instance", "scene", "experiment", "solution"]


def parse_args(argv: list[str]) -> tuple[str, list[str], int]:
    plain = [a for a in argv if not a.startswith("--")]
    flags = [a.split("=")[0] for a in argv if a.startswith("--")]
    backend = "mysql" if "--mysql" in flags else "sqlite"
    iters = 60
    for a in argv:
        if a.startswith("--iters"):
            iters = int(a.split("=")[1])
    return backend, plain, iters


# --------------------------------------------------------------------------
# 业务操作（db 是 db.Db 实例，SQLite / MySQL 通用）
# --------------------------------------------------------------------------
def get_or_create_instance(db, inst, source_path: str = "", size: str = "") -> int:
    rows = db.query("SELECT id FROM instance WHERE name = ?", (inst.name,))
    if rows:
        return rows[0][0]
    cur = db.execute(
        "INSERT INTO instance (name, size, n_customers, capacity, vehicle_count, speed,"
        " total_demand, source_path) VALUES (?,?,?,?,?,?,?,?)",
        (inst.name, size, inst.n_customers, inst.capacity, inst.vehicle_count,
         inst.speed, inst.total_demand, source_path))
    db.commit()
    return cur.lastrowid


def get_or_create_scene(db, config: dict) -> int:
    name = config.get("name") or "unnamed"
    rows = db.query("SELECT id FROM scene WHERE name = ?", (name,))
    if rows:
        return rows[0][0]
    cur = db.execute("INSERT INTO scene (name, config_json, note) VALUES (?,?,?)",
                     (name, json.dumps(config, ensure_ascii=False), config.get("note", "")))
    db.commit()
    return cur.lastrowid


def insert_experiment(db, instance_id: int, method: str, run_index: int, metrics: dict,
                      seed: int | None = None, iterations: int | None = None,
                      scene_id: int | None = None, seconds: float | None = None) -> int:
    cur = db.execute(
        "INSERT INTO experiment (instance_id, scene_id, method, run_index, seed, iterations,"
        " distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (instance_id, scene_id, method, run_index, seed, iterations,
         metrics.get("total_distance"), metrics.get("vehicles"),
         1 if metrics.get("feasible") else 0, metrics.get("tw_violation"),
         metrics.get("on_time_rate"), metrics.get("load_rate"),
         seconds if seconds is not None else metrics.get("seconds")))
    db.commit()
    return cur.lastrowid


def insert_solution(db, experiment_id: int, inst, routes: list[list[int]]) -> None:
    for idx, route in enumerate(routes, start=1):
        rep = evaluate_route(inst, route)
        db.execute(
            "INSERT INTO solution (experiment_id, route_index, customers, stop_count,"
            " route_length, route_load) VALUES (?,?,?,?,?,?)",
            (experiment_id, idx, ",".join(str(c) for c in route), len(route),
             round(rep.distance, 2), rep.load))
    db.commit()


def import_experiments_csv(db, csv_path: Path | str) -> int:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)
    data_dir = HERE / "data" / "solomon"
    n = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        for row in _csv.DictReader(fh):
            name = (row.get("instance") or "").upper()
            if not name or not row.get("distance"):
                continue
            size = row.get("size") or ""
            src = data_dir / size / f"{name.lower()}.txt"
            inst = parse_solomon(src)
            iid = get_or_create_instance(db, inst, str(src), size)
            db.execute(
                "INSERT INTO experiment (instance_id, method, run_index, distance, vehicles,"
                " feasible, tw_violation, on_time_rate, load_rate, seconds)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (iid, row.get("method"), int(row.get("run") or 0),
                 float(row["distance"]), int(row.get("vehicles") or 0),
                 1 if str(row.get("feasible")).lower() in {"true", "1"} else 0,
                 float(row.get("tw_violation") or 0),
                 float(row.get("on_time_rate") or 0) or None,
                 float(row.get("load_rate") or 0) or None,
                 float(row.get("seconds") or 0)))
            n += 1
    db.commit()
    return n


def import_scenes_from_folder(db) -> int:
    """把 scenes/*.json 里的场景写进 scene 表。"""
    n = 0
    for f in sorted((HERE / "scenes").glob("*.json")):
        cfg = json.loads(f.read_text(encoding="utf-8"))
        before = db.query("SELECT COUNT(*) FROM scene")[0][0]
        get_or_create_scene(db, cfg)
        after = db.query("SELECT COUNT(*) FROM scene")[0][0]
        n += (after - before)
    return n


def cmd_status(db, backend: str) -> None:
    print(f"数据库：{db.describe}")
    for t in TABLES:
        try:
            print(f"  {t:<12} {db.query(f'SELECT COUNT(*) FROM {t}')[0][0]} 行")
        except Exception as exc:
            print(f"  {t:<12} 不可用（{type(exc).__name__}）")
    try:
        print(f"  {'kpi_view':<12} {len(db.query('SELECT * FROM kpi_view'))} 行（视图）")
    except Exception:
        print(f"  {'kpi_view':<12} 不可用")


def main() -> None:
    backend, args, iters = parse_args(sys.argv[1:])
    cmd = args[0] if args else "status"

    if cmd == "schema":
        print(schema(backend))
        return
    if cmd == "example-config":
        p = write_example_config()
        print(f"[OK] 已生成 {p}（复制成 mysql_config.json 并填入密码即可）")
        return

    db = connect(backend)
    try:
        if cmd == "init":
            db.executescript(schema(backend))
            print("[OK] 表已就绪（CREATE IF NOT EXISTS，不会删已有数据）")
            cmd_status(db, backend)
        elif cmd == "status":
            cmd_status(db, backend)
        elif cmd == "import":
            if "--reset" in sys.argv:
                db.execute("DELETE FROM solution")
                db.execute("DELETE FROM experiment")
                db.commit()
                print("[OK] 已清空 experiment / solution 表（避免重复导入）")
            print(f"[OK] 已导入 {import_experiments_csv(db, args[1])} 条实验记录")
        elif cmd == "import-scenes":
            print(f"[OK] 已导入 {import_scenes_from_folder(db)} 个场景")
        elif cmd == "kpi":
            rows = db.query("SELECT * FROM kpi_view ORDER BY instance, method")
            print(f"{'算例':<8}{'方法':<22}{'次数':<6}{'平均里程':<12}{'最优':<10}{'车辆':<8}耗时")
            for r in rows:
                print(f"{r[0]:<8}{r[2]:<22}{r[3]:<6}{r[4]:<12}{r[5]:<10}{r[6]:<8}{r[9]}")
        elif cmd == "save":
            src = Path(args[1])
            inst = parse_solomon(src)
            res = solve_aco(inst, ACOConfig(max_iter=iters, seed=1))
            iid = get_or_create_instance(db, inst, str(src), src.parent.name)
            eid = insert_experiment(db, iid, "L3 +局部搜索(改进版)", 1, res["metrics"],
                                    seed=1, iterations=iters, seconds=res["seconds"])
            insert_solution(db, eid, inst, res["routes"])
            print(f"[OK] 已保存方案：{inst.name}｜里程 {res['distance']:.2f}｜"
                  f"车辆 {res['vehicles']}｜路线 {len(res['routes'])} 条（experiment_id={eid}）")
        else:
            raise SystemExit(f"未知命令：{cmd}\n{__doc__}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
