"""エンドツーエンドパイプライン実行スクリプト。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

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
    parser.add_argument("--artifacts-dir", type=Path, default=ROOT / "artifacts",
                        help="レジストリJSONのディレクトリ")
    parser.add_argument("--no-cache", action="store_true", help="パース結果キャッシュを使わない")
    parser.add_argument("--no-judge", action="store_true",
                        help="judgeを実行しない（GTのないtest質問の診断run用。gate_reason等は保存される）")
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

    project_aliases: dict[str, list[str]] = {}
    term_registry: list[dict] = []
    projects_path = args.artifacts_dir / "project_registry.json"
    terms_path = args.artifacts_dir / "term_registry.json"
    if projects_path.exists():
        projects = json.loads(projects_path.read_text(encoding="utf-8"))
        project_aliases = {p["project_name"]: p.get("aliases", []) for p in projects}
    if terms_path.exists():
        term_registry = json.loads(terms_path.read_text(encoding="utf-8"))

    pipeline = Pipeline(
        data_dir=args.data_dir,
        max_concurrent=args.concurrent,
        top_k=args.top_k,
        confidence_threshold=args.threshold,
        run_judge=not args.no_judge,
        project_aliases=project_aliases,
        term_registry=term_registry,
        artifacts_dir=args.artifacts_dir,
        cache_dir=None if args.no_cache else ROOT / ".cache",
        # 質問CSVの置き場（質問回答/）はコーパスから除外する — valid CSVは正解列を
        # 含むため、取り込むと検索経由の正解リークになる（20260705の事故）
        exclude_dirs=[args.questions.parent],
    )

    pipeline.build_index()
    results = pipeline.run(qa_pairs)
    pipeline.save_results(results, args.out_dir, args.run_name)


if __name__ == "__main__":
    main()
