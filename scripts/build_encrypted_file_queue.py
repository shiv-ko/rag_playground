"""Collect encrypted/extraction-failed files into a remediation queue."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
DOCS = ROOT / "docs"
QUEUE_PATH = ARTIFACTS / "encrypted_file_queue.jsonl"
REPORT_PATH = DOCS / "encrypted_file_queue.md"


FAILURE_SOURCES = [
    ("spreadsheet", ARTIFACTS / "spreadsheet_failures.jsonl"),
    ("train_xlsx", ARTIFACTS / "train_xlsx_failures.jsonl"),
    ("office", ARTIFACTS / "office_mark_failures.jsonl"),
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def cfb_signature(source_path: str) -> bool:
    try:
        return (ROOT / source_path).read_bytes()[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    except OSError:
        return False


def classify_error(error: str, source_path: str) -> str:
    text = error.lower()
    if "encrypted" in text or "password" in text or "office file is encrypted" in text or "pw-" in source_path:
        return "encrypted"
    if cfb_signature(source_path):
        return "encrypted_or_legacy_office_container"
    if "badzipfile" in text:
        return "corrupt_or_not_zip"
    return "extraction_failed"


def build_queue() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for extractor, path in FAILURE_SOURCES:
        for failure in read_jsonl(path):
            source_path = failure.get("source_path") or failure.get("path") or ""
            error = failure.get("error") or failure.get("reason") or ""
            failure_type = classify_error(error, source_path)
            key = (extractor, source_path)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "extractor": extractor,
                    "source_path": source_path,
                    "file_name": Path(source_path).name,
                    "failure_type": failure_type,
                    "error": error,
                    "recommended_action": recommended_action(failure_type, source_path),
                }
            )
    rows.sort(key=lambda row: (row["failure_type"], row["source_path"]))
    return rows


def recommended_action(failure_type: str, source_path: str) -> str:
    if failure_type in {"encrypted", "encrypted_or_legacy_office_container"}:
        if "pw-" in source_path or "パスワード" in source_path:
            return "derive password from filename/internal password rule and rerun extractor"
        return "check whether CFB file is encrypted or legacy Office; decrypt/convert to temp copy, rerun extractor"
    return "inspect file manually and rerun extractor after format handling is added"


def write_report(rows: list[dict[str, Any]]) -> None:
    lines = [
        "# 暗号化・抽出失敗ファイルキュー",
        "",
        "## 目的",
        "",
        "構造化抽出から漏れたファイルを一覧化し、復号または形式対応後に再抽出できるようにする。",
        "",
        "## 集計",
        "",
        f"- queued files: {len(rows)}",
        f"- encrypted/legacy containers: {sum(1 for row in rows if row['failure_type'] in {'encrypted', 'encrypted_or_legacy_office_container'})}",
        f"- other failures: {sum(1 for row in rows if row['failure_type'] not in {'encrypted', 'encrypted_or_legacy_office_container'})}",
        "",
        "| type | extractor | file | action | error |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        error = str(row["error"]).replace("|", "/")
        if len(error) > 120:
            error = error[:117] + "..."
        lines.append(
            f"| {row['failure_type']} | {row['extractor']} | `{row['source_path']}` | {row['recommended_action']} | `{error}` |"
        )
    lines.extend(
        [
            "",
            "## 注意",
            "",
            "- このキューは復号そのものは行わない。",
            "- 復号済みコピーを作る場合は元ファイルを変更せず、一時ディレクトリまたは派生成果物として扱う。",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = build_queue()
    write_jsonl(QUEUE_PATH, rows)
    write_report(rows)
    print(f"queued={len(rows)}")
    print(f"encrypted_or_legacy={sum(1 for row in rows if row['failure_type'] in {'encrypted', 'encrypted_or_legacy_office_container'})}")


if __name__ == "__main__":
    main()
