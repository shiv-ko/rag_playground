"""長文Documentを固定長・オーバーラップ付きでチャンク分割するユーティリティ。"""
from __future__ import annotations

from src.models import Document

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# 行の途中でチャンクが切れると、条件式のようなワンライナーが泣き別れて
# 部分コードから誤断定するリスクがある（実測: valid Q28）。スナップは
# ウィンドウの後半分までに留め、極端に短いチャンクが生まれるのを防ぐ。
_MIN_SNAP_RATIO = 0.5


def _snap_end_to_line_boundary(text: str, window_start: int, ideal_end: int) -> int:
    """ideal_end付近の行境界（空行優先、無ければ改行）にスナップする。
    ウィンドウ後半に境界が無ければ、無限ループを避けるため元のideal_endを返す
    （改行が一切ない巨大な1行のテキスト等の安全側フォールバック）。"""
    if ideal_end >= len(text):
        return ideal_end
    min_end = window_start + max(1, int((ideal_end - window_start) * _MIN_SNAP_RATIO))

    blank = text.rfind("\n\n", min_end, ideal_end)
    if blank != -1:
        return blank + 2
    newline = text.rfind("\n", min_end, ideal_end)
    if newline != -1:
        return newline + 1
    return ideal_end


def chunk_documents(
    documents: list[Document],
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[Document]:
    """text が chunk_size を超える Document を overlap 分重複させながら分割する。
    分割位置は可能な限り行境界にスナップし、行の途中でチャンクが切れないようにする。"""
    result: list[Document] = []
    for doc in documents:
        text = doc.text
        if len(text) <= chunk_size:
            result.append(doc)
            continue

        start = 0
        chunk_index = 0
        while start < len(text):
            ideal_end = start + chunk_size
            end = _snap_end_to_line_boundary(text, start, ideal_end)
            chunk_index += 1
            result.append(Document(
                text=text[start:end],
                source_path=doc.source_path,
                location=f"{doc.location}_chunk{chunk_index}",
                metadata=dict(doc.metadata),
            ))
            if end >= len(text):
                break
            next_start = end - overlap
            start = next_start if next_start > start else end
    return result
