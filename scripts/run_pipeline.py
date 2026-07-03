"""エンドツーエンドパイプライン実行スクリプト。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.orchestrator.pipeline import Pipeline, QAPair
from src.utils.logging import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="RAGパイプライン実行")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "sample",
                        help="ドキュメントディレクトリ")
    parser.add_argument("--questions", type=Path, default=ROOT / "data" / "sample" / "questions.json",
                        help="質問JSONファイル")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments",
                        help="結果出力ディレクトリ")
    parser.add_argument("--run-name", default="run", help="実験名")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--concurrent", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.4)
    args = parser.parse_args()

    logger = setup_logging()

    if not args.questions.exists():
        logger.error(f"質問ファイルが見つかりません: {args.questions}")
        logger.info("先に python scripts/make_sample_data.py を実行してください")
        sys.exit(1)

    if args.questions.suffix.lower() == ".csv":
        from src.utils.question_loader import load_questions_csv
        qa_pairs = load_questions_csv(args.questions)
    else:
        qa_raw = json.loads(args.questions.read_text(encoding="utf-8"))
        qa_pairs = [
            QAPair(
                question_id=item["id"],
                question=item["question"],
                reference_answer=item.get("answer", ""),
            )
            for item in qa_raw
        ]

    pipeline = Pipeline(
        data_dir=args.data_dir,
        max_concurrent=args.concurrent,
        top_k=args.top_k,
        confidence_threshold=args.threshold,
    )

    pipeline.build_index()
    results = pipeline.run(qa_pairs)
    pipeline.save_results(results, args.out_dir, args.run_name)


if __name__ == "__main__":
    main()
