"""スコア集計ユーティリティ。"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.models import CRAGLabel, JudgeResult


@dataclass
class EvalSummary:
    total: int
    label_counts: dict[str, int]
    mean_score: float
    scores: list[float]

    def report(self) -> str:
        lines = [
            f"Total: {self.total}",
            f"Mean score: {self.mean_score:.4f}",
        ]
        for label in CRAGLabel:
            count = self.label_counts.get(label.value, 0)
            pct = 100 * count / self.total if self.total else 0
            lines.append(f"  {label.value}: {count} ({pct:.1f}%)")
        return "\n".join(lines)


def summarize(results: list[JudgeResult]) -> EvalSummary:
    scores = [r.score for r in results]
    counts = Counter(r.label.value for r in results)
    mean = sum(scores) / len(scores) if scores else 0.0
    return EvalSummary(
        total=len(results),
        label_counts=dict(counts),
        mean_score=mean,
        scores=scores,
    )
