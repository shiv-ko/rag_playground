"""同一コードN runの多数決ラベル。±0.05のrun間ゆらぎ対策（next-steps §1 Task 4）。

多数決が同数（例: N=3で3ラベルが割れる）の場合はCRAGスコア最小のラベルを採用する
（楽観的な誤判定で実験を採択するより保守側に倒す）。
"""
from __future__ import annotations

from collections import Counter

from src.models import label_score as _score


def majority_labels(runs: list[dict]) -> dict[str, dict]:
    by_id: dict[str, list[dict]] = {}
    for run in runs:
        for r in run["results"]:
            by_id.setdefault(r["question_id"], []).append(r)

    out: dict[str, dict] = {}
    for qid, records in by_id.items():
        counts = Counter(r["judge_label"] for r in records)
        top = max(counts.values())
        winners = [label for label, c in counts.items() if c == top]
        label = min(winners, key=_score)  # 同数はスコア最小（保守側）
        out[qid] = {
            "label": label,
            "votes": counts[label],
            "total": len(records),
            "question": records[0]["question"],
        }
    return out


def unstable_questions(runs: list[dict]) -> list[dict]:
    majority = majority_labels(runs)
    unstable = []
    for qid, m in majority.items():
        labels = sorted(
            r["judge_label"]
            for run in runs
            for r in run["results"]
            if r["question_id"] == qid
        )
        if len(set(labels)) > 1:
            unstable.append({"question_id": qid, "labels": labels, "question": m["question"]})
    return sorted(unstable, key=lambda u: u["question_id"])


def to_pseudo_run(majority: dict[str, dict]) -> dict:
    return {
        "summary": {},
        "results": [
            {
                "question_id": qid,
                "question": m["question"],
                "judge_label": m["label"],
                "answer": "",
            }
            for qid, m in sorted(majority.items())
        ],
    }
