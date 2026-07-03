"""チャンク分割ユーティリティのテスト。"""
from __future__ import annotations

from pathlib import Path

from src.models import Document
from src.parsers.chunker import chunk_documents


def test_short_document_is_not_split(tmp_path: Path) -> None:
    doc = Document(text="短いテキスト", source_path=tmp_path / "a.txt", location="full")
    result = chunk_documents([doc])
    assert len(result) == 1
    assert result[0].text == "短いテキスト"
    assert result[0].location == "full"


def test_long_document_is_split_into_multiple_chunks(tmp_path: Path) -> None:
    long_text = "あ" * 2000
    doc = Document(text=long_text, source_path=tmp_path / "b.txt", location="full")
    result = chunk_documents([doc], chunk_size=800, overlap=100)
    assert len(result) > 1
    assert all(len(c.text) <= 800 for c in result)
    assert result[0].location == "full_chunk1"
    assert result[1].location == "full_chunk2"


def test_chunks_preserve_metadata(tmp_path: Path) -> None:
    long_text = "い" * 2000
    doc = Document(
        text=long_text,
        source_path=tmp_path / "c.txt",
        metadata={"project": "サンプル社"},
    )
    result = chunk_documents([doc], chunk_size=800, overlap=100)
    assert all(c.metadata["project"] == "サンプル社" for c in result)


def test_consecutive_chunks_overlap(tmp_path: Path) -> None:
    long_text = "0123456789" * 200  # 2000文字
    doc = Document(text=long_text, source_path=tmp_path / "d.txt")
    result = chunk_documents([doc], chunk_size=800, overlap=100)
    assert result[1].text[:100] == result[0].text[-100:]


def test_reconstructs_full_directory_via_dispatcher(tmp_path: Path) -> None:
    """dispatcher.parse_directory が長文ファイルをチャンク分割して返す"""
    from src.parsers.dispatcher import ParserDispatcher

    (tmp_path / "long.txt").write_text("う" * 2000, encoding="utf-8")
    dispatcher = ParserDispatcher()
    docs = dispatcher.parse_directory(tmp_path)
    assert len(docs) > 1
    assert all(len(d.text) <= 800 for d in docs)
