"""パイプライン結果からSIGNATE提出用のpredictions.csv（ヘッダーなし, index,answer）を生成する。"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.orchestrator.pipeline import Pipeline
from src.utils.question_loader import load_questions_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="predictions.csv 生成")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "predictions.csv")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--concurrent", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.4)
    args = parser.parse_args()

    qa_pairs = load_questions_csv(args.questions)

    pipeline = Pipeline(
        data_dir=args.data_dir,
        max_concurrent=args.concurrent,
        top_k=args.top_k,
        confidence_threshold=args.threshold,
        run_judge=False,
    )
    pipeline.build_index()
    results = pipeline.run(qa_pairs)

    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for r in sorted(results, key=lambda r: int(r.question_id)):
            writer.writerow([r.question_id, r.answer])

    print(f"書き出し完了: {args.out} ({len(results)}件)")


if __name__ == "__main__":
    main()
