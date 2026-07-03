# データ戦略TODO

ベースライン実装とは別に進める、勝つためのデータ基盤バックログ。目的は「文書チャンク検索だけでは取れない設問」を、データ種別ごとの専用抽出・構造化・計算で取りに行くこと。

参照:

- [`data_strategy/`](./data_strategy/)
- [`strategy.md`](./strategy.md)
- [`todo_and_experiments.md`](./todo_and_experiments.md)

## 0. 前提方針

- これはベースライン構築タスクではない。ベースラインのBM25/RAGとは独立して、後から接続できる中間データ基盤を作る。
- 優先するのは、test 100問で出現が多く、機械的に高精度化できる領域。
- LLMに長い文書を読ませて推測させるのではなく、ファイル形式ごとの構造化抽出を先に行う。
- 数値問題・列挙問題は誤答コストが高いため、計算根拠や抽出完了性が確認できない場合はMissingに落とす。

## 1. 完了: 質問ラベリング表を作る

### 目的

どのデータ戦略が何問分の価値を持つかを定量化する。以降の実装優先度は、このラベル表を根拠に決める。

### 作るもの

`docs/question_labels.csv`

推奨カラム:

| カラム | 内容 |
|---|---|
| `split` | `valid` / `test` |
| `index` | 質問index |
| `question` | 質問文 |
| `primary_type` | 主能力ラベル |
| `secondary_types` | 複数ラベルを `;` 区切り |
| `source_section` | `00.提案` / `01.契約` / `02.計画` / `03.データ` / `04.分析` / `05.会議` / `06.報告書` / `社内管理` / `cross_project` |
| `answer_shape` | `single_text` / `list` / `number` / `money` / `date` / `diff` |
| `risk` | `low` / `medium` / `high` |
| `required_extractor` | 必要な専用抽出器 |
| `notes` | 判断メモ |

ラベル候補:

- `single_text`
- `office_style`
- `spreadsheet_state`
- `spreadsheet_calc`
- `image_graph`
- `code_static`
- `notebook_output`
- `analysis_metrics`
- `version_diff`
- `cross_project`
- `contract_rule`
- `internal_terms`
- `list_extraction`
- `numeric_exact`

### 完了条件

- [x] valid 30問、test 100問の全問にラベルが付いている。
- [x] `primary_type` が必ず1つ入っている。
- [x] `risk=high` の基準が明確になっている。
- [x] 各ラベルの件数集計が出せる。

### 初期ラベル結果

`scripts/build_question_labels.py` で初期ラベルを生成済み。出力は [`question_labels.csv`](./question_labels.csv)。

test 100問の主ラベル分布:

| primary_type | 件数 |
|---|---:|
| `spreadsheet_state` | 21 |
| `version_diff` | 11 |
| `internal_terms` | 11 |
| `contract_rule` | 10 |
| `office_style` | 9 |
| `spreadsheet_calc` | 9 |
| `cross_project` | 9 |
| `single_text` | 6 |
| `list_extraction` | 4 |
| `analysis_metrics` | 3 |
| `notebook_output` | 2 |
| `image_graph` | 2 |
| `code_static` | 2 |
| `numeric_exact` | 1 |

リスク分布:

| split | high | medium | low |
|---|---:|---:|---:|
| valid | 15 | 7 | 8 |
| test | 64 | 20 | 16 |

この結果から、次の実装優先度は `spreadsheet_extractor` が最上位。testで21問が主対象で、さらに `spreadsheet_calc` 9問にも波及する。

### 次に使う場面

- 実験優先度の決定。
- 専用抽出器の期待ゲイン見積もり。
- ベースライン結果の失敗分析。
- 「この設問はまだ能力外なのでMissing」の判定。

## 2. 完了: project / alias / document registry を作る

### 目的

質問文の略称・社内用語・資料種別から、正しい案件フォルダとファイル群に到達できるようにする。これは全データ戦略の土台。

### 作るもの

中間データ:

- `artifacts/project_registry.json`
- `artifacts/document_registry.json`
- `artifacts/term_registry.json`

最低限の項目:

`project_registry`

- 正式案件名
- 主略称
- 別名/短縮名
- 業界カテゴリ
- 契約方式
- 契約期間
- 顧客担当者
- DA側担当者

`document_registry`

- `source_path`
- `project_name`
- `section`
- `document_type`
- `file_name`
- `extension`
- `version_tag`
- `version_order`
- `date`
- `ids`

`term_registry`

- 略語
- 展開語
- 用途
- ルーティング先

重要な略語:

- `PP`: 提案書
- `CT`: 契約書
- `PLAN` / `PL`: 計画
- `MM`: 会議/中間資料
- `FR`: 最終報告
- `APR`: 決裁基準
- `FM`: 座席表
- `TG`: 目的変数
- `EXT`: 内線
- `ESTH`: 見込工数
- `ACTH`: 実績工数
- `RATE`: 単価

### 実装メモ

- 案件名リストは `プロジェクト/` 配下から動的に導出する。
- 社内用語集は辞書として構造化する。
- ファイル名から `old`, `v1`, `v2`, `v3`, `final`, `draft`, `r1`, `r2` を抽出する。
- 質問に出る略称が社内用語集にない場合でも、ファイル名・契約書・提案書から補完候補を作る。

### 完了条件

- [x] 全412ファイルに `project_name`, `section`, `document_type`, `version_tag` のいずれかが付く。
- [x] `KSS`, `AYM`, `MINAMINO`, `AOSHIO`, `AOBM`, `TOTO` などの質問中略称から候補案件を引ける。
- [x] `PP`, `CT`, `PL`, `FR`, `MM`, `APR`, `FM` から優先検索セクションを決められる。

### 初期レジストリ結果

`scripts/build_registries.py` を追加し、以下を生成済み。

- `artifacts/project_registry.json`
- `artifacts/document_registry.jsonl`
- `artifacts/term_registry.json`

生成結果:

| 項目 | 件数 |
|---|---:|
| projects | 10 |
| documents | 416 |
| terms | 13 |

`documents=416` は `プロジェクト/` 配下412ファイルに `社内管理/` 4ファイルを足した件数。

主な `document_type` 分布:

| document_type | 件数 |
|---|---:|
| `analysis_code` | 100 |
| `analysis_artifact` | 88 |
| `analysis_figure` | 54 |
| `meeting_minutes` | 31 |
| `meeting_report` | 23 |
| `train_data` | 19 |
| `proposal` | 16 |
| `plan` | 12 |
| `final_report` | 12 |
| `contract` | 11 |
| `analysis_metrics` | 11 |
| `notebook` | 11 |
| `column_description` | 10 |
| `analysis_leaderboard` | 10 |

版タグ付きファイルは13件。`old`, `v1`, `v2`, `v3`, `final`, `r1`, `r2`, `draft` を検出済み。

次の改善:

- 社内用語集からterm registryを完全抽出する。
- 契約書/提案書から主略称・人員・契約方式を補完する。
- `document_registry` から `version_pairs` を生成する。

## 3. 着手中: Excel抽出PoCを作る

### 目的

testで最も期待値が高い `xlsx` 系設問を取りに行く。セル値だけでなく、表示状態・色・数式・フィルターを抽出する。

### 対象

優先対象:

- `02.計画/スケジュール*.xlsx`
- `03.データ/train.xlsx`

対象にする情報:

- workbook path
- sheet name
- cell address
- value
- formula
- number format
- fill color
- font color
- bold / italic / underline
- merged cells
- auto filter範囲と条件
- hidden rows/columns
- charts metadata

### 作るもの

- `artifacts/spreadsheet_cells.parquet` または JSONL
- `artifacts/spreadsheet_sheets.jsonl`
- `artifacts/highlight_cells.jsonl`
- `artifacts/schedule_tasks.jsonl`

### 優先ユースケース

1. オレンジにハイライトされたWBS行のタスクID/タスク名を取る。
2. 黄色/青色ハイライトセルの値と周辺見出しを取る。
3. フィルター条件を復元する。
4. Pivotシートの表示値から最大/最小を取る。
5. 数式セルと参照先から計算根拠を取る。

### 完了条件

- [ ] すべての `xlsx` でシート一覧とセル数を出せる。
- [x] `02.計画/スケジュール*.xlsx` でシート一覧とセル数を出せる。
- [x] `02.計画/スケジュール*.xlsx` の色付きセル/行を一覧化できる。
- [x] `スケジュール*.xlsx` からタスクID・タスク名・担当者・開始日・終了日・工数を抽出できる。
- [x] `train.xlsx` からSheet名、色付きセル、数式セルを抽出できる。
- [x] `train.xlsx` のハイライトセルについて、周辺見出し・近傍セル・数式参照を復元できる。
- valid/testのExcel系設問に対して「必要情報が取れている/取れていない」を自動判定できる。

### 初期PoC結果

`scripts/extract_spreadsheets.py` を追加し、まず `02.計画/スケジュール*.xlsx` に限定して抽出済み。

出力:

- `artifacts/spreadsheet_sheets.jsonl`
- `artifacts/spreadsheet_cells.jsonl`
- `artifacts/highlight_cells.jsonl`
- `artifacts/schedule_tasks.jsonl`
- `artifacts/spreadsheet_failures.jsonl`

実行結果:

| 項目 | 件数 |
|---|---:|
| 対象xlsx | 11 |
| 抽出シート | 24 |
| 抽出セル | 5,890 |
| 書式付きセル | 1,388 |
| スケジュール行 | 473 |
| 失敗 | 1 |

失敗ファイル:

- `医療法人社団 恒一会 かえで総合病院/02.計画/スケジュール.xlsx`
  - `file` 判定は `CDFV2 Encrypted`
  - パスワード導出/復号戦略に接続する必要がある

次の課題:

- `train.xlsx` 系はPivot cacheの読み込みが重いため、通常の `openpyxl.load_workbook` では詰まりやすい。値・書式・図表を分けた軽量抽出方針にする。
- `highlight_cells` はフォント色由来の既定スタイルをまだ拾いすぎている可能性がある。質問対応では `fill_color_name` と行単位の色を優先する。
- 有効活用するために、`question_labels.csv` の `spreadsheet_state` 設問と `schedule_tasks.jsonl` のカバレッジを突き合わせる。

### カバレッジ分析

`scripts/analyze_spreadsheet_coverage.py` を追加し、[`spreadsheet_coverage.md`](./spreadsheet_coverage.md) を生成済み。

現時点の判定:

| status | 件数 |
|---|---:|
| `covered_artifact` | 4 |
| `partial` | 11 |
| `not_covered` | 16 |

`covered_artifact` は、スケジュールxlsxの抽出結果から直接候補を出せるもの。候補回答と根拠は [`schedule_query_candidates.md`](./schedule_query_candidates.md) に出力済み。

直接候補を出せた例:

- valid 20: AYMの探索的分析・仮説整理フェーズのタスクID候補。
- test 41: AOBMで加藤さんが担当者に含まれるタスクID数候補。
- test 89: 京橋信用ソリューションズのフェーズNo6で最後に開始するタスク名候補。
- test 90: 青潮モビリティサービスのバッファ工数合計候補。

`partial` の主な不足:

- 役割解決が必要: ビジネスアナリスト、データエンジニアなど。
- 元資料がpptx/docx/pdf: スケジュール行は補助情報に留まる。
- diffロジックが必要: `スケジュール_r1.xlsx` と `スケジュール_r2.xlsx` の比較など。

### train.xlsx軽量スキャン結果

`scripts/scan_train_xlsx_xml.py` を追加し、`03.データ/train.xlsx` をzip/XMLとして直接スキャンする方式を確認済み。`openpyxl` のPivot cache読み込みを避けるため、全セルをExcelオブジェクトとして開かない。

出力:

- `artifacts/train_xlsx_sheets.jsonl`
- `artifacts/train_xlsx_highlights.jsonl`
- `artifacts/train_xlsx_formula_cells.jsonl`
- `artifacts/train_xlsx_failures.jsonl`
- [`train_xlsx_scan.md`](./train_xlsx_scan.md)

実行結果:

| 項目 | 件数 |
|---|---:|
| 対象workbook | 9 |
| sheets | 29 |
| highlighted cells | 813 |
| formula cells | 53,751 |
| failures | 0 |

重要な判断:

- 全セルJSONLは1GB超になったため保存しない方針に変更済み。
- 保存対象はシート概要、ハイライトセル、数式セルに限定する。
- フィルター、図表参照、色付きセル、数式セルの有無は取得できる。
- セル周辺見出しの復元は `scripts/build_train_xlsx_highlight_context.py` で初期対応済み。
- 次段階は、グラフ系列の元データ解決、Pivot表示値の意味解釈、Excel系設問との自動カバレッジ突き合わせ。

### train.xlsxハイライト文脈復元結果

`scripts/build_train_xlsx_highlight_context.py` を追加し、[`train_xlsx_highlight_context.md`](./train_xlsx_highlight_context.md) を生成済み。

出力:

- `artifacts/train_xlsx_highlight_context.jsonl`
- `artifacts/train_xlsx_highlight_blocks.jsonl`
- `docs/train_xlsx_highlight_context.md`

結果:

| 項目 | 件数 |
|---|---:|
| ハイライトセル | 813 |
| ハイライトブロック | 13 |

主な復元内容:

- 蒼泉会: `Sheet1!F22` を `平均 / bmi`、`Sheet2!E14` を `合計 / age` の文脈として復元。
- 東都人材: `Sheet1!E1409` を `個数` 列、左隣 `Spain` と結び付け。
- 青嶺不動産: `Sheet2!B22` の数式参照 `B18`, `Sheet1!U26118`, `Sheet1!V26118`, `Sheet1!W26118` などを抽出。
- 青葉バイオ: `MonthlyIncome` 列 `R1:R736`、および `train_0077` / `train_0136` の行ハイライトを列名付きで復元。
- 白峰信用: `合計 / Attr5`, `合計 / Attr19` の青色ハイライト文脈を復元。

注意:

- XML上のキャッシュ値を読むため、Excel再計算はしていない。
- 色名は簡易正規化で、テーマ色は `THEME:*` として残る。
- ハイライト文脈は回答生成の根拠候補であり、設問ごとの最終回答には質問文との照合ロジックが別途必要。

## 4. 完了: Office書式抽出PoCを作る

### 目的

太字・下線・イタリック・赤字・黄色ハイライトなど、通常のテキスト抽出で失われる情報を得点源にする。

### 対象

- `docx`: 契約書、会議録、報告資料、社内用語集。
- `pptx`: 提案書、最終報告、座席表、基礎分析。
- `pdf`: ページ番号、本文、画像領域、OCR/VLM対象。

### 作るもの

- `artifacts/office_runs.jsonl`
- `artifacts/office_shapes.jsonl`
- `artifacts/office_tables.jsonl`
- `artifacts/pdf_pages.jsonl`
- `artifacts/office_marks.jsonl`

最低限の項目:

- `source_path`
- `project_name`
- `document_type`
- `page_number` / `slide_number`
- `paragraph_index`
- `text`
- `bold`
- `italic`
- `underline`
- `font_color`
- `highlight_color`
- `fill_color`
- `comment_text`

### 優先ユースケース

1. 契約書の太字箇所を抽出。
2. 会議録/報告資料の太字+下線+イタリック箇所を抽出。
3. 黄色ハイライトかつ赤字の箇所を抽出。
4. 提案書P7の赤色強調を抽出。
5. ページ番号を問う設問に対応する。

### 完了条件

- [x] docxのrun単位で太字/下線/イタリック/色/ハイライトを取れる。
- [x] pptxのshape単位で文字列・slide番号・色を取れる。
- PDFはページ単位の本文とページ番号を保持できる。
- 色名を `yellow`, `red`, `blue`, `orange` などに正規化できる。
- `すべて抜き出す` 系設問では対象ファイル全体を走査済みか判定できる。

### 初期PoC結果

`scripts/extract_office_marks.py` を追加し、DOCX/PPTXの書式抽出PoCを実行済み。PDFはまだ対象外。

出力:

- `artifacts/office_marks.jsonl`
- `artifacts/office_mark_failures.jsonl`
- [`office_marks_scan.md`](./office_marks_scan.md)

結果:

| 項目 | 件数 |
|---|---:|
| marks | 9,315 |
| failures | 1 |
| bold | 4,596 |
| italic | 111 |
| underline | 18 |
| font_color | 8,210 |
| highlight_color | 21 |

失敗:

- `恒一会 かえで総合病院/01.契約/契約書_pw-kaede20250902.docx`
  - 暗号化DOCX。パスワード導出/復号キューに回す。

次の課題:

- PPTXは通常の図形塗りやテーマ色も多く拾うため、質問条件に応じた色名正規化とノイズ除去が必要。
- PDFのページ単位抽出/OCR/VLMは別途実装する。
- `office_style` 設問と `office_marks.jsonl` のカバレッジ突き合わせを作る。

## 5. 完了: 新旧比較のファイルペア一覧を作る

### 目的

diff問題を検索任せにしない。旧版/新版のペア同定を先に自動化する。

### 対象パターン

- `提案書old.pptx` -> `提案書.pptx`
- `old/提案書.pptx` -> `提案書.pptx`
- `提案書_v1.pptx` -> `提案書_v2.pptx` -> `提案書_v3.pptx`
- `提案書_v1.pptx` -> `提案書_final.pptx`
- `最終報告_old.pptx` -> `最終報告.pptx`
- `old/最終報告.pptx` -> `最終報告.pptx`
- `01_eda_old.ipynb` -> `01_eda.ipynb`
- `スケジュール_r1.xlsx` -> `スケジュール_r2.xlsx`

### 作るもの

- `artifacts/version_pairs.jsonl`
- `artifacts/version_diffs.jsonl`

`version_pairs` 項目:

- `project_name`
- `document_type`
- `old_path`
- `new_path`
- `old_version_tag`
- `new_version_tag`
- `confidence`
- `pair_reason`

### 差分分類

- `scope_change`
- `schedule_change`
- `role_change`
- `cost_change`
- `model_change`
- `status_change`
- `wording_only`
- `format_only`

### 完了条件

- [x] 旧版/新版候補を全案件で列挙できる。
- [x] ペア候補にconfidenceを付けられる。
- pptx/docx/xlsx/ipynbのうち、少なくともpptxとxlsxで差分抽出方針が動く。
- 「案件遂行に関連する変更」から `wording_only` / `format_only` を除外できる見込みがある。

### 初期version pair結果

`scripts/build_version_pairs.py` を追加し、以下を生成済み。

- `artifacts/version_pairs.jsonl`
- [`version_pairs.md`](./version_pairs.md)

結果:

| 項目 | 件数 |
|---|---:|
| version pairs | 11 |
| high confidence | 11 |

内訳:

| document_type | 件数 |
|---|---:|
| `proposal` | 6 |
| `final_report` | 2 |
| `plan` | 1 |
| `contract` | 1 |
| `notebook` | 1 |

`scripts/analyze_version_pair_coverage.py` で [`version_pair_coverage.md`](./version_pair_coverage.md) も生成済み。`version_diff` ラベル付き12問のうち、実比較設問9問でペア特定済み、3問は `PP_final.pptx` や `スケジュール_r2.xlsx` のように版語を含むがdiffではない設問として分類した。

次の課題:

- pptx/ipynb/xlsx/docxの形式別diff抽出器を作る。
- diffを `scope_change`, `schedule_change`, `role_change`, `cost_change`, `model_change`, `status_change`, `wording_only`, `format_only` に分類する。

## 6. analysis成果物レジストリを作る

### 目的

`04.分析` を単なるファイル群ではなく、分析証跡として統合する。Notebook、コード、metrics、leaderboard、図表をつなげる。

### 作るもの

- `artifacts/analysis_registry.jsonl`
- `artifacts/notebook_cells.jsonl`
- `artifacts/code_units.jsonl`
- `artifacts/metrics_registry.jsonl`
- `artifacts/figure_registry.jsonl`

### 抽出対象

Notebook:

- markdownセル
- codeセル
- stdout/stderr
- execute_result
- display_data
- 埋め込み画像有無

コード:

- 関数名
- クラス名
- 引数
- 定数
- 条件分岐
- 代入
- config参照

metrics:

- モデル名
- 評価指標
- 詳細値
- selected_columns
- best model
- parameter

図表:

- ファイル名
- 図の種類
- 生成元Notebook/コード候補
- 元データ範囲候補
- VLM/OCR対象パス

### 完了条件

- `01_eda.ipynb` のセル本文と出力を検索できる。
- `metrics.json`, `leaderboard.csv`, `run_summary.json` の値を構造化して引ける。
- `modeling.py` などから条件分岐・デフォルト値を検索できる。
- `reports/figures/*.png` をファイル名・案件・図種別で引ける。

## 7. 横断レジストリの設計を固定する

### 目的

全案件集計、契約計算、APR判定、人員/内線/座席問題をアドホックにしない。

### 作るもの

設計書:

- `docs/data_strategy/cross_project_schema.md`

中間データ候補:

- `artifacts/projects.jsonl`
- `artifacts/contracts.jsonl`
- `artifacts/payments.jsonl`
- `artifacts/people_assignments.jsonl`
- `artifacts/schedule_tasks.jsonl`
- `artifacts/action_items.jsonl`
- `artifacts/data_profiles.jsonl`
- `artifacts/approval_rules.jsonl`
- `artifacts/seat_map.jsonl`

### 優先項目

契約:

- 契約方式
- 契約期間
- 税込金額
- 税抜金額
- 着手金
- RATE
- ESTH
- ACTH
- 支払月

人員:

- 人名
- 役割
- 案件
- タスクID
- アクションID
- 内線番号
- 座席位置

APR:

- 金額帯
- 承認レベル
- 医療案件補正
- time_and_materials補正
- 優先順位

### 完了条件

- 全案件の契約金額・契約方式・契約期間の抽出状況を一覧化できる。
- 人名と役割を複数資料から統合する方針が決まっている。
- APR-M1/M2/M3の判定関数を作れるだけのschemaが決まっている。
- 「全案件で」「完了案件のうち」系の設問で、必要な母集合を定義できる。

## 8. 回答ゲートと検証ログを設計する

### 目的

専用抽出器を増やすほど誤答リスクも増える。どの能力で答えたか、根拠が十分かを機械的に残す。

### 作るもの

- `artifacts/answer_evidence_schema.md`
- `artifacts/extractor_coverage_report.json`

回答時に残す項目:

- 使用したextractor
- 使用したsource paths
- 使用したunit ids
- 計算式
- 入力行数
- 欠損の有無
- list抽出の走査範囲
- confidence
- Missingに落とした理由

### 完了条件

- 各質問に対して「対応能力あり/なし」を判定できる。
- 数値問題では計算式と丸め規則をログに残せる。
- 列挙問題では対象ファイル/案件の走査完了を確認できる。
- 不完全な抽出で回答しないルールが明文化されている。

## 9. 完了: S/A優先タスクの初期実装

### 目的

既存artifactを「実際にどの設問へ使えるか」に変換し、次の回答ロジック実装で迷わないようにする。

### 追加したもの

- `scripts/analyze_structured_artifact_coverage.py`
- `scripts/build_version_diff_poc.py`
- `scripts/build_encrypted_file_queue.py`
- `artifacts/excel_question_coverage.csv`
- `artifacts/office_style_coverage.csv`
- `artifacts/version_diff_poc.jsonl`
- `artifacts/encrypted_file_queue.jsonl`
- [`excel_question_coverage.md`](./excel_question_coverage.md)
- [`office_style_coverage.md`](./office_style_coverage.md)
- [`version_diff_poc.md`](./version_diff_poc.md)
- [`encrypted_file_queue.md`](./encrypted_file_queue.md)

### 結果

Excel系カバレッジ:

| status | 件数 |
|---|---:|
| `covered_artifact` | 17 |
| `partial` | 8 |
| `not_covered` | 23 |

Office書式カバレッジ:

| status | 件数 |
|---|---:|
| `covered_artifact` | 9 |
| `partial` | 0 |
| `not_covered` | 3 |

version diff PoC:

| 項目 | 件数 |
|---|---:|
| pairs | 11 |
| ok | 11 |
| failed | 0 |

暗号化・抽出失敗キュー:

| type | 件数 |
|---|---:|
| encrypted / legacy Office container | 2 |
| other failures | 0 |

### 判断

- Excelは、スケジュール系とtrain.xlsxハイライト系が回答候補生成まで近い。
- Office書式は、太字・赤字・下線/イタリック・ハイライト抽出にすぐ使える。一方、コメント、ページ番号、グラフ値読み取りは未対応。
- version diffは全11ペアで行単位差分を出せたが、案件遂行に関係する変更だけを抽出する意味分類は未実装。
- 暗号化/旧Officeコンテナは2件。元ファイルは変更せず、復号または変換した一時コピーで再抽出する必要がある。

## 10. 推奨実行順

1. `question_labels.csv` を作る。
2. `project_registry` / `document_registry` / `term_registry` を作る。
3. Excel抽出PoCを作る。
4. Office書式抽出PoCを作る。
5. 新旧比較の `version_pairs` を作る。
6. analysis成果物レジストリを作る。
7. 横断レジストリschemaを固定する。
8. 回答ゲート・検証ログを設計する。

## 11. 採否判断

各タスクは、実装前に以下を埋める。

| 項目 | 内容 |
|---|---|
| 対象ラベル | どの質問タイプに効くか |
| 対象問数 | valid/testで何問に効く見込みか |
| 期待ゲイン | Perfect化できる問数、Incorrect回避できる問数 |
| 実装コスト | 低/中/高 |
| 誤答リスク | 低/中/高 |
| 採用条件 | 何ができたら本採用か |
| 撤退条件 | 何ができなければ後回しか |

この表なしに大きな専用抽出器を作らない。
