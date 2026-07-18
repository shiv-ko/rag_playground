# test Missing診断: spreadsheet_state系20問（Q7/10/16/17/29/47/51/63/65/72/80/82/83/88/89/90/92/94/95/96）

- 診断日: 2026-07-18
- 対象: `experiments/repro_test_s1_1784290906.json`（100問, `run_judge`実行済み単発run）と
  `experiments/predictions_stability_1784291565.json`（N=3多数決結果）。
  routing_tagsに`spreadsheet_state`を含み、N=3多数決後もMissingの20問。
  - 構造化パスが発火せずplain retrievalに落ちた13問（最重要）: Q16, 17, 29, 51, 63, 72, 83, 88, 89, 90, 92, 94, 96
  - 何らかの構造化パスは通ったがMissingの7問: Q7, 10, 47, 65, 80, 82, 95
- 制約: 診断のみ。`src/`等のコード変更なし。LLM API呼び出しなし。すべて`src/`の実関数
  （`classify_question` / `build_office_style_context` / `build_spreadsheet_state_context` /
  `StructuredArtifactStore` 等）をオフラインでそのまま呼び出し、artifacts/生データと突き合わせて
  決定論的に再現した（作業スクリプトはリポジトリ外のscratchpadに保存）。
- 関連: `docs/test_missing_spreadsheet_calc_diag_20260718.md`（同日、集計・計算観点から並行診断された
  spreadsheet_calc系7問。Q47/90/92は本レポートと対象が重なり、Q90の「種別列」原因は両診断で独立に同一結論
  に到達している＝クロスバリデーション済み）。

## ① コードフロー要約

1. `src/utils/question_classifier.classify_question()` が質問文をキーワード一致でタグ付けする
   （`spreadsheet_state` / `office_style` / `image_or_graph` 等、複数タグ可）。
2. `Pipeline._process_one()`（`src/orchestrator/pipeline.py`）で、構造化系タグが1つでも付けば
   `_process_structured()` を呼ぶ。ここでプロジェクト名を解決し、タグに応じて専用ビルダーを順に試す。
3. `office_style`/`spreadsheet_state`/`version_diff` タグの場合は
   `src/retriever/structured_context.py` の `build_office_style_context` /
   `build_spreadsheet_state_context` / `build_version_diff_context` を呼ぶ。
   - **重要**: これらは「そのタグが`tags`に含まれている場合のみ」呼ばれる（`pipeline.py` L358-363）。
     office_styleタグが付かなければ`build_office_style_context`は一度も実行されない。
   - `build_spreadsheet_state_context` 内部は4つの独立したif分岐（ハイライト要求/フィルタ要求/
     xlsx言及時のPivot/スケジュール行の値一致）のOR合成で、どれにも当たらなければ空リストを返す。
4. 空リストなら`_process_structured`は`None`を返し、`_process_one`は通常のplain retrieval
   （ベクトル/BM25検索→LLM生成）にフォールバックする。これが「13問」パターンの直接原因。
5. 非空でも、完全性ゲート`is_enumeration_complete`や、生成後の`ConfidenceGate`
   （`src/generator/confidence_gate.py`、`looks_like_missing`判定含む）でMissingに変わりうる。
   これが「7問」パターン。
6. 構造化データの実体は`artifacts/*.jsonl`（`StructuredArtifactStore`経由）。
   xlsx由来（`schedule_tasks` / `train_xlsx_highlight_blocks` / `train_xlsx_small_sheet_cells` /
   `train_xlsx_pivot_aggregates`等）とdocx/pptx由来（`office_marks`）に分かれ、**PDFは対象外**。
   `office_marks`の`highlight_color`は`python-docx`の`WD_COLOR_INDEX`にのみ存在するため
   **docxのみ抽出され、pptxには存在しない**（後述）。

## ② 問別の分類表

| 問ID | 質問の要旨 | 落ちた箇所 | 原因仮説 | 確信度 |
|---|---|---|---|---|
| Q16 | 中間報告資料(docx)の黄色ハイライト＋赤字箇所を抜き出す | タグ分類: `office_style`が付かず`build_office_style_context`が未実行 | `classify_question`のOFFICE_STYLE_KEYWORDSは「黄色で」「赤で」「ハイライトされている」のみで「黄色ハイライトかつ赤字」という言い回しに一致しない。実際には`artifacts/office_marks.jsonl`に該当データが**存在する**（`報告資料_2025-04-09.docx`: `highlight_color=YELLOW(7)`, `font_color=FF0000`, text=`"4,620,000"`）。データはあるがルーティングで一度も見られていない。 | 高（正解候補まで特定） |
| Q17 | AYMのMMにおいて黄色ハイライト＋RED数値の上昇率を計算 | タグ分類: `office_style`未付与＋計算ロジック不在 | 同上の理由でoffice_styleタグが付かず未実行。加えて実際の`retrieved_sources`はPDF会議録（`office_marks`抽出対象外）に偏っており、「MM」が複数回の会議資料(docx)を指すなら`報告資料_2025-04-09.docx`(YELLOW+FF0000=4,620,000)と`報告資料_2025-04-29.docx`(YELLOW+EE0000=0.589)がヒットしうるが、2値間の上昇率計算を行うロジックはどこにも無い。 | 中（対象ファイル特定は推定） |
| Q29 | train.xlsxのTPヒストグラムで3番目にカウントが多いビン範囲 | タグ分類: `image_or_graph`が付かず、`spreadsheet_state`側は無関係データにマッチ | IMAGE_KEYWORDSに「ヒストグラム」が含まれず画像パスへ回らない。プロジェクトには`numeric_distribution_top6.png`等の実ヒストグラム図が存在する一方、`train_xlsx_pivot_aggregates`にあるのはGender/disease/Age別「平均」ピボット（カウント表ではない）のみ。`question_mentions_spreadsheet`は真だが`_pivot_argmax_docs`は最上級語（最も多い/少ない）のみ対応でNth順位は非対応、`_pivot_cache_aggregate_docs`は「ピボット」語が無いため不発。 | 高 |
| Q51 | 提案書.pptx内の「モデルの高度化」スケジュールが第何週目か | スケジュール行マッチング: 該当列が対象外 | `artifacts/schedule_tasks.jsonl`のWBSシートに正解候補行が実在（`タスクID=T18, タスク名="モデル高度化実験", フェーズ4, 開始日2025-06-19`）。しかし`_schedule_row_matches_question`が参照する列名は`("フェーズ","担当","ステータス","成果物")`のみで「タスク名」列は対象外のため一致しない。 | 高（正解候補まで特定） |
| Q63 | train.xlsxの回帰係数でid=0を予測 | 計算ロジック不在 | `train_xlsx_small_sheet_cells`に「回帰分析」シート（切片・各変数の係数）が完全に抽出済み。しかし「係数×該当行の特徴量値+切片」という予測値計算を行うanswererが存在しない。`question_mentions_spreadsheet`は真だがPivot系(`_pivot_argmax_docs`等)は最上級語専用で無関係。 | 高 |
| Q72 | KSSでデータエンジニアが担当するタスクID数 | スケジュール行マッチング列制限＋役割⇔氏名の結合ロジック不在 | `schedule_tasks`の「リソース計画」シートに担当者ごとの`関連タスク`列（タスクIDのCSV）は存在するが、`主担当領域`は長文の職務内容で「データエンジニア」という短いロール名と一致しない。さらに`_schedule_row_matches_question`の列制限（フェーズ/担当/ステータス/成果物）では「主担当領域」「関連タスク」列自体が対象外。役割名→担当者名→タスクIDの複数ホップの結合を行うロジックがそもそも無い。 | 中 |
| Q83 | train.xlsxの回帰係数でindex=1770を予測 | 計算ロジック不在 | Q63と同型。この案件のtrain.xlsxにも「回帰分析」シート（切片＋係数）が完全抽出済みだが、予測値計算answererが無い。 | 高 |
| Q88 | 提案書内スケジュール案で第5週目の項目 | 構造化抽出の対象外（PPTX埋め込み表） | `schedule_tasks.jsonl`は全件`.xlsx`由来で、PPTX内に埋め込まれた非公式なスケジュール案（週番号ベース）は抽出対象外。この案件の正式`スケジュール.xlsx`（20行）は開始日/終了日の日付管理で「第N週」表記を持たず、質問が指すのは提案書pptx内の別表と判断できる。 | 中 |
| Q89 | スケジュール.xlsxのフェーズNo6で最後に開始するタスク名 | スケジュール行マッチング: 数値IDが長さフィルタで除外 | `_schedule_value_match_parts`は`len(p) >= 2`未満の値を除外する。「フェーズNo.」列の値は整数`6`（文字列化すると1文字）のため、質問文の「フェーズNo6」との照合対象から機械的に脱落する。仮に一致しても「最後に開始する（開始日最大）」という集約（argmax by date）を行うロジックが無い。 | 高（コードで直接特定） |
| Q90 | スケジュール.xlsxのバッファ工数合計 | スケジュール行マッチング: 「種別」列が対象外＋SUM集計ロジック不在 | `schedule_tasks`に`種別="バッファ"`, `工数(h)`列が完全抽出済み（4行、計6〜8h）。`_SCHEDULE_MATCH_KEY_PARTS`に「種別」が含まれず不一致。仮に一致しても複数行の`工数(h)`をSUMする機構が無い。**`docs/test_missing_spreadsheet_calc_diag_20260718.md`のQ90所見と同一結論に独立到達**。 | 高（コードで直接特定、他診断と合致） |
| Q92 | かえで総合病院の3種ID（MS/タスク/アクション）発行総数（md以外） | 集計ロジック不在 | 単一行マッチングの仕組みしかなく、複数ファイル横断でID種別ごとにユニーク集合を作りCOUNTする機構が無い。`docs/test_missing_spreadsheet_calc_diag_20260718.md`と同一結論。 | 高 |
| Q94 | スケジュール.xlsxのMS3タスクでビジネスアナリスト関与分のタスクID | スケジュール行マッチング列制限＋役割⇔氏名の結合ロジック不在 | `関連マイルストーン`列に`MS3`が付いた行は実在するが、この列は`_SCHEDULE_MATCH_KEY_PARTS`の対象外。またこの案件のスケジュール表には役割ラベル列が無く、担当者氏名からロールを引く別ソースとの結合が必要（Q72と同型の欠如）。 | 中 |
| Q96 | チェックポイント2に関連するタスクID | スケジュール行マッチング: 「回次/ID」列が対象外 | 該当案件の`Sheet3`（チェックポイント表）に`回次/ID="CP2"`, `関連MS/タスク="MS2"`の行が実在するが、`回次/ID`列は`_SCHEDULE_MATCH_KEY_PARTS`の対象外で一致しない。さらにCP→MS→タスクの2ホップ変換も必要（このシートには直接タスクIDが無い）。 | 高（正解候補行まで特定） |
| Q7 | 基礎分析.pptxの黄色ハイライト数値の抽出条件・集計内容 | office_styleは発火したが誤ファイルへのフォールバック | pptxには`highlight_color`相当の抽出が存在しない（python-pptxにネイティブハイライトは無い）ため、`.pptx`拡張子で絞り込むと0件になり、`_narrow_marks_by_question_hints`の「絞り込み結果が空なら絞り込みを適用しない」という安全側フォールバックが働き、**無関係な同案件の別ファイル**（`報告資料_2025-08-06.docx`）のハイライトを返してしまう。生成LLMは文脈と質問（「基礎分析.pptx」）の不整合を検知しMissingと判断したとみられる。 | 高 |
| Q10 | train.xlsxのAG_ratioヒストグラムで最多カウント | タグ分類ミス＋Pivot列選択の意味不一致 | Q29と同根（「ヒストグラム」がIMAGE_KEYWORDS未収録）。`question_mentions_spreadsheet`が真のため`_pivot_argmax_docs`は動くが、ヘッダトークン一致だけで列を選ぶため「平均/AG_ratio」（Gender/disease/Age別の平均値ピボット）という、質問が意図する「ヒストグラムのカウント」とは無関係な列にヒットしてしまう（集計種別=カウントかどうかの検証が無い）。 | 高 |
| Q47 | train.xlsxの黄色ハイライトセル(予測誤差)の対象不動産の建設年 | ハイライトブロックの行コンテキスト不足 | 抽出されたハイライトブロックは1件のみで、回帰統計サマリ表内（「自由度」欄）を指しており、質問が求める「対象不動産の行」を特定する情報（元データの行ID等の逆引きキー）が`同じ行の値`に含まれない。`docs/test_missing_spreadsheet_calc_diag_20260718.md`と同一結論。 | 中 |
| Q65 | train.xlsxの相関係数シートで黄色ハイライトセルの条件 | 抽出データの品質異常（色誤分類・ヘッダ誤検出） | 質問は「黄色」だが抽出結果は`色: blue`。列見出しも`404.74...`のような数値（本来はA列/列名文字列のはず）で、ヘッダ行判定ロジックがこのシートのレイアウト（結合セル・非標準配置）で破綻している可能性が高い。 | 中 |
| Q80 | train.xlsxのSheet2の黄色ハイライトセルの抽出条件・集計内容 | シート名スコープの欠如 | 質問は明示的に「Sheet2」を指定するが、`train_xlsx_highlight_blocks_for`はプロジェクト内の全ハイライトブロックを無条件に返し、シート名で絞り込む仕組みが無い（`build_office_style_context`の`_narrow_marks_by_question_hints`に相当する機能がspreadsheet_state側に無い）。実際に返るのは唯一存在する`Sheet1`のブロックで、質問と矛盾する。 | 高 |
| Q82 | スケジュール.xlsxのWBSシートでオレンジハイライト行のタスクID一覧 | ファイル種別スコープの欠如 | 質問は「スケジュール.xlsx」を指すが、`_requests_highlight_condition`の分岐は`train_xlsx_highlight_blocks_for`（=train.xlsx由来）を無条件に含めるため、無関係な`train.xlsx`のSheet1/Sheet2（bmi/ageの平均集計）が混入する。`_schedule_highlight_docs`（スケジュール由来のオレンジハイライト行）は0件（この案件のWBSシートのハイライトが`dominant_row_fill`として抽出されていない、または色がオレンジ系に分類されていない可能性）。 | 中 |
| Q95 | スケジュール_r1/r2.xlsxの比較で業務関連の変更点（未着手→完了を除く） | ルーティングは正常。生成の確信度ゲート | `answer_path=structured:version_diff`まで正しく到達し`ctx_version_diff_count=1`（該当ペアを1件に絞り込み成功）。`gate_reason="confidence"`のため、構造化コンテキスト自体は妥当だがLLM生成側の確信度が閾値未満でMissing化した、ルーティングとは別軸の問題。 | 中 |

## ③ 原因パターン別グルーピング

| パターン | 該当問 | 件数 |
|---|---|---|
| P1. タグ分類キーワードの表現ギャップ（office_style/image_or_graphが付くべきなのに未付与） | Q16, Q17, Q29, Q10 | 4 |
| P2. スケジュール行マッチングの列名ホワイトリスト制限（`_SCHEDULE_MATCH_KEY_PARTS`が狭すぎる）＋数値ID除外 | Q51, Q72, Q89, Q90, Q94, Q96 | 6 |
| P3. PPTX/PDF埋め込みデータが構造化抽出の対象外（xlsx/docxのみ対応） | Q88, Q7（Q17も一部該当） | 2〜3 |
| P4. xlsxハイライト検索にシート名/ファイル種別のスコープ絞り込みが無い | Q80, Q82, Q47 | 3 |
| P5. 抽出品質の異常（色誤分類・ヘッダ誤検出） | Q65 | 1 |
| P6. 計算系answererの機能不足（回帰予測・Nth順位・COUNT/SUM集計・複数ホップ結合） | Q63, Q83, Q92（＋P2/P1各問の二次要因として広く関与） | 3（主要因ベース） |
| P7. 生成側の確信度ゲート（ルーティングは正常） | Q95 | 1 |

※多くの問は複合原因（例: Q51はP2が主因だが、仮に解決しても「第何週目」への日付換算は別途必要）。
上表は各問の**最初に構造化パスから落ちた箇所**を主要因として1パターンに割り当てている。

## ④ 汎用修正候補と期待改善問数の見積もり

いずれも特定の質問ID・特定ファイル名への分岐ではなく、構造・列名・キーワードパターンへの一般的対応。

1. **`OFFICE_STYLE_KEYWORDS`/`IMAGE_KEYWORDS`の拡充（P1対応）**
   - 内容: `OFFICE_STYLE_KEYWORDS`に色名単体＋「ハイライト」の組み合わせ検出（例: 「赤字」「黄色ハイライト」等の助詞非依存パターン）を追加。`IMAGE_KEYWORDS`に「ヒストグラム」「ビン」等を追加し、`image_or_graph`と`spreadsheet_state`が競合した場合の優先順位判定も見直す。
   - 期待改善: Q16は正解候補データ（YELLOW+FF0000="4,620,000"）が既に存在するため直接救済の可能性が高い（高確信）。Q29/Q10は`image_or_graph`に正しく回っても、その先でヒストグラム画像から順位付きビンを読み取る能力（VLM側の力量）に依存するため部分的（中確信）。Q17はMM特定の不確実性込みで中確信。
   - 見積もり: 直接1問（Q16）、条件付き2〜3問（Q29, Q10, Q17）。

2. **`_SCHEDULE_MATCH_KEY_PARTS`の拡張、または「列名フィルタ廃止＋値一致のみで判定」への変更（P2対応、最優先）**
   - 内容: 現行の`("フェーズ","担当","ステータス","成果物")`に「種別」「タスク名」「回次」「ID」「関連マイルストーン」等を追加するか、そもそも列名を問わず全列の値で`_schedule_value_match_parts`によるマッチングを行う設計に変更する（値の`len>=2`ガードは誤マッチ防止として維持）。数値ID（フェーズNo.等）については、文字列化した値がquestionの数字直後に現れるかを別途チェックする軽量ルールを追加する。
   - 期待改善: Q51・Q90・Q96は正解候補行がartifactsに実在すると確認済みのため、列制限を外すだけで該当行の再取得まで高確信で到達する（ただしQ51は日付→週番号換算、Q90はSUM集計、Q96はCP→MS→タスクの2ホップ変換が別途必要なため、行の再取得＝正解到達ではない）。Q89は`len>=2`フィルタの別修正が必要。Q72・Q94はさらに役割⇔氏名の結合ロジックが要る。
   - 見積もり: 実装コスト最小（タプル拡張は1行）で該当6問全てに何らかの改善（行の再取得成功）をもたらすが、**最終回答までの完全な救済は集計/結合ロジック追加とセットで3〜4問程度**が現実的な見積もり。単独では「Missingから抜けるが正答するとは限らない」問題が残る点に注意。

3. **xlsxハイライト/ピボット検索へのシート名・ファイル名スコープ絞り込みの追加（P4対応）**
   - 内容: `build_office_style_context`の`_narrow_marks_by_question_hints`と同種の仕組みを`build_spreadsheet_state_context`側にも導入し、質問文中のシート名（「Sheet2」等）・ファイル名（「スケジュール.xlsx」等）で`train_xlsx_highlight_blocks_for`等の候補プールを絞り込む。絞った結果が0件なら絞り込みを適用しない安全側設計は維持。
   - 期待改善: Q80はシート名スコープの追加だけで正しいSheet2ブロックに到達できる可能性が高い（高確信）。Q82はファイル種別スコープ追加で無関係なtrain.xlsxの混入は防げるが、そもそも`_schedule_highlight_docs`側でオレンジハイライト行が0件の問題は別途調査が必要（中確信）。Q47は行コンテキスト（同じ行の値に元データの行ID等を含める）の拡充が必要で本施策だけでは不十分。
   - 見積もり: 直接1問（Q80）、条件付き1問（Q82）。

4. **PPTX/PDFの構造化抽出範囲拡大（P3対応）**
   - 内容: (i) PPTX内の表（週次スケジュール案等）を`schedule_tasks`相当の構造化データとして抽出する処理を追加、(ii) `office_marks`のフォールバック時に「絞り込み結果0件→無条件に別ファイルを返す」のではなく「該当拡張子でハイライト相当の情報が無い」ことを明示しMissing応答に倒す（誤ファイル混入の防止）。PDFの色/装飾抽出は現状の`PDFParser`の実装次第でスコープが大きいため本レポートでは着手判断を保留。
   - 期待改善: (ii)はQ7の誤答混入を防ぐ効果はあるが、Q7自体の救済（正しい黄色ハイライト値の取得）には繋がらない可能性が高い（pptxにネイティブハイライトが無いため、そもそも抽出対象が存在しない構造的制約）。(i)はQ88の直接救済に繋がりうる（中確信、実装コストは中〜大）。
   - 見積もり: 直接1問（Q88、要中規模実装）。Q7はフォールバック改善で「誤答→正しいMissing」への切替のみ（正答化ではない）。

5. **回帰予測計算・件数集計answererの新設（P6対応）**
   - 内容: `train_xlsx_small_sheet_cells`から「回帰分析」シート形式（切片＋変数別係数のグリッド）を検出し、質問中のid/index指定と対応する特徴量値（train.csv/train.xlsxの該当行）を掛け合わせて予測値を計算する専用ロジック。ID種別ごとのユニークカウント集計は`spreadsheet_calc`診断（Q92）と共通のため、そちらの新設判断と合わせて検討すべき（重複実装回避）。
   - 期待改善: Q63・Q83は回帰係数・特徴量データともにartifactsに実在確認済みのため、専用ロジック実装で高確信の直接救済が見込める。Q92は`docs/test_missing_spreadsheet_calc_diag_20260718.md`が既に「費用対効果が低い」と判定済み（本診断でも同意）。
   - 見積もり: 直接2問（Q63, Q83、高確信）。Q92は低優先度。

### まとめ（期待改善問数の見積もり、対象20問中）

- 修正候補2（スケジュール列名フィルタ緩和）は該当問数が最多（6問）で実装コストも最小だが、**単独では完全救済にならない問（集計・結合ロジックが別途要る）が多い**ことに注意。
- 修正候補5（回帰予測answerer新設）はQ63・Q83の2問について、必要なデータがartifactsに既に揃っていることまで確認済みで、実装すれば高確信で直接救済できる。
- 修正候補1（タグキーワード拡充）はQ16について正解候補データの存在まで確認済みで、修正コストが最小（キーワード追加のみ）な割に確度が高い。
- 修正候補3（シートスコープ絞り込み）はQ80について高確信、実装は`_narrow_marks_by_question_hints`の既存パターンを流用できるため中コスト。

## トップ3サマリ（回答末尾用）

1. **スケジュール行マッチングの列名ホワイトリスト制限**（`_SCHEDULE_MATCH_KEY_PARTS`が「フェーズ/担当/ステータス/成果物」の4種のみ） — 該当6問（Q51,72,89,90,94,96）。列制限を撤廃/拡張するだけで該当行の再取得までは高確信で到達するが、完全な正答化には集計(SUM/argmax)・複数ホップ結合(役割→氏名→タスク、CP→MS→タスク)の追加実装が必要。現実的な救済見積もりは3〜4問。
2. **タグ分類キーワードの表現ギャップ**（office_style/image_or_graphが本来必要なのに未付与） — 該当4問（Q16,17,29,10）。Q16は正解候補データ（YELLOW+FF0000="4,620,000"）の存在まで確認済みで、キーワード追加のみで高確信の直接救済が見込める。ヒストグラム系(Q29,Q10)はimage_or_graphへの誤タグ修正後もVLM側の読み取り能力に依存し部分的。
3. **回帰係数を使った予測値計算answererの不在**（Q63,83）とxlsxハイライトのシート/ファイルスコープ欠如（Q80,82,47） — ともに3問規模。前者はartifactsに必要データ（回帰統計シート）が完全な形で存在することを確認済みで、専用計算ロジックを1つ実装すれば2問を高確信で救済できる。後者はSheet名/ファイル名によるスコープ絞り込みを`office_style`側と同様の仕組みで`spreadsheet_state`側にも追加すれば、Q80を中心に改善が見込める。
