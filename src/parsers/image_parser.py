"""画像・グラフパーサー。本番ではVLM（Claude）でキャプション化する。今はスタブ。"""
from pathlib import Path

from src.models import Document

SUPPORTED = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


class ImageParser:
    """
    本番差し替えポイント: parse() の中身をClaude VLM呼び出しに置き換える。
    インターフェースは変えない。
    """

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in SUPPORTED

    def parse(self, file_path: Path) -> list[Document]:
        # スタブ: ファイル名だけを返す。本番はVLMでキャプション生成。
        return [Document(
            text=f"[画像: {file_path.name}] (VLMキャプション未実装)",
            source_path=file_path,
            location="image",
            metadata={"type": "image"},
        )]
