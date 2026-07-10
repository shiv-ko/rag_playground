"""run JSON の Missing を評価用ラベルと経路別に集計する純粋関数群。

question_labels.csv は評価専用であり、このモジュールは evaluator/ 配下と
診断 CLI からのみ利用する。回答生成・ルーティングには接続しない。
"""
from __future__ import annotations

import csv
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.utils.question_classifier import classify_question

STRUCTURED_TAGS = frozenset({
    "office_style",
    "spreadsheet_state",
    "spreadsheet_calc",
    "version_diff",
    "ms_date_duration",
    "ms_date_cross_project_list",
    "contract_rule",
})


@dataclass(frozen=True)
class MissingDiagnostic:
    question_id: str
    primary_type: str
    gate_reason: str
    routing: str
    structured_path: str


def find_latest_run(experiments_dir: Path) -> Path:
    """results 配列を持つ最新の run JSON を返す。"""
    candidates: list[Path] = []
    for path in experiments_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload.get("results"), list):
            candidates.append(path)
    if not candidates:
        raise FileNotFoundError(f"run JSON が見つかりません: {experiments_dir}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_labels(path: Path) -> dict[str, dict[str, tuple[str, str]]]:
    """split -> question_id -> (primary_type, question) を読む。"""
    labels: dict[str, dict[str, tuple[str, str]]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            labels.setdefault(row["split"], {})[row["index"]] = (
                row["primary_type"], row["question"]
            )
    return labels


def infer_split(results: list[dict], labels: dict[str, dict[str, tuple[str, str]]]) -> str:
    """IDだけでなく質問文も照合し、valid/test のID重複を安全に解決する。"""
    def normalize(value: object) -> str:
        return unicodedata.normalize("NFC", str(value or ""))

    scores = {
        split: sum(
            normalize(mapping.get(str(row.get("question_id")), (None, None))[1])
            == normalize(row.get("question"))
            for row in results
        )
        for split, mapping in labels.items()
    }
    if not scores or max(scores.values()) == 0:
        raise ValueError("run と question_labels.csv の split を質問文から特定できません")
    best = max(scores.values())
    winners = [split for split, score in scores.items() if score == best]
    if len(winners) != 1:
        raise ValueError(f"split を一意に特定できません: {scores}")
    return winners[0]


def _source_locations(row: dict) -> list[str]:
    return [str(source).rsplit("::", 1)[-1] for source in row.get("retrieved_sources", [])]


def infer_structured_path(row: dict, tags: list[str]) -> str:
    """新スキーマの明示値を優先し、旧runは保存済みsourceの痕跡から推定する。"""
    explicit = row.get("answer_path") or row.get("structured_path")
    if explicit:
        return str(explicit)

    locations = _source_locations(row)
    inferred = ""
    if any(location.startswith("version_diff_") for location in locations):
        inferred = "version_diff"
    elif any("_pivot_" in location or location.endswith("_filter") or "_row_" in location
             for location in locations):
        inferred = "spreadsheet_state"
    elif any(location in {"paragraph_run", "table_cell_run"} for location in locations):
        inferred = "office_style"

    if inferred:
        suffix = "gated" if row.get("was_gated") else "answered"
        return f"structured_fired:{inferred}:{suffix}"

    structured_tags = [tag for tag in tags if tag in STRUCTURED_TAGS]
    if structured_tags:
        return "structured_not_observed:legacy_run"
    return "retrieval_only"


def diagnose_missing(
    results: list[dict], label_map: dict[str, tuple[str, str]]
) -> list[MissingDiagnostic]:
    rows: list[MissingDiagnostic] = []
    for row in results:
        # judgeなしのtest診断runは was_gated がMissing判定の正本。
        is_missing = row.get("judge_label") == "Missing" or (
            not row.get("judge_label") and bool(row.get("was_gated"))
        )
        if not is_missing:
            continue
        qid = str(row.get("question_id"))
        tags = list(row.get("routing_tags") or classify_question(str(row.get("question", ""))))
        structured_tags = [tag for tag in tags if tag in STRUCTURED_TAGS]
        routing = "+".join(structured_tags) if structured_tags else "text_only"
        primary_type = label_map.get(qid, ("?", ""))[0]
        rows.append(MissingDiagnostic(
            question_id=qid,
            primary_type=primary_type,
            gate_reason=str(row.get("gate_reason") or "unspecified"),
            routing=routing,
            structured_path=infer_structured_path(row, tags),
        ))
    return rows


def aggregate(rows: list[MissingDiagnostic]) -> Counter[tuple[str, str, str, str]]:
    return Counter(
        (row.primary_type, row.gate_reason, row.routing, row.structured_path)
        for row in rows
    )


def render_markdown(rows: list[MissingDiagnostic], run_path: Path, split: str) -> str:
    counts = aggregate(rows)
    lines = [
        "# Missing 経路診断",
        "",
        f"run: `{run_path}` / split: `{split}` / Missing: {len(rows)}件",
        "",
        "| primary_type | gate_reason | routing | structured_path | 件数 |",
        "|---|---|---|---|---:|",
    ]
    for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {' | '.join(key)} | {count} |")
    lines.extend(["", "## 質問ID", ""])
    for row in rows:
        lines.append(
            f"- {row.question_id}: {row.primary_type} / {row.gate_reason} / "
            f"{row.routing} / {row.structured_path}"
        )
    return "\n".join(lines) + "\n"
