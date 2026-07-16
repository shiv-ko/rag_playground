"""保存済みrun JSON間の再現性を監査する純粋関数。"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.generator.confidence_gate import MISSING_RESPONSE

FIELDS = ("final_answer", "answer_status", "answer_path", "retrieved_sources")
FIELD_TO_STAGE = {
    "final_answer": "generation",
    "answer_status": "gate",
    "answer_path": "routing",
    "retrieved_sources": "retrieval",
}


def audit_run_payloads(
    payloads: Sequence[dict[str, Any]],
    *,
    run_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """2つ以上のrunを質問IDで整列し、全run完全一致率とflipを返す。

    通常runの ``results`` と、多数決監査runの ``decisions`` の双方を扱う。
    後者にない検索元・回答経路は比較不能として集計対象から除外する。
    """
    if len(payloads) < 2:
        raise ValueError("at least two runs are required")
    names = list(run_names) if run_names is not None else [
        f"run_{index}" for index in range(1, len(payloads) + 1)
    ]
    if len(names) != len(payloads) or len(set(names)) != len(names):
        raise ValueError("run_names must be unique and match the number of runs")

    runs = [_index_payload(payload) for payload in payloads]
    expected_ids = set(runs[0])
    for index, run in enumerate(runs[1:], start=2):
        if set(run) != expected_ids:
            raise ValueError(f"question_id sets differ between run 1 and run {index}")

    question_ids = sorted(expected_ids, key=_question_sort_key)
    metrics = {
        field: {"comparable_count": 0, "matching_count": 0, "agreement_rate": None}
        for field in FIELDS
    }
    flips: list[dict[str, Any]] = []
    stage_flips: dict[str, list[str]] = {
        "retrieval": [], "generation": [], "gate": [], "routing": []
    }

    for question_id in question_ids:
        changed_fields: list[str] = []
        for field in FIELDS:
            values = [run[question_id][field] for run in runs]
            if any(value is None for value in values):
                continue
            metrics[field]["comparable_count"] += 1
            if all(value == values[0] for value in values[1:]):
                metrics[field]["matching_count"] += 1
            else:
                changed_fields.append(field)
                stage_flips[FIELD_TO_STAGE[field]].append(question_id)
        if changed_fields:
            flips.append({
                "question_id": question_id,
                "changed_fields": changed_fields,
                "values": {
                    name: runs[index][question_id]
                    for index, name in enumerate(names)
                },
            })

    for metric in metrics.values():
        comparable = metric["comparable_count"]
        if comparable:
            metric["agreement_rate"] = metric["matching_count"] / comparable

    return {
        "run_count": len(runs),
        "run_names": names,
        "question_count": len(question_ids),
        "metrics": metrics,
        "stage_flips": stage_flips,
        "flips": flips,
    }


def _index_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if isinstance(payload.get("results"), list):
        rows = payload["results"]
    elif isinstance(payload.get("decisions"), list):
        rows = payload["decisions"]
    else:
        raise ValueError("run JSON must contain a results or decisions list")

    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or "question_id" not in row:
            raise ValueError("every run row must contain question_id")
        question_id = str(row["question_id"])
        if question_id in indexed:
            raise ValueError(f"duplicate question_id: {question_id}")
        answer = row.get("answer", row.get("chosen", row.get("final_answer")))
        if not isinstance(answer, str):
            raise ValueError(f"question_id {question_id} has no string final answer")
        sources = row.get("retrieved_sources")
        if sources is not None:
            if not isinstance(sources, list) or not all(
                isinstance(x, str) for x in sources
            ):
                raise ValueError(
                    f"question_id {question_id} has invalid retrieved_sources"
                )
            sources = list(sources)
        indexed[question_id] = {
            "final_answer": answer,
            "answer_status": _answer_status(row, answer),
            "answer_path": row.get("answer_path", row.get("structured_path")),
            "retrieved_sources": sources,
        }
    return indexed


def _answer_status(row: dict[str, Any], answer: str) -> str:
    explicit = row.get("answer_status")
    if explicit in {"answered", "Missing"}:
        return explicit
    is_missing = row.get("was_gated") is True or answer == MISSING_RESPONSE
    return "Missing" if is_missing else "answered"


def _question_sort_key(question_id: str) -> tuple[int, int | str]:
    try:
        return (0, int(question_id))
    except ValueError:
        return (1, question_id)
