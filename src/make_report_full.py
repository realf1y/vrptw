# -*- coding: utf-8 -*-
"""生成报告正文：第一至第四章（每人一份，1–4 章内容相同）

产出：D:\\vrptw\\docs\\报告-前四章-任绪锋-2318140115.docx
      D:\\vrptw\\docs\\报告-前四章-苍韵同-2318140111.docx

说明：第五至第七章按各自模块不同，本文件只到第四章，末尾附五~七章提纲。
      插图取自 results/diagrams/（E-R / 用例 / 架构 / 界面原型）。
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
IMG = HERE / "results" / "diagrams"
OUT = Path("D:/vrptw/docs")

TOPIC = "基于改进蚁群算法的带时间窗配送路径优化系统设计与实现"
PEOPLE = {"任绪锋": "2318140115", "苍韵同": "2318140111"}


# --------------------------------------------------------------------------
# 排版工具
# --------------------------------------------------------------------------
def style_run(run, size=12, bold=False, cn="宋体", color=None):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), cn)
    if color:
        run.font.color.rgb = color


def p(doc, text, size=12, bold=False, indent=True, align=None, cn="宋体",
      space_after=6, color=None):
    par = doc.add_paragraph()
    pf = par.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(22)
    pf.space_after = Pt(space_after)
    if indent:
        pf.first_line_indent = Pt(24)
    if align is not None:
        par.alignment = align
    style_run(par.add_run(text), size=size, bold=bold, cn=cn, color=color)
    return par


def h(doc, text, level=1):
    head = doc.add_heading(level=level)
    style_run(head.add_run(text), size={1: 16, 2: 14, 3: 12}.get(level, 12),
              bold=True, cn="黑体")


def figure(doc, name: str, caption: str, width_cm: float = 15.0):
    path = IMG / name
    if not path.exists():
        p(doc, f"（缺图：{name}）", indent=False, color=RGBColor(0xCC, 0x00, 0x00))
        return
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before = Pt(6)
    par.add_run().add_picture(str(path), width=Cm(width_cm))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    style_run(cap.add_run(caption), size=10.5)


def table(doc, headers: list[str], rows: list[list[str]], widths: list[float] | None = None,
          caption: str = ""):
    if caption:
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        style_run(cap.add_run(caption), size=10.5)
    tb = doc.add_table(rows=1, cols=len(headers))
    tb.style = "Table Grid"
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = tb.rows[0].cells
    for i, t in enumerate(headers):
        hdr[i].text = ""
        style_run(hdr[i].paragraphs[0].add_run(t), size=10.5, bold=True, cn="黑体")
    for row in rows:
        cells = tb.add_row().cells
        for i, t in enumerate(row):
            cells[i].text = ""
            style_run(cells[i].paragraphs[0].add_run(str(t)), size=10)
    if widths:
        for i, w in enumerate(widths):
            for row in tb.rows:
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return tb


# --------------------------------------------------------------------------
# 正文
# --------------------------------------------------------------------------
def build(name: str, sid: str, ch5_fn=None, doc=None, ch67_fn=None, appx_fn=None) -> Document:
    fresh = doc is None
    if fresh:
        doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    # ---------------- 封面（仅在新建文档时画）----------------
    if fresh:
        p(doc, "《软件工程系统实训》综合报告", size=22, bold=True, indent=False,
          align=WD_ALIGN_PARAGRAPH.CENTER, cn="黑体", space_after=24)
        for k, v in [
            ("题　　目：", TOPIC),
            ("起讫日期：", "2026 年 9 月 21 日 至 2026 年 12 月 20 日"),
            ("学生姓名：", name),
            ("学　　号：", sid),
            ("所在院系：", "轨道智能工程学院"),
            ("专业班级：", "【待填】"),
            ("指导教师：", "【待填】"),
        ]:
            p(doc, f"{k}{v}", size=14, indent=False, space_after=10)
        doc.add_page_break()

    # ================= 第一章 =================
    h(doc, "第一章  系统概述", 1)

    h(doc, "1.1  应用领域调研", 2)
    p(doc, "配送路径优化是物流与供应链管理的核心问题之一。随着电子商务与即时配送的发展，"
           "企业需要在有限的车辆、载重与时间窗约束下，以尽可能低的成本完成多点配送。"
           "本节选取三类代表性系统进行对比分析。")
    p(doc, "第一类是商用路线规划平台，以 Route4Me（https://www.route4me.com/）为代表。该类系统面向中小企业提供多点路径优化、"
           "实时车辆跟踪与司机端应用，优点是开箱即用、上手快；不足是算法不公开、按订阅收费，"
           "难以用于算法层面的对比实验[1]。")
    p(doc, "第二类是开源运筹优化库，以 Google OR-Tools（https://developers.google.com/optimization/routing）为代表。它提供车辆路径问题的求解器与约束编程能力，"
           "成熟且高效；不足是需要较强的建模与编程能力，实验参数、指标统计与结果呈现都需要另行搭建。")
    p(doc, "第三类是国内即时配送平台的调度系统。这类系统面向海量订单做实时分配与路径规划，"
           "实时性与规模优势明显，但系统不对外开放，算法细节与数据均不可复现。")
    p(doc, "三者的相似之处在于：解决的都是“多客户、带约束的车辆路线安排”问题，目标都是降低总里程与成本、"
           "提高准时率。不同之处在于本系统的定位是教学与实验：算法完全自主实现、参数可配置、"
           "指标可复现、结果可导出（CSV / HTML），不追求实时与超大规模，但要求每一步计算可解释、"
           "不同方法之间可对比。这也决定了本系统在功能取舍上更重视“可实验性”而非“商业完备性”。")

    h(doc, "1.2  选题合理性", 2)
    p(doc, "带时间窗的车辆路径问题（Vehicle Routing Problem with Time Windows，VRPTW）属于 NP-hard 问题。"
           "当客户数量为 n 时，可能的访问序列组合随 n 呈指数增长，精确算法难以在可接受时间内给出最优解，"
           "因此工程上普遍采用启发式或元启发式算法求近似最优解。")
    p(doc, "从实际业务看，配送并非“把货送到就行”：客户对送达时间有明确要求，车辆有载重上限，"
           "司机有工作时长限制。多个约束叠加后，人工排线高度依赖经验，客户数量一多便难以兼顾里程与准时率，"
           "经常出现“车派多了成本高、车派少了送不完”的两难。")
    p(doc, "从课程角度看，该题目同时覆盖问题建模、算法设计、工程实现与实验分析四个环节，"
           "与软件工程实训的要求吻合；蚁群算法本身具备明确的改进空间（启发式因子、信息素策略、局部搜索），"
           "便于设计消融实验，用数据说明每一项改进的作用。")

    h(doc, "1.3  系统概述", 2)
    p(doc, "本系统以改进蚁群算法为核心，输入为标准 Solomon 算例或自定义业务场景，"
           "输出为各车辆的行驶路线及对应指标（总里程、车辆数、准时率、装载率、求解耗时）。")
    p(doc, "系统划分为十四个功能模块。六个基础模块：算例与数据管理（读取、校验与导出算例、构建距离矩阵）、"
           "算法引擎（构造可行解、局部搜索、信息素更新）、路线可视化（路线图与优化前后对比）、"
           "实验管理与统计（批量实验、指标汇总）、约束与场景配置（载重、车速、硬/软时间窗、多车场、多车型、客户优先级）、"
           "方案对比与报表（KPI 汇总与 Markdown / CSV / HTML / Excel 多格式导出）。"
           "六个扩展模块：动态重优化（插单后局部重排）、运营 KPI 看板、"
           "成本/碳排多目标优化、成本碳排对比页、订单 Excel 导入、用户与项目空间、"
           "任务监控（后台队列）、全文排版与查重自检。")
    p(doc, "技术选型上，算法与数据处理仅使用 Python 标准库实现，数据库访问使用 pymysql 驱动 MySQL 9.5，"
           "同时兼容 SQLite 以便零配置运行；图形输出采用标准库生成 SVG、Pillow 输出 PNG；"
           "报表支持 Markdown、CSV 与 HTML 三种格式。")
    p(doc, "系统的能力边界为：支持单仓库与多车场（多个仓库坐标）、多车型（不同载重与固定成本）、"
           "100 客户规模、硬时间窗与软时间窗两种模式；支持动态插单与局部重排（单次插单重排 0.3–0.7 秒，"
           "不需要全量重算），提供运营 KPI 看板，并支持成本/碳排的加权多目标求解与对比页"
           "（成本优先 / 均衡 / 低碳优先三组权重）。暂不支持分钟级的连续流式调度与车辆在线位置追踪，"
           "这两项列入后续工作。")

    # ================= 第二章 =================
    doc.add_page_break()
    h(doc, "第二章  可行性研究及需求分析", 1)

    h(doc, "2.1  可行性研究", 2)
    p(doc, "技术可行性。算法与数据处理只依赖 Python 标准库，数据库驱动 pymysql 为纯 Python 包，"
           "无需编译环境。实测在 i9-13900HX / 64 GB 内存的笔记本上，100 客户算例单次求解耗时 6–40 秒"
           "（随迭代代数与是否启用局部搜索变化），400 次批量实验在 16 进程并行下约 8 分钟完成，"
           "普通开发机即可支撑全部实验。")
    p(doc, "经济可行性。系统全部使用开源软件与公开基准算例，无软件许可费用；"
           "开发、测试与实验均在同一台笔记本上完成，不产生额外硬件与云服务开支。")
    p(doc, "操作可行性。系统提供命令行入口与一键脚本（单个算例求解、批量实验、可视化、报表生成），"
           "并输出可直接双击打开的 HTML 报表页；实验人员无需编程即可查看路线图与指标，"
           "需要改参数时修改配置文件或命令行参数即可。")
    p(doc, "法律与合规可行性。实验使用 Solomon 公开基准算例，不包含任何真实客户信息；"
           "若后续接入真实业务数据，需先做脱敏处理，并限制数据库账号权限（系统已采用仅授予单库权限的业务账号）。")

    h(doc, "2.2  系统需求概述", 2)
    p(doc, "系统的直接参与者为实验人员，外部依赖为算例文件与 MySQL 数据库。"
           "实验人员的核心诉求是：选一个算例、设定业务场景与算法参数、跑出结果、看清路线、"
           "比较不同方法、把结果整理成可提交的材料。")
    p(doc, "据此归纳出七个用例：管理算例数据、配置业务场景、运行优化算法、查看路线方案、"
           "方案对比分析、导出实验报表、维护数据库。系统总用例图如图 2-1 所示。")
    figure(doc, "usecase.png", "图 2-1  系统用例图", 14.5)
    p(doc, "其中“运行优化算法”包含“校验载重与时间窗”，“方案对比分析”包含“统计 KPI 指标”，"
           "这两个包含关系体现了系统的核心约束：任何方案都必须先满足可行性，再谈优劣。")

    h(doc, "2.3  运行优化算法用例分析", 2)
    h(doc, "2.3.1  用例描述", 3)
    table(doc,
          ["项目", "内容"],
          [["用例名称", "运行优化算法"],
           ["参与者", "实验人员"],
           ["前置条件", "算例文件存在且格式合法；场景参数已配置；数据库可连接（可选）"],
           ["主流程", "1. 选择算例；2. 读取场景参数；3. 解析算例并构建距离矩阵；"
                    "4. 构造初始可行解；5. 迭代：构造解 → 局部搜索 → 评价 → 更新信息素；"
                    "6. 输出最优路线与指标；7. 写入实验记录"],
           ["异常流程", "算例格式错误 → 提示字段缺失并终止；载重上限过小导致无可行解 → 返回违反量最小的解并标注不可行"],
           ["后置条件", "生成一条实验记录（方法、种子、里程、车辆数、准时率、装载率、耗时）"]],
          widths=[4.0, 12.0], caption="表 2-1  运行优化算法用例描述")
    h(doc, "2.3.2  用例对应的活动图", 3)
    p(doc, "该用例的活动流程为：选择算例 → 校验数据合法性（不合法则报错退出）→ 构建距离矩阵 → "
           "构造初始解 → 判断是否达到迭代上限（未达到则继续迭代）→ 输出最优解与指标 → 落库。"
           "活动图见图 2-2。")
    figure(doc, "act_run.png", "图 2-2  运行优化算法活动图", 14.0)

    h(doc, "2.4  配置业务场景用例分析", 2)
    h(doc, "2.4.1  用例描述", 3)
    table(doc,
          ["项目", "内容"],
          [["用例名称", "配置业务场景"],
           ["参与者", "实验人员"],
           ["前置条件", "已知业务约束（载重、车型、时效要求）"],
           ["主流程", "1. 新建场景；2. 设置载重与车辆数上限；3. 设置车速；"
                    "4. 选择时间窗模式（硬/软）并设置惩罚系数；5. 设置客户优先级；"
                    "6. 校验取值范围；7. 保存为 JSON"],
           ["异常流程", "取值越界（如载重为负）→ 拒绝保存并提示；场景重名 → 提示覆盖或改名"],
           ["后置条件", "生成场景配置文件，可被算法引擎与批量实验复用"]],
          widths=[4.0, 12.0], caption="表 2-2  配置业务场景用例描述")
    h(doc, "2.4.2  用例对应的活动图", 3)
    p(doc, "活动流程为：新建场景 → 填写约束参数 → 取值校验（不通过则返回修改）→ 保存 JSON → 结束。"
           "该用例把“业务假设”从代码中抽离出来，使同一套算法可以在不同业务条件下复用。")
    figure(doc, "act_scene.png", "图 2-3  配置业务场景活动图", 12.5)

    # ================= 第三章 =================
    doc.add_page_break()
    h(doc, "第三章  项目系统的数据库设计", 1)

    h(doc, "3.1  概念设计", 2)
    p(doc, "系统围绕“算例—场景—实验—路线”四类对象组织数据。算例（instance）描述一次求解的输入，"
           "包括客户数、载重上限、车辆数上限、总需求等属性；场景（scene）描述业务约束假设，"
           "以 JSON 保存载重、车速、时间窗模式、惩罚系数与客户优先级；实验记录（experiment）"
           "保存一次运行的方法、种子、迭代数与各项指标；方案路线（solution）保存一次实验产出的每条路线。")
    p(doc, "实体之间的联系为：一个算例可对应多次实验（1:N），一个场景也可对应多次实验（1:N），"
           "一次实验产出多条路线（1:N）。E-R 图如图 3-1 所示。")
    figure(doc, "er.png", "图 3-1  系统数据库 E-R 图", 15.5)

    h(doc, "3.2  逻辑设计", 2)
    p(doc, "将 E-R 图转换为如下关系模式（下划线字段为主键）：")
    for line in [
        "算例 instance（id，name，size，n_customers，capacity，vehicle_count，speed，total_demand，source_path，created_at）",
        "场景 scene（id，name，config_json，note，created_at）",
        "实验记录 experiment（id，instance_id，scene_id，method，run_index，seed，iterations，"
        "distance，vehicles，feasible，tw_violation，on_time_rate，load_rate，seconds，created_at）",
        "方案路线 solution（id，experiment_id，route_index，customers，stop_count，route_length，route_load）",
    ]:
        p(doc, line, size=11, space_after=2)
    p(doc, "四个关系模式均满足第三范式：每个非主属性完全函数依赖于主键，且不存在传递依赖。"
           "例如 experiment 中的距离、车辆数等指标只依赖于实验本身，与算例名称无关；"
           "solution 中的路线里程只依赖于“实验 + 路线序号”。")

    h(doc, "3.3  物理设计", 2)
    p(doc, "数据库选用 MySQL 9.5，存储引擎 InnoDB，字符集 utf8mb4，以支持中文场景名与备注。"
           "四张表的字段定义如下。")
    table(doc, ["字段", "类型", "约束", "说明"],
          [["id", "INT", "PK, AUTO_INCREMENT", "算例编号"],
           ["name", "VARCHAR(64)", "NOT NULL, UNIQUE", "算例名，如 C101"],
           ["size", "VARCHAR(16)", "", "规模 25/50/100"],
           ["n_customers", "INT", "NOT NULL", "客户数"],
           ["capacity", "DOUBLE", "NOT NULL", "车辆载重上限"],
           ["vehicle_count", "INT", "", "车辆数上限"],
           ["speed", "DOUBLE", "NOT NULL DEFAULT 1.0", "车速，行驶时间=距离/车速"],
           ["total_demand", "DOUBLE", "", "总需求"],
           ["source_path", "VARCHAR(255)", "", "算例文件路径"],
           ["created_at", "DATETIME", "DEFAULT CURRENT_TIMESTAMP", "写入时间"]],
          widths=[4.0, 4.0, 5.0, 5.0], caption="表 3-1  算例表 instance")
    table(doc, ["字段", "类型", "约束", "说明"],
          [["id", "INT", "PK, AUTO_INCREMENT", "实验编号"],
           ["instance_id", "INT", "NOT NULL, FK → instance(id)", "算例"],
           ["scene_id", "INT", "FK → scene(id)", "场景，可为空"],
           ["method", "VARCHAR(64)", "NOT NULL", "方法名：最近邻 / L0 / L1 / L2 / L3"],
           ["run_index", "INT", "NOT NULL", "第几次运行"],
           ["seed", "INT", "", "随机种子"],
           ["iterations", "INT", "", "迭代代数"],
           ["distance", "DOUBLE", "", "总里程"],
           ["vehicles", "INT", "", "车辆数"],
           ["feasible", "TINYINT(1)", "", "是否可行"],
           ["tw_violation", "DOUBLE", "", "时间窗违反量"],
           ["on_time_rate", "DOUBLE", "", "准时率"],
           ["load_rate", "DOUBLE", "", "装载率"],
           ["seconds", "DOUBLE", "", "求解耗时"],
           ["created_at", "DATETIME", "DEFAULT CURRENT_TIMESTAMP", "写入时间"]],
          widths=[4.0, 4.0, 5.5, 4.5], caption="表 3-2  实验记录表 experiment")
    p(doc, "索引与约束设计：instance.name 与 scene.name 建唯一索引，避免重复导入；"
           "experiment 对 instance_id 与 method 建普通索引，支撑“按算例/按方法”的聚合查询；"
           "solution 对 experiment_id 建索引，便于按实验取回全部路线。"
           "三个外键均设置级联删除：删除算例时其下实验与路线一并清理，避免脏数据。")
    p(doc, "为便于报表直接取数，建立汇总视图 kpi_view，按“算例 × 方法”预聚合运行次数、平均里程、"
           "最优里程、平均车辆数、平均准时率、平均装载率与平均耗时。报表模块只需查询该视图，"
           "无需在应用层重复写聚合逻辑。")

    h(doc, "3.4  数据库连接", 2)
    p(doc, "系统通过 pymysql 连接 MySQL，连接参数集中在配置文件 mysql_config.json 中"
           "（host、port、user、password、database、charset），避免把口令写进代码。"
           "连接流程为：读取配置 → 建立连接（未指定库）→ 执行 CREATE DATABASE IF NOT EXISTS 建库 → "
           "USE 目标库 → 执行建表脚本（CREATE TABLE IF NOT EXISTS，可重复执行且不破坏已有数据）。")
    p(doc, "权限方面，应用使用独立业务账号 vrptw，仅授予 vrptw 库的权限，不使用 root 连接，"
           "遵循最小权限原则。为避免绑定单一后端，代码通过 db.py 统一封装数据库访问，"
           "同时支持 SQLite 与 MySQL：开发阶段用 SQLite 零配置运行，部署阶段切换到 MySQL，"
           "业务代码无需修改，只需在命令后加 --mysql。")

    # ================= 第四章 =================
    doc.add_page_break()
    h(doc, "第四章  项目系统的总体设计", 1)

    h(doc, "4.1  系统总体架构设计", 2)
    p(doc, "系统采用四层架构，自上而下为展示层、服务层、算法层与数据层，如图 4-1 所示。"
           "层间只通过接口依赖，上层不直接操作下层的数据结构，因此替换算法或更换数据库不会影响其他层。")
    figure(doc, "arch.png", "图 4-1  系统总体架构图", 15.5)
    p(doc, "展示层负责路线图、收敛曲线、消融对比图与 KPI 报表的呈现；服务层负责实验调度、"
           "指标计算、报表导出与场景管理；算法层负责构造可行解、局部搜索、信息素更新与约束校验；"
           "数据层负责算例解析、距离矩阵构建以及 SQLite / MySQL 的持久化。")
    p(doc, "这样划分的好处是：算法层可以独立替换（例如把蚁群换成遗传算法），只要保持"
           "“输入算例、输出路线”的接口不变；数据层可以独立切换（SQLite ↔ MySQL），"
           "服务层与展示层不受影响。")

    h(doc, "4.2  系统界面设计", 2)
    p(doc, "界面按“配置 → 对比 → 报表”的工作流组织为三屏，如图 4-2 所示。")
    figure(doc, "ui.png", "图 4-2  系统界面原型（三屏）", 15.5)
    p(doc, "第一屏“实验配置”：左侧选择算例与场景，中部设置算法参数（α、β、ρ、蚂蚁数、迭代代数），"
           "底部显示求解进度。参数采用输入框而非滑块，是为了保证实验可复现——便于记录具体取值。")
    p(doc, "第二屏“路线对比”：左右并排显示优化前后两张路线图，下方给出里程、车辆数、准时率三项对比指标，"
           "底部是收敛曲线。并排对比是这一屏的核心设计：只看最终方案很难判断改进是否真实，"
           "放在一起才能看出路线条数与交叉的减少。")
    p(doc, "第三屏“实验报表”：顶部四张 KPI 卡片（平均里程、平均车辆、准时率、平均耗时），"
           "中部是逐算例对比表，底部是导出与刷新按钮。三屏共同遵循三条原则：信息分层（概览在上、明细在下）、"
           "对比可见（同类指标同屏）、操作可复现（参数与结果一一对应）。")
    p(doc, "第 13 周在这三屏之外增加第四屏“运营看板”：顶部六张 KPI 卡片（总里程、车辆数、准时率、"
           "平均装载率、平均每车停靠、总成本），中部三张条形图（每车里程、每车装载率、每车停靠数）"
           "与一张准时率仪表，底部是逐车明细表。看板面向“不看算法、只看经营指标”的读者，"
           "因此刻意不放参数调节入口，只回答“这套方案跑下来花多少钱、准不准时、车装得满不满”。")

    h(doc, "4.3  系统功能模块设计", 2)
    p(doc, "系统共划分十四个功能模块（六个基础模块 + 八个扩展模块），模块之间按“高内聚、低耦合”原则组织："
           "每个模块只负责一类职责，对外暴露明确的函数或文件接口。各模块的职责与输入输出见表 4-1。")
    table(doc, ["模块", "主要职责", "输入", "输出"],
          [["M1 算例与数据管理", "解析 Solomon 算例、构建距离矩阵、校验与导出算例", "算例文件", "算例对象、距离矩阵、算例文件"],
           ["M2 算法引擎", "构造可行解、局部搜索、信息素更新、成本/碳排加权多目标", "算例对象、参数、权重", "路线方案、收敛过程、成本构成"],
           ["M3 路线可视化", "绘制路线图、收敛曲线、消融对比图，Web 在线求解页", "路线方案、实验记录、参数", "SVG / PNG / HTML 页面"],
           ["M4 实验管理与统计", "批量实验调度、指标汇总、消融对比", "算例集合、参数组合", "明细 CSV、汇总表"],
           ["M5 约束与场景配置", "载重/车速/时间窗/优先级、多车场与多车型配置", "业务约束", "场景 JSON"],
           ["M6 方案对比与报表", "KPI 计算、多方案对比、报表导出", "实验明细", "Markdown / CSV / HTML / Excel 报表"],
           ["M7 动态重优化", "插单插入、局部重排、受影响客户延迟评估", "现有路线、新订单", "新路线、延迟清单"],
           ["M8 运营 KPI 看板", "运营指标汇总、逐车明细、成本/碳排对比页、内联 SVG 图表", "路线方案、多方案结果", "HTML 看板页 / 对比页"],
           ["M9 成本/碳排多目标", "加权目标（里程/固定/碳价/罚金）、权重预设", "算例、权重", "多组方案与成本构成"],
           ["M10 成本碳排对比页", "成本构成堆叠图、碳排对比、成本—碳排散点", "多组方案", "HTML 对比页"],
           ["M11 订单 Excel 导入", "读 xlsx、表头别名匹配、校验、导出 Solomon、回读校验", "订单表格", "算例文件、预览"],
           ["M12 用户与项目空间", "项目新建、算例/场景归档、实验摘要", "名称、文件", "项目目录与清单"],
           ["M13 任务监控", "后台队列、进度回调、取消、状态查询", "算例、参数", "任务 JSON、状态页"],
           ["M14 排版自检", "字数/编号/颜色/表格/行距/页码/查重检查", "最终 docx", "检查报告"]],
          widths=[4.5, 6.0, 3.5, 4.5], caption="表 4-1  功能模块划分")
    p(doc, "模块划分的直接收益体现在分工上：本组两人各负责三个基础模块，"
           "接口以数据文件（算例、CSV、数据库表）为准，因此可以并行开发、独立测试，"
           "最后通过统一的数据格式集成；扩展模块按周分工（动态重优化、订单导入、任务监控由任绪锋负责，"
           "运营看板、项目空间、进度前端与排版自检由苍韵同负责），接口仍是“路线方案 + 指标字典 + 算例文件”，"
           "不破坏既有结构。")

    # ================= 第五章 =================
    doc.add_page_break()
    if ch5_fn is not None:
        ch5_fn(doc)
    else:
        h(doc, "第五章至第七章（待写）", 1)
        p(doc, "第五章 项目系统的实现（每人只写自己负责的模块，3 节）："
               "5.1 / 5.2 / 5.3 分别对应本人的三个模块。")
        p(doc, "第六章至第七章待写。")

    if ch67_fn is not None:
        doc.add_page_break()
        ch67_fn(doc)

    if appx_fn is not None:
        doc.add_page_break()
        appx_fn(doc)

    add_references(doc)
    single_space_images(doc)
    center_tables(doc)
    return doc


def single_space_images(doc) -> None:
    """所有含图片的段落统一改为 1.0 倍行距（固定行距会把图片裁掉）"""
    for par in doc.paragraphs:
        if par._p.findall(".//" + qn("w:drawing")):
            pf = par.paragraph_format
            pf.line_spacing = 1.0
            pf.line_spacing_rule = WD_LINE_SPACING.SINGLE


def center_tables(doc) -> None:
    """只处理表格：单元格文字水平居中、彻底取消首行缩进（正文段落不动）

    注意：把 first_line_indent 设为 None 只是“不写段落级缩进”，样式里的
    firstLineChars=200（2 字符）仍会继承；必须显式写 0 才真正取消。
    """
    for tbl in doc.tables[1:]:          # 跳过封面表（封面标签要左对齐，与模板一致）
        for row in tbl.rows:
            for cell in row.cells:
                for par in cell.paragraphs:
                    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    pPr = par._p.get_or_add_pPr()
                    ind = pPr.find(qn("w:ind"))
                    if ind is None:
                        ind = OxmlElement("w:ind")
                        pPr.append(ind)
                    for attr in ("w:firstLine", "w:firstLineChars",
                                 "w:hanging", "w:hangingChars",
                                 "w:left", "w:leftChars"):
                        ind.set(qn(attr), "0")


def add_references(doc) -> None:
    # ================= 参考文献 =================
    h(doc, "参考文献", 1)
    for ref in [
        "[1] Route4Me. Route Planning Software[EB/OL]. https://www.route4me.com/.",
        "[2] Google. OR-Tools: Vehicle Routing[EB/OL]. https://developers.google.com/optimization/routing.",
        "[3] Solomon M M. Algorithms for the vehicle routing and scheduling problems with time window constraints[J]. Operations Research, 1987, 35(2): 254-265.",
        "[4] Dorigo M, Stützle T. Ant Colony Optimization[M]. Cambridge, MA: MIT Press, 2004.",
        "[5] 司守奎, 孙玺菁. 数学建模算法与应用[M]. 北京: 国防工业出版社, 2021.",
        "[6] 王宇春, 李雪梅, 等. 数据库系统及应用教程——SQL Server 2019[M]. 北京: 清华大学出版社, 2022.",
        "[7] DeepSeek. https://www.deepseek.com/.",
        "[8] 豆包. https://www.doubao.com/chat/.",
        "[9] GitHub Copilot. https://github.com/features/copilot.",
    ]:
        p(doc, ref, size=10.5, indent=False, space_after=3)


def main() -> None:
    from report_base import base_doc

    OUT.mkdir(parents=True, exist_ok=True)
    for name, sid in PEOPLE.items():
        path = OUT / f"报告-前四章-{name}-{sid}.docx"
        try:
            build(name, sid, doc=base_doc(name, sid)).save(str(path))
        except PermissionError:
            print(f"[跳过] {path.name} 正被 Word 占用")
            continue
        d = Document(str(path))
        chars = sum(len(x.text) for x in d.paragraphs)
        imgs = len(d.inline_shapes)
        print(f"[OK] {path.name}：{len(d.paragraphs)} 段｜正文 {chars} 字｜插图 {imgs} 张｜"
              f"{path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
