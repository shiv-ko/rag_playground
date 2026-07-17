# 次アクション計画（2026-07-17）

## 現在地

- LB **0.2333（7/30）**、過去最高（`submission_20260716_q17-filescope3run.zip`、`cc013f1`で記録）。valid officialは**0.8000**でこちらも過去最高。
- valid officialの残存Incorrectは**Q6のみ**（かえで総合病院PivotTable。GTにない集計値`= 873.6978985`を付加していることが原因の可能性が高い）。
- local judgeとofficial judgeのagreementが**67%**と低く、実験採否の意思決定リスクになっている（Q17/Q25のGT完全一致をMissing/Incorrectと誤判定した実績）。
- plan_0703 §6.4の判断どおり、能力追加は収穫逓減に入っており、**Phase 5（較正・安定化）の前倒し**が方針。

## 優先順位（strategy.md の原則: 守り先行 / 該当問数×改善確率×得点差 / 1実験1変更）

### 1. Q6対策 — pivot系answererの「求められていない集計値の付加」を止める

唯一のvalid official Incorrect（-1/30）。`f301c6c`で条件・集計内容の完全回答を強制した後も未解決。

- [ ] 診断: Q6の生成トレースを確認し、集計値`= 873.6978985`がどこで付加されるかを特定する（`src/generator/answer_generator.py` / `src/retriever/structured_context.py` あたりのpivot系コンテキスト・プロンプト）。
- [ ] 修正方針: 「質問が求める要素のみを返す」を原則としてpivot/集計系全体に一般化する（値の付加は検証を通ったときのみ、または質問が値を求めるときのみ）。**Q6固有の合わせ込みは禁止**。
- [ ] 検証: valid N=3 + official較正で採否判断。採用条件は「Q6がPerfect/Missingへ、かつ新規Incorrect 0」。
- 期待値: Incorrect→Perfectで+2/30相当（official 0.8667）、最低でも→Missingで+1/30。testのpivot系（Excel表示状態21問）にも同型の過剰付加があれば上積み。

### 2. local judge較正の改善（API不要・オフラインで着手可）

- [ ] `experiments/judge_calibration_*.json`（20件蓄積済み）を「official判定の回帰セット」に整形するスクリプトを作る（question_id × local判定 × official判定 × 回答文）。
- [ ] 不一致パターンを類型化する。既知: GT完全一致の短い回答（「未連絡」等）をMissing扱い、GT完全一致の列挙（「1. データ理解・EDA」）をIncorrect扱い。
- [ ] local judgeプロンプトを修正し、回帰セットでagreement **67%→85%以上**を確認してから採用。過去runの再評価はしない（前向き適用のみ）。
- 期待値: 直接のLB上積みは無いが、以降の全実験の採否判断の精度が上がる（誤棄却・誤採用の削減）。

### 3. Phase 5前倒し（較正・安定化）

- [ ] **confidence_thresholdのタイプ別グリッドサーチ**: 既存run JSONの再集計のみでAPI不要。設問タイプ別に「答える/Missingに逃がす」損益分岐を求める（strategy.md §1.2: 要素列挙・数値は閾値高め）。※判定はlocal judge依存のため、#2の後に実施すると信頼度が上がる。
- [ ] **3時間制限の本番実測**: hybrid検索ON + 埋め込みキャッシュ（`2615251`）状態で、test 100問×3runのend-to-end所要時間を計測し、plan_0703に記録。超過リスクがあれば並列化・run数削減の判断材料にする。
- [ ] **再現性検証**: 同一入力2回実行の一致率を計測。既知のQ8/Q9/Q94のanswered⇄Missing反転の原因（温度・多数決の割れ方・API 529）を切り分け、シード・温度固定で潰せるか確認。本番judgeは1回のみのため、不安定さはそのままLB分散になる。

### 4. 提出

- [ ] Q6対策が採用確定したら test predictions.csv をN=3で再生成し、`submission_YYYYMMDD_<内容>.zip` を作成・提出してLBを記録（1変更1提出でLBとの対応を保つ）。

### 保留継続（着手しない）

- Q79/Q92向け新規集計answerer（test限定2問）・座席表OCR（test Q13/Q46）・test Q66画像特定: 期待値低、安全なMissing維持。

## 実行環境の注記

- #2（judge較正の回帰セット分析）と#3のグリッドサーチは既存JSONの再集計であり**API・実データ不要**。クラウドセッションでも実施可能（`2026-07-08-cloud-implementable-tasks.md`の分類と同型）。
- #1の検証run・#3の時間実測・#4の提出はAPIキーと`data/raw/`が要るため、ローカル環境で行う。
