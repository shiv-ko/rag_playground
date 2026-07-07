# カバレッジブロック（チャンク境界・検索ランキング・ファイル指定）実装指示書 — Codex向け

> 位置づけ: `2026-07-04-next-steps.md` §5（チャンク・検索の修正）の本実施。LB乖離分析
> （`docs/daily作業ログ/20260704_215500.md`）で確定した「test回答率20%（valid比で半分）＝スコア上限0.20の壁」への
> 主対策。test側の該当規模: text_onlyタグのMissing 39問＋spreadsheet_state 16問。
> **実装者はCodex**（サブエージェント無し環境）。レビューは `.claude/skills/step-review` のテンプレートを
> セルフレビューチェックリストとしてコミット前に1周。開発規約は `.codex/skills/dev-process.md`（TDD・1実験1変更）。

## 実行環境・判定の約束（2026-07-05版。前版からの差分に注意）

- テスト: `.venv/bin/pytest tests/ -v`（現在**330件**、全件PASS維持）
- 評価: 変更ごとに valid 30問をN=3 runし多数決:
  ```bash
  for i in 1 2 3; do .venv/bin/python scripts/run_pipeline.py \
    --data-dir "data/raw/share/共有ドライブ" \
    --questions "data/raw/share/質問回答/questions_valid.csv" --run-name <実験名> --no-cache; done
  .venv/bin/python scripts/majority_eval.py experiments/exp_officegate_valid_*.json --vs experiments/<実験名>_*.json
  ```
- **⚠ 本ブロック最大の footgun: パースキャッシュはコード変更を検知しない**。
  `.cache/parsed_<fp>.pkl` のフィンガープリントは data_dir のファイル構成（相対パス・mtime・サイズ）**のみ**
  （`20260704_005800.md`）。**chunker/parserを変更する本ブロックでは、実験は必ず `--no-cache` を付けるか
  変更後に `rm -rf .cache` すること**。付け忘れると旧チャンクのまま実験して「効果なし」と誤判定する
- **比較元グループ**: `experiments/exp_officegate_valid_*.json`（3run、local多数決 **0.3500**、
  official 0.3333/0.3667帯、HEAD `42c73d2` 時点の採用構成）
- **判定原則（plan_0703 §2.2/§2.3の学び。厳守）**:
  1. mean単独で採否を判定しない。多数決＋不安定問一覧＋raw_answer目視＋（回答形式に関わる変更は）
     official較正 `scripts/calibrate_judge.py <run.json>`
  2. **local judgeはMissing誤判定もIncorrect誤判定もする**（Q25でGT完全一致をIncorrect判定した実績）。
     localのIncorrect増を見たら、まずraw_answerとGTを目視→official較正で確定。
     採否の「Incorrect増は拒否」は**officialのIncorrect問の顔ぶれの変化**で判断する
  3. **official judge自体も同一回答でゆらぐ**（Q6は較正4回中3回Incorrect・1回Perfect）。
     official較正はmeanの絶対値でなく「どの問がIncorrectか」の変化で読む
  4. 決定的パス由来の変更は**新旧runの回答バイト比較**が最も安い無影響証明
     （実験Dで実証。judge経由のmean比較はゆらぎに埋もれる）
  5. 迷ったら保守側（abstain/Missing）。不採用の変更はrevertし、run JSONだけ証跡コミット
- **1実験1変更**: Task 2〜4は独立にN=3で採否確定してから次へ
- NFC/NFD: ファイルパス・ファイル名由来の文字列はNFD。**新しい文字列比較は必ず両辺
  `unicodedata.normalize("NFC", ...)`**（このリポジトリで4回起きた事故）
- 競技規約: 特定の案件名・ファイル名・質問文・正解のハードコード禁止。`question_labels.csv` は
  評価・triage専用（回答生成パスからのimport禁止。triageスクリプトでの参照は適法 — plan_0703 §2.3学び1）

## 前提となる現状（2026-07-05、`42c73d2`時点の実測）

valid 30問の未回収は16問。うち**回収対象はmissing_text 12問**（capability 2問=Q1/Q24の画像系と、
confidence 1問=Q3のcross_projectは意図的ゲートで対象外。Q27はjudgeゆらぎで実際は回答済み）。

`exp_officegate_valid_1783176844.json` の実測（retrieved_sourcesとraw_answer）から見えている死因パターン:

| パターン | 該当問（valid） | 実測の証拠 | 対応Task |
|---|---|---|---|
| **タイトルスライド汚染**: top-5が各pptxの`slide_1`（表紙）で埋まり、内容スライドが入らない | Q2, Q12, Q19（他のMissingでも頻出） | Q19のtop-5中3枠が別ファイルの`slide_1`。Q2/Q12も同様 | Task 3 |
| **800字機械切り**: docxが`full_chunkN`（境界無視の固定長）で条件・文が泣き別れ | Q28（CAT判定条件の泣き別れ・確定済み）, Q12（契約書chunk1/8のみhit）, Q4 | `src/parsers/chunker.py`は`doc.text[start:end]`の素朴スライス | Task 2 |
| **ファイル指定の不一致**: 質問が明示したファイルと別ファイルを掴む | Q22（NB01_eda.ipynb指定→01_eda.ipynbをhit）, Q10, Q16 | Q22のsourcesに指定ファイル無し | Task 4 |
| 未分類（再診断が必要） | Q9, Q15, Q21ほか | Phase 0 triage（`missing_triage_20260704.md`）は朝時点の構成で古い | Task 1 |

- スコア基準: 前回提出LB 0.03333（公開LBは約30問サブセット・1/30刻み。`plan_0703.md` §1.1.1）。
  **提出は本ブロック完了時に実験D（`869a1ff`、未提出）とまとめて1回**（運用ルール4「無駄撃ちしない」）

## 関連コードの事実（実装前に必ず実物を確認）

- `src/parsers/chunker.py`: `CHUNK_SIZE=800, CHUNK_OVERLAP=100`。`chunk_documents`は
  `doc.text[start:end]` の固定長スライスで**行・文・段落境界を一切見ない**。location命名は`{元location}_chunkN`
- `src/parsers/office_parser.py`: docxは`location="full"`の1 Document（→chunkerで`full_chunkN`化）。
  pptxはスライド単位`slide_N`、xlsxはシート単位`sheet_<name>`
- `src/parsers/notebook_parser.py`: セル単位`cell_{i}_{cell_type}`のDocument（→800字超のセルはchunkerで分割）
- `src/retriever/project_scoped_retriever.py`: `ProjectScopedRetriever`（案件名でスコープ）。
  下層は`src/retriever/hybrid_retriever.py`（keyword+vector、`search(query, top_k=5)`）。
  クエリは`src/retriever/query_expander.py`の`QueryExpander`（term_registry）で拡張済みの文字列
- 診断ツールが既にある: `scripts/eval_retrieval.py`（検索recall計測）と `scripts/triage_failures.py`
  （検索/生成の切り分け表生成。Phase 0 Task 3の成果物）。**新規に書く前にこの2つの入出力を確認**
- run JSONの`retrieved_sources`は`ファイル::location`形式、`raw_answer`はゲート前のLLM出力
- 期待ファイルの実在確認は `find "data/raw/share/共有ドライブ" -name "<パターン>"` で（NFDに注意。
  `-name`はバイト一致なので `find ... | grep -i` の方が安全）

---

## Task 1: 再triage（診断のみ。コード変更なし）

Phase 0のtriage表は朝時点（改善前）の構成で古い。**現構成での死因を確定してからTask 2〜4に入る**。

1. `scripts/triage_failures.py --help` と `scripts/eval_retrieval.py --help` で入出力を確認し、
   現HEADの構成でvalidの検索recall＋切り分け表を再生成する（実行できない/引数が現状と合わない場合は
   最小修正して使う。判定ロジックの書き換えはしない）
2. missing_text 12問（Q0,Q2,Q4,Q9,Q10,Q12,Q15,Q16,Q19,Q21,Q22,Q28）それぞれについて
   「①正解を含むファイルのチャンクがインデックスに存在するか ②top-5に入っているか
   ③入っているのに生成が拾えないか」を表にする（GT参照はtriage用途なので適法）
3. 結果を `docs/plan/missing_triage_20260705.md` に保存し、**上の死因パターン表と食い違う問があれば
   Task 2〜4の対象リストを修正**（表の3パターンに該当しない問は本ブロックで無理に追わない —
   Q0=M02対応付け、Q21=compact pivot、Q9=version_diff、Q15=cross-project集計は別トラック）。
   **③型（正解チャンクがtop-5に入っているのに生成が拾えない）が2問以上あれば**、修正案を出す前に
   triage表へその旨を明記して指示書の発行者に相談（チャンクヘッダ付与等の候補はあるが本ブロック外で判断）
4. コミット（診断結果のみ。実装なし）

## Task 2: チャンカーの境界スナップ（泣き別れ対策）

**方針**: `chunk_documents` を、チャンク終端を固定位置でなく**直前の自然境界にスナップ**する実装に変更。
一般則: 終端候補位置から遡って `\n\n` → `。` → `\n` の優先順で境界を探し、
`chunk_size - 200` より手前まで見つからなければ従来通り固定長で切る（無限ループ・極小チャンク防止）。
オーバーラップは境界スナップ後の終端から従来と同じ意味で適用。location命名（`_chunkN`）は変えない
（構造化パスや既存テストが参照している可能性があるため。変える場合はgrepで影響確認）。

- TDD（`tests/test_chunker.py`。無ければ新規）:
  - 900字で500字目に`\n\n`がある文書 → 1チャンク目が`\n\n`で終わる（文が泣き別れない）
  - 境界なしの900字連続文字列 → 従来通り800字で切れる（フォールバック）
  - `if cond1 and\ncond2:` のような複数行条件を含むコードセル → 条件式が同一チャンクに収まるケースを1つ
  - 800字以下の文書は無変更（既存挙動の退行ガード）
  - 全チャンク連結が元テキストを被覆する（オーバーラップ考慮で欠落なし）
- **実験は`--no-cache`必須**（上のfootgun）。N=3（実験名 `exp_chunkbound_valid`）:
  - 見る点: Q28（泣き別れ確定問）の遷移、**全体の悪化問ゼロ**（チャンク割りが全ファイルで変わるため
    影響は全問に及ぶ。不安定問はraw_answer目視）、officialのIncorrect顔ぶれ不変
  - チャンク総数の変化を確認しログに記録（インデックス構築ログの「N チャンク取得」）
- コミット

## Task 3: タイトルスライド汚染の解消（検索ランキング）

**2026-07-07完了（案Aのみ）**: `ProjectScopedRetriever.search()`にスコープ後クエリからの
案件名・エイリアストークン除去を実装（`782aead`）。TDD3ケース（トークン除去・除去後空文字→
元クエリフォールバック・全体検索時は無変更）＋BM25実データ想定の回帰テスト（cover slide型
チャンクが除去前は誤って上位化することを確認してから修正）で全件PASS。
**未実施**: 診断先行のtop-5内訳集計（Task 1診断）と、実データでのN=3実験・official較正・
案Bの要否判断は`data/raw`が無い本セッションでは実施不能。次回実データ環境で
`exp_rankfix_valid`のN=3実験から着手する。

**診断先行**: Task 1の表で、top-5に入った`slide_1`（および各pptxの表紙相当）が正解チャンクを
押し出しているケースを数える。3問以上で確認できたら実装に進む。

**方針（一般則で、効果の小さい順に試す。1実験1変更なので別実験に分ける）**:
- 案A（推奨・まず単体で）: **プロジェクトスコープ後のクエリから案件名・エイリアストークンを除去**。
  スコープ内では案件名トークンは全チャンク共通で識別力ゼロなのに、表紙スライド（案件名の密度が高い）を
  不当に上位化している。`ProjectScopedRetriever`のスコープ確定後、検索クエリから該当プロジェクトの
  `project_aliases`のトークンを取り除く（両辺NFC正規化。除去後クエリが空になる場合は元クエリを使う）
- 案B（案Aで不足なら別実験で）: 同一ファイルからtop-5に複数チャンクが入る場合の多様化
  （同一ファイル上限2件など）。**過剰に削ると列挙系（同一ファイル複数チャンクが正しい）を壊す**ので、
  案Aの結果を見てから判断
- TDD（案A）:
  - スコープ済み検索で、クエリ「〇〇社の評価指標」から「〇〇社」トークンが除去されて検索されること
    （FakeStoreでクエリをキャプチャする既存テストパターンに合わせる）
  - エイリアス除去後が空文字になるクエリ → 元クエリのまま
  - スコープが決まらない（全体検索）場合は除去しない
- N=3（`exp_rankfix_valid`）: Q2/Q12/Q19の遷移＋**回答済み問の悪化ゼロ**。
  officialのIncorrect顔ぶれ不変を較正で確認（回答が変わる変更なので較正必須）
- コミット

## Task 4: 質問中の明示ファイル名によるスコープ絞り

**診断先行**: Q22の指定ファイル`NB01_eda.ipynb`が実データに存在するか確認
（`find ... | grep -i "nb01"`）。存在しない場合、正解の所在ファイルを特定してから方針を決める
（例: 質問側の呼称と実ファイル名の対応ルールが必要なら、それはM02型の対応付け問題なのでスコープ外へ）。

**方針**（指定ファイルが実在する前提）: 質問に**拡張子付きファイル名**（`\S+\.(ipynb|py|csv|xlsx|docx|pptx|pdf)`
の正規表現マッチ）が含まれる場合、検索結果をそのファイル名（NFC正規化・大文字小文字無視で
`source_path`の末尾一致）のチャンクへ**優先**する。実装は「該当ファイルのチャンクがtop-k内に1件も
無ければ、該当ファイル内の上位チャンクでtop-kの下位を置換」の保守形にする（全置換はランキング破壊のリスク）。
該当ファイルがインデックスに無ければ何もしない（Missing方向・安全側）。

- TDD:
  - 質問「`foo.ipynb`の出力は？」＋インデックスに`foo.ipynb`と`bar.ipynb` → top-kに`foo.ipynb`の
    チャンクが必ず1件以上入る
  - 質問にファイル名なし → 挙動不変
  - 指定ファイルがインデックスに無い → 挙動不変
  - `FOO.IPYNB`/NFD混在ファイル名でも一致する（正規化テスト）
- N=3（`exp_filehint_valid`）: Q22（と再診断でこの型に分類された問）の遷移、回答済み問の悪化ゼロ
- コミット

## Task 5: 記録と提出判断

1. `plan_0703.md` §2.3の実験表にE/F/G…行として追記（多数決before/after・採否・SHA）
2. `2026-07-04-next-steps.md` §5のチェックボックス更新（日付・SHA）
3. `docs/daily作業ログ/` に新規ログ（目的→結果→やったこと（SHA）→学び→残課題）
4. **提出**: 本ブロックの採用分＋実験D（`869a1ff`、未提出）を含む構成で
   `scripts/make_predictions.py` を実行（**事前に`rm -rf .cache`** — 提出経路はキャッシュ不使用だが
   検証runとの整合のため）。予測の検品（100問・ID重複なし・最長回答のトークン確認・
   前回`predictions.csv`とのdiff目視で-1型ミスマッチがないか）→ zip作成 → ユーザーに手動提出を提案

## スコープ外（次以降のブロック。手を出さない）

- Q21型compact階層pivot（outlineLevel/pivotTable XML — 設計が別物）
- Q0の「M02資料」→ファイル対応付けの汎用化（next-steps §3の継続）
- Q3/Q15のcross-project集計、Q9のversion_diff本回収（Phase 3）
- Q1/Q24の画像・図表読解（能力外ゲート維持が正）
- Q17「未連絡」言い換え・Q18章番号（-1リスク監視中。回答形の実験は本ブロックと混ぜない）
