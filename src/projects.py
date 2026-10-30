# -*- coding: utf-8 -*-
"""M12｜用户与项目空间（Project Workspace）

一个人可能同时做多个配送课题：校园配送、社区团购、某公司的线路复现。每个项目要有自己的
算例、场景、实验记录和备注，互不污染。本模块用一个目录 + 一份 project.json 来管理：

    projects/
      校园配送/
        project.json        # 名称、负责人、备注、创建时间、算例/场景清单
        instances/*.txt     # 算例副本（Solomon 格式）
        scenes/*.json       # 场景副本（约束配置）

不建数据库表，是为了不动第三章已经核对过的四张表结构（instance / scene / experiment / solution）；
项目只是一个“文件柜”，实验记录仍可写进数据库。

用法
----
    python projects.py new 校园配送 --owner 任绪锋 --note 软时间窗，车速 1.2
    python projects.py list
    python projects.py show 校园配送
    python projects.py add-instance 校园配送 data/solomon/orders/demo.txt
    python projects.py add-scene 校园配送 校园配送-软时间窗
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "projects"


class ProjectError(ValueError):
    """项目操作失败，消息可直接展示。"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ProjectError("项目名不能为空")
    bad = set('\\/:*?"<>|')
    if any(ch in bad for ch in name):
        raise ProjectError("项目名不能包含 \\ / : * ? \" < > |")
    return name


def project_dir(name: str) -> Path:
    return ROOT / _safe(name)


def create(name: str, owner: str = "", note: str = "") -> dict:
    d = project_dir(name)
    if d.exists():
        raise ProjectError("项目已存在：" + name)
    (d / "instances").mkdir(parents=True)
    (d / "scenes").mkdir(parents=True)
    meta = {"name": name, "owner": owner, "note": note, "created_at": _now(),
            "instances": [], "scenes": [], "experiments": []}
    (d / "project.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def load(name: str) -> dict:
    p = project_dir(name) / "project.json"
    if not p.exists():
        raise ProjectError("项目不存在：" + name)
    return json.loads(p.read_text(encoding="utf-8"))


def save(meta: dict) -> None:
    p = project_dir(meta["name"]) / "project.json"
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def list_projects() -> list[dict]:
    if not ROOT.exists():
        return []
    out = []
    for d in sorted(ROOT.iterdir()):
        p = d / "project.json"
        if p.exists():
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    return out


def add_instance(name: str, path: str | Path) -> dict:
    meta = load(name)
    src = Path(path)
    if not src.exists():
        raise ProjectError("算例文件不存在：" + str(src))
    dst = project_dir(name) / "instances" / src.name
    shutil.copy2(src, dst)
    if src.name not in meta["instances"]:
        meta["instances"].append(src.name)
    save(meta)
    return meta


def add_scene(name: str, scene_name: str) -> dict:
    meta = load(name)
    src = HERE / "scenes" / (scene_name + ".json")
    if not src.exists():
        raise ProjectError("场景不存在：" + scene_name)
    dst = project_dir(name) / "scenes" / src.name
    shutil.copy2(src, dst)
    if src.name not in meta["scenes"]:
        meta["scenes"].append(src.name)
    save(meta)
    return meta


def record_experiment(name: str, summary: dict) -> dict:
    meta = load(name)
    summary = dict(summary)
    summary.setdefault("time", _now())
    meta["experiments"].append(summary)
    save(meta)
    return meta


def describe(meta: dict) -> str:
    return ("项目 %s｜负责人 %s｜算例 %d 个｜场景 %d 个｜实验 %d 条｜建 %s%s"
            % (meta["name"], meta.get("owner") or "未填", len(meta.get("instances", [])),
               len(meta.get("scenes", [])), len(meta.get("experiments", [])),
               meta.get("created_at", ""),
               ("｜" + meta["note"]) if meta.get("note") else ""))


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "help", "list"}:
        for m in list_projects():
            print("  " + describe(m))
        if not list_projects():
            print("（还没有项目，用 python projects.py new 名称 新建）")
        return
    cmd = args[0]
    if cmd == "new":
        if len(args) < 2:
            raise SystemExit("用法：python projects.py new 名称 [--owner 姓名] [--note 备注]")
        owner = note = ""
        for i, a in enumerate(args):
            if a == "--owner" and i + 1 < len(args):
                owner = args[i + 1]
            if a == "--note" and i + 1 < len(args):
                note = args[i + 1]
        print("已创建：" + describe(create(args[1], owner, note)))
        return
    if cmd == "show":
        meta = load(args[1])
        print(describe(meta))
        print("  算例：" + (", ".join(meta["instances"]) or "无"))
        print("  场景：" + (", ".join(meta["scenes"]) or "无"))
        print("  实验：" + (str(len(meta["experiments"])) + " 条"))
        return
    if cmd == "add-instance":
        print("已加入：" + describe(add_instance(args[1], args[2])))
        return
    if cmd == "add-scene":
        print("已加入：" + describe(add_scene(args[1], args[2])))
        return
    raise SystemExit("未知命令：" + cmd)


if __name__ == "__main__":
    main()
