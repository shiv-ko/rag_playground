# generated_eval TODO

このディレクトリは本物の valid/test とは混ぜない。目的はスコア推定ではなく、artifact由来で正解を機械生成できる能力別の回帰テストを増やすこと。

## 方針

- `questions.json` は生成評価用。`questions_valid.csv` / `docs/question_labels.csv` には混ぜない
- 正解をartifactや決定的計算から作れるケースだけ採用する
- 指標は全体meanより、タイプ別pass率・Incorrect発生・ルーティング失敗を見る
- validに似せすぎず、少し軸をずらした問題を入れる

## カバレッジ現状 (2026-07-04)

| question type | valid+test 出現数 | generated_eval 現状 | 目標 | artifact | 状態 |
|---|---|---|---|---|---|
| spreadsheet_state | ~18 | 11 (filter×1, highlight×5, schedule_フェーズ名×5) | 30+ | schedule_tasks, highlight_blocks, sheets | 🟡 一部 |
| office_style | ~10 | 5 (太字/下線/イタリック) | 15+ | office_marks | 🟡 一部 |
| internal_terms | ~12 | 0 | 15+ | term_registry.json | 🔴 未着手 |
| contract_rule | ~11 | 0 | 10+ | (要抽出) | 🔴 未着手 |
| version_diff | ~11 | 0 | 15+ | version_pairs.jsonl, version_diff_poc.jsonl | 🔴 未着手 |
| spreadsheet_calc | ~9 | 0 | 15+ | spreadsheet_cells.jsonl, formula_cells | 🔴 未着手 |
| cross_project | ~8 | 0 | 5+ | document_registry.jsonl | 🔴 未着手 |
| single_text | ~10 | 0 | 5+ | document_registry.jsonl | ⚪ P2 |
| list_extraction | ~5 | 0 | 5+ | schedule_tasks | ⚪ P2 |
| negative_case | (散在) | 0 | 5+ | 全般 | ⚪ P2 |

**合計: 4タイプ 16問 → 目標 10+タイプ 100+問**

## 未使用artifact一覧

| artifact | サイズ | 内容 | 対象type |
|---|---|---|---|
| term_registry.json | 24KB | 略称⇔正式名の辞書 (PP, CT, PL, MM, FR等) | internal_terms |
| version_pairs.jsonl | 9KB (12 pairs) | 旧→新バージョンペア | version_diff |
| version_diff_poc.jsonl | 26KB | 差分サンプル (added/removed/changed) | version_diff |
| spreadsheet_cells.jsonl | 3.6MB (5891行) | セルレベルデータ | spreadsheet_calc |
| train_xlsx_formula_cells.jsonl | 29.5MB | 数式セル | spreadsheet_calc |
| train_xlsx_small_sheet_cells.jsonl | 4.9MB | Pivot/小規模シートのセル | spreadsheet_state |
| train_xlsx_highlight_context.jsonl | 4.3MB | ハイライト周辺文脈 | spreadsheet_state |
| document_registry.jsonl | 296KB (417件) | 全ファイルカタログ | cross_project, routing |
| highlight_cells.jsonl | 853KB | ハイライトセル一般 | spreadsheet_state |
| spreadsheet_sheets.jsonl | 12KB | シートメタデータ | spreadsheet_state |

## 優先順 — ギャップ分析に基づく

### 🔴 P0 — 高頻度 & artifact準備済み

#### 1. version_diff (valid+test: ~11問, artifact: version_diff_poc.jsonl)

- [ ] `version_diff_poc.jsonl` の added/removed/changed サンプルから「旧→新で追加された項目」系を生成
- [ ] `version_pairs.jsonl` (12ペア) の各ペアから変更点の質問を生成
- [ ] 削除された記述を問う問題 (「旧版にあって新版で削除された条項は？」)
- [ ] 変更箇所の数を問う問題 (「何箇所変更されましたか？」)
- [ ] 目標: 15問以上

#### 2. internal_terms (valid+test: ~12問, artifact: term_registry.json)

- [ ] 略称→正式名称の変換テスト (PP→?, CT→?)
- [ ] 正式名称→略称の逆引きテスト
- [ ] 文中の略称を含む質問 (「PP案件のCT担当者は？」)
- [ ] 未登録略称に対するMissing/不明回答テスト
- [ ] 目標: 15問以上

#### 3. spreadsheet_calc (valid+test: ~9問, artifact: spreadsheet_cells.jsonl)

- [ ] 条件付き平均・件数・合計を `spreadsheet_cells.jsonl` から決定的に作る
- [ ] groupby後の最大/最小行を問う
- [ ] 同率最大・同率最小の扱いをテストする
- [ ] 0件マッチ・列名不存在・非数値列集計はMissingになる
- [ ] 回答は値のみ、必要最小限の単位のみになる
- [ ] 目標: 15問以上

### 🟡 P1 — 中頻度 or 既存拡張

#### 4. schedule 拡張 (現状: フェーズ名のみ → 担当者/ステータス/成果物/日付範囲)

- [ ] コード上は `_schedule_questions` が担当者・ステータス・成果物を対応済み → per-type上限を上げて生成確認
- [ ] 日付範囲クエリの追加 (「2026年1月以降に開始されたタスクは？」)
- [ ] 複合担当者 (`A / B`) で片方の名前で拾えるかテスト
- [ ] 該当0件の条件ではMissingに倒す
- [ ] 目標: 各サブタイプ5問 = 計25問

#### 5. office_style_combo (test Q11, Q71: bold+underline+italic同時)

- [ ] 同一ファイル内に太字/下線/イタリックが複数ある場合のcombo問題
- [ ] docx黄色ハイライトとpptx背景色を区別する
- [ ] ページ番号・スライド番号指定で候補を絞る
- [ ] 句読点だけ、空白だけ、短すぎるrunを除外する
- [ ] 目標: 10問追加

#### 6. contract_rule (valid+test: ~11問)

- [ ] 契約書テキストからの条項抽出artifact作成が先決
- [ ] 条件付き計算問題 (「〜の場合の違約金は？」)
- [ ] 期限・日数計算問題
- [ ] 目標: 10問以上 (artifact作成後)

### 🟢 P2 — 低頻度 or 実装コスト高

#### 7. cross_project (valid+test: ~8問)

- [ ] `document_registry.jsonl` (417件) から複数案件にまたがる集計問題
- [ ] 「全案件でtrain.xlsxを持つプロジェクト数は？」
- [ ] 目標: 5問以上

#### 8. negative_case

- [ ] 別案件の似たファイルに引っ張られない
- [ ] 曖昧すぎる質問では答えずMissingになる
- [ ] 該当artifactがない場合に通常検索へ誤って流れてIncorrect化しない
- [ ] 目標: 5問以上

#### 9. document_structure (ページ番号・章番号)

- [ ] ページ番号指定の質問 (「3ページ目の表タイトルは？」)
- [ ] 章・節番号指定の質問
- [ ] 目標: 3問以上

## 追加したい高度ケース (P1/P2共通)

### 曖昧ルーティング

- [ ] 「ハイライト」が Excel / docx / pptx のどれかを正しく振り分ける
- [ ] ファイル名なしで、案件略称と資料種別だけから正しいartifactに到達する
- [ ] 正式名称・略称・英字略称を混ぜても同じ案件に解決する

### 列挙完全性

- [ ] タスクIDが5件以上ある条件で全件列挙できる
- [ ] 部分列挙をPerfect扱いしない検査を追加する
- [ ] 抽出件数が多すぎる場合は全件列挙できる範囲に制限する

### Pivot / Excel状態

- [ ] merged cell由来の空欄をforward-fillしてPivot行を読む
- [ ] 複数数値列の中から質問中の列名で対象列を選ぶ
- [ ] autoFilter条件が複数列あるケースを生成する
- [ ] ハイライトセルが複数ある場合にセル番地・シート名で曖昧性を解消する

## 実行メモ

```bash
# 全タイプ生成 (タイプあたり最大20問)
.venv/bin/python scripts/build_generated_eval.py --per-type 20

# タイプあたり上限を上げて生成 (schedule拡張確認用)
.venv/bin/python scripts/build_generated_eval.py --per-type 40

# 生成結果の評価
.venv/bin/python scripts/run_generated_eval.py

# メタデータ確認 (タイプ別件数)
cat data/generated_eval/metadata.jsonl | python -c "
import sys, json, collections
types = collections.Counter()
for line in sys.stdin:
    types[json.loads(line)['type']] += 1
for t, c in types.most_common():
    print(f'  {t}: {c}')
"
```

結果は `experiments/generated_eval/` に保存する。本物validの実験結果とは比較軸を分ける。
