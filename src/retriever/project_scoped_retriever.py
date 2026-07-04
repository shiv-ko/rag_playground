"""案件フォルダ絞り込み＋BM25検索を行うRetriever。

質問文から案件名を検出できた場合はその案件＋社内管理配下のみを対象にBM25検索し、
検出できない場合は全体（社内管理含む）を対象に検索する。
案件名リストはadd()時にDocument.metadata["project"]から動的に導出する（ハードコードしない）。
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from src.indexer.keyword_store import KeywordStore
from src.models import Document, ScoredDocument

_CORPORATE_AFFIXES = ("株式会社", "医療法人社団", "有限会社", "合同会社")
_FILE_HINT_RE = re.compile(r"(?P<name>[^\s/\\]+?\.(?:ipynb|py|csv|xlsx|docx|pptx|pdf))", re.IGNORECASE)


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
        self._global_docs: list[Document] = []
        self._project_docs: dict[str, list[Document]] = {}
        self._project_names: list[str] = []
        self._aliases_by_normalized_name: dict[str, list[str]] = {
            _normalize_project_name(name): aliases
            for name, aliases in (project_aliases or {}).items()
        }

    def add(self, documents: list[Document]) -> None:
        self._global_store.add(documents)
        self._global_docs.extend(documents)

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
            self._project_docs.setdefault(project, []).extend(docs)
            if internal_docs:
                self._project_stores[project].add(internal_docs)
                self._project_docs[project].extend(internal_docs)

    def clear(self) -> None:
        self._global_store.clear()
        self._project_stores = {}
        self._global_docs = []
        self._project_docs = {}
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
        if project is not None:
            search_query = self._query_without_project_terms(query, project)
            results = self._project_stores[project].search(search_query, top_k)
            return self._ensure_file_hint_result(query, search_query, results, self._project_docs.get(project, []), top_k)
        results = self._global_store.search(query, top_k)
        return self._ensure_file_hint_result(query, query, results, self._global_docs, top_k)

    def _query_without_project_terms(self, query: str, project: str) -> str:
        normalized_query = unicodedata.normalize("NFC", query)
        terms = [
            unicodedata.normalize("NFC", project),
            _normalize_project_name(project),
            *[
                unicodedata.normalize("NFC", alias)
                for alias in self._aliases_by_normalized_name.get(_normalize_project_name(project), [])
            ],
            *[
                _normalize_project_name(alias)
                for alias in self._aliases_by_normalized_name.get(_normalize_project_name(project), [])
            ],
        ]
        rewritten = normalized_query
        for term in sorted({t for t in terms if t}, key=len, reverse=True):
            rewritten = rewritten.replace(term, "")
        rewritten = re.sub(r"\s+", " ", rewritten).strip()
        return rewritten or query

    def _ensure_file_hint_result(
        self,
        original_query: str,
        search_query: str,
        results: list[ScoredDocument],
        docs: list[Document],
        top_k: int,
    ) -> list[ScoredDocument]:
        hints = _file_hints(original_query)
        if not hints:
            return results
        if any(_matches_any_hint(r.document.source_path, hints) for r in results):
            return results

        matching_docs = [doc for doc in docs if _matches_any_hint(doc.source_path, hints)]
        if not matching_docs:
            return results

        store = KeywordStore()
        store.add(matching_docs)
        candidates = store.search(search_query, 1)
        injected = candidates[0] if candidates else ScoredDocument(
            document=matching_docs[0], score=0.0, retrieval_method="keyword"
        )

        kept = results[: max(0, top_k - 1)]
        return [injected, *kept][:top_k]


def _file_hints(query: str) -> list[str]:
    return [
        unicodedata.normalize("NFC", match.group("name")).lower()
        for match in _FILE_HINT_RE.finditer(query)
    ]


def _matches_any_hint(path: Path, hints: list[str]) -> bool:
    normalized = unicodedata.normalize("NFC", str(path)).lower()
    return any(normalized.endswith(hint) for hint in hints)
