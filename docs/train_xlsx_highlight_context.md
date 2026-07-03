# train.xlsx ハイライトセル周辺見出し復元

## 目的

`03.データ/train.xlsx` の色付きセルについて、セル値だけでなく周辺見出し・近傍セル・数式参照を復元し、設問回答時に「何の値か」を判定できるようにする。

## 生成物

- `artifacts/train_xlsx_highlight_context.jsonl`: ハイライトセル単位の周辺文脈
- `artifacts/train_xlsx_highlight_blocks.jsonl`: 連続ハイライト範囲の集約

## 集計

- ハイライトセル: 813
- ハイライトブロック: 13

| project | highlighted cells |
|---|---:|
| 医療法人社団 蒼泉会 ひがし丘総合病院 | 2 |
| 株式会社東都人材プラットフォーム | 1 |
| 株式会社青嶺不動産アセットマネジメント | 1 |
| 株式会社青潮モビリティサービス | 6 |
| 株式会社青葉バイオメディカル機器 | 800 |
| 白峰信用リスク評価株式会社 | 3 |

## 主要ブロック

| project | sheet | range | count | color | orientation | first | last | inferred context |
|---|---|---:|---:|---|---|---|---|---|
| 医療法人社団 蒼泉会 ひがし丘総合病院 | Sheet1 | `F22` | 1 | yellow | single | 35.950927843529414 | 35.950927843529414 | 平均 / bmi |
| 医療法人社団 蒼泉会 ひがし丘総合病院 | Sheet2 | `E14` | 1 | yellow | single | 4674 | 4674 | 合計 / age |
| 株式会社東都人材プラットフォーム | Sheet1 | `E1409` | 1 | yellow | single | 12 | 12 | 個数 |
| 株式会社青嶺不動産アセットマネジメント | Sheet2 | `B22` | 1 | yellow | single | 141250325712.51495 | 141250325712.51495 | 自由度 |
| 株式会社青潮モビリティサービス | Sheet2 | `I3:M3` | 5 | THEME:4 | horizontal | 行ラベル | 平均 / cnt | 平均 / cnt |
| 株式会社青潮モビリティサービス | Sheet3 | `D14` | 1 | yellow | single | 0.78 | 0.78 | 2 |
| 株式会社青葉バイオメディカル機器 | train | `A138:Q138` | 17 | yellow | horizontal | train_0136 | Divorced | id, Age, Attrition, BusinessTravel, DailyRate, Department |
| 株式会社青葉バイオメディカル機器 | train | `A79:Q79` | 17 | yellow | horizontal | train_0077 | Divorced | id, Age, Attrition, BusinessTravel, DailyRate, Department |
| 株式会社青葉バイオメディカル機器 | train | `R1:R736` | 736 | yellow | vertical | MonthlyIncome | 5775 | MonthlyIncome |
| 株式会社青葉バイオメディカル機器 | train | `S138:AG138` | 15 | yellow | horizontal | 4 | 3 | NumCompaniesWorked, Over18, OverTime, PercentSalaryHike, PerformanceRating, RelationshipSatisfaction |
| 株式会社青葉バイオメディカル機器 | train | `S79:AG79` | 15 | yellow | horizontal | 4 | 3 | NumCompaniesWorked, Over18, OverTime, PercentSalaryHike, PerformanceRating, RelationshipSatisfaction |
| 白峰信用リスク評価株式会社 | Sheet5 | `B8:B9` | 2 | blue | vertical | -11850477.417452984 | -669.37054356655221 | 合計 / Attr5 |
| 白峰信用リスク評価株式会社 | Sheet5 | `E12` | 1 | blue | single | -99.061310848999824 | -99.061310848999824 | 合計 / Attr19 |

## 単独セルサンプル

| project | sheet | cell | value | left | above | formula refs |
|---|---|---:|---|---|---|---|
| 医療法人社団 蒼泉会 ひがし丘総合病院 | Sheet1 | `F22` | 35.950927843529414 | 39 | 33.022105717000002 |  |
| 医療法人社団 蒼泉会 ひがし丘総合病院 | Sheet2 | `E14` | 4674 | no | 6746 |  |
| 株式会社東都人材プラットフォーム | Sheet1 | `E1409` | 12 | Spain | 1 |  |
| 株式会社青嶺不動産アセットマネジメント | Sheet2 | `B22` | 141250325712.51495 |  | -209451.40458687639 | B18, Sheet1!U26118, Sheet2!B19, Sheet1!V26118, Sheet2!B17, Sheet1!W26118 |
| 株式会社青潮モビリティサービス | Sheet3 | `D14` | 0.78 | 0.8 | 0.76 |  |
| 白峰信用リスク評価株式会社 | Sheet5 | `E12` | -99.061310848999824 | 合計 / Attr19 | 550.37827214399931 |  |

## 読み取り上の注意

- XML上のキャッシュ値と数式文字列を使っており、Excel再計算はしていない。
- 色は `scan_train_xlsx_xml.py` と同じ簡易正規化を使う。
- `train` シートの縦長ハイライト列は、セル単位成果物では全行、レポートではブロックとして要約する。
