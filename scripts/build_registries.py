"""Build project/document/term registries for data routing."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from docx import Document as DocxDocument

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.glossary import parse_project_aliases, parse_term_entries

SHARE_ROOT = ROOT / "data" / "raw" / "share" / "共有ドライブ"
PROJECT_ROOT = SHARE_ROOT / "プロジェクト"
INTERNAL_ROOT = SHARE_ROOT / "社内管理"
ARTIFACTS = ROOT / "artifacts"
GLOSSARY_PATH = INTERNAL_ROOT / "社内用語集.docx"


SECTION_PREFIXES = {
    "00.": "00.提案",
    "01.": "01.契約",
    "02.": "02.計画",
    "03.": "03.データ",
    "04.": "04.分析",
    "05.": "05.会議",
    "06.": "06.報告書",
}


def read_docx_tables(path: Path) -> list[list[list[str]]]:
    """docxの全テーブルを list[表] / 表=list[行] / 行=list[セル文字列] として読む。"""
    doc = DocxDocument(path)
    return [[[cell.text for cell in row.cells] for row in table.rows] for table in doc.tables]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_project_name(name: str) -> str:
    # macOSのファイルシステムはユニコードをNFD分解して返すため、
    # ディレクトリ名(NFD)とdocx由来の案件名(NFC)がバイト列として不一致になりうる。
    return unicodedata.normalize("NFC", name).replace(" ", "")


def aliases_for(project_name: str, project_aliases: dict[str, list[str]]) -> list[str]:
    normalized = normalize_project_name(project_name)
    aliases = {normalized}
    for key, values in project_aliases.items():
        if normalize_project_name(key) == normalized:
            aliases.update(values)
    # Conservative short aliases from company name (NFC正規化後の文字列に対して判定する。
    # ディレクトリ名がNFD分解されている場合、正規化前の文字列だとtoken一致に失敗するため)。
    for token in ("株式会社", "医療法人社団", "総合病院", "女性医療センター"):
        if token in normalized:
            aliases.add(normalized.replace(token, "").strip())
    return sorted(alias for alias in aliases if alias)


def section_for(path: Path) -> tuple[str | None, str | None]:
    try:
        rel = path.relative_to(PROJECT_ROOT)
    except ValueError:
        return "社内管理", None
    parts = rel.parts
    raw = parts[1] if len(parts) > 1 else None
    if not raw:
        return None, None
    section = next((value for prefix, value in SECTION_PREFIXES.items() if raw.startswith(prefix)), raw)
    return section, raw


def version_tag(path: Path) -> str | None:
    text = "/".join(path.parts).lower()
    name = path.stem.lower()
    if "/old/" in text or "old" in name:
        return "old"
    for tag in ("final", "draft", "v1", "v2", "v3", "r1", "r2"):
        if re.search(rf"(^|[_\-.]){tag}($|[_\-.])", name) or f"/{tag}/" in text:
            return tag
    return None


def version_order(tag: str | None) -> int | None:
    order = {
        "old": 0,
        "draft": 1,
        "r1": 2,
        "v1": 2,
        "r2": 3,
        "v2": 3,
        "v3": 4,
        "final": 5,
    }
    return order.get(tag) if tag else None


def document_type(path: Path, section: str | None) -> str:
    name = path.name
    parts = path.parts
    if section == "00.提案":
        if "提案" in name:
            return "proposal"
        return "proposal_reference"
    if section == "01.契約":
        return "contract"
    if section == "02.計画":
        return "plan"
    if section == "03.データ":
        if name.startswith("train"):
            return "train_data"
        if "カラム説明" in name:
            return "column_description"
        return "data_reference"
    if section == "04.分析":
        if "metrics" in name:
            return "analysis_metrics"
        if "leaderboard" in name:
            return "analysis_leaderboard"
        if path.suffix == ".ipynb":
            return "notebook"
        if path.suffix == ".py":
            return "analysis_code"
        if path.suffix == ".png":
            return "analysis_figure"
        return "analysis_artifact"
    if section == "05.会議":
        if "会議録" in parts or "会議録" in name:
            return "meeting_minutes"
        if "報告資料" in parts or "報告資料" in name:
            return "meeting_report"
        return "meeting_artifact"
    if section == "06.報告書":
        return "final_report"
    if section == "社内管理":
        if "用語集" in name:
            return "term_glossary"
        if "決裁基準" in name:
            return "approval_rule"
        if "パスワード" in name:
            return "password_rule"
        if "座席表" in name:
            return "seat_map"
        return "internal_admin"
    return "unknown"


def ids_from_path(path: Path) -> list[str]:
    text = path.name
    return sorted(set(re.findall(r"\b(?:M|MS|T|A|CP)\d{1,3}\b", text)))


def build_project_registry(project_aliases: dict[str, list[str]]) -> list[dict[str, Any]]:
    projects = []
    for project_dir in sorted(p for p in PROJECT_ROOT.iterdir() if p.is_dir()):
        files = [p for p in project_dir.rglob("*") if p.is_file()]
        projects.append(
            {
                "project_name": project_dir.name,
                "aliases": aliases_for(project_dir.name, project_aliases),
                "file_count": len(files),
                "sections": sorted({section_for(p)[0] for p in files if section_for(p)[0]}),
            }
        )
    return projects


def build_document_registry(project_aliases: dict[str, list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    all_files = [p for p in PROJECT_ROOT.rglob("*") if p.is_file()]
    all_files.extend(p for p in INTERNAL_ROOT.rglob("*") if p.is_file())
    for path in sorted(all_files):
        project_name = None
        try:
            rel_project = path.relative_to(PROJECT_ROOT)
            project_name = rel_project.parts[0]
        except ValueError:
            pass
        section, raw_section = section_for(path)
        tag = version_tag(path)
        rows.append(
            {
                "source_path": str(path.relative_to(ROOT)),
                "project_name": project_name,
                "project_aliases": aliases_for(project_name, project_aliases) if project_name else [],
                "section": section,
                "raw_section": raw_section,
                "document_type": document_type(path, section),
                "file_name": path.name,
                "stem": path.stem,
                "extension": path.suffix.lower(),
                "version_tag": tag,
                "version_order": version_order(tag),
                "ids": ids_from_path(path),
                "is_noise_candidate": path.name.startswith("~$") or path.suffix.lower() in {".pyc", ".lock"},
                "size_bytes": path.stat().st_size,
            }
        )
    return rows


def main() -> None:
    tables = read_docx_tables(GLOSSARY_PATH)
    project_aliases = parse_project_aliases(tables)
    term_registry = parse_term_entries(tables)

    projects = build_project_registry(project_aliases)
    documents = build_document_registry(project_aliases)
    write_json(ARTIFACTS / "project_registry.json", projects)
    write_jsonl(ARTIFACTS / "document_registry.jsonl", documents)
    write_json(ARTIFACTS / "term_registry.json", term_registry)
    print(f"projects={len(projects)}")
    print(f"documents={len(documents)}")
    print(f"terms={len(term_registry)}")


if __name__ == "__main__":
    main()
