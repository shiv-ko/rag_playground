"""パスワード保護されたOOXMLファイル（docx/xlsx/pptx）を扱うユーティリティ。

データアステル社内規定_パスワード導出規則.docx（レビューで裏取り済み）に定められた
`DA-[案件略号]-[開始年月日8桁]-[拡張子コード]` 形式のパスワード導出と、
msoffcrypto-tool を使った復号（元ファイルは変更せず、指定した出力先に平文コピーを書く）
の2機能を提供する。

このモジュールはbuild_contract_registry.pyから呼ばれる想定だが、配線は別タスク。
ここでは単体の汎用ユーティリティとしてのみ実装・テストする。
"""
from __future__ import annotations

import re
from pathlib import Path

import msoffcrypto

_DATE_SEP_RE = re.compile(r"[^0-9]")


def _normalize_start_date(start_date: str) -> str:
    """`YYYY-MM-DD`等の日付表記、または既に8桁の数字列を`YYYYMMDD`へ正規化する。"""
    digits = _DATE_SEP_RE.sub("", start_date)
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError(
            f"start_date must normalize to 8 digits (YYYYMMDD), got {start_date!r}"
        )
    return digits


def _normalize_extension(file_extension: str) -> str:
    """先頭のドットの有無を吸収し、小文字化した拡張子コードを返す。"""
    return file_extension.lstrip(".").lower()


def derive_office_password(project_alias: str, start_date: str, file_extension: str) -> str:
    """社内規定のパスワード導出規則を実装する純粋関数（I/Oなし）。

    形式: `DA-[案件略号]-[開始年月日8桁]-[拡張子コード]`
    例: derive_office_password("AOMINE", "2025-08-06", ".xlsx") == "DA-AOMINE-20250806-xlsx"
    """
    date_part = _normalize_start_date(start_date)
    ext_part = _normalize_extension(file_extension)
    return f"DA-{project_alias}-{date_part}-{ext_part}"


def decrypt_office_file(source_path: Path, password: str, output_path: Path) -> Path:
    """パスワード保護されたOOXMLファイルを復号し、平文コピーをoutput_pathに書く。

    source_path（元ファイル）やそのディレクトリには一切書き込まない。
    パスワードが誤っている等で復号できない場合は
    msoffcrypto.exceptions.InvalidKeyError（DecryptionErrorのサブクラス）が送出される。
    呼び出し側（将来のbuild_contract_registry.py連携）はこれを捕捉して
    status=failedにフォールバックする想定（既存の安全側フォールバック方針に合わせる）。
    """
    source_path = Path(source_path)
    output_path = Path(output_path)

    with open(source_path, "rb") as f:
        office_file = msoffcrypto.OfficeFile(f)
        office_file.load_key(password=password, verify_password=True)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as out:
            office_file.decrypt(out)

    return output_path
