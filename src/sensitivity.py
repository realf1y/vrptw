# -*- coding: utf-8 -*-
"""参数敏感性实验：α（信息素）、β（启发式）、ρ（挥发率）怎么影响解质量

做法：
- α × β 网格：{0.5, 1, 2} × {2, 3, 5}，固定算例 R101，每个组合 3 个随机种子
- ρ 单变量扫描：{0.05, 0.1, 0.2, 0.3}，固定算例 RC101，每个 3 个种子
- 多进程并行，输出 results/sensitivity.csv + results/sensitivity.md

结论**由数据算出**，不写死（避免结论与表格矛盾）。

用法::
    python sensitivity.py                 # 重新跑实验
    python sensitivity.py --from-csv      # 不重跑，直接用现有 CSV 重建报告
"""
from __future__ import annotations

import csv
import multiprocessing as mp
import statistics
import sys
import time
from pathlib import Path

from aco import ACOConfig, solve_aco
from instance import parse_solomon

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "solomon" / "100"
RESULTS = HERE / "results"
CSV_PATH = RESULTS / "sensitivity.csv"
MD_PATH = RESULTS / "sensitivity.md"
ITERS = 40
SEEDS = [1, 2, 3]
ALPHAS = (0.5, 1.0, 2.0)
BETAS = (2.0, 3.0, 5.0)
RHOS = (0.05, 0.1, 0.2, 0.3)


def _work(task):
    inst_name, alpha, beta, rho, seed = task
    inst = parse_solomon(DATA / f"{inst_name}.txt")
    cfg = ACOConfig(max_iter=ITERS, seed=seed, alpha=alpha, beta=beta, rho=rho)
    res = solve_aco(inst, cfg)
    return {"instance": inst_name.upper(), "alpha": alpha, "beta": beta, "rho": rho,
            "seed": seed, "distance": res["distance"], "vehicles": res["vehicles"],
            "seconds": res["seconds"]}


def load_csv() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
        return [{"instance": r["instance"], "alpha": float(r["alpha"]), "beta": float(r["beta"]),
                 "rho": float(r["rho"]), "seed": int(r["seed"]),
                 "distance": float(r["distance"]), "vehicles": int(r["vehicles"]),
                 "seconds": float(r["seconds"])} for r in csv.DictReader(fh)]


def agg(rows: list[dict]) -> tuple[float, float]:
    vals = [r["distance"] for r in rows]
    return statistics.mean(vals), (statistics.pstdev(vals) if len(vals) > 1 else 0.0)


def main() -> None:
    jobs = max(mp.cpu_count() - 2, 1)
    for a in sys.argv[1:]:
        if a.startswith("--jobs"):
            jobs = int(a.split("=")[1])

    if "--from-csv" in sys.argv and CSV_PATH.exists():
        rows = load_csv()
        print(f"[复用] 从 {CSV_PATH.name} 读入 {len(rows)} 条记录（不重跑）")
    else:
        tasks = []
        for alpha in ALPHAS:
            for beta in BETAS:
                for seed in SEEDS:
                    tasks.append(("r101", alpha, beta, 0.1, seed))
        for rho in RHOS:
            for seed in SEEDS:
                tasks.append(("rc101", 1.0, 3.0, rho, seed))

        print(f"敏感性实验：{len(tasks)} 次运行，{jobs} 进程并行，迭代 {ITERS} 代", flush=True)
        t0 = time.perf_counter()
        rows = []
        with mp.Pool(jobs) as pool:
            for i, row in enumerate(pool.imap_unordered(_work, tasks), 1):
                rows.append(row)
                if i % 5 == 0 or i == len(tasks):
                    print(f"  {i}/{len(tasks)}｜{time.perf_counter() - t0:.0f}s", flush=True)

        RESULTS.mkdir(exist_ok=True)
        with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # ---------- 汇总 ----------
    grid = {}
    for alpha in ALPHAS:
        for beta in BETAS:
            sel = [r for r in rows if r["instance"] == "R101"
                   and abs(r["alpha"] - alpha) < 1e-9 and abs(r["beta"] - beta) < 1e-9]
            grid[(alpha, beta)] = agg(sel) if sel else (float("nan"), 0.0)

    rho_stat = {}
    for rho in RHOS:
        sel = [r for r in rows if r["instance"] == "RC101" and abs(r["rho"] - rho) < 1e-9]
        rho_stat[rho] = agg(sel)

    lines = ["# 参数敏感性实验", "",
             f"- 迭代 {ITERS} 代，每个参数组合 3 个随机种子（1/2/3）",
             "- 目的：确定 α、β、ρ 的取值范围，为最终参数取值提供依据", "",
             "## α × β 网格（算例 R101）", "",
             "| α \\ β | " + " | ".join(f"β={b:g}" for b in BETAS) + " |",
             "| --- | " + " | ".join(["---"] * len(BETAS)) + " |"]
    for alpha in ALPHAS:
        cells = [f"{grid[(alpha, b)][0]:.2f} ± {grid[(alpha, b)][1]:.2f}" for b in BETAS]
        lines.append(f"| α={alpha:g} | " + " | ".join(cells) + " |")

    lines += ["", "## ρ 扫描（算例 RC101，α=1、β=3）", "",
              "| ρ | 平均里程 | 标准差 |", "| --- | --- | --- |"]
    for rho in RHOS:
        m, s = rho_stat[rho]
        lines.append(f"| {rho:g} | {m:.2f} | {s:.2f} |")

    # ---------- 结论（全部由数据算） ----------
    best_ab = min(grid.items(), key=lambda kv: kv[1][0])[0]
    best_mean = grid[best_ab][0]
    worst_ab = max(grid.items(), key=lambda kv: kv[1][0])[0]
    alpha_best = {a: statistics.mean(grid[(a, b)][0] for b in BETAS) for a in ALPHAS}
    beta_best = {b: statistics.mean(grid[(a, b)][0] for a in ALPHAS) for b in BETAS}
    best_rho = min(rho_stat.items(), key=lambda kv: kv[1][0])[0]

    lines += ["", "## 结论（由数据算出）", "",
              f"1. **α×β 最优组合：α={best_ab[0]:g}、β={best_ab[1]:g}**，平均里程 {best_mean:.2f}；"
              f"最差组合 α={worst_ab[0]:g}、β={worst_ab[1]:g}，"
              f"相差 {(grid[worst_ab][0] - best_mean) / best_mean * 100:.1f}%。",
              "2. 按 α 取平均：" + "；".join(f"α={a:g} → {v:.1f}" for a, v in alpha_best.items())
              + f"。本算例上 **α={min(alpha_best, key=alpha_best.get):g} 最好**（里程越小越好）。",
              "3. 按 β 取平均：" + "；".join(f"β={b:g} → {v:.1f}" for b, v in beta_best.items())
              + f"。本算例上 **β={min(beta_best, key=beta_best.get):g} 最好**（β 越大，启发式信息的权重越高）。",
              "4. ρ 扫描：" + "；".join(f"ρ={r:g} → {rho_stat[r][0]:.1f}" for r in RHOS)
              + f"。本算例上 **ρ={best_rho:g} 最好**"
              + ("，即该算例更依赖快速遗忘、避免过早收敛。"
                 if best_rho == max(RHOS) else "。"),
              "",
              "**注意**：敏感性只在单个算例上做，结论反映趋势，不等于全局最优；"
              "正式取值建议在 2–3 个算例上复核后再定。",
              "",
              f"当前主实验采用的参数为 α=1、β=3、ρ=0.1；"
              f"若改用本实验给出的 α={best_ab[0]:g}、β={best_ab[1]:g}，"
              "解质量仍有下降空间，可作为后续调优方向。"]

    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\n[OK] {CSV_PATH}\n[OK] {MD_PATH}")


if __name__ == "__main__":
    main()
