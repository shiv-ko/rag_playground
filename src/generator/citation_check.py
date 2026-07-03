"""生成回答の根拠引用が、実際にLLMへ渡したcontext内に存在するかを確認する。"""
from __future__ import annotations


def citation_supported(citation: str, context_text: str) -> bool:
    citation = citation.strip()
    if not citation:
        return False
    return citation in context_text
