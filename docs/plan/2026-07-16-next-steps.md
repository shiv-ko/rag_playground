# 次アクション計画（2026-07-16）

## 現在地

- 拡張子なしの実在ファイルstemを質問文から検出し、該当ファイルを検索上位へ補完する修正を実装済み（`45a2048`）。
- valid検索recallはハイブリッド検索導入時の0.793から **0.862（25/29）** へ改善。Q17は`カラム説明.md`がrank 1、single_textは4/4。
- 629 tests pass、step-reviewのCONFIRMED 2件（助詞境界、全件検索の性能問題）も修正済み。

## 次に行うこと

- [x] ユーザ承認後、`q17_filescope_valid_r1〜r3`を実行。local mean 0.6167 / 0.6333 / 0.6167、Q17は3run共通で「未連絡」。（2026-07-16）
- [x] r1をofficial較正。official mean **0.8000**、Q17はPerfect、直前ハイブリッド版0.7333から+0.0667。official Incorrectは既知Q6のみで新規0。**採用確定**。（2026-07-16）
- [x] test predictions.csvをN=3で再生成し、`submission_20260716_q17-filescope3run.zip`を作成・形式検証。（2026-07-16、`2615251`で提出生成の埋め込みキャッシュ配線漏れも修正）
- [ ] `submission_20260716_q17-filescope3run.zip`をSIGNATEに手動提出し、LBを記録する。
- [ ] API送信を承認しない場合は、検索recall改善までを根拠に実装を維持し、Phase 5のローカル作業へ進む。

## 較正結果からの新規発見（2026-07-16、`judge_calibration_1784145455.json`）

- **Q25はofficial Perfectだった**（回答「1. データ理解・EDA」はGT完全一致）。local judgeがIncorrectと誤判定していただけで、「既知の書式抽出パターンの誤答」という従来認識は誤り。**対策不要**。
- **唯一のofficial IncorrectはQ6**（かえで総合病院PivotTable）。回答は抽出条件・集計内容ともGTと整合するが、GTにない集計値`= 873.6978985`を付加しており、これがIncorrect化の原因である可能性が高い（`f301c6c`で「条件と集計内容の完全回答」を強制した後も未解決）。
- **local judgeのagreementが67%と低い**。Q17（GT完全一致の「未連絡」）をMissing、Q25（GT完全一致）をIncorrectと誤判定。実験の採否判断がlocal判定に依存しているため、判定精度自体が意思決定リスクになっている。

## 次アクション計画（2026-07-16策定、優先順）

判断原則は strategy.md（守り先行 / 該当問数×改善確率×得点差 / 1実験1変更）に従う。

### 1. 【最優先・残タスク】提出物の作成

- [ ] `make_predictions.py --runs 3` でtest predictions.csvを再生成し、前回提出とのdiffで「新規の危険な誤答パターンがない」ことを確認する。
- [ ] `submission_20260716_q17filescope3run.zip` を作成する（SIGNATE提出はユーザー判断）。
- [ ] LB結果を `plan_0703.md` §1.1.1に記録する。

**期待値**: testにもQ17類似の「拡張子なし名指しファイル」問があればLB +1/30以上。valid officialは0.7333→0.8000で過去最高。

### 2. Q6対策（唯一の残存official Incorrect、-1/30）

- [ ] pivot系answererの回答から、質問が求めていない集計値の付加を止める（または値の検証を通ったときのみ付与する）方向で診断・修正する。
- [ ] 汎用性チェック: 「質問が求める要素のみを返す」原則としてpivot/集計系全体に一般化できる設計か確認（Q6固有の合わせ込み禁止）。
- [ ] valid N=3+official較正で採否判断（Q6がPerfect/Missingへ、新規Incorrect 0）。

**期待値**: Incorrect→Perfectで+2/30（official 0.8667相当）、最低でも→Missingで+1/30。

### 3. local judge較正の改善（実験サイクルの意思決定品質）

- [ ] 蓄積済み `judge_calibration_*.json`（20件）を「official判定の回帰セット」として、local judgeプロンプトの改善（GT完全一致をMissing/Incorrect誤判定するパターンの修正）を検証する。API不要のオフライン分析から着手可能。
- [ ] agreement 67%→85%以上を目標。改善後は過去runの再評価はしない（前向きにのみ適用）。

### 4. Phase 5前倒し着手（plan_0703 §6.4の判断どおり）

能力追加は収穫逓減に入ったため、較正・安定化へ軸足を移す:

- [ ] confidence_threshold のタイプ別グリッドサーチ（既存run JSONの再集計、API不要）
- [ ] 3時間制限の本番実測（hybrid検索ON状態のtest 100問end-to-endは未実測）
- [ ] 再現性検証（Q8/Q9/Q94のanswered⇄Missing反転が既知。同一入力2回実行の一致率を計測）

### 保留継続

- Q79/Q92向け新規集計answerer（test限定2問）・座席表OCR（test Q13/Q46）・test Q66画像特定: 期待値低、安全なMissing維持。
