"""spreadsheet_calc のテスト。"""
from __future__ import annotations

import pandas as pd

from src.generator.spreadsheet_calc import (
    CalcSpec,
    FilterCondition,
    SpreadsheetCalcAnswerer,
    execute_calc_spec,
    parse_calc_spec,
)


def test_parse_calc_spec_valid_json() -> None:
    raw = '{"filters": [{"column": "grade", "op": "==", "value": "B1"}], "target_column": "loan_amnt", "aggregation": "mean", "round_to": 0}'
    spec = parse_calc_spec(raw)
    assert spec is not None
    assert spec.filters == [FilterCondition(column="grade", op="==", value="B1")]
    assert spec.target_column == "loan_amnt"
    assert spec.aggregation == "mean"
    assert spec.round_to == 0


def test_parse_calc_spec_invalid_json_returns_none() -> None:
    assert parse_calc_spec("not json") is None


def test_parse_calc_spec_missing_target_column_returns_none() -> None:
    raw = '{"filters": [], "aggregation": "mean"}'
    assert parse_calc_spec(raw) is None


def test_parse_calc_spec_multiple_filters() -> None:
    raw = '{"filters": [{"column": "term", "op": "==", "value": "3 years"}, {"column": "grade", "op": "==", "value": "B1"}], "target_column": "loan_amnt", "aggregation": "mean", "round_to": 0}'
    spec = parse_calc_spec(raw)
    assert spec is not None
    assert len(spec.filters) == 2


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "term": ["3 years", "3 years", "5 years"],
        "grade": ["B1", "B1", "B1"],
        "loan_amnt": [1000.0, 2000.0, 5000.0],
    })


def test_execute_mean_with_single_filter() -> None:
    spec = CalcSpec([FilterCondition("term", "==", "3 years")], "loan_amnt", "mean", 0)
    assert execute_calc_spec(spec, _sample_df()) == 1500


def test_execute_with_multiple_filters() -> None:
    spec = CalcSpec(
        [FilterCondition("term", "==", "3 years"), FilterCondition("grade", "==", "B1")],
        "loan_amnt", "mean", 0,
    )
    assert execute_calc_spec(spec, _sample_df()) == 1500


def test_execute_count_aggregation() -> None:
    spec = CalcSpec([], "loan_amnt", "count", None)
    assert execute_calc_spec(spec, _sample_df()) == 3


def test_execute_unknown_column_returns_none() -> None:
    spec = CalcSpec([], "存在しない列", "mean", None)
    assert execute_calc_spec(spec, _sample_df()) is None


def test_execute_filter_matching_zero_rows_returns_none() -> None:
    spec = CalcSpec([FilterCondition("term", "==", "99 years")], "loan_amnt", "mean", None)
    assert execute_calc_spec(spec, _sample_df()) is None


def test_execute_numeric_comparison_filter() -> None:
    spec = CalcSpec([FilterCondition("loan_amnt", ">", 1500)], "loan_amnt", "sum", None)
    assert execute_calc_spec(spec, _sample_df()) == 7000


class FakeAnswerer(SpreadsheetCalcAnswerer):
    def __init__(self, fake_response: str) -> None:
        super().__init__()
        self.fake_response = fake_response

    def _call_llm(self, question: str, columns_preview: str) -> str:
        return self.fake_response


def test_answerer_returns_computed_value_ungated() -> None:
    fake = '{"filters": [{"column": "term", "op": "==", "value": "3 years"}], "target_column": "loan_amnt", "aggregation": "mean", "round_to": 0}'
    answerer = FakeAnswerer(fake)
    answer = answerer.answer("term=3 yearsの中でloan_amntの平均を教えてください。", _sample_df())
    assert answer.was_gated is False
    assert "1500" in answer.text


def test_answerer_gates_when_spec_unparseable() -> None:
    answerer = FakeAnswerer("not json")
    answer = answerer.answer("何かの集計質問", _sample_df())
    assert answer.was_gated is True


def test_answerer_gates_when_filter_matches_nothing() -> None:
    fake = '{"filters": [{"column": "term", "op": "==", "value": "99 years"}], "target_column": "loan_amnt", "aggregation": "mean", "round_to": 0}'
    answerer = FakeAnswerer(fake)
    answer = answerer.answer("term=99 yearsの中でloan_amntの平均を教えてください。", _sample_df())
    assert answer.was_gated is True


def test_answerer_gates_groupby_style_question_without_calling_llm():
    """CalcSpecで表現できないグループ別・argmax系の質問（「最も高い」「〜ごと」）は、
    もっともらしいspecで誤った数値を返すリスクがあるためLLMを呼ばずにゲートする。"""

    class BoomAnswerer(SpreadsheetCalcAnswerer):
        def _call_llm(self, question: str, columns_preview: str) -> str:
            raise AssertionError("表現できない質問ではLLMを呼ばない")

    answerer = BoomAnswerer()
    answer = answerer.answer(
        "disease=1の女性の中で、ALT_GPTの平均値が最も高い年齢は何歳ですか。", _sample_df()
    )
    assert answer.was_gated is True


def test_parse_calc_spec_not_applicable_returns_none():
    assert parse_calc_spec('{"not_applicable": true}') is None
