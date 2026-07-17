import unicodedata

import pytest

from src.generator.confidence_gate import MISSING_RESPONSE
from src.orchestrator.answer_stabilizer import (
    align_run_answers,
    normalize_answer,
    stabilize_answers,
)


def test_normalize_answer_equivalent_currency_forms():
    assert normalize_answer("1,234円") == normalize_answer("¥1,234")
    assert normalize_answer("1,234円") == normalize_answer(" 1,234 JPY")


def test_normalize_answer_bare_number_matches_jpy_forms():
    assert normalize_answer("1,234") == normalize_answer("1,234円")


def test_normalize_answer_keeps_unit_words_inside_terms():
    assert normalize_answer("円グラフ") != normalize_answer("グラフ")
    assert normalize_answer("ハンドル") != normalize_answer("ハン")


def test_normalize_answer_distinguishes_currencies():
    assert normalize_answer("100円") != normalize_answer("100ドル")
    assert normalize_answer("$100") == normalize_answer("100ドル")


def test_normalize_answer_distinguishes_different_numbers():
    assert normalize_answer("3") != normalize_answer("4")


def test_normalize_answer_nfc_and_nfd_are_equivalent():
    nfc = "パリ"  # パ はNFDで ハ+結合半濁点 に分解される
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert normalize_answer(nfc) == normalize_answer(nfd)


def test_normalize_answer_unifies_dash_and_minus_variants():
    """U+2212(−)・enダッシュ・emダッシュ・全角－はASCIIハイフンと同一視する
    （実データQ8で同一内容の3回答が文字差だけで3クラスタに割れno_majority化した対策）。"""
    base = "約14,744ドル（140,000ドル - 125,256ドル）"
    assert normalize_answer("約14,744ドル（140,000ドル − 125,256ドル）") == normalize_answer(base)
    assert normalize_answer("約14,744ドル（140,000ドル – 125,256ドル）") == normalize_answer(base)
    assert normalize_answer("約14,744ドル（140,000ドル — 125,256ドル）") == normalize_answer(base)
    assert normalize_answer("約14,744ドル（140,000ドル － 125,256ドル）") == normalize_answer(base)


def test_normalize_answer_keeps_katakana_prolonged_sound_mark():
    """カタカナ長音「ー」はダッシュ類と同一視しない（サーバー≠サ-バ-）。"""
    assert normalize_answer("サーバー") != normalize_answer("サ-バ-")


def test_stabilize_answers_dash_variant_answers_form_majority():
    """ダッシュ文字差だけの回答はクラスタが統合され、no_majorityにならない。"""
    decisions = stabilize_answers(
        ["8"],
        [
            ["約14,744ドル（140,000ドル − 125,256ドル）"],
            ["約14,744ドル（140,000ドル - 125,256ドル）"],
            [MISSING_RESPONSE],
        ],
    )
    assert decisions[0].reason == "majority"
    assert decisions[0].chosen != MISSING_RESPONSE


def test_stabilize_answers_uses_two_of_three_majority_with_raw_representative():
    decisions = stabilize_answers(["1"], [["東京"], ["東京"], ["大阪"]])
    assert decisions[0].question_id == "1"
    assert decisions[0].chosen == "東京"
    assert decisions[0].reason == "majority"


def test_stabilize_answers_three_way_split_becomes_missing():
    decisions = stabilize_answers(["1"], [["東京"], ["大阪"], ["名古屋"]])
    assert decisions[0].chosen == MISSING_RESPONSE
    assert decisions[0].reason == "no_majority"


def test_stabilize_answers_missing_majority_stays_missing():
    decisions = stabilize_answers(["1"], [[MISSING_RESPONSE], [MISSING_RESPONSE], ["東京"]])
    assert decisions[0].chosen == MISSING_RESPONSE
    assert decisions[0].reason == "all_missing"


def test_stabilize_answers_normalized_currency_majority_uses_earliest_raw_on_tie():
    decisions = stabilize_answers(
        ["8"],
        [["¥1,234"], ["1,234円"], ["1,234円少なくなる"]],
    )
    assert decisions[0].chosen == "¥1,234"
    assert decisions[0].reason == "majority"


def test_stabilize_answers_single_run_passthrough():
    decisions = stabilize_answers(["1", "2"], [["東京", MISSING_RESPONSE]])
    assert [d.chosen for d in decisions] == ["東京", MISSING_RESPONSE]
    assert [d.reason for d in decisions] == ["single_run", "single_run"]


def test_stabilize_answers_two_run_split_has_no_majority():
    decisions = stabilize_answers(["1"], [["東京"], ["大阪"]])
    assert decisions[0].chosen == MISSING_RESPONSE
    assert decisions[0].reason == "no_majority"


def test_stabilize_answers_rejects_inconsistent_question_counts():
    with pytest.raises(ValueError):
        stabilize_answers(["1", "2"], [["東京", "大阪"], ["東京"]])


def test_stabilize_answers_rejects_empty_runs():
    with pytest.raises(ValueError):
        stabilize_answers(["1"], [])


def test_stabilize_answers_empty_key_majority_becomes_missing():
    decisions = stabilize_answers(["1"], [[""], [" "], ["東京"]])
    assert decisions[0].chosen == MISSING_RESPONSE
    assert decisions[0].reason == "no_majority"


def test_stabilize_answers_representative_counts_nfc_equivalent_raw_forms():
    nfc = "パリ"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    decisions = stabilize_answers(["1"], [[nfd], [nfd], [nfc]])
    assert decisions[0].chosen == nfc
    assert decisions[0].reason == "unanimous"


def test_align_run_answers_passthrough_when_all_runs_complete():
    per_run_answers, dropped = align_run_answers(
        ["1", "2"],
        [{"1": "東京", "2": "大阪"}, {"1": "東京", "2": "名古屋"}],
    )
    assert per_run_answers == [["東京", "大阪"], ["東京", "名古屋"]]
    assert dropped == [[], []]


def test_align_run_answers_fills_missing_question_with_missing_response():
    per_run_answers, dropped = align_run_answers(
        ["1", "2"],
        [{"1": "東京", "2": "大阪"}, {"1": "東京"}],
    )
    assert per_run_answers == [["東京", "大阪"], ["東京", MISSING_RESPONSE]]
    assert dropped == [[], ["2"]]


def test_align_run_answers_rejects_unexpected_question_id():
    with pytest.raises(ValueError):
        align_run_answers(["1"], [{"1": "東京", "9": "謎"}])
