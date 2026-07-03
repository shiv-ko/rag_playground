"""ベクトル検索とキーワード検索を統合するHybridRetriever + 簡易re-ranking。"""
from __future__ import annotations

from src.indexer.keyword_store import KeywordStore
from src.indexer.vector_store import VectorStore
from src.models import Document, ScoredDocument


class HybridRetriever:
    def __init__(
        self,
        vector_weight: float = 0.6,
        keyword_weight: float = 0.4,
        rerank_top_n: int = 3,
    ) -> None:
        self.vector_store = VectorStore()
        self.keyword_store = KeywordStore()
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.rerank_top_n = rerank_top_n

    def add(self, documents: list[Document]) -> None:
        self.vector_store.add(documents)
        self.keyword_store.add(documents)

    def clear(self) -> None:
        self.vector_store.clear()
        self.keyword_store.clear()

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        fetch_k = top_k * 3  # re-ranking前に多めに取る

        vec_results = self.vector_store.search(query, fetch_k)
        kw_results = self.keyword_store.search(query, fetch_k)

        # 各ストアのスコアを0-1正規化してから重み付き合算
        vec_scores = _normalize({r.document.text: r.score for r in vec_results})
        kw_scores = _normalize({r.document.text: r.score for r in kw_results})

        # doc.textをキーにして統合
        merged: dict[str, ScoredDocument] = {}
        for r in vec_results:
            key = id(r.document)
            merged[key] = ScoredDocument(
                document=r.document,
                score=vec_scores.get(r.document.text, 0) * self.vector_weight,
                retrieval_method="hybrid",
            )
        for r in kw_results:
            key = id(r.document)
            if key in merged:
                merged[key].score += kw_scores.get(r.document.text, 0) * self.keyword_weight
            else:
                merged[key] = ScoredDocument(
                    document=r.document,
                    score=kw_scores.get(r.document.text, 0) * self.keyword_weight,
                    retrieval_method="hybrid",
                )

        ranked = sorted(merged.values(), key=lambda x: x.score, reverse=True)
        return ranked[:top_k]


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_s = max(scores.values())
    min_s = min(scores.values())
    span = max_s - min_s or 1.0
    return {k: (v - min_s) / span for k, v in scores.items()}
