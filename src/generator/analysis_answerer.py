"""Deterministic answers backed by analysis JSON and Python AST artifacts."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.models import Answer, Document, ScoredDocument
from src.structured.artifact_store import StructuredArtifactStore

_COMPARISON_SYMBOLS = {"Lt": "<", "LtE": "<=", "Gt": ">", "GtE": ">=", "Eq": "==", "NotEq": "!="}
_INVERTED_COMPARISON_SYMBOLS = {"Lt": ">=", "LtE": ">", "Gt": "<=", "GtE": "<", "Eq": "!=", "NotEq": "=="}
_DEFAULT_RE = re.compile(r"\b(?:to_int|to_float)\(model_params\.get\(['\"]([^'\"]+)['\"]\),\s*([^()]+)\)")


def _source(record: dict) -> ScoredDocument:
    return ScoredDocument(
        document=Document(
            text=str(record.get("payload", "")),
            source_path=Path(record.get("source_path", "analysis_records.jsonl")),
            metadata={"artifact_kind": record.get("kind")},
        ),
        score=1.0,
        retrieval_method="structured",
    )


def _answer(text: Any, records: list[dict]) -> Answer:
    return Answer(text=str(text), confidence=0.95, source_docs=[_source(record) for record in records])


def _json_records(records: list[dict], filename: str) -> list[dict]:
    return [record for record in records if record.get("kind") == "json" and Path(record.get("source_path", "")).name == filename]


def _python_records(records: list[dict]) -> list[dict]:
    return [record for record in records if record.get("kind") == "python"]


class AnalysisAnswerer:
    def answer(
        self, question: str, project_name: str, store: StructuredArtifactStore
    ) -> Answer | None:
        records = store.analysis_records_for(project_name)
        if not records:
            return None
        if "sparse_output" in question and "False" in question:
            return self._sparse_false(records)
        if "CAT" in question and "dtype" in question and ("ユニーク" in question or "nunique" in question):
            return self._categorical_condition(records)
        if all(name in question for name in ("n_estimators", "learning_rate", "random_state")):
            return self._runtime_defaults(records)
        if "max_depth" in question:
            return self._metrics_path(records, ("model_params", "max_depth"))
        if "selected_columns" in question and ("交互作用" in question or "__x__" in question):
            return self._interaction_columns(records)
        return None

    def _sparse_false(self, records: list[dict]) -> Answer | None:
        matches: list[tuple[str, dict]] = []
        pattern = re.compile(r"^\s*\w+\s*!=\s*['\"]([^'\"]+)['\"]\s*$")
        for record in _python_records(records):
            for call in record.get("payload", {}).get("calls", []):
                expression = call.get("keywords", {}).get("sparse_output", {})
                if isinstance(expression, dict):
                    match = pattern.match(str(expression.get("expression", "")))
                    if match:
                        matches.append((match.group(1), record))
        if len(matches) != 1:
            return None
        return _answer(matches[0][0], [matches[0][1]])

    def _categorical_condition(self, records: list[dict]) -> Answer | None:
        dtype_names: set[str] = set()
        comparisons: list[tuple[dict, dict]] = []
        for record in _python_records(records):
            payload = record.get("payload", {})
            for call in payload.get("calls", []):
                match = re.search(r"is_(object|string|categorical)_dtype$", call.get("function", ""))
                if match and call.get("args"):
                    dtype_names.add(match.group(1))
            for comparison in payload.get("comparisons", []):
                if comparison.get("left") in {"unique_count", "series.nunique()"}:
                    operators = comparison.get("operators", [])
                    comparators = comparison.get("comparators", [])
                    if len(operators) == len(comparators) == 1 and operators[0] in _COMPARISON_SYMBOLS:
                        comparisons.append((comparison, record))
        unique_comparisons = {
            (item[0]["left"], item[0]["operators"][0], str(item[0]["comparators"][0])) for item in comparisons
        }
        if not dtype_names or len(unique_comparisons) != 1:
            return None
        comparison, record = comparisons[0]
        comparator = comparison["comparators"][0]
        if isinstance(comparator, dict) and "name" in comparator:
            comparator = comparator["name"]
        # features.pyの比較は高cardinality列を除外するif条件なので、CATとして残る条件は否定形。
        symbol = _INVERTED_COMPARISON_SYMBOLS[comparison["operators"][0]]
        ordered = [name for name in ("object", "string", "categorical") if name in dtype_names]
        return _answer(
            f"{'・'.join(ordered)}型で、かつ unique_count {symbol} {comparator} の列をCATと判定します。",
            [record],
        )

    def _runtime_defaults(self, records: list[dict]) -> Answer | None:
        configs = _json_records(records, "project_config.json")
        if len(configs) != 1:
            return None
        config = configs[0].get("payload", {})
        if config.get("model_type") != "gradient_boosting" or not isinstance(config.get("model_params"), dict):
            return None
        params = config["model_params"]
        values: dict[str, Any] = {key: params[key] for key in ("n_estimators", "learning_rate") if key in params}
        relevant: list[dict] = []
        for record in _python_records(records):
            payload = record.get("payload", {})
            calls = [call for call in payload.get("calls", []) if call.get("function") == "GradientBoostingClassifier"]
            if not calls:
                continue
            relevant.append(record)
            for assignment in payload.get("assignments", []):
                target = assignment.get("target")
                value = assignment.get("value")
                if target not in {"n_estimators", "learning_rate"} or target in values or not isinstance(value, dict):
                    continue
                match = _DEFAULT_RE.fullmatch(value.get("expression", ""))
                if match and match.group(1) == target:
                    raw = match.group(2).strip()
                    try:
                        values[target] = float(raw) if "." in raw else int(raw)
                    except ValueError:
                        return None
        random_state = config.get("random_state")
        if len(relevant) != 1 or set(values) != {"n_estimators", "learning_rate"} or random_state is None:
            return None
        return _answer(
            f"n_estimators={values['n_estimators']}、learning_rate={values['learning_rate']}、random_state={random_state}",
            [configs[0], relevant[0]],
        )

    def _metrics_path(self, records: list[dict], path: tuple[str, ...]) -> Answer | None:
        matches: list[tuple[Any, dict]] = []
        for record in _json_records(records, "metrics.json"):
            value: Any = record.get("payload")
            for key in path:
                if not isinstance(value, dict) or key not in value:
                    break
                value = value[key]
            else:
                matches.append((value, record))
        if len(matches) != 1 or matches[0][0] is None:
            return None
        return _answer(matches[0][0], [matches[0][1]])

    def _interaction_columns(self, records: list[dict]) -> Answer | None:
        metrics = _json_records(records, "metrics.json")
        if len(metrics) != 1:
            return None
        selected = metrics[0].get("payload", {}).get("feature_selection", {}).get("selected_columns")
        if not isinstance(selected, list) or not all(isinstance(value, str) for value in selected):
            return None
        code_records = [
            record for record in _python_records(records)
            if any("__x__" in str(item.get("value")) for item in record.get("payload", {}).get("assignments", []))
        ]
        if len(code_records) != 1:
            return None
        values = [value for value in selected if re.fullmatch(r".+__x__.+", value)]
        if not values:
            return None
        return _answer("、".join(values), [metrics[0], code_records[0]])
