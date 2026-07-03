"""ファイル拡張子に応じて適切なパーサーへ振り分ける。"""
from pathlib import Path

from src.models import Document
from src.parsers.image_parser import ImageParser
from src.parsers.office_parser import OfficeParser
from src.parsers.pdf_parser import PDFParser
from src.parsers.text_parser import TextParser


class ParserDispatcher:
    def __init__(self) -> None:
        self._parsers = [
            TextParser(),
            PDFParser(),
            OfficeParser(),
            ImageParser(),
        ]

    def parse(self, file_path: Path) -> list[Document]:
        for parser in self._parsers:
            if parser.can_handle(file_path):
                return parser.parse(file_path)
        return [Document(
            text=f"[未対応形式: {file_path.suffix}] {file_path.name}",
            source_path=file_path,
            location="unsupported",
        )]

    def parse_directory(self, directory: Path) -> list[Document]:
        docs: list[Document] = []
        for file_path in sorted(directory.rglob("*")):
            if file_path.is_file() and not file_path.name.startswith("."):
                docs.extend(self.parse(file_path))
        return docs
