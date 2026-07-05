# spreadsheet_state発火設計（カバレッジ攻めブロックA）

> 位置づけ: test Missing 85問の死因診断（2026-07-05、`diag_test_1783239219.json`・コミット`dadcc82`後の実測）に基づくカバレッジ攻め第1ブロック。ブロックB（横断14問 = cross_project / internal_terms / contract_rule、Phase 3既定路線）は別スペック。
> ユーザー承認: 2026-07-05（案X = A→B分割、および本設計の§1〜§5）。

## 0. 診断サマリ（設計根拠）

`predictions.csv`（LB 0.13333提出）のMissing 85問 × 診断run（`run_pipeline.py --no-judge`）の実測:

- **死因はゲートではない**: missing_text 72 / citation 4 / confidence 3 / capability(画像) 3 / 生成ゆらぎ 3
- **案件ルーティング失敗はゼロ**: missing_text 72問中58問は正しい案件のファイルを検索済み（中身不足）。14問は質問から案件を特定できない横断クラスタ（→ブロックB）
- **spreadsheet_state 23問**: 16問は正しいファイル種別すら検索上位に来ない。例: Q2は「スケジュール_r2.xlsx」と名指しなのにtrain.xlsxを引く
- **根本原因（コード実測）**: `build_spreadsheet_state_context` のハイライト分岐は `train_xlsx_highlight_blocks.jsonl`（train.xlsxのみ・13行）しか見ておらず、`highlight_cells.jsonl`（スケジュール系xlsx・1,388行、うちスケジュール_r2.xlsx 61行）と `schedule_tasks.jsonl`（473行）が**未接続**（plan_0703 §1.2の未接続資産）
- **ファイル名明示質問はMissing 85中33問**（spreadsheet_state 18 / office_style 5 / text_only 5 / version_diff 2 / image 3）

## 1. 目的と成功基準

既存資産の**配線のみ**（新規資産構築なし）でspreadsheet_state系のMissingを回収する。

成功基準:
1. validの既回収問（Q6/Q11/Q21等）が全問バイト同一または改善（no-harm）。official較正で悪化なしを確認
2. test発火プローブ: 変更が対象問（Q2/Q82型）で構造化コンテキストを実際に生成することを提出前に確認（「validで作ったパスがtest発火ゼロ」再発防止）
3. 提出は `--runs 3` 安定化を標準とし、LBは参考情報として記録

## 2. コンポーネント1: 質問中の明示ファイル名によるスコープ絞り（汎用）

質問文が拡張子付きファイル名を含む場合にそれを抽出し、2箇所で使う:

- **構造化ビルダー側**: 候補行（highlight_cells / schedule_tasks / train_xlsx系 / pivot集計）を該当ファイルに絞る。「_r2を聞かれてスケジュール.xlsxの1,326行を返す」誤爆を防ぎ、完全性ゲートのプール定義も正しくなる
- **通常検索側**: ソースパスのbasenameが質問中のファイル名と一致するチャンクを**スコア加点**する（ハードフィルタにはしない — 名指しファイルが答えを含まない場合に他文書からの回答可能性を殺さないため）

規則:
- 抽出は「拡張子付きトークン」の正規表現による一般則（`\.xlsx|\.pptx|\.docx|\.pdf|\.csv|\.ipynb` 等）。**特定ファイル名のハードコードはしない**（質問文由来の値のみ使う — 競技規約適合）
- 文字列比較は**必ず両辺NFC**（このリポジトリの再発事故パターン）
- **ファイル名がヒットしない場合は必ず従来動作にフォールバック**（絞り込みは条件付き追加のみ。誤った絞り込みで既存回収問を壊さない）

## 3. コンポーネント2: `highlight_cells.jsonl` / `schedule_tasks.jsonl` の接続

`build_spreadsheet_state_context` のハイライト分岐を拡張:

- `highlight_cells.jsonl`（セル単位・fill色情報付き）を候補に追加。質問の色指定は既存 `_requested_color_names` の対応表を流用
- 行単位に集約し、`schedule_tasks.jsonl`（行→タスク名・担当・日付）と突合して「指定色のハイライト行のタスク名」を列挙できるコンテキストを構築
- 既存の完全性ゲート（`is_enumeration_complete`）は維持。プール件数は絞り込み後の走査対象から取る
- 既存の `train_xlsx_highlight_blocks` 経路は変更しない（validのQ6/Q21回収を守る）

`StructuredArtifactStore` に highlight_cells / schedule_tasks のプロジェクト別アクセサが無ければ追加する（読み込みは既存artifactsの流儀に従う）。

## 4. 検証とリスク管理

- TDD: 合成jsonlフィクスチャでビルダー・ファイル名抽出・絞り込みを単体テスト（実データの案件名・回答値はテストに書かない）
- step-review: 1タスク=1レビュー=1コミット（提出経路に近い変更はsonnet）
- valid 30問 N=3 → 既回収問バイト同一確認（flip監視）→ official較正
- test発火プローブ: 対象問で構造化パスの発火有無だけ確認（回答の中身の目視はするが、正解合わせはしない）
- 主リスクは「誤ったファイルへの絞り込み」→ §2のフォールバック規則で遮断

## 5. スコープ外

- 横断14問（ブロックB: cross_project / internal_terms / contract_rule — 別スペック）
- office_style残6問・ヒストグラム/グラフ読み取り系（capability扱い）・citation/confidenceゲート7問
- 回答正規化ルール（answer_stabilizer）の変更
- 新規artifactの生成スクリプト（既存jsonlの範囲で賄う）
