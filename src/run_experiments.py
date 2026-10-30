# -*- coding: utf-8 -*-
"""M4｜批量实验与消融分析（报告第 6 章的数据来源）

改进版：**多进程并行 + 增量写盘 + 实时进度**
- 用满你的多核 CPU（`--jobs`，默认取 CPU 核数-2）
- 每跑完一次就写一行 CSV 并刷盘 → 中断也能保住已有结果、随时能看进度

用法::

    python run_experiments.py 100 10 c101 c201 r101 r201 rc101 rc201
    python run_experiments.py 100 10 --iters=40 --jobs=16
    python run_experiments.py 25 3                      # 25 客户全套（快）

消融层级
--------
    L0 基线      标准蚁群（η=1/距离，无精英/MMAS，无局部搜索）
    L1 +η        加时间窗启发式因子              （创新点②）
    L2 +MMAS     再加精英策略 + 信息素上下界      （创新点③）
    L3 +局部搜索 再加 2-opt / Or-opt / relocate   （创新点④）= 最终改进版
"""
from __future__ import annotations

import csv
import json
import multiprocessing as mp
import statistics
import sys
import time
from pathlib import Path

from aco import ACOConfig, solve_aco
from instance import parse_solomon
from solution import evaluate, nearest_neighbor

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "solomon"
RESULTS = HERE / "results"
BKS_FILE = HERE / "data" / "solomon_bks.json"

METHOD_ORDER = ["最近邻(贪心)", "L0 基线ACO", "L1 +时间窗η", "L2 +MMAS精英", "L3 +局部搜索(改进版)"]


def method_specs(iters: int) -> dict:
    """方法名 → 参数字典（None 表示最近邻）。用纯 dict 方便进程间传递。"""
    base = {"max_iter": iters}
    return {
        "最近邻(贪心)": None,
        "L0 基线ACO": {**base, "w_wait": 0.0, "w_slack": 0.0,
                       "elitist": False, "mmas": False, "local_search": False},
        "L1 +时间窗η": {**base, "elitist": False, "mmas": False, "local_search": False},
        "L2 +MMAS精英": {**base, "local_search": False},
        "L3 +局部搜索(改进版)": {**base},
    }


_SPECS: dict = {}
_BKS: dict = {}
_SIZE = "100"


def _norm_row(r: dict) -> dict:
    """把 CSV 读回来的字符串行转换成与运行结果一致的类型（供 --append 使用）"""
    out = dict(r)
    for k in ("distance", "vehicles", "seconds", "tw_violation", "on_time_rate", "load_rate", "bks"):
        v = out.get(k)
        try:
            out[k] = float(v) if v not in (None, "", "None") else None
        except (TypeError, ValueError):
            out[k] = None
    try:
        out["run"] = int(out.get("run") or 0)
    except (TypeError, ValueError):
        out["run"] = 0
    out["feasible"] = str(out.get("feasible")).lower() in {"true", "1"}
    return out


def _work(task):
    """一个工作单元：某个算例 × 某个方法 × 某一次运行。"""
    inst_path, method, run_idx = task
    try:
        inst = parse_solomon(inst_path)
        cfg = _SPECS[method]
        if cfg is None:
            routes = nearest_neighbor(inst, allow_time_window_violation=False)
            ev = evaluate(inst, routes)
            dist, veh, feas, secs = ev["total_distance"], ev["vehicles"], ev["feasible"], 0.0
            tw, otr, lr = ev["tw_violation"], ev["on_time_rate"], ev["load_rate"]
        else:
            c = ACOConfig(**{**cfg, "seed": 1000 + run_idx})
            res = solve_aco(inst, c)
            dist, veh, feas, secs = res["distance"], res["vehicles"], res["feasible"], res["seconds"]
            m = res["metrics"]
            tw, otr, lr = m["tw_violation"], m["on_time_rate"], m["load_rate"]
        return {"instance": Path(inst_path).stem.upper(), "size": _SIZE, "method": method,
                "run": run_idx + 1, "distance": round(dist, 2), "vehicles": veh,
                "feasible": feas, "seconds": secs, "tw_violation": tw,
                "on_time_rate": otr, "load_rate": lr,
                "bks": (_BKS.get(Path(inst_path).stem.upper(), {}).get("distance")
                        if _SIZE == "100" else None)}
    except Exception as e:  # 单个任务失败不影响整批
        return {"instance": Path(inst_path).stem.upper(), "size": _SIZE, "method": method,
                "run": run_idx + 1, "distance": None, "vehicles": None,
                "feasible": None, "seconds": None, "bks": None, "error": f"{type(e).__name__}: {e}"}


def _init_worker(specs, bks, size):
    global _SPECS, _BKS, _SIZE
    _SPECS, _BKS, _SIZE = specs, bks, size


def build_summary(rows, methods, instances, bks, size, iters, runs) -> str:
    lines = [f"# 实验结果（{size} 客户算例，每方法 {runs} 次，迭代 {iters} 代）", "",
             "| 算例 | 已知最优 | " + " | ".join(methods) + " |",
             "| --- | --- | " + " | ".join(["---"] * len(methods)) + " |"]
    for inst in instances:
        key = inst
        b = bks.get(key, {}).get("distance") if size == "100" else None
        cells = []
        for m in methods:
            vals = [r["distance"] for r in rows if r["instance"] == key and r["method"] == m
                    and r["distance"] is not None]
            if not vals:
                cells.append("-")
                continue
            mean, std = statistics.mean(vals), statistics.pstdev(vals)
            gap = f"，gap {100 * (mean - b) / b:.1f}%" if b else ""
            cells.append(f"{mean:.2f} ± {std:.2f}{gap}")
        lines.append(f"| {key} | {b if b else '-'} | " + " | ".join(cells) + " |")

    lines += ["", "## 各方法耗时（秒/次，均值）", "",
              "| 方法 | 平均耗时 |", "| --- | --- |"]
    for m in methods:
        secs = [r["seconds"] for r in rows if r["method"] == m and r["seconds"] is not None]
        if secs:
            lines.append(f"| {m} | {statistics.mean(secs):.2f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    size = args[0] if args else "25"
    runs = int(args[1]) if len(args) > 1 else 3
    names = args[2:]

    iters, jobs = 100, max(mp.cpu_count() - 2, 1)
    for a in sys.argv[1:]:
        if a.startswith("--iters"):
            iters = int(a.split("=")[1])
        if a.startswith("--jobs"):
            jobs = int(a.split("=")[1])

    folder = DATA / size
    if not folder.exists():
        raise SystemExit(f"没找到算例目录：{folder}")
    files = sorted(folder.glob("*.txt"))
    if names:
        want = {n.lower() for n in names}
        files = [f for f in files if f.stem.lower() in want]
    if not files:
        raise SystemExit("没有匹配的算例文件")

    bks = json.loads(BKS_FILE.read_text(encoding="utf-8")) if BKS_FILE.exists() else {}
    methods = METHOD_ORDER
    specs = method_specs(iters)
    tasks = [(str(f), m, r) for f in files for m in methods for r in range(runs)]

    RESULTS.mkdir(exist_ok=True)
    stem = f"experiments_{size}_{runs}x"
    csv_path, md_path = RESULTS / f"{stem}.csv", RESULTS / f"{stem}.md"

    print(f"算例 {len(files)} 个｜方法 {len(methods)} 个｜每方法 {runs} 次｜迭代 {iters}｜"
          f"并行 {jobs} 进程", flush=True)
    print(f"共 {len(tasks)} 个任务，明细边跑边写：{csv_path.name}", flush=True)

    rows: list[dict] = []
    append = "--append" in sys.argv
    fieldnames = ["instance", "size", "method", "run", "distance", "vehicles",
                  "feasible", "seconds", "tw_violation", "on_time_rate", "load_rate",
                  "bks", "error"]
    if append and csv_path.exists():
        with csv_path.open(encoding="utf-8-sig", newline="") as fh:
            rows = [_norm_row(r) for r in csv.DictReader(fh)]
        print(f"[append] 已有 {len(rows)} 条记录，本次追加 {len(tasks)} 条", flush=True)

    t0 = time.perf_counter()
    mode = "a" if rows else "w"
    with csv_path.open(mode, newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if not rows:
            writer.writeheader()
        fh.flush()
        with mp.Pool(jobs, initializer=_init_worker, initargs=(specs, bks, size)) as pool:
            for done, row in enumerate(pool.imap_unordered(_work, tasks), 1):
                rows.append(row)
                writer.writerow({k: row.get(k) for k in fieldnames})
                fh.flush()
                if done % 5 == 0 or done == len(tasks):
                    el = time.perf_counter() - t0
                    eta = el / done * (len(tasks) - done)
                    print(f"  进度 {done}/{len(tasks)}｜已用 {el:.0f}s｜预计还需 {eta:.0f}s", flush=True)

    md_path.write_text(build_summary(rows, methods,
                                     sorted({(r["instance"] or "").upper() for r in rows}),
                                     bks, size, iters, runs), encoding="utf-8")
    print("\n" + build_summary(rows, methods,
                                sorted({(r["instance"] or "").upper() for r in rows}),
                                bks, size, iters, runs), flush=True)
    print(f"明细：{csv_path}\n汇总：{md_path}", flush=True)


if __name__ == "__main__":
    main()
