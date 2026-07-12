"""Generate artifacts/analysis_records.jsonl from project analysis files."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.structured.analysis_artifacts import build_analysis_records, write_analysis_records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts" / "analysis_records.jsonl"
    )
    args = parser.parse_args()
    records = build_analysis_records(args.data_dir)
    write_analysis_records(args.output, records)
    print(f"wrote {len(records)} records to {args.output}")


if __name__ == "__main__":
    main()

