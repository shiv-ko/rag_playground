"""HashEmbedderの単体テスト（ネットワーク/実モデル不要）。"""
from __future__ import annotations

import numpy as np

from src.indexer.embedder import HashEmbedder


def test_hash_embedder_returns_normalized_vectors():
    embedder = HashEmbedder(dim=16)
    vecs = embedder.embed_documents(["宿泊費の上限は15,000円です。", "交通費は1回10,000円まで。"])
    assert vecs.shape == (2, 16)
    norms = np.linalg.norm(vecs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_hash_embedder_is_deterministic():
    embedder = HashEmbedder(dim=16)
    v1 = embedder.embed_query("宿泊費の上限")
    v2 = embedder.embed_query("宿泊費の上限")
    assert np.array_equal(v1, v2)


def test_hash_embedder_similar_text_higher_similarity():
    embedder = HashEmbedder(dim=64)
    a = embedder.embed_query("宿泊費の上限は15,000円です")
    b = embedder.embed_query("宿泊費の上限は15,000円")
    c = embedder.embed_query("Model Xのバッテリーは18時間")
    assert float(a @ b) > float(a @ c)
