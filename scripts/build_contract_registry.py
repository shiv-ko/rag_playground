"""Build contract registry from project contract documents."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import msoffcrypto
from docx import Document as DocxDocument
from pptx import Presentation

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.office_crypto import decrypt_office_file, derive_office_password

SHARE_ROOT = ROOT / "data" / "raw" / "share" / "共有ドライブ"
PROJECT_ROOT = SHARE_ROOT / "プロジェクト"
ARTIFACTS = ROOT / "artifacts"
CONTRACTS_PATH = ARTIFACTS / "contracts.jsonl"
PROJECT_REGISTRY_PATH = ARTIFACTS / "project_registry.json"

# 実データの暗号化契約書は「契約書_pw-<英字トークン><開始年月日8桁>.docx」のような
# 命名規則を使う（社内規定のパスワード導出規則:
# DA-[案件略号]-[開始年月日8桁]-[拡張子コード]）。特定ファイル名のハードコードは
# 競技規約違反のため、汎用の命名規則regexのみを使う。
PW_FILENAME_RE = re.compile(r"pw-([A-Za-z]+)(\d{8})", re.IGNORECASE)


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("\u3000", " ")


def parse_yen(value: str) -> int:
    return int(re.sub(r"[^0-9]", "", value))


def parse_float(value: str) -> float:
    return float(value.replace(",", ""))


def read_docx_text(path: Path) -> str:
    doc = DocxDocument(path)
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if values:
                lines.append(" | ".join(values))
    return normalize_text("\n".join(lines))


def _load_project_registry(registry_path: Path) -> list[dict[str, Any]]:
    if not registry_path.exists():
        return []
    with registry_path.open(encoding="utf-8") as f:
        return json.load(f)


def _password_alias_candidates(
    path: Path, project_dir_name: str, registry_path: Path
) -> list[str]:
    """パスワード導出に使う案件略号候補を優先順（ファイル名 → registry）で返す。

    ファイル名の汎用パターン `pw-<英字トークン><8桁数字>` に一致しない場合は空リスト
    （＝復号を試みない）。8桁の開始年月日はファイル名由来のみを使う
    （registry側は日付を持たないため）。
    """
    match = PW_FILENAME_RE.search(path.stem)
    if not match:
        return []
    aliases = [match.group(1).upper()]
    registry = _load_project_registry(registry_path)
    normalized_dir_name = unicodedata.normalize("NFC", project_dir_name)
    for proj in registry:
        proj_name = unicodedata.normalize("NFC", proj.get("project_name", ""))
        if proj_name != normalized_dir_name:
            continue
        # パスワード規則の略号は大文字（DA-KAEDE-...）。registry値は現状すべて
        # 大文字だが、導出規則側の前提として明示的に揃える。
        primary_alias = (proj.get("primary_alias") or "").upper()
        if primary_alias and primary_alias not in aliases:
            aliases.append(primary_alias)
        break
    return aliases


def read_docx_text_with_decryption(
    path: Path,
    project_dir_name: str,
    registry_path: Path = PROJECT_REGISTRY_PATH,
) -> str:
    """暗号化docxの復号を試みてからテキストを抽出するフォールバック。

    パスワードは「ファイル名の汎用パターン」から導出した案件略号・開始年月日8桁を
    最優先候補とし、project_registry.jsonのprimary_aliasが読めれば追加候補として
    順に試す（`InvalidKeyError`は次候補へ）。ファイル名がパターンに一致しない、
    または全候補で復号失敗した場合は例外を送出し、呼び出し側で従来通り
    `status=failed`に落とす。
    """
    match = PW_FILENAME_RE.search(path.stem)
    if not match:
        raise ValueError(
            f"filename does not match pw-<alias><8digits> pattern: {path.name}"
        )
    start_date = match.group(2)
    aliases = _password_alias_candidates(path, project_dir_name, registry_path)

    last_error: Exception | None = None
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / f"decrypted{path.suffix}"
        for alias in aliases:
            password = derive_office_password(alias, start_date, path.suffix)
            try:
                decrypt_office_file(path, password, output_path)
            except msoffcrypto.exceptions.InvalidKeyError as exc:
                last_error = exc
                continue
            return read_docx_text(output_path)

    if last_error is not None:
        raise last_error
    raise ValueError(f"no usable password candidates for {path.name}")


def read_pptx_text(path: Path) -> str:
    prs = Presentation(path)
    lines: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text.strip():
                lines.append(shape.text)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if values:
                        lines.append(" | ".join(values))
    return normalize_text("\n".join(lines))


def read_pdf_text(path: Path) -> str:
    import pypdf

    reader = pypdf.PdfReader(str(path))
    return normalize_text("\n".join(page.extract_text() or "" for page in reader.pages))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def select_contract_path(project_dir: Path) -> Path | None:
    contract_dirs = [p for p in project_dir.iterdir() if p.is_dir() and p.name.startswith("01.")]
    candidates: list[Path] = []
    for contract_dir in contract_dirs:
        candidates.extend(
            p for p in contract_dir.glob("*.docx")
            if not p.name.startswith("~$") and "draft" not in p.stem.lower()
        )
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: ("pw-" in p.name, p.name))[0]


def extract_billing_clause(text: str) -> str:
    match = re.search(r"6\.\s*報酬および支払条件(?P<body>.*?)(?:\n7\.|\n第7条|$)", text, re.DOTALL)
    body = match.group("body") if match else text
    return " ".join(body.split())[:1200]


def classify_contract_type(text: str) -> str:
    if "time_and_materials" in text or "Time & Materials" in text:
        return "time_and_materials"
    if "固定価格" in text or "固定金額" in text or "金額を固定" in text:
        return "fixed"
    return "unknown"


def classify_rounding_rule(clause: str) -> str:
    if "30分未満を0.5時間" in clause and "30分超60分未満を1.0時間" in clause:
        return "half_unit_bucket"
    if "30分" in clause and ("切り上げ" in clause or "切上げ" in clause):
        return "ceiling_to_unit"
    if "丸め" not in clause and "端数" not in clause:
        return "none"
    return "unknown"


def first_amount(patterns: list[str], text: str) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return parse_yen(match.group(1))
    return None


def extract_advance_payment(text: str, amount_incl: int | None) -> int | None:
    direct = first_amount([r"着手金[：:\s]*([0-9,]+)円"], text)
    if direct is not None:
        return direct
    if amount_incl is None:
        return None
    # 支払表は案件ごとに列順が異なる(税抜/税込の位置が揺れる)ため、金額セルを直接
    # 拾わず、同じ行にある比率(%)から契約金額（税込）に対する割合として算出する。
    for line in text.splitlines():
        if "着手金" not in line:
            continue
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[%％]", line)
        if match:
            return int(round(amount_incl * float(match.group(1)) / 100))
    return None


def extract_dates(text: str) -> tuple[str | None, str | None, int | None]:
    match = re.search(
        r"(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?\s*から\s*(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?\s*まで",
        text,
    )
    if match:
        values = [int(v) for v in match.groups()]
        start = date(values[0], values[1], values[2])
        end = date(values[3], values[4], values[5])
        return start.isoformat(), end.isoformat(), (end - start).days + 1
    match = re.search(r"(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?\s*から起算して(\d+)週間", text)
    if not match:
        return None, None, None
    year, month, day, weeks = [int(v) for v in match.groups()]
    start = date(year, month, day)
    end = start + timedelta(days=weeks * 7 - 1)
    return start.isoformat(), end.isoformat(), (end - start).days + 1


def extract_report_values(project_dir: Path) -> dict[str, Any]:
    report_dirs = [p for p in project_dir.iterdir() if p.is_dir() and p.name.startswith("06.")]
    texts: list[str] = []
    for report_dir in report_dirs:
        for path in sorted(report_dir.glob("*.pptx")):
            if "old" in path.stem.lower() or path.name.startswith("~$"):
                continue
            try:
                texts.append(read_pptx_text(path))
            except Exception:
                continue
        for path in sorted(report_dir.glob("*.pdf")):
            try:
                texts.append(read_pdf_text(path))
            except Exception:
                continue
    text = "\n".join(texts)
    actual_hours = None
    m_hours = re.search(r"実績工数[：:\s|]*([0-9]+(?:\.[0-9]+)?)\s*時間", text)
    if m_hours:
        actual_hours = parse_float(m_hours.group(1))
    final_incl = first_amount([r"最終請求金額（税込）[：:\s|]*([0-9,]+)\s*円", r"税込金額[：:\s|]*([0-9,]+)\s*円"], text)
    return {"actual_hours": actual_hours, "final_amount_incl_tax": final_incl}


def parse_contract_text(project_name: str, source_path: str, text: str) -> dict[str, Any]:
    text = normalize_text(text)
    clause = extract_billing_clause(text)
    contract_type = classify_contract_type(text)
    start_date, end_date, days = extract_dates(text)
    rate = first_amount([r"時間単価[は：:\s|]*([0-9,]+)円", r"1時間当たり([0-9,]+)円"], text)
    esth_match = re.search(r"(?:想定総工数|見込工数)[は：:\s]*([0-9]+(?:\.[0-9]+)?)\s*時間", text)
    esth = parse_float(esth_match.group(1)) if esth_match else None
    amount_excl = first_amount([r"(?:契約金額|報酬総額|見込金額|想定金額)（税抜）[：:\s|]*([0-9,]+)円", r"税抜\s*([0-9,]+)円"], text)
    amount_incl = first_amount([r"(?:契約金額|報酬総額|見込金額|想定金額)（税込）[：:\s|]*([0-9,]+)円", r"税込\s*([0-9,]+)円"], text)
    tax = first_amount([r"消費税(?:額)?[：:\s]*([0-9,]+)円"], text)
    advance = extract_advance_payment(text, amount_incl)
    return {
        "project_name": project_name,
        "contract_type": contract_type,
        "rate_yen_per_hour": rate,
        "esth_hours": esth,
        "estimated_amount_excl_tax": amount_excl,
        "estimated_amount_incl_tax": amount_incl,
        "tax_rate": round(tax / amount_excl, 2) if tax and amount_excl else 0.10,
        "rounding_unit_minutes": 30 if "30分" in clause else None,
        "rounding_rule": classify_rounding_rule(clause),
        "start_date": start_date,
        "end_date": end_date,
        "contract_period_days": days,
        "advance_payment_amount": advance,
        "raw_billing_clause": clause,
        "source_path": source_path,
        "status": "ok",
        "error": None,
    }


def build_contract_registry(project_root: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for project_dir in sorted(p for p in project_root.iterdir() if p.is_dir()):
        path = select_contract_path(project_dir)
        if path is None:
            continue
        project_name = normalize_text(project_dir.name)
        try:
            rel_path = str(path.relative_to(ROOT))
        except ValueError:
            # project_root がROOT配下でない場合（テストのtmp_pathフィクスチャ等）。
            rel_path = str(path)
        # 復号フォールバックはread_docx_text（暗号化ファイル等での読み込み失敗）にのみ
        # 適用する。parse/report抽出の例外まで巻き込むと、無関係な失敗の元例外が
        # パターン不一致のValueErrorで上書きされてデバッグ時に誤誘導になる。
        try:
            text = read_docx_text(path)
        except Exception as read_exc:  # noqa: BLE001
            try:
                text = read_docx_text_with_decryption(path, project_dir.name)
            except Exception as decrypt_exc:  # noqa: BLE001
                rows.append({
                    "project_name": project_name,
                    "source_path": rel_path,
                    "contract_type": "unknown",
                    "status": "failed",
                    "error": f"{read_exc!r} (decrypt fallback: {decrypt_exc!r})",
                })
                continue
        try:
            row = parse_contract_text(project_name, rel_path, text)
            row.update(extract_report_values(project_dir))
        except Exception as exc:  # noqa: BLE001
            row = {
                "project_name": project_name,
                "source_path": rel_path,
                "contract_type": "unknown",
                "status": "failed",
                "error": repr(exc),
            }
        rows.append(row)
    return rows


def main() -> None:
    rows = build_contract_registry()
    write_jsonl(CONTRACTS_PATH, rows)
    print(f"contracts={len(rows)}")
    print(f"ok={sum(1 for row in rows if row.get('status') == 'ok')}")
    print(f"failed={sum(1 for row in rows if row.get('status') != 'ok')}")


if __name__ == "__main__":
    main()
