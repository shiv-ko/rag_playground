"""Build context around highlighted cells in 03.データ/train.xlsx files."""
from __future__ import annotations

import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from scan_train_xlsx_xml import (
    ARTIFACTS,
    NS,
    PROJECT_ROOT,
    ROOT,
    cell_value,
    load_shared_strings,
    read_xml,
    sheet_map,
)


HIGHLIGHTS_PATH = ARTIFACTS / "train_xlsx_highlights.jsonl"
CONTEXT_PATH = ARTIFACTS / "train_xlsx_highlight_context.jsonl"
BLOCKS_PATH = ARTIFACTS / "train_xlsx_highlight_blocks.jsonl"
REPORT_PATH = ROOT / "docs" / "train_xlsx_highlight_context.md"

CELL_RE = re.compile(r"^([A-Z]+)([0-9]+)$")
REF_RE = re.compile(r"(?:'([^']+)'|([A-Za-z0-9_]+))?!?\$?([A-Z]{1,3})\$?([0-9]+)")


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


def split_cell(ref: str) -> tuple[int, int]:
    match = CELL_RE.match(ref)
    if not match:
        raise ValueError(f"Invalid cell reference: {ref}")
    col_name, row = match.groups()
    col = 0
    for ch in col_name:
        col = col * 26 + ord(ch) - ord("A") + 1
    return int(row), col


def col_name(col: int) -> str:
    chars = []
    while col:
        col, rem = divmod(col - 1, 26)
        chars.append(chr(ord("A") + rem))
    return "".join(reversed(chars))


def cell_ref(row: int, col: int) -> str:
    return f"{col_name(col)}{row}"


def project_name(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).parts[0]


def workbook_path(source_path: str) -> Path:
    return ROOT / source_path


def sheet_cell_map(
    zf: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
) -> dict[tuple[int, int], dict[str, Any]]:
    root = read_xml(zf, sheet_path)
    if root is None:
        return {}
    cells: dict[tuple[int, int], dict[str, Any]] = {}
    for cell in root.findall(".//main:c", NS):
        ref = cell.attrib.get("r")
        if not ref:
            continue
        try:
            row, col = split_cell(ref)
        except ValueError:
            continue
        formula_node = cell.find("main:f", NS)
        formula = formula_node.text if formula_node is not None else None
        value = cell_value(cell, shared_strings)
        if value is None and formula is None:
            continue
        cells[(row, col)] = {
            "cell": ref,
            "row": row,
            "col": col,
            "value": value,
            "formula": formula,
        }
    return cells


def compact_cell(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        "cell": cell["cell"],
        "value": cell.get("value"),
        "formula": cell.get("formula"),
    }


def nearest_left(cells: dict[tuple[int, int], dict[str, Any]], row: int, col: int) -> dict[str, Any] | None:
    for c in range(col - 1, max(0, col - 12), -1):
        hit = cells.get((row, c))
        if hit and hit.get("value") not in {None, ""}:
            return compact_cell(hit)
    return None


def nearest_above(cells: dict[tuple[int, int], dict[str, Any]], row: int, col: int) -> dict[str, Any] | None:
    for r in range(row - 1, max(0, row - 20), -1):
        hit = cells.get((r, col))
        if hit and hit.get("value") not in {None, ""}:
            return compact_cell(hit)
    return None


def window_cells(
    cells: dict[tuple[int, int], dict[str, Any]],
    row: int,
    col: int,
    row_radius: int = 3,
    col_radius: int = 4,
) -> list[dict[str, Any]]:
    rows = range(max(1, row - row_radius), row + row_radius + 1)
    cols = range(max(1, col - col_radius), col + col_radius + 1)
    return [
        compact_cell(cells[(r, c)])
        for r in rows
        for c in cols
        if (r, c) in cells
    ]


def same_row_values(cells: dict[tuple[int, int], dict[str, Any]], row: int, col: int) -> list[dict[str, Any]]:
    values = [cell for (r, _), cell in cells.items() if r == row]
    values.sort(key=lambda item: abs(item["col"] - col))
    return [compact_cell(item) for item in values[:16]]


def same_col_headers(cells: dict[tuple[int, int], dict[str, Any]], row: int, col: int) -> list[dict[str, Any]]:
    values = [
        cell
        for (r, c), cell in cells.items()
        if c == col and r < row and cell.get("value") not in {None, ""}
    ]
    values.sort(key=lambda item: row - item["row"])
    return [compact_cell(item) for item in values[:10]]


def likely_column_header(cells: dict[tuple[int, int], dict[str, Any]], row: int, col: int) -> dict[str, Any] | None:
    candidates = [
        cells[(r, col)]
        for r in range(1, min(row, 31))
        if (r, col) in cells and cells[(r, col)].get("value") not in {None, ""}
    ]
    for candidate in candidates:
        value = str(candidate.get("value") or "")
        if re.search(r"[A-Za-z一-龥ぁ-んァ-ン]", value):
            return compact_cell(candidate)
    return compact_cell(candidates[0]) if candidates else None


def formula_references(formula: str | None) -> list[dict[str, str]]:
    if not formula:
        return []
    refs = []
    for sheet_quoted, sheet_plain, col, row in REF_RE.findall(formula):
        refs.append(
            {
                "sheet": sheet_quoted or sheet_plain or "",
                "cell": f"{col}{row}",
            }
        )
    return refs


def build_context(
    highlight: dict[str, Any],
    cells: dict[tuple[int, int], dict[str, Any]],
) -> dict[str, Any]:
    row, col = split_cell(highlight["cell"])
    return {
        **highlight,
        "row": row,
        "col": col,
        "nearest_left": nearest_left(cells, row, col),
        "nearest_above": nearest_above(cells, row, col),
        "column_header": likely_column_header(cells, row, col),
        "same_col_headers": same_col_headers(cells, row, col),
        "same_row_values": same_row_values(cells, row, col),
        "nearby_window": window_cells(cells, row, col),
        "formula_references": formula_references(highlight.get("formula")),
    }


def block_range(rows: list[dict[str, Any]]) -> str:
    parsed = [split_cell(row["cell"]) for row in rows]
    min_row = min(r for r, _ in parsed)
    max_row = max(r for r, _ in parsed)
    min_col = min(c for _, c in parsed)
    max_col = max(c for _, c in parsed)
    start = cell_ref(min_row, min_col)
    end = cell_ref(max_row, max_col)
    return start if start == end else f"{start}:{end}"


def build_blocks(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in contexts:
        key = (
            row["source_path"],
            row["sheet_name"],
            row.get("fill_color_name") or "",
            row.get("fill_rgb") or row.get("fill_theme") or "",
        )
        grouped[key].append(row)

    blocks: list[dict[str, Any]] = []
    for (_, _, _, _), rows in grouped.items():
        remaining = sorted(rows, key=lambda item: (item["row"], item["col"]))
        while remaining:
            seed = remaining.pop(0)
            vertical = [seed]
            cursor = seed["row"] + 1
            for candidate in list(remaining):
                if candidate["col"] == seed["col"] and candidate["row"] == cursor:
                    vertical.append(candidate)
                    remaining.remove(candidate)
                    cursor += 1
            if len(vertical) > 1:
                block_rows = vertical
                orientation = "vertical"
            else:
                horizontal = [seed]
                cursor = seed["col"] + 1
                for candidate in list(remaining):
                    if candidate["row"] == seed["row"] and candidate["col"] == cursor:
                        horizontal.append(candidate)
                        remaining.remove(candidate)
                        cursor += 1
                block_rows = horizontal
                orientation = "horizontal" if len(horizontal) > 1 else "single"

            values = [row.get("value") for row in block_rows]
            column_headers = [
                row["column_header"]
                for row in block_rows
                if row.get("column_header") and row["column_header"]["cell"] != row["cell"]
            ]
            seen_headers = set()
            unique_column_headers = []
            for header in column_headers:
                key = (header["cell"], header.get("value"))
                if key in seen_headers:
                    continue
                seen_headers.add(key)
                unique_column_headers.append(header)
            blocks.append(
                {
                    "source_path": seed["source_path"],
                    "project_name": seed["project_name"],
                    "sheet_name": seed["sheet_name"],
                    "range": block_range(block_rows),
                    "orientation": orientation,
                    "cell_count": len(block_rows),
                    "fill_color_name": seed.get("fill_color_name"),
                    "first_value": values[0] if values else None,
                    "last_value": values[-1] if values else None,
                    "sample_values": values[:8],
                    "nearest_left": seed.get("nearest_left"),
                    "nearest_above": seed.get("nearest_above"),
                    "column_header": seed.get("column_header"),
                    "column_headers": unique_column_headers[:20],
                    "same_col_headers": seed.get("same_col_headers"),
                    "same_row_values": seed.get("same_row_values"),
                    "formula_references": seed.get("formula_references"),
                }
            )
    blocks.sort(key=lambda row: (row["project_name"], row["sheet_name"], row["range"]))
    return blocks


def context_by_sheet(highlights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in highlights:
        grouped[(row["source_path"], row["sheet_name"])].append(row)

    for (source_path, sheet_name), rows in sorted(grouped.items()):
        path = workbook_path(source_path)
        with zipfile.ZipFile(path) as zf:
            shared_strings = load_shared_strings(zf)
            sheets = {sheet["name"]: sheet for sheet in sheet_map(zf)}
            sheet = sheets.get(sheet_name)
            if sheet is None:
                continue
            cells = sheet_cell_map(zf, sheet["path"], shared_strings)
            for highlight in rows:
                contexts.append(build_context(highlight, cells))
    contexts.sort(key=lambda row: (row["project_name"], row["sheet_name"], row["row"], row["col"]))
    return contexts


def md_value(value: Any, max_len: int = 80) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\n", " ")
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def has_text(value: Any) -> bool:
    return bool(re.search(r"[A-Za-z一-龥ぁ-んァ-ン]", str(value or "")))


def best_context_text(block: dict[str, Any]) -> str:
    headers = block.get("column_headers") or []
    text_headers = [header for header in headers if has_text(header.get("value"))]
    if text_headers:
        return ", ".join(md_value(header.get("value"), 24) for header in text_headers[:6])
    for key in ("column_header", "nearest_left", "nearest_above"):
        context = block.get(key)
        if context and has_text(context.get("value")):
            return md_value(context.get("value"))
    context = block.get("column_header") or block.get("nearest_left") or block.get("nearest_above")
    return md_value(context.get("value") if context else "")


def write_report(contexts: list[dict[str, Any]], blocks: list[dict[str, Any]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    by_project = defaultdict(int)
    for row in contexts:
        by_project[row["project_name"]] += 1

    lines = [
        "# train.xlsx ハイライトセル周辺見出し復元",
        "",
        "## 目的",
        "",
        "`03.データ/train.xlsx` の色付きセルについて、セル値だけでなく周辺見出し・近傍セル・数式参照を復元し、設問回答時に「何の値か」を判定できるようにする。",
        "",
        "## 生成物",
        "",
        "- `artifacts/train_xlsx_highlight_context.jsonl`: ハイライトセル単位の周辺文脈",
        "- `artifacts/train_xlsx_highlight_blocks.jsonl`: 連続ハイライト範囲の集約",
        "",
        "## 集計",
        "",
        f"- ハイライトセル: {len(contexts)}",
        f"- ハイライトブロック: {len(blocks)}",
        "",
        "| project | highlighted cells |",
        "|---|---:|",
    ]
    for project, count in sorted(by_project.items()):
        lines.append(f"| {project} | {count} |")

    lines.extend(
        [
            "",
            "## 主要ブロック",
            "",
            "| project | sheet | range | count | color | orientation | first | last | inferred context |",
            "|---|---|---:|---:|---|---|---|---|---|",
        ]
    )
    for block in blocks:
        if block["cell_count"] == 1 and len(blocks) > 20:
            continue
        context_text = best_context_text(block)
        lines.append(
            "| {project} | {sheet} | `{range}` | {count} | {color} | {orientation} | {first} | {last} | {context} |".format(
                project=block["project_name"],
                sheet=block["sheet_name"],
                range=block["range"],
                count=block["cell_count"],
                color=block.get("fill_color_name") or "",
                orientation=block["orientation"],
                first=md_value(block.get("first_value"), 40),
                last=md_value(block.get("last_value"), 40),
                context=context_text,
            )
        )

    lines.extend(
        [
            "",
            "## 単独セルサンプル",
            "",
            "| project | sheet | cell | value | left | above | formula refs |",
            "|---|---|---:|---|---|---|---|",
        ]
    )
    single_contexts = [
        block for block in blocks if block["orientation"] == "single"
    ]
    for block in single_contexts[:20]:
        left = block.get("nearest_left")
        above = block.get("nearest_above")
        refs = ", ".join(
            f"{ref['sheet']}!{ref['cell']}" if ref.get("sheet") else ref["cell"]
            for ref in block.get("formula_references") or []
        )
        lines.append(
            "| {project} | {sheet} | `{cell}` | {value} | {left} | {above} | {refs} |".format(
                project=block["project_name"],
                sheet=block["sheet_name"],
                cell=block["range"],
                value=md_value(block.get("first_value"), 40),
                left=md_value(left.get("value") if left else "", 40),
                above=md_value(above.get("value") if above else "", 40),
                refs=md_value(refs, 80),
            )
        )

    lines.extend(
        [
            "",
            "## 読み取り上の注意",
            "",
            "- XML上のキャッシュ値と数式文字列を使っており、Excel再計算はしていない。",
            "- 色は `scan_train_xlsx_xml.py` と同じ簡易正規化を使う。",
            "- `train` シートの縦長ハイライト列は、セル単位成果物では全行、レポートではブロックとして要約する。",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    highlights = read_jsonl(HIGHLIGHTS_PATH)
    contexts = context_by_sheet(highlights)
    blocks = build_blocks(contexts)
    write_jsonl(CONTEXT_PATH, contexts)
    write_jsonl(BLOCKS_PATH, blocks)
    write_report(contexts, blocks)
    print(f"highlight contexts: {len(contexts)}")
    print(f"highlight blocks: {len(blocks)}")
    print(f"wrote {CONTEXT_PATH.relative_to(ROOT)}")
    print(f"wrote {BLOCKS_PATH.relative_to(ROOT)}")
    print(f"wrote {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
