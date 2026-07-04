from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


@dataclass
class Document:
    text: str
    source_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    # ページ番号、シート名等の位置情報
    location: str = ""

    def __repr__(self) -> str:
        return f"Document(source={self.source_path.name!r}, chars={len(self.text)}, loc={self.location!r})"


@dataclass
class ScoredDocument:
    document: Document
    score: float
    retrieval_method: str = ""  # "vector" / "keyword" / "hybrid"

    def __repr__(self) -> str:
        return f"ScoredDocument(score={self.score:.3f}, {self.document})"


@dataclass
class Answer:
    text: str
    confidence: float          # 0.0〜1.0
    source_docs: list[ScoredDocument] = field(default_factory=list)
    was_gated: bool = False    # 確信度ゲートによってMissingになった場合True
    raw_text: str = ""         # ゲート適用前のLLM回答（切り分け分析用）
    gate_reason: str = ""      # どのゲートで落ちたか（""=非ゲート。capability/no_context/missing_text/confidence/citation）


class CRAGLabel(str, Enum):
    PERFECT = "Perfect"
    ACCEPTABLE = "Acceptable"
    MISSING = "Missing"
    INCORRECT = "Incorrect"

    @property
    def score(self) -> float:
        return {
            CRAGLabel.PERFECT: 1.0,
            CRAGLabel.ACCEPTABLE: 0.5,
            CRAGLabel.MISSING: 0.0,
            CRAGLabel.INCORRECT: -1.0,
        }[self]


@dataclass
class JudgeResult:
    label: CRAGLabel
    reason: str
    score: float = field(init=False)

    def __post_init__(self) -> None:
        self.score = self.label.score
