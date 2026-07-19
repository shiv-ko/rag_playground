"""構造化コンテキストビルダーのテスト。"""
from __future__ import annotations

from src.retriever.structured_context import (
    build_office_style_context,
    build_spreadsheet_state_context,
    build_version_diff_context,
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
        "train_xlsx_pivot_aggregates": {},
        "version_diff_pairs": {},
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


def test_multiple_color_conditions_require_all_to_match_same_mark() -> None:
    """「黄色ハイライトかつ赤字」のような複数条件の質問は、両方を同時に満たす
    マークのみを返す（従来はどちらか一方だけでもOR和集合でヒットしていた）。"""
    store = _store_with_marks([
        {"source_path": "x/報告資料.docx", "file_name": "報告資料.docx", "slide_number": None,
         "text": "両方一致", "bold": False, "italic": False, "underline": False,
         "font_color": "FF0000", "fill_color": None, "highlight_color": "YELLOW (7)"},
        {"source_path": "x/報告資料.docx", "file_name": "報告資料.docx", "slide_number": None,
         "text": "黄色のみ", "bold": False, "italic": False, "underline": False,
         "font_color": None, "fill_color": None, "highlight_color": "YELLOW (7)"},
        {"source_path": "x/報告資料.docx", "file_name": "報告資料.docx", "slide_number": None,
         "text": "赤字のみ", "bold": False, "italic": False, "underline": False,
         "font_color": "FF0000", "fill_color": None, "highlight_color": None},
    ])
    docs = build_office_style_context(
        "資料において黄色ハイライトかつ赤字となっている部分を抜き出してください。", "A社", store
    )
    texts = [d.document.text for d in docs]
    assert any("両方一致" in t for t in texts)
    assert not any("黄色のみ" in t for t in texts)
    assert not any("赤字のみ" in t for t in texts)


def test_multiple_style_conditions_require_all_true() -> None:
    """「太字、下線、イタリックのすべてに該当する」は3条件すべてを満たすマークのみ。"""
    store = _store_with_marks([
        {"source_path": "x/a.pptx", "file_name": "a.pptx", "slide_number": 1,
         "text": "全部該当", "bold": True, "italic": True, "underline": True,
         "font_color": None, "fill_color": None},
        {"source_path": "x/a.pptx", "file_name": "a.pptx", "slide_number": 1,
         "text": "太字のみ", "bold": True, "italic": False, "underline": False,
         "font_color": None, "fill_color": None},
    ])
    docs = build_office_style_context(
        "太字、下線、イタリックのすべてに該当する箇所を抽出してください。", "A社", store
    )
    texts = [d.document.text for d in docs]
    assert any("全部該当" in t for t in texts)
    assert not any("太字のみ" in t for t in texts)


def test_english_red_keyword_is_recognized_as_color_condition() -> None:
    """色名の英語表記（RED）も一般語彙として色条件に認識される。"""
    store = _store_with_marks([
        {"source_path": "x/a.pptx", "file_name": "a.pptx", "slide_number": 1,
         "text": "英語表記の赤", "bold": False, "italic": False, "underline": False,
         "font_color": "FF0000", "fill_color": None},
        {"source_path": "x/a.pptx", "file_name": "a.pptx", "slide_number": 1,
         "text": "無関係", "bold": False, "italic": False, "underline": False,
         "font_color": "1A1A1A", "fill_color": None},
    ])
    docs = build_office_style_context("REDになっている数値を挙げてください。", "A社", store)
    texts = [d.document.text for d in docs]
    assert any("英語表記の赤" in t for t in texts)
    assert not any("無関係" in t for t in texts)


def test_bare_color_kanji_in_project_name_does_not_add_spurious_color_condition() -> None:
    """案件名に色を表す1文字漢字（「青」「緑」等）が偶然含まれることがある
    （例: 「青〜」で始まる社名）。単独の1文字を無条件に色条件として拾うと、
    AND判定で無関係な色条件が紛れ込み、本来一致すべきマークまで除外されてしまう。
    色条件は「色」「で」「字」等の修飾を伴う形でのみ認識する。"""
    store = _store_with_marks([
        {"source_path": "x/報告資料.docx", "file_name": "報告資料.docx", "slide_number": None,
         "text": "黄色ハイライトかつ赤字の箇所", "bold": False, "italic": False, "underline": False,
         "font_color": "FF0000", "fill_color": None, "highlight_color": "YELLOW (7)"},
    ])
    # 「青空商事」のように社名に色の1文字（青）が含まれるが、質問の装飾条件は
    # 「黄色ハイライトかつ赤字」のみで「青」に関する条件は本来含まれない。
    docs = build_office_style_context(
        "青空商事の中間報告資料にて、黄色ハイライトかつ赤字となっている部分を抜き出してください。",
        "A社",
        store,
    )
    texts = [d.document.text for d in docs]
    assert any("黄色ハイライトかつ赤字の箇所" in t for t in texts)


def test_or_conjunction_returns_union_not_and() -> None:
    """「または」のような選言（OR）の質問は、従来どおり和集合を返す。
    AND化がすべての複数条件に無条件適用されると、OR質問がAND扱いされて
    0件になり、構造化の恩恵が丸ごと失われてしまう（回帰テスト）。"""
    store = _store_with_marks([
        {"source_path": "x/報告資料.docx", "file_name": "報告資料.docx", "slide_number": None,
         "text": "黄色のみ", "bold": False, "italic": False, "underline": False,
         "font_color": None, "fill_color": None, "highlight_color": "YELLOW (7)"},
        {"source_path": "x/報告資料.docx", "file_name": "報告資料.docx", "slide_number": None,
         "text": "赤字のみ", "bold": False, "italic": False, "underline": False,
         "font_color": "FF0000", "fill_color": None, "highlight_color": None},
        {"source_path": "x/報告資料.docx", "file_name": "報告資料.docx", "slide_number": None,
         "text": "どちらでもない", "bold": False, "italic": False, "underline": False,
         "font_color": None, "fill_color": None, "highlight_color": None},
    ])
    docs = build_office_style_context(
        "黄色ハイライトまたは赤字になっている箇所を抜き出してください。", "A社", store
    )
    texts = [d.document.text for d in docs]
    assert any("黄色のみ" in t for t in texts)
    assert any("赤字のみ" in t for t in texts)
    assert not any("どちらでもない" in t for t in texts)


def test_ambiguous_conjunction_without_marker_defaults_to_union() -> None:
    """明示的な連言マーカー（かつ/両方/すべて/同時に）もOR系マーカーも無い場合は、
    従来どおり和集合として扱う（安全側デフォルト）。"""
    store = _store_with_marks([
        {"source_path": "x/報告資料.docx", "file_name": "報告資料.docx", "slide_number": None,
         "text": "黄色のみ", "bold": False, "italic": False, "underline": False,
         "font_color": None, "fill_color": None, "highlight_color": "YELLOW (7)"},
    ])
    docs = build_office_style_context(
        "黄色ハイライトと赤字になっている箇所を抜き出してください。", "A社", store
    )
    texts = [d.document.text for d in docs]
    assert any("黄色のみ" in t for t in texts)


def test_adjective_color_forms_are_recognized() -> None:
    """修飾形（「赤い」「赤の」「青い」「青の」「緑の」等）は色条件として認識される
    （1文字裸の色漢字を条件外にした際に、こうした自然な修飾形まで後退しないこと
    の回帰テスト。社名等との誤爆防止のため1文字裸自体は引き続き対象外）。"""
    store_red = _store_with_marks([
        {"source_path": "x/a.pptx", "file_name": "a.pptx", "slide_number": 1,
         "text": "赤い文字の警告", "bold": False, "italic": False, "underline": False,
         "font_color": "FF0000", "fill_color": None},
    ])
    assert any(
        "赤い文字の警告" in d.document.text
        for d in build_office_style_context("赤い文字になっている箇所を挙げてください。", "A社", store_red)
    )
    assert any(
        "赤い文字の警告" in d.document.text
        for d in build_office_style_context("赤の文字になっている箇所を挙げてください。", "A社", store_red)
    )

    store_blue = _store_with_marks([
        {"source_path": "x/a.pptx", "file_name": "a.pptx", "slide_number": 1,
         "text": "青い文字の注記", "bold": False, "italic": False, "underline": False,
         "font_color": "0000FF", "fill_color": None},
    ])
    assert any(
        "青い文字の注記" in d.document.text
        for d in build_office_style_context("青い文字になっている箇所を挙げてください。", "A社", store_blue)
    )
    assert any(
        "青い文字の注記" in d.document.text
        for d in build_office_style_context("青の文字になっている箇所を挙げてください。", "A社", store_blue)
    )

    store_green = _store_with_marks([
        {"source_path": "x/a.pptx", "file_name": "a.pptx", "slide_number": 1,
         "text": "緑の文字の注記", "bold": False, "italic": False, "underline": False,
         "font_color": "008000", "fill_color": None},
    ])
    assert any(
        "緑の文字の注記" in d.document.text
        for d in build_office_style_context("緑の文字になっている箇所を挙げてください。", "A社", store_green)
    )


def test_color_keyword_matching_is_casefold_and_fullwidth_normalized() -> None:
    """「red」「Red」「ＲＥＤ」のような大小文字・全角差異は同一の色条件として
    正規化して照合する（classify_question側は既にlower()で吸収しているため、
    この関数側でも表記ゆれを不統一に扱わないよう揃える）。"""
    store = _store_with_marks([
        {"source_path": "x/a.pptx", "file_name": "a.pptx", "slide_number": 1,
         "text": "英語表記の赤", "bold": False, "italic": False, "underline": False,
         "font_color": "FF0000", "fill_color": None},
    ])
    for phrasing in ("redになっている数値を挙げてください。", "Redになっている数値を挙げてください。", "ＲＥＤになっている数値を挙げてください。"):
        docs = build_office_style_context(phrasing, "A社", store)
        texts = [d.document.text for d in docs]
        assert any("英語表記の赤" in t for t in texts), f"failed for: {phrasing}"


def test_single_condition_behavior_unchanged_when_multiple_marks_partially_match() -> None:
    """後方互換性: 単一条件の場合は従来どおり、その1条件を満たすマークのみを返す
    （AND化の副作用で単一条件時の挙動が変わらないことの回帰テスト）。"""
    store = _store_with_marks([
        {"source_path": "x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 1,
         "text": "黄色のみ一致", "bold": False, "italic": False, "underline": False,
         "font_color": None, "fill_color": None, "highlight_color": "YELLOW (7)"},
    ])
    docs = build_office_style_context(
        "黄色でハイライトされている部分を抜き出してください。", "A社", store
    )
    texts = [d.document.text for d in docs]
    assert any("黄色のみ一致" in t for t in texts)


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

    def test_distinct_highlight_ranges_on_same_sheet_are_not_deduplicated(self) -> None:
        store = _full_store(train_xlsx_highlight_blocks={"A社": [
            {
                "source_path": "data/raw/x/train.xlsx", "sheet_name": "train", "range": "A2:C2",
                "fill_color_name": "yellow", "first_value": "row-a",
                "column_headers": [{"cell": "A1", "value": "id", "formula": None}],
                "same_row_values": [{"cell": "A2", "value": "row-a", "formula": None}],
            },
            {
                "source_path": "data/raw/x/train.xlsx", "sheet_name": "train", "range": "D2:F2",
                "fill_color_name": "yellow", "first_value": "10",
                "column_headers": [{"cell": "D1", "value": "score", "formula": None}],
                "same_row_values": [{"cell": "D2", "value": "10", "formula": None}],
            },
        ]})

        docs = build_spreadsheet_state_context(
            "train.xlsxで黄色ハイライトが交差するセルを教えてください。", "A社", store
        )

        assert len(docs) == 2
        assert {doc.document.location for doc in docs} == {
            "sheet_train_range_A2:C2",
            "sheet_train_range_D2:F2",
        }

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


class TestSpreadsheetStateSheetAndFileScoping:
    """質問文中のシート名・ファイル名ヒントでxlsxハイライト系候補を絞り込む
    （office_style側の_narrow_marks_by_question_hintsと対称の設計）。
    「対象が実在するか」の判定はtrain_xlsx_sheets/schedule_tasksの全件
    （ハイライトの有無を問わない）を基準にする — train_xlsx_highlight_blocks
    自体はtrain.xlsx以外のファイルを一切含まないため、それ単体では
    「質問が別の実在ファイルを名指ししている」ケースを検出できないため。"""

    def test_sheet_name_hint_narrows_highlight_blocks_to_named_sheet(self) -> None:
        store = _full_store(
            train_xlsx_sheets={"A社": [
                {"source_path": "data/x/train.xlsx", "file_name": "train.xlsx", "sheet_name": "Sheet1"},
                {"source_path": "data/x/train.xlsx", "file_name": "train.xlsx", "sheet_name": "Sheet2"},
            ]},
            train_xlsx_highlight_blocks={"A社": [
                {"source_path": "data/x/train.xlsx", "sheet_name": "Sheet1", "range": "A1",
                 "fill_color_name": "yellow", "first_value": "sheet1-value"},
                {"source_path": "data/x/train.xlsx", "sheet_name": "Sheet2", "range": "B2",
                 "fill_color_name": "yellow", "first_value": "sheet2-value"},
            ]},
        )
        docs = build_spreadsheet_state_context(
            "train.xlsxのSheet2で黄色にハイライトされたセルの抽出条件を教えてください。", "A社", store
        )
        texts = [d.document.text for d in docs]
        assert any("sheet2-value" in t for t in texts)
        assert not any("sheet1-value" in t for t in texts)

    def test_file_name_hint_excludes_train_xlsx_when_different_file_named(self) -> None:
        """質問がプロジェクト内の別の実在ファイル（スケジュール.xlsx）を名指しして
        いる場合、train_xlsx_highlight_blocks（train.xlsx由来）は混入させない。"""
        store = _full_store(
            train_xlsx_highlight_blocks={"A社": [
                {"source_path": "data/x/train.xlsx", "sheet_name": "Sheet1", "range": "A1",
                 "fill_color_name": "yellow", "first_value": "train-value"},
            ]},
            schedule_tasks={"A社": [
                {"source_path": "data/x/スケジュール.xlsx", "file_name": "スケジュール.xlsx",
                 "sheet_name": "WBSタスク一覧", "row_number": 2, "dominant_row_fill": None,
                 "values": {"タスクID": "T01"}},
            ]},
        )
        docs = build_spreadsheet_state_context(
            "スケジュール.xlsxにおいて、オレンジ色にハイライトされている行のタスクIDを教えてください。",
            "A社", store,
        )
        assert not any("train-value" in d.document.text for d in docs)

    def test_unmatched_sheet_hint_falls_back_to_original_candidates(self) -> None:
        """質問中のシート名ヒントがプロジェクト内のどの既知シートとも一致しない
        （表記ゆれ・誤ヒント）場合、絞り込みを適用せず従来候補を維持する。"""
        store = _full_store(
            train_xlsx_sheets={"A社": [
                {"source_path": "data/x/train.xlsx", "file_name": "train.xlsx", "sheet_name": "Sheet1"},
            ]},
            train_xlsx_highlight_blocks={"A社": [
                {"source_path": "data/x/train.xlsx", "sheet_name": "Sheet1", "range": "A1",
                 "fill_color_name": "yellow", "first_value": "sheet1-value"},
            ]},
        )
        docs = build_spreadsheet_state_context(
            "train.xlsxのSheet9で黄色にハイライトされたセルを教えてください。", "A社", store
        )
        assert any("sheet1-value" in d.document.text for d in docs)

    def test_sheet_name_that_is_substring_of_named_file_is_not_treated_as_hint(self) -> None:
        """シート名がファイル名（拡張子抜き）に含まれる場合（例: シート名"工程"と
        ファイル"工程_r2.xlsx"）、ファイル名の言及とシート名の言及を区別できない
        ため、シート名ヒントとしては扱わない（ファイル名絞り込みのみ適用）。"""
        store = _full_store(schedule_tasks={"A社": [
            {"source_path": "data/x/02.計画/工程_r2.xlsx", "file_name": "工程_r2.xlsx",
             "sheet_name": "工程", "row_number": 2, "dominant_row_fill": "F2E0D0",
             "values": {"タスクID": "T02", "タスク名": "要件整理"}},
            {"source_path": "data/x/02.計画/工程_r2.xlsx", "file_name": "工程_r2.xlsx",
             "sheet_name": "サブ工程", "row_number": 3, "dominant_row_fill": "F2E0D0",
             "values": {"タスクID": "T03", "タスク名": "詳細設計"}},
        ]})
        docs = build_spreadsheet_state_context(
            "工程_r2.xlsxにおいて、オレンジにハイライトされている行のタスクIDは？", "A社", store
        )
        texts = "\n".join(d.document.text for d in docs)
        assert "T02" in texts
        assert "T03" in texts  # sheet_name「工程」はfile_stemの部分文字列なのでシートヒントとして誤発火しない

    def test_no_hint_question_leaves_multi_sheet_candidates_unchanged(self) -> None:
        """質問文にシート名・別ファイル名ヒントが一切無い場合は、既知シート/
        ファイル情報が利用可能でも従来どおり全候補を返す（後方互換）。"""
        store = _full_store(
            train_xlsx_sheets={"A社": [
                {"source_path": "data/x/train.xlsx", "file_name": "train.xlsx", "sheet_name": "Sheet1"},
                {"source_path": "data/x/train.xlsx", "file_name": "train.xlsx", "sheet_name": "Sheet2"},
            ]},
            train_xlsx_highlight_blocks={"A社": [
                {"source_path": "data/x/train.xlsx", "sheet_name": "Sheet1", "range": "A1",
                 "fill_color_name": "yellow", "first_value": "sheet1-value"},
                {"source_path": "data/x/train.xlsx", "sheet_name": "Sheet2", "range": "B2",
                 "fill_color_name": "yellow", "first_value": "sheet2-value"},
            ]},
        )
        docs = build_spreadsheet_state_context(
            "train.xlsxで黄色にハイライトされたセルをすべて教えてください。", "A社", store
        )
        texts = "\n".join(d.document.text for d in docs)
        assert "sheet1-value" in texts
        assert "sheet2-value" in texts

    def test_sheet_name_hint_matching_is_nfc_and_casefold_normalized(self) -> None:
        """シート名ヒントの照合はNFC正規化・casefoldを適用する（全角英数等の
        表記ゆれを吸収する）。"""
        store = _full_store(
            train_xlsx_sheets={"A社": [
                {"source_path": "data/x/train.xlsx", "file_name": "train.xlsx", "sheet_name": "Sheet1"},
                {"source_path": "data/x/train.xlsx", "file_name": "train.xlsx", "sheet_name": "Sheet2"},
            ]},
            train_xlsx_highlight_blocks={"A社": [
                {"source_path": "data/x/train.xlsx", "sheet_name": "Sheet1", "range": "A1",
                 "fill_color_name": "yellow", "first_value": "sheet1-value"},
                {"source_path": "data/x/train.xlsx", "sheet_name": "Sheet2", "range": "B2",
                 "fill_color_name": "yellow", "first_value": "sheet2-value"},
            ]},
        )
        docs = build_spreadsheet_state_context(
            "train.xlsxのＳｈｅｅｔ２で黄色にハイライトされたセルを教えてください。", "A社", store
        )
        texts = [d.document.text for d in docs]
        assert any("sheet2-value" in t for t in texts)
        assert not any("sheet1-value" in t for t in texts)


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

    def test_non_whitelisted_column_name_matches_by_value(self) -> None:
        """列名ホワイトリストの当初4種（フェーズ/担当/ステータス/成果物）に含まれない
        拡張後の列名（例: 種別）でも、値が質問文に現れれば行をマッチさせる。"""
        store = _full_store(schedule_tasks={"A社": [
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "sheet1", "row_number": 5,
             "values": {"タスクID": "T30", "種別": "バッファ", "工数(h)": "2"}},
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "sheet1", "row_number": 6,
             "values": {"タスクID": "T31", "種別": "レビュー", "工数(h)": "3"}},
        ]})
        docs = build_spreadsheet_state_context(
            "バッファに該当するタスクIDと工数を教えてください。", "A社", store
        )
        texts = "\n".join(d.document.text for d in docs)
        assert "T30" in texts
        assert "T31" not in texts

    def test_extended_synonym_columns_match_by_value(self) -> None:
        """種別以外にも、タスク・マイルストーン・回次といった類義の列名（未知の
        スケジュール表で一般的に現れる分類・識別用の列名）が値一致でマッチする。
        列名を無制限に許すのではなく、この一般語彙リストの範囲で汎用化する設計。"""
        store = _full_store(schedule_tasks={"A社": [
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "WBS", "row_number": 3,
             "values": {"タスクID": "T50", "タスク名": "モデル改善実験"}},
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "WBS", "row_number": 4,
             "values": {"タスクID": "T51", "関連マイルストーン": "MS3"}},
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "WBS", "row_number": 5,
             "values": {"タスクID": "T52", "回次/ID": "CP2"}},
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "WBS", "row_number": 6,
             "values": {"タスクID": "T53", "タスク名": "無関係の作業"}},
        ]})
        docs = build_spreadsheet_state_context(
            "モデル改善実験というタスク、MS3に関連するタスク、CP2に関連するタスクの"
            "タスクIDをそれぞれ教えてください。",
            "A社", store,
        )
        texts = "\n".join(d.document.text for d in docs)
        assert "T50" in texts
        assert "T51" in texts
        assert "T52" in texts
        assert "T53" not in texts

    def test_header_echo_row_not_matched_for_non_whitelisted_column(self) -> None:
        """拡張後の列名（当初のホワイトリスト4種以外）でも、値==列名のヘッダ行残骸は除外される。"""
        store = _full_store(schedule_tasks={"A社": [
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "sheet1", "row_number": 2,
             "values": {"タスクID": "タスクID", "種別": "種別"}},
        ]})
        docs = build_spreadsheet_state_context(
            "種別の一覧を教えてください。", "A社", store
        )
        assert docs == []

    def test_column_name_outside_generic_vocabulary_is_not_matched(self) -> None:
        """一般語彙リストに含まれない列名（例: 工数、確認欄のような数値・自由記述の列）は
        値一致の対象にしない。列名を問わず全列を対象にすると、質問と無関係な列の値が
        誤って行マッチの根拠になってしまう（Incorrect回答のリスクを高める）ため。"""
        store = _full_store(schedule_tasks={"A社": [
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "sheet1", "row_number": 7,
             "values": {"タスクID": "T60", "タスク名": "初期設計", "工数(h)": "18", "ステータス": "未着手"}},
        ]})
        docs = build_spreadsheet_state_context(
            "7月18日時点で完了しているタスクIDを教えてください。", "A社", store
        )
        assert docs == []

    def test_purely_numeric_value_is_not_matched_even_in_whitelisted_column(self) -> None:
        """一般語彙リストに含まれる列名（例: ステータスコード）であっても、値が数値のみ
        （ステータスコード等の識別番号）の場合は、質問文中の無関係な数字（日付等）との
        偶然の部分一致で行マッチの根拠にしない。列名一致だけでは誤マッチを防げないため、
        値側にも数値単独除外という独立した安全条件を設ける。"""
        store = _full_store(schedule_tasks={"A社": [
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "sheet1", "row_number": 8,
             "values": {"タスクID": "T61", "タスク名": "設計レビュー", "ステータスコード": "18"}},
        ]})
        docs = build_spreadsheet_state_context(
            "7月18日に予定されているタスクIDを教えてください。", "A社", store
        )
        assert docs == []

    def test_generic_status_word_in_unrelated_column_does_not_shadow_authoritative_status(self) -> None:
        """本来の状態を表す列（ステータス）は「未着手」なのに、無関係な自由記述列
        （確認欄）に紛れ込んだ汎用語「完了」だけで行を完了扱いにしない。列名が
        一般語彙リストの対象外である以上、値が一致しても行マッチの根拠にしない。"""
        store = _full_store(schedule_tasks={"A社": [
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "sheet1", "row_number": 9,
             "values": {"タスクID": "T62", "フェーズ": "検証", "ステータス": "未着手", "確認欄": "完了"}},
        ]})
        docs = build_spreadsheet_state_context(
            "レビューが完了したフェーズを教えてください。", "A社", store
        )
        assert docs == []


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
    argmax行はラベル列（マージセル）も集計列Cも空欄 — ラベルはfillされるが
    集計値はfillされてはならない。層列で行の同一性は一意（compact階層ガード非発火）。"""
    cells = []
    header = {"A3": "性別", "B3": "層", "C3": "平均 / ALP", "D3": "平均 / bmi"}
    data = {
        4: {"A": "Male", "B": "20代", "C": "10.5", "D": "1.0"},
        5: {"B": "30代", "D": "99.9"},  # A列はマージセルで空、C列（集計列）は欠損
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
        "Pivotシートでbmiの平均が最も高いものの抽出条件は？", "テスト案件", store)
    assert len(docs) >= 1
    text = docs[0].document.text
    assert "性別=Male" in text and "99.9" in text  # ラベルのfillは維持される
    assert "平均 / ALP=10.5" not in text           # 直前行の集計値を捏造fillしていない


def test_pivot_argmax_abstains_on_compact_hierarchical_pivot():
    """階層を1列に畳み込んだcompactレイアウトのpivot（ラベルタプルがデータ行間で重複）では
    行単独で完全な抽出条件を復元できないため、docを出さない（部分条件の回答は
    official規則「部分一致はIncorrect」で-1になる — 実測valid Q21）。"""
    cells = []
    header = {"A3": "行ラベル", "B3": "平均 / MonthlyIncome"}
    # 「Human Resources」が別ブロック（親階層違い）で重複出現するcompact pivot
    data = {
        4: {"A": "Female", "B": "7216.2"},
        5: {"A": "Human Resources", "B": "9140"},
        6: {"A": "Male", "B": "6835.7"},
        7: {"A": "Human Resources", "B": "17328"},
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
        "PivotシートでMonthlyIncomeの平均が最も高い層の抽出条件は？", "テスト案件", store)
    assert docs == []


def test_pivot_argmax_no_matching_column_returns_nothing():
    store = _store({"train_xlsx_small_sheet_cells": [
        {"sheet_name": "Pivot", "file_name": "train.xlsx", "source_path": "x",
         "cell": "A1", "row": 1, "value": "層"},
    ]})
    docs = build_spreadsheet_state_context("XYZの平均が最も高いのは？", "テスト案件", store)
    assert docs == []


def test_pivot_cache_aggregate_context_for_single_candidate() -> None:
    store = _store({"train_xlsx_pivot_aggregates": [{
        "source_path": "data/raw/x/train.xlsx",
        "file_name": "train.xlsx",
        "sheet_name": "Pivot",
        "pivot_table_name": "PivotTable1",
        "data_field_name": "平均 / Sales",
        "data_field_source": "Sales",
        "subtotal": "average",
        "argmax_labels": {"Region": "東", "Category": "A"},
        "argmax_value": 123.0,
        "argmin_labels": {"Region": "西", "Category": "B"},
        "argmin_value": 45.0,
    }]})
    docs = build_spreadsheet_state_context(
        "Pivotシートで平均売上が最も高い層の抽出条件は？", "テスト案件", store)
    assert len(docs) == 1
    text = docs[0].document.text
    assert "Region = 東、Category = A" in text
    assert "値: 123.0" in text
    assert "最小のグループ" in text


def test_pivot_cache_aggregate_requires_superlative() -> None:
    store = _store({"train_xlsx_pivot_aggregates": [{
        "source_path": "data/raw/x/train.xlsx",
        "sheet_name": "Pivot",
        "pivot_table_name": "PivotTable1",
        "data_field_name": "平均 / Sales",
        "data_field_source": "Sales",
        "subtotal": "average",
        "argmax_labels": {"Region": "東"},
        "argmax_value": 123.0,
        "argmin_labels": {"Region": "西"},
        "argmin_value": 45.0,
    }]})
    docs = build_spreadsheet_state_context("PivotシートでSalesの平均は？", "テスト案件", store)
    assert docs == []


def test_pivot_cache_aggregate_abstains_when_multiple_data_fields_do_not_match() -> None:
    base = {
        "source_path": "data/raw/x/train.xlsx",
        "sheet_name": "Pivot",
        "pivot_table_name": "PivotTable1",
        "subtotal": "average",
        "argmax_labels": {"Region": "東"},
        "argmax_value": 123.0,
        "argmin_labels": {"Region": "西"},
        "argmin_value": 45.0,
    }
    store = _store({"train_xlsx_pivot_aggregates": [
        {**base, "data_field_name": "平均 / Sales", "data_field_source": "Sales"},
        {**base, "data_field_name": "平均 / Profit", "data_field_source": "Profit"},
    ]})
    docs = build_spreadsheet_state_context("Pivotシートで平均売上が最も高い層は？", "テスト案件", store)
    assert docs == []


class TestVersionDiffContext:
    def test_single_pair_returns_diff_context(self) -> None:
        store = _store({"version_diff_pairs": [{
            "project_name": "テスト案件",
            "normalized_title": "提案書",
            "old_path": "data/raw/x/提案書_v1.pptx",
            "new_path": "data/raw/x/提案書_final.pptx",
            "old_file_name": "提案書_v1.pptx",
            "new_file_name": "提案書_final.pptx",
            "old_version_tag": "v1",
            "new_version_tag": "final",
            "status": "ok",
            "added_count": 0, "removed_count": 0, "changed_count": 1,
            "added_samples": [], "removed_samples": [],
            "changed_samples": [{"before": "担当: 鈴木", "after": "担当: 高橋"}],
        }]})
        docs = build_version_diff_context(
            "テスト案件の提案書について、旧版と最新版を比較し、実質的な変更を挙げてください。",
            "テスト案件", store,
        )
        assert len(docs) == 1
        text = docs[0].document.text
        assert "担当: 鈴木" in text
        assert "担当: 高橋" in text
        assert docs[0].retrieval_method == "structured_version_diff"
        assert str(docs[0].document.source_path) == "data/raw/x/提案書_final.pptx"

    def test_no_pairs_for_project_returns_empty(self) -> None:
        store = _store({"version_diff_pairs": []})
        docs = build_version_diff_context("旧版と最新版の実質的な変更を挙げてください。", "テスト案件", store)
        assert docs == []

    def test_narrows_by_version_tags_when_multiple_pairs_share_title(self) -> None:
        rows = [
            {
                "project_name": "テスト案件", "normalized_title": "提案書", "status": "ok",
                "old_path": "x/提案書_v1.pptx", "new_path": "x/提案書_v2.pptx",
                "old_file_name": "提案書_v1.pptx", "new_file_name": "提案書_v2.pptx",
                "old_version_tag": "v1", "new_version_tag": "v2",
                "added_count": 0, "removed_count": 0, "changed_count": 1,
                "added_samples": [], "removed_samples": [],
                "changed_samples": [{"before": "v1->v2の変更", "after": "v1->v2の変更後"}],
            },
            {
                "project_name": "テスト案件", "normalized_title": "提案書", "status": "ok",
                "old_path": "x/提案書_v1.pptx", "new_path": "x/提案書_v3.pptx",
                "old_file_name": "提案書_v1.pptx", "new_file_name": "提案書_v3.pptx",
                "old_version_tag": "v1", "new_version_tag": "v3",
                "added_count": 0, "removed_count": 0, "changed_count": 1,
                "added_samples": [], "removed_samples": [],
                "changed_samples": [{"before": "v1->v3の変更", "after": "v1->v3の変更後"}],
            },
        ]
        store = _store({"version_diff_pairs": rows})
        docs = build_version_diff_context(
            "テスト案件の提案書_v1.pptxから提案書_v3.pptxに修正されたもののうち、案件遂行に関連する変更を挙げてください。",
            "テスト案件", store,
        )
        assert len(docs) == 1
        assert "v1->v3の変更" in docs[0].document.text
        assert "v1->v2の変更" not in docs[0].document.text

    def test_ambiguous_pair_returns_empty_instead_of_guessing(self) -> None:
        rows = [
            {
                "project_name": "テスト案件", "normalized_title": "提案書", "status": "ok",
                "old_path": "x/提案書_v1.pptx", "new_path": "x/提案書_v2.pptx",
                "old_file_name": "提案書_v1.pptx", "new_file_name": "提案書_v2.pptx",
                "old_version_tag": "v1", "new_version_tag": "v2",
                "added_count": 0, "removed_count": 0, "changed_count": 0,
                "added_samples": [], "removed_samples": [], "changed_samples": [],
            },
            {
                "project_name": "テスト案件", "normalized_title": "提案書", "status": "ok",
                "old_path": "x/提案書_v1.pptx", "new_path": "x/提案書_v3.pptx",
                "old_file_name": "提案書_v1.pptx", "new_file_name": "提案書_v3.pptx",
                "old_version_tag": "v1", "new_version_tag": "v3",
                "added_count": 0, "removed_count": 0, "changed_count": 0,
                "added_samples": [], "removed_samples": [], "changed_samples": [],
            },
        ]
        store = _store({"version_diff_pairs": rows})
        docs = build_version_diff_context(
            "テスト案件の提案書について、案件遂行に関連する変更を挙げてください。",
            "テスト案件", store,
        )
        assert docs == []

    def test_status_not_ok_pairs_are_excluded(self) -> None:
        store = _store({"version_diff_pairs": [{
            "project_name": "テスト案件", "normalized_title": "提案書", "status": "error",
            "old_path": "x/提案書_old.pptx", "new_path": "x/提案書.pptx",
            "old_file_name": "提案書_old.pptx", "new_file_name": "提案書.pptx",
            "old_version_tag": "old", "new_version_tag": None,
            "added_samples": [], "removed_samples": [], "changed_samples": [],
        }]})
        docs = build_version_diff_context(
            "テスト案件の提案書について、旧版と最新版の実質的な変更を挙げてください。",
            "テスト案件", store,
        )
        assert docs == []


def test_hex_color_family_classifies_hue_buckets() -> None:
    from src.retriever.structured_context import _hex_color_family

    assert _hex_color_family("F2E0D0") == "orange"
    assert _hex_color_family("B4C6E7") == "blue"
    assert _hex_color_family("E2EFDA") == "green"
    assert _hex_color_family("FFFF00") == "yellow"
    assert _hex_color_family("FF0000") == "red"
    assert _hex_color_family("FFFFFF") == "achromatic"
    assert _hex_color_family("808080") == "achromatic"
    assert _hex_color_family("00FFFF00") == "yellow"
    assert _hex_color_family("") == ""
    assert _hex_color_family("THEME:1") == ""


def test_hex_color_family_orange_yellow_hue_boundary_at_40() -> None:
    """Excel標準の薄い黄色FFF2CC(hue≈44.7°)は彩度が低くhueがorange側(旧閾値45°)に
    寄るため、閾値を40°に下げてyellowへ正しく分類する（実測: 「黄色にハイライト」
    質問がFFF2CC系の淡色セルで全滅していたバグの修正）。"""
    from src.retriever.structured_context import _hex_color_family

    assert _hex_color_family("FFF2CC") == "yellow"
    assert _hex_color_family("FFD700") == "yellow"
    # 濃い橙(hue≈39°)は引き続きorangeのまま
    assert _hex_color_family("FFA500") == "orange"
    assert _hex_color_family("F2E0D0") == "orange"


def test_hex_color_family_accepts_normalized_color_names() -> None:
    """scripts/extract_spreadsheets.pyのnormalize_color()は彩度の高い標準色を
    "yellow"/"red"等の名前文字列に変換してdominant_row_fillへ格納することがある。
    hexパースの前にこれらの名前を素通しし、achromatic系(black/white/gray/grey)は
    "achromatic"へ正規化する。"""
    from src.retriever.structured_context import _hex_color_family

    assert _hex_color_family("yellow") == "yellow"
    assert _hex_color_family("YELLOW") == "yellow"
    assert _hex_color_family("red") == "red"
    assert _hex_color_family("orange") == "orange"
    assert _hex_color_family("white") == "achromatic"
    assert _hex_color_family("black") == "achromatic"
    assert _hex_color_family("gray") == "achromatic"
    assert _hex_color_family("grey") == "achromatic"


def _schedule_rows() -> list[dict]:
    def row(file_name: str, row_number: int, fill: str | None, task: str) -> dict:
        return {
            "source_path": f"data/x/02.計画/{file_name}",
            "file_name": file_name,
            "sheet_name": "工程",
            "row_number": row_number,
            "dominant_row_fill": fill,
            "values": {"タスクID": f"T{row_number}", "タスク名": task, "担当者": "架空 太郎"},
        }

    return [
        row("工程_r2.xlsx", 2, "F2E0D0", "要件整理"),
        row("工程_r2.xlsx", 3, None, "設計"),
        row("工程_r2.xlsx", 4, "F2E0D0", "受入確認"),
        row("工程_r2.xlsx", 5, "B4C6E7", "移行リハーサル"),
        row("工程.xlsx", 2, "F2E0D0", "旧版タスク"),
    ]


def test_schedule_highlight_docs_filters_by_named_file_and_color() -> None:
    from src.retriever.structured_context import _schedule_highlight_docs

    docs = _schedule_highlight_docs(
        "工程_r2.xlsxにおいて、オレンジにハイライトされている行のタスク名をすべて答えてください。",
        _schedule_rows(),
    )
    texts = [d.document.text for d in docs]
    assert len(docs) == 2
    assert any("要件整理" in t for t in texts)
    assert any("受入確認" in t for t in texts)
    assert not any("旧版タスク" in t for t in texts)
    assert not any("移行リハーサル" in t for t in texts)
    assert not any("設計" in t for t in texts)


def test_schedule_highlight_docs_without_color_returns_all_filled_rows() -> None:
    from src.retriever.structured_context import _schedule_highlight_docs

    docs = _schedule_highlight_docs(
        "工程_r2.xlsxでハイライトされている行は？", _schedule_rows()
    )
    assert len(docs) == 3


def test_schedule_highlight_docs_keeps_rows_when_named_file_absent() -> None:
    from src.retriever.structured_context import _schedule_highlight_docs

    docs = _schedule_highlight_docs(
        "不在.xlsxでオレンジにハイライトされている行は？", _schedule_rows()
    )
    assert len(docs) == 3


def _schedule_rows_with_particle_kana_name() -> list[dict]:
    def row(file_name: str, row_number: int, fill: str | None, task: str) -> dict:
        return {
            "source_path": f"data/x/02.見積/{file_name}",
            "file_name": file_name,
            "sheet_name": "工程",
            "row_number": row_number,
            "dominant_row_fill": fill,
            "values": {"タスクID": f"T{row_number}", "タスク名": task, "担当者": "架空 太郎"},
        }

    return [
        row("見積もり一覧.xlsx", 2, "F2E0D0", "要件整理"),
        row("見積もり一覧.xlsx", 3, None, "設計"),
        row("一覧.xlsx", 2, "F2E0D0", "旧版タスク"),
    ]


def test_schedule_highlight_docs_matches_file_name_containing_particle_kana() -> None:
    """ファイル名内部に助詞かなを含む合成名（見積もり一覧.xlsx）でも
    find_named_files経由の照合で名指し絞り込みが発火する回帰テスト。"""
    from src.retriever.structured_context import _schedule_highlight_docs

    docs = _schedule_highlight_docs(
        "見積もり一覧.xlsxにおいて、オレンジにハイライトされている行のタスク名を教えてください。",
        _schedule_rows_with_particle_kana_name(),
    )
    texts = [d.document.text for d in docs]
    assert len(docs) == 1
    assert any("要件整理" in t for t in texts)
    assert not any("旧版タスク" in t for t in texts)


def test_schedule_highlight_docs_nfd_question_matches_color_filter() -> None:
    """_schedule_highlight_docs冒頭でquestionをNFC正規化してから色キーワード照合に
    渡す（修正5）。NFD正規化された質問でも色フィルタが機能することを確認する。"""
    import unicodedata

    from src.retriever.structured_context import _schedule_highlight_docs

    question_nfd = unicodedata.normalize("NFD", "工程_r2.xlsxにおいて、オレンジにハイライトされている行のタスク名は？")
    docs = _schedule_highlight_docs(question_nfd, _schedule_rows())
    texts = [d.document.text for d in docs]
    assert len(docs) == 2
    assert any("要件整理" in t for t in texts)
    assert any("受入確認" in t for t in texts)


def test_spreadsheet_state_context_includes_schedule_highlights() -> None:
    store = _full_store(schedule_tasks={"A社": [
        {
            "source_path": "data/x/02.計画/工程_r2.xlsx",
            "file_name": "工程_r2.xlsx",
            "sheet_name": "工程",
            "row_number": 2,
            "dominant_row_fill": "F2E0D0",
            "values": {"タスク名": "要件整理"},
        },
    ]})
    docs = build_spreadsheet_state_context(
        "工程_r2.xlsxにおいて、オレンジにハイライトされている行のタスク名は？", "A社", store
    )
    assert any("要件整理" in d.document.text for d in docs)


def test_spreadsheet_state_context_dedups_schedule_row_appearing_in_both_paths() -> None:
    """_schedule_highlight_docs（ハイライト経路）と既存の値マッチ経路（担当者名一致等）が
    同一スケジュール行を同一locationで二重に出力しうる問題の回帰テスト。
    「ハイライト」語と担当者名の両方を含む質問で、同一行のdocは1件だけになる。"""
    store = _full_store(schedule_tasks={"A社": [
        {
            "source_path": "data/x/02.計画/工程_r2.xlsx",
            "file_name": "工程_r2.xlsx",
            "sheet_name": "工程",
            "row_number": 2,
            "dominant_row_fill": "F2E0D0",
            "values": {"タスク名": "要件整理", "担当者": "架空 太郎"},
        },
    ]})
    docs = build_spreadsheet_state_context(
        "架空 太郎さんが担当していて、ハイライトされている行のタスク名は？", "A社", store
    )
    keys = [(str(d.document.source_path), d.document.location) for d in docs]
    assert len(keys) == len(set(keys))
    assert len(docs) == 1
    assert "要件整理" in docs[0].document.text


def test_spreadsheet_state_context_train_xlsx_path_unchanged() -> None:
    store = _full_store(
        train_xlsx_highlight_blocks={"A社": [
            {
                "source_path": "data/x/03.データ/train.xlsx",
                "sheet_name": "Sheet1",
                "range": "B2:B4",
                "fill_color_name": "FFFF00",
                "first_value": "42",
                "column_header": {"value": "件数", "cell": "B1"},
                "same_row_values": [],
            },
        ]},
        schedule_tasks={"A社": []},
    )
    docs = build_spreadsheet_state_context(
        "train.xlsxでハイライトされているセルの値は？", "A社", store
    )
    assert any("ハイライト範囲" in d.document.text for d in docs)


# --- 回帰予測（回帰係数×特徴量値の内積＋切片）の係数グリッド検出 -------------------- #


def test_regression_prediction_context_detects_grid_with_intercept_before_features() -> None:
    """Excel回帰分析出力の典型レイアウト（切片行が特徴量行より上）から
    「係数」ヘッダ列＋「切片」ラベル行の組み合わせのみで係数グリッドを検出し、doc化する。"""
    cells = [
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B5", "row": 5, "value": "係数"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "C5", "row": 5, "value": "標準誤差"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A6", "row": 6, "value": "切片"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B6", "row": 6, "value": "1.5"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A7", "row": 7, "value": "feat_x"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B7", "row": 7, "value": "2.0"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A8", "row": 8, "value": "feat_y"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B8", "row": 8, "value": "-0.5"},
    ]
    store = _store({"train_xlsx_small_sheet_cells": cells})
    docs = build_spreadsheet_state_context(
        "テスト案件のtrain.xlsxで算出された回帰係数を使ってid=0を予測した場合の予測値はいくらですか。",
        "テスト案件", store,
    )
    matches = [d for d in docs if "切片" in d.document.text and "係数" in d.document.text]
    assert len(matches) == 1
    text = matches[0].document.text
    assert "切片: 1.5" in text
    assert "feat_x=2.0" in text
    assert "feat_y=-0.5" in text


def test_regression_prediction_context_detects_grid_with_intercept_after_features() -> None:
    """切片行が特徴量行より下（表の末尾）に来るレイアウトでも同様に検出できる
    （実データ2案件で順序が異なることを確認済みのため、順序に依存しない設計であることの回帰テスト）。"""
    cells = [
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B5", "row": 5, "value": "係数"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A6", "row": 6, "value": "feat_x"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B6", "row": 6, "value": "0.3"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A7", "row": 7, "value": "feat_y"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B7", "row": 7, "value": "0.7"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A8", "row": 8, "value": "切片"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B8", "row": 8, "value": "-2.25"},
    ]
    store = _store({"train_xlsx_small_sheet_cells": cells})
    docs = build_spreadsheet_state_context(
        "テスト案件のtrain.xlsxの回帰分析の結果として記載されている係数をindex=10のデータに"
        "当てはめたときの予測値はいくつですか。",
        "テスト案件", store,
    )
    matches = [d for d in docs if "切片" in d.document.text and "係数" in d.document.text]
    assert len(matches) == 1
    text = matches[0].document.text
    assert "切片: -2.25" in text
    assert "feat_x=0.3" in text
    assert "feat_y=0.7" in text


def test_regression_prediction_context_not_triggered_without_prediction_keyword() -> None:
    """「回帰」「係数」は含むが「予測」を含まない質問では回帰係数docを追加しない
    （検出は一般語彙3語の共起のみで判定し、既存のPivot等の挙動に影響を与えないことの確認）。"""
    cells = [
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B5", "row": 5, "value": "係数"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A6", "row": 6, "value": "切片"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B6", "row": 6, "value": "1.5"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A7", "row": 7, "value": "feat_x"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B7", "row": 7, "value": "2.0"},
    ]
    store = _store({"train_xlsx_small_sheet_cells": cells})
    docs = build_spreadsheet_state_context(
        "train.xlsxの回帰分析シートに記載されている係数を教えてください。", "テスト案件", store,
    )
    assert not any("切片" in d.document.text for d in docs)


def test_regression_prediction_context_not_triggered_for_residual_or_error_request() -> None:
    """「予測値と実測値の残差/誤差を求めよ」型の質問は、予測値そのものではなく
    別の量（実測値との差）を問うものであり、予測値を直答すると誤答になる。
    「残差」「誤差」を含む質問では回帰係数docを追加しない（負のガード）。"""
    cells = [
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B5", "row": 5, "value": "係数"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A6", "row": 6, "value": "切片"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B6", "row": 6, "value": "1.5"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A7", "row": 7, "value": "feat_x"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B7", "row": 7, "value": "2.0"},
    ]
    store = _store({"train_xlsx_small_sheet_cells": cells})
    for question in (
        "train.xlsxで算出された回帰係数を使ってid=0を予測した場合の残差はいくらですか。",
        "train.xlsxで算出された回帰係数を使ってid=0を予測した場合の予測値との誤差はいくらですか。",
    ):
        docs = build_spreadsheet_state_context(question, "テスト案件", store)
        assert not any("切片" in d.document.text for d in docs), question


def test_regression_prediction_context_ambiguous_multiple_grids_returns_nothing() -> None:
    """案件内に複数の回帰係数グリッド候補（複数シート）が構造的に検出される場合、
    誤った式を使うリスクを避けるため回帰係数docを一切出さない（曖昧なら出さない）。"""
    cells = []
    for sheet in ("回帰分析A", "回帰分析B"):
        cells.append({"sheet_name": sheet, "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
                       "cell": "B5", "row": 5, "value": "係数"})
        cells.append({"sheet_name": sheet, "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
                       "cell": "A6", "row": 6, "value": "切片"})
        cells.append({"sheet_name": sheet, "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
                       "cell": "B6", "row": 6, "value": "1.0"})
        cells.append({"sheet_name": sheet, "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
                       "cell": "A7", "row": 7, "value": "feat_x"})
        cells.append({"sheet_name": sheet, "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
                       "cell": "B7", "row": 7, "value": "2.0"})
    store = _store({"train_xlsx_small_sheet_cells": cells})
    docs = build_spreadsheet_state_context(
        "train.xlsxで算出された回帰係数を使ってid=0を予測した場合の予測値はいくらですか。", "テスト案件", store,
    )
    assert not any("切片" in d.document.text for d in docs)


def test_regression_prediction_context_missing_intercept_label_returns_nothing() -> None:
    """「係数」ヘッダはあっても「切片」ラベル行が無い場合はグリッドとして採用しない
    （切片が欠ければ予測値を計算できないため）。"""
    cells = [
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B5", "row": 5, "value": "係数"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "A6", "row": 6, "value": "feat_x"},
        {"sheet_name": "回帰分析", "file_name": "train.xlsx", "source_path": "data/raw/x/train.xlsx",
         "cell": "B6", "row": 6, "value": "2.0"},
    ]
    store = _store({"train_xlsx_small_sheet_cells": cells})
    docs = build_spreadsheet_state_context(
        "train.xlsxで算出された回帰係数を使ってid=0を予測した場合の予測値はいくらですか。", "テスト案件", store,
    )
    assert not any("切片" in d.document.text for d in docs)
