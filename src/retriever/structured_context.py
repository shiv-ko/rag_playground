"""質問タイプ別の構造化コンテキストビルダー。"""
from __future__ import annotations

import re
from pathlib import Path

from src.generator.color_names import nearest_basic_color_name
from src.models import Document, ScoredDocument
from src.structured.artifact_store import StructuredArtifactStore

_STYLE_KEYWORD_MAP = {
    "bold": ("太字",),
    "italic": ("イタリック",),
    "underline": ("下線",),
}
_STYLE_LABELS = {"bold": "太字", "italic": "イタリック", "underline": "下線"}
_COLOR_LABELS = {
    "red": "赤", "yellow": "黄色", "blue": "青", "green": "緑",
    "orange": "オレンジ", "purple": "紫", "pink": "ピンク",
    "black": "黒", "white": "白", "gray": "灰色", "brown": "茶", "cyan": "シアン",
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


_SPREADSHEET_HINTS = (".xlsx", "シート", "セル", "ピボット", "pivot")


def question_mentions_spreadsheet(question: str) -> bool:
    """質問がxlsx系ファイルを指しているか（office_style/spreadsheet_state両タグが
    付いた場合に、どちらの構造化パスを先に試すかの判定に使う）。"""
    lower = question.lower()
    return any(hint in lower for hint in _SPREADSHEET_HINTS)


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


# docxのrun.font.highlight_colorはWD_COLOR_INDEXの文字列（例: "YELLOW (7)"）で入る
_HIGHLIGHT_NAME_ALIASES = {"bright_green": "green", "dark_yellow": "yellow", "dark_red": "red"}


def _highlight_color_name(mark: dict) -> str:
    raw = mark.get("highlight_color")
    if not raw:
        return "none"
    token = str(raw).split("(")[0].strip().lower()
    return _HIGHLIGHT_NAME_ALIASES.get(token, token)


def _narrow_marks_by_question_hints(question: str, marks: list[dict]) -> list[dict]:
    """質問中のファイル種別・ファイル名・ページ番号ヒントで候補を絞る。
    絞った結果が0件になるヒントは適用しない（安全側）。すべて汎用ヒントで、
    特定の案件名・ファイル名のハードコードはしない。"""
    lower = question.lower()

    ext = None
    if "docx" in lower:
        ext = ".docx"
    elif "pptx" in lower or "スライド" in question:
        ext = ".pptx"
    if ext:
        narrowed = [
            m for m in marks
            if str(m.get("extension") or Path(str(m.get("file_name") or "")).suffix).lower() == ext
        ]
        if narrowed:
            marks = narrowed

    stems = {Path(str(m.get("file_name") or "")).stem for m in marks}
    hinted_stems = {s for s in stems if s and s in question}
    if hinted_stems:
        narrowed = [m for m in marks if Path(str(m.get("file_name") or "")).stem in hinted_stems]
        if narrowed:
            marks = narrowed

    page = re.search(r"[PpＰ]\s*(\d+)|スライド\s*(\d+)|(\d+)\s*ページ", question)
    if page:
        num = int(next(g for g in page.groups() if g))
        narrowed = [m for m in marks if m.get("slide_number") == num]
        if narrowed:
            marks = narrowed

    return marks


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
        decorations = [
            _STYLE_LABELS[attr] for attr in style_attrs if mark.get(attr)
        ]
        if color_names:
            font_name = nearest_basic_color_name(mark.get("font_color"))
            fill_name = nearest_basic_color_name(mark.get("fill_color"))
            highlight_name = _highlight_color_name(mark)
            if font_name in color_names:
                decorations.append(f"{_COLOR_LABELS.get(font_name, font_name)}の文字色")
            if fill_name in color_names:
                decorations.append(f"{_COLOR_LABELS.get(fill_name, fill_name)}の背景色")
            if highlight_name in color_names:
                decorations.append(f"{_COLOR_LABELS.get(highlight_name, highlight_name)}のハイライト")
        if decorations:
            matched.append((mark, decorations))

    narrowed_marks = _narrow_marks_by_question_hints(question, [m for m, _ in matched])
    narrowed_ids = {id(m) for m in narrowed_marks}
    matched = [(m, d) for m, d in matched if id(m) in narrowed_ids]

    docs = []
    for mark, decorations in matched:
        slide_number = mark.get("slide_number")
        location = f"slide_{slide_number}" if slide_number is not None else mark.get("unit_type", "")
        # LLMが「この断片は質問の装飾条件に一致した箇所だ」と確信できるよう自己記述にする
        file_name = mark.get("file_name") or Path(str(mark.get("source_path") or "")).name
        text = f"{file_name} 内の装飾箇所（{'、'.join(decorations)}）: {mark['text']}"
        doc = Document(
            text=text,
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


# スケジュール表の列名はプロジェクトごとに揺れる（「フェーズ名」/「フェーズ」等）ため、
# 列名の部分一致で「質問の絞り込み条件になりうる列」を判定する
_SCHEDULE_MATCH_KEY_PARTS = ("フェーズ", "担当", "ステータス", "成果物")
# 値の先頭の番号接頭辞（「3. 探索的分析・仮説整理」等）は質問文には現れないことが多い
_NUMBER_PREFIX_RE = re.compile(r"^\s*\d+\s*[\.．]\s*")


def _schedule_value_match_parts(raw_value: str) -> list[str]:
    """マッチ判定に使う値の候補: 番号接頭辞を除いた全体＋区切り文字で分割した各要素
    （担当者「山本 彩乃 / 藤田 彩」のような複合値に対応）。短すぎる断片は誤マッチ源なので捨てる。"""
    value = _NUMBER_PREFIX_RE.sub("", raw_value).strip()
    parts = [value] + [p.strip() for p in re.split(r"[/、,]", value)]
    return [p for p in parts if len(p) >= 2]


def _schedule_row_matches_question(values: dict, question: str) -> bool:
    question_no_space = re.sub(r"[ 　]", "", question)
    for key, raw in values.items():
        if not any(part in str(key) for part in _SCHEDULE_MATCH_KEY_PARTS):
            continue
        raw_str = str(raw or "").strip()
        if not raw_str or raw_str == str(key):  # 空値・ヘッダ行の残骸は除外
            continue
        for part in _schedule_value_match_parts(raw_str):
            if part in question or re.sub(r"[ 　]", "", part) in question_no_space:
                return True
    return False


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
        matched_rows = [
            row for row in schedule_rows
            if _schedule_row_matches_question(row.get("values", {}), question)
        ]
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
