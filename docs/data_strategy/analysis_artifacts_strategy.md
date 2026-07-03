# 分析成果物戦略

## 1. 対象データ

`04.分析` は最もファイル数が多い。274ファイルあり、以下が混在する。

- `analysis_outputs/metrics.json`
- `analysis_outputs/leaderboard.csv`
- `analysis_outputs/run_summary.json`
- `analysis_project/notebooks/01_eda.ipynb`
- `analysis_project/src/*.py`
- `analysis_project/configs/project_config.json`
- `analysis_project/reports/figures/*.png`
- `README.md`, `requirements.txt`, `pyproject.toml`

ここは単なる文書ではなく、分析の実行証跡として読む。

## 2. 統合すべき情報

案件ごとに `analysis_registry` を作る。

| 情報 | 主なソース |
|---|---|
| 目的変数 | カラム説明、Notebook、config |
| 特徴量 | features.py、Notebook、selected_columns |
| 前処理 | preprocess.py、modeling.py |
| モデル種別 | modeling.py、config、leaderboard |
| ハイパーパラメータ | config、modeling.pyのデフォルト、実行時引数 |
| 評価指標 | metrics.json、leaderboard.csv、run_summary.json |
| 可視化 | reports/figures/*.png、Notebook outputs |
| 観察結果サマリ | Notebook markdown/output |

## 3. Notebook戦略

`ipynb` はJSONとしてセル単位に分解する。

抽出対象:

- markdownセル本文
- codeセル本文
- stdout/stderr
- display_data
- execute_result
- 埋め込み画像
- セル順序

質問は「Notebookに出力されている」「可視化において」「観察結果サマリ」など、実行後の出力を問うことがある。コードだけ読んでも答えられないため、outputsを必ず索引化する。

`01_eda_old.ipynb` と `01_eda.ipynb` の比較もあるので、Notebookも版管理対象にする。

## 4. コード戦略

`src/*.py` は静的検索だけでなく、設定値解決が必要。

例:

- `modeling.py` で `sparse_output=False` になる条件。
- CAT判定のdtype/ユニーク数条件。
- 勾配ブースティングに渡される `n_estimators`, `learning_rate`, `random_state`。
- 生成された交互作用特徴量。

戦略:

1. Pythonファイルを関数/クラス単位に分割する。
2. ASTで関数名、引数、定数、条件分岐、代入を抽出する。
3. `project_config.json` とコードのデフォルト値を統合する。
4. 「明示されていない値」はコード上のデフォルトを辿る。

LLMに長いコードを読ませるだけでは不安定。少なくとも関数単位の検索と設定解決テーブルを持つ。

## 5. metrics/leaderboard戦略

JSON/CSVは構造化データとして読む。

- `metrics.json`: 指標の詳細値、小数桁、モデル名、特徴量選択。
- `leaderboard.csv`: モデル順位、スコア差、設定差分。
- `run_summary.json`: 実行概要、最良モデル、パラメータ。

小数第N位の設問が多いため、元値をfloatに丸めて失わない。JSON文字列の原値も保持する。

## 6. 図表戦略

`reports/figures/*.png` は、ファイル名で検索できるようにしつつ、画像としてVLMに渡す。

重要な図:

- `feature_correlation_heatmap.png`
- `numeric_distribution_top6.png`
- `date_feature_trend.png`
- `target_distribution.png`
- `figure_06.png`

可能ならNotebookやコードから図の元データを辿る。VLMでグラフ数値を読むより、元データや生成コードから計算したほうが正確。

優先順位:

1. 図の元データ/生成コードを特定して計算する。
2. それが無理なら画像VLMで読む。
3. 数値完全一致が必要で確信が低い場合はMissing。

