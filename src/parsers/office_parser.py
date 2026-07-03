"""Word/Excel/PowerPoint パーサー。各ライブラリが未インストールならスタブを返す。"""
from pathlib import Path

from src.models import Document

SUPPORTED = {".docx", ".xlsx", ".pptx"}


class OfficeParser:
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in SUPPORTED

    def parse(self, file_path: Path) -> list[Document]:
        suffix = file_path.suffix.lower()
        if suffix == ".docx":
            return self._parse_docx(file_path)
        if suffix == ".xlsx":
            return self._parse_xlsx(file_path)
        if suffix == ".pptx":
            return self._parse_pptx(file_path)
        return []

    def _parse_docx(self, file_path: Path) -> list[Document]:
        try:
            import docx
        except ImportError:
            return [Document(text=f"[DOCX未解析: python-docx未インストール] {file_path.name}",
                             source_path=file_path, location="stub")]
        try:
            doc = docx.Document(str(file_path))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            return [Document(
                text=f"[DOCX解析失敗: パスワード保護または破損の可能性] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]
        return [Document(text=text, source_path=file_path, location="full")]

    def _parse_xlsx(self, file_path: Path) -> list[Document]:
        try:
            import openpyxl
        except ImportError:
            return [Document(text=f"[XLSX未解析: openpyxl未インストール] {file_path.name}",
                             source_path=file_path, location="stub")]
        try:
            wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
            docs = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = []
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) if c is not None else "" for c in row]
                    if any(c.strip() for c in cells):
                        rows.append(" | ".join(cells))
                if rows:
                    docs.append(Document(
                        text="\n".join(rows),
                        source_path=file_path,
                        location=f"sheet_{sheet_name}",
                    ))
        except Exception:
            return [Document(
                text=f"[XLSX解析失敗: パスワード保護または破損の可能性] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]
        return docs or [Document(text="", source_path=file_path, location="empty")]

    def _parse_pptx(self, file_path: Path) -> list[Document]:
        try:
            from pptx import Presentation
        except ImportError:
            return [Document(text=f"[PPTX未解析: python-pptx未インストール] {file_path.name}",
                             source_path=file_path, location="stub")]
        try:
            prs = Presentation(str(file_path))
            docs = []
            for i, slide in enumerate(prs.slides):
                texts = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        texts.append(shape.text)
                if texts:
                    docs.append(Document(
                        text="\n".join(texts),
                        source_path=file_path,
                        location=f"slide_{i+1}",
                    ))
        except Exception:
            return [Document(
                text=f"[PPTX解析失敗: パスワード保護または破損の可能性] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]
        return docs or [Document(text="", source_path=file_path, location="empty")]
