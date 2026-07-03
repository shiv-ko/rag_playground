"""パース＋チャンク結果のディスクキャッシュ。

data_dir 配下のファイル構成（相対パス・mtime・サイズ）が変わらない限り、
ParserDispatcher.parse_directory() を再実行せず pickle から復元する。
"""
from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

from src.models import Document
from src.parsers.dispatcher import ParserDispatcher


def compute_fingerprint(data_dir: Path) -> str:
    entries = []
    for p in sorted(data_dir.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        stat = p.stat()
        entries.append(f"{p.relative_to(data_dir)}|{stat.st_mtime_ns}|{stat.st_size}")
    digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return digest[:16]


def load_or_parse(data_dir: Path, cache_dir: Path) -> list[Document]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"parsed_{compute_fingerprint(data_dir)}.pkl"
    if cache_path.exists():
        return pickle.loads(cache_path.read_bytes())
    docs = ParserDispatcher().parse_directory(data_dir)
    cache_path.write_bytes(pickle.dumps(docs))
    return docs
