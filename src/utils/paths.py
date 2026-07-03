"""リポジトリルート基準のパス正規化。document_registry.jsonl のsource_path（repo相対）との突合に使う。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def to_repo_relative(path: Path) -> str:
    # symlink解決はしない（.resolve()ではなく.absolute()）。
    # 開発環境ではdata/raw等がsymlinkで外部を指すことがあり、
    # symlink解決するとROOT外に出てreconciliationが壊れるため。
    try:
        return str(Path(path).absolute().relative_to(ROOT))
    except ValueError:
        return str(path)
