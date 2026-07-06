# Q21型 compact pivot回収（pivotCache再計算）実装指示書 — Codex向け

> 位置づけ: `plan_0703.md` §2.3 残課題①（2026-07-05更新版）。設計と実現可能性は
> **`docs/pivot_cache_recovery_poc.md` で確定済み**（PoCがQ21のGTと完全一致、9/9 pivotTableで0エラー）。
> 本指示書はそのPoCの本実装。参照実装は `scripts/poc_pivot_recompute.py`（動くコードとして読める）。
> レビューは `.claude/skills/step-review` テンプレートのセルフレビューを各コミット前に1周。
> 開発規約は `.codex/skills/dev-process.md`（TDD）。

## 実行環境・検証の約束（**前ブロックからの重要な変更**）

- テスト: `.venv/bin/pytest tests/ -v`（現在**311件**、全件PASS維持）
- **Codex環境はLLM APIに接続できない（前ブロックで確認済み）。valid N=3実験・official較正は
  実装完了後にClaude側が代行する**。Codexは以下の決定的検証のみ行い、実験は試みない:
  1. ユニットテスト（合成XML/合成rows）
  2. artifacts再生成と件数・内容のスポットチェック（後述Task 2）
  3. `scripts/poc_pivot_recompute.py` の出力との自己整合チェック（GTとの照合はしない —
     PoC出力と本実装出力が一致すれば十分。GT値をテストやコードに書かない）
- 実装が終わったら**コミットして停止し、Claudeに引き継ぐ**（実験名は `exp_pivotagg_valid` を予約）
- NFC/NFD: 実データのパス・案件名はNFD。**新しい文字列比較は必ず両辺 `unicodedata.normalize("NFC", ...)`**
  （このリポジトリで5回目の事故を起こさない。Task 2に既存の潜在バグ修正を含む）
- `artifacts/` は手編集禁止（スキャナで再生成。git管理対象なので再生成結果はコミットする）
- 競技規約: 特定の案件名・列名・正解値のハードコード禁止。テストのフィクスチャは**合成の列名**
  （Region/Category/Sales等）を使い、実データの列名（Attrition等）をテストに書かない
- 検索レイヤ（chunker/retriever）には**一切触れない**（実験Eの教訓: plan_0703 §2.3学び5。
  本ブロックは構造化パスのみで完結し、既存回答への影響ゼロが設計目標）

## 前提となる現状（2026-07-05、`508efbc`時点）

- valid Q21「…train.xlsxのPivotシートにおいて、平均月収が最も高い層の抽出条件を答えてください」は
  Missing（`gate_reason="missing_text"`）。Pivotシートはcompactレイアウト（インデント階層が
  シートセルからは復元不能）のため、既存の `_pivot_argmax_docs`（small_sheet_cells経由）は
  B2実験で**意図的に保守abstain**している
- PoCで確立した解法: **pivotシートの表示セルは読まず、`xl/pivotTables/pivotTable*.xml`（構造定義）＋
  `xl/pivotCache/`（元データのキャッシュ）から全グループの集計を再計算**する。
  罠10件（`<x>`参照vs生値、`x="-2"`除外、subtotal省略=sum、rowItems不使用ほか）は
  PoCレポート§4に列挙済み — **実装前に必ず§4を読むこと**
- 対象データ実測: 5プロジェクト・9 pivotTable（うち白峰の2つはrowFieldsが実質空の別パターン）

## 関連コードの事実（実装前に実物を確認）

- `scripts/poc_pivot_recompute.py`: 参照実装。`load_typed_relationships` / `parse_cache_fields` /
  `parse_cache_records` / `parse_pivot_table` / `aggregate` 相当のロジックが全て入っている
- `scripts/scan_train_xlsx_xml.py`: `target_workbooks()`（**line 328付近、`"03.データ" in p.parts` が
  NFC/NFD非対応の潜在バグ** — ソースのリテラルとNFDの実パスが不一致。現状は古い`__pycache__`で
  偶然動いている）。`main()`は5本のjsonlを `write_jsonl(ARTIFACTS / "...", rows)` で書く構造
- `src/structured/artifact_store.py`: `_ARTIFACT_FILES` dict（line 9〜）にkind→ファイル名を足し、
  `xxx_for(project_name)` アクセサを1つ足すだけ（`_get`がNFC正規化込みの引き当てを既にやる）
- `src/retriever/structured_context.py`:
  - `build_spreadsheet_state_context(question, project_name, store)` が spreadsheet_state タグの入口。
    ハイライト条件→フィルタ条件→`_pivot_argmax_docs`（line 410、small_sheet_cells）→…の順に
    質問ヒントごとのセクションが並ぶ
  - `_SUPERLATIVE_MAX` / `_SUPERLATIVE_MIN`（最上級表現の既存定数）と
    `_pivot_argmax_docs`（compact検出時はabstainする既存実装）がある
- pipelineの構造化ルート: タグ付き質問は `_process_structured` → state/officeビルダー。
  ビルダーが空listを返せば従来通りフォールバック（=非対象質問への影響なし）

---

## Task 1: `src/parsers/pivot_cache.py`（新規） — コアロジックの移植

PoCから移植し、**テスト可能な形に分離**する: XMLパース関数は `xml.etree.ElementTree.Element` または
XML文字列を受け取り、zipファイルを直接要求しない。zip走査（`xl/pivotTables/pivotTable*.xml`列挙と
rel chain解決）は薄いラッパ関数1つに隔離する。

公開インターフェース（Task 2/4が使う）:
```python
@dataclass(frozen=True)
class PivotAggregate:
    sheet_name: str          # pivotTableが載っているシート名（rels経由で解決）
    pivot_table_name: str
    row_fields: list[str]
    data_field_name: str     # 例「平均 / MonthlyIncome」
    data_field_source: str   # 例「MonthlyIncome」
    subtotal: str            # average|sum|max|min|count等（省略時"sum"）
    n_groups: int
    argmax_labels: dict[str, str|int|float]
    argmax_value: float
    argmin_labels: dict[str, str|int|float]
    argmin_value: float

def extract_pivot_aggregates(xlsx_path: Path) -> list[PivotAggregate]:
    """1ワークブックの全pivotTable×全dataFieldの集計を返す。
    rowFieldsが実質空（x=-2のみ）／pageFieldsあり／隠しアイテムありのテーブルは
    保守側でスキップ（返さない）。"""
```

- TDD（`tests/test_pivot_cache.py` 新規。**合成XML文字列**でユニットテスト）:
  - `parse_cache_fields`: `count`属性つきsharedItems（辞書型）と、`count`なし
    `<sharedItems/>`（生値型）の判別
  - `parse_cache_records`: `<x v="1"/>`が辞書引きされ、`<n v="42"/>`が生値になる。`<m/>`はNone
  - `parse_pivot_table`: rowFields解決、`x="-2"`除外、subtotal省略→"sum"
  - `aggregate`: 合成レコード（列 Region/Category、値 Sales）でaverage→argmax/argmin。
    欠損None除外。rowFields空→空リスト（例外を出さない）
  - zipラッパ: `zipfile.ZipFile`をtmp_pathに合成して（pivotTable1.xml＋definition＋records＋
    relsの最小構成を文字列から書き込む）end-to-endで`extract_pivot_aggregates`が1件返す
- 全テストPASS → セルフレビュー → コミット

## Task 2: スキャナ拡張＋NFDバグ修正＋artifacts再生成

1. **先にNFDバグを直す**: `target_workbooks()`の `"03.データ" in p.parts` を両辺NFC正規化の比較に変更
   （例: `any(unicodedata.normalize("NFC", part) == unicodedata.normalize("NFC", "03.データ") for part in p.parts)`）。
   `find … -name "train.xlsx"` の実件数（9件）と `target_workbooks()` の件数が一致することを確認
   （**`__pycache__`に注意**: 検証時は `.venv/bin/python -B` か `find . -name __pycache__ -path "*scripts*"` の削除で
   フレッシュ実行を保証）
2. `main()`に pivot集計の収集を追加: 各workbookで `extract_pivot_aggregates()` を呼び、
   `artifacts/train_xlsx_pivot_aggregates.jsonl` に1行=1(project, sheet, pivotTable, dataField)で出力。
   スキーマはPoCレポート§5-2のJSON例に従う（`project_name`＋PivotAggregateの全フィールド）
3. スキャナ実行でartifacts再生成 → **検証**:
   - 新jsonlの行数が期待と一致（PoC実測: 青葉バイオ1・かえで8・ひがし丘7・青潮8 = **24行**。
     白峰の2テーブルはrowFields空でスキップされ0行）
   - `scripts/poc_pivot_recompute.py` を再実行し、argmax_labels/argmax_valueが新jsonlと一致（全行）
   - **既存5本のjsonlがNFD修正後も差分ゼロ**（`git diff artifacts/`で確認。
     もし差分が出たら「pycacheで偶然動いていた」前提が違ったということなので、差分内容を
     作業ログに記録して相談）
- テスト: `target_workbooks`のNFC比較はパス合成のユニットテストを1本（tmp_pathにNFD名ディレクトリを
  作って検出できること）
- コミット（artifacts含む）

## Task 3: `StructuredArtifactStore` への接続（小タスク）

- `_ARTIFACT_FILES` に `"train_xlsx_pivot_aggregates": "train_xlsx_pivot_aggregates.jsonl"` を追加
- アクセサ `pivot_aggregates_for(self, project_name)` を既存アクセサと同形で追加
- テスト: tmp_pathのartifacts_dirに合成jsonlを置き、project_name（NFC/NFD両方）で引けること
- コミット（Task 4と同一コミットでも可）

## Task 4: `build_spreadsheet_state_context` にpivot集計セクションを追加

**挿入位置**: 既存の `_pivot_argmax_docs`（line 410付近）より**前**。新セクションがdocsを返したら
既存のcompact abstainには到達しない。返さなければ従来挙動に完全フォールバック（no-harm）。

**発火条件（全て満たす場合のみ）**:
1. 質問（NFC正規化後）に「Pivot」「ピボット」のいずれかを含む
2. `_SUPERLATIVE_MAX` または `_SUPERLATIVE_MIN` にマッチ（既存定数を再利用）
3. `store.pivot_aggregates_for(project_name)` に、**質問文中に `data_field_source` または
   `data_field_name` の正規化形が部分一致で見つかる行**がある（例: 質問「平均月収が最も高い」と
   `data_field_name="平均 / MonthlyIncome"` — 日本語質問と英語列名は一致しないことがあるので、
   `data_field_source`/`data_field_name` に加えて**term_registryの対訳があれば展開後の質問で照合**。
   `QueryExpander.expand_terms` 適用後の質問文字列を使うのが最短。どのdataFieldにも一致しなければ
   **候補が1つだけの場合に限り**その1つを使う — 複数候補で不一致なら空リスト＝保守側）

**レンダリング**（LLM生成へ渡すコンテキスト。直接回答はしない — 実験Dの意図ゲートの教訓）:
```
{file_name} の {sheet_name}（ピボットテーブル: {pivot_table_name}）
集計: {data_field_name}（{subtotal}）
最大のグループ: {field1} = {value1}、{field2} = {value2}、…（値: {argmax_value}）
最小のグループ: {field1} = {value1}、…（値: {argmin_value}）
```
（「A = B、…」の連結形はGT形式の逆算ではなく、フィルタ条件文（B実験・Q11）と同じ既存の
汎用レンダリング慣行。max/min両方を常に含め、質問の向きの解釈はLLMに委ねる）

- TDD（`tests/test_structured_context.py` に追記。既存のfake storeパターンに合わせる）:
  - 「Pivotシートで平均◯◯が最も高い層の抽出条件」型（合成列名Sales使用）→ コンテキストに
    `Region = 東、Category = A` 形式の行と値が含まれる
  - 最上級表現なし → 空（既存挙動）
  - dataField複数で質問と不一致 → 空
  - **既存テスト全PASS維持**（Q6/Q11型のフィルタ条件・ハイライトセクションに触れないこと）
- コミット

## Task 5: 引き継ぎ（Codexはここで停止）

1. `.venv/bin/pytest tests/ -v` 全件PASSを最終確認
2. 作業ログ `docs/daily作業ログ/YYYYMMDD_HHMMSS.md` を書く（実装サマリ・テスト件数・
   artifacts再生成の検証結果・判断に迷った点）
3. コミットして**停止**。valid N=3（`exp_pivotagg_valid`）・official較正・採否判定・提出判断は
   Claude側が実施する（見る点: Q21の遷移、Q6/Q11の無傷、既存回答のバイト同一性、
   official Incorrectの顔ぶれ不変）

## スコープ外（手を出さない）

- 白峰型（rowFields空）pivotの質問対応・pageFields/隠しアイテムの適用ロジック（検出スキップのみ）
- 検索レイヤ（chunker/retriever）全般 — 実験Eでrevert済み。触らない
- Q17/Q18の-1リスク、Q6のofficial表現問題、提出作業
