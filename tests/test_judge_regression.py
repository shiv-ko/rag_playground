from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluator.judge_regression import (
    build_regression_dataset,
    evaluate_regression,
)


def _write_calibration(
    directory: Path,
    sequence: int,
    rows: list[dict[str, str]],
) -> Path:
    path = directory / f"judge_calibration_{sequence:02d}.json"
    path.write_text(json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")
    return path


def _row(
    *,
    question: str = "質問",
    answer: str = "回答",
    ground_truth: str = "正解",
    local: str = "Perfect",
    official: str = "Perfect",
) -> dict[str, str]:
    return {
        "question_id": "1",
        "question": question,
        "answer": answer,
        "ground_truth": ground_truth,
        "local_label": local,
        "official_label": official,
    }


def test_build_dataset_uses_oldest_15_and_latest_5_and_excludes_middle(
    tmp_path: Path,
) -> None:
    for sequence in range(1, 22):
        _write_calibration(
            tmp_path,
            sequence,
            [_row(question=f"q{sequence}", answer=f"a{sequence}")],
        )

    dataset = build_regression_dataset(tmp_path)

    assert [p.name for p in dataset.dev_files] == [
        f"judge_calibration_{i:02d}.json" for i in range(1, 16)
    ]
    assert [p.name for p in dataset.holdout_files] == [
        f"judge_calibration_{i:02d}.json" for i in range(17, 22)
    ]
    assert [p.name for p in dataset.excluded_files] == ["judge_calibration_16.json"]
    assert len(dataset.dev) == 15
    assert len(dataset.holdout) == 5


def test_explicit_manifest_does_not_rotate_when_new_file_is_added(
    tmp_path: Path,
) -> None:
    for sequence in range(1, 5):
        _write_calibration(
            tmp_path,
            sequence,
            [_row(question=f"q{sequence}", answer=f"a{sequence}")],
        )

    dataset = build_regression_dataset(
        tmp_path,
        dev_file_names=("judge_calibration_01.json",),
        holdout_file_names=("judge_calibration_03.json",),
    )

    assert [path.name for path in dataset.dev_files] == ["judge_calibration_01.json"]
    assert [path.name for path in dataset.holdout_files] == [
        "judge_calibration_03.json"
    ]
    assert [path.name for path in dataset.excluded_files] == [
        "judge_calibration_02.json",
        "judge_calibration_04.json",
    ]


def test_deduplicates_nfc_key_latest_wins_and_flags_official_instability(
    tmp_path: Path,
) -> None:
    # 「ガ」はNFD/NFCで表現を変えても同じ質問として扱う。
    _write_calibration(
        tmp_path,
        1,
        [
            _row(
                question="カ\N{COMBINING KATAKANA-HIRAGANA VOICED SOUND MARK}",
                official="Incorrect",
            )
        ],
    )
    _write_calibration(tmp_path, 2, [_row(question="ガ", official="Perfect")])

    dataset = build_regression_dataset(tmp_path, dev_file_count=1, holdout_file_count=1)

    assert dataset.dev == ()  # holdoutと重なるキーはリーク防止のためholdoutへ寄せる
    assert len(dataset.holdout) == 1
    record = dataset.holdout[0]
    assert record.question == "ガ"
    assert record.official_label == "Perfect"
    assert record.official_labels == ("Incorrect", "Perfect")
    assert record.official_label_unstable is True
    assert record.duplicate_count == 2


def test_evaluate_regression_calculates_required_metrics() -> None:
    rows = [
        _row(local="Perfect", official="Perfect"),
        _row(question="q2", local="Missing", official="Incorrect"),
        _row(question="q3", local="Incorrect", official="Incorrect"),
        _row(question="q4", local="Incorrect", official="Missing"),
    ]

    metrics = evaluate_regression(rows)

    assert metrics.total == 4
    assert metrics.agreement == pytest.approx(0.5)
    assert metrics.incorrect_recall == pytest.approx(0.5)
    assert metrics.mean_absolute_error == pytest.approx(0.5)
    assert metrics.confusion_matrix["Missing"]["Incorrect"] == 1
    assert metrics.confusion_matrix["Incorrect"]["Missing"] == 1


def test_incorrect_recall_is_none_when_official_has_no_incorrect() -> None:
    metrics = evaluate_regression([_row()])

    assert metrics.incorrect_recall is None


def test_rejects_unknown_crag_label(tmp_path: Path) -> None:
    _write_calibration(tmp_path, 1, [_row(official="unknown")])

    with pytest.raises(ValueError, match="official_label"):
        build_regression_dataset(tmp_path, dev_file_count=1, holdout_file_count=0)
