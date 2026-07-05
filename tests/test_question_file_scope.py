"""質問文中の明示ファイル名の抽出・照合のテスト。"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from src.retriever.question_file_scope import extract_file_names, matches_file_name


def test_extract_single_xlsx_name():
    q = "計画_r2.xlsxにおいて、オレンジにハイライトされている行を答えてください。"
    assert extract_file_names(q) == ["計画_r2.xlsx"]


def test_extract_multiple_and_dedup():
    q = "報告.pptxと報告.pptxと分析.docxの違いは？"
    assert extract_file_names(q) == ["報告.pptx", "分析.docx"]


def test_extract_returns_empty_when_no_file():
    assert extract_file_names("宿泊費の上限を教えてください。") == []


def test_extract_normalizes_nfd_to_nfc():
    name_nfd = unicodedata.normalize("NFD", "データ一覧.xlsx")
    q = f"{name_nfd}のシート数は？"
    assert extract_file_names(q) == [unicodedata.normalize("NFC", "データ一覧.xlsx")]


def test_extract_stops_at_japanese_punctuation():
    q = "つぎのファイル、集計.csvの行数は？"
    assert extract_file_names(q) == ["集計.csv"]


def test_matches_file_name_by_basename_nfc():
    names = extract_file_names("計画_r2.xlsxの内容は？")
    nfd_path = unicodedata.normalize("NFD", "data/raw/x/02.計画/計画_r2.xlsx")
    assert matches_file_name(nfd_path, names)
    assert matches_file_name(Path("y/計画_r2.xlsx"), names)
    assert not matches_file_name("data/raw/x/02.計画/計画.xlsx", names)


def test_matches_file_name_empty_names_is_false():
    assert not matches_file_name("a/b.xlsx", [])
