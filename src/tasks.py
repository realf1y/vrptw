# -*- coding: utf-8 -*-
"""M13｜任务监控（后台队列 + 状态查询）

蚁群求解 100 客户算例要几十秒，Web 页面不能一直挂着等。本模块把求解放到后台线程：
提交后立刻返回任务号，页面轮询进度；任务状态写成 JSON 文件，进程重启也能查历史。

任务字段
--------
    id / instance / method / iters / seed      提交参数
    state        queued | running | done | failed | cancelled
    progress     0–1（每代结束刷新）
    iter/total   已完成代数 / 总代数
    best_cost    当前最优代价（含时间窗惩罚）
    distance / vehicles / feasible / seconds   完成后写入
    error        失败原因
    created_at / started_at / finished_at / updated_at

用法
----
    python tasks.py submit --instance data/solomon/100/c101.txt --iters 40
    python tasks.py list
    python tasks.py status 20261030-184500-abcd
    python tasks.py wait 20261030-184500-abcd
    python tasks.py cancel 20261030-184500-abcd
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK_DIR = HERE / "results" / "tasks"
TERMINAL = {"done", "failed", "cancelled"}


class TaskCancelled(Exception):
    """用户在迭代途中取消任务。"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _path(tid: str) -> Path:
    return TASK_DIR / (tid + ".json")


def save(task: dict) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(task["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(task, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)                      # 原子替换，轮询端不会读到半个 JSON


def load(tid: str) -> dict:
    p = _path(tid)
    if not p.exists():
        raise FileNotFoundError("任务不存在：" + tid)
    return json.loads(p.read_text(encoding="utf-8"))


def list_tasks(limit: int = 50) -> list[dict]:
    if not TASK_DIR.exists():
        return []
    items = []
    for p in TASK_DIR.glob("*.json"):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    items.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return items[:limit]


def new_task(instance: str, iters: int = 40, method: str = "improved", seed: int = 1) -> dict:
    tid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    return {
        "id": tid, "instance": instance, "method": method, "iters": int(iters),
        "seed": int(seed), "state": "queued", "progress": 0.0, "iter": 0,
        "total": int(iters), "best_cost": None, "distance": None, "vehicles": None,
        "feasible": None, "seconds": None, "error": None, "cancel_requested": False,
        "created_at": _now(), "started_at": None, "finished_at": None, "updated_at": _now(),
    }


def _run(task: dict) -> None:
    from aco import ACOConfig, AntColonySolver, baseline_config
    from instance import parse_solomon

    task["state"] = "running"
    task["started_at"] = _now()
    save(task)
    try:
        src = Path(task["instance"])
        inst = parse_solomon(src if src.is_absolute() else HERE / src)
        cfg = (baseline_config if task["method"] == "baseline" else ACOConfig)(
            max_iter=task["iters"], seed=task["seed"])
        solver = AntColonySolver(inst, cfg)

        def cb(done: int, total: int, cost: float) -> None:
            cur = load(task["id"])
            if cur.get("cancel_requested"):
                raise TaskCancelled()
            cur["progress"] = round(done / max(1, total), 4)
            cur["iter"] = done
            cur["total"] = total
            cur["best_cost"] = round(cost, 2)
            cur["updated_at"] = _now()
            save(cur)

        solver.progress_cb = cb
        res = solver.solve()
        task = load(task["id"])
        task.update({"state": "done", "progress": 1.0, "iter": task["iters"],
                     "distance": res["distance"], "vehicles": res["vehicles"],
                     "feasible": res["feasible"], "tw_violation": res["tw_violation"],
                     "seconds": res["seconds"]})
    except TaskCancelled:
        task = load(task["id"])
        task["state"] = "cancelled"
    except Exception as exc:                      # noqa: BLE001 - 失败原因要落到页面上
        task = load(task["id"])
        task["state"] = "failed"
        task["error"] = str(exc)
    finally:
        task["finished_at"] = _now()
        task["updated_at"] = _now()
        save(task)


def submit(instance: str, iters: int = 40, method: str = "improved",
           seed: int = 1, background: bool = True) -> dict:
    task = new_task(instance, iters, method, seed)
    save(task)
    th = threading.Thread(target=_run, args=(task,), daemon=True)
    th.start()
    if not background:
        th.join()
        return load(task["id"])
    return task


def spawn_worker(tid: str) -> None:
    """用独立进程跑任务：命令行提交后本进程退出，任务仍继续（线程会随进程结束）。"""
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "run", tid],
                     cwd=str(HERE), creationflags=flags,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cancel(tid: str) -> dict:
    task = load(tid)
    if task["state"] in TERMINAL:
        return task
    task["cancel_requested"] = True
    task["updated_at"] = _now()
    save(task)
    return task


def describe(task: dict) -> str:
    pct = int(round((task.get("progress") or 0) * 100))
    extra = ""
    if task["state"] == "done":
        extra = "｜里程 %.2f｜车辆 %d｜%.1fs" % (task["distance"], task["vehicles"], task["seconds"] or 0)
    elif task["state"] == "failed":
        extra = "｜错误：" + str(task.get("error"))
    return ("%s  %-8s %3d%%（%s/%s）  %s%s"
            % (task["id"], task["state"], pct, task.get("iter", 0),
               task.get("total", 0), Path(task["instance"]).name, extra))


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "list":
        for t in list_tasks():
            print("  " + describe(t))
        if not list_tasks():
            print("（没有任务）")
        return
    cmd = args[0]
    opts = {}
    i = 1
    while i < len(args):
        if args[i].startswith("--") and i + 1 < len(args):
            opts[args[i][2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    if cmd == "submit":
        task = new_task(opts.get("instance", "data/solomon/100/c101.txt"),
                        int(opts.get("iters", 40)), opts.get("method", "improved"),
                        int(opts.get("seed", 1)))
        save(task)
        spawn_worker(task["id"])
        print("已提交：" + task["id"])
        print("查询：python tasks.py status " + task["id"])
        return
    if cmd == "run":
        task = load(args[1])
        if task["state"] == "queued":
            _run(task)
        return
    if cmd == "status":
        print(describe(load(args[1])))
        return
    if cmd == "wait":
        while True:
            t = load(args[1])
            print(describe(t), flush=True)
            if t["state"] in TERMINAL:
                return
            time.sleep(0.5)
    if cmd == "cancel":
        print(describe(cancel(args[1])))
        return
    raise SystemExit("未知命令：" + cmd)


if __name__ == "__main__":
    main()
