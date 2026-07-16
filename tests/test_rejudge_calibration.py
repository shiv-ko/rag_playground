from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import rejudge_calibration as module
from src.evaluator.judge_regression import RegressionDataset, RegressionRecord
from src.models import CRAGLabel, JudgeResult


def test_default_split_is_dev() -> None:
    args = module.parse_args(["--output", "result.json"])

    assert args.split == "dev"


def test_holdout_requires_explicit_split_value() -> None:
    args = module.parse_args(["--split", "holdout", "--output", "result.json"])

    assert args.split == "holdout"


@pytest.mark.parametrize(
    ("split_args", "expected_answer", "expected_split"),
    [([], "dev-answer", "dev"), (["--split", "holdout"], "holdout-answer", "holdout")],
)
def test_main_scores_only_selected_split_with_fake_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    split_args: list[str],
    expected_answer: str,
    expected_split: str,
) -> None:
    def record(answer: str, official: str) -> RegressionRecord:
        unstable = answer == "holdout-answer"
        return RegressionRecord(
            question_id=answer,
            question=f"question-{answer}",
            answer=answer,
            ground_truth=f"truth-{answer}",
            local_label="Missing",
            official_label=official,
            official_labels=(("Perfect", official) if unstable else (official,)),
            official_label_unstable=unstable,
            duplicate_count=1,
            source_files=(f"{answer}.json",),
        )

    dataset = RegressionDataset(
        dev=(record("dev-answer", "Perfect"),),
        holdout=(record("holdout-answer", "Incorrect"),),
        dev_files=(Path("dev.json"),),
        holdout_files=(Path("holdout.json"),),
        excluded_files=(),
    )

    class FakeJudge:
        def __init__(self) -> None:
            self.answers: list[str] = []

        def score(
            self, question: str, generated_answer: str, reference_or_context: str
        ) -> JudgeResult:
            self.answers.append(generated_answer)
            label = (
                CRAGLabel.PERFECT
                if generated_answer == "dev-answer"
                else CRAGLabel.INCORRECT
            )
            return JudgeResult(label=label, reason="fake")

    fake = FakeJudge()
    monkeypatch.setattr(
        module, "build_regression_dataset", lambda *args, **kwargs: dataset
    )
    monkeypatch.setattr(module, "LocalJudge", lambda: fake)
    output = tmp_path / "result.json"

    module.main([*split_args, "--output", str(output)])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert fake.answers == [expected_answer]
    assert payload["split"] == expected_split
    assert payload["rows"][0]["new_local_label"] in {"Perfect", "Incorrect"}
    assert set(payload["metrics"]) == {
        "total",
        "agreement",
        "incorrect_recall",
        "mean_absolute_error",
        "confusion_matrix",
    }
    assert set(payload["stable_metrics"]) == set(payload["metrics"])
    assert payload["unstable_count"] == (1 if expected_split == "holdout" else 0)
