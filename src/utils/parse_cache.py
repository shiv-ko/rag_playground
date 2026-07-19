"""パース＋チャンク結果のディスクキャッシュ。

data_dir 配下のファイル構成（相対パス・mtime・サイズ）が変わらない限り、
ParserDispatcher.parse_directory() を再実行せず pickle から復元する。
exclude_dirs（評価用質問CSVディレクトリ等）はパース対象外で、フィンガー
プリントにも含めない＋除外設定自体をキーに混ぜる — 除外あり/なしの
キャッシュが同じキーに衝突して汚染コーパスが再利用されるのを防ぐ。
"""
from __future__ import annotations

import hashlib
import pickle
import unicodedata
from pathlib import Path

from src.models import Document
from src.parsers.dispatcher import (
    ParserDispatcher,
    is_under_excluded,
    normalized_resolved_posix,
)


def _default_code_dirs() -> list[Path]:
    """パース結果に影響するコードが置かれているディレクトリ群。
    新しいパーサー/チャンカーを追加してもハードコード列挙を増やさずに
    自動で対象になるよう、ファイル名ではなくディレクトリ単位で指定する。"""
    return [Path(__file__).resolve().parent.parent / "parsers"]


def _hash_code_dirs(code_dirs: list[Path]) -> str:
    """コードディレクトリ配下の全.pyファイルの内容ハッシュを集約する。
    mtimeではなくファイル内容のハッシュを使うため、gitチェックアウト等で
    mtimeだけ変わっても内容が同じならキャッシュキーは変化しない。"""
    entries = []
    for code_dir in code_dirs:
        if not code_dir.is_dir():
            continue
        code_dir_norm = normalized_resolved_posix(code_dir)
        for p in sorted(code_dir.rglob("*.py")):
            if not p.is_file():
                continue
            content_hash = hashlib.sha256(p.read_bytes()).hexdigest()
            rel = normalized_resolved_posix(p)[len(code_dir_norm):].lstrip("/")
            entries.append(f"{code_dir.name}/{rel}|{content_hash}")
    return hashlib.sha256("\n".join(sorted(entries)).encode("utf-8")).hexdigest()


def compute_fingerprint(
    data_dir: Path,
    exclude_dirs: list[Path] | None = None,
    code_dirs: list[Path] | None = None,
) -> str:
    excluded = [normalized_resolved_posix(d) for d in (exclude_dirs or [])]
    entries = []
    for p in sorted(data_dir.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        if is_under_excluded(p, excluded):
            continue
        stat = p.stat()
        entries.append(f"{p.relative_to(data_dir)}|{stat.st_mtime_ns}|{stat.st_size}")
    # 除外設定をキーに含める（data_dirからの相対パスで、マシン非依存に）
    data_dir_norm = normalized_resolved_posix(data_dir)
    exclude_marks = []
    for d in excluded:
        if d == data_dir_norm or d.startswith(data_dir_norm + "/"):
            exclude_marks.append(d[len(data_dir_norm):].lstrip("/"))
        else:
            exclude_marks.append(unicodedata.normalize("NFC", Path(d).name))
    entries.append("exclude:" + "|".join(sorted(exclude_marks)))
    # パーサー/チャンカーのコード内容をキーに混ぜる。コードを直しても古い
    # キャッシュがヒットし続けて修正が無効化される罠を防ぐため。
    entries.append("code:" + _hash_code_dirs(code_dirs if code_dirs is not None else _default_code_dirs()))
    digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return digest[:16]


def load_or_parse(
    data_dir: Path, cache_dir: Path, exclude_dirs: list[Path] | None = None
) -> list[Document]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"parsed_{compute_fingerprint(data_dir, exclude_dirs)}.pkl"
    if cache_path.exists():
        return pickle.loads(cache_path.read_bytes())
    docs = ParserDispatcher().parse_directory(data_dir, exclude_dirs=exclude_dirs)
    cache_path.write_bytes(pickle.dumps(docs))
    return docs
