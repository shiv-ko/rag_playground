"""contracts.jsonl extraction tests."""
from __future__ import annotations

import io
import json
from pathlib import Path

import msoffcrypto
import pytest
from docx import Document as DocxDocument

from scripts.build_contract_registry import (
    build_contract_registry,
    classify_rounding_rule,
    parse_contract_text,
    read_docx_text_with_decryption,
)
from src.utils.office_crypto import derive_office_password


def test_parse_time_and_materials_contract_values() -> None:
    text = """
5. 契約期間
本契約の契約期間は、2025-07-08から2025-08-11までの5週間とする。
6. 報酬および支払条件
本契約の料金モデルは、time_and_materialsとし、実績工数に基づく事後精算（月次精算）とする。
時間単価は25,000円（消費税別）とする。
想定総工数は170時間とする。
見込金額は、税抜4,250,000円、消費税425,000円、税込4,675,000円とする。
作業時間の計上単位は30分とし、30分未満の端数は30分単位に切り上げて計上する。
7. 知的財産
"""
    row = parse_contract_text("テスト社", "契約書.docx", text)
    assert row["contract_type"] == "time_and_materials"
    assert row["rate_yen_per_hour"] == 25000
    assert row["esth_hours"] == 170
    assert row["estimated_amount_incl_tax"] == 4675000
    assert row["rounding_rule"] == "ceiling_to_unit"
    assert row["contract_period_days"] == 35


def test_parse_fixed_contract_values() -> None:
    text = """
5. 契約期間
本契約の契約期間は、2025-10-01から2025-11-11までの6週間とする。
6. 報酬および支払条件
本契約の契約形態は固定価格契約とし、契約金額（税抜）：5,250,000円、
消費税額：525,000円、契約金額（税込）：5,775,000円とする。
支払計画: 着手金50%（期日: 2025-10-08）＋ 検収金50%。
"""
    row = parse_contract_text("固定社", "契約書.docx", text)
    assert row["contract_type"] == "fixed"
    assert row["estimated_amount_incl_tax"] == 5775000
    assert row["advance_payment_amount"] == 2887500


def test_parse_contract_period_with_spaces_around_kara_made() -> None:
    # 実データの一部契約書は「日?から」「日?まで」の前後にスペースが入る表記を使う
    # （例: 白峰の契約書相当の合成データ）。regexがスペースを許容しないと
    # start_date/end_date/contract_period_daysが全てnullになる回帰を防ぐ。
    text = """
5. 契約期間
本契約の契約期間は、2025-05-13 から 2025-07-22 までとする。
6. 報酬および支払条件
本契約の料金モデルは、time_and_materialsとし、実績工数に基づく事後精算（月次精算）とする。
"""
    row = parse_contract_text("架空商事", "契約書.docx", text)
    assert row["start_date"] == "2025-05-13"
    assert row["end_date"] == "2025-07-22"
    assert row["contract_period_days"] == 71


def test_parse_contract_period_kiten_with_spaces() -> None:
    # 起算型表記でもスペース入りで日付が正しく返ること
    text = """
5. 契約期間
本契約の契約期間は、2025-05-13 から起算して4週間とする。
6. 報酬および支払条件
本契約の料金モデルは、time_and_materialsとし、実績工数に基づく事後精算（月次精算）とする。
"""
    row = parse_contract_text("架空物産", "契約書.docx", text)
    assert row["start_date"] == "2025-05-13"
    assert row["end_date"] == "2025-06-09"
    assert row["contract_period_days"] == 28


def test_classify_half_unit_bucket_rounding() -> None:
    clause = "工数計上の丸め単位は30分とし、30分未満を0.5時間、30分超60分未満を1.0時間として0.5時間単位で計上する。"
    assert classify_rounding_rule(clause) == "half_unit_bucket"


def test_parse_advance_payment_from_docx_table_row_with_percent_column() -> None:
    # 実データの表形式（京橋信用ソリューションズと同じ列順）:
    # 支払回 | 名目 | 比率 | 金額（税抜） | 消費税額 | 金額（税込） | 支払条件 | 支払期日
    text = """
6. 報酬および支払条件
6.1 契約金額
本契約の契約形態は固定価格契約とし、契約金額（税抜）：5,250,000円、
消費税額：525,000円、契約金額（税込）：5,775,000円とする。
6.2 支払条件
支払回 | 名目 | 比率 | 金額（税抜） | 消費税額 | 金額（税込） | 支払条件 | 支払期日
第1回 | 着手金 | 50% | 2,625,000円 | 262,500円 | 2,887,500円 | 契約締結後5営業日以内 | 2025-10-08
第2回 | 検収金 | 50% | 2,625,000円 | 262,500円 | 2,887,500円 | 検収完了後5営業日以内 | 2025-11-19
"""
    row = parse_contract_text("京橋風", "契約書.docx", text)
    assert row["advance_payment_amount"] == 2_887_500


def test_parse_advance_payment_from_docx_table_row_with_different_column_order() -> None:
    # 実データの表形式（青葉与信マネジメントと同じ列順、支払条件が税抜より前に来る）:
    # 支払回 | 支払名目 | 比率 | 支払条件 | 税抜金額 | 消費税額 | 税込金額 | 支払期日
    text = """
6. 報酬および支払条件
本契約の契約形態は固定価格とし、契約時に金額を固定し、工数実績による事後精算は行わない。
本契約の報酬総額は、税抜4,200,000円、消費税420,000円、税込4,620,000円とする。
支払回 | 支払名目 | 比率 | 支払条件 | 税抜金額 | 消費税額 | 税込金額 | 支払期日
1 | 着手金 | 50% | 契約締結後5営業日以内 | 2,100,000円 | 210,000円 | 2,310,000円 | 2025-04-16
2 | 検収金 | 50% | 検収完了後5営業日以内 | 2,100,000円 | 210,000円 | 2,310,000円 | 2025-06-04
"""
    row = parse_contract_text("青葉与信風", "契約書.docx", text)
    assert row["advance_payment_amount"] == 2_310_000


# --- 暗号化docxの復号フォールバック（office_crypto.pyの配線） ---
#
# 実データの暗号化契約書は「契約書_pw-<英字トークン><開始年月日8桁>.docx」のような
# 命名規則を使う。特定ファイル名のハードコードは競技規約違反のため、ここでは
# 架空のプロジェクト名・トークンによる合成フィクスチャのみを使い、汎用の
# regexベースの解決ロジックを検証する。
#
# footgun: msoffcrypto-tool 6.0.0は暗号化ペイロードが4KB未満だとmini-FAT/regular-FAT
# 不整合で往復が壊れることがある。python-docxで作る最小docxでもstyles.xml等の
# オーバーヘッドで自然に4KBを超えるが、念のためパディング段落を追加しておく。

CONTRACT_LINES = [
    "5. 契約期間",
    "本契約の契約期間は、2025-09-02から2025-10-06までとする。",
    "6. 報酬および支払条件",
    "本契約の契約形態は固定価格契約とし、契約金額（税抜）：1,000,000円、"
    "消費税額：100,000円、契約金額（税込）：1,100,000円とする。",
    "7. 知的財産",
]


def _real_docx_bytes(lines: list[str], padding_paragraphs: int = 150) -> bytes:
    """python-docxで実際に生成した最小docxのバイト列を返す（暗号化フィクスチャの平文用）。

    暗号化後のペイロードが確実に4KBを超えるよう、パディング段落を大量に追加する。
    """
    doc = DocxDocument()
    for line in lines:
        doc.add_paragraph(line)
    for i in range(padding_paragraphs):
        doc.add_paragraph("パディング用のテキストです。" * 5 + f" {i}")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_encrypted_docx(dest_path: Path, password: str, lines: list[str]) -> Path:
    plain_bytes = _real_docx_bytes(lines)
    plain_buf = io.BytesIO(plain_bytes)
    office_file = msoffcrypto.OfficeFile(plain_buf)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        office_file.encrypt(password, f)
    return dest_path


def test_read_docx_text_with_decryption_recovers_text_via_filename_password(tmp_path):
    alias = "TANUKI"
    start_date = "20250902"
    password = derive_office_password(alias, start_date, "docx")
    encrypted_path = tmp_path / f"契約書_pw-tanuki{start_date}.docx"
    _make_encrypted_docx(encrypted_path, password, CONTRACT_LINES)

    text = read_docx_text_with_decryption(
        encrypted_path,
        "架空プロジェクト",
        registry_path=tmp_path / "no_such_registry.json",
    )
    assert "契約金額（税込）：1,100,000円" in text


def test_read_docx_text_with_decryption_wrong_password_raises_invalid_key_error(tmp_path):
    alias = "TANUKI"
    actual_password = derive_office_password(alias, "20250902", "docx")
    # ファイル名の8桁は実際の暗号化パスワードの日付と異なる（導出失敗ケース）
    encrypted_path = tmp_path / "契約書_pw-tanuki20250101.docx"
    _make_encrypted_docx(encrypted_path, actual_password, CONTRACT_LINES)

    with pytest.raises(msoffcrypto.exceptions.InvalidKeyError):
        read_docx_text_with_decryption(
            encrypted_path,
            "架空プロジェクト",
            registry_path=tmp_path / "no_such_registry.json",
        )


def test_read_docx_text_with_decryption_falls_back_to_registry_primary_alias(tmp_path):
    # ファイル名のトークンが正式な案件略号と一致しないケース（通称等）でも、
    # project_registry.jsonのprimary_aliasを追加候補として試すことで復号できること。
    project_dir_name = "架空商事ホールディングス株式会社"
    real_alias = "TANUKIHD"
    start_date = "20250902"
    password = derive_office_password(real_alias, start_date, "docx")
    encrypted_path = tmp_path / f"契約書_pw-nickname{start_date}.docx"
    _make_encrypted_docx(encrypted_path, password, CONTRACT_LINES)

    registry_path = tmp_path / "project_registry.json"
    registry_path.write_text(
        json.dumps(
            [{"project_name": project_dir_name, "primary_alias": real_alias}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    text = read_docx_text_with_decryption(
        encrypted_path, project_dir_name, registry_path=registry_path
    )
    assert "契約金額（税込）：1,100,000円" in text


def test_read_docx_text_with_decryption_no_pw_pattern_raises():
    with pytest.raises(ValueError):
        read_docx_text_with_decryption(Path("契約書.docx"), "架空プロジェクト")


def test_build_contract_registry_decrypts_password_protected_docx(tmp_path):
    project_dir = tmp_path / "架空印刷合同会社"
    contract_dir = project_dir / "01.契約"
    alias = "KIRIN"
    start_date = "20250902"
    password = derive_office_password(alias, start_date, "docx")
    encrypted_path = contract_dir / f"契約書_pw-kirin{start_date}.docx"
    _make_encrypted_docx(encrypted_path, password, CONTRACT_LINES)

    rows = build_contract_registry(project_root=tmp_path)

    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "ok"
    assert row["contract_type"] == "fixed"
    assert row["estimated_amount_incl_tax"] == 1_100_000


def test_build_contract_registry_status_failed_when_password_mismatch(tmp_path):
    project_dir = tmp_path / "架空印刷合同会社2"
    contract_dir = project_dir / "01.契約"
    alias = "KIRIN"
    actual_password = derive_office_password(alias, "20250902", "docx")
    # ファイル名の8桁が実際のパスワードの日付と食い違う（全候補失敗ケース）
    encrypted_path = contract_dir / "契約書_pw-kirin20250101.docx"
    _make_encrypted_docx(encrypted_path, actual_password, CONTRACT_LINES)

    rows = build_contract_registry(project_root=tmp_path)

    assert len(rows) == 1
    assert rows[0]["status"] == "failed"


def test_build_contract_registry_plain_docx_still_ok(tmp_path):
    # 非暗号化の正常系docxが引き続きstatus==okであること（非退行確認）
    project_dir = tmp_path / "架空物産合同会社"
    contract_dir = project_dir / "01.契約"
    contract_dir.mkdir(parents=True)
    doc = DocxDocument()
    for line in CONTRACT_LINES:
        doc.add_paragraph(line)
    doc.save(contract_dir / "契約書.docx")

    rows = build_contract_registry(project_root=tmp_path)

    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["estimated_amount_incl_tax"] == 1_100_000
