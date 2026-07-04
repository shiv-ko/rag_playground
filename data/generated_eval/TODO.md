# generated_eval TODO

このディレクトリは本物の valid/test とは混ぜない。目的はスコア推定ではなく、artifact由来で正解を機械生成できる能力別の回帰テストを増やすこと。

## 方針

- `questions.json` は生成評価用。`questions_valid.csv` / `docs/question_labels.csv` には混ぜない
- 正解をartifactや決定的計算から作れるケースだけ採用する
- 指標は全体meanより、タイプ別pass率・Incorrect発生・ルーティング失敗を見る
- validに似せすぎず、少し軸をずらした問題を入れる

## 追加したい高度ケース

### 1. 曖昧ルーティング

- [ ] 「ハイライト」が Excel / docx / pptx のどれかを正しく振り分ける
- [ ] ファイル名なしで、案件略称と資料種別だけから正しいartifactに到達する
- [ ] 正式名称・略称・英字略称を混ぜても同じ案件に解決する
- [ ] 該当artifactがない場合に通常検索へ誤って流れてIncorrect化しない

### 2. 列挙完全性

- [ ] タスクIDが5件以上ある条件で全件列挙できる
- [ ] 担当者が `A / B` の複合値でも片方の名前で拾える
- [ ] フェーズ・担当者・ステータス・成果物の各列で列挙問題を生成する
- [ ] 該当0件の条件ではMissingに倒す
- [ ] 部分列挙をPerfect扱いしない検査を追加する

### 3. 数値・集計

- [ ] 条件付き平均・件数・合計をtrain.csvから決定的に作る
- [ ] groupby後の最大/最小行を問う
- [ ] 同率最大・同率最小の扱いをテストする
- [ ] 0件マッチ・列名不存在・非数値列集計はMissingになる
- [ ] 回答は値のみ、必要最小限の単位のみになる

### 4. Pivot / Excel状態

- [ ] merged cell由来の空欄をforward-fillしてPivot行を読む
- [ ] 複数数値列の中から質問中の列名で対象列を選ぶ
- [ ] autoFilter条件が複数列あるケースを生成する
- [ ] autoFilter条件がないが非表示行だけあるケースは保守的にMissingにする
- [ ] ハイライトセルが複数ある場合にセル番地・シート名で曖昧性を解消する

### 5. Office style

- [ ] docx黄色ハイライトとpptx背景色を区別する
- [ ] ページ番号・スライド番号指定で候補を絞る
- [ ] 同一ファイル内に太字/下線/イタリックが複数あるケースを作る
- [ ] 句読点だけ、空白だけ、短すぎるrunを除外する
- [ ] 抽出件数が多すぎる場合はMissingまたは要約せず全件列挙できる範囲に制限する

### 6. ネガティブケース

- [ ] 別案件の似たファイルに引っ張られない
- [ ] 曖昧すぎる質問では答えずMissingになる
- [ ] 未実装タイプ（version_diff等）は専用実装前に通さない
- [ ] cross_project系は専用実装前に保守的にMissingへ倒す

## 優先順

1. spreadsheet_state hard cases: filter / Pivot / highlight ambiguity
2. spreadsheet_calc hard cases: groupby / argmax / 0件 / 列不存在
3. office_style hard cases: docx/pptx区別・ページ指定・ノイズ除外
4. schedule/list extraction hard cases: 複数件・複合担当者・0件
5. version_diff / contract_rule / cross_project は実装開始時に追加

## 実行メモ

```bash
.venv/bin/python scripts/build_generated_eval.py --per-type 20
.venv/bin/python scripts/run_generated_eval.py
```

結果は `experiments/generated_eval/` に保存する。本物validの実験結果とは比較軸を分ける。
