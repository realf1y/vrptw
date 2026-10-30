# -*- coding: utf-8 -*-
"""M3｜可视化：路线图 / 收敛曲线 / 消融柱状图 → SVG + PNG + 一个自带切换的 HTML 报告页

不依赖任何绘图库：
- SVG 用标准库拼字符串
- PNG 用 Pillow 直接画（渲染中文用系统自带微软雅黑）
- HTML 报告把 SVG 内嵌进去，双击即可打开，**不需要起服务器、不需要联网**

用法::

    python viz.py                              # 默认：100 客户 c101，迭代 50
    python viz.py data/solomon/100/r101.txt    # 指定算例
    python viz.py data/solomon/100/c101.txt --iters=80
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

from aco import ACOConfig, solve_aco
from instance import parse_solomon
from solution import evaluate, nearest_neighbor

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "viz"
PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
           "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#393b79", "#ad494a"]

METHOD_KEY = {"最近邻(贪心)": "NN", "L0 基线ACO": "L0", "L1 +时间窗η": "L1",
              "L2 +MMAS精英": "L2", "L3 改进版": "L3"}

CN_FONTS = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]


# --------------------------------------------------------------------------
# 两个画布后端：同样的接口，一个出 SVG 字符串，一个出 PNG
# --------------------------------------------------------------------------
class SvgCanvas:
    def __init__(self, w, h, bg="#ffffff"):
        self.w, self.h = w, h
        self.parts = [f'<rect width="{w}" height="{h}" fill="{bg}"/>']

    def polyline(self, pts, color="#333", width=2, opacity=1.0):
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.parts.append(
            f'<polyline points="{p}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-opacity="{opacity}" '
            f'stroke-linejoin="round" stroke-linecap="round"/>')

    def line(self, x1, y1, x2, y2, color="#ccc", width=1, opacity=1.0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                          f'stroke="{color}" stroke-width="{width}" '
                          f'stroke-opacity="{opacity}"{d}/>')

    def circle(self, x, y, r, fill="#fff", stroke="none", sw=1, opacity=1.0, tip=""):
        t = f"<title>{html.escape(tip)}</title>" if tip else ""
        self.parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" '
                          f'stroke="{stroke}" stroke-width="{sw}" fill-opacity="{opacity}">{t}</circle>')

    def rect(self, x, y, w, h, fill="#111", stroke="none", sw=1, opacity=1.0):
        self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="{h}" '
                          f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" fill-opacity="{opacity}"/>')

    def text(self, x, y, s, size=13, color="#222", anchor="start", weight="normal"):
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="Microsoft YaHei,SimHei,sans-serif" '
                          f'font-size="{size}" fill="{color}" text-anchor="{anchor}" '
                          f'font-weight="{weight}">{html.escape(s)}</text>')

    def to_string(self) -> str:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}">' + "".join(self.parts) + "</svg>")

    def save(self, path: Path) -> None:
        path.write_text(self.to_string(), encoding="utf-8")


class PngCanvas:
    def __init__(self, w, h, bg="#ffffff"):
        from PIL import Image, ImageDraw
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w, h), bg)
        self.d = ImageDraw.Draw(self.img, "RGBA")
        self._fonts: dict = {}

    def _font(self, size):
        from PIL import ImageFont
        if size not in self._fonts:
            f = None
            for p in CN_FONTS:
                try:
                    f = ImageFont.truetype(p, size)
                    break
                except Exception:
                    continue
            self._fonts[size] = f or ImageFont.load_default()
        return self._fonts[size]

    def polyline(self, pts, color="#333", width=2, opacity=1.0):
        self.d.line([tuple(p) for p in pts], fill=color, width=int(width), joint="curve")

    def line(self, x1, y1, x2, y2, color="#ccc", width=1, opacity=1.0, dash=None):
        self.d.line([(x1, y1), (x2, y2)], fill=color, width=int(width))

    def circle(self, x, y, r, fill="#fff", stroke="none", sw=1, opacity=1.0, tip=""):
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill,
                       outline=None if stroke == "none" else stroke, width=int(sw))

    def rect(self, x, y, w, h, fill="#111", stroke="none", sw=1, opacity=1.0):
        self.d.rectangle([x, y, x + w, y + h], fill=fill,
                         outline=None if stroke == "none" else stroke, width=int(sw))

    def text(self, x, y, s, size=13, color="#222", anchor="start", weight="normal"):
        # 用 baseline 锚点（ls/ms/rs），与 SVG 的 y = 基线保持一致；
        # 若用 la（ascender）会让所有文字整体下移半个字高。
        a = {"start": "ls", "middle": "ms", "end": "rs"}.get(anchor, "ls")
        self.d.text((x, y), s, font=self._font(size), fill=color, anchor=a)

    def save(self, path: Path) -> None:
        self.img.save(path)


# --------------------------------------------------------------------------
# 画图
# --------------------------------------------------------------------------
def _scaler(inst, w, h, pad, top):
    xs = [c.x for c in inst.customers]
    ys = [c.y for c in inst.customers]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    spanx, spany = max(maxx - minx, 1e-6), max(maxy - miny, 1e-6)
    s = min((w - 2 * pad) / spanx, (h - top - pad) / spany)

    def f(c):
        return (pad + (c.x - minx) * s, h - pad - (c.y - miny) * s)
    return f


def draw_route_map(canvas, inst, routes, title, subtitle=""):
    w, h = canvas.w, canvas.h
    canvas.text(18, 26, title, size=18, weight="bold")
    if subtitle:
        canvas.text(18, 48, subtitle, size=12, color="#666")
    f = _scaler(inst, w, h, 40, 70)

    for i, route in enumerate(routes):
        color = PALETTE[i % len(PALETTE)]
        pts = [f(inst.customers[0])] + [f(inst.customers[cid]) for cid in route] + [f(inst.customers[0])]
        canvas.polyline(pts, color=color, width=2, opacity=0.9)

    for c in inst.customers[1:]:
        x, y = f(c)
        canvas.circle(x, y, 3, fill="#ffffff", stroke="#555", sw=1,
                      tip=f"客户 {c.id}｜需求 {c.demand:g}｜时间窗 [{c.ready:g},{c.due:g}]")

    dx, dy = f(inst.customers[0])
    canvas.rect(dx - 6, dy - 6, 12, 12, fill="#111")
    canvas.text(dx + 10, dy + 4, "仓库", size=12, color="#111")


def draw_convergence(canvas, histories: dict, title="收敛曲线（每代最优里程）"):
    w, h = canvas.w, canvas.h
    canvas.text(18, 26, title, size=18, weight="bold")
    left, right, top, bottom = 70, w - 30, 70, h - 50
    allv = [v for hs in histories.values() for v in hs]
    lo, hi = min(allv), max(allv)
    pad_v = max((hi - lo) * 0.1, 1.0)
    lo, hi = lo - pad_v, hi + pad_v
    n = max(len(next(iter(histories.values()))), 2)

    for k in range(5):
        y = top + (bottom - top) * k / 4
        canvas.line(left, y, right, y, color="#e8e8e8", width=1)
        canvas.text(left - 8, y + 4, f"{hi - (hi - lo) * k / 4:.0f}", size=11,
                    color="#888", anchor="end")
    canvas.line(left, top, left, bottom, color="#999")
    canvas.line(left, bottom, right, bottom, color="#999")
    canvas.text((left + right) / 2, h - 16, "迭代代数", size=12, color="#666", anchor="middle")

    for idx, (name, hist) in enumerate(histories.items()):
        color = PALETTE[idx % len(PALETTE)]
        pts = [(left + (right - left) * i / max(n - 1, 1),
                bottom - (bottom - top) * (v - lo) / (hi - lo)) for i, v in enumerate(hist)]
        canvas.polyline(pts, color=color, width=2)
        canvas.rect(left + 10 + idx * 190, 52, 14, 4, fill=color)
        canvas.text(left + 30 + idx * 190, 58, name, size=12, color="#333")


def draw_bars(canvas, items, title="消融对比（总里程，越低越好）"):
    """items: [(label, value, note)]"""
    w, h = canvas.w, canvas.h
    canvas.text(18, 26, title, size=18, weight="bold")
    left, right, top, bottom = 70, w - 30, 70, h - 60
    vmax = max(v for _, v, _ in items) * 1.18
    n = len(items)
    slot = (right - left) / n
    bw = slot * 0.55
    for it, (label, value, note) in enumerate(items):
        x = left + slot * it + (slot - bw) / 2
        bh = (bottom - top) * value / vmax
        y = bottom - bh
        color = PALETTE[it % len(PALETTE)]
        canvas.rect(x, y, bw, bh, fill=color)
        canvas.text(x + bw / 2, y - 8, f"{value:.1f}", size=13, anchor="middle", weight="bold")
        if note:
            canvas.text(x + bw / 2, y - 26, note, size=11, color="#c0392b", anchor="middle")
        canvas.text(x + bw / 2, bottom + 22, label, size=12, color="#333", anchor="middle")
    canvas.line(left, bottom, right, bottom, color="#999")


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def build_methods(iters: int) -> dict:
    base = dict(max_iter=iters, seed=1)
    return {
        "最近邻(贪心)": None,
        "L0 基线ACO": ACOConfig(**base, w_wait=0.0, w_slack=0.0,
                                 elitist=False, mmas=False, local_search=False),
        "L1 +时间窗η": ACOConfig(**base, elitist=False, mmas=False, local_search=False),
        "L2 +MMAS精英": ACOConfig(**base, local_search=False),
        "L3 改进版": ACOConfig(**base),
    }


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    iters = 50
    for a in sys.argv[1:]:
        if a.startswith("--iters"):
            iters = int(a.split("=")[1]) if "=" in a else iters

    path = Path(args[0]) if args else HERE / "data" / "solomon" / "100" / "c101.txt"
    inst = parse_solomon(path)
    name = path.stem.upper()
    RESULTS.mkdir(parents=True, exist_ok=True)

    print(f"算例 {name}（{inst.n_customers} 客户）｜迭代 {iters}")
    methods = build_methods(iters)
    outputs: dict[str, dict] = {}
    for mname, cfg in methods.items():
        if cfg is None:
            routes = nearest_neighbor(inst, allow_time_window_violation=False)
            ev = evaluate(inst, routes)
            outputs[mname] = {"routes": routes, "metrics": ev, "history": None, "seconds": 0.0}
        else:
            res = solve_aco(inst, cfg)
            outputs[mname] = {"routes": res["routes"], "metrics": res["metrics"],
                              "history": res["history"], "seconds": res["seconds"]}
        m = outputs[mname]["metrics"]
        print(f"  {mname}: 里程 {m['total_distance']:.2f}｜车辆 {m['vehicles']}"
              f"｜可行 {m['feasible']}｜{outputs[mname]['seconds']}s")

    # ---- 每个方法一张路线图（SVG + PNG）----
    svg_routes, pngs = {}, {}
    for i, mname in enumerate(methods):
        m = outputs[mname]["metrics"]
        sub = (f"里程 {m['total_distance']:.2f}｜车辆 {m['vehicles']}｜"
               f"{'可行' if m['feasible'] else '不可行'}")
        key = METHOD_KEY[mname]
        svg = SvgCanvas(720, 560)
        draw_route_map(svg, inst, outputs[mname]["routes"], f"{name} · {mname}", sub)
        svg_path = RESULTS / f"{name}_{key}_route.svg"
        svg.save(svg_path)
        svg_routes[mname] = svg.to_string()

        png = PngCanvas(720, 560)
        draw_route_map(png, inst, outputs[mname]["routes"], f"{name} · {mname}", sub)
        png_path = RESULTS / f"{name}_{key}_route.png"
        png.save(png_path)
        pngs[mname] = png_path

    # ---- 前后对比图（最近邻 vs 改进版）----
    ba = PngCanvas(1480, 580)
    first, last = list(methods)[0], list(methods)[-1]
    draw_route_map(ba, inst, outputs[first]["routes"],
                   f"优化前 · {first}", f"里程 {outputs[first]['metrics']['total_distance']:.2f}")
    # 右半张：单独画到临时画布，再粘贴上去
    tmp = PngCanvas(740, 580)
    draw_route_map(tmp, inst, outputs[last]["routes"],
                   f"优化后 · {last}", f"里程 {outputs[last]['metrics']['total_distance']:.2f}")
    ba.img.paste(tmp.img, (740, 0))
    before_after = RESULTS / f"{name}_before_after.png"
    ba.save(before_after)

    # ---- 收敛曲线 ----
    conv = {n: outputs[n]["history"] for n in methods if outputs[n]["history"]}
    svg = SvgCanvas(820, 420)
    draw_convergence(svg, conv)
    (RESULTS / f"{name}_convergence.svg").write_text(svg.to_string(), encoding="utf-8")
    png = PngCanvas(820, 420)
    draw_convergence(png, conv)
    png.save(RESULTS / f"{name}_convergence.png")

    # ---- 消融柱状图 ----
    bks = {}
    bks_file = HERE / "data" / "solomon_bks.json"
    if bks_file.exists():
        import json
        bks = json.loads(bks_file.read_text(encoding="utf-8"))
    opt = bks.get(name, {}).get("distance")
    items = []
    for mname in methods:
        v = outputs[mname]["metrics"]["total_distance"]
        note = f"gap {100 * (v - opt) / opt:.1f}%" if opt else ""
        items.append((mname.split()[0], v, note))
    svg = SvgCanvas(820, 440)
    draw_bars(svg, items)
    (RESULTS / f"{name}_ablation.svg").write_text(svg.to_string(), encoding="utf-8")
    png = PngCanvas(820, 440)
    draw_bars(png, items)
    png.save(RESULTS / f"{name}_ablation.png")

    # ---- HTML 报告页 ----
    rows = []
    for mname in methods:
        m = outputs[mname]["metrics"]
        rows.append(
            f"<tr><td>{html.escape(mname)}</td><td>{m['total_distance']:.2f}</td>"
            f"<td>{m['vehicles']}</td><td>{'✅' if m['feasible'] else '❌'}</td>"
            f"<td>{outputs[mname]['seconds']}s</td>"
            f"<td>{('gap %.1f%%' % (100 * (m['total_distance'] - opt) / opt)) if opt else '-'}</td></tr>")

    panels = []
    buttons = []
    for i, mname in enumerate(methods):
        disp = "block" if i == 0 else "none"
        panels.append(f'<div class="panel" id="p{i}" style="display:{disp}">{svg_routes[mname]}</div>')
        buttons.append(f'<button onclick="show({i})">{html.escape(mname)}</button>')

    params = ACOConfig(max_iter=iters)
    param_rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in params.__dict__.items())

    css = """
    body{font-family:Microsoft YaHei,SimHei,sans-serif;margin:0;background:#f5f6f8;color:#222}
    header{background:#1f2d3d;color:#fff;padding:18px 26px}
    header h1{margin:0;font-size:20px;font-weight:600}
    header p{margin:6px 0 0;color:#9fb3c8;font-size:13px}
    .wrap{max-width:1000px;margin:20px auto;padding:0 16px}
    .card{background:#fff;border-radius:10px;padding:18px 20px;margin-bottom:18px;
          box-shadow:0 1px 3px rgba(0,0,0,.08)}
    .card h2{font-size:16px;margin:0 0 12px;color:#1f2d3d}
    table{border-collapse:collapse;width:100%;font-size:14px}
    th,td{border-bottom:1px solid #eee;padding:8px 10px;text-align:left}
    th{background:#fafbfc;color:#555;font-weight:600}
    button{margin:0 8px 12px 0;padding:7px 14px;border:1px solid #d0d7de;background:#fff;
           border-radius:6px;cursor:pointer;font-size:13px}
    button:hover{background:#f0f6ff;border-color:#7aa7ff}
    img{max-width:100%}
    .hint{color:#666;font-size:13px;line-height:1.7}
    """
    html_doc = (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{name} 配送路径优化结果</title><style>{css}</style></head><body>"
        "<header><h1>基于改进蚁群算法的配送路径优化 · 实验结果</h1>"
        f"<p>算例 {name}｜客户 {inst.n_customers} 个｜载重上限 {inst.capacity:g}｜"
        f"迭代 {iters} 代｜已知最优 {opt if opt else '未知'}</p></header><div class='wrap'>"
        "<div class='card'><h2>各方法指标</h2><table><tr><th>方法</th><th>总里程</th>"
        "<th>车辆数</th><th>可行</th><th>用时</th><th>与最优差距</th></tr>"
        + "".join(rows) + "</table>"
        "<p class='hint'>蚁群是随机算法，这里只跑了一次；正式实验每个算例每方法要跑 ≥10 次报均值±标准差。</p></div>"
        "<div class='card'><h2>路线图（点按钮切换方法）</h2>"
        + "".join(buttons) + "".join(panels) + "</div>"
        "<div class='card'><h2>收敛曲线</h2><img src='" + f"{name}_convergence.svg" + "'></div>"
        "<div class='card'><h2>消融对比</h2><img src='" + f"{name}_ablation.svg" + "'></div>"
        "<div class='card'><h2>算法参数</h2><table><tr><th>参数</th><th>取值</th></tr>"
        + param_rows + "</table></div>"
        "<div class='card'><h2>复现命令</h2><p class='hint'>"
        f"python run_aco.py data/solomon/{inst.n_customers}/{path.name} 10<br>"
        f"python run_experiments.py {inst.n_customers} 10 {path.stem}<br>"
        f"python viz.py data/solomon/{inst.n_customers}/{path.name}</p></div>"
        "</div><script>function show(i){document.querySelectorAll('.panel').forEach("
        "(e,k)=>e.style.display=(k===i?'block':'none'));}</script></body></html>")

    html_path = RESULTS / f"{name}_report.html"
    html_path.write_text(html_doc, encoding="utf-8")

    print("\n产出：")
    print("  ", html_path.relative_to(HERE), "  ← 双击打开（路线图可切换）")
    print("  ", before_after.relative_to(HERE), " ← 优化前后对比图")
    print("  ", (RESULTS / f"{name}_convergence.png").relative_to(HERE))
    print("  ", (RESULTS / f"{name}_ablation.png").relative_to(HERE))


if __name__ == "__main__":
    main()
