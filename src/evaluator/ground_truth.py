"""正解回答（valid_txt.csv）のローダー。評価スクリプト共用。

valid_txt.csv は**ヘッダなし** `index,answer` 形式（questions_valid.csv とは別物）。
"""
from __future__ import annotations

import csv
from pathlib import Path


def load_ground_truth(path: Path) -> dict[str, str]:
    """valid_txt.csv（ヘッダなし index,answer）を読む。"""
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {row[0]: row[1] for row in csv.reader(f) if row}
