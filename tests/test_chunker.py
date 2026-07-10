"""チャンク分割ユーティリティのテスト (TDD)。

Q28（valid, code_static）が検索失敗→Incorrectになった根本原因の1つは、
固定長・文字数ベースの分割が行単位の境界を無視していたこと
（実データではさらに.pyファイル自体が未対応だった問題もあり、そちらは
tests/test_parsers.py 側で別途対応する）。ここでは「分割が必要なときは
行の途中で切らない」ことを保証する回帰テストを書く。
"""
from __future__ import annotations

from pathlib import Path

from src.models import Document
from src.parsers.chunker import chunk_documents


def _doc(text: str, path: Path) -> Document:
    return Document(text=text, source_path=path, location="full")


class TestChunkDocumentsPreservesShortDocuments:
    def test_document_under_chunk_size_is_returned_unchanged(self, tmp_path: Path) -> None:
        doc = _doc("短いテキスト", tmp_path / "a.txt")
        result = chunk_documents([doc], chunk_size=800, overlap=100)
        assert result == [doc]


class TestChunkDocumentsAvoidsMidLineSplits:
    def test_does_not_split_a_line_across_two_chunks(self, tmp_path: Path) -> None:
        """行の途中でチャンクが切れると、条件式のようなワンライナーが
        泣き別れて部分コードから誤断定するリスクがある（Q28型の事故）。"""
        condition_line = (
            "if df['CAT'].dtype == 'object' and df['CAT'].nunique() < 10: "
            "category_columns.append('CAT')"
        )
        # chunk_sizeの境界付近にちょうど条件式が来るよう、前後を改行区切りの行で埋める
        filler_line = "x = 1  # padding line to push the condition near the boundary"
        lines = [filler_line] * 20 + [condition_line] + [filler_line] * 20
        text = "\n".join(lines)

        result = chunk_documents([_doc(text, tmp_path / "modeling.py")], chunk_size=400, overlap=50)

        assert len(result) > 1  # 分割は発生している前提のテスト
        assert any(condition_line in chunk.text for chunk in result)

    def test_chunk_boundaries_align_with_newlines_when_possible(self, tmp_path: Path) -> None:
        lines = [f"line_{i:03d} content here" for i in range(60)]
        text = "\n".join(lines)

        result = chunk_documents([_doc(text, tmp_path / "b.py")], chunk_size=300, overlap=30)

        assert len(result) > 1
        for chunk in result[:-1]:
            # 最後のチャンク以外は改行の直後で終わっている（行の途中で切れていない）
            assert chunk.text.endswith("\n")

    def test_falls_back_to_hard_cut_when_no_newline_exists(self, tmp_path: Path) -> None:
        """改行が一切ない巨大な1行のテキストは、行境界を待たずに従来通り強制分割する
        （無限ループ・チャンク生成停止を防ぐフォールバック）。"""
        text = "a" * 2000
        result = chunk_documents([_doc(text, tmp_path / "c.txt")], chunk_size=400, overlap=50)

        assert len(result) > 1
        assert result[0].text == text[:400]

    def test_all_chunks_together_cover_the_original_text_without_gaps(self, tmp_path: Path) -> None:
        lines = [f"stmt_{i}" for i in range(50)]
        text = "\n".join(lines)
        result = chunk_documents([_doc(text, tmp_path / "d.py")], chunk_size=120, overlap=20)

        # 元テキストの各行がどこかのチャンクに含まれている（内容の欠落が無い）
        for line in lines:
            assert any(line in chunk.text for chunk in result)
