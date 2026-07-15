"""質問文中の明示ファイル名の抽出・照合のテスト。"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from src.retriever.question_file_scope import (
    extract_file_names,
    find_named_files,
    find_question_stem_matches,
    find_stem_matches,
    matches_file_name,
)

# _FILE_BOUNDARY_CHARS から助詞かな（のにでとはをがもや）を削除したため、
# extract_file_names は「ファイル名の直後に助詞かなが続き、他に境界記号が無い」
# 入力ではもう名前を切り出せない（例: 「計画_r2.xlsxにおいて」は不一致）。
# これはバグ修正の意図した副作用: 助詞かなをファイル名内部の切り詰め源として
# 使わないことが目的で、質問側の境界判定は句読点・括弧・空白にのみ依存させる。
# 以下のテストは境界記号（「」、。等）をファイル名の直後に置く形に書き換えた。
# 名指し照合の主経路は find_named_files に移ったため、この関数はゲート・
# 後方互換用として維持する。


def test_extract_single_xlsx_name():
    q = "「計画_r2.xlsx」において、オレンジにハイライトされている行を答えてください。"
    assert extract_file_names(q) == ["計画_r2.xlsx"]


def test_extract_multiple_and_dedup():
    q = "報告.pptx、報告.pptx、分析.docx。それぞれの違いは？"
    assert extract_file_names(q) == ["報告.pptx", "分析.docx"]


def test_extract_returns_empty_when_no_file():
    assert extract_file_names("宿泊費の上限を教えてください。") == []


def test_extract_normalizes_nfd_to_nfc():
    name_nfd = unicodedata.normalize("NFD", "データ一覧.xlsx")
    q = f"「{name_nfd}」のシート数は？"
    assert extract_file_names(q) == [unicodedata.normalize("NFC", "データ一覧.xlsx")]


def test_extract_stops_at_japanese_punctuation():
    q = "つぎのファイル、集計.csv、行数を教えてください。"
    assert extract_file_names(q) == ["集計.csv"]


def test_matches_file_name_by_basename_nfc():
    names = extract_file_names("「計画_r2.xlsx」の内容は？")
    nfd_path = unicodedata.normalize("NFD", "data/raw/x/02.計画/計画_r2.xlsx")
    assert matches_file_name(nfd_path, names)
    assert matches_file_name(Path("y/計画_r2.xlsx"), names)
    assert not matches_file_name("data/raw/x/02.計画/計画.xlsx", names)


def test_matches_file_name_empty_names_is_false():
    assert not matches_file_name("a/b.xlsx", [])


class TestFindNamedFiles:
    """既知basename集合と質問文の部分文字列照合（境界文字に依存しない）。
    ファイル名内部に助詞かなを含む合成名でも丸ごと照合できることを確認する。"""

    def test_matches_known_name_containing_particle_kana(self):
        # 「見積もり一覧.xlsx」は助詞的なかな（もり等）を内部に含む合成ファイル名。
        q = "見積もり一覧.xlsxの内容を教えてください。"
        assert find_named_files(q, ["見積もり一覧.xlsx"]) == ["見積もり一覧.xlsx"]

    def test_matches_known_name_with_market_forecast_style(self):
        # 実データでバグを踏んだパターンを模した合成名（「市場の分析」に助詞「の」を含む）。
        q = "市場の分析.pdfのまとめを教えてください。"
        assert find_named_files(q, ["市場の分析.pdf", "別紙.docx"]) == ["市場の分析.pdf"]

    def test_prefers_longest_match_over_substring_match(self):
        q = "見積もり一覧.xlsxの内容を教えてください。"
        known = ["一覧.xlsx", "見積もり一覧.xlsx"]
        assert find_named_files(q, known) == ["見積もり一覧.xlsx"]

    def test_keeps_short_name_when_it_also_appears_independently(self):
        # 「一覧.xlsx」が「見積もり一覧.xlsx」の内部一致としてだけでなく、
        # 質問中に独立して出現している場合は両方返す（キー同士の包含関係
        # だけで除外すると、独立に名指しされたファイルが落ちる）。
        q = "一覧.xlsxと見積もり一覧.xlsxの違いを教えてください。"
        known = ["一覧.xlsx", "見積もり一覧.xlsx"]
        assert find_named_files(q, known) == ["一覧.xlsx", "見積もり一覧.xlsx"]

    def test_matches_from_basename_of_full_path(self):
        q = "見積もり一覧.xlsxの内容を教えてください。"
        known = [Path("data/raw/A社/02.見積/見積もり一覧.xlsx")]
        assert find_named_files(q, known) == ["見積もり一覧.xlsx"]

    def test_handles_nfd_question_and_nfd_known_name(self):
        name_nfc = "見積もり一覧.xlsx"
        name_nfd = unicodedata.normalize("NFD", name_nfc)
        q = unicodedata.normalize("NFD", f"{name_nfc}の内容を教えてください。")
        assert find_named_files(q, [name_nfd]) == [name_nfc]

    def test_unknown_file_returns_empty_list(self):
        q = "見積もり一覧.xlsxの内容を教えてください。"
        assert find_named_files(q, ["別紙.docx"]) == []

    def test_no_known_names_returns_empty_list(self):
        assert find_named_files("見積もり一覧.xlsxの内容は？", []) == []


class TestFindStemMatches:
    """用語集展開語（例: "CT"→"契約書"）とファイルbasenameのstem（拡張子除去部）の
    部分文字列照合。質問文そのものではなく展開語ヒントのリストを入力に取る。"""

    def test_hint_matches_exact_stem(self):
        assert find_stem_matches(["契約書"], ["契約書.docx", "会議録_2025-09-30.docx"]) == [
            "契約書.docx"
        ]

    def test_hint_matches_stem_with_suffix(self):
        # 「契約書_draft.docx」のstemは「契約書_draft」で「契約書」を部分文字列に含む
        result = find_stem_matches(["契約書"], ["契約書_draft.docx", "提案書.pptx"])
        assert result == ["契約書_draft.docx"]

    def test_hint_shorter_than_stem_extension_still_matches(self):
        # TX→"train.xlsx" のように展開語自体に拡張子が付く場合でも、
        # stem「train」が展開語に部分文字列として含まれていれば一致する
        result = find_stem_matches(["train.xlsx"], ["train.xlsx", "別紙.pdf"])
        assert result == ["train.xlsx"]

    def test_no_hints_returns_empty_list(self):
        assert find_stem_matches([], ["契約書.docx"]) == []

    def test_no_known_names_returns_empty_list(self):
        assert find_stem_matches(["契約書"], []) == []

    def test_hint_not_present_in_any_stem_returns_empty_list(self):
        assert find_stem_matches(["決裁基準"], ["契約書.docx", "提案書.pptx"]) == []

    def test_matches_multiple_files_of_same_type(self):
        # 「提案書」は複数版（_v1/_v2/_final）すべてのstemに含まれる
        known = ["提案書_v1.pptx", "提案書_v2.pptx", "提案書_final.pptx", "契約書.docx"]
        assert find_stem_matches(["提案書"], known) == [
            "提案書_v1.pptx",
            "提案書_v2.pptx",
            "提案書_final.pptx",
        ]

    def test_dedups_repeated_basenames(self):
        known = ["契約書.docx", "契約書.docx"]
        assert find_stem_matches(["契約書"], known) == ["契約書.docx"]

    def test_ignores_blank_hints(self):
        assert find_stem_matches(["", "  "], ["契約書.docx"]) == []

    def test_ignores_hints_shorter_than_three_chars(self):
        # term_registryの"R2"→"R2"や"RED"→"赤字"のような書式・統計用語（2文字）は、
        # ファイル名の版数サフィックス（実データの"スケジュール_r2.xlsx"等）との
        # 偶然一致リスクが高いため、文書種別を表さない短いhintとして除外する。
        assert find_stem_matches(["R2", "赤字"], ["スケジュール_r2.xlsx", "契約書.docx"]) == []

    def test_three_char_hint_still_matches(self):
        assert find_stem_matches(["契約書"], ["契約書.docx"]) == ["契約書.docx"]

    def test_filename_like_hint_requires_exact_stem_not_substring(self):
        # term_registryの"EDA1"→"01_eda.ipynb"のような、拡張子付きの具体的な
        # ファイル名そのものを指すhintは、実データで"eda.py"（stem="eda"）が
        # 同一プロジェクトに実在するため部分文字列一致だと誤って両方ヒットする。
        # 拡張子付きhintはstem完全一致のみを許可する。
        result = find_stem_matches(["01_eda.ipynb"], ["01_eda.ipynb", "eda.py"])
        assert result == ["01_eda.ipynb"]

    def test_ascii_hint_requires_word_boundary_not_bare_substring(self):
        # term_registry実在の"Lift"/"Gain"/"MAE"等のASCII英字hint（拡張子なし）は、
        # 語境界の無いbare substring一致だと英単語の一部に偶然含まれて誤マッチする。
        assert find_stem_matches(["Lift"], ["uplift_model.csv", "契約書.docx"]) == []
        assert find_stem_matches(["Gain"], ["再検証_gainful.csv", "契約書.docx"]) == []
        assert find_stem_matches(["MAE"], ["yamae_note.txt", "契約書.docx"]) == []

    def test_ascii_hint_matches_at_word_boundary(self):
        assert find_stem_matches(["Gain"], ["report_gain_v1.csv"]) == ["report_gain_v1.csv"]
        assert find_stem_matches(["MAE"], ["MAE.csv"]) == ["MAE.csv"]

    def test_japanese_hint_substring_containment_still_works(self):
        # 日本語hint（拡張子なし・非ASCII）は既存どおり語境界チェック無しの
        # 部分文字列一致を維持する（「契約書_draft」等の版違いを広く拾うため）。
        assert find_stem_matches(["契約書"], ["契約書_draft.docx"]) == ["契約書_draft.docx"]

    def test_normalizes_nfd_hint_and_known_name(self):
        hint_nfd = unicodedata.normalize("NFD", "契約書")
        name_nfd = unicodedata.normalize("NFD", "契約書.docx")
        assert find_stem_matches([hint_nfd], [name_nfd]) == ["契約書.docx"]


class TestFindQuestionStemMatches:
    """質問文に拡張子なしで明示された、実在ファイルのstemとの照合。"""

    def test_matches_extensionless_stem_and_normalizes_nfd(self):
        question = unicodedata.normalize("NFD", "A社のカラム説明において値は？")
        known = [unicodedata.normalize("NFD", "data/A社/カラム説明.md")]
        assert find_question_stem_matches(question, known) == ["カラム説明.md"]

    def test_matches_stem_followed_by_kara_or_yori(self):
        known = ["カラム説明.md"]
        assert find_question_stem_matches("カラム説明から値を答えて", known) == [
            "カラム説明.md"
        ]
        assert find_question_stem_matches("カラム説明より値を答えて", known) == [
            "カラム説明.md"
        ]

    def test_ignores_short_stem_even_when_independently_mentioned(self):
        assert find_question_stem_matches("A社の表において値は？", ["表.md"]) == []

    def test_does_not_match_stem_inside_longer_word(self):
        assert find_question_stem_matches("カラム説明において値は？", ["説明.md"]) == []

    def test_prefers_longest_stem_at_same_occurrence(self):
        known = ["説明.md", "カラム説明.md"]
        assert find_question_stem_matches("カラム説明において値は？", known) == [
            "カラム説明.md"
        ]
