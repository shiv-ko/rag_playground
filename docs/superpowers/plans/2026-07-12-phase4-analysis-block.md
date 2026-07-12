# Phase 4 analysis系ブロック実装計画

## 目的と範囲

`analysis_metrics` / `notebook_output` / `code_static` の主対象12問について、正解ラベルを参照せず、実データから再生成可能な決定的回答経路を追加する。巨大な万能registryは作らず、次の三種類に限定する。

1. `metrics.json`・設定JSONの構造化読取
2. Notebookのsource・text outputと元CSVを用いた相関計算
3. Python ASTによる定数・条件・実効デフォルト値の抽出

画像の軸目盛りが必要なtest Q56は本ブロックでは安全なMissingを維持する。列挙は完全性を機械確認できる場合だけ回答する。`question_labels.csv`と質問回答CSVはテスト期待値の作成・回答生成に使用しない。

## 最小設計

- artifactは`artifacts/analysis_records.jsonl`一つ。1行を1ソースファイルとし、`project_name`, `source_path`, `kind`, `payload`を保持する。
- `payload`はkind別固定: JSONは本文、Notebookはセルsource/text output、PythonはASTから得た代入・比較・呼出し、CSVは保持せず回答時に必要列だけ読む。
- 汎用演算は専用`AnalysisAnswerer`に限定する: JSON path参照、設定とコード既定値の合成、Notebook相関順位、元CSV相関、生成列とselected_columnsの集合積、2値の差。
- パターンに一意一致しない、参照ファイルが複数、対象列や集合の完全性を確定できない場合は`None`を返し、通常経路またはMissingへ委ねる。

## Task 1: analysis artifact生成基盤

**コミット:** `feat: build minimal analysis artifacts`

**変更ファイル**

- 新規 `scripts/build_analysis_artifacts.py`
- 新規 `src/structured/analysis_artifacts.py`
- 更新 `src/structured/artifact_store.py`
- 新規 `tests/test_analysis_artifacts.py`
- 生成 `artifacts/analysis_records.jsonl`

**REDテスト**

- NFD/NFCの案件名をNFCへ正規化する。
- `metrics.json` / `project_config.json`のJSON本文とsource pathを保持する。
- Notebookはcell番号、cell type、source、`stream`・`text/plain`出力を保持し、画像バイナリは保持しない。
- Pythonは`ast`で定数、単純代入、比較式、関数呼出しのキーワード引数を記録する。構文エラーはfailure行にして全体生成を止めない。
- 同一案件の外側metricsとproject内metricsが両方ある場合、pathを失わず区別する。

**実装**

- `04.分析`配下のみ走査し、対象拡張子を`.json/.ipynb/.py`へ限定する。
- JSONLはpath順の決定的出力とし、手編集禁止のヘッダ情報を各行へ含める。
- storeへ`analysis_records_for(project_name, kind=None)`を追加する。

**検証**

```bash
.venv/bin/pytest tests/test_analysis_artifacts.py -v
.venv/bin/python scripts/build_analysis_artifacts.py --data-dir "data/raw/share/共有ドライブ" --output artifacts/analysis_records.jsonl
git diff --check
```

## Task 2: JSON・ASTによる短答経路

**コミット:** `feat: answer analysis json and code questions`

**変更ファイル**

- 新規 `src/generator/analysis_answerer.py`
- 更新 `src/utils/question_classifier.py`
- 更新 `src/orchestrator/pipeline.py`
- 新規 `tests/test_analysis_answerer.py`
- 更新 `tests/test_pipeline.py`

**REDテスト**

- `sparse_output=model_key != "hist_gradient_boosting"`からFalseとなる値を返す。
- dtype候補と`nunique < limit`をASTから説明できる。演算子`<=`等へ決め打ちしない。
- configが空のとき、選択されたmodel branchのコード既定値とconfigの`random_state`を合成する。
- metricsの`model_params.max_depth`を取得する。
- `feature_selection.selected_columns`と、コードの`left__x__right`生成規則に一致する列の集合を完全列挙する。
- 同名候補が複数・branch不明・必須値欠落の場合は回答しない。

**実装**

- classifierへ限定的な`analysis_json` / `analysis_code`タグを追加する。
- `AnalysisAnswerer.answer(question, project, store)`で上記意図だけを扱う。
- 回答には参照artifactをsource docとして付与し、決定的回答は高confidenceとする。
- pipelineの構造化経路へ通常検索より前に接続する。

**対象見込み**

- valid Q4/Q28、test Q5/Q32/Q61/Q73。

**検証**

```bash
.venv/bin/pytest tests/test_analysis_answerer.py tests/test_pipeline.py -v
.venv/bin/pytest tests/ -v
git diff --check
```

## Task 3: Notebook output・相関計算経路

**コミット:** `feat: answer deterministic notebook correlations`

**変更ファイル**

- 更新 `src/generator/analysis_answerer.py`
- 新規 `src/structured/analysis_data.py`
- 更新 `src/utils/question_classifier.py`
- 新規 `tests/test_analysis_data.py`
- 更新 `tests/test_analysis_answerer.py`

**REDテスト**

- Notebook text outputの相関Seriesから「上位Nのうち最小」を数値順で決める。
- Notebook sourceが絶対相関上位Nをheatmap対象化している場合、同じCSV・target・Nで再計算し最小列を返す。
- 「目的変数と最も高い相関」はtarget自身と識別子列を除き、質問が絶対値を明記しない場合はNotebookの実処理（降順/絶対値）に従う。
- target/config/data pathのいずれかが不明、一意でない、CSVを安全に読めない場合は回答しない。
- 定数列NaNと欠損を除外し、同率は回答しない。

**実装**

- `analysis_data.py`はconfigからdata path・targetを解決し、必要列のみpandasで読む。
- Notebook出力を第一根拠、再計算を整合確認として用いる。出力がなくてもsourceに演算仕様が明示されていれば再計算可とする。
- ファイル名の`NB01_eda` / `01_eda`表記揺れを正規化して照合する。

**対象見込み**

- valid Q22/Q24、test Q4。test Q56は明示的に非発火。

**検証**

```bash
.venv/bin/pytest tests/test_analysis_data.py tests/test_analysis_answerer.py -v
.venv/bin/pytest tests/ -v
git diff --check
```

## Task 4: 複数成果物の数値差・表順位

**コミット:** `feat: answer deterministic analysis comparisons`

**変更ファイル**

- 更新 `src/generator/analysis_answerer.py`
- 更新 `src/parsers/office_parser.py`（表の行列境界が不足する場合のみ）
- 更新 `tests/test_analysis_answerer.py`
- 更新 `tests/test_parsers.py`（parser変更時のみ）

**REDテスト**

- 中間資料の詳細値とmetrics JSON値をsource別に一つずつ選び、`Decimal`で差を小数第6位へ丸める。
- F1降順表で指定モデルに次ぐ行のAccuracyを返す。列名・行境界・順位が全て確認できない場合は回答しない。
- 丸め済み表示値しかない場合、質問が「詳細値」を要求すれば回答しない。
- 同一指標候補が複数あり版・時点を解決できない場合は回答しない。

**実装**

- 既存OfficeParserの表テキストを優先利用する。行列境界が保持されない場合のみ最小拡張する。
- 比較ロジックを指標名、時点、モデル名、列名で一般化し、案件名や期待値を埋め込まない。

**対象見込み**

- valid Q27、test Q35。

**検証**

```bash
.venv/bin/pytest tests/test_analysis_answerer.py tests/test_parsers.py -v
.venv/bin/pytest tests/ -v
git diff --check
```

## Task 5: 実データ統合検証・採否

**コミット:** `test: verify phase4 analysis block`

**変更ファイル**

- 更新 `tests/test_analysis_answerer.py`（実データ存在時skip可能な回帰のみ）
- 更新 `docs/plan/2026-07-12-next-steps.md`
- 更新 `docs/plan/plan_0703.md`
- 新規 `docs/daily作業ログ/YYYYMMDD_HHMMSS.md`
- 実測時のみ `experiments/phase4_analysis_*.json`

**RED/回帰確認**

- 主対象12問についてanswer path、回答/Missing、根拠sourceを診断出力する。
- test Q56はMissingまたは既存の安全な画像経路のみであり、本経路が推測回答しない。
- 列挙回答は抽出集合件数と出力件数が一致する。
- 対象外質問のanswer pathと既存official結果に回帰がない。

**検証**

```bash
.venv/bin/pytest tests/ -v
.venv/bin/python scripts/run_pipeline.py --data-dir "data/raw/share/共有ドライブ" --questions "data/raw/share/質問回答/questions_valid.csv" --artifacts-dir artifacts --run-name phase4_analysis_valid
```

validはN=3で安定性を確認し、official較正で新規Incorrect 0を採否条件とする。対象問の過半がPerfect相当、列挙完全性確認済み、全テスト成功を完了条件とする。実測値・run名・最終コミットSHAを計画台帳とdailyログへ記録する。

## 各コミットのレビュー手順

各TaskでRED確認後に最小実装、対象テスト、全体テスト、`git diff --check`を実行する。コミット前にstep-reviewスキルで当該差分のみをサブエージェントレビューし、指摘を修正してからコミットする。次Taskは前Taskのコミット完了後に開始する。
