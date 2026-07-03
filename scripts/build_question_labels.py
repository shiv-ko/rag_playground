"""Build an initial question label table for data-strategy prioritization."""
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
QA_DIR = ROOT / "data" / "raw" / "share" / "質問回答"
OUT = ROOT / "docs" / "question_labels.csv"


LABEL_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "office_style",
        (
            "ハイライト",
            "太字",
            "下線",
            "イタリック",
            "赤字",
            "赤で強調",
            "黄色",
            "青色",
            "オレンジ",
            "マーカー",
            "コメント",
        ),
    ),
    (
        "spreadsheet_state",
        (
            "train.xlsx",
            "スケジュール",
            "Sheet",
            "シート",
            "Pivot",
            "フィルター",
            "WBS",
            "セル",
            "ヒストグラム",
            "相関係数シート",
        ),
    ),
    (
        "spreadsheet_calc",
        (
            "train.csv",
            "平均",
            "合計",
            "割合",
            "相関",
            "F1",
            "回帰係数",
            "予測値",
            "欠損",
            "行数",
            "四捨五入",
            "切り上げ",
        ),
    ),
    (
        "image_graph",
        (
            "figure",
            ".png",
            "グラフ",
            "ヒートマップ",
            "可視化",
            "y軸",
            "折れ線",
            "目盛り",
        ),
    ),
    (
        "code_static",
        (
            ".py",
            "modeling.py",
            "分析コード",
            "実装設定",
            "コード上",
            "dtype",
            "ユニーク数",
        ),
    ),
    (
        "notebook_output",
        (
            ".ipynb",
            "Notebook",
            "notebook",
            "観察結果サマリ",
        ),
    ),
    (
        "analysis_metrics",
        (
            "metrics.json",
            "leaderboard",
            "最良モデル",
            "モデル比較",
            "Macro F1",
            "Accuracy",
            "selected_columns",
        ),
    ),
    (
        "version_diff",
        (
            "old",
            "旧版",
            "最新版",
            "比較",
            "更新内容",
            "修正",
            "変更内容",
            "変更点",
            "_v1",
            "_v2",
            "_v3",
            "final",
            "_r1",
            "_r2",
        ),
    ),
    (
        "cross_project",
        (
            "全案件",
            "各案件",
            "完了案件",
            "固定金額契約",
            "事後精算案件",
            "最も高い案件",
            "もっとも多くの案件",
            "支払月ごと",
            "契約期間が重なっている案件",
        ),
    ),
    (
        "contract_rule",
        (
            "契約",
            "税込",
            "税抜",
            "請求",
            "見込金額",
            "確定金額",
            "着手金",
            "APR",
            "決裁",
            "RATE",
            "ESTH",
            "ACTH",
            "工数",
        ),
    ),
    (
        "internal_terms",
        (
            "PP",
            "CT",
            "PL",
            "PLAN",
            "FR",
            "MM",
            "APR",
            "FM",
            "TG",
            "EXT",
            "ES",
            "AOBM",
            "AYM",
            "KSS",
            "MINAMINO",
            "AOSHIO",
            "AOMINE",
            "TOTO",
            "京ソ",
            "東都",
            "ひがし丘",
            "略称",
        ),
    ),
    (
        "list_extraction",
        (
            "すべて",
            "全部",
            "挙げて",
            "抽出",
            "抜き出",
            "列",
        ),
    ),
    (
        "numeric_exact",
        (
            "何円",
            "いくら",
            "何日",
            "何歳",
            "何ページ",
            "何週",
            "何時間",
            "何%",
            "小数",
            "整数",
            "計算",
            "算出",
            "差額",
            "総額",
            "合計",
            "平均",
            "割合",
            "F1",
            "Accuracy",
        ),
    ),
]


SOURCE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("00.提案", ("提案", "PP", "調査資料", "市場")),
    ("01.契約", ("契約", "CT")),
    ("02.計画", ("スケジュール", "WBS", "PLAN", "PL", "タスク", "マイルストーン")),
    ("03.データ", ("train.csv", "train.xlsx", "Sheet", "Pivot", "フィルター")),
    ("04.分析", ("metrics.json", "leaderboard", "01_eda", ".ipynb", ".py", "分析コード", "figure", "グラフ", "モデル")),
    ("05.会議", ("会議", "報告資料", "中間報告", "MM", "アクション")),
    ("06.報告書", ("最終報告", "FR")),
    ("社内管理", ("社内管理", "APR", "FM", "座席", "内線", "EXT", "用語")),
    ("cross_project", ("全案件", "各案件", "完了案件", "固定金額契約", "事後精算案件")),
]


PRIMARY_PRIORITY = [
    "version_diff",
    "spreadsheet_state",
    "office_style",
    "cross_project",
    "contract_rule",
    "analysis_metrics",
    "notebook_output",
    "code_static",
    "image_graph",
    "spreadsheet_calc",
    "internal_terms",
    "list_extraction",
    "numeric_exact",
    "single_text",
]


EXTRACTOR_BY_PRIMARY = {
    "version_diff": "version_diff_extractor",
    "spreadsheet_state": "spreadsheet_extractor",
    "office_style": "office_style_extractor",
    "cross_project": "cross_project_registry",
    "contract_rule": "contract_rule_extractor",
    "analysis_metrics": "analysis_registry",
    "notebook_output": "notebook_extractor",
    "code_static": "code_static_extractor",
    "image_graph": "vlm_or_chart_extractor",
    "spreadsheet_calc": "table_calc_engine",
    "internal_terms": "term_registry",
    "list_extraction": "list_extraction_gate",
    "numeric_exact": "numeric_answer_gate",
    "single_text": "text_retriever",
}


def contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def labels_for(question: str) -> list[str]:
    labels = [label for label, needles in LABEL_RULES if contains_any(question, needles)]
    if not labels:
        labels.append("single_text")
    # Some xlsx questions are also exact numeric questions, but spreadsheet_state should
    # remain the primary label. Keep all secondary labels for later filtering.
    return labels


def primary_label(labels: list[str]) -> str:
    for label in PRIMARY_PRIORITY:
        if label in labels:
            return label
    return labels[0]


def source_section(question: str, labels: list[str]) -> str:
    hits = [section for section, needles in SOURCE_RULES if contains_any(question, needles)]
    if "cross_project" in labels:
        return "cross_project"
    if len(hits) == 1:
        return hits[0]
    if hits:
        return ";".join(hits)
    return "unknown"


def answer_shape(question: str, labels: list[str]) -> str:
    if "version_diff" in labels:
        return "diff"
    if "list_extraction" in labels:
        return "list"
    if "numeric_exact" in labels:
        if any(word in question for word in ("円", "税込", "税抜", "金額", "総額", "差額")):
            return "money"
        if any(word in question for word in ("日", "週", "月", "年")):
            return "date_or_duration"
        return "number"
    return "single_text"


def risk_for(labels: list[str], shape: str) -> str:
    high_labels = {
        "version_diff",
        "office_style",
        "spreadsheet_state",
        "cross_project",
        "image_graph",
    }
    if shape in {"list", "diff"}:
        return "high"
    if any(label in high_labels for label in labels):
        return "high"
    if "numeric_exact" in labels or "contract_rule" in labels:
        return "medium"
    return "low"


def load_questions(split: str) -> list[dict[str, str]]:
    filename = f"questions_{split}.csv"
    with (QA_DIR / filename).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    rows: list[dict[str, str]] = []
    for split in ("valid", "test"):
        for row in load_questions(split):
            question = row["question"]
            labels = labels_for(question)
            primary = primary_label(labels)
            shape = answer_shape(question, labels)
            rows.append(
                {
                    "split": split,
                    "index": row["index"],
                    "question": question,
                    "primary_type": primary,
                    "secondary_types": ";".join(label for label in labels if label != primary),
                    "source_section": source_section(question, labels),
                    "answer_shape": shape,
                    "risk": risk_for(labels, shape),
                    "required_extractor": EXTRACTOR_BY_PRIMARY[primary],
                    "notes": "auto_labeled_initial_pass",
                }
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "split",
                "index",
                "question",
                "primary_type",
                "secondary_types",
                "source_section",
                "answer_shape",
                "risk",
                "required_extractor",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {OUT.relative_to(ROOT)} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
