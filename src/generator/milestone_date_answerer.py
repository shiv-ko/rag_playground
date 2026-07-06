"""マイルストーン日付を使った日数計算・横断リスト回答（Phase 3 internal_terms）。

LLMを介さず、Pythonでschedule_tasksを直接走査して計算する
（SpreadsheetCalcAnswererと同様、数値・列挙の完全一致はLLMに推測させない）。
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from src.generator.confidence_gate import ConfidenceGate
from src.models import Answer
from src.retriever.milestone_resolver import (
    MILESTONE_EXPANSION_TO_GROUP,
    detect_milestone_group,
    resolve_milestone_date,
    resolve_milestone_date_by_group,
)
from src.structured.artifact_store import StructuredArtifactStore

# 日本語の\bはUnicode文字境界で機能しないため、milestone_resolverと同じ
# 非英数字境界の判定を使う。
_MS_CODE_RE = re.compile(r"(?<![A-Za-z0-9])M\d{2}(?![A-Za-z0-9])")
_INCLUSIVE_COUNT_HINTS = ("1日目として数え", "当日を1日目")
_THRESHOLD_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def _extract_milestone_tokens(question: str, term_registry: list[dict]) -> list[str]:
    """質問文中のマイルストーントークン（M01, FR等）を出現順に抽出する。

    term_registryには文書種別コード（PL=スケジュール、CT=契約書等）も含まれるため、
    expansionがマイルストーン語義（キックオフ/中間報告/最終報告）に一致するものだけを
    候補にする（PLのような無関係なコードを誤ってトークン化しないため）。
    """
    candidates: set[str] = set(_MS_CODE_RE.findall(question))
    for entry in term_registry:
        term = entry.get("term")
        expansion = entry.get("expansion")
        if term and expansion in MILESTONE_EXPANSION_TO_GROUP and term in question:
            candidates.add(term)

    positioned = sorted(
        ((question.find(term), term) for term in candidates if question.find(term) >= 0),
        key=lambda p: p[0],
    )
    tokens: list[str] = []
    for _, term in positioned:
        if term not in tokens:
            tokens.append(term)
    return tokens


def _wants_inclusive_count(question: str) -> bool:
    return any(hint in question for hint in _INCLUSIVE_COUNT_HINTS)


def _primary_alias_for(project_name: str, project_primary_aliases: dict[str, str]) -> str | None:
    normalized = unicodedata.normalize("NFC", project_name)
    for name, alias in project_primary_aliases.items():
        if unicodedata.normalize("NFC", name) == normalized:
            return alias
    return None


class MilestoneDurationAnswerer:
    """Q16型: 「M01の日からFR実施までの日数は何日ですか」のような単一案件のMS間日数計算。"""

    def __init__(self, threshold: float = 0.4) -> None:
        self.gate = ConfidenceGate(threshold=threshold)

    def answer(
        self,
        question: str,
        project_name: str,
        store: StructuredArtifactStore,
        term_registry: list[dict],
    ) -> Answer:
        question_nfc = unicodedata.normalize("NFC", question)
        tokens = _extract_milestone_tokens(question_nfc, term_registry)
        if len(tokens) < 2:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)

        schedule_rows = store.schedule_tasks_for(project_name)
        if not schedule_rows:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)

        start_date = resolve_milestone_date(schedule_rows, tokens[0], term_registry)
        end_date = resolve_milestone_date(schedule_rows, tokens[1], term_registry)
        if start_date is None or end_date is None:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)

        days = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days
        if _wants_inclusive_count(question_nfc):
            days += 1
        return Answer(text=str(days), confidence=0.9, was_gated=False)


class MilestoneThresholdListAnswerer:
    """Q15型: 「中間報告会または中間レビューが2025年7月1日以前に実施された案件を、
    主略称ですべて挙げてください」のような横断・MS日付しきい値でのリスト回答。"""

    def __init__(self, threshold: float = 0.4) -> None:
        self.gate = ConfidenceGate(threshold=threshold)

    def answer(
        self,
        question: str,
        store: StructuredArtifactStore,
        project_primary_aliases: dict[str, str],
    ) -> Answer:
        question_nfc = unicodedata.normalize("NFC", question)
        group = detect_milestone_group(question_nfc)
        threshold_match = _THRESHOLD_DATE_RE.search(question_nfc)
        if "以前" in question_nfc:
            direction = "before"
        elif "以降" in question_nfc:
            direction = "after"
        else:
            direction = None
        if group is None or threshold_match is None or direction is None:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)

        year, month, day = (int(g) for g in threshold_match.groups())
        threshold = date(year, month, day)

        matched_aliases: list[str] = []
        for project_name in store.project_names():
            schedule_rows = store.schedule_tasks_for(project_name)
            if not schedule_rows:
                # スケジュールデータが無い案件は判定対象外（曖昧一致とは区別し、
                # 全体Missingには倒さない）。
                continue
            resolved = resolve_milestone_date_by_group(schedule_rows, group)
            if resolved is None:
                # スケジュールはあるが日付を一意に解決できない = 判定不能。
                # 列挙系は部分一致=Incorrectの最危険カテゴリのため、安全側で
                # 全体をMissingに倒す（1案件でも判定不能なら全体Missing）。
                return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)
            event_date = date.fromisoformat(resolved)
            matches_threshold = (
                event_date <= threshold if direction == "before" else event_date >= threshold
            )
            if matches_threshold:
                alias = _primary_alias_for(project_name, project_primary_aliases)
                if alias:
                    matched_aliases.append(alias)

        if not matched_aliases:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)
        return Answer(text="、".join(sorted(matched_aliases)), confidence=0.9, was_gated=False)
