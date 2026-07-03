"""ProjectScopedRetriever (案件フォルダ絞り込み＋BM25) のテスト。"""
from __future__ import annotations

from pathlib import Path

from src.models import Document
from src.retriever.project_scoped_retriever import (
    ProjectScopedRetriever,
    _normalize_project_name,
)


def _doc(text: str, project: str | None = None, is_internal: bool = False, path: str = "x.txt") -> Document:
    return Document(
        text=text,
        source_path=Path(path),
        metadata={"project": project, "is_internal": is_internal},
    )


class TestNormalizeProjectName:
    def test_strips_kabushiki_gaisha_prefix(self) -> None:
        assert _normalize_project_name("株式会社青潮モビリティサービス") == "青潮モビリティサービス"

    def test_strips_kabushiki_gaisha_suffix(self) -> None:
        assert _normalize_project_name("白峰信用リスク評価株式会社") == "白峰信用リスク評価"

    def test_strips_iryouhoujin_prefix(self) -> None:
        assert _normalize_project_name("医療法人社団 恒一会 かえで総合病院") == "恒一会 かえで総合病院"


class TestProjectScopedRetriever:
    def test_query_mentioning_project_is_scoped_to_that_project(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [
            _doc("青潮モビリティサービスの需要予測結果です。", project="株式会社青潮モビリティサービス"),
            _doc("かえで総合病院の患者数データです。", project="医療法人社団 恒一会 かえで総合病院"),
        ]
        retriever.add(docs)

        results = retriever.search("青潮モビリティサービスの需要予測について教えてください", top_k=5)

        assert len(results) == 1
        assert "青潮モビリティサービス" in results[0].document.text

    def test_internal_docs_are_always_included_in_project_scope(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [
            _doc("青潮モビリティサービスの需要予測結果です。", project="株式会社青潮モビリティサービス"),
            _doc("社内用語集: TGは目的変数の略。", is_internal=True),
        ]
        retriever.add(docs)

        results = retriever.search("青潮モビリティサービスのTGについて教えてください", top_k=5)

        texts = [r.document.text for r in results]
        assert any("社内用語集" in t for t in texts)

    def test_query_without_known_project_falls_back_to_global_search(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [
            _doc("青潮モビリティサービスの需要予測結果です。", project="株式会社青潮モビリティサービス"),
            _doc("かえで総合病院の患者数データです。", project="医療法人社団 恒一会 かえで総合病院"),
        ]
        retriever.add(docs)

        results = retriever.search("患者数データについて教えてください", top_k=5)

        assert any("かえで総合病院" in r.document.text for r in results)

    def test_detect_project_returns_none_when_no_match(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [_doc("テキスト", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)

        assert retriever.detect_project("無関係な質問です") is None

    def test_detect_project_returns_matching_project_name(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [_doc("テキスト", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)

        assert retriever.detect_project("青潮モビリティサービスについて") == "株式会社青潮モビリティサービス"

    def test_clear_resets_all_stores(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [_doc("テキスト", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)
        retriever.clear()

        assert retriever.detect_project("青潮モビリティサービス") is None
        assert retriever.search("青潮モビリティサービス", top_k=5) == []
