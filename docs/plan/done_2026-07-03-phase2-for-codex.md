# Phase 2（構造化資産の接続: Excel/Office系39問） Codex実装計画

> **実行者向け:** これはCodex CLI（またはこのリポジトリで作業する別のAIコーディングエージェント）にそのまま渡す自己完結型のタスク指示書です。superpowers系のスキルには依存しません。タスクは**上から順番に**実行し、各タスクの最後で `.venv/bin/pytest tests/ -v` を実行して**全件PASS**することを確認してからコミットしてください。1タスク＝1コミット。疑問点があれば実装を進める前に確認すること（推測でコードを変えない）。

**Goal:** `docs/plan/plan_0703.md` Phase 2「構造化資産の接続」を実装する。`spreadsheet_state`（21問）・`office_style`（9問）・`spreadsheet_calc`（9問）の計39問を、既存の構造化抽出artifacts（`artifacts/*.jsonl`、実データから機械的に生成済み）を使った専用回答パスで処理する。本コンペ最大の単一投資領域。

**Architecture:** 質問タイプ別の専用「構造化コンテキストビルダー」を新設し、通常のBM25検索（`ProjectScopedRetriever.search`）の代わりに、構造化artifactsから関連レコードを抽出して`ScoredDocument`化する。これを既存の`AnswerGenerator.generate()`にそのまま渡すことで、Phase 1で作ったタイプ別ゲート・引用実在チェック・「わかりません」矛盾検出をすべて再利用する（車輪の再発明をしない）。`spreadsheet_calc`（数値集計）だけは例外で、LLMに自由記述させず「フィルタ条件＋集計方法」をJSON構造で出させ、決定的なpandas処理で計算する専用パスにする（LLMは算術が信頼できないため。コード生成→サンドボックス実行ではなく、構造化スペック→決定的実行にすることでサンドボックスが不要になり安全性も上がる — これは`plan_0703.md`原案からの意図的な改善）。

**Tech Stack:** Python 3.11+ (`.venv/bin/python`), pytest, pandas（`spreadsheet_calc`用、`pyproject.toml`の`parsers`/`search` extrasに無ければ追加）, 既存のFakeサブクラスパターン。

## 前提（重要・着手前に必ず確認）

1. **本計画は Phase 1（`docs/plan/2026-07-03-phase1-for-codex.md`）が `main` にマージ済みであることを前提にします。** `Pipeline._process_one` / `AnswerGenerator.generate` / `ConfidenceGate` はPhase 1で変更されている前提でコード例を書いています。`git log`で確認し、もしまだマージされていなければ、先にPhase 1を完了させるか、少なくとも該当ファイルの現状を読んでから本計画のコード例を実際のコードに合わせて調整してください。
2. **`artifacts/*.jsonl` は「実行時にプログラムで実データを読んで生成された」ファイルであり、`data/raw`が変わったら再生成が必要です。** 本計画のコードはこれらのartifactsを**静的ファイルとして読み込む**設計です（`artifacts/project_registry.json`をPhase 1で読み込んだのと同じパターン）。新しい案件データが来た場合の再生成手順は次の4スクリプトを順に実行することです（このタスクでは変更しない。既に汎用的〈特定案件名のハードコードなし〉であることをPhase 2計画作成時に確認済み）:
   ```bash
   .venv/bin/python scripts/extract_spreadsheets.py
   .venv/bin/python scripts/scan_train_xlsx_xml.py
   .venv/bin/python scripts/build_train_xlsx_highlight_context.py
   .venv/bin/python scripts/extract_office_marks.py
   ```
   Task 8でこの手順をREADME相当の場所に明記します。
3. **既知の技術的負債（本計画のスコープ外・触らないこと）:** `scripts/analyze_spreadsheet_coverage.py`に`build_registries.py`修正前と同種の案件名→略称のハードコード辞書が残っている（分析専用スクリプトで回答生成には使われていないため実害はないが要修正）。`scripts/build_schedule_query_candidates.py`は特定の質問番号（valid 20, test 41, test 89, test 90, test 94）ごとに手書きの抽出条件を書いた調査用スクリプトで、出力は`docs/schedule_query_candidates.md`のみ・回答生成パスからは一切参照されていない（確認済み）。**この2ファイルを本計画のタスクで参考にする場合、個別の質問番号やプロジェクト名への分岐ではなく、そこで使われている一般的なテクニック（「フェーズ名でタスクを絞る」「担当者名でタスクを絞る」等）だけを一般化して抽出すること。** 削除するかどうかは別途人間の判断を仰ぐこと（本計画では触らない）。
4. 着手前に `.venv/bin/pytest tests/ -v` を実行し、全件PASSすることを確認する。

## Global Constraints

- **回答は1000トークン以内**（`CLAUDE.md`）。`MAX_CHARS_APPROX`のtruncationロジックは維持する。
- **ハードコード禁止**（`competition.md`）: 特定の案件名・ファイル名・質問文をキーにした分岐を書かない。列挙・フィルタ・集計のロジックは「質問文からLLMまたは汎用ヒューリスティックで条件を抽出し、任意のプロジェクト・任意のシート・任意の列に対して同じロジックで動く」形にする。
- テストは決定的にする: LLM呼び出しは`_call_llm()`をサブクラスでオーバーライドして排除する。
- すべてのテスト実行は `.venv/bin/pytest tests/ -v`。各タスク完了時点で全件PASSを維持すること。
- **列挙系設問の安全側原則**: CRAGでは部分一致がすべてIncorrect（`Acceptable`が使えない、最も危険なカテゴリ）。全要素を抽出できたと機械的に確認できない場合は、無理に列挙せずMissingにする（Task 6のゲートが必須）。
- コミットメッセージは変更内容の要約を日本語で。Co-Authored-Byトレーラーは使用ツール自身の規約に従う。

## 前提となる既存コードの事実（実装者向け）

### artifacts のスキーマ（実データから生成済み、`artifacts/`配下）

- **`highlight_cells.jsonl`** / **`spreadsheet_cells.jsonl`**（同一スキーマ、`scripts/extract_spreadsheets.py`生成）: 1行1セル。キー: `source_path, project_name, section, file_name, sheet_name, cell, row, column, value, formula, number_format, fill_color(hex), fill_color_name(意味づけ済み: "yellow"/"white"/"black"等またはhex), font_color, font_color_name, bold, italic, underline`。全セルが入っている（ハイライトの有無で絞り込みは呼び出し側の責務）。
- **`spreadsheet_sheets.jsonl`**: 1行1シート。キー: `source_path, project_name, section, file_name, sheet_name, max_row, max_column, auto_filter_ref(フィルタ範囲、無ければnull), freeze_panes, merged_ranges, hidden_rows, hidden_columns`。**`auto_filter_ref`が非nullならフィルタ条件が設定されているシート**（ただし具体的な絞り込み条件〈どの列がどの値でフィルタされているか〉はopenpyxlのAutoFilter APIからは値までは取れないことが多いので、実際の抽出条件は「フィルタ範囲の列ヘッダ＋非表示行との差分」から推定する必要がある。Task 4で詳述）。
- **`schedule_tasks.jsonl`**: 1行1タスク行（スケジュール表のヘッダ行から下の各行）。キー: `source_path, project_name, section, file_name, sheet_name, header_row, row_number, row_fill_colors, dominant_row_fill, values(dict: ヘッダ列名→値。列名はプロジェクトごとに違いうる。例: "タスクID","フェーズNo.","フェーズ名","タスク名","詳細・補足","担当者","開始日","終了日","日数","依存タスク","成果物","ステータス","CP","備考")`。
- **`office_marks.jsonl`**（`scripts/extract_office_marks.py`生成）: 1行1テキストrun（pptxのslide内テキスト、docxの段落・表内テキスト）。キー: `source_path, project_name, section, file_name, extension, unit_type("slide_run"/"paragraph_run"/"table_run"), slide_number/paragraph_index等, run_index, text, bold, italic, underline, font_color(hex or null), fill_color(hex or null)`。docxのみ`highlight`相当のキーが別途あるかスキーマを実際に`head`で確認すること（`docx_highlight()`は`run.font.highlight_color`の`str()`、`"WD_COLOR_INDEX.YELLOW (7)"`のような文字列になるので、色名を取るには`.`区切りの2番目のトークンをさらに`(`で分割するなどのパースが必要）。
- **`train_xlsx_sheets.jsonl` / `train_xlsx_highlights.jsonl` / `train_xlsx_highlight_blocks.jsonl` / `train_xlsx_highlight_context.jsonl` / `train_xlsx_formula_cells.jsonl`**（`train.xlsx`はzipとして壊れているファイルが多く、`scripts/scan_train_xlsx_xml.py`でXMLレベルから直接スキャンして生成）:
  - `train_xlsx_sheets.jsonl`: シートメタ（`drawing_count`>0ならグラフあり、`sheet_name`が"Pivot"ならピボット表）。
  - `train_xlsx_highlights.jsonl`: ハイライトされた個別セル（`cell, value, fill_rgb, fill_color_name`）。
  - `train_xlsx_highlight_blocks.jsonl`: 隣接するハイライトセルをブロック化し、`column_header`（そのブロックが属する列の見出しセル）・`same_col_headers`（同じ列の他の値）・`same_row_values`（同じ行の他の値）まで付けたもの。**列挙・集計の抽出条件を答える設問はこれが主要データ源。**
  - `train_xlsx_highlight_context.jsonl`: `_blocks`とほぼ同内容だが`nearby_window`（周辺セルの2次元窓）も持つ、より広い文脈。
  - `train_xlsx_formula_cells.jsonl`: 数式付きセル（`formula`キーに数式文字列）。
- **`spreadsheet_question_coverage.csv` / `office_style_coverage.csv` / `excel_question_coverage.csv`**: 人手が付けた`question_labels.csv`と突き合わせた「現状のartifactsでどこまで答えられそうか」の**分析専用**CSV（`coverage_status`列: `covered_artifact` / `partial` / `not_covered`）。**回答生成コードから読み込んではいけない**（`question_labels.csv`由来のため）。本計画作成時の参考情報としてのみ使った: `excel_question_coverage.csv`は17 covered / 8 partial / 23 not_covered（計48行、`spreadsheet_state`/`spreadsheet_calc`/一部`image_graph`/`notebook_output`を含む）。`office_style_coverage.csv`は9 covered_artifact / 3 not_covered（not_coveredはページ番号系でPDF/DOCXレイアウト解析が必要、本計画のスコープ外）。

### 既存コードの拡張ポイント

- `classify_question(question: str) -> list[str]`（`src/utils/question_classifier.py`）: キーワード部分一致でタグ付けする小さい関数。既存タグ: `image_or_graph, version_diff, password_protected, multi_hop, text_only`。Task 1で`spreadsheet_state, office_style, spreadsheet_calc`を追加する。
- `AnswerGenerator.generate(question: str, contexts: list[ScoredDocument]) -> Answer`（`src/generator/answer_generator.py`、Phase 1後）: `contexts`の出どころは検索結果でなくてもよい。**Task 3・4はこの関数のシグネチャを変えず、`contexts`に構造化データから作った`ScoredDocument`を渡すだけで済む設計にする。**
- `Pipeline._process_one(qa: QAPair) -> PipelineResult`（`src/orchestrator/pipeline.py`、Phase 1後は`search_query = self.query_expander.expand_terms(qa.question)`→`contexts = self.retriever.search(search_query, ...)`→`self.generator.generate(qa.question, contexts)`の順）。Task 7でタイプ別分岐を追加する。
- `ScoredDocument(document: Document, score: float, retrieval_method: str = "")` / `Document(text: str, source_path: Path, metadata: dict = {}, location: str = "")`（`src/models.py`）: 構造化データから合成する際は`source_path`に元のExcel/pptxファイルパス、`location`にシート名やスライド番号相当の文字列を入れる（`_build_context`が`(ファイル名 / location)`の形で表示するため）。

---

### Task 1: 質問タイプの拡張分類（spreadsheet_state / office_style / spreadsheet_calc）

**目的:** 質問文だけから（人手ラベルを使わず）構造化パスへ振り分けるべき質問を機械的にタグ付けする。

**Files:**
- Modify: `src/utils/question_classifier.py`
- Modify: `tests/test_question_classifier.py`

**Interfaces:**
- Produces: `classify_question`が返すタグに`"spreadsheet_state"`, `"office_style"`, `"spreadsheet_calc"`が追加される。Task 7の`Pipeline._process_one`がこのタグを消費する。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_question_classifier.py` に追記:

```python
def test_detects_spreadsheet_state_question():
    assert "spreadsheet_state" in classify_question(
        "東都人材プラットフォームのtrain.xlsxにおいて、trainシートでフィルターで抽出されている条件を教えてください。"
    )
    assert "spreadsheet_state" in classify_question(
        "AOSHIOのM02資料（docx）において、黄色でハイライトされている部分をすべて抜き出してください。"
    )
    assert "spreadsheet_state" in classify_question(
        "青葉与信マネジメントのPLにおいて、探索的分析・仮説整理フェーズに一致するタスクIDをすべて挙げてください。"
    )


def test_detects_office_style_question():
    assert "office_style" in classify_question(
        "恒一会 かえで総合病院の契約書において、太字で記載されている箇所のうち、日付以外のものをすべて抽出してください。"
    )
    assert "office_style" in classify_question(
        "東都人材プラットフォームの提案書P7において、赤で強調されている箇所の文字列を抜き出してください。"
    )


def test_detects_spreadsheet_calc_question():
    assert "spreadsheet_calc" in classify_question(
        "青葉与信マネジメントの分析対象データにおいて、term=3 years、grade=B1、purpose=credit_cardに該当するloan_amntの平均を算出してください。四捨五入して整数値で出してください。"
    )
    assert "spreadsheet_calc" in classify_question(
        "恒一会 かえで総合病院のプロジェクトデータ（train.csv）において、disease=1の女性の中で、ALT_GPTの平均値が最も高い年齢は何歳ですか。"
    )


def test_question_can_have_both_spreadsheet_state_and_highlight_style_tags():
    """xlsxのハイライト条件はspreadsheet_state、docx/pptxのハイライトはoffice_style。
    どちらもキーワード的には「ハイライト」を含みうるため両方付いてもよい
    （ルーティング側でretrieved先の拡張子を見て最終判定する。Task 7参照）。"""
    tags = classify_question("提案書.pptxで黄色ハイライトされている数値を抜き出してください。")
    assert "office_style" in tags
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_question_classifier.py -v`
Expected: 新規4テストがFAIL（`AssertionError`、タグが返らない）

- [ ] **Step 3: 実装**

`src/utils/question_classifier.py` を次の内容に置換:

```python
"""質問文を要求能力タグに分類するヒューリスティック。ベースラインの理論上限スコア見積もり、
および構造化回答パス（spreadsheet_state/office_style/spreadsheet_calc）へのルーティングに使う。
"""
from __future__ import annotations

IMAGE_KEYWORDS = (".png", ".jpg", "画像", "グラフ", "figure", "マーカー", "折れ線", "図")
VERSION_DIFF_KEYWORDS = ("old", "旧版", "新旧", "更新内容", "実質的な変更", "最新版")
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
SPREADSHEET_CALC_KEYWORDS = (
    "平均", "合計", "四捨五入", "算出してください", "train.csv", "何人", "何件",
    "の中で", "該当する",
)


def classify_question(question: str) -> list[str]:
    tags: list[str] = []
    lower = question.lower()
    if any(k.lower() in lower for k in IMAGE_KEYWORDS):
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
```

（既存の`image_or_graph`等のロジックはそのまま。新規3タグを末尾に追加しただけ。`text_only`が「他に何も無い場合のみ」なのは既存動作を維持している。）

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_question_classifier.py -v`
Expected: 全件PASS

- [ ] **Step 5: 全テスト実行＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/utils/question_classifier.py tests/test_question_classifier.py
git commit -m "Phase2 Task1: 質問分類にspreadsheet_state/office_style/spreadsheet_calcタグを追加"
```

---

### Task 2: 構造化artifactsのロード層

**目的:** `artifacts/*.jsonl`を読み込み、案件名・シート名で高速に絞り込めるようにする。以降のTask 3〜5が共通で使うデータアクセス層。

**Files:**
- Create: `src/structured/__init__.py`
- Create: `src/structured/artifact_store.py`
- Create: `tests/test_artifact_store.py`

**Interfaces:**
- Produces: `StructuredArtifactStore.from_artifacts_dir(artifacts_dir: Path) -> StructuredArtifactStore`。メソッド: `highlight_cells_for(project_name: str) -> list[dict]`, `schedule_tasks_for(project_name: str) -> list[dict]`, `office_marks_for(project_name: str) -> list[dict]`, `train_xlsx_highlight_blocks_for(project_name: str) -> list[dict]`, `train_xlsx_sheets_for(project_name: str) -> list[dict]`, `spreadsheet_sheets_for(project_name: str) -> list[dict]`。全メソッド、該当データが無ければ空リストを返す（例外を投げない）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_artifact_store.py`:

```python
"""StructuredArtifactStore のテスト。実artifactsではなく合成jsonlで検証する。"""
from __future__ import annotations

import json
from pathlib import Path

from src.structured.artifact_store import StructuredArtifactStore


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


def test_loads_and_filters_highlight_cells(tmp_path: Path):
    _write_jsonl(tmp_path / "highlight_cells.jsonl", [
        {"project_name": "A社", "cell": "A1", "fill_color_name": "yellow"},
        {"project_name": "B社", "cell": "B1", "fill_color_name": "white"},
    ])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    rows = store.highlight_cells_for("A社")
    assert len(rows) == 1
    assert rows[0]["cell"] == "A1"


def test_missing_artifact_file_returns_empty_list(tmp_path: Path):
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    assert store.highlight_cells_for("A社") == []
    assert store.schedule_tasks_for("A社") == []
    assert store.office_marks_for("A社") == []
    assert store.train_xlsx_highlight_blocks_for("A社") == []
    assert store.train_xlsx_sheets_for("A社") == []
    assert store.spreadsheet_sheets_for("A社") == []


def test_unknown_project_returns_empty_list(tmp_path: Path):
    _write_jsonl(tmp_path / "schedule_tasks.jsonl", [
        {"project_name": "A社", "values": {"タスクID": "T01"}},
    ])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    assert store.schedule_tasks_for("存在しない案件") == []


def test_all_seven_artifact_kinds_load_from_their_own_files(tmp_path: Path):
    _write_jsonl(tmp_path / "schedule_tasks.jsonl", [{"project_name": "A社", "x": 1}])
    _write_jsonl(tmp_path / "office_marks.jsonl", [{"project_name": "A社", "x": 2}])
    _write_jsonl(tmp_path / "train_xlsx_highlight_blocks.jsonl", [{"project_name": "A社", "x": 3}])
    _write_jsonl(tmp_path / "train_xlsx_sheets.jsonl", [{"project_name": "A社", "x": 4}])
    _write_jsonl(tmp_path / "spreadsheet_sheets.jsonl", [{"project_name": "A社", "x": 5}])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    assert store.schedule_tasks_for("A社")[0]["x"] == 1
    assert store.office_marks_for("A社")[0]["x"] == 2
    assert store.train_xlsx_highlight_blocks_for("A社")[0]["x"] == 3
    assert store.train_xlsx_sheets_for("A社")[0]["x"] == 4
    assert store.spreadsheet_sheets_for("A社")[0]["x"] == 5
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_artifact_store.py -v`
Expected: FAIL — `No module named 'src.structured'`

- [ ] **Step 3: 実装**

`src/structured/__init__.py`: 空ファイル。

`src/structured/artifact_store.py`:

```python
"""artifacts/配下の構造化jsonlを読み込み、案件名で絞り込めるようにする。

Phase 2の各構造化回答パス（spreadsheet_state / office_style / spreadsheet_calc）
が共通で使うデータアクセス層。artifactsは scripts/extract_spreadsheets.py 等が
実データから実行時に生成する（このモジュールは中身を解釈しない、素通しする）。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

_ARTIFACT_FILES = {
    "highlight_cells": "highlight_cells.jsonl",
    "schedule_tasks": "schedule_tasks.jsonl",
    "office_marks": "office_marks.jsonl",
    "train_xlsx_highlight_blocks": "train_xlsx_highlight_blocks.jsonl",
    "train_xlsx_sheets": "train_xlsx_sheets.jsonl",
    "spreadsheet_sheets": "spreadsheet_sheets.jsonl",
}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


class StructuredArtifactStore:
    def __init__(self, by_kind_and_project: dict[str, dict[str, list[dict]]]) -> None:
        self._data = by_kind_and_project

    @classmethod
    def from_artifacts_dir(cls, artifacts_dir: Path) -> "StructuredArtifactStore":
        by_kind_and_project: dict[str, dict[str, list[dict]]] = {}
        for kind, filename in _ARTIFACT_FILES.items():
            by_project: dict[str, list[dict]] = defaultdict(list)
            for row in _load_jsonl(artifacts_dir / filename):
                by_project[row.get("project_name", "")].append(row)
            by_kind_and_project[kind] = by_project
        return cls(by_kind_and_project)

    def _get(self, kind: str, project_name: str) -> list[dict]:
        return self._data.get(kind, {}).get(project_name, [])

    def highlight_cells_for(self, project_name: str) -> list[dict]:
        return self._get("highlight_cells", project_name)

    def schedule_tasks_for(self, project_name: str) -> list[dict]:
        return self._get("schedule_tasks", project_name)

    def office_marks_for(self, project_name: str) -> list[dict]:
        return self._get("office_marks", project_name)

    def train_xlsx_highlight_blocks_for(self, project_name: str) -> list[dict]:
        return self._get("train_xlsx_highlight_blocks", project_name)

    def train_xlsx_sheets_for(self, project_name: str) -> list[dict]:
        return self._get("train_xlsx_sheets", project_name)

    def spreadsheet_sheets_for(self, project_name: str) -> list[dict]:
        return self._get("spreadsheet_sheets", project_name)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_artifact_store.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 実データで動作確認**

```bash
.venv/bin/python -c "
from pathlib import Path
from src.structured.artifact_store import StructuredArtifactStore
store = StructuredArtifactStore.from_artifacts_dir(Path('artifacts'))
print(len(store.highlight_cells_for('京橋信用ソリューションズ株式会社')))
print(len(store.schedule_tasks_for('京橋信用ソリューションズ株式会社')))
"
```

Expected: 0件でないこと（京橋信用ソリューションズのスケジュール.xlsxは実データに存在するため）。

- [ ] **Step 6: 全テスト＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/structured/ tests/test_artifact_store.py
git commit -m "Phase2 Task2: 構造化artifactsのロード層（案件名で絞り込み）"
```

---

### Task 3: office_styleパス（太字・下線・イタリック・色による列挙）

**目的:** 「太字/下線/イタリック/特定の色で強調されている箇所をすべて抜き出せ」系の質問に、`office_marks.jsonl`から該当runを列挙して回答する。既存の`AnswerGenerator.generate()`にそのまま渡すことでPhase 1のゲート・引用チェックを再利用する。

**Files:**
- Create: `src/generator/color_names.py`
- Create: `src/retriever/structured_context.py`（このタスクでは`build_office_style_context`のみ実装。Task 4で同ファイルに追記）
- Create: `tests/test_color_names.py`
- Create: `tests/test_structured_context.py`

**Interfaces:**
- Consumes: `StructuredArtifactStore.office_marks_for(project_name) -> list[dict]`（Task 2）
- Produces: `nearest_basic_color_name(hex_color: str) -> str`。`build_office_style_context(question: str, project_name: str, store: StructuredArtifactStore) -> list[ScoredDocument]`。Task 7がこれを`retriever.search`の代わりに呼ぶ。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_color_names.py`:

```python
"""RGB16進数から基本色名への変換（一般的な最近傍色名マッチング。案件依存ではない）。"""
from __future__ import annotations

from src.generator.color_names import nearest_basic_color_name


def test_pure_red_is_red():
    assert nearest_basic_color_name("FF0000") == "red"


def test_pure_yellow_is_yellow():
    assert nearest_basic_color_name("FFFF00") == "yellow"


def test_pure_black_is_black():
    assert nearest_basic_color_name("000000") == "black"


def test_pure_white_is_white():
    assert nearest_basic_color_name("FFFFFF") == "white"


def test_dark_red_maroon_is_red():
    assert nearest_basic_color_name("8B2500") == "red"


def test_none_returns_none_name():
    assert nearest_basic_color_name(None) == "none"
```

`tests/test_structured_context.py`:

```python
"""構造化コンテキストビルダーのテスト。ScoredDocumentへの変換ロジックを検証する。"""
from __future__ import annotations

from src.retriever.structured_context import build_office_style_context
from src.structured.artifact_store import StructuredArtifactStore


def _store_with_marks(marks: list[dict]) -> StructuredArtifactStore:
    return StructuredArtifactStore({"office_marks": {"A社": marks}, "highlight_cells": {}, "schedule_tasks": {}, "train_xlsx_highlight_blocks": {}, "train_xlsx_sheets": {}, "spreadsheet_sheets": {}})


def test_bold_question_selects_only_bold_runs():
    store = _store_with_marks([
        {"source_path": "x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 1, "text": "太字の見出し", "bold": True, "italic": False, "underline": False, "font_color": None, "fill_color": None},
        {"source_path": "x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 1, "text": "普通の本文", "bold": False, "italic": False, "underline": False, "font_color": None, "fill_color": None},
    ])
    docs = build_office_style_context("太字で記載されている箇所をすべて抽出してください。", "A社", store)
    texts = [d.document.text for d in docs]
    assert any("太字の見出し" in t for t in texts)
    assert not any("普通の本文" in t for t in texts)


def test_red_question_selects_red_font_color():
    store = _store_with_marks([
        {"source_path": "x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 1, "text": "赤字の警告文", "bold": False, "italic": False, "underline": False, "font_color": "8B2500", "fill_color": None},
        {"source_path": "x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 1, "text": "黒字の本文", "bold": False, "italic": False, "underline": False, "font_color": "1A1A1A", "fill_color": None},
    ])
    docs = build_office_style_context("赤で強調されている箇所の文字列を抜き出してください。", "A社", store)
    texts = [d.document.text for d in docs]
    assert any("赤字の警告文" in t for t in texts)
    assert not any("黒字の本文" in t for t in texts)


def test_no_matching_marks_returns_empty_list():
    store = _store_with_marks([])
    docs = build_office_style_context("太字で記載されている箇所をすべて抽出してください。", "A社", store)
    assert docs == []


def test_scored_document_has_source_path_and_location():
    store = _store_with_marks([
        {"source_path": "data/raw/x/提案書.pptx", "file_name": "提案書.pptx", "slide_number": 3, "text": "太字テキスト", "bold": True, "italic": False, "underline": False, "font_color": None, "fill_color": None},
    ])
    docs = build_office_style_context("太字の箇所を抽出してください。", "A社", store)
    assert len(docs) == 1
    assert str(docs[0].document.source_path) == "data/raw/x/提案書.pptx"
    assert docs[0].document.location == "slide_3"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_color_names.py tests/test_structured_context.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 実装**

`src/generator/color_names.py`:

```python
"""RGB16進数コードを基本色名に変換する（一般的な最近傍マッチング。特定案件のデータに依存しない）。

office_marks.jsonl等は生のRGB16進数しか持たないため、「赤で強調」のような質問に
答えるには色名への変換が必要。CSS拡張色名のような固定パレットに対するユークリッド距離
最近傍探索で、どんな案件のどんな配色にも同じロジックで対応できる。
"""
from __future__ import annotations

_BASIC_PALETTE: dict[str, tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "orange": (255, 165, 0),
    "yellow": (255, 255, 0),
    "green": (0, 128, 0),
    "cyan": (0, 255, 255),
    "blue": (0, 0, 255),
    "purple": (128, 0, 128),
    "pink": (255, 192, 203),
    "brown": (139, 69, 19),
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (128, 128, 128),
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def nearest_basic_color_name(hex_color: str | None) -> str:
    if not hex_color or len(hex_color) < 6:
        return "none"
    try:
        r, g, b = _hex_to_rgb(hex_color)
    except ValueError:
        return "none"
    best_name = "none"
    best_dist = float("inf")
    for name, (pr, pg, pb) in _BASIC_PALETTE.items():
        dist = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name
```

`src/retriever/structured_context.py`:

```python
"""質問タイプ別の構造化コンテキストビルダー。

BM25検索(ProjectScopedRetriever.search)の代わりに、構造化artifactsから
関連レコードを抽出してScoredDocument化する。既存のAnswerGenerator.generate()に
そのまま渡せる形にすることで、Phase 1のタイプ別ゲート・引用チェックを再利用する。
"""
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
    return [attr for attr, keywords in _STYLE_KEYWORD_MAP.items() if any(k in question for k in keywords)]


def _requested_color_names(question: str) -> list[str]:
    return [name for name, keywords in _COLOR_KEYWORD_MAP.items() if any(k in question for k in keywords)]


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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_color_names.py tests/test_structured_context.py -v`
Expected: 全件PASS

- [ ] **Step 5: 全テスト＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/generator/color_names.py src/retriever/structured_context.py tests/test_color_names.py tests/test_structured_context.py
git commit -m "Phase2 Task3: office_styleパス（太字・下線・イタリック・色による列挙）"
```

---

### Task 4: spreadsheet_stateパス（ハイライト条件・フィルタ条件・タスク列挙）

**目的:** 「xlsxで黄色ハイライトされているセルの抽出条件と集計内容」「フィルタ条件」「特定フェーズ/担当者のタスクID一覧」系の質問に、`highlight_cells.jsonl` / `train_xlsx_highlight_blocks.jsonl` / `schedule_tasks.jsonl` / `spreadsheet_sheets.jsonl`から回答する。

**Files:**
- Modify: `src/retriever/structured_context.py`（`build_spreadsheet_state_context`を追記）
- Modify: `tests/test_structured_context.py`

**Interfaces:**
- Consumes: `StructuredArtifactStore`の各`*_for()`メソッド（Task 2）、`nearest_basic_color_name`（Task 3）
- Produces: `build_spreadsheet_state_context(question: str, project_name: str, store: StructuredArtifactStore) -> list[ScoredDocument]`。Task 7が消費する。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_structured_context.py` に追記（importに`build_spreadsheet_state_context`を追加）:

```python
def _full_store(**kinds) -> StructuredArtifactStore:
    base = {"office_marks": {}, "highlight_cells": {}, "schedule_tasks": {}, "train_xlsx_highlight_blocks": {}, "train_xlsx_sheets": {}, "spreadsheet_sheets": {}}
    base.update(kinds)
    return StructuredArtifactStore(base)


class TestSpreadsheetStateContext:
    def test_highlight_question_uses_train_xlsx_highlight_blocks(self):
        store = _full_store(train_xlsx_highlight_blocks={"A社": [
            {
                "source_path": "data/raw/x/train.xlsx", "sheet_name": "Pivot", "range": "F22",
                "fill_color_name": "yellow", "first_value": "35.95",
                "column_header": {"cell": "F3", "value": "平均 / bmi", "formula": None},
                "same_row_values": [{"cell": "E22", "value": "39", "formula": None}],
            }
        ]})
        docs = build_spreadsheet_state_context(
            "train.xlsxのPivotシートで黄色ハイライトされているセルの抽出条件を教えてください。", "A社", store
        )
        assert len(docs) == 1
        assert "平均 / bmi" in docs[0].document.text
        assert "35.95" in docs[0].document.text

    def test_filter_question_uses_spreadsheet_sheets_auto_filter(self):
        store = _full_store(spreadsheet_sheets={"A社": [
            {"source_path": "data/raw/x/train.xlsx", "sheet_name": "train", "auto_filter_ref": "A1:N31", "hidden_rows": [5, 6, 7]},
        ]}, highlight_cells={"A社": [
            {"source_path": "data/raw/x/train.xlsx", "sheet_name": "train", "cell": "A1", "row": 1, "column": 1, "value": "ステータス"},
        ]})
        docs = build_spreadsheet_state_context(
            "train.xlsxのtrainシートでフィルターで抽出されている条件を教えてください。", "A社", store
        )
        assert len(docs) >= 1
        assert any("A1:N31" in d.document.text or "非表示" in d.document.text for d in docs)

    def test_task_listing_question_uses_schedule_tasks(self):
        store = _full_store(schedule_tasks={"A社": [
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "WBSタスク一覧",
             "values": {"タスクID": "T05", "フェーズ名": "探索的分析・仮説整理", "タスク名": "仮説一覧作成"}},
            {"source_path": "data/raw/x/スケジュール.xlsx", "sheet_name": "WBSタスク一覧",
             "values": {"タスクID": "T09", "フェーズ名": "モデル構築", "タスク名": "学習実行"}},
        ]})
        docs = build_spreadsheet_state_context(
            "探索的分析・仮説整理フェーズに一致するタスクIDをすべて挙げてください。", "A社", store
        )
        texts = "\n".join(d.document.text for d in docs)
        assert "T05" in texts
        assert "T09" not in texts

    def test_no_matching_data_returns_empty_list(self):
        store = _full_store()
        docs = build_spreadsheet_state_context("何かの質問", "A社", store)
        assert docs == []
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_structured_context.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_spreadsheet_state_context'`

- [ ] **Step 3: 実装**

`src/retriever/structured_context.py` の末尾に追記:

```python
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

    # タスク列挙: 質問文に現れるフェーズ名/担当者名等の固有名詞は
    # schedule_tasks側のvaluesに実際に含まれる文字列との部分一致で判定する
    # （質問文中のどの部分文字列が「条件」かは事前に決め打ちしない。
    #  values の主要な値がquestionに含まれているかを総当たりでチェックする）
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
```

**実装注記（実装者の裁量が必要な箇所）:** タスク列挙のマッチングは「質問文にschedule_tasksの値がそのまま部分文字列として含まれるか」という単純な総当たりです。実データ（`artifacts/schedule_tasks.jsonl`）とtest split の実際の質問文（`data/raw/share/質問回答/questions_test.csv`、アクセス可能なら）で試し、フェーズ名の表記ゆれ（例:「探索的分析・仮説整理」）で取りこぼしが多い場合は、`AnswerGenerator`に渡す前段でLLMに「質問文からフェーズ名/担当者名などのフィルタ条件を抽出させる」小さな追加呼び出しを検討してよい（ただしその場合もLLM出力はcontextsの絞り込みにのみ使い、質問ごとの分岐をハードコードしないこと）。この調整を行った場合はDONE_WITH_CONCERNSで報告し、変更理由を明記すること。

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_structured_context.py -v`
Expected: 全件PASS

- [ ] **Step 5: 実データで動作確認**

```bash
.venv/bin/python -c "
from pathlib import Path
from src.structured.artifact_store import StructuredArtifactStore
from src.retriever.structured_context import build_spreadsheet_state_context

store = StructuredArtifactStore.from_artifacts_dir(Path('artifacts'))
docs = build_spreadsheet_state_context(
    '京橋信用ソリューションズのスケジュールで契約発効に関連するタスクIDを教えてください。',
    '京橋信用ソリューションズ株式会社', store,
)
for d in docs[:5]:
    print(d.document.text[:100])
"
```

Expected: 0件でないこと（実データに合わせて質問文は調整してよい）。

- [ ] **Step 6: 全テスト＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/retriever/structured_context.py tests/test_structured_context.py
git commit -m "Phase2 Task4: spreadsheet_stateパス（ハイライト条件・フィルタ条件・タスク列挙）"
```

---

### Task 5: spreadsheet_calcパス（train.csv構造化フィルタ＋集計）

**目的:** 「term=3 years、grade=B1、purpose=credit_cardに該当するloan_amntの平均を四捨五入して整数で」のような数値集計質問に答える。LLMに数値計算そのものをさせず、LLMには「フィルタ条件＋集計方法」をJSON構造で抽出させ、決定的なpandas処理で計算する（LLMの算術は信頼できないため）。任意コード実行はしない＝サンドボックス不要。

**Files:**
- Create: `src/generator/spreadsheet_calc.py`
- Create: `tests/test_spreadsheet_calc.py`
- Modify: `pyproject.toml`（`dependencies`に`pandas`を追加、無ければ）

**Interfaces:**
- Produces:
  - `CalcSpec`（dataclass）: `filters: list[FilterCondition]`, `target_column: str`, `aggregation: str`（`"mean"|"sum"|"count"|"max"|"min"`）, `round_to: int | None`
  - `FilterCondition`（dataclass）: `column: str`, `op: str`（`"=="|"!="|">"|"<"|">="|"<="`）, `value: str | float`
  - `parse_calc_spec(raw_json: str) -> CalcSpec | None`（不正なJSON/欠損キーは`None`）
  - `execute_calc_spec(spec: CalcSpec, df: "pandas.DataFrame") -> float | int | None`（列が存在しない、フィルタ後0行等はNone）
  - `SpreadsheetCalcAnswerer`: `_call_llm(question, columns_preview) -> str`をオーバーライド可能なクラス。`answer(question: str, df: "pandas.DataFrame") -> Answer`

- [ ] **Step 1: pandasが無ければ追加**

`pyproject.toml`の`dependencies`配列を確認し、`pandas`が無ければ`"pandas>=2.0",`を追加。`.venv/bin/pip install pandas`（未インストールなら）。

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_spreadsheet_calc.py`:

```python
"""spreadsheet_calc のテスト。_call_llm をオーバーライドしてAPI呼び出しを排除。"""
from __future__ import annotations

import pandas as pd
import pytest

from src.generator.spreadsheet_calc import (
    CalcSpec,
    FilterCondition,
    SpreadsheetCalcAnswerer,
    execute_calc_spec,
    parse_calc_spec,
)


# ---------------------------------------------------------------------------
# parse_calc_spec
# ---------------------------------------------------------------------------


def test_parse_calc_spec_valid_json():
    raw = '{"filters": [{"column": "grade", "op": "==", "value": "B1"}], "target_column": "loan_amnt", "aggregation": "mean", "round_to": 0}'
    spec = parse_calc_spec(raw)
    assert spec is not None
    assert spec.filters == [FilterCondition(column="grade", op="==", value="B1")]
    assert spec.target_column == "loan_amnt"
    assert spec.aggregation == "mean"
    assert spec.round_to == 0


def test_parse_calc_spec_invalid_json_returns_none():
    assert parse_calc_spec("not json") is None


def test_parse_calc_spec_missing_target_column_returns_none():
    raw = '{"filters": [], "aggregation": "mean"}'
    assert parse_calc_spec(raw) is None


def test_parse_calc_spec_multiple_filters():
    raw = '{"filters": [{"column": "term", "op": "==", "value": "3 years"}, {"column": "grade", "op": "==", "value": "B1"}], "target_column": "loan_amnt", "aggregation": "mean", "round_to": 0}'
    spec = parse_calc_spec(raw)
    assert len(spec.filters) == 2


# ---------------------------------------------------------------------------
# execute_calc_spec
# ---------------------------------------------------------------------------


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "term": ["3 years", "3 years", "5 years"],
        "grade": ["B1", "B1", "B1"],
        "loan_amnt": [1000.0, 2000.0, 5000.0],
    })


def test_execute_mean_with_single_filter():
    spec = CalcSpec(
        filters=[FilterCondition(column="term", op="==", value="3 years")],
        target_column="loan_amnt", aggregation="mean", round_to=0,
    )
    assert execute_calc_spec(spec, _sample_df()) == 1500


def test_execute_with_multiple_filters():
    spec = CalcSpec(
        filters=[
            FilterCondition(column="term", op="==", value="3 years"),
            FilterCondition(column="grade", op="==", value="B1"),
        ],
        target_column="loan_amnt", aggregation="mean", round_to=0,
    )
    assert execute_calc_spec(spec, _sample_df()) == 1500


def test_execute_count_aggregation():
    spec = CalcSpec(filters=[], target_column="loan_amnt", aggregation="count", round_to=None)
    assert execute_calc_spec(spec, _sample_df()) == 3


def test_execute_unknown_column_returns_none():
    spec = CalcSpec(filters=[], target_column="存在しない列", aggregation="mean", round_to=None)
    assert execute_calc_spec(spec, _sample_df()) is None


def test_execute_filter_matching_zero_rows_returns_none():
    spec = CalcSpec(
        filters=[FilterCondition(column="term", op="==", value="99 years")],
        target_column="loan_amnt", aggregation="mean", round_to=None,
    )
    assert execute_calc_spec(spec, _sample_df()) is None


def test_execute_numeric_comparison_filter():
    spec = CalcSpec(
        filters=[FilterCondition(column="loan_amnt", op=">", value=1500)],
        target_column="loan_amnt", aggregation="sum", round_to=None,
    )
    assert execute_calc_spec(spec, _sample_df()) == 5000


# ---------------------------------------------------------------------------
# SpreadsheetCalcAnswerer
# ---------------------------------------------------------------------------


class FakeAnswerer(SpreadsheetCalcAnswerer):
    def __init__(self, fake_response: str) -> None:
        super().__init__()
        self.fake_response = fake_response

    def _call_llm(self, question: str, columns_preview: str) -> str:
        return self.fake_response


def test_answerer_returns_computed_value_ungated():
    fake = '{"filters": [{"column": "term", "op": "==", "value": "3 years"}], "target_column": "loan_amnt", "aggregation": "mean", "round_to": 0}'
    answerer = FakeAnswerer(fake_response=fake)
    answer = answerer.answer("term=3 yearsの中でloan_amntの平均を教えてください。", _sample_df())
    assert answer.was_gated is False
    assert "1500" in answer.text


def test_answerer_gates_when_spec_unparseable():
    answerer = FakeAnswerer(fake_response="not json")
    answer = answerer.answer("何かの集計質問", _sample_df())
    assert answer.was_gated is True


def test_answerer_gates_when_filter_matches_nothing():
    fake = '{"filters": [{"column": "term", "op": "==", "value": "99 years"}], "target_column": "loan_amnt", "aggregation": "mean", "round_to": 0}'
    answerer = FakeAnswerer(fake_response=fake)
    answer = answerer.answer("term=99 yearsの中でloan_amntの平均を教えてください。", _sample_df())
    assert answer.was_gated is True
```

- [ ] **Step 3: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_spreadsheet_calc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.generator.spreadsheet_calc'`

- [ ] **Step 4: 実装**

`src/generator/spreadsheet_calc.py`:

```python
"""train.csv構造化フィルタ＋集計。LLMには「フィルタ条件＋集計方法」のJSON抽出のみ
させ、実際の計算は決定的なpandas処理で行う（LLMの算術は信頼できないため、また
コード生成→exec方式に比べサンドボックスが不要で安全）。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import pandas as pd
from anthropic import Anthropic

from src.generator.confidence_gate import ConfidenceGate
from src.models import Answer

_OPS = {
    "==": lambda s, v: s == v,
    "!=": lambda s, v: s != v,
    ">": lambda s, v: s > v,
    "<": lambda s, v: s < v,
    ">=": lambda s, v: s >= v,
    "<=": lambda s, v: s <= v,
}

_AGGS = {
    "mean": lambda s: s.mean(),
    "sum": lambda s: s.sum(),
    "count": lambda s: s.count(),
    "max": lambda s: s.max(),
    "min": lambda s: s.min(),
}

SYSTEM_PROMPT = """\
あなたはExcel/CSVデータに対する集計質問を、フィルタ条件と集計方法のJSON仕様に変換するアシスタントです。
実際の計算はあなたが行う必要はありません。列名は与えられた一覧から選び、存在しない列名を作らないこと。

【出力形式】
{
  "filters": [{"column": "列名", "op": "==|!=|>|<|>=|<=", "value": "値"}],
  "target_column": "集計対象の列名",
  "aggregation": "mean|sum|count|max|min",
  "round_to": 0
}

"round_to"は四捨五入する小数桁数（整数なら0）。指定が無ければnullにすること。
"""


@dataclass(frozen=True)
class FilterCondition:
    column: str
    op: str
    value: str | float


@dataclass
class CalcSpec:
    filters: list[FilterCondition] = field(default_factory=list)
    target_column: str = ""
    aggregation: str = ""
    round_to: int | None = None


def parse_calc_spec(raw_json: str) -> CalcSpec | None:
    try:
        m = re.search(r"\{.*\}", raw_json, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group())
        target_column = data.get("target_column")
        aggregation = data.get("aggregation")
        if not target_column or aggregation not in _AGGS:
            return None
        filters = [
            FilterCondition(column=f["column"], op=f["op"], value=f["value"])
            for f in data.get("filters", [])
            if f.get("column") and f.get("op") in _OPS
        ]
        return CalcSpec(
            filters=filters,
            target_column=target_column,
            aggregation=aggregation,
            round_to=data.get("round_to"),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def execute_calc_spec(spec: CalcSpec, df: pd.DataFrame) -> float | int | None:
    if spec.target_column not in df.columns:
        return None
    filtered = df
    for cond in spec.filters:
        if cond.column not in filtered.columns:
            return None
        op_fn = _OPS.get(cond.op)
        if op_fn is None:
            return None
        try:
            filtered = filtered[op_fn(filtered[cond.column], cond.value)]
        except TypeError:
            return None
    if len(filtered) == 0:
        return None
    agg_fn = _AGGS.get(spec.aggregation)
    if agg_fn is None:
        return None
    result = agg_fn(filtered[spec.target_column])
    if pd.isna(result):
        return None
    if spec.round_to is not None:
        result = round(float(result), spec.round_to)
        if spec.round_to == 0:
            result = int(result)
    return result


class SpreadsheetCalcAnswerer:
    def __init__(self, threshold: float = 0.4) -> None:
        self.gate = ConfidenceGate(threshold=threshold)
        self._client: Anthropic | None = None

    def answer(self, question: str, df: pd.DataFrame) -> Answer:
        columns_preview = ", ".join(df.columns)
        raw = self._call_llm(question, columns_preview)
        spec = parse_calc_spec(raw)
        if spec is None:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)

        result = execute_calc_spec(spec, df)
        if result is None:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)

        return Answer(text=str(result), confidence=0.9, was_gated=False)

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _call_llm(self, question: str, columns_preview: str) -> str:
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
        message = self._get_client().messages.create(
            model=model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"【質問】\n{question}\n\n【利用可能な列名】\n{columns_preview}",
            }],
        )
        return "".join(block.text for block in message.content if hasattr(block, "text"))
```

**実装注記:** `value`の型（文字列 vs 数値）はJSON側の型をそのまま使う設計です。CSV由来のDataFrameで列が文字列型なのにLLMが数値でフィルタ値を出す等の型不一致が実データで頻発する場合は、`execute_calc_spec`内で比較前に`str(filtered[cond.column]) == str(cond.value)`のような緩い比較にフォールバックしてよい（ただし挙動が変わるならテストを追加すること）。

- [ ] **Step 5: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_spreadsheet_calc.py -v`
Expected: 全件PASS

- [ ] **Step 6: 全テスト＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/generator/spreadsheet_calc.py tests/test_spreadsheet_calc.py pyproject.toml
git commit -m "Phase2 Task5: spreadsheet_calcパス（構造化フィルタ+集計、LLMは仕様抽出のみ）"
```

---

### Task 6: 列挙・完全性ゲート

**目的:** 列挙系の回答（office_style・spreadsheet_stateのタスク列挙等）で、「全要素を抽出できたか」を機械的に確認できない場合はMissingに倒す。CRAGでは部分一致がすべてIncorrectになる最も危険なカテゴリのため。

**Files:**
- Create: `src/generator/enumeration_gate.py`
- Create: `tests/test_enumeration_gate.py`

**Interfaces:**
- Produces: `is_enumeration_complete(matched_count: int, candidate_pool_size: int, extraction_method: str) -> bool`。Task 7がTask 3/4の構造化コンテキスト件数と組み合わせて使う。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_enumeration_gate.py`:

```python
"""列挙の完全性ゲート。全要素抽出が機械的に確認できない場合はMissingに倒すためのロジック。"""
from __future__ import annotations

from src.generator.enumeration_gate import is_enumeration_complete


def test_structured_extraction_with_matches_is_complete():
    """artifactsからの直接抽出（style/highlight属性でのフィルタ）は
    全件をコードで走査しているので、1件以上マッチすれば完全とみなせる。"""
    assert is_enumeration_complete(matched_count=3, candidate_pool_size=10, extraction_method="structured_attribute_filter") is True


def test_structured_extraction_with_zero_matches_is_not_complete():
    """0件マッチは「該当なし」なのか「抽出条件を認識できなかった」のか区別できないため
    安全側でMissing扱いにする。"""
    assert is_enumeration_complete(matched_count=0, candidate_pool_size=10, extraction_method="structured_attribute_filter") is False


def test_structured_extraction_with_empty_pool_is_not_complete():
    """artifacts自体が空（該当ファイルの抽出に失敗している等）の場合は完全性を主張できない。"""
    assert is_enumeration_complete(matched_count=0, candidate_pool_size=0, extraction_method="structured_attribute_filter") is False


def test_unknown_extraction_method_is_not_complete():
    """未知の抽出方式は安全側でMissing扱い（新しいコード経路を足したら明示的にこの関数へ登録する）。"""
    assert is_enumeration_complete(matched_count=5, candidate_pool_size=10, extraction_method="something_new") is False
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_enumeration_gate.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 実装**

`src/generator/enumeration_gate.py`:

```python
"""列挙系回答の完全性ゲート。

CRAGでは列挙設問の部分一致がすべてIncorrect（Acceptable無し）になる、
最も安全マージンの無いカテゴリ。全要素を抽出できたと機械的に確認できる
方式のときだけ「完全」とみなし、それ以外はMissingに倒す。
"""
from __future__ import annotations

# artifacts全件をコードで走査してスタイル属性等で機械的にフィルタする方式は、
# マッチ件数が0より大きければ「その条件に該当する全件」を返している
# （検索エンジンのtop-k打ち切りのような取りこぼしが構造的に起きない）。
_COMPLETE_METHODS = frozenset({"structured_attribute_filter"})


def is_enumeration_complete(matched_count: int, candidate_pool_size: int, extraction_method: str) -> bool:
    if extraction_method not in _COMPLETE_METHODS:
        return False
    if candidate_pool_size == 0:
        return False
    if matched_count == 0:
        return False
    return True
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_enumeration_gate.py -v`
Expected: 全件PASS

- [ ] **Step 5: 全テスト＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/generator/enumeration_gate.py tests/test_enumeration_gate.py
git commit -m "Phase2 Task6: 列挙系回答の完全性ゲート（部分一致=Incorrect対策）"
```

---

### Task 7: ルーティング統合

**目的:** `Pipeline._process_one`で、質問タイプに応じて構造化パス（Task 3/4/5）と通常のBM25検索パスを振り分ける。構造化パスの結果もPhase 1のゲート・引用チェックを通す（`spreadsheet_calc`のみ専用ゲート）。

**Files:**
- Modify: `src/orchestrator/pipeline.py`
- Modify: `scripts/run_pipeline.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `classify_question`（Task 1）、`StructuredArtifactStore`（Task 2）、`build_office_style_context` / `build_spreadsheet_state_context`（Task 3/4）、`SpreadsheetCalcAnswerer`（Task 5）、`is_enumeration_complete`（Task 6）
- Produces: `Pipeline.__init__(..., artifacts_dir: Path | None = None)`（新しい任意引数）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pipeline.py` の末尾に追記:

```python
def test_pipeline_routes_office_style_question_through_structured_context(tmp_path: Path):
    """office_styleタグの質問は、通常のBM25検索ではなく構造化コンテキストを使う。"""
    import json as json_module
    from src.orchestrator.pipeline import Pipeline, QAPair

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "office_marks.jsonl").write_text(
        json_module.dumps({
            "source_path": "data/raw/x/提案書.pptx", "project_name": "テスト社",
            "file_name": "提案書.pptx", "slide_number": 1, "text": "太字の重要事項",
            "bold": True, "italic": False, "underline": False, "font_color": None, "fill_color": None,
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False, artifacts_dir=artifacts_dir)
    pipeline.generator._call_llm = lambda q, c: json_module.dumps({
        "answer": "太字の重要事項", "confidence": 0.9, "citation": "太字の重要事項", "reasoning": "r",
    })

    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(question_id="0", question="太字で記載されている箇所を抽出してください。案件はテスト社です。"))

    assert "太字の重要事項" in result.answer


def test_pipeline_routes_spreadsheet_calc_question_to_calc_answerer(tmp_path: Path, monkeypatch):
    """spreadsheet_calcタグの質問はSpreadsheetCalcAnswererに渡り、通常のgenerate()は呼ばれない。"""
    import json as json_module
    from src.orchestrator.pipeline import Pipeline, QAPair

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    csv_dir = tmp_path / "data" / "raw" / "share" / "共有ドライブ" / "プロジェクト" / "テスト社" / "03.データ"
    csv_dir.mkdir(parents=True)
    (csv_dir / "train.csv").write_text("term,loan_amnt\n3 years,1000\n3 years,2000\n", encoding="utf-8")

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False)

    def _boom(question, contexts):
        raise AssertionError("spreadsheet_calcは通常のgenerate()を使ってはいけない")

    pipeline.generator.generate = _boom
    pipeline.spreadsheet_calc_answerer._call_llm = lambda q, cols: json_module.dumps({
        "filters": [{"column": "term", "op": "==", "value": "3 years"}],
        "target_column": "loan_amnt", "aggregation": "mean", "round_to": 0,
    })

    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="0",
        question="テスト社のtrain.csvにおいて、term=3 yearsの中でloan_amntの平均を算出してください。",
    ))

    assert "1500" in result.answer
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 新規2テストがFAIL（`TypeError`または属性エラー）

- [ ] **Step 3: 実装**

`src/orchestrator/pipeline.py`:

- import追加:

```python
from src.generator.spreadsheet_calc import SpreadsheetCalcAnswerer
from src.retriever.structured_context import build_office_style_context, build_spreadsheet_state_context
from src.structured.artifact_store import StructuredArtifactStore
from src.utils.question_classifier import classify_question
```

- `Pipeline.__init__` に`artifacts_dir`引数を追加:

```python
    def __init__(
        self,
        data_dir: Path,
        max_concurrent: int = 5,
        top_k: int = 5,
        confidence_threshold: float = 0.4,
        run_judge: bool = True,
        project_aliases: dict[str, list[str]] | None = None,
        term_registry: list[dict] | None = None,
        artifacts_dir: Path | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.max_concurrent = max_concurrent
        self.top_k = top_k
        self.run_judge = run_judge
        self.logger = setup_logging()

        self.dispatcher = ParserDispatcher()
        self.retriever = ProjectScopedRetriever(project_aliases=project_aliases)
        self.query_expander = QueryExpander(term_registry or [])
        self.generator = AnswerGenerator(threshold=confidence_threshold)
        self.judge = LocalJudge()

        self.artifacts_dir = artifacts_dir
        self.structured_store = (
            StructuredArtifactStore.from_artifacts_dir(artifacts_dir) if artifacts_dir else None
        )
        self.spreadsheet_calc_answerer = SpreadsheetCalcAnswerer(threshold=confidence_threshold)
```

（`project_aliases`/`term_registry`/`QueryExpander`はPhase 1で既に入っている前提。無ければPhase 1の該当diffを先に適用すること。）

- `_process_one` を書き換え。まず質問を分類し、案件名を推定（`self.retriever.detect_project(qa.question)`は`ProjectScopedRetriever`のPhase 1版を使う。案件名が特定できない構造化質問は通常パスにフォールバックする):

```python
    def _resolve_project_name(self, question: str) -> str | None:
        return self.retriever.detect_project(question)

    def _process_structured(self, qa: QAPair, tags: list[str]) -> Answer | None:
        if self.structured_store is None:
            return None
        project_name = self._resolve_project_name(qa.question)
        if project_name is None:
            return None

        if "spreadsheet_calc" in tags:
            df = self._load_train_csv(project_name)
            if df is not None:
                return self.spreadsheet_calc_answerer.answer(qa.question, df)
            return None

        contexts: list[ScoredDocument] = []
        if "office_style" in tags:
            contexts = build_office_style_context(qa.question, project_name, self.structured_store)
        elif "spreadsheet_state" in tags:
            contexts = build_spreadsheet_state_context(qa.question, project_name, self.structured_store)

        if not contexts:
            return None

        if not is_enumeration_complete(
            matched_count=len(contexts), candidate_pool_size=len(contexts),
            extraction_method="structured_attribute_filter",
        ):
            return None

        return self.generator.generate(qa.question, contexts)

    def _load_train_csv(self, project_name: str):
        import pandas as pd
        candidates = list(self.data_dir.rglob("train.csv"))
        matching = [p for p in candidates if project_name in str(p)]
        target = matching[0] if matching else (candidates[0] if len(candidates) == 1 else None)
        if target is None:
            return None
        try:
            return pd.read_csv(target)
        except Exception:
            return None

    def _process_one(self, qa: QAPair) -> PipelineResult:
        tags = classify_question(qa.question)
        structured_answer = None
        if any(t in tags for t in ("office_style", "spreadsheet_state", "spreadsheet_calc")):
            structured_answer = self._process_structured(qa, tags)

        if structured_answer is not None:
            answer = structured_answer
            retrieved_sources = []
        else:
            search_query = self.query_expander.expand_terms(qa.question)
            contexts = self.retriever.search(search_query, top_k=self.top_k)
            answer = self.generator.generate(qa.question, contexts)
            retrieved_sources = [
                f"{to_repo_relative(sd.document.source_path)}::{sd.document.location}"
                for sd in contexts
            ]

        # ...（judge呼び出し・PipelineResult組み立ては既存のまま。retrieved_sourcesの扱いは
        #     Phase 0 Task 2が既に入っている前提でそのフィールドに渡す）
```

**重要な統合注記:** 上のコードは骨格です。`_process_one`の残り（judge呼び出し、`PipelineResult`の組み立て）はPhase 0 Task 2・Phase 1 Task 3で既に変更されているはずなので、**実際のファイルを読んでから、構造化パス分岐だけを追加する形でマージしてください**（書き換え全体を貼り付けるのではなく、差分として組み込む）。`is_enumeration_complete`は`from src.generator.enumeration_gate import is_enumeration_complete`のimportが必要です。`ScoredDocument`の型ヒントを使うなら`from src.models import ScoredDocument`も必要です。

`scripts/run_pipeline.py`:

- argparseに追加: `parser.add_argument("--artifacts-dir", ...)`がPhase 1 Task 3で既に追加されている場合は、その値をそのまま`Pipeline(artifacts_dir=args.artifacts_dir, ...)`に渡すだけでよい（Phase 1で`--artifacts-dir`が無ければこのタスクで追加する）。

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 全件PASS

- [ ] **Step 5: 全テスト＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/orchestrator/pipeline.py scripts/run_pipeline.py tests/test_pipeline.py
git commit -m "Phase2 Task7: 質問タイプ別の構造化パス/通常パスのルーティング統合"
```

---

### Task 8: E2E確認・artifacts再生成手順の文書化・plan_0703.md更新

**目的:** 実データ・実APIでvalid 30問を再実行し、spreadsheet_state/office_style/spreadsheet_calcの該当問（valid内で各3問程度）でPerfect過半・Incorrect 0を確認する。artifacts再生成手順を文書化する。**このタスクはAPIコストが発生する。**

**Files:**
- Create: `experiments/phase2_valid_<ts>.json`
- Modify: `docs/plan/plan_0703.md`
- Modify: `README.md`（無ければ作成せず、既存のセットアップ手順ドキュメントに追記。存在場所が不明ならCLAUDE.mdの近くに`docs/setup.md`等を作らず、まず`ls *.md`で既存箇所を確認すること）

**Interfaces:**
- Consumes: Task 1〜7の全成果物
- Produces: Phase 2完了条件の実測確認

- [ ] **Step 1: artifactsが最新か確認して再生成**

```bash
.venv/bin/python scripts/extract_spreadsheets.py
.venv/bin/python scripts/scan_train_xlsx_xml.py
.venv/bin/python scripts/build_train_xlsx_highlight_context.py
.venv/bin/python scripts/extract_office_marks.py
```

- [ ] **Step 2: valid 30問をフルパイプラインで再実行**

```bash
.venv/bin/python scripts/run_pipeline.py \
  --data-dir "data/raw/share/共有ドライブ" \
  --questions "data/raw/share/質問回答/questions_valid.csv" \
  --artifacts-dir artifacts \
  --run-name phase2_valid
```

- [ ] **Step 3: ベースライン・Phase1結果と比較**

`docs/question_labels.csv`で`primary_type`が`spreadsheet_state`/`office_style`/`spreadsheet_calc`のvalid行（該当indexを`grep`等で特定）について、`experiments/phase2_valid_<ts>.json`の`judge_label`を確認する。

**必須確認事項:**
- 該当typeでIncorrectが増えていないこと（列挙系は特に注意）。
- 該当typeでPerfect/Acceptableが増えていること（完了条件: 各type3問中Perfect過半）。
- 全体のIncorrect件数がこれまでの最良値以下であること。

- [ ] **Step 4: `docs/plan/plan_0703.md`に結果を追記**

Phase 1の実装結果セクションの直後に、Phase 1と同形式のテーブルでPhase 2の実測値を追記する。

- [ ] **Step 5: 最終確認＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add experiments/ docs/plan/plan_0703.md
git commit -m "Phase2 Task8: valid30問での実測確認とartifacts再生成手順の文書化"
```

---

## 完了条件

- Task 1〜7の全変更後、`.venv/bin/pytest tests/ -v` が全件PASSする。
- valid の spreadsheet_state 3問・office_style 3問・spreadsheet_calc 3問でPerfect過半、Incorrect 0（`plan_0703.md`完了条件）。
- `docs/plan/plan_0703.md`に実測結果が追記されている。
- `scripts/analyze_spreadsheet_coverage.py`のハードコード辞書、`scripts/build_schedule_query_candidates.py`の個別質問対応コードは温存されたまま（本計画では触らない）だが、Task 4の実装がそのパターンを踏襲していないこと（レビュー時に確認）。
