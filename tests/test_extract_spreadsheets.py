"""scripts/extract_spreadsheets.py の暗号化xlsx復号フォールバックのテスト（TDD）。

かえで総合病院のスケジュール.xlsxが`encrypted_or_legacy_office_container`のまま
未解決だった問題に対応する。build_contract_registry.pyの契約書復号と同じ2系統の
パスワード候補（(1) ファイル名の`pw-<トークン>`リテラル (2) DA-規則＋日付候補）を、
xlsx向けに配線する。
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import msoffcrypto
import openpyxl
import pytest

import scripts.extract_spreadsheets as mod
from scripts.extract_spreadsheets import (
    attempt_decrypt_workbook,
    candidate_start_dates_from_contracts,
)
from src.utils.office_crypto import derive_office_password

# msoffcrypto-tool 6.0.0のOLEコンテナ書き込みは、暗号化payloadが小さい(<=4096バイト)と
# mini-FAT/regular-FATの不整合で壊れることがある（tests/test_office_crypto.pyで裏取り済み）。
# ここでも十分な行数を足して4KB超のペイロードにしてから暗号化する。
def _build_real_xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "スケジュール"
    ws.append(["タスクID", "担当者", "開始日"])
    for i in range(300):
        ws.append([f"T{i:03d}", "テスト担当者", f"padding padding padding padding {i}"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_encrypted_xlsx(dest: Path, password: str) -> None:
    plain_buf = io.BytesIO(_build_real_xlsx_bytes())
    office_file = msoffcrypto.OfficeFile(plain_buf)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        office_file.encrypt(password, f)


def _write_contracts(path: Path, project_name: str, start_date: str) -> None:
    path.write_text(
        json.dumps({"project_name": project_name, "start_date": start_date}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# --- candidate_start_dates_from_contracts ---


def test_candidate_start_dates_from_contracts_reads_matching_project(tmp_path: Path) -> None:
    contracts_path = tmp_path / "contracts.jsonl"
    _write_contracts(contracts_path, "テスト案件", "2025-09-02")
    assert candidate_start_dates_from_contracts("テスト案件", contracts_path) == ["20250902"]


def test_candidate_start_dates_from_contracts_empty_when_no_match(tmp_path: Path) -> None:
    contracts_path = tmp_path / "contracts.jsonl"
    _write_contracts(contracts_path, "他の案件", "2025-09-02")
    assert candidate_start_dates_from_contracts("テスト案件", contracts_path) == []


def test_candidate_start_dates_from_contracts_empty_when_file_missing(tmp_path: Path) -> None:
    assert candidate_start_dates_from_contracts("テスト案件", tmp_path / "no_contracts.jsonl") == []


# --- attempt_decrypt_workbook ---


def test_attempt_decrypt_workbook_succeeds_via_da_rule_and_contract_date(tmp_path: Path) -> None:
    alias = "KAEDE"
    password = derive_office_password(alias, "2025-09-02", ".xlsx")
    source = tmp_path / "source" / "スケジュール.xlsx"
    _write_encrypted_xlsx(source, password)

    contracts_path = tmp_path / "contracts.jsonl"
    _write_contracts(contracts_path, "テスト案件", "2025-09-02")

    output_path = tmp_path / "decrypted.xlsx"
    ok = attempt_decrypt_workbook(
        source,
        "テスト案件",
        {"テスト案件": alias},
        output_path,
        contracts_path=contracts_path,
    )
    assert ok is True
    wb = openpyxl.load_workbook(output_path)
    assert wb.active["A1"].value == "タスクID"


def test_attempt_decrypt_workbook_succeeds_via_literal_filename_password(tmp_path: Path) -> None:
    source = tmp_path / "source" / "スケジュール_pw-testtoken123.xlsx"
    _write_encrypted_xlsx(source, "testtoken123")

    output_path = tmp_path / "decrypted.xlsx"
    ok = attempt_decrypt_workbook(
        source,
        "無関係案件",
        {},
        output_path,
        contracts_path=tmp_path / "no_contracts.jsonl",
    )
    assert ok is True


def test_attempt_decrypt_workbook_fails_when_no_candidate_matches(tmp_path: Path) -> None:
    source = tmp_path / "source" / "スケジュール.xlsx"
    _write_encrypted_xlsx(source, derive_office_password("REAL", "2025-01-01", ".xlsx"))

    output_path = tmp_path / "decrypted.xlsx"
    ok = attempt_decrypt_workbook(
        source,
        "テスト案件",
        {"テスト案件": "WRONG"},
        output_path,
        contracts_path=tmp_path / "no_contracts.jsonl",
    )
    assert ok is False
    assert not output_path.exists()


# --- extract_workbook integration (decrypt-then-parse) ---


def test_extract_workbook_recovers_encrypted_xlsx_via_decrypt_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "プロジェクト"
    plan_dir = project_root / "テスト案件" / "02.計画"
    plan_dir.mkdir(parents=True)
    alias = "KAEDE"
    password = derive_office_password(alias, "2025-09-02", ".xlsx")
    xlsx_path = plan_dir / "スケジュール.xlsx"
    _write_encrypted_xlsx(xlsx_path, password)

    contracts_path = tmp_path / "contracts.jsonl"
    _write_contracts(contracts_path, "テスト案件", "2025-09-02")

    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "PROJECT_ROOT", project_root)

    sheets, cells, highlights, schedule_rows = mod.extract_workbook(
        xlsx_path, {"テスト案件": alias}, contracts_path=contracts_path
    )
    assert sheets[0]["project_name"] == "テスト案件"
    assert cells
    assert schedule_rows  # タスクID/担当者ヘッダーが検出され、行が抽出される


def test_extract_workbook_reraises_when_not_encrypted_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 暗号化(CDFV2)ではない単なる破損ファイルは、復号フォールバックを試みずに
    # 従来どおり例外を送出する（main()側のfailures収集ロジックに変更がないことの確認）。
    project_root = tmp_path / "プロジェクト"
    plan_dir = project_root / "テスト案件" / "02.計画"
    plan_dir.mkdir(parents=True)
    bad_path = plan_dir / "スケジュール.xlsx"
    bad_path.write_bytes(b"not a real xlsx at all, just garbage bytes")

    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "PROJECT_ROOT", project_root)

    with pytest.raises(Exception):
        mod.extract_workbook(bad_path, {}, contracts_path=tmp_path / "no_contracts.jsonl")


def test_extract_workbook_reraises_when_all_password_candidates_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "プロジェクト"
    plan_dir = project_root / "テスト案件" / "02.計画"
    plan_dir.mkdir(parents=True)
    xlsx_path = plan_dir / "スケジュール.xlsx"
    _write_encrypted_xlsx(xlsx_path, derive_office_password("REAL", "2025-01-01", ".xlsx"))

    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "PROJECT_ROOT", project_root)

    with pytest.raises(Exception):
        mod.extract_workbook(
            xlsx_path,
            {"テスト案件": "WRONG"},
            contracts_path=tmp_path / "no_contracts.jsonl",
        )
