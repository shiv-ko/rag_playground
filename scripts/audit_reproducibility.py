"""既存run JSON間の再現性をAPI実行なしで監査するCLI。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluator.reproducibility import audit_run_payloads  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="複数run JSONの再現性監査")
    parser.add_argument(
        "run_json", type=Path, nargs="+", help="比較するrun JSON（2つ以上）"
    )
    parser.add_argument("--output", "-o", type=Path, help="監査JSONの保存先")
    args = parser.parse_args()
    if len(args.run_json) < 2:
        parser.error("run_json は2つ以上指定してください")

    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in args.run_json]
    report = audit_run_payloads(
        payloads, run_names=[str(path) for path in args.run_json]
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
