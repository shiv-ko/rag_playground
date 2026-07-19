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


def _default_code_files() -> list[Path]:
    """_default_code_dirs()（src/parsers/配下のディレクトリ走査）だけでは拾えない、
    パース結果に影響する個別ファイル群。

    office_parser.pyの暗号化ファイル対応(_decrypt_via_password_candidates)は
    src/utils/office_crypto.py（src/parsers/配下ではないためディレクトリ走査の対象外）と、
    artifacts/project_registry.json・artifacts/contracts.jsonl（パスワード導出に使う
    機械生成レジストリ。中身が変わると同じ暗号化ファイルでも復号成否＝パース結果が
    変わりうる）に依存する。これらをfingerprintに含めないと、office_crypto.pyや
    artifactsだけを直しても古いキャッシュがヒットし続けて修正が無効化される
    （src/parsers/配下のコード変更にしか追随しなかった既存の罠と同型）。
    """
    root = Path(__file__).resolve().parent.parent.parent
    return [
        root / "src" / "utils" / "office_crypto.py",
        root / "artifacts" / "project_registry.json",
        root / "artifacts" / "contracts.jsonl",
    ]


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


def _hash_code_files(code_files: list[Path]) -> str:
    """個別ファイル群の内容ハッシュを集約する。存在しないファイル（例: run_pipeline未実行で
    contracts.jsonlがまだ無い）は空バイト列として扱い、欠落そのものではキーが不安定に
    ならないようにする（生成された瞬間にはじめて内容が反映され、以後の変更も追随する）。"""
    entries = []
    for p in code_files:
        content = p.read_bytes() if p.is_file() else b""
        content_hash = hashlib.sha256(content).hexdigest()
        entries.append(f"{normalized_resolved_posix(p)}|{content_hash}")
    return hashlib.sha256("\n".join(sorted(entries)).encode("utf-8")).hexdigest()


def compute_fingerprint(
    data_dir: Path,
    exclude_dirs: list[Path] | None = None,
    code_dirs: list[Path] | None = None,
    code_files: list[Path] | None = None,
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
    # src/parsers/配下のディレクトリ走査だけでは拾えない個別ファイル（office_crypto.py・
    # artifacts/project_registry.json・contracts.jsonl等）もキーに混ぜる。
    entries.append("files:" + _hash_code_files(code_files if code_files is not None else _default_code_files()))
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
