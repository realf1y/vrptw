# -*- coding: utf-8 -*-
"""M14｜全文排版与查重自检（Report Lint）

定稿前把模板要求变成可执行的检查，避免“打开 Word 一眼看不出问题、交上去被打回”：

    1. 正文字数（不含封面表）是否达到 15000 字
    2. 章节编号是否连续（第 X 章、X.Y、X.Y.Z）
    3. 图/表编号是否按章连续，图注数量与插图数量是否匹配
    4. 文内重复段落（>=40 字）——自查“复制粘贴重复”
    5. 是否还有彩色文字（模板要求全文黑色）
    6. 表格是否居中、单元格首行缩进是否为 0
    7. 图片所在段落是否 1.0 倍行距（固定行距会把图裁掉）
    8. 是否插入了页码域（PAGE）
    9. 是否还有“（缺图：xxx）”占位

用法
----
    python check_report.py                              # 检查两份最终报告
    python check_report.py --file docs/xxx.docx --out docs/排版检查.txt
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn

HERE = Path(__file__).resolve().parent
DOCS = HERE / "docs"
DEFAULT_FILES = [DOCS / "报告-最终-任绪锋-2318140115.docx",
                 DOCS / "报告-最终-苍韵同-2318140111.docx"]

CN_NUM = "一二三四五六七八九十"


def _text(doc) -> list[str]:
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]


def _heading_level(p) -> int:
    try:
        style = p.style.name
    except AttributeError:
        return 0
    m = re.match(r"Heading (\d)", style or "")
    return int(m.group(1)) if m else 0


def check_file(path: Path) -> tuple[list[tuple[str, bool, str]], dict]:
    doc = Document(str(path))
    paras = doc.paragraphs
    texts = _text(doc)
    body_chars = sum(len(t) for t in texts)
    results: list[tuple[str, bool, str]] = []

    # 1 字数
    results.append(("正文字数 ≥ 15000", body_chars >= 15000, "%d 字" % body_chars))

    # 2 章节编号
    chapter_no, sub_no, problems = 0, 0, []
    for p in paras:
        t = p.text.strip()
        m = re.match(r"^第([一二三四五六七八九十]+)章", t)
        if m and _heading_level(p) == 1:
            idx = CN_NUM.find(m.group(1)) + 1
            if idx != chapter_no + 1:
                problems.append("章号跳号：%s" % t)
            chapter_no, sub_no = idx, 0
            continue
        m = re.match(r"^(\d+)\.(\d+)\s", t)
        if m and _heading_level(p) in (2, 3):
            if int(m.group(1)) != chapter_no:
                problems.append("节号与章不符：%s" % t)
            if _heading_level(p) == 2:
                if int(m.group(2)) != sub_no + 1:
                    problems.append("二级节号跳号：%s" % t)
                sub_no = int(m.group(2))
    results.append(("章节编号连续", not problems, "；".join(problems[:3]) or "共 %d 章" % chapter_no))

    # 3 图表编号
    fig_caps = [t for t in texts if re.match(r"^图\s*[0-9A-Za-z]+-\d+", t)]
    tab_caps = [t for t in texts if re.match(r"^表\s*[0-9A-Za-z]+-\d+", t)]
    bad = []
    for prefix, caps in (("图", fig_caps), ("表", tab_caps)):
        last_ch, last_no = 0, 0
        for c in caps:
            m = re.match(r"^%s\s*([0-9A-Za-z]+)-(\d+)" % prefix, c)
            if not m.group(1).isdigit():
                continue
            ch, no = int(m.group(1)), int(m.group(2))
            if ch == last_ch and no != last_no + 1:
                bad.append("%s 编号不连续：%s" % (prefix, c))
            if ch < last_ch:
                bad.append("%s 章序倒退：%s" % (prefix, c))
            last_ch, last_no = ch, no
    figs = len(doc.inline_shapes)
    results.append(("图注/表注编号连续", not bad, "；".join(bad[:3]) or "图 %d、表 %d" % (len(fig_caps), len(tab_caps))))
    results.append(("图注数与插图数匹配", len(fig_caps) == figs, "图注 %d / 插图 %d" % (len(fig_caps), figs)))

    # 4 重复段落
    code_lines = set()
    for p in paras:
        if any((r.font.name or "") == "Consolas" for r in p.runs):
            code_lines.add(p.text.strip())
    seen, dup = {}, []
    for t in texts:
        if len(t) < 40 or t in code_lines:
            continue
        seen[t] = seen.get(t, 0) + 1
        if seen[t] == 2:
            dup.append(t[:24] + "…")
    results.append(("无重复长段落", not dup, "；".join(dup[:3]) or "0 处"))

    # 5 彩色文字
    colored = []
    for p in paras:
        for r in p.runs:
            color = r.font.color
            if color is None or color.rgb is None:
                continue
            rgb = str(color.rgb).upper()
            if rgb not in {"000000", "FFFFFF"}:
                colored.append((rgb, r.text[:12]))
    results.append(("无彩色文字", not colored, "；".join("%s:%s" % c for c in colored[:3]) or "0 处"))

    # 6 表格格式（跳过封面表）
    bad_tbl = 0
    for tbl in doc.tables[1:]:
        for row in tbl.rows:
            for cell in row.cells:
                for par in cell.paragraphs:
                    ind = par.paragraph_format.first_line_indent
                    if ind is not None and ind.pt != 0:
                        bad_tbl += 1
                    if par.alignment not in (WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT):
                        bad_tbl += 1
    results.append(("表格居中且无首行缩进", bad_tbl == 0, "异常单元格 %d" % bad_tbl))

    # 7 图片段落行距
    bad_img = 0
    for p in paras:
        if p._p.findall(".//" + qn("w:drawing")):
            if p.paragraph_format.line_spacing != 1.0:
                bad_img += 1
    results.append(("图片段落 1.0 倍行距", bad_img == 0, "异常 %d 段" % bad_img))

    # 8 页码域
    xml = doc.element.xml
    for sec in doc.sections:
        for part in (sec.header, sec.footer, sec.first_page_header, sec.first_page_footer):
            try:
                xml += part._element.xml
            except Exception:
                continue
    has_page = ("PAGE" in xml) and ("fldSimple" in xml or "instrText" in xml)
    results.append(("含页码域（PAGE）", has_page, "已插入" if has_page else "未找到"))

    # 9 缺图占位
    missing = [t for t in texts if "（缺图：" in t or t.startswith("（缺图")]
    results.append(("无缺图占位", not missing, "；".join(missing[:2]) or "0 处"))

    stats = {"chars": body_chars, "figs": figs, "tables": len(doc.tables),
             "paras": len(paras)}
    return results, stats


def render(path: Path, results, stats) -> str:
    lines = ["排版与查重自检：" + path.name, "=" * 46]
    ok = sum(1 for _n, good, _d in results if good)
    for name, good, detail in results:
        lines.append(("[PASS] " if good else "[FAIL] ") + name + "：" + detail)
    lines.append("-" * 46)
    lines.append("通过 %d / %d｜正文 %d 字｜段落 %d｜图 %d｜表 %d"
                 % (ok, len(results), stats["chars"], stats["paras"], stats["figs"], stats["tables"]))
    return chr(10).join(lines)


def main() -> None:
    args = sys.argv[1:]
    files = list(DEFAULT_FILES)
    out = DOCS / "排版检查.txt"
    i = 0
    while i < len(args):
        if args[i] == "--file" and i + 1 < len(args):
            files = [Path(args[i + 1])]
            i += 2
        elif args[i] == "--out" and i + 1 < len(args):
            out = Path(args[i + 1])
            i += 2
        else:
            i += 1

    all_lines, failed = [], 0
    for f in files:
        if not f.exists():
            print("找不到：" + str(f))
            failed += 1
            continue
        results, stats = check_file(f)
        text = render(f, results, stats)
        print(text)
        print()
        all_lines.append(text)
        failed += sum(1 for _n, good, _d in results if not good)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(chr(10).join(all_lines) + chr(10), encoding="utf-8")
    print("检查结果已写入：" + str(out))
    raise SystemExit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
