"""質問タイプ別の構造化コンテキストビルダー。"""
from __future__ import annotations

from pathlib import Path

from src.generator.color_names import nearest_basic_color_name
from src.models import Document, ScoredDocument
from src.structured.artifact_store import StructuredArtifactStore

_STYLE_KEYWORD_MAP = {
    "bold": ("太字",),
    "italic": ("イタリック",),
    "underline": ("下線",),
}
_COLOR_KEYWORD_MAP = {
    "red": ("赤",),
    "yellow": ("黄", "黄色"),
    "blue": ("青",),
    "green": ("緑",),
    "orange": ("オレンジ",),
    "purple": ("紫",),
    "pink": ("ピンク",),
}


def _requested_style_attrs(question: str) -> list[str]:
    return [
        attr
        for attr, keywords in _STYLE_KEYWORD_MAP.items()
        if any(k in question for k in keywords)
    ]


def _requested_color_names(question: str) -> list[str]:
    return [
        name
        for name, keywords in _COLOR_KEYWORD_MAP.items()
        if any(k in question for k in keywords)
    ]


def build_office_style_context(
    question: str, project_name: str, store: StructuredArtifactStore
) -> list[ScoredDocument]:
    marks = store.office_marks_for(project_name)
    style_attrs = _requested_style_attrs(question)
    color_names = _requested_color_names(question)
    if not style_attrs and not color_names:
        return []

    matched = []
    for mark in marks:
        if not mark.get("text", "").strip():
            continue
        if style_attrs and any(mark.get(attr) for attr in style_attrs):
            matched.append(mark)
            continue
        if color_names:
            font_name = nearest_basic_color_name(mark.get("font_color"))
            fill_name = nearest_basic_color_name(mark.get("fill_color"))
            if font_name in color_names or fill_name in color_names:
                matched.append(mark)

    docs = []
    for mark in matched:
        slide_number = mark.get("slide_number")
        location = f"slide_{slide_number}" if slide_number is not None else mark.get("unit_type", "")
        doc = Document(
            text=mark["text"],
            source_path=Path(mark["source_path"]),
            location=location,
        )
        docs.append(ScoredDocument(document=doc, score=1.0, retrieval_method="structured_office_style"))
    return docs


def _render_highlight_block(block: dict) -> str:
    header = block.get("column_header") or {}
    same_row = block.get("same_row_values") or []
    parts = [
        f"シート: {block.get('sheet_name')}",
        f"ハイライト範囲: {block.get('range')} (色: {block.get('fill_color_name')})",
        f"値: {block.get('first_value')}",
    ]
    if header.get("value"):
        parts.append(f"列見出し: {header['value']} ({header.get('cell')})")
    if same_row:
        row_desc = ", ".join(f"{c.get('cell')}={c.get('value')}" for c in same_row)
        parts.append(f"同じ行の値: {row_desc}")
    return "\n".join(parts)


def _requests_filter_condition(question: str) -> bool:
    return any(k in question for k in ("フィルター", "フィルタ"))


def _requests_highlight_condition(question: str) -> bool:
    return any(k in question for k in ("ハイライト", "highlight"))


def build_spreadsheet_state_context(
    question: str, project_name: str, store: StructuredArtifactStore
) -> list[ScoredDocument]:
    docs: list[ScoredDocument] = []

    if _requests_highlight_condition(question):
        for block in store.train_xlsx_highlight_blocks_for(project_name):
            source = block.get("source_path")
            if not source:
                continue
            doc = Document(
                text=_render_highlight_block(block),
                source_path=Path(source),
                location=f"sheet_{block.get('sheet_name')}",
            )
            docs.append(ScoredDocument(document=doc, score=1.0, retrieval_method="structured_spreadsheet_state"))

    if _requests_filter_condition(question):
        for sheet in store.spreadsheet_sheets_for(project_name):
            if not sheet.get("auto_filter_ref"):
                continue
            headers = [
                c for c in store.highlight_cells_for(project_name)
                if c.get("sheet_name") == sheet.get("sheet_name") and c.get("row") == 1
            ]
            header_text = ", ".join(f"{c.get('column')}列={c.get('value')}" for c in headers)
            hidden = sheet.get("hidden_rows") or []
            text = (
                f"シート: {sheet.get('sheet_name')}\n"
                f"フィルタ範囲: {sheet.get('auto_filter_ref')}\n"
                f"列見出し: {header_text}\n"
                f"非表示行番号: {hidden}"
            )
            doc = Document(
                text=text,
                source_path=Path(sheet["source_path"]),
                location=f"sheet_{sheet.get('sheet_name')}",
            )
            docs.append(ScoredDocument(document=doc, score=1.0, retrieval_method="structured_spreadsheet_state"))

    schedule_rows = store.schedule_tasks_for(project_name)
    if schedule_rows:
        matched_rows = []
        for row in schedule_rows:
            values = row.get("values", {})
            for key in ("フェーズ名", "担当者", "ステータス", "成果物"):
                cell_value = str(values.get(key, ""))
                if cell_value and cell_value in question:
                    matched_rows.append(row)
                    break
        for row in matched_rows:
            values = row.get("values", {})
            text = ", ".join(f"{k}={v}" for k, v in values.items())
            doc = Document(
                text=text,
                source_path=Path(row["source_path"]),
                location=f"sheet_{row.get('sheet_name')}_row_{row.get('row_number')}",
            )
            docs.append(ScoredDocument(document=doc, score=1.0, retrieval_method="structured_spreadsheet_state"))

    return docs
