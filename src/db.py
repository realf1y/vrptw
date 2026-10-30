# -*- coding: utf-8 -*-
"""数据库访问层：一套代码同时支持 SQLite（默认）与 MySQL

- **SQLite**：单文件 `vrptw.db`，零配置，跑起来最快（本地开发/演示用）
- **MySQL**：读项目根目录 `mysql_config.json`（或环境变量），正式部署用；Navicat 可直接连

两种后端对外接口完全一致::

    from db import connect, schema
    db = connect()            # SQLite
    db = connect("mysql")     # MySQL
    db.execute("INSERT INTO instance (name) VALUES (?)", ("C101",))
    db.query("SELECT * FROM kpi_view")
    db.executescript(schema("mysql"))

SQL 里统一写 `?` 占位符，MySQL 后端会自动转成 `%s`。
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
SQLITE_PATH = HERE / "vrptw.db"
CONFIG_PATH = HERE / "mysql_config.json"
EXAMPLE_PATH = HERE / "mysql_config.example.json"

MYSQL_CREATE_DB = ("CREATE DATABASE IF NOT EXISTS `{db}` "
                   "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS instance (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,
    size          TEXT,
    n_customers   INTEGER NOT NULL,
    capacity      REAL    NOT NULL,
    vehicle_count INTEGER,
    speed         REAL    NOT NULL DEFAULT 1.0,
    total_demand  REAL,
    source_path   TEXT,
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS scene (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    config_json TEXT    NOT NULL,
    note        TEXT,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS experiment (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id  INTEGER NOT NULL REFERENCES instance(id) ON DELETE CASCADE,
    scene_id     INTEGER REFERENCES scene(id),
    method       TEXT    NOT NULL,
    run_index    INTEGER NOT NULL,
    seed         INTEGER,
    iterations   INTEGER,
    distance     REAL,
    vehicles     INTEGER,
    feasible     INTEGER,
    tw_violation REAL,
    on_time_rate REAL,
    load_rate    REAL,
    seconds      REAL,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_exp_instance ON experiment(instance_id);
CREATE INDEX IF NOT EXISTS idx_exp_method   ON experiment(method);
CREATE TABLE IF NOT EXISTS solution (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL REFERENCES experiment(id) ON DELETE CASCADE,
    route_index   INTEGER NOT NULL,
    customers     TEXT    NOT NULL,
    stop_count    INTEGER NOT NULL,
    route_length  REAL,
    route_load    REAL
);
CREATE INDEX IF NOT EXISTS idx_sol_exp ON solution(experiment_id);
CREATE VIEW IF NOT EXISTS kpi_view AS
SELECT i.name                AS instance, i.size AS size, e.method AS method,
       COUNT(*)              AS runs,
       ROUND(AVG(e.distance), 2)     AS avg_distance,
       ROUND(MIN(e.distance), 2)     AS best_distance,
       ROUND(AVG(e.vehicles), 2)     AS avg_vehicles,
       ROUND(AVG(e.on_time_rate), 4) AS avg_on_time,
       ROUND(AVG(e.load_rate), 4)    AS avg_load_rate,
       ROUND(AVG(e.seconds), 2)      AS avg_seconds
FROM experiment e JOIN instance i ON i.id = e.instance_id
GROUP BY i.name, i.size, e.method;
"""

MYSQL_SCHEMA = """
-- 注意：全部用 IF NOT EXISTS，不会删已有数据
CREATE TABLE IF NOT EXISTS instance (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(64)  NOT NULL UNIQUE  COMMENT '算例名（如 C101）',
  size          VARCHAR(16)                   COMMENT '规模 25/50/100',
  n_customers   INT          NOT NULL         COMMENT '客户数',
  capacity      DOUBLE       NOT NULL         COMMENT '车辆载重上限',
  vehicle_count INT                           COMMENT '车辆数上限',
  speed         DOUBLE       NOT NULL DEFAULT 1.0 COMMENT '车速：行驶时间=距离/车速',
  total_demand  DOUBLE                        COMMENT '总需求',
  source_path   VARCHAR(255)                  COMMENT '算例文件路径',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='算例';

CREATE TABLE IF NOT EXISTS scene (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(64) NOT NULL UNIQUE     COMMENT '场景名',
  config_json TEXT        NOT NULL            COMMENT '场景配置 JSON',
  note        VARCHAR(255)                    COMMENT '说明',
  created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='业务场景配置';

CREATE TABLE IF NOT EXISTS experiment (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  instance_id  INT NOT NULL                   COMMENT '算例',
  scene_id     INT NULL                       COMMENT '场景（可空）',
  method       VARCHAR(64) NOT NULL           COMMENT '方法：最近邻/L0/L1/L2/L3',
  run_index    INT NOT NULL                   COMMENT '第几次运行',
  seed         INT NULL                       COMMENT '随机种子',
  iterations   INT NULL                       COMMENT '迭代代数',
  distance     DOUBLE                         COMMENT '总里程',
  vehicles     INT                            COMMENT '车辆数',
  feasible     TINYINT(1)                     COMMENT '是否可行',
  tw_violation DOUBLE                         COMMENT '时间窗违反量',
  on_time_rate DOUBLE                         COMMENT '准时率',
  load_rate    DOUBLE                         COMMENT '装载率',
  seconds      DOUBLE                         COMMENT '求解耗时（秒）',
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_exp_instance FOREIGN KEY (instance_id) REFERENCES instance(id) ON DELETE CASCADE,
  CONSTRAINT fk_exp_scene    FOREIGN KEY (scene_id)    REFERENCES scene(id),
  INDEX idx_exp_instance (instance_id),
  INDEX idx_exp_method   (method)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='实验记录';

CREATE TABLE IF NOT EXISTS solution (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  experiment_id INT NOT NULL                  COMMENT '所属实验',
  route_index   INT NOT NULL                  COMMENT '第几条路线',
  customers     TEXT NOT NULL                 COMMENT '客户访问顺序（逗号分隔）',
  stop_count    INT NOT NULL                  COMMENT '停靠点数量',
  route_length  DOUBLE                        COMMENT '该路线里程',
  route_load    DOUBLE                        COMMENT '该路线载重',
  CONSTRAINT fk_sol_exp FOREIGN KEY (experiment_id) REFERENCES experiment(id) ON DELETE CASCADE,
  INDEX idx_sol_exp (experiment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='方案路线';

CREATE OR REPLACE VIEW kpi_view AS
SELECT i.name                        AS instance, i.size AS size, e.method AS method,
       COUNT(*)                      AS runs,
       ROUND(AVG(e.distance), 2)     AS avg_distance,
       ROUND(MIN(e.distance), 2)     AS best_distance,
       ROUND(AVG(e.vehicles), 2)     AS avg_vehicles,
       ROUND(AVG(e.on_time_rate), 4) AS avg_on_time,
       ROUND(AVG(e.load_rate), 4)    AS avg_load_rate,
       ROUND(AVG(e.seconds), 2)      AS avg_seconds
FROM experiment e JOIN instance i ON i.id = e.instance_id
GROUP BY i.name, i.size, e.method;
"""


def load_mysql_config() -> dict:
    cfg = {"host": "127.0.0.1", "port": 3306, "user": "root", "password": "",
           "database": "vrptw", "charset": "utf8mb4"}
    if CONFIG_PATH.exists():
        # utf-8-sig：容忍记事本保存时带的 BOM
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        loaded = {k: (v.strip() if isinstance(v, str) else v) for k, v in loaded.items()}
        cfg.update(loaded)
    for key, env in [("host", "MYSQL_HOST"), ("port", "MYSQL_PORT"), ("user", "MYSQL_USER"),
                     ("password", "MYSQL_PASSWORD"), ("database", "MYSQL_DATABASE")]:
        val = os.environ.get(env)
        if val:
            cfg[key] = int(val) if key == "port" else val
    return cfg


def check_login_fields(cfg: dict) -> None:
    """pymysql 的认证包只能放拉丁字符，中文/全角密码必须先拦下来并给出明确提示。"""
    for field in ("user", "password", "host"):
        val = cfg.get(field) or ""
        bad = [c for c in val if ord(c) > 255]
        if bad:
            raise SystemExit(
                f"\n配置里的 {field} 含有 {len(bad)} 个非拉丁字符（中文/全角），"
                "pymysql 无法用它登录 MySQL。\n\n"
                "推荐做法：在 Navicat 里给项目建一个专用账号（密码用半角），例如：\n"
                "    CREATE USER 'vrptw'@'localhost' IDENTIFIED BY 'Vrptw@2026';\n"
                "    GRANT ALL PRIVILEGES ON vrptw.* TO 'vrptw'@'localhost';\n"
                "    FLUSH PRIVILEGES;\n"
                f"然后把 {CONFIG_PATH.name} 里的 user / password 改成这个账号。\n"
            )


def write_example_config() -> Path:
    example = {"_说明": "复制本文件为 mysql_config.json，把 password 改成你自己的密码",
               "host": "127.0.0.1", "port": 3306, "user": "root",
               "password": "在这里填你的 MySQL 密码", "database": "vrptw",
               "charset": "utf8mb4"}
    EXAMPLE_PATH.write_text(json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8")
    return EXAMPLE_PATH


class Db:
    """统一的数据库句柄（SQLite / MySQL 通用）。"""

    def __init__(self, conn, backend: str, describe: str):
        self.conn = conn
        self.backend = backend
        self.describe = describe

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.backend == "mysql" else sql

    def execute(self, sql: str, params=()):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), params)
        return cur

    def query(self, sql: str, params=()) -> list:
        return self.execute(sql, params).fetchall()

    def executescript(self, sql: str) -> None:
        if self.backend == "mysql":
            for stmt in (s.strip() for s in sql.split(";")):
                if stmt:
                    self.conn.cursor().execute(stmt)
        else:
            self.conn.executescript(sql)
        self.conn.commit()

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def connect(backend: str = "sqlite", config: dict | None = None) -> Db:
    if backend == "mysql":
        try:
            import pymysql
        except ImportError as exc:                       # pragma: no cover
            raise SystemExit("缺少 MySQL 驱动：python -m pip install pymysql") from exc

        cfg = load_mysql_config()
        if config:
            cfg.update(config)
        check_login_fields(cfg)
        dbname = cfg.get("database", "vrptw")
        try:
            conn = pymysql.connect(host=cfg["host"], port=int(cfg["port"]), user=cfg["user"],
                                   password=cfg["password"], charset=cfg.get("charset", "utf8mb4"),
                                   autocommit=False, connect_timeout=5)
        except Exception as exc:
            raise SystemExit(
                f"\n连不上 MySQL（{cfg['host']}:{cfg['port']}，用户 {cfg['user']}）：{exc}\n\n"
                "请依次确认：\n"
                "  1) MySQL 服务已启动（管理员命令行）：net start MySQL95\n"
                f"  2) 密码写进了配置文件：{CONFIG_PATH}\n"
                f"     （可复制 {EXAMPLE_PATH.name} 改名而来）\n"
                "  3) 端口没被改过（默认 3306）\n"
            ) from exc
        conn.cursor().execute(MYSQL_CREATE_DB.format(db=dbname))
        conn.cursor().execute(f"USE `{dbname}`")
        conn.commit()
        return Db(conn, "mysql",
                  f"MySQL {cfg['host']}:{cfg['port']} / 库 {dbname} / 用户 {cfg['user']}")

    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    return Db(conn, "sqlite", f"SQLite {SQLITE_PATH}")


def schema(backend: str = "sqlite") -> str:
    return MYSQL_SCHEMA if backend == "mysql" else SCHEMA_SQLITE
