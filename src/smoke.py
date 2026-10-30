import sys, time
sys.path.insert(0, ".")
from instance import parse_solomon
from aco import ACOConfig, solve_aco
from solution import evaluate, nearest_neighbor
from scene import Scene
from db import connect

inst = parse_solomon("data/solomon/100/c101.txt")
print("M1 解析 :", inst.describe())

routes = nearest_neighbor(inst, allow_time_window_violation=False)
ev = evaluate(inst, routes)
print("M1 评价 :", ev["total_distance"], "| 车", ev["vehicles"], "| 可行", ev["feasible"])

t0 = time.time()
res = solve_aco(inst, ACOConfig(max_iter=5, seed=1))
print("M2 求解 : %.2f 里 | 车 %d | 可行 %s | %.1fs" % (res["distance"], res["vehicles"], res["feasible"], time.time()-t0))

s = Scene.load("校园配送-软时间窗")
i2 = s.load_instance()
print("M5 场景 : speed=%.1f tw_hard=%s 优先级=%d 个" % (i2.speed, i2.tw_hard, len(i2.priority)))

for b in ("sqlite", "mysql"):
    try:
        db = connect(b)
        n = db.query("SELECT COUNT(*) FROM experiment")[0][0]
        m = db.query("SELECT COUNT(*) FROM solution")[0][0]
        print("DB %-6s: OK  experiment %d 行  solution %d 行" % (b, n, m))
        db.close()
    except SystemExit as e:
        print("DB %-6s: 不可用 -> %s" % (b, str(e).splitlines()[0][:60]))
