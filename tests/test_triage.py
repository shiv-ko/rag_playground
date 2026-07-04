from src.evaluator.triage import (
    CLASS_CALIBRATION_OVERGATE,
    CLASS_CALIBRATION_PASSTHROUGH,
    CLASS_GENERATION,
    CLASS_OK,
    CLASS_RETRIEVAL,
    CLASS_UNMEASURABLE,
    classify,
    needs_raw_judge,
)


def test_ok():
    assert classify("Perfect", False, True, True, None) == CLASS_OK
    assert classify("Acceptable", False, True, True, None) == CLASS_OK


def test_unmeasurable():
    assert classify("Missing", True, False, False, None) == CLASS_UNMEASURABLE


def test_retrieval_failure():
    assert classify("Missing", True, True, False, None) == CLASS_RETRIEVAL


def test_calibration_overgate():
    """検索は当たり、ゲート前回答も正しいのにゲートで落とした。"""
    assert classify("Missing", True, True, True, "Perfect") == CLASS_CALIBRATION_OVERGATE
    assert classify("Missing", True, True, True, "Acceptable") == CLASS_CALIBRATION_OVERGATE


def test_generation_failure_gated_wrong_raw():
    """検索は当たったがゲート前回答も間違っていた。"""
    assert classify("Missing", True, True, True, "Incorrect") == CLASS_GENERATION
    assert classify("Missing", True, True, True, "Missing") == CLASS_GENERATION


def test_generation_failure_refused():
    """ゲートは通ったのにLLMが「わかりません」と答えた。"""
    assert classify("Missing", False, True, True, None) == CLASS_GENERATION


def test_calibration_passthrough():
    """間違った回答がゲートを素通りしてIncorrectになった。"""
    assert classify("Incorrect", False, True, True, None) == CLASS_CALIBRATION_PASSTHROUGH


def test_classify_incorrect_and_gated():
    """通常は起きない組み合わせ（gatedなら最終回答はMissing定型文のはず）だが、
    起きた場合はwas_gated分岐が優先される現挙動を固定する。"""
    assert classify("Incorrect", True, True, True, "Perfect") == CLASS_CALIBRATION_OVERGATE
    assert classify("Incorrect", True, True, True, "Incorrect") == CLASS_GENERATION


def test_needs_raw_judge():
    """ゲート落ち＋検索ヒット＋生回答ありの場合だけ生回答judgeが要る。"""
    assert needs_raw_judge("Missing", True, True, True, "生回答") is True
    assert needs_raw_judge("Missing", True, True, True, "") is False
    assert needs_raw_judge("Missing", True, True, False, "生回答") is False
    assert needs_raw_judge("Perfect", False, True, True, "生回答") is False
