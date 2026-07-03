"""列挙の完全性ゲートのテスト。"""
from __future__ import annotations

from src.generator.enumeration_gate import is_enumeration_complete


def test_structured_extraction_with_matches_is_complete() -> None:
    assert is_enumeration_complete(3, 10, "structured_attribute_filter") is True


def test_structured_extraction_with_zero_matches_is_not_complete() -> None:
    assert is_enumeration_complete(0, 10, "structured_attribute_filter") is False


def test_structured_extraction_with_empty_pool_is_not_complete() -> None:
    assert is_enumeration_complete(0, 0, "structured_attribute_filter") is False


def test_unknown_extraction_method_is_not_complete() -> None:
    assert is_enumeration_complete(5, 10, "something_new") is False
