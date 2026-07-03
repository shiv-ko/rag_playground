"""PDFパーサー。pypdfが入っていれば使い、なければダミーを返す。"""
from pathlib import Path

from src.models import Document

SUPPORTED = {".pdf"}


class PDFParser:
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in SUPPORTED

    def parse(self, file_path: Path) -> list[Document]:
        try:
            import pypdf  # optional dependency
        except ImportError:
            return [Document(
                text=f"[PDF未解析: pypdfが未インストール] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]

        docs: list[Document] = []
        reader = pypdf.PdfReader(str(file_path))
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                docs.append(Document(
                    text=text,
                    source_path=file_path,
                    location=f"page_{i+1}",
                ))
        return docs or [Document(text="", source_path=file_path, location="empty")]
