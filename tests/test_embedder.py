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


class _ConcurrencyTrackingSTModel:
    """encode()呼び出しの重なり（同時実行数）を記録するフェイク。
    実際のsentence-transformers（PyTorch MPSバックエンド）はスレッドセーフでなく、
    並行呼び出しでセグフォルトすることが実データ検証で確認された（Task 8）。
    このフェイクはGPU実行を模倣せず、encode()呼び出し区間の重なりだけを検出する。"""

    def __init__(self) -> None:
        import threading
        self._lock = threading.Lock()
        self._active = 0
        self.max_concurrent_calls = 0

    def encode(self, texts, batch_size=None, normalize_embeddings=None):
        import time
        with self._lock:
            self._active += 1
            self.max_concurrent_calls = max(self.max_concurrent_calls, self._active)
        time.sleep(0.05)
        with self._lock:
            self._active -= 1
        is_batch = isinstance(texts, list)
        n = len(texts) if is_batch else 1
        vecs = np.tile(np.array([1.0, 0.0], dtype=np.float32), (n, 1))
        return vecs if is_batch else vecs[0]


def test_japanese_embedder_serializes_concurrent_embed_query_calls():
    """複数スレッドから同時にembed_query()を呼んでも、モデル呼び出しは1回ずつ直列化される
    （MPSバックエンドの並行呼び出しセグフォルトを防ぐため）。"""
    from concurrent.futures import ThreadPoolExecutor

    embedder = JapaneseEmbedder()
    fake = _ConcurrencyTrackingSTModel()
    embedder._model = fake

    queries = [f"質問{i}" for i in range(8)]
    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(embedder.embed_query, queries))

    assert fake.max_concurrent_calls == 1


from src.indexer.embedder import CachedEmbedder


class _CountingEmbedder:
    """embed_documentsの呼び出し回数と実際に埋め込んだテキストを記録するフェイク。"""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        self.calls.append(list(texts))
        return np.array([[float(len(t)), 0.0] for t in texts], dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return np.array([float(len(text)), 0.0], dtype=np.float32)


def test_cached_embedder_dedupes_repeated_texts_within_session():
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner)

    cached.embed_documents(["共通文書A", "固有文書1"])
    cached.embed_documents(["共通文書A", "固有文書2"])  # "共通文書A"は既にキャッシュ済み

    # 2回目の呼び出しでは新規分（"固有文書2"）のみinner側に渡る
    assert inner.calls[0] == ["共通文書A", "固有文書1"]
    assert inner.calls[1] == ["固有文書2"]


def test_cached_embedder_returns_correct_vectors_in_order():
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner)

    vecs1 = cached.embed_documents(["共通文書A", "固有文書1"])
    vecs2 = cached.embed_documents(["固有文書2", "共通文書A"])  # 順序が変わっても正しく揃う

    assert vecs2[0][0] == float(len("固有文書2"))
    assert vecs2[1][0] == vecs1[0][0]  # "共通文書A"は同じベクトル


def test_cached_embedder_persists_to_disk(tmp_path):
    cache_path = tmp_path / "emb_cache.pkl"
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner, cache_path=cache_path)
    cached.embed_documents(["文書A"])
    cached.flush()

    assert cache_path.exists()

    # 新しいCachedEmbedderインスタンスがディスクキャッシュを読み込み、再計算しない
    inner2 = _CountingEmbedder()
    cached2 = CachedEmbedder(inner2, cache_path=cache_path)
    cached2.embed_documents(["文書A"])
    assert inner2.calls == []  # 全てキャッシュヒットのためinner2は一度も呼ばれない


def test_cached_embedder_embed_query_passthrough():
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner)
    result = cached.embed_query("質問文")
    assert result[0] == float(len("質問文"))
