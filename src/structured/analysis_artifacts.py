"""Build deterministic structured records from project analysis files."""
from __future__ import annotations

import ast
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

_GENERATED_BY = "scripts/build_analysis_artifacts.py"
_SUPPORTED_SUFFIXES = {".json", ".ipynb", ".py"}
_EMBEDDED_IMAGE_RE = re.compile(r"data:image/[^;\s)]+;base64,[A-Za-z0-9+/=\r\n]+")


def _text(value: str | list[str] | None) -> str:
    if value is None:
        return ""
    return "".join(value) if isinstance(value, list) else value


def _source_text(value: str | list[str] | None) -> str:
    return _EMBEDDED_IMAGE_RE.sub("[embedded-image-removed]", _text(value))


def _expression(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        if node.value is None or isinstance(node.value, (str, int, float, bool)):
            return node.value
        return {"literal": repr(node.value)}
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [_expression(item) for item in node.elts]
    if isinstance(node, ast.Dict):
        result = {}
        for key, value in zip(node.keys, node.values):
            if key is None:
                result["**"] = _expression(value)
            else:
                result[_expression(key)] = _expression(value)
        return result
    if isinstance(node, ast.Name):
        return {"name": node.id}
    if isinstance(node, ast.Attribute):
        return {"attribute": ast.unparse(node)}
    return {"expression": ast.unparse(node)}


def _target(node: ast.AST) -> str | None:
    if isinstance(node, (ast.Name, ast.Attribute)):
        return ast.unparse(node)
    return None


def _python_payload(source: str) -> dict[str, list[dict[str, Any]]]:
    tree = ast.parse(source)
    assignments: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is not None:
                for candidate in targets:
                    name = _target(candidate)
                    if name:
                        assignments.append({"target": name, "value": _expression(value)})
        elif isinstance(node, ast.Compare):
            comparisons.append(
                {
                    "left": _expression(node.left).get("name", ast.unparse(node.left))
                    if isinstance(_expression(node.left), dict)
                    else _expression(node.left),
                    "operators": [type(operator).__name__ for operator in node.ops],
                    "comparators": [_expression(item) for item in node.comparators],
                }
            )
        elif isinstance(node, ast.Call):
            calls.append(
                {
                    "function": ast.unparse(node.func),
                    "args": [_expression(argument) for argument in node.args],
                    "keywords": {
                        keyword.arg or "**": _expression(keyword.value) for keyword in node.keywords
                    },
                }
            )
    return {"assignments": assignments, "comparisons": comparisons, "calls": calls}


def _notebook_payload(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    cells = []
    for number, cell in enumerate(data.get("cells", []), start=1):
        outputs = []
        for output in cell.get("outputs", []):
            if output.get("output_type") == "stream" and "text" in output:
                outputs.append(
                    {
                        "output_type": "stream",
                        "name": output.get("name"),
                        "text": _text(output["text"]),
                    }
                )
            elif isinstance(output.get("data"), dict) and "text/plain" in output["data"]:
                outputs.append(
                    {
                        "output_type": output.get("output_type"),
                        "text/plain": _text(output["data"]["text/plain"]),
                    }
                )
        cells.append(
            {
                "cell_number": number,
                "cell_type": cell.get("cell_type"),
                "source": _source_text(cell.get("source")),
                "outputs": outputs,
            }
        )
    return {"cells": cells}


def _source_path(data_dir: Path, path: Path) -> str:
    parts = path.relative_to(data_dir).parts
    return "/".join(unicodedata.normalize("NFC", part) for part in parts)


def build_analysis_records(data_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for analysis_dir in data_dir.rglob("04.分析"):
        if (
            not analysis_dir.is_dir()
            or unicodedata.normalize("NFC", analysis_dir.parent.parent.name) != "プロジェクト"
        ):
            continue
        project_name = unicodedata.normalize("NFC", analysis_dir.parent.name)
        for path in analysis_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
                continue
            source_path = _source_path(data_dir, path)
            kind = {".json": "json", ".ipynb": "notebook", ".py": "python"}[path.suffix.lower()]
            try:
                if kind == "json":
                    payload = json.loads(path.read_text(encoding="utf-8"))
                elif kind == "notebook":
                    payload = _notebook_payload(json.loads(path.read_text(encoding="utf-8")))
                else:
                    payload = _python_payload(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError, SyntaxError, TypeError, ValueError) as error:
                payload = {
                    "source_kind": kind,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
                kind = "failure"
            records.append(
                {
                    "project_name": project_name,
                    "source_path": source_path,
                    "kind": kind,
                    "payload": payload,
                    "generated_by": _GENERATED_BY,
                    "do_not_edit": True,
                }
            )
    return sorted(records, key=lambda row: row["source_path"])


def write_analysis_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
