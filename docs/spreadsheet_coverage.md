# Spreadsheet Coverage

`scripts/analyze_spreadsheet_coverage.py` による初期カバレッジ分析。回答生成ではなく、抽出済みartifactでどの質問に近づけるかを判定するためのメモ。

## Summary

| status | count |
|---|---:|
| `not_covered` | 16 |
| `partial` | 11 |
| `covered_artifact` | 4 |

## By Split

| split | status | count |
|---|---|---:|
| `test` | `covered_artifact` | 3 |
| `test` | `not_covered` | 13 |
| `test` | `partial` | 11 |
| `valid` | `covered_artifact` | 1 |
| `valid` | `not_covered` | 3 |

## Questions

| split | index | status | project | reason | question |
|---|---:|---|---|---|---|
| `valid` | 6 | `not_covered` | 医療法人社団 恒一会 かえで総合病院 | train.xlsx extraction is not implemented yet | 恒一会 かえで総合病院のtrain.xlsx内の PivotTable で集計されている表から、ALPの平均が最も高いものの抽出条件を教えてください。 |
| `valid` | 11 | `not_covered` | 株式会社東都人材プラットフォーム | train.xlsx extraction is not implemented yet | 東都人材プラットフォームのtrain.xlsxにおいて、trainシートでフィルターで抽出されている条件を教えてください。 |
| `valid` | 20 | `covered_artifact` | 青葉与信マネジメント株式会社 | schedule rows extracted; query-specific computation still needed | AYMのPLにおいて、探索的分析・仮説整理フェーズに一致するタスクIDをすべて挙げてください。 |
| `valid` | 21 | `not_covered` | 株式会社青葉バイオメディカル機器 | train.xlsx extraction is not implemented yet | 青葉バイオメディカル機器のtrain.xlsxのPivotシートにおいて、平均月収が最も高い層の抽出条件を答えてください。 |
| `test` | 2 | `partial` | 株式会社青嶺不動産アセットマネジメント | schedule rows extracted, but diff logic is not implemented | 青嶺不動産アセットマネジメントのスケジュール_r2.xlsxにおいて、オレンジにハイライトされている行のタスク名をすべて答えてください。 |
| `test` | 10 | `not_covered` | 医療法人社団 恒一会 かえで総合病院 | train.xlsx extraction is not implemented yet | 恒一会 かえで総合病院のtrain.xlsxにおいて、AG_ratioのヒストグラムで最も多いカウント数はいくつですか。 |
| `test` | 12 | `partial` | 医療法人社団 蒼泉会 ひがし丘総合病院 | schedule rows may help, but the requested source is not the schedule workbook | 蒼泉会 ひがし丘総合病院の報告資料_2025-07-08.docxにおいて、WBS観点の進捗状況の見出しがあるのは何ページですか。 |
| `test` | 15 | `not_covered` | 株式会社東都人材プラットフォーム | train.xlsx extraction is not implemented yet | 東都人材プラットフォームのtrain.xlsxにおいて、Sheet1の黄色にハイライトされたセルの抽出条件と集計内容を答えてください。 |
| `test` | 19 | `partial` | 株式会社青嶺不動産アセットマネジメント | schedule rows extracted, but diff logic is not implemented | 青嶺不動産アセットマネジメントのスケジュール_r2.xlsxにおいて、2025-08-11から2025-09-09の間に開始日または終了日が設定されているタスクIDをすべて挙げてください。 |
| `test` | 25 | `not_covered` | 白峰信用リスク評価株式会社 | train.xlsx extraction is not implemented yet | 白峰信用リスク評価のtrain.xlsxにおいて、青色ハイライト部分の合計値を求めてください。四捨五入して整数で答えてください。 |
| `test` | 29 | `not_covered` | 医療法人社団 恒一会 かえで総合病院 | train.xlsx extraction is not implemented yet | 恒一会 かえで総合病院のtrain.xlsx内のTPのヒストグラムで、3番目にカウント数が多いビンの範囲を小数第6位までで答えてください。 |
| `test` | 39 | `not_covered` | 株式会社青潮モビリティサービス | train.xlsx extraction is not implemented yet | 青潮モビリティサービスのtrain.xlsxのSheet1にあるグラフ1はどのカラムを可視化したものですか。 |
| `test` | 41 | `covered_artifact` | 株式会社青葉バイオメディカル機器 | schedule rows extracted; query-specific computation still needed | AOBMのPLANにおいて、加藤さんが担当者に含まれるタスクIDはいくつありますか。 |
| `test` | 42 | `not_covered` | 医療法人社団 蒼泉会 ひがし丘総合病院 | train.xlsx extraction is not implemented yet | 蒼泉会 ひがし丘総合病院のtrain.xlsxのSheet1において、黄色ハイライトされている数値に対応するデータの抽出条件と集計内容を答えてください。 |
| `test` | 47 | `not_covered` | 株式会社青嶺不動産アセットマネジメント | train.xlsx extraction is not implemented yet | 青嶺不動産アセットマネジメントのtrain.xlsxにおいて、黄色ハイライトセルは予測と実際の誤差を計算していますが、その予測値の対象となっている不動産の建設年を算出してください。 |
| `test` | 51 | `partial` | 白峰信用リスク評価株式会社 | schedule rows may help, but the requested source is not the schedule workbook | 白峰信用リスク評価の提案書.pptxにおいて、モデルの高度化（説明性・セグメント分析）の実行予定スケジュールは案件開始から第何週目に実施予定でしょうか。 |
| `test` | 63 | `not_covered` | 青葉与信マネジメント株式会社 | train.xlsx extraction is not implemented yet | 青葉与信マネジメントのtrain.xlsxにて算出された回帰係数を使ってid=0を予測した場合の予測値はいくらになりますか。小数第5位まで求めてください。 |
| `test` | 65 | `not_covered` | 白峰信用リスク評価株式会社 | train.xlsx extraction is not implemented yet | 白峰信用リスク評価のtrain.xlsxにおいて、表示されている相関係数シートで、黄色ハイライトになっているセルの条件を答えてください。 |
| `test` | 69 | `partial` | 白峰信用リスク評価株式会社 | schedule rows may help, but the requested source is not the schedule workbook | 白峰信用リスク評価の最終報告資料において、パイロット運用は本番化スケジュール上で第何週目から第何週目に実施予定ですか。 |
| `test` | 72 | `partial` | 京橋信用ソリューションズ株式会社 | schedule rows may help, but the requested source is not the schedule workbook | KSSにおいて、データエンジニアが担当するタスクIDはいくつありますか。 |
| `test` | 77 | `not_covered` | 医療法人社団 蒼泉会 ひがし丘総合病院 | train.xlsx extraction is not implemented yet | 蒼泉会 ひがし丘総合病院のtrain.xlsxのSheet2において、黄色ハイライトされている数値に対応するデータの抽出条件と集計内容を答えてください。 |
| `test` | 80 | `not_covered` | 株式会社東都人材プラットフォーム | train.xlsx extraction is not implemented yet | 東都人材プラットフォームのtrain.xlsxにおいて、Sheet2の黄色にハイライトされたセルの抽出条件と集計内容を答えてください。 |
| `test` | 82 | `partial` | 医療法人社団 蒼泉会 ひがし丘総合病院 | schedule rows and row colors extracted; answer logic still needed | 蒼泉会 ひがし丘総合病院のスケジュール.xlsxにおいて、WBSシートでオレンジ色にハイライトされている行のタスクIDをすべて教えてください。 |
| `test` | 83 | `not_covered` | 医療法人社団 蒼樹会 みなみ野女性医療センター | train.xlsx extraction is not implemented yet | 蒼樹会 みなみ野女性医療センターのtrain.xlsxにおいて、回帰分析の結果として記載されている係数をindex=1770のデータに当てはめたときの予測値はいくつですか。小数第5位まで答えてください。 |
| `test` | 88 | `partial` | 医療法人社団 蒼樹会 みなみ野女性医療センター | schedule rows may help, but the requested source is not the schedule workbook | 蒼樹会 みなみ野女性医療センターの提案書内のスケジュール案において、第5週目に実施することになっている項目は何ですか。 |
| `test` | 89 | `covered_artifact` | 京橋信用ソリューションズ株式会社 | schedule rows extracted; query-specific computation still needed | 京橋信用ソリューションズのスケジュール.xlsxにおいて、フェーズNo6にて最後に開始するタスク名は何ですか。 |
| `test` | 90 | `covered_artifact` | 株式会社青潮モビリティサービス | schedule rows extracted; query-specific computation still needed | 青潮モビリティサービスのスケジュール.xlsxにおいて、バッファとして使用した工数の合計は何時間ですか。 |
| `test` | 94 | `partial` | 医療法人社団 蒼樹会 みなみ野女性医療センター | schedule rows extracted, but role/person registry is required | 蒼樹会 みなみ野女性医療センターのスケジュール.xlsxにおいて、MS3に紐づくタスクのうち、ビジネスアナリストが関わっているタスクIDを答えてください。 |
| `test` | 95 | `partial` | 株式会社青嶺不動産アセットマネジメント | schedule rows extracted, but diff logic is not implemented | 青嶺不動産アセットマネジメントのスケジュール_r1.xlsxとスケジュール_r2.xlsxを比較したとき、未着手から完了への変更を除いて、案件遂行に関連する変更点を挙げてください。 |
| `test` | 96 | `partial` | 青葉与信マネジメント株式会社 | schedule rows may help, but the requested source is not the schedule workbook | 青葉与信マネジメントのチェックポイント2として設定されている内容に関連するタスクIDを教えてください。 |
| `test` | 97 | `not_covered` | 株式会社青葉バイオメディカル機器 | train.xlsx extraction is not implemented yet | 青葉バイオメディカル機器のtrain.xlsxにおいて、黄色ハイライトが交差している2つのセルの値の差の絶対値を計算してください。 |
