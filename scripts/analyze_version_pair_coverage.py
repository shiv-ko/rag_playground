"""Map version-diff labeled questions to generated version pairs."""
from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "docs" / "question_labels.csv"
PAIRS = ROOT / "artifacts" / "version_pairs.jsonl"
OUT_CSV = ROOT / "artifacts" / "version_pair_coverage.csv"
OUT_MD = ROOT / "docs" / "version_pair_coverage.md"


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


DOC_TYPE_HINTS = {
    "proposal": ("提案書", "PP"),
    "final_report": ("最終報告", "最終報告資料", "最終報告書", "FR"),
    "notebook": ("ipynb", "notebook", "Notebook", "01_eda"),
    "plan": ("スケジュール", "PLAN", "PL"),
    "contract": ("契約書", "CT"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def infer_project(question: str) -> str | None:
    for project, hints in PROJECT_HINTS.items():
        if any(hint in question for hint in hints):
            return project
    return None


def infer_doc_type(question: str) -> str | None:
    for doc_type, hints in DOC_TYPE_HINTS.items():
        if any(hint in question for hint in hints):
            return doc_type
    return None


def requested_tags(question: str) -> tuple[str | None, str | None]:
    lower = question.lower()
    old_tag = None
    new_tag = None
    for tag in ("old", "v1", "v2", "v3", "r1", "r2", "final"):
        if tag in lower:
            if old_tag is None:
                old_tag = tag
            else:
                new_tag = tag
    if "旧版" in question:
        old_tag = old_tag or "old"
    if "最新版" in question:
        new_tag = new_tag or None
    return old_tag, new_tag


def is_actual_diff_request(question: str) -> bool:
    return any(word in question for word in ("比較", "更新内容", "変更内容", "変更点", "修正された", "旧版と最新版"))


def find_pair(question: str, pairs: list[dict]) -> tuple[str, str, dict | None]:
    if not is_actual_diff_request(question):
        return "not_diff", "question uses version-like terms but is not a file diff request", None
    project = infer_project(question)
    doc_type = infer_doc_type(question)
    old_tag, new_tag = requested_tags(question)
    candidates = pairs
    if project:
        candidates = [pair for pair in candidates if pair["project_name"] == project]
    if doc_type:
        candidates = [pair for pair in candidates if pair["document_type"] == doc_type]
    if old_tag:
        candidates = [pair for pair in candidates if pair["old_version_tag"] == old_tag]
    if new_tag:
        candidates = [pair for pair in candidates if pair["new_version_tag"] == new_tag]
    if len(candidates) == 1:
        return "pair_found", "unique version pair found", candidates[0]
    if candidates:
        return "ambiguous", f"{len(candidates)} candidate pairs found", candidates[0]
    return "not_found", "no matching version pair found", None


def main() -> None:
    labels = read_csv(LABELS)
    pairs = read_jsonl(PAIRS)
    rows = []
    for row in labels:
        label_text = ";".join([row["primary_type"], row["secondary_types"]])
        if "version_diff" not in label_text:
            continue
        status, reason, pair = find_pair(row["question"], pairs)
        rows.append(
            {
                "split": row["split"],
                "index": row["index"],
                "status": status,
                "reason": reason,
                "project_name": pair["project_name"] if pair else (infer_project(row["question"]) or ""),
                "document_type": pair["document_type"] if pair else (infer_doc_type(row["question"]) or ""),
                "old_path": pair["old_path"] if pair else "",
                "new_path": pair["new_path"] if pair else "",
                "question": row["question"],
            }
        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Version Pair Coverage",
        "",
        "`scripts/analyze_version_pair_coverage.py` による比較設問と `version_pairs.jsonl` の対応表。",
        "",
        "| split | index | status | project | type | reason | question |",
        "|---|---:|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['split']}` | {row['index']} | `{row['status']}` | {row['project_name']} | `{row['document_type']}` | {row['reason']} | {row['question'].replace('|', '\\|')} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_CSV.relative_to(ROOT)} ({len(rows)} rows)")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
