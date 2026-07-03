"""Build candidate answers from extracted schedule artifacts for high-value checks."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCHEDULE_TASKS = ROOT / "artifacts" / "schedule_tasks.jsonl"
OUT = ROOT / "docs" / "schedule_query_candidates.md"


def load_rows() -> list[dict[str, Any]]:
    return [json.loads(line) for line in SCHEDULE_TASKS.read_text(encoding="utf-8").splitlines() if line.strip()]


def rows_for(rows: list[dict[str, Any]], project_hint: str) -> list[dict[str, Any]]:
    return [row for row in rows if project_hint in row["project_name"]]


def value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row["values"]:
            return row["values"][key]
    return None


def parse_dt(value_: Any) -> datetime | None:
    if not value_:
        return None
    if isinstance(value_, str):
        try:
            return datetime.fromisoformat(value_)
        except ValueError:
            return None
    return None


def unique_by_task(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for row in rows:
        task_id = value(row, "タスクID")
        sheet = row.get("sheet_name")
        key = (row["project_name"], row["file_name"], sheet, task_id, value(row, "タスク名"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def fmt_task(row: dict[str, Any]) -> str:
    vals = row["values"]
    return (
        f"`{value(row, 'タスクID')}`: {value(row, 'タスク名')} "
        f"(担当: {value(row, '担当者')}, 開始: {value(row, '開始日')}, 終了: {value(row, '終了日')})"
    )


def main() -> None:
    rows = load_rows()
    lines = [
        "# Schedule Query Candidates",
        "",
        "`artifacts/schedule_tasks.jsonl` から、現時点で直接候補を出せる質問の根拠を整理する。これは提出回答ではなく、抽出器の有効性確認用。",
        "",
    ]

    # valid 20
    aym = rows_for(rows, "青葉与信")
    phase_rows = unique_by_task(
        [
            row
            for row in aym
            if "探索的分析・仮説整理" in str(value(row, "フェーズ"))
            and value(row, "タスクID")
        ]
    )
    lines.extend(
        [
            "## valid 20: AYMのPLで探索的分析・仮説整理フェーズのタスクID",
            "",
            f"候補: {', '.join(str(value(row, 'タスクID')) for row in phase_rows)}",
            "",
            "根拠:",
        ]
    )
    lines.extend(f"- {fmt_task(row)}" for row in phase_rows)
    lines.append("")

    # test 41
    aobm = rows_for(rows, "青葉バイオ")
    kato_rows = unique_by_task(
        [
            row
            for row in aobm
            if "加藤" in str(value(row, "担当者"))
            and value(row, "タスクID")
        ]
    )
    lines.extend(
        [
            "## test 41: AOBMのPLANで加藤さんが担当者に含まれるタスクID数",
            "",
            f"候補: {len(kato_rows)}件",
            "",
            "根拠:",
        ]
    )
    lines.extend(f"- {fmt_task(row)}" for row in kato_rows)
    lines.append("")

    # test 89
    kss = rows_for(rows, "京橋")
    phase6 = unique_by_task(
        [
            row
            for row in kss
            if value(row, "フェーズNo.", "フェーズNo") == 6
            and value(row, "タスクID")
        ]
    )
    phase6_sorted = sorted(phase6, key=lambda row: parse_dt(value(row, "開始日")) or datetime.min)
    latest_start = parse_dt(value(phase6_sorted[-1], "開始日")) if phase6_sorted else None
    latest_rows = [
        row
        for row in phase6_sorted
        if parse_dt(value(row, "開始日")) == latest_start
    ]
    lines.extend(
        [
            "## test 89: 京橋信用ソリューションズのフェーズNo6で最後に開始するタスク名",
            "",
            f"候補: {', '.join(str(value(row, 'タスク名')) for row in latest_rows)}",
            "",
            "根拠:",
        ]
    )
    lines.extend(f"- {fmt_task(row)}" for row in phase6_sorted)
    lines.append("")

    # test 90
    aoshio = rows_for(rows, "青潮")
    buffer_rows_raw = [
        row
        for row in aoshio
        if ("バッファ" in str(value(row, "種別")) or "バッファ" in str(value(row, "タスク名")))
        and value(row, "タスクID")
    ]
    # The workbook may have display/calculation duplicate sheets. Keep one row per task id,
    # preferring the largest hours value when duplicate task IDs differ.
    by_task: dict[str, dict[str, Any]] = {}
    for row in buffer_rows_raw:
        task_id = str(value(row, "タスクID"))
        hours = value(row, "工数(h)", "工数", "想定工数")
        prev = by_task.get(task_id)
        prev_hours = value(prev, "工数(h)", "工数", "想定工数") if prev else None
        if prev is None or (hours or 0) > (prev_hours or 0):
            by_task[task_id] = row
    buffer_rows = [by_task[key] for key in sorted(by_task)]
    total_hours = sum(float(value(row, "工数(h)", "工数", "想定工数") or 0) for row in buffer_rows)
    lines.extend(
        [
            "## test 90: 青潮モビリティサービスのバッファとして使用した工数合計",
            "",
            f"候補: {total_hours:g}時間",
            "",
            "根拠:",
        ]
    )
    lines.extend(f"- {fmt_task(row)} / 工数: {value(row, '工数(h)', '工数', '想定工数')}" for row in buffer_rows)
    lines.append("")

    # test 94 remains partial
    minamino = rows_for(rows, "蒼樹")
    ms3_rows = unique_by_task(
        [
            row
            for row in minamino
            if "MS3" in str(row["values"])
            and value(row, "タスクID")
        ]
    )
    lines.extend(
        [
            "## test 94: MINAMINOのMS3紐づきタスクとビジネスアナリスト",
            "",
            "状態: partial。MS3関連タスク候補は取れるが、ビジネスアナリストが誰かを解決する人員/役割レジストリが未作成。",
            "",
            "MS3関連候補:",
        ]
    )
    lines.extend(f"- {fmt_task(row)} / 備考: {value(row, '備考')}" for row in ms3_rows)
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
