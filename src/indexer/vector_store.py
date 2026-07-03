"""ベクトル検索ストア。本番差し替えポイント: 埋め込みモデルとバックエンドをここで差し替える。"""
from __future__ import annotations

import math
import re
from src.models import Document, ScoredDocument


def _simple_embed(text: str, dim: int = 64) -> list[float]:
    """埋め込みAPIが使えない間のハッシュベース疑似ベクトル。本番はClaude/OpenAI等に差し替え。"""
    vec = [0.0] * dim
    for i, ch in enumerate(text[:500]):
        vec[ord(ch) % dim] += 1.0 / (i + 1)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class VectorStore:
    """
    本番差し替えポイント:
      - _embed() を実際の埋め込みAPIに置き換える
      - ストレージをChroma/FAISSに置き換える
      インターフェース(add/search/clear)は変えない。
    """

    def __init__(self) -> None:
        self._docs: list[Document] = []
        self._vecs: list[list[float]] = []

    def add(self, documents: list[Document]) -> None:
        for doc in documents:
            self._docs.append(doc)
            self._vecs.append(self._embed(doc.text))

    def clear(self) -> None:
        self._docs = []
        self._vecs = []

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        if not self._docs:
            return []
        q_vec = self._embed(query)
        scored = [
            (i, _cosine(q_vec, v)) for i, v in enumerate(self._vecs)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            ScoredDocument(document=self._docs[i], score=s, retrieval_method="vector")
            for i, s in scored[:top_k]
        ]

    def _embed(self, text: str) -> list[float]:
        return _simple_embed(text)
