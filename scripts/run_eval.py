"""実験結果JSONの再集計＋run間flip分析。

使い方:
  .venv/bin/python scripts/run_eval.py                # 全run集計＋最新2runのflip
  .venv/bin/python scripts/run_eval.py A.json B.json  # 指定2runのflip（A=base, B=new）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluator.flip import compare_runs
from src.evaluator.metrics import summarize
from src.models import CRAGLabel, JudgeResult


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "results" not in data:
        sys.exit(
            f"{path.name} はpipelineのrun JSONではありません（resultsキーなし。"
            "retrieval_*.json / judge_calibration_*.json は指定できません）"
        )
    return data


def _print_summary(path: Path, data: dict) -> None:
    results = [
        JudgeResult(label=CRAGLabel(r["judge_label"]), reason=r["judge_reason"])
        for r in data["results"]
        if r["judge_label"]
    ]
    print(f"\n=== {path.name} ===")
    print(summarize(results).report())

    incorrects = [r for r in data["results"] if r["judge_label"] == "Incorrect"]
    if incorrects:
        print(f"\n[要分析: Incorrect {len(incorrects)}件]")
        for r in incorrects:
            print(f"  {r['question_id']}: {r['question'][:60]}")
            print(f"    -> {r['answer'][:80]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="実験結果の集計とflip分析")
    parser.add_argument("runs", nargs="*", type=Path,
                        help="比較する2つのrun JSON（省略時は全run集計＋最新2runのflip）")
    args = parser.parse_args()

    if len(args.runs) == 2:
        base_path, new_path = args.runs
    elif len(args.runs) == 0:
        # retrieval_*.json などpipeline以外の結果は除外する
        candidates = sorted(
            p for p in (ROOT / "experiments").glob("*.json")
            if not p.name.startswith(("retrieval_", "judge_calibration_"))
        )
        if not candidates:
            print("experiments/ に結果ファイルがありません。run_pipeline.py を先に実行してください。")
            return
        for path in candidates:
            _print_summary(path, _load(path))
        if len(candidates) < 2:
            return
        base_path, new_path = sorted(candidates, key=lambda p: p.stat().st_mtime)[-2:]
    else:
        parser.error("run JSONは0個か2個で指定してください")

    base, new = _load(base_path), _load(new_path)
    if len(args.runs) == 2:
        _print_summary(base_path, base)
        _print_summary(new_path, new)
    print()
    print(compare_runs(base, new, base_name=base_path.name, new_name=new_path.name).report())


if __name__ == "__main__":
    main()
