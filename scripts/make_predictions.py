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

from src.orchestrator.answer_stabilizer import align_run_answers, stabilize_answers
from src.orchestrator.pipeline import Pipeline
from src.utils.question_loader import load_questions_csv


def write_predictions(path: Path, rows: list[tuple[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for question_id, answer in rows:
            writer.writerow([question_id, answer])


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
    parser.add_argument("--no-cache", action="store_true",
                        help="パース・埋め込みキャッシュを使わず再計算する")
    parser.add_argument("--conservative", action="store_true",
                        help="保守構成: 多数決で勝っても内容の矛盾する少数派回答がある質問はMissingへ倒す")
    parser.add_argument("--hybrid-search", dest="hybrid_search", action="store_true", default=True,
                        help="BM25+日本語埋め込みベクトルのハイブリッド検索を使う（デフォルト。要 pip install -e '.[embeddings]'）")
    parser.add_argument("--no-hybrid-search", dest="hybrid_search", action="store_false",
                        help="BM25単体検索に戻す")
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
        cache_dir=None if args.no_cache else ROOT / ".cache",
        # 質問CSVの置き場（質問回答/）はコーパスから除外する（run_pipeline.pyと同一規則）
        exclude_dirs=[args.questions.parent],
        use_hybrid_search=args.hybrid_search,
    )
    pipeline.build_index()
    if args.runs == 1:
        results = pipeline.run(qa_pairs)

        write_predictions(
            args.out,
            [(r.question_id, r.answer) for r in sorted(results, key=lambda r: int(r.question_id))],
        )

        print(f"書き出し完了: {args.out} ({len(results)}件)")
        return

    # pipeline.runは例外時もMissing行で埋めて返すが、念のため質問リスト由来のIDを正とし
    # 万一runごとに欠落があってもMissing票として補完する（1問の一時エラーで全runを捨てない）
    question_ids = sorted((qa.question_id for qa in qa_pairs), key=int)
    per_run_maps = [
        {r.question_id: r.answer for r in pipeline.run(qa_pairs)}
        for _ in range(args.runs)
    ]
    per_run_answers, dropped = align_run_answers(question_ids, per_run_maps)
    for run_index, missing_ids in enumerate(dropped):
        if missing_ids:
            print(f"警告: run {run_index} で回答が得られなかった質問をMissing票として補完: {missing_ids}")

    decisions = stabilize_answers(
        question_ids=question_ids,
        per_run_answers=per_run_answers,
        conservative=args.conservative,
    )

    write_predictions(args.out, [(d.question_id, d.chosen) for d in decisions])
    print(f"書き出し完了: {args.out} ({len(decisions)}件)")

    # 監査ファイルは証跡であり提出物ではないので、書き込み失敗でCSV生成を失敗扱いにしない
    audit_path = ROOT / "experiments" / f"predictions_stability_{int(time.time())}.json"
    try:
        audit_path.parent.mkdir(exist_ok=True)
        audit_path.write_text(
            json.dumps(
                {
                    "runs": args.runs,
                    "dropped_question_ids_per_run": dropped,
                    "decisions": [asdict(decision) for decision in decisions],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"安定化監査: {audit_path}")
    except OSError as e:
        print(f"警告: 監査ファイルの書き込みに失敗（predictions.csvは正常）: {e}")


if __name__ == "__main__":
    main()
