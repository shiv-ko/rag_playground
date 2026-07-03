# vault.md — 作業ファイルの場所と保存ルール

> セッション開始時はまずここを読む。「今どこまで進んでいて、次に何をするか」は
> **①`docs/plan/`の最新日付のnext-steps → ②`docs/daily作業ログ/`の最新ログ** の順に見れば分かる。

## 今の状態を知る（セッション開始時に見る順）

1. **`docs/plan/` の最新の `YYYY-MM-DD-next-steps.md`** — 次に何をどの順でやるか（進捗チェックボックス付き）
2. **`docs/daily作業ログ/` の最新ファイル**（`YYYYMMDD_HHMMSS.md`、名前順ソートで末尾が最新）— 直近セッションで何をやり、何を学び、何が残ったか
3. `docs/plan/plan_0703.md` — フェーズ全体のマスターロードマップ（各Phaseの実測結果を追記していく台帳）
4. `git log --oneline -15` — 実際のコミット状況（ログと食い違ったらコミットが正）

## ディレクトリ規約（何をどこに保存するか）

| 場所 | 中身 | 保存ルール |
|---|---|---|
| `docs/plan/` | 計画書 | マスター: `plan_0703.md`（フェーズ台帳、実測結果もここに追記）。次アクション: `YYYY-MM-DD-next-steps.md`（日付付きで新規作成、古いものは更新せず残す）。実装指示書: `YYYY-MM-DD-phaseN-for-codex.md` |
| `docs/superpowers/plans/` | superpowersフロー（subagent実行）用の実装計画 | `YYYY-MM-DD-<題名>.md`。Phase 0はここ |
| `docs/daily作業ログ/` | 作業ログ | **作業ブロックごとに `YYYYMMDD_HHMMSS.md` を新規作成**（追記より新規。目的→結果サマリ→やったこと（コミットSHA付き）→学び→残課題の構成） |
| `experiments/` | run結果JSON | `run_pipeline.py`が`<run-name>_<unixtime>.json`で自動保存。run-nameは`<フェーズや変更内容>_valid`等、後で見て分かる名前にする |
| `artifacts/` | 実データから機械生成したレジストリ・構造化jsonl | 手編集禁止。再生成手順は`AGENTS.md`参照。git管理対象 |
| `docs/`直下の各種md/csv | データ調査レポート（coverage系、scan系）と`question_labels.csv`（人手ラベル・**評価専用**） | 調査スクリプトの出力先。回答生成コードから読み込むのは禁止（`question_labels.csv`由来のもの） |
| リポジトリ直下 | `predictions.csv`（git管理）と`submission_*.zip`（提出物） | zipは`submission_YYYYMMDD_<内容>.zip` |
| `.cache/` | パース結果キャッシュ（gitignore） | 消してよい。`--no-cache`で無視できる |
| `.claude/skills/`・`.codex/skills/` | エージェント向けスキル（architecture / scoring / dev-process / experiments） | 開発規約はここが正 |

## ルート直下のmdの役割

- `CLAUDE.md` / `AGENTS.md` — エージェント向けの最小指示（venv・テスト・制約・artifacts再生成手順）
- `competition.md` / `rule.md` — コンペ規約（ハードコード禁止等の根拠）
- `strategy.md` — 上位戦略。`docs/data_strategy_todo.md`・`docs/data_strategy/` — データ基盤の詳細
- `vault.md` — 本ファイル（場所と保存ルールの索引）

## 書き込み時の約束

1. **計画を変えたら** `docs/plan/` の最新next-stepsのチェックボックスを更新する（完了項目には日付とコミットSHAを書く）
2. **作業を終えたら** `docs/daily作業ログ/` に新規ログを書く（何を・なぜ・結果・学び・残課題）
3. **実測結果が出たら** `plan_0703.md` の該当Phaseの節に追記する（run名・比較対象・テーブル・判定）
4. ログや計画に書いた事実とコードが食い違う場合に備え、**必ずコミットSHAを併記**する
5. 新しい置き場所を作ったら本ファイルの表に1行足す
