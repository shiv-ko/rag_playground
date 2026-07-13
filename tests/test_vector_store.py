"""VectorStoreの単体テスト（HashEmbedderのみ使用、実モデル不要）。"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.indexer.embedder import Embedder
from src.indexer.vector_store import VectorStore
from src.models import Document


class _FixedEmbedder:
    """テキストに関わらず固定ベクトルを返すフェイクEmbedder（注入テスト用）。"""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.array([self._vectors[t] for t in texts], dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return np.array(self._vectors[text], dtype=np.float32)


def test_vector_store_uses_injected_embedder():
    fixed = _FixedEmbedder({
        "近い文書": [1.0, 0.0],
        "遠い文書": [0.0, 1.0],
        "近いクエリ": [0.9, 0.1],
    })
    store = VectorStore(embedder=fixed)
    store.add([
        Document(text="近い文書", source_path=Path("a.txt")),
        Document(text="遠い文書", source_path=Path("b.txt")),
    ])
    results = store.search("近いクエリ", top_k=1)
    assert results[0].document.text == "近い文書"


def test_vector_store_default_embedder_is_hash_embedder():
    store = VectorStore()
    store.add([Document(text="宿泊費の上限は15,000円です。", source_path=Path("a.txt"))])
    results = store.search("宿泊費", top_k=1)
    assert len(results) == 1
    assert results[0].retrieval_method == "vector"


def test_vector_store_empty_search_returns_empty():
    store = VectorStore()
    assert store.search("何か", top_k=5) == []


def test_vector_store_clear_resets_state():
    store = VectorStore()
    store.add([Document(text="宿泊費", source_path=Path("a.txt"))])
    store.clear()
    assert store.search("宿泊費", top_k=5) == []
