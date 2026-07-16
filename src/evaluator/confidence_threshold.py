"""保存済みrunを使ったconfidence threshold引き上げの反実仮想分析。"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from src.generator.confidence_gate import (
    CAPABILITY_BLOCKED_TAGS,
    HIGH_RISK_TAGS,
    HIGH_RISK_THRESHOLD_BONUS,
)
from src.models import label_score

REQUIRED_FIELDS = frozenset({"confidence", "routing_tags", "raw_answer", "judge_label"})
VALID_LABELS = frozenset({"Perfect", "Acceptable", "Missing", "Incorrect"})


@dataclass(frozen=True)
class ScoreResult:
    mean_score: float
    total_score: float
    row_count: int
    gated_count: int = 0


@dataclass(frozen=True)
class Configuration(ScoreResult):
    common_threshold: float = 0.4
    tag_thresholds: dict[str, float] = field(default_factory=dict)
    holdout_mean_score: float | None = None
    holdout_gated_count: int | None = None


@dataclass(frozen=True)
class TagCandidate:
    tag: str
    count: int
    eligible: bool
    recommended_threshold: float


@dataclass(frozen=True)
class JudgeCandidate:
    question_id: str
    confidence: float
    routing_tags: list[str]
    raw_answer: str


@dataclass(frozen=True)
class ThresholdReport:
    current_threshold: float
    evaluated_thresholds: list[float]
    baseline: ScoreResult
    common_candidates: list[Configuration]
    tag_candidates: list[TagCandidate]
    best: Configuration
    conservative: Configuration
    needs_additional_judge: list[JudgeCandidate]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_run(path: Path | str) -> list[dict[str, Any]]:
    """run JSONを読み、分析に必須の保存済みフィールドを検証する。"""
    path = Path(path)
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise ValueError(f"{path}: results が配列ではありません")
    _validate_rows(rows, prefix=f"{path}: ")
    return rows


def _validate_rows(rows: list[dict[str, Any]], *, prefix: str = "") -> None:
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{prefix}results[{index}] がオブジェクトではありません")
        missing = sorted(REQUIRED_FIELDS - row.keys())
        if missing:
            raise ValueError(
                f"{prefix}results[{index}] に必須項目 {', '.join(missing)} がありません"
            )
        confidence = row["confidence"]
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError(
                f"{prefix}results[{index}].confidence が0〜1の有限数ではありません"
            )
        if not isinstance(row["routing_tags"], list):
            raise ValueError(
                f"{prefix}results[{index}].routing_tags が配列ではありません"
            )
        if not isinstance(row["raw_answer"], str):
            raise ValueError(
                f"{prefix}results[{index}].raw_answer が文字列ではありません"
            )
        if row["judge_label"] not in VALID_LABELS:
            raise ValueError(
                f"{prefix}results[{index}].judge_label が有効な判定ではありません"
            )


def _score_rows(
    rows: list[dict[str, Any]],
    common_threshold: float,
    tag_thresholds: dict[str, float],
) -> ScoreResult:
    total = 0.0
    gated = 0
    for row in rows:
        original = label_score(str(row["judge_label"]))
        # 既にMissingの行を回答へ戻す反実仮想はjudge結果がないため行わない。
        if str(row["judge_label"]) == "Missing":
            total += original
            continue
        base_threshold = max(
            [common_threshold]
            + [
                tag_thresholds[tag]
                for tag in row["routing_tags"]
                if tag in tag_thresholds
            ]
        )
        effective = _effective_threshold(base_threshold, row["routing_tags"])
        if float(row["confidence"]) < effective:
            gated += 1
        else:
            total += original
    count = len(rows)
    return ScoreResult(total / count if count else 0.0, total, count, gated)


def _effective_threshold(base_threshold: float, tags: Iterable[str]) -> float:
    if any(tag in HIGH_RISK_TAGS for tag in tags):
        return min(1.0, base_threshold + HIGH_RISK_THRESHOLD_BONUS)
    return base_threshold


def _configuration(
    development: list[dict[str, Any]],
    holdout: list[dict[str, Any]],
    common: float,
    per_tag: dict[str, float],
) -> Configuration:
    # 共通閾値以下のタグ値は実効値を変えないため、構成表示から除いて正規化する。
    effective_tags = {tag: value for tag, value in per_tag.items() if value > common}
    dev = _score_rows(development, common, effective_tags)
    hold = _score_rows(holdout, common, effective_tags) if holdout else None
    return Configuration(
        **asdict(dev),
        common_threshold=common,
        tag_thresholds=effective_tags,
        holdout_mean_score=hold.mean_score if hold else None,
        holdout_gated_count=hold.gated_count if hold else None,
    )


def _tag_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for tag in set(map(str, row["routing_tags"])):
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def analyze_thresholds(
    development_rows: list[dict[str, Any]],
    *,
    holdout_rows: list[dict[str, Any]] | None = None,
    current_threshold: float = 0.4,
    candidate_thresholds: Iterable[float] = (0.4, 0.5, 0.6, 0.7, 0.8),
    min_tag_count: int = 5,
    max_configurations: int = 1_000_000,
) -> ThresholdReport:
    """開発データだけで共通・タグ別閾値を探索し、選択構成をholdout評価する。"""
    holdout = holdout_rows or []
    _validate_rows(development_rows, prefix="development: ")
    _validate_rows(holdout, prefix="holdout: ")
    if not 0 <= current_threshold <= 1:
        raise ValueError("current_threshold は0〜1で指定してください")
    if min_tag_count < 1:
        raise ValueError("min_tag_count は1以上で指定してください")
    requested = {float(value) for value in candidate_thresholds}
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in requested):
        raise ValueError("candidate_thresholds は0〜1で指定してください")
    lower_thresholds = sorted(value for value in requested if value < current_threshold)
    thresholds = sorted(value for value in requested if value >= current_threshold)
    if current_threshold not in thresholds:
        thresholds.insert(0, current_threshold)
    baseline = _score_rows(development_rows, current_threshold, {})
    common = [
        _configuration(development_rows, holdout, value, {}) for value in thresholds
    ]
    counts = _tag_counts(development_rows)
    eligible_tags = sorted(
        tag for tag, count in counts.items() if count >= min_tag_count
    )
    combinations = len(thresholds) ** (len(eligible_tags) + 1)
    if combinations > max_configurations:
        raise ValueError(
            f"探索構成数 {combinations:,} が上限 {max_configurations:,} を超えます。"
            "候補かタグを減らしてください"
        )

    configurations: list[Configuration] = []
    for values in itertools.product(thresholds, repeat=len(eligible_tags) + 1):
        common_value = values[0]
        per_tag = dict(zip(eligible_tags, values[1:], strict=True))
        configurations.append(
            _configuration(development_rows, holdout, common_value, per_tag)
        )

    # 同点なら、最高スコア構成は個別overrideが少ないもの、次にゲートが弱いものを選ぶ。
    def best_key(config: Configuration) -> tuple[float, int, int, float]:
        overrides = sum(
            value != config.common_threshold for value in config.tag_thresholds.values()
        )
        return (
            config.mean_score,
            -overrides,
            -config.gated_count,
            config.common_threshold,
        )

    best = max(configurations, key=best_key)
    best_score = best.mean_score
    # 保守的構成は最高スコアを維持する中で最も多く回答をMissingへ寄せる。
    conservative = max(
        (
            config
            for config in configurations
            if abs(config.mean_score - best_score) < 1e-12
        ),
        key=lambda config: (
            config.gated_count,
            sum(config.tag_thresholds.values()),
            config.common_threshold,
        ),
    )

    tag_candidates: list[TagCandidate] = []
    for tag, count in sorted(counts.items()):
        if count < min_tag_count:
            recommended = current_threshold
            eligible = False
        else:
            candidates = [
                _configuration(development_rows, [], current_threshold, {tag: value})
                for value in thresholds
            ]
            selected = max(candidates, key=best_key)
            recommended = selected.tag_thresholds.get(tag, current_threshold)
            eligible = True
        tag_candidates.append(TagCandidate(tag, count, eligible, recommended))

    needs_judge = [
        JudgeCandidate(
            question_id=str(row.get("question_id", "")),
            confidence=float(row["confidence"]),
            routing_tags=list(map(str, row["routing_tags"])),
            raw_answer=str(row["raw_answer"]),
        )
        # holdoutを追加judgeへ回すと選択フィードバックになるため、開発側だけを列挙する。
        for row in development_rows
        if str(row["judge_label"]) == "Missing"
        and bool(str(row["raw_answer"]).strip())
        and not any(tag in CAPABILITY_BLOCKED_TAGS for tag in row["routing_tags"])
        and row.get("gate_reason", "confidence") == "confidence"
        and any(
            _effective_threshold(lower, row["routing_tags"])
            <= float(row["confidence"])
            < _effective_threshold(current_threshold, row["routing_tags"])
            for lower in lower_thresholds
        )
    ]
    return ThresholdReport(
        current_threshold=current_threshold,
        evaluated_thresholds=thresholds,
        baseline=baseline,
        common_candidates=common,
        tag_candidates=tag_candidates,
        best=best,
        conservative=conservative,
        needs_additional_judge=needs_judge,
    )
