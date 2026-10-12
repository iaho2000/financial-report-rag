# -*- coding: utf-8 -*-
"""04 建索引：向量（Qwen3-Embedding-0.6B，本地）+ BM25（jieba）。
对齐课件第三课 P25/P34：向量管"意思相近"，BM25 管"字面必须出现"，两条并排跑。
用法：python 04_build_index.py
输出：data/vectors.npy, data/bm25.pkl, data/meta.json
"""
import json
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bm25_lib import BM25, tokenize  # noqa: E402

BASE = os.path.dirname(HERE)
DATA = os.path.join(BASE, "data")
MODEL_DIR = os.path.join(BASE, "models", "Qwen3-Embedding-0.6B")


def load_chunks():
    """原文块 + 汇总速查块（07 生成）。汇总块是凭空补出来的，没有它就答不了跨公司题。"""
    out = []
    for fn in ("chunks.jsonl", "extra_chunks.jsonl"):
        path = os.path.join(DATA, fn)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            out += [json.loads(l) for l in f if l.strip()]
    return out


def main():
    bm25_only = "--bm25-only" in sys.argv
    chunks = load_chunks()
    print(f"载入 {len(chunks)} 块")
    texts = [c["text"] for c in chunks]

    # ---- 向量 ----
    vpath = os.path.join(DATA, "vectors.npy")
    if bm25_only:
        emb = None
    elif os.path.exists(vpath):
        print("向量已存在，跳过编码")
        emb = np.load(vpath)
    else:
        from sentence_transformers import SentenceTransformer
        print("加载本地模型 ...")
        model = SentenceTransformer(MODEL_DIR, device="cpu")
        # 必须显式设窗口：Qwen3-Embedding 原生支持 32768，但这个仓库里没有
        # sentence_bert_config.json，ST 会退回一个很短的默认值，
        # 把 800 字的块尾巴悄悄截掉——截掉的正好常是表格的后几行。
        model.max_seq_length = 1024
        _n = max(len(model.tokenizer(t, add_special_tokens=False)["input_ids"])
                 for t in texts[:300])
        print(f"抽样最长块 {_n} token / 窗口 {model.max_seq_length}")
        if _n > model.max_seq_length:
            print("!! 有块超窗口，会被截断，请把 max_seq_length 调大或把块切小")
        emb = model.encode(texts, batch_size=16, normalize_embeddings=True,
                           show_progress_bar=True, convert_to_numpy=True)
        emb = emb.astype(np.float16)
        np.save(vpath, emb)
        print(f"向量完成 {emb.shape} -> {vpath}")
    if emb is not None:
        print(f"向量矩阵 {emb.shape}  {emb.nbytes/1e6:.1f}MB")

    # ---- BM25 ----
    bpath = os.path.join(DATA, "bm25.pkl")
    # 0 字节 = 上次 dump 中途失败留下的残file，不能当"已存在"跳过
    if os.path.exists(bpath) and os.path.getsize(bpath) > 0:
        print("BM25 已存在，跳过")
    else:
        print("分词中 ...")
        toks = [tokenize(t) for t in texts]
        bm = BM25(toks)
        with open(bpath, "wb") as f:
            pickle.dump({"bm25": bm}, f)
        print(f"BM25 完成，词表 {len(bm.idf)} -> {bpath}")

    if bm25_only:
        print("--bm25-only：跳过 meta 写入")
        return

    meta = {
        "n_chunks": len(chunks),
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "dim": int(emb.shape[1]),
        "companies": sorted({(c["code"], c["name"]) for c in chunks}),
    }
    json.dump(meta, open(os.path.join(DATA, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("meta:", json.dumps(meta, ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
