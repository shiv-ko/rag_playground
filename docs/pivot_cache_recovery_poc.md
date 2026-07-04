# compact pivot質問の回収可能性 診断レポート（valid Q21 / 株式会社青葉バイオメディカル機器）

> 2026-07-05、Sonnetサブエージェントによる診断（読み取り専用PoC）。レビュー済み:
> PoC結果JSON（かえで総合病院のpivot構造・Q21のargmax=GT一致）と、罠#1のNFD潜在バグ
> （`'03.データ' in p.parts`が実パスのNFD形とマッチしないこと）をレビュアーが独立に再現確認した。
> PoCスクリプトは `scripts/poc_pivot_recompute.py` として保存。

対象質問（valid Q21）:
> 青葉バイオメディカル機器のtrain.xlsxのPivotシートにおいて、平均月収が最も高い層の抽出条件を答えてください。

GT: `Attrition = No、Gender = Female、MaritalStatus = Single、EducationField = Human Resources`

結論を先に: **PoCはGTと完全一致。pivotTable定義＋pivotCache（definition+records）だけで、compact表示済みのPivotワークシートを一切読まずに argmax層を再導出できる。** 対象5プロジェクト・9個のpivotTableすべてで構造抽出は成功（0 failures）。ただし「行フィールドが実在しない（プレースホルダのみ）」という別パターンのpivotTableも1プロジェクトに2件存在し、これは今回のロジックでは「グループなし」と正しく判定されるが、別の質問形式（層ごとの比較ではない）に対応する必要がある。

---

## 1. 構造の確認（青葉バイオメディカル機器 train.xlsx）

### (a) rowFields構成
`xl/pivotTables/pivotTable1.xml`:
```xml
<rowFields count="4">
  <field x="2"/><field x="10"/><field x="16"/><field x="8"/>
</rowFields>
```
`x`はpivotFields（＝cacheFields）の0始まりインデックス。`xl/pivotCache/pivotCacheDefinition1.xml`のcacheFields順から解決すると:

| x | cacheField名 |
|--:|---|
| 2 | Attrition |
| 10 | Gender |
| 16 | MaritalStatus |
| 8 | EducationField |

→ rowFieldsの並びは **Attrition → Gender → MaritalStatus → EducationField** で、GTの4条件・順序と完全一致。

### (b) dataField（集計定義）
```xml
<dataFields count="1">
  <dataField name="平均 / MonthlyIncome" fld="17" subtotal="average" baseField="16" baseItem="2" numFmtId="176"/>
</dataFields>
```
`fld="17"` → cacheFields[17] = `MonthlyIncome`。`subtotal="average"` = 平均。`baseField/baseItem`は「基準に対する差分％」等の表示専用オプションで、単純平均には無関係（無視してよい）。

### (c) キャッシュから元データを復元できるか
`pivotCacheDefinition1.xml`のcacheFields（33個）は各フィールドについて:
- カテゴリ値（Attrition, Gender, MaritalStatus, EducationField, BusinessTravel, Department, JobRole, OverTime, Over18 等）は `<sharedItems count="N">` で値の辞書を持つ。ただしBusinessTravel/Department/JobRole/OverTimeは`count`属性なしの`<sharedItems/>`のみ＝レコード側は生値（indexなし）。
- 数値フィールド（Age, MonthlyIncome, DailyRate 等）は`containsNumber="1"`の範囲情報のみで辞書なし＝レコード側は生の`<n v="...">`。

`xl/pivotCache/pivotCacheRecords1.xml`は735件の`<r>`要素、各要素はcacheFieldsと同じ順で33個の子要素を持つ。子要素の種別で解釈が変わる:
- `<x v="i"/>` … そのフィールドのsharedItemsのi番目を参照（辞書引き）
- `<n v="...">` / `<s v="...">` / `<b v="...">` / `<m/>`（欠損） … 生の型付き値をそのまま使う

実際に先頭レコードで検証: `<s v="train_0000"/><n v="41"/><x v="0"/><s v="Non-Travel"/>...` の並びがcacheFields順（id, Age, Attrition, BusinessTravel, ...）と1:1対応し、`recordCount="735"`とpivotCacheRecords内`<r>`実数(735)も一致。
→ **キャッシュだけで元データ735行×33列を完全復元できる**（`train`シートのA1:AG736と同一のはずで、cacheSourceの`worksheetSource ref="A1:AG736" sheet="train"`もこれを裏付ける）。

---

## 2. PoC実行結果

スクリプト: `/private/tmp/.../scratchpad/poc_pivot_recompute.py`
実行結果: `/private/tmp/.../scratchpad/poc_pivot_results.json`（生ログ: `poc_run.log`）

処理内容:
1. zip内`xl/pivotTables/pivotTable*.xml`を列挙
2. 各pivotTableの`_rels`から`pivotCacheDefinition`を辿り、さらにそこから`pivotCacheRecords`を辿る（workbook.xmlのpivotCaches/cacheIdは経由しない・より直接的で頑健）
3. cacheFieldsのsharedItems辞書を構築
4. 735件のレコードをフルデコード（`<x>`は辞書引き、それ以外は型付き生値）
5. pivotTableのrowFields（`x="-2"`＝値軸プレースホルダは除外）でrecordsを再グルーピングし、dataFieldのsubtotal関数（average/sum/max/min等）で集計
6. 全グループのargmax/argminを算出（**Excelが書き出したrowItems/キャッシュ済み表示値は一切使わず、生レコードから再計算**）

### Q21の出力
```
row_fields=['Attrition', 'Gender', 'MaritalStatus', 'EducationField']
data_field=平均 / MonthlyIncome (subtotal=average), n_groups=66
argmax={'Attrition': 'No', 'Gender': 'Female', 'MaritalStatus': 'Single', 'EducationField': 'Human Resources'}
argmax_value=17328.0
argmin={'Attrition': 'Yes', 'Gender': 'Male', 'MaritalStatus': 'Single', 'EducationField': 'Other'}
argmin_value=2105.5
```

**GTと4条件・値すべて完全一致。** さらに独立したクロスチェックとして、`artifacts/train_xlsx_small_sheet_cells.jsonl`（既存スキャナが保存していたPivotワークシートの表示済みセル値、NFC正規化後にproject_nameで抽出）を見ると、compact表示のA19='Single', A20='Human Resources', B20='17328' という葉セルが実在し、再計算値17328.0と完全一致。（=Excel側の実表示値と、キャッシュからの再計算値の両方が同じ答えを出しており、手法の正しさを二重に確認できた。）

---

## 3. 一般化検証（全train.xlsx × 全pivotTable）

`find "data/raw/share/共有ドライブ" -iname "*.xlsx"` で列挙し、zip内に`xl/pivotTables/pivotTable*.xml`を持つものを抽出。全9 train.xlsxのうち5件・pivotTable計9個。

| project | pivotTable | rowFields | colFields | dataFields (subtotal) | records | 結果 |
|---|---|---|---|---|---:|---|
| 株式会社青葉バイオメディカル機器 | pivotTable1 | Attrition, Gender, MaritalStatus, EducationField | (なし) | 平均/MonthlyIncome(average) | 735 | OK, GT一致 (argmax=17328.0) |
| **医療法人社団 恒一会 かえで総合病院**（Q6対象・過去failures=1記録あり） | pivotTable1 | Gender, disease, Age | (なし) | T_Bil/D_Bil/ALP/ALT_GPT/AST_GOT/TP/Alb/AG_ratio 各average ×8 | 3500 | **OK、0エラーで再計算成功**（203グループ×8指標のargmax/argminを算出済み） |
| 医療法人社団 蒼泉会 ひがし丘総合病院 | pivotTable1 | sex, smoker, region, charges | (なし) | age/bmi (average) | 1600 | OK |
| 〃 | pivotTable2 | children, region | (なし) | bmi (sum) | 1600 | OK |
| 〃 | pivotTable3 | children, smoker | (なし) | age/bmi (sum) | 1600 | OK |
| 〃 | pivotTable4 | children | (なし) | age/bmi (sum) | 1600 | OK |
| 株式会社青潮モビリティサービス | pivotTable1 | weekday | (なし) | temp/atemp/hum/windspeed/cnt (average) | 8645 | OK |
| 〃 | pivotTable2 | hr | weekday | temp/hum/cnt (**max**) | 8645 | OK（colFieldsあり・subtotal=maxでも動作） |
| 白峰信用リスク評価株式会社 | pivotTable1 | **(実在フィールドなし＝`x=-2`のみ)** | (なし) | Attr11〜Attr20 (sum、subtotal属性省略＝デフォルトsum) | 7352 | **構造抽出はOK。ただし「層の比較」ではない別パターン** |
| 〃 | pivotTable2 | **(同上)** | (なし) | Attr1〜Attr10 (sum) | 7352 | 同上 |

- 失敗0件。恒一会 かえで総合病院のtrain.xlsxも問題なく読める（過去のfailures=1は別の処理系（openpyxlのpivot cache読み込み等）由来と推測され、本PoCのzip/XML直読み方式では再現しない）。
- 白峰の2テーブルは`rowFields`が`x="-2"`（値軸プレースホルダ）のみで実フィールドを持たない。これは「列ごとの合計を1行で並べた要約表」であり、「どの層が最大か」を問う compact pivot 質問の対象にはならない別パターン。本ロジックは`row_fields=[]`を正しく検出し「グループなし」と報告する（誤って何かを答えてしまうことはない）。

---

## 4. 罠・エッジケース一覧

1. **NFD/NFC正規化（実際に踏んだ）**: `data/raw/share/共有ドライブ/...`配下のパス構成要素はNFD正規化（例:「デ」がU+30C6+U+3099の分解形）。既存の`scripts/scan_train_xlsx_xml.py`の`target_workbooks()`は`"03.データ" in p.parts`という正規化なしの文字列比較を使っており、**このリテラルの符号化形式（NFC/NFD）次第で挙動が変わる**ことを実機で確認した（`__pycache__`が古い版のバイトコードを保持していたため現状は動いているが、現在のソースをその場でフレッシュコンパイルして実行すると`p.parts`とのNFC/NFD不一致で該当ファイルが1件もヒットしなくなることを確認 — pycacheを消す／CI等クリーン環境で再実行すると顕在化しうる潜在バグ）。本PoCではパス比較・project_name比較の両辺に必ず`unicodedata.normalize("NFC", ...)`を適用して回避した。**既存スキャナ側もリテラル比較を明示的にNFC正規化するよう直すことを推奨**（本タスクでは書き込み禁止のため未修正、報告のみ）。
2. **`<x v="N"/>` vs 生値の判定**: cacheFieldの`<sharedItems>`に`count`属性があるかどうかで、レコード側が`<x>`（辞書引き）になるか生の型付き値になるかが変わる。`count`なし・子要素なしの`<sharedItems/>`（例: BusinessTravel, Department, JobRole, OverTime）は生文字列。数値フィールドは`containsNumber`等はあるが`count`は無く生の`<n>`。これを取り違えると全フィールドがズレるので、cacheFieldごとに個別判定が必須（本PoCで実装・検証済み）。
3. **rowFields/colFieldsの`x="-2"`**: 「Σ値」プレースホルダであり実フィールドではない。除外しないとargmaxのグループ分けが壊れる（青潮モビリティサービスのpivotTable2、恒一会のcolFieldsで確認）。
4. **subtotal属性の省略時デフォルト**: OOXML仕様上、`<dataField>`に`subtotal`属性が無い場合は`sum`がデフォルト（白峰の2テーブルで確認）。
5. **rowFieldsが実質空（`[-2]`のみ）のpivotTable**: 「層ごとの比較」ではなく「列ごとの単純集計を1枚に並べただけ」のパターン。argmax/argminの意味を持たないので、この場合は別の質問タイプ（「〜列の合計は？」等）用のロジックに委譲する必要がある。
6. **rowItems/キャッシュ済み表示値を信用しない**: pivotTable XMLの`<rowItems>`はExcelが最後に保存した時点の表示ツリー（サブトータル行・`t="grand"`総計行を含む、間引き表示あり）で、これをそのままパースして「どれが最深階層＝実際の層か」を判定するのは複雑かつ壊れやすい。**本PoCは`rowItems`を一切使わず、pivotCacheの生レコードをrowFields名で再グルーピングして集計し直す**方式を取ったため、この複雑さを完全に回避できている。
7. **欠損値`<m/>`**: 集計（average/sum）からは除外すべき（Excelの挙動に合わせ、本PoCでも除外済み）。今回のデータでは実際に`<m/>`は未観測だったが、コードパスとしては対応済み。
8. **pageFields（レポートフィルタ）**: 今回の9テーブルには存在しなかった（`page_field_count=0`）が、存在する場合は特定ページ値でレコードを絞り込む必要がある未実装の拡張ポイント（検出のみ実装、フィルタ適用は未実装＝要注意ケースとして残す）。
9. **隠しアイテム（`item[@h="1"]`）**: 今回は0件だったが、存在すればそのカテゴリ値はpivot表示から除外される（ただし元データには残る）。設問が「表示されている層の中で」を意図している場合は生レコードのみの再集計では不十分になりうる。今回は該当なしのため実害なし。
10. **pivotTable→cache解決はworkbook.xmlのcacheId経由ではなく、`pivotTable*.xml.rels`→`pivotCacheDefinition`→`pivotCacheDefinition*.xml.rels`→`pivotCacheRecords`の直接rel chainを使うのが最も頑健**（cacheId周りのworkbook.xml解析を省略でき、実装もシンプルになる）。

---

## 5. 一般実装の設計案

### 方針
「未知のpivot質問でも同じ導出になる」一般則として実装する。特定案件名・フィールド値のハードコードはしない。pivotTableの構造（rowFields名・dataFieldのsubtotal種別）から機械的にargmax/argmin表を作るだけで、質問文の解釈（「最も高い」→argmax、「最も低い」→argmin、どのdataFieldを見るか）は別レイヤ（retriever側）に委ねる。

### 組み込み場所
1. **`src/parsers/pivot_cache.py`（新規）** — 本PoCのコアロジック（`load_typed_relationships` / `parse_cache_fields` / `parse_cache_records` / `parse_pivot_table` / `aggregate`）を移植。zipfile.ZipFileを受け取り、1ワークブック分の「pivotTable一覧 → 各テーブルのrow/col fields・dataFields・全グループ集計・argmax/argmin」を返す関数を提供。scan_train_xlsx_xml.py・将来のretriever・テストの3者から再利用できるよう、xlsxファイル固有の話（プロジェクト名解決など）は持たせない。
2. **`scripts/scan_train_xlsx_xml.py`の拡張** — `target_workbooks()`ループ内で各workbookのzipfile.ZipFileを開いた直後に`xl/pivotTables/pivotTable*.xml`の有無をチェックし、あれば`src/parsers/pivot_cache.py`の関数を呼んで集計結果を収集。新規jsonl `artifacts/train_xlsx_pivot_aggregates.jsonl` に1行=1(project, sheet, pivotTable, dataField)として書き出す。スキーマ例:
   ```json
   {
     "project_name": "株式会社青葉バイオメディカル機器",
     "sheet_name": "Pivot",
     "pivot_table_name": "ピボットテーブル1",
     "row_fields": ["Attrition", "Gender", "MaritalStatus", "EducationField"],
     "data_field_name": "平均 / MonthlyIncome",
     "data_field_source": "MonthlyIncome",
     "subtotal": "average",
     "n_groups": 66,
     "argmax_labels": {"Attrition": "No", "Gender": "Female", "MaritalStatus": "Single", "EducationField": "Human Resources"},
     "argmax_value": 17328.0,
     "argmin_labels": {...},
     "argmin_value": 2105.5
   }
   ```
   （このタスク自体で`scripts/scan_train_xlsx_xml.py`や`artifacts/`への書き込みは禁止のため、上記は設計提案のみで未実装。）
   同時に、この拡張と対で「NFC正規化されていない`"03.データ" in p.parts`」を`unicodedata.normalize("NFC", ...)`込みの比較に直すことも合わせて提案する（エッジケース#1参照）。
3. **`src/structured/artifact_store.py`** — `_ARTIFACT_FILES`に`"train_xlsx_pivot_aggregates": "train_xlsx_pivot_aggregates.jsonl"`を追加するだけ（既存の`_get()`はNFC正規化込みでproject_name引き当てを行う実装が既にあるので、ここは手を加えずに済む）。
4. **`src/retriever/structured_context.py`** — 新しい質問パターン検出関数（例: `_is_pivot_layer_extremum_question(question)`）を追加。「Pivot」「ピボット」等のヒント＋「最も高い/低い」「最大/最小」等の比較語＋対象指標名（dataField名やdataField_sourceの部分一致）を検出したら、`StructuredArtifactStore`から`train_xlsx_pivot_aggregates`をproject_nameで引き、指標名でdataFieldを絞り込み、argmax（or argmin）のlabelsを`"Attrition = No、Gender = Female、..."`の形式に整形して返す。質問文からdataFieldを一意に決められない場合（同名複数dataFieldがある等）は候補を全部提示するなど安全側にフォールバックする。

### この設計が「一般則」である理由
- どのフィールドがrowFieldか、どれがdataFieldか、集計関数が何かは、すべてpivotTable/pivotCacheDefinition XMLから機械的に読み取るのみで、特定の列名・値をコードに書いていない。
- 質問文からの実行時解釈（「最も高い」→argmax等）は別関数に分離してあり、artifacts生成側は質問文を一切見ない。
- 5プロジェクト・9pivotTableという構造の異なる実データ（rowFields数1〜4、colFieldsあり/なし、subtotal average/sum/max、rowFieldsが実質空、のいずれのバリエーションも）で0エラー・意味的に妥当なargmax/argminが出ており、未知のpivot質問（異なる案件・異なるdataField・異なる比較の向き）に対しても同じ導出パスで対応できる。

---

## 付随ファイル
- PoCスクリプト: `scripts/poc_pivot_recompute.py`（本リポジトリに保存。再実行で全train.xlsxの
  pivot再計算結果を再現できる）
- 全件実行結果(JSON)・実行ログ・生XMLダンプはセッションの一時領域のみ（スクリプト再実行で再現可能）
