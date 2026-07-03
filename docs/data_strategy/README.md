# 勝つためのデータ戦略

`dataset_overview.md` はデータの静的な概要に留める。この配下では、設問と実データから逆算して、スコアを伸ばすためにどのデータをどう構造化・検索・検証するかを扱う。

## ドキュメント一覧

| 文書 | 役割 |
|---|---|
| [`question_taxonomy.md`](./question_taxonomy.md) | valid/testの設問傾向から、勝ち筋になる能力を分類する |
| [`metadata_and_routing.md`](./metadata_and_routing.md) | 全データ共通のmetadata設計、案件ルーティング、略称解決 |
| [`office_visual_strategy.md`](./office_visual_strategy.md) | docx/pptx/pdfの本文・ページ・書式・強調表現の戦略 |
| [`spreadsheet_strategy.md`](./spreadsheet_strategy.md) | xlsx/csv/tsv、Pivot、フィルター、セル色、集計問題の戦略 |
| [`analysis_artifacts_strategy.md`](./analysis_artifacts_strategy.md) | analysis_project、Notebook、コード、metrics、図表の戦略 |
| [`version_diff_strategy.md`](./version_diff_strategy.md) | old/v1/v2/v3/finalなど新旧比較問題の戦略 |
| [`cross_project_rules_strategy.md`](./cross_project_rules_strategy.md) | 社内管理、契約、計画、全案件横断集計、APR/請求計算の戦略 |

## 全体方針

勝つための基本方針は、文書チャンク検索の上にすべてを載せないこと。設問は、本文読解だけでなく、Excelの表示状態、Office書式、画像内数値、Notebook出力、コード実行時の値、契約計算、社内略語、複数案件横断に依存する。これらは検索だけでは不安定で、専用抽出器で構造化してから検索・計算・回答生成に渡す。

優先順位は次の通り。

1. 全ファイルに共通metadataを付与し、案件・資料種別・版・ページ/シート/セルまで辿れるようにする。
2. 設問数が多いExcel/Office書式を先に攻略する。
3. analysis成果物はNotebook/コード/metrics/図表を別々に読まず、同じ分析証跡として統合する。
4. 新旧比較はファイルペア同定と差分抽出を専用化する。
5. 全案件横断は、契約・計画・人員・金額を構造化テーブルに落としてから計算する。
6. どの専用能力で答えたかを回答に紐づけ、能力外の設問はMissingに落とす。

## 成果物のイメージ

最終的には、生チャンクだけでなく以下の中間データを持つ。

- `document_units`: ファイル、ページ、スライド、段落、表、画像、シート、セルの単位。
- `project_registry`: 案件名、主略称、別名、業界、契約期間、契約方式、金額。
- `office_marks`: 太字、下線、イタリック、色、ハイライト、コメント、ページ番号。
- `spreadsheet_cells`: セル値、数式、色、シート、フィルター、Pivot由来情報。
- `analysis_registry`: Notebook出力、metrics、leaderboard、図表、コード設定。
- `version_pairs`: 同一資料種別の旧版/新版候補と差分。
- `people_registry`: 人名、役割、案件、内線、座席。

