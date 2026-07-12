# 2026-07-11 全案件横断（cross_project）ブロック実装計画

> 位置づけ: `plan_0703.md` Phase 3 の残りタスク（`docs/plan/2026-07-06-contract-rule-block.md` の続き）。
> 本書は**実データ調査＋実装計画のみ**（コード未着手）。着手時は本書のタスク単位でTDD実装し、
> 1タスク=1コミット=1レビュー（step-review）で進める。

## 0. 対象設問（`docs/question_labels.csv`, `primary_type == cross_project`）

valid 1問・test 9問（計10問）。

| split | idx | 質問要約 | 状態（実測） |
|---|---|---|---|
| valid | 3 | 全案件の消費税総額 | **valid唯一のIncorrect**（confidence 0.55で誤答、plan_0703 §1.1） |
| test | 13 | 最多案件関与者の内線番号 | 未実装・**infra欠落でブロック**（§1.4） |
| test | 26 | 契約期間重複40日超の案件列挙 | **実装済み**（`contract_overlap`、07/09診断runで発火確認） |
| test | 31 | 固定金額契約の1行あたり単価最高 | **実装済み**（`contract_per_row`、同上） |
| test | 40 | 支払月ごと精算総額 上位3 | 未実装・**新規抽出で高確度に実現可能**（§1.3） |
| test | 46 | 着手金最高案件のES内線番号 | 未実装・**infra欠落でブロック**（§1.4、Q13と同一制約） |
| test | 55 | 事後精算案件の見積/実績工数乖離最大 | **実装済み**（`contract_hours_gap`、同上） |
| test | 67 | APR-M2該当・完了・提案時とFR時の金額差 | 未実装・中確度で実現可能（§1.5） |
| test | 86 | PP/契約書/PLAN/FR横断のDA側人数 | 未実装・**高工数、別ブロック推奨**（§1.6） |
| test | 87 | APR-M1該当・完了・サンプル数10000行以上 | ルーティング済みだが**「完了」判定にバグを発見**（§1.2、実データはMissing誤り） |

→ 9問中3問はcontract_rule実装（`afe0d2d`〜）で既に解決済み。本書は残り6問（valid 1 + test 5: Q3/13/40/46/67/86）と、既存実装の隠れたバグ（Q87）を扱う。

## 1. 実データ調査で分かったこと

### 1.1 valid Q3「全案件で支払った税込金額をもとに、消費税額の総額を計算」

`src/utils/question_classifier.py` の `CONTRACT_RULE_KEYWORDS`（`契約金額`,`APR-M`,`ACTH`等）にも
`MULTI_HOP_KEYWORDS`成立後の`contract_rule`タグにも該当語がヒットせず、**`ContractCalcAnswerer`に到達すらしていない**
（実際に`answer()`を直接呼ぶと`contract_no_project`でMissing相当だが、パイプラインでは`contract_rule`タグが立たないため
通常の生成LLMパスに落ち、confidence 0.55で誤答している）。タグ・ルーティングの欠落が根本原因。

「支払った税込金額」= 各案件の確定精算額（固定価格は`estimated_amount_incl_tax`そのもの、事後精算は
実績工数からの計算額）。`artifacts/contracts.jsonl`の全10件で検証:

| 案件 | 方式 | 支払額（税込） | 根拠 |
|---|---|---:|---|
| 京橋(KSS) | 固定 | 5,775,000円 | `estimated_amount_incl_tax` |
| かえで | T&M | 3,850,000円 | `final_amount_incl_tax`（実績=見込） |
| みなみ野 | 固定 | 3,960,000円 | `estimated_amount_incl_tax` |
| ひがし丘 | T&M | 4,675,000円 | `final_amount_incl_tax`（実績=見込） |
| 東都 | T&M | 4,675,000円 | `billed_amount_incl_tax()`で計算可（rate/rounding/actual_hours 全て揃っている） |
| 青嶺 | T&M | 5,073,750円 | 同上（実績184.5h > 見込170h、増額側） |
| **青潮** | T&M | **不明** | `actual_hours`がnull。最終報告が**画像のみのPDF**（後述§1.7）で機械抽出不能 |
| 青葉バイオ | T&M | 3,443,000円 | `final_amount_incl_tax`（実績減） |
| 白峰 | 固定 | 7,480,000円 | `estimated_amount_incl_tax` |
| 青葉与信 | 固定 | 4,620,000円 | `estimated_amount_incl_tax` |

9/10件は決定的に計算可能（合計43,551,750円、税額3,959,250円）。**青潮1件がOCR/VLM未実装のため解決不能**。
`strategy.md`/`cross_project_rules_strategy.md`の「1案件でも必要項目が欠ける場合Missing優先」原則に従い、
**全10件が揃わない限りMissingにフォールバックする設計**とする。これは現在のIncorrect（confidence 0.55の誤答）を
決定的にMissingへ変える、安全側の確実な改善（正答化は狙わない）。

### 1.2 test Q87 / 「完了案件」判定のバグ発見（`contract_calc.py` 既存実装）

既存の`_answer_apr_m1_completed_row_threshold`（Q87用、07/09実装済み）を実データで実行すると
**`contract_apr_m1_no_match`でMissing**になる。原因を追うと、「完了」判定に流用している
`final_amount_incl_tax is not None`は**固定価格契約の最終報告書のフレーズパターンと構造的に不一致**:

- 抽出正規表現: `最終請求金額（税込）[：:\s|]*([0-9,]+)円` / `税込金額[：:\s|]*([0-9,]+)円`
- 実データ（青葉与信・固定価格・APR-M1該当・train.csv 17,500行≥10000）の最終報告pptx文言:
  `契約金額：¥4,200,000（税抜）/ ¥4,620,000（税込）` ← どちらの正規表現にも一致しない

固定価格契約は元々「事後精算を行わない」ため最終報告で金額を再掲しない/しても言い回しが違う。
結果として**固定価格契約は`final_amount_incl_tax`が常にnullになり「未完了」と誤判定される**。
実際には全10案件とも`06.報告書/*.pptx`or`*.pdf`（`old`除く）が存在し、報告書自体は提出済み
（＝完了案件と判断すべき）。**この誤判定は青葉与信だけでなく、`final_amount_incl_tax`を「完了」の
代理指標に使う全ての横断集計（Q67/Q86でも流用予定だった）に波及するバグ**。

修正方針: 「完了」は`final_amount_incl_tax`の非null性ではなく、**`06.報告書/`配下に`old`を除く
最終報告ファイルが存在するか**（`build_contract_registry.py`の`extract_report_values`が既に
`report_dirs`を走査しているのでファイル存在フラグ`has_final_report: bool`を追加するだけで済む）で判定する。

### 1.3 test Q40「支払月ごとの精算総額 上位3」

契約書docxの支払条件テーブル（`6.2 支払条件`付近）を10件全て確認。**列見出しの語順・列名は
案件ごとに揺れる**（`支払回/名目/比率/...`、`支払回/支払割合/...`、`支払回/マイルストーン/比率/...`等、
3パターン確認）が、**ヘッダー名ベースで`税込`列・`支払期日`列を探索すれば10件全て機械抽出できる**
（欠損・抽出失敗0件、実地検証済み）。

実データで月次集計を実行した結果（上位3）:

| 支払月 | 合計（税込） |
|---|---:|
| 2025-09 | 9,350,000円 |
| 2025-08 | 8,415,000円 |
| 2025-10 | 7,562,500円 |

固定価格は1〜2回払い（着手金/検収金）、T&M最終一括精算は1回払いが基本パターン。
**「2026年7月1日時点で存在する案件」フィルタの意味は要注意**: 全10案件の契約期間はいずれも
2025年内に終了しており、`project_registry`に完了/解約ステータスの区別がないため、現状データでは
このフィルタは実質「全10案件」に一致する（フィルタが空振りする可能性がある = 曖昧さとして§4に記載）。

### 1.4 test Q13 / Q46「ESの内線番号」— インフラ欠落でブロック

`社内管理/座席表.pptx`を実データで開くと、**スライドの構成要素はPICTURE 1枚＋空のAUTO_SHAPE 2枚のみ**
（`shape.text_frame.text`が両方とも空文字列）。つまり座席表は**画像埋め込みのみでテキスト層が存在しない**。
内線番号・座席位置は現在のOffice/PDFパーサー（テキスト抽出専用）では一切取得できず、**OCR/VLM実装が
前提条件**（`plan_0703.md` Phase 4 の image_graph投資と同種の課題）。

`people_assignments`registryを仮に構築しても、Q13/Q46は最終的にこの内線番号マッピングがなければ
回答文を完成できないため、**現時点ではpeople_registryへの投資は両問いずれの正答化にも直結しない**。
本ブロックでは着手せず、Missing運用のまま Phase 4（VLM）待ちとする。

### 1.5 test Q67「APR-M2該当・完了・提案時金額≠FR時金額」

`00.提案/`配下のファイル名は`提案書*.pptx`（一部`.pdf`、draft/v1/v2/final等の版揺れあり、
`契約書`と同型の版タグ問題）。1件（京橋/KSS）で実地確認したところ、提案書pptx内に
`契約金額（税抜）`/`契約金額（税込）`/`費用: ¥5,775,000（税込・固定価格）`のような金額記載が
存在し、正規表現抽出は可能と分かった。ただし**10件全件の文言パターン一致率は未検証**
（`build_contract_registry.py`の契約書抽出と同じく「10件中に第3のパターンが出る」リスクがある）。
「完了」判定は§1.2の修正後`has_final_report`を流用する。「FR時の金額」は既存`final_amount_incl_tax`
（今回T&Mのみ非null、固定は§1.2のバグ次第）を使うため、固定価格案件はFR時金額が取れず
比較不能→Missing側に倒れる（安全）。

### 1.6 test Q86「PP/契約書/PLAN/FR横断のDA側人数」— 高工数、別ブロック推奨

`cross_project_rules_strategy.md`の`people_assignments`registry相当が必要。ソース別の状況:

- **PLAN（02.計画）**: `artifacts/schedule_tasks.jsonl`に`担当者`列が既に存在（473行、全10案件分パース済み）。追加抽出不要。
- **PP（00.提案）**: 実施体制のセクションはpptx内にテキストとして存在する見込みだが、役割付き氏名の
  構造化抽出は未実装・未検証（表形式かテキストか案件ごとに要確認）。
- **契約書（01.契約）**: 甲乙の担当者名は契約書docxの当事者条項にあるはずだが未検証。
- **FR（06.報告書）**: 実施体制の再掲有無を10件通して未確認。

4種類×10案件=最大40資料の役割付き氏名抽出＋DA側/顧客側の判別＋表記ゆれ名寄せが必要で、
`contract_rule`ブロック（10件のみ・数値中心）より対象が広く曖昧性も高い。**本ブロックのスコープ外**とし、
`docs/plan/2026-07-06-contract-rule-block.md`が既にQ86を「別ブロック候補」としていた判断を踏襲する。

### 1.7 副次発見: PDF画像化ファイルのテキスト抽出0件（一般的なパーサー制約）

`06.報告書/*.pdf`のうち、みなみ野・青潮の2件は`pypdf`でテキストがほぼ0文字しか取れない
（全ページがPICTUREのみでテキストレイヤーなし。ひがし丘のPDFは同フォルダ構成でも7,902文字取得できており、
**ファイル単位でテキスト層の有無が異なる**＝スキャン/画像export起因）。§1.4の座席表と同じ制約分類で、
Phase 4のVLM投資が解決すれば芋づる式にQ3の青潮ブロッカーも解消しうる。

## 2. 設計方針

### 2.1 ルーティング拡張

`src/utils/question_classifier.py`に構造キーワードベースのタグを追加する（既存`CONTRACT_RULE_KEYWORDS`と
同型、特定質問文へのべた書きではなく汎用パターン）:

```python
CROSS_PROJECT_KEYWORDS = (
    "消費税額の総額", "支払月", "精算総額", "提案時金額", "FR時",
)
```

`pipeline._process_structured`は既存の`"contract_rule" in tags`分岐に`"cross_project" in tags`を
追加する形で`ContractCalcAnswerer.answer()`へ委譲する（新規クラスを作らず既存クラスにメソッド追加、
`contracts.jsonl`アクセサ・alias解決・ゲート挙動を再利用）。

### 2.2 `contracts.jsonl`スキーマ拡張（`build_contract_registry.py`）

- `has_final_report: bool`（§1.2のバグ修正。`report_dirs`走査時に`old`を除くファイルが1件以上あれば`true`）
- `payment_schedule: list[{month: str, amount_incl_tax: int, due_date: str}]`（§1.3、支払テーブルの
  ヘッダー名ベース抽出。列名バリエーションは`税込`を含む列・`支払期日`/`支払期限`を含む列を都度探索）
- `proposal_amount_incl_tax: int | None`（§1.5、`00.提案/`の金額抽出。既存`契約書*.docx`探索と同型の
  glob＋バージョンタグ選別ロジックを流用、抽出失敗時はnullのままMissineフォールバック）

いずれも既存の「実データから機械抽出、案件名分岐なし」の方針を継続（`build_version_diff_poc.py`/
`build_contract_registry.py`と同型）。

### 2.3 消費税総額の計算関数（Q3）

```python
def paid_amount_incl_tax(contract: dict) -> int | None:
    if contract["contract_type"] == "fixed":
        return contract["estimated_amount_incl_tax"]
    if contract.get("final_amount_incl_tax") is not None:
        return contract["final_amount_incl_tax"]
    if contract.get("actual_hours") is not None:
        return billed_amount_incl_tax(contract, float(contract["actual_hours"]))  # 既存関数を再利用
    return None
```

全件`paid_amount_incl_tax()`が非Noneであることを要求し、1件でもNoneならMissine（§1.1の設計）。
税額は`sum(paid) - sum(paid) / (1 + tax_rate)`（案件ごとに税率が異なる場合は案件単位で計算してから合算、
現状は全件`tax_rate=0.1`で統一されているが決め打ちしない）。

## 3. タスク分割（TDD・1タスク1コミット想定）

| # | タスク | 内容 | 該当設問 | 優先度 |
|---|---|---|---|---|
| 1 | `has_final_report`フィールド追加＋Q87完了判定バグ修正 | `build_contract_registry.py`にファイル存在フラグ追加、`_answer_apr_m1_completed_row_threshold`の完了判定を差し替え | Q87 | **最高**（既存実装の実データ検証済みバグ、実装済み機能の是正） |
| 2 | Q3ルーティング＋消費税総額計算 | `question_classifier`にタグ追加、`ContractCalcAnswerer`に`paid_amount_incl_tax`＋`_answer_tax_total`実装、全件非Null要求のMissingゲート | valid Q3 | **最高**（validの唯一のIncorrectを解消） |
| 3 | `payment_schedule`抽出＋Q40月次集計 | ヘッダー名ベースのテーブル抽出関数、月次sum・top3整形 | Q40 | 高（実データでの抽出成功率100%を確認済み） |
| 4 | `proposal_amount_incl_tax`抽出＋Q67比較 | `00.提案/`金額抽出（版タグ選別込み）、APR-M2フィルタ×金額不一致リスト化（タスク1の`has_final_report`に依存） | Q67 | 中（10件全件のパターン一致率が未検証） |
| 5 | 実データ検証（valid該当問＋test診断run） | `--no-judge`診断runで全経路発火確認、valid該当問（Q3のみ）はofficial較正 | 全体 | 高（本ブロック完了条件） |

Q13・Q46は座席表OCR/VLM前提のため本ブロックでは着手しない（§1.4、Phase 4待ち）。
Q86はpeople_registry構築が必要な別スコープのため本ブロックでは着手しない（§1.6、別ブロック提案）。

## 4. リスク・不確実性

- **規約適合性**: 新規抽出はすべて既存の`build_contract_registry.py`と同型（ヘッダー名・キーワード
  ベースの機械抽出、案件名・ファイル名への直接分岐なし）。`CROSS_PROJECT_KEYWORDS`もcontract_rule同様、
  質問の構造パターン（「支払月」＋「精算総額」等）へのマッチであり、特定の質問文そのものへの分岐ではない
- **Q3のカバレッジ上限**: 青潮の最終報告が画像PDFのため、Phase 4のVLM投資がない限り9/10案件までしか
  解決できない。現設計は「全件揃わなければMissing」なので**誤答リスクはゼロだが正答化もしない**
  （Incorrect→Missineの安全化のみが確定効果）
- **Q40の「存在する案件」フィルタの解釈**: `project_registry`に完了/解約ステータスがなく、現在の
  10案件データでは事実上フィルタが空振りする。将来的にステータスフィールドを追加するかは本タスクの
  スコープ外とし、現状は「全10案件を対象にする」実装で進める
- **Q67の10件パターン一致率**: 京橋（KSS）1件のみ実地確認済み。残り9件で提案書の金額記載パターンが
  大きく異なる場合、抽出失敗→Missingに倒れるため誤答リスクはないが、正答化率の見積もりが下がる
- **Q87修正の副作用範囲**: `has_final_report`を「完了」の代理指標に変えることで、既存のcontract_rule
  ブロック（Q38 APR-M3集計等）が同じ`final_amount_incl_tax`ベースの完了判定を流用していないか要確認
  （現状Q38は`_answer_apr_list`内で完了判定を使っていないため影響なしと推測、実装時に再確認）

## 5. 期待値

- **valid Q3（1問）**: Incorrect→Missingへの決定的な是正。CRAG型採点でConfident-wrong(-1)→Missing(0)は
  valid mean **+1/30（約+0.033）**。正答化は狙わないため上振れなし
- **test Q87修正（1問）**: 既存実装のバグ修正で、正しくは非Missing（青葉与信/APR-M1該当・列挙1件）になる
  はずの設問。高確度（APR判定は決定的、`has_final_report`はファイル存在確認のみ）→成功率7〜8割
- **test Q40（1問）**: 実データで抽出0件欠損を確認済み、高確度（`contract_overlap`等の既存実績と同水準）
  →成功率7〜8割
- **test Q67（1問）**: 提案書抽出パターンが1件しか検証できていないため中確度→成功率4〜5割
- **test Q13/Q46/Q86（3問）**: 本ブロックでは対応せず、Missing運用を維持（誤答化はしない）
- 合計: 該当4問（valid 1 + test 3）×成功率階層別 → **valid +0.033（確定）、test +0.02程度（期待値）**。
  `plan_0703`のPhase3全体見積もり（+0.12〜0.15）のうち、contract_rule実装済み分（Q6/23/26/31/37/55/76/87想定）
  を除いた残余として妥当な水準

## 6. 次アクション

本書のタスク1（`has_final_report`修正）から着手する。既存の`contract_calc.py`テストスイートに
回帰がないか確認しながら進め、タスク2（valid Q3）を最優先で完了させた時点で一度`--runs 3`のvalid診断runを
実施し、Incorrectが解消されたことを確認してから残タスクに進む。
