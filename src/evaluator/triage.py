"""失敗切り分け（triage）: 各問を検索失敗/生成失敗/較正失敗に分類する。

plan_0703.md §2 の3類型:
1. 検索失敗 — 正解候補ファイルがtop-kに入っていない
2. 生成失敗 — 根拠はあるのにLLMが答えない/間違える
3. 較正失敗 — 正しく答えたのにゲートで落ちた（過剰ゲート）、
              または間違いがゲートを通った（素通り）
"""
from __future__ import annotations

CLASS_OK = "OK"
CLASS_RETRIEVAL = "検索失敗"
CLASS_GENERATION = "生成失敗"
CLASS_CALIBRATION_OVERGATE = "較正失敗(過剰ゲート)"
CLASS_CALIBRATION_PASSTHROUGH = "較正失敗(ゲート素通り)"
CLASS_UNMEASURABLE = "計測不能(手動確認)"

_GOOD_LABELS = ("Perfect", "Acceptable")


def classify(
    judge_label: str,
    was_gated: bool,
    measurable: bool,
    hit: bool,
    raw_judge_label: str | None,
) -> str:
    if judge_label in _GOOD_LABELS:
        return CLASS_OK
    if not measurable:
        return CLASS_UNMEASURABLE
    if not hit:
        return CLASS_RETRIEVAL
    if was_gated:
        if raw_judge_label in _GOOD_LABELS:
            return CLASS_CALIBRATION_OVERGATE
        return CLASS_GENERATION
    if judge_label == "Incorrect":
        return CLASS_CALIBRATION_PASSTHROUGH
    return CLASS_GENERATION


def needs_raw_judge(
    judge_label: str,
    was_gated: bool,
    measurable: bool,
    hit: bool,
    raw_answer: str,
) -> bool:
    """ゲート前回答のjudgeが分類に必要なケースか（API節約のため必要時のみ呼ぶ）。"""
    return (
        judge_label not in _GOOD_LABELS
        and was_gated
        and measurable
        and hit
        and bool(raw_answer.strip())
    )
