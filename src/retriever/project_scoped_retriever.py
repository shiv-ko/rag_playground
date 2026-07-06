"""案件フォルダ絞り込み＋BM25検索を行うRetriever。

質問文から案件名を検出できた場合はその案件＋社内管理配下のみを対象にBM25検索し、
検出できない場合は全体（社内管理含む）を対象に検索する。
案件名リストはadd()時にDocument.metadata["project"]から動的に導出する（ハードコードしない）。
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from src.indexer.keyword_store import KeywordStore
from src.models import Document, ScoredDocument
from src.retriever.question_file_scope import find_named_files, question_mentions_extension

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
    """

    def __init__(self, project_aliases: dict[str, list[str]] | None = None) -> None:
        self._global_store = KeywordStore()
        self._project_stores: dict[str, KeywordStore] = {}
        self._project_names: list[str] = []
        self._aliases_by_normalized_name: dict[str, list[str]] = {
            _normalize_project_name(name): aliases
            for name, aliases in (project_aliases or {}).items()
        }

    def add(self, documents: list[Document]) -> None:
        self._global_store.add(documents)

        internal_docs = [d for d in documents if d.metadata.get("is_internal")]
        by_project: dict[str, list[Document]] = {}
        for doc in documents:
            project = doc.metadata.get("project")
            if project:
                by_project.setdefault(project, []).append(doc)

        for project, docs in by_project.items():
            if project not in self._project_stores:
                self._project_stores[project] = KeywordStore()
                self._project_names.append(project)
            self._project_stores[project].add(docs)
            if internal_docs:
                self._project_stores[project].add(internal_docs)

    def clear(self) -> None:
        self._global_store.clear()
        self._project_stores = {}
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

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        project = self.detect_project(query)
        store = self._project_stores[project] if project is not None else self._global_store
        if not question_mentions_extension(query):
            return store.search(query, top_k)

        # 名指しファイルのチャンクを優先する。候補を広めに取り、候補のbasename
        # 集合を既知名として質問文と部分文字列照合する（find_named_files）。
        # 一致ゼロなら従来結果と同一 — ハードフィルタにしない。
        candidates = store.search(query, top_k * 4)
        known_names = [c.document.source_path for c in candidates]
        matched_basenames = set(find_named_files(query, known_names))
        if not matched_basenames:
            return candidates[:top_k]

        matched: list[ScoredDocument] = []
        others: list[ScoredDocument] = []
        for c in candidates:
            basename = unicodedata.normalize("NFC", Path(str(c.document.source_path)).name)
            (matched if basename in matched_basenames else others).append(c)
        return (matched + others)[:top_k]
