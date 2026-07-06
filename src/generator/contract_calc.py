"""Deterministic answers for contract billing and approval-rule questions."""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.generator.approval_rule import determine_apr_level, is_medical_project
from src.generator.confidence_gate import ConfidenceGate
from src.models import Answer
from src.structured.artifact_store import StructuredArtifactStore


def _missing(gate: ConfidenceGate, reason: str = "contract_calc") -> Answer:
    return Answer(text=gate.missing_text(), confidence=0.0, was_gated=True, gate_reason=reason)


def _fmt_yen(value: float | int) -> str:
    return f"{int(round(value)):,}円"


def parse_hours(text: str) -> float | None:
    patterns = [
        r"ACTH\s*[=：:]\s*([0-9]+(?:\.[0-9]+)?)\s*h(?:\s*([0-9]+)\s*m)?",
        r"([0-9]+(?:\.[0-9]+)?)\s*時間\s*([0-9]+)\s*分",
        r"ACTH\s*[=：:]\s*([0-9]+(?:\.[0-9]+)?)\s*時間",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        hours = float(match.group(1))
        minutes = float(match.group(2) or 0) if len(match.groups()) > 1 else 0
        return hours + minutes / 60
    return None


def rounded_hours(hours: float, rule: str, unit_minutes: int | None) -> float | None:
    if rule == "none":
        return hours
    if unit_minutes is None:
        return None
    unit = unit_minutes / 60
    if rule in {"ceiling_to_unit", "half_unit_bucket"}:
        return math.ceil((hours - 1e-9) / unit) * unit
    return None


def billed_amount_incl_tax(contract: dict[str, Any], hours: float, rate_delta: int = 0) -> int | None:
    rate = contract.get("rate_yen_per_hour")
    if rate is None:
        return None
    rounded = rounded_hours(
        hours,
        str(contract.get("rounding_rule") or "unknown"),
        contract.get("rounding_unit_minutes"),
    )
    if rounded is None:
        return None
    return int(round(rounded * (int(rate) + rate_delta) * (1 + float(contract.get("tax_rate") or 0.10))))


def _project_alias(project: str, primary_aliases: dict[str, str]) -> str:
    normalized = unicodedata.normalize("NFC", project)
    for key, value in primary_aliases.items():
        if unicodedata.normalize("NFC", key) == normalized:
            return value
    return project


class ContractCalcAnswerer:
    def __init__(self, threshold: float = 0.4, data_dir: Path | None = None) -> None:
        self.gate = ConfidenceGate(threshold=threshold)
        self.data_dir = data_dir

    def answer(
        self,
        question: str,
        project_name: str | None,
        store: StructuredArtifactStore,
        project_primary_aliases: dict[str, str] | None = None,
        project_aliases: dict[str, list[str]] | None = None,
    ) -> Answer:
        project_primary_aliases = project_primary_aliases or {}
        project_aliases = project_aliases or {}
        if "APR-M3" in question:
            return self._answer_apr_list(question, store, project_primary_aliases, project_aliases)
        if "契約期間" in question and "40日" in question:
            return self._answer_overlap(question, store, project_primary_aliases)
        if "1行あたり" in question and ("固定" in question or "固定金額" in question):
            return self._answer_fixed_per_row(store, project_primary_aliases)
        if "乖離" in question and "工数" in question:
            return self._answer_largest_hours_gap(store, project_primary_aliases)
        if project_name is None:
            return _missing(self.gate, "contract_no_project")
        rows = [r for r in store.contracts_for(project_name) if r.get("status") == "ok"]
        if not rows:
            return _missing(self.gate, "contract_not_found")
        contract = rows[0]
        if "単価" in question and ("+2000" in question or "＋2000" in question):
            return self._answer_rate_delta(question, contract)
        if "ESTH" in question and "ACTH" in question and "割" in question:
            return self._answer_derived_hourly_rate(contract)
        hours = parse_hours(question)
        if hours is not None and ("見込" in question or "請求" in question):
            return self._answer_amount_difference(question, contract, hours)
        if "差額" in question and contract.get("final_amount_incl_tax") is not None:
            return self._answer_final_difference(contract)
        return _missing(self.gate)

    def _answer_amount_difference(self, question: str, contract: dict[str, Any], hours: float) -> Answer:
        actual = billed_amount_incl_tax(contract, hours)
        expected = contract.get("estimated_amount_incl_tax")
        if actual is None or expected is None:
            return _missing(self.gate)
        diff = int(expected) - actual
        suffix = "減額" if diff >= 0 else "増額"
        text = f"{_fmt_yen(abs(diff))}{suffix}"
        return Answer(text=text, confidence=0.95, was_gated=False, raw_text=text, gate_reason="contract_calc")

    def _answer_final_difference(self, contract: dict[str, Any]) -> Answer:
        expected = contract.get("estimated_amount_incl_tax")
        final = contract.get("final_amount_incl_tax")
        if expected is None or final is None:
            return _missing(self.gate)
        diff = int(expected) - int(final)
        suffix = "減額" if diff >= 0 else "増額"
        text = f"{_fmt_yen(abs(diff))}{suffix}"
        return Answer(text=text, confidence=0.9, was_gated=False, raw_text=text, gate_reason="contract_final_diff")

    def _answer_derived_hourly_rate(self, contract: dict[str, Any]) -> Answer:
        expected = contract.get("estimated_amount_incl_tax")
        final = contract.get("final_amount_incl_tax")
        esth = contract.get("esth_hours")
        actual = contract.get("actual_hours")
        if expected is None or final is None or esth is None or actual is None:
            return _missing(self.gate)
        hour_gap = float(esth) - float(actual)
        if abs(hour_gap) < 1e-9:
            return _missing(self.gate)
        text = _fmt_yen((int(expected) - int(final)) / hour_gap)
        return Answer(text=text, confidence=0.9, was_gated=False, raw_text=text, gate_reason="contract_derived_rate")

    def _answer_rate_delta(self, question: str, contract: dict[str, Any]) -> Answer:
        match = re.search(r"ACTH\s*[-−]\s*([0-9]+(?:\.[0-9]+)?)\s*h", question, re.IGNORECASE)
        if not match or contract.get("esth_hours") is None or contract.get("estimated_amount_incl_tax") is None:
            return _missing(self.gate)
        scenario_hours = float(contract["esth_hours"]) - float(match.group(1))
        scenario = billed_amount_incl_tax(contract, scenario_hours, rate_delta=2000)
        if scenario is None:
            return _missing(self.gate)
        diff = scenario - int(contract["estimated_amount_incl_tax"])
        suffix = "増額" if diff >= 0 else "減額"
        text = f"{_fmt_yen(abs(diff))}{suffix}"
        return Answer(text=text, confidence=0.9, was_gated=False, raw_text=text, gate_reason="contract_calc")

    def _answer_apr_list(
        self,
        question: str,
        store: StructuredArtifactStore,
        primary_aliases: dict[str, str],
        aliases: dict[str, list[str]],
    ) -> Answer:
        matches: list[dict[str, Any]] = []
        for row in store.all_contracts():
            amount = row.get("estimated_amount_incl_tax")
            if not amount or row.get("status") != "ok":
                continue
            level = determine_apr_level(
                int(amount),
                is_medical_project(row["project_name"], aliases.get(row["project_name"])),
                row.get("contract_type") == "time_and_materials",
            )
            if level == "APR-M3":
                matches.append(row)
        if not matches:
            return _missing(self.gate)
        total = sum(int(row["estimated_amount_incl_tax"]) for row in matches)
        names = "、".join(_project_alias(row["project_name"], primary_aliases) for row in matches)
        text = f"{names}、合計{_fmt_yen(total)}"
        return Answer(text=text, confidence=0.9, was_gated=False, raw_text=text, gate_reason="contract_apr")

    def _answer_overlap(
        self,
        question: str,
        store: StructuredArtifactStore,
        primary_aliases: dict[str, str],
    ) -> Answer:
        dates = re.findall(r"(\d{4})年(\d{1,2})月(\d{1,2})日", question)
        if len(dates) < 2:
            return _missing(self.gate)
        start = date(*(int(x) for x in dates[0]))
        end = date(*(int(x) for x in dates[1]))
        result = []
        for row in store.all_contracts():
            if not row.get("start_date") or not row.get("end_date"):
                continue
            cs = date.fromisoformat(row["start_date"])
            ce = date.fromisoformat(row["end_date"])
            overlap = (min(end, ce) - max(start, cs)).days + 1
            if overlap > 40:
                result.append(_project_alias(row["project_name"], primary_aliases))
        if not result:
            return _missing(self.gate)
        text = "、".join(result)
        return Answer(text=text, confidence=0.9, was_gated=False, raw_text=text, gate_reason="contract_overlap")

    def _answer_fixed_per_row(self, store: StructuredArtifactStore, primary_aliases: dict[str, str]) -> Answer:
        if self.data_dir is None:
            return _missing(self.gate)
        best: tuple[float, str] | None = None
        for row in store.all_contracts():
            if row.get("contract_type") != "fixed" or not row.get("estimated_amount_incl_tax"):
                continue
            normalized_project = unicodedata.normalize("NFC", row["project_name"])
            csvs = sorted(
                p for p in self.data_dir.rglob("train.csv")
                if normalized_project in unicodedata.normalize("NFC", str(p))
            )
            if not csvs:
                continue
            try:
                n_rows = len(pd.read_csv(csvs[0]))
            except Exception:
                continue
            value = int(row["estimated_amount_incl_tax"]) / n_rows
            if best is None or value > best[0]:
                best = (value, row["project_name"])
        if best is None:
            return _missing(self.gate)
        text = _project_alias(best[1], primary_aliases)
        return Answer(text=text, confidence=0.85, was_gated=False, raw_text=text, gate_reason="contract_per_row")

    def _answer_largest_hours_gap(self, store: StructuredArtifactStore, primary_aliases: dict[str, str]) -> Answer:
        best: tuple[float, str] | None = None
        for row in store.all_contracts():
            if row.get("contract_type") != "time_and_materials":
                continue
            if row.get("esth_hours") is None or row.get("actual_hours") is None:
                continue
            gap = abs(float(row["esth_hours"]) - float(row["actual_hours"]))
            if best is None or gap > best[0]:
                best = (gap, row["project_name"])
        if best is None:
            return _missing(self.gate)
        text = _project_alias(best[1], primary_aliases)
        return Answer(text=text, confidence=0.85, was_gated=False, raw_text=text, gate_reason="contract_hours_gap")
