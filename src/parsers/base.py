from pathlib import Path
from typing import Protocol, runtime_checkable

from src.models import Document


@runtime_checkable
class Parser(Protocol):
    def parse(self, file_path: Path) -> list[Document]:
        """ファイルをパースしてDocumentのリストを返す。1ファイル→複数チャンク可。"""
        ...

    def can_handle(self, file_path: Path) -> bool:
        """このパーサーが対象ファイルを処理できるか判定する。"""
        ...
