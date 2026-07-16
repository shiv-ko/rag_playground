"""judge較正JSON群から固定dev/holdout回帰データと指標を作る。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluator.judge_regression import (  # noqa: E402
    FIXED_DEV_FILE_NAMES,
    FIXED_HOLDOUT_FILE_NAMES,
    RegressionDataset,
    build_regression_dataset,
    evaluate_regression,
)


def _split_payload(rows: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "metrics": evaluate_regression(rows).to_dict(),
        "official_unstable_count": sum(row.official_label_unstable for row in rows),
        "rows": [row.to_dict() for row in rows],
    }


def _payload(dataset: RegressionDataset) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "deduplication_key": ["question", "answer", "ground_truth"],
        "dev_files": [path.name for path in dataset.dev_files],
        "holdout_files": [path.name for path in dataset.holdout_files],
        "excluded_files": [path.name for path in dataset.excluded_files],
        "dev": _split_payload(dataset.dev),
        "holdout": _split_payload(dataset.holdout),
    }


def _print_metrics(name: str, split: dict[str, Any]) -> None:
    metrics = split["metrics"]
    recall = metrics["incorrect_recall"]
    recall_text = "N/A" if recall is None else f"{recall:.3f}"
    print(
        f"{name}: n={metrics['total']}, agreement={metrics['agreement']:.3f}, "
        f"Incorrect recall={recall_text}, MAE={metrics['mean_absolute_error']:.3f}, "
        f"official揺らぎ={split['official_unstable_count']}"
    )
    print("  confusion matrix (local -> official):")
    for local, counts in metrics["confusion_matrix"].items():
        print(f"    {local}: {counts}")


def main() -> None:
    parser = argparse.ArgumentParser(description="local judgeのオフライン回帰分析")
    parser.add_argument("--calibration-dir", type=Path, default=ROOT / "experiments")
    parser.add_argument("--output", type=Path, help="回帰データと指標をJSON保存")
    args = parser.parse_args()

    dataset = build_regression_dataset(
        args.calibration_dir,
        dev_file_names=FIXED_DEV_FILE_NAMES,
        holdout_file_names=FIXED_HOLDOUT_FILE_NAMES,
    )
    payload = _payload(dataset)
    print(
        f"files: dev={len(dataset.dev_files)}, holdout={len(dataset.holdout_files)}, "
        f"excluded={len(dataset.excluded_files)}"
    )
    _print_metrics("dev", payload["dev"])
    _print_metrics("holdout", payload["holdout"])

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
