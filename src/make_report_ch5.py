# -*- coding: utf-8 -*-
"""在报告前四章基础上追加第五章（每人三个模块：功能需求 / 设计思路 / 关键实现 / 运行效果）

产出：D:\\vrptw\\docs\\报告-前五章-<姓名>-<学号>.docx
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

from make_report_full import PEOPLE, OUT, build, h, p

CODE_FONT = "Consolas"


def code(doc, text: str, size: float = 9) -> None:
    """等宽字体代码块（每行一个段落，紧排）"""
    for line in text.strip("\n").splitlines():
        par = doc.add_paragraph()
        pf = par.paragraph_format
        pf.line_spacing = Pt(13)
        pf.space_after = Pt(0)
        pf.left_indent = Pt(14)
        r = par.add_run(line if line.strip() else " ")
        r.font.name = CODE_FONT
        r.font.size = Pt(size)
        r._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


# ==========================================================================
# 任绪锋：M1 算例与数据管理 / M2 算法引擎 / M5 约束与场景配置
# ==========================================================================
def ch5_ren(doc) -> None:
    h(doc, "第五章  项目系统的实现", 1)
    p(doc, "本章按本人负责的三个模块分别说明：算例与数据管理、蚁群算法引擎、约束与场景配置。"
           "每个模块按“功能需求—设计思路—关键实现—运行效果”四段展开。")

    # ---------- 5.1 ----------
    h(doc, "5.1  算例与数据管理模块的设计与实现", 2)
    h(doc, "5.1.1  功能需求", 3)
    p(doc, "该模块负责把外部算例变成程序可用的数据结构：读取 Solomon 标准格式文件，解析车辆信息"
           "（车辆数、载重上限）与客户信息（坐标、需求、时间窗、服务时长），并预计算距离矩阵。"
           "当文件缺失或字段不全时，需要给出明确错误而不是静默失败；在没有网络的环境下，"
           "还要能生成合规的测试算例；同时支持把内存中的算例写回 Solomon 格式，便于保存修改后的算例。")
    h(doc, "5.1.2  设计思路", 3)
    p(doc, "解析采用“分段状态机”：读到 VEHICLE 进入车辆段，读到 CUSTOMER 进入客户段，"
           "段内只接受数字行。判断表头与数据行的办法是“整行是否全部为数字”——只要有一个字段"
           "不是数字就当作表头跳过，这样就不必依赖列名拼写。客户点用 frozen dataclass 保存，"
           "防止后续流程误改；距离矩阵在实例构造时一次性算好（O(n²)），后续任意两点查询为 O(1)。")
    h(doc, "5.1.3  关键实现", 3)
    code(doc, '''
section = None
for raw in text.splitlines():
    line = raw.strip()
    if not line:
        continue
    key = line.upper()
    if key.startswith("VEHICLE"):
        section = "vehicle";  continue
    if key.startswith("CUSTOMER"):
        section = "customer"; continue
    nums = _numeric_tokens(line)
    if not nums:                 # 表头或噪声行
        continue
    if section == "vehicle" and vehicle_count is None:
        vehicle_count, capacity = int(nums[0]), float(nums[1])
    elif section == "customer" and len(nums) >= 7:
        customers.append(Customer(int(nums[0]), nums[1], nums[2],
                                  nums[3], nums[4], nums[5], nums[6]))

# 距离矩阵：只算上三角，对称赋值
for i in range(n):
    for j in range(i + 1, n):
        d = round(math.hypot(ci.x - cj.x, ci.y - cj.y), 2)
        m[i][j] = m[j][i] = d
''')
    h(doc, "5.1.4  运行效果", 3)
    p(doc, "对下载的 168 个标准算例（25 / 50 / 100 客户各 56 个）逐个解析，全部通过；"
           "100 客户算例的解析与矩阵构建耗时在 10 毫秒以内，不会成为求解过程的瓶颈。"
           "解析结果同时用于实验与分析脚本，保证各模块读到的算例完全一致。"
           "导出功能做了往返测试：把 C101 导出后再解析，客户数（100）、载重（200）、"
           "车辆数（25）、需求与距离矩阵完全一致。")

    # ---------- 5.2 ----------
    h(doc, "5.2  蚁群算法引擎模块的设计与实现", 2)
    h(doc, "5.2.1  功能需求", 3)
    p(doc, "在载重与时间窗约束下，为每只蚂蚁构造一组可行路线；支持 α、β、ρ、蚂蚁数、迭代代数等"
           "参数配置；支持开启或关闭局部搜索，以便做消融实验；输出每一代的最优里程用于绘制收敛曲线。")
    h(doc, "5.2.2  设计思路", 3)
    p(doc, "每代由 n_ants 只蚂蚁各自构造解：从仓库出发，先在所有未访问客户中筛出“装得下且赶得上”的"
           "候选集，再按 (τ^α · η^β) 做轮盘赌选择。这样把约束检查放在构造阶段，避免产生大量不可行解。"
           "η 同时考虑距离、等待时间与时间窗裕度。每代结束后对本代最优解做 2-opt、Or-opt 与路线间 "
           "relocate 三种局部搜索，再用“精英 + 最大最小（MMAS）”策略更新信息素，把信息素限制在"
           "上下界之内，抑制早熟。")
    h(doc, "5.2.3  关键实现", 3)
    code(doc, '''
for cid in unvisited:
    c = inst.customers[cid]
    if load + c.demand > inst.capacity:          # 装不下
        continue
    trav = inst.time(prev, cid)                  # 时间 = 距离 / 车速
    start = max(t + trav, c.ready)
    if start > c.due:                            # 赶不上时间窗
        continue
    cands.append((cid, inst.dist(prev, cid), trav, start - (t + trav), c.due - start))

weights = [(tau[prev][cid] ** alpha) *
           (self._eta(d, wait, slack) ** beta)
           for (cid, d, trav, wait, slack) in cands]
cid, d, trav, wait, slack = self._roulette(cands, weights)

# MMAS：更新后把信息素夹到 [tau_min, tau_max]
tau_max = 1.0 / (rho * best_cost)
tau_min = tau_max / (2.0 * self.n)
for i in range(self.n):
    for j in range(self.n):
        if i != j:
            tau[i][j] = min(tau_max, max(tau_min, tau[i][j]))
''')
    h(doc, "5.2.4  运行效果", 3)
    p(doc, "在 C101（100 客户）上，改进版求得总里程 829.01，与已知最优解 828.94 相差 0.01%；"
           "12 个算例、每个 10 次重复的平均 gap 为 17.1%，相对基线蚁群（平均 gap 55.2%）下降明显。"
           "单次求解耗时随迭代代数与是否启用局部搜索变化，100 客户算例约 6–50 秒。")

    # ---------- 5.3 ----------
    h(doc, "5.3  约束与场景配置模块的设计与实现", 2)
    h(doc, "5.3.1  功能需求", 3)
    p(doc, "把“业务假设”从代码里抽出来：载重上限、车辆数上限、车速、硬/软时间窗及惩罚系数、"
           "多车场（多个仓库坐标）、多车型（不同载重与固定成本）、"
           "客户优先级都可以配置，并以 JSON 保存复用；同时把算法参数模板一并存入场景，"
           "保证“同一场景 + 同一参数”能复现同一结果。")
    h(doc, "5.3.2  设计思路", 3)
    p(doc, "场景用 dataclass 表示，apply() 负责把约束“贴”到算例对象上（不复制算例，避免大对象拷贝），"
           "aco_config() 负责生成算法参数：硬时间窗自动把违约惩罚调到极大值，逼算法优先找可行解；"
           "软时间窗则使用配置的 λ。参数名不在 ACOConfig 字段内时直接抛出异常，"
           "避免拼写错误被静默忽略、跑出一堆“看起来正常”的错误实验。")
    h(doc, "5.3.3  关键实现", 3)
    code(doc, '''
def apply(self, inst):
    if self.capacity is not None:
        inst.capacity = float(self.capacity)
    if self.max_vehicles is not None:
        inst.vehicle_count = int(self.max_vehicles)
    inst.speed = float(self.speed or 1.0)          # 时间 = 距离 / 车速
    inst.tw_hard = (str(self.tw_mode).lower() != "soft")
    inst.priority = {int(k): float(v) for k, v in (self.priority or {}).items()}
    return inst

def aco_config(self, **overrides):
    params = dict(self.aco or {}); params.update(overrides)
    if self.tw_mode == "hard":
        params.setdefault("lambda_tw", 1e4)        # 硬时间窗：违约重罚
    else:
        params.setdefault("lambda_tw", float(self.lambda_tw))
    allowed = set(ACOConfig.__dataclass_fields__)
    unknown = [k for k in params if k not in allowed]
    if unknown:
        raise ValueError(f"未知的算法参数：{unknown}")
    return ACOConfig(**params)
''')
    h(doc, "5.3.4  运行效果", 3)
    p(doc, "系统内置三个预设场景：标准场景（硬时间窗）、校园配送（软时间窗，λ=25）、"
           "雨天慢速（车速 0.8，λ=50）。同一算例切换到“雨天慢速”后，等效行驶时间变长，"
           "算法自动多派车并缩短单条路线，结果与业务直觉一致，说明约束确实作用到了求解过程。"
           "多车场测试：把 C101 的客户 5 也设为仓库，同一组路线的最优里程从 1870.73 降到 1747.63（省 6.6%）；"
           "多车型测试：配置 200 与 100 两种载重，系统按每条路线的载重自动选型并累加固定成本。")


    # ---------- 5.4 ----------
    h(doc, "5.4  动态重优化模块的设计与实现", 2)
    h(doc, "5.4.1  功能需求", 3)
    p(doc, "前面的算法解决的是“从零排一次”，而配送现场真正高频的是“改一下”：车已经出发，"
           "临时来一张新订单、客户改约时间、某张单撤掉。若每次都全量重算，100 客户算例要 10–40 秒，"
           "而且所有司机的路线都会被推翻，现场无法执行。本模块要解决的是：在已有方案上做最小改动的修复，"
           "要求（1）给出插入到哪条路线、第几位；（2）给出增量里程与新增的时间窗违反；（3）列出受影响的客户"
           "各延后多少分钟；（4）单次重排控制在 1 秒以内；（5）确实没有可行位置时，明确给出“新开一辆车”的选择。")
    h(doc, "5.4.2  设计思路", 3)
    p(doc, "把一次插单拆成“枚举—选优—重排”三步。枚举阶段遍历每条路线的每个插入位置，用现有的"
           "路线评价函数算出插入后的载重、里程与时间窗违反量，载重装不下的直接淘汰；若车辆还没派完，"
           "再把“单独开一条线”也作为一个候选。选优不按单一里程，而按三元组（是否新增时间窗违反，违反量，"
           "增量里程）排序——硬时间窗下“不新增违反”优先于“少跑几公里”，否则会为了省几公里把客户送晚。"
           "选定后只对受影响的路线做局部重排（2-opt、Or-opt，以及与其他路线互搬客户的 relocate），"
           "并且给装载率留 8% 的余量：局部搜索若把某辆车塞满，下一单就只能新开一辆车，"
           "这在动态场景里是隐形成本。")
    h(doc, "5.4.3  关键实现", 3)
    code(doc, '''for ri, route in enumerate(routes):
    rep = evaluate_route(inst, route)
    for pos in range(len(route) + 1):
        cand = route[:pos] + [cid] + route[pos:]
        nrep = evaluate_route(inst, cand)
        if nrep.load > capacity:                  # 装不下
            continue
        tw_delta = nrep.tw_violation - rep.tw_violation
        cands.append((1 if tw_delta > 1e-9 else 0,  # 先比可行性
                      round(tw_delta, 4),           # 再比违反量
                      round(nrep.distance - rep.distance, 2),  # 最后比里程
                      ri, pos, cand))

if len(routes) < inst.vehicle_count:             # 车还没派完：新开一辆也算候选
    cands.append((0, 0.0, evaluate_route(inst, [cid]).distance, -1, 0, [cid]))

cands.sort(key=lambda x: (x[0], x[1], x[2]))
routes = improve(inst, routes2, reserve=0.08)   # 局部重排，预留 8% 装载余量
''')
    h(doc, "5.4.4  运行效果", 3)
    p(doc, "在 C101（100 客户）上以 40 代求得基础方案 829.01、10 辆车、准时率 100%。"
           "从中抽掉客户 9、60、97 三个客户再逐个作为“插单”插回：新增里程分别为 +0.40、+3.44、+0.00，"
           "总里程回到 829.01（相对原方案 0.00%），车辆数仍为 10，准时率 100%，时间窗违反 0，"
           "三次重排合计 2.05 秒，其中单次 0.66–0.70 秒；同样的算例全量重算 40 代需要 10.6 秒。"
           "也就是说，插单修复的耗时约为全量重算的 1/5–1/15，且不会打乱无关车辆的路线。"
           "在 25 客户算例上连续插入三张坐标随机的新订单（需求 10–25、截止时间 600–1100），"
           "里程由 213.59 增至 331.25，三次插入都没有新增车辆（始终 4 辆），准时率保持 100%，"
           "单次重排耗时 6–10 毫秒，说明小规模场景下重排是毫秒级的。"
           "当所有路线都装不下时（例如某条线已满载且时间窗无余量），模块会给出“新开车辆”的方案并计入增量里程，"
           "由调度员决定是否接受，而不是悄悄把客户塞进超载路线。")

    # ---------- 5.5 ----------
    h(doc, "5.5  成本与碳排多目标优化的设计与实现", 2)
    h(doc, "5.5.1  功能需求", 3)
    p(doc, "前面的算法只优化里程，但企业决策不只看里程：多派一辆车要多付司机与折旧，跑得远碳排高，"
           "晚到还要赔钱。本模块把这些折算成钱，支持按“成本优先 / 均衡 / 低碳优先”三组权重求解，"
           "输出总成本、成本构成（里程成本、固定成本、碳成本、晚到罚金）与碳排（kg CO2），"
           "并且不改变原有算法的骨架——仍然复用蚁群构造解与局部搜索，只替换目标函数。")
    h(doc, "5.5.2  设计思路", 3)
    p(doc, "成本模型取四个可解释的参数：里程成本 3.5 元/km（油费、保养、司机分摊），车辆固定成本 300 元/车，"
           "碳价 0.5 元/kg（约 70 欧元/吨，接近当前碳市场价），晚到罚金 50 元/单位时间窗违反。"
           "碳排按“空载 0.25 kg/km + 满载附加 0.25 kg/km × 装载率”估算，装载越满单位里程碳排越高，"
           "因此“少跑”和“少派车”并不总是同向——这正是多目标要展示的取舍。"
           "实现上用继承而不是改原类：WeightedSolver 继承 AntColonySolver，只覆写 _route_cost 与 _solution_cost，"
           "构造解、信息素更新、局部搜索全部复用，保证单目标与多目标的搜索结果可比。"
           "为降低随机性影响，每组权重跑 2 个随机种子，取该组目标最优的一次（run_multiobj.py）。")
    h(doc, "5.5.3  关键实现", 3)
    code(doc, '''class WeightedSolver(AntColonySolver):
    def _route_cost(self, route):
        rep = evaluate_route(self.inst, route)
        ratio = min(1.0, rep.load / self.inst.capacity)
        carbon = rep.distance * (0.25 + 0.25 * ratio)   # kg CO2
        return (self.w.dist_cost * rep.distance
                + self.w.carbon_price * carbon
                + self.w.late_rate * rep.tw_violation)

    def _solution_cost(self, routes):
        used = [r for r in routes if r]
        return sum(self._route_cost(r) for r in used) + self.w.fixed_cost * len(used)

PRESETS = {"成本优先": Weights(carbon_price=0.0),
           "均衡":     Weights(carbon_price=0.5),
           "低碳优先": Weights(carbon_price=6.0)}
''')
    h(doc, "5.5.4  运行效果", 3)
    p(doc, "C101 上三组权重收敛到同一方案（829.01、10 辆车、碳排 394.7 kg、总成本 6098.9 元）："
           "该算例总需求 1810、载重 200，车辆数下界就是 10，权重再怎么调也压不下来，"
           "这本身就说明“先看约束、再谈优化”。R101 上出现了真实差异：均衡组 1886.60 km、21 辆车、"
           "总成本 13227.4 元、碳排 648.6 kg；低碳优先组 1890.72 km、21 辆车、13240.5 元、645.9 kg——"
           "多跑 4.12 km（+0.22%）、多花 13.1 元（+0.10%），换 2.6 kg 碳排（−0.41%）。"
           "成本优先组（1959.93 km、13492.8 元）反而被均衡组同时压倒，说明在这个算例上它陷入了局部最优；"
           "这也暴露了加权和法的局限：权重改变的是“往哪边找”，不改变搜索能力，单次随机搜索的结果不能当作结论，"
           "所以正式对比统一用 2 个种子取优，并把这一点如实写进报告，而不是只挑好看的数字。")
    p(doc, "另外一个有价值的发现是成本结构：以均衡组为例，固定成本 6300 元占总成本 47.6%，"
           "里程成本 6603.1 元占 49.9%，碳成本 324.3 元只占 2.5%。也就是说，"
           "在当前碳价下“少派一辆车”比“少跑几公里”更能省钱；碳价要涨到约 24 元/kg，"
           "碳成本才会和固定成本同量级——这为后续碳价敏感性分析留了口子。")

    # ---------- 5.6 ----------
    h(doc, "5.6  订单 Excel 导入模块的设计与实现", 2)
    h(doc, "5.6.1  功能需求", 3)
    p(doc, "业务现场给过来的不是 Solomon 算例，而是一张 Excel：客户名、坐标、需求、时间窗、服务时长。"
           "本模块负责把它变成系统能直接求解的算例：（1）表头允许中英文、顺序任意，只要包含经度、纬度、需求；"
           "（2）逐行校验取值，坐标不是数字、需求为负、最晚时间早于最早时间都要给出明确提示；"
           "（3）识别仓库行，没有仓库就用客户坐标的质心；"
           "（4）写出 Solomon 格式并**回读校验**，客户数对不上就报错；"
           "（5）Web 端上传 xlsx 后直接求解并显示路线图，做到“上传即跑”。")
    h(doc, "5.6.2  设计思路", 3)
    p(doc, "表头匹配不用列名硬编码，而是建一张别名表（名称/name、经度/lon/x、需求/qty…），"
           "把表头去空格转小写后查表，因此“经度”“x”“X坐标”都能认。前 10 行里找同时含 x、y、demand 的行当表头，"
           "避免标题行、说明行干扰。仓库判定有两种：类型列写“仓库/depot”，或没有类型列时把第一行当仓库；"
           "若整张表没有仓库，就用所有客户坐标的质心，时间窗上界取客户最晚时间。"
           "车辆数不要求用户填，按“总需求 / 载重”向上取整估算，用户也可以在命令行显式指定。"
           "写文件之后立刻用 parse_solomon 读回来比对客户数，这一步防的是编码、分隔符之类的低级错误——"
           "导入模块最怕的不是报错，而是“看起来成功、其实少了一行”。")
    h(doc, "5.6.3  关键实现", 3)
    code(doc, '''ALIASES = {
    "x": {"经度", "x", "xcoord", "x坐标", "lon", "lng", "longitude"},
    "y": {"纬度", "y", "ycoord", "y坐标", "lat", "latitude"},
    "demand": {"需求", "需求量", "demand", "qty", "数量"},
    ...
}

for i, row in enumerate(rows[:10]):
    found = {key: j for j, cell in enumerate(row)
             if (key := _match(cell)) is not None}
    if {"x", "y", "demand"} <= set(found):
        header_idx, mapping = i, found
        break

item = {"x": _num(rec.get("x"), "经度", r),
        "demand": _num(rec.get("demand"), "需求", r), ...}
if item["demand"] < 0:
    raise OrderImportError("第 %d 行需求为负数" % r)
if item["due"] < item["ready"]:
    raise OrderImportError("第 %d 行最晚时间早于最早时间" % r)

write_solomon(inst, out)
again = parse_solomon(out)                      # 回读校验
if again.n_customers != inst.n_customers:
    raise OrderImportError("导出后回读客户数不一致")
''')
    h(doc, "5.6.4  运行效果", 3)
    p(doc, "用模板（1 个仓库 + 9 个客户、总需求 145、载重 200）导入：识别出 9 个客户，"
           "按总需求估算 1 辆车，写出 Solomon 文件后回读仍是 9 个客户，客户数、载重、需求与距离矩阵一致。"
           "Web 端 POST /import 返回 200，页面直接给出路线图、里程、车辆数与用时，并列出前 10 个客户的需求与时间窗。"
           "异常数据也做了验证：缺经度列、需求为负、最晚早于最早，三种情况都会返回中文提示而不是 500 错误。"
           "整个过程（读表 → 校验 → 写算例 → 回读 → 求解）在 1 秒内完成。")


    # ---------- 5.7 ----------
    h(doc, "5.7  任务监控与后台队列的设计与实现", 2)
    h(doc, "5.7.1  功能需求", 3)
    p(doc, "100 客户算例跑 40 代要十几到几十秒，Web 页面不能一直转圈等结果；实验人员也常常一次提交好几个配置，"
           "希望先拿到任务号、再回来看进度。本模块要提供：提交任务立刻返回编号；任务在后台执行并持续写进度；"
           "能查询状态、看当前代数与最优代价；能取消；进程重启后历史任务仍可查；失败时把原因写清楚，"
           "而不是只显示“出错了”。")
    h(doc, "5.7.2  设计思路", 3)
    p(doc, "任务用 JSON 文件表示，一个任务一个文件，写入时先写 .tmp 再原子替换，轮询端不会读到半个 JSON。"
           "状态机只有五态：queued → running → done / failed / cancelled。执行方式分两种："
           "Web 端用后台线程（Flask 进程常驻）；命令行用独立进程（DETACHED_PROCESS），"
           "因为线程会随父进程退出而被杀掉——第一版就踩了这个坑，提交后退出命令行，任务永远停在 queued。"
           "进度靠给蚁群加一个可选回调：每代结束回传（已做代数、总代数、当前最优代价），"
           "回调里顺便检查取消标志，置位就抛异常终止。")
    h(doc, "5.7.3  关键实现", 3)
    code(doc, '''def _run(task):
    task["state"] = "running"; save(task)
    solver = AntColonySolver(inst, cfg)
    def cb(done, total, cost):
        cur = load(task["id"])
        if cur.get("cancel_requested"):
            raise TaskCancelled()
        cur["progress"] = round(done / max(1, total), 4)
        cur["iter"] = done; cur["best_cost"] = round(cost, 2)
        save(cur)
    solver.progress_cb = cb
    res = solver.solve()
    task.update({"state": "done", "distance": res["distance"], ...})

def spawn_worker(tid):
    subprocess.Popen([sys.executable, __file__, "run", tid],
                     creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
''')
    h(doc, "5.7.4  运行效果", 3)
    p(doc, "命令行提交 25 客户、12 代的任务，0.1 秒完成，状态 done、进度 100%、里程 213.59、4 辆车；"
           "提交 100 客户、10 代的任务后立刻退出命令行，几秒后再查仍是 done、里程 829.01，说明独立进程方案有效。"
           "Web 端 /tasks 返回 200，/tasks.json 返回任务列表；提交后首屏状态 running、进度 0%，"
           "2 秒后轮询到 done、进度 1.0、里程 829.01；取消接口返回 200。"
           "任一任务失败时 error 字段会带上异常消息，页面上直接显示，不需要翻日志。")

# ==========================================================================
# 苍韵同：M3 可视化 / M4 实验管理 / M6 报表
# ==========================================================================
def ch5_cang(doc) -> None:
    h(doc, "第五章  项目系统的实现", 1)
    p(doc, "本章按本人负责的三个模块分别说明：路线可视化与交互、实验管理与统计、方案对比与报表。"
           "每个模块按“功能需求—设计思路—关键实现—运行效果”四段展开。")

    # ---------- 5.1 ----------
    h(doc, "5.1  路线可视化与交互模块的设计与实现", 2)
    h(doc, "5.1.1  功能需求", 3)
    p(doc, "把求解结果变成能看懂的图：多车路线图（不同车辆不同颜色、客户点可查看需求与时间窗）、"
           "优化前后并排对比、收敛曲线、消融柱状图；并把它们整合成一个可以直接双击打开的页面，"
           "支持在多个方法之间切换查看。另外提供一个在线求解页面（Flask）：选算例、调 α/β/ρ/迭代数，"
           "提交后直接看到路线图与指标。")
    h(doc, "5.1.2  设计思路", 3)
    p(doc, "先抽象出统一的“画布”接口（画线、画圆、画矩形、写字），再用两个实现分别输出 SVG 与 PNG："
           "SVG 用字符串拼接、便于嵌网页与放大不糊；PNG 用 Pillow、便于直接插入 Word。"
           "绘图函数只依赖接口，因此同一份绘图代码能同时产出两种格式。坐标按算例的经纬度范围"
           "归一化到画布，并翻转 y 轴以符合屏幕坐标。HTML 页面把各方法的 SVG 内嵌进去，"
           "用几行 JavaScript 控制显示，不需要起服务器、也不需要联网。")
    h(doc, "5.1.3  关键实现", 3)
    code(doc, '''
class SvgCanvas:                      # 出 SVG：拼字符串
    def polyline(self, pts, color="#333", width=2, opacity=1.0):
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.parts.append(f'<polyline points="{p}" fill="none" '
                          f'stroke="{color}" stroke-width="{width}"/>')

class PngCanvas:                      # 出 PNG：Pillow
    def polyline(self, pts, color="#333", width=2, opacity=1.0):
        self.d.line([tuple(p) for p in pts], fill=color,
                    width=int(width), joint="curve")

# 页面里切换方法（无服务器）
function show(i){
  document.querySelectorAll('.panel').forEach(
      (e,k)=>e.style.display=(k===i?'block':'none'));
}
''')
    h(doc, "5.1.4  运行效果", 3)
    p(doc, "以 C101 为例，优化前（最近邻）为 1870.73、21 辆车，优化后为 829.01、10 辆车，"
           "并排图能直观看到路线由“长距离交叉”变为“成簇短途”。单张路线图生成时间小于 1 秒，"
           "12 个算例的全部图表可在十几秒内批量产出。在线页面用 Flask 测试客户端验证："
           "首页返回 200，提交求解返回 200，页面内含 SVG 路线图与指标卡片。")

    # ---------- 5.2 ----------
    h(doc, "5.2  实验管理与统计模块的设计与实现", 2)
    h(doc, "5.2.1  功能需求", 3)
    p(doc, "支持“多算例 × 多方法 × 多次重复”的批量实验；蚁群是随机算法，同一配置必须重复运行"
           "才能报均值与标准差；实验规模大（数百次运行），因此需要并行加速，并且要求中途中断时"
           "已完成的记录不丢失。")
    h(doc, "5.2.2  设计思路", 3)
    p(doc, "把实验拆成最小任务单元（算例、方法、第几次运行），交给进程池并行执行；主进程用"
           "imap_unordered 按完成顺序取结果，每取到一条就写一行 CSV 并立即 flush。"
           "这样即使进程被中断，已写入的记录仍然可用，也便于随时查看进度。"
           "全部完成后由内存中的行直接生成汇总表，避免二次读盘造成口径不一致。")
    h(doc, "5.2.3  关键实现", 3)
    code(doc, '''
tasks = [(str(f), m, r) for f in files for m in methods for r in range(runs)]
print(f"共 {len(tasks)} 个任务，并行 {jobs} 进程", flush=True)

with mp.Pool(jobs) as pool:
    for done, row in enumerate(pool.imap_unordered(_work, tasks), 1):
        rows.append(row)
        writer.writerow({k: row.get(k) for k in fieldnames})
        fh.flush()                                  # 边跑边落盘
        if done % 5 == 0 or done == len(tasks):
            el = time.perf_counter() - t0
            print(f"进度 {done}/{len(tasks)}｜已用 {el:.0f}s", flush=True)
''')
    h(doc, "5.2.4  运行效果", 3)
    p(doc, "600 次运行（12 个算例 × 5 种方法 × 10 次）在 16 进程下约 8 分钟完成；"
           "按单次平均耗时估算，单进程需要 60 分钟以上，加速比约 7–8 倍（受最慢任务限制）。"
           "中断测试中，已完成的 400 条记录完整保留，后续可用追加模式继续跑。")

    # ---------- 5.3 ----------
    h(doc, "5.3  方案对比与报表模块的设计与实现", 2)
    h(doc, "5.3.1  功能需求", 3)
    p(doc, "把实验明细汇总成可提交的报表：按算例与方法统计总里程（均值与标准差）、最优值、"
           "车辆数、准时率、装载率、与已知最优的差距、平均耗时；支持逐算例对比，"
           "并能一次导出 Markdown、CSV、HTML、Excel 四种格式，其中 Excel 版分「KPI 汇总」与「逐算例」两个工作表。")
    h(doc, "5.3.2  设计思路", 3)
    p(doc, "数据源可以是实验 CSV，也可以直接查数据库视图，两者字段一致，因此聚合逻辑只写一份。"
           "按方法分组后用 statistics 计算均值与总体标准差；gap 只在存在已知最优解的算例上计算，"
           "缺失时留空而不是填 0，避免误导。HTML 用 KPI 卡片 + 两张表，打印或投影都清楚。")
    h(doc, "5.3.3  关键实现", 3)
    code(doc, '''
for m in methods:
    sel = [r for r in rows if r["method"] == m]
    vals = [float(r["distance"]) for r in sel if r.get("distance") not in (None, "")]
    if not vals:
        continue
    mean, std = statistics.mean(vals), statistics.pstdev(vals)
    gaps = [100 * (float(r["distance"]) - bks[r["instance"].upper()]) /
            bks[r["instance"].upper()]
            for r in sel if r["instance"].upper() in bks]
    summary.append({
        "method": m, "runs": len(sel),
        "distance_mean": round(mean, 2), "distance_std": round(std, 2),
        "gap_mean": round(statistics.mean(gaps), 1) if gaps else None,
        "on_time": round(statistics.mean([float(r["on_time_rate"]) for r in sel]) * 100, 1),
    })
''')
    h(doc, "5.3.4  运行效果", 3)
    p(doc, "以 12 个算例 × 5 种方法为例，报表生成 60 行 KPI 汇总，四种格式一键导出（Excel 首行冻结）；"
           "HTML 版可直接用于组会汇报，Markdown 版可直接粘进报告，CSV 版可用 Excel 画箱线图。"
           "从原始明细到成品报表的耗时在 1 秒以内。")


    # ---------- 5.4 ----------
    h(doc, "5.4  运营 KPI 看板模块的设计与实现", 2)
    h(doc, "5.4.1  功能需求", 3)
    p(doc, "算法跑出的是路线，运营人员关心的是成本与服务质量。本模块把一次求解的结果汇总成一页看板："
           "顶部六张 KPI 卡片（总里程、车辆数、准时率、平均装载率、平均每车停靠、总成本），"
           "中部三张条形图（每车里程、每车装载率、每车停靠数）与一张准时率仪表，"
           "底部是逐车明细表（仓库、停靠数、载重与装载率、里程、等待、晚到、准时率）。"
           "约束有三条：不引入第三方绘图库（环境里没有 matplotlib）；生成的页面能离线双击打开；"
           "同一份指标口径既用于命令行输出，也用于 Web 页面，避免两处数字对不上。")
    h(doc, "5.4.2  设计思路", 3)
    p(doc, "指标不另起一套算法：总里程、车辆数、准时率、装载率、固定成本直接取自 evaluate() 的返回值，"
           "逐车明细用 evaluate_route() 逐条路线算，这样看板、报表、测试用例三处的口径天然一致。"
           "图表用内联 SVG 字符串拼接：给定标签与数值，先算坐标再写 rect/text 元素，"
           "条形图带四条水平网格线与数值标注，仪表用一段圆弧的起止角度画。"
           "页面用 CSS Grid 自适应列宽，窄屏自动单列；打印时是白底深字，可直接贴进汇报材料。"
           "Web 端在 Flask 里挂 /dashboard 路由，与在线求解页共用同一套算例与参数，"
           "首页右上角提供入口，两个页面互相可跳转。")
    h(doc, "5.4.3  关键实现", 3)
    code(doc, '''def bar_chart(labels, values, unit="", color="#2980b9", width=520, height=220):
    inner_w, inner_h = width - 58, height - 52
    vmax = max(values) or 1.0
    slot = inner_w / len(values)
    for i, (lab, v) in enumerate(zip(labels, values)):
        h = inner_h * (v / vmax)
        x = pad_l + slot * i + (slot - bar_w) / 2
        y = pad_t + inner_h - h
        parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"/>'
                     % (x, y, bar_w, h, color))
        parts.append('<text x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
                     % (x + bar_w / 2, y - 4, fmt.format(v) + unit))

def kpi_summary(inst, routes):
    ev = evaluate(inst, routes)            # 与报表、测试共用同一口径
    rows = [evaluate_route(inst, r) for r in routes]
    return {"distance": ev["total_distance"], "vehicles": ev["vehicles"],
            "on_time_rate": ev["on_time_rate"], "load_rate": ev["load_rate"],
            "avg_stops": sum(len(r) for r in routes) / max(1, len(rows)),
            "total_cost": ev["total_cost"], "rows": rows}
''')
    h(doc, "5.4.4  运行效果", 3)
    p(doc, "以 C101 的改进版方案为例，看板显示：总里程 829.01、车辆 10 台、准时率 100%、"
           "平均装载率 90.5%、平均每车停靠 10.0 个点、总成本 829.01（单一车型、无固定成本）；"
           "逐车明细 10 行，装载率在 75%–100% 之间，最长的一条路线 127.30（9 个客户，跨两个聚类），"
           "其余路线都在 50–102 之间，与路线图上的“长短线”分布一致。"
           "页面 15 KB、含 4 张内联 SVG，生成耗时不足 1 秒，离线双击即可打开；"
           "Web 端 /dashboard 返回 200，页面含 4 张图与 10 行明细，与命令行输出的数字完全一致。")


    # ---------- 5.5 ----------
    h(doc, "5.5  成本与碳排对比页的设计与实现", 2)
    h(doc, "5.5.1  功能需求", 3)
    p(doc, "把“成本优先 / 均衡 / 低碳优先”三组权重的结果放在同一页里对比：三组的总成本、碳排与车辆数，"
           "成本构成（里程、固定、碳、罚金四块），碳排对比，以及一张“成本—碳排”散点图，"
           "让读者一眼看出哪个方案更划算、哪个更环保、两者差多少。要求同样不依赖第三方绘图库，"
           "页面离线可打开，并挂在 Web 端的 /compare 路由上。")
    h(doc, "5.5.2  设计思路", 3)
    p(doc, "数据口径直接复用多目标模块的 breakdown()，不另写聚合，保证页面、命令行与报告三处数字一致。"
           "三张图各有分工：堆叠条形图回答“钱花在哪”，碳排条形图回答“谁更环保”，"
           "散点图把两个目标放在同一坐标系里——越靠左下越好，两点之间的斜率就是“减一公斤碳要花多少钱”。"
           "散点图的坐标范围按数据自动留 4% 边距，避免点贴在边框上；图例与口径说明直接写在页面里，"
           "免得读者自己猜系数。Web 端对同一组（算例、迭代数）缓存页面，第二次打开不再重复求解。")
    h(doc, "5.5.3  关键实现", 3)
    code(doc, '''def stacked_cost_chart(schemes, width=560, height=250):
    totals = [s["dist_cost"] + s["fixed_cost"] + s["carbon_cost"] + s["late_penalty"]
              for s in schemes]
    for i, s in enumerate(schemes):
        x = pad_l + slot * i + (slot - bar_w) / 2
        y = pad_t + inner_h
        for key, _label, color in [("dist_cost", "", "#2f6f9f"),
                                   ("fixed_cost", "", "#27ae60"),
                                   ("carbon_cost", "", "#e67e22"),
                                   ("late_penalty", "", "#8e44ad")]:
            h = inner_h * (s[key] / vmax)
            y -= h
            parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
                         % (x, y, bar_w, h, color))

def scatter(schemes):                     # 成本—碳排散点
    cx = pad_l + inner_w * (s["carbon_kg"] - x0) / (x1 - x0)
    cy = pad_t + inner_h * (1 - (s["total_cost"] - y0) / (y1 - y0))
    parts.append('<circle cx="%.1f" cy="%.1f" r="7" fill="%s"/>' % (cx, cy, color))
''')
    h(doc, "5.5.4  运行效果", 3)
    p(doc, "以 R101 的三组方案为例，页面 8.8 KB、含 3 张内联 SVG 与 3 行明细，生成不足 1 秒；"
           "/compare 返回 200，页面包含成本构成、碳排对比与散点三张图。散点图上均衡组与低碳优先组几乎重叠，"
           "成本优先组明显偏右上——与表里的数字一致：均衡 13227.4 元 / 648.6 kg，低碳 13240.5 元 / 645.9 kg，"
           "成本优先 13492.8 元 / 666.0 kg。堆叠图显示固定成本占了将近一半，"
           "这也解释了为什么“多派一辆车”比“多跑几公里”更伤成本。")


    # ---------- 5.6 ----------
    h(doc, "5.6  项目空间模块的设计与实现", 2)
    h(doc, "5.6.1  功能需求", 3)
    p(doc, "一个人手上往往不止一个配送课题：校园配送、社区团购、某公司的线路复现，"
           "它们的算例、场景和实验记录不能混在一起。本模块提供“项目”这一层：新建项目时记录名称、负责人与备注，"
           "之后可以把算例和场景复制进项目、查看项目下有哪些文件与多少条实验记录，"
           "并在 Web 端列出所有项目、直接新建。要求不修改数据库结构——第三章的四张表已经逐字段核对过，"
           "不能为了一个文件柜去动表。")
    h(doc, "5.6.2  设计思路", 3)
    p(doc, "项目就是一个目录：projects/项目名/ 下面放 project.json、instances/ 与 scenes/。"
           "project.json 存元信息与文件清单，算例和场景按原文件名复制，实验只记摘要（方法、里程、车辆数、时间），"
           "不复制大文件。项目名做安全校验，禁止路径分隔符与 Windows 非法字符，避免“名字叫 ../x”把文件写到别处。"
           "列表按目录名排序，坏掉的 json 直接跳过而不让整页崩掉。Web 端 POST 新建后重定向回列表，"
           "刷新不会重复提交。")
    h(doc, "5.6.3  关键实现", 3)
    code(doc, '''def create(name, owner="", note=""):
    d = project_dir(name)                       # 校验名称合法性
    if d.exists():
        raise ProjectError("项目已存在：" + name)
    (d / "instances").mkdir(parents=True)
    (d / "scenes").mkdir(parents=True)
    meta = {"name": name, "owner": owner, "note": note,
            "created_at": _now(), "instances": [], "scenes": [], "experiments": []}
    (d / "project.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta

def add_instance(name, path):
    meta = load(name)
    dst = project_dir(name) / "instances" / Path(path).name
    shutil.copy2(path, dst)
    if dst.name not in meta["instances"]:
        meta["instances"].append(dst.name)
    save(meta)
    return meta
''')
    h(doc, "5.6.4  运行效果", 3)
    p(doc, "新建“校园配送”项目（负责人任绪锋，备注软时间窗），把导入的 demo.txt 算例与"
           "“校园配送-软时间窗”场景加入后，project.json 中算例 1 个、场景 1 个、实验 0 条，"
           "目录下 instances/ 与 scenes/ 各有一份副本；再次加入同名文件不会重复登记。"
           "Web 端 /projects 返回 200，新建后项目立即出现在列表里（负责人、算例/场景/实验数量、创建时间齐全），"
           "刷新页面不会重复创建。整个模块不依赖数据库，换机器时把 projects/ 目录拷走即可。")


    # ---------- 5.7 ----------
    h(doc, "5.7  任务进度前端与全文排版自检的设计与实现", 2)
    h(doc, "5.7.1  功能需求", 3)
    p(doc, "前端要解决两件事。第一是进度可见：提交任务后不整页刷新，也能看到状态、进度条、当前代数与最终指标，"
           "并能取消。第二是交稿前的自检：模板对字数、编号、颜色、表格缩进、图片行距、页码都有要求，"
           "人工逐条核对容易漏，希望有一条命令把这些问题一次性查出来。")
    h(doc, "5.7.2  设计思路", 3)
    p(doc, "进度页采用“服务端渲染首屏 + 前端轮询局部更新”：第一次打开由 Flask 把任务列表渲染出来，"
           "之后每 2 秒 fetch 一次 /tasks.json，按 data-id 找到对应行，只改进度条宽度、状态文字和明细，"
           "不重绘整页，因此正在输入的表单不会被冲掉。取消按钮 POST 到 /tasks/<id>/cancel，再触发一次轮询。"
           "自检脚本把模板要求拆成 10 条可执行断言：字数、章节编号、图注/表注连续、图注数与插图数一致、"
           "重复长段落、彩色文字、表格缩进与居中、图片段落行距、页码域、缺图占位，"
           "结果同时打印并写入 docs/排版检查.txt，任何一条不过就以非零码退出，方便接进流程。"
           "查重只比对正文段落，并跳过 Consolas 字体的代码块——否则两处相同的示例代码会被误判成抄袭自己。")
    h(doc, "5.7.3  关键实现", 3)
    code(doc, '''function paint(t){
  var row = document.querySelector('.row[data-id="' + t.id + '"]');
  row.querySelector('[data-role=state]').textContent = t.state;
  row.querySelector('[data-role=bar]').style.width = (t.progress * 100).toFixed(0) + '%';
  var d = t.instance + '｜方法 ' + t.method;
  if (t.state === 'done') d += '｜里程 ' + t.distance + '｜车辆 ' + t.vehicles;
  row.querySelector('[data-role=detail]').textContent = d;
}
setInterval(function(){ fetch('/tasks.json').then(r => r.json()).then(ts => ts.forEach(paint)); }, 2000);

# 自检：图注允许附录字母编号（图 B-1），查重跳过代码段
fig_caps = [t for t in texts if t.startswith("图 ") or t.startswith("图 B-")]
if any((r.font.name or "") == "Consolas" for r in p.runs):
    code_lines.add(p.text.strip())
''')
    h(doc, "5.7.4  运行效果", 3)
    p(doc, "两份最终报告的自检结果都是 10/10 通过：任绪锋约 2.5 万字、470 余段、11 张图、8 张表；"
           "苍韵同约 2.3 万字、440 余段、12 张图、8 张表；重复长段落 0 处、彩色文字 0 处、缺图占位 0 处，"
           "页码域已插入，表格居中且首行缩进为 0，图片段落均为 1.0 倍行距。"
           "过程中自检脚本自己也有三个误报：附录图号是“图 B-1”不带数字章号、两处代码块被当成重复段落、"
           "页码域在页脚里而脚本只看了正文——都改掉后才得到上面的结果。"
           "这一步把“交稿前逐项翻 Word”变成了跑一条命令，后续改稿也能随时复查。")


def main() -> None:
    from report_base import base_doc

    OUT.mkdir(parents=True, exist_ok=True)
    for name, sid in PEOPLE.items():
        fn = ch5_ren if name == "任绪锋" else ch5_cang
        path = OUT / f"报告-前五章-{name}-{sid}.docx"
        try:
            build(name, sid, ch5_fn=fn, doc=base_doc(name, sid)).save(str(path))
        except PermissionError:
            print(f"[跳过] {path.name} 正被 Word 占用")
            continue
        d = Document(str(path))
        chars = sum(len(x.text) for x in d.paragraphs)
        print(f"[OK] {path.name}：{len(d.paragraphs)} 段｜正文 {chars} 字｜"
              f"插图 {len(d.inline_shapes)} 张｜表格 {len(d.tables)} 个｜{path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
