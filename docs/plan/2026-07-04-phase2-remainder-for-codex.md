# Phase 2 残課題（office_style / spreadsheet_calc）実装指示書 — Codex向け

> 位置づけ: `2026-07-04-next-steps.md` §3の残り（spreadsheet_stateは2026-07-04のflip安定化〜spreadsheet_state強化ブロックで対応済み）。
> **実装者はCodex**（サブエージェント無し環境）を想定。レビューは `.claude/skills/step-review` のテンプレートを
> **セルフレビューチェックリストとしてコミット前に1周**すること（同スキルの運用ルールに明記）。
> 開発規約は `.codex/skills/dev-process.md`（TDD・1実験1変更）。

## 実行環境・判定の約束（2026-07-04ブロックで確立した運用）

- テスト: `.venv/bin/pytest tests/ -v`（現在310件、全件PASS維持）
- 評価: 変更ごとに valid 30問を**N=3 run**し、多数決で判定する:
  ```bash
  for i in 1 2 3; do .venv/bin/python scripts/run_pipeline.py \
    --data-dir "data/raw/share/共有ドライブ" \
    --questions "data/raw/share/質問回答/questions_valid.csv" --run-name <実験名>; done
  .venv/bin/python scripts/majority_eval.py <直前グループの3run> --vs experiments/<実験名>_*.json
  ```
  1run約2分。**比較元グループはこの指示書着手時点のHEADで直近に採用された3run**（experiments/の最新の採用実験、
  作業ログ/plan_0703 §2.2〜参照）。
- **判定原則（plan_0703 §2.2の学び。厳守）**:
  1. **mean単独で採否を判定しない** — local judge（claude）は正答をMissingへ誤判定する率が高い（Q5/Q8/Q27で実測）。
     多数決＋不安定問一覧＋**raw_answer/answerの目視**＋（回答形式に関わる変更は）official較正
     `scripts/calibrate_judge.py <run.json>`（OpenAI 30問）で判断
  2. **local/official Incorrectの増加はどのmean改善より優先で拒否**（誤答-1 > Missing 0）
  3. 迷ったら保守側（abstain/Missing）に倒す。安全機構（引用ゲート等）は緩めない（実験②の負の結果）
  4. 不採用の変更はrevertし、run JSONだけ証跡としてコミット（メッセージに「不採用」と根拠）
- **1実験1変更**: 下記Task 1〜4はそれぞれ独立にN=3で採否を確定してから次へ。まとめて回さない
- NFC/NFD: artifacts・ファイルパス由来の文字列はNFD。**新しい文字列比較は必ず両辺 `unicodedata.normalize("NFC", ...)`**
  （このリポジトリで4回起きた事故パターン）
- 競技規約（competition.md）: 特定の案件名・ファイル名・質問文・正解のハードコード禁止。
  `question_labels.csv`は評価専用（回答生成パスからのimport禁止）

## 前提となる現状（2026-07-04終了時点の実測）

- valid 30問 多数決mean **0.2833**（同一コード3run）。official（gpt-5.2本番同一judge）single-run mean 0.2333
- 本指示書の対象4問の現状（`experiments/expB2b_calcfall_valid_1783159486.json` ほか）:

| 問 | タイプ | 現状 | 死因（診断済み） | 正解の形 |
|---|---|---|---|---|
| Q0 | office_style | Missing（`gate_reason="capability"`） | `IMAGE_KEYWORDS`の「マーカー」が「**マーカーされている**単語」にマッチ→image_or_graphタグ→能力外ゲート即死。office_styleタグも付いているのに生成器のcapabilityゲートが優先 | `hr、weekday、weathersit、temp`（列挙） |
| Q7 | spreadsheet_calc | Missing（`gate_reason="missing_text"`） | CalcSpecが単一フィルタ＋単一集計のみ。「最も」が`_UNSUPPORTED_QUESTION_HINTS`で意図的ゲート | `32歳`（group_by年齢→ALT_GPT平均のargmax） |
| Q26 | spreadsheet_calc | Missing（同上） | フィルタ後の**ID列の値列挙**がCalcSpecに無い | `train_0077、train_0216、train_0242、train_0722`（、連結） |
| Q25 | office_style | Missing（`gate_reason="missing_text"`） | **未診断**（office_marksに該当データがあるか不明。Task 4で診断先行） | `1. データ理解・EDA` |

- 参考: Q23（office_style）は現構成でAcceptable〜Perfectが出るが不安定（多数決A/M/M）。M02→ファイル対応付けの
  汎用化（next-steps §3のスケジュールMS表方式）は本指示書のスコープ外（Q25診断で同根と判明したら追記して相談）
- run JSONには`gate_reason`（どのゲートで落ちたか: capability/no_context/missing_text/confidence/citation）と
  `raw_answer`・`retrieved_sources`が入っている。切り分けに使うこと

## 関連コードの事実（実装前に必ず実物を確認）

- `src/utils/question_classifier.py`: `IMAGE_KEYWORDS = (".png", ".jpg", "画像", "グラフ", "figure", "マーカー", "折れ線", "図")`、
  `OFFICE_STYLE_KEYWORDS`に「マーカーされている」あり。`classify_question`は各キーワード群に独立マッチ（排他なし）
- `src/generator/answer_generator.py` の `generate()`: 冒頭で `is_capability_blocked(tags)` → image_or_graphタグがあると
  コンテキストの有無に関わらずMissing（`gate_reason="capability"`）
- `src/generator/spreadsheet_calc.py`: `CalcSpec(filters, target_column, aggregation, round_to)`。
  `_UNSUPPORTED_QUESTION_HINTS = ("最も", "ごとの", "ごとに", "毎に", "それぞれ")` が`answer()`冒頭で即ゲート。
  `execute_calc_spec`はpandasで決定的計算、`answer()`は成功時 `Answer(text=str(result), confidence=0.9)`
- `src/retriever/structured_context.py`: `build_office_style_context(question, project_name, store)`、
  `_requested_style_attrs`/`_requested_color_names`/`_narrow_marks_by_question_hints` あり
- `artifacts/office_marks.jsonl`: 行によって`project_name`等がNoneのことがある（2026-07-04に確認）。
  `.get(...) or ""` で防御してから正規化すること
- pipelineの構造化ルート: `_process_one` → タグがあれば `_process_structured`（calc→state/officeビルダーの順、
  calcはtrain.csv不在/ゲート時にfall-through）

---

## Task 1: Q0型の誤ルーティング修正（office_style語がimage能力外ゲートに殺される）

**方針**: `classify_question`で、office_style系キーワード（「マーカーされている」「ハイライトされている」等の
**装飾語**）にマッチした場合、その部分文字列マッチだけを根拠とするimage_or_graphタグを付けない。
一般則で実装する（例: IMAGE_KEYWORDSのマッチ位置がOFFICE_STYLE_KEYWORDSのマッチ範囲に包含されるなら無効、
または「マーカー」を「マーカーされ」を除く形の否定条件付きマッチにする）。**特定の質問文への分岐は禁止**。

- TDD: `tests/test_question_classifier.py`（既存があれば追記）
  - `classify_question("最終報告における、要因分析のページで、マーカーされている単語をすべて抜き出してください。")`
    → `"office_style" in tags` かつ `"image_or_graph" not in tags`
  - 純粋な画像質問（「このグラフの色は？」「画像に写っているものは？」）→ 引き続き `image_or_graph` が付く（退行ガード）
  - 「折れ線グラフのマーカーの色は」のような真の画像文脈は image_or_graph が残ること（マーカー単体語の扱いに注意）
- 全テストPASS → セルフレビュー（step-reviewテンプレ観点1: 分岐の排他）→ N=3実験（実験名 `exp_q0route_valid`）
  - 見る点: Q0の遷移（Missing→回答側）、**image_graph系のQ1が能力外ゲートのままか**（過剰開放でIncorrectを
    作っていないか）、Incorrectゼロ維持
- コミット（`Co-Authored-By:`はCodexの規約に従う）

## Task 2: CalcSpec拡張① group_by + select（Q7型: 「最も〜な<グループ>は」）

**方針**: specに `group_by`（列名）と `select`（`argmax|argmin`）を追加。
`group_by`指定時は `df.groupby(group_by)[target_column].agg(aggregation)` を計算し、
`select`でグループ値（index）を返す。**返り値はグループ値そのもの**（例: `32`。GTの「32歳」とは
接尾辞違い＝official数値規則で同一視される）。

- SYSTEM_PROMPTの【出力形式】に `"group_by"`/`"select"` を追記し、「グループ別の集計」を
  not_applicable例から**削除**（`round_to`同様、無ければnull）
- `_UNSUPPORTED_QUESTION_HINTS`から「最も」を外す。「ごとの/ごとに/毎に/それぞれ」（グループ**列挙**）は残す
- ゲート維持: group_by列・target列が実在しない／グループ0件→従来通りMissing。
  `select`がargmax/argmin以外→parse失敗扱い（None）
- TDD（`tests/test_spreadsheet_calc.py`に追記。既存のFakeパターン=`_call_llm`オーバーライドに合わせる）:
  - `parse_calc_spec`: group_by+selectありJSONのパース、select不正値でNone
  - `execute_calc_spec`: filters＋group_by mean argmax → 期待グループ値（合成DataFrameで決定的に）。
    グループ列不在→None、フィルタ後0行→None
  - `answer()`: 「最も」を含むgroup_by質問がゲートされずspec経由で答える／「ごとの」は引き続きゲート
- N=3実験（`exp_calcgroupby_valid`）: Q7の遷移、Q13（既存calc Perfect）の無傷、Incorrectゼロ維持。
  **Q7の回答をofficial judgeでも確認**（`scripts/calibrate_judge.py`または単発probe — 数値+接尾辞の扱い）
- コミット

## Task 3: CalcSpec拡張② フィルタ後の値列挙（Q26型: 「該当するIDをすべて」）

**方針**: `aggregation: "list"` を追加。フィルタ後の`target_column`の値を**元データの出現順（index順）で
「、」連結**した文字列を返す（GT形式は「train_0077、train_0216、…」— 、連結・空白なし）。

- ゲート: 0件→Missing（従来通り）。**件数上限**（例: 50件超→Missing）を入れる — 列挙の1000トークン制約と、
  誤specで全行を吐く事故（Incorrect直行）の両方を防ぐ保守側ガード
- SYSTEM_PROMPTの出力形式に `"aggregation": "...|list"` を追記（「該当する値をすべて挙げる質問はlist」）
- TDD:
  - `execute_calc_spec`: filters→list → 「、」連結文字列。0件→None。51件→None（上限ガード）
  - `parse_calc_spec`: aggregation="list"を受理
  - `answer()`: str(result)がそのまま回答になる（round_to無視）
- N=3実験（`exp_calclist_valid`）: Q26の遷移（**official probeでGTとの一致形式を必ず確認** —
  要素列挙は部分一致=Incorrectなので、1件でも欠け/余りがあるならMissingの方がまし。件数が合わない場合は採否を保守側に）
- コミット

## Task 4: Q25の診断→（診断結果に応じて）office_style文脈の修正

**診断先行。感覚で直さない**（roadmapの原則）。修正内容は診断結果次第なので、まず以下を確認して
作業ログに記録すること:

1. `artifacts/office_marks.jsonl` に東都提案書（.pptx）のスライド7・赤系色のrunが存在するか
   （NFC正規化して検索。`color`/`color_name`のスキーマと値、`slide_number`の有無を確認）
2. 存在する場合: `build_office_style_context` が「赤で」「P7/スライド7」ヒントで該当runを
   コンテキストに含めているか（`_requested_color_names`が「赤」を拾うか、ページ絞りがあるか）を
   ユニットレベルで再現 → 欠けている絞り込み/レンダリングを一般則で追加（TDD）
3. 存在しない場合: 生成元スキャナ（`scripts/`のoffice_marks生成スクリプト。`AGENTS.md`の再生成手順参照）の
   抽出漏れ（pptxの赤文字runの色表現）を調査 → スキャナ修正＋artifacts再生成（手編集禁止）
4. N=3実験（`exp_q25office_valid`）: Q25とQ0（Task 1後は同じoffice_styleパスに乗る）・Q23の遷移、Incorrectゼロ維持

## Task 5: 記録と提出判断

1. `docs/plan/plan_0703.md` に実測結果を追記（§2.2の続きの節。各実験の多数決before/after・採否・SHA）
2. `docs/plan/2026-07-04-next-steps.md` §3のチェックボックス更新（日付・SHA付き）
3. `docs/daily作業ログ/YYYYMMDD_HHMMSS.md` 新規作成（目的→結果→やったこと（SHA）→学び→残課題）
4. **提出の提案**: このブロック完了時点の構成で `scripts/make_predictions.py` によるtest 100問予測を生成し、
   ユーザーに提出（SIGNATEアップロードは手動）を提案する。ローカル多数決0.28超は前回提出時（0.13〜0.22）から
   大幅改善しており、`plan_0703.md`運用ルール4（各フェーズ完了ごとに提出しLB乖離を監視）に合致。
   生成前に `make_predictions.py` が最新のPipeline構成（レジストリ・artifacts・キャッシュ）と
   同一かをdiffで確認すること（2026-07-04にドリフト事故の前例 `1140bab`）

## スコープ外（次以降のブロック。手を出さない）

- Q21型compact階層pivotの本回収（xlsxの`outlineLevel`/pivotTable XMLから階層抽出 — 設計が別物）
- Q17（「未連絡」言い換え）・Q18（章番号を「4」と誤答する内容不安定）— 実弾-1リスクとして監視中
- §5チャンク改善（生成失敗12問の主対策: Q2/Q9/Q12/Q22/Q25の一部はファイルhit・チャンク内容欠落型）
- Phase 3（version_diff/contract_rule/cross_project/internal_terms）
