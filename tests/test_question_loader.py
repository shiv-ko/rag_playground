"""CSV形式の質問ファイル読み込みのテスト。"""
from __future__ import annotations

from pathlib import Path

from src.utils.question_loader import load_questions_csv


def test_loads_questions_with_answer_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "questions_valid.csv"
    csv_path.write_text(
        "index,question,answer\n0,質問A,回答A\n1,質問B,回答B\n",
        encoding="utf-8-sig",
    )
    pairs = load_questions_csv(csv_path)
    assert len(pairs) == 2
    assert pairs[0].question_id == "0"
    assert pairs[0].question == "質問A"
    assert pairs[0].reference_answer == "回答A"


def test_loads_questions_without_answer_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "questions_test.csv"
    csv_path.write_text("index,question\n0,質問A\n1,質問B\n", encoding="utf-8-sig")
    pairs = load_questions_csv(csv_path)
    assert len(pairs) == 2
    assert pairs[0].reference_answer == ""


def test_handles_bom_in_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "q.csv"
    csv_path.write_bytes("﻿index,question\n0,質問A\n".encode("utf-8"))
    pairs = load_questions_csv(csv_path)
    assert pairs[0].question_id == "0"
    assert pairs[0].question == "質問A"
