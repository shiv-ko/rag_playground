"""Jupyter Notebook (.ipynb) 用パーサー。Markdown/コードセルのテキストのみ抽出する。"""
from __future__ import annotations

import json
from pathlib import Path

from src.models import Document

SUPPORTED = {".ipynb"}


class NotebookParser:
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in SUPPORTED

    def parse(self, file_path: Path) -> list[Document]:
        try:
            data = json.loads(file_path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            return [Document(
                text=f"[Notebook解析失敗] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]

        docs: list[Document] = []
        for i, cell in enumerate(data.get("cells", [])):
            source = cell.get("source", "")
            text = "".join(source) if isinstance(source, list) else str(source)
            if text.strip():
                cell_type = cell.get("cell_type", "unknown")
                docs.append(Document(
                    text=text,
                    source_path=file_path,
                    location=f"cell_{i+1}_{cell_type}",
                ))
        return docs or [Document(text="", source_path=file_path, location="empty")]
