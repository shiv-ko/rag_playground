"""pivotTable definition + pivotCache から行グループ集計を再計算する。"""
from __future__ import annotations

import os
import re
import statistics
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


@dataclass(frozen=True)
class PivotAggregate:
    sheet_name: str
    pivot_table_name: str
    row_fields: list[str]
    data_field_name: str
    data_field_source: str
    subtotal: str
    n_groups: int
    argmax_labels: dict[str, str | int | float]
    argmax_value: float
    argmin_labels: dict[str, str | int | float]
    argmin_value: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _root(xml_or_root: str | ET.Element) -> ET.Element:
    return ET.fromstring(xml_or_root) if isinstance(xml_or_root, str) else xml_or_root


def _read_xml(zf: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(zf.read(name))
    except KeyError:
        return None


def _rels_path_for(member: str) -> str:
    path = Path(member)
    return str(path.parent / "_rels" / f"{path.name}.rels").replace("\\", "/")


def _resolve_target(member: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return os.path.normpath(str(Path(member).parent / target)).replace("\\", "/")


def load_typed_relationships(zf: zipfile.ZipFile, member: str) -> dict[str, str]:
    root = _read_xml(zf, _rels_path_for(member))
    if root is None:
        return {}
    out: dict[str, str] = {}
    for rel in root.findall("pkgrel:Relationship", NS):
        rel_type = (rel.attrib.get("Type") or "").rsplit("/", 1)[-1]
        target = rel.attrib.get("Target") or ""
        if rel_type and target:
            out[rel_type] = _resolve_target(member, target)
    return out


def _load_id_relationships(zf: zipfile.ZipFile, member: str) -> dict[str, str]:
    root = _read_xml(zf, _rels_path_for(member))
    if root is None:
        return {}
    out: dict[str, str] = {}
    for rel in root.findall("pkgrel:Relationship", NS):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id and target:
            out[rel_id] = _resolve_target(member, target)
    return out


def _coerce_shared_item(child: ET.Element) -> Any:
    tag = child.tag.rsplit("}", 1)[-1]
    value = child.attrib.get("v")
    if tag == "n" and value is not None:
        return float(value) if ("." in value or "e" in value.lower()) else int(value)
    if tag == "b":
        return value == "1"
    if tag in {"m", "e"}:
        return None
    return value


def parse_cache_fields(cache_def: str | ET.Element) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for field in _root(cache_def).findall("main:cacheFields/main:cacheField", NS):
        shared = field.find("main:sharedItems", NS)
        shared_items = None
        if shared is not None and shared.attrib.get("count") is not None:
            shared_items = [_coerce_shared_item(child) for child in list(shared)]
        fields.append({"name": field.attrib.get("name", ""), "shared_items": shared_items})
    return fields


def _coerce_record_value(child: ET.Element, field: dict[str, Any]) -> Any:
    tag = child.tag.rsplit("}", 1)[-1]
    value = child.attrib.get("v")
    if tag == "x":
        shared_items = field.get("shared_items")
        if shared_items is None:
            raise ValueError(f"field {field.get('name')!r} has indexed record without sharedItems")
        return shared_items[int(value or "0")]
    if tag == "n" and value is not None:
        return float(value) if ("." in value or "e" in value.lower()) else int(value)
    if tag == "b":
        return value == "1"
    if tag in {"m", "e"}:
        return None
    return value


def parse_cache_records(records: str | ET.Element, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for record in _root(records).findall("main:r", NS):
        children = list(record)
        if len(children) != len(fields):
            raise ValueError(f"record has {len(children)} cells but cacheFields has {len(fields)}")
        out.append({
            field["name"]: _coerce_record_value(child, field)
            for field, child in zip(fields, children)
        })
    return out


def parse_pivot_table(pivot_table: str | ET.Element, field_names: list[str]) -> dict[str, Any]:
    root = _root(pivot_table)

    def field_list(tag: str) -> list[str]:
        values: list[str] = []
        for field in root.findall(f"main:{tag}/main:field", NS):
            idx = int(field.attrib.get("x", "-2"))
            if idx == -2:
                continue
            values.append(field_names[idx])
        return values

    data_fields = []
    for field in root.findall("main:dataFields/main:dataField", NS):
        idx = int(field.attrib["fld"])
        data_fields.append({
            "name": field.attrib.get("name", field_names[idx]),
            "field": field_names[idx],
            "subtotal": field.attrib.get("subtotal", "sum"),
        })
    return {
        "name": root.attrib.get("name", ""),
        "row_fields": field_list("rowFields"),
        "col_fields": field_list("colFields"),
        "data_fields": data_fields,
        "page_field_count": len(root.findall("main:pageFields/main:pageField", NS)),
        "hidden_item_count": len(root.findall(".//main:item[@h='1']", NS)),
    }


_SUBTOTAL_FUNCS = {
    "average": statistics.fmean,
    "sum": sum,
    "count": len,
    "countNums": len,
    "max": max,
    "min": min,
    "product": lambda xs: __import__("math").prod(xs),
    "stdDev": statistics.stdev,
    "stdDevp": statistics.pstdev,
    "var": statistics.variance,
    "varp": statistics.pvariance,
}


def aggregate(
    records: list[dict[str, Any]],
    row_fields: list[str],
    data_field: dict[str, Any],
) -> dict[tuple[Any, ...], float]:
    if not row_fields:
        return {}
    groups: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    value_field = data_field["field"]
    for record in records:
        value = record.get(value_field)
        if value is None:
            continue
        groups[tuple(record.get(field) for field in row_fields)].append(value)
    func = _SUBTOTAL_FUNCS.get(data_field.get("subtotal", "sum"))
    if func is None:
        raise NotImplementedError(f"unsupported subtotal function: {data_field.get('subtotal')}")
    return {key: float(func(values)) for key, values in groups.items() if values}


def _pivot_table_sheet_names(zf: zipfile.ZipFile) -> dict[str, str]:
    workbook = _read_xml(zf, "xl/workbook.xml")
    if workbook is None:
        return {}
    workbook_rels = _load_id_relationships(zf, "xl/workbook.xml")
    out: dict[str, str] = {}
    for sheet in workbook.findall("main:sheets/main:sheet", NS):
        rel_id = sheet.attrib.get(f"{{{NS['rel']}}}id")
        sheet_member = workbook_rels.get(rel_id or "")
        if not sheet_member:
            continue
        sheet_root = _read_xml(zf, sheet_member)
        sheet_rels = _load_id_relationships(zf, sheet_member)
        sheet_name = sheet.attrib.get("name", "")
        for member in sheet_rels.values():
            if re.fullmatch(r"xl/pivotTables/pivotTable\d+\.xml", member):
                out[member] = sheet_name
        if sheet_root is not None:
            for pt in sheet_root.findall(".//main:pivotTableDefinition", NS):
                pt_rel = pt.attrib.get(f"{{{NS['rel']}}}id")
                pt_member = sheet_rels.get(pt_rel or "")
                if pt_member:
                    out[pt_member] = sheet_name
    return out


def _find_pivot_tables(zf: zipfile.ZipFile) -> list[str]:
    return sorted(
        name for name in zf.namelist()
        if re.fullmatch(r"xl/pivotTables/pivotTable\d+\.xml", name)
    )


def extract_pivot_aggregates(xlsx_path: Path) -> list[PivotAggregate]:
    """1ワークブックの全pivotTable×全dataFieldのargmax/argmin集計を返す。"""
    aggregates: list[PivotAggregate] = []
    with zipfile.ZipFile(xlsx_path) as zf:
        sheet_names = _pivot_table_sheet_names(zf)
        for pt_member in _find_pivot_tables(zf):
            pt_root = _read_xml(zf, pt_member)
            cache_def_member = load_typed_relationships(zf, pt_member).get("pivotCacheDefinition")
            if pt_root is None or not cache_def_member:
                continue
            cache_def_root = _read_xml(zf, cache_def_member)
            records_member = load_typed_relationships(zf, cache_def_member).get("pivotCacheRecords")
            records_root = _read_xml(zf, records_member) if records_member else None
            if cache_def_root is None or records_root is None:
                continue
            fields = parse_cache_fields(cache_def_root)
            records = parse_cache_records(records_root, fields)
            info = parse_pivot_table(pt_root, [field["name"] for field in fields])
            if not info["row_fields"] or info["page_field_count"] or info["hidden_item_count"]:
                continue
            for data_field in info["data_fields"]:
                grouped = aggregate(records, info["row_fields"], data_field)
                if not grouped:
                    continue
                best_key = max(grouped, key=grouped.get)
                worst_key = min(grouped, key=grouped.get)
                aggregates.append(PivotAggregate(
                    sheet_name=sheet_names.get(pt_member, ""),
                    pivot_table_name=info["name"],
                    row_fields=info["row_fields"],
                    data_field_name=data_field["name"],
                    data_field_source=data_field["field"],
                    subtotal=data_field["subtotal"],
                    n_groups=len(grouped),
                    argmax_labels=dict(zip(info["row_fields"], best_key)),
                    argmax_value=grouped[best_key],
                    argmin_labels=dict(zip(info["row_fields"], worst_key)),
                    argmin_value=grouped[worst_key],
                ))
    return aggregates
