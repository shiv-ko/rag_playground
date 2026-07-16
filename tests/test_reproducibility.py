from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.evaluator.reproducibility import audit_run_payloads


def _result(
    question_id: str,
    answer: str,
    *,
    was_gated: bool = False,
    answer_path: str = "retrieval",
    sources: list[str] | None = None,
) -> dict:
    return {
        "question_id": question_id,
        "answer": answer,
        "was_gated": was_gated,
        "answer_path": answer_path,
        "retrieved_sources": sources if sources is not None else ["a::chunk1"],
    }


def test_audit_reports_agreement_and_field_flips_for_all_questions() -> None:
    run1 = {
        "results": [
            _result("8", "東京"),
            _result("94", "回答なし", was_gated=True),
        ]
    }
    run2 = {
        "results": [
            _result("8", "大阪", sources=["b::chunk2"]),
            _result("94", "東京", was_gated=False, answer_path="structured:analysis"),
        ]
    }

    report = audit_run_payloads([run1, run2], run_names=["first", "second"])

    assert report["question_count"] == 2
    assert report["metrics"]["final_answer"] == {
        "comparable_count": 2,
        "matching_count": 0,
        "agreement_rate": 0.0,
    }
    assert report["metrics"]["answer_status"]["agreement_rate"] == 0.5
    assert report["metrics"]["answer_path"]["agreement_rate"] == 0.5
    assert report["metrics"]["retrieved_sources"]["agreement_rate"] == 0.5
    flips = {flip["question_id"]: flip for flip in report["flips"]}
    assert flips["8"]["changed_fields"] == ["final_answer", "retrieved_sources"]
    assert flips["8"]["values"]["first"]["final_answer"] == "東京"
    assert flips["94"]["changed_fields"] == [
        "final_answer", "answer_status", "answer_path"
    ]
    assert report["stage_flips"] == {
        "retrieval": ["8"],
        "generation": ["8", "94"],
        "gate": ["94"],
        "routing": ["94"],
    }


def test_audit_compares_three_or_more_runs_by_unanimous_equality() -> None:
    payloads = [
        {"results": [_result("1", "A")]},
        {"results": [_result("1", "A")]},
        {"results": [_result("1", "B")]},
    ]

    report = audit_run_payloads(payloads)

    assert report["run_count"] == 3
    assert report["metrics"]["final_answer"]["matching_count"] == 0
    assert report["flips"][0]["values"]["run_3"]["final_answer"] == "B"


def test_audit_accepts_majority_json_and_marks_missing_fields_unavailable() -> None:
    run1 = {"decisions": [{"question_id": "1", "chosen": "東京"}]}
    run2 = {"decisions": [{"question_id": "1", "chosen": "東京"}]}

    report = audit_run_payloads([run1, run2])

    assert report["metrics"]["final_answer"]["agreement_rate"] == 1.0
    assert report["metrics"]["answer_status"]["agreement_rate"] == 1.0
    assert report["metrics"]["answer_path"] == {
        "comparable_count": 0,
        "matching_count": 0,
        "agreement_rate": None,
    }
    assert report["flips"] == []


def test_audit_rejects_duplicate_or_inconsistent_question_ids() -> None:
    duplicate = {"results": [_result("1", "A"), _result("1", "B")]}
    with pytest.raises(ValueError, match="duplicate question_id"):
        audit_run_payloads([duplicate, {"results": [_result("1", "A")]}])

    with pytest.raises(ValueError, match="question_id sets differ"):
        audit_run_payloads([
            {"results": [_result("1", "A")]},
            {"results": [_result("2", "A")]},
        ])


def test_cli_writes_json_to_stdout_and_output_file(tmp_path: Path) -> None:
    paths = []
    for index, answer in enumerate(["A", "B"], start=1):
        path = tmp_path / f"run{index}.json"
        path.write_text(
            json.dumps({"results": [_result("37", answer)]}), encoding="utf-8"
        )
        paths.append(path)
    output = tmp_path / "audit.json"

    completed = subprocess.run(
        [
            ".venv/bin/python",
            "scripts/audit_reproducibility.py",
            *(str(path) for path in paths),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
    )

    stdout_report = json.loads(completed.stdout)
    file_report = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_report == file_report
    assert stdout_report["flips"][0]["question_id"] == "37"
