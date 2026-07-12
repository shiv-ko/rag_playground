"""パスワード保護されたOOXMLファイル（docx/xlsx/pptx）を扱うユーティリティ。

データアステル社内規定_パスワード導出規則.docx（レビューで裏取り済み）に定められた
`DA-[案件略号]-[開始年月日8桁]-[拡張子コード]` 形式のパスワード導出と、
msoffcrypto-tool を使った復号（元ファイルは変更せず、指定した出力先に平文コピーを書く）に加え、
暗号化ファイルらしさの判定・ファイル名からのパスワード候補抽出も提供する。

`scripts/build_contract_registry.py`（契約書docx）と`scripts/extract_spreadsheets.py`
（スケジュールxlsx等）の両方から呼ばれる共通ユーティリティ。
"""
from __future__ import annotations

import re
from pathlib import Path

import msoffcrypto

_DATE_SEP_RE = re.compile(r"[^0-9]")

# CDFV2 (OLE2/Compound File Binary) のマジックナンバー。パスワード保護されたOOXMLファイルは
# 素のzipではなくこのコンテナ形式になるため、通常のパース失敗時に「暗号化されているらしいか」
# をここで判定してから復号フォールバックを試みる（他の破損原因と区別するため）。
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# 実運用の命名慣習（docs/encrypted_file_queue.md記載）: 暗号化されたファイルはファイル名に
# `pw-<案件略号><開始年月日8桁>` を含む。案件略号の綴りは問わず8桁の日付だけを抽出する
# （特定の案件名をハードコードしない汎用パターン）。
_FILENAME_DATE_RE = re.compile(r"pw-[a-zA-Z0-9]{0,32}?(\d{8})", re.IGNORECASE)

# 実データで判明した別の命名慣習: `pw-<トークン>`のトークン自体がDA-規則を介さず
# そのまま平文パスワードになっているケースがある。マーカー以降・拡張子より前の
# 英数字列全体を1つのリテラルパスワード候補として扱う（特定案件名のハードコードではなく
# `pw-`マーカーという汎用の命名規則から導出する）。
_FILENAME_LITERAL_PASSWORD_RE = re.compile(r"pw-([a-zA-Z0-9]+)", re.IGNORECASE)


def looks_like_encrypted_office_file(path: Path) -> bool:
    """先頭8バイトのCDFV2マジックナンバーで、パスワード保護されたOOXMLコンテナらしいかを判定する。"""
    try:
        return path.read_bytes()[:8] == _OLE_MAGIC
    except OSError:
        return False


def candidate_dates_from_filename(path: Path) -> list[str]:
    """ファイル名の`pw-...<8桁>`命名慣習から、パスワード導出用の日付候補(YYYYMMDD)を抽出する。"""
    return _FILENAME_DATE_RE.findall(path.stem)


def literal_password_from_filename(path: Path) -> str | None:
    """ファイル名の`pw-<トークン>`命名慣習から、トークン自体をリテラルパスワード候補として返す。

    DA-規則（案件略号・開始日・拡張子からの導出）とは別の、より直接的な命名慣習。
    マーカーが無ければNoneを返す。
    """
    match = _FILENAME_LITERAL_PASSWORD_RE.search(path.stem)
    return match.group(1) if match else None


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
