"""列挙系回答の完全性ゲート。"""
from __future__ import annotations

_COMPLETE_METHODS = frozenset({"structured_attribute_filter"})


def is_enumeration_complete(matched_count: int, candidate_pool_size: int, extraction_method: str) -> bool:
    if extraction_method not in _COMPLETE_METHODS:
        return False
    if candidate_pool_size == 0:
        return False
    if matched_count == 0:
        return False
    return True
