"""ProjectScopedRetriever (案件フォルダ絞り込み＋BM25) のテスト。"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from src.models import Document
from src.retriever.project_scoped_retriever import (
    ProjectScopedRetriever,
    _normalize_project_name,
)


class CapturingStore:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, top_k: int = 5) -> list:
        self.queries.append(query)
        return []


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

    def test_normalizes_nfd_to_nfc(self) -> None:
        """macOSのファイルシステムはユニコードをNFD分解して返すため、
        ディレクトリ名由来のproject名(NFD)とクエリ文字列(NFC)がバイト列として
        不一致になりうる。正規化して同一視する。"""
        nfd_name = unicodedata.normalize("NFD", "青潮モビリティサービス")
        assert nfd_name != "青潮モビリティサービス"  # 前提: 実際に異なるバイト列
        assert _normalize_project_name(nfd_name) == "青潮モビリティサービス"


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

    def test_detect_project_matches_despite_nfd_project_name(self) -> None:
        """project名がNFD分解されたファイルシステム由来でも、NFCのクエリで検出できる。"""
        retriever = ProjectScopedRetriever()
        nfd_name = unicodedata.normalize("NFD", "株式会社青潮モビリティサービス")
        assert nfd_name != "株式会社青潮モビリティサービス"
        docs = [_doc("テキスト", project=nfd_name)]
        retriever.add(docs)

        assert retriever.detect_project("青潮モビリティサービスについて") == nfd_name

    def test_clear_resets_all_stores(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [_doc("テキスト", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)
        retriever.clear()

        assert retriever.detect_project("青潮モビリティサービス") is None
        assert retriever.search("青潮モビリティサービス", top_k=5) == []

    def test_detect_project_matches_via_alias(self) -> None:
        """project_registry.json由来のエイリアスでも案件を検出できる。"""
        retriever = ProjectScopedRetriever(
            project_aliases={"株式会社青潮モビリティサービス": ["AOSHIO", "青潮"]}
        )
        docs = [_doc("需要予測データです。", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)

        assert retriever.detect_project("AOSHIOの需要予測について") == "株式会社青潮モビリティサービス"

    def test_detect_project_alias_does_not_leak_to_other_project(self) -> None:
        retriever = ProjectScopedRetriever(
            project_aliases={
                "株式会社青潮モビリティサービス": ["AOSHIO"],
                "医療法人社団 恒一会 かえで総合病院": ["KAEDE"],
            }
        )
        docs = [
            _doc("需要予測データです。", project="株式会社青潮モビリティサービス"),
            _doc("患者数データです。", project="医療法人社団 恒一会 かえで総合病院"),
        ]
        retriever.add(docs)

        assert retriever.detect_project("KAEDEの患者数について") == "医療法人社団 恒一会 かえで総合病院"

    def test_detect_project_without_aliases_arg_still_works(self) -> None:
        """project_aliases省略時は従来通り正式名称のみで検出する。"""
        retriever = ProjectScopedRetriever()
        docs = [_doc("テキスト", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)

        assert retriever.detect_project("青潮モビリティサービスについて") == "株式会社青潮モビリティサービス"

    def test_scoped_search_removes_project_alias_tokens_from_query(self) -> None:
        retriever = ProjectScopedRetriever(
            project_aliases={"株式会社青潮モビリティサービス": ["AOSHIO", "青潮"]}
        )
        retriever.add([_doc("Recall が評価指標です。", project="株式会社青潮モビリティサービス")])
        store = CapturingStore()
        retriever._project_stores["株式会社青潮モビリティサービス"] = store  # type: ignore[assignment]

        retriever.search("AOSHIOの評価指標", top_k=5)

        assert store.queries == ["の評価指標"]

    def test_scoped_search_keeps_original_query_when_alias_removal_makes_empty(self) -> None:
        retriever = ProjectScopedRetriever(project_aliases={"株式会社青潮モビリティサービス": ["AOSHIO"]})
        retriever.add([_doc("AOSHIO", project="株式会社青潮モビリティサービス")])
        store = CapturingStore()
        retriever._project_stores["株式会社青潮モビリティサービス"] = store  # type: ignore[assignment]

        retriever.search("AOSHIO", top_k=5)

        assert store.queries == ["AOSHIO"]

    def test_unscoped_search_does_not_rewrite_query(self) -> None:
        retriever = ProjectScopedRetriever(project_aliases={"株式会社青潮モビリティサービス": ["AOSHIO"]})
        retriever.add([_doc("AOSHIO", project="株式会社青潮モビリティサービス")])
        store = CapturingStore()
        retriever._global_store = store  # type: ignore[assignment]

        retriever.search("未知案件の評価指標", top_k=5)

        assert store.queries == ["未知案件の評価指標"]

    def test_explicit_file_name_hint_injects_matching_file_when_absent_from_top_k(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [
            _doc("需要予測の概要です。", project="A社", path="x/foo.ipynb"),
            _doc("需要予測の詳細です。", project="A社", path="x/bar.ipynb"),
        ]
        retriever.add(docs)

        results = retriever.search("foo.ipynbの出力は？ 需要予測", top_k=1)

        assert results
        assert results[0].document.source_path.name == "foo.ipynb"

    def test_file_name_hint_missing_from_index_keeps_results_unchanged(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [
            _doc("需要予測の詳細です。", project="A社", path="x/bar.ipynb"),
        ]
        retriever.add(docs)

        hinted = retriever.search("foo.ipynbの出力は？ 需要予測", top_k=1)
        plain = retriever.search("需要予測", top_k=1)

        assert [r.document.source_path for r in hinted] == [r.document.source_path for r in plain]

    def test_file_name_hint_matches_case_and_unicode_normalized_suffix(self) -> None:
        retriever = ProjectScopedRetriever()
        nfd_path = unicodedata.normalize("NFD", "x/データ.IPYNB")
        docs = [
            _doc("分析出力です。", project="A社", path=nfd_path),
            _doc("分析出力です。", project="A社", path="x/other.ipynb"),
        ]
        retriever.add(docs)

        results = retriever.search("データ.ipynbの分析出力", top_k=1)

        assert results
        assert unicodedata.normalize("NFC", results[0].document.source_path.name).lower() == "データ.ipynb"
