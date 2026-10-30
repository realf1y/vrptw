# -*- coding: utf-8 -*-
"""M8｜运营 KPI 看板（Operations Dashboard）

把一次求解的结果翻译成“运营人员看得懂”的一页：
    · 六个 KPI 卡片：总里程、车辆数、准时率、平均装载率、平均每车停靠、总成本
    · 三张条形图：每车里程、每车装载率、每车停靠数
    · 一张逐车明细表：仓库、停靠数、载重/装载率、里程、等待、晚到、准时率

图表用内联 SVG 直接拼进 HTML（不依赖 matplotlib、不联网），双击即可打开。

用法
----
    python dashboard.py                                  # C101 + 改进版算法，输出 results/viz/dashboard.html
    python dashboard.py --instance data/solomon/100/r101.txt --iters 40
    python dashboard.py --scene 校园配送-软时间窗 --out results/viz/campus.html
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

from solution import evaluate, evaluate_route

HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# 数据
# --------------------------------------------------------------------------
def vehicle_rows(inst, routes):
    """逐车明细：路线号、仓库、停靠数、载重、装载率、里程、等待、晚到、准时率"""
    capacity = inst.capacity or 1.0
    rows = []
    for idx, route in enumerate(routes, start=1):
        rep = evaluate_route(inst, route)
        n = len(route)
        rows.append({
            "index": idx,
            "depot": rep.depot,
            "stops": n,
            "load": round(rep.load, 1),
            "load_rate": round(rep.load / capacity, 4),
            "distance": round(rep.distance, 2),
            "wait": round(rep.wait_time, 1),
            "late": rep.late_customers,
            "on_time": rep.on_time_rate,
        })
    return rows


def kpi_summary(inst, routes):
    ev = evaluate(inst, routes)
    rows = vehicle_rows(inst, routes)
    n = max(1, len(rows))
    total_wait = round(sum(r["wait"] for r in rows), 1)
    return {
        "distance": ev["total_distance"],
        "vehicles": ev["vehicles"],
        "on_time_rate": ev["on_time_rate"],
        "load_rate": ev["load_rate"],
        "avg_stops": round(sum(r["stops"] for r in rows) / n, 1),
        "total_cost": ev["total_cost"],
        "fixed_cost": ev["fixed_cost"],
        "wait": total_wait,
        "max_route": max((r["distance"] for r in rows), default=0.0),
        "late_customers": ev["late_customers"],
        "feasible": ev["feasible"],
        "rows": rows,
        "metrics": ev,
    }


# --------------------------------------------------------------------------
# SVG 图表（纯字符串，不依赖第三方库）
# --------------------------------------------------------------------------
def bar_chart(labels, values, unit="", color="#2980b9", width=520, height=220,
              title="", fmt="{:.1f}") -> str:
    if not values:
        return ""
    pad_l, pad_b, pad_t, pad_r = 46, 34, 18, 12
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_b - pad_t
    vmax = max(values) or 1.0
    n = len(values)
    slot = inner_w / n
    bar_w = min(38.0, slot * 0.62)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
             'width="100%%" role="img" aria-label="%s">' % (width, height, html.escape(title))]
    parts.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (width, height))
    # 水平网格
    for g in range(5):
        y = pad_t + inner_h * g / 4
        val = vmax * (4 - g) / 4
        parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef1f4"/>'
                     % (pad_l, y, width - pad_r, y))
        parts.append('<text x="%d" y="%.1f" font-size="9" fill="#8a949e" text-anchor="end">%s</text>'
                     % (pad_l - 6, y + 3, fmt.format(val)))
    for i, (lab, v) in enumerate(zip(labels, values)):
        h = inner_h * (v / vmax) if vmax else 0
        x = pad_l + slot * i + (slot - bar_w) / 2
        y = pad_t + inner_h - h
        parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"/>'
                     % (x, y, bar_w, h, color))
        parts.append('<text x="%.1f" y="%.1f" font-size="9.5" fill="#34495e" text-anchor="middle">%s</text>'
                     % (x + bar_w / 2, y - 4, fmt.format(v) + unit))
        parts.append('<text x="%.1f" y="%d" font-size="9.5" fill="#5b6770" text-anchor="middle">%s</text>'
                     % (x + bar_w / 2, height - 12, html.escape(str(lab))))
    parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#c9d2da"/>'
                 % (pad_l, pad_t + inner_h, width - pad_r, pad_t + inner_h))
    parts.append("</svg>")
    return "".join(parts)


def gauge(percent: float, label: str, width: int = 220, height: int = 120, color="#27ae60") -> str:
    """半圆仪表：0–100%"""
    import math
    cx, cy, r = width / 2, height - 16, 78
    ang = math.pi * (1 - max(0.0, min(1.0, percent)))
    x2, y2 = cx + r * math.cos(ang), cy - r * math.sin(ang)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="100%%">'
            '<path d="M %.1f %.1f A %d %d 0 0 1 %.1f %.1f" fill="none" stroke="#e8eef3" stroke-width="12" stroke-linecap="round"/>'
            '<path d="M %.1f %.1f A %d %d 0 0 1 %.1f %.1f" fill="none" stroke="%s" stroke-width="12" stroke-linecap="round"/>'
            '<text x="%.1f" y="%.1f" font-size="20" font-weight="600" fill="#1f2d3d" text-anchor="middle">%.1f%%</text>'
            '<text x="%.1f" y="%d" font-size="10" fill="#7f8c8d" text-anchor="middle">%s</text>'
            '</svg>') % (width, height,
                         cx - r, cy, r, r, x2, y2,
                         cx - r, cy, r, r, x2, y2, color,
                         cx, cy - 22, percent * 100,
                         cx, height - 2, html.escape(label))


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------
CSS = """
body{font-family:"Microsoft YaHei","PingFang SC",SimHei,sans-serif;margin:0;background:#f4f6f9;color:#243240}
header{background:linear-gradient(90deg,#1f3a5f,#2f6f9f);color:#fff;padding:20px 28px}
header h1{margin:0;font-size:21px;font-weight:600}
header .sub{opacity:.82;font-size:12.5px;margin-top:5px}
.wrap{max-width:1180px;margin:20px auto 40px;padding:0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:12px}
.card{background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(20,40,60,.08)}
.card .t{font-size:12px;color:#7b8794}
.card .v{font-size:22px;font-weight:600;margin-top:6px;color:#1f3a5f}
.card .u{font-size:12px;color:#95a2ad;margin-left:3px;font-weight:400}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:16px}
.charts .card h3,.detail h3{margin:0 0 8px;font-size:13.5px;color:#3b4a59;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:7px 8px;border-bottom:1px solid #eef1f4;text-align:center}
th{background:#f7f9fb;color:#5b6770;font-weight:600}
tbody tr:hover{background:#fbfdff}
.bad{color:#c0392b;font-weight:600}
.ok{color:#1e8449}
.foot{margin-top:16px;font-size:12px;color:#8592a0;line-height:1.7}
.tag{display:inline-block;padding:2px 8px;border-radius:10px;background:#eaf4ec;color:#1e8449;font-size:11.5px}
.tag.warn{background:#fdecea;color:#c0392b}
@media (max-width:860px){.charts{grid-template-columns:1fr}}
"""


def render_html(inst, routes, title="运营 KPI 看板", subtitle="", kpi=None) -> str:
    kpi = kpi or kpi_summary(inst, routes)
    rows = kpi["rows"]
    labels = ["车 " + str(r["index"]) for r in rows]
    dist_svg = bar_chart(labels, [r["distance"] for r in rows], "", "#2f6f9f", title="每车里程")
    load_svg = bar_chart(labels, [r["load_rate"] * 100 for r in rows], "%", "#27ae60", title="每车装载率")
    stop_svg = bar_chart(labels, [r["stops"] for r in rows], "", "#8e6bbf", fmt="{:.0f}", title="每车停靠数")
    on_time_svg = gauge(kpi["on_time_rate"], "整体准时率")

    cards = [
        ("总里程", "%.2f" % kpi["distance"], "km"),
        ("车辆数", str(kpi["vehicles"]), "台"),
        ("准时率", "%.1f%%" % (kpi["on_time_rate"] * 100), ""),
        ("平均装载率", "%.1f%%" % (kpi["load_rate"] * 100), ""),
        ("平均每车停靠", "%.1f" % kpi["avg_stops"], "点"),
        ("总成本", "%.2f" % kpi["total_cost"], "（里程+固定）"),
    ]
    card_html = "".join(
        '<div class="card"><div class="t">%s</div><div class="v">%s<span class="u">%s</span></div></div>'
        % (t, v, u) for t, v, u in cards)

    body_rows = []
    for r in rows:
        cls = "bad" if r["late"] else "ok"
        body_rows.append(
            "<tr><td>%d</td><td>%d</td><td>%d</td><td>%.1f</td><td>%.1f%%</td><td>%.2f</td>"
            "<td>%.1f</td><td class=\"%s\">%d</td><td class=\"%s\">%.1f%%</td></tr>"
            % (r["index"], r["depot"], r["stops"], r["load"], r["load_rate"] * 100,
               r["distance"], r["wait"], cls, r["late"], cls, r["on_time"] * 100))

    feasible_tag = ('<span class="tag">方案可行</span>' if kpi["feasible"]
                    else '<span class="tag warn">存在约束违反</span>')
    return ("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>%s</title><style>%s</style></head><body>"
            "<header><h1>%s</h1><div class=\"sub\">%s　%s</div></header>"
            "<div class=\"wrap\"><div class=\"grid\">%s</div>"
            "<div class=\"charts\"><div class=\"card\"><h3>%s</h3>%s</div>"
            "<div class=\"card\"><h3>%s</h3>%s</div></div>"
            "<div class=\"charts\"><div class=\"card\"><h3>每车停靠数</h3>%s</div>"
            "<div class=\"card\"><h3>整体准时率</h3>%s</div></div>"
            "<div class=\"card detail\" style=\"margin-top:14px\"><h3>逐车明细</h3>"
            "<table><thead><tr><th>车次</th><th>仓库</th><th>停靠</th><th>载重</th><th>装载率</th>"
            "<th>里程</th><th>等待</th><th>晚到</th><th>准时率</th></tr></thead><tbody>%s</tbody></table></div>"
            "<div class=\"foot\">%s　等待合计 %.1f｜最长单车里程 %.2f｜固定成本 %.2f</div>"
            "</div></body></html>"
            ) % (html.escape(title), CSS, html.escape(title), html.escape(subtitle), feasible_tag,
                 card_html, "每车里程（km）", dist_svg, "每车装载率（%）", load_svg,
                 stop_svg, on_time_svg, "".join(body_rows),
                 "数据口径：total_distance 为回路里程之和；准时率 = 未晚到客户数 / 客户总数。",
                 kpi["wait"], kpi["max_route"], kpi["fixed_cost"])


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------
def main() -> None:
    args = sys.argv[1:]
    instance = "data/solomon/100/c101.txt"
    out = "results/viz/dashboard.html"
    iters, seed, scene_name = 40, 1, None
    i = 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else None
        if a == "--instance" and nxt:
            instance = nxt; i += 1
        elif a.startswith("--instance="):
            instance = a.split("=", 1)[1]
        elif a == "--out" and nxt:
            out = nxt; i += 1
        elif a.startswith("--out="):
            out = a.split("=", 1)[1]
        elif a == "--iters" and nxt:
            iters = int(nxt); i += 1
        elif a.startswith("--iters="):
            iters = int(a.split("=", 1)[1])
        elif a == "--seed" and nxt:
            seed = int(nxt); i += 1
        elif a == "--scene" and nxt:
            scene_name = nxt; i += 1
        i += 1

    from aco import ACOConfig, solve_aco
    from instance import parse_solomon

    if scene_name:
        from scene import Scene
        scene = Scene.load(scene_name)
        inst = scene.load_instance()
        cfg = scene.aco_config(max_iter=iters, seed=seed)
        subtitle = scene.describe()
    else:
        inst = parse_solomon(instance)
        cfg = ACOConfig(max_iter=iters, seed=seed)
        subtitle = inst.describe()

    res = solve_aco(inst, cfg)
    kpi = kpi_summary(inst, res["routes"])
    page = render_html(inst, res["routes"], "配送运营 KPI 看板",
                       subtitle + "｜里程 %.2f｜车辆 %d｜用时 %.1fs"
                       % (res["distance"], res["vehicles"], res["seconds"]), kpi)
    path = Path(out)
    if not path.is_absolute():
        path = HERE / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    print("看板已生成：%s" % path)
    print("KPI：里程 %.2f｜车辆 %d｜准时率 %.1f%%｜装载率 %.1f%%｜总成本 %.2f"
          % (kpi["distance"], kpi["vehicles"], kpi["on_time_rate"] * 100,
             kpi["load_rate"] * 100, kpi["total_cost"]))
    print("逐车：")
    for r in kpi["rows"]:
        print("  车%-2d 停靠 %2d｜载重 %5.1f（%4.1f%%）｜里程 %6.2f｜等待 %5.1f｜晚到 %d"
              % (r["index"], r["stops"], r["load"], r["load_rate"] * 100,
                 r["distance"], r["wait"], r["late"]))


if __name__ == "__main__":
    main()
