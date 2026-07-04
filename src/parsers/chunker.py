"""長文Documentを固定長・オーバーラップ付きでチャンク分割するユーティリティ。"""
from __future__ import annotations

from src.models import Document

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
SNAP_LOOKBACK = 300


def _snap_chunk_end(text: str, start: int, fixed_end: int, chunk_size: int) -> int:
    end = min(fixed_end, len(text))
    if end >= len(text):
        return end

    min_end = start + max(1, chunk_size - SNAP_LOOKBACK)
    if min_end >= end:
        return end

    for marker in ("\n\n", "。", "\n"):
        pos = text.rfind(marker, start, end)
        if pos != -1:
            snapped = pos + len(marker)
            if snapped >= min_end and snapped > start:
                return snapped
    return end


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
            fixed_end = start + chunk_size
            end = _snap_chunk_end(doc.text, start, fixed_end, chunk_size)
            chunk_index += 1
            result.append(Document(
                text=doc.text[start:end],
                source_path=doc.source_path,
                location=f"{doc.location}_chunk{chunk_index}",
                metadata=dict(doc.metadata),
            ))
            if end >= len(doc.text):
                break
            start = max(end - overlap, start + 1)
    return result
