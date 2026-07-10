"""質問タイプ別の構造化コンテキストビルダー。"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from src.generator.color_names import nearest_basic_color_name
from src.models import Document, ScoredDocument
from src.retriever.question_file_scope import find_named_files
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


def _render_filter_conditions(sheet: dict) -> str:
    lines = [
        f"シート: {sheet.get('sheet_name')}（{sheet.get('file_name')}）",
        f"フィルタ範囲: {sheet.get('auto_filter_ref')}（非表示行 {sheet.get('hidden_row_count', 0)}行）",
        "フィルタで抽出されている条件（xlsxのautoFilter定義から機械抽出）:",
    ]
    for fc in sheet.get("filter_columns") or []:
        name = fc.get("header") or f"列{fc.get('col_id')}"
        if fc.get("values"):
            lines.append(f"  - {name} = {' / '.join(str(v) for v in fc['values'])}")
        for cf in fc.get("custom") or []:
            lines.append(f"  - {name} {cf.get('operator')} {cf.get('val')}")
    return "\n".join(lines)


# scripts/extract_spreadsheets.pyのnormalize_color()は彩度の高い標準色を、hexの
# 代わりにこれらの名前文字列でdominant_row_fillへ格納することがある。
_NAMED_COLOR_FAMILIES = {"yellow", "red", "blue", "orange", "green", "purple", "pink"}
_NAMED_ACHROMATIC_COLORS = {"black", "white", "gray", "grey"}


def _hex_color_family(hex_str: str) -> str:
    """xlsxのfill色(RRGGBB/AARRGGBB、または正規化済み色名)を色ファミリへ分類する。
    判定不能は空文字。

    色相(hue)ベースの一般則のみ。特定の答えに合わせた個別色コードは書かない。
    """
    token_raw = str(hex_str or "").strip()
    token_lower = token_raw.lower()
    if token_lower in _NAMED_COLOR_FAMILIES:
        return token_lower
    if token_lower in _NAMED_ACHROMATIC_COLORS:
        return "achromatic"

    token = token_raw.lstrip("#")
    if len(token) == 8:
        token = token[2:]
    if len(token) != 6:
        return ""
    try:
        r, g, b = (int(token[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return ""

    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 12:
        return "achromatic"
    delta = mx - mn
    if mx == r:
        hue = (60 * ((g - b) / delta)) % 360
    elif mx == g:
        hue = 60 * ((b - r) / delta) + 120
    else:
        hue = 60 * ((r - g) / delta) + 240

    if hue < 15 or hue >= 345:
        return "red"
    if hue < 40:
        return "orange"
    if hue < 70:
        return "yellow"
    if hue < 170:
        return "green"
    if hue < 255:
        return "blue"
    if hue < 290:
        return "purple"
    return "pink"


def _schedule_highlight_docs(question: str, rows: list[dict]) -> list[ScoredDocument]:
    """schedule_tasks.jsonlの行データから、質問の色・ファイル名指定に合う
    ハイライト行のコンテキストを作る。"""
    # 色キーワード照合・ファイル名照合の双方に一貫してNFCを渡す
    # （NFD質問だと色キーワード照合が生の文字列比較のため無音で失敗するため）。
    question = unicodedata.normalize("NFC", question)
    candidates = [r for r in rows if r.get("dominant_row_fill")]
    if not candidates:
        return []

    known_names = [r.get("source_path") or r.get("file_name") or "" for r in candidates]
    matched_basenames = set(find_named_files(question, known_names))
    if matched_basenames:
        narrowed = [
            r for r in candidates
            if unicodedata.normalize(
                "NFC", Path(str(r.get("source_path") or r.get("file_name") or "")).name
            ) in matched_basenames
        ]
        if narrowed:
            candidates = narrowed

    # (row, family) を1回だけ算出して以降で使い回す（フィルタ判定とラベル生成の
    # 二重計算を避ける）。
    rows_with_family = [
        (r, _hex_color_family(str(r.get("dominant_row_fill")))) for r in candidates
    ]
    color_names = _requested_color_names(question)
    if color_names:
        rows_with_family = [(r, family) for r, family in rows_with_family if family in color_names]

    docs: list[ScoredDocument] = []
    for r, family in rows_with_family:
        values = r.get("values") or {}
        value_desc = ", ".join(f"{k}={v}" for k, v in values.items() if v not in (None, ""))
        color_label = _COLOR_LABELS.get(family, family or "不明")
        text = "\n".join([
            f"ファイル: {r.get('file_name')} / シート: {r.get('sheet_name')} / 行: {r.get('row_number')}",
            f"行のハイライト色: {color_label}（fill={r.get('dominant_row_fill')}）",
            f"行の値: {value_desc}",
        ])
        docs.append(
            ScoredDocument(
                document=Document(
                    text=text,
                    source_path=Path(str(r.get("source_path") or r.get("file_name") or "")),
                    location=f"sheet_{r.get('sheet_name')}_row_{r.get('row_number')}",
                ),
                score=1.0,
                retrieval_method="structured_spreadsheet_state",
            )
        )
    return docs


_SUPERLATIVE_MAX = ("最も高い", "最も多い", "最大")
_SUPERLATIVE_MIN = ("最も低い", "最も少ない", "最小")


def _pivot_argmax_docs(question: str, cells: list[dict]) -> list[Document]:
    """小型シート（Pivot等）をグリッド化し、質問中の列見出しトークンで対象列を特定して
    argmax/argmin行を返す。列を特定できない・最上級表現が無い場合は何も返さない（保守側）。"""
    want_max = any(k in question for k in _SUPERLATIVE_MAX)
    want_min = any(k in question for k in _SUPERLATIVE_MIN)
    if not (want_max or want_min):
        return []

    by_sheet: dict[tuple[str, str], list[dict]] = {}
    for c in cells:
        by_sheet.setdefault((str(c.get("source_path")), str(c.get("sheet_name"))), []).append(c)

    docs: list[Document] = []
    question_nfc = unicodedata.normalize("NFC", question)
    for (source, sheet_name), sheet_cells in by_sheet.items():
        grid: dict[int, dict[str, Any]] = {}
        for c in sheet_cells:
            grid.setdefault(int(c["row"]), {})[re.sub(r"\d+", "", c["cell"])] = c.get("value")
        rows = sorted(grid)
        if len(rows) < 2:
            continue
        # ヘッダ行 = 非数値の値を2つ以上含む最初の行
        header_row = None
        for r in rows:
            texts = [v for v in grid[r].values() if v is not None and not _is_number(v)]
            if len(texts) >= 2:
                header_row = r
                break
        if header_row is None:
            continue
        headers = grid[header_row]
        data_rows_all = [r for r in rows if r > header_row]
        # 行ラベル列 = 最左から連続する「存在する値の数値が過半でない」列。
        # 最初の「存在する値の数値が過半」の列（=集計値領域の開始）で打ち切る。
        label_cols = _pivot_label_columns(grid, headers, data_rows_all)
        # マージセル由来で空欄になった行ラベルをforward-fillで補完（階層構造を尊重:
        # より左のラベル列に新しい値が現れた行では、それより右の列の引き継ぎを打ち切る）。
        # 集計値の列はfill対象にしない — 値の捏造になるため。
        _forward_fill_label_columns(grid, label_cols, data_rows_all)
        # 質問に現れるトークンを含む列（行ラベル列は除く）
        numeric_cols = [c for c in headers if c not in label_cols]
        # ヘッダをトークン化（例: 「平均 / ALP」→ ["平均","ALP"]）。
        # Pivotの列見出しは「集計関数名 / 変数名」の形が多く、集計関数名（平均・合計・個数等）は
        # 全ての数値列に共通して現れるため判定に使えない。複数列で共有されるトークンは
        # 一般則として除外し、その列だけに現れるトークン（変数名側）でのみ判定する。
        header_tokens = {
            c: [t for t in re.split(r"[\s/／・]+", unicodedata.normalize("NFC", str(headers[c]))) if t]
            for c in numeric_cols
        }
        token_col_count: dict[str, int] = {}
        for toks in header_tokens.values():
            for t in set(toks):
                token_col_count[t] = token_col_count.get(t, 0) + 1
        target_cols = [
            c for c in numeric_cols
            if any(
                len(tok) >= 2 and token_col_count.get(tok, 0) == 1 and tok in question_nfc
                for tok in header_tokens[c]
            )
        ]
        if not target_cols and len(numeric_cols) == 1:
            target_cols = numeric_cols  # 数値列が1つしかなければそれ
        if len(target_cols) != 1:
            continue  # 曖昧なら出さない（誤答よりMissing）
        col = target_cols[0]
        data_rows = [
            r for r in rows if r > header_row and _is_number(grid[r].get(col))
        ]
        if not data_rows:
            continue
        # 階層を1列に畳み込んだcompactレイアウトのpivot対策: 行の同一性（抽出条件）を
        # 表す列 = 集計列以外の全列。集計列は「複数列で共有される集計関数トークン
        # （平均・合計等）を見出しに含む列」＋判定列として一般則で検出する。
        # 同一性タプルがデータ行間で重複する場合、行単独では親階層込みの完全な
        # 抽出条件を復元できない。部分条件の回答はofficial規則「部分一致はIncorrect」で
        # -1になるため出さない（実測valid Q21: 「Human Resources」が親階層違いで重複）。
        aggregate_cols = {
            c for c in numeric_cols
            if any(token_col_count.get(t, 0) >= 2 for t in header_tokens[c])
        } | {col}
        identity_cols = [c for c in sorted(headers) if c not in aggregate_cols]
        identity_tuples = [
            tuple(grid[r].get(c) for c in identity_cols) for r in data_rows
        ]
        if len(set(identity_tuples)) < len(identity_tuples):
            continue
        pick = (max if want_max else min)(data_rows, key=lambda r: float(grid[r][col]))
        lines = [
            f"シート: {sheet_name}（Pivot集計表・xlsxセル値から機械抽出）",
            f"判定列: {headers[col]}",
            "ヘッダ行: " + ", ".join(f"{c}={v}" for c, v in sorted(headers.items())),
            f"{'最大' if want_max else '最小'}の行: "
            + ", ".join(f"{headers.get(c, c)}={grid[pick].get(c)}" for c in sorted(grid[pick])),
        ]
        docs.append(Document(
            text="\n".join(lines), source_path=Path(source),
            location=f"sheet_{sheet_name}_row_{pick}",
        ))
    return docs


def _pivot_cache_aggregate_docs(question: str, aggregates: list[dict]) -> list[Document]:
    question_nfc = unicodedata.normalize("NFC", question)
    if not ("Pivot" in question_nfc or "ピボット" in question_nfc):
        return []
    if not (
        any(term in question_nfc for term in _SUPERLATIVE_MAX)
        or any(term in question_nfc for term in _SUPERLATIVE_MIN)
    ):
        return []

    def matches_data_field(row: dict) -> bool:
        expanded_question = question_nfc
        for value in (row.get("data_field_source"), row.get("data_field_name")):
            token = unicodedata.normalize("NFC", str(value or ""))
            if token and token in expanded_question:
                return True
        return False

    matched = [row for row in aggregates if matches_data_field(row)]
    if not matched and len(aggregates) == 1:
        matched = aggregates
    if not matched:
        return []

    docs: list[Document] = []
    for row in matched:
        source_path = row.get("source_path") or "train.xlsx"
        file_name = row.get("file_name") or Path(str(source_path)).name or "train.xlsx"
        max_labels = _render_label_pairs(row.get("argmax_labels") or {})
        min_labels = _render_label_pairs(row.get("argmin_labels") or {})
        text = "\n".join([
            f"{file_name} の {row.get('sheet_name')}（ピボットテーブル: {row.get('pivot_table_name')}）",
            f"集計: {row.get('data_field_name')}（{row.get('subtotal')}）",
            f"最大のグループ: {max_labels}（値: {row.get('argmax_value')}）",
            f"最小のグループ: {min_labels}（値: {row.get('argmin_value')}）",
        ])
        docs.append(Document(
            text=text,
            source_path=Path(str(source_path)),
            location=f"sheet_{row.get('sheet_name')}_pivot_{row.get('pivot_table_name')}",
        ))
    return docs


def _render_label_pairs(labels: dict) -> str:
    return "、".join(f"{key} = {value}" for key, value in labels.items())


def _pivot_label_columns(
    grid: dict[int, dict[str, Any]], headers: dict[str, Any], data_rows: list[int]
) -> list[str]:
    """Pivot表の行ラベル列（グループキー）を一般則で判定する。
    行ラベルは表の最左から連続して並び、存在する値（非欠損）は非数値または
    カテゴリ的（例: 「0」「0 集計」のようにグループ名＋小計行ラベルが混在）。
    集計値の列は存在する値のほぼ全てが数値になるため、最初の「存在する値の
    数値が過半」の列でラベル領域は終わる。欠損の有無（密度）は分類に使わない —
    欠損セルを含む集計列をラベル列と誤判定してforward-fillで数値を捏造しないため。"""
    label_cols: list[str] = []
    for col in sorted(headers):
        present = [
            grid[r][col] for r in data_rows if grid[r].get(col) not in (None, "")
        ]
        numeric = [v for v in present if _is_number(v)]
        if present and len(numeric) * 2 > len(present):
            break  # 存在する値の数値が過半 = 集計値領域の開始
        label_cols.append(col)
    if not label_cols and headers:
        label_cols = [min(headers)]  # 最低でも最左列はラベルとみなす（従来挙動）
    return label_cols


def _forward_fill_label_columns(
    grid: dict[int, dict[str, Any]], label_cols: list[str], data_rows: list[int]
) -> None:
    """マージセル由来で空欄になった行ラベルを、直前の非空値で補完する（in-place）。
    階層構造を尊重: より左のラベル列に新しい値が現れた行では、それより右の列の
    引き継ぎ値を破棄する（左の親グループが変わったら右の子ラベルは持ち越さない）。"""
    carries: dict[str, Any] = {}
    for r in data_rows:
        for i, col in enumerate(label_cols):
            v = grid[r].get(col)
            if v not in (None, ""):
                carries[col] = v
                for right in label_cols[i + 1:]:
                    carries.pop(right, None)
            elif col in carries:
                grid[r][col] = carries[col]


def _is_number(v: Any) -> bool:
    try:
        float(str(v))
        return True
    except (TypeError, ValueError):
        return False


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
                # 同じシートに独立したハイライト範囲が複数あるため、範囲まで
                # locationへ含める。シート名だけでは末尾のdedupで別範囲が消える。
                location=f"sheet_{block.get('sheet_name')}_range_{block.get('range')}",
            )
            docs.append(ScoredDocument(document=doc, score=1.0, retrieval_method="structured_spreadsheet_state"))
        docs.extend(_schedule_highlight_docs(question, store.schedule_tasks_for(project_name)))

    if _requests_filter_condition(question):
        # train.xlsx（XML直読み系）のフィルタ条件 — 条件そのものが取れるので最優先
        for sheet in store.train_xlsx_sheets_for(project_name):
            if not sheet.get("filter_columns"):
                continue
            doc = Document(
                text=_render_filter_conditions(sheet),
                source_path=Path(sheet["source_path"]),
                location=f"sheet_{sheet.get('sheet_name')}_filter",
            )
            docs.append(ScoredDocument(document=doc, score=1.0, retrieval_method="structured_spreadsheet_state"))

    if question_mentions_spreadsheet(question):
        pivot_docs = _pivot_cache_aggregate_docs(question, store.pivot_aggregates_for(project_name))
        if not pivot_docs:
            pivot_docs = _pivot_argmax_docs(question, store.small_sheet_cells_for(project_name))
        for doc in pivot_docs:
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

    # _schedule_highlight_docs（ハイライト経路）と上の値マッチ経路が同一スケジュール行を
    # 同一locationで二重に出力しうるため、最初の出現を残してdedupする
    # （ハイライト版が先に追加されるため、情報の濃い方が残る）。
    seen_keys: set[tuple[str, str]] = set()
    deduped: list[ScoredDocument] = []
    for doc in docs:
        key = (str(doc.document.source_path), doc.document.location)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(doc)
    return deduped


def _version_diff_tag_matches(tag: str | None, question_lower: str) -> bool:
    """バージョンタグ（v1/v2/old/final等）が質問文に含まれるか。タグ無し（None）は
    「最新版」等の未タグ付き候補を指すため、比較なしで条件成立とみなす。"""
    if not tag:
        return True
    return str(tag).lower() in question_lower


_TITLE_SEPARATOR_RE = re.compile(r"[ _\-.]")


def _normalize_title_token(text: str) -> str:
    """タイトル・ファイル名比較用のゆるい正規化: 区切り文字（_ - . 空白）を除去し
    casefoldする。normalized_titleが「01eda」、実ファイル名/質問文が「01_eda」の
    ような区切り文字違いでも同一視できるようにする。"""
    return _TITLE_SEPARATOR_RE.sub("", unicodedata.normalize("NFC", text)).casefold()


def _narrow_version_diff_pairs(question: str, rows: list[dict]) -> list[dict]:
    """案件内に複数の新旧ペア（提案書のv1/v2/v3等）がある場合に、質問文の
    タイトル・バージョンタグ手がかりで対象ペアを1つに絞る。絞り込んでも複数残る
    場合は誤ったペアで回答するリスクが高いため、何も返さない（保守側）。"""
    ok_rows = [r for r in rows if r.get("status", "ok") == "ok"]
    if not ok_rows:
        return []

    question_nfc = unicodedata.normalize("NFC", question)
    question_title_key = _normalize_title_token(question_nfc)
    by_title = [
        r for r in ok_rows
        if r.get("normalized_title") and _normalize_title_token(r["normalized_title"]) in question_title_key
    ]
    candidates = by_title or ok_rows
    if len(candidates) == 1:
        return candidates

    question_lower = question_nfc.lower()
    tag_matched = [
        r for r in candidates
        if _version_diff_tag_matches(r.get("old_version_tag"), question_lower)
        and _version_diff_tag_matches(r.get("new_version_tag"), question_lower)
    ]
    if len(tag_matched) == 1:
        return tag_matched
    return []


def _render_version_diff_pair(row: dict) -> str:
    old_tag = row.get("old_version_tag") or "(タグなし)"
    new_tag = row.get("new_version_tag") or "(タグなし・最新候補)"
    lines = [
        f"比較対象: {row.get('old_file_name')}（{old_tag}） → {row.get('new_file_name')}（{new_tag}）",
        "以下は機械diffの結果（自動抽出のため見出し番号のずれ等の表面的な差分を含みうる。"
        "案件遂行に関連する実質的な変更かどうかは内容を読んで判断すること）:",
    ]
    added = row.get("added_samples") or []
    removed = row.get("removed_samples") or []
    changed = row.get("changed_samples") or []
    if added:
        lines.append(f"[新版で追加された内容 {row.get('added_count', len(added))}件]")
        lines.extend(f"  + {s}" for s in added)
    if removed:
        lines.append(f"[旧版から削除された内容 {row.get('removed_count', len(removed))}件]")
        lines.extend(f"  - {s}" for s in removed)
    if changed:
        lines.append(f"[変更された内容 {row.get('changed_count', len(changed))}件]")
        for c in changed:
            lines.append(f"  変更前: {c.get('before')}")
            lines.append(f"  変更後: {c.get('after')}")
    if not (added or removed or changed):
        lines.append("(diff上の差分は検出されなかった)")
    return "\n".join(lines)


def build_version_diff_context(
    question: str, project_name: str, store: StructuredArtifactStore
) -> list[ScoredDocument]:
    rows = store.version_diff_pairs_for(project_name)
    matched = _narrow_version_diff_pairs(question, rows)

    docs: list[ScoredDocument] = []
    for row in matched:
        source = row.get("new_path") or row.get("old_path")
        if not source:
            continue
        doc = Document(
            text=_render_version_diff_pair(row),
            source_path=Path(source),
            location=f"version_diff_{row.get('old_version_tag')}_{row.get('new_version_tag')}",
        )
        docs.append(ScoredDocument(document=doc, score=1.0, retrieval_method="structured_version_diff"))
    return docs
