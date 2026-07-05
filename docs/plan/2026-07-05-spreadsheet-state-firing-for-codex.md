# spreadsheet_state発火 実装指示書 — Codex向け

> 実装本体は **`docs/superpowers/plans/2026-07-05-spreadsheet-state-firing.md`** に
> タスク単位（コード・テスト・コマンド・期待値つき）で全て書いてある。本書は
> Codex実行時の環境約束だけを定める。設計の背景は
> `docs/superpowers/specs/2026-07-05-spreadsheet-state-firing-design.md`。

## 実行範囲

- 計画の **Task 1 〜 Task 4 のみ** を順に実施する（1タスク=1コミット）
- **Task 5 は実施しない**（LLM API・OpenAI較正が必要なためClaudeが代行）。
  Task 4 のコミットが済んだら**停止してClaudeに引き継ぐ**

## 環境・検証の約束（安定化ブロックと同じ）

- テスト: `.venv/bin/pytest tests/ -v`（開始時点**341件**、タスクごとに計画記載の期待件数まで増える。全件PASS維持）
- **CodexはLLM APIに接続できない** — 計画のタスク1〜4はユニットテストのみで完結する設計になっている
- サブエージェント不可のため、計画中の「step-review（sonnet）」は
  `.codex/skills/step-review` のセルフレビューチェックリスト1周で代替する（コミット前に毎回）
- NFC/NFD: 新しい文字列比較は必ず両辺 `unicodedata.normalize("NFC", ...)`（計画のコードは対応済み。
  変更を加える場合もこの規則を守る）
- 競技規約: 特定の案件名・ファイル名・質問文・正解値のハードコード禁止。
  テストのフィクスチャは計画に書いてある合成値をそのまま使う（実データの値に置き換えない）
- 計画のコードをそのまま使ってよいが、**テストを先に書いてFAILを確認してから**実装を入れる
  （計画の各タスクのStep順に従う）。既存テストのアサーションは変更しない

## スコープ外（触らない）

- `scripts/make_predictions.py`・`src/orchestrator/answer_stabilizer.py`（提出経路）
- `build_spreadsheet_state_context` の train_xlsx / filter / pivot 既存分岐（Task 4はハイライト分岐への2行追加のみ）
- `office_marks` 経路・`highlight_cells.jsonl` の接続（今回はschedule_tasksが主データ源。不足が実測されたら別タスク）
- valid実験フロー（run_pipeline / majority_eval / calibrate_judge）

## 引き継ぎ（Task 4完了後）

1. `.venv/bin/pytest tests/ -v` 全件PASS（期待: 357件）を最終確認
2. 作業ログ `docs/daily作業ログ/YYYYMMDD_HHMMSS.md`（実装サマリ・テスト件数・迷った点・
   セルフレビューで直した点）
3. コミットして**停止**。以降はClaude側が計画のTask 5（valid N=3回帰・official較正・
   test発火プローブ・提出判断）を実施する
