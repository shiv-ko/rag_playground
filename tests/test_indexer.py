"""Indexer コンポーネントの TDD テスト。

テスト対象:
  - KeywordStore  (src/indexer/keyword_store.py)
  - VectorStore   (src/indexer/vector_store.py)
  - HybridRetriever (src/retriever/hybrid_retriever.py)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models import Document, ScoredDocument
from src.indexer.keyword_store import KeywordStore
from src.indexer.vector_store import VectorStore
from src.retriever.hybrid_retriever import HybridRetriever


# ---------------------------------------------------------------------------
# 共有フィクスチャ
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_docs(tmp_path: Path) -> list[Document]:
    """検索テスト用の複数ドキュメント（日本語・英数字混在）。"""
    return [
        Document(
            text="宿泊費の上限は15,000円です。東京出張では20,000円まで認められます。",
            source_path=tmp_path / "a.txt",
        ),
        Document(
            text="交通費は1回10,000円まで精算できます。新幹線利用は別途申請が必要。",
            source_path=tmp_path / "b.txt",
        ),
        Document(
            text="Model Xのバッテリーは18時間持続します。充電時間は約2時間です。",
            source_path=tmp_path / "c.txt",
        ),
        Document(
            text="出張規定には宿泊費と交通費の詳細が記載されています。改訂版は2024年版。",
            source_path=tmp_path / "d.txt",
        ),
        Document(
            text="社員食堂のメニューは毎週更新されます。テイクアウトも可能です。",
            source_path=tmp_path / "e.txt",
        ),
    ]


# ---------------------------------------------------------------------------
# KeywordStore
# ---------------------------------------------------------------------------

class TestKeywordStore:
    """KeywordStore の動作検証。"""

    def test_add_and_search_returns_scored_documents(
        self, tmp_docs: list[Document]
    ) -> None:
        """add() でドキュメントを追加後、search() でスコア付きドキュメントを返す。"""
        store = KeywordStore()
        store.add(tmp_docs)

        results = store.search("宿泊費", top_k=3)

        assert len(results) > 0
        assert all(isinstance(r, ScoredDocument) for r in results)
        assert all(r.score > 0 for r in results)

    def test_search_results_ordered_by_score_descending(
        self, tmp_docs: list[Document]
    ) -> None:
        """search() 結果はスコア降順になっている。"""
        store = KeywordStore()
        store.add(tmp_docs)

        results = store.search("宿泊費 交通費 精算", top_k=5)

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), (
            f"スコアが降順になっていない: {scores}"
        )

    def test_relevant_doc_ranked_higher_than_irrelevant_japanese(
        self, tmp_path: Path
    ) -> None:
        """クエリに関連するドキュメントが無関係なドキュメントより上位になる（日本語）。

        小規模コーパス(2件)ではBM25がIDF=0になるため、TF-IDF fallbackを使用。
        """
        # Force TF-IDF fallback for small corpora where BM25 gives 0 IDF
        with patch.dict(sys.modules, {"rank_bm25": None}):
            # Clear the keyword_store module cache to force reimport
            if "src.indexer.keyword_store" in sys.modules:
                del sys.modules["src.indexer.keyword_store"]

            from src.indexer.keyword_store import KeywordStore as KeywordStoreWithoutBM25

            relevant = Document(
                text="宿泊費の精算には領収書が必要です。上限は20,000円。",
                source_path=tmp_path / "relevant.txt",
            )
            irrelevant = Document(
                text="バッテリーの充電時間は2時間です。",
                source_path=tmp_path / "irrelevant.txt",
            )
            store = KeywordStoreWithoutBM25()
            store.add([relevant, irrelevant])

            results = store.search("宿泊費 精算", top_k=2)

            assert len(results) > 0, "クエリに関連する結果が 1 件以上返るべき"
            assert results[0].document.text == relevant.text, (
                f"関連ドキュメントが先頭に来るべき。実際: {results[0].document.text!r}"
            )

    def test_clear_then_search_returns_empty_list(
        self, tmp_docs: list[Document]
    ) -> None:
        """clear() 後に search() は空リストを返す。"""
        store = KeywordStore()
        store.add(tmp_docs)
        store.clear()

        results = store.search("宿泊費", top_k=5)

        assert results == []

    def test_top_k_limits_result_count(self, tmp_docs: list[Document]) -> None:
        """top_k パラメータが結果の最大件数を制限する。"""
        store = KeywordStore()
        store.add(tmp_docs)

        results = store.search("費 円", top_k=2)

        assert len(results) <= 2

    def test_search_with_no_documents_returns_empty_list(self) -> None:
        """ドキュメントが 0 件のとき search() は空リストを返す。"""
        store = KeywordStore()

        results = store.search("宿泊費", top_k=5)

        assert results == []


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class TestVectorStore:
    """VectorStore の動作検証。"""

    def test_add_and_search_returns_scored_documents(
        self, tmp_docs: list[Document]
    ) -> None:
        """add() 後 search() がスコア付きドキュメントを返す。"""
        store = VectorStore()
        store.add(tmp_docs)

        results = store.search("宿泊費", top_k=3)

        assert len(results) > 0
        assert all(isinstance(r, ScoredDocument) for r in results)

    def test_clear_then_search_returns_empty_list(
        self, tmp_docs: list[Document]
    ) -> None:
        """clear() 後に search() は空リストを返す。"""
        store = VectorStore()
        store.add(tmp_docs)
        store.clear()

        results = store.search("宿泊費", top_k=5)

        assert results == []

    def test_exact_match_text_has_highest_score(self, tmp_path: Path) -> None:
        """同一テキストを追加してクエリしたとき最高スコアになる。"""
        target_text = "人工知能の研究開発に関する最新動向レポート"
        target_doc = Document(
            text=target_text, source_path=tmp_path / "target.txt"
        )
        other_docs = [
            Document(
                text="社員食堂のランチメニューは500円です。",
                source_path=tmp_path / "x.txt",
            ),
            Document(
                text="交通費は月額3万円まで支給されます。",
                source_path=tmp_path / "y.txt",
            ),
        ]
        store = VectorStore()
        store.add(other_docs + [target_doc])

        results = store.search(target_text, top_k=3)

        assert len(results) > 0
        assert results[0].document.text == target_text, (
            f"同一テキストが最高スコアになるべき。実際の先頭: {results[0].document.text!r}"
        )

    def test_retrieval_method_is_vector(self, tmp_docs: list[Document]) -> None:
        """retrieval_method が 'vector' である。"""
        store = VectorStore()
        store.add(tmp_docs)

        results = store.search("宿泊費", top_k=3)

        assert all(r.retrieval_method == "vector" for r in results), (
            f"全結果の retrieval_method が 'vector' であるべき: "
            f"{[r.retrieval_method for r in results]}"
        )


# ---------------------------------------------------------------------------
# HybridRetriever
# ---------------------------------------------------------------------------

class TestHybridRetriever:
    """HybridRetriever の動作検証。"""

    def test_add_and_search_returns_integrated_results(
        self, tmp_docs: list[Document]
    ) -> None:
        """add() 後 search() が vector と keyword を統合した結果を返す。"""
        retriever = HybridRetriever()
        retriever.add(tmp_docs)

        results = retriever.search("宿泊費 精算", top_k=3)

        assert len(results) > 0
        assert all(isinstance(r, ScoredDocument) for r in results)

    def test_retrieval_method_is_hybrid(self, tmp_docs: list[Document]) -> None:
        """結果の retrieval_method が 'hybrid' である。"""
        retriever = HybridRetriever()
        retriever.add(tmp_docs)

        results = retriever.search("交通費 精算", top_k=3)

        assert all(r.retrieval_method == "hybrid" for r in results), (
            f"全結果の retrieval_method が 'hybrid' であるべき: "
            f"{[r.retrieval_method for r in results]}"
        )

    def test_clear_then_search_returns_empty_list(
        self, tmp_docs: list[Document]
    ) -> None:
        """clear() 後に search() は空リストを返す。"""
        retriever = HybridRetriever()
        retriever.add(tmp_docs)
        retriever.clear()

        results = retriever.search("宿泊費", top_k=5)

        assert results == []

    def test_top_k_limits_result_count(self, tmp_docs: list[Document]) -> None:
        """top_k で件数が制限される。"""
        retriever = HybridRetriever()
        retriever.add(tmp_docs)

        results = retriever.search("費 円 精算", top_k=2)

        assert len(results) <= 2

    def test_empty_stores_returns_empty_list(self) -> None:
        """両方のストアが空のとき空リストを返す。"""
        retriever = HybridRetriever()

        results = retriever.search("宿泊費", top_k=5)

        assert results == []

    def test_vector_only_weight_matches_vector_store_top_result(
        self, tmp_docs: list[Document]
    ) -> None:
        """vector_weight=1.0, keyword_weight=0.0 で VectorStore と同等の結果になる。

        正規化によりスコア値は異なるが、上位ドキュメントの順序が一致することを確認する。
        """
        query = "宿泊費の上限"

        retriever = HybridRetriever(vector_weight=1.0, keyword_weight=0.0)
        retriever.add(tmp_docs)
        hybrid_results = retriever.search(query, top_k=3)

        vector_store = VectorStore()
        vector_store.add(tmp_docs)
        vector_results = vector_store.search(query, top_k=3)

        assert len(hybrid_results) > 0
        assert len(vector_results) > 0
        assert hybrid_results[0].document.text == vector_results[0].document.text, (
            f"vector_weight=1.0 のとき HybridRetriever の先頭ドキュメントが "
            f"VectorStore の先頭ドキュメントと一致するべき。\n"
            f"  hybrid[0]: {hybrid_results[0].document.text!r}\n"
            f"  vector[0]: {vector_results[0].document.text!r}"
        )
