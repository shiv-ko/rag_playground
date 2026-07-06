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


def _make_data_dir_with_eval(tmp_path: Path) -> tuple[Path, Path]:
    """コーパス1件＋評価用質問CSVディレクトリを持つdata_dirを作る。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.txt").write_text("こんにちは、テスト文書です。", encoding="utf-8")
    qa_dir = data_dir / "質問回答"
    qa_dir.mkdir()
    (qa_dir / "questions_valid.csv").write_text(
        "index,question,answer\n0,テスト質問,テスト正解\n", encoding="utf-8"
    )
    return data_dir, qa_dir


def test_fingerprint_differs_with_exclusion(tmp_path):
    data_dir, qa_dir = _make_data_dir_with_eval(tmp_path)
    assert compute_fingerprint(data_dir) != compute_fingerprint(data_dir, exclude_dirs=[qa_dir])


def test_load_or_parse_excludes_eval_dir(tmp_path):
    data_dir, qa_dir = _make_data_dir_with_eval(tmp_path)
    cache_dir = tmp_path / "cache"
    docs = load_or_parse(data_dir, cache_dir, exclude_dirs=[qa_dir])
    assert docs, "コーパス本体は読み込まれる"
    assert not any("questions_valid" in str(d.source_path) for d in docs)
    assert not any("テスト正解" in d.text for d in docs)


def test_load_or_parse_exclusion_does_not_reuse_unexcluded_cache(tmp_path):
    # 除外なしで作られた（汚染済み）キャッシュが、除外指定時に再利用されないこと
    data_dir, qa_dir = _make_data_dir_with_eval(tmp_path)
    cache_dir = tmp_path / "cache"
    docs_all = load_or_parse(data_dir, cache_dir)
    assert any("questions_valid" in str(d.source_path) for d in docs_all)
    docs_excluded = load_or_parse(data_dir, cache_dir, exclude_dirs=[qa_dir])
    assert not any("questions_valid" in str(d.source_path) for d in docs_excluded)
