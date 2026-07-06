# 2026-07-06 契約ルール（contract_rule）ブロック実装計画

> 位置づけ: `plan_0703.md` Phase 3の残りタスク。本書は**実データ調査＋実装計画**のみ（コード未着手）。
> 着手時は本書のタスク単位でTDD実装し、1タスク=1コミット=1レビュー（step-review）で進める。

## 1. 実データ調査で分かったこと

### 1.1 契約書の構造（`01.契約/契約書*.docx`、全10案件）

- 全案件に条文番号付きの構造化契約書docxが存在する（1.当事者〜14.特約事項、案件により項番構成は微妙に異なる）
- **料金モデルは2種類が混在**: `time_and_materials`（事後精算・実績工数連動）と`固定価格`（契約時に総額固定）。
  固定価格契約にはRATE/ESTH/ACTHの概念自体が存在しない（例: 青葉与信マネジメント = 固定価格、税込4,620,000円で確定）
- T&M契約の「6. 報酬および支払条件」に以下が高い再現性で出現（項番の有無・文言は案件ごとに揺れる）:
  - 料金モデル宣言（`time_and_materials`という語がほぼそのまま出る）
  - 時間単価（RATE）: 「時間単価は25,000円（消費税別）」等
  - 想定総工数（ESTH）: 「想定総工数は170時間」等
  - 見込金額（税抜/消費税/税込の3点セット）
  - **工数端数処理ルール（丸め単位・丸め方向）**: これが案件ごとに文言も規則も異なる。
    実データで確認した2パターン:
    - ひがし丘: 「作業時間の計上単位は30分とし、30分未満の端数は30分単位に切り上げて計上する」
      （= 30分単位で常に切り上げ。155時間10分 → 155.5時間）
    - 東都: 「工数計上の丸め単位は30分とし...30分未満を0.5時間、30分超60分未満を1.0時間として
      0.5時間単位で計上する」（= 表現が異なり、解釈にはより注意深い読解が必要）
    → **丸め規則は自由文からの解釈が必須で、単純な正規表現の使い回しでは全案件をカバーできない**。
      案件数が10件と少ないため、契約ごとに機械抽出→人間/LLMレビューで規則タイプ（enum化）を
      確定する半PoC的アプローチが現実的（`version_diff_poc.jsonl`と同じ思想）
- **draft版と最終版の差分は要注意**: 青葉バイオメディカル機器の`契約書.docx`と`契約書_draft.docx`は
  段落テキストが完全一致（0差分）。数値もテキストも同一で、実質的な違いが無い（version_diff Q9で見た
  「実質的な差分はテーブル内」パターンとは異なり、今回確認した1組は本当に無差分だった）。
  ただし全案件でdraftの有無・差分の有無を確認したわけではないため、実装時に`document_registry`で
  draft/finalの選別ロジック（既存のversion_tag機構を流用可）を明示する

### 1.2 決裁基準（APR）: 完全に機械判定可能

`社内管理/データアステル社内管理_決裁基準.md`は曖昧さのない決定的ルール:

1. 契約金額（税込）から基本レベルを判定（4段階の金額帯テーブル）
2. 医療案件なら1段階引き上げ
3. `time_and_materials`契約なら「部長承認以上」を保証（医療補正後の結果と比較して高い方を採用）

`APR-M1/M2/M3`のラベルは`社内用語集.docx`由来で**既に`artifacts/term_registry.json`に格納済み**
（`APR-M1=課長承認`, `APR-M2=部長承認`, `APR-M3=本部長承認`、主任承認はAPR-M系ラベルの対象外）。
→ **LLM不要。純粋な決定関数として実装できる、本ブロック最高信頼度の対象**

### 1.3 対象設問（`docs/question_labels.csv`、test）

`primary_type=contract_rule`（9問。plan_0703記載の「10問」とは軽微な差があるが実測優先）:

| Q | 質問 | 計算/判定の型 |
|---|---|---|
| 6 | ひがし丘: 見込税込金額と最終請求金額の差額 | 単一契約の税込差額（要ACTH — 文書内 or 質問内） |
| 23 | ひがし丘: ACTH=155h10mなら見込税込と比べて何円減額 | RATE×丸め済みACTH+税 vs 見込税込 |
| 37 | AOBM: 見込税込-確定税込をESTH-ACTHの差で割った時間単価 | 差額÷工数差の計算 |
| 38 | APR-M3必要案件を主略称ですべて挙げ契約金額合計 | APR判定関数＋横断集計 |
| 52 | みなみ野: 「別契約」明記箇所の抽出 | 純粋テキスト抽出（list_extraction寄り） |
| 76 | AOMINE: 単価+2000円・ACTH-11.2hなら請求額はいくら変動 | 差分シナリオ計算（what-if） |
| 78 | ひがし丘: ACTH200時間超の精算規定内容 | 純粋テキスト抽出（契約書の該当条文を引用） |
| 79 | かえで計画: DA担当者の1タスクあたり想定工数最大の人 | schedule_tasks集計（既存registryの流用） |
| 98 | TM案件: RATE変更日 | 契約書内のRATE変更条項テキスト抽出 |

secondary_typesで`contract_rule`かつ`cross_project`が主の設問（7問、`artifacts/contracts.jsonl`が
できれば横断計算基盤としてそのまま使える）:

| Q | 質問 | 必要な横断集計 |
|---|---|---|
| 26 | 指定期間に契約期間が重なり40日超の案件を列挙 | `contracts.jsonl`の契約開始日・期間 |
| 31 | 固定金額契約中、分析データ1行あたり契約金額最高の案件 | `contracts.jsonl`(固定金額のみ)×train.csv行数 |
| 46 | 着手金最高の案件のESの内線番号 | `contracts.jsonl`(着手金)×座席表registry |
| 55 | 事後精算案件中、見積工数と実績工数の乖離最大の案件 | `contracts.jsonl`(ESTH)×最終報告書のACTH記載 |
| 67 | APR-M2該当かつ提案時金額とFR時金額が異なる完了案件 | APR判定関数×提案書/FR金額比較 |
| 86 | 各案件のPP/契約書/PLAN/FRでDA側実施体制の人数 | 既存people抽出（未着手）の拡張 |
| 87 | APR-M1該当かつサンプル数10000行以上の完了案件 | APR判定関数×train.csv行数 |

`office_style`が主でcontract_ruleが副の設問（Q3, Q81=契約書の太字抽出）は**既存のoffice_style
パスで対応可能な射程**（新規registry不要、優先度低）。

## 2. 設計方針

### 2.1 データ資産: `artifacts/contracts.jsonl`

`scripts/build_contract_registry.py`（新規）を`build_version_diff_poc.py`と同じ思想で作る:
案件ごとに1レコード、機械抽出できる項目は正規表現/構造化抽出、丸め規則のような自由文条項は
契約書全文を`raw_billing_clause`として保持しつつ、**丸め規則タイプを`rounding_rule`という
enumフィールドに人手/LLM補助で分類**して埋める（10件程度なので実行可能）。

フィールド案:

```json
{
  "project_name": "...",
  "contract_type": "time_and_materials | fixed",
  "rate_yen_per_hour": 25000,
  "esth_hours": 170.0,
  "estimated_amount_excl_tax": 4250000,
  "estimated_amount_incl_tax": 4675000,
  "tax_rate": 0.10,
  "rounding_unit_minutes": 30,
  "rounding_rule": "ceiling_to_unit | half_unit_bucket | none | unknown",
  "start_date": "2025-07-08",
  "contract_period_days": 35,
  "advance_payment_amount": null,
  "raw_billing_clause": "（該当条文の生テキスト。ゲート判断・監査ログ用）",
  "source_path": "..."
}
```

- 既存パターン踏襲: `artifact_store.py`に`contracts_for(project_name)`アクセサを追加
- 固定価格契約は`rate_yen_per_hour`等をnullのまま（型で自然に分岐できる）

### 2.2 計算パス: `src/generator/contract_calc.py`（新規、`spreadsheet_calc.py`と同構成）

- 質問文から「ACTHがX時間Y分だった場合」のようなwhat-ifシナリオ値を抽出（既存の`question_classifier`
  的な正規表現アプローチ。数値抽出のみなのでLLM不要）
- `contracts.jsonl`のレコード＋質問内シナリオ値を使い、Pythonで決定的に計算
  （RATE×丸め後ACTH×(1+税率) 等）。丸め規則は`rounding_rule`で分岐
- 計算根拠（丸め後の値・適用した条文）を`gate_reason`/監査ログに残す（既存`Answer.gate_reason`の
  慣習を継続）
- 該当契約が見つからない・`rounding_rule=unknown`・シナリオ値の抽出に失敗した場合は**Missingに
  フォールバック**（strategy.md §1.2の数値問題は「惜しい数字はむしろ危険」の原則に従う）

### 2.3 APR判定: `src/generator/approval_rule.py`（新規、純粋関数）

`データアステル社内管理_決裁基準.md`の§2〜4のロジックをそのままPython化する決定関数:

```python
def determine_apr_level(amount_incl_tax: int, is_medical: bool, is_time_and_materials: bool) -> str:
    ...
```

- 入力は`contracts.jsonl`(金額・契約方式)＋`project_registry`(業界カテゴリ=医療案件判定)
- `term_registry`の`APR-M1/M2/M3`マッピングは既存資産のまま利用（新規抽出不要）
- Q38/Q67/Q87のような横断集計はこの関数を全案件にmapしてfilterするだけ

### 2.4 横断集計（cross_project由来の7問）

`contracts.jsonl`が揃えば、Q26（契約期間重複）・Q31（1行あたり金額）・Q46（着手金最高）・
Q55（工数乖離最大）は既存の`project_registry`・train.csv行数・（Q46のみ）座席表registryとの
単純な結合・集計で解ける。Q86（人数カウント）は本ブロックの主題（金額計算）とは性質が異なる
（people_registry拡張が必要）ため、優先度を下げて別ブロック（人員横断）に切り出す判断もありうる。

## 3. タスク分割（TDD・1タスク1コミット想定）

| # | タスク | 内容 | 該当設問 |
|---|---|---|---|
| 1 | `build_contract_registry.py`実装（機械抽出項目のみ） | 契約方式・RATE・ESTH・見込金額・税率・開始日・期間をdocxから正規表現抽出、`contracts.jsonl`出力 | 基盤 |
| 2 | 丸め規則の分類（半手動） | 10件の`raw_billing_clause`を読み`rounding_rule`enumを埋める。ロジックが2パターン以上あれば`rounding_rule`ごとの適用関数を実装 | 6, 23, 76 |
| 3 | `contract_calc.py`: 単一契約の請求額計算 | RATE×ACTH計算・丸め適用・税込変換 | 6, 23, 76 |
| 4 | `approval_rule.py`: APR判定関数 | 決裁基準ロジックのPython化、term_registry連携 | 38, 67, 87 |
| 5 | パイプライン接続（`contract_rule`タグルーティング） | `question_classifier`に`contract_rule`用what-if数値抽出、`pipeline._process_structured`に新パス追加 | 全体 |
| 6 | 横断集計（cross_project側4問: 26, 31, 46, 55） | `contracts.jsonl`×project_registry×train.csv行数の結合ロジック | 26, 31, 46, 55 |
| 7 | 実データ検証（valid該当問があれば）＋test診断run | `--no-judge`診断runでgate通過確認、該当あればN=3+official較正 | 全体 |

Q78・Q98・Q52は純粋テキスト抽出（該当条文の引用）で、構造化計算ではなく**既存の検索+生成
パスの引用精度向上**で対応する方が自然（新規registryへの投資対効果が低い）。優先度は上記タスクの後。
Q86は前述の通り別ブロック候補として保留。

## 4. リスク・不確実性

- **規約適合性**: `build_contract_registry.py`はdocx本文を正規表現で機械抽出するのみで、
  案件名・ファイル名によるハードコード分岐は発生しない（version_diff_poc/spreadsheet_calcと同型）。
  丸め規則の分類だけは人手/LLM補助が入るが、これは「実データから機械的に導出したレジストリ」
  （vault.mdの`artifacts/`定義に合致）であり、質問・正解への直接ハードコードではない
- **丸め規則の一般化限界**: 10件中に3パターン目以上の丸め規則が出てくる場合、`rounding_rule`
  enumの拡張が必要になる。未知パターンは`unknown`としてMissingに落とす設計なので安全側には倒れる
- **見込金額 vs 確定金額の意味差**: 一部設問（Q6等）は「提案時の見込金額」と「最終請求金額」を
  比較する。「見込金額」は契約書に記載があるが「最終請求金額」は最終報告書側にある可能性があり、
  `contracts.jsonl`だけでは完結しない設問がある（要: 最終報告書からのACTH/確定金額抽出も検討）
- **Q79は契約ではなくスケジュール構造化データ**: 実質的に`schedule_tasks`registry（既存資産）の
  集計問題であり、本ブロックの契約計算パスとは独立。既存資産の再利用で済むはずなので優先度は高いが
  実装は本ブロックと分離できる

## 5. 期待値

- 主対象9問（primary_type=contract_rule）× 高信頼度実装（APR判定は決定的、billing計算は
  丸め規則さえ拾えれば決定的）→ 成功率5〜6割見込み（office_style/spreadsheet_calc実績と同水準）
  → **+0.045〜0.054相当**
- cross_project経由7問のうち`contracts.jsonl`の直接恩恵を受けるのは4問（26/31/46/55）
  → 成功率4割見込みで**+0.016相当**
- 合計 該当16問 × 成功率階層別 → **+0.06〜0.07程度**。plan_0703のPhase3全体見積もり
  （+0.12〜0.15、version_diff/cross_project合算）の一部として妥当な水準

## 6. 次アクション

本書のタスク1から着手する場合、TDD（`dev-process`スキル）に従い
`build_contract_registry.py`のテスト（合成docx or 実データの一部を使った決定的検証）から開始する。
着手前に、Q6/Q78のように「見込金額 vs 最終請求額」の対比が最終報告書側のデータも必要とする設問が
どの程度あるか、最終報告書（`06.報告書/`）側の記載パターンも軽く確認しておくと手戻りが減る。
