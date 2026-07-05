"""提出用回答の複数run多数決を安定化する純粋関数。"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

from src.generator.confidence_gate import MISSING_RESPONSE

_MISSING_KEY = "\x00missing"
_REMOVE_CHARS = "、。，,．.・:：;；()（）「」¥￥＄$"
_REMOVE_TRANS = str.maketrans("", "", _REMOVE_CHARS)


@dataclass(frozen=True)
class StabilizationDecision:
    question_id: str
    chosen: str
    reason: str
    cluster_sizes: dict[str, int]
    run_answers: list[str]


def normalize_answer(text: str) -> str:
    """回答表記ゆれを多数決用キーへ正規化する。"""
    if text == MISSING_RESPONSE:
        return _MISSING_KEY
    normalized = unicodedata.normalize("NFC", text).casefold()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.translate(_REMOVE_TRANS)
    for unit in ("円", "ドル", "jpy"):
        normalized = normalized.replace(unit, "")
    return normalized


def stabilize_answers(
    question_ids: list[str],
    per_run_answers: list[list[str]],
) -> list[StabilizationDecision]:
    """runごとの回答列を質問単位で多数決し、採用回答を返す。"""
    if not per_run_answers:
        return []
    expected_count = len(question_ids)
    for answers in per_run_answers:
        if len(answers) != expected_count:
            raise ValueError("All runs must have the same number of answers as question_ids")

    run_count = len(per_run_answers)
    if run_count == 1:
        return [
            StabilizationDecision(
                question_id=qid,
                chosen=answer,
                reason="single_run",
                cluster_sizes={normalize_answer(answer): 1},
                run_answers=[answer],
            )
            for qid, answer in zip(question_ids, per_run_answers[0], strict=True)
        ]

    majority_threshold = run_count // 2 + 1
    decisions: list[StabilizationDecision] = []
    for question_index, question_id in enumerate(question_ids):
        run_answers = [answers[question_index] for answers in per_run_answers]
        clusters: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for run_index, answer in enumerate(run_answers):
            clusters[normalize_answer(answer)].append((run_index, answer))

        cluster_sizes = {key: len(values) for key, values in clusters.items()}
        majority_key = next(
            (key for key, size in cluster_sizes.items() if size >= majority_threshold),
            None,
        )
        if majority_key is None:
            decisions.append(
                StabilizationDecision(
                    question_id=question_id,
                    chosen=MISSING_RESPONSE,
                    reason="no_majority",
                    cluster_sizes=cluster_sizes,
                    run_answers=run_answers,
                )
            )
            continue

        if majority_key == _MISSING_KEY:
            chosen = MISSING_RESPONSE
            reason = "all_missing"
        else:
            chosen = _representative_raw_answer(clusters[majority_key])
            reason = "unanimous" if cluster_sizes[majority_key] == run_count else "majority"
        decisions.append(
            StabilizationDecision(
                question_id=question_id,
                chosen=chosen,
                reason=reason,
                cluster_sizes=cluster_sizes,
                run_answers=run_answers,
            )
        )
    return decisions


def _representative_raw_answer(run_indexed_answers: list[tuple[int, str]]) -> str:
    counts = Counter(answer for _, answer in run_indexed_answers)
    return min(
        (answer for _, answer in run_indexed_answers),
        key=lambda answer: (-counts[answer], _first_run_index(run_indexed_answers, answer)),
    )


def _first_run_index(run_indexed_answers: list[tuple[int, str]], target: str) -> int:
    return next(run_index for run_index, answer in run_indexed_answers if answer == target)
