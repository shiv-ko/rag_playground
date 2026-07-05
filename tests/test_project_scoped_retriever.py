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
