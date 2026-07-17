"""提出用回答の複数run多数決を安定化する純粋関数。"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

from src.generator.confidence_gate import MISSING_RESPONSE

_MISSING_KEY = "\x00missing"
_REMOVE_CHARS = "、。，,．.・:：;；()（）「」"
_REMOVE_TRANS = str.maketrans("", "", _REMOVE_CHARS)
# LLM出力はマイナス/ダッシュに複数のUnicode変種を使い分けるため、多数決キーでは
# ASCIIハイフンへ畳む。カタカナ長音「ー」(U+30FC)は文字として意味を持つので対象外。
_DASH_VARIANTS = "‐‑‒–—―−－"
_DASH_TRANS = str.maketrans({ch: "-" for ch in _DASH_VARIANTS})
# 通貨表記は数字に隣接する場合のみ正規化する（「円グラフ」等の語中の単位語は保持）。
# JPYは既定通貨として無印に寄せ、ドルは「<数字>ドル」の形へ寄せて通貨の区別を保つ。
_YEN_PREFIX = re.compile(r"[¥￥](?=\d)")
_YEN_SUFFIX = re.compile(r"(?<=\d)(円|jpy)")
_DOLLAR_PREFIX = re.compile(r"[＄$](\d+)")


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
    normalized = normalized.translate(_DASH_TRANS)
    normalized = _DOLLAR_PREFIX.sub(r"\1ドル", normalized)
    normalized = _YEN_PREFIX.sub("", normalized)
    normalized = _YEN_SUFFIX.sub("", normalized)
    return normalized


def _same_content(key_a: str, key_b: str) -> bool:
    """正規化キー同士が「同じ内容の詳細度・順序ちがい」とみなせるか。
    片方が他方の部分文字列（詳細度の差）、または文字多重集合が一致（列挙順の入れ替え）なら同内容。"""
    return key_a in key_b or key_b in key_a or sorted(key_a) == sorted(key_b)


def stabilize_answers(
    question_ids: list[str],
    per_run_answers: list[list[str]],
    conservative: bool = False,
) -> list[StabilizationDecision]:
    """runごとの回答列を質問単位で多数決し、採用回答を返す。

    conservative=True（提出2枠の保守構成用）は、多数決で勝っても内容の矛盾する
    少数派回答が存在する質問をMissingへ倒す（reason="answer_conflict"）。
    バッチごとに多数決の勝者が入れ替わる真性不安定問（Q69型）のIncorrectヘッジ。"""
    if not per_run_answers:
        raise ValueError("per_run_answers must contain at least one run")
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
        if majority_key == "":
            # 正規化で消える回答（空・記号のみ）は提出回答として採用しない
            majority_key = None
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
        elif conservative and any(
            key not in ("", _MISSING_KEY, majority_key)
            and not _same_content(key, majority_key)
            for key in cluster_sizes
        ):
            chosen = MISSING_RESPONSE
            reason = "answer_conflict"
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


def align_run_answers(
    question_ids: list[str],
    per_run_results: list[dict[str, str]],
) -> tuple[list[list[str]], list[list[str]]]:
    """runごとの id→回答 を question_ids の順に整列する。

    runに欠けた質問は MISSING_RESPONSE で補完し（欠落＝そのrunは棄権票）、
    run別の欠落IDリストを併せて返す。想定外のIDは黙って捨てずValueError。
    """
    expected = set(question_ids)
    per_run_answers: list[list[str]] = []
    dropped: list[list[str]] = []
    for results in per_run_results:
        unexpected = sorted(set(results) - expected)
        if unexpected:
            raise ValueError(f"unexpected question_id in run: {unexpected}")
        per_run_answers.append([results.get(qid, MISSING_RESPONSE) for qid in question_ids])
        dropped.append([qid for qid in question_ids if qid not in results])
    return per_run_answers, dropped


def _representative_raw_answer(run_indexed_answers: list[tuple[int, str]]) -> str:
    # NFC同士で数え、最頻（同数はrun番号が小さい方）のNFC形を代表にする
    counts = Counter(
        unicodedata.normalize("NFC", answer) for _, answer in run_indexed_answers
    )
    return max(counts, key=counts.get)
