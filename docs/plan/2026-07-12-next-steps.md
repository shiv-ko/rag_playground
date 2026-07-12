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
- [x] `submission_20260712_phase4-imagegraph.zip` を作成して提出し、LBを`plan_0703.md`へ記録する。（2026-07-12、zip作成済み。**SIGNATEへの実アップロードとLB記録はユーザーが手動実施予定・未完了**）

**完了条件**: 提出zip・生成条件・LB・前回提出との差分解釈が作業ログに残っている。（LB実測記録のみユーザー報告待ち）

## 2. Phase 4 analysis系ブロック（次の主投資）

対象: `analysis_metrics` / `notebook_output` / `code_static`（primaryでvalid 5問・test 7問、secondary波及あり）。

**理由**: metrics.json、Notebook、Pythonコードという機械可読資産があり、VLMや自由生成より決定的な回答パスを作りやすい。

- [ ] 実データ調査: 対象12問の根拠ファイル・既存parser/artifact・現在のrouting/gateを一覧化する。
- [ ] Notebook画像問題は、VLMより先に元データ・セル出力・コードから再計算できるかPoCする。
- [ ] `analysis_registry` の最小スキーマと生成手順を設計する。手編集せず再生成可能にする。
- [ ] 問題型を、決定的抽出可能 / LLM補助が必要 / 能力外でMissing、に分類する。
- [ ] 期待ゲインとIncorrectリスクを見積もり、TDDの実装計画を別文書にする。
- [ ] 1タスク1変更・step-reviewで実装し、test診断runとvalid N=3＋official較正で採否を決める。

**完了条件**: 対象問の過半をPerfect相当で回収し、新規official Incorrect 0。列挙問題は完全性を機械確認できなければMissing。

## 3. パスワード保護ファイル（小工数候補）

- [ ] `encrypted_file_queue.jsonl` の対象とパスワード導出規則を実データで再確認する。
- [ ] `DA-[案件略号]-[契約開始日8桁]-[拡張子コード]` を汎用ロジックとして実装し、通常のartifact生成へ合流させる。
- [ ] 復号によるQ38など既存contract_rule経路の追加回収を検証する。

**着手判断**: analysis系の調査で大きなブロッカーが見つかった場合、または1作業ブロックで完了可能と確認できた場合に先行してよい。

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
