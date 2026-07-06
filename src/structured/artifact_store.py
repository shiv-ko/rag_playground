"""artifacts/配下の構造化jsonlを読み込み、案件名で絞り込む。"""
from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from pathlib import Path

_ARTIFACT_FILES = {
    "highlight_cells": "highlight_cells.jsonl",
    "schedule_tasks": "schedule_tasks.jsonl",
    "office_marks": "office_marks.jsonl",
    "train_xlsx_highlight_blocks": "train_xlsx_highlight_blocks.jsonl",
    "train_xlsx_sheets": "train_xlsx_sheets.jsonl",
    "spreadsheet_sheets": "spreadsheet_sheets.jsonl",
    "train_xlsx_small_sheet_cells": "train_xlsx_small_sheet_cells.jsonl",
    "train_xlsx_pivot_aggregates": "train_xlsx_pivot_aggregates.jsonl",
    "version_diff_pairs": "version_diff_poc.jsonl",
}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


class StructuredArtifactStore:
    def __init__(self, by_kind_and_project: dict[str, dict[str, list[dict]]]) -> None:
        self._data = by_kind_and_project

    @classmethod
    def from_artifacts_dir(cls, artifacts_dir: Path) -> "StructuredArtifactStore":
        by_kind_and_project: dict[str, dict[str, list[dict]]] = {}
        for kind, filename in _ARTIFACT_FILES.items():
            by_project: dict[str, list[dict]] = defaultdict(list)
            for row in _load_jsonl(artifacts_dir / filename):
                by_project[row.get("project_name", "")].append(row)
            by_kind_and_project[kind] = by_project
        return cls(by_kind_and_project)

    def _get(self, kind: str, project_name: str) -> list[dict]:
        by_project = self._data.get(kind, {})
        if project_name in by_project:
            return by_project[project_name]
        normalized = unicodedata.normalize("NFC", project_name)
        for name, rows in by_project.items():
            if unicodedata.normalize("NFC", name) == normalized:
                return rows
        return []

    def project_names(self) -> list[str]:
        names: set[str] = set()
        for by_project in self._data.values():
            names.update(name for name in by_project if name)
        return sorted(names)

    def highlight_cells_for(self, project_name: str) -> list[dict]:
        return self._get("highlight_cells", project_name)

    def schedule_tasks_for(self, project_name: str) -> list[dict]:
        return self._get("schedule_tasks", project_name)

    def office_marks_for(self, project_name: str) -> list[dict]:
        return self._get("office_marks", project_name)

    def train_xlsx_highlight_blocks_for(self, project_name: str) -> list[dict]:
        return self._get("train_xlsx_highlight_blocks", project_name)

    def train_xlsx_sheets_for(self, project_name: str) -> list[dict]:
        return self._get("train_xlsx_sheets", project_name)

    def spreadsheet_sheets_for(self, project_name: str) -> list[dict]:
        return self._get("spreadsheet_sheets", project_name)

    def small_sheet_cells_for(self, project_name: str) -> list[dict]:
        return self._get("train_xlsx_small_sheet_cells", project_name)

    def pivot_aggregates_for(self, project_name: str) -> list[dict]:
        return self._get("train_xlsx_pivot_aggregates", project_name)

    def version_diff_pairs_for(self, project_name: str) -> list[dict]:
        return self._get("version_diff_pairs", project_name)
