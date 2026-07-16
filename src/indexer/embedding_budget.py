"""cold index時のembedding時間予算判定。

設計: docs/plan/2026-07-16-cold-fallback-design.md
embeddingは途中で安全に中断しにくいため、encode開始前に
「未処理チャンク数 × 同一環境の実測throughput」で所要時間を見積もり、
予算超過またはthroughput実測不能ならBM25単体へ退避する。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from src.indexer.embedder import CachedEmbedder

# index安全上限（2時間目標）。全体上限10,800秒−generation・出力予約900秒=9,900秒より
# さらに保守的な値を設計で採用している（cold-fallback-design.md）
INDEX_BUDGET_SECONDS = 7200.0
PROBE_SIZE = 64


@dataclass(frozen=True)
class EmbeddingBudgetDecision:
    use_vectors: bool
    pending_count: int
    estimated_seconds: float | None
    reason: str


def evaluate_embedding_budget(
    embedder: CachedEmbedder,
    texts: list[str],
    budget_seconds: float = INDEX_BUDGET_SECONDS,
    probe_size: int = PROBE_SIZE,
    timer: Callable[[], float] = time.perf_counter,
) -> EmbeddingBudgetDecision:
    """encode開始前にembedding所要時間を見積もり、ベクトル検索を使うか判定する。

    probeで埋め込んだ分はCachedEmbedderにキャッシュされ、本番encodeで再利用される。
    """
    pending = embedder.pending_texts(texts)
    pending_count = len(pending)
    if pending_count <= probe_size:
        return EmbeddingBudgetDecision(
            use_vectors=True,
            pending_count=pending_count,
            estimated_seconds=0.0,
            reason="pending_within_probe",
        )

    try:
        # 初回encodeはモデルロードを含み計測が歪むため、1件でウォームアップしてから計測する
        embedder.embed_documents(pending[:1])
        start = timer()
        embedder.embed_documents(pending[1 : 1 + probe_size])
        elapsed = timer() - start
    except Exception:
        return EmbeddingBudgetDecision(
            use_vectors=False,
            pending_count=pending_count,
            estimated_seconds=None,
            reason="probe_failed",
        )

    if elapsed <= 0:
        return EmbeddingBudgetDecision(
            use_vectors=False,
            pending_count=pending_count,
            estimated_seconds=None,
            reason="no_throughput",
        )

    throughput = probe_size / elapsed
    remaining = pending_count - 1 - probe_size
    estimated_seconds = remaining / throughput
    if estimated_seconds > budget_seconds:
        return EmbeddingBudgetDecision(
            use_vectors=False,
            pending_count=pending_count,
            estimated_seconds=estimated_seconds,
            reason="estimated_over_budget",
        )
    return EmbeddingBudgetDecision(
        use_vectors=True,
        pending_count=pending_count,
        estimated_seconds=estimated_seconds,
        reason="within_budget",
    )
