"""ProjectScopedRetriever の検索スコープ制御テスト。"""
from __future__ import annotations

from pathlib import Path

from src.models import Document, ScoredDocument
from src.retriever.project_scoped_retriever import ProjectScopedRetriever


def _doc(text: str, path: str, project: str = "A社") -> Document:
    return Document(
        text=text,
        source_path=Path(path),
        location="sheet_1",
        metadata={"project": project},
    )


class _CapturingStore:
    """store.search() に渡された query 文字列を記録するテスト用フェイク。"""

    def __init__(self, docs: list[Document] | None = None) -> None:
        self.received_queries: list[str] = []
        self._docs = docs or []

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        self.received_queries.append(query)
        return [
            ScoredDocument(document=d, score=1.0, retrieval_method="keyword")
            for d in self._docs[:top_k]
        ]


def test_search_prioritizes_explicitly_named_file():
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("スケジュール タスク 進捗 管理 一覧 計画", "data/A社/02.計画/計画.xlsx"),
        _doc("スケジュール タスク 進捗 担当 記録", "data/A社/02.計画/計画_r2.xlsx"),
    ])
    results = retriever.search("A社の計画_r2.xlsxのスケジュールでタスクの進捗は？", top_k=1)
    assert results[0].document.source_path.name == "計画_r2.xlsx"


def test_search_without_file_name_is_unchanged():
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("宿泊費 上限 規定", "data/A社/規定.docx"),
    ])
    results = retriever.search("A社の宿泊費の上限は？", top_k=5)
    assert len(results) == 1


def test_search_falls_back_when_named_file_has_no_chunks():
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("スケジュール タスク 進捗", "data/A社/02.計画/計画.xlsx"),
    ])
    results = retriever.search("A社の存在しない.xlsxのスケジュールは？", top_k=5)
    assert len(results) == 1


def test_search_prioritizes_file_name_containing_particle_kana():
    """ファイル名の内部に助詞かな（もり等）を含む合成ファイル名でも、
    known basenameとの部分文字列照合（find_named_files経由）で名指し優先が発火する
    ことを確認する回帰テスト（旧実装は助詞かなを境界文字として扱い切り詰めていた）。"""
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("スケジュール タスク 進捗 管理 一覧", "data/A社/02.見積/一覧.xlsx"),
        _doc("スケジュール タスク 進捗 担当 記録", "data/A社/02.見積/見積もり一覧.xlsx"),
    ])
    results = retriever.search("A社の見積もり一覧.xlsxのスケジュールでタスクの進捗は？", top_k=1)
    assert results[0].document.source_path.name == "見積もり一覧.xlsx"


def test_title_slide_no_longer_outranks_relevant_chunk_after_token_stripping():
    """タイトルスライド汚染の回帰テスト（Task 3案A）。

    スコープ済みストアでは案件名トークンは全チャンク共通で識別力ゼロなのに、
    表紙スライド（案件名を繰り返すだけで内容に無関係）がBM25で不当に上位化され、
    実際に関連する内容チャンクを押し出してしまう。案件名・エイリアストークンを
    クエリから除去すれば、内容が一致する方が正しく1位になるはず。
    """
    retriever = ProjectScopedRetriever(project_aliases={"A社": ["エーシャ"]})

    cover_slide = _doc(
        ("A社 " * 15) + "エーシャ 提案書 表紙 概要",
        "data/A社/資料/提案書.pptx",
    )
    relevant_slide = _doc(
        "判定基準は正解率と再現率とF値を用いる。しきい値は0.5固定とする。",
        "data/A社/資料/評価.pptx",
    )
    filler_docs = [
        _doc(f"無関係な内容の埋め草チャンク番号{i} 天気 交通 雑談", f"data/A社/filler/f{i}.docx")
        for i in range(8)
    ]
    retriever.add([cover_slide, relevant_slide, *filler_docs])

    results = retriever.search("A社のモデルの性能はどう評価する？", top_k=1)

    assert results[0].document.source_path.name == "評価.pptx"


def test_search_strips_project_and_alias_tokens_from_scoped_query():
    """スコープ確定後、検索クエリから案件名・エイリアストークンが除去されること。"""
    retriever = ProjectScopedRetriever(project_aliases={"A社": ["エーシャ"]})
    retriever.add([_doc("本文", "data/A社/資料.docx")])

    fake_store = _CapturingStore([_doc("本文", "data/A社/資料.docx")])
    retriever._project_stores["A社"] = fake_store

    retriever.search("A社の評価指標は？", top_k=5)
    assert fake_store.received_queries
    query_used = fake_store.received_queries[-1]
    assert "A社" not in query_used
    assert "評価指標" in query_used

    fake_store.received_queries.clear()
    retriever.search("エーシャの評価指標は？", top_k=5)
    query_used = fake_store.received_queries[-1]
    assert "エーシャ" not in query_used
    assert "評価指標" in query_used


def test_search_falls_back_to_original_query_when_stripped_query_is_empty():
    """除去後クエリが空文字になる場合は、元クエリのまま検索してフォールバックする。"""
    retriever = ProjectScopedRetriever(project_aliases={"A社": ["エーシャ"]})
    retriever.add([_doc("本文", "data/A社/資料.docx")])

    fake_store = _CapturingStore([_doc("本文", "data/A社/資料.docx")])
    retriever._project_stores["A社"] = fake_store

    results = retriever.search("A社", top_k=5)

    assert fake_store.received_queries[-1] == "A社"
    assert len(results) == 1


def test_search_does_not_strip_tokens_when_no_project_detected():
    """案件が検出できない（全体検索）場合はクエリを一切加工しない。"""
    retriever = ProjectScopedRetriever(project_aliases={"A社": ["エーシャ"]})
    retriever.add([_doc("本文", "data/A社/資料.docx")])

    fake_global_store = _CapturingStore([_doc("本文", "data/A社/資料.docx")])
    retriever._global_store = fake_global_store

    query = "無関係な質問です。案件名は含まれません。"
    retriever.search(query, top_k=5)

    assert fake_global_store.received_queries == [query]
