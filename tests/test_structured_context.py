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


class TestScheduleTaskMatchingGeneralization:
    """実データ形式への対応: 列名「フェーズ」（「フェーズ名」でない）、
    番号接頭辞付きの値（「3. 探索的分析・仮説整理」）、複合担当者（「A / B」）。"""

    def _aym_like_store(self) -> StructuredArtifactStore:
        return _full_store(schedule_tasks={"A社": [
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "sheet1", "row_number": 11,
             "values": {"タスクID": "T09", "フェーズ": "3. 探索的分析・仮説整理", "タスク名": "基準不良率・単変量分析", "担当者": "山本 彩乃"}},
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "sheet1", "row_number": 12,
             "values": {"タスクID": "T10", "フェーズ": "3. 探索的分析・仮説整理", "タスク名": "セグメント別分析", "担当者": "山本 彩乃 / 藤田 彩"}},
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "sheet1", "row_number": 20,
             "values": {"タスクID": "T16", "フェーズ": "5. モデル構築", "タスク名": "学習実行", "担当者": "斎藤 悠斗"}},
            # ヘッダ行の残骸（値==列名）はマッチさせない
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "sheet1", "row_number": 2,
             "values": {"タスクID": "タスクID", "フェーズ": "フェーズ", "担当者": "担当者"}},
        ]})

    def test_numbered_phase_value_matches_question_without_number(self) -> None:
        docs = build_spreadsheet_state_context(
            "探索的分析・仮説整理フェーズに一致するタスクIDをすべて挙げてください。", "A社", self._aym_like_store()
        )
        texts = "\n".join(d.document.text for d in docs)
        assert "T09" in texts
        assert "T10" in texts
        assert "T16" not in texts

    def test_phase_key_without_mei_suffix_is_recognized(self) -> None:
        """列名が「フェーズ名」でなく「フェーズ」でもマッチ対象になる。"""
        docs = build_spreadsheet_state_context(
            "モデル構築フェーズのタスクIDを教えてください。", "A社", self._aym_like_store()
        )
        texts = "\n".join(d.document.text for d in docs)
        assert "T16" in texts
        assert "T09" not in texts

    def test_compound_assignee_value_matches_single_person_question(self) -> None:
        docs = build_spreadsheet_state_context(
            "藤田 彩さんが担当しているタスクIDを教えてください。", "A社", self._aym_like_store()
        )
        texts = "\n".join(d.document.text for d in docs)
        assert "T10" in texts
        assert "T09" not in texts

    def test_header_echo_row_is_not_matched(self) -> None:
        docs = build_spreadsheet_state_context(
            "フェーズと担当者とタスクIDの一覧を教えてください。", "A社", self._aym_like_store()
        )
        assert all("row_2" not in d.document.location for d in docs)


class TestOfficeStyleHighlightAndNarrowing:
    """docxのhighlight_colorキー対応と、質問中のヒント（拡張子・ファイル名・ページ番号）
    によるコンテキスト絞り込み。"""

    def _mark(self, **over) -> dict:
        base = {
            "source_path": "x/提案書.pptx", "file_name": "提案書.pptx", "extension": ".pptx",
            "slide_number": 1, "text": "テキスト", "bold": False, "italic": False,
            "underline": False, "font_color": None, "fill_color": None, "highlight_color": None,
        }
        base.update(over)
        return base

    def test_docx_highlight_color_key_is_matched(self):
        store = _store_with_marks([
            self._mark(file_name="M02.docx", extension=".docx", slide_number=None,
                       text="黄色ハイライトの一文", highlight_color="YELLOW (7)"),
            self._mark(file_name="M02.docx", extension=".docx", slide_number=None,
                       text="無印の一文"),
        ])
        docs = build_office_style_context(
            "M02資料（docx）において、黄色でハイライトされている部分をすべて抜き出してください。", "A社", store
        )
        texts = [d.document.text for d in docs]
        assert any("黄色ハイライトの一文" in t for t in texts)
        assert not any("無印の一文" in t for t in texts)

    def test_extension_hint_restricts_to_matching_files(self):
        store = _store_with_marks([
            self._mark(file_name="M02.docx", extension=".docx", slide_number=None,
                       text="docxの黄色", highlight_color="YELLOW (7)"),
            self._mark(text="pptxの黄色", fill_color="FFFF00"),
        ])
        docs = build_office_style_context(
            "M02資料（docx）において、黄色でハイライトされている部分を抜き出してください。", "A社", store
        )
        texts = [d.document.text for d in docs]
        assert any("docxの黄色" in t for t in texts)
        assert not any("pptxの黄色" in t for t in texts)

    def test_page_number_hint_restricts_slides(self):
        store = _store_with_marks([
            self._mark(slide_number=7, text="7ページの赤字", font_color="FF0000"),
            self._mark(slide_number=2, text="2ページの赤字", font_color="FF0000"),
        ])
        docs = build_office_style_context(
            "提案書P7において、赤で強調されている箇所の文字列を抜き出してください。", "A社", store
        )
        texts = [d.document.text for d in docs]
        assert any("7ページの赤字" in t for t in texts)
        assert not any("2ページの赤字" in t for t in texts)

    def test_file_stem_hint_restricts_files(self):
        store = _store_with_marks([
            self._mark(text="提案書の赤字", font_color="FF0000"),
            self._mark(file_name="最終報告.pptx", source_path="x/最終報告.pptx",
                       text="最終報告の赤字", font_color="FF0000"),
        ])
        docs = build_office_style_context(
            "提案書において赤で強調されている箇所を抜き出してください。", "A社", store
        )
        texts = [d.document.text for d in docs]
        assert any("提案書の赤字" in t for t in texts)
        assert not any("最終報告の赤字" in t for t in texts)

    def test_hints_do_not_empty_out_results_when_nothing_matches_hint(self):
        """ヒントで絞った結果が0件になる場合は絞り込みを適用しない（安全側）。"""
        store = _store_with_marks([
            self._mark(slide_number=2, text="2ページの赤字", font_color="FF0000"),
        ])
        docs = build_office_style_context(
            "P99において赤で強調されている箇所を抜き出してください。", "A社", store
        )
        assert len(docs) == 1


class TestOfficeStyleContextSelfDescription:
    """LLMに渡すdocument textに「どの装飾に一致したか」を明記する。
    生のrun断片だけだと、LLMがそれをハイライト箇所と確信できずゲートしてしまう。"""

    def test_highlight_match_text_describes_decoration(self):
        store = _store_with_marks([
            {"source_path": "x/M02.docx", "file_name": "M02.docx", "extension": ".docx",
             "slide_number": None, "text": "見込金額（税込）", "bold": False, "italic": False,
             "underline": False, "font_color": None, "fill_color": None,
             "highlight_color": "YELLOW (7)"},
        ])
        docs = build_office_style_context(
            "M02資料（docx）において、黄色でハイライトされている部分を抜き出してください。", "A社", store
        )
        assert len(docs) == 1
        text = docs[0].document.text
        assert "見込金額（税込）" in text
        assert "黄色" in text and "ハイライト" in text  # 装飾の説明が含まれる

    def test_bold_match_text_describes_decoration(self):
        store = _store_with_marks([
            {"source_path": "x/契約書.docx", "file_name": "契約書.docx", "extension": ".docx",
             "slide_number": None, "text": "重要条項", "bold": True, "italic": False,
             "underline": False, "font_color": None, "fill_color": None},
        ])
        docs = build_office_style_context("契約書で太字の箇所を抽出してください。", "A社", store)
        assert "太字" in docs[0].document.text


def _store(kind_data: dict[str, list[dict]]) -> StructuredArtifactStore:
    by_kind = {kind: {"テスト案件": rows} for kind, rows in kind_data.items()}
    return StructuredArtifactStore(by_kind_and_project=by_kind)


def test_filter_condition_from_train_xlsx_filter_columns():
    store = _store({
        "train_xlsx_sheets": [{
            "source_path": "data/raw/x/train.xlsx", "file_name": "train.xlsx",
            "sheet_name": "train", "auto_filter_ref": "A1:J100", "hidden_row_count": 90,
            "filter_columns": [
                {"col_id": 1, "header": "gender", "values": ["Male"], "custom": []},
                {"col_id": 3, "header": "country", "values": ["India"], "custom": []},
            ],
        }],
    })
    docs = build_spreadsheet_state_context(
        "train.xlsxのtrainシートでフィルターで抽出されている条件を教えてください。", "テスト案件", store)
    assert len(docs) == 1
    text = docs[0].document.text
    assert "gender" in text and "Male" in text
    assert "country" in text and "India" in text
    assert "90" in text  # 非表示行数


def test_filter_condition_renders_custom_filters():
    store = _store({
        "train_xlsx_sheets": [{
            "source_path": "data/raw/x/train.xlsx", "file_name": "train.xlsx",
            "sheet_name": "train", "auto_filter_ref": "A1:B10", "hidden_row_count": 5,
            "filter_columns": [
                {"col_id": 0, "header": "age", "values": [],
                 "custom": [{"operator": "greaterThan", "val": "30"}]},
            ],
        }],
    })
    docs = build_spreadsheet_state_context("フィルタの条件は？", "テスト案件", store)
    assert "age" in docs[0].document.text
    assert "greaterThan" in docs[0].document.text and "30" in docs[0].document.text


def test_pivot_argmax_row_selected():
    """「最も高い」質問で、質問に現れる列見出しのargmax行がdoc化される。"""
    cells = []
    header = {"A3": "層", "B3": "平均 / ALP", "C3": "平均 / bmi"}
    rows = {4: ("20代", "10.5", "1.0"), 5: ("30代", "99.9", "2.0"), 6: ("40代", "50.0", "3.0")}
    for cell, v in header.items():
        cells.append({"sheet_name": "Pivot", "file_name": "train.xlsx",
                      "source_path": "data/raw/x/train.xlsx", "cell": cell, "row": 3, "value": v})
    for row, (label, alp, bmi) in rows.items():
        for col, v in zip("ABC", (label, alp, bmi)):
            cells.append({"sheet_name": "Pivot", "file_name": "train.xlsx",
                          "source_path": "data/raw/x/train.xlsx", "cell": f"{col}{row}", "row": row, "value": v})
    store = _store({"train_xlsx_small_sheet_cells": cells})
    docs = build_spreadsheet_state_context(
        "PivotシートでALPの平均が最も高いものの抽出条件は？", "テスト案件", store)
    assert len(docs) >= 1
    text = docs[0].document.text
    assert "30代" in text          # argmax行のラベル
    assert "99.9" in text
    assert "平均 / ALP" in text    # どの列で判定したか


def test_pivot_argmax_forward_fills_merged_label_columns():
    """マージセル由来で疎なラベル列は直前の非空値を引き継いでargmax行docに含める。
    数値の集計列は空欄でもfillしない（値の捏造になるため）。"""
    cells = []
    header = {"A3": "性別", "B3": "層", "C3": "平均 / ALP", "D3": "平均 / bmi"}
    data = {
        4: {"A": "Male", "B": "20代", "C": "10.5", "D": "1.0"},
        5: {"B": "30代", "C": "99.9"},  # A列はマージセルで空、D列は欠損
        6: {"A": "Female", "B": "40代", "C": "50.0", "D": "3.0"},
    }
    for cell, v in header.items():
        cells.append({"sheet_name": "Pivot", "file_name": "train.xlsx",
                      "source_path": "data/raw/x/train.xlsx", "cell": cell, "row": 3, "value": v})
    for row, cols in data.items():
        for col, v in cols.items():
            cells.append({"sheet_name": "Pivot", "file_name": "train.xlsx",
                          "source_path": "data/raw/x/train.xlsx", "cell": f"{col}{row}", "row": row, "value": v})
    store = _store({"train_xlsx_small_sheet_cells": cells})
    docs = build_spreadsheet_state_context(
        "PivotシートでALPの平均が最も高いものの抽出条件は？", "テスト案件", store)
    assert len(docs) >= 1
    text = docs[0].document.text
    assert "性別=Male" in text        # マージセルのラベルがforward-fillされている
    assert "30代" in text and "99.9" in text
    assert "平均 / bmi=1.0" not in text  # 数値集計列は捏造fillしない


def test_pivot_argmax_does_not_fill_sparse_numeric_aggregate_column():
    """欠損セルを含む数値の集計列はラベル列と誤判定せず、forward-fillで
    実データに存在しない数値を捏造しない（回帰テスト）。
    argmax行はラベル列（マージセル）も集計列Bも空欄 — ラベルはfillされるが
    集計値はfillされてはならない。"""
    cells = []
    header = {"A3": "性別", "B3": "平均 / ALP", "C3": "平均 / bmi"}
    data = {
        4: {"A": "Male", "B": "10.5", "C": "1.0"},
        5: {"C": "99.9"},  # A列はマージセルで空、B列（集計列）は欠損
        6: {"A": "Female", "B": "50.0", "C": "3.0"},
    }
    for cell, v in header.items():
        cells.append({"sheet_name": "Pivot", "file_name": "train.xlsx",
                      "source_path": "data/raw/x/train.xlsx", "cell": cell, "row": 3, "value": v})
    for row, cols in data.items():
        for col, v in cols.items():
            cells.append({"sheet_name": "Pivot", "file_name": "train.xlsx",
                          "source_path": "data/raw/x/train.xlsx", "cell": f"{col}{row}", "row": row, "value": v})
    store = _store({"train_xlsx_small_sheet_cells": cells})
    docs = build_spreadsheet_state_context(
        "Pivotシートでbmiの平均が最も高いものの抽出条件は？", "テスト案件", store)
    assert len(docs) >= 1
    text = docs[0].document.text
    assert "性別=Male" in text and "99.9" in text  # ラベルのfillは維持される
    assert "平均 / ALP=10.5" not in text           # 直前行の集計値を捏造fillしていない


def test_pivot_argmax_no_matching_column_returns_nothing():
    store = _store({"train_xlsx_small_sheet_cells": [
        {"sheet_name": "Pivot", "file_name": "train.xlsx", "source_path": "x",
         "cell": "A1", "row": 1, "value": "層"},
    ]})
    docs = build_spreadsheet_state_context("XYZの平均が最も高いのは？", "テスト案件", store)
    assert docs == []
