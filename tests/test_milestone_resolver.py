"""マイルストーン日付リゾルバのテスト（合成フィクスチャで案件ごとの表記揺れを再現する）。"""
from __future__ import annotations

from src.retriever.milestone_resolver import (
    detect_milestone_group,
    resolve_milestone_date,
    resolve_milestone_date_by_group,
)

TERM_REGISTRY = [
    {"term": "M01", "expansion": "キックオフ", "note": ""},
    {"term": "M02", "expansion": "中間報告", "note": ""},
    {"term": "M03", "expansion": "最終報告", "note": ""},
    {"term": "FR", "expansion": "最終報告書", "note": "Final Report"},
    {"term": "PL", "expansion": "スケジュール", "note": "Plan"},
]


def _row(task_name: str, remark: str, start: str, end: str) -> dict:
    return {
        "values": {
            "タスク名": task_name,
            "備考": remark,
            "開始日": f"{start}T00:00:00",
            "終了日": f"{end}T00:00:00",
        }
    }


def test_resolves_via_literal_bracket_code_touto_style() -> None:
    """東都型: 「（M0N）」がタスク名末尾に付く書式。"""
    rows = [
        _row("プロジェクト立上げ", "", "2025-08-18", "2025-08-18"),
        _row("キックオフ会議実施（M01）", "議事録反映期限", "2025-08-18", "2025-08-18"),
        _row("中間報告会議実施（M02）", "", "2025-09-08", "2025-09-08"),
    ]
    assert resolve_milestone_date(rows, "M01", TERM_REGISTRY) == "2025-08-18"
    assert resolve_milestone_date(rows, "M02", TERM_REGISTRY) == "2025-09-08"


def test_resolves_via_literal_bare_code_aomine_style() -> None:
    """青嶺不動産型: 「M0N」が括弧無しで備考に前置きされる書式。"""
    rows = [
        _row("プロジェクトキックオフ実施", "M01 キックオフ会議（クライアント窓口: 前田）", "2025-08-06", "2025-08-06"),
        _row("中間報告会実施", "M02 中間報告会議（クライアント窓口: 前田）", "2025-08-26", "2025-08-26"),
    ]
    assert resolve_milestone_date(rows, "M01", TERM_REGISTRY) == "2025-08-06"
    assert resolve_milestone_date(rows, "M02", TERM_REGISTRY) == "2025-08-26"


def test_resolves_via_semantic_fallback_when_no_ms_code_present() -> None:
    """みなみ野型: M0N表記が一切無く、キーワードのみで意味的に解決する必要がある案件。"""
    rows = [
        _row("キックオフ実施・開始合意", "CP1：キックオフ完了", "2025-04-03", "2025-04-03"),
        _row("中間レビュー実施", "CP3：中間レビュー承認", "2025-04-24", "2025-04-24"),
        _row("最終成果物提出・最終報告会", "CP6：最終成果物提出・最終報告会完了", "2025-05-15", "2025-05-15"),
    ]
    assert resolve_milestone_date(rows, "M01", TERM_REGISTRY) == "2025-04-03"
    assert resolve_milestone_date(rows, "M02", TERM_REGISTRY) == "2025-04-24"
    # FRのexpansionは「最終報告書」（文書名）なので「最終報告」語義グループへフォールバックする
    assert resolve_milestone_date(rows, "FR", TERM_REGISTRY) == "2025-05-15"


def test_literal_code_takes_priority_over_semantic_meaning_shirane_style() -> None:
    """白峰型: M02が他案件と異なり「分析方針レビュー」を指す独自付番。
    文字通りの(M02)一致が、term_registryの「中間報告」意味付けより優先されること
    （意味的に解決すると誤って別行=中間レビュー実施（M03）を指してしまう）。"""
    rows = [
        _row("キックオフ実施（M01）", "", "2025-05-13", "2025-05-13"),
        _row("分析方針レビュー実施（M02）", "マイルストーンMS3", "2025-05-27", "2025-05-27"),
        _row("中間レビュー実施（M03）", "マイルストーンMS5", "2025-06-17", "2025-06-17"),
        _row("最終レビュー実施（M04）", "マイルストーンMS8", "2025-07-15", "2025-07-15"),
    ]
    assert resolve_milestone_date(rows, "M02", TERM_REGISTRY) == "2025-05-27"
    assert resolve_milestone_date(rows, "M03", TERM_REGISTRY) == "2025-06-17"


def test_ambiguous_literal_match_returns_none_without_semantic_fallback() -> None:
    """文字通りの一致が複数の異なる日付にヒットする場合はNone（意味的一致へは逃げない）。"""
    rows = [
        _row("キックオフ実施（M01）", "", "2025-05-13", "2025-05-13"),
        _row("再キックオフ実施（M01）", "スコープ変更のため再実施", "2025-06-01", "2025-06-01"),
    ]
    assert resolve_milestone_date(rows, "M01", TERM_REGISTRY) is None


def test_ambiguous_semantic_match_returns_none() -> None:
    """意味的一致が複数の異なる日付にヒットする場合もNoneに倒す。"""
    rows = [
        _row("キックオフ実施・開始合意", "", "2025-04-03", "2025-04-03"),
        _row("再キックオフ実施", "スコープ変更のため", "2025-04-10", "2025-04-10"),
    ]
    assert resolve_milestone_date(rows, "M01", TERM_REGISTRY) is None


def test_unresolvable_code_returns_none() -> None:
    rows = [_row("キックオフ実施（M01）", "", "2025-05-13", "2025-05-13")]
    assert resolve_milestone_date(rows, "M99", TERM_REGISTRY) is None


def test_prep_tasks_are_not_confused_with_the_actual_event() -> None:
    """「〜資料作成」「〜ドラフト作成」等の準備タスクは、実際のイベント行と混同しない
    （準備タスクにも同じキーワードが含まれるため、"実施"接尾を要求して区別する）。"""
    rows = [
        _row("中間報告資料作成", "", "2025-08-21", "2025-08-25"),
        _row("中間報告会実施", "MS4関連", "2025-08-26", "2025-08-26"),
    ]
    assert resolve_milestone_date_by_group(rows, "中間報告") == "2025-08-26"


def test_detect_milestone_group_from_question_keywords() -> None:
    assert detect_milestone_group("中間報告会または中間レビューが2025年7月1日以前に実施された案件") == "中間報告"
    assert detect_milestone_group("キックオフが実施された案件") == "キックオフ"
    assert detect_milestone_group("最終報告会が実施された案件") == "最終報告"
    assert detect_milestone_group("契約金額が最大の案件") is None
