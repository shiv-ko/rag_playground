"""parse_cache のテスト。実パーサーは呼ばず、txtファイルで検証する。"""
from pathlib import Path

from src.utils.parse_cache import compute_fingerprint, load_or_parse


def _make_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.txt").write_text("こんにちは、テスト文書です。", encoding="utf-8")
    return data_dir


def test_fingerprint_stable(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    assert compute_fingerprint(data_dir) == compute_fingerprint(data_dir)


def test_fingerprint_changes_on_file_change(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    fp1 = compute_fingerprint(data_dir)
    (data_dir / "b.txt").write_text("新しいファイル", encoding="utf-8")
    assert compute_fingerprint(data_dir) != fp1


def test_load_or_parse_caches(tmp_path, monkeypatch):
    data_dir = _make_data_dir(tmp_path)
    cache_dir = tmp_path / "cache"

    docs1 = load_or_parse(data_dir, cache_dir)
    assert len(docs1) >= 1

    # 2回目はパーサーを呼ばずにキャッシュから返す
    import src.utils.parse_cache as pc

    def _boom(self, directory):
        raise AssertionError("キャッシュがあるのに再パースした")

    monkeypatch.setattr(pc.ParserDispatcher, "parse_directory", _boom)
    docs2 = load_or_parse(data_dir, cache_dir)
    assert [d.text for d in docs2] == [d.text for d in docs1]
    assert [str(d.source_path) for d in docs2] == [str(d.source_path) for d in docs1]


def test_load_or_parse_reparses_on_change(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    cache_dir = tmp_path / "cache"
    load_or_parse(data_dir, cache_dir)

    (data_dir / "b.txt").write_text("追加ファイル", encoding="utf-8")
    docs = load_or_parse(data_dir, cache_dir)
    assert any("追加ファイル" in d.text for d in docs)
