"""citation_check のテスト。"""
from __future__ import annotations

from src.generator.citation_check import citation_supported


def test_citation_present_in_context_is_supported() -> None:
    assert citation_supported(
        "宿泊費の上限は15,000円です。", "前略。宿泊費の上限は15,000円です。後略。"
    ) is True


def test_citation_absent_from_context_is_not_supported() -> None:
    assert citation_supported("架空の引用文です。", "宿泊費の上限は15,000円です。") is False


def test_empty_citation_is_not_supported() -> None:
    assert citation_supported("", "何らかのcontext") is False


def test_citation_with_surrounding_whitespace_is_stripped_before_check() -> None:
    assert citation_supported(
        "  宿泊費の上限は15,000円です。  ", "宿泊費の上限は15,000円です。"
    ) is True
