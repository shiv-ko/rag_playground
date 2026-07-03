"""質問文の要求能力タグ分類のテスト。"""
from __future__ import annotations

from src.utils.question_classifier import classify_question


def test_detects_image_or_graph_question() -> None:
    q = "figure_06.pngにおいて、dayによる件数推移を教えてください。"
    assert "image_or_graph" in classify_question(q)


def test_detects_version_diff_question() -> None:
    q = "提案書old.pptxから提案書.pptxへの更新内容のうち、実質的な変更を挙げてください。"
    assert "version_diff" in classify_question(q)


def test_detects_password_protected_question() -> None:
    q = "契約書のパスワードを教えてください。"
    assert "password_protected" in classify_question(q)


def test_detects_multi_hop_question() -> None:
    q = "すべての案件のうち、契約金額が最大のものはどれですか。"
    assert "multi_hop" in classify_question(q)


def test_plain_question_is_text_only() -> None:
    q = "宿泊費の上限はいくらですか。"
    assert classify_question(q) == ["text_only"]


def test_question_can_have_multiple_tags() -> None:
    q = "old版のfigure_06.pngとの差分を教えてください。"
    tags = classify_question(q)
    assert "image_or_graph" in tags
    assert "version_diff" in tags
