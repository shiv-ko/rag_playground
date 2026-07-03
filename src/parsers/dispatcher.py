"""ファイル拡張子に応じて適切なパーサーへ振り分ける。"""
from pathlib import Path

from src.models import Document
from src.parsers.chunker import chunk_documents
from src.parsers.image_parser import ImageParser
from src.parsers.notebook_parser import NotebookParser
from src.parsers.office_parser import OfficeParser
from src.parsers.pdf_parser import PDFParser
from src.parsers.text_parser import TextParser

_NOISE_SUFFIXES = {".pyc", ".lock"}
_NOISE_DIR_NAMES = {"__pycache__"}


def _is_noise(file_path: Path) -> bool:
    if file_path.name.startswith("~$"):
        return True
    if file_path.suffix.lower() in _NOISE_SUFFIXES:
        return True
    if any(part in _NOISE_DIR_NAMES for part in file_path.parts):
        return True
    return False


def _extract_metadata(root: Path, file_path: Path) -> dict:
    try:
        rel_parts = file_path.relative_to(root).parts
    except ValueError:
        rel_parts = file_path.parts

    metadata: dict = {"project": None, "category": None, "is_internal": False}
    if "プロジェクト" in rel_parts:
        idx = rel_parts.index("プロジェクト")
        if idx + 1 < len(rel_parts):
            metadata["project"] = rel_parts[idx + 1]
        if idx + 2 < len(rel_parts):
            metadata["category"] = rel_parts[idx + 2]
    elif "社内管理" in rel_parts:
        metadata["is_internal"] = True
    return metadata


class ParserDispatcher:
    def __init__(self) -> None:
        self._parsers = [
            TextParser(),
            PDFParser(),
            OfficeParser(),
            NotebookParser(),
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
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            if _is_noise(file_path):
                continue
            file_docs = self.parse(file_path)
            metadata = _extract_metadata(directory, file_path)
            for doc in file_docs:
                doc.metadata.update(metadata)
            docs.extend(file_docs)
        return chunk_documents(docs)
