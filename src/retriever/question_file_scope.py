"""質問文中に明示されたファイル名の抽出と、ソースパスとの照合。

抽出は「拡張子付きトークン」の一般則のみ（質問文由来の値だけを使う）。
特定のファイル名・案件名はハードコードしない。
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# 空白・和文/欧文の区切り記号で切れる連続文字列＋既知拡張子。
# 「::」はチャンクlocation区切りのため除外対象に含める。
_FILE_BOUNDARY_CHARS = r"\s、。，「」『』（）()：:；;・？！?!*/\\のにでとはをがもや"
_FILE_NAME_RE = re.compile(
    rf"[^{_FILE_BOUNDARY_CHARS}]+"
    r"\.(?:xlsx|xlsm|pptx|docx|pdf|csv|ipynb|txt|md)"
    rf"(?=$|[{_FILE_BOUNDARY_CHARS}])",
    re.IGNORECASE,
)


def extract_file_names(question: str) -> list[str]:
    """質問中の拡張子付きファイル名をNFC正規化して出現順に返す（重複除去）。"""
    normalized = unicodedata.normalize("NFC", question)
    seen: list[str] = []
    for match in _FILE_NAME_RE.finditer(normalized):
        name = match.group(0)
        if name not in seen:
            seen.append(name)
    return seen


def matches_file_name(source: str | Path, file_names: list[str]) -> bool:
    """sourceのbasenameが file_names のいずれかとNFC一致するか。"""
    if not file_names:
        return False
    basename = unicodedata.normalize("NFC", Path(str(source)).name)
    return basename in file_names
