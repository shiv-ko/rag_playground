"""埋め込みベクトル生成の抽象化。本番差し替えポイント: 埋め込みモデルをここで差し替える。"""
from __future__ import annotations

import math
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def _simple_embed(text: str, dim: int) -> list[float]:
    """埋め込みAPIが使えない間のハッシュベース疑似ベクトル。単体テスト・デフォルト値用。"""
    vec = [0.0] * dim
    for i, ch in enumerate(text[:500]):
        vec[ord(ch) % dim] += 1.0 / (i + 1)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class HashEmbedder:
    """埋め込みAPI/モデルなしで動くハッシュベース疑似埋め込み。単体テスト・デフォルト値用。"""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.array([_simple_embed(t, self.dim) for t in texts], dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return np.array(_simple_embed(text, self.dim), dtype=np.float32)


_QUERY_PREFIX = "クエリ: "
_DOC_PREFIX = "文章: "


class JapaneseEmbedder:
    """日本語特化の埋め込みモデル（cl-nagoya/ruri-base）。本番用。
    要install: sentence-transformers, fugashi, unidic-lite, sentencepiece（pyproject.tomlの[embeddings]グループ）。"""

    def __init__(self, model_name: str = "cl-nagoya/ruri-base", batch_size: int = 64) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        model = self._load_model()
        prefixed = [_DOC_PREFIX + t for t in texts]
        vecs = model.encode(prefixed, batch_size=self.batch_size, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        model = self._load_model()
        vec = model.encode(_QUERY_PREFIX + text, normalize_embeddings=True)
        return np.asarray(vec, dtype=np.float32)
