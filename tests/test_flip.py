from src.evaluator.flip import compare_runs


def _run(labels: dict[str, str]) -> dict:
    return {
        "summary": {},
        "results": [
            {"question_id": qid, "question": f"質問{qid}", "judge_label": label,
             "answer": "回答"}
            for qid, label in labels.items()
        ],
    }


def test_compare_runs_detects_flips():
    base = _run({"0": "Missing", "1": "Perfect", "2": "Incorrect", "3": "Missing"})
    new = _run({"0": "Perfect", "1": "Missing", "2": "Incorrect", "3": "Missing"})
    rep = compare_runs(base, new, base_name="base", new_name="new")

    assert [f["question_id"] for f in rep.improved] == ["0"]
    assert [f["question_id"] for f in rep.worsened] == ["1"]
    assert rep.unchanged_count == 2
    assert rep.base_mean == (0 + 1 - 1 + 0) / 4
    assert rep.new_mean == (1 + 0 - 1 + 0) / 4


def test_compare_runs_handles_missing_ids():
    """片方にしか無いquestion_idは無視（共通部分のみ比較）。"""
    base = _run({"0": "Missing", "9": "Perfect"})
    new = _run({"0": "Perfect"})
    rep = compare_runs(base, new)
    assert [f["question_id"] for f in rep.improved] == ["0"]
    assert rep.unchanged_count == 0


def test_report_is_readable():
    base = _run({"0": "Missing"})
    new = _run({"0": "Perfect"})
    text = compare_runs(base, new).report()
    assert "Missing" in text and "Perfect" in text and "0" in text
