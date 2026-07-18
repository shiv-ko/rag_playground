# 次アクション計画（2026-07-18、Phase 5前倒し完了後の再照準）

[`2026-07-16-next-steps-2.md`](./2026-07-16-next-steps-2.md)の後継。Phase 5の主要項目（cold対策・再現性検証・保守モード・ダッシュ正規化・judge較正改善）が予定より約3週早く完了したため、フリーズ（8/13目安）までの約4週間の投資先を再決定する。

## 現在地（2026-07-18時点）

- valid official mean **0.8333**、official Incorrect **0**、LB **0.23333（7/30）**で過去最高。
- 守り（ゲート・多数決・保守モード`b2eed00`・ダッシュ正規化`78f1bde`）は完成度が高い: N=3バッチ間一致95%、valid上の多数決後Incorrectはゼロ。
- **testはN=3多数決後もall_missingが57/100問**（`predictions_stability_1784291565`）。validは頭打ちに近く、残りの得点源はほぼすべてtest側のMissingにある。

### test all_missing 57問の内訳（`repro_test_s1_1784290906`とのクロス集計、2026-07-18実測）

| 切り口 | 内訳 |
|---|---|
| gate_reason | **missing_text 53**（LLM自身が「わかりません」）、capability 2、contract_no_project 1、confidence 1 |
| answer_path | retrieval 45、structured:spreadsheet_state 5、version_diff 3、office_style 3、cross_project 1 |
| routing_tags | text_only 24、**spreadsheet_state 20**、office_style 7、spreadsheet_calc 7、他 |

タグ別のパス通過状況:

- **spreadsheet_state: タグ30問中Missing 20問。うち13問は構造化パスが発火せずplain retrievalに落ちている**（発火して答えられたのは6問のみ）。Phase 2資産の接続漏れが最大の疑い。
- **text_only: タグ32問中Missing 24問、全てretrievalパス**。検索ミスか読解失敗かの切り分けが未実施。
- spreadsheet_calc: 9問中Missing 7問（6問はretrieval落ち）。

ゲートで消えているのではなく「答えが作れていない」のが本質（confidenceゲートは57問中1問のみ）。つまり閾値緩和ではなく能力・検索の問題。

## 優先順位の判断

strategy.md §1.3（該当設問数×改善確率×得点差）で見ると、spreadsheet_state Missing 20問・text_only Missing 24問は現存する最大の期待値ブロック。守りが完成している今、Missing→正答の変換は精度50%超なら期待値プラス（Perfect +1 vs Incorrect -1）で、既存ゲートが精度の下限を守る。一方validにこれらの型はほぼ無く（spreadsheet_state系はvalid 3問）、validでの検証力が弱い点が最大のリスク——「診断→汎用修正→valid退行なし確認→testでの発火数・回答内容の目視妥当性確認」の順を守る。

## 1. test Missing 57問の診断ドリルダウン【最優先・まず診断のみ】

修正に入る前に、失敗を型別に切り分けて期待値の高い1〜2本に絞る。

- [x] spreadsheet_state Missing 20問: 診断完了（2026-07-18、sonnetサブエージェント、`docs/test_missing_spreadsheet_state_diag_20260718.md`）。主要パターン: ①スケジュール行マッチングの列名ホワイトリスト`_SCHEDULE_MATCH_KEY_PARTS`が狭すぎる（6問、救済見込み3〜4問。正解行のartifacts実在を確認済み） ②`classify_question`のキーワード語彙ギャップでoffice_style/imageタグ欠落（4問。Q16はoffice_marksに正解候補実在） ③回帰予測計算answerer不在（2問、係数グリッドはartifacts済み）＋xlsxハイライトのシート名スコープ欠如（3問）。
- [x] text_only Missing 24問: 診断完了（2026-07-18、`docs/test_missing_text_only_diag_20260718.md`）。A検索ミス9問 / Bパース欠落1問 / C根拠不明3問 / **C'画像・OCR必要11問（46%）**。最有望: ①`_parse_docx`が`doc.tables`を完全無視（docx46件中35件に表。社内用語集.docx 820セルが実質検索不能、Q99直接+略語問題へ波及） ②暗号化ファイル検知漏れ（Q79、ファイル名に`pw-`が無いCDFV2暗号化が検知されない） ③クロスリファレンス追跡・チャンク束ね（3問）。
- [x] spreadsheet_calc Missing 7問: 診断完了（2026-07-18、`docs/test_missing_spreadsheet_calc_diag_20260718.md`）。Q90=スケジュール列ホワイトリスト（spreadsheet_state診断と独立に同一結論、クロスバリデーション済み）、Q64=スキャンPDFのOCR未対応（同問題が3案件10ファイル超に波及）、Q30=CalcSpec表現力不足、Q38/86/92=案件横断突合（1修正1問で費用対効果悪、保留維持を再確認）。
- [x] 実装優先順位の確定（2026-07-18、期待改善問数×実装コスト）:
  1. **スケジュール列ホワイトリスト緩和**（3〜4問、小、2診断でクロス確認済み）
  2. **docxテーブル抽出**（Q99直接+社内用語集経由の波及、中、検索基盤全体の改善）
  3. **分類キーワード拡充**（Q16直接+ヒストグラム誤ルーティング解消、小。全130問の前後ルーティングdiffで副作用確認必須）
  4. 第2波候補: 暗号化検知の内容ベース化（Q79）/ 回帰予測answerer（Q63/83）/ xlsxシート名スコープ（Q80/82/47）/ パースキャッシュfingerprintへのパーサーバージョン組み込み（下記の罠の恒久策）
  5. **OCR/VLM判断は別枠で再評価**: 画像起因Missingが計12問超（text_only 11問+Q64）と判明し、当初の「該当2問」見積もりを大幅超過。コスト・精度・3時間制限への影響を見積もってから着手判断。

### 第1波の実装状況（2026-07-19、sonnetサブエージェント+step-review運用）

- [x] スケジュール行マッチング汎用化（`e88aae9`）: 初回実装（ホワイトリスト全撤廃）はstep-reviewで誤マッチ2ケース（数値列「18」の日付偶然一致・無関係列「完了」の汎用語一致）がCONFIRMEDとなり再設計。列名語彙の拡張ゲート（状態/種別/区分/分類/タスク/マイルストーン/回次を追加）＋純数値値の一律除外＋NFC正規化の2層防御で決着。オフライン前後比較で診断6問中Q90/Q94解消・Q96部分解消（3/6、見積もり3〜4問の範囲内）、誤マッチ2ケースは回帰テストでブロック。702 tests pass。
- [x] docxテーブル抽出（`29eedaa`）: step-reviewで結合セル重複・無音握りつぶし・テスト検出力不足の3件CONFIRMED→修正。`iter_inner_content()`採用、tc要素参照保持のdedup（id()ベースはlxmlプロキシのアドレス再利用でid衝突する罠を実データスモークで検出）、全except節にlogger.warning。社内用語集.docx抽出134→7,681文字。
- [x] 分類キーワード追加＋office_style複合条件AND絞り込み（`af65451`）: キーワード2語＋連言マーカー検出時のみAND＋過剰列挙ガード（閾値20件）を1実験としてコミット。レビュー2巡（OR全損・形容詞形後退・casefold漏れのCONFIRMED 3件を修正）。Q16: 375→2件（正解候補一致）、Q17: 11→2件、answered問はQ71の正解値収束のみで他は無変化。
- [x] valid検索recall退行チェック（2026-07-19）: 25/29（86%）でベースライン0.862と同一、失敗4問も同一集合（`retrieval_valid_1784393831.json`）。**採用条件クリア**。
- [ ] **valid N=3＋flip分析（最終採用ゲート、要ユーザー承認）**: 外部生成/judge APIへの非公開データ送信を伴うため承認待ち。承認後 `run_pipeline.py` valid N=3 → flip分析 → 新規Incorrectゼロ確認。詳細は作業ログ`20260719_015735.md`。
- **キャッシュの罠（対処済み・恒久策は第2波）**: `compute_fingerprint()`はデータファイルのmtime/sizeのみでパーサーコードのバージョンを含まないため、パーサー修正がキャッシュヒットで無効化される。2026-07-19に旧`parsed_*.pkl` 9件を削除済み（embeddingキャッシュは温存）。

**採用条件（修正着手後）**: valid official mean・検索recall 0.862に退行なし、valid official Incorrect 0維持、testでの新規回答は目視で根拠つき妥当性を確認してから提出物に反映。

## 2. Q15順序不一致の解消【小・独立】

7/16データ更新で`questions_valid.csv` index=15は新順序に反映済みだが、採点キー`valid_txt.csv`が旧順序のまま（メモリ`eval-data-update-0716-q15-order-mismatch`）。valid評価の信頼性に関わるため、現状を確認して整合させる。

- [x] 現状確認: 不一致は実在（採点キー2ファイルとも旧順序`MINAMINO、SHR、AYM`のまま）だが**実害なし**——ローカルjudge・公式judge再現記録（`judge_calibration_*.json` 20件）とも順序違いを内容一致としてPerfect判定。詳細は`docs/q15_valid_scoring_key_check_20260718.md`。（2026-07-18、sonnetサブエージェント検証）
- [x] 修正適用: `data/raw/evaluation/data/valid_txt.csv`と`data/evaluation/data/valid_txt.csv`の15行目を新順序`AYM、SHR、MINAMINO`に統一。既存runへの影響なし（上記のとおり全記録Perfectで不変）。API再較正は非公開データ送信の承認が必要なため見送り（実害なしのため必須でない）。（2026-07-18）

## 3. 提出サイクル

- [ ] 項目1の修正が1本でも採用確定したら、N=3提出物を新規生成して提出（`78f1bde`ダッシュ正規化はここで初めて提出物に反映される）。修正が全て不採用でも、7/16提出以降の安定化分を反映した1回は提出しておく。

## 4. バックグラウンド・任意

- [ ] フルcold N=3 E2E確認実行: マシンのメモリに余裕がある時間帯に1回。外挿値（1.72h）との乖離とBM25フォールバック非発火を確認（`589cec3`の安全網検証）。

## 5. クローズ判定（追加作業なしで決着）

- [x] confidence thresholdタイプ別探索: 予備実測で最高構成・保守構成ともholdout 0.6333で現行と同率のため、**現行閾値を維持で決着**。明確な改善根拠が出ない限り再開しない。（2026-07-18判断）
- [x] local judge較正改善: `2026-07-16-next-steps-2.md`項目3の未チェック2項目は同日夜に完了済みだった（`3413b52`、holdout stable agreement 89.7%、採用確定。plan_0703.md「2026-07-16 local judge較正の改善」参照）。チェックボックス更新漏れをここで訂正。

## 6. フリーズ準備（8/13目安、着手は8月上旬〜）

- [ ] 最終提出2枠の生成: 「現行構成」N=3と「`--conservative`構成」N=3（ルール確定済み`b2eed00`）
- [ ] エッジケース処理・検収を意識したコード整理・README/実行手順の整備（plan_0703 Phase 5残項目）

## 保留継続

- Q79/Q92向け新規集計answerer・座席表OCR（test Q13/Q46）・test Q66画像特定: 期待値低、安全なMissing維持。ただし項目1の診断でspreadsheet_calc側の共通原因が見つかれば再評価。
