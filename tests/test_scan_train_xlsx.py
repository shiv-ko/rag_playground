"""scan_train_xlsx_xml のフィルタ条件・小型シートセル抽出のテスト（合成xlsx使用）。"""
from __future__ import annotations

import importlib.util
import unicodedata
import zipfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "scan_train_xlsx_xml",
    Path(__file__).parent.parent / "scripts" / "scan_train_xlsx_xml.py",
)
scanner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scanner)

_WORKBOOK = """<?xml version="1.0"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="train" sheetId="1" r:id="rId1"/><sheet name="Pivot" sheetId="2" r:id="rId2"/></sheets>
</workbook>"""

_RELS = """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>"""

_SHARED = """<?xml version="1.0"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="4" uniqueCount="4">
<si><t>gender</t></si><si><t>country</t></si><si><t>Male</t></si><si><t>層</t></si>
</sst>"""

# trainシート: ヘッダ行(A1=gender,B1=country) + フィルタ(colId=0 val=Male) + hidden行2つ
_SHEET_TRAIN = """<?xml version="1.0"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:B4"/>
<sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
<row r="2" hidden="1"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>10</v></c></row>
<row r="3" hidden="1"><c r="A3" t="s"><v>2</v></c><c r="B3"><v>20</v></c></row>
<row r="4"><c r="A4" t="s"><v>2</v></c><c r="B4"><v>30</v></c></row>
</sheetData>
<autoFilter ref="A1:B4"><filterColumn colId="0"><filters><filter val="Male"/></filters></filterColumn></autoFilter>
</worksheet>"""

# Pivotシート: 小型（値セル4個）
_SHEET_PIVOT = """<?xml version="1.0"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:B2"/>
<sheetData>
<row r="1"><c r="A1" t="s"><v>3</v></c><c r="B1"><v>1.5</v></c></row>
<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>2.5</v></c></row>
</sheetData>
</worksheet>"""

_STYLES = """<?xml version="1.0"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<cellXfs count="1"><xf fillId="0"/></cellXfs>
</styleSheet>"""


def _make_xlsx(tmp_path: Path) -> Path:
    # 実データと同じ相対構造（<project>/03.データ/train.xlsx）にする
    path = tmp_path / "プロジェクト" / "テスト案件" / "03.データ" / "train.xlsx"
    path.parent.mkdir(parents=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/workbook.xml", _WORKBOOK)
        zf.writestr("xl/_rels/workbook.xml.rels", _RELS)
        zf.writestr("xl/sharedStrings.xml", _SHARED)
        zf.writestr("xl/styles.xml", _STYLES)
        zf.writestr("xl/worksheets/sheet1.xml", _SHEET_TRAIN)
        zf.writestr("xl/worksheets/sheet2.xml", _SHEET_PIVOT)
    return path


def _scan_all(path: Path):
    with zipfile.ZipFile(path) as zf:
        shared = scanner.load_shared_strings(zf)
        fills = scanner.load_fills(zf)
        style_fills = scanner.load_cell_style_fills(zf)
        results = [
            scanner.scan_sheet(zf, path, sheet, shared, fills, style_fills)
            for sheet in scanner.sheet_map(zf)
        ]
    return results


def test_filter_columns_with_header_and_hidden_count(tmp_path):
    results = _scan_all(_make_xlsx(tmp_path))
    train_meta = results[0][0]
    assert train_meta["sheet_name"] == "train"
    assert train_meta["hidden_row_count"] == 2
    fc = train_meta["filter_columns"]
    assert len(fc) == 1
    assert fc[0]["col_id"] == 0
    assert fc[0]["header"] == "gender"
    assert fc[0]["values"] == ["Male"]


def test_small_sheet_cells_dumped_for_non_train_only(tmp_path):
    results = _scan_all(_make_xlsx(tmp_path))
    train_small = results[0][3]
    pivot_small = results[1][3]
    assert train_small == []  # trainシートはダンプしない
    assert {c["cell"] for c in pivot_small} == {"A1", "B1", "A2", "B2"}
    assert all(c["sheet_name"] == "Pivot" for c in pivot_small)
    assert [c for c in pivot_small if c["cell"] == "A1"][0]["value"] == "層"
    assert [c for c in pivot_small if c["cell"] == "A1"][0]["row"] == 1


def test_target_workbooks_matches_nfd_data_dir(tmp_path, monkeypatch):
    project_root = tmp_path / "プロジェクト"
    data_dir = project_root / "テスト案件" / unicodedata.normalize("NFD", "03.データ")
    data_dir.mkdir(parents=True)
    workbook = data_dir / "train.xlsx"
    workbook.write_bytes(b"")
    monkeypatch.setattr(scanner, "PROJECT_ROOT", project_root)

    assert scanner.target_workbooks() == [workbook]
