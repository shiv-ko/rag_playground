"""Analyze coverage of Excel and Office style questions by current artifacts."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
DOCS = ROOT / "docs"

QUESTION_LABELS = DOCS / "question_labels.csv"
EXCEL_CSV = ARTIFACTS / "excel_question_coverage.csv"
OFFICE_CSV = ARTIFACTS / "office_style_coverage.csv"
EXCEL_MD = DOCS / "excel_question_coverage.md"
OFFICE_MD = DOCS / "office_style_coverage.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_questions() -> list[dict[str, str]]:
    with QUESTION_LABELS.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def norm(text: str | None) -> str:
    return (text or "").replace(" ", "").replace("　", "")


def project_aliases() -> dict[str, list[str]]:
    projects = read_json(ARTIFACTS / "project_registry.json")
    aliases: dict[str, list[str]] = {}
    for project in projects:
        values = set(project.get("aliases") or [])
        values.add(project["project_name"])
        aliases[project["project_name"]] = sorted(values, key=len, reverse=True)
    return aliases


def match_project(question: str, aliases: dict[str, list[str]]) -> str | None:
    q = norm(question)
    for project, values in aliases.items():
        for alias in values:
            if norm(alias) and norm(alias) in q:
                return project
    return None


def has_label(row: dict[str, str], label: str) -> bool:
    labels = [row.get("primary_type", "")]
    labels.extend((row.get("secondary_types") or "").split(";"))
    return label in labels


def excel_relevant(row: dict[str, str]) -> bool:
    return has_label(row, "spreadsheet_state") or has_label(row, "spreadsheet_calc")


def office_relevant(row: dict[str, str]) -> bool:
    return row.get("primary_type") == "office_style"


def summarize_status(rows: list[dict[str, Any]]) -> list[str]:
    counts = Counter(row["status"] for row in rows)
    order = ["covered_artifact", "partial", "not_covered"]
    return [f"- `{status}`: {counts.get(status, 0)}" for status in order]


def excel_coverage() -> list[dict[str, Any]]:
    aliases = project_aliases()
    questions = [row for row in read_questions() if excel_relevant(row)]
    schedule_tasks = read_jsonl(ARTIFACTS / "schedule_tasks.jsonl")
    train_context = read_jsonl(ARTIFACTS / "train_xlsx_highlight_blocks.jsonl")
    train_sheets = read_jsonl(ARTIFACTS / "train_xlsx_sheets.jsonl")
    formulas = read_jsonl(ARTIFACTS / "train_xlsx_formula_cells.jsonl")

    schedule_projects = {row["project_name"] for row in schedule_tasks}
    train_highlight_projects = {row["project_name"] for row in train_context}
    train_sheet_projects = {row["project_name"] for row in train_sheets}
    formula_projects = {row["project_name"] for row in formulas}

    rows: list[dict[str, Any]] = []
    for q in questions:
        question = q["question"]
        project = match_project(question, aliases)
        q_norm = norm(question)
        evidence: list[str] = []
        status = "not_covered"
        needed = "unknown"

        if "ページ" in question and any(ext in question for ext in ["docx", "pptx", "報告資料", "最終報告"]):
            needed = "page_layout"
            status = "not_covered"
        elif "比較" in question and ("r1" in question or "r2" in question or "old" in question):
            needed = "spreadsheet_diff"
            if project in schedule_projects:
                status = "partial"
                evidence.append("schedule_tasks")
        elif "スケジュール" in question or "WBS" in question or "タスク" in question or "第何週" in question:
            needed = "schedule_tasks"
            if project in schedule_projects:
                status = "covered_artifact"
                evidence.append("schedule_tasks")
            else:
                status = "not_covered"
        elif "train.xlsx" in question:
            if "ハイライト" in question or "黄色" in question or "青色" in question:
                needed = "train_xlsx_highlight_context"
                if project in train_highlight_projects:
                    status = "covered_artifact"
                    evidence.append("train_xlsx_highlight_context")
                elif project in train_sheet_projects:
                    status = "partial"
                    evidence.append("train_xlsx_sheets")
            elif "係数" in question or "回帰" in question or "予測" in question:
                needed = "train_xlsx_formula_cells"
                if project in formula_projects:
                    status = "partial"
                    evidence.append("train_xlsx_formula_cells")
            elif "Pivot" in question or "フィルター" in question or "グラフ" in question or "ヒストグラム" in question:
                needed = "train_xlsx_visual_or_pivot"
                if project in train_sheet_projects:
                    status = "partial"
                    evidence.append("train_xlsx_sheets")
                    if project in train_highlight_projects:
                        evidence.append("train_xlsx_highlight_context")
            elif project in train_sheet_projects:
                needed = "train_xlsx"
                status = "partial"
                evidence.append("train_xlsx_sheets")
        elif any(word in q_norm for word in ["train.csv", "分析対象データ", "顧客データ", "欠損値"]):
            needed = "raw_table_calc"
            status = "not_covered"
        elif q.get("source_section") and "02.計画" in q["source_section"] and project in schedule_projects:
            needed = "schedule_tasks"
            status = "partial"
            evidence.append("schedule_tasks")

        rows.append(
            {
                "split": q["split"],
                "index": q["index"],
                "project_name": project or "",
                "question": question,
                "primary_type": q["primary_type"],
                "status": status,
                "needed_artifact": needed,
                "evidence_artifacts": ";".join(evidence),
                "notes": coverage_note(status, needed, question),
            }
        )
    return rows


def coverage_note(status: str, needed: str, question: str) -> str:
    if status == "covered_artifact":
        return "current artifact can provide direct candidates; answer logic still needed"
    if needed in {"train_xlsx_visual_or_pivot", "train_xlsx_formula_cells"}:
        return "metadata exists, but chart/pivot/formula interpretation is still needed"
    if needed == "raw_table_calc":
        return "requires CSV/table calculation engine outside current Excel artifacts"
    if "ページ" in question:
        return "requires page-level document extraction"
    return "artifact missing or insufficient"


def office_coverage() -> list[dict[str, Any]]:
    aliases = project_aliases()
    questions = [row for row in read_questions() if office_relevant(row)]
    marks = read_jsonl(ARTIFACTS / "office_marks.jsonl")
    by_project: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for mark in marks:
        by_project[mark.get("project_name")].append(mark)

    rows: list[dict[str, Any]] = []
    for q in questions:
        question = q["question"]
        project = match_project(question, aliases)
        project_marks = by_project.get(project, []) if project else marks
        condition = office_condition(question)
        candidates = [mark for mark in project_marks if mark_matches_condition(mark, condition)]
        status = "not_covered"
        if candidates and condition != "comment":
            status = "covered_artifact"
        elif project_marks and condition not in {"comment", "page", "graph_value"}:
            status = "partial"
        elif "PDF" in question or "pdf" in question:
            status = "not_covered"

        rows.append(
            {
                "split": q["split"],
                "index": q["index"],
                "project_name": project or "",
                "question": question,
                "condition": condition,
                "status": status,
                "candidate_count": len(candidates),
                "sample_text": " / ".join(str(mark.get("text", "")).strip() for mark in candidates[:3]),
                "notes": office_note(status, condition),
            }
        )
    return rows


def office_condition(question: str) -> str:
    if "コメント" in question:
        return "comment"
    if "ページ" in question:
        return "page"
    if "グラフ" in question or "折れ線" in question:
        return "graph_value"
    if "黄色" in question and ("赤字" in question or "RED" in question):
        return "yellow_and_red"
    if "黄色" in question or "ハイライト" in question or "マーカー" in question:
        return "highlight"
    if "太字" in question and "下線" in question and "イタリック" in question:
        return "bold_underline_italic"
    if "太字" in question:
        return "bold"
    if "赤" in question:
        return "red"
    return "style"


def is_red(value: Any) -> bool:
    text = str(value or "").upper()
    return text.startswith("FF") or text in {"C00000", "FF0000", "RED"}


def mark_matches_condition(mark: dict[str, Any], condition: str) -> bool:
    if condition == "bold":
        return bool(mark.get("bold"))
    if condition == "bold_underline_italic":
        return bool(mark.get("bold") and mark.get("underline") and mark.get("italic"))
    if condition == "red":
        return is_red(mark.get("font_color")) or is_red(mark.get("fill_color"))
    if condition == "highlight":
        return bool(mark.get("highlight_color") or mark.get("fill_color"))
    if condition == "yellow_and_red":
        return bool(mark.get("highlight_color") or mark.get("fill_color")) and is_red(mark.get("font_color"))
    if condition in {"comment", "page", "graph_value"}:
        return False
    return any(mark.get(key) for key in ["bold", "italic", "underline", "font_color", "fill_color", "highlight_color"])


def office_note(status: str, condition: str) -> str:
    if condition == "comment":
        return "comments are not extracted by current office_marks artifact"
    if condition == "page":
        return "page number needs PDF/DOCX layout extraction"
    if condition == "graph_value":
        return "graph numeric reading needs chart/VLM extraction"
    if status == "covered_artifact":
        return "style-conditioned candidates exist"
    return "office marks exist but exact condition may need normalization"


def write_excel_report(rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Excel系設問カバレッジ",
        "",
        "## 集計",
        "",
        *summarize_status(rows),
        "",
        "## covered_artifact",
        "",
        "| split | index | project | needed | evidence | question |",
        "|---|---:|---|---|---|---|",
    ]
    for row in rows:
        if row["status"] != "covered_artifact":
            continue
        lines.append(f"| {row['split']} | {row['index']} | {row['project_name']} | {row['needed_artifact']} | {row['evidence_artifacts']} | {row['question']} |")
    lines.extend(["", "## partial / not_covered", "", "| status | split | index | needed | note | question |", "|---|---|---:|---|---|---|"])
    for row in rows:
        if row["status"] == "covered_artifact":
            continue
        lines.append(f"| {row['status']} | {row['split']} | {row['index']} | {row['needed_artifact']} | {row['notes']} | {row['question']} |")
    EXCEL_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_office_report(rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Office書式設問カバレッジ",
        "",
        "## 集計",
        "",
        *summarize_status(rows),
        "",
        "## covered_artifact",
        "",
        "| split | index | project | condition | candidates | sample | question |",
        "|---|---:|---|---|---:|---|---|",
    ]
    for row in rows:
        if row["status"] != "covered_artifact":
            continue
        lines.append(f"| {row['split']} | {row['index']} | {row['project_name']} | {row['condition']} | {row['candidate_count']} | {row['sample_text']} | {row['question']} |")
    lines.extend(["", "## partial / not_covered", "", "| status | split | index | condition | note | question |", "|---|---|---:|---|---|---|"])
    for row in rows:
        if row["status"] == "covered_artifact":
            continue
        lines.append(f"| {row['status']} | {row['split']} | {row['index']} | {row['condition']} | {row['notes']} | {row['question']} |")
    OFFICE_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    excel_rows = excel_coverage()
    office_rows = office_coverage()
    write_csv(
        EXCEL_CSV,
        excel_rows,
        ["split", "index", "project_name", "primary_type", "status", "needed_artifact", "evidence_artifacts", "notes", "question"],
    )
    write_csv(
        OFFICE_CSV,
        office_rows,
        ["split", "index", "project_name", "condition", "status", "candidate_count", "sample_text", "notes", "question"],
    )
    write_excel_report(excel_rows)
    write_office_report(office_rows)
    print(f"excel questions={len(excel_rows)}")
    print(Counter(row["status"] for row in excel_rows))
    print(f"office questions={len(office_rows)}")
    print(Counter(row["status"] for row in office_rows))


if __name__ == "__main__":
    main()
