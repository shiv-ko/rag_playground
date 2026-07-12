"""質問文を要求能力タグに分類するヒューリスティック。

ベースラインの理論上限スコア見積もり、および構造化回答パスへの
ルーティングに使う。
"""
from __future__ import annotations

import re

IMAGE_KEYWORDS = (".png", ".jpg", "画像", "グラフ", "figure", "マーカー", "折れ線", "図", "可視化")
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
# Q16型（「M01の日からFR実施までの日数は何日ですか」）: マイルストーンコード
# （M0N等。日本語の\bはUnicode文字境界で機能しないため非英数字境界で判定する）と
# 日数を問う言い回しが共起する質問。
_MS_CODE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])M\d{2}(?![A-Za-z0-9])")
MS_DATE_DURATION_KEYWORDS = ("日数", "何日")
# Q15型（「中間報告会または中間レビューが2025年7月1日以前に実施された案件を、
# 主略称ですべて挙げてください」）: マイルストーンの業務イベント語＋しきい値日付＋
# 前後方向＋案件列挙の組み合わせが揃う質問。
MS_DATE_EVENT_KEYWORDS = ("キックオフ", "中間報告", "中間レビュー", "最終報告", "最終レビュー", "検収")
MS_DATE_DIRECTION_KEYWORDS = ("以前", "以降")
_MS_DATE_TOKEN_RE = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日")
CONTRACT_RULE_KEYWORDS = (
    "契約金額", "契約期間", "見込税込", "最終請求", "実績工数", "想定総工数",
    "時間単価", "APR-M", "固定金額契約", "固定価格", "事後精算", "ACTH",
)
# 全案件横断の契約集計問い（cross_project block）。「消費税額の総額」等は質問の構造パターン
# （何を横断集計するか）へのマッチであり、特定の質問文そのものへの分岐ではない。
CROSS_PROJECT_KEYWORDS = (
    "消費税額の総額", "支払月", "精算総額", "提案時金額", "FR時",
)
ANALYSIS_JSON_KEYWORDS = ("metrics.json", "selected_columns", "model_params", "max_depth")
ANALYSIS_CODE_KEYWORDS = (
    "modeling.py", "分析コード", "sparse_output", "n_estimators", "nunique",
    "one-hot encoding", "one hot encoding",
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
    if _MS_CODE_TOKEN_RE.search(question) and any(k in question for k in MS_DATE_DURATION_KEYWORDS):
        tags.append("ms_date_duration")
    if (
        any(k in question for k in MS_DATE_EVENT_KEYWORDS)
        and any(k in question for k in MS_DATE_DIRECTION_KEYWORDS)
        and _MS_DATE_TOKEN_RE.search(question)
        and "案件" in question
    ):
        tags.append("ms_date_cross_project_list")
    if any(k in question for k in CONTRACT_RULE_KEYWORDS):
        tags.append("contract_rule")
    if any(k in question for k in CROSS_PROJECT_KEYWORDS):
        tags.append("cross_project")
    if any(k.lower() in lower for k in ANALYSIS_JSON_KEYWORDS):
        tags.append("analysis_json")
    if any(k.lower() in lower for k in ANALYSIS_CODE_KEYWORDS):
        tags.append("analysis_code")
    if ".ipynb" in lower:
        tags.append("analysis_notebook")
    if "f1" in lower and "accuracy" in lower and ("次ぐ" in question or "順位" in question):
        tags.append("analysis_report")
    if not tags:
        tags.append("text_only")
    return tags
