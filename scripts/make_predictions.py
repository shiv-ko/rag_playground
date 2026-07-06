"""パイプライン結果からSIGNATE提出用のpredictions.csv（ヘッダーなし, index,answer）を生成する。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.orchestrator.answer_stabilizer import stabilize_answers
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
    parser.add_argument("--runs", type=int, default=1,
                        help="提出用回答生成を複数回実行し、N>1なら正規化多数決で安定化する")
    parser.add_argument("--artifacts-dir", type=Path, default=ROOT / "artifacts",
                        help="レジストリJSON・構造化artifactsのディレクトリ")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be >= 1")

    qa_pairs = load_questions_csv(args.questions)

    # run_pipeline.pyと同じ構成でレジストリを接続する（提出生成でも同一の回答経路を通す）
    project_aliases: dict[str, list[str]] = {}
    project_primary_aliases: dict[str, str] = {}
    term_registry: list[dict] = []
    projects_path = args.artifacts_dir / "project_registry.json"
    terms_path = args.artifacts_dir / "term_registry.json"
    if projects_path.exists():
        projects = json.loads(projects_path.read_text(encoding="utf-8"))
        project_aliases = {p["project_name"]: p.get("aliases", []) for p in projects}
        project_primary_aliases = {
            p["project_name"]: p["primary_alias"] for p in projects if p.get("primary_alias")
        }
    if terms_path.exists():
        term_registry = json.loads(terms_path.read_text(encoding="utf-8"))

    pipeline = Pipeline(
        data_dir=args.data_dir,
        max_concurrent=args.concurrent,
        top_k=args.top_k,
        confidence_threshold=args.threshold,
        run_judge=False,
        project_aliases=project_aliases,
        project_primary_aliases=project_primary_aliases,
        term_registry=term_registry,
        artifacts_dir=args.artifacts_dir,
    )
    pipeline.build_index()
    if args.runs == 1:
        results = pipeline.run(qa_pairs)

        with args.out.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            for r in sorted(results, key=lambda r: int(r.question_id)):
                writer.writerow([r.question_id, r.answer])

        print(f"書き出し完了: {args.out} ({len(results)}件)")
        return

    sorted_runs = [
        sorted(pipeline.run(qa_pairs), key=lambda r: int(r.question_id))
        for _ in range(args.runs)
    ]
    question_ids = [r.question_id for r in sorted_runs[0]]
    for run_results in sorted_runs[1:]:
        run_question_ids = [r.question_id for r in run_results]
        if run_question_ids != question_ids:
            raise ValueError("question_id mismatch between runs")

    decisions = stabilize_answers(
        question_ids=question_ids,
        per_run_answers=[[r.answer for r in run_results] for run_results in sorted_runs],
    )

    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for decision in decisions:
            writer.writerow([decision.question_id, decision.chosen])

    experiments_dir = ROOT / "experiments"
    experiments_dir.mkdir(exist_ok=True)
    audit_path = experiments_dir / f"predictions_stability_{int(time.time())}.json"
    audit_path.write_text(
        json.dumps(
            {"runs": args.runs, "decisions": [asdict(decision) for decision in decisions]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"書き出し完了: {args.out} ({len(decisions)}件)")
    print(f"安定化監査: {audit_path}")


if __name__ == "__main__":
    main()
