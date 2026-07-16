"""固定judge回帰データを現在のLocalJudgeで再評価してJSON保存する。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.evaluator.judge import LocalJudge  # noqa: E402
from src.evaluator.judge_regression import (  # noqa: E402
    FIXED_DEV_FILE_NAMES,
    FIXED_HOLDOUT_FILE_NAMES,
    build_regression_dataset,
    rejudge_regression,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="固定local judge回帰データの再評価")
    parser.add_argument("--calibration-dir", type=Path, default=ROOT / "experiments")
    parser.add_argument("--split", choices=("dev", "holdout"), default="dev")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    dataset = build_regression_dataset(
        args.calibration_dir,
        dev_file_names=FIXED_DEV_FILE_NAMES,
        holdout_file_names=FIXED_HOLDOUT_FILE_NAMES,
    )
    rows = dataset.dev if args.split == "dev" else dataset.holdout
    source_files = dataset.dev_files if args.split == "dev" else dataset.holdout_files
    result = rejudge_regression(rows, LocalJudge())
    payload = {
        "schema_version": 1,
        "split": args.split,
        "source_files": [path.name for path in source_files],
        "metrics": result.metrics.to_dict(),
        "rows": list(result.rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metrics = result.metrics
    recall = (
        "N/A"
        if metrics.incorrect_recall is None
        else f"{metrics.incorrect_recall:.3f}"
    )
    print(
        f"{args.split}: n={metrics.total}, agreement={metrics.agreement:.3f}, "
        f"Incorrect recall={recall}, MAE={metrics.mean_absolute_error:.3f}"
    )
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
