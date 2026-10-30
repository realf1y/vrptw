# -*- coding: utf-8 -*-
"""M3：Web 交互界面（Flask）

启动：python webapp.py   然后浏览器打开 http://127.0.0.1:5000
"""
import tempfile
from pathlib import Path

from flask import Flask, redirect, render_template_string, request, url_for

from aco import ACOConfig, solve_aco
from compare import build_page as build_compare_page, scheme_summary
from dashboard import kpi_summary, render_html
from multiobjective import presets as mo_presets, solve_weighted
from orders import OrderImportError, import_xlsx
from projects import ProjectError, create as create_project, describe as describe_project
from projects import list_projects, load as load_project
from tasks import cancel as cancel_task, list_tasks, load as load_task, submit as submit_task
from instance import parse_solomon
from viz import SvgCanvas, draw_route_map

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "solomon" / "100"

app = Flask(__name__)

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>配送路径优化</title>
<style>
body{font-family:Microsoft YaHei,SimHei,sans-serif;margin:0;background:#f5f6f8;color:#222}
header{background:#1f2d3d;color:#fff;padding:16px 24px}
header h1{margin:0;font-size:19px}
.wrap{max-width:1080px;margin:18px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:16px;
      box-shadow:0 1px 3px rgba(0,0,0,.08)}
label{display:inline-block;margin:0 12px 8px 0;font-size:13px;color:#555}
input,select{padding:5px 8px;border:1px solid #cfd8dc;border-radius:5px;font-size:13px;width:86px}
select{width:150px}
button{padding:8px 18px;background:#2980b9;color:#fff;border:0;border-radius:6px;font-size:14px;cursor:pointer}
button:hover{background:#1f6391}
.kpi{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px}
.k{background:#f8fbfd;border:1px solid #d6e3ee;border-radius:8px;padding:10px 14px;min-width:140px}
.k .t{font-size:12px;color:#7f8c8d}.k .v{font-size:18px;font-weight:600;margin-top:4px}
</style></head><body>
<header><h1>带时间窗配送路径优化 · 在线求解
<a href="/dashboard" style="float:right;color:#9fc7e8;font-size:13px;font-weight:400;text-decoration:none;margin-left:16px">运营 KPI 看板 →</a>
<a href="/compare" style="float:right;color:#9fc7e8;font-size:13px;font-weight:400;text-decoration:none;margin-left:16px">成本/碳排对比 →</a>
<a href="/import" style="float:right;color:#9fc7e8;font-size:13px;font-weight:400;text-decoration:none;margin-left:16px">订单导入 →</a>
<a href="/projects" style="float:right;color:#9fc7e8;font-size:13px;font-weight:400;text-decoration:none;margin-left:16px">项目空间 →</a>
<a href="/tasks" style="float:right;color:#9fc7e8;font-size:13px;font-weight:400;text-decoration:none;margin-left:16px">任务监控 →</a></h1></header>
<div class="wrap">
<div class="card">
<form method="post" action="/run">
  <label>算例 <select name="inst">{% for f in files %}<option {% if f == cur %}selected{% endif %}>{{ f }}</option>{% endfor %}</select></label>
  <label>α <input name="alpha" value="{{ alpha }}"></label>
  <label>β <input name="beta" value="{{ beta }}"></label>
  <label>ρ <input name="rho" value="{{ rho }}"></label>
  <label>迭代 <input name="iters" value="{{ iters }}"></label>
  <button type="submit">开始优化</button>
</form>
</div>
{% if result %}<div class="card">{{ result|safe }}</div>{% endif %}
</div></body></html>"""


@app.route("/")
def index():
    files = sorted(p.name for p in DATA.glob("*.txt"))
    return render_template_string(PAGE, files=files, cur="c101.txt",
                                  alpha="1.0", beta="3.0", rho="0.1", iters="30", result=None)


@app.route("/run", methods=["POST"])
def run():
    files = sorted(p.name for p in DATA.glob("*.txt"))
    name = request.form.get("inst", "c101.txt")
    alpha = float(request.form.get("alpha", 1.0))
    beta = float(request.form.get("beta", 3.0))
    rho = float(request.form.get("rho", 0.1))
    iters = max(1, min(int(request.form.get("iters", 30)), 200))

    inst = parse_solomon(DATA / name)
    res = solve_aco(inst, ACOConfig(alpha=alpha, beta=beta, rho=rho, max_iter=iters, seed=1))

    svg = SvgCanvas(760, 560)
    draw_route_map(svg, inst, res["routes"], f"{inst.name} · 改进版",
                   f"里程 {res['distance']:.2f}｜车辆 {res['vehicles']}")
    kpi = (f'<div class="kpi">'
           f'<div class="k"><div class="t">总里程</div><div class="v">{res["distance"]:.2f}</div></div>'
           f'<div class="k"><div class="t">车辆数</div><div class="v">{res["vehicles"]}</div></div>'
           f'<div class="k"><div class="t">可行</div><div class="v">{"是" if res["feasible"] else "否"}</div></div>'
           f'<div class="k"><div class="t">用时</div><div class="v">{res["seconds"]}s</div></div>'
           f'</div>')
    return render_template_string(PAGE, files=files, cur=name, alpha=alpha, beta=beta,
                                  rho=rho, iters=iters, result=kpi + svg.to_string())


@app.route("/dashboard")
def dashboard():
    name = request.args.get("inst", "c101.txt")
    iters = max(1, min(int(request.args.get("iters", 30)), 200))
    inst = parse_solomon(DATA / name)
    res = solve_aco(inst, ACOConfig(max_iter=iters, seed=1))
    kpi = kpi_summary(inst, res["routes"])
    page = render_html(inst, res["routes"], "配送运营 KPI 看板",
                       f"{inst.name}｜里程 {res['distance']:.2f}｜车辆 {res['vehicles']}"
                       f"｜求解 {res['seconds']}s", kpi)
    page = page.replace("</header>",
                        '<div style="padding:0 28px 14px"><a href="/" '
                        'style="color:#cfe3f5;font-size:12.5px;text-decoration:none">← 返回在线求解</a>'
                        "</div></header>")
    return page


_COMPARE_CACHE = {}


@app.route("/compare")
def compare_page():
    name = request.args.get("inst", "r101.txt")
    iters = max(5, min(int(request.args.get("iters", 20)), 60))
    key = (name, iters)
    if key not in _COMPARE_CACHE:
        inst = parse_solomon(DATA / name)
        schemes = []
        for nm, w in mo_presets().items():
            res = solve_weighted(inst, nm, w, iters=iters, seed=1)
            schemes.append(scheme_summary(inst, res["routes"], nm))
        _COMPARE_CACHE[key] = build_compare_page(
            inst, schemes, "成本与碳排对比",
            f"{inst.name}｜{iters} 代｜成本优先 / 均衡 / 低碳优先")
    page = _COMPARE_CACHE[key].replace("</header>",
        '<div style="padding:0 28px 14px"><a href="/" '
        'style="color:#cfe3f5;font-size:12.5px;text-decoration:none">← 返回在线求解</a>'
        "</div></header>")
    return page


IMPORT_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>订单 Excel 导入</title>
<style>
body{font-family:Microsoft YaHei,SimHei,sans-serif;margin:0;background:#f5f6f8;color:#222}
header{background:#1f2d3d;color:#fff;padding:16px 24px}header h1{margin:0;font-size:19px}
header a{color:#9fc7e8;font-size:13px;text-decoration:none;margin-right:18px}
.wrap{max-width:1000px;margin:18px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
label{display:inline-block;margin:0 14px 8px 0;font-size:13px;color:#555}
input{padding:5px 8px;border:1px solid #cfd8dc;border-radius:5px;font-size:13px}
button{padding:8px 18px;background:#2980b9;color:#fff;border:0;border-radius:6px;font-size:14px;cursor:pointer}
.err{color:#c0392b;font-size:13px}.ok{color:#1e8449;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:10px}
th,td{border-bottom:1px solid #eef1f4;padding:5px 6px;text-align:center}
th{background:#f7f9fb}
</style></head><body>
<header><h1>订单 Excel 导入<a href="/" style="float:right">← 返回在线求解</a></h1></header>
<div class="wrap">
<div class="card">
<form method="post" enctype="multipart/form-data">
  <label>选择 xlsx <input type="file" name="xlsx" accept=".xlsx"></label>
  <label>载重 <input name="capacity" value="{{ cap }}" size="6"></label>
  <label>迭代 <input name="iters" value="{{ iters }}" size="4"></label>
  <button type="submit">上传并求解</button>
</form>
<div class="err" style="margin-top:8px">表头至少要有：经度(x)、纬度(y)、需求(demand)；可选 最早/最晚/服务/类型。模板：<code>python orders.py template</code></div>
</div>
{% if result %}<div class="card">{{ result|safe }}</div>{% endif %}
</div></body></html>"""


PROJECTS_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>项目空间</title>
<style>
body{font-family:Microsoft YaHei,SimHei,sans-serif;margin:0;background:#f5f6f8;color:#222}
header{background:#1f2d3d;color:#fff;padding:16px 24px}header h1{margin:0;font-size:19px}
header a{color:#9fc7e8;font-size:13px;text-decoration:none;margin-right:18px}
.wrap{max-width:960px;margin:18px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
label{display:inline-block;margin:0 12px 8px 0;font-size:13px;color:#555}
input{padding:5px 8px;border:1px solid #cfd8dc;border-radius:5px;font-size:13px}
button{padding:8px 18px;background:#2980b9;color:#fff;border:0;border-radius:6px;font-size:14px;cursor:pointer}
.p{border-bottom:1px solid #eef1f4;padding:9px 2px;font-size:13.5px}
.p b{color:#1f3a5f}.p .meta{color:#7b8794;font-size:12px;margin-left:8px}
.err{color:#c0392b;font-size:13px}
</style></head><body>
<header><h1>项目空间<a href="/" style="float:right">← 返回在线求解</a></h1></header>
<div class="wrap">
<div class="card"><form method="post" action="/projects">
  <label>项目名 <input name="name" size="16"></label>
  <label>负责人 <input name="owner" size="10"></label>
  <label>备注 <input name="note" size="24"></label>
  <button type="submit">新建项目</button>
</form>{% if error %}<div class="err">{{ error }}</div>{% endif %}</div>
<div class="card"><h3 style="margin:0 0 8px;font-size:14px">已有项目</h3>
{% for p in items %}<div class="p"><b>{{ p.name }}</b><span class="meta">负责人 {{ p.owner or '未填' }}｜算例 {{ p.instances|length }}｜场景 {{ p.scenes|length }}｜实验 {{ p.experiments|length }}｜{{ p.created_at }}</span><div class="meta">{{ p.note }}</div></div>{% endfor %}
{% if not items %}<div class="meta">还没有项目</div>{% endif %}
</div></div></body></html>"""


@app.route("/import", methods=["GET", "POST"])
def import_orders():
    cap = request.form.get("capacity", "200")
    iters = request.form.get("iters", "30")
    if request.method == "GET":
        return render_template_string(IMPORT_PAGE, cap=cap, iters=iters, result="")
    f = request.files.get("xlsx")
    if f is None or not f.filename:
        return render_template_string(IMPORT_PAGE, cap=cap, iters=iters,
                                      result='<div class="err">请选择 .xlsx 文件</div>')
    tmp = Path(tempfile.gettempdir()) / ("vrptw_" + Path(f.filename).name)
    f.save(str(tmp))
    try:
        inst, out = import_xlsx(tmp, HERE / "data" / "solomon" / "orders" /
                                (Path(f.filename).stem + ".txt"),
                                capacity=float(cap))
    except (OrderImportError, ValueError) as e:
        return render_template_string(IMPORT_PAGE, cap=cap, iters=iters,
                                      result='<div class="err">导入失败：%s</div>' % e)
    res = solve_aco(inst, ACOConfig(max_iter=max(1, min(int(iters), 100)), seed=1))
    svg = SvgCanvas(720, 520)
    draw_route_map(svg, inst, res["routes"], inst.name,
                   "里程 %.2f｜车辆 %d" % (res["distance"], res["vehicles"]))
    rows = "".join("<tr><td>%s</td><td>%.0f</td><td>%.0f</td><td>%.0f</td><td>%.0f</td><td>%.0f</td></tr>"
                   % (c.name if hasattr(c, "name") else c.id, c.x, c.y, c.demand, c.ready, c.due)
                   for c in inst.customers[1:11])
    table = ("<table><thead><tr><th>客户</th><th>x</th><th>y</th><th>需求</th><th>最早</th><th>最晚</th>"
             "</tr></thead><tbody>%s</tbody></table>" % rows)
    result = ('<div class="ok">导入成功：%s｜里程 %.2f｜车辆 %d｜用时 %.1fs｜已保存 %s</div>'
              % (inst.describe(), res["distance"], res["vehicles"], res["seconds"], out.name))
    result += svg.to_string() + table
    return render_template_string(IMPORT_PAGE, cap=cap, iters=iters, result=result)


@app.route("/projects", methods=["GET", "POST"])
def projects_page():
    error = ""
    if request.method == "POST":
        try:
            create_project(request.form.get("name", ""), request.form.get("owner", ""),
                           request.form.get("note", ""))
            return redirect(url_for("projects_page"))
        except ProjectError as e:
            error = str(e)
    items = list_projects()
    return render_template_string(PROJECTS_PAGE, items=items, error=error)


TASKS_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>任务监控</title>
<style>
body{font-family:Microsoft YaHei,SimHei,sans-serif;margin:0;background:#f5f6f8;color:#222}
header{background:#1f2d3d;color:#fff;padding:16px 24px}header h1{margin:0;font-size:19px}
header a{color:#9fc7e8;font-size:13px;text-decoration:none;margin-right:18px}
.wrap{max-width:1000px;margin:18px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
label{display:inline-block;margin:0 12px 8px 0;font-size:13px;color:#555}
input,select{padding:5px 8px;border:1px solid #cfd8dc;border-radius:5px;font-size:13px}
button{padding:8px 16px;background:#2980b9;color:#fff;border:0;border-radius:6px;font-size:13.5px;cursor:pointer}
.row{border-bottom:1px solid #eef1f4;padding:10px 2px;font-size:13px}
.row .id{font-family:Consolas,monospace;color:#5b6770;font-size:12px}
.bar{height:8px;background:#e8eef3;border-radius:4px;margin-top:6px;overflow:hidden}
.bar i{display:block;height:100%;background:#2980b9;width:0}
.st{font-weight:600;margin-left:8px}
.st.done{color:#1e8449}.st.failed{color:#c0392b}.st.cancelled{color:#8a8f95}.st.running{color:#2980b9}
.meta{color:#7b8794;font-size:12px;margin-top:3px}
</style></head><body>
<header><h1>任务监控<a href="/" style="float:right">← 返回在线求解</a></h1></header>
<div class="wrap">
<div class="card"><form method="post" action="/tasks">
  <label>算例 <select name="inst">{% for f in files %}<option {% if f == cur %}selected{% endif %}>{{ f }}</option>{% endfor %}</select></label>
  <label>方法 <select name="method"><option value="improved">改进版</option><option value="baseline">基线</option></select></label>
  <label>迭代 <input name="iters" value="40" size="4"></label>
  <button type="submit">提交任务</button>
</form>
<div class="meta">任务在后台运行，本页每 2 秒自动刷新进度。</div>
</div>
<div class="card" id="list">
{% for t in items %}
<div class="row" data-id="{{ t.id }}">
  <span class="id">{{ t.id }}</span><span class="st {{ t.state }}" data-role="state">{{ t.state }}</span>
  <span style="float:right">{{ t.iter }}/{{ t.total }}</span>
  <div class="bar"><i data-role="bar" style="width:{{ (t.progress*100)|round(0) }}%"></i></div>
  <div class="meta"><span data-role="detail">{{ t.instance }}｜方法 {{ t.method }}</span>
    {% if t.state in ['queued','running'] %}<button style="padding:3px 10px;font-size:12px;margin-left:8px" onclick="cancelTask('{{ t.id }}')">取消</button>{% endif %}
  </div>
</div>
{% endfor %}
{% if not items %}<div class="meta">还没有任务</div>{% endif %}
</div></div>
<script>
function paint(t){
  var row=document.querySelector('.row[data-id="'+t.id+'"]');
  if(!row){location.reload();return;}
  row.querySelector('[data-role=state]').textContent=t.state;
  row.querySelector('[data-role=state]').className='st '+t.state;
  row.querySelector('[data-role=bar]').style.width=(t.progress*100).toFixed(0)+'%';
  var d=t.instance+'｜方法 '+t.method;
  if(t.state==='done'){d+='｜里程 '+t.distance+'｜车辆 '+t.vehicles+'｜'+t.seconds+'s';}
  if(t.state==='failed'){d+='｜错误：'+t.error;}
  row.querySelector('[data-role=detail]').textContent=d;
}
function poll(){fetch('/tasks.json').then(function(r){return r.json();}).then(function(ts){ts.forEach(paint);}).catch(function(){});}
function cancelTask(id){fetch('/tasks/'+id+'/cancel',{method:'POST'}).then(poll);}
setInterval(poll,2000);
</script></body></html>"""


@app.route("/tasks", methods=["GET", "POST"])
def tasks_page():
    files = sorted(p.name for p in DATA.glob("*.txt"))
    if request.method == "POST":
        name = request.form.get("inst", "c101.txt")
        submit_task(str(DATA / name), int(request.form.get("iters", 40)),
                    request.form.get("method", "improved"))
        return redirect(url_for("tasks_page"))
    return render_template_string(TASKS_PAGE, files=files, cur="c101.txt", items=list_tasks(20))


@app.route("/tasks.json")
def tasks_json():
    return {"tasks": list_tasks(20)}


@app.route("/tasks/<tid>/cancel", methods=["POST"])
def tasks_cancel(tid):
    try:
        cancel_task(tid)
    except FileNotFoundError:
        pass
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
