# -*- coding: utf-8 -*-
"""M5｜约束与场景配置（Constraint & Scene Configuration）

一个「场景」= 一份 JSON，用来描述同一套算法在不同业务下的假设。这样换业务不用改代码：

    instance       算例文件（相对项目目录或绝对路径）
    capacity       载重上限（不填则用算例自带值）
    max_vehicles   车辆数上限（不填则用算例自带值）
    speed          车速：行驶时间 = 距离 / 车速（默认 1.0，即距离当时间用）
    tw_mode        hard = 硬时间窗（违反即不可行）；soft = 软时间窗（只罚分）
    lambda_tw      软时间窗的惩罚系数
    priority       客户优先级 {客户号: 权重}：晚到高优先级客户，惩罚按权重放大
    aco            算法参数模板（覆盖 ACOConfig 的任意字段）

用法::

    python scene.py new campus-c101 --instance data/solomon/100/c101.txt --capacity 180 --speed 1.2 --tw soft
    python scene.py list
    python scene.py show campus-c101
    python scene.py apply campus-c101 --iters=40        # 按这个场景跑一遍改进版算法
    python scene.py rm campus-c101
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aco import ACOConfig, solve_aco
from instance import parse_solomon
from solution import evaluate

HERE = Path(__file__).resolve().parent
SCENE_DIR = HERE / "scenes"


@dataclass
class Scene:
    name: str
    instance: str
    capacity: float | None = None
    max_vehicles: int | None = None
    speed: float = 1.0
    tw_mode: str = "hard"                    # hard | soft
    lambda_tw: float = 10.0
    priority: dict = field(default_factory=dict)
    depots: list = field(default_factory=list)          # 多车场：仓库的客户 id 列表
    vehicle_types: list = field(default_factory=list)   # 多车型：[{name,capacity,count,fixed_cost}]
    aco: dict = field(default_factory=dict)
    note: str = ""

    # ---------- 存取 ----------
    def path(self) -> Path:
        return SCENE_DIR / f"{self.name}.json"

    def save(self) -> Path:
        SCENE_DIR.mkdir(parents=True, exist_ok=True)
        self.path().write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2),
                               encoding="utf-8")
        return self.path()

    @classmethod
    def load(cls, name: str) -> "Scene":
        p = SCENE_DIR / f"{name}.json"
        if not p.exists():
            raise FileNotFoundError(f"场景不存在：{p}")
        return cls(**json.loads(p.read_text(encoding="utf-8")))

    # ---------- 应用 ----------
    def instance_path(self) -> Path:
        p = Path(self.instance)
        return p if p.is_absolute() else (HERE / p)

    def load_instance(self):
        inst = parse_solomon(self.instance_path())
        return self.apply(inst)

    def apply(self, inst):
        """把场景里的约束套到算例对象上。"""
        if self.capacity is not None:
            inst.capacity = float(self.capacity)
        if self.max_vehicles is not None:
            inst.vehicle_count = int(self.max_vehicles)
        inst.speed = float(self.speed or 1.0)
        inst.tw_hard = (str(self.tw_mode).lower() != "soft")
        inst.priority = {int(k): float(v) for k, v in (self.priority or {}).items()}
        if self.depots:
            inst.depots = [int(x) for x in self.depots]
        if self.vehicle_types:
            from instance import VehicleType
            inst.vehicle_types = [VehicleType(**vt) for vt in self.vehicle_types]
            inst.capacity = max(t.capacity for t in inst.vehicle_types)
            inst.vehicle_count = sum(t.count for t in inst.vehicle_types)
        return inst

    def aco_config(self, **overrides) -> ACOConfig:
        params = dict(self.aco or {})
        params.update({k: v for k, v in overrides.items() if v is not None})
        if str(self.tw_mode).lower() == "hard":
            params.setdefault("lambda_tw", 1e4)        # 硬时间窗：违约重罚，逼算法找可行解
        else:
            params.setdefault("lambda_tw", float(self.lambda_tw))
        params.setdefault("seed", 1)
        allowed = set(ACOConfig.__dataclass_fields__)
        unknown = [k for k in params if k not in allowed]
        if unknown:
            raise ValueError(f"未知的算法参数：{unknown}")
        return ACOConfig(**params)

    def describe(self) -> str:
        return (f"场景 {self.name}｜算例 {Path(self.instance).name}"
                f"｜载重 {self.capacity if self.capacity is not None else '算例默认'}"
                f"｜车辆上限 {self.max_vehicles if self.max_vehicles is not None else '算例默认'}"
                f"｜车速 {self.speed:g}｜时间窗 {'硬' if self.tw_mode == 'hard' else '软'}"
                f"（λ={self.lambda_tw:g}）"
                + (f"｜优先级客户 {len(self.priority)} 个" if self.priority else "")
                + (f"｜仓库 {len(self.depots)} 个" if self.depots else "")
                + (f"｜车型 {len(self.vehicle_types)} 种" if self.vehicle_types else ""))


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------
def _flag(args: list[str], key: str):
    for i, a in enumerate(args):
        if a == f"--{key}":
            return args[i + 1]
        if a.startswith(f"--{key}="):
            return a.split("=", 1)[1]
    return None


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "help"}:
        print(__doc__)
        return
    cmd = args[0]

    if cmd == "list":
        SCENE_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(SCENE_DIR.glob("*.json"))
        if not files:
            print("（还没有场景，用 scene.py new <名字> 新建）")
        for f in files:
            s = Scene.load(f.stem)
            print("  ", s.describe())
        return

    if cmd == "new":
        name = args[1]
        inst = _flag(args, "instance")
        if not inst:
            raise SystemExit("必须指定 --instance <算例路径>")
        s = Scene(
            name=name,
            instance=inst,
            capacity=float(_flag(args, "capacity")) if _flag(args, "capacity") else None,
            max_vehicles=int(_flag(args, "max-vehicles")) if _flag(args, "max-vehicles") else None,
            speed=float(_flag(args, "speed") or 1.0),
            tw_mode=(_flag(args, "tw") or "hard"),
            lambda_tw=float(_flag(args, "lambda") or 10.0),
            note=_flag(args, "note") or "",
        )
        p = s.save()
        print(f"[OK] 已创建场景：{p}")
        print("   ", s.describe())
        return

    if cmd == "show":
        print(Scene.load(args[1]).describe())
        print("  算法模板：", Scene.load(args[1]).aco or "（未设置，用默认）")
        return

    if cmd == "apply":
        s = Scene.load(args[1])
        inst = s.load_instance()
        iters = _flag(args, "iters")
        cfg = s.aco_config(max_iter=int(iters) if iters else None)
        res = solve_aco(inst, cfg)
        print(s.describe())
        print(f"  结果：里程 {res['distance']:.2f}｜车辆 {res['vehicles']}｜"
              f"可行 {'是' if res['feasible'] else '否'}｜时间窗违反 {res['tw_violation']:.2f}｜"
              f"用时 {res['seconds']}s")
        return

    if cmd == "rm":
        p = SCENE_DIR / f"{args[1]}.json"
        if p.exists():
            p.unlink()
            print("[OK] 已删除", p.name)
        else:
            print("不存在", p.name)
        return

    if cmd == "demo":
        presets = [
            Scene(name="标准场景-硬时间窗", instance="data/solomon/100/c101.txt",
                  note="完全按算例原始约束：硬时间窗、车速 1.0"),
            Scene(name="校园配送-软时间窗", instance="data/solomon/100/c101.txt",
                  tw_mode="soft", lambda_tw=25.0,
                  note="允许小幅迟到，按 λ 罚分；适合业务上“晚到可接受但要付出代价”的场景"),
            Scene(name="雨天慢速-软时间窗", instance="data/solomon/100/c101.txt",
                  speed=0.8, tw_mode="soft", lambda_tw=50.0,
                  note="雨天路滑导致车速降为 0.8，迟到代价加倍"),
        ]
        for s in presets:
            p = s.save()
            print("[OK]", p.name, "|", s.describe())
        return

    raise SystemExit(f"未知命令：{cmd}")


if __name__ == "__main__":
    main()
