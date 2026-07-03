"""構造化コンテキストビルダーのテスト。"""
from __future__ import annotations

from src.retriever.structured_context import (
    build_office_style_context,
    build_spreadsheet_state_context,
)
from src.structured.artifact_store import StructuredArtifactStore


def _full_store(**kinds) -> StructuredArtifactStore:
    base = {
        "office_marks": {},
        "highlight_cells": {},
        "schedule_tasks": {},
        "train_xlsx_highlight_blocks": {},
        "train_xlsx_sheets": {},
        "spreadsheet_sheets": {},
    }
    base.update(kinds)
    return StructuredArtifactStore(base)


def _store_with_marks(marks: list[dict]) -> StructuredArtifactStore:
    return _full_store(office_marks={"A社": marks})


def test_bold_question_selects_only_bold_runs() -> None:
    store = _store_with_marks([
        {"source_path": "x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 1, "text": "太字の見出し", "bold": True, "italic": False, "underline": False, "font_color": None, "fill_color": None},
        {"source_path": "x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 1, "text": "普通の本文", "bold": False, "italic": False, "underline": False, "font_color": None, "fill_color": None},
    ])
    docs = build_office_style_context("太字で記載されている箇所をすべて抽出してください。", "A社", store)
    texts = [d.document.text for d in docs]
    assert any("太字の見出し" in t for t in texts)
    assert not any("普通の本文" in t for t in texts)


def test_red_question_selects_red_font_color() -> None:
    store = _store_with_marks([
        {"source_path": "x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 1, "text": "赤字の警告文", "bold": False, "italic": False, "underline": False, "font_color": "8B2500", "fill_color": None},
        {"source_path": "x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 1, "text": "黒字の本文", "bold": False, "italic": False, "underline": False, "font_color": "1A1A1A", "fill_color": None},
    ])
    docs = build_office_style_context("赤で強調されている箇所の文字列を抜き出してください。", "A社", store)
    texts = [d.document.text for d in docs]
    assert any("赤字の警告文" in t for t in texts)
    assert not any("黒字の本文" in t for t in texts)


def test_no_matching_marks_returns_empty_list() -> None:
    store = _store_with_marks([])
    docs = build_office_style_context("太字で記載されている箇所をすべて抽出してください。", "A社", store)
    assert docs == []


def test_scored_document_has_source_path_and_location() -> None:
    store = _store_with_marks([
        {"source_path": "data/raw/x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 3, "text": "太字テキスト", "bold": True, "italic": False, "underline": False, "font_color": None, "fill_color": None},
    ])
    docs = build_office_style_context("太字の箇所を抽出してください。", "A社", store)
    assert len(docs) == 1
    assert str(docs[0].document.source_path) == "data/raw/x/提案書.pptx"
    assert docs[0].document.location == "slide_3"


class TestSpreadsheetStateContext:
    def test_highlight_question_uses_train_xlsx_highlight_blocks(self) -> None:
        store = _full_store(train_xlsx_highlight_blocks={"A社": [
            {
                "source_path": "data/raw/x/train.xlsx", "sheet_name": "Pivot", "range": "F22",
                "fill_color_name": "yellow", "first_value": "35.95",
                "column_header": {"cell": "F3", "value": "平均 / bmi", "formula": None},
                "same_row_values": [{"cell": "E22", "value": "39", "formula": None}],
            }
        ]})
        docs = build_spreadsheet_state_context(
            "train.xlsxのPivotシートで黄色ハイライトされているセルの抽出条件を教えてください。", "A社", store
        )
        assert len(docs) == 1
        assert "平均 / bmi" in docs[0].document.text
        assert "35.95" in docs[0].document.text

    def test_filter_question_uses_spreadsheet_sheets_auto_filter(self) -> None:
        store = _full_store(spreadsheet_sheets={"A社": [
            {"source_path": "data/raw/x/train.xlsx", "sheet_name": "train", "auto_filter_ref": "A1:N31", "hidden_rows": [5, 6, 7]},
        ]}, highlight_cells={"A社": [
            {"source_path": "data/raw/x/train.xlsx", "sheet_name": "train", "cell": "A1", "row": 1, "column": 1, "value": "ステータス"},
        ]})
        docs = build_spreadsheet_state_context(
            "train.xlsxのtrainシートでフィルターで抽出されている条件を教えてください。", "A社", store
        )
        assert len(docs) >= 1
        assert any("A1:N31" in d.document.text or "非表示" in d.document.text for d in docs)

    def test_task_listing_question_uses_schedule_tasks(self) -> None:
        store = _full_store(schedule_tasks={"A社": [
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "WBSタスク一覧",
             "values": {"タスクID": "T05", "フェーズ名": "探索的分析・仮説整理", "タスク名": "仮説一覧作成"}},
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "WBSタスク一覧",
             "values": {"タスクID": "T09", "フェーズ名": "モデル構築", "タスク名": "学習実行"}},
        ]})
        docs = build_spreadsheet_state_context(
            "探索的分析・仮説整理フェーズに一致するタスクIDをすべて挙げてください。", "A社", store
        )
        texts = "\n".join(d.document.text for d in docs)
        assert "T05" in texts
        assert "T09" not in texts

    def test_no_matching_data_returns_empty_list(self) -> None:
        store = _full_store()
        docs = build_spreadsheet_state_context("何かの質問", "A社", store)
        assert docs == []
