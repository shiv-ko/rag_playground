"""ProjectScopedRetriever の検索スコープ制御テスト。"""
from __future__ import annotations

from pathlib import Path

from src.models import Document
from src.retriever.project_scoped_retriever import ProjectScopedRetriever


def _doc(text: str, path: str, project: str = "A社") -> Document:
    return Document(
        text=text,
        source_path=Path(path),
        location="sheet_1",
        metadata={"project": project},
    )


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


def test_search_prioritizes_file_by_term_hint_without_extension_in_question():
    """質問文に拡張子は現れないが、term_hints（QueryExpanderの展開語）が
    候補basenameのstemと一致する場合、named-file boostingが発火する
    （"CT"→"契約書"の展開語ヒント経由でcontractスコープが効くケースを模す）。"""
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("業務範囲 章 データ 前提 制約", "data/A社/01.契約/契約書.docx"),
        _doc("市場規模 分析 章 4.1 概況", "data/A社/04.分析/データサイエンティスト調査.docx"),
    ])
    results = retriever.search(
        "A社のCTにおいて、章番号は？ 契約書", top_k=1, term_hints=["契約書"]
    )
    assert results[0].document.source_path.name == "契約書.docx"


def test_search_term_hints_do_not_affect_other_project_stem_matches():
    """term_hintsがマッチするstemは同一project内のみ考慮される
    （detect_projectで既にスコープされているため、他案件の同名stemに引きずられない）。"""
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("業務範囲 章 データ", "data/A社/01.契約/契約書.docx"),
        _doc("別案件の契約内容", "data/B社/01.契約/契約書.docx", project="B社"),
    ])
    results = retriever.search("A社のCTについて 契約書", top_k=5, term_hints=["契約書"])
    assert all(r.document.metadata.get("project") == "A社" for r in results)


def test_search_term_hints_without_match_falls_back_unchanged():
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("宿泊費 上限 規定", "data/A社/規定.docx"),
    ])
    results = retriever.search("A社の宿泊費の上限は？", top_k=5, term_hints=["契約書"])
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


def test_search_prioritizes_extensionless_named_stem_outside_normal_candidate_pool():
    retriever = ProjectScopedRetriever()
    distractors = [
        _doc("pdays -1 値 意味 分析 " * 3, f"data/A社/分析_{i}.md")
        for i in range(8)
    ]
    target = _doc("未連絡", "data/A社/03.データ/カラム説明.md")
    retriever.add(distractors + [target])

    results = retriever.search(
        "A社のカラム説明において、pdaysの-1は何を表す？", top_k=1
    )

    assert results[0].document.source_path.name == "カラム説明.md"


def test_search_extensionless_stem_keeps_same_named_files_in_detected_project_only():
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("第一の定義", "data/A社/03.データ/用語説明.md"),
        _doc("第二の定義", "data/A社/04.分析/用語説明.md"),
        _doc("値 定義 意味", "data/B社/03.データ/用語説明.md", project="B社"),
    ])

    results = retriever.search("A社の用語説明において定義は？", top_k=2)

    assert len(results) == 2
    assert all(r.document.source_path.name == "用語説明.md" for r in results)
    assert all(r.document.metadata.get("project") == "A社" for r in results)


def test_search_extensionless_stem_does_not_boost_partial_or_short_matches():
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("無関係", "data/A社/説明.md"),
        _doc("無関係", "data/A社/表.md"),
        _doc("カラム 説明 値 定義", "data/A社/検索結果.md"),
    ])

    partial = retriever.search("A社のカラム説明において値は？", top_k=1)
    short = retriever.search("A社の表においてカラムの値は？", top_k=1)

    assert partial[0].document.source_path.name == "検索結果.md"
    assert short[0].document.source_path.name == "検索結果.md"


def test_search_extensionless_stem_works_with_hybrid_store():
    import numpy as np

    class _DistractorFavoringEmbedder:
        def embed_documents(self, texts: list[str]) -> np.ndarray:
            return np.asarray([[1.0] if "無関係" in text else [0.0] for text in texts])

        def embed_query(self, text: str) -> np.ndarray:
            return np.asarray([1.0])

    retriever = ProjectScopedRetriever(embedder=_DistractorFavoringEmbedder())
    retriever.add([
        _doc("無関係 カラム 値", "data/A社/提案書.md"),
        _doc("未連絡", "data/A社/カラム説明.md"),
    ])

    results = retriever.search("A社のカラム説明において値は？", top_k=1)

    assert results[0].document.source_path.name == "カラム説明.md"


def test_search_checks_each_source_path_once_for_extensionless_stem(monkeypatch):
    seen_names: list[object] = []

    def capture_names(question, known_names):
        seen_names.extend(known_names)
        return []

    monkeypatch.setattr(
        "src.retriever.project_scoped_retriever.find_question_stem_matches",
        capture_names,
    )
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("チャンク1", "data/A社/同じファイル.md"),
        _doc("チャンク2", "data/A社/同じファイル.md"),
    ])

    retriever.search("A社の質問", top_k=1)

    assert [Path(str(name)).name for name in seen_names] == ["同じファイル.md"]


def test_search_uses_hybrid_retriever_when_embedder_given():
    import numpy as np
    from src.indexer.embedder import Embedder

    class _StubEmbedder:
        def embed_documents(self, texts: list[str]) -> np.ndarray:
            return np.zeros((len(texts), 2), dtype=np.float32)

        def embed_query(self, text: str) -> np.ndarray:
            return np.zeros(2, dtype=np.float32)

    retriever = ProjectScopedRetriever(embedder=_StubEmbedder())
    retriever.add([_doc("スケジュール タスク 進捗", "data/A社/02.計画/計画.xlsx")])

    from src.retriever.hybrid_retriever import HybridRetriever
    assert isinstance(retriever._global_store, HybridRetriever)

    results = retriever.search("A社のスケジュールでタスクの進捗は？", top_k=1)
    assert len(results) == 1


def test_search_without_embedder_still_uses_keyword_store():
    from src.indexer.keyword_store import KeywordStore

    retriever = ProjectScopedRetriever()
    retriever.add([_doc("スケジュール タスク 進捗", "data/A社/02.計画/計画.xlsx")])
    assert isinstance(retriever._global_store, KeywordStore)
