"""スケジュールタスクからマイルストーン（M0N/FR等のコード）に対応する日付を解決する。

案件ごとにマイルストーン表記がバラバラ（(M0N)付きの案件、素のM0Nを備考に前置きする案件、
M0N表記が一切無くキーワードのみの案件、さらに白峰のようにM番号の意味付け自体が他案件と
ずれている案件がある）ため、以下の優先順で解決する:

  1) 質問中のコード（M01, FR等）がスケジュール内に文字通り出現する行を最優先で使う。
     白峰のようにM番号の意味付けが他案件とずれているケースでも、書かれている通りの
     コードを信じるのが最も安全なため。
  2) 文字通りの一致が無い場合のみ、term_registryの語義（キックオフ/中間報告/最終報告）から
     一般的な業務イベント語彙（会議実施・レビュー実施等）で意味的に一致する行を探す。

複数の異なる日付に曖昧一致する場合はNoneを返す（誤答よりMissingを優先する競技規約に従う）。
"""
from __future__ import annotations

import re

# 案件ごとに「〜会議実施」「〜会実施」「〜実施」のように表記の揺れがあるため、
# 会議/会の有無を許容する（キックオフ会議実施/キックオフ実施のいずれにも一致させる）。
# 「最終」グループは複数のイベント（最終報告会・最終成果物提出・検収会）が別日程になりうる
# 案件があり、その場合は意図的に複数日付=曖昧としてNoneに倒す（誤答よりMissing優先）。
_MILESTONE_EVENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "キックオフ": (r"キックオフ(?:会議|会)?実施",),
    "中間報告": (r"中間報告(?:会議|会)?実施", r"中間レビュー(?:会議|会)?実施"),
    "最終報告": (
        r"最終報告(?:会議|会)?実施",
        r"最終レビュー(?:会議|会)?実施",
        r"最終成果物提出",
        r"検収会実施",
    ),
}

# term_registryのexpansionは一般語義（キックオフ/中間報告/最終報告）と一致するものが多いが、
# FRのように「最終報告書」という文書名になっている場合はイベント語義へフォールバックする。
MILESTONE_EXPANSION_TO_GROUP: dict[str, str] = {
    "キックオフ": "キックオフ",
    "中間報告": "中間報告",
    "最終報告": "最終報告",
    "最終報告書": "最終報告",
}

# Q15型（横断リスト）の質問文キーワードから対象グループを判定するための検出語。
_GROUP_DETECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "キックオフ": ("キックオフ",),
    "中間報告": ("中間報告", "中間レビュー"),
    "最終報告": ("最終報告", "最終レビュー", "検収"),
}


def _row_text(row: dict) -> str:
    values = row.get("values", {})
    return f"{values.get('タスク名') or ''} {values.get('備考') or ''}"


def _row_date(row: dict) -> str | None:
    values = row.get("values", {})
    raw = values.get("終了日") or values.get("開始日")
    if not raw:
        return None
    return str(raw).split("T")[0]


def _resolve_from_rows(rows: list[dict]) -> str | None:
    dates = {d for d in (_row_date(r) for r in rows) if d}
    if len(dates) != 1:
        return None
    return next(iter(dates))


def _literal_code_matches(schedule_rows: list[dict], code: str) -> list[dict]:
    # 前後がアルファベット・数字でなければ一致とみなす（Japaneseの\wはUnicode文字も
    # 含むため\bは日本語文字との境界で機能しない。括弧付き「（M01）」・素の「M01 」の
    # 両方の書式に対応するための境界判定）。
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])")
    return [row for row in schedule_rows if pattern.search(_row_text(row))]


def resolve_milestone_date_by_group(schedule_rows: list[dict], group: str) -> str | None:
    """業務イベント語義グループ（キックオフ/中間報告/最終報告）で一致する行の日付を解決する。"""
    patterns = _MILESTONE_EVENT_PATTERNS.get(group)
    if not patterns:
        return None
    matched = [
        row for row in schedule_rows
        if any(re.search(p, _row_text(row)) for p in patterns)
    ]
    return _resolve_from_rows(matched)


def detect_milestone_group(question: str) -> str | None:
    """質問文中のキーワードから対象のマイルストーン語義グループを判定する（Q15型で使用）。"""
    for group, keywords in _GROUP_DETECTION_KEYWORDS.items():
        if any(k in question for k in keywords):
            return group
    return None


def resolve_milestone_date(
    schedule_rows: list[dict],
    milestone_code: str,
    term_registry: list[dict],
) -> str | None:
    """質問文中のマイルストーンコード（M01, FR等）に対応する日付を解決する（Q16型で使用）。

    1) スケジュール内に文字通り`milestone_code`が出現する行を最優先する。
    2) 文字通りの一致が無い場合のみterm_registryの語義から意味的に一致する行を探す。
    """
    literal_rows = _literal_code_matches(schedule_rows, milestone_code)
    if literal_rows:
        # 文字通りの一致があるのに日付が割れている場合は曖昧。意味的一致へは
        # フォールバックしない（意味的一致は白峰のような独自付番案件では
        # 別のイベントを指してしまうため、誤答より安全側のMissingを優先する）。
        return _resolve_from_rows(literal_rows)

    expansion = next(
        (t.get("expansion") for t in term_registry if t.get("term") == milestone_code),
        None,
    )
    if expansion is None:
        return None
    group = MILESTONE_EXPANSION_TO_GROUP.get(expansion)
    if group is None:
        return None
    return resolve_milestone_date_by_group(schedule_rows, group)
