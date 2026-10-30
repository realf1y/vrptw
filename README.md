# 基于改进蚁群算法的带时间窗配送路径优化系统（v1.0）

面向《软件工程系统实训》的课程项目。输入带时间窗的配送算例，用改进蚁群算法求解车辆路线，
并配套可视化、批量实验、多车场/多车型、动态重优化、成本碳排多目标、订单导入、任务监控与报表导出。

## 目录结构

    src/        程序源码（可直接运行）+ data/ 算例 + scenes/ 场景 + results/ 结果
    docs/       综合报告、周记、课程模板、开发文档
    sql/        MySQL 建库脚本

## 运行环境

- Python 3.10 及以上（开发与测试使用 3.14.3）
- 安装依赖：pip install -r requirements.txt
- 数据库：默认 SQLite（零配置）；可选 MySQL 9.x（脚本见 sql/mysql_vrptw.sql）

## 快速开始

    cd src
    python demo.py                                      # 数据层自检
    python run_aco.py data/solomon/100/c101.txt 1       # 单算例求解
    python viz.py data/solomon/100/c101.txt --iters=30  # 路线图/收敛曲线/HTML 报告
    python report.py 100 10                             # 生成 md/csv/html/xlsx 报表
    python store.py status                              # 查看数据库
    python webapp.py                                    # Web 界面 127.0.0.1:5000

## 数据说明

- data/solomon 下的 25 / 50 / 100 三个目录：168 个 Solomon 标准算例（每个规模 56 个）
- data/solomon_bks.csv 与 .json：56 个算例的已知最优解（用于计算 gap）
- data/orders_template.xlsx：订单导入模板
- scenes：3 个预设场景（标准硬时间窗 / 校园软时间窗 / 雨天慢速）

## 模块清单（M1–M14）

基础六个：M1 算例与数据管理、M2 算法引擎、M3 路线可视化与 Web 交互、M4 实验管理与统计、
M5 约束与场景配置（含多车场/多车型）、M6 方案对比与报表（含 Excel 导出）。

扩展八个：M7 动态重优化、M8 运营 KPI 看板、M9 成本/碳排多目标、M10 成本碳排对比页、
M11 订单 Excel 导入、M12 用户与项目空间、M13 任务监控、M14 排版自检。

## 已知限制

- 动态重优化采用插单后局部重排，非全局重求解
- 任务监控用线程（Web）与独立进程（命令行），未做分布式任务队列
- 多车场按每条路线选择最优仓库处理，未考虑仓库容量约束
