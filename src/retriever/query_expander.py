"""社内用語の略語が質問文に含まれる場合、正式名称を検索クエリに併記する。"""
from __future__ import annotations


class QueryExpander:
    def __init__(self, term_registry: list[dict]) -> None:
        self._term_registry = term_registry

    def expand_terms(self, query: str) -> str:
        expansions: list[str] = []
        for entry in self._term_registry:
            term = entry.get("term", "")
            expansion = entry.get("expansion", "")
            if term and expansion and term in query and expansion not in expansions:
                expansions.append(expansion)
        if not expansions:
            return query
        return query + " " + " ".join(expansions)
