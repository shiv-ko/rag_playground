"""parse_cache のテスト。実パーサーは呼ばず、txtファイルで検証する。"""
import os
import time
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


def _make_code_dir(tmp_path: Path, name: str = "fake_parsers") -> Path:
    code_dir = tmp_path / name
    code_dir.mkdir()
    (code_dir / "text_parser.py").write_text(
        "def parse():\n    return 1\n", encoding="utf-8"
    )
    sub = code_dir / "sub"
    sub.mkdir()
    (sub / "chunker.py").write_text(
        "def chunk():\n    return []\n", encoding="utf-8"
    )
    return code_dir


def test_fingerprint_changes_when_parser_code_changes(tmp_path):
    """パーサー/チャンカーのコード内容が変わるとfingerprintが変わる。"""
    data_dir = _make_data_dir(tmp_path)
    code_dir = _make_code_dir(tmp_path)
    fp1 = compute_fingerprint(data_dir, code_dirs=[code_dir])

    (code_dir / "text_parser.py").write_text(
        "def parse():\n    return 2  # 内容変更\n", encoding="utf-8"
    )
    fp2 = compute_fingerprint(data_dir, code_dirs=[code_dir])
    assert fp1 != fp2


def test_fingerprint_changes_when_nested_code_changes(tmp_path):
    """サブディレクトリ（chunker相当）の内容変更も検知する。"""
    data_dir = _make_data_dir(tmp_path)
    code_dir = _make_code_dir(tmp_path)
    fp1 = compute_fingerprint(data_dir, code_dirs=[code_dir])

    (code_dir / "sub" / "chunker.py").write_text(
        "def chunk():\n    return [1]  # 内容変更\n", encoding="utf-8"
    )
    fp2 = compute_fingerprint(data_dir, code_dirs=[code_dir])
    assert fp1 != fp2


def test_fingerprint_stable_when_data_and_code_unchanged(tmp_path):
    """データもコードも不変ならfingerprintは安定。"""
    data_dir = _make_data_dir(tmp_path)
    code_dir = _make_code_dir(tmp_path)
    assert compute_fingerprint(data_dir, code_dirs=[code_dir]) == compute_fingerprint(
        data_dir, code_dirs=[code_dir]
    )


def test_fingerprint_stable_when_only_mtime_changes(tmp_path):
    """mtimeだけ変わって内容が不変なら同一fingerprint（内容ハッシュで判定するため）。"""
    data_dir = _make_data_dir(tmp_path)
    code_dir = _make_code_dir(tmp_path)
    fp1 = compute_fingerprint(data_dir, code_dirs=[code_dir])

    target = code_dir / "text_parser.py"
    # 内容は変えずmtimeだけ未来にずらす（gitチェックアウトでの再書き込みを模擬）
    future = time.time() + 1000
    os.utime(target, (future, future))
    fp2 = compute_fingerprint(data_dir, code_dirs=[code_dir])
    assert fp1 == fp2


def test_fingerprint_uses_real_parsers_dir_by_default():
    """code_dirs省略時はsrc/parsers/配下が使われ、実行のたびに安定する。"""
    tmp = Path(__file__).resolve().parent
    data_dir = tmp / "fixtures" if (tmp / "fixtures").exists() else tmp
    fp1 = compute_fingerprint(data_dir)
    fp2 = compute_fingerprint(data_dir)
    assert fp1 == fp2


# --- code_files: office_crypto.py・artifacts(project_registry.json/contracts.jsonl)への追随 ---
#
# office_parser.pyの暗号化ファイル対応はsrc/utils/office_crypto.py（src/parsers/配下ではない
# ためcode_dirsの走査対象外）とartifacts/project_registry.json・artifacts/contracts.jsonl
# （機械生成レジストリ、パース結果に影響しうる）に依存するようになったが、これらは
# 従来のfingerprintに一切反映されていなかった（office_crypto.py側だけ直してもキャッシュが
# 古いパース結果を返し続ける罠）。code_dirsと並ぶ第2の入力としてcode_filesを追加する。


def test_fingerprint_changes_when_code_file_content_changes(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    extra_file = tmp_path / "office_crypto.py"
    extra_file.write_text("PASSWORD_RULE = 'DA'\n", encoding="utf-8")
    fp1 = compute_fingerprint(data_dir, code_files=[extra_file])

    extra_file.write_text("PASSWORD_RULE = 'DA2'  # 内容変更\n", encoding="utf-8")
    fp2 = compute_fingerprint(data_dir, code_files=[extra_file])
    assert fp1 != fp2


def test_fingerprint_changes_when_artifact_file_content_changes(tmp_path):
    """artifacts側(project_registry.json相当)の変更もfingerprintに反映される。"""
    data_dir = _make_data_dir(tmp_path)
    artifact = tmp_path / "project_registry.json"
    artifact.write_text("[]", encoding="utf-8")
    fp1 = compute_fingerprint(data_dir, code_files=[artifact])

    artifact.write_text('[{"project_name": "x", "primary_alias": "X"}]', encoding="utf-8")
    fp2 = compute_fingerprint(data_dir, code_files=[artifact])
    assert fp1 != fp2


def test_fingerprint_stable_when_code_file_missing(tmp_path):
    """指定した追加ファイルが存在しなくても例外を出さず安定したfingerprintになる
    （contracts.jsonl未生成時点でも壊れないこと）。"""
    data_dir = _make_data_dir(tmp_path)
    missing = tmp_path / "does_not_exist.jsonl"
    fp1 = compute_fingerprint(data_dir, code_files=[missing])
    fp2 = compute_fingerprint(data_dir, code_files=[missing])
    assert fp1 == fp2


def test_fingerprint_unaffected_by_code_files_when_omitted_matches_explicit_empty(tmp_path):
    """code_files=[]（追加ファイルなし）はcode_dirsのみのfingerprintと独立して安定する。"""
    data_dir = _make_data_dir(tmp_path)
    assert compute_fingerprint(data_dir, code_files=[]) == compute_fingerprint(
        data_dir, code_files=[]
    )


def test_default_code_files_includes_office_crypto_and_artifacts():
    """code_files省略時のデフォルトが、office_parser.pyが実際に依存する
    src/utils/office_crypto.py・artifacts/project_registry.json・artifacts/contracts.jsonl
    を含んでいること（配線の確認）。"""
    from src.utils.parse_cache import _default_code_files

    files = _default_code_files()
    name_pairs = {(p.parent.name, p.name) for p in files}
    assert ("utils", "office_crypto.py") in name_pairs
    assert ("artifacts", "project_registry.json") in name_pairs
    assert ("artifacts", "contracts.jsonl") in name_pairs


def test_fingerprint_uses_default_code_files_when_omitted(tmp_path, monkeypatch):
    """code_files省略時は_default_code_files()の中身がfingerprintに反映される
    （実ファイルを汚さず、差し替えたデフォルトの内容変更で検証する）。"""
    import src.utils.parse_cache as pc

    working_copy = tmp_path / "office_crypto.py"
    working_copy.write_text("PASSWORD_RULE = 'DA'\n", encoding="utf-8")
    monkeypatch.setattr(pc, "_default_code_files", lambda: [working_copy])

    data_dir = _make_data_dir(tmp_path)
    fp1 = compute_fingerprint(data_dir)

    working_copy.write_text("PASSWORD_RULE = 'DA2'  # 内容変更\n", encoding="utf-8")
    fp2 = compute_fingerprint(data_dir)
    assert fp1 != fp2
