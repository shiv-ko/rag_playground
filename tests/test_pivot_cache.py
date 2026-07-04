"""pivotCache 再集計パーサのテスト（合成XMLのみ）。"""
from __future__ import annotations

import zipfile
from pathlib import Path

from src.parsers.pivot_cache import (
    aggregate,
    extract_pivot_aggregates,
    parse_cache_fields,
    parse_cache_records,
    parse_pivot_table,
)

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKGREL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _cache_def_xml() -> str:
    return f"""<?xml version="1.0"?>
<pivotCacheDefinition xmlns="{MAIN}">
  <cacheFields count="3">
    <cacheField name="Region"><sharedItems count="2"><s v="東"/><s v="西"/></sharedItems></cacheField>
    <cacheField name="Category"><sharedItems count="2"><s v="A"/><s v="B"/></sharedItems></cacheField>
    <cacheField name="Sales"><sharedItems/></cacheField>
  </cacheFields>
</pivotCacheDefinition>"""


def _records_xml() -> str:
    return f"""<?xml version="1.0"?>
<pivotCacheRecords xmlns="{MAIN}" count="5">
  <r><x v="0"/><x v="0"/><n v="10"/></r>
  <r><x v="0"/><x v="0"/><n v="30"/></r>
  <r><x v="1"/><x v="1"/><n v="5"/></r>
  <r><x v="1"/><x v="0"/><m/></r>
  <r><x v="1"/><x v="0"/><n v="20"/></r>
</pivotCacheRecords>"""


def _pivot_table_xml(row_field_x: str = "0") -> str:
    return f"""<?xml version="1.0"?>
<pivotTableDefinition xmlns="{MAIN}" name="PivotTable1">
  <rowFields count="3"><field x="{row_field_x}"/><field x="1"/><field x="-2"/></rowFields>
  <dataFields count="1"><dataField name="平均 / Sales" fld="2" subtotal="average"/></dataFields>
</pivotTableDefinition>"""


def test_parse_cache_fields_distinguishes_indexed_and_raw_fields() -> None:
    fields = parse_cache_fields(_cache_def_xml())
    assert fields[0]["name"] == "Region"
    assert fields[0]["shared_items"] == ["東", "西"]
    assert fields[2]["name"] == "Sales"
    assert fields[2]["shared_items"] is None


def test_parse_cache_records_decodes_indexed_raw_and_missing_values() -> None:
    fields = parse_cache_fields(_cache_def_xml())
    records = parse_cache_records(_records_xml(), fields)
    assert records[0] == {"Region": "東", "Category": "A", "Sales": 10}
    assert records[3] == {"Region": "西", "Category": "A", "Sales": None}


def test_parse_pivot_table_resolves_row_fields_and_default_subtotal() -> None:
    xml = f"""<?xml version="1.0"?>
<pivotTableDefinition xmlns="{MAIN}" name="PivotTable1">
  <rowFields count="2"><field x="0"/><field x="-2"/></rowFields>
  <dataFields count="1"><dataField name="合計 / Sales" fld="2"/></dataFields>
</pivotTableDefinition>"""
    info = parse_pivot_table(xml, ["Region", "Category", "Sales"])
    assert info["row_fields"] == ["Region"]
    assert info["data_fields"][0]["subtotal"] == "sum"


def test_aggregate_average_argmax_argmin_and_blank_exclusion() -> None:
    fields = parse_cache_fields(_cache_def_xml())
    records = parse_cache_records(_records_xml(), fields)
    data_field = {"field": "Sales", "subtotal": "average"}
    grouped = aggregate(records, ["Region", "Category"], data_field)
    best_key = max(grouped, key=grouped.get)
    worst_key = min(grouped, key=grouped.get)
    assert dict(zip(["Region", "Category"], best_key)) == {"Region": "東", "Category": "A"}
    assert grouped[best_key] == 20.0
    assert dict(zip(["Region", "Category"], worst_key)) == {"Region": "西", "Category": "B"}
    assert grouped[worst_key] == 5.0
    assert aggregate(records, [], data_field) == {}


def test_extract_pivot_aggregates_minimal_xlsx(tmp_path: Path) -> None:
    path = tmp_path / "train.xlsx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/workbook.xml", f"""<workbook xmlns="{MAIN}" xmlns:r="{REL}">
<sheets><sheet name="Pivot" sheetId="1" r:id="rId1"/></sheets></workbook>""")
        zf.writestr("xl/_rels/workbook.xml.rels", f"""<Relationships xmlns="{PKGREL}">
<Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>""")
        zf.writestr("xl/worksheets/sheet1.xml", f"""<worksheet xmlns="{MAIN}" xmlns:r="{REL}">
<sheetData/></worksheet>""")
        zf.writestr("xl/worksheets/_rels/sheet1.xml.rels", f"""<Relationships xmlns="{PKGREL}">
<Relationship Id="rId1" Type="{REL}/pivotTable" Target="../pivotTables/pivotTable1.xml"/></Relationships>""")
        zf.writestr("xl/pivotTables/pivotTable1.xml", _pivot_table_xml())
        zf.writestr("xl/pivotTables/_rels/pivotTable1.xml.rels", f"""<Relationships xmlns="{PKGREL}">
<Relationship Id="rId1" Type="{REL}/pivotCacheDefinition" Target="../pivotCache/pivotCacheDefinition1.xml"/></Relationships>""")
        zf.writestr("xl/pivotCache/pivotCacheDefinition1.xml", _cache_def_xml())
        zf.writestr("xl/pivotCache/_rels/pivotCacheDefinition1.xml.rels", f"""<Relationships xmlns="{PKGREL}">
<Relationship Id="rId1" Type="{REL}/pivotCacheRecords" Target="pivotCacheRecords1.xml"/></Relationships>""")
        zf.writestr("xl/pivotCache/pivotCacheRecords1.xml", _records_xml())

    aggregates = extract_pivot_aggregates(path)
    assert len(aggregates) == 1
    aggregate_row = aggregates[0]
    assert aggregate_row.sheet_name == "Pivot"
    assert aggregate_row.row_fields == ["Region", "Category"]
    assert aggregate_row.data_field_name == "平均 / Sales"
    assert aggregate_row.argmax_labels == {"Region": "東", "Category": "A"}
    assert aggregate_row.argmax_value == 20.0
