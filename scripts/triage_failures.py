"""Missing切り分け表の生成。

run JSON（raw_answer/retrieved_sources付き・Task 2以降のrun）と
retrieval eval JSON（Task 3）を突き合わせ、各問を分類して
docs/plan/missing_triage_<YYYYMMDD>.md に書き出す。

使い方:
  .venv/bin/python scripts/triage_failures.py \
      experiments/phase0_valid_XXXX.json experiments/retrieval_valid_YYYY.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.evaluator.ground_truth import load_ground_truth
from src.evaluator.triage import classify, needs_raw_judge


def load_label_types(path: Path, split: str) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {
            r["index"]: r["primary_type"]
            for r in csv.DictReader(f)
            if r["split"] == split
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="失敗切り分け表の生成")
    parser.add_argument("run_json", type=Path)
    parser.add_argument("retrieval_json", type=Path)
    parser.add_argument("--answers", type=Path,
                        default=ROOT / "data" / "raw" / "evaluation" / "data" / "valid_txt.csv")
    parser.add_argument("--labels", type=Path, default=ROOT / "docs" / "question_labels.csv")
    parser.add_argument("--split", default="valid")
    parser.add_argument("--judge", choices=["openai", "local", "none"], default="openai",
                        help="ゲート前回答の正誤判定に使うjudge")
    args = parser.parse_args()

    run = json.loads(args.run_json.read_text(encoding="utf-8"))
    retrieval = json.loads(args.retrieval_json.read_text(encoding="utf-8"))
    truth = load_ground_truth(args.answers)
    types = load_label_types(args.labels, args.split)
    ret_by_id = {r["question_id"]: r for r in retrieval["records"]}

    raw_judge = None
    if args.judge == "openai":
        from src.evaluator.openai_judge import OpenAICragJudge
        raw_judge = OpenAICragJudge()
    elif args.judge == "local":
        from src.evaluator.judge import LocalJudge
        local = LocalJudge()
        class _Wrapper:
            def score(self, generated_answer, ground_truth):
                return local.score(question="", generated_answer=generated_answer,
                                   reference_or_context=ground_truth)
        raw_judge = _Wrapper()

    rows = []
    for r in run["results"]:
        qid = r["question_id"]
        ret = ret_by_id.get(qid, {"measurable": False, "hit": False})
        raw_label = None
        if raw_judge is not None and needs_raw_judge(
            r["judge_label"], r["was_gated"], ret["measurable"], ret["hit"],
            r.get("raw_answer", ""),
        ):
            gt = truth.get(qid, "")
            raw_label = raw_judge.score(
                generated_answer=r["raw_answer"], ground_truth=gt
            ).label.value

        cls = classify(r["judge_label"], r["was_gated"], ret["measurable"],
                       ret["hit"], raw_label)
        rows.append({
            "question_id": qid,
            "primary_type": types.get(qid, "?"),
            "judge_label": r["judge_label"],
            "hit": ret["hit"],
            "was_gated": r["was_gated"],
            "raw_judge_label": raw_label or "-",
            "class": cls,
            "question": r["question"],
        })
        print(f"  {qid}: {cls} ({types.get(qid, '?')})")

    counts = Counter(row["class"] for row in rows)

    lines = [
        f"# valid 失敗切り分け表（{date.today().isoformat()}）",
        "",
        f"run: `{args.run_json.name}` / retrieval: `{args.retrieval_json.name}` / raw判定judge: {args.judge}",
        "",
        "## 集計",
        "",
        "| 分類 | 件数 |",
        "|---|---|",
    ]
    for cls, count in counts.most_common():
        lines.append(f"| {cls} | {count} |")
    lines += [
        "",
        "## 質問別",
        "",
        "| # | type | 最終label | 検索hit | gated | 生回答判定 | 分類 | 質問 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['question_id']} | {row['primary_type']} | {row['judge_label']} "
            f"| {'○' if row['hit'] else '×'} | {'○' if row['was_gated'] else '-'} "
            f"| {row['raw_judge_label']} | {row['class']} | {row['question'][:40]} |"
        )

    out_path = ROOT / "docs" / "plan" / f"missing_triage_{date.today().strftime('%Y%m%d')}.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n分類集計: {dict(counts)}")
    print(f"切り分け表: {out_path}")


if __name__ == "__main__":
    main()
