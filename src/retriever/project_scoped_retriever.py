"""案件フォルダ絞り込み＋BM25検索を行うRetriever。

質問文から案件名を検出できた場合はその案件＋社内管理配下のみを対象にBM25検索し、
検出できない場合は全体（社内管理含む）を対象に検索する。
案件名リストはadd()時にDocument.metadata["project"]から動的に導出する（ハードコードしない）。
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from src.indexer.embedder import Embedder
from src.indexer.keyword_store import KeywordStore
from src.retriever.hybrid_retriever import HybridRetriever
from src.models import Document, ScoredDocument
from src.retriever.question_file_scope import (
    find_named_files,
    find_question_stem_matches,
    find_stem_matches,
    question_mentions_extension,
)

_CORPORATE_AFFIXES = ("株式会社", "医療法人社団", "有限会社", "合同会社")


def _normalize_project_name(name: str) -> str:
    # macOSのファイルシステムはユニコードをNFD分解して返すため、
    # ディレクトリ名由来のproject名とNFCのクエリ文字列がバイト列として
    # 不一致になりうる。NFCに正規化してから比較する。
    result = unicodedata.normalize("NFC", name)
    for affix in _CORPORATE_AFFIXES:
        result = result.replace(affix, "")
    return result.strip()


class ProjectScopedRetriever:
    """
    add() は全ドキュメントを1回でまとめて渡す想定（Pipeline.build_indexの使い方と一致）。
    embedderを渡すとBM25+ベクトルのハイブリッド検索になる（未指定時は既存のBM25単体のまま）。
    """

    def __init__(
        self,
        project_aliases: dict[str, list[str]] | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._embedder = embedder
        self._global_store = self._make_store()
        self._global_documents: list[Document] = []
        self._global_source_paths: list[Path] = []
        self._project_stores: dict[str, KeywordStore | HybridRetriever] = {}
        self._project_documents: dict[str, list[Document]] = {}
        self._project_source_paths: dict[str, list[Path]] = {}
        self._project_names: list[str] = []
        self._aliases_by_normalized_name: dict[str, list[str]] = {
            _normalize_project_name(name): aliases
            for name, aliases in (project_aliases or {}).items()
        }

    def _make_store(self) -> KeywordStore | HybridRetriever:
        if self._embedder is not None:
            return HybridRetriever(embedder=self._embedder)
        return KeywordStore()

    def add(self, documents: list[Document]) -> None:
        self._global_store.add(documents)
        self._global_documents.extend(documents)
        self._global_source_paths = _unique_source_paths(self._global_documents)

        internal_docs = [d for d in documents if d.metadata.get("is_internal")]
        by_project: dict[str, list[Document]] = {}
        for doc in documents:
            project = doc.metadata.get("project")
            if project:
                by_project.setdefault(project, []).append(doc)

        for project, docs in by_project.items():
            if project not in self._project_stores:
                self._project_stores[project] = self._make_store()
                self._project_documents[project] = []
                self._project_source_paths[project] = []
                self._project_names.append(project)
            self._project_stores[project].add(docs)
            self._project_documents[project].extend(docs)
            if internal_docs:
                self._project_stores[project].add(internal_docs)
                self._project_documents[project].extend(internal_docs)
            self._project_source_paths[project] = _unique_source_paths(
                self._project_documents[project]
            )

    def clear(self) -> None:
        self._global_store.clear()
        self._global_documents = []
        self._global_source_paths = []
        self._project_stores = {}
        self._project_documents = {}
        self._project_source_paths = {}
        self._project_names = []

    def detect_project(self, query: str) -> str | None:
        normalized_query = unicodedata.normalize("NFC", query)
        for name in self._project_names:
            normalized = _normalize_project_name(name)
            if normalized and normalized in normalized_query:
                return name
        for name in self._project_names:
            aliases = self._aliases_by_normalized_name.get(_normalize_project_name(name), [])
            for alias in aliases:
                normalized_alias = _normalize_project_name(alias)
                if normalized_alias and normalized_alias in normalized_query:
                    return name
        return None

    def search(
        self,
        query: str,
        top_k: int = 5,
        term_hints: list[str] | None = None,
    ) -> list[ScoredDocument]:
        project = self.detect_project(query)
        store = self._project_stores[project] if project is not None else self._global_store
        scope_documents = (
            self._project_documents[project]
            if project is not None
            else self._global_documents
        )
        scope_source_paths = (
            self._project_source_paths[project]
            if project is not None
            else self._global_source_paths
        )
        mentions_extension = question_mentions_extension(query)
        hints = [h for h in (term_hints or []) if h]

        # 名指しファイル・質問中の拡張子なしstem・用語集展開語
        # （例: "CT"→"契約書"）に一致するファイルのチャンクを優先する。
        # 通常のtop_k候補外にある名指しファイルも検出できるよう、検出済み
        # project（未検出時は全体）の全source_pathと照合する。
        known_names = scope_source_paths
        matched_basenames: set[str] = set()
        if mentions_extension:
            matched_basenames.update(find_named_files(query, known_names))
        matched_basenames.update(find_question_stem_matches(query, known_names))
        if hints:
            matched_basenames.update(find_stem_matches(hints, known_names))
        if not matched_basenames:
            return store.search(query, top_k)

        # 一致時だけ通常より広めの候補を取得する。
        # BM25はscore=0のチャンクを返さないため、名指しsourceのみ
        # 後段で補完し、本文にquery語がなくても根拠候補から落とさない。
        candidates = store.search(query, top_k * 4)

        matched: list[ScoredDocument] = []
        others: list[ScoredDocument] = []
        seen_document_ids: set[int] = set()
        for c in candidates:
            basename = unicodedata.normalize("NFC", Path(str(c.document.source_path)).name)
            (matched if basename in matched_basenames else others).append(c)
            seen_document_ids.add(id(c.document))
        for document in scope_documents:
            basename = unicodedata.normalize("NFC", Path(str(document.source_path)).name)
            if basename in matched_basenames and id(document) not in seen_document_ids:
                matched.append(
                    ScoredDocument(
                        document=document,
                        score=0.0,
                        retrieval_method="named_file",
                    )
                )
        return (matched + others)[:top_k]


def _unique_source_paths(documents: list[Document]) -> list[Path]:
    """同一ファイル由来の複数チャンクを、NFCを考慮して1パスにまとめる。"""
    paths: dict[str, Path] = {}
    for document in documents:
        path = Path(str(document.source_path))
        key = unicodedata.normalize("NFC", str(path)).casefold()
        paths.setdefault(key, path)
    return list(paths.values())
