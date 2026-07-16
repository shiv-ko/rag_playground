"""cold index時のembedding時間予算判定のテスト（実モデル・ネットワーク不要）。

設計: docs/plan/2026-07-16-cold-fallback-design.md
- encode開始前に未処理チャンク数×実測throughputで所要時間を見積もる
- 見積もりが予算超過、またはthroughputが実測できない場合はBM25単体へ退避する
"""
from __future__ import annotations

import numpy as np
import pytest

from src.indexer.embedder import CachedEmbedder
from src.indexer.embedding_budget import evaluate_embedding_budget


class _FakeClock:
    """embed呼び出しで進む疑似時計。timer注入でthroughput計測を決定的にする。"""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _TimedEmbedder:
    """1テキストあたりseconds_per_text秒だけ疑似時計を進めるフェイク。"""

    def __init__(self, clock: _FakeClock, seconds_per_text: float) -> None:
        self._clock = clock
        self._seconds_per_text = seconds_per_text
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        self.calls.append(list(texts))
        self._clock.now += self._seconds_per_text * len(texts)
        return np.zeros((len(texts), 2), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return np.zeros(2, dtype=np.float32)


def _texts(n: int) -> list[str]:
    return [f"文書{i}" for i in range(n)]


def test_within_budget_uses_vectors():
    clock = _FakeClock()
    inner = _TimedEmbedder(clock, seconds_per_text=0.1)
    cached = CachedEmbedder(inner)

    decision = evaluate_embedding_budget(
        cached, _texts(100), budget_seconds=100.0, probe_size=8, timer=clock
    )

    assert decision.use_vectors is True
    assert decision.reason == "within_budget"
    assert decision.pending_count == 100
    # warm-up 1件 + probe 8件を除いた残り91件 × 0.1秒/件
    assert decision.estimated_seconds == pytest.approx(9.1)


def test_over_budget_falls_back_to_bm25():
    clock = _FakeClock()
    inner = _TimedEmbedder(clock, seconds_per_text=10.0)
    cached = CachedEmbedder(inner)

    decision = evaluate_embedding_budget(
        cached, _texts(100), budget_seconds=100.0, probe_size=8, timer=clock
    )

    assert decision.use_vectors is False
    assert decision.reason == "estimated_over_budget"
    assert decision.pending_count == 100
    assert decision.estimated_seconds > 100.0


def test_fully_cached_corpus_skips_probe_and_uses_vectors():
    clock = _FakeClock()
    inner = _TimedEmbedder(clock, seconds_per_text=10.0)
    cached = CachedEmbedder(inner)
    texts = _texts(10)
    cached.embed_documents(texts)  # 全件キャッシュ済みにする
    inner.calls.clear()

    decision = evaluate_embedding_budget(
        cached, texts, budget_seconds=100.0, probe_size=8, timer=clock
    )

    assert decision.use_vectors is True
    assert decision.pending_count == 0
    assert inner.calls == []  # probeも実行しない


def test_small_pending_within_probe_size_skips_probe():
    clock = _FakeClock()
    inner = _TimedEmbedder(clock, seconds_per_text=10.0)
    cached = CachedEmbedder(inner)

    decision = evaluate_embedding_budget(
        cached, _texts(8), budget_seconds=100.0, probe_size=8, timer=clock
    )

    assert decision.use_vectors is True
    assert decision.reason == "pending_within_probe"
    assert inner.calls == []


class _BrokenEmbedder:
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        raise RuntimeError("モデルがロードできない")

    def embed_query(self, text: str) -> np.ndarray:
        raise RuntimeError("モデルがロードできない")


def test_probe_failure_falls_back_to_bm25():
    clock = _FakeClock()
    cached = CachedEmbedder(_BrokenEmbedder())

    decision = evaluate_embedding_budget(
        cached, _texts(100), budget_seconds=100.0, probe_size=8, timer=clock
    )

    assert decision.use_vectors is False
    assert decision.reason == "probe_failed"
    assert decision.estimated_seconds is None


class _InstantEmbedder(_TimedEmbedder):
    def __init__(self, clock: _FakeClock) -> None:
        super().__init__(clock, seconds_per_text=0.0)


def test_zero_elapsed_probe_is_treated_as_no_throughput():
    """時計が進まない（throughput計測不能）場合は保守的にBM25へ退避する。"""
    clock = _FakeClock()
    cached = CachedEmbedder(_InstantEmbedder(clock))

    decision = evaluate_embedding_budget(
        cached, _texts(100), budget_seconds=100.0, probe_size=8, timer=clock
    )

    assert decision.use_vectors is False
    assert decision.reason == "no_throughput"


def test_probe_results_are_cached_and_reused():
    """probeで埋め込んだ分はキャッシュされ、本番encodeで再計算されない。"""
    clock = _FakeClock()
    inner = _TimedEmbedder(clock, seconds_per_text=0.1)
    cached = CachedEmbedder(inner)
    texts = _texts(100)

    evaluate_embedding_budget(cached, texts, budget_seconds=100.0, probe_size=8, timer=clock)
    probed = sum(len(c) for c in inner.calls)
    assert probed == 9  # warm-up 1 + probe 8

    inner.calls.clear()
    cached.embed_documents(texts)
    assert sum(len(c) for c in inner.calls) == 100 - 9
