"""PoC: recompute pivotTable row-group aggregates directly from
pivotTable definition + pivotCache (definition + records), without
depending on openpyxl's pivot cache materialization or on the
already-rendered "compact" worksheet cells.

Goal: for a "compact pivot" question like
  "在 train.xlsx の Pivot シートで、平均月収が最も高い層の抽出条件を答えよ"
we want a *general* procedure (works for any project's pivotTable, not just
Aoba Biomedical) that:
  1. finds every pivotTable in the workbook and its linked pivotCache
     (definition + records) via the OOXML relationship chain,
  2. resolves each cacheField's sharedItems dictionary,
  3. decodes every cached record (dereferencing <x v="i"/> against
     sharedItems, or using the raw typed value when a field has no
     shared-items index),
  4. reconstructs the *actual* pivotTable's row-field tuple → aggregate
     mapping by regrouping raw records (i.e. NOT reusing Excel's cached
     subtotal numbers), and
  5. reports argmax/argmin over the row-field combinations for each
     dataField.

This directly answers: "does pivotTable+pivotCache alone let us derive the
row-combination with the highest/lowest aggregate, without ever opening the
compact worksheet?"

READ-ONLY: only reads from data/raw/... All output goes to this scratchpad.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

REPO_ROOT = Path("/Users/shiv/P/rag_comp")
PROJECT_ROOT = REPO_ROOT / "data" / "raw" / "share" / "共有ドライブ" / "プロジェクト"

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def read_xml(zf: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(zf.read(name))
    except KeyError:
        return None


def rels_path_for(member: str) -> str:
    p = Path(member)
    return str(p.parent / "_rels" / (p.name + ".rels")).replace("\\", "/")


def load_typed_relationships(zf: zipfile.ZipFile, member: str) -> dict[str, str]:
    """rel Type (last path segment) -> resolved target member path."""
    rel_path = rels_path_for(member)
    root = read_xml(zf, rel_path)
    if root is None:
        return {}
    base_dir = Path(member).parent
    out: dict[str, str] = {}
    for rel in root.findall("pkgrel:Relationship", NS):
        rtype = (rel.attrib.get("Type") or "").rsplit("/", 1)[-1]
        target = rel.attrib.get("Target") or ""
        if target.startswith("/"):
            resolved = target.lstrip("/")
        else:
            # os.path.normpath (not pathlib) so ".." segments actually collapse.
            import os

            resolved = os.path.normpath(str(base_dir / target)).replace("\\", "/")
        out[rtype] = resolved
    return out


def find_pivot_tables(zf: zipfile.ZipFile) -> list[str]:
    names = zf.namelist()
    return sorted(n for n in names if re.fullmatch(r"xl/pivotTables/pivotTable\d+\.xml", n))


# ---------------------------------------------------------------------------
# pivotCacheDefinition parsing
# ---------------------------------------------------------------------------

def _coerce_shared_item(child: ET.Element) -> Any:
    tag = child.tag.rsplit("}", 1)[-1]
    v = child.attrib.get("v")
    if tag == "s":
        return v
    if tag == "n":
        if v is None:
            return None
        return float(v) if ("." in v or "e" in v.lower()) else int(v)
    if tag == "b":
        return v == "1"
    if tag == "d":
        return v
    if tag == "m":
        return None
    if tag == "e":
        return None
    return v


def parse_cache_fields(cache_def_root: ET.Element) -> list[dict[str, Any]]:
    fields = []
    for cf in cache_def_root.findall("main:cacheFields/main:cacheField", NS):
        name = cf.attrib.get("name")
        si = cf.find("main:sharedItems", NS)
        shared_items: list[Any] | None = None
        if si is not None and si.attrib.get("count") is not None:
            shared_items = [_coerce_shared_item(child) for child in list(si)]
        fields.append({"name": name, "shared_items": shared_items})
    return fields


def _coerce_record_value(child: ET.Element, field: dict[str, Any]) -> Any:
    tag = child.tag.rsplit("}", 1)[-1]
    if tag == "x":
        idx = int(child.attrib["v"])
        if field["shared_items"] is None:
            raise ValueError(f"field {field['name']!r} has <x> record but no indexed sharedItems")
        return field["shared_items"][idx]
    if tag == "m":
        return None
    if tag == "s":
        return child.attrib.get("v")
    if tag == "n":
        v = child.attrib.get("v")
        if v is None:
            return None
        return float(v) if ("." in v or "e" in v.lower()) else int(v)
    if tag == "b":
        return child.attrib.get("v") == "1"
    if tag == "d":
        return child.attrib.get("v")
    if tag == "e":
        return None
    return child.attrib.get("v")


def parse_cache_records(records_root: ET.Element, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for r in records_root.findall("main:r", NS):
        children = list(r)
        if len(children) != len(fields):
            raise ValueError(f"record has {len(children)} cells but cacheFields has {len(fields)}")
        row = {}
        for field, child in zip(fields, children):
            row[field["name"]] = _coerce_record_value(child, field)
        records.append(row)
    return records


# ---------------------------------------------------------------------------
# pivotTable parsing
# ---------------------------------------------------------------------------

def parse_pivot_table(pt_root: ET.Element, field_names: list[str]) -> dict[str, Any]:
    def field_list(tag: str) -> list[str]:
        out = []
        for f in pt_root.findall(f"main:{tag}/main:field", NS):
            x = int(f.attrib.get("x", "-2"))
            if x == -2:
                continue  # placeholder for the "Values" (data) axis, not a real field
            out.append(field_names[x])
        return out

    row_fields = field_list("rowFields")
    col_fields = field_list("colFields")

    data_fields = []
    for df in pt_root.findall("main:dataFields/main:dataField", NS):
        fld_idx = int(df.attrib["fld"])
        data_fields.append(
            {
                "name": df.attrib.get("name"),
                "field": field_names[fld_idx],
                # OOXML default subtotal, when the attribute is omitted, is "sum".
                "subtotal": df.attrib.get("subtotal", "sum"),
            }
        )

    location = pt_root.find("main:location", NS)
    page_fields = pt_root.findall("main:pageFields/main:pageField", NS)
    hidden_items = pt_root.findall(".//main:item[@h='1']", NS)

    return {
        "name": pt_root.attrib.get("name"),
        "location": location.attrib.get("ref") if location is not None else None,
        "row_fields": row_fields,
        "col_fields": col_fields,
        "data_fields": data_fields,
        "page_field_count": len(page_fields),
        "hidden_item_count": len(hidden_items),
    }


SUBTOTAL_FUNCS = {
    "average": statistics.fmean,
    "sum": sum,
    "count": len,
    "countNums": lambda xs: len(xs),
    "max": max,
    "min": min,
    "product": lambda xs: __import__("math").prod(xs),
    "stdDev": statistics.stdev,
    "stdDevp": statistics.pstdev,
    "var": statistics.variance,
    "varp": statistics.pvariance,
}


def aggregate(records: list[dict[str, Any]], row_fields: list[str], data_field: dict[str, Any]) -> dict[tuple, float]:
    groups: dict[tuple, list[Any]] = defaultdict(list)
    fname = data_field["field"]
    for rec in records:
        key = tuple(rec.get(rf) for rf in row_fields)
        val = rec.get(fname)
        if val is None:
            continue  # Excel's aggregate functions ignore blanks
        groups[key].append(val)
    func = SUBTOTAL_FUNCS.get(data_field["subtotal"])
    if func is None:
        raise NotImplementedError(f"unsupported subtotal function: {data_field['subtotal']}")
    return {k: func(v) for k, v in groups.items() if v}


def analyze_workbook(xlsx_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(xlsx_path.relative_to(REPO_ROOT)),
        "project": nfc(xlsx_path.parent.parent.name),
        "ok": False,
        "error": None,
        "pivot_tables": [],
    }
    try:
        with zipfile.ZipFile(xlsx_path) as zf:
            pt_members = find_pivot_tables(zf)
            if not pt_members:
                result["error"] = "no pivotTables in workbook"
                return result
            for pt_member in pt_members:
                pt_root = read_xml(zf, pt_member)
                pt_rels = load_typed_relationships(zf, pt_member)
                cache_def_member = pt_rels.get("pivotCacheDefinition")
                if not cache_def_member:
                    result["pivot_tables"].append({"member": pt_member, "error": "no pivotCacheDefinition rel"})
                    continue
                cache_def_root = read_xml(zf, cache_def_member)
                cache_rels = load_typed_relationships(zf, cache_def_member)
                records_member = cache_rels.get("pivotCacheRecords")
                if not records_member:
                    result["pivot_tables"].append({"member": pt_member, "error": "no pivotCacheRecords rel"})
                    continue
                records_root = read_xml(zf, records_member)

                fields = parse_cache_fields(cache_def_root)
                field_names = [f["name"] for f in fields]
                records = parse_cache_records(records_root, fields)
                pt_info = parse_pivot_table(pt_root, field_names)
                pt_info["member"] = pt_member
                pt_info["record_count"] = len(records)

                per_data_field = []
                for df in pt_info["data_fields"]:
                    try:
                        agg = aggregate(records, pt_info["row_fields"], df) if pt_info["row_fields"] else {}
                        if agg:
                            best_key = max(agg, key=agg.get)
                            worst_key = min(agg, key=agg.get)
                            per_data_field.append(
                                {
                                    "data_field": df,
                                    "n_groups": len(agg),
                                    "argmax": dict(zip(pt_info["row_fields"], best_key)),
                                    "argmax_value": agg[best_key],
                                    "argmin": dict(zip(pt_info["row_fields"], worst_key)),
                                    "argmin_value": agg[worst_key],
                                }
                            )
                        else:
                            per_data_field.append({"data_field": df, "n_groups": 0, "note": "no row_fields or empty groups"})
                    except NotImplementedError as e:
                        per_data_field.append({"data_field": df, "error": str(e)})
                pt_info["aggregates"] = per_data_field
                result["pivot_tables"].append(pt_info)
            result["ok"] = True
    except Exception as e:  # noqa: BLE001 - audit failures for the report
        result["error"] = repr(e)
    return result


def find_all_train_xlsx() -> list[Path]:
    # NOTE: path components under data/raw/share/... are NFD-normalized on
    # disk (macOS/HFS+-style decomposition, e.g. "デ" = U+30C6 U+3099 rather
    # than the precomposed U+30C7). A literal "03.データ" typed/stored in a
    # different normalization form (NFC) will silently fail to match -- this
    # bit scripts/scan_train_xlsx_xml.py's target_workbooks(), whose filter
    # only "works" today because of a stale __pycache__ compiled against an
    # older (NFD) source; recompiling the *current* checked-in source fresh
    # reproduces the mismatch. Normalize both sides explicitly to avoid this.
    target = nfc("03.データ")
    return sorted(
        p for p in PROJECT_ROOT.rglob("train.xlsx")
        if any(nfc(part) == target for part in p.parts) and not p.name.startswith("~$")
    )


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "poc_pivot_results.json"
    all_results = []
    for path in find_all_train_xlsx():
        r = analyze_workbook(path)
        all_results.append(r)
        print(f"=== {r['project']} ({r['path']}) ok={r['ok']} error={r['error']}")
        for pt in r["pivot_tables"]:
            if "error" in pt and pt.get("error"):
                print(f"    pivotTable {pt.get('member')}: ERROR {pt['error']}")
                continue
            print(f"    {pt['member']} loc={pt['location']} row_fields={pt['row_fields']} col_fields={pt['col_fields']} "
                  f"records={pt['record_count']} page_fields={pt['page_field_count']} hidden_items={pt['hidden_item_count']}")
            for agg in pt["aggregates"]:
                df = agg["data_field"]
                if "error" in agg:
                    print(f"        data_field={df} ERROR {agg['error']}")
                elif agg.get("n_groups", 0) == 0:
                    print(f"        data_field={df} -> {agg.get('note')}")
                else:
                    print(f"        data_field={df['name']} (fld={df['field']}, subtotal={df['subtotal']}) "
                          f"n_groups={agg['n_groups']}")
                    print(f"            argmax={agg['argmax']} value={agg['argmax_value']}")
                    print(f"            argmin={agg['argmin']} value={agg['argmin_value']}")
    out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
