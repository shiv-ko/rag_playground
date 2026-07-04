"""data/generated_eval/questions.json を本物validとは別枠で実行する。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="生成評価セットを実行")
    parser.add_argument("--questions", type=Path, default=ROOT / "data" / "generated_eval" / "questions.json")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--run-name", default="generated_eval")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments" / "generated_eval")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    if not args.questions.exists():
        subprocess.run([
            sys.executable, str(ROOT / "scripts" / "build_generated_eval.py")
        ], check=True)

    cmd = [
        sys.executable, str(ROOT / "scripts" / "run_pipeline.py"),
        "--data-dir", str(args.data_dir),
        "--questions", str(args.questions),
        "--out-dir", str(args.out_dir),
        "--run-name", args.run_name,
    ]
    if args.no_cache:
        cmd.append("--no-cache")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
