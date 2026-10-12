# -*- coding: utf-8 -*-
"""01 从巨潮资讯网下载自选股 2026 年半年度报告全文 PDF。
数据源：cninfo.com.cn（证监会指定披露平台）
用法：python 01_download.py
断点续传：PDF 已存在则跳过。
"""
import json
import os
import time

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE, "data", "pdf")
os.makedirs(PDF_DIR, exist_ok=True)

# 大哥自选股里的 14 只主板票（00/60）
STOCKS = [
    "001332",  # 锡装股份
    "000988",  # 华工科技
    "600309",  # 万华化学
    "600176",  # 中国巨石
    "600487",  # 亨通光电
    "600418",  # 江淮汽车
    "002185",  # 华天科技
    "002138",  # 顺络电子
    "000960",  # 锡业股份
    "601890",  # 亚星锚链
    "002837",  # 英维克
    "000530",  # 冰山冷热
    "002639",  # 雪人股份
    "002506",  # 协鑫集成
]

YEAR = "2026"
HALF = f"{YEAR}年半年度报告"

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "http://www.cninfo.com.cn/",
})


def search_org(code):
    r = s.post("http://www.cninfo.com.cn/new/information/topSearch/query",
               data={"keyWord": code, "maxNum": "10"}, timeout=20)
    for it in r.json():
        if it.get("code") == code:
            return it["orgId"], it["zwjc"]
    return None, None


def find_report(code, org_id):
    col = "sse" if code.startswith("6") else "szse"
    r = s.post("http://www.cninfo.com.cn/new/hisAnnouncement/query",
               data={"pageNum": "1", "pageSize": "30", "column": col,
                     "tabName": "fulltext", "plate": "", "stock": f"{code},{org_id}",
                     "searchkey": "", "secid": "", "category": "category_bndbg_szsh",
                     "trade": "", "seDate": "", "sortName": "", "sortType": "",
                     "isHLtitle": "true"}, timeout=25)
    for a in (r.json().get("announcements") or []):
        t = a["announcementTitle"].replace("<em>", "").replace("</em>", "")
        # 深市标题就是"2026年半年度报告"；沪市带公司名前缀，故用 endswith；一律排除"摘要"
        if t.endswith(HALF) and "摘要" not in t:
            return a["adjunctUrl"], t
    return None, None


def main():
    meta = []
    for i, code in enumerate(STOCKS, 1):
        out = os.path.join(PDF_DIR, f"{code}_{YEAR}H1.pdf")
        if os.path.exists(out) and os.path.getsize(out) > 100_000:
            print(f"[{i}/{len(STOCKS)}] {code} 已存在，跳过")
            meta.append({"code": code, "pdf": out})
            continue
        try:
            org, name = search_org(code)
            if not org:
                print(f"[{i}/{len(STOCKS)}] {code} 找不到 orgId")
                continue
            url, title = find_report(code, org)
            if not url:
                print(f"[{i}/{len(STOCKS)}] {code} {name} 没有 {HALF}")
                continue
            pdf_url = "http://static.cninfo.com.cn/" + url
            r = s.get(pdf_url, timeout=120)
            r.raise_for_status()
            with open(out, "wb") as f:
                f.write(r.content)
            print(f"[{i}/{len(STOCKS)}] {code} {name} {len(r.content)/1e6:.2f}MB OK")
            meta.append({"code": code, "name": name, "orgId": org, "pdf": out,
                         "url": pdf_url, "title": title})
        except Exception as e:
            print(f"[{i}/{len(STOCKS)}] {code} 失败 {type(e).__name__} {str(e)[:80]}")
        time.sleep(1.2)                     # 限速，别封 IP

    mp = os.path.join(BASE, "data", "stocks.json")
    old = {}
    if os.path.exists(mp):
        old = {d["code"]: d for d in json.load(open(mp, encoding="utf-8"))}
    for d in meta:
        old.setdefault(d["code"], {}).update(d)
    json.dump(list(old.values()), open(mp, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"共 {len(old)} 只写入 {mp}")


if __name__ == "__main__":
    main()
