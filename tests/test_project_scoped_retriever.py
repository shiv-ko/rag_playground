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
