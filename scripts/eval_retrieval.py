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
    parser.add_argument("--hybrid-search", dest="hybrid_search", action="store_true", default=True,
                        help="BM25+日本語埋め込みベクトルのハイブリッド検索を使う（デフォルト。要 pip install -e '.[embeddings]'）")
    parser.add_argument("--no-hybrid-search", dest="hybrid_search", action="store_false",
                        help="BM25単体検索に戻す")
    parser.add_argument("--exclude-dir", type=Path, action="append", default=None,
                        help="コーパスから除外するディレクトリ（複数指定可）。"
                             "評価用質問CSVの置き場（質問回答/等）をdata-dir配下に含む場合は必須 — "
                             "取り込むと正解リークになる")
    args = parser.parse_args()

    # 既定のdata-dir（共有ドライブ）は質問回答/の兄弟なので安全だが、
    # data/raw/share を渡した場合に備え、質問回答/ が配下にあれば自動で除外する
    exclude_dirs = list(args.exclude_dir or [])
    default_qa_dir = args.data_dir / "質問回答"
    if default_qa_dir.is_dir():
        exclude_dirs.append(default_qa_dir)

    docs = (
        ParserDispatcher().parse_directory(args.data_dir, exclude_dirs=exclude_dirs)
        if args.no_cache
        else load_or_parse(args.data_dir, ROOT / ".cache", exclude_dirs=exclude_dirs)
    )

    project_registry = json.loads(
        (ROOT / "artifacts" / "project_registry.json").read_text(encoding="utf-8")
    )
    project_aliases = {p["project_name"]: p.get("aliases", []) for p in project_registry}
    embedder = None
    if args.hybrid_search:
        from src.indexer.embedder import CachedEmbedder, JapaneseEmbedder
        embedder = CachedEmbedder(JapaneseEmbedder(), cache_path=ROOT / ".cache" / "embeddings_ruri-base.pkl")
    retriever = ProjectScopedRetriever(project_aliases=project_aliases, embedder=embedder)
    retriever.add(docs)
    if embedder is not None:
        embedder.flush()

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
