"""パスワード保護されたOOXMLファイル（docx/xlsx/pptx）を扱うユーティリティ。

データアステル社内規定_パスワード導出規則.docx（レビューで裏取り済み）に定められた
`DA-[案件略号]-[開始年月日8桁]-[拡張子コード]` 形式のパスワード導出と、
msoffcrypto-tool を使った復号（元ファイルは変更せず、指定した出力先に平文コピーを書く）に加え、
暗号化ファイルらしさの判定・ファイル名からのパスワード候補抽出も提供する。

`scripts/build_contract_registry.py`（契約書docx）と`scripts/extract_spreadsheets.py`
（スケジュールxlsx等）の両方から呼ばれる共通ユーティリティ。
"""
from __future__ import annotations

import json
import re
import unicodedata
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


# 実データ由来のマーカー: `data/raw/.../共有ドライブ/プロジェクト/<案件名>/...`という
# ディレクトリ構造の"プロジェクト"直下が案件名。特定案件名のハードコードではなく、
# この汎用ディレクトリ規約から案件名を取り出す（dispatcher.py::_extract_metadataと同じ規約）。
_PROJECT_DIR_MARKER = "プロジェクト"


def normalize_project_text(text: str) -> str:
    """案件名の表記ゆれ吸収: NFC正規化＋全角スペース→半角スペース。

    build_contract_registry.py / extract_spreadsheets.py の同名ローカル関数と同一ロジック。
    """
    return unicodedata.normalize("NFC", text).replace("　", " ")


def load_primary_aliases(project_registry_path: Path) -> dict[str, str]:
    """project_registry.json（機械生成の案件レジストリ）から

    `project_name(正規化済み) -> primary_alias` の対応表を作る。ファイルが無ければ空の辞書。
    """
    project_registry_path = Path(project_registry_path)
    if not project_registry_path.exists():
        return {}
    data = json.loads(project_registry_path.read_text(encoding="utf-8"))
    return {
        normalize_project_text(row["project_name"]): row["primary_alias"]
        for row in data
        if row.get("primary_alias")
    }


def candidate_start_dates_from_contracts(
    project_name: str, contracts_path: Path
) -> list[str]:
    """同一案件のcontracts.jsonl（既に復号済みの契約書から生成された構造化artifact）から

    パスワード導出用の開始/終了日候補(YYYYMMDD、出現順・重複除去)を抽出する。
    ファイル名に`pw-...<8桁>`の日付が無い暗号化ファイル（実データのKAEDEスケジュール.xlsx等）
    でも、同一案件の既知の日付からDA-規則パスワードを再構成できるようにするための代替経路。
    """
    contracts_path = Path(contracts_path)
    if not contracts_path.exists():
        return []
    normalized_project = normalize_project_text(project_name)
    candidates: list[str] = []
    seen: set[str] = set()
    with contracts_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if normalize_project_text(row.get("project_name", "")) != normalized_project:
                continue
            for key in ("start_date", "end_date"):
                value = row.get(key)
                if not value:
                    continue
                digits = _DATE_SEP_RE.sub("", str(value))[:8]
                if len(digits) == 8 and digits not in seen:
                    seen.add(digits)
                    candidates.append(digits)
    return candidates


def project_name_from_path(path: Path, marker: str = _PROJECT_DIR_MARKER) -> str | None:
    """パスの中から`プロジェクト`ディレクトリ直下の案件名セグメントを取り出す。

    特定の案件名を判定に使わず、汎用のディレクトリ規約（マーカー名の次のセグメント）
    のみに依拠する。macOS/zip展開由来のNFD分解パスとソース中のNFCリテラルが
    一致しない事故（dispatcher.py::_extract_metadataで対策済みと同型）を避けるため、
    比較前に各セグメントをNFCへ正規化する。マーカーが無ければNoneを返す。
    """
    parts = tuple(unicodedata.normalize("NFC", part) for part in Path(path).parts)
    normalized_marker = unicodedata.normalize("NFC", marker)
    if normalized_marker not in parts:
        return None
    idx = parts.index(normalized_marker)
    if idx + 1 >= len(parts):
        return None
    return parts[idx + 1]


def password_candidates_for_file(
    path: Path,
    project_name: str,
    primary_aliases: dict[str, str],
    contracts_path: Path,
) -> list[str]:
    """暗号化ファイルに対して試すパスワード候補を優先順に返す（I/Oはcontracts_pathの読込のみ）。

    2系統の候補を組み合わせる（build_contract_registry.py / extract_spreadsheets.py の
    既存の2系統ロジックと同一の優先順位）:
    (1) ファイル名`pw-<トークン>`のトークン自体をリテラルパスワードとして先に試す。
    (2) DA-規則 `DA-[案件略号]-[開始年月日8桁]-[拡張子コード]`。開始年月日はまず
        ファイル名の`pw-...<8桁>`命名慣習から、それが無ければ同一案件のcontracts.jsonl
        (start_date/end_date)から候補を得る。案件略号(primary_alias)が無ければ(2)は空。
    候補が1つも無い場合は空リストを返す（呼び出し側はstubフォールバックへ進む）。
    """
    candidates: list[str] = []
    literal_password = literal_password_from_filename(path)
    if literal_password is not None:
        candidates.append(literal_password)

    alias = primary_aliases.get(normalize_project_text(project_name))
    if alias:
        dates = candidate_dates_from_filename(path)
        if not dates:
            dates = candidate_start_dates_from_contracts(project_name, contracts_path)
        ext = Path(path).suffix
        for date in dates:
            candidates.append(derive_office_password(alias, date, ext))
    return candidates
