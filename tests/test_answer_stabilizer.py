import unicodedata

import pytest

from src.generator.confidence_gate import MISSING_RESPONSE
from src.orchestrator.answer_stabilizer import normalize_answer, stabilize_answers


def test_normalize_answer_equivalent_currency_forms():
    assert normalize_answer("1,234円") == normalize_answer("¥1,234")
    assert normalize_answer("1,234円") == normalize_answer(" 1,234 JPY")


def test_normalize_answer_distinguishes_different_numbers():
    assert normalize_answer("3") != normalize_answer("4")


def test_normalize_answer_nfc_and_nfd_are_equivalent():
    nfc = "カフェ"
    nfd = unicodedata.normalize("NFD", nfc)
    assert normalize_answer(nfc) == normalize_answer(nfd)


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
