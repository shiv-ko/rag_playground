"""確信度が閾値未満、または能力外の設問タイプなら回答をMissing相当に差し替えるゲート。"""
from __future__ import annotations

from collections.abc import Sequence

MISSING_RESPONSE = "提供された資料からは、ご質問に対する回答を見つけることができませんでした。"

CAPABILITY_BLOCKED_TAGS = frozenset({"image_or_graph", "password_protected"})
HIGH_RISK_TAGS = frozenset({"multi_hop"})
HIGH_RISK_THRESHOLD_BONUS = 0.2


class ConfidenceGate:
    def __init__(self, threshold: float = 0.4) -> None:
        self.threshold = threshold

    def is_capability_blocked(self, tags: Sequence[str] = ()) -> bool:
        return any(tag in CAPABILITY_BLOCKED_TAGS for tag in tags)

    def should_answer(self, confidence: float, tags: Sequence[str] = ()) -> bool:
        if self.is_capability_blocked(tags):
            return False
        effective_threshold = self.threshold
        if any(tag in HIGH_RISK_TAGS for tag in tags):
            effective_threshold = min(1.0, self.threshold + HIGH_RISK_THRESHOLD_BONUS)
        return confidence >= effective_threshold

    def missing_text(self) -> str:
        return MISSING_RESPONSE


_MISSING_PHRASES = ("わかりません", "見つかりません", "不明です")


def looks_like_missing(text: str) -> bool:
    """LLMの回答本文がMissing相当の自己申告かどうかを判定する。"""
    return any(phrase in text for phrase in _MISSING_PHRASES)
