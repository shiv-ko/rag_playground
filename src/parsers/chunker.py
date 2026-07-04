"""長文Documentを固定長・オーバーラップ付きでチャンク分割するユーティリティ。"""
from __future__ import annotations

from src.models import Document

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def chunk_documents(
    documents: list[Document],
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[Document]:
    """text が chunk_size を超える Document を overlap 分重複させながら分割する。"""
    result: list[Document] = []
    for doc in documents:
        if len(doc.text) <= chunk_size:
            result.append(doc)
            continue

        step = chunk_size - overlap
        start = 0
        chunk_index = 0
        while start < len(doc.text):
            end = start + chunk_size
            chunk_index += 1
            result.append(Document(
                text=doc.text[start:end],
                source_path=doc.source_path,
                location=f"{doc.location}_chunk{chunk_index}",
                metadata=dict(doc.metadata),
            ))
            if end >= len(doc.text):
                break
            start += step
    return result
