"""質問文を要求能力タグに分類するヒューリスティック。

ベースラインの理論上限スコア見積もり、および構造化回答パスへの
ルーティングに使う。
"""
from __future__ import annotations

IMAGE_KEYWORDS = (".png", ".jpg", "画像", "グラフ", "figure", "マーカー", "折れ線", "図")
VERSION_DIFF_KEYWORDS = (
    "old", "旧版", "新旧", "更新内容", "変更内容", "実質的な変更", "最新版",
    "修正されたもの", "を比較したとき", "変わっている点",
)
PASSWORD_KEYWORDS = ("パスワード", "password", "保護されたファイル")
MULTI_HOP_KEYWORDS = ("すべての案件", "各案件", "複数の案件", "全案件")
SPREADSHEET_STATE_KEYWORDS = (
    "フィルター", "フィルタ", "ピボット", "pivot", "Pivot", "PivotTable",
    ".xlsx", "train.xlsx", "スケジュール", "シート", "タスクID", "セル",
    "ハイライト", "highlight",
)
OFFICE_STYLE_KEYWORDS = (
    "太字", "下線", "イタリック", "強調されている", "マーカーされている",
    ".docx", ".pptx", "スライド", "赤で", "黄色で", "ハイライトされている",
)
# 「の中で」「該当する」のような一般文に頻出する語は入れない（誤ルーティング源になる）
SPREADSHEET_CALC_KEYWORDS = (
    "平均", "合計", "四捨五入", "算出してください", "train.csv", "何人", "何件",
)


def _keyword_spans(text: str, keywords: tuple[str, ...]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    lower = text.lower()
    for keyword in keywords:
        needle = keyword.lower()
        start = 0
        while True:
            index = lower.find(needle, start)
            if index < 0:
                break
            spans.append((index, index + len(needle)))
            start = index + len(needle)
    return spans


def _is_contained(span: tuple[int, int], containers: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(container_start <= start and end <= container_end for container_start, container_end in containers)


def classify_question(question: str) -> list[str]:
    tags: list[str] = []
    lower = question.lower()
    office_style_spans = _keyword_spans(question, OFFICE_STYLE_KEYWORDS)
    image_spans = _keyword_spans(question, IMAGE_KEYWORDS)
    if any(not _is_contained(span, office_style_spans) for span in image_spans):
        tags.append("image_or_graph")
    if any(k in question for k in VERSION_DIFF_KEYWORDS):
        tags.append("version_diff")
    if any(k.lower() in lower for k in PASSWORD_KEYWORDS):
        tags.append("password_protected")
    if any(k in question for k in MULTI_HOP_KEYWORDS):
        tags.append("multi_hop")
    if any(k.lower() in lower for k in SPREADSHEET_STATE_KEYWORDS):
        tags.append("spreadsheet_state")
    if any(k.lower() in lower for k in OFFICE_STYLE_KEYWORDS):
        tags.append("office_style")
    if any(k.lower() in lower for k in SPREADSHEET_CALC_KEYWORDS):
        tags.append("spreadsheet_calc")
    if not tags:
        tags.append("text_only")
    return tags
