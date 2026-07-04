"""load_ground_truth のテスト。ヘッダなし・BOM・カンマ入り回答を検証する。"""
from pathlib import Path

from src.evaluator.ground_truth import load_ground_truth


def test_load_ground_truth_headerless_bom_and_quoted_comma(tmp_path: Path):
    csv_path = tmp_path / "valid_txt.csv"
    csv_path.write_bytes(
        "﻿".encode("utf-8")
        + '0,hr、weekday\n1,"A, B"\n'.encode("utf-8")
    )
    truth = load_ground_truth(csv_path)
    assert truth == {"0": "hr、weekday", "1": "A, B"}
