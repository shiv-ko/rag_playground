"""生成回答の根拠引用が、実際にLLMへ渡したcontext内に存在するかを確認する。"""
from __future__ import annotations


def _normalize(text: str) -> str:
    # 改行・空白の揺れで正しい引用が偽陰性にならないよう、空白類を除去して比較する
    return "".join(text.split())


def citation_supported(citation: str, context_text: str) -> bool:
    citation = _normalize(citation)
    if not citation:
        return False
    return citation in _normalize(context_text)
