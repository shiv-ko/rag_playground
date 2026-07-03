"""QueryExpander のテスト。"""
from __future__ import annotations

from src.retriever.query_expander import QueryExpander


def test_expand_terms_appends_expansion_when_term_present() -> None:
    expander = QueryExpander([{"term": "TG", "expansion": "目的変数", "note": "Target"}])
    assert expander.expand_terms("TGの分布を教えて") == "TGの分布を教えて 目的変数"


def test_expand_terms_returns_original_when_no_term_matches() -> None:
    expander = QueryExpander([{"term": "TG", "expansion": "目的変数"}])
    assert expander.expand_terms("関係ない質問です") == "関係ない質問です"


def test_expand_terms_dedupes_identical_expansions() -> None:
    registry = [
        {"term": "PL", "expansion": "計画"},
        {"term": "PLAN", "expansion": "計画"},
    ]
    expander = QueryExpander(registry)
    result = expander.expand_terms("PLANとPLの違いは？")
    assert result.count("計画") == 1


def test_expand_terms_with_empty_registry_returns_original() -> None:
    expander = QueryExpander([])
    assert expander.expand_terms("TGの分布を教えて") == "TGの分布を教えて"
