"""Resolve analysis CSV inputs and compute deterministic correlation rankings."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.structured.artifact_store import StructuredArtifactStore


@dataclass(frozen=True)
class AnalysisInputs:
    frame: pd.DataFrame
    target: str
    notebook_record: dict
    config_record: dict


def normalize_notebook_name(name: str) -> str:
    stem = Path(unicodedata.normalize("NFC", name)).stem.casefold()
    stem = re.sub(r"^nb", "", stem)
    return re.sub(r"^\d+[_-]*", "", stem)


def resolve_analysis_inputs(
    data_dir: Path,
    project_name: str,
    store: StructuredArtifactStore,
    notebook_hint: str,
) -> AnalysisInputs | None:
    records = store.analysis_records_for(project_name)
    configs = [
        record for record in records
        if record.get("kind") == "json" and Path(record.get("source_path", "")).name == "project_config.json"
    ]
    wanted_notebook = normalize_notebook_name(notebook_hint)
    notebooks = [
        record for record in records
        if record.get("kind") == "notebook"
        and normalize_notebook_name(Path(record.get("source_path", "")).name) == wanted_notebook
    ]
    if len(configs) != 1 or len(notebooks) != 1:
        return None
    config = configs[0].get("payload", {})
    relative_data = config.get("data_csv")
    target = config.get("target_column")
    if not isinstance(relative_data, str) or not isinstance(target, str) or not target:
        return None
    normalized_project = unicodedata.normalize("NFC", project_name)
    normalized_suffix = unicodedata.normalize("NFC", relative_data.replace("\\", "/"))
    candidates = [
        path for path in data_dir.rglob(Path(relative_data).name)
        if path.is_file()
        and normalized_project in unicodedata.normalize("NFC", path.as_posix())
        and unicodedata.normalize("NFC", path.as_posix()).endswith(normalized_suffix)
    ]
    if len(candidates) != 1:
        return None
    try:
        separator = "\t" if candidates[0].suffix.casefold() == ".tsv" else ","
        frame = pd.read_csv(candidates[0], sep=separator)
    except (OSError, UnicodeError, pd.errors.ParserError):
        return None
    if target not in frame.columns:
        return None
    return AnalysisInputs(frame=frame, target=target, notebook_record=notebooks[0], config_record=configs[0])


def correlation_ranking(frame: pd.DataFrame, target: str, absolute: bool) -> pd.Series:
    numeric = frame.select_dtypes(include="number")
    if target not in numeric.columns:
        return pd.Series(dtype=float)
    excluded = {target}
    excluded.update(column for column in numeric.columns if column.casefold() in {"id", "index"})
    feature_columns = [column for column in numeric.columns if column not in excluded]
    feature_columns = [column for column in feature_columns if numeric[column].nunique(dropna=True) > 1]
    if not feature_columns:
        return pd.Series(dtype=float)
    ranking = numeric[feature_columns].corrwith(numeric[target]).dropna()
    if absolute:
        ranking = ranking.abs()
    return ranking.sort_values(ascending=False, kind="stable")
