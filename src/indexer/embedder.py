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
