"""質問文中の明示ファイル名の抽出・照合のテスト。"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from src.retriever.question_file_scope import (
    extract_file_names,
    find_named_files,
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
