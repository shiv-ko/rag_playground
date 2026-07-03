"""Generate a markdown summary for Office style extraction."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
OUT = ROOT / "docs" / "office_marks_scan.md"


def load_jsonl(name: str) -> list[dict]:
    path = ARTIFACTS / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    marks = load_jsonl("office_marks.jsonl")
    failures = load_jsonl("office_mark_failures.jsonl")
    lines = [
        "# Office Marks Scan",
        "",
        "`scripts/extract_office_marks.py` によるDOCX/PPTXの書式抽出PoC。PDFは対象外。",
        "",
        "## Summary",
        "",
        "| item | count |",
        "|---|---:|",
        f"| marks | {len(marks)} |",
        f"| failures | {len(failures)} |",
        f"| bold | {sum(1 for row in marks if row.get('bold'))} |",
        f"| italic | {sum(1 for row in marks if row.get('italic'))} |",
        f"| underline | {sum(1 for row in marks if row.get('underline'))} |",
        f"| font_color | {sum(1 for row in marks if row.get('font_color'))} |",
        f"| highlight_color | {sum(1 for row in marks if row.get('highlight_color'))} |",
        "",
        "## By Extension",
        "",
        "| extension | count |",
        "|---|---:|",
    ]
    for extension, count in Counter(row["extension"] for row in marks).most_common():
        lines.append(f"| `{extension}` | {count} |")

    lines.extend(["", "## Highlight Colors", "", "| color | count |", "|---|---:|"])
    for color, count in Counter(row.get("highlight_color") for row in marks if row.get("highlight_color")).most_common():
        lines.append(f"| `{color}` | {count} |")

    lines.extend(["", "## Font Colors Top", "", "| color | count |", "|---|---:|"])
    for color, count in Counter(row.get("font_color") for row in marks if row.get("font_color")).most_common(20):
        lines.append(f"| `{color}` | {count} |")

    lines.extend(["", "## Failures", "", "| source | error |", "|---|---|"])
    for failure in failures:
        lines.append(f"| `{failure['source_path']}` | `{failure['error']}` |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- PPTXは図形塗りや通常テーマ色も拾うため、回答時は質問条件に応じて色/太字/スライド番号で絞る。",
            "- DOCXの黄色ハイライト、下線、イタリック、太字はrun単位で抽出できる。",
            "- 失敗1件は暗号化DOCXで、パスワード導出/復号キューに回す。",
        ]
    )
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
