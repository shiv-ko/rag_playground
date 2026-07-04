"""N run多数決の評価。同一コードのrunを3つ渡すと多数決mean・不安定問を出す。

使い方:
  .venv/bin/python scripts/majority_eval.py A1.json A2.json A3.json
  .venv/bin/python scripts/majority_eval.py A1.json A2.json A3.json --vs B1.json B2.json B3.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluator.flip import compare_runs
from src.evaluator.majority import majority_labels, to_pseudo_run, unstable_questions
from src.models import CRAGLabel


def _load_group(paths: list[Path]) -> list[dict]:
    runs = []
    for p in paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        if "results" not in data:
            sys.exit(f"{p.name} はpipelineのrun JSONではありません（resultsキーなし）")
        runs.append(data)
    return runs


def _report_group(name: str, runs: list[dict]) -> dict:
    majority = majority_labels(runs)
    scores = [CRAGLabel(m["label"]).score for m in majority.values()]
    mean = sum(scores) / len(scores) if scores else 0.0
    print(f"\n=== {name}: 多数決mean {mean:.4f}（{len(runs)} run, {len(majority)}問） ===")
    unstable = unstable_questions(runs)
    if unstable:
        print(f"[不安定（全会一致でない）: {len(unstable)}問]")
        for u in unstable:
            print(f"  {u['question_id']}: {'/'.join(u['labels'])}  {u['question'][:50]}")
    return majority


def main() -> None:
    parser = argparse.ArgumentParser(description="N run多数決評価")
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--vs", nargs="+", type=Path, default=None,
                        help="比較先グループ（多数決同士でflip）")
    args = parser.parse_args()

    base_majority = _report_group("グループA", _load_group(args.runs))
    if args.vs:
        new_majority = _report_group("グループB", _load_group(args.vs))
        print()
        print(compare_runs(
            to_pseudo_run(base_majority), to_pseudo_run(new_majority),
            base_name="A多数決", new_name="B多数決",
        ).report())


if __name__ == "__main__":
    main()
