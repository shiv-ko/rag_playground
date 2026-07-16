"""Local judgeのオフライン回帰データ構築と評価。

回答生成パイプラインから独立した評価専用モジュールである。
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from src.models import CRAGLabel, JudgeResult

LABELS = tuple(label.value for label in CRAGLabel)
_FILE_RE = re.compile(r"judge_calibration_(\d+)\.json$")

# 2026-07-16時点で確定した回帰セット。新しい較正runを追加しても回転させない。
FIXED_DEV_FILE_NAMES = (
    "judge_calibration_1783125320.json",
    "judge_calibration_1783140909.json",
    "judge_calibration_1783143105.json",
    "judge_calibration_1783159723.json",
    "judge_calibration_1783163986.json",
    "judge_calibration_1783169170.json",
    "judge_calibration_1783177178.json",
    "judge_calibration_1783182281.json",
    "judge_calibration_1783236763.json",
    "judge_calibration_1783293004.json",
    "judge_calibration_1783341078.json",
    "judge_calibration_1783520472.json",
    "judge_calibration_1783521863.json",
    "judge_calibration_1783603984.json",
    "judge_calibration_1783777064.json",
)
FIXED_HOLDOUT_FILE_NAMES = (
    "judge_calibration_1783848948.json",
    "judge_calibration_1783945810.json",
    "judge_calibration_1784040090.json",
    "judge_calibration_1784145455.json",
    "judge_calibration_1784184775.json",
)


@dataclass(frozen=True)
class RegressionRecord:
    question_id: str
    question: str
    answer: str
    ground_truth: str
    local_label: str
    official_label: str
    official_labels: tuple[str, ...]
    official_label_unstable: bool
    duplicate_count: int
    source_files: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegressionDataset:
    dev: tuple[RegressionRecord, ...]
    holdout: tuple[RegressionRecord, ...]
    dev_files: tuple[Path, ...]
    holdout_files: tuple[Path, ...]
    excluded_files: tuple[Path, ...]


@dataclass(frozen=True)
class RegressionMetrics:
    total: int
    agreement: float
    incorrect_recall: float | None
    mean_absolute_error: float
    confusion_matrix: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegressionEvaluation:
    metrics: RegressionMetrics
    stable_metrics: RegressionMetrics
    unstable_count: int


@dataclass(frozen=True)
class RejudgeResult:
    rows: tuple[dict[str, Any], ...]
    metrics: RegressionMetrics
    stable_metrics: RegressionMetrics
    unstable_count: int


class JudgeScorer(Protocol):
    def score(
        self,
        question: str,
        generated_answer: str,
        reference_or_context: str,
    ) -> JudgeResult: ...


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _file_order(path: Path) -> int:
    match = _FILE_RE.fullmatch(path.name)
    if match is None:  # glob結果なので通常は到達しない
        raise ValueError(f"較正ファイル名が不正です: {path.name}")
    return int(match.group(1))


def _validate_label(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or value not in LABELS:
        raise ValueError(f"{path.name}: {field} が不正です: {value!r}")
    return value


def _load_rows(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{path.name}: rows が配列ではありません")

    required = ("question_id", "question", "answer", "ground_truth")
    loaded: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}: rows[{index}] がobjectではありません")
        values: dict[str, str] = {}
        for field in required:
            value = row.get(field)
            if not isinstance(value, (str, int)):
                raise ValueError(f"{path.name}: rows[{index}].{field} が不正です")
            values[field] = _normalise(str(value))
        values["local_label"] = _validate_label(
            row.get("local_label"), "local_label", path
        )
        values["official_label"] = _validate_label(
            row.get("official_label"), "official_label", path
        )
        loaded.append(values)
    return loaded


def build_regression_dataset(
    calibration_dir: Path,
    *,
    dev_file_count: int = 15,
    holdout_file_count: int = 5,
    dev_file_names: Sequence[str] | None = None,
    holdout_file_names: Sequence[str] | None = None,
) -> RegressionDataset:
    """古いdevファイルと直近holdoutファイルから重複なしデータを作る。

    両splitに同じ質問×回答×GTがある場合は、時間的リークを避けるため
    最新観測の属するholdoutへ割り当てる。official/localラベルも最新観測を採る。
    """
    if (dev_file_names is None) != (holdout_file_names is None):
        raise ValueError("dev/holdoutのmanifestは両方指定してください")
    if dev_file_count < 0 or holdout_file_count < 0:
        raise ValueError("ファイル数は0以上で指定してください")
    files = tuple(
        sorted(calibration_dir.glob("judge_calibration_*.json"), key=_file_order)
    )
    if dev_file_names is not None and holdout_file_names is not None:
        dev_files = tuple(calibration_dir / name for name in dev_file_names)
        holdout_files = tuple(calibration_dir / name for name in holdout_file_names)
        selected = set(dev_files + holdout_files)
        if len(selected) != len(dev_files) + len(holdout_files):
            raise ValueError("dev/holdoutのmanifestに重複があります")
        missing = [path.name for path in selected if not path.is_file()]
        if missing:
            raise ValueError(f"manifestの較正ファイルがありません: {sorted(missing)}")
        excluded_files = tuple(path for path in files if path not in selected)
    else:
        selected_count = dev_file_count + holdout_file_count
        if len(files) < selected_count:
            raise ValueError(
                "較正ファイルが不足しています: "
                f"必要={selected_count}, 実際={len(files)}"
            )
        dev_files = files[:dev_file_count]
        holdout_files = (
            files[len(files) - holdout_file_count :] if holdout_file_count else ()
        )
        excluded_end = (
            len(files) - holdout_file_count if holdout_file_count else len(files)
        )
        excluded_files = files[dev_file_count:excluded_end]

    groups: dict[tuple[str, str, str], list[tuple[str, Path, dict[str, str]]]] = {}
    for split, split_files in (("dev", dev_files), ("holdout", holdout_files)):
        for path in split_files:
            for row in _load_rows(path):
                key = (row["question"], row["answer"], row["ground_truth"])
                groups.setdefault(key, []).append((split, path, row))

    split_records: dict[str, list[RegressionRecord]] = {"dev": [], "holdout": []}
    for observations in groups.values():
        latest_split, _, latest = observations[-1]
        official_labels = tuple(item[2]["official_label"] for item in observations)
        record = RegressionRecord(
            question_id=latest["question_id"],
            question=latest["question"],
            answer=latest["answer"],
            ground_truth=latest["ground_truth"],
            local_label=latest["local_label"],
            official_label=latest["official_label"],
            official_labels=official_labels,
            official_label_unstable=len(set(official_labels)) > 1,
            duplicate_count=len(observations),
            source_files=tuple(item[1].name for item in observations),
        )
        split_records[latest_split].append(record)

    return RegressionDataset(
        dev=tuple(split_records["dev"]),
        holdout=tuple(split_records["holdout"]),
        dev_files=tuple(dev_files),
        holdout_files=tuple(holdout_files),
        excluded_files=tuple(excluded_files),
    )


def _value(row: RegressionRecord | Mapping[str, Any], field: str) -> Any:
    return getattr(row, field) if isinstance(row, RegressionRecord) else row[field]


def evaluate_regression(
    rows: Sequence[RegressionRecord | Mapping[str, Any]],
) -> RegressionMetrics:
    """local（予測）をofficial（正解）に対して評価する。"""
    matrix = {predicted: {actual: 0 for actual in LABELS} for predicted in LABELS}
    agreements = 0
    absolute_errors = 0.0
    incorrect_total = 0
    incorrect_hits = 0

    for row in rows:
        predicted = _validate_label(
            _value(row, "local_label"), "local_label", Path("row")
        )
        actual = _validate_label(
            _value(row, "official_label"), "official_label", Path("row")
        )
        matrix[predicted][actual] += 1
        agreements += predicted == actual
        incorrect_total += actual == CRAGLabel.INCORRECT.value
        incorrect_hits += actual == predicted == CRAGLabel.INCORRECT.value
        absolute_errors += abs(CRAGLabel(predicted).score - CRAGLabel(actual).score)

    total = len(rows)
    return RegressionMetrics(
        total=total,
        agreement=agreements / total if total else 0.0,
        incorrect_recall=(
            incorrect_hits / incorrect_total if incorrect_total else None
        ),
        mean_absolute_error=absolute_errors / total if total else 0.0,
        confusion_matrix=matrix,
    )


def evaluate_regression_summary(
    rows: Sequence[RegressionRecord | Mapping[str, Any]],
) -> RegressionEvaluation:
    """全行とofficial labelが安定した行を分けて評価する。

    旧形式のmappingに揺らぎフラグがない場合はstableとして扱う。
    """
    stable_rows = tuple(
        row
        for row in rows
        if not (
            row.official_label_unstable
            if isinstance(row, RegressionRecord)
            else bool(row.get("official_label_unstable", False))
        )
    )
    return RegressionEvaluation(
        metrics=evaluate_regression(rows),
        stable_metrics=evaluate_regression(stable_rows),
        unstable_count=len(rows) - len(stable_rows),
    )


def rejudge_regression(
    rows: Sequence[RegressionRecord], judge: JudgeScorer
) -> RejudgeResult:
    """固定回帰レコードをjudgeで再採点し、新ラベル基準の指標を返す。"""
    rejudged: list[dict[str, Any]] = []
    metric_rows: list[dict[str, str]] = []
    for row in rows:
        judged = judge.score(
            question=row.question,
            generated_answer=row.answer,
            reference_or_context=row.ground_truth,
        )
        payload = row.to_dict()
        payload["new_local_label"] = judged.label.value
        payload["new_local_reason"] = judged.reason
        rejudged.append(payload)
        metric_rows.append(
            {
                "local_label": judged.label.value,
                "official_label": row.official_label,
                "official_label_unstable": row.official_label_unstable,
            }
        )
    evaluation = evaluate_regression_summary(metric_rows)
    return RejudgeResult(
        rows=tuple(rejudged),
        metrics=evaluation.metrics,
        stable_metrics=evaluation.stable_metrics,
        unstable_count=evaluation.unstable_count,
    )
