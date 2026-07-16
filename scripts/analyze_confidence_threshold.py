#!/usr/bin/env python3
"""保存済みrun JSONからconfidence threshold引き上げ候補を分析する。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluator.confidence_threshold import analyze_thresholds, load_run


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("development", nargs="+", type=Path, help="探索用run JSON")
    parser.add_argument(
        "--holdout", nargs="*", type=Path, default=[], help="確認専用run JSON"
    )
    parser.add_argument("--current-threshold", type=float, default=0.4)
    parser.add_argument("--candidates", default="0.4,0.5,0.6,0.7,0.8")
    parser.add_argument("--min-tag-count", type=int, default=5)
    parser.add_argument("--max-configurations", type=int, default=1_000_000)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--output", type=Path)
    return parser


def _load_all(paths: list[Path]) -> list[dict]:
    return [row for path in paths for row in load_run(path)]


def _text_report(payload: dict) -> str:
    best = payload["best"]
    conservative = payload["conservative"]
    lines = [
        f"baseline mean: {payload['baseline']['mean_score']:.4f}",
        "最高スコア構成: "
        f"mean={best['mean_score']:.4f}, common={best['common_threshold']}, "
        f"tags={best['tag_thresholds']}, holdout={best['holdout_mean_score']}",
        "保守的構成: "
        f"mean={conservative['mean_score']:.4f}, "
        f"common={conservative['common_threshold']}, "
        f"tags={conservative['tag_thresholds']}, gated={conservative['gated_count']}, "
        f"holdout={conservative['holdout_mean_score']}",
        "引き下げは未評価: 追加judge必要候補 "
        f"{len(payload['needs_additional_judge'])}件",
    ]
    return "\n".join(lines)


def main() -> None:
    args = _parser().parse_args()
    candidates = [float(value) for value in args.candidates.split(",")]
    report = analyze_thresholds(
        _load_all(args.development),
        holdout_rows=_load_all(args.holdout),
        current_threshold=args.current_threshold,
        candidate_thresholds=candidates,
        min_tag_count=args.min_tag_count,
        max_configurations=args.max_configurations,
    )
    payload = report.to_dict()
    rendered = (
        json.dumps(payload, ensure_ascii=False, indent=2)
        if args.format == "json"
        else _text_report(payload)
    )
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
