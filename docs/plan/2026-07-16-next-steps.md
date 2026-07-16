# 次アクション計画（2026-07-16）

## 現在地

- 拡張子なしの実在ファイルstemを質問文から検出し、該当ファイルを検索上位へ補完する修正を実装済み（`45a2048`）。
- valid検索recallはハイブリッド検索導入時の0.793から **0.862（25/29）** へ改善。Q17は`カラム説明.md`がrank 1、single_textは4/4。
- 629 tests pass、step-reviewのCONFIRMED 2件（助詞境界、全件検索の性能問題）も修正済み。

## 次に行うこと

- [x] ユーザ承認後、`q17_filescope_valid_r1〜r3`を実行。local mean 0.6167 / 0.6333 / 0.6167、Q17は3run共通で「未連絡」。（2026-07-16）
- [x] r1をofficial較正。official mean **0.8000**、Q17はPerfect、直前ハイブリッド版0.7333から+0.0667。official Incorrectは既知Q6のみで新規0。**採用確定**。（2026-07-16）
- [x] test predictions.csvをN=3で再生成し、`submission_20260716_q17-filescope3run.zip`を作成・形式検証。（2026-07-16、`2615251`で提出生成の埋め込みキャッシュ配線漏れも修正）
- [x] `submission_20260716_q17-filescope3run.zip`をSIGNATEに提出。LB **0.23333333333333334（=7/30）**、前回0.2から+1/30で過去最高更新。（2026-07-16）

## 較正結果からの新規発見（2026-07-16、`judge_calibration_1784145455.json`）

- **Q25はofficial Perfectだった**（回答「1. データ理解・EDA」はGT完全一致）。local judgeがIncorrectと誤判定していただけで、「既知の書式抽出パターンの誤答」という従来認識は誤り。**対策不要**。
- **今回の較正で唯一のofficial IncorrectはQ6**（かえで総合病院PivotTable）。回答は抽出条件・集計内容ともGTと整合するが、GTにない集計値`= 873.6978985`を付加しており、これがIncorrect化の原因である可能性が高い（`f301c6c`で「条件と集計内容の完全回答」を強制した後も未解決）。ただしofficial judgeにも既知の判定ゆらぎがあるため、単発判定だけで原因確定とはしない。
- **local judgeのagreementが67%と低い**。Q17（GT完全一致の「未連絡」）をMissing、Q25（GT完全一致）をIncorrectと誤判定。実験の採否判断がlocal判定に依存しているため、判定精度自体が意思決定リスクになっている。

## 次アクション計画（2026-07-16策定、優先順）

判断原則は [`docs/strategy.md`](../strategy.md)（守り先行 / 該当問数×改善確率×得点差 / 1実験1変更）に従う。

### 1. 【完了】提出物の作成・LB確認

- [x] `make_predictions.py --runs 3` でtest predictions.csvを再生成し、前回提出とのdiff 9問を確認。
- [x] `submission_20260716_q17-filescope3run.zip` を作成・提出。
- [x] LB **0.23333333333333334（=7/30）**を `plan_0703.md` §1.1.1に記録。

**期待値**: testにもQ17類似の「拡張子なし名指しファイル」問があればLB +1/30以上。valid officialは0.7333→0.8000で過去最高。

### 2. Q6対策（直近較正で唯一のofficial Incorrect、-1/30）

- [x] 出力組み立て経路を追跡し、機械直答テンプレートが内部検証用の最大値を回答へ無条件付加していたと特定。（2026-07-16、`6ca3746`）
- [x] 最大値の存在確認は完全性ゲートとして維持しつつ、質問が求めない集計値だけを最終回答から除外。（2026-07-16、`6ca3746`）
- [x] 汎用性チェック: 案件名・列名・値に依存しないテンプレート変更と回帰テストを実装。値欠落時のMissingゲートを維持し、全631 tests pass、step-review問題なし。（2026-07-16、`6ca3746`）
- [x] 外部通信なしの実データQ6 N=3で、回答文字列・answer path・ゲート状態が完全一致。（2026-07-16）
- [x] full valid N=3を実行。local mean 0.6500 / 0.6167 / 0.6333、Q6は3run同一回答・Perfect。回答経路と取得根拠に変更なし。（2026-07-16）
- [x] r1をofficial較正。mean **0.8333**（修正前0.8000）、Q6のみIncorrect→Missing、official Incorrect 0、他29問のofficialラベル変更0。最低目標+1/30を達成したため採用確定。（2026-07-16、`judge_calibration_1784184775.json`）

**実測**: Incorrect→Missingで+1/30、official 0.8000→**0.8333**。新規Incorrect・他問退行なし。

### 3. 3時間制限の本番実測（ハード制約を先に確認）

- [x] hybrid検索ONでtest 100問を実測。coldはindexだけで3時間33分を超えたためgenerationを中止、warm単発は3分9.47秒、標準N=3は7分25.50秒。（2026-07-16）
- [x] 区間別実測: cold parse 14秒 / embedding index 3時間32分49秒。warm index 66秒 / generation 120.5秒。N=3はindex 65秒 / run約121秒・125秒・約135秒（多数決/出力込み）。（2026-07-16）
- [x] 条件記録: macOS 26.5.2 arm64、hybrid ON、`cl-nagoya/ruri-base`、generator `claude-sonnet-5`、top-k 5、concurrent 5、threshold 0.4、test 100問。（2026-07-16）
- [ ] 採用条件: warm N=3は3時間/2時間目標を大幅クリア。一方、未知データを想定したcold indexがgeneration前に3時間超過したため未達。再現性検証より先に、埋め込み初回構築の高速化または再利用可能な事前キャッシュ設計を行う。

### 4. 再現性検証

- [ ] 同一入力・同一設定でtest単発を2回実行し、最終回答・answered/Missing・answer pathの一致率を計測する。
- [ ] Q8/Q9/Q94に加え、全100問のflip一覧を出す。検索結果が同一かも比較し、検索・生成・ゲートのどこで揺れたかを分離する。
- [ ] N=3多数決後の一致率も記録し、不一致問は保守的構成の候補にする。

### 5. local judge較正の改善（実験サイクルの意思決定品質）

- [x] `judge_calibration_*.json` を「質問×回答×GT」で重複除去し、official判定の回帰データを作成（`cb88bb4`、`build_regression_dataset`）。評価専用、回答生成コードから未参照。
- [x] 固定dev/holdoutを`FIXED_DEV_FILE_NAMES`/`FIXED_HOLDOUT_FILE_NAMES`で分離し、holdoutを見ずにdevだけでプロンプト調整。officialの同一回答への判定ゆらぎは`official_label_unstable`でフラグ化・`stable_metrics`から除外（`e958100`）。（2026-07-16）
- [x] 解析エラー時の1回再試行を実装（`17ce9fc`）。dev stable agreementは81.6%（v3）で85%未達。
- [x] 誤判定7件中3件が同一パターン（Q17「pdays=-1→未連絡」への同義言い換えをAcceptable誤判定）と特定。ルール4（短答の言い換えはIncorrect）とルール5（軽微な不完全さはAcceptable）の衝突が原因と判明。
- [x] ルール6追加でルール4を優先するようプロンプト修正（`3413b52`、TDD・step-review済み、669 tests pass）。dev再判定でstable agreement **89.5%**（v4/v5で完全再現、ノイズでないことを確認）。採用条件クリア。（2026-07-16）
- [x] 採用条件を確認: holdout stable agreement **89.7%**（39件中35件一致）、Incorrect recall 0.333、MAE 0.103。dev改善前のbaseline（agreement 0.816未満、recall 0.286、MAE 0.237）より全指標が改善しており悪化なし。（2026-07-16、`judge_recheck_holdout_1784206351.json`）

### 6. confidence thresholdのタイプ別探索

能力追加は収穫逓減に入ったため、較正・安定化へ軸足を移す:

- [ ] 既存run JSONの`confidence`・`routing_tags`・`raw_answer`を使い、まず現行閾値からの**引き上げのみ**をオフライン再集計する。回答→Missingは0点として反実仮想評価できる。
- [ ] 閾値引き下げでMissing→回答となる候補は、保存済み`raw_answer`にjudge結果がないため、オフライン集計だけで採否しない。候補を別途judgeしてから評価する。
- [ ] タイプは評価専用`question_labels.csv`を本番処理に流用せず、実行時に生成される`routing_tags`で定義する。
- [ ] 開発/holdoutを分離し、タイプ別の最低件数を満たさない場合は個別最適化せず共通閾値を維持する。
- [ ] 最終的に「最高スコア構成」と「保守的構成（ゲート強め）」の2提出候補を固定する。

### 保留継続

- Q79/Q92向け新規集計answerer（test限定2問）・座席表OCR（test Q13/Q46）・test Q66画像特定: 期待値低、安全なMissing維持。
