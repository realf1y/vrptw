# -*- coding: utf-8 -*-
"""查看数据库内容（SQLite 默认，加 --mysql 看 MySQL）

用法::

    python dbview.py                  # 表清单 + 每张表行数（SQLite）
    python dbview.py kpi              # KPI 汇总视图
    python dbview.py experiment 50    # 看某张表前 50 行
    python dbview.py sql              # 打印建表语句
    python dbview.py status --mysql   # 看 MySQL（需配好 mysql_config.json 且服务已启动）
"""
from __future__ import annotations

import sys

from db import connect

ALIAS = {"kpi": "kpi_view", "kpis": "kpi_view", "view": "kpi_view"}


def show_table(db, name: str, limit: int = 20) -> None:
    try:
        cur = db.execute(f"SELECT * FROM {name} LIMIT 1")
    except Exception as exc:
        print(f"读不到 {name}：{exc}")
        return
    cols = [d[0] for d in cur.description]
    rows = db.query(f"SELECT * FROM {name} LIMIT {limit}")
    total = db.query(f"SELECT COUNT(*) FROM {name}")[0][0]
    print(f"== {name}（字段 {len(cols)} 个，共 {total} 行）==")
    print("  " + " | ".join(cols))
    for r in rows:
        cells = ["" if v is None else str(v)[:26] for v in r]
        print("  " + " | ".join(cells))
    print()


def main() -> None:
    argv = sys.argv[1:]
    backend = "mysql" if "--mysql" in argv else "sqlite"
    args = [a for a in argv if not a.startswith("--")]
    db = connect(backend)
    print(f"数据库：{db.describe}\n")

    if not args or args[0] in {"status", "tables"}:
        if backend == "mysql":
            objs = db.query("SELECT table_type, table_name FROM information_schema.tables"
                            " WHERE table_schema = DATABASE() ORDER BY table_type, table_name")
        else:
            objs = db.query("SELECT type, name FROM sqlite_master"
                            " WHERE name NOT LIKE 'sqlite_%' ORDER BY type DESC, name")
        for typ, name in objs:
            try:
                n = db.query(f"SELECT COUNT(*) FROM {name}")[0][0]
                print(f"  [{typ}] {name:<12} {n} 行")
            except Exception:
                print(f"  [{typ}] {name}")
        db.close()
        return

    if args[0] == "sql":
        if backend == "mysql":
            for t in ["instance", "scene", "experiment", "solution", "kpi_view"]:
                kind = "VIEW" if t == "kpi_view" else "TABLE"
                try:
                    row = db.query(f"SHOW CREATE {kind} {t}")[0]
                    print(row[1].strip(), ";\n")
                except Exception:
                    pass
        else:
            for (sql,) in [r for r in db.query(
                    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name")]:
                print(sql.strip(), ";\n")
        db.close()
        return

    name = ALIAS.get(args[0], args[0])
    limit = int(args[1]) if len(args) > 1 else 20
    show_table(db, name, limit)
    db.close()


if __name__ == "__main__":
    main()
