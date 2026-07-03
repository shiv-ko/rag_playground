"""BM25ベースのキーワード検索。rank-bm25が未インストールならTF-IDF的な簡易実装にフォールバック。"""
from __future__ import annotations

import math
import re
from collections import Counter

from src.models import Document, ScoredDocument


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (0x4E00 <= cp <= 0x9FFF or   # CJK統合漢字
            0x3040 <= cp <= 0x309F or   # ひらがな
            0x30A0 <= cp <= 0x30FF)     # カタカナ


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    # ASCII単語はそのまま
    for word in re.findall(r"[a-zA-Z0-9]+", text.lower()):
        tokens.append(word)
    # CJK文字はバイグラム（unigram+bigram）
    # 空白や句読点で分割して、各セグメント内でバイグラムを作成（単語境界を超えない）
    segments = re.split(r'[\s\W]+', text)  # 空白と非単語文字で分割
    for segment in segments:
        cjk_chars = [ch for ch in segment if _is_cjk(ch)]
        tokens.extend(cjk_chars)  # unigram
        for i in range(len(cjk_chars) - 1):
            tokens.append(cjk_chars[i] + cjk_chars[i + 1])  # bigram
    return tokens


class KeywordStore:
    def __init__(self) -> None:
        self._docs: list[Document] = []
        self._use_bm25 = False
        self._bm25 = None

    def add(self, documents: list[Document]) -> None:
        self._docs.extend(documents)
        self._rebuild()

    def clear(self) -> None:
        self._docs = []
        self._bm25 = None

    def _rebuild(self) -> None:
        try:
            from rank_bm25 import BM25Okapi
            corpus = [_tokenize(d.text) for d in self._docs]
            self._bm25 = BM25Okapi(corpus)
            self._use_bm25 = True
        except ImportError:
            self._use_bm25 = False

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        if not self._docs:
            return []
        if self._use_bm25 and self._bm25 is not None:
            return self._search_bm25(query, top_k)
        return self._search_tfidf(query, top_k)

    def _search_bm25(self, query: str, top_k: int) -> list[ScoredDocument]:
        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            ScoredDocument(document=self._docs[i], score=float(s), retrieval_method="keyword")
            for i, s in ranked if s > 0
        ]

    def _search_tfidf(self, query: str, top_k: int) -> list[ScoredDocument]:
        """BM25なし時の簡易TF-IDF風スコアリング。"""
        query_tokens = set(_tokenize(query))
        n = len(self._docs)
        df = Counter[str]()
        for doc in self._docs:
            for token in set(_tokenize(doc.text)):
                df[token] += 1

        results: list[ScoredDocument] = []
        for doc in self._docs:
            tokens = _tokenize(doc.text)
            tf = Counter(tokens)
            total = len(tokens) or 1
            score = 0.0
            for token in query_tokens:
                if token in tf:
                    idf = math.log((n + 1) / (df[token] + 1))
                    score += (tf[token] / total) * idf
            results.append(ScoredDocument(document=doc, score=score, retrieval_method="keyword"))

        results.sort(key=lambda x: x.score, reverse=True)
        return [r for r in results[:top_k] if r.score > 0]
