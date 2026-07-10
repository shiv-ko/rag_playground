"""run JSON の Missing を type・gate・経路で集計する評価専用CLI。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluator.missing_diagnostics import (
    diagnose_missing,
    find_latest_run,
    infer_split,
    load_labels,
    render_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Missing回答の経路別診断")
    parser.add_argument("run_json", nargs="?", type=Path,
                        help="省略時はexperiments内の最新run JSON")
    parser.add_argument("--experiments-dir", type=Path, default=ROOT / "experiments")
    parser.add_argument("--labels", type=Path, default=ROOT / "docs" / "question_labels.csv",
                        help="評価専用ラベルCSV（回答生成には使用しない）")
    parser.add_argument("--split", help="省略時は質問文の一致数から推定")
    parser.add_argument("--output", type=Path, help="Markdownの保存先（省略時はstdout）")
    args = parser.parse_args()

    run_path = args.run_json or find_latest_run(args.experiments_dir)
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    results = payload.get("results")
    if not isinstance(results, list):
        parser.error(f"results配列を持つrun JSONではありません: {run_path}")
    labels = load_labels(args.labels)
    split = args.split or infer_split(results, labels)
    if split not in labels:
        parser.error(f"labelsにsplit={split!r}がありません")

    report = render_markdown(diagnose_missing(results, labels[split]), run_path, split)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(args.output)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
