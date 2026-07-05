# 次アクション計画（2026-07-04策定）

> 位置づけ: `plan_0703.md`（ロードマップ）の進捗更新版。Phase 1+2 是正後（valid mean 0.13〜0.22、3run）を起点に、
> 次に何をどの順でやるかを定める。各項目の着手時は従来通り実装計画を別途作ってから進める（1実験1変更・TDD）。

## 0. 現在地（2026-07-04時点の実測）

- valid 30問: mean **0.13〜0.22**（同一コード3run。ゆらぎ±0.05は既知の制約 — temperature指定不可のため）
- **安定Perfect（3/3）**: Q8（契約条件計算）/ Q13（spreadsheet_calc）/ Q20（scheduleタスク列挙）
- **フリップ（1〜2/3のみ成功）**: Q5 / Q14 / Q18 / Q27 — 能力はあるのに安定しない層。**回収すれば+0.10〜0.15相当**
- **安定Incorrect傾向**: Q28（notebookチャンク分割で判定条件が泣き別れ→部分コードから誤断定）
- 安定Missing 21問の内訳: office_style 3 / spreadsheet_state 3 / calc 2 / single_text 2 / list_extraction 2 / internal_terms 2 / notebook_output 2 / その他5
- test 100問の規模感: **spreadsheet_state 21** / version_diff 11 / internal_terms 11 / contract_rule 10 / office_style 9 / calc 9 / cross_project 9

## 1. 【最優先】Phase 0 計測基盤の完成とマージ

**理由**: 今回のNFDバグ診断は `retrieved_sources` が無いために実データ再現を何度も要した。Phase 0 Task 2の
診断情報があれば数分で切り分けられた。また±0.05のrun間ゆらぎにより、以降の実験は単一runの数値比較では
判断できない — flip分析の標準化（Task 4）が全実験の前提になる。

- [x] worktree `.claude/worktrees/phase0-measurement-infra` の完了済みTask 1（パースキャッシュ）・Task 2（診断情報）を
      現mainへ統合する（2026-07-04完了: `ac612e9` / `9c86d8e`。raw_textを現行の全ゲート経路に適応。
      詳細は`docs/daily作業ログ/20260704_005800.md`）
- [x] Task 3: 検索単体評価（retrieval recall）スクリプト（2026-07-04完了 `68fc097`。valid recall 66%=19/29。
      NFC/NFD突合バグをrecall 0の実測で検出し修正）
- [x] Task 4: flip分析の標準化（`scripts/run_eval.py`にrun間差分出力、2026-07-04完了 `31bff62`）。
      N=3 run多数決の手順化は今後の実験運用で適用
- [x] Task 5: OpenAI CRAGジャッジとの較正（2026-07-04完了 `3f58499`。official 0.1333 vs local 0.15、一致率90%。
      judgeゆらぎの定量化（同一回答N回判定）は未実施・必要になったら）
- [x] Task 6-7: Missing切り分け表の生成と`plan_0703.md`更新（2026-07-04完了 `5b4d3d7`＋E2E実行。
      `docs/plan/missing_triage_20260704.md`: 検索失敗10/生成失敗12/過剰ゲート1/計測不能1。`plan_0703.md` §2.1参照）

**完了条件**: ✅達成（2026-07-04）。「変更→30問評価→flip確認」= 2分3秒＋flip数秒で回る。Missing+Incorrectは
検索失敗10/生成失敗12/較正失敗1/計測不能1に分類済み。

## 2. フリップ層の安定化（安価・+0.10〜0.15）

Q5/Q14/Q18/Q27は正解を出せることが実証済みで、落ちる原因はゲート境界（conf 0.4付近）と引用のゆらぎ。

→ **実装計画策定済み（2026-07-04）**: `docs/superpowers/plans/2026-07-04-flip-stabilization.md`。
Phase 0実測による更新: Q18の真因は**JSONパース失敗**（citation内の生改行→conf 0.0扱い）で`strict=False`により決定的に修正可能。
Q17は用語言い換え（「未連絡」→「前回未接触」）でofficial Incorrect → 直答形式ルールで対処。
gate_reason記録とN=3多数決ツールを先に整備してから、パース修正・引用プロンプト・直答プロンプトを1実験1変更で検証する6タスク構成。

- [x] 落ちたrunのゲート特定（2026-07-04完了）: `gate_reason`をrun JSONに恒久記録（`589d6bf`）。
      Q18の真因はJSONパース失敗と確定→`strict=False`で修正・採用（`89435eb`、1/3runでPerfect回収）
- [x] 引用の安定化（2026-07-04実験・**不採用**）: 30字制約はcitationゲート死亡を0にしたが
      Incorrect素通りを生み多数決mean 0.15→0.10。**引用ゲートの誤答遮断価値が偽陰性コストを上回る**（`f417aec`）
- [x] （追加実験）短答系の直答形式（2026-07-04・採用 `641e858`）: 不安定問6→3・local Incorrectゼロ化
- [ ] しきい値調整はPhase 5のグリッドサーチまで温存（単発でいじらない）
- [x] **①「値のみ」超短答の実験**（2026-07-04実施・採用 `bc22924` = plan_0703 §2.3 実験A。
      official 0.1167→0.1667。Q8/Q27回収）
- [ ] **残課題（plan_0703 §2.2-2.3）**: ①Q17言い換え・Q18章番号誤りのゲート通過中-1リスク
      ②実験判定はmean単独禁止の運用継続 ③Q6のofficial表現問題（規約適合の範囲での一般的回答形改善のみ可 —
      正解文の型の模倣は**規約違反としてB3をrevert済み**。plan_0703 §2.3 学び1参照）

## 3. Phase 2 残課題（test 39問に直結、期待値最大）

完了条件「該当タイプでPerfect過半」は未達（9問中1）。診断済みの残ギャップを潰す。優先はtest問数の多い順。

→ **実装計画策定済み（2026-07-04）**: `docs/superpowers/plans/2026-07-04-value-only-and-spreadsheet-state.md`。
計画時の実地調査による更新: (a) 東都train.xlsxの**autoFilter XMLにフィルタ条件そのものが保存されている**
（gender=Male等・非表示行11,413）→値差分の推計は不要で決定的に抽出可能。(b) **かえで「ファイル破損failures=1」は
古い情報**で実際はPivotシート1,907セルが読める — 欠落はPivotセル値のartifact未出力のみ。
(c) §2残課題の短答「値のみ」実験も同計画のTask 1として先行実施。

- [x] **spreadsheet_state（test 21問・最大）**（2026-07-05完了: Q11=実験B・Q6=実験B2・Q21=実験F `b265b12` で主要3問を回収。official 0.3833）:
  - フィルタ条件質問: ヘッダ＋非表示行番号だけでは条件を導けない。`spreadsheet_cells.jsonl`（全セル保持）から
    **可視行と非表示行の列ごとの値差分**を計算してコンテキスト化（Q11）
  - Pivot質問: `train_xlsx_highlight_blocks/context` をspreadsheet_stateパスに接続強化（Q6/Q21。
    かえで総合病院はファイル破損で`failures=1`のため、`scan_train_xlsx_xml.py`側の到達可否も確認）
    - 2026-07-05: compact Pivot向けに `pivotTableDefinition + pivotCache` から再集計する構造化パスを実装。
      `artifacts/train_xlsx_pivot_aggregates.jsonl` は24行、PoC比較 mismatch 0。コミットは本変更。
    - 2026-07-05検証（実験F・採用）: `exp_pivotagg_valid`×3でQ21 Missing→Perfect 3/3、
      official較正 mean **0.3833**（`judge_calibration_1783182281.json`）、official IncorrectはQ17のみで不変。
- [x] **office_style（test 9問）**: Q0/Q25系のoffice_styleルート改善（2026-07-04完了:
  `8b07c3a` / `ef22058`）。Q25は単発スモークで `1. データ理解・EDA` 回収。
  Q0はcapability gateを脱出したが、文脈不足で未回収。残る「M02資料」→`報告資料_2025-08-06.docx`対応付けは次ブロックへ継続。
  スケジュールxlsxのマイルストーン表（MS ID→日付）が実行時に取れるので、**「M0N資料」= MS0Nの日付近傍の
  報告系ファイル**として汎用導出する（ファイル名ハードコード禁止の規約に適合）。対応付け後もLLMが確信を
  持てない場合はコンテキストに対応根拠を明記（Q0/Q23/Q25）
- [x] **spreadsheet_calc（test 9問）**: CalcSpecに `group_by` + `select`（argmax/argmin）と
  `list` / `closest_to_mean_list` を追加（2026-07-04完了: `725acfd` / `37e62f1`）。
  Q7はlocal/official Perfect、Q26は単発official Perfect。ゲート（0行・列不在・51件以上→Missing）は維持。
- [x] **HEAD最終構成の後追い検証（2026-07-04完了: `eaf6f77`）**: `exp_phase2rem_head_valid` N=3＋
  official較正で採用確定。**official mean 0.3667**（B2b 0.2333→calcgroupby 0.2667→0.3667）、
  Q25/Q26/Q27 official Perfect、Q23 Acceptable安定化、official IncorrectはQ17のみ（Q6解消で2→1）。
  local多数決0.3000への見かけ低下はjudge誤判定（Q25: GT完全一致をIncorrect判定。plan_0703 §2.3学び4）

→ **office_style＋spreadsheet_calc（Q0/Q7/Q26/Q25）のCodex向け実装指示書策定済み（2026-07-04）**:
`2026-07-04-phase2-remainder-for-codex.md`（`b2c0f0a`）。Codexはサブエージェント不可のため
step-reviewはコミット前セルフレビュー1周で代替する（`.claude/skills/step-review`の代替手順）。

## 4. Phase 3 着手（test 30問、Phase 2と並行可）

`plan_0703.md` §Phase 3 の既定路線。資産（`version_diff_poc.jsonl`全11ペアdiff成功等）があり着手可能。

- [x] version_diff（11問）の構造化回答パス実装（2026-07-06完了）: `build_version_diff_context`で
      `version_diff_poc.jsonl`を接続。タイトル＋バージョンタグで対象ペアを1つに絞り、曖昧なら`[]`
      （Missingに逃がす）。実データ8問（valid Q9, test Q0/1/9/14/74/95/22）でオフライン検証しペア特定は全問成功。
      詳細は`docs/daily作業ログ/20260706_004522.md`。**未実施**: 実データ・APIキー環境でのvalid実行・
      official較正・test生成（本セッションはキー無しのクラウド環境のため不可）
- [ ] contract_rule（10問）→ cross_project（9問）の順（valid Q3のIncorrect歴があるcross_projectは最後・ゲート厚め）
- [ ] internal_terms（test 11問）はPhase 3扱いで追加検討: valid Q15/Q16はMS日付・営業日計算系で、
  上記スケジュール/マイルストーン資産（§3のMS表）を流用できる可能性が高い

## 5. チャンク・検索の修正（Phase 0の切り分け結果待ち）

low-riskの安定Missing（Q2/Q4/Q17/Q22）と唯一のIncorrect（Q28）はretrieval/chunking起因の疑い。
**Phase 0 Task 3のrecall実測で規模を確定してから**着手（Phase 1計画で意図的に先送りした項目。感覚で直さない）。

→ **2026-07-04 実測で規模確定**（`missing_triage_20260704.md`）: 検索失敗は10問でspreadsheet系に集中
（spreadsheet_state 0/3・code_static 0/2・spreadsheet_calc 1/3が全/半滅）。当初疑いのうち**Q4・Q28は検索失敗と確定**、
Q2/Q17/Q22は検索hitしており**生成失敗側**だった（チャンク内容の質の問題の可能性はある — raw_answer読みで切り分け）。

- [ ] Q28型の対策: notebook/コードのチャンク分割で条件式が泣き別れないよう、セル単位・関数単位の境界を優先

## 6. 提出・運用

- [x] 提出ファイル生成済み（2026-07-04: `submission_20260704_phase1-2fix.zip`、回答19/Missing 81。
      `make_predictions.py`がレジストリ未接続だった問題を修正してから生成 `1140bab`）
- [x] SIGNATEへアップロード → LB **0.03333**（2026-07-04記録、`plan_0703.md` §1.1.1）。ローカル0.13〜0.22との乖離大。
      0.03333=1/30ちょうどのため公開LBがサブセット採点の疑い。乖離の確定解釈はPhase 0 Task 5（judge較正）・Task 6-7（triage）で行う
- [ ] 以降も各フェーズ完了ごとに提出。判断は常にタイプ別フリップで（validは1問=3.3%揺れる）。**提出は`--runs 3`安定化を標準とする**（2026-07-05 LB 0.13333で効果確認済み、`plan_0703.md` §1.1.1）
- [ ] **TODO（2026-07-05ブレスト・案C）**: `make_predictions.py` の安定化監査JSONに診断フィールド（`gate_reason` / `retrieved_sources` / `confidence`）を同梱する — 提出のたびにtest側の死因診断がタダで付く。当面は `run_pipeline.py --no-judge` の診断runで代替。実装時はretrieved_sourcesでJSONが肥大しない形（run 1のみ記録等）にする

## 推奨順序と目安

| 順 | 項目 | 期待効果 | 目安 |
|---|---|---|---|
| 1 | §1 Phase 0完成・マージ | 全実験の判定精度（前提投資） | 〜7/6 |
| 2 | §2 フリップ安定化 | +0.10〜0.15 | 7/6前後 |
| 3 | §3 Phase 2残課題 | test 39問×成功率向上 | 〜7/13 |
| 4 | §4 Phase 3 | test 30問（+internal_terms 11） | 〜7/27 |
| 5 | §5 チャンク・検索 | low-risk Missing回収＋Incorrect根絶 | 切り分け後 |

※ 締切8/20・フリーズ目安8/13（`plan_0703.md` §5）。元計画より約1週間先行しているので、貯金は§3〜4の精度向上に使う。
