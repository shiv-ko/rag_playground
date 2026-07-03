from typing import Protocol, runtime_checkable

from src.models import Document, ScoredDocument


@runtime_checkable
class Indexer(Protocol):
    def add(self, documents: list[Document]) -> None:
        """ドキュメントをインデックスに追加する。"""
        ...

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        """クエリに対してスコア付きドキュメントをtop_k件返す。"""
        ...

    def clear(self) -> None:
        """インデックスをリセットする。"""
        ...
