"""Lightweight XML scanner for train.xlsx workbooks.

This avoids openpyxl's expensive pivot cache loading and extracts enough
metadata to prioritize spreadsheet-specific answer logic.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT / "data" / "raw" / "share" / "共有ドライブ" / "プロジェクト"
ARTIFACTS = ROOT / "artifacts"

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_xml(zf: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(zf.read(name))
    except KeyError:
        return None


def project_name(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).parts[0]


def rel_target(base: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    base_dir = str(Path(base).parent)
    return str(Path(base_dir, target)).replace("\\", "/")


def load_relationships(zf: zipfile.ZipFile, rel_path: str) -> dict[str, str]:
    root = read_xml(zf, rel_path)
    if root is None:
        return {}
    rels = {}
    for rel in root.findall("pkgrel:Relationship", NS):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id and target:
            source = rel_path.replace("_rels/", "").replace(".rels", "")
            rels[rel_id] = rel_target(source, target)
    return rels


def load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    root = read_xml(zf, "xl/sharedStrings.xml")
    if root is None:
        return []
    values = []
    for si in root.findall("main:si", NS):
        texts = [t.text or "" for t in si.findall(".//main:t", NS)]
        values.append("".join(texts))
    return values


def load_fills(zf: zipfile.ZipFile) -> list[dict[str, Any]]:
    root = read_xml(zf, "xl/styles.xml")
    if root is None:
        return []
    fills = []
    fills_root = root.find("main:fills", NS)
    if fills_root is None:
        return fills
    for fill in fills_root.findall("main:fill", NS):
        pattern = fill.find("main:patternFill", NS)
        fg = pattern.find("main:fgColor", NS) if pattern is not None else None
        fills.append(
            {
                "pattern_type": pattern.attrib.get("patternType") if pattern is not None else None,
                "rgb": fg.attrib.get("rgb")[-6:].upper() if fg is not None and fg.attrib.get("rgb") else None,
                "indexed": fg.attrib.get("indexed") if fg is not None else None,
                "theme": fg.attrib.get("theme") if fg is not None else None,
                "tint": fg.attrib.get("tint") if fg is not None else None,
            }
        )
    return fills


def load_cell_style_fills(zf: zipfile.ZipFile) -> dict[int, int | None]:
    root = read_xml(zf, "xl/styles.xml")
    if root is None:
        return {}
    xfs = root.find("main:cellXfs", NS)
    if xfs is None:
        return {}
    mapping: dict[int, int | None] = {}
    for idx, xf in enumerate(xfs.findall("main:xf", NS)):
        fill_id = xf.attrib.get("fillId")
        mapping[idx] = int(fill_id) if fill_id is not None else None
    return mapping


def normalize_color(rgb: str | None, indexed: str | None = None, theme: str | None = None) -> str | None:
    if rgb:
        r = int(rgb[0:2], 16)
        g = int(rgb[2:4], 16)
        b = int(rgb[4:6], 16)
        if r > 220 and g > 180 and b < 130:
            return "yellow"
        if r > 180 and g < 160 and b < 160:
            return "red"
        if b > 160 and r < 190:
            return "blue"
        if r > 200 and 80 < g < 190 and b < 140:
            return "orange"
        if g > 160 and r < 190 and b < 190:
            return "green"
        return rgb
    if indexed:
        return f"INDEXED:{indexed}"
    if theme:
        return f"THEME:{theme}"
    return None


def sheet_map(zf: zipfile.ZipFile) -> list[dict[str, str]]:
    wb = read_xml(zf, "xl/workbook.xml")
    rels = load_relationships(zf, "xl/_rels/workbook.xml.rels")
    if wb is None:
        return []
    sheets = []
    for sheet in wb.findall("main:sheets/main:sheet", NS):
        rel_id = sheet.attrib.get(f"{{{NS['rel']}}}id")
        target = rels.get(rel_id or "")
        if target:
            sheets.append(
                {
                    "name": sheet.attrib.get("name", ""),
                    "sheet_id": sheet.attrib.get("sheetId", ""),
                    "path": target,
                }
            )
    return sheets


def cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    value_node = cell.find("main:v", NS)
    inline_node = cell.find("main:is/main:t", NS)
    if inline_node is not None:
        return inline_node.text
    if value_node is None or value_node.text is None:
        return None
    raw = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw


def scan_sheet(
    zf: zipfile.ZipFile,
    workbook_path: Path,
    sheet: dict[str, str],
    shared_strings: list[str],
    fills: list[dict[str, Any]],
    style_fills: dict[int, int | None],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    root = read_xml(zf, sheet["path"])
    meta = {
        "source_path": str(workbook_path.relative_to(ROOT)),
        "project_name": project_name(workbook_path),
        "file_name": workbook_path.name,
        "sheet_name": sheet["name"],
        "sheet_path": sheet["path"],
        "dimension": None,
        "auto_filter_ref": None,
        "table_count": 0,
        "drawing_count": 0,
        "cell_count": 0,
        "formula_count": 0,
        "styled_cell_count": 0,
        "colored_cell_count": 0,
    }
    if root is None:
        return meta, [], []

    dim = root.find("main:dimension", NS)
    meta["dimension"] = dim.attrib.get("ref") if dim is not None else None
    auto_filter = root.find("main:autoFilter", NS)
    meta["auto_filter_ref"] = auto_filter.attrib.get("ref") if auto_filter is not None else None
    meta["table_count"] = len(root.findall(".//main:tablePart", NS))
    meta["drawing_count"] = len(root.findall(".//main:drawing", NS))

    formula_cells: list[dict[str, Any]] = []
    highlights: list[dict[str, Any]] = []
    scanned_cell_count = 0
    for cell in root.findall(".//main:c", NS):
        ref = cell.attrib.get("r")
        if not ref:
            continue
        formula_node = cell.find("main:f", NS)
        formula = formula_node.text if formula_node is not None else None
        value = cell_value(cell, shared_strings)
        style_id = int(cell.attrib["s"]) if cell.attrib.get("s", "").isdigit() else None
        fill_id = style_fills.get(style_id) if style_id is not None else None
        fill = fills[fill_id] if fill_id is not None and fill_id < len(fills) else {}
        color_name = normalize_color(fill.get("rgb"), fill.get("indexed"), fill.get("theme"))
        has_color = bool(color_name and color_name not in {"THEME:1", "INDEXED:64"})
        if value is None and formula is None and style_id is None:
            continue
        scanned_cell_count += 1
        row = {
            "source_path": meta["source_path"],
            "project_name": meta["project_name"],
            "file_name": meta["file_name"],
            "sheet_name": meta["sheet_name"],
            "cell": ref,
            "value": value,
            "formula": formula,
            "style_id": style_id,
            "fill_id": fill_id,
            "fill_rgb": fill.get("rgb"),
            "fill_indexed": fill.get("indexed"),
            "fill_theme": fill.get("theme"),
            "fill_color_name": color_name,
        }
        if formula:
            meta["formula_count"] += 1
            formula_cells.append(row)
        if style_id is not None:
            meta["styled_cell_count"] += 1
        if has_color:
            meta["colored_cell_count"] += 1
            highlights.append(row)
    meta["cell_count"] = scanned_cell_count
    return meta, formula_cells, highlights


def target_workbooks() -> list[Path]:
    return sorted(
        p
        for p in PROJECT_ROOT.rglob("train.xlsx")
        if "03.データ" in p.parts and not p.name.startswith("~$")
    )


def main() -> None:
    sheets_out: list[dict[str, Any]] = []
    formula_cells_out: list[dict[str, Any]] = []
    highlights_out: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for path in target_workbooks():
        print(f"scanning {path.relative_to(ROOT)}", flush=True)
        try:
            with zipfile.ZipFile(path) as zf:
                shared_strings = load_shared_strings(zf)
                fills = load_fills(zf)
                style_fills = load_cell_style_fills(zf)
                for sheet in sheet_map(zf):
                    meta, formula_cells, highlights = scan_sheet(zf, path, sheet, shared_strings, fills, style_fills)
                    sheets_out.append(meta)
                    formula_cells_out.extend(formula_cells)
                    highlights_out.extend(highlights)
        except Exception as exc:  # noqa: BLE001 - audit failures.
            failures.append({"source_path": str(path.relative_to(ROOT)), "error": repr(exc)})

    write_jsonl(ARTIFACTS / "train_xlsx_sheets.jsonl", sheets_out)
    write_jsonl(ARTIFACTS / "train_xlsx_formula_cells.jsonl", formula_cells_out)
    write_jsonl(ARTIFACTS / "train_xlsx_highlights.jsonl", highlights_out)
    write_jsonl(ARTIFACTS / "train_xlsx_failures.jsonl", failures)

    print(f"workbooks={len(target_workbooks())}")
    print(f"sheets={len(sheets_out)}")
    print(f"formula_cells={len(formula_cells_out)}")
    print(f"highlights={len(highlights_out)}")
    print(f"failures={len(failures)}")


if __name__ == "__main__":
    main()
