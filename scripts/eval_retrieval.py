"""検索単体評価スクリプト。実インデックスを組み、valid質問のretrieval recallを出す。

LLMは呼ばないため無料。パース結果はキャッシュされる（Task 1）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluator.retrieval_eval import (
    candidate_files,
    evaluate_one,
    load_labels,
    records_to_payload,
    summarize_records,
)
from src.parsers.dispatcher import ParserDispatcher
from src.retriever.project_scoped_retriever import ProjectScopedRetriever
from src.utils.parse_cache import load_or_parse


def main() -> None:
    parser = argparse.ArgumentParser(description="retrieval recall 評価")
    parser.add_argument("--data-dir", type=Path,
                        default=ROOT / "data" / "raw" / "share" / "共有ドライブ")
    parser.add_argument("--labels", type=Path, default=ROOT / "docs" / "question_labels.csv")
    parser.add_argument("--split", default="valid")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments")
    parser.add_argument("--no-cache", action="store_true",
                        help="パースキャッシュを使わず、現在のparser/chunkerで再パースする")
    args = parser.parse_args()

    docs = (
        ParserDispatcher().parse_directory(args.data_dir)
        if args.no_cache
        else load_or_parse(args.data_dir, ROOT / ".cache")
    )

    project_registry = json.loads(
        (ROOT / "artifacts" / "project_registry.json").read_text(encoding="utf-8")
    )
    project_aliases = {p["project_name"]: p.get("aliases", []) for p in project_registry}
    retriever = ProjectScopedRetriever(project_aliases=project_aliases)
    retriever.add(docs)

    labels = load_labels(args.labels, split=args.split)
    doc_registry = [
        json.loads(line)
        for line in (ROOT / "artifacts" / "document_registry.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    records = []
    for label in labels:
        cand = candidate_files(label, doc_registry, project_registry)
        records.append(evaluate_one(retriever.search, label, cand, top_k=args.top_k))

    print(summarize_records(records))
    misses = [r for r in records if r.measurable and not r.hit]
    if misses:
        print("\n[検索失敗（候補ファイルがtop-kに無い）]")
        for r in misses:
            print(f"  {args.split}#{r.question_id} ({r.primary_type}) 候補{r.candidate_count}件")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"retrieval_{args.split}_{int(time.time())}.json"
    out_path.write_text(
        json.dumps(records_to_payload(records), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n結果保存: {out_path}")


if __name__ == "__main__":
    main()
