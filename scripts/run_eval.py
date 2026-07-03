"""過去の実験結果JSONを読み込んでスコアを再集計する。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluator.metrics import summarize
from src.models import CRAGLabel, JudgeResult


def main() -> None:
    experiments_dir = ROOT / "experiments"
    jsons = sorted(experiments_dir.glob("*.json"))
    if not jsons:
        print("experiments/ に結果ファイルがありません。run_pipeline.py を先に実行してください。")
        return

    for path in jsons:
        data = json.loads(path.read_text(encoding="utf-8"))
        results = [
            JudgeResult(label=CRAGLabel(r["judge_label"]), reason=r["judge_reason"])
            for r in data["results"]
        ]
        summary = summarize(results)
        print(f"\n=== {path.name} ===")
        print(summary.report())

        # Incorrect一覧（要分析ケース）
        incorrects = [
            r for r in data["results"] if r["judge_label"] == "Incorrect"
        ]
        if incorrects:
            print(f"\n[要分析: Incorrect {len(incorrects)}件]")
            for r in incorrects:
                print(f"  {r['question_id']}: {r['question'][:60]}")
                print(f"    -> {r['answer'][:80]}")


if __name__ == "__main__":
    main()
