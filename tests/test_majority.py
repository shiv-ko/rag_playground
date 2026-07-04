from src.evaluator.majority import majority_labels, to_pseudo_run, unstable_questions


def _run(labels: dict[str, str]) -> dict:
    return {
        "summary": {},
        "results": [
            {"question_id": qid, "question": f"質問{qid}", "judge_label": label, "answer": "a"}
            for qid, label in labels.items()
        ],
    }


RUNS = [
    _run({"0": "Perfect", "1": "Missing", "2": "Perfect"}),
    _run({"0": "Perfect", "1": "Perfect", "2": "Missing"}),
    _run({"0": "Perfect", "1": "Missing", "2": "Incorrect"}),
]


def test_majority_unanimous_and_split():
    m = majority_labels(RUNS)
    assert m["0"]["label"] == "Perfect" and m["0"]["votes"] == 3
    assert m["1"]["label"] == "Missing" and m["1"]["votes"] == 2


def test_majority_three_way_tie_takes_worst():
    # Q2はPerfect/Missing/Incorrectの3すくみ → スコア最小のIncorrectを採用（保守側）
    m = majority_labels(RUNS)
    assert m["2"]["label"] == "Incorrect"


def test_unstable_questions_lists_non_unanimous():
    unstable = unstable_questions(RUNS)
    ids = {u["question_id"] for u in unstable}
    assert ids == {"1", "2"}


def test_to_pseudo_run_feeds_compare_runs():
    from src.evaluator.flip import compare_runs

    m = majority_labels(RUNS)
    pseudo = to_pseudo_run(m)
    rep = compare_runs(pseudo, pseudo)
    assert rep.unchanged_count == 3
