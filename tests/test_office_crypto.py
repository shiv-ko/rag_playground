"""src/utils/office_crypto.py のテスト（TDD）。

社内規定「パスワードは DA-[案件略号]-[開始年月日8桁]-[拡張子コード] の形式」
（データアステル社内規定_パスワード導出規則.docx、レビューで裏取り済み）を実装する
純粋関数 derive_office_password と、msoffcrypto-tool を使った汎用decryptユーティリティ
decrypt_office_file の2つを検証する。

このタスクのスコープでは実データ（data/raw/の実際の暗号化契約書）は存在しない前提のため、
decryptのテストはmsoffcrypto-tool自身のencrypt APIで作った合成フィクスチャを使う。
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import msoffcrypto
import pytest

from src.utils.office_crypto import decrypt_office_file, derive_office_password

PASSWORD = "DA-KAEDE-20250902-docx"
PLAINTEXT_MEMBER = "word/document.xml"
# msoffcrypto-tool 6.0.0のOLEコンテナ書き込み（ECMA376Encrypted._write_Content）は、
# "EncryptedPackage"ストリームの中身が小さい（<=4096バイト）と、本来レギュラーFAT用に
# 割り当てたStartingSectorLocationのままミニFAT領域へ書き込んでしまい、往復（自前で
# encryptしたものを自前でdecrypt）してもバイト列が壊れるという実装上のクセがある
# （調査で確認済み: 暗号化後payloadが4096バイトを僅かに超えると再現しなくなる）。
# これは本モジュール(src/utils/office_crypto.py)側の問題ではなくmsoffcrypto-tool側の
# 挙動なので、テストフィクスチャの平文を十分大きくして避ける。
PLAINTEXT_CONTENT = b"<xml>hello office crypto</xml>" + b"A" * 8000
# msoffcrypto はプレーンOOXMLかどうかを[Content_Types].xmlの中身で判定する
# （format/ooxml.py の _is_ooxml）。実物のdocxである必要はないが、この最小限の
# 中身は必要。
_CONTENT_TYPES_XML = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b"</Types>"
)


def _make_plain_ooxml_bytes() -> bytes:
    """最小限の有効なOOXML風zip（本物のdocxである必要はない。復号はバイト列レベルで形式非依存）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        zf.writestr(PLAINTEXT_MEMBER, PLAINTEXT_CONTENT)
    return buf.getvalue()


def _make_encrypted_fixture(tmp_path: Path, password: str) -> Path:
    plain_bytes = _make_plain_ooxml_bytes()
    plain_buf = io.BytesIO(plain_bytes)
    office_file = msoffcrypto.OfficeFile(plain_buf)
    encrypted_path = tmp_path / "source" / "契約書_pw-kaede20250902.docx"
    encrypted_path.parent.mkdir(parents=True, exist_ok=True)
    with open(encrypted_path, "wb") as f:
        office_file.encrypt(password, f)
    return encrypted_path


# --- derive_office_password ---


def test_derive_office_password_matches_documented_example():
    # docs/plan/2026-07-07-contract-rule-followup-todo.md に記載の例
    assert derive_office_password("AOMINE", "2025-08-06", ".xlsx") == "DA-AOMINE-20250806-xlsx"


def test_derive_office_password_accepts_extension_without_leading_dot():
    assert derive_office_password("KAEDE", "2025-09-02", "docx") == "DA-KAEDE-20250902-docx"


def test_derive_office_password_accepts_already_8digit_date():
    assert derive_office_password("KAEDE", "20250902", "docx") == "DA-KAEDE-20250902-docx"


def test_derive_office_password_lowercases_extension():
    assert derive_office_password("KAEDE", "2025-09-02", ".DOCX") == "DA-KAEDE-20250902-docx"


def test_derive_office_password_is_pure_no_io(tmp_path, monkeypatch):
    # cwdを消しても（I/Oを一切行わない）動くことで純粋関数であることを確認する
    monkeypatch.chdir(tmp_path)
    assert derive_office_password("KAEDE", "2025-09-02", "docx") == "DA-KAEDE-20250902-docx"


# --- decrypt_office_file ---


def test_decrypt_office_file_correct_password_recovers_plaintext_bytes(tmp_path):
    source_path = _make_encrypted_fixture(tmp_path, PASSWORD)
    original_bytes = source_path.read_bytes()
    original_mtime = source_path.stat().st_mtime_ns

    output_path = tmp_path / "decrypted" / "output.docx"
    result_path = decrypt_office_file(source_path, PASSWORD, output_path)

    assert result_path == output_path
    with zipfile.ZipFile(output_path) as zf:
        assert zf.read(PLAINTEXT_MEMBER) == PLAINTEXT_CONTENT

    # 元ファイルは一切変更されていないこと
    assert source_path.read_bytes() == original_bytes
    assert source_path.stat().st_mtime_ns == original_mtime


def test_decrypt_office_file_creates_missing_output_directory(tmp_path):
    source_path = _make_encrypted_fixture(tmp_path, PASSWORD)
    output_path = tmp_path / "does" / "not" / "exist" / "output.docx"
    assert not output_path.parent.exists()

    result_path = decrypt_office_file(source_path, PASSWORD, output_path)

    assert result_path.exists()
    assert output_path.parent.exists()


def test_decrypt_office_file_wrong_password_raises_and_leaves_no_output(tmp_path):
    source_path = _make_encrypted_fixture(tmp_path, PASSWORD)
    output_path = tmp_path / "decrypted" / "output.docx"

    with pytest.raises(msoffcrypto.exceptions.InvalidKeyError):
        decrypt_office_file(source_path, "WRONG-PASSWORD", output_path)

    assert not output_path.exists()


def test_decrypt_office_file_does_not_write_to_source_directory(tmp_path):
    source_path = _make_encrypted_fixture(tmp_path, PASSWORD)
    source_dir_entries_before = sorted(p.name for p in source_path.parent.iterdir())

    output_path = tmp_path / "elsewhere" / "output.docx"
    decrypt_office_file(source_path, PASSWORD, output_path)

    source_dir_entries_after = sorted(p.name for p in source_path.parent.iterdir())
    assert source_dir_entries_after == source_dir_entries_before
