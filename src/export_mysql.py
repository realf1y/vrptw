# -*- coding: utf-8 -*-
"""把当前库导出成 MySQL 可直接执行的 SQL 文件（建库 + 建表 + 视图 + 数据）

产出：db/mysql_vrptw.sql
用途：不想让脚本直连 MySQL 时，用 Navicat / Workbench 手动执行这个脚本即可。

用法::

    python export_mysql.py                 # 从 SQLite 库导出
    python export_mysql.py --from-mysql    # 从 MySQL 库反向导出（备份用）
"""
from __future__ import annotations

import sys
from pathlib import Path

from db import MYSQL_CREATE_DB, MYSQL_SCHEMA, connect

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "db"
OUT = OUT_DIR / "mysql_vrptw.sql"
TABLES = ["instance", "scene", "experiment", "solution"]


def sql_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def main() -> None:
    src_backend = "mysql" if "--from-mysql" in sys.argv else "sqlite"
    db = connect(src_backend)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "-- ---------------------------------------------------------------------------",
        "-- 带时间窗配送路径优化系统 · 数据库脚本（MySQL 8/9）",
        f"-- 数据来源：{db.describe}",
        "-- 执行方式：mysql -u root -p < mysql_vrptw.sql",
        "--           或在 Navicat / MySQL Workbench 中打开本文件整体执行",
        "-- ---------------------------------------------------------------------------",
        MYSQL_CREATE_DB.format(db="vrptw"),
        "USE `vrptw`;",
        MYSQL_SCHEMA,
        "",
        "-- ------------------------------- 数据 -------------------------------",
    ]

    total = 0
    for table in TABLES:
        try:
            cur = db.execute(f"SELECT * FROM {table}")
            cols = [d[0] for d in cur.description]
            rows = db.query(f"SELECT * FROM {table}")
        except Exception as exc:
            lines.append(f"-- {table}: 跳过（{exc}）")
            continue
        if not rows:
            continue
        lines.append(f"\n-- {table}：{len(rows)} 行")
        for row in rows:
            values = ", ".join(sql_value(v) for v in row)
            lines.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({values});")
        total += len(rows)
    db.close()

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] 已生成：{OUT}")
    print(f"     4 张表｜数据 {total} 行｜{OUT.stat().st_size / 1024:.1f} KB")
    print("\n在 Navicat 里导入：连接本地 MySQL → 右键连接选「运行 SQL 文件」→ 选上面这个文件")
    print("或命令行：mysql -u root -p < db/mysql_vrptw.sql")


if __name__ == "__main__":
    main()
