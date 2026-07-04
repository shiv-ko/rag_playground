"""judge較正: 既存runの回答を本番同一プロンプトのOpenAI CRAGジャッジで再採点し、
ローカルClaude judgeとの乖離表を出す。

使い方:
  .venv/bin/python scripts/calibrate_judge.py experiments/baseline_valid_XXXX.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.evaluator.openai_judge import OpenAICragJudge
from src.models import CRAGLabel


def load_ground_truth(path: Path) -> dict[str, str]:
    """valid_txt.csv（ヘッダなし index,answer）を読む。"""
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {row[0]: row[1] for row in csv.reader(f) if row}


def main() -> None:
    parser = argparse.ArgumentParser(description="ローカルjudgeとOpenAI CRAG judgeの較正")
    parser.add_argument("run_json", type=Path, help="対象run（experiments/*.json）")
    parser.add_argument("--answers", type=Path,
                        default=ROOT / "data" / "raw" / "evaluation" / "data" / "valid_txt.csv")
    parser.add_argument("--model", default="gpt-5.2-2025-12-11")
    args = parser.parse_args()

    run = json.loads(args.run_json.read_text(encoding="utf-8"))
    truth = load_ground_truth(args.answers)
    judge = OpenAICragJudge(model=args.model)

    rows = []
    for r in run["results"]:
        gt = truth.get(r["question_id"])
        if gt is None:
            print(f"警告: 正解なし question_id={r['question_id']}")
            continue
        official = judge.score(generated_answer=r["answer"], ground_truth=gt)
        rows.append({
            "question_id": r["question_id"],
            "question": r["question"],
            "answer": r["answer"],
            "ground_truth": gt,
            "local_label": r["judge_label"],
            "official_label": official.label.value,
            "official_score": official.score,
        })
        print(f"  {r['question_id']}: local={r['judge_label']:>10} / official={official.label.value}")

    if not rows:
        sys.exit("採点対象が0件です（runのquestion_idと--answersの正解indexが一致していません）")

    official_mean = sum(row["official_score"] for row in rows) / len(rows)
    local_mean = sum(CRAGLabel(row["local_label"]).score for row in rows) / len(rows)
    agree = sum(row["local_label"] == row["official_label"] for row in rows)

    print(f"\n=== 較正結果 ({args.run_json.name}, {len(rows)}問) ===")
    print(f"official mean: {official_mean:.4f} / local mean: {local_mean:.4f}")
    print(f"一致率: {agree}/{len(rows)} ({100 * agree / len(rows):.0f}%)")

    matrix = Counter((row["local_label"], row["official_label"]) for row in rows)
    print("\n[乖離マトリクス local → official]")
    for (local, official), count in sorted(matrix.items()):
        marker = "" if local == official else "  ← 乖離"
        print(f"  {local:>10} → {official:<10} {count}件{marker}")

    out_path = ROOT / "experiments" / f"judge_calibration_{int(time.time())}.json"
    out_path.write_text(json.dumps({
        "run": args.run_json.name,
        "model": args.model,
        "official_mean": official_mean,
        "local_mean": local_mean,
        "agreement": agree / len(rows),
        "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n結果保存: {out_path}")


if __name__ == "__main__":
    main()
