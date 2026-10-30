# -*- coding: utf-8 -*-
"""M6｜方案对比与报表（Reporting）

把实验结果汇总成能直接交给老师的报表，三个格式一起出：

    results/report_<规模>_<次数>x.md      Markdown（可直接贴进文档）
    results/report_<规模>_<次数>x.csv     明细表（Excel 打开可画图）
    results/report_<规模>_<次数>x.html    HTML 报表页（双击看，带 KPI 卡片）

KPI 定义
--------
- 总里程：均值 ± 标准差（蚁群是随机算法，必须报标准差）
- 车辆数：平均用车数
- 准时率：按时间窗准时送达的客户占比
- 装载率：总需求 / (车辆数 × 单车载重)
- 与最优差距：相对 Solomon 已知最优解的 gap
- 平均耗时：单次求解秒数

用法::
    python report.py 100 10          # 读 results/experiments_100_10x.csv
    python report.py 100 3 --db      # 改用数据库里的记录（store.py import 之后）
"""
from __future__ import annotations

import csv
import json
import sqlite3
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
DB_PATH = HERE / "vrptw.db"
BKS_FILE = HERE / "data" / "solomon_bks.json"

METHOD_ORDER = ["最近邻(贪心)", "L0 基线ACO", "L1 +时间窗η", "L2 +MMAS精英",
                "L3 +局部搜索(改进版)"]


def load_rows(size: str, runs: int, use_db: bool) -> list[dict]:
    if use_db:
        if not DB_PATH.exists():
            raise SystemExit(f"数据库不存在：{DB_PATH}（先跑 store.py import）")
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.execute(
            "SELECT i.name, e.method, e.distance, e.vehicles, e.feasible,"
            " e.on_time_rate, e.load_rate, e.seconds"
            " FROM experiment e JOIN instance i ON i.id = e.instance_id"
            " WHERE i.size = ?", (size,))
        rows = [{"instance": r[0], "method": r[1], "distance": r[2], "vehicles": r[3],
                 "feasible": r[4], "on_time_rate": r[5], "load_rate": r[6], "seconds": r[7]}
                for r in cur.fetchall()]
        conn.close()
        return rows

    path = RESULTS / f"experiments_{size}_{runs}x.csv"
    if not path.exists():
        raise SystemExit(f"没找到实验结果：{path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def summarize(rows: list[dict], bks: dict) -> tuple[list[dict], list[dict]]:
    """返回 (方法级汇总, 算例×方法明细)。"""
    methods = [m for m in METHOD_ORDER if any(r["method"] == m for r in rows)]
    methods += [m for m in sorted({r["method"] for r in rows}) if m not in methods]
    instances = sorted({(r["instance"] or "").upper() for r in rows})

    method_summary = []
    for m in methods:
        sel = [r for r in rows if r["method"] == m]
        dists = [fnum(r.get("distance")) for r in sel if fnum(r.get("distance")) is not None]
        if not dists:
            continue
        opt = None
        gaps = []
        for r in sel:
            b = bks.get((r["instance"] or "").upper(), {}).get("distance")
            d = fnum(r.get("distance"))
            if b and d:
                gaps.append(100 * (d - b) / b)
        veh = [fnum(r.get("vehicles")) for r in sel if fnum(r.get("vehicles")) is not None]
        otr = [fnum(r.get("on_time_rate")) for r in sel if fnum(r.get("on_time_rate")) is not None]
        lr = [fnum(r.get("load_rate")) for r in sel if fnum(r.get("load_rate")) is not None]
        sec = [fnum(r.get("seconds")) for r in sel if fnum(r.get("seconds")) is not None]
        feas = [r for r in sel if str(r.get("feasible")).lower() in {"true", "1"}]
        method_summary.append({
            "method": m,
            "runs": len(sel),
            "distance_mean": round(statistics.mean(dists), 2),
            "distance_std": round(statistics.pstdev(dists), 2) if len(dists) > 1 else 0.0,
            "distance_best": round(min(dists), 2),
            "gap_mean": round(statistics.mean(gaps), 1) if gaps else None,
            "vehicles": round(statistics.mean(veh), 1) if veh else None,
            "on_time": round(statistics.mean(otr) * 100, 1) if otr else None,
            "load_rate": round(statistics.mean(lr) * 100, 1) if lr else None,
            "seconds": round(statistics.mean(sec), 2) if sec else None,
            "feasible_rate": round(100 * len(feas) / len(sel), 1) if sel else None,
        })

    detail = []
    for inst in instances:
        row = {"instance": inst, "bks": bks.get(inst, {}).get("distance")}
        for m in methods:
            sel = [fnum(r.get("distance")) for r in rows
                   if r["method"] == m and (r["instance"] or "").upper() == inst]
            sel = [v for v in sel if v is not None]
            row[m] = (round(statistics.mean(sel), 2),
                      round(statistics.pstdev(sel), 2) if len(sel) > 1 else 0.0,
                      len(sel))
        detail.append(row)

    return method_summary, detail


def render_markdown(ms: list[dict], detail: list[dict], size: str, runs: int) -> str:
    lines = [f"# 实验结果报表（{size} 客户算例，每方法 {runs} 次）", "",
             "## 一、方法级 KPI 汇总", "",
             "| 方法 | 次数 | 总里程（均值±标准差） | 最优 | 与最优差距 | 车辆数 | 准时率 | 装载率 | 平均耗时 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in ms:
        gap = f"{r['gap_mean']}%" if r["gap_mean"] is not None else "-"
        lines.append(
            f"| {r['method']} | {r['runs']} | {r['distance_mean']} ± {r['distance_std']} | "
            f"{r['distance_best']} | {gap} | {r['vehicles']} | "
            f"{r['on_time'] if r['on_time'] is not None else '-'}% | "
            f"{r['load_rate'] if r['load_rate'] is not None else '-'}% | "
            f"{r['seconds']}s |")

    lines += ["", "## 二、逐算例对比（总里程）", ""]
    methods = [r["method"] for r in ms]
    lines.append("| 算例 | 已知最优 | " + " | ".join(methods) + " |")
    lines.append("| --- | --- | " + " | ".join(["---"] * len(methods)) + " |")
    for d in detail:
        cells = []
        for m in methods:
            v = d.get(m)
            cells.append(f"{v[0]:.2f} ± {v[1]:.2f}" if v and v[2] else "-")
        lines.append(f"| {d['instance']} | {d['bks'] if d['bks'] else '-'} | " + " | ".join(cells) + " |")

    lines += ["", "## 三、结论要点", "",
              "1. 改进版相对基线 ACO 的总里程下降幅度见上表「与最优差距」列；",
              "2. 聚类型算例（C 类）容易在 L1 就饱和，R / RC 类才能看出各层改进的梯度；",
              "3. 蚁群为随机算法，表中标准差反映稳定性——改进版的标准差通常明显小于基线；",
              "4. 局部搜索（L3）以时间换质量，平均耗时高于其他层级。"]
    return "\n".join(lines) + "\n"


def export_xlsx(path: Path, ms: list[dict], detail: list[dict], size: str, runs: int) -> Path:
    """导出 Excel：两个工作表（KPI 汇总 + 逐算例），首行加粗冻结"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    head_font = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="EEF4F8")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws = wb.active
    ws.title = "KPI汇总"
    headers = ["方法", "次数", "总里程均值", "标准差", "最优", "与最优差距(%)",
               "车辆数", "准时率(%)", "装载率(%)", "平均耗时(s)", "可行率(%)"]
    ws.append(headers)
    for r in ms:
        ws.append([r["method"], r["runs"], r["distance_mean"], r["distance_std"],
                   r["distance_best"], r["gap_mean"], r["vehicles"], r["on_time"],
                   r["load_rate"], r["seconds"], r["feasible_rate"]])

    ws2 = wb.create_sheet("逐算例")
    methods = [r["method"] for r in ms]
    ws2.append(["算例", "已知最优"] + [f"{m}(均值)" for m in methods] + [f"{m}(标准差)" for m in methods])
    for d in detail:
        row = [d["instance"], d["bks"]]
        row += [(d.get(m) or (None, None, 0))[0] for m in methods]
        row += [(d.get(m) or (None, None, 0))[1] for m in methods]
        ws2.append(row)

    for sheet in (ws, ws2):
        for c in sheet[1]:
            c.font = head_font
            c.fill = head_fill
            c.alignment = center
        sheet.freeze_panes = "A2"
        for col in sheet.columns:
            width = max(len(str(c.value or "")) for c in col) * 1.6 + 4
            sheet.column_dimensions[col[0].column_letter].width = min(max(width, 10), 34)

    ws.insert_rows(1)
    ws["A1"] = f"实验结果（{size} 客户算例，每方法 {runs} 次）"
    ws["A1"].font = Font(bold=True, size=12)
    wb.save(str(path))
    return path


def render_html(ms: list[dict], detail: list[dict], size: str, runs: int) -> str:
    css = """
    body{font-family:Microsoft YaHei,SimHei,sans-serif;margin:0;background:#f5f6f8;color:#222}
    header{background:#1f2d3d;color:#fff;padding:18px 26px}
    header h1{margin:0;font-size:20px}
    header p{margin:6px 0 0;color:#9fb3c8;font-size:13px}
    .wrap{max-width:1100px;margin:20px auto;padding:0 16px}
    .cards{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:18px}
    .kpi{background:#fff;border-radius:10px;padding:14px 18px;flex:1 1 180px;
         box-shadow:0 1px 3px rgba(0,0,0,.08)}
    .kpi .t{font-size:12px;color:#7a8a99}
    .kpi .v{font-size:22px;font-weight:600;margin-top:6px;color:#1f2d3d}
    .kpi .s{font-size:12px;color:#98a6b3;margin-top:4px}
    .card{background:#fff;border-radius:10px;padding:18px 20px;margin-bottom:18px;
          box-shadow:0 1px 3px rgba(0,0,0,.08)}
    h2{font-size:16px;margin:0 0 12px;color:#1f2d3d}
    table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{border-bottom:1px solid #eee;padding:8px 10px;text-align:left;white-space:nowrap}
    th{background:#fafbfc;color:#555}
    tr:hover td{background:#f7fbff}
    .good{color:#1a7f37;font-weight:600}
    .warn{color:#b54708}
    """
    def kpi_card(title, value, sub=""):
        return (f"<div class='kpi'><div class='t'>{title}</div>"
                f"<div class='v'>{value}</div><div class='s'>{sub}</div></div>")

    best = min((r for r in ms if r["method"].startswith("L3")), key=lambda r: r["distance_mean"],
               default=None)
    base = next((r for r in ms if r["method"].startswith("L0")), None)
    cards = ""
    if best:
        cards += kpi_card("改进版平均总里程", f"{best['distance_mean']:.2f}",
                          f"± {best['distance_std']:.2f}（{best['runs']} 次）")
        cards += kpi_card("相对基线 ACO 提升",
                          f"{(base['distance_mean'] - best['distance_mean']) / base['distance_mean'] * 100:.1f}%"
                          if base else "-", "同算例同次数对比")
        cards += kpi_card("与已知最优差距", f"{best['gap_mean']}%" if best["gap_mean"] is not None else "-",
                          "Solomon 标准算例")
        cards += kpi_card("平均耗时", f"{best['seconds']}s", "单次求解（100 客户）")

    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{} ± {}</td><td>{}</td>"
        "<td>{}</td><td>{}</td><td>{}%</td><td>{}%</td><td>{}s</td></tr>".format(
            r["method"], r["runs"], r["distance_mean"], r["distance_std"], r["distance_best"],
            f"{r['gap_mean']}%" if r["gap_mean"] is not None else "-",
            r["vehicles"], r["on_time"] if r["on_time"] is not None else "-",
            r["load_rate"] if r["load_rate"] is not None else "-", r["seconds"])
        for r in ms)

    methods = [r["method"] for r in ms]
    head = "".join(f"<th>{m}</th>" for m in methods)
    detail_rows = ""
    for d in detail:
        cells = ""
        for m in methods:
            v = d.get(m)
            cells += f"<td>{v[0]:.2f} ± {v[1]:.2f}</td>" if v and v[2] else "<td>-</td>"
        detail_rows += (f"<tr><td>{d['instance']}</td>"
                        f"<td>{d['bks'] if d['bks'] else '-'}</td>{cells}</tr>")

    return ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            f"<title>实验结果报表 {size} 客户</title><style>{css}</style></head><body>"
            "<header><h1>带时间窗配送路径优化 · 实验结果报表</h1>"
            f"<p>算例规模 {size} 客户｜每方法重复 {runs} 次｜算法：改进蚁群（时间窗启发式 + MMAS 精英 + 混合局部搜索）</p>"
            f"</header><div class='wrap'><div class='cards'>{cards}</div>"
            "<div class='card'><h2>一、方法级 KPI 汇总</h2><table>"
            "<tr><th>方法</th><th>次数</th><th>总里程</th><th>最优</th><th>与最优差距</th>"
            "<th>车辆数</th><th>准时率</th><th>装载率</th><th>平均耗时</th></tr>"
            + rows + "</table></div>"
            "<div class='card'><h2>二、逐算例对比（总里程）</h2><table>"
            f"<tr><th>算例</th><th>已知最优</th>{head}</tr>{detail_rows}</table></div>"
            "<div class='card'><h2>三、结论要点</h2><ul>"
            "<li>聚类型（C 类）算例在加时间窗启发式后即接近最优，R / RC 类才能看出四层改进的梯度；</li>"
            "<li>蚁群为随机算法，标准差反映稳定性，改进版通常明显更稳；</li>"
            "<li>局部搜索以时间换质量：里程最低，单次耗时也最高；</li>"
            "<li>MMAS 与精英策略在本参数设置下增益有限（40 代），可增大迭代数进一步验证。</li>"
            "</ul></div></div></body></html>")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_db = "--db" in sys.argv
    size = args[0] if args else "100"
    runs = int(args[1]) if len(args) > 1 else 10

    rows = load_rows(size, runs, use_db)
    bks = json.loads(BKS_FILE.read_text(encoding="utf-8")) if BKS_FILE.exists() else {}
    ms, detail = summarize(rows, bks)

    RESULTS.mkdir(exist_ok=True)
    stem = f"report_{size}_{runs}x"
    md = render_markdown(ms, detail, size, runs)
    (RESULTS / f"{stem}.md").write_text(md, encoding="utf-8")
    (RESULTS / f"{stem}.html").write_text(render_html(ms, detail, size, runs), encoding="utf-8")

    with (RESULTS / f"{stem}.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(list(ms[0].keys()) if ms else [])
        for r in ms:
            w.writerow(list(r.values()))

    xlsx = export_xlsx(RESULTS / f"{stem}.xlsx", ms, detail, size, runs)

    print(md)
    print(f"报表已输出：\n  results/{stem}.md\n  results/{stem}.html\n"
          f"  results/{stem}.csv\n  results/{stem}.xlsx")


if __name__ == "__main__":
    main()
