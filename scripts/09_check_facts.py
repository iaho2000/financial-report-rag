# -*- coding: utf-8 -*-
"""09 反查：直接从 PDF 原始页重新抠一遍主要会计数据，和 07 的结果逐项对比。

为什么要单独做这一步：07 读的是 02 切好的块（已经过表格还原 + 章节切分），
如果切块环节出错，07 会"自信地"给出错数字，而下游全都在这个错数字上跑。
这里换一个**文本来源**（PyMuPDF 直接读整页），对不上的就打 MISMATCH。

注意：换的是文本来源，不是算法——同一套"关键词后面跟两个数"的读法。
它能抓住切块/表格还原的错，抓不住读法本身的错（读法本身的坑在 07 的注释里）。

用法：python 09_check_facts.py
"""
import glob
import json
import os
import re

import pymupdf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "out")

NUM = r"[-\d][\d,]*\.?\d*"


def loose(kw):
    return r"\s*".join(re.escape(ch) for ch in kw)


UNIT = r"(?:\s*[（(]\s*元\s*[）)])?"
ITEMS = {
    "营业收入": loose("营业收入") + UNIT,
    "归母净利润": loose("归属于上市公司股东的净利润") + UNIT,
    "扣非净利润": loose("归属于上市公司股东的扣除非经常性损益的净利润") + UNIT,
    "经营现金流": loose("经营活动产生的现金流量净额") + UNIT,
}


def flatten(t):
    t = t.replace("|", " ")
    t = re.sub(r"[ \t　]+", " ", t)
    return re.sub(r"\s*\n\s*", " ", t)


def grab(txt, pattern):
    m = re.search(pattern + r"[^\d\-]{0,40}(" + NUM + r")[^\d\-]{0,40}(" + NUM + r")",
                  txt)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def main():
    facts = json.load(open(os.path.join(OUT, "facts.json"), encoding="utf-8"))
    bad = 0
    for code, rec in sorted(facts.items()):
        paths = glob.glob(os.path.join(DATA, "pdf", f"{code}_2026H1.pdf"))
        if not paths:
            print(f"{rec['name']:<8} 无 PDF")
            continue
        doc = pymupdf.open(paths[0])
        # 挑"主要会计数据"那张表所在页。两个坑：
        #  ① 管理层讨论与分析里也会出现同样的句子（"上半年实现归母净利润4.47亿元"），
        #     按"含关键词的第一页"挑会挑到它——所以要求同时出现表头
        #     「本报告期」「上年同期」；
        #  ② 表格单元格窄，关键词会被折成"净利 润"，用死的字符串判断找不到页
        #     （锡装就因此整页没找到）——所以用 loose() 判断。
        page_txt = ""
        need = re.compile(loose("归属于上市公司股东的净利润"))
        for pno in range(min(16, len(doc))):
            t = flatten(doc[pno].get_text())
            if "本报告期" in t and "上年同期" in t and need.search(t):
                page_txt = t
                break
        doc.close()
        line, diffs = [], []
        for k, pat in ITEMS.items():
            raw = grab(page_txt, pat)
            got = rec.get(k)
            ok = (raw is None and got is None) or (
                raw is not None and got is not None and abs(raw - got) < 1)
            line.append(f"{k}={'OK' if ok else 'X'}")
            if not ok:
                diffs.append(f"{k}: 原始页={raw} 07={got}")
        if diffs:
            bad += 1
            print(f"{rec['name']:<8} {' '.join(line)}")
            for d in diffs:
                print("        ", d)
        else:
            print(f"{rec['name']:<8} {' '.join(line)}")
    print(f"\n对不上 {bad} / {len(facts)} 家")


if __name__ == "__main__":
    main()
