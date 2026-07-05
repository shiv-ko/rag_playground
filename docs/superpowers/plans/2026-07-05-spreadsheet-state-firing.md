# spreadsheet_state発火（カバレッジ攻めブロックA）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 質問中の明示ファイル名によるスコープ絞りと、未接続の `schedule_tasks.jsonl` ハイライト行データの接続で、test Missing 85問中のspreadsheet_state系を回収する。

**Architecture:** 純粋関数の新モジュール `question_file_scope.py`（ファイル名抽出・照合）を検索層と構造化ビルダーの両方から使う。`build_spreadsheet_state_context` のハイライト分岐に schedule_tasks 由来の行docを追加する（既存 train_xlsx 経路は不変）。色指定は16進fill色→色ファミリ分類の純粋関数で解決する。

**Tech Stack:** Python 3.11+ / pytest / 既存の `StructuredArtifactStore`・`KeywordStore`。新規依存なし。

**Spec:** `docs/superpowers/specs/2026-07-05-spreadsheet-state-firing-design.md`

## Global Constraints

- テスト: `.venv/bin/pytest tests/ -v`（現在**341件**、全件PASS維持）
- 新しい文字列比較は必ず両辺 `unicodedata.normalize("NFC", ...)`（このリポジトリで7回目の事故を起こさない）
- 競技規約: 特定の案件名・ファイル名・質問文・正解値のハードコード禁止。テストのフィクスチャは合成値のみ
- 絞り込みは安全側: 「絞った結果が0件になるヒントは適用しない」（`_narrow_marks_by_question_hints` の既存パターンに従う）
- 各タスク完了ごとに step-review（`.claude/skills/step-review`、検索・提出経路に近いのでsonnet）→ コミット
- スコープ外: 横断14問（ブロックB）、office_marks経路、`train_xlsx_highlight_blocks` 経路の変更、answer_stabilizer

---

### Task 1: `src/retriever/question_file_scope.py` — 質問中のファイル名抽出・照合

**Files:**
- Create: `src/retriever/question_file_scope.py`
- Test: `tests/test_question_file_scope.py`

**Interfaces:**
- Produces: `extract_file_names(question: str) -> list[str]`（NFC正規化済みファイル名、出現順・重複除去）
- Produces: `matches_file_name(source: str | Path, file_names: list[str]) -> bool`（sourceのbasenameがいずれかとNFC一致）
- Task 2（retriever）と Task 3（structured_context）が両方これを使う

- [ ] **Step 1: 失敗するテストを書く**

```python
"""質問文中の明示ファイル名の抽出・照合のテスト。"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from src.retriever.question_file_scope import extract_file_names, matches_file_name


def test_extract_single_xlsx_name():
    q = "計画_r2.xlsxにおいて、オレンジにハイライトされている行を答えてください。"
    assert extract_file_names(q) == ["計画_r2.xlsx"]


def test_extract_multiple_and_dedup():
    q = "報告.pptxと報告.pptxと分析.docxの違いは？"
    assert extract_file_names(q) == ["報告.pptx", "分析.docx"]


def test_extract_returns_empty_when_no_file():
    assert extract_file_names("宿泊費の上限を教えてください。") == []


def test_extract_normalizes_nfd_to_nfc():
    name_nfd = unicodedata.normalize("NFD", "データ一覧.xlsx")
    q = f"{name_nfd}のシート数は？"
    assert extract_file_names(q) == [unicodedata.normalize("NFC", "データ一覧.xlsx")]


def test_extract_stops_at_japanese_punctuation():
    q = "つぎのファイル、集計.csvの行数は？"
    assert extract_file_names(q) == ["集計.csv"]


def test_matches_file_name_by_basename_nfc():
    names = extract_file_names("計画_r2.xlsxの内容は？")
    nfd_path = unicodedata.normalize("NFD", "data/raw/x/02.計画/計画_r2.xlsx")
    assert matches_file_name(nfd_path, names)
    assert matches_file_name(Path("y/計画_r2.xlsx"), names)
    assert not matches_file_name("data/raw/x/02.計画/計画.xlsx", names)


def test_matches_file_name_empty_names_is_false():
    assert not matches_file_name("a/b.xlsx", [])
```

- [ ] **Step 2: テストが正しい理由で失敗することを確認**

Run: `.venv/bin/pytest tests/test_question_file_scope.py -v`
Expected: FAIL（`ModuleNotFoundError: src.retriever.question_file_scope`）

- [ ] **Step 3: 最小実装**

```python
"""質問文中に明示されたファイル名の抽出と、ソースパスとの照合。

抽出は「拡張子付きトークン」の一般則のみ（質問文由来の値だけを使う）。
特定のファイル名・案件名はハードコードしない。
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# 空白・和文/欧文の区切り記号で切れる連続文字列＋既知拡張子。
# 「::」はチャンクlocation区切りのため除外対象に含める。
_FILE_NAME_RE = re.compile(
    r"[^\s、。，「」『』（）()：:；;・？！?!*/\\]+"
    r"\.(?:xlsx|xlsm|pptx|docx|pdf|csv|ipynb|txt|md)",
    re.IGNORECASE,
)


def extract_file_names(question: str) -> list[str]:
    """質問中の拡張子付きファイル名をNFC正規化して出現順に返す（重複除去）。"""
    normalized = unicodedata.normalize("NFC", question)
    seen: list[str] = []
    for match in _FILE_NAME_RE.finditer(normalized):
        name = match.group(0)
        if name not in seen:
            seen.append(name)
    return seen


def matches_file_name(source: str | Path, file_names: list[str]) -> bool:
    """sourceのbasenameが file_names のいずれかとNFC一致するか。"""
    if not file_names:
        return False
    basename = unicodedata.normalize("NFC", Path(str(source)).name)
    return basename in file_names
```

- [ ] **Step 4: テストPASSを確認**

Run: `.venv/bin/pytest tests/test_question_file_scope.py -v`
Expected: 7 passed

- [ ] **Step 5: 全テストPASSを確認**

Run: `.venv/bin/pytest tests/ -v`
Expected: 348 passed（341 + 7）

- [ ] **Step 6: step-review（sonnet）→ コミット**

step-reviewテンプレートでレビュー（意図: 質問文由来ファイル名の汎用抽出。NFC両辺・ハードコードなしを重点確認）。CONFIRMEDのみ修正後:

```bash
git add src/retriever/question_file_scope.py tests/test_question_file_scope.py
git commit -m "Add question file-name extraction for retrieval scoping"
```

---

### Task 2: `ProjectScopedRetriever.search` — 名指しファイルのチャンク優先

**Files:**
- Modify: `src/retriever/project_scoped_retriever.py`（`search()` メソッド、現在77-82行目）
- Test: `tests/test_project_scoped_retriever.py`（既存ファイルに追記。無ければ新規作成）

**Interfaces:**
- Consumes: Task 1の `extract_file_names` / `matches_file_name`
- Produces: `search(query, top_k)` の挙動変更 — 質問がファイル名を明示し、かつ一致チャンクが候補内に存在する場合のみ一致チャンクを先頭に安定ソート。それ以外は完全に従来動作

- [ ] **Step 1: 失敗するテストを書く**（既存テストファイルの末尾に追記）

```python
def _doc(text: str, path: str, project: str = "A社") -> Document:
    return Document(
        text=text,
        source_path=Path(path),
        location="sheet_1",
        metadata={"project": project},
    )


def test_search_prioritizes_explicitly_named_file():
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("スケジュール タスク 進捗 管理 一覧", "data/A社/02.計画/計画.xlsx"),
        _doc("スケジュール タスク 進捗 担当 記録", "data/A社/02.計画/計画_r2.xlsx"),
    ])
    results = retriever.search("A社の計画_r2.xlsxのスケジュールでタスクの進捗は？", top_k=1)
    assert results[0].document.source_path.name == "計画_r2.xlsx"


def test_search_without_file_name_is_unchanged():
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("宿泊費 上限 規定", "data/A社/規定.docx"),
    ])
    results = retriever.search("A社の宿泊費の上限は？", top_k=5)
    assert len(results) == 1


def test_search_falls_back_when_named_file_has_no_chunks():
    retriever = ProjectScopedRetriever()
    retriever.add([
        _doc("スケジュール タスク 進捗", "data/A社/02.計画/計画.xlsx"),
    ])
    results = retriever.search("A社の存在しない.xlsxのスケジュールは？", top_k=5)
    assert len(results) == 1  # 一致ゼロでも従来の検索結果を返す
```

注意: importは既存ファイル先頭の流儀に合わせる（`Document` / `Path` / `ProjectScopedRetriever` が未importなら追加）。

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_project_scoped_retriever.py -v`
Expected: `test_search_prioritizes_explicitly_named_file` がFAIL（BM25スコア順のため `計画.xlsx` が来る場合）。
もしBM25が偶然 `_r2` を先に返してPASSする場合は、`計画.xlsx` 側のdocのtextに質問語彙を1語多く含めて（例: 「スケジュール タスク 進捗 管理 一覧 計画」）非優先側が先に来るフィクスチャに調整し、FAILを確認してから進む。

- [ ] **Step 3: 最小実装**（`search()` を置き換え）

```python
    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        project = self.detect_project(query)
        store = self._project_stores[project] if project is not None else self._global_store
        file_names = extract_file_names(query)
        if not file_names:
            return store.search(query, top_k)

        # 名指しファイルのチャンクを優先する。候補を広めに取り、一致分を先頭に
        # 安定ソート（一致ゼロなら従来結果と同一 — ハードフィルタにしない）
        candidates = store.search(query, top_k * 4)
        matched = [c for c in candidates if matches_file_name(c.document.source_path, file_names)]
        if not matched:
            return candidates[:top_k]
        others = [c for c in candidates if not matches_file_name(c.document.source_path, file_names)]
        return (matched + others)[:top_k]
```

ファイル先頭に追加:

```python
from src.retriever.question_file_scope import extract_file_names, matches_file_name
```

- [ ] **Step 4: テストPASSを確認**

Run: `.venv/bin/pytest tests/test_project_scoped_retriever.py -v`
Expected: 追加3件を含め全PASS

- [ ] **Step 5: 全テストPASSを確認**

Run: `.venv/bin/pytest tests/ -v`
Expected: 351 passed。既存の検索系テストが落ちた場合は「候補プールをtop_k*4に広げたことによる順位変動」を疑い、実装ではなく原因を確認してから対処（既存アサーションの意図を壊さない）

- [ ] **Step 6: step-review（sonnet）→ コミット**

```bash
git add src/retriever/project_scoped_retriever.py tests/test_project_scoped_retriever.py
git commit -m "Prioritize explicitly named files in project-scoped search"
```

---

### Task 3: 色ファミリ分類とスケジュール行ハイライトdocsビルダー

**Files:**
- Modify: `src/retriever/structured_context.py`（`_render_filter_conditions` の直後あたりに追加）
- Test: `tests/test_structured_context.py`（末尾に追記）

**Interfaces:**
- Consumes: Task 1の `extract_file_names` / `matches_file_name`、既存 `_requested_color_names`
- Produces: `_hex_color_family(hex_str: str) -> str`（"red"/"orange"/"yellow"/"green"/"blue"/"purple"/"pink"/"achromatic"/""）
- Produces: `_schedule_highlight_docs(question: str, rows: list[dict]) -> list[ScoredDocument]`（Task 4が `build_spreadsheet_state_context` から呼ぶ）

- [ ] **Step 1: 失敗するテストを書く**（合成値のみ。実データの案件名・タスク名は書かない）

```python
def test_hex_color_family_classifies_hue_buckets() -> None:
    from src.retriever.structured_context import _hex_color_family

    assert _hex_color_family("F2E0D0") == "orange"   # 淡いオレンジ
    assert _hex_color_family("B4C6E7") == "blue"     # 淡い青
    assert _hex_color_family("E2EFDA") == "green"    # 淡い緑
    assert _hex_color_family("FFFF00") == "yellow"
    assert _hex_color_family("FF0000") == "red"
    assert _hex_color_family("FFFFFF") == "achromatic"
    assert _hex_color_family("808080") == "achromatic"
    assert _hex_color_family("00FFFF00") == "yellow"  # ARGB 8桁は下6桁
    assert _hex_color_family("") == ""
    assert _hex_color_family("THEME:1") == ""


def _schedule_rows() -> list[dict]:
    def row(file_name: str, row_number: int, fill: str | None, task: str) -> dict:
        return {
            "source_path": f"data/x/02.計画/{file_name}",
            "file_name": file_name,
            "sheet_name": "工程",
            "row_number": row_number,
            "dominant_row_fill": fill,
            "values": {"タスクID": f"T{row_number}", "タスク名": task, "担当者": "架空 太郎"},
        }

    return [
        row("工程_r2.xlsx", 2, "F2E0D0", "要件整理"),
        row("工程_r2.xlsx", 3, None, "設計"),
        row("工程_r2.xlsx", 4, "F2E0D0", "受入確認"),
        row("工程_r2.xlsx", 5, "B4C6E7", "移行リハーサル"),
        row("工程.xlsx", 2, "F2E0D0", "旧版タスク"),
    ]


def test_schedule_highlight_docs_filters_by_named_file_and_color() -> None:
    from src.retriever.structured_context import _schedule_highlight_docs

    docs = _schedule_highlight_docs(
        "工程_r2.xlsxにおいて、オレンジにハイライトされている行のタスク名をすべて答えてください。",
        _schedule_rows(),
    )
    texts = [d.document.text for d in docs]
    assert len(docs) == 2
    assert any("要件整理" in t for t in texts)
    assert any("受入確認" in t for t in texts)
    assert not any("旧版タスク" in t for t in texts)   # 名指し外のファイルは除外
    assert not any("移行リハーサル" in t for t in texts)  # 色不一致は除外
    assert not any("設計" in t for t in texts)          # 塗りなし行は除外


def test_schedule_highlight_docs_without_color_returns_all_filled_rows() -> None:
    from src.retriever.structured_context import _schedule_highlight_docs

    docs = _schedule_highlight_docs(
        "工程_r2.xlsxでハイライトされている行は？", _schedule_rows()
    )
    assert len(docs) == 3  # 塗りあり3行（色指定なしなら全ハイライト行）


def test_schedule_highlight_docs_keeps_rows_when_named_file_absent() -> None:
    from src.retriever.structured_context import _schedule_highlight_docs

    docs = _schedule_highlight_docs(
        "不在.xlsxでオレンジにハイライトされている行は？", _schedule_rows()
    )
    # 絞った結果が0件になるヒントは適用しない（既存 _narrow_marks_by_question_hints と同じ安全則）
    assert len(docs) == 3
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_structured_context.py -k "hex_color or schedule_highlight" -v`
Expected: FAIL（`ImportError: cannot import name '_hex_color_family'`）

- [ ] **Step 3: 最小実装**（`structured_context.py` に追加。import節に `from src.retriever.question_file_scope import extract_file_names, matches_file_name` を追加）

```python
def _hex_color_family(hex_str: str) -> str:
    """xlsxのfill色(RRGGBB/AARRGGBB)を色ファミリへ分類する。判定不能は空文字。

    色相(hue)ベースの一般則のみ。特定の答えに合わせた個別色コードは書かない。
    """
    token = str(hex_str or "").strip().lstrip("#")
    if len(token) == 8:
        token = token[2:]
    if len(token) != 6:
        return ""
    try:
        r, g, b = (int(token[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return ""

    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 12:  # 彩度がほぼ無い → 白/灰/黒
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
    if hue < 45:
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
    candidates = [r for r in rows if r.get("dominant_row_fill")]
    if not candidates:
        return []

    file_names = extract_file_names(question)
    if file_names:
        narrowed = [r for r in candidates if matches_file_name(r.get("source_path") or r.get("file_name") or "", file_names)]
        if narrowed:  # 絞った結果が0件になるヒントは適用しない（安全側）
            candidates = narrowed

    color_names = _requested_color_names(question)
    if color_names:
        candidates = [
            r for r in candidates
            if _hex_color_family(str(r.get("dominant_row_fill"))) in color_names
        ]

    docs: list[ScoredDocument] = []
    for r in candidates:
        values = r.get("values") or {}
        value_desc = ", ".join(f"{k}={v}" for k, v in values.items() if v not in (None, ""))
        family = _hex_color_family(str(r.get("dominant_row_fill")))
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
```

注意: `_COLOR_LABELS` のキーに "achromatic" は無いので `color_label` はフォールバック側（family文字列）になる — それで良い（達成したいのは色指定質問とのマッチであり、ラベルは補助表示）。

- [ ] **Step 4: テストPASSを確認**

Run: `.venv/bin/pytest tests/test_structured_context.py -k "hex_color or schedule_highlight" -v`
Expected: 4 passed

- [ ] **Step 5: 全テストPASSを確認 → step-review（sonnet）→ コミット**

Run: `.venv/bin/pytest tests/ -v`
Expected: 355 passed

```bash
git add src/retriever/structured_context.py tests/test_structured_context.py
git commit -m "Add schedule-row highlight context with hex color family matching"
```

---

### Task 4: `build_spreadsheet_state_context` への配線

**Files:**
- Modify: `src/retriever/structured_context.py`（`build_spreadsheet_state_context` のハイライト分岐、現在433-443行目）
- Test: `tests/test_structured_context.py`（末尾に追記）

**Interfaces:**
- Consumes: Task 3の `_schedule_highlight_docs`、既存 `store.schedule_tasks_for(project_name)`
- Produces: `build_spreadsheet_state_context` がスケジュール系xlsxのハイライト行docsも返す。`pipeline._structured_pool_size` は既に `schedule_tasks_for` をプールに含むため変更不要

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_spreadsheet_state_context_includes_schedule_highlights() -> None:
    store = _full_store(schedule_tasks={"A社": [
        {
            "source_path": "data/x/02.計画/工程_r2.xlsx",
            "file_name": "工程_r2.xlsx",
            "sheet_name": "工程",
            "row_number": 2,
            "dominant_row_fill": "F2E0D0",
            "values": {"タスク名": "要件整理"},
        },
    ]})
    docs = build_spreadsheet_state_context(
        "工程_r2.xlsxにおいて、オレンジにハイライトされている行のタスク名は？", "A社", store
    )
    assert any("要件整理" in d.document.text for d in docs)


def test_spreadsheet_state_context_train_xlsx_path_unchanged() -> None:
    store = _full_store(
        train_xlsx_highlight_blocks={"A社": [
            {
                "source_path": "data/x/03.データ/train.xlsx",
                "sheet_name": "Sheet1",
                "range": "B2:B4",
                "fill_color_name": "FFFF00",
                "first_value": "42",
                "column_header": {"value": "件数", "cell": "B1"},
                "same_row_values": [],
            },
        ]},
        schedule_tasks={"A社": []},
    )
    docs = build_spreadsheet_state_context(
        "train.xlsxでハイライトされているセルの値は？", "A社", store
    )
    assert any("ハイライト範囲" in d.document.text for d in docs)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_structured_context.py -k "includes_schedule or train_xlsx_path_unchanged" -v`
Expected: `includes_schedule` がFAIL（schedule_tasksは現状未接続）、`train_xlsx_path_unchanged` はPASS（現状仕様の押さえ）

- [ ] **Step 3: 最小実装**（ハイライト分岐の末尾に2行追加）

```python
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
        # スケジュール系xlsx（train.xlsx以外）のハイライト行はschedule_tasksから
        docs.extend(_schedule_highlight_docs(question, store.schedule_tasks_for(project_name)))
```

- [ ] **Step 4: テストPASSを確認**

Run: `.venv/bin/pytest tests/test_structured_context.py -v`
Expected: 全PASS（追加2件含む）

- [ ] **Step 5: 全テストPASSを確認 → step-review（sonnet）→ コミット**

Run: `.venv/bin/pytest tests/ -v`
Expected: 357 passed

```bash
git add src/retriever/structured_context.py tests/test_structured_context.py
git commit -m "Wire schedule-task highlights into spreadsheet_state context"
```

---

### Task 5: オフライン検証・valid回帰・test発火プローブ（LLM必要 — Claude実施）

**Files:**
- 生成: `experiments/exp_ssfire_valid_*.json` ×3、`experiments/judge_calibration_*.json`、`experiments/diag_test_*.json`
- 記録: `docs/daily作業ログ/`（新規）、`docs/plan/plan_0703.md` §2系に実測追記

**Interfaces:**
- Consumes: Task 1〜4の完成コード（HEAD）
- Produces: 提出可否判断の材料（no-harm確認＋発火実測）

- [ ] **Step 1: valid 30問 N=3 を実行**

```bash
for i in 1 2 3; do
  .venv/bin/python scripts/run_pipeline.py \
    --data-dir data/raw/share \
    --questions "data/raw/share/質問回答/questions_valid.csv" \
    --run-name exp_ssfire_valid
done
```

- [ ] **Step 2: flip確認（no-harm）**

`exp_pivotagg_valid` 3本と質問単位で回答を突合し、既回収問（少なくともQ6/Q11/Q21）が全runバイト同一または改善のみであることを確認。悪化flipが1問でもあれば原因を特定するまで提出フローに進まない。

- [ ] **Step 3: official較正**

```bash
.venv/bin/python scripts/calibrate_judge.py experiments/exp_ssfire_valid_<最新のunixtime>.json
```

Expected: official mean が 0.3833（pivotagg単発基準）から悪化していないこと。判断は §2.3 の学びどおり mean 単独でなく問別ラベルで行う

- [ ] **Step 4: test発火プローブ（診断run）**

```bash
.venv/bin/python scripts/run_pipeline.py \
  --data-dir data/raw/share \
  --questions "data/raw/share/質問回答/questions_test.csv" \
  --run-name diag_ssfire_test --no-judge
```

診断JSONで以下を確認（回答の正解合わせはしない）:
- 前回診断（`diag_test_1783239219.json`）でmissing_textだったspreadsheet_state 23問のうち、何問で `retrieved_sources` に名指しファイル由来のチャンク/構造化locationが現れたか
- Q2/Q82型（スケジュール×ハイライト）で `structured_spreadsheet_state` 経路が発火しているか（gate_reasonの変化）

- [ ] **Step 5: 記録とコミット**

作業ログ（実測内訳・flip表・較正結果・発火プローブ結果）を書き、run JSON証跡とともにコミット。plan_0703 §2系に実験行を追記。提出判断（`--runs 3` 生成→zip）はユーザーと相談

---

## Self-Review（実施済み）

1. **Spec coverage**: §2 C1（ファイル名スコープ）→ Task 1+2（検索側）/Task 3（ビルダー側の絞り）。§3 C2（highlight_cells/schedule_tasks接続）→ Task 3+4（schedule_tasksの行データは`dominant_row_fill`と`values`を持ち、highlight_cellsのセル単位データより行→タスク名の回答に直接適合するため、schedule_tasksを主データ源とする。highlight_cellsはスケジュール系以外のxlsxセル質問向けで、本ブロックの対象23問の実測ではスケジュール系が支配的 — 不足が出たら追補タスク）。§4 検証 → Task 5。§1 成功基準 → Task 5 Step 2-4
2. **Placeholder scan**: なし（全ステップにコード・コマンド・期待値を記載）
3. **Type consistency**: `extract_file_names`/`matches_file_name` はTask 1定義とTask 2/3の利用で署名一致。`_schedule_highlight_docs(question, rows)` はTask 3定義とTask 4の呼び出しで一致
