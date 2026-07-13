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


from src.indexer.embedder import JapaneseEmbedder


class _FakeSTModel:
    """sentence_transformers.SentenceTransformerの最小フェイク。呼び出された引数を記録する。"""

    def __init__(self) -> None:
        self.encode_calls: list[dict] = []

    def encode(self, texts, batch_size=None, normalize_embeddings=None):
        self.encode_calls.append({
            "texts": texts,
            "batch_size": batch_size,
            "normalize_embeddings": normalize_embeddings,
        })
        is_batch = isinstance(texts, list)
        n = len(texts) if is_batch else 1
        vecs = np.tile(np.array([1.0, 0.0], dtype=np.float32), (n, 1))
        return vecs if is_batch else vecs[0]


def test_japanese_embedder_applies_document_prefix():
    embedder = JapaneseEmbedder()
    fake = _FakeSTModel()
    embedder._model = fake  # 遅延ロードをバイパスしてフェイクを注入

    embedder.embed_documents(["これはテスト文書です。"])

    assert fake.encode_calls[0]["texts"] == ["文章: これはテスト文書です。"]
    assert fake.encode_calls[0]["normalize_embeddings"] is True


def test_japanese_embedder_applies_query_prefix():
    embedder = JapaneseEmbedder()
    fake = _FakeSTModel()
    embedder._model = fake

    embedder.embed_query("これは質問です。")

    assert fake.encode_calls[0]["texts"] == "クエリ: これは質問です。"


def test_japanese_embedder_lazy_loads_model_once():
    embedder = JapaneseEmbedder()
    fake = _FakeSTModel()
    embedder._model = fake

    embedder.embed_documents(["a"])
    embedder.embed_query("b")

    # _load_model()が_modelを上書きしていない（既にセット済みならそのまま使う）ことを確認
    assert embedder._model is fake
