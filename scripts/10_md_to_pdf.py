# -*- coding: utf-8 -*-
"""10 把 结论.md 转成 结论.pdf（作业要求交「一页结论（PDF）」）。

为什么不装东西：本机已有 `markdown` 库 + Edge 浏览器。
  md --markdown--> html --Edge 无头 --print-to-pdf--> pdf
（LibreOffice / pandoc 这台机器都没有，也没必要为一张纸去装。）

用法：python 10_md_to_pdf.py
输出：结论.pdf（项目根目录）
"""
import os
import subprocess
import sys

import markdown

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
# 默认 结论.md -> 结论.pdf；也可给两个参数转别的：
#   python 10_md_to_pdf.py 一页结论.md 一页结论.pdf
SRC = os.path.join(BASE, sys.argv[1] if len(sys.argv) > 1 else "结论.md")
OUT = os.path.join(BASE, sys.argv[2] if len(sys.argv) > 2 else "结论.pdf")
HTML = os.path.join(BASE, "out", "_" + os.path.splitext(os.path.basename(OUT))[0] + ".html")

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# 字号和边距都往小了压，目的是尽量塞进一页；中文用雅黑，否则 PDF 里会是方块。
CSS = """
@page { size: A4; margin: 12mm 13mm; }
body { font-family: "Microsoft YaHei", "SimHei", sans-serif; font-size: 9.5pt;
       line-height: 1.45; color: #111; }
h1 { font-size: 15pt; margin: 0 0 6pt; border-bottom: 1.2pt solid #333; padding-bottom: 3pt; }
h2 { font-size: 11.5pt; margin: 9pt 0 4pt; }
h3 { font-size: 10pt; margin: 7pt 0 3pt; }
p, li { margin: 2pt 0; }
ul, ol { margin: 3pt 0 3pt 1.1em; padding: 0; }
table { border-collapse: collapse; width: 100%; font-size: 8.5pt; margin: 4pt 0; }
th, td { border: 0.5pt solid #999; padding: 1.5pt 3pt; text-align: left; }
th { background: #eee; }
code { font-family: Consolas, monospace; font-size: 8.5pt; background: #f4f4f4;
       padding: 0 2pt; }
pre { background: #f4f4f4; padding: 4pt 5pt; font-size: 8pt; line-height: 1.3;
      border-left: 2pt solid #bbb; margin: 4pt 0; overflow-wrap: break-word;
      white-space: pre-wrap; }
pre code { background: none; padding: 0; }
blockquote { margin: 4pt 0 4pt 6pt; padding-left: 6pt; border-left: 2pt solid #ccc;
             color: #444; }
hr { border: none; border-top: 0.5pt solid #ccc; margin: 7pt 0; }
a { color: #0645ad; text-decoration: none; }
"""


def main():
    if not os.path.exists(EDGE):
        sys.exit(f"找不到 Edge：{EDGE}")
    md = open(SRC, encoding="utf-8").read()
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    html = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")
    os.makedirs(os.path.dirname(HTML), exist_ok=True)
    open(HTML, "w", encoding="utf-8").write(html)
    print(f"HTML -> {HTML}")

    cmd = [EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={OUT}", "file:///" + HTML.replace("\\", "/")]
    # 不能用 text=True：那会用本机默认编码(GBK)去解 Edge 的输出，
    # 而 Edge 回显的是 UTF-8 的中文路径，读取线程直接抛 UnicodeDecodeError。
    # 报错虽在后台线程、不挡 PDF 生成，但会打印一串 traceback，很难看。
    r = subprocess.run(cmd, capture_output=True, timeout=180)
    if not os.path.exists(OUT):
        print(r.stdout.decode("utf-8", "replace")[-500:],
              r.stderr.decode("utf-8", "replace")[-500:])
        sys.exit("PDF 没生成")
    print(f"PDF  -> {OUT}  {os.path.getsize(OUT)/1024:.0f} KB")

    # 页数：PDF 里数一遍 /Type /Page（不装 PyPDF 也能数）
    raw = open(OUT, "rb").read()
    print(f"页数 ≈ {raw.count(b'/Type /Page') - raw.count(b'/Type /Pages')}")


if __name__ == "__main__":
    main()
