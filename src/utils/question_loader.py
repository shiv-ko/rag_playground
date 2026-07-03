"""questions_valid.csv / questions_test.csv 形式のCSVを読み込むローダー。"""
from __future__ import annotations

import csv
from pathlib import Path

from src.orchestrator.pipeline import QAPair


def load_questions_csv(path: Path) -> list[QAPair]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [
            QAPair(
                question_id=row["index"],
                question=row["question"],
                reference_answer=row.get("answer") or "",
            )
            for row in reader
        ]
