import shutil
from pathlib import Path

SRC = Path("D:/vrptw")
DST = SRC / "交付-v1.0-2026-10-30"
SKIP_FILES = {"mysql_config.json", "_build_new.py", "_ins.py", "_ins2.py"}
SKIP_DIRS = {"__pycache__", "docs", "交付-v1.0-2026-10-30", "db", "templates"}

n = 0
for p in SRC.rglob("*"):
    rel = p.relative_to(SRC)
    if any(part in SKIP_DIRS for part in rel.parts):
        continue
    if not p.is_file():
        continue
    if p.name in SKIP_FILES or p.suffix == ".log" or p.name.endswith(".err"):
        continue
    if p.suffix not in {".py", ".json", ".csv", ".txt", ".md"} and p.name != "vrptw.db":
        continue
    target = DST / "src" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, target)
    n += 1

nd = 0
D = SRC / "docs"
(DST / "docs" / "周记").mkdir(parents=True, exist_ok=True)
(DST / "docs" / "课程模板").mkdir(parents=True, exist_ok=True)
for f in D.glob("*.docx"):
    shutil.copy2(f, DST / "docs" / f.name); nd += 1
for f in D.glob("*.md"):
    shutil.copy2(f, DST / "docs" / f.name); nd += 1
for f in (D / "周记").glob("*.docx"):
    shutil.copy2(f, DST / "docs" / "周记" / f.name); nd += 1
for f in (D / "课程模板").glob("*.*"):
    shutil.copy2(f, DST / "docs" / "课程模板" / f.name); nd += 1

(DST / "sql").mkdir(parents=True, exist_ok=True)
for f in (SRC / "db").glob("*.sql"):
    shutil.copy2(f, DST / "sql" / f.name)

print("代码/数据:", n, "| 文档:", nd)
print("总大小 MB:", round(sum(x.stat().st_size for x in DST.rglob("*") if x.is_file())/1024/1024, 1))
