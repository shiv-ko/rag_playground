# 次アクション計画（2026-07-12策定）

> 位置づけ: `plan_0703.md` と2026-07-12までの作業ログを、現在の実装・実測に合わせて更新した実行順序。
> 判断原則は `strategy.md` の「守りを先行」「該当問数 × 改善確率 × 得点差」「1実験1変更」に従う。

## 0. 現在地

- Phase 2（spreadsheet_state / office_style / spreadsheet_calc）は完了条件を達成。2026-07-11 official較正は mean **0.4833**。
- Phase 3は version_diff・contract_rule・cross_projectの主要ブロックを実装済み。パスワード保護ファイル2件は未着手。
- Phase 4 image_graphブロックは実装・実データ検証・whole-branch reviewまで完了（`7dc6f13`）。
  - test Q39/Q33/Q54をネイティブチャートXMLから決定的に抽出。
  - valid Q1はVLM回答でofficial Perfect。
  - test Q66は安全にMissingへ落ちるが未回収。
- 既知のofficial Incorrectは主にQ17の冗長な言い換え。単問への過適合は避ける。
- 最新の提出物はPhase 4より前の構成。Phase 4のLB効果は未計測。

## 1. 【最優先】Phase 4構成の提出とLB確認

**理由**: 実装済みの改善を提出せず次の能力追加へ進むと、ローカル評価と本番LBの乖離を検知できない。

- [x] 未追跡の `predictions 2.csv` の生成元・用途を確認し、正式な`predictions.csv`との混同を解消する。（2026-07-12、`submission_20260704_phase1-2fix.zip`内predictions.csvと完全一致の古い残骸と判明、ユーザー確認の上削除）
- [x] 現HEAD・実データを明示して `make_predictions.py --runs 3` 相当の安定化生成を行う。（2026-07-12、HEAD `7dc6f13`、回答28/Missing72。詳細は`docs/daily作業ログ/20260712_162501.md`）
- [x] 診断監査で新規Incorrectリスク、構造化パスの発火、Missing理由を確認する。（2026-07-12、valid official mean 0.5333・新規Incorrectなし、test診断runで異常ルーティングなしを確認）
- [x] `submission_20260712_phase4-imagegraph.zip` を作成して提出し、LBを`plan_0703.md`へ記録する。（2026-07-12、ユーザーがSIGNATEへ手動提出。LB **0.1**（=3/30、前回5/30からnet -2/30）を`plan_0703.md` §1.1.1に記録済み）

**完了条件**: 提出zip・生成条件・LB・前回提出との差分解釈が作業ログに残っている。→ **達成**（`docs/daily作業ログ/20260712_162501.md`）

## 2. Phase 4 analysis系ブロック（次の主投資）

対象: `analysis_metrics` / `notebook_output` / `code_static`（primaryでvalid 5問・test 7問、secondary波及あり）。

**理由**: metrics.json、Notebook、Pythonコードという機械可読資産があり、VLMや自由生成より決定的な回答パスを作りやすい。

- [x] 実データ調査: 対象12問の根拠ファイル・既存parser/artifact・現在のrouting/gateを一覧化する。（2026-07-12、実装計画 `docs/superpowers/plans/2026-07-12-phase4-analysis-block.md`）
- [x] Notebook画像問題は、VLMより先に元データ・セル出力・コードから再計算できるかPoCする。（2026-07-12、valid Q22/Q24・test Q4を決定的に回収、test Q56は安全なMissing）
- [x] `analysis_registry` の最小スキーマと生成手順を設計する。手編集せず再生成可能にする。（`59a3fb1`、`artifacts/analysis_records.jsonl`を139 sourceから再生成）
- [x] 問題型を、決定的抽出可能 / LLM補助が必要 / 能力外でMissing、に分類する。（対象12問中11問が構造化回答、Q56のみ能力外）
- [x] 期待ゲインとIncorrectリスクを見積もり、TDDの実装計画を別文書にする。（上記実装計画）
- [x] 1タスク1変更・step-reviewで実装し、test診断runとvalid N=3＋official較正で採否を決める。（実装コミット: `59a3fb1` / `8f0a94a` / `670b061` / `b2215e6` / `70fd3c2`（gap fix、step-review CONFIRMED 0件）。565 tests PASS。valid N=3・official較正は2026-07-12ユーザー承認（Anthropic・OpenAI送信とも）を得て実施、target 5問officialすべてPerfect・新規Incorrect 0を確認。full test診断は接続可能な環境で再実行し、Connection error 0/100・対象外94問への回帰なしを確認済み）

**確定診断（2026-07-12）**: 正しい入力はdata-dir=`data/raw/share/共有ドライブ`、valid=`data/raw/share/質問回答/questions_valid.csv`、test=`data/raw/share/質問回答/questions_test.csv`。直接構造化診断ではvalid Q4/Q22/Q24/Q27/Q28、test Q4/Q5/Q32/Q35/Q61/Q73が`structured:analysis`で回答し、test Q56のみ安全なMissing。valid N=3+official較正（`judge_calibration_1783848948.json`、official mean 0.6333）でQ4/Q22/Q24/Q27/Q28はofficial Perfect 5/5、新規Incorrectなし（Incorrectだったのは既知のQ17・Q18のみ）。full test診断再実行（`phase4analysis_gapfix_test_diag_1783849572.json`）でtarget test 6問が同一値で安定・対象外94問に異常回答なしを確認。詳細は`docs/daily作業ログ/20260712_182541.md`・`20260712_183749.md`・`20260712_185411.md`参照。

**完了条件**: 対象問の過半をPerfect相当で回収し、新規official Incorrect 0。列挙問題は完全性を機械確認できなければMissing。→ **達成**（valid officialで確認、test構造化診断も安定）。次の提出でtest側LBを確認する。

## 3. パスワード保護ファイル（2026-07-12完了）

- [x] `encrypted_file_queue.jsonl` の対象とパスワード導出規則を実データで再確認する。（2026-07-12、契約書は既に別ルートで復号済み・Q38はMissingが正解と確認済みと判明）
- [x] `DA-[案件略号]-[契約開始日8桁]-[拡張子コード]` を汎用ロジックとして実装し、通常のartifact生成へ合流させる。（`6692190`/`ea70afe`、スケジュール.xlsxをextract_spreadsheets.pyに配線・実データ再生成済み）
- [x] 復号によるQ38など既存contract_rule経路の追加回収を検証する。（Q38は追加対応不要と再確認。スケジュール.xlsx依存のtest Q79/Q92は該当する汎用集計answererが未実装のため今回はMissing継続・新規回収なしをユーザー確認の上でスコープ外に。診断runで新規Incorrectなし・回帰なしを確認）

**完了条件**: →達成。詳細は`docs/daily作業ログ/20260712_210800.md`・`plan_0703.md` Phase3参照。**残課題**: Q79/Q92向けの新規集計answerer（担当者別想定工数、ID種別カウント）は未着手（test限定2問、valid該当なし。着手判断は期待値と工数のバランス次第）。

## 4. 後回しにする項目

- Q17専用の正解表現合わせ込み: 規約・valid過適合リスクがある。汎用的な簡潔化実験としてのみ扱う。
- test Q66の画像特定: ファイル名非明記を一般的に解決できる設計ができるまで安全なMissingを維持する。
- 座席表OCR（test Q13/Q46）・画像のみPDF: analysis系とパスワード復号後に期待値を再比較する。
- confidence threshold調整: Phase 5のタイプ別グリッドサーチまで単発調整しない。

## 5. 運用上の是正

- [ ] 本文書を今後の進捗チェックの正とし、完了時に日付・コミットSHA・実測run名を追記する。
- [ ] `plan_0703.md` §6の古い「直近アクション」は、次回の実測更新時に現状へ合わせる。
- [ ] 未追跡の計画書・作業ログ・実験JSONを確認し、成果物と一時ファイルを整理する（ユーザーの既存ファイルは削除しない）。
- [ ] 実データrunでは必ず `--data-dir "data/raw/share/共有ドライブ"` と質問CSVを明示する。
- [ ] 各作業ブロック終了時に新しいdaily作業ログを作成する。

## 推奨実行順

1. Phase 4版3-run提出・LB確認
2. analysis系の実データ調査とPoC
3. analysis系の実装計画・実装・評価
4. パスワード保護ファイル復号
5. 残存Incorrectの汎用対策
6. Phase 5の較正・性能・再現性検証
