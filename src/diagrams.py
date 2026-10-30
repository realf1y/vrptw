# -*- coding: utf-8 -*-
"""生成报告用图：E-R 图 / 用例图 / 界面原型（SVG + PNG，零绘图库依赖）

用法::

    python diagrams.py            # 输出到 results/diagrams/
"""
from __future__ import annotations

from pathlib import Path

from viz import PALETTE, PngCanvas, SvgCanvas

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "diagrams"


# --------------------------------------------------------------------------
# 通用小工具：椭圆（SvgCanvas / PngCanvas 都支持）
# --------------------------------------------------------------------------
def ellipse(cv, cx, cy, rx, ry, fill="#ffffff", stroke="#333333", sw=1):
    if hasattr(cv, "d"):                       # PNG 后端
        cv.d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill, outline=stroke,
                     width=max(1, int(round(sw))))
    else:                                      # SVG 后端
        cv.parts.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" '
                        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def entity(cv, x, y, w, title, fields, color="#1f77b4"):
    head = 36
    line_h = 20
    h = head + 14 + line_h * len(fields) + 12
    cv.rect(x, y, w, head, fill=color)
    cv.text(x + 12, y + 24, title, size=14, color="#ffffff", weight="bold")
    cv.rect(x, y + head, w, h - head, fill="#ffffff", stroke=color, sw=1.5)
    for i, f in enumerate(fields):
        cv.text(x + 12, y + head + 24 + i * line_h, f, size=11, color="#333333")
    return x + w, y + h


def stub(cv, x, y, scale=1.0, label="实验人员"):
    """火柴人"""
    s = scale
    cv.circle(x, y - 46 * s, 13 * s, fill="#ffffff", stroke="#333333", sw=2)
    cv.line(x, y - 33 * s, x, y + 8 * s, color="#333333", width=2)
    cv.line(x - 22 * s, y - 16 * s, x + 22 * s, y - 16 * s, color="#333333", width=2)
    cv.line(x, y + 8 * s, x - 16 * s, y + 40 * s, color="#333333", width=2)
    cv.line(x, y + 8 * s, x + 16 * s, y + 40 * s, color="#333333", width=2)
    cv.text(x, y + 62 * s, label, size=13, anchor="middle", color="#222222")


# --------------------------------------------------------------------------
# 1) E-R 图
# --------------------------------------------------------------------------
def draw_er(cv):
    cv.text(18, 30, "系统数据库 E-R 图（4 个实体 / 3 组 1:N 关系）", size=19, weight="bold")
    cv.text(18, 54, "对应 report 第三章「数据库设计」：概念设计（E-R）→ 逻辑设计（关系模式）→ 物理设计（MySQL 表）",
            size=11, color="#777777")

    entity(cv, 50, 110, 260, "instance 算例", [
        "id  INT  PK", "name  VARCHAR(64) UQ", "size  VARCHAR(16)",
        "n_customers  INT", "capacity  DOUBLE", "vehicle_count  INT",
        "speed  DOUBLE", "total_demand  DOUBLE",
    ], color="#1f77b4")

    entity(cv, 50, 400, 260, "scene 场景", [
        "id  INT  PK", "name  VARCHAR(64) UQ",
        "config_json  TEXT", "note  VARCHAR(255)",
    ], color="#2ca02c")

    entity(cv, 470, 210, 300, "experiment 实验记录", [
        "id  INT  PK", "instance_id  INT  FK", "scene_id  INT  FK",
        "method  VARCHAR(64)", "run_index  INT", "seed  INT",
        "distance  DOUBLE", "vehicles  INT", "feasible  TINYINT",
        "on_time_rate  DOUBLE", "load_rate  DOUBLE", "seconds  DOUBLE",
    ], color="#d62728")

    entity(cv, 900, 250, 250, "solution 方案路线", [
        "id  INT  PK", "experiment_id  INT  FK", "route_index  INT",
        "customers  TEXT", "stop_count  INT", "route_length  DOUBLE",
        "route_load  DOUBLE",
    ], color="#9467bd")

    # 关系线
    cv.line(310, 190, 470, 300, color="#555555", width=2)
    cv.text(318, 182, "1", size=13, color="#c0392b", weight="bold")
    cv.text(455, 292, "N", size=13, color="#c0392b", weight="bold")

    cv.line(310, 470, 470, 470, color="#555555", width=2)
    cv.text(318, 462, "1", size=13, color="#c0392b", weight="bold")
    cv.text(448, 462, "N", size=13, color="#c0392b", weight="bold")

    cv.line(770, 350, 900, 350, color="#555555", width=2)
    cv.text(778, 342, "1", size=13, color="#c0392b", weight="bold")
    cv.text(882, 342, "N", size=13, color="#c0392b", weight="bold")

    cv.text(50, 730, "说明：instance 1—N experiment（一个算例可跑多次实验）；scene 1—N experiment（同一实验可在不同场景下重复）；"
                     "experiment 1—N solution（一次实验产出一组路线）。",
            size=11, color="#666666")


# --------------------------------------------------------------------------
# 2) 用例图
# --------------------------------------------------------------------------
def draw_usecase(cv):
    cv.text(18, 30, "系统用例图", size=19, weight="bold")
    x0, y0, w, h = 300, 80, 520, 640
    cv.rect(x0, y0, w, h, fill="#fbfdff", stroke="#7f8c8d", sw=1.5)
    cv.text(x0 + w / 2, y0 + 26, "配送路径优化系统", size=15, anchor="middle", color="#2c3e50", weight="bold")

    stub(cv, 130, 330, 1.3, "实验人员")

    cases = [
        ("管理算例数据", 160), ("配置业务场景", 225), ("运行优化算法", 290),
        ("查看路线方案", 355), ("方案对比分析", 420), ("导出实验报表", 485),
        ("维护数据库", 550),
    ]
    centers = []
    for name, cy in cases:
        cx = x0 + w / 2
        ellipse(cv, cx, cy, 120, 26, fill="#ffffff", stroke="#2980b9", sw=1.6)
        cv.text(cx, cy + 4, name, size=12, anchor="middle", color="#1b4f72")
        centers.append((cx, cy))
        cv.line(175, 330, cx - 120, cy, color="#95a5a6", width=1.2)

    # include 关系（虚线）
    cv.line(centers[2][0] + 90, centers[2][1] + 18, 640, 600, color="#8e44ad", width=1.4, dash="5,4")
    ellipse(cv, 640, 600, 92, 22, fill="#fdf6ff", stroke="#8e44ad", sw=1.4)
    cv.text(640, 604, "校验载重与时间窗", size=11, anchor="middle", color="#6c3483")
    cv.text(700, 566, "«include»", size=10, color="#8e44ad")

    cv.line(centers[4][0] - 60, centers[4][1] + 20, 700, 660, color="#8e44ad", width=1.4, dash="5,4")
    ellipse(cv, 700, 660, 78, 20, fill="#fdf6ff", stroke="#8e44ad", sw=1.4)
    cv.text(700, 664, "统计 KPI 指标", size=11, anchor="middle", color="#6c3483")
    cv.text(742, 640, "«include»", size=10, color="#8e44ad")

    cv.text(18, 748, "说明：实验人员通过 7 个用例完成「选算例 → 配场景 → 跑算法 → 看路线 → 对比方案 → 出报表」的闭环；"
                     "「运行优化算法」与「方案对比分析」分别包含约束校验与 KPI 统计。",
            size=11, color="#666666")


# --------------------------------------------------------------------------
# 3) 界面原型
# --------------------------------------------------------------------------
def _panel(cv, x, y, w, h, title):
    cv.rect(x, y, w, h, fill="#ffffff", stroke="#c8d0d8", sw=1.5)
    cv.rect(x, y, w, 34, fill="#34495e")
    cv.text(x + 12, y + 22, title, size=13, color="#ffffff", weight="bold")


def _placeholder(cv, x, y, w, h, label):
    cv.rect(x, y, w, h, fill="#f7f9fb", stroke="#b0bec5", sw=1)
    cv.line(x, y, x + w, y + h, color="#dfe6e9", width=1)
    cv.line(x + w, y, x, y + h, color="#dfe6e9", width=1)
    cv.text(x + w / 2, y + h / 2, label, size=12, anchor="middle", color="#78909c")


def draw_ui(cv):
    cv.text(18, 30, "系统界面原型（三屏）", size=19, weight="bold")
    top, ph = 60, 650

    # --- 屏 1：实验配置 ---
    _panel(cv, 30, top, 430, ph, "① 实验配置")
    cv.text(48, top + 62, "算例", size=12, color="#555")
    cv.rect(120, top + 48, 320, 28, fill="#f5f7fa", stroke="#b0bec5")
    cv.text(132, top + 67, "c101（100 客户 · 25 车 · 载重 200）", size=11, color="#333")

    cv.text(48, top + 112, "场景", size=12, color="#555")
    for i, name in enumerate(["标准场景（硬时间窗）", "校园配送（软时间窗 λ=25）", "雨天慢速（车速0.8）"]):
        yy = top + 100 + i * 30
        cv.rect(120, yy, 14, 14, fill="#ffffff" if i else "#2980b9", stroke="#7f8c8d")
        cv.text(144, yy + 12, name, size=11, color="#333")

    cv.text(48, top + 206, "算法参数", size=12, color="#555")
    params = [("α 信息素", "1.0"), ("β 启发式", "3.0"), ("ρ 挥发率", "0.10"),
              ("蚂蚁数", "20"), ("迭代代数", "40")]
    for i, (k, v) in enumerate(params):
        yy = top + 218 + i * 32
        cv.text(60, yy + 14, k, size=11, color="#555")
        cv.rect(170, yy, 90, 24, fill="#f5f7fa", stroke="#b0bec5")
        cv.text(180, yy + 17, v, size=11, color="#333")

    cv.rect(60, top + 400, 360, 44, fill="#2980b9")
    cv.text(240, top + 428, "开始优化", size=14, color="#ffffff", anchor="middle", weight="bold")
    cv.text(60, top + 476, "进度：构造解 → 局部搜索 → 更新信息素 … 40/40 代", size=11, color="#666")
    cv.rect(60, top + 490, 360, 10, fill="#e8eef3", stroke="#cfd8dc")
    cv.rect(60, top + 490, 300, 10, fill="#27ae60")

    # --- 屏 2：路线对比 ---
    _panel(cv, 490, top, 430, ph, "② 路线对比")
    _placeholder(cv, 510, top + 60, 190, 240, "优化前·最近邻")
    _placeholder(cv, 710, top + 60, 190, 240, "优化后·改进蚁群")
    cv.text(560, top + 322, "1870.73 / 21 车", size=11, anchor="middle", color="#c0392b")
    cv.text(805, top + 322, "829.01 / 10 车", size=11, anchor="middle", color="#27ae60")

    kpis = [("总里程", "829.01", "-55.7%"), ("车辆数", "10", "-11"), ("准时率", "100%", "+0.0pp")]
    for i, (k, v, d) in enumerate(kpis):
        xx = 510 + i * 138
        cv.rect(xx, top + 350, 126, 76, fill="#f8fbfd", stroke="#d6e3ee")
        cv.text(xx + 10, top + 372, k, size=11, color="#7f8c8d")
        cv.text(xx + 10, top + 398, v, size=17, color="#1f2d3d", weight="bold")
        cv.text(xx + 10, top + 418, d, size=10, color="#27ae60")

    cv.text(510, top + 462, "路线配色 = 车辆编号；点击客户点可看时间窗与需求。", size=11, color="#666")
    _placeholder(cv, 510, top + 480, 390, 140, "收敛曲线（每代最优里程）")

    # --- 屏 3：实验报表 ---
    _panel(cv, 950, top, 430, ph, "③ 实验报表")
    cards = [("平均里程", "1424.49", "gap 17.6%"), ("平均车辆", "11.7", ""),
             ("准时率", "99.8%", ""), ("平均耗时", "41.1 s", "")]
    for i, (k, v, d) in enumerate(cards):
        xx = 970 + (i % 2) * 200
        yy = top + 56 + (i // 2) * 86
        cv.rect(xx, yy, 186, 74, fill="#f8fbfd", stroke="#d6e3ee")
        cv.text(xx + 10, yy + 22, k, size=11, color="#7f8c8d")
        cv.text(xx + 10, yy + 48, v, size=18, color="#1f2d3d", weight="bold")
        cv.text(xx + 10, yy + 66, d, size=10, color="#c0392b")

    cv.text(970, top + 250, "逐算例对比", size=12, color="#34495e", weight="bold")
    rows, cols = 6, 5
    cw, ch = 74, 30
    for r in range(rows):
        for c in range(cols):
            xx, yy = 970 + c * cw, top + 264 + r * ch
            cv.rect(xx, yy, cw, ch, fill="#eef4f8" if r == 0 else "#ffffff", stroke="#d6e3ee")
            if r == 0:
                label = ["算例", "L0", "L1", "L2", "L3"][c]
                cv.text(xx + 8, yy + 20, label, size=10, color="#2c3e50", weight="bold")
            elif c == 0:
                cv.text(xx + 8, yy + 20, ["C101", "C201", "R101", "R201", "RC101"][r - 1], size=10, color="#333")
            else:
                cv.text(xx + 8, yy + 20, "—", size=10, color="#95a5a6")

    cv.rect(970, top + 470, 186, 38, fill="#34495e")
    cv.text(1063, top + 494, "导出 Markdown / CSV / HTML", size=10, color="#ffffff", anchor="middle")
    cv.rect(1170, top + 470, 186, 38, fill="#ffffff", stroke="#34495e")
    cv.text(1263, top + 494, "刷新数据（读数据库）", size=10, color="#34495e", anchor="middle")


def draw_arch(cv):
    """四层架构图：展示层 / 服务层 / 算法层 / 数据层"""
    cv.text(18, 30, "系统总体架构（四层）", size=19, weight="bold")
    cv.text(18, 54, "上层只依赖下层的接口，换算法或换数据库不影响其他层", size=11, color="#777777")

    layers = [
        ("展示层", "#2980b9", ["路线图", "收敛曲线", "消融对比", "KPI 报表"]),
        ("服务层", "#16a085", ["实验调度", "指标计算", "报表导出", "场景管理"]),
        ("算法层", "#8e44ad", ["构造可行解", "局部搜索", "信息素更新", "约束校验"]),
        ("数据层", "#d35400", ["算例解析", "距离矩阵", "SQLite", "MySQL"]),
    ]
    top, band_h, gap = 90, 108, 28
    for i, (name, color, comps) in enumerate(layers):
        y = top + i * (band_h + gap)
        cv.rect(40, y, 150, band_h, fill=color)
        # 竖排文字用单字逐行画
        for k, ch in enumerate(name):
            cv.text(115, y + 40 + k * 24, ch, size=15, color="#ffffff",
                    anchor="middle", weight="bold")
        cv.rect(190, y, 960, band_h, fill="#fbfdff", stroke=color, sw=1.4)
        bw = 205
        for j, comp in enumerate(comps):
            x = 215 + j * (bw + 22)
            cv.rect(x, y + 28, bw, 52, fill="#ffffff", stroke=color, sw=1.2)
            cv.text(x + bw / 2, y + 60, comp, size=12, anchor="middle", color="#2c3e50")

    # 层间箭头（双向）
    for i in range(len(layers) - 1):
        y1 = top + i * (band_h + gap) + band_h
        y2 = y1 + gap
        cv.line(660, y1 + 3, 660, y2 - 3, color="#7f8c8d", width=2)
        cv.line(660, y1 + 3, 654, y1 + 9, color="#7f8c8d", width=2)
        cv.line(660, y1 + 3, 666, y1 + 9, color="#7f8c8d", width=2)
        cv.line(660, y2 - 3, 654, y2 - 9, color="#7f8c8d", width=2)
        cv.line(660, y2 - 3, 666, y2 - 9, color="#7f8c8d", width=2)

    cv.text(40, 660, "数据流：算例 → 距离矩阵 → 蚁群构造解 → 局部搜索优化 → 指标计算 → 落库 → 图表与报表",
            size=11, color="#555555")
    cv.text(40, 684, "模块映射：M1 数据层、M2 算法层、M3 展示层、M4 服务层、M5 场景管理、M6 报表导出",
            size=11, color="#555555")


def box_shape(cv, cx, cy, w, h, text, fill="#ffffff", stroke="#2980b9", size=12):
    cv.rect(cx - w / 2, cy - h / 2, w, h, fill=fill, stroke=stroke, sw=1.4)
    cv.text(cx, cy + 5, text, size=size, anchor="middle", color="#2c3e50")


def diamond(cv, cx, cy, w, h, text, fill="#fff8e1", stroke="#e67e22"):
    pts = [(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)]
    if hasattr(cv, "d"):
        cv.d.polygon(pts, fill=fill, outline=stroke)
    else:
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        cv.parts.append(f'<polygon points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
    cv.text(cx, cy + 4, text, size=11, anchor="middle", color="#8a4b08")


def arrow(cv, pts, color="#555555"):
    """折线箭头（最后一段带箭头尖）"""
    import math
    for i in range(len(pts) - 1):
        cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], color=color, width=1.6)
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    ang = math.atan2(y2 - y1, x2 - x1)
    for s in (0.42, -0.42):
        cv.line(x2, y2, x2 - 10 * math.cos(ang - s), y2 - 10 * math.sin(ang - s),
                color=color, width=1.6)


def _start_end(cv, cx, cy, label="开始"):
    ellipse(cv, cx, cy, 26, 16, fill="#dfe6e9", stroke="#7f8c8d", sw=1.4)
    cv.text(cx, cy + 4, label, size=11, anchor="middle", color="#2c3e50")


def draw_activity_run(cv):
    cv.text(18, 30, "图 2-2  运行优化算法活动图", size=18, weight="bold")
    _start_end(cv, 500, 70)
    box_shape(cv, 500, 130, 170, 42, "选择算例")
    box_shape(cv, 500, 205, 190, 42, "校验算例格式")
    diamond(cv, 500, 285, 200, 76, "格式合法？")
    box_shape(cv, 790, 285, 170, 42, "提示字段缺失", fill="#fdecea", stroke="#c0392b", size=11)
    _start_end(cv, 790, 355, "结束")
    box_shape(cv, 500, 385, 190, 42, "构建距离矩阵")
    box_shape(cv, 500, 460, 190, 42, "构造初始解")
    diamond(cv, 500, 550, 230, 80, "达到迭代上限？")
    box_shape(cv, 500, 660, 330, 54,
              "构造解 → 局部搜索 → 评价 → 更新信息素", size=11)
    box_shape(cv, 800, 550, 210, 42, "输出最优路线与指标", size=11)
    box_shape(cv, 800, 630, 210, 42, "写入实验记录", size=11)
    _start_end(cv, 800, 700, "结束")

    for a, b in [((500, 86), (500, 109)), ((500, 151), (500, 184)),
                 ((500, 226), (500, 247))]:
        arrow(cv, [a, b])
    arrow(cv, [(600, 285), (705, 285)], color="#c0392b")   # 否
    cv.text(640, 275, "否", size=11, color="#c0392b")
    arrow(cv, [(790, 306), (790, 339)], color="#c0392b")
    arrow(cv, [(500, 323), (500, 364)])                    # 是
    cv.text(512, 350, "是", size=11, color="#27ae60")
    arrow(cv, [(500, 406), (500, 439)])
    arrow(cv, [(500, 481), (500, 510)])
    arrow(cv, [(500, 590), (500, 633)])                    # 否 → 迭代体
    cv.text(512, 618, "否", size=11, color="#c0392b")
    arrow(cv, [(335, 660), (290, 660), (290, 550), (385, 550)])   # 回环
    cv.text(300, 600, "继续迭代", size=10, color="#555")
    arrow(cv, [(615, 550), (695, 550)])                    # 是 → 输出
    cv.text(650, 540, "是", size=11, color="#27ae60")
    arrow(cv, [(800, 571), (800, 609)])
    arrow(cv, [(800, 651), (800, 684)])


def draw_activity_scene(cv):
    cv.text(18, 30, "图 2-3  配置业务场景活动图", size=18, weight="bold")
    _start_end(cv, 420, 80)
    box_shape(cv, 420, 145, 180, 42, "新建场景")
    box_shape(cv, 420, 230, 380, 56,
              "填写约束：载重 / 车速 / 时间窗模式 / 优先级", size=11)
    diamond(cv, 420, 330, 200, 76, "取值合法？")
    box_shape(cv, 720, 330, 160, 42, "提示并返回修改", fill="#fdecea", stroke="#c0392b", size=11)
    box_shape(cv, 420, 430, 180, 42, "保存为 JSON")
    _start_end(cv, 420, 500, "结束")

    arrow(cv, [(420, 96), (420, 124)])
    arrow(cv, [(420, 166), (420, 202)])
    arrow(cv, [(420, 258), (420, 292)])
    arrow(cv, [(520, 330), (640, 330)], color="#c0392b")
    cv.text(570, 320, "否", size=11, color="#c0392b")
    arrow(cv, [(720, 309), (720, 230), (615, 230)], color="#c0392b")
    arrow(cv, [(420, 368), (420, 409)])
    cv.text(432, 395, "是", size=11, color="#27ae60")
    arrow(cv, [(420, 451), (420, 484)])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("er", (1300, 780), draw_er, "E-R 图"),
        ("usecase", (1100, 780), draw_usecase, "用例图"),
        ("ui", (1420, 760), draw_ui, "界面原型"),
        ("arch", (1200, 720), draw_arch, "总体架构图"),
        ("act_run", (1020, 740), draw_activity_run, "图2-2 运行算法活动图"),
        ("act_scene", (900, 560), draw_activity_scene, "图2-3 配置场景活动图"),
    ]
    for name, (w, h), fn, label in jobs:
        svg = SvgCanvas(w, h)
        fn(svg)
        svg.save(OUT / f"{name}.svg")
        png = PngCanvas(w, h)
        fn(png)
        png.save(OUT / f"{name}.png")
        print(f"[OK] {label}: {name}.svg / {name}.png  ({w}x{h})")
    print(f"\n输出目录：{OUT}")


if __name__ == "__main__":
    main()
