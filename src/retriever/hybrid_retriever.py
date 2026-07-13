"""ベクトル検索とキーワード検索をReciprocal Rank Fusion(RRF)で統合するHybridRetriever。"""
from __future__ import annotations

from src.indexer.embedder import Embedder
from src.indexer.keyword_store import KeywordStore
from src.indexer.vector_store import VectorStore
from src.models import Document, ScoredDocument

_RRF_K = 60  # Cormack et al. (2009) の標準値。文献値をそのまま使い、valid過適合の対象にしない。


class HybridRetriever:
    def __init__(
        self,
        embedder: Embedder | None = None,
        rerank_top_n: int = 3,
    ) -> None:
        self.vector_store = VectorStore(embedder=embedder)
        self.keyword_store = KeywordStore()
        self.rerank_top_n = rerank_top_n

    def add(self, documents: list[Document]) -> None:
        self.vector_store.add(documents)
        self.keyword_store.add(documents)

    def clear(self) -> None:
        self.vector_store.clear()
        self.keyword_store.clear()

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        fetch_k = max(top_k * 6, 30)
        vec_results = self.vector_store.search(query, fetch_k)
        kw_results = self.keyword_store.search(query, fetch_k)
        fused = _reciprocal_rank_fusion([vec_results, kw_results])
        return fused[:top_k]


def _reciprocal_rank_fusion(
    result_lists: list[list[ScoredDocument]], k: int = _RRF_K
) -> list[ScoredDocument]:
    scores: dict[int, float] = {}
    doc_by_key: dict[int, ScoredDocument] = {}
    for results in result_lists:
        for rank, r in enumerate(results, start=1):
            key = id(r.document)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in doc_by_key:
                doc_by_key[key] = r
    fused = [
        ScoredDocument(document=doc_by_key[key].document, score=score, retrieval_method="hybrid")
        for key, score in scores.items()
    ]
    fused.sort(key=lambda x: x.score, reverse=True)
    return fused
