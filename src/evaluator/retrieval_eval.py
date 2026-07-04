"""検索単体評価（retrieval recall）。

question_labels.csv の source_section と project_registry のエイリアス照合から
「正解根拠ファイル候補」を機械的に導出し、retriever の top-k にその候補が
入ったかを判定する。LLMは呼ばない。

注意: このモジュールは評価専用。回答生成パスから import してはならない
（question_labels.csv は人手ラベルであり、回答生成に使うと規約違反になる）。
"""
from __future__ import annotations

import csv
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from src.models import ScoredDocument
from src.utils.paths import to_repo_relative

_UNSPECIFIC_SECTIONS = {"unknown", "cross_project", ""}


def _nfc(text: str) -> str:
    """macOSファイルシステムはパスをNFD正規化して返すため、registry由来の
    NFC文字列と実パス由来のNFD/混在文字列がバイト単位で不一致になりうる。
    比較境界は必ずNFCに揃える。"""
    return unicodedata.normalize("NFC", text)


@dataclass
class QuestionLabel:
    split: str
    index: str
    question: str
    primary_type: str
    source_section: list[str]


def load_labels(path: Path, split: str) -> list[QuestionLabel]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] == split]
    return [
        QuestionLabel(
            split=r["split"],
            index=r["index"],
            question=r["question"],
            primary_type=r["primary_type"],
            source_section=[s for s in r["source_section"].split(";") if s],
        )
        for r in rows
    ]


def resolve_projects(question: str, project_registry: list[dict]) -> list[str]:
    normalized_question = _nfc(question)
    hits = []
    for proj in project_registry:
        if any(_nfc(alias) in normalized_question for alias in proj["aliases"]):
            hits.append(proj["project_name"])
    return hits


@dataclass
class CandidateSet:
    measurable: bool
    files: frozenset[str]
    reason: str = ""


def candidate_files(
    label: QuestionLabel,
    doc_registry: list[dict],
    project_registry: list[dict],
) -> CandidateSet:
    projects = resolve_projects(label.question, project_registry)
    sections = [s for s in label.source_section if s not in _UNSPECIFIC_SECTIONS]

    if not projects and not sections:
        return CandidateSet(
            measurable=False, files=frozenset(),
            reason="案件もセクションも機械特定できない（cross_project等）",
        )

    files = set()
    for entry in doc_registry:
        if projects and entry.get("project_name") not in projects:
            continue
        if sections and entry.get("section") not in sections:
            continue
        files.add(_nfc(entry["source_path"]))

    if not files:
        return CandidateSet(measurable=False, files=frozenset(), reason="候補0件")
    return CandidateSet(measurable=True, files=frozenset(files))


@dataclass
class RetrievalRecord:
    question_id: str
    primary_type: str
    measurable: bool
    hit: bool
    first_hit_rank: int  # 1始まり。ヒットなしは0
    retrieved: list[str]
    candidate_count: int
    reason: str = ""


SearchFn = Callable[[str, int], list[ScoredDocument]]


def evaluate_one(
    search_fn: SearchFn,
    label: QuestionLabel,
    cand: CandidateSet,
    top_k: int,
) -> RetrievalRecord:
    retrieved = search_fn(label.question, top_k)
    sources = [_nfc(to_repo_relative(sd.document.source_path)) for sd in retrieved]
    first_hit_rank = 0
    for rank, src in enumerate(sources, 1):
        if src in cand.files:
            first_hit_rank = rank
            break
    return RetrievalRecord(
        question_id=label.index,
        primary_type=label.primary_type,
        measurable=cand.measurable,
        hit=first_hit_rank > 0,
        first_hit_rank=first_hit_rank,
        retrieved=sources,
        candidate_count=len(cand.files),
        reason=cand.reason,
    )


def summarize_records(records: list[RetrievalRecord]) -> str:
    measurable = [r for r in records if r.measurable]
    by_type: dict[str, list[RetrievalRecord]] = defaultdict(list)
    for r in measurable:
        by_type[r.primary_type].append(r)

    lines = [
        f"計測可能: {len(measurable)}/{len(records)}問",
    ]
    if measurable:
        hits = sum(r.hit for r in measurable)
        lines.append(f"recall@top-k: {hits}/{len(measurable)} ({100 * hits / len(measurable):.0f}%)")
    lines.append("")
    lines.append("| primary_type | recall | hit/計測可能 |")
    lines.append("|---|---|---|")
    for ptype in sorted(by_type):
        recs = by_type[ptype]
        hits = sum(r.hit for r in recs)
        lines.append(f"| {ptype} | {100 * hits / len(recs):.0f}% | {hits}/{len(recs)} |")
    return "\n".join(lines)


def records_to_payload(records: list[RetrievalRecord]) -> dict:
    measurable = [r for r in records if r.measurable]
    by_type: dict[str, dict] = {}
    for ptype in sorted({r.primary_type for r in measurable}):
        recs = [r for r in measurable if r.primary_type == ptype]
        by_type[ptype] = {"hit": sum(r.hit for r in recs), "measurable": len(recs)}
    return {
        "summary": {
            "recall": (sum(r.hit for r in measurable) / len(measurable)) if measurable else 0.0,
            "measurable": len(measurable),
            "total": len(records),
            "by_type": by_type,
        },
        "records": [asdict(r) for r in records],
    }
