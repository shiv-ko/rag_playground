from __future__ import annotations

from scripts.analyze_judge_calibration import _split_payload
from src.evaluator.judge_regression import RegressionRecord


def _record(*, unstable: bool) -> RegressionRecord:
    return RegressionRecord(
        question_id="1",
        question="q",
        answer="a",
        ground_truth="gt",
        local_label="Perfect",
        official_label="Perfect" if not unstable else "Incorrect",
        official_labels=("Perfect",) if not unstable else ("Perfect", "Incorrect"),
        official_label_unstable=unstable,
        duplicate_count=1,
        source_files=("source.json",),
    )


def test_split_payload_adds_stable_metrics_and_keeps_old_unstable_count() -> None:
    payload = _split_payload((_record(unstable=False), _record(unstable=True)))

    assert payload["metrics"]["total"] == 2
    assert payload["stable_metrics"]["total"] == 1
    assert payload["unstable_count"] == 1
    assert payload["official_unstable_count"] == 1
