# 短答「値のみ」実験＋spreadsheet_state強化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> コミット前に `/step-review`（`.claude/skills/step-review`）を挟む運用。生成経路・スキャナ・構造化パスはsonnetでレビュー。

**Goal:** (A) Q17/Q18型の「ゲート通過したのにofficial Incorrect」を解消する短答フォーマット実験（`plan_0703.md` §2.2 学び3）、(B) test最大勢力 spreadsheet_state（21問）のフィルタ条件・Pivot質問を、XLSXのXMLから決定的に抽出したデータで回答可能にする（next-steps §3先頭）。

**Architecture:** (A)はSYSTEM_PROMPTのルール6強化＋N=3多数決＋official較正で採否判定。(B)は `scan_train_xlsx_xml.py` を拡張して①autoFilterの**フィルタ条件そのもの**（filterColumn/filter val）と非表示行数、②Pivot等の小型シートの全セル値、をartifactsに出力し、`build_spreadsheet_state_context` から決定的コンテキスト（フィルタ条件文・Pivot表のargmax行）として生成器へ渡す。

**Tech Stack:** Python 3.12 (`.venv/bin/python`), pytest, zipfile/ElementTree（xlsx XML直読み・API不使用）, Anthropic API（valid評価時のみ）

## Global Constraints

- 回答は1000トークン以内（`CLAUDE.md`）。
- 特定の質問・案件・ファイル名・正解のハードコード禁止（`competition.md`）。列名・シート名への分岐も禁止（データから汎用導出のみ）。
- `artifacts/` は手編集禁止。変更はスキャナの修正→再生成（`.venv/bin/python scripts/scan_train_xlsx_xml.py`、決定的・API不使用）で行い、再生成後のjsonlをコミットする（`AGENTS.md`）。
- テストは決定的に: LLMは`_call_llm()`オーバーライドで排除。スキャナのテストは合成xlsx（zip+XML）fixtureで行い実データに依存しない。
- 全テスト `.venv/bin/pytest tests/ -v` 全件PASS（現在297件）。
- **実験の採否判定はmean単独禁止**（`plan_0703.md` §2.2 学び2）: N=3多数決＋不安定問一覧＋raw_answer読み＋（プロンプト変更時は）official較正1本で判断。**local Incorrectゼロ維持を最優先で確認**。
- しきい値（threshold=0.4）は不変（Phase 5まで温存）。
- コミットメッセージ末尾: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## 前提となる既存コードの事実（実装者向け・2026-07-04実測）

- **Q6/Q11/Q21（valid spreadsheet_state 3問）が全てMissing**の原因はルーティングではなくデータ欠落。classifier（`src/utils/question_classifier.py`）は「フィルター/フィルタ/ピボット/pivot/Pivot/PivotTable」で`spreadsheet_state`タグを付け、`Pipeline._process_structured`が`build_spreadsheet_state_context`を呼ぶ配線は機能している。
- **東都 train.xlsx のautoFilter XMLにはフィルタ条件が保存されている**（実測: `<filterColumn colId="1"><filters><filter val="Male"/></filters></filterColumn>` ＋ colId=3 val="India" ＋ colId=9 val="2"、hidden行11,413）。`colId`は**フィルタ範囲の左端列を0とする相対位置**。ヘッダ名はフィルタ範囲先頭行のセル値から解決する。
- **かえで総合病院 train.xlsx は読める**（Pivotシート1,907セル、trainシート42,012セル。next-steps §3の「ファイル破損failures=1」は古い情報 — `train_xlsx_failures.jsonl`は現在空）。Pivotシート規模: かえで A3:K213（211行×11列）、青葉バイオ172セル。
- `scripts/scan_train_xlsx_xml.py` の `scan_sheet(zf, workbook_path, sheet, shared_strings, fills, style_fills) -> (meta, formula_cells, highlights)` が1シートを走査。**現在セル値はformula/highlight行にしか出力されない**（メタにcell_count等のみ）。`auto_filter`は`meta["auto_filter_ref"]`として参照のみ取得済み（scan_sheet冒頭、セルループの前）。`cell_value(cell, shared_strings)`・`NS`（namespace dict）・`read_xml`等のヘルパーあり。`main()`は`target_workbooks()`（`03.データ/train.xlsx`）を走査し `write_jsonl` で artifacts へ出力。
- `src/structured/artifact_store.py` の `StructuredArtifactStore.from_artifacts_dir(artifacts_dir)` がkind別jsonlを読み、`project_name`でグループ化。アクセサは `train_xlsx_sheets_for(project_name)` 等（76行の小さいファイル。新kindは既存パターンに合わせて追加）。
- `src/retriever/structured_context.py` の `build_spreadsheet_state_context(question, project_name, store)`: ①ハイライト質問→`train_xlsx_highlight_blocks_for`、②フィルタ質問（`_requests_filter_condition`）→`spreadsheet_sheets_for`（**train.xlsx非対応**・ヘッダと非表示行番号のみで条件を導けない）、③スケジュール行マッチ。
- **NFC/NFD**: artifacts内の`project_name`はNFD。`store`はartifact由来の`project_name`（NFD）でルックアップされるため既存パスは一貫しているが、**テストfixtureや新コードで文字列比較を足す場合はNFC正規化してから比較**する（このリポジトリで3回起きた事故パターン）。
- 生成器の`_build_context`は各docのtextを**800字で切り詰める**。長い表を1 docに入れない設計にすること。
- 実験手順: `for i in 1 2 3; do .venv/bin/python scripts/run_pipeline.py --data-dir "data/raw/share/共有ドライブ" --questions "data/raw/share/質問回答/questions_valid.csv" --run-name <名前>; done`（1run約2分）→ `scripts/majority_eval.py <前グループ3run> --vs <新3run>`。現行比較基準グループ: `experiments/flipfix_direct_valid_1783140559/1783140680/1783140801.json`（多数決mean 0.1333）。official較正: `scripts/calibrate_judge.py <run.json>`（OpenAI 30問）。
- SYSTEM_PROMPTの現ルール6（`641e858`で追加）: 「設問が特定の用語・数値・名称・章番号など短い事実を問う場合、文書中の表記をそのまま使って回答の冒頭で短く直答し、必要な補足はその後に続けること（…）」。今回の実験Aはこの「補足はその後に続ける」を「answerには値のみ・補足はreasoningへ」に変える。

---

### Task 1: 実験A — 短答系answerの「値のみ」化

Q18は「3章です。…説明…」がofficial Incorrect（正解「3」）。official judgeの数値規則は「単位・接尾辞の違いは同一視」なので、answerフィールドを**回答そのものだけ**にし説明をreasoningへ移す。

**Files:**
- Modify: `src/generator/answer_generator.py`（SYSTEM_PROMPTルール6のみ）
- Test: `tests/test_generator.py`（退行ガード更新）

- [ ] **Step 1: 退行ガードテストを更新（失敗させる）**

`tests/test_generator.py` の `test_system_prompt_requires_direct_answer_with_document_wording` に1アサーション追加:

```python
    def test_system_prompt_requires_direct_answer_with_document_wording(self) -> None:
        """短答系設問への直答ルール（文書表記を言い換えない・説明はreasoningへ）がプロンプトから消えていない。"""
        assert "言い換えない" in SYSTEM_PROMPT
        assert "reasoning" in SYSTEM_PROMPT.split("【重要ルール】")[1].split("【出力形式】")[0]
```

Run: `.venv/bin/pytest tests/test_generator.py -v -k direct_answer` → Expected: FAIL（現ルール6は重要ルール節に"reasoning"を含まない）

- [ ] **Step 2: SYSTEM_PROMPTルール6を差し替え**

```python
6. 設問が特定の用語・数値・名称・章番号など短い事実を問う場合、"answer" には文書中の表記を
   そのまま使った回答そのもの（値・用語・短い名詞句）だけを入れ、説明文を続けないこと。
   計算過程・根拠の説明は "reasoning" に書く（文書の用語を別の言葉に言い換えない。
   採点は正解表記との一致で行われるため、answerに余計な文を足すと不一致になる）。
   列挙を求める設問では、求められた要素だけをカンマ区切りで並べる。
```

Run: `.venv/bin/pytest tests/ -v` → Expected: 全件PASS

- [ ] **Step 3: N=3実験＋official較正**

```bash
for i in 1 2 3; do
  .venv/bin/python scripts/run_pipeline.py \
    --data-dir "data/raw/share/共有ドライブ" \
    --questions "data/raw/share/質問回答/questions_valid.csv" \
    --run-name expA_valueonly_valid
done
.venv/bin/python scripts/majority_eval.py \
  experiments/flipfix_direct_valid_1783140559.json experiments/flipfix_direct_valid_1783140680.json experiments/flipfix_direct_valid_1783140801.json \
  --vs experiments/expA_valueonly_valid_*.json
.venv/bin/python scripts/calibrate_judge.py experiments/expA_valueonly_valid_<最初のts>.json
```

採否判定（Global Constraints準拠。特に見る点）:
- official較正でQ8/Q18/Q27のofficialラベルが悪化していないか。**Q18がofficial Incorrect→Perfect/Missingに動いたか**（狙い）
- local Incorrectゼロ維持・多数決の悪化がjudgeノイズでないことをraw_answerで確認
- 列挙系（Q20等の安定Perfect）が壊れていないか
- 不採用なら`git restore`でrevertし、run JSONのみ証跡コミット

- [ ] **Step 4: step-review（sonnet・生成経路）→Commit**

```bash
git add src/generator/answer_generator.py tests/test_generator.py experiments/expA_valueonly_valid_*.json experiments/judge_calibration_*.json
git commit -m "実験A: 短答系answerを値のみに（説明はreasoningへ移動、official不一致対策）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

（不採用の場合はメッセージを「実験A: 値のみ化は不採用（負の結果を記録）」とし、コードはrevert済み・runのみadd）

---

### Task 2: スキャナ拡張 — フィルタ条件・非表示行数・小型シートセルの抽出

`scan_train_xlsx_xml.py` に3つの出力を追加する: ①`filter_columns`（autoFilterの条件をヘッダ名付きで）、②`hidden_row_count`、③小型シート（非train・値セル5000以下）の全セル値ダンプ `train_xlsx_small_sheet_cells.jsonl`。

**Files:**
- Modify: `scripts/scan_train_xlsx_xml.py`
- Create: `tests/test_scan_train_xlsx.py`
- Regenerate: `artifacts/train_xlsx_sheets.jsonl`（filter_columns/hidden_row_count付きに）、`artifacts/train_xlsx_small_sheet_cells.jsonl`（新規）

**Interfaces:**
- Produces: `train_xlsx_sheets.jsonl` の各行に `filter_columns: [{"col_id": int, "header": str|None, "values": [str], "custom": [{"operator": str, "val": str}]}]` と `hidden_row_count: int` を追加。新artifact `train_xlsx_small_sheet_cells.jsonl` 各行 = `{"source_path", "project_name", "file_name", "sheet_name", "cell", "row": int, "value"}`（Task 3が消費）
- 小型シートの判定: `sheet["name"] != "train"` かつ 値セル数（value非None）≤ 5000

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_scan_train_xlsx.py`（合成xlsxをzipで組み立てる。実データ非依存）:

```python
"""scan_train_xlsx_xml のフィルタ条件・小型シートセル抽出のテスト（合成xlsx使用）。"""
from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "scan_train_xlsx_xml",
    Path(__file__).parent.parent / "scripts" / "scan_train_xlsx_xml.py",
)
scanner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scanner)

_WORKBOOK = """<?xml version="1.0"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="train" sheetId="1" r:id="rId1"/><sheet name="Pivot" sheetId="2" r:id="rId2"/></sheets>
</workbook>"""

_RELS = """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>"""

_SHARED = """<?xml version="1.0"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="4" uniqueCount="4">
<si><t>gender</t></si><si><t>country</t></si><si><t>Male</t></si><si><t>層</t></si>
</sst>"""

# trainシート: ヘッダ行(A1=gender,B1=country) + フィルタ(colId=0 val=Male) + hidden行2つ
_SHEET_TRAIN = """<?xml version="1.0"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:B4"/>
<sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
<row r="2" hidden="1"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>10</v></c></row>
<row r="3" hidden="1"><c r="A3" t="s"><v>2</v></c><c r="B3"><v>20</v></c></row>
<row r="4"><c r="A4" t="s"><v>2</v></c><c r="B4"><v>30</v></c></row>
</sheetData>
<autoFilter ref="A1:B4"><filterColumn colId="0"><filters><filter val="Male"/></filters></filterColumn></autoFilter>
</worksheet>"""

# Pivotシート: 小型（値セル4個）
_SHEET_PIVOT = """<?xml version="1.0"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:B2"/>
<sheetData>
<row r="1"><c r="A1" t="s"><v>3</v></c><c r="B1"><v>1.5</v></c></row>
<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>2.5</v></c></row>
</sheetData>
</worksheet>"""

_STYLES = """<?xml version="1.0"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<cellXfs count="1"><xf fillId="0"/></cellXfs>
</styleSheet>"""


def _make_xlsx(tmp_path: Path) -> Path:
    # 実データと同じ相対構造（<project>/03.データ/train.xlsx）にする
    path = tmp_path / "プロジェクト" / "テスト案件" / "03.データ" / "train.xlsx"
    path.parent.mkdir(parents=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/workbook.xml", _WORKBOOK)
        zf.writestr("xl/_rels/workbook.xml.rels", _RELS)
        zf.writestr("xl/sharedStrings.xml", _SHARED)
        zf.writestr("xl/styles.xml", _STYLES)
        zf.writestr("xl/worksheets/sheet1.xml", _SHEET_TRAIN)
        zf.writestr("xl/worksheets/sheet2.xml", _SHEET_PIVOT)
    return path


def _scan_all(path: Path):
    with zipfile.ZipFile(path) as zf:
        shared = scanner.load_shared_strings(zf)
        fills = scanner.load_fills(zf)
        style_fills = scanner.load_cell_style_fills(zf)
        results = [
            scanner.scan_sheet(zf, path, sheet, shared, fills, style_fills)
            for sheet in scanner.sheet_map(zf)
        ]
    return results


def test_filter_columns_with_header_and_hidden_count(tmp_path):
    results = _scan_all(_make_xlsx(tmp_path))
    train_meta = results[0][0]
    assert train_meta["sheet_name"] == "train"
    assert train_meta["hidden_row_count"] == 2
    fc = train_meta["filter_columns"]
    assert len(fc) == 1
    assert fc[0]["col_id"] == 0
    assert fc[0]["header"] == "gender"
    assert fc[0]["values"] == ["Male"]


def test_small_sheet_cells_dumped_for_non_train_only(tmp_path):
    results = _scan_all(_make_xlsx(tmp_path))
    train_small = results[0][3]
    pivot_small = results[1][3]
    assert train_small == []  # trainシートはダンプしない
    assert {c["cell"] for c in pivot_small} == {"A1", "B1", "A2", "B2"}
    assert all(c["sheet_name"] == "Pivot" for c in pivot_small)
    assert [c for c in pivot_small if c["cell"] == "A1"][0]["value"] == "層"
    assert [c for c in pivot_small if c["cell"] == "A1"][0]["row"] == 1
```

（`scan_sheet`の戻り値を4要素タプル `(meta, formula_cells, highlights, small_cells)` に拡張する前提。既存の呼び出し元`main()`も合わせて直す。`_make_xlsx`のパスが`workbook_path.relative_to(ROOT)`と衝突する場合は、`scan_sheet`の`source_path`算出を`try/except ValueError`でリポジトリ外パスは`str(path)`にフォールバックさせる — `src/utils/paths.py`の`to_repo_relative`と同じ方針）

Run: `.venv/bin/pytest tests/test_scan_train_xlsx.py -v`
Expected: FAIL（`hidden_row_count`キー無し / 戻り値3要素）

- [ ] **Step 2: 実装**

`scripts/scan_train_xlsx_xml.py` の `scan_sheet` に追加（既存コードの該当位置に挿入）:

(a) メタ初期化に2キー追加: `"filter_columns": [], "hidden_row_count": 0,`

(b) `auto_filter` 取得直後（セルループ前）にフィルタ条件をパース:

```python
    filter_header_row = None
    filter_start_col = 0
    if auto_filter is not None:
        ref = auto_filter.attrib.get("ref") or ""
        m = re.match(r"([A-Z]+)(\d+):", ref)
        if m:
            filter_start_col = col_letters_to_index(m.group(1))  # A=0
            filter_header_row = int(m.group(2))
        for fc in auto_filter.findall("main:filterColumn", NS):
            col_id = int(fc.attrib.get("colId", "0"))
            values = [f.attrib.get("val") for f in fc.findall("main:filters/main:filter", NS)]
            customs = [
                {"operator": cf.attrib.get("operator", "equal"), "val": cf.attrib.get("val")}
                for cf in fc.findall("main:customFilters/main:customFilter", NS)
            ]
            meta["filter_columns"].append(
                {"col_id": col_id, "header": None, "values": values, "custom": customs}
            )
```

ファイル冒頭に`import re`（無ければ）と、セル参照分解ヘルパーを追加:

```python
_REF_RE = re.compile(r"([A-Z]+)(\d+)")


def col_letters_to_index(letters: str) -> int:
    """'A'→0, 'B'→1, ... 'AA'→26"""
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def split_ref(ref: str) -> tuple[int, int] | None:
    """'B12' → (col_index=1, row=12)"""
    m = _REF_RE.fullmatch(ref)
    if not m:
        return None
    return col_letters_to_index(m.group(1)), int(m.group(2))
```

(c) セルループ内で「ヘッダ行の値」「hidden行数」「小型シート用セル」を収集。ループ前に:

```python
    header_values: dict[int, Any] = {}
    small_cells: list[dict[str, Any]] = []
    is_train_sheet = sheet["name"] == "train"
    meta["hidden_row_count"] = sum(
        1 for r in root.findall(".//main:row", NS) if r.attrib.get("hidden") == "1"
    )
```

ループ内（`scanned_cell_count += 1` の後）に:

```python
        parsed = split_ref(ref)
        if parsed is not None:
            col_idx, row_num = parsed
            if filter_header_row is not None and row_num == filter_header_row:
                header_values[col_idx] = value
            if not is_train_sheet and value is not None:
                small_cells.append({
                    "source_path": meta["source_path"],
                    "project_name": meta["project_name"],
                    "file_name": meta["file_name"],
                    "sheet_name": meta["sheet_name"],
                    "cell": ref,
                    "row": row_num,
                    "value": value,
                })
```

ループ後（`meta["cell_count"] = ...` の後）:

```python
    for fc in meta["filter_columns"]:
        fc["header"] = header_values.get(filter_start_col + fc["col_id"])
    if len(small_cells) > 5000:
        small_cells = []  # 大きすぎるシートはダンプしない（コンテキスト用途外）
    return meta, formula_cells, highlights, small_cells
```

(d) `main()`: `scan_sheet`の受け取りを4要素にし、`small_cells_out`に集約して最後に
`write_jsonl(ARTIFACTS / "train_xlsx_small_sheet_cells.jsonl", small_cells_out)` を追加（既存のwrite_jsonl群と同じ場所・変数名は既存に合わせる）。

Run: `.venv/bin/pytest tests/test_scan_train_xlsx.py -v` → Expected: PASS (2 passed)

- [ ] **Step 3: artifactsを再生成して実データ確認**

```bash
.venv/bin/python scripts/scan_train_xlsx_xml.py
```

Expected: エラーなし。確認（NFC正規化を忘れない）:
- `train_xlsx_sheets.jsonl` の東都trainシート行に `filter_columns` 3件（header付き: colId 1/3/9のヘッダ名が実列名で埋まる）と `hidden_row_count: 11413`
- `train_xlsx_small_sheet_cells.jsonl` が生成され、かえでPivot（1907件）・青葉バイオPivot（172件）を含む
- `train_xlsx_failures.jsonl` が空のまま

- [ ] **Step 4: 全テスト→step-review（sonnet・データ抽出）→Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add scripts/scan_train_xlsx_xml.py tests/test_scan_train_xlsx.py artifacts/train_xlsx_sheets.jsonl artifacts/train_xlsx_small_sheet_cells.jsonl
git commit -m "スキャナ拡張: autoFilter条件・非表示行数・小型シートセルをartifacts化

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 構造化コンテキスト接続 — フィルタ条件文とPivot表のargmax行

**Files:**
- Modify: `src/structured/artifact_store.py`（新kindアクセサ）
- Modify: `src/retriever/structured_context.py`（`build_spreadsheet_state_context`拡張）
- Test: `tests/test_structured_context.py`（既存があれば追記、無ければ新規）

**Interfaces:**
- Consumes: Task 2の `filter_columns` / `hidden_row_count` / `train_xlsx_small_sheet_cells.jsonl`
- Produces:
  - `StructuredArtifactStore.small_sheet_cells_for(project_name) -> list[dict]`（既存アクセサ群と同パターン。`from_artifacts_dir`のkind列挙に `train_xlsx_small_sheet_cells` を追加）
  - `build_spreadsheet_state_context` がフィルタ質問で train.xlsx の**条件文doc**を、Pivot系質問（最も高い/低い）で**argmax/argmin行doc**を返す

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_structured_context.py` に追記（fakeのstoreは`StructuredArtifactStore(by_kind_and_project={...})`を直接組む。既存テストの組み方に合わせる）:

```python
def _store(kind_data: dict[str, list[dict]]) -> StructuredArtifactStore:
    by_kind = {kind: {"テスト案件": rows} for kind, rows in kind_data.items()}
    return StructuredArtifactStore(by_kind_and_project=by_kind)


def test_filter_condition_from_train_xlsx_filter_columns():
    store = _store({
        "train_xlsx_sheets": [{
            "source_path": "data/raw/x/train.xlsx", "file_name": "train.xlsx",
            "sheet_name": "train", "auto_filter_ref": "A1:J100", "hidden_row_count": 90,
            "filter_columns": [
                {"col_id": 1, "header": "gender", "values": ["Male"], "custom": []},
                {"col_id": 3, "header": "country", "values": ["India"], "custom": []},
            ],
        }],
    })
    docs = build_spreadsheet_state_context(
        "train.xlsxのtrainシートでフィルターで抽出されている条件を教えてください。", "テスト案件", store)
    assert len(docs) == 1
    text = docs[0].document.text
    assert "gender" in text and "Male" in text
    assert "country" in text and "India" in text
    assert "90" in text  # 非表示行数


def test_filter_condition_renders_custom_filters():
    store = _store({
        "train_xlsx_sheets": [{
            "source_path": "data/raw/x/train.xlsx", "file_name": "train.xlsx",
            "sheet_name": "train", "auto_filter_ref": "A1:B10", "hidden_row_count": 5,
            "filter_columns": [
                {"col_id": 0, "header": "age", "values": [],
                 "custom": [{"operator": "greaterThan", "val": "30"}]},
            ],
        }],
    })
    docs = build_spreadsheet_state_context("フィルタの条件は？", "テスト案件", store)
    assert "age" in docs[0].document.text
    assert "greaterThan" in docs[0].document.text and "30" in docs[0].document.text


def test_pivot_argmax_row_selected():
    """「最も高い」質問で、質問に現れる列見出しのargmax行がdoc化される。"""
    cells = []
    header = {"A3": "層", "B3": "平均 / ALP", "C3": "平均 / bmi"}
    rows = {4: ("20代", "10.5", "1.0"), 5: ("30代", "99.9", "2.0"), 6: ("40代", "50.0", "3.0")}
    for cell, v in header.items():
        cells.append({"sheet_name": "Pivot", "file_name": "train.xlsx",
                      "source_path": "data/raw/x/train.xlsx", "cell": cell, "row": 3, "value": v})
    for row, (label, alp, bmi) in rows.items():
        for col, v in zip("ABC", (label, alp, bmi)):
            cells.append({"sheet_name": "Pivot", "file_name": "train.xlsx",
                          "source_path": "data/raw/x/train.xlsx", "cell": f"{col}{row}", "row": row, "value": v})
    store = _store({"train_xlsx_small_sheet_cells": cells})
    docs = build_spreadsheet_state_context(
        "PivotシートでALPの平均が最も高いものの抽出条件は？", "テスト案件", store)
    assert len(docs) >= 1
    text = docs[0].document.text
    assert "30代" in text          # argmax行のラベル
    assert "99.9" in text
    assert "平均 / ALP" in text    # どの列で判定したか


def test_pivot_argmax_no_matching_column_returns_nothing():
    store = _store({"train_xlsx_small_sheet_cells": [
        {"sheet_name": "Pivot", "file_name": "train.xlsx", "source_path": "x",
         "cell": "A1", "row": 1, "value": "層"},
    ]})
    docs = build_spreadsheet_state_context("XYZの平均が最も高いのは？", "テスト案件", store)
    assert docs == []
```

Run: `.venv/bin/pytest tests/test_structured_context.py -v` → Expected: 新規4件FAIL

- [ ] **Step 2: artifact_storeにアクセサ追加**

`src/structured/artifact_store.py`: `from_artifacts_dir`のkind列挙（既存の読み込みリスト）に `"train_xlsx_small_sheet_cells"` を追加し、アクセサを既存パターンで:

```python
    def small_sheet_cells_for(self, project_name: str) -> list[dict]:
        return self._get("train_xlsx_small_sheet_cells", project_name)
```

- [ ] **Step 3: structured_contextの実装**

`src/retriever/structured_context.py` に追加:

```python
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
        # 質問に現れるトークンを含む列（ラベル列=最左は除く）
        label_col = min(headers)
        target_cols = [
            col for col, h in headers.items()
            if col != label_col and h and any(
                len(tok) >= 2 and tok in question_nfc
                for tok in re.split(r"[\s/／・]+", unicodedata.normalize("NFC", str(h)))
            )
        ]
        numeric_cols = [c for c in headers if c != label_col]
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
        pick = (max if want_max else min)(data_rows, key=lambda r: float(grid[r][col]))
        lines = [
            f"シート: {sheet_name}（Pivot集計表・xlsxセル値から機械抽出）",
            f"判定列: {headers[col]}",
            f"ヘッダ行: " + ", ".join(f"{c}={v}" for c, v in sorted(headers.items())),
            f"{'最大' if want_max else '最小'}の行: "
            + ", ".join(f"{headers.get(c, c)}={grid[pick].get(c)}" for c in sorted(grid[pick])),
        ]
        docs.append(Document(
            text="\n".join(lines), source_path=Path(source),
            location=f"sheet_{sheet_name}_row_{pick}",
        ))
    return docs


def _is_number(v: Any) -> bool:
    try:
        float(str(v))
        return True
    except (TypeError, ValueError):
        return False
```

（ファイル冒頭に `import unicodedata` と `from typing import Any` を追加。`re`は既存import）

`build_spreadsheet_state_context` に2ブロック追加:

```python
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
        for doc in _pivot_argmax_docs(question, store.small_sheet_cells_for(project_name)):
            docs.append(ScoredDocument(document=doc, score=1.0, retrieval_method="structured_spreadsheet_state"))
```

（既存のフィルタブロック（spreadsheet_sheets_for）は残す — スケジュール等の非train xlsx用。追加位置は既存フィルタブロックの直前）

Run: `.venv/bin/pytest tests/test_structured_context.py -v` → Expected: PASS

- [ ] **Step 4: 実データスモーク**

```bash
.venv/bin/python - <<'EOF'
import sys, unicodedata
sys.path.insert(0, ".")
from pathlib import Path
from src.structured.artifact_store import StructuredArtifactStore
from src.retriever.structured_context import build_spreadsheet_state_context

store = StructuredArtifactStore.from_artifacts_dir(Path("artifacts"))
for name in store.project_names():
    n = unicodedata.normalize("NFC", name)
    if "東都" in n:
        docs = build_spreadsheet_state_context(
            "東都人材プラットフォームのtrain.xlsxにおいて、trainシートでフィルターで抽出されている条件を教えてください。",
            name, store)
        print("Q11型:", [d.document.text for d in docs])
    if "かえで" in n:
        docs = build_spreadsheet_state_context(
            "train.xlsx内の PivotTable で集計されている表から、ALPの平均が最も高いものの抽出条件を教えてください。",
            name, store)
        print("Q6型:", [d.document.text[:200] for d in docs])
EOF
```

Expected: Q11型でgender=Male/country=India等の条件文doc、Q6型でALP列のargmax行doc（かえでPivotの実ヘッダ構造に依存 — 出なければヘッダ検出ロジックを実データで確認し、判明した構造をテストfixtureに反映して直す。**directに答えをハードコードしない**）

- [ ] **Step 5: 全テスト→step-review（sonnet・構造化パス）→Commit**

```bash
git add src/structured/artifact_store.py src/retriever/structured_context.py tests/test_structured_context.py
git commit -m "spreadsheet_state: フィルタ条件文とPivot argmax行を構造化コンテキストとして接続

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 実験B — valid N=3で採否判定

- [ ] **Step 1: N=3実験**

```bash
for i in 1 2 3; do
  .venv/bin/python scripts/run_pipeline.py \
    --data-dir "data/raw/share/共有ドライブ" \
    --questions "data/raw/share/質問回答/questions_valid.csv" \
    --run-name expB_ssstate_valid
done
.venv/bin/python scripts/majority_eval.py \
  <Task1採用時: experiments/expA_valueonly_valid_*.json / 不採用時: flipfix_direct 3run> \
  --vs experiments/expB_ssstate_valid_*.json
```

見る点: Q6/Q11/Q21の多数決ラベル（目標: Missing→Perfect側）、**Incorrect素通りが増えていないか**（決定的コンテキストでも生成が間違えれば-1。増えたら該当doc renderを疑う）、他タイプへの悪影響なし（構造化パスの発火条件が広がりすぎていないか）。

- [ ] **Step 2: 判定・記録用の生データ確認**

flipで動いた問のraw_answer・retrieved_sources（`structured_spreadsheet_state`が使われたか）を確認。判定基準はGlobal Constraints。不採用ならTask 3のコードをrevert（Task 2のartifacts拡張は無害なので残す）。

- [ ] **Step 3: Commit**

```bash
git add experiments/expB_ssstate_valid_*.json
git commit -m "実験B: spreadsheet_state構造化接続のvalid N=3実測（採否と根拠をメッセージに記載）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: 結果の記録と計画更新

- [ ] **Step 1**: `docs/plan/plan_0703.md` — §2.2の下に「2.3 短答値のみ＋spreadsheet_state（YYYY-MM-DD）」節を追記（実験A/Bの多数決before/after・official較正・採否・Q6/Q11/Q21の遷移）
- [ ] **Step 2**: `docs/plan/2026-07-04-next-steps.md` §2残課題①と§3 spreadsheet_stateのチェックボックス更新（**「かえで破損failures=1」の記述は誤りだったことも訂正**: 実測でPivot 1907セル読取可）
- [ ] **Step 3**: `docs/daily作業ログ/` に新規ログ（目的→結果→SHA→学び→残課題）
- [ ] **Step 4**: Commit

```bash
git add docs/plan/ "docs/daily作業ログ/"
git commit -m "短答値のみ＋spreadsheet_state強化の実測結果を記録

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review 済みの注意点（実装者向け）

1. **colIdは範囲相対**（フィルタ範囲がB1始まりならcolId=0はB列）。ヘッダ解決は必ず`filter_start_col + col_id`で行う。テストはA1始まりだが実装は開始列を足すこと。
2. **NFC/NFD**: artifactsのproject_name・source_pathはNFD。新しい文字列比較（列見出しトークン×質問）は両辺NFC正規化（`_pivot_argmax_docs`は実装済み。他に足すなら同様に）。
3. **_build_contextの800字制限**があるため、Pivot全行をdoc化しない。argmax行方式は「曖昧なら出さない」に倒す（誤答-1 > Missing 0。実験②の教訓: 防御を緩めない）。
4. **スキャナ戻り値の変更**は`main()`側の受け取りと同時に直す（タプル要素数ズレは静かに壊れない=即例外なのでテストで捕まる）。
5. 小型シートセルの上限5000は「コンテキスト用途」の線引き。白峰のSheet1〜3（4225セル×3）が入るが数MB程度で問題ない。
6. 実験A・Bは**独立にrevert可能**な構成（AはプロンプトのみFile、Bはstructured系のみ）。両方走らせてから一括判定しない — Aの採否を確定させてからBの実験を回す（1実験1変更）。
7. Task 2のartifacts再生成は**既存フィールドを消さない**（train_xlsx_highlight_blocks等の他ファイルはスキャナが同時に再出力する — diffで意図しない変化がないか`git diff --stat artifacts/`で確認してからadd）。
