"""Generate a markdown summary for train.xlsx XML scan artifacts."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
OUT = ROOT / "docs" / "train_xlsx_scan.md"


def load_jsonl(name: str) -> list[dict]:
    path = ARTIFACTS / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    sheets = load_jsonl("train_xlsx_sheets.jsonl")
    highlights = load_jsonl("train_xlsx_highlights.jsonl")
    formulas = load_jsonl("train_xlsx_formula_cells.jsonl")
    failures = load_jsonl("train_xlsx_failures.jsonl")

    lines = [
        "# train.xlsx XML Scan",
        "",
        "`scripts/scan_train_xlsx_xml.py` による `03.データ/train.xlsx` の軽量スキャン結果。openpyxlのPivot cache読み込みを避けるため、xlsxをzip/XMLとして直接読む。",
        "",
        "## Summary",
        "",
        "| item | count |",
        "|---|---:|",
        f"| sheets | {len(sheets)} |",
        f"| highlighted cells | {len(highlights)} |",
        f"| formula cells | {len(formulas)} |",
        f"| failures | {len(failures)} |",
        "",
        "## Sheet Signals",
        "",
        "| project | sheet | dimension | filter | drawings | formulas | colored |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for sheet in sheets:
        if sheet["auto_filter_ref"] or sheet["drawing_count"] or sheet["formula_count"] or sheet["colored_cell_count"]:
            lines.append(
                "| {project} | {sheet} | `{dim}` | `{filter_ref}` | {drawings} | {formulas} | {colored} |".format(
                    project=sheet["project_name"],
                    sheet=sheet["sheet_name"],
                    dim=sheet["dimension"],
                    filter_ref=sheet["auto_filter_ref"],
                    drawings=sheet["drawing_count"],
                    formulas=sheet["formula_count"],
                    colored=sheet["colored_cell_count"],
                )
            )

    lines.extend(["", "## Highlight Colors", "", "| color | count |", "|---|---:|"])
    for color, count in Counter(row["fill_color_name"] for row in highlights).most_common():
        lines.append(f"| `{color}` | {count} |")

    lines.extend(["", "## Highlights By Project", "", "| project | count |", "|---|---:|"])
    for project, count in Counter(row["project_name"] for row in highlights).most_common():
        lines.append(f"| {project} | {count} |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- 全セルJSONLは巨大化するため保存しない。保存対象はシート概要、ハイライトセル、数式セルに限定する。",
            "- `train.xlsx` 9件は失敗なしでスキャン可能。",
            "- フィルター、図表参照、色付きセル、数式セルの有無は取れている。",
            "- Pivotの意味解釈、グラフ系列の元データ解決、セル周辺見出しの復元は次段階。",
        ]
    )

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
