"""ベクトル検索ストア。本番差し替えポイント: 埋め込みモデルをEmbedder経由で差し替える。"""
from __future__ import annotations

import numpy as np

from src.indexer.embedder import Embedder, HashEmbedder
from src.models import Document, ScoredDocument


class VectorStore:
    """
    本番差し替えポイント:
      - embedder引数に実モデル（例: JapaneseEmbedder）を渡す
      インターフェース(add/search/clear)は変えない。
    """

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder: Embedder = embedder or HashEmbedder()
        self._docs: list[Document] = []
        self._matrix: np.ndarray | None = None

    def add(self, documents: list[Document]) -> None:
        if not documents:
            return
        vecs = np.asarray(self._embedder.embed_documents([d.text for d in documents]), dtype=np.float32)
        self._docs.extend(documents)
        self._matrix = vecs if self._matrix is None else np.vstack([self._matrix, vecs])

    def clear(self) -> None:
        self._docs = []
        self._matrix = None

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        if not self._docs or self._matrix is None:
            return []
        q_vec = np.asarray(self._embedder.embed_query(query), dtype=np.float32)
        scores = self._matrix @ q_vec
        top_idx = np.argsort(-scores)[:top_k]
        return [
            ScoredDocument(document=self._docs[i], score=float(scores[i]), retrieval_method="vector")
            for i in top_idx
        ]
