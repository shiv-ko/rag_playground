from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.evaluator.confidence_threshold import analyze_thresholds, load_run


def _row(
    qid: str,
    confidence: float,
    label: str,
    tags: list[str],
    *,
    raw_answer: str = "回答",
) -> dict:
    return {
        "question_id": qid,
        "confidence": confidence,
        "routing_tags": tags,
        "raw_answer": raw_answer,
        "judge_label": label,
    }


def test_raise_only_counterfactual_and_best_configurations() -> None:
    development = [
        _row("1", 0.45, "Incorrect", ["text_only"]),
        _row("2", 0.55, "Perfect", ["text_only"]),
        _row("3", 0.95, "Perfect", ["multi_hop"]),
        _row("4", 0.85, "Incorrect", ["multi_hop"]),
    ]

    report = analyze_thresholds(
        development,
        current_threshold=0.4,
        candidate_thresholds=[0.4, 0.5, 0.7, 0.8],
        min_tag_count=2,
    )

    assert report.baseline.mean_score == pytest.approx(0.0)
    assert report.best.common_threshold == 0.5
    assert report.best.tag_thresholds == {"multi_hop": 0.7}
    assert report.best.mean_score == pytest.approx(0.5)
    assert report.conservative.mean_score == report.best.mean_score
    assert report.conservative.gated_count >= report.best.gated_count
    assert {item.tag for item in report.tag_candidates} == {"multi_hop", "text_only"}


def test_rare_tag_keeps_common_threshold_and_holdout_is_not_optimized() -> None:
    development = [
        _row("1", 0.45, "Incorrect", ["rare"]),
        _row("2", 0.9, "Perfect", ["text_only"]),
        _row("3", 0.9, "Perfect", ["text_only"]),
    ]
    holdout = [_row("h1", 0.45, "Perfect", ["rare"])]

    report = analyze_thresholds(
        development,
        holdout_rows=holdout,
        current_threshold=0.4,
        candidate_thresholds=[0.4, 0.5],
        min_tag_count=2,
    )

    assert report.best.tag_thresholds == {}
    # holdoutは構成選択に使わないため、開発で選ばれた0.5をそのまま評価する。
    assert report.best.holdout_mean_score == pytest.approx(0.0)
    rare = next(item for item in report.tag_candidates if item.tag == "rare")
    assert rare.eligible is False
    assert rare.recommended_threshold == 0.4


def test_missing_raw_answer_is_only_reported_as_needing_judge() -> None:
    rows = [
        _row("1", 0.2, "Missing", ["text_only"], raw_answer="候補回答"),
        _row("2", 0.1, "Missing", ["text_only"], raw_answer=""),
        _row("3", 0.5, "Missing", ["multi_hop"], raw_answer="複数段候補"),
    ]

    report = analyze_thresholds(
        rows,
        current_threshold=0.4,
        candidate_thresholds=[0.2, 0.4, 0.5],
        min_tag_count=1,
    )

    assert report.baseline.mean_score == 0.0
    assert [candidate.question_id for candidate in report.needs_additional_judge] == [
        "1",
        "3",
    ]
    assert report.evaluated_thresholds == [0.4, 0.5]


def test_load_run_requires_saved_analysis_fields(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"results": [{"question_id": "1"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="confidence"):
        load_run(path)


def test_unjudged_run_is_rejected_instead_of_scored_as_zero() -> None:
    rows = [_row("1", 0.5, "", ["text_only"])]

    with pytest.raises(ValueError, match="judge_label"):
        analyze_thresholds(rows)


def test_lowering_candidate_requires_requested_lower_threshold() -> None:
    rows = [_row("1", 0.2, "Missing", ["text_only"], raw_answer="候補回答")]

    report = analyze_thresholds(rows, candidate_thresholds=[0.4, 0.5])

    assert report.needs_additional_judge == []


def test_holdout_lowering_candidate_is_not_exposed_for_additional_judge() -> None:
    development = [_row("d", 0.9, "Perfect", ["text_only"])]
    holdout = [_row("h", 0.2, "Missing", ["text_only"], raw_answer="盲検回答")]

    report = analyze_thresholds(
        development,
        holdout_rows=holdout,
        candidate_thresholds=[0.2, 0.4],
    )

    assert report.needs_additional_judge == []


def test_cli_outputs_json_without_question_labels(tmp_path: Path) -> None:
    run = tmp_path / "run.json"
    run.write_text(
        json.dumps({"results": [_row("1", 0.45, "Incorrect", ["text_only"])]}),
        encoding="utf-8",
    )
    script = Path(__file__).parents[1] / "scripts" / "analyze_confidence_threshold.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            str(run),
            "--candidates",
            "0.4,0.5",
            "--min-tag-count",
            "1",
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["best"]["mean_score"] == 0.0
    assert "needs_additional_judge" in payload
