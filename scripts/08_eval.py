# -*- coding: utf-8 -*-
"""08 出 10 道题并评测：逐题记录召回了哪些块、答对没有、错在哪。
用法：python 08_eval.py
输出：out/eval_raw.json, out/eval_report.md
"""
import importlib.util
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
OUT = os.path.join(BASE, "out")
DATA = os.path.join(BASE, "data")


def load_rag():
    spec = importlib.util.spec_from_file_location("rag05", os.path.join(HERE, "05_rag.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


F = json.load(open(os.path.join(OUT, "facts.json"), encoding="utf-8"))


def yi(v):
    return None if v is None else round(v / 1e8, 2)


QUESTIONS = [
    {"id": 1, "type": "单公司", "codes": ["001332"],
     "q": "锡装股份上半年营业收入和归母净利润分别是多少？同比增减如何？",
     "std": f"营业收入 661,835,670.17 元（6.62亿，+6.27%）；归母净利润 97,702,373.86 元（0.98亿，-20.33%）",
     "nums": [661835670.17, 97702373.86]},
    {"id": 2, "type": "单公司", "codes": ["000988"],
     "q": "华工科技上半年归属于上市公司股东的净利润和扣非净利润分别是多少？",
     "std": "归母净利润 1,186,000,791.50 元（11.86亿，+30.17%）；扣非净利润 746,984,454.92 元（7.47亿，+2.42%）",
     "nums": [1186000791.50, 746984454.92]},
    {"id": 3, "type": "单公司", "codes": ["600309"],
     "q": "万华化学上半年经营活动产生的现金流量净额是多少？",
     "std": "11,784,141,040.70 元（117.84亿，+11.93%）",
     "nums": [11784141040.70]},
    {"id": 4, "type": "单公司", "codes": ["600176"],
     "q": "中国巨石上半年归属于上市公司股东的净利润同比变化是多少？",
     "std": "归母净利润 29.33 亿元，同比增长 73.87%",
     "nums": [F["600176"]["归母净利润"]], "pcts": [73.87]},
    {"id": 5, "type": "单公司", "codes": ["600487"],
     "q": "亨通光电上半年归属于上市公司股东的净利润是多少？同比增长多少？",
     "std": "31.20 亿元，同比增长 93.38%",
     "nums": [F["600487"]["归母净利润"]], "pcts": [93.38]},
    {"id": 6, "type": "单公司", "codes": ["600418"],
     "q": "江淮汽车上半年归属于上市公司股东的净利润是多少？同比增减如何？",
     # 标准答案改过一次：原先写"同比下降 196.91%"，那是我把上年同期的负号
     # 读丢了（-772,811,725.52 被当成 +772,811,725.52）算出来的假数。
     # 真实是亏损收窄；报告原文这一项同比增减直接写「不适用」。
     "std": "-748,926,742.94 元（-7.49 亿元）；上年同期 -772,811,725.52 元"
            "（-7.73 亿元），亏损同比收窄约 3.09%；报告原文该项「同比增减」"
            "标注为「不适用」（上年同期为负，比率无意义）",
     "nums": [F["600418"]["归母净利润"]]},
    {"id": 7, "type": "单公司", "codes": ["000960"],
     "q": "锡业股份上半年营业收入和归母净利润分别是多少？",
     "std": "营业收入 315.73 亿元（+49.68%）；归母净利润 15.04 亿元（+41.60%）",
     "nums": [F["000960"]["营业收入"], F["000960"]["归母净利润"]]},
    {"id": 8, "type": "单公司", "codes": ["002837"],
     "q": "英维克上半年营业收入同比增长多少？管理层提到的增长原因是什么？",
     "std": "营业收入 30.17 亿元，同比增长 17.24%；原因见「管理层讨论与分析」",
     "nums": [F["002837"]["营业收入"]], "pcts": [17.24]},
    {"id": 9, "type": "跨公司全景", "codes": [c for c in F],
     "q": "这 14 家公司里，上半年归属于上市公司股东的净利润同比增长最快的是哪一家？增长多少？",
     "std": "华天科技，归母净利润 8.13 亿元，同比增长 259.15%",
     "nums": [F["002185"]["归母净利润"]], "pcts": [259.15]},
    {"id": 10, "type": "跨公司全景", "codes": [c for c in F],
     "q": "这 14 家公司里，上半年经营活动现金流量净额与归母净利润差异最大的是哪一家？",
     "std": "江淮汽车：经营现金流 -52.88 亿元 vs 归母净利润 -7.49 亿元，差 45.39 亿元",
     "nums": [F["600418"]["经营现金流"], F["600418"]["归母净利润"]]},
]


def norm_num(s):
    return re.sub(r"[,\s]", "", s)


def hit_number(ans, v):
    if ans is None or v is None:
        return False
    a = ans.replace(",", "").replace(" ", "")
    cands = set()
    cands.add(f"{v:,.2f}")
    cands.add(f"{v:.0f}")
    cands.add(f"{v/1e8:.2f}")
    cands.add(f"{v/1e8:.1f}")
    cands.add(f"{abs(v)/1e8:.2f}")
    for c in cands:
        if c and c.replace(",", "") in a:
            return True
    return False


def main():
    rag = load_rag()
    eng = rag.RagEngine()
    results = []
    for item in QUESTIONS:
        print(f"[{item['id']}/10] {item['q'][:34]} ...", flush=True)
        r = eng.answer(item["q"], topk=8, mode="hybrid", use_llm=True)
        ans = r.get("answer") or ""
        checks = {str(round(v, 2)): hit_number(ans, v) for v in item["nums"] if v is not None}
        for p in item.get("pcts", []):
            checks[f"{p}%"] = (str(p) in ans.replace("−", "-")) or (f"{p}" in ans)
        results.append({
            "id": item["id"], "type": item["type"], "q": item["q"],
            "std": item["std"], "answer": ans, "model": r.get("model"),
            "num_hits": checks,
            "auto_pass": all(checks.values()) if checks else None,
            "hits": [{"n": i + 1, "name": h["name"], "code": h["code"],
                      "section": h["section"], "page": h["page"],
                      "score": h["score"], "text": h["text"][:300]}
                     for i, h in enumerate(r["hits"])],
        })
    json.dump(results, open(os.path.join(OUT, "eval_raw.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    npass = sum(1 for r in results if r["auto_pass"])
    print(f"\n自动判定通过 {npass}/{len(results)}（数字命中判定，仅供初筛，须人工复核）")
    print("->", os.path.join(OUT, "eval_raw.json"))


if __name__ == "__main__":
    main()
