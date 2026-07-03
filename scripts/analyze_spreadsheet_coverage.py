"""Analyze which labeled spreadsheet questions are covered by extracted artifacts."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "docs" / "question_labels.csv"
SCHEDULE_TASKS = ROOT / "artifacts" / "schedule_tasks.jsonl"
FAILURES = ROOT / "artifacts" / "spreadsheet_failures.jsonl"
OUT_CSV = ROOT / "artifacts" / "spreadsheet_question_coverage.csv"
OUT_MD = ROOT / "docs" / "spreadsheet_coverage.md"


PROJECT_HINTS = {
    "京橋信用ソリューションズ株式会社": ("京橋", "京ソ", "KSS"),
    "医療法人社団 恒一会 かえで総合病院": ("恒一", "かえで"),
    "医療法人社団 蒼樹会 みなみ野女性医療センター": ("蒼樹", "みなみ野", "MINAMINO"),
    "医療法人社団 蒼泉会 ひがし丘総合病院": ("蒼泉", "ひがし丘"),
    "株式会社東都人材プラットフォーム": ("東都", "TOTO"),
    "株式会社青嶺不動産アセットマネジメント": ("青嶺", "AOMINE"),
    "株式会社青潮モビリティサービス": ("青潮", "AOSHIO"),
    "株式会社青葉バイオメディカル機器": ("青葉バイオ", "AOBM"),
    "白峰信用リスク評価株式会社": ("白峰", "SHR"),
    "青葉与信マネジメント株式会社": ("青葉与信", "AYM"),
}


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def infer_project(question: str) -> str | None:
    for project, hints in PROJECT_HINTS.items():
        if any(hint in question for hint in hints):
            return project
    return None


def wanted_schedule(question: str) -> bool:
    return any(word in question for word in ("スケジュール", "WBS", "PLAN", "PL", "タスク", "マイルストーン"))


def direct_schedule_artifact_question(question: str) -> bool:
    if any(word in question for word in ("報告資料", "最終報告", "提案書", ".docx", ".pptx", ".pdf")):
        return "スケジュール.xlsx" in question or "スケジュール_r" in question
    return any(word in question for word in ("スケジュール.xlsx", "スケジュール_r", "WBSシート", "PLAN", "PL"))


def wanted_train_xlsx(question: str) -> bool:
    return "train.xlsx" in question or "Sheet" in question or "Pivot" in question or "ヒストグラム" in question


def wanted_color(question: str) -> bool:
    return any(word in question for word in ("黄色", "青色", "オレンジ", "ハイライト"))


def wanted_diff(question: str) -> bool:
    return any(word in question for word in ("比較", "変更", "修正", "old", "_r1", "_r2", "最新版"))


def classify_coverage(question: str, project: str | None, extracted_projects: set[str], encrypted_projects: set[str]) -> tuple[str, str]:
    if wanted_train_xlsx(question):
        return "not_covered", "train.xlsx extraction is not implemented yet"
    if not wanted_schedule(question):
        return "not_covered", "not a schedule/WBS spreadsheet question"
    if not direct_schedule_artifact_question(question):
        return "partial", "schedule rows may help, but the requested source is not the schedule workbook"
    if any(word in question for word in ("ビジネスアナリスト", "データエンジニア", "役割")):
        return "partial", "schedule rows extracted, but role/person registry is required"
    if project is None:
        return "partial", "project could not be inferred by heuristic"
    if project in encrypted_projects:
        return "blocked", "schedule workbook is encrypted"
    if project not in extracted_projects:
        return "not_covered", "no extracted schedule rows for inferred project"
    if wanted_diff(question):
        return "partial", "schedule rows extracted, but diff logic is not implemented"
    if wanted_color(question):
        return "partial", "schedule rows and row colors extracted; answer logic still needed"
    return "covered_artifact", "schedule rows extracted; query-specific computation still needed"


def main() -> None:
    labels = load_csv(LABELS)
    schedule_rows = load_jsonl(SCHEDULE_TASKS)
    failures = load_jsonl(FAILURES)

    extracted_projects = {row["project_name"] for row in schedule_rows}
    encrypted_projects = {
        project
        for failure in failures
        for project, hints in PROJECT_HINTS.items()
        if any(hint in failure["source_path"] for hint in hints) or project in failure["source_path"]
    }

    target_rows: list[dict[str, str]] = []
    for row in labels:
        labels_joined = ";".join([row["primary_type"], row["secondary_types"]])
        if "spreadsheet_state" not in labels_joined and row["source_section"] != "02.計画":
            continue
        question = row["question"]
        project = infer_project(question)
        status, reason = classify_coverage(question, project, extracted_projects, encrypted_projects)
        target_rows.append(
            {
                "split": row["split"],
                "index": row["index"],
                "primary_type": row["primary_type"],
                "project_name": project or "",
                "coverage_status": status,
                "coverage_reason": reason,
                "question": question,
            }
        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "split",
                "index",
                "primary_type",
                "project_name",
                "coverage_status",
                "coverage_reason",
                "question",
            ],
        )
        writer.writeheader()
        writer.writerows(target_rows)

    status_counts = Counter(row["coverage_status"] for row in target_rows)
    split_counts = Counter((row["split"], row["coverage_status"]) for row in target_rows)

    lines = [
        "# Spreadsheet Coverage",
        "",
        "`scripts/analyze_spreadsheet_coverage.py` による初期カバレッジ分析。回答生成ではなく、抽出済みartifactでどの質問に近づけるかを判定するためのメモ。",
        "",
        "## Summary",
        "",
        "| status | count |",
        "|---|---:|",
    ]
    for status, count in status_counts.most_common():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(["", "## By Split", "", "| split | status | count |", "|---|---|---:|"])
    for (split, status), count in sorted(split_counts.items()):
        lines.append(f"| `{split}` | `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Questions",
            "",
            "| split | index | status | project | reason | question |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for row in target_rows:
        question = row["question"].replace("|", "\\|")
        project = row["project_name"].replace("|", "\\|")
        reason = row["coverage_reason"].replace("|", "\\|")
        lines.append(
            f"| `{row['split']}` | {row['index']} | `{row['coverage_status']}` | {project} | {reason} | {question} |"
        )

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")
    print(dict(status_counts))


if __name__ == "__main__":
    main()
