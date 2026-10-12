# -*- coding: utf-8 -*-
"""05 检索 + 回答引擎（被 06 网页和 07 评测共用）。
对齐课件第三课：
  - 混合检索：向量 + BM25 并排跑，RRF 融合（P34/P35）
  - 一次把候选全看完再挑，而不是逐块打分（P18/P19：同一个模型，
    一次看完 30 块再挑 0.75 vs 逐块打分 0.55）
  - 回答只依据给定材料，每句带出处；材料没有就写"材料未涉及"（P92/P93）
"""
import json
import os
import pickle
import sys

import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bm25_lib import BM25  # noqa: E402,F401  反序列化 bm25.pkl 需要能 import 这个类

BASE = os.path.dirname(HERE)
DATA = os.path.join(BASE, "data")
MODEL_DIR = os.path.join(BASE, "models", "Qwen3-Embedding-0.6B")

INSTRUCT = ("Instruct: Given a web search query, retrieve relevant passages "
            "that answer the query\nQuery: ")

SYSTEM = """你是财报分析助手。只能依据【材料】回答，不许使用材料之外的知识，不许编造数字。
规则：
1. 每个论断后面必须标出出处编号，如 [1][2]。
2. 材料里没有的，直接写"材料未涉及"，不要猜、不要用常识补。
3. 数字要写全（单位、口径），口径不同要指出（如母公司报表 vs 合并报表）。
4. 先给结论，再给依据。
"""


class RagEngine:
    def __init__(self, load_model=True):
        self.chunks = []
        for fn in ("chunks.jsonl", "extra_chunks.jsonl"):   # 顺序必须和 04 建索引时一致
            p = os.path.join(DATA, fn)
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                self.chunks += [json.loads(l) for l in f if l.strip()]
        self.vectors = np.load(os.path.join(DATA, "vectors.npy"))
        with open(os.path.join(DATA, "bm25.pkl"), "rb") as f:
            self.bm25 = pickle.load(f)["bm25"]
        self.model = None
        if load_model:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(MODEL_DIR, device="cpu")
            # 和 04 建索引时必须一致，否则问句和块不在同一个截断口径上
            self.model.max_seq_length = 1024
        self.meta = json.load(open(os.path.join(DATA, "meta.json"), encoding="utf-8"))

    # ---------- 检索 ----------
    def vec_search(self, query, topk=30):
        q = self.model.encode([INSTRUCT + query], normalize_embeddings=True,
                              convert_to_numpy=True)[0].astype(np.float32)
        sims = self.vectors.astype(np.float32) @ q
        idx = np.argpartition(-sims, topk)[:topk]
        idx = idx[np.argsort(-sims[idx])]
        return [(int(i), float(sims[i])) for i in idx]

    def hybrid(self, query, topk_vec=30, topk_bm=30, k=60):
        """RRF 融合两路召回"""
        v = self.vec_search(query, topk_vec)
        b = self.bm25.search(query, topk_bm)
        score = {}
        for rank, (i, _) in enumerate(v):
            score[i] = score.get(i, 0) + 1 / (k + rank + 1)
        for rank, (i, _) in enumerate(b):
            score[i] = score.get(i, 0) + 1 / (k + rank + 1)
        order = sorted(score.items(), key=lambda x: -x[1])
        return [(i, s) for i, s in order]

    def retrieve(self, query, topk=8, mode="hybrid"):
        pairs = self.hybrid(query) if mode == "hybrid" else self.vec_search(query)
        out = []
        for i, s in pairs[:topk]:
            c = dict(self.chunks[i])
            c["score"] = round(s, 6)
            c["_idx"] = i
            out.append(c)
        return out

    # ---------- 回答 ----------
    @staticmethod
    def _client():
        base = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
        tok = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        model = os.environ.get("RAG_LLM_MODEL", "deepseek-v4-flash")
        if not base or not tok:
            return None, None
        return (base, tok, model), None

    @staticmethod
    def build_materials(hits):
        parts = []
        for n, h in enumerate(hits, 1):
            head = f"[{n}] {h['name']}({h['code']}) | {h['section']} | 第 {h['page']} 页"
            parts.append(f"{head}\n{h['text']}")
        return "\n\n".join(parts)

    def answer(self, query, topk=8, mode="hybrid", use_llm=True):
        hits = self.retrieve(query, topk=topk, mode=mode)
        out = {"query": query, "hits": hits, "answer": None, "model": None}
        if not use_llm:
            return out
        cli, _ = self._client()
        if not cli:
            out["answer"] = "（未配置生成模型：环境变量 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN 缺失）"
            return out
        base, tok, model = cli
        user = (f"【材料】\n{self.build_materials(hits)}\n\n"
                f"【问题】{query}\n\n请依据材料回答，每句标出处编号。")
        try:
            r = requests.post(f"{base}/v1/messages",
                headers={"Authorization": f"Bearer {tok}",
                         "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                # thinking 关掉：实测该端点默认返回 thinking 块，白烧输出 token；
                # 关掉后 content 只剩 text 块，又快又省。
                json={"model": model, "max_tokens": 2000, "system": SYSTEM,
                      "thinking": {"type": "disabled"},
                      "messages": [{"role": "user", "content": user}]},
                timeout=180)
            r.raise_for_status()
            data = r.json()
            txt = "".join(b.get("text", "") for b in data.get("content", []))
            out["answer"] = txt.strip()
            out["model"] = model
            out["usage"] = data.get("usage")
        except Exception as e:
            out["answer"] = f"（生成失败：{type(e).__name__} {str(e)[:120]}）"
        return out

    def format_sources(self, hits):
        lines = []
        for n, h in enumerate(hits, 1):
            lines.append(f"[{n}] {h['name']}({h['code']}) {h['section']} 第{h['page']}页 "
                         f"score={h['score']:.4f}")
        return "\n".join(lines)


if __name__ == "__main__":
    e = RagEngine()
    q = "锡装股份上半年营业收入和归母净利润是多少？"
    r = e.answer(q, topk=6)
    print("== 召回 ==")
    print(e.format_sources(r["hits"]))
    print("\n== 回答 ==")
    print(r["answer"])
