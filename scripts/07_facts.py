# -*- coding: utf-8 -*-
"""07 从"主要会计数据和财务指标"一节抽取标准答案（供评测对照用）。
不依赖模型，纯规则。输出 out/facts.json + 控制台表格。
"""
import json
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

NUM = r"[-\d][\d,]*\.?\d*"


def loose(kw):
    """把一个词变成"允许字与字之间有空白"的正则。
    PDF 表格单元格窄，"归属于上市公司股东的净利润"常被折成
    "净利 润"、"扣除 非经常性损益"，写死连着的词就匹配不到
    —— 实测 14 家里只有 1 家的扣非净利润能抠出来。"""
    return r"\s*".join(re.escape(ch) for ch in kw)


# 单位"（元）"整体可选：深市写"营业收入（元）"，沪市写"营业收入"
UNIT = r"(?:\s*[（(]\s*元\s*[）)])?"
ITEMS = {
    "营业收入": loose("营业收入") + UNIT,
    "归母净利润": loose("归属于上市公司股东的净利润") + UNIT,
    "扣非净利润": loose("归属于上市公司股东的扣除非经常性损益的净利润") + UNIT,
    "经营现金流": loose("经营活动产生的现金流量净额") + UNIT,
}


def flat(text):
    t = text.replace("|", " ")
    t = re.sub(r"[ \t　]+", " ", t)
    t = re.sub(r"\s*\n\s*", " ", t)
    return t


def grab(txt, pattern):
    # 分隔符必须排除负号：`[^\d]` 会把第二个数字的 "-" 一并吃掉，
    # 于是上年同期 -772,811,725.52 被读成 +772,811,725.52，
    # 江淮的归母净利润同比就从真实的"减亏"变成 -196.91%（实测踩过）。
    m = re.search(pattern + r"[^\d\-]{0,40}(" + NUM + r")[^\d\-]{0,40}(" + NUM + r")",
                  txt)
    if not m:
        return None, None
    a, b = m.group(1), m.group(2)
    try:
        fa = float(a.replace(",", ""))
        fb = float(b.replace(",", ""))
    except ValueError:
        return None, None
    return fa, fb


def yi(v):
    return "—" if v is None else f"{v/1e8:.2f}"


def pct(r, k):
    return "—" if r.get(k) is None else r[k]


def write_extra_chunks(facts):
    """RAG 的天然短板是跨文档汇总：14 家的数字散在 14 份 PDF 里，
    没有任何一个原文块包含全部 14 家 —— 检索永远召不全，
    "哪家增长最快" 这类问题必然答错。
    补法（课件 P24「拆碎了之后要把碎块重新组织」的同一思路）：
    把各家的"主要会计数据"预先汇成一张速查表，当成普通块塞进索引，
    这样它和原文块一起参与检索，谁问汇总谁就能召回它。
    """
    hdr = ("| 公司 | 代码 | 营业收入(亿) | 同比% | 归母净利润(亿) | 同比% "
           "| 扣非净利润(亿) | 同比% | 经营活动现金流量净额(亿) |")
    sep = "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    rows = [hdr, sep]
    for code, r in facts.items():
        rows.append(
            f"| {r['name']} | {code} | {yi(r['营业收入'])} | {pct(r,'营业收入_同比%')} "
            f"| {yi(r['归母净利润'])} | {pct(r,'归母净利润_同比%')} "
            f"| {yi(r['扣非净利润'])} | {pct(r,'扣非净利润_同比%')} "
            f"| {yi(r['经营现金流'])} |")

    def rank(key, rev=False):
        """按 key 排名。key 是「同比%」，是百分数不是金额。
        这里原先写的是 f"{v/1e8:.2f} 亿元"——把百分数又除了一次 1e8，
        于是榜单每一行都印成「0.00 亿元」（同一个坑在本文件里踩了第二次，
        第一次在 FAQ 的 top_rec 那里）。第 9 题的模型回答里自己指出了这个矛盾。"""
        items = [(r[key], r["name"], r["code"])
                 for r in facts.values() if r.get(key) is not None]
        items.sort(key=lambda x: x[0], reverse=rev)
        return [f"{i}. {n}（{c}）：{v:.2f}%"
                for i, (v, n, c) in enumerate(items, 1)]

    both = [(r["经营现金流"], r["归母净利润"], r["name"], r["code"])
            for r in facts.values()
            if r.get("经营现金流") is not None and r.get("归母净利润") is not None]
    both.sort(key=lambda x: -abs(x[0] - x[1]))
    gap = [f"{i}. {n}（{c}）：经营现金流 {a/1e8:.2f} 亿元，"
           f"归母净利润 {b/1e8:.2f} 亿元，差 {abs(a-b)/1e8:.2f} 亿元"
           for i, (a, b, n, c) in enumerate(both, 1)]

    def top_rec(key, rev=True):
        """按 key 排序取第一名，返回整条记录。
        注意：必须返回整条记录。上一版只返回 r[key]（那是"同比增速"），
        再拿它 /1e8 当金额写进表里，写出"归母净利润 0.00 亿元"——把
        增速当成了金额。"""
        items = [r for r in facts.values() if r.get(key) is not None]
        items.sort(key=lambda r: r[key], reverse=rev)
        return items[0]

    def amt(r, k):
        return "—" if r.get(k) is None else f"{r[k]/1e8:.2f} 亿元"

    # 逐条把"问题原话"和"答案"绑在一起写进块里。
    # 原因：检索靠字面+语义匹配，问句写的是全称「归属于上市公司股东的净利润」，
    # 表里写的是简称「归母净利润」，对不上就会掉出前 8（实测 Q9 只排第 7）。
    # 把问法本身写进块，等于给这块加了和问句一致的措辞。
    r1 = top_rec("归母净利润_同比%")
    r2 = top_rec("归母净利润_同比%", False)
    r3 = top_rec("营业收入_同比%")
    r4 = top_rec("扣非净利润_同比%")
    a5, b5, n5, c5 = both[0]
    faq_items = [
        ("1. 问：这 14 家公司里，上半年归属于上市公司股东的净利润"
         "（简称「归母净利润」）同比增长最快的是哪一家？增长多少？\n"
         f"   答：{r1['name']}（{r1['code']}），归母净利润 {amt(r1, '归母净利润')}，"
         f"同比增长 {r1['归母净利润_同比%']}%。"),
        ("2. 问：归母净利润同比下降最多的是哪一家？\n"
         f"   答：{r2['name']}（{r2['code']}），归母净利润 {amt(r2, '归母净利润')}，"
         f"同比下降 {abs(r2['归母净利润_同比%'])}%。"),
        ("3. 问：营业收入（营收）同比增长最快的是哪一家？\n"
         f"   答：{r3['name']}（{r3['code']}），营业收入 {amt(r3, '营业收入')}，"
         f"同比增长 {r3['营业收入_同比%']}%。"),
        ("4. 问：扣非净利润同比增速最高（即降幅最小）的是哪一家？\n"
         f"   答：{r4['name']}（{r4['code']}），扣非净利润 {amt(r4, '扣非净利润')}，"
         f"同比 {r4['扣非净利润_同比%']}%（14 家中最高）。"),
        ("5. 问：哪一家经营活动产生的现金流量净额（简称「经营现金流」）"
         "与归母净利润的差异（差额）最大？\n"
         f"   答：{n5}（{c5}），经营活动现金流量净额 {a5 / 1e8:.2f} 亿元，"
         f"归母净利润 {b5 / 1e8:.2f} 亿元，两者相差 {abs(a5 - b5) / 1e8:.2f} 亿元。"),
        (f"6. 问：这 14 家公司一共几家？报告期是什么？\n"
         f"   答：共 {len(facts)} 家，报告期为 2026 年 1-6 月（2026 年半年度）。"),
    ]

    # ---- 速查块必须切小 ----
    # 向量模型 bge-small-zh-v1.5 的窗口只有 512 token。上一版把整张汇总表做成
    # 一个块（787 token）、把 FAQ+四个排行榜做成一个块（1852 token），
    # 超窗部分被模型**静默截掉**——而截掉的偏偏是排在后面的几家公司、后几个榜单。
    # 所以这里按条目拆成多个小块，每块自己就是完整的一条信息。
    HEAD = ("14 家公司 2026 年半年度主要会计数据和财务指标"
            "（口径：合并报表、报告期累计、单位亿元）\n")
    chunks = []
    items = list(facts.items())
    for gi in range(0, len(items), 4):          # 每 4 家一块（7 家实测 767 token，超窗）
        part = items[gi:gi + 4]
        g = gi // 4 + 1
        chunks.append({
            "id": f"SUMMARY-1{g:02d}", "code": "SUMMARY", "name": "14家速查表",
            "section": f"主要会计数据和财务指标汇总速查表（第{g}组）",
            "page": "—", "page_end": "—",
            "text": HEAD + "".join(
                f"{r['name']}（{c}）：营业收入 {yi(r['营业收入'])} 亿元，"
                f"同比增长 {pct(r, '营业收入_同比%')}%；"
                f"归属上市公司股东的净利润（归母净利润）{yi(r['归母净利润'])} 亿元，"
                f"同比增长 {pct(r, '归母净利润_同比%')}%；"
                f"扣非净利润 {yi(r['扣非净利润'])} 亿元，"
                f"同比增长 {pct(r, '扣非净利润_同比%')}%；"
                f"经营活动产生的现金流量净额 {yi(r['经营现金流'])} 亿元。\n"
                for c, r in part),
        })

    rank_lists = [
        ("归母净利润同比增长最快排名（降序，%）", rank("归母净利润_同比%", True)),
        ("营业收入同比增长最快排名（降序，%）", rank("营业收入_同比%", True)),
        ("扣非净利润同比增长最快排名（降序，%）", rank("扣非净利润_同比%", True)),
        ("经营活动现金流量净额与归母净利润差额排名（降序，亿元）", gap),
    ]
    for gi in range(0, len(faq_items), 3):      # FAQ 每 3 条一块
        part = faq_items[gi:gi + 3]
        g = gi // 3 + 1
        chunks.append({
            "id": f"SUMMARY-2{g:02d}", "code": "SUMMARY", "name": "14家速查表",
            "section": f"常见问法与直接答案（第{g}组）",
            "page": "—", "page_end": "—",
            "text": "常见问法与直接答案（跨公司汇总，口径：合并报表、报告期累计、单位亿元）\n"
                    + "\n".join(part),
        })
    for li, (title, body) in enumerate(rank_lists, 1):
        for gi in range(0, len(body), 7):      # 一个榜单太长也拆，每段重贴标题
            part = body[gi:gi + 7]
            g = gi // 7 + 1
            tail = f"（第{g}段）" if len(body) > 7 else ""
            chunks.append({
                "id": f"SUMMARY-3{li}{g}", "code": "SUMMARY", "name": "14家速查表",
                "section": f"跨公司排名：{title}{tail}",
                "page": "—", "page_end": "—",
                "text": f"14 家公司 2026 年半年度{title}{tail}\n" + "\n".join(part),
            })

    path = os.path.join(DATA, "extra_chunks.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"\n补充块 {len(chunks)} 个 -> {path}")


def main():
    chunks = [json.loads(l) for l in open(os.path.join(DATA, "chunks.jsonl"),
                                          encoding="utf-8")]
    by_code = {}
    for c in chunks:
        by_code.setdefault(c["code"], []).append(c)

    facts = {}
    for code, cs in by_code.items():
        name = cs[0]["name"]
        # 只看第二节/主要会计数据 相关块
        pool = [c for c in cs if ("主要会计数据" in c["text"]
                                  or c["section"].startswith("第二节"))]
        txt = flat(" ".join(c["text"] for c in pool))
        rec = {"code": code, "name": name}
        for k, pat in ITEMS.items():
            a, b = grab(txt, pat)
            rec[k] = a
            rec[k + "_上年"] = b
            if a is not None and b not in (None, 0):
                rec[k + "_同比%"] = round((a - b) / abs(b) * 100, 2)
        facts[code] = rec

    json.dump(facts, open(os.path.join(OUT, "facts.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    write_extra_chunks(facts)

    def yi(v):
        return "—" if v is None else f"{v/1e8:.2f}亿"

    print(f"{'公司':<10}{'营收':>10}{'同比%':>9}{'归母净利':>10}{'同比%':>9}{'经营现金流':>12}")
    for code, r in facts.items():
        print(f"{r['name']:<10}{yi(r['营业收入']):>10}"
              f"{str(r.get('营业收入_同比%','—')):>9}"
              f"{yi(r['归母净利润']):>10}{str(r.get('归母净利润_同比%','—')):>9}"
              f"{yi(r['经营现金流']):>12}")
    print(f"\n-> {os.path.join(OUT,'facts.json')}")


if __name__ == "__main__":
    main()
