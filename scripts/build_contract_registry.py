"""Build contract registry from project contract documents."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from docx import Document as DocxDocument
from pptx import Presentation

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SHARE_ROOT = ROOT / "data" / "raw" / "share" / "共有ドライブ"
PROJECT_ROOT = SHARE_ROOT / "プロジェクト"
ARTIFACTS = ROOT / "artifacts"
CONTRACTS_PATH = ARTIFACTS / "contracts.jsonl"


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
    match = re.search(r"(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?\s*から\s*(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?\s*まで", text)
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
        rel_path = str(path.relative_to(ROOT))
        try:
            row = parse_contract_text(project_name, rel_path, read_docx_text(path))
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
