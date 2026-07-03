"""パイプライン結果からSIGNATE提出用のpredictions.csv（ヘッダーなし, index,answer）を生成する。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

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
    parser.add_argument("--artifacts-dir", type=Path, default=ROOT / "artifacts",
                        help="レジストリJSON・構造化artifactsのディレクトリ")
    args = parser.parse_args()

    qa_pairs = load_questions_csv(args.questions)

    # run_pipeline.pyと同じ構成でレジストリを接続する（提出生成でも同一の回答経路を通す）
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
        run_judge=False,
        project_aliases=project_aliases,
        term_registry=term_registry,
        artifacts_dir=args.artifacts_dir,
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
