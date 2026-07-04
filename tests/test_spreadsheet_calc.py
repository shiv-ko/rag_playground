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


def test_parse_calc_spec_group_by_select() -> None:
    raw = '{"filters": [{"column": "disease", "op": "==", "value": 1}], "target_column": "ALT_GPT", "aggregation": "mean", "round_to": null, "group_by": "age", "select": "argmax"}'
    spec = parse_calc_spec(raw)
    assert spec is not None
    assert spec.group_by == "age"
    assert spec.select == "argmax"


def test_parse_calc_spec_invalid_select_returns_none() -> None:
    raw = '{"filters": [], "target_column": "ALT_GPT", "aggregation": "mean", "group_by": "age", "select": "top"}'
    assert parse_calc_spec(raw) is None


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


def test_execute_group_by_mean_argmax() -> None:
    df = pd.DataFrame({
        "sex": ["F", "F", "F", "M"],
        "disease": [1, 1, 1, 1],
        "age": [31, 32, 32, 33],
        "ALT_GPT": [10.0, 30.0, 50.0, 100.0],
    })
    spec = CalcSpec(
        filters=[FilterCondition("sex", "==", "F"), FilterCondition("disease", "==", 1)],
        target_column="ALT_GPT",
        aggregation="mean",
        round_to=None,
        group_by="age",
        select="argmax",
    )
    assert execute_calc_spec(spec, df) == 32


def test_execute_group_by_missing_column_returns_none() -> None:
    spec = CalcSpec([], "loan_amnt", "mean", None, group_by="age", select="argmax")
    assert execute_calc_spec(spec, _sample_df()) is None


def test_execute_group_by_after_zero_row_filter_returns_none() -> None:
    spec = CalcSpec(
        [FilterCondition("term", "==", "99 years")],
        "loan_amnt",
        "mean",
        None,
        group_by="grade",
        select="argmax",
    )
    assert execute_calc_spec(spec, _sample_df()) is None


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


def test_answerer_answers_groupby_argmax_question() -> None:
    fake = '{"filters": [{"column": "term", "op": "==", "value": "3 years"}], "target_column": "loan_amnt", "aggregation": "mean", "round_to": null, "group_by": "grade", "select": "argmax"}'
    answerer = FakeAnswerer(fake)
    answer = answerer.answer(
        "term=3 yearsの中で、loan_amntの平均値が最も高いgradeは何ですか。", _sample_df()
    )
    assert answer.was_gated is False
    assert answer.text == "B1"


def test_answerer_still_gates_group_listing_question_without_calling_llm() -> None:
    class BoomAnswerer(SpreadsheetCalcAnswerer):
        def _call_llm(self, question: str, columns_preview: str) -> str:
            raise AssertionError("表現できない質問ではLLMを呼ばない")

    answerer = BoomAnswerer()
    answer = answerer.answer(
        "gradeごとのloan_amntの平均をそれぞれ教えてください。", _sample_df()
    )
    assert answer.was_gated is True


def test_answerer_gates_xlsx_pivot_question_without_calling_llm() -> None:
    class BoomAnswerer(SpreadsheetCalcAnswerer):
        def _call_llm(self, question: str, columns_preview: str) -> str:
            raise AssertionError("xlsx/Pivot系はspreadsheet_stateへフォールバックする")

    answerer = BoomAnswerer()
    answer = answerer.answer(
        "train.xlsxのPivotシートにおいて、平均月収が最も高い層の抽出条件を教えてください。",
        _sample_df(),
    )
    assert answer.was_gated is True


def test_parse_calc_spec_not_applicable_returns_none():
    assert parse_calc_spec('{"not_applicable": true}') is None
