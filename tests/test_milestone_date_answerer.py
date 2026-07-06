"""Q15型（横断MS日付しきい値リスト）・Q16型（単一案件MS間日数計算）のテスト。"""
from __future__ import annotations

from src.generator.milestone_date_answerer import (
    MilestoneDurationAnswerer,
    MilestoneThresholdListAnswerer,
)
from src.structured.artifact_store import StructuredArtifactStore

TERM_REGISTRY = [
    {"term": "M01", "expansion": "キックオフ", "note": ""},
    {"term": "M02", "expansion": "中間報告", "note": ""},
    {"term": "M03", "expansion": "最終報告", "note": ""},
    {"term": "FR", "expansion": "最終報告書", "note": "Final Report"},
    {"term": "PL", "expansion": "スケジュール", "note": "Plan"},
]


def _row(project: str, task_name: str, remark: str, start: str, end: str) -> dict:
    return {
        "project_name": project,
        "values": {
            "タスク名": task_name,
            "備考": remark,
            "開始日": f"{start}T00:00:00",
            "終了日": f"{end}T00:00:00",
        },
    }


def _store(rows: list[dict]) -> StructuredArtifactStore:
    by_project: dict[str, list[dict]] = {}
    for row in rows:
        by_project.setdefault(row["project_name"], []).append(row)
    return StructuredArtifactStore({"schedule_tasks": by_project})


# --------------------------------------------------------------------- #
# Q16型: MilestoneDurationAnswerer
# --------------------------------------------------------------------- #


def test_duration_answerer_minamino_style_keyword_only_case() -> None:
    """みなみ野型: M0N表記が無くキーワードのみで、質問はM01/FRトークンで参照する
    （実データ実測: 2025-04-03キックオフ〜2025-05-15最終成果物提出=43日、1日目として数える指示あり）。"""
    rows = [
        _row("MINAMINO", "キックオフ実施・開始合意", "CP1", "2025-04-03", "2025-04-03"),
        _row("MINAMINO", "最終成果物提出・最終報告会", "CP6", "2025-05-15", "2025-05-15"),
    ]
    answerer = MilestoneDurationAnswerer()
    answer = answerer.answer(
        "MINAMINOのPLにおいて、M01当日を1日目として数えた場合、M01の日からFR実施までの日数は何日ですか。",
        "MINAMINO",
        _store(rows),
        TERM_REGISTRY,
    )
    assert not answer.was_gated
    assert answer.text == "43"


def test_duration_answerer_without_inclusive_phrase_uses_plain_diff() -> None:
    rows = [
        _row("MINAMINO", "キックオフ実施", "", "2025-04-03", "2025-04-03"),
        _row("MINAMINO", "最終成果物提出", "", "2025-05-15", "2025-05-15"),
    ]
    answerer = MilestoneDurationAnswerer()
    answer = answerer.answer(
        "MINAMINOのPLにおいて、M01の日からFR実施までの日数は何日ですか。",
        "MINAMINO",
        _store(rows),
        TERM_REGISTRY,
    )
    assert not answer.was_gated
    assert answer.text == "42"


def test_duration_answerer_returns_missing_when_only_one_token_found() -> None:
    rows = [_row("MINAMINO", "キックオフ実施", "", "2025-04-03", "2025-04-03")]
    answerer = MilestoneDurationAnswerer()
    answer = answerer.answer(
        "MINAMINOのPLにおいて、M01の日から完了までの日数は何日ですか。",
        "MINAMINO",
        _store(rows),
        TERM_REGISTRY,
    )
    assert answer.was_gated


def test_duration_answerer_returns_missing_when_a_token_is_unresolvable() -> None:
    rows = [_row("MINAMINO", "キックオフ実施", "", "2025-04-03", "2025-04-03")]
    answerer = MilestoneDurationAnswerer()
    answer = answerer.answer(
        "MINAMINOのPLにおいて、M01の日からM09までの日数は何日ですか。",
        "MINAMINO",
        _store(rows),
        TERM_REGISTRY,
    )
    assert answer.was_gated


def test_duration_answerer_ignores_unrelated_term_codes_like_pl() -> None:
    """PL（スケジュールの略）のような無関係なterm_registryコードをマイルストーン
    トークンとして誤抽出しないこと（PLはM01より前に出現するが、抽出対象は
    キックオフ/中間報告/最終報告語義のコードのみに絞る）。"""
    rows = [
        _row("MINAMINO", "キックオフ実施", "", "2025-04-03", "2025-04-03"),
        _row("MINAMINO", "最終成果物提出", "", "2025-05-15", "2025-05-15"),
    ]
    answerer = MilestoneDurationAnswerer()
    answer = answerer.answer(
        "MINAMINOのPLにおいて、M01の日からFR実施までの日数は何日ですか。",
        "MINAMINO",
        _store(rows),
        TERM_REGISTRY,
    )
    assert not answer.was_gated
    assert answer.text == "42"


# --------------------------------------------------------------------- #
# Q15型: MilestoneThresholdListAnswerer
# --------------------------------------------------------------------- #


def test_threshold_list_answerer_filters_projects_by_date_before() -> None:
    rows = [
        _row("KSS社", "中間報告会実施", "", "2025-06-01", "2025-06-01"),
        _row("TOTO社", "中間報告会議実施（M02）", "", "2025-08-01", "2025-08-01"),
    ]
    store = _store(rows)
    answerer = MilestoneThresholdListAnswerer()
    answer = answerer.answer(
        "中間報告会または中間レビューが2025年7月1日以前に実施された案件を、主略称ですべて挙げてください。",
        store,
        {"KSS社": "KSS", "TOTO社": "TOTO"},
    )
    assert not answer.was_gated
    assert answer.text == "KSS"


def test_threshold_list_answerer_filters_projects_by_date_after() -> None:
    rows = [
        _row("KSS社", "中間報告会実施", "", "2025-06-01", "2025-06-01"),
        _row("TOTO社", "中間報告会議実施（M02）", "", "2025-08-01", "2025-08-01"),
    ]
    store = _store(rows)
    answerer = MilestoneThresholdListAnswerer()
    answer = answerer.answer(
        "中間報告会または中間レビューが2025年7月1日以降に実施された案件を、主略称ですべて挙げてください。",
        store,
        {"KSS社": "KSS", "TOTO社": "TOTO"},
    )
    assert not answer.was_gated
    assert answer.text == "TOTO"


def test_threshold_list_answerer_excludes_prep_tasks_from_matching() -> None:
    """「中間報告資料作成」のような準備タスクを実際のイベントと混同しないこと。"""
    rows = [
        _row("KSS社", "中間報告資料作成", "", "2025-05-01", "2025-05-05"),
        _row("KSS社", "中間報告会実施", "MS4関連", "2025-08-01", "2025-08-01"),
    ]
    store = _store(rows)
    answerer = MilestoneThresholdListAnswerer()
    answer = answerer.answer(
        "中間報告会または中間レビューが2025年7月1日以前に実施された案件を、主略称ですべて挙げてください。",
        store,
        {"KSS社": "KSS"},
    )
    assert answer.was_gated  # 実際のイベントは8月なので該当なし=Missing


def test_threshold_list_answerer_projects_without_schedule_are_excluded_not_ambiguous() -> None:
    """スケジュールデータが無い案件（例: かえで総合病院）は判定対象外として除外し、
    曖昧一致による全体Missingの引き金にはしない。"""
    rows = [_row("KSS社", "中間報告会実施", "", "2025-06-01", "2025-06-01")]
    store = StructuredArtifactStore({
        "schedule_tasks": {"KSS社": rows},
        "office_marks": {"かえで": []},  # スケジュール以外の他artifactにのみ登場する案件
    })
    answerer = MilestoneThresholdListAnswerer()
    answer = answerer.answer(
        "中間報告会または中間レビューが2025年7月1日以前に実施された案件を、主略称ですべて挙げてください。",
        store,
        {"KSS社": "KSS", "かえで": "KAEDE"},
    )
    assert not answer.was_gated
    assert answer.text == "KSS"


def test_threshold_list_answerer_ambiguous_project_forces_global_missing() -> None:
    """1案件でも判定不能（曖昧一致）なら、部分一致=Incorrectの最危険カテゴリを避けるため
    全体をMissingに倒す。"""
    rows = [
        _row("KSS社", "中間報告会実施", "", "2025-06-01", "2025-06-01"),
        _row("曖昧社", "中間報告会実施", "", "2025-06-01", "2025-06-01"),
        _row("曖昧社", "再中間報告会実施", "スコープ変更のため再実施", "2025-06-10", "2025-06-10"),
    ]
    store = _store(rows)
    answerer = MilestoneThresholdListAnswerer()
    answer = answerer.answer(
        "中間報告会または中間レビューが2025年7月1日以前に実施された案件を、主略称ですべて挙げてください。",
        store,
        {"KSS社": "KSS", "曖昧社": "AIMAI"},
    )
    assert answer.was_gated


def test_threshold_list_answerer_missing_group_or_date_is_gated() -> None:
    answerer = MilestoneThresholdListAnswerer()
    answer = answerer.answer(
        "契約金額が最大の案件を教えてください。",
        _store([]),
        {},
    )
    assert answer.was_gated
