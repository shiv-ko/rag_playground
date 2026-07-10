import json
import unicodedata
from pathlib import Path

import pytest

from src.evaluator.missing_diagnostics import (
    aggregate,
    diagnose_missing,
    find_latest_run,
    infer_split,
)


LABELS = {
    "valid": {"0": ("office_style", "valid質問")},
    "test": {"0": ("spreadsheet_state", "test質問")},
}


def test_infer_split_uses_question_text_when_ids_overlap() -> None:
    assert infer_split([{"question_id": "0", "question": "test質問"}], LABELS) == "test"


def test_infer_split_normalizes_nfd_question_text() -> None:
    labels = {"test": {"0": ("single_text", "かえで病院の質問")}}
    results = [{"question_id": "0", "question": unicodedata.normalize("NFD", "かえで病院の質問")}]
    assert infer_split(results, labels) == "test"


def test_infer_split_rejects_unknown_questions() -> None:
    with pytest.raises(ValueError):
        infer_split([{"question_id": "0", "question": "不明"}], LABELS)


def test_diagnose_missing_groups_structured_fallback() -> None:
    results = [{
        "question_id": "0", "question": "train.xlsxのフィルターを確認してください",
        "judge_label": "", "was_gated": True, "gate_reason": "missing_text",
        "retrieved_sources": ["data/example.xlsx::sheet_train"],
    }]
    rows = diagnose_missing(results, LABELS["test"])
    assert rows[0].routing == "spreadsheet_state"
    assert rows[0].structured_path == "structured_not_observed:legacy_run"
    assert aggregate(rows) == {
        ("spreadsheet_state", "missing_text", "spreadsheet_state",
         "structured_not_observed:legacy_run"): 1
    }


def test_explicit_answer_path_takes_priority_over_legacy_inference() -> None:
    results = [{
        "question_id": "0", "question": "train.xlsxのフィルターを確認してください",
        "judge_label": "", "was_gated": True, "gate_reason": "missing_text",
        "routing_tags": ["spreadsheet_state"], "answer_path": "retrieval",
        "retrieved_sources": ["data/example.xlsx::sheet_train_row_2"],
    }]
    rows = diagnose_missing(results, LABELS["test"])
    assert rows[0].structured_path == "retrieval"


def test_diagnose_missing_detects_structured_context_gated() -> None:
    results = [{
        "question_id": "0", "question": "旧版と新版の変更内容",
        "judge_label": "Missing", "was_gated": True, "gate_reason": "citation",
        "retrieved_sources": ["data/new.xlsx::version_diff_r1_r2"],
    }]
    rows = diagnose_missing(results, LABELS["test"])
    assert rows[0].structured_path == "structured_fired:version_diff:gated"


def test_diagnose_missing_ignores_answered_no_judge_row() -> None:
    results = [{
        "question_id": "0", "question": "test質問", "judge_label": "",
        "was_gated": False, "gate_reason": "", "retrieved_sources": [],
    }]
    assert diagnose_missing(results, LABELS["test"]) == []


def test_legacy_spreadsheet_calc_without_sources_is_not_assumed_to_have_fired() -> None:
    row = {
        "question_id": "0", "question": "平均を算出してください",
        "judge_label": "Perfect", "was_gated": False, "gate_reason": "",
        "retrieved_sources": [],
    }
    from src.evaluator.missing_diagnostics import infer_structured_path
    assert infer_structured_path(row, ["spreadsheet_calc"]) == "structured_not_observed:legacy_run"


def test_find_latest_run_skips_non_run_json(tmp_path: Path) -> None:
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    newest_non_run = tmp_path / "calibration.json"
    old.write_text(json.dumps({"results": []}), encoding="utf-8")
    new.write_text(json.dumps({"results": [{}]}), encoding="utf-8")
    newest_non_run.write_text(json.dumps({"records": []}), encoding="utf-8")
    old.touch()
    new.touch()
    newest_non_run.touch()
    # mtime同値になりうる環境でも、newだけを後の時刻に固定する。
    import os
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))
    os.utime(newest_non_run, (3, 3))
    assert find_latest_run(tmp_path) == new
