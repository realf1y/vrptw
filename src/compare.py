# -*- coding: utf-8 -*-
"""M10｜成本与碳排对比页（Cost & Carbon Comparison）

把「成本优先 / 均衡 / 低碳优先」三组权重的求解结果放在一页里对比：
    · 六张卡片：三个方案的总成本、碳排、车辆数
    · 成本构成堆叠条形图（里程成本 / 固定成本 / 碳成本 / 晚到罚金）
    · 碳排对比条形图
    · 成本—碳排散点图（左上角更优，展示取舍）
    · 明细表：里程、车辆、各项成本、碳排、准时率、装载率

图表同样是内联 SVG（不依赖 matplotlib），页面可离线打开。

用法
----
    python compare.py --instance data/solomon/100/r101.txt --iters 40
    python compare.py --instance data/solomon/100/c101.txt --iters 40 --out results/viz/cost_carbon_c101.html
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

from multiobjective import breakdown, presets, solve_weighted

HERE = Path(__file__).resolve().parent

COLORS = ["#2f6f9f", "#27ae60", "#e67e22", "#8e44ad"]


def scheme_summary(inst, routes, name: str) -> dict:
    b = breakdown(inst, routes)
    b["name"] = name
    return b


# --------------------------------------------------------------------------
# SVG
# --------------------------------------------------------------------------
def stacked_cost_chart(schemes, width=560, height=250) -> str:
    pad_l, pad_b, pad_t = 58, 40, 18
    inner_w = width - pad_l - 20
    inner_h = height - pad_b - pad_t
    totals = [s["dist_cost"] + s["fixed_cost"] + s["carbon_cost"] + s["late_penalty"] for s in schemes]
    vmax = max(totals) or 1.0
    slot = inner_w / max(1, len(schemes))
    bar_w = min(70.0, slot * 0.5)
    keys = [("dist_cost", "里程成本", COLORS[0]), ("fixed_cost", "固定成本", COLORS[1]),
            ("carbon_cost", "碳成本", COLORS[2]), ("late_penalty", "晚到罚金", COLORS[3])]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="100%%">' % (width, height)]
    parts.append('<rect width="%d" height="%d" fill="#fff"/>' % (width, height))
    for g in range(4):
        y = pad_t + inner_h * g / 3
        parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef1f4"/>'
                     % (pad_l, y, width - 20, y))
        parts.append('<text x="%d" y="%.1f" font-size="9" fill="#8a949e" text-anchor="end">%.0f</text>'
                     % (pad_l - 6, y + 3, vmax * (3 - g) / 3))
    for i, s in enumerate(schemes):
        x = pad_l + slot * i + (slot - bar_w) / 2
        y = pad_t + inner_h
        for key, _label, color in keys:
            h = inner_h * (s[key] / vmax) if vmax else 0
            y -= h
            if h > 0:
                parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
                             % (x, y, bar_w, h, color))
        parts.append('<text x="%.1f" y="%d" font-size="10" fill="#5b6770" text-anchor="middle">%s</text>'
                     % (x + bar_w / 2, height - 14, html.escape(s["name"])))
        parts.append('<text x="%.1f" y="%.1f" font-size="9.5" fill="#34495e" text-anchor="middle">%.0f</text>'
                     % (x + bar_w / 2, y - 5, totals[i]))
    parts.append("</svg>")
    return "".join(parts)


def simple_bar(schemes, key: str, unit="", color="#27ae60", width=520, height=230, fmt="{:.0f}") -> str:
    pad_l, pad_b, pad_t = 52, 38, 16
    inner_w, inner_h = width - pad_l - 20, height - pad_b - pad_t
    values = [s[key] for s in schemes]
    vmax = max(values) or 1.0
    slot = inner_w / max(1, len(values))
    bar_w = min(64.0, slot * 0.5)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="100%%">' % (width, height)]
    parts.append('<rect width="%d" height="%d" fill="#fff"/>' % (width, height))
    for g in range(4):
        y = pad_t + inner_h * g / 3
        parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef1f4"/>'
                     % (pad_l, y, width - 20, y))
        parts.append('<text x="%d" y="%.1f" font-size="9" fill="#8a949e" text-anchor="end">%s</text>'
                     % (pad_l - 6, y + 3, fmt.format(vmax * (3 - g) / 3)))
    for i, s in enumerate(schemes):
        v = s[key]
        h = inner_h * (v / vmax) if vmax else 0
        x = pad_l + slot * i + (slot - bar_w) / 2
        y = pad_t + inner_h - h
        parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"/>'
                     % (x, y, bar_w, h, color))
        parts.append('<text x="%.1f" y="%.1f" font-size="10" fill="#34495e" text-anchor="middle">%s%s</text>'
                     % (x + bar_w / 2, y - 5, fmt.format(v), unit))
        parts.append('<text x="%.1f" y="%d" font-size="10" fill="#5b6770" text-anchor="middle">%s</text>'
                     % (x + bar_w / 2, height - 14, html.escape(s["name"])))
    parts.append("</svg>")
    return "".join(parts)


def scatter(schemes, width=520, height=300) -> str:
    pad_l, pad_b, pad_t, pad_r = 62, 44, 18, 22
    inner_w, inner_h = width - pad_l - pad_r, height - pad_b - pad_t
    xs = [s["carbon_kg"] for s in schemes]
    ys = [s["total_cost"] for s in schemes]
    x0, x1 = min(xs) * 0.96, max(xs) * 1.04
    y0, y1 = min(ys) * 0.96, max(ys) * 1.04
    if x1 - x0 < 1e-9:
        x1 = x0 + 1
    if y1 - y0 < 1e-9:
        y1 = y0 + 1

    def px(v):
        return pad_l + inner_w * (v - x0) / (x1 - x0)

    def py(v):
        return pad_t + inner_h * (1 - (v - y0) / (y1 - y0))

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="100%%">' % (width, height)]
    parts.append('<rect width="%d" height="%d" fill="#fff"/>' % (width, height))
    parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#d8e0e8"/>'
                 % (pad_l, pad_t, inner_w, inner_h))
    for g in range(4):
        pct = g / 3
        parts.append('<text x="%d" y="%.1f" font-size="9" fill="#8a949e" text-anchor="end">%.0f</text>'
                     % (pad_l - 6, pad_t + inner_h * (1 - pct) + 3, y0 + (y1 - y0) * pct))
        parts.append('<text x="%.1f" y="%d" font-size="9" fill="#8a949e" text-anchor="middle">%.0f</text>'
                     % (pad_l + inner_w * pct, height - 22, x0 + (x1 - x0) * pct))
    parts.append('<text x="%.1f" y="%d" font-size="10" fill="#5b6770" text-anchor="middle">碳排（kg CO2）</text>'
                 % (pad_l + inner_w / 2, height - 6))
    parts.append('<text x="14" y="%.1f" font-size="10" fill="#5b6770" transform="rotate(-90 14 %.1f)">总成本（元）</text>'
                 % (pad_t + inner_h / 2, pad_t + inner_h / 2))
    for i, s in enumerate(schemes):
        cx, cy = px(s["carbon_kg"]), py(s["total_cost"])
        parts.append('<circle cx="%.1f" cy="%.1f" r="7" fill="%s" fill-opacity="0.85"/>'
                     % (cx, cy, COLORS[i % len(COLORS)]))
        parts.append('<text x="%.1f" y="%.1f" font-size="10" fill="#34495e" text-anchor="middle">%s</text>'
                     % (cx, cy - 12, html.escape(s["name"])))
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------
CSS = """
body{font-family:"Microsoft YaHei","PingFang SC",SimHei,sans-serif;margin:0;background:#f4f6f9;color:#243240}
header{background:linear-gradient(90deg,#173a34,#2f7f6f);color:#fff;padding:20px 28px}
header h1{margin:0;font-size:21px;font-weight:600}
header .sub{opacity:.85;font-size:12.5px;margin-top:5px}
.wrap{max-width:1180px;margin:20px auto 40px;padding:0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(20,40,60,.08)}
.card .t{font-size:12px;color:#7b8794}
.card .v{font-size:21px;font-weight:600;margin-top:6px;color:#1f3a34}
.card .u{font-size:12px;color:#95a2ad;margin-left:3px;font-weight:400}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:16px}
.charts .card h3,.detail h3{margin:0 0 8px;font-size:13.5px;color:#3b4a59;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:7px 8px;border-bottom:1px solid #eef1f4;text-align:center}
th{background:#f7f9fb;color:#5b6770;font-weight:600}
.foot{margin-top:14px;font-size:12px;color:#8592a0;line-height:1.7}
.legend span{display:inline-block;margin-right:14px;font-size:12px;color:#5b6770}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
@media (max-width:860px){.charts{grid-template-columns:1fr}}
"""


def build_page(inst, schemes, title="成本与碳排对比", subtitle="") -> str:
    cards = []
    for s in schemes:
        cards.append('<div class="card"><div class="t">%s · 总成本</div><div class="v">%.0f<span class="u">元</span></div></div>'
                     % (html.escape(s["name"]), s["total_cost"]))
    for s in schemes:
        cards.append('<div class="card"><div class="t">%s · 碳排</div><div class="v">%.1f<span class="u">kg</span></div></div>'
                     % (html.escape(s["name"]), s["carbon_kg"]))
    for s in schemes:
        cards.append('<div class="card"><div class="t">%s · 车辆</div><div class="v">%d<span class="u">台</span></div></div>'
                     % (html.escape(s["name"]), s["vehicles"]))

    rows = []
    for s in schemes:
        rows.append("<tr><td>%s</td><td>%.2f</td><td>%d</td><td>%.1f</td><td>%.1f</td>"
                    "<td>%.1f</td><td>%.1f</td><td>%.1f</td><td>%.1f</td><td>%.1f%%</td><td>%.1f%%</td></tr>"
                    % (html.escape(s["name"]), s["distance"], s["vehicles"], s["dist_cost"],
                       s["fixed_cost"], s["carbon_kg"], s["carbon_cost"], s["late_penalty"],
                       s["total_cost"], s["on_time_rate"] * 100, s["load_rate"] * 100))

    legend = ('<div class="legend"><span><i style="background:%s"></i>里程成本</span>'
              '<span><i style="background:%s"></i>固定成本</span>'
              '<span><i style="background:%s"></i>碳成本</span>'
              '<span><i style="background:%s"></i>晚到罚金</span></div>'
              % (COLORS[0], COLORS[1], COLORS[2], COLORS[3]))

    return ("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>%s</title><style>%s</style></head><body>"
            "<header><h1>%s</h1><div class=\"sub\">%s</div></header>"
            "<div class=\"wrap\"><div class=\"grid\">%s</div>"
            "<div class=\"charts\"><div class=\"card\"><h3>成本构成</h3>%s%s</div>"
            "<div class=\"card\"><h3>碳排对比（kg CO2）</h3>%s</div></div>"
            "<div class=\"charts\"><div class=\"card\"><h3>成本—碳排取舍</h3>%s</div>"
            "<div class=\"card\"><h3>口径说明</h3><div class=\"foot\">"
            "里程成本 3.5 元/km；固定成本 300 元/车；碳排 = 里程 ×（0.25 + 0.25 × 装载率）kg/km；"
            "碳成本按 0.5 元/kg 折算；晚到罚金 50 元/单位时间窗违反。"
            "散点越靠左下越好：同样的钱排更少的碳，或同样的碳花更少的钱。</div></div></div>"
            "<div class=\"card detail\" style=\"margin-top:14px\"><h3>方案明细</h3>"
            "<table><thead><tr><th>方案</th><th>里程</th><th>车辆</th><th>里程成本</th><th>固定成本</th>"
            "<th>碳排(kg)</th><th>碳成本</th><th>晚到罚金</th><th>总成本</th><th>准时率</th><th>装载率</th>"
            "</tr></thead><tbody>%s</tbody></table></div></div></body></html>"
            ) % (html.escape(title), CSS, html.escape(title), html.escape(subtitle),
                 "".join(cards), legend, stacked_cost_chart(schemes),
                 simple_bar(schemes, "carbon_kg", " kg", COLORS[1], fmt="{:.1f}"),
                 scatter(schemes), "".join(rows))


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------
def main() -> None:
    args = sys.argv[1:]
    instance = "data/solomon/100/c101.txt"
    iters, seed = 40, 1
    out = "results/viz/cost_carbon.html"
    i = 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else None
        if a == "--instance" and nxt:
            instance = nxt; i += 1
        elif a.startswith("--instance="):
            instance = a.split("=", 1)[1]
        elif a == "--iters" and nxt:
            iters = int(nxt); i += 1
        elif a.startswith("--iters="):
            iters = int(a.split("=", 1)[1])
        elif a == "--seed" and nxt:
            seed = int(nxt); i += 1
        elif a == "--out" and nxt:
            out = nxt; i += 1
        elif a.startswith("--out="):
            out = a.split("=", 1)[1]
        i += 1

    from instance import parse_solomon

    inst = parse_solomon(instance)
    schemes = []
    for name, w in presets().items():
        print("求解 " + name + " ...", flush=True)
        res = solve_weighted(inst, name, w, iters=iters, seed=seed)
        schemes.append(scheme_summary(inst, res["routes"], name))
    page = build_page(inst, schemes, "成本与碳排对比",
                      "%s｜%d 代｜%s" % (inst.describe(), iters, " / ".join(s["name"] for s in schemes)))
    path = Path(out)
    if not path.is_absolute():
        path = HERE / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    print("对比页已生成：" + str(path))
    for s in schemes:
        print("  %-6s 里程 %7.2f｜车辆 %2d｜碳排 %7.1f kg｜总成本 %8.1f 元"
              % (s["name"], s["distance"], s["vehicles"], s["carbon_kg"], s["total_cost"]))


if __name__ == "__main__":
    main()
