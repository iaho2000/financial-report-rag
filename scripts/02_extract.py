# -*- coding: utf-8 -*-
"""02 提取 PDF 正文 + 表格（按行列还原），切块并打标签。
要点（对齐课件第三课 P24/P25/P30）：
  - 表格必须按行列还原，且单独成块、块头带表名 —— 否则"表名留在前一块、本块只剩数字"
  - 每块带四个标签：公司 / 章节 / 页码 / 块序号
用法：python 02_extract.py
输出：data/chunks.jsonl
"""
import json
import os
import re
import sys

import fitz  # PyMuPDF

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE, "data", "pdf")
OUT = os.path.join(BASE, "data", "chunks.jsonl")

CHUNK = 800          # 每块目标字数
OVERLAP = 120        # 重叠字数

SEC_RE = re.compile(r"第\s*([一二三四五六七八九十]+)\s*节\s*([^\n]{0,30})")

# 整行就是章节标题才认。旧版只要求"短行里出现第X节"，结果把正文引用也当成了章节名
# （实测出现 section = "第八节 、五、11、金融工具。"、"第八节 “五、11.金融工具”进行会计处理。"）。
# 三种合法形态：① "第八节 财务报告" ② "第八节"（标题在下一行）
# ③ "第三节 管理层讨论与分析"。判据：标题里不能有句读符号。
HEAD_RE = re.compile(r"^第\s*([一二三四五六七八九十]+)\s*节[\s　]*(.*)$")
HEAD_BAD = set("、，。；：“”\"'（）()〔〕【】.,;:!?/\\|")


def as_heading(txt):
    m = HEAD_RE.match(txt.strip())
    if not m:
        return None
    title = m.group(2).strip()
    if len(title) > 20 or any(ch in HEAD_BAD for ch in title):
        return None
    return f"第{m.group(1)}节 {title}".strip()


def table_to_md(rows):
    """二维列表 -> markdown 表格；丢掉全空行列"""
    rows = [[("" if c is None else str(c).replace("\n", " ").strip()) for c in r] for r in rows]
    rows = [r for r in rows if any(c for c in r)]
    if len(rows) < 2:
        return ""
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    # 删掉全空列：PyMuPDF 常把单元格之间的间隙误判成独立列，
    # 不删的话「释义项|指|释义内容」会被切成 9 列
    keep = [j for j in range(ncol) if any(r[j] for r in rows)]
    if not keep:
        return ""
    rows = [[r[j] for j in keep] for r in rows]
    head, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(head) + " |",
             "|" + "|".join([" --- "] * ncol) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def load_meta():
    mp = os.path.join(BASE, "data", "stocks.json")
    return {d["code"]: d for d in json.load(open(mp, encoding="utf-8"))}


def process_pdf(code, meta):
    path = os.path.join(PDF_DIR, f"{code}_{meta.get('year','2026')}H1.pdf")
    doc = fitz.open(path)
    name = meta.get("name", code)
    # 逐页取"行"，每行知道自己在第几页
    stream = []          # [(page, kind, text)]  kind: 't' 正文行 / 'T' 表格块
    for pno in range(doc.page_count):
        page = doc[pno]
        text = page.get_text("text")
        # 目录页整页跳过：一页里出现 ≥3 个"第X节"必然是目录，
        # 否则目录会把 cur_sec 带偏（实测踩过）
        if len(SEC_RE.findall(text)) >= 3:
            continue
        # ---- 表格：先抽出来，转为 markdown，并带表名 ----
        tbl_texts = []
        try:
            finder = page.find_tables()
            for tb in finder.tables:
                md = table_to_md(tb.extract())
                if not md:
                    continue
                # 表名 = 表格上方最近的一行非空文字
                y0 = tb.bbox[1]
                above = []
                for b in page.get_text("blocks"):
                    if b[3] < y0 - 2 and (b[4] or "").strip():
                        above.append((b[3], b[4].strip().replace("\n", " ")))
                cap = sorted(above)[-1][1][:60] if above else ""
                tbl_texts.append(f"[表格] {cap}\n{md}")
        except Exception:
            pass
        for ln in text.split("\n"):
            if ln.strip():
                stream.append((pno + 1, "t", ln.strip()))
        for t in tbl_texts:
            stream.append((pno + 1, "T", t))
    doc.close()

    # ---- 按字切块，维护"当前章节" ----
    chunks = []
    cur_sec = ""
    buf, buf_pages, buf_sec = [], set(), cur_sec
    size = 0
    cid = 0

    def flush():
        nonlocal buf, buf_pages, size, cid
        if size < 60:
            buf, buf_pages, size = [], set(), 0
            return
        cid += 1
        chunks.append({
            "id": f"{code}-{cid:04d}",
            "code": code, "name": name, "section": buf_sec,
            "page": (min(buf_pages) if buf_pages else 0),
            "page_end": (max(buf_pages) if buf_pages else 0),
            "text": "\n".join(buf),
        })
        # 重叠：保留尾部若干行
        keep, ksize = [], 0
        for ln in reversed(buf):
            if ksize >= OVERLAP:
                break
            keep.insert(0, ln)
            ksize += len(ln)
        buf = keep[:]
        size = ksize
        buf_pages = set(list(buf_pages)[-1:])

    for pno, kind, txt in stream:
        sec = as_heading(txt) if kind == "t" else None
        if sec and "..." not in txt and "…" not in txt:
            if size > 200:          # 章节切换时先落块，块内不跨大节
                flush()
            cur_sec = sec
            buf_sec = cur_sec
        if kind == "T":             # 表格：独立成块，不与正文混
            flush()
            cid += 1
            chunks.append({
                "id": f"{code}-{cid:04d}",
                "code": code, "name": name, "section": cur_sec,
                "page": pno, "page_end": pno, "text": txt,
            })
            continue
        if not buf:
            buf_sec = cur_sec
        buf.append(txt)
        buf_pages.add(pno)
        size += len(txt)
        if size >= CHUNK:
            flush()
    flush()
    return chunks


def main():
    metas = load_meta()
    all_chunks = []
    for code, meta in metas.items():
        if not os.path.exists(os.path.join(PDF_DIR, f"{code}_2026H1.pdf")):
            print(f"跳过 {code} 无PDF")
            continue
        ch = process_pdf(code, meta)
        all_chunks += ch
        pages = max([c["page_end"] for c in ch], default=0)
        tabs = sum(1 for c in ch if c["text"].startswith("[表格]"))
        print(f"{code} {meta.get('name','')}: {len(ch):5d} 块  表格块 {tabs:4d}  页数 {pages}")
    with open(OUT, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"合计 {len(all_chunks)} 块 -> {OUT}")


if __name__ == "__main__":
    main()
