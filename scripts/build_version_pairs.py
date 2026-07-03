"""Build old/new document version pair candidates from document_registry."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
DOC_REGISTRY = ARTIFACTS / "document_registry.jsonl"
OUT_JSONL = ARTIFACTS / "version_pairs.jsonl"
OUT_MD = ROOT / "docs" / "version_pairs.md"


VERSION_ORDER = {
    "old": 0,
    "draft": 1,
    "r1": 2,
    "v1": 2,
    "r2": 3,
    "v2": 3,
    "v3": 4,
    "final": 5,
    None: 99,
}

PAIRABLE_TYPES = {
    "proposal",
    "final_report",
    "notebook",
    "plan",
    "contract",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_title(row: dict[str, Any]) -> str:
    stem = row["stem"]
    project = row.get("project_name") or ""
    title = stem
    if project and title.startswith(project):
        title = title[len(project) :]
    title = title.lower()
    title = title.replace("＿", "_")
    title = re.sub(r"(^|[_\-\s])old($|[_\-\s])", "_", title)
    title = re.sub(r"(^|[_\-\s])(v1|v2|v3|r1|r2|final|draft)($|[_\-\s])", "_", title)
    title = re.sub(r"old$", "", title)
    title = re.sub(r"_(v1|v2|v3|r1|r2|final|draft)$", "", title)
    title = re.sub(r"(v1|v2|v3|r1|r2|final|draft)$", "", title)
    title = title.replace("_", "")
    title = title.replace("-", "")
    title = title.replace(" ", "")
    title = title.strip()
    if not title:
        title = row["document_type"]
    return title


def version_order(row: dict[str, Any]) -> int:
    return VERSION_ORDER.get(row.get("version_tag"), 99)


def is_pairable(row: dict[str, Any]) -> bool:
    if row.get("is_noise_candidate"):
        return False
    if row.get("project_name") is None:
        return False
    if row.get("document_type") not in PAIRABLE_TYPES:
        return False
    return row.get("extension") in {".pptx", ".xlsx", ".ipynb", ".docx", ".pdf"}


def pair_confidence(old: dict[str, Any], new: dict[str, Any], group_size: int) -> tuple[str, str]:
    if old["document_type"] != new["document_type"]:
        return "low", "different document_type"
    if old["extension"] != new["extension"]:
        return "medium", "same normalized title but different extension"
    old_tag = old.get("version_tag")
    new_tag = new.get("version_tag")
    if old_tag and new_tag:
        return "high", f"ordered explicit version tags: {old_tag}->{new_tag}"
    if old_tag and new_tag is None:
        return "high", f"explicit old version to untagged latest candidate: {old_tag}->untagged"
    if group_size == 2:
        return "medium", "two files in same normalized title group"
    return "low", "implicit ordering in multi-file group"


def build_pairs(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in documents:
        if not is_pairable(row):
            continue
        row = dict(row)
        row["normalized_title"] = normalize_title(row)
        key = (
            row["project_name"],
            row["section"],
            row["document_type"],
            row["normalized_title"],
        )
        groups[key].append(row)

    pairs: list[dict[str, Any]] = []
    for key, rows in groups.items():
        if len(rows) < 2:
            continue
        rows = sorted(rows, key=lambda r: (version_order(r), r["source_path"]))
        for i, old in enumerate(rows):
            for new in rows[i + 1 :]:
                if version_order(old) == version_order(new):
                    continue
                confidence, reason = pair_confidence(old, new, len(rows))
                pairs.append(
                    {
                        "project_name": old["project_name"],
                        "section": old["section"],
                        "document_type": old["document_type"],
                        "normalized_title": old["normalized_title"],
                        "old_path": old["source_path"],
                        "new_path": new["source_path"],
                        "old_version_tag": old.get("version_tag"),
                        "new_version_tag": new.get("version_tag"),
                        "old_version_order": version_order(old),
                        "new_version_order": version_order(new),
                        "confidence": confidence,
                        "pair_reason": reason,
                        "old_file_name": old["file_name"],
                        "new_file_name": new["file_name"],
                    }
                )
    return sorted(
        pairs,
        key=lambda r: (
            r["project_name"],
            r["section"] or "",
            r["document_type"],
            r["normalized_title"],
            r["old_version_order"],
            r["new_version_order"],
            r["old_path"],
            r["new_path"],
        ),
    )


def write_report(pairs: list[dict[str, Any]]) -> None:
    lines = [
        "# Version Pairs",
        "",
        "`scripts/build_version_pairs.py` による旧版/新版ペア候補。差分抽出前に、比較対象ファイルを固定するための中間成果物。",
        "",
        "## Summary",
        "",
        "| key | count |",
        "|---|---:|",
        f"| pairs | {len(pairs)} |",
    ]
    confidence_counts = Counter(pair["confidence"] for pair in pairs)
    for confidence, count in confidence_counts.most_common():
        lines.append(f"| confidence={confidence} | {count} |")

    lines.extend(["", "## By Document Type", "", "| document_type | count |", "|---|---:|"])
    for document_type, count in Counter(pair["document_type"] for pair in pairs).most_common():
        lines.append(f"| `{document_type}` | {count} |")

    lines.extend(
        [
            "",
            "## Pairs",
            "",
            "| confidence | project | type | old | new | reason |",
            "|---|---|---|---|---|---|",
        ]
    )
    for pair in pairs:
        lines.append(
            "| `{confidence}` | {project} | `{doc_type}` | `{old}` | `{new}` | {reason} |".format(
                confidence=pair["confidence"],
                project=pair["project_name"],
                doc_type=pair["document_type"],
                old=pair["old_file_name"],
                new=pair["new_file_name"],
                reason=pair["pair_reason"],
            )
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    documents = load_jsonl(DOC_REGISTRY)
    pairs = build_pairs(documents)
    write_jsonl(OUT_JSONL, pairs)
    write_report(pairs)
    print(f"wrote {OUT_JSONL.relative_to(ROOT)} ({len(pairs)} pairs)")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
