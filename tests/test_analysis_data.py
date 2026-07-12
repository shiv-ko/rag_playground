from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pandas as pd

from src.structured.analysis_data import (
    correlation_ranking,
    normalize_notebook_name,
    resolve_analysis_inputs,
)
from src.structured.artifact_store import StructuredArtifactStore


def _store(tmp_path: Path, rows: list[dict]) -> StructuredArtifactStore:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "analysis_records.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8"
    )
    return StructuredArtifactStore.from_artifacts_dir(artifacts)


def test_notebook_name_normalizes_nb_prefix() -> None:
    assert normalize_notebook_name("NB01_eda.ipynb") == "eda"
    assert normalize_notebook_name("01_eda.ipynb") == "eda"
    assert normalize_notebook_name("01_eda_old.ipynb") == "eda_old"


def test_resolves_config_target_and_csv_with_nfd_paths(tmp_path: Path) -> None:
    project = "青潮モビリティサービス"
    project_dir = tmp_path / unicodedata.normalize("NFD", project) / "04.分析" / "analysis_project"
    (project_dir / "data").mkdir(parents=True)
    pd.DataFrame({"x": [1, 2], "target": [2, 4]}).to_csv(project_dir / "data" / "train.csv", index=False)
    rows = [
        {"project_name": project, "kind": "json", "source_path": f"{project}/04.分析/analysis_project/configs/project_config.json", "payload": {"data_csv": "data/train.csv", "target_column": "target"}},
        {"project_name": project, "kind": "notebook", "source_path": f"{project}/04.分析/analysis_project/notebooks/01_eda.ipynb", "payload": {"cells": []}},
    ]
    store = _store(tmp_path, rows)

    resolved = resolve_analysis_inputs(tmp_path, project, store, "NB01_eda.ipynb")

    assert resolved is not None
    assert resolved.target == "target"
    assert list(resolved.frame.columns) == ["x", "target"]


def test_correlation_ranking_excludes_target_identifier_constants_and_nan() -> None:
    frame = pd.DataFrame({
        "id": [1, 2, 3, 4], "target": [1, 2, 3, 4], "high": [1, 2, 4, 8],
        "negative": [4, 3, 2, 1], "constant": [1, 1, 1, 1], "text": list("abcd"),
    })
    signed = correlation_ranking(frame, "target", absolute=False)
    absolute = correlation_ranking(frame, "target", absolute=True)
    assert list(signed.index) == ["high", "negative"]
    assert list(absolute.index) == ["negative", "high"]


def test_resolution_returns_none_for_ambiguous_or_missing_inputs(tmp_path: Path) -> None:
    rows = [
        {"project_name": "A社", "kind": "json", "source_path": "a/project_config.json", "payload": {"data_csv": "data/train.csv", "target_column": "y"}},
        {"project_name": "A社", "kind": "json", "source_path": "b/project_config.json", "payload": {"data_csv": "data/train.csv", "target_column": "y"}},
    ]
    assert resolve_analysis_inputs(tmp_path, "A社", _store(tmp_path, rows), "01_eda.ipynb") is None

