# -*- coding: utf-8 -*-
"""BM25（jieba 分词）。独立模块：pickle 需要类能被正常 import。"""
import math
import re
from collections import Counter

import jieba

PUNCT = re.compile(r"^[\W_]+$", re.UNICODE)


def tokenize(text):
    ws = []
    for w in jieba.lcut(text):
        w = w.strip()
        if not w or PUNCT.match(w) or len(w) < 2:
            continue
        ws.append(w)
    return ws


class BM25:
    """标准 BM25，k1=1.5 b=0.75（课件 P35：词频高加分 / 全库少见更值钱 / 块长打折）"""

    def __init__(self, docs_tokens, k1=1.5, b=0.75):
        import numpy as np
        self.k1, self.b = k1, b
        self.N = len(docs_tokens)
        self.doc_len = np.array([len(d) for d in docs_tokens], dtype=np.float32)
        self.avgdl = float(self.doc_len.mean()) if self.N else 1.0
        df = Counter()
        self.tf = []
        for d in docs_tokens:
            c = Counter(d)
            self.tf.append(c)
            for w in c:
                df[w] += 1
        self.idf = {w: math.log(1 + (self.N - n + 0.5) / (n + 0.5))
                    for w, n in df.items()}
        self.postings = {}
        for i, c in enumerate(self.tf):
            for w in c:
                self.postings.setdefault(w, []).append(i)

    def search(self, query, topk=30):
        qs = tokenize(query)
        cand = set()
        for w in qs:
            cand.update(self.postings.get(w, []))
        if not cand:
            return []
        scores = {}
        for i in cand:
            s = 0.0
            dl = self.doc_len[i]
            for w in qs:
                f = self.tf[i].get(w)
                if not f:
                    continue
                s += self.idf.get(w, 0.0) * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            if s > 0:
                scores[i] = s
        return sorted(scores.items(), key=lambda x: -x[1])[:topk]
