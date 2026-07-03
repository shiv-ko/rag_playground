"""プレーンテキスト/Markdown用パーサー（本番でも使える軽量実装）。"""
from pathlib import Path

from src.models import Document

SUPPORTED = {".txt", ".md", ".csv", ".json", ".tsv"}


class TextParser:
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in SUPPORTED

    def parse(self, file_path: Path) -> list[Document]:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        return [Document(text=text, source_path=file_path, location="full")]
