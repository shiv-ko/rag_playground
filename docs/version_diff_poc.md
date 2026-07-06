# version_pairs 差分抽出PoC

## 目的

`version_pairs.jsonl` の高信頼ペアに対し、pptx/docx/xlsx/ipynbから軽量に行単位差分を抽出し、後続の意味分類と回答生成に渡せる候補を作る。

## 集計

- pairs: 11
- ok: 11
- failed: 0

| project | type | old | new | changed | added | removed | status |
|---|---|---|---|---:|---:|---:|---|
| 京橋信用ソリューションズ株式会社 | proposal | 提案書_v1.pptx | 提案書_final.pptx | 1 | 0 | 0 | ok |
| 医療法人社団 恒一会 かえで総合病院 | final_report | 医療法人社団 恒一会 かえで総合病院_最終報告_old.pptx | 医療法人社団 恒一会 かえで総合病院_最終報告.pptx | 4 | 43 | 5 | ok |
| 株式会社青嶺不動産アセットマネジメント | proposal | 提案書.pptx | 提案書.pptx | 1 | 0 | 0 | ok |
| 株式会社青嶺不動産アセットマネジメント | plan | スケジュール_r1.xlsx | スケジュール_r2.xlsx | 23 | 0 | 0 | ok |
| 株式会社青葉バイオメディカル機器 | contract | 契約書_draft.docx | 契約書.docx | 0 | 0 | 0 | ok |
| 白峰信用リスク評価株式会社 | proposal | 提案書old.pptx | 提案書.pptx | 0 | 10 | 0 | ok |
| 白峰信用リスク評価株式会社 | notebook | 01_eda_old.ipynb | 01_eda.ipynb | 0 | 0 | 0 | ok |
| 青葉与信マネジメント株式会社 | proposal | 提案書_v1.pptx | 提案書_v2.pptx | 26 | 0 | 0 | ok |
| 青葉与信マネジメント株式会社 | proposal | 提案書_v1.pptx | 提案書_v3.pptx | 37 | 28 | 0 | ok |
| 青葉与信マネジメント株式会社 | proposal | 提案書_v2.pptx | 提案書_v3.pptx | 13 | 28 | 0 | ok |
| 青葉与信マネジメント株式会社 | final_report | 青葉与信マネジメント株式会社_最終報告.pptx | 青葉与信マネジメント株式会社_最終報告.pptx | 98 | 0 | 1 | ok |

## 差分サンプル

### 京橋信用ソリューションズ株式会社 / proposal / 提案書_v1.pptx -> 提案書_final.pptx
- before: slide 10 shape 3: 鈴木 修 主任 リスク管理部 与信モデル統括課 成果物レビューおよび検収の窓口、業務観点の妥当性確認
  after: slide 10 shape 3: 高橋 恒一 課長 リスク管理部 与信モデル統括課 成果物レビューおよび検収の窓口、業務観点の妥当性確認

### 医療法人社団 恒一会 かえで総合病院 / final_report / 医療法人社団 恒一会 かえで総合病院_最終報告_old.pptx -> 医療法人社団 恒一会 かえで総合病院_最終報告.pptx
- before: slide 2 shape 0: ビジネス成果 肝疾患リスク把握を支援する分析基盤と運用判断材料を納品。業務での閾値運用案と導入前検証要件を提示。 分析成果 最終モデル：hist_gradient_boosting（特徴量10） AUC-ROC = 0.905 / Accuracy = 0.833 / F1-macro = 0.829 中間段階の線形系試行（T04等）から性能改善を確認。 契約・商流 料金体系：Time & Materials 実績工数：140時間 最終請求金額（税込）：3,850,000円 （税率10%、検収完了に基づく精算） 本報告は、提案書・契約書・スケジュール・議事録（M01/M02）・中間報告・分析出力との整合を保ち、事実と仮定を明確に区分して記載している。 主要指標（内部検証値） AUC-ROC: 0.905 ｜ Accuracy: 0.833 ｜ F1-macro: 0.829 ｜ Precision@10%: 0.971
  after: slide 2 shape 0: 1. エグゼクティブサマリ
- before: slide 2 shape 1: 1. エグゼクティブサマリ
  after: slide 2 shape 1: ビジネス成果
- before: slide 4 shape 0: 3. 実施方法 実施方針 単一データソース前提で再現可能な手順を採用 説明可能性を重視し線形系と非線形モデルを比較 医療文脈での慎重な解釈を徹底 主な作業フロー 1. キックオフ (M01) — スコープ・前提確定 2. データ受領 読込検証 — train.csv 3. EDA — 分布・外れ値確認 4. 前処理設計 — id除外 Gender処理 5. モデル試作 — 線形系比較試行 6. 改善・最終確定 — hist_gradient_boosting 7. 最終報告書作成 — 検収対応 再現性トレース ● 実験アーティファクト：run_summary.json、metrics.json、experiments/leaderboard.json ● 中間レビュー議事録：会議録_2025-09-16.md（M02）
  after: slide 4 shape 0: 3. 実施方法
- added: slide 2 shape 2: 肝疾患リスク把握を支援する分析基盤と運用判断材料を納品。業務での閾値運用案と導入前検証要件を提示。
- added: slide 2 shape 3: 分析成果
- added: slide 2 shape 4: 最終モデル：hist_gradient_boosting（特徴量10） AUC-ROC = 0.905 / Accuracy = 0.833 F1-macro = 0.829 中間段階の線形系試行（T04等）から性能改善を確認。
- removed: slide 7 shape 2 table row 0: 指標 | 中間 (T04 linear) | 最終 (hist_gradient_boosting) | 改善幅
- removed: slide 7 shape 2 table row 1: AUC-ROC | 0.825 | 0.905 | +0.080
- removed: slide 7 shape 2 table row 2: F1-macro | 0.733 | 0.829 | +0.096

### 株式会社青嶺不動産アセットマネジメント / proposal / 提案書.pptx -> 提案書.pptx
- before: slide 8 shape 1 table row 6: QAレビューア | 池田 直哉 | 成果物レビュー、整合性確認
  after: slide 8 shape 1 table row 6: QAレビューア | 小林 直樹 | 成果物レビュー、整合性確認

### 株式会社青嶺不動産アセットマネジメント / plan / スケジュール_r1.xlsx -> スケジュール_r2.xlsx
- before: スケジュール row 3: No. | タスクID | 依存タスク | ステータス | フェーズ | タスク名 | 詳細・内容 | クリティカルパス | マイルストーン | チェックポイント | 成果物 | 開始日 | 終了日 | 担当者 | 備考
  after: スケジュール row 1: No. | フェーズ | タスクID | タスク名 | 詳細・内容 | 担当者 | 開始日 | 終了日 | 依存タスク | 成果物 | ステータス | クリティカルパス | マイルストーン | チェックポイント | 備考
- before: スケジュール row 4: 1 | T01 | - | 未着手 | P1 立上げ・前提固定 | プロジェクトキックオフ実施 | スコープ、対象データ(data\train.csv)、目的変数(SALE PRICE)、役割分担、会議運営を確認。議事メモ即日配布 | ○ | MS1: キックオフ完了・前提固定 | CP1: キックオフ完了確認 | キックオフ議事メモ | 2025-08-06 00:00:00 | 2025-08-06 00:00:00 | 佐藤 健一 | M01 キックオフ会議（クライアント窓口: 前田 美咲 部長）
  after: スケジュール row 2: 1 | P1 立上げ・前提固定 | T01 | プロジェクトキックオフ実施 | スコープ、対象データ(data\train.csv)、目的変数(SALE PRICE)、役割分担、会議運営を確認。議事メモ即日配布 | 佐藤 健一 | 2025-08-06 00:00:00 | 2025-08-06 00:00:00 | - | キックオフ議事メモ | 完了 | ○ | MS1: キックオフ完了・前提固定 | CP1: キックオフ完了確認 | M01 キックオフ会議（クライアント窓口: 前田 美咲 部長）
- before: スケジュール row 5: 2 | T02 | T01 | 未着手 | P1 立上げ・前提固定 | 正本前提・スコープ・役割分担確定 | 正本前提整理、スコープ確定、役割分担の文書化 |  |  |  | 前提確定メモ | 2025-08-06 00:00:00 | 2025-08-07 00:00:00 | 佐藤 健一 / 藤田 彩 | 
  after: スケジュール row 3: 2 | P1 立上げ・前提固定 | T02 | 正本前提・スコープ・役割分担確定 | 正本前提整理、スコープ確定、役割分担の文書化 | 佐藤 健一 / 藤田 彩 | 2025-08-06 00:00:00 | 2025-08-07 00:00:00 | T01 | 前提確定メモ | 完了 |  |  |  | 

### 株式会社青葉バイオメディカル機器 / contract / 契約書_draft.docx -> 契約書.docx

### 白峰信用リスク評価株式会社 / proposal / 提案書old.pptx -> 提案書.pptx
- added: slide 6 shape 2: 4.1 データ理解 品質確認
- added: slide 6 shape 3: 4.2 前処理 方針策定
- added: slide 6 shape 4: 4.3 モデル 比較

### 白峰信用リスク評価株式会社 / notebook / 01_eda_old.ipynb -> 01_eda.ipynb

### 青葉与信マネジメント株式会社 / proposal / 提案書_v1.pptx -> 提案書_v2.pptx
- before: slide 3 shape 10: loan_amnt
  after: slide 3 shape 10: 主要データ項目
- before: slide 3 shape 11: term
  after: slide 3 shape 11: loan_amnt
- before: slide 3 shape 12: interest_rate
  after: slide 3 shape 12: term

### 青葉与信マネジメント株式会社 / proposal / 提案書_v1.pptx -> 提案書_v3.pptx
- before: slide 3 shape 10: loan_amnt
  after: slide 3 shape 10: 主要データ項目
- before: slide 3 shape 11: term
  after: slide 3 shape 11: loan_amnt
- before: slide 3 shape 12: interest_rate
  after: slide 3 shape 12: term
- added: slide 6 shape 9: 追加データ取得、外部信用情報連携
- added: slide 6 shape 10: ✕
- added: slide 6 shape 11: 時系列予測、ビンテージ分析、月次運用設計

### 青葉与信マネジメント株式会社 / proposal / 提案書_v2.pptx -> 提案書_v3.pptx
- before: slide 6 shape 4: データ基盤新規構築、DWH設計、ETL常設化 追加データ取得、外部信用情報連携 本番運用時のモデル監視仕組み構築 時系列予測、ビンテージ分析、月次運用設計 本件データに含まれない項目を前提とした詳細損失率推計 本契約範囲外の追加要件に対する無償対応 法務判断、規制当局対応の代行 本番システム実装、API化、審査システム連携
  after: slide 6 shape 4: ✕
- before: slide 6 shape 6: 変更管理方針
  after: slide 6 shape 5: 本番システム実装、API化、審査システム連携
- before: slide 6 shape 7: 本契約範囲外の追加対応は、別紙見積にて金額・納期を事前合意のうえ実施する。
  after: slide 6 shape 6: ✕
- added: slide 6 shape 9: 追加データ取得、外部信用情報連携
- added: slide 6 shape 10: ✕
- added: slide 6 shape 11: 時系列予測、ビンテージ分析、月次運用設計

### 青葉与信マネジメント株式会社 / final_report / 青葉与信マネジメント株式会社_最終報告.pptx -> 青葉与信マネジメント株式会社_最終報告.pptx
- before: slide 4 shape 16: モデリング 評価・比較
  after: slide 4 shape 17: Step 4
- before: slide 4 shape 17: MS5-6
  after: slide 4 shape 18: モデリング 評価・比較
- before: slide 4 shape 18: ベースライン構築 extra_trees 説明性重視手法比較
  after: slide 4 shape 19: MS5-6
- removed: slide 14 shape 15: 次アクション（推奨）

## 注意

- これはPoCであり、差分の意味分類は未実装。
- PPTXはshape単位、DOCXは段落/表行単位、XLSXは行単位、ipynbはセル/出力単位で比較する。
- 書式だけの変更、文言だけの変更、案件遂行に関係する変更の切り分けは次段階。
