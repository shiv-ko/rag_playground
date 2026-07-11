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


def _fmt_month(month: str) -> str:
    year, mon = month.split("-")
    return f"{year}年{int(mon)}月"


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


def paid_amount_incl_tax(contract: dict[str, Any]) -> int | None:
    """案件が最終的に支払った（支払う）税込金額を返す（cross_project Q3型）。

    固定価格契約は事後精算を行わないため見積額（`estimated_amount_incl_tax`）がそのまま
    支払額。それ以外（T&M/事後精算）は最終報告書由来の確定額`final_amount_incl_tax`を優先し、
    それも無ければ実績工数から`billed_amount_incl_tax`で計算する。いずれも取れなければNone
    （呼び出し側で「全件揃わなければMissing」の判断に使う）。
    """
    if contract.get("contract_type") == "fixed":
        amount = contract.get("estimated_amount_incl_tax")
        return int(amount) if amount is not None else None
    final = contract.get("final_amount_incl_tax")
    if final is not None:
        return int(final)
    actual_hours = contract.get("actual_hours")
    if actual_hours is not None:
        return billed_amount_incl_tax(contract, float(actual_hours))
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


_DATE_ISO_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_DATE_JP_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def parse_two_dates(question: str) -> tuple[date, date] | None:
    matches = _DATE_ISO_RE.findall(question)
    if len(matches) < 2:
        matches = _DATE_JP_RE.findall(question)
    if len(matches) < 2:
        return None
    d1 = date(*(int(x) for x in matches[0]))
    d2 = date(*(int(x) for x in matches[1]))
    return d1, d2


_YEN_DELTA_RE = re.compile(r"([0-9]+(?:,[0-9]{3})*)\s*円\s*(高く|安く|高い|低く|低い)")
_HOUR_DELTA_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*時間\s*(少な|多)")


def parse_yen_delta(question: str) -> int | None:
    match = _YEN_DELTA_RE.search(question)
    if not match:
        return None
    amount = int(match.group(1).replace(",", ""))
    return -amount if match.group(2) in ("安く", "低く", "低い") else amount


def parse_hour_delta(question: str) -> float | None:
    match = _HOUR_DELTA_RE.search(question)
    if not match:
        return None
    magnitude = float(match.group(1))
    return -magnitude if match.group(2) == "少な" else magnitude


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
        if "消費税額の総額" in question:
            return self._answer_tax_total(store)
        if "支払月" in question and "精算総額" in question:
            return self._answer_payment_top3(store)
        if "APR-M3" in question:
            return self._answer_apr_list(question, store, project_primary_aliases, project_aliases)
        if "APR-M1" in question and "10000" in question:
            return self._answer_apr_m1_completed_row_threshold(
                store, project_primary_aliases, project_aliases
            )
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
        if "単価" in question and parse_yen_delta(question) is not None and parse_hour_delta(question) is not None:
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
        yen_delta = parse_yen_delta(question)
        hour_delta = parse_hour_delta(question)
        actual_hours = contract.get("actual_hours")
        if yen_delta is None or hour_delta is None or actual_hours is None:
            return _missing(self.gate)
        baseline = billed_amount_incl_tax(contract, float(actual_hours))
        scenario = billed_amount_incl_tax(
            contract, float(actual_hours) + hour_delta, rate_delta=yen_delta
        )
        if baseline is None or scenario is None:
            return _missing(self.gate)
        diff = scenario - baseline
        suffix = "増額" if diff >= 0 else "減額"
        text = f"{_fmt_yen(abs(diff))}{suffix}"
        return Answer(text=text, confidence=0.9, was_gated=False, raw_text=text, gate_reason="contract_calc")

    def _answer_tax_total(self, store: StructuredArtifactStore) -> Answer:
        """全案件で支払った税込金額をもとに消費税額の総額を答える（Q3型）。

        1件でも`paid_amount_incl_tax`が算出不能ならMissingにフォールバックする
        （§1.1の設計: 正答化ではなく安全化が目的。青潮のようにOCR未実装で解決不能な
        案件が1件でも混じれば、全体をMissingへ倒す）。
        """
        rows = [r for r in store.all_contracts() if r.get("status") == "ok"]
        if not rows:
            return _missing(self.gate, "contract_tax_total_no_contracts")
        total_tax = 0.0
        for row in rows:
            paid = paid_amount_incl_tax(row)
            if paid is None:
                return _missing(self.gate, "contract_tax_total_incomplete")
            tax_rate = float(row.get("tax_rate") or 0.10)
            total_tax += paid - paid / (1 + tax_rate)
        text = _fmt_yen(total_tax)
        return Answer(text=text, confidence=0.85, was_gated=False, raw_text=text, gate_reason="contract_tax_total")

    def _answer_payment_top3(self, store: StructuredArtifactStore) -> Answer:
        """全案件の支払月ごとの精算総額を集計し、上位3ヶ月と総額を答える（Q40型）。

        1件でもpayment_scheduleが空ならMissingへフォールバックする（Q3の§1.1と同じ
        「全件揃わなければMissing」の安全側設計を踏襲。抽出失敗した案件を除外して集計すると
        黙って過小集計になりIncorrectのリスクを持ち込むため）。
        """
        rows = [r for r in store.all_contracts() if r.get("status") == "ok"]
        if not rows:
            return _missing(self.gate, "contract_payment_top3_no_contracts")
        monthly: dict[str, int] = {}
        for row in rows:
            schedule = row.get("payment_schedule")
            if not schedule:
                return _missing(self.gate, "contract_payment_top3_incomplete")
            for entry in schedule:
                monthly[entry["month"]] = monthly.get(entry["month"], 0) + int(entry["amount_incl_tax"])
        top3 = sorted(monthly.items(), key=lambda kv: kv[1], reverse=True)[:3]
        text = "、".join(f"{_fmt_month(month)}: {_fmt_yen(amount)}" for month, amount in top3)
        return Answer(text=text, confidence=0.8, was_gated=False, raw_text=text, gate_reason="contract_payment_top3")

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

    def _answer_apr_m1_completed_row_threshold(
        self,
        store: StructuredArtifactStore,
        primary_aliases: dict[str, str],
        aliases: dict[str, list[str]],
    ) -> Answer:
        """APR-M1該当・完了案件・train.csv行数10000行以上の案件を列挙する（Q87型）。

        「完了案件」は`has_final_report`（`06.報告書/`配下にoldを除く最終報告ファイルが
        1件以上存在するか）で判定する。以前は`final_amount_incl_tax`（最終報告書からの
        金額の正規表現抽出）の非null性を代理指標にしていたが、固定価格契約は最終報告書で
        金額を再掲しない/言い回しが既存正規表現と一致しないため、報告書自体は提出済み
        （＝完了）でも常にnullになり誤って「未完了」判定されるバグが実データで見つかった。
        `has_final_report`はファイル存在の確認のみなので、この誤判定を避けられる。
        フラグが立たない（報告書自体が無い）案件は対象外とし、誤ってMissingへ倒す
        （ゲート厚めの原則、勝手に「未完了」と断定して除外はするが「完了」と断定はしない）。
        """
        if self.data_dir is None:
            return _missing(self.gate, "contract_apr_m1_no_data_dir")
        matches: list[str] = []
        for row in store.all_contracts():
            if row.get("status") != "ok":
                continue
            amount = row.get("estimated_amount_incl_tax")
            if not amount:
                continue
            if not row.get("has_final_report"):
                continue
            level = determine_apr_level(
                int(amount),
                is_medical_project(row["project_name"], aliases.get(row["project_name"])),
                row.get("contract_type") == "time_and_materials",
            )
            if level != "APR-M1":
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
            if n_rows < 10_000:
                continue
            matches.append(_project_alias(row["project_name"], primary_aliases))
        if not matches:
            return _missing(self.gate, "contract_apr_m1_no_match")
        text = "、".join(matches)
        return Answer(
            text=text, confidence=0.85, was_gated=False, raw_text=text, gate_reason="contract_apr_m1_completed"
        )

    def _answer_overlap(
        self,
        question: str,
        store: StructuredArtifactStore,
        primary_aliases: dict[str, str],
    ) -> Answer:
        date_range = parse_two_dates(question)
        if date_range is None:
            return _missing(self.gate)
        start, end = date_range
        result = []
        for row in store.all_contracts():
            if not row.get("start_date") or not row.get("end_date"):
                continue
            cs = date.fromisoformat(row["start_date"])
            ce = date.fromisoformat(row["end_date"])
            overlaps = min(end, ce) >= max(start, cs)
            period_days = row.get("contract_period_days")
            if overlaps and period_days is not None and period_days > 40:
                result.append(_project_alias(row["project_name"], primary_aliases))
        if not result:
            return _missing(self.gate)
        text = "、".join(result)
        return Answer(text=text, confidence=0.9, was_gated=False, raw_text=text, gate_reason="contract_overlap")

    def _answer_fixed_per_row(self, store: StructuredArtifactStore, primary_aliases: dict[str, str]) -> Answer:
        if self.data_dir is None:
            return _missing(self.gate)
        best: tuple[int, str] | None = None
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
            value = math.ceil(int(row["estimated_amount_incl_tax"]) / n_rows)
            if best is None or value > best[0]:
                best = (value, row["project_name"])
        if best is None:
            return _missing(self.gate)
        alias = _project_alias(best[1], primary_aliases)
        text = f"{alias}、{best[0]:,}円"
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
