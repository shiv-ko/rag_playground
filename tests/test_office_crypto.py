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
import json
import unicodedata
import zipfile
from pathlib import Path

import msoffcrypto
import pytest

from src.utils.office_crypto import (
    candidate_start_dates_from_contracts,
    decrypt_office_file,
    derive_office_password,
    load_primary_aliases,
    normalize_project_text,
    password_candidates_for_file,
    project_name_from_path,
)

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


# --- normalize_project_text ---


def test_normalize_project_text_replaces_fullwidth_space():
    assert normalize_project_text("かえで　総合病院") == "かえで 総合病院"


def test_normalize_project_text_normalizes_nfd_to_nfc():
    nfd = unicodedata.normalize("NFD", "かえで総合病院")
    assert normalize_project_text(nfd) == unicodedata.normalize("NFC", "かえで総合病院")


# --- load_primary_aliases ---


def test_load_primary_aliases_maps_normalized_project_name_to_alias(tmp_path):
    registry_path = tmp_path / "project_registry.json"
    registry_path.write_text(
        json.dumps(
            [{"project_name": "かえで　総合病院", "primary_alias": "KAEDE"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    aliases = load_primary_aliases(registry_path)
    assert aliases == {"かえで 総合病院": "KAEDE"}


def test_load_primary_aliases_skips_rows_without_primary_alias(tmp_path):
    registry_path = tmp_path / "project_registry.json"
    registry_path.write_text(
        json.dumps([{"project_name": "案件A"}], ensure_ascii=False), encoding="utf-8"
    )
    assert load_primary_aliases(registry_path) == {}


def test_load_primary_aliases_empty_when_file_missing(tmp_path):
    assert load_primary_aliases(tmp_path / "no_registry.json") == {}


# --- candidate_start_dates_from_contracts ---


def test_candidate_start_dates_from_contracts_reads_matching_project(tmp_path):
    contracts_path = tmp_path / "contracts.jsonl"
    contracts_path.write_text(
        json.dumps({"project_name": "テスト案件", "start_date": "2025-09-02"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    assert candidate_start_dates_from_contracts("テスト案件", contracts_path) == ["20250902"]


def test_candidate_start_dates_from_contracts_empty_when_no_match(tmp_path):
    contracts_path = tmp_path / "contracts.jsonl"
    contracts_path.write_text(
        json.dumps({"project_name": "他の案件", "start_date": "2025-09-02"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    assert candidate_start_dates_from_contracts("テスト案件", contracts_path) == []


def test_candidate_start_dates_from_contracts_empty_when_file_missing(tmp_path):
    assert candidate_start_dates_from_contracts("テスト案件", tmp_path / "missing.jsonl") == []


# --- project_name_from_path ---


def test_project_name_from_path_extracts_segment_after_marker():
    path = Path("/root/data/raw/share/共有ドライブ/プロジェクト/かえで総合病院/02.計画/スケジュール.xlsx")
    assert project_name_from_path(path) == "かえで総合病院"


def test_project_name_from_path_none_when_marker_absent():
    path = Path("/root/data/raw/share/共有ドライブ/社内管理/座席表.pptx")
    assert project_name_from_path(path) is None


def test_project_name_from_path_matches_nfd_marker_segment():
    # macOS/zip展開由来のNFD分解パスでも"プロジェクト"マーカーを検知できること
    nfd_marker = unicodedata.normalize("NFD", "プロジェクト")
    nfd_project = unicodedata.normalize("NFD", "かえで総合病院")
    path = Path(f"/root/{nfd_marker}/{nfd_project}/02.計画/スケジュール.xlsx")
    assert project_name_from_path(path) == "かえで総合病院"


# --- password_candidates_for_file ---


def test_password_candidates_for_file_prefers_literal_filename_token(tmp_path):
    path = tmp_path / "契約書_pw-testtoken123.docx"
    candidates = password_candidates_for_file(path, "無関係案件", {}, tmp_path / "no_contracts.jsonl")
    assert candidates[0] == "testtoken123"


def test_password_candidates_for_file_derives_da_rule_from_filename_date(tmp_path):
    path = tmp_path / "契約書_pw-kaede20250902.docx"
    candidates = password_candidates_for_file(
        path, "かえで総合病院", {"かえで総合病院": "KAEDE"}, tmp_path / "no_contracts.jsonl"
    )
    assert "DA-KAEDE-20250902-docx" in candidates


def test_password_candidates_for_file_falls_back_to_contracts_date_without_filename_marker(tmp_path):
    # KAEDEの実データ相当: ファイル名に`pw-`マーカーが一切無いケース
    path = tmp_path / "スケジュール.xlsx"
    contracts_path = tmp_path / "contracts.jsonl"
    contracts_path.write_text(
        json.dumps(
            {"project_name": "かえで総合病院", "start_date": "2025-09-02"}, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    candidates = password_candidates_for_file(
        path, "かえで総合病院", {"かえで総合病院": "KAEDE"}, contracts_path
    )
    assert candidates == ["DA-KAEDE-20250902-xlsx"]


def test_password_candidates_for_file_empty_when_no_marker_and_no_alias(tmp_path):
    path = tmp_path / "スケジュール.xlsx"
    candidates = password_candidates_for_file(path, "不明案件", {}, tmp_path / "no_contracts.jsonl")
    assert candidates == []
