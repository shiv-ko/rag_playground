# Excel系設問カバレッジ

## 集計

- `covered_artifact`: 17
- `partial`: 8
- `not_covered`: 23

## covered_artifact

| split | index | project | needed | evidence | question |
|---|---:|---|---|---|---|
| test | 2 | 株式会社青嶺不動産アセットマネジメント | schedule_tasks | schedule_tasks | 青嶺不動産アセットマネジメントのスケジュール_r2.xlsxにおいて、オレンジにハイライトされている行のタスク名をすべて答えてください。 |
| test | 15 | 株式会社東都人材プラットフォーム | train_xlsx_highlight_context | train_xlsx_highlight_context | 東都人材プラットフォームのtrain.xlsxにおいて、Sheet1の黄色にハイライトされたセルの抽出条件と集計内容を答えてください。 |
| test | 19 | 株式会社青嶺不動産アセットマネジメント | schedule_tasks | schedule_tasks | 青嶺不動産アセットマネジメントのスケジュール_r2.xlsxにおいて、2025-08-11から2025-09-09の間に開始日または終了日が設定されているタスクIDをすべて挙げてください。 |
| test | 25 | 白峰信用リスク評価株式会社 | train_xlsx_highlight_context | train_xlsx_highlight_context | 白峰信用リスク評価のtrain.xlsxにおいて、青色ハイライト部分の合計値を求めてください。四捨五入して整数で答えてください。 |
| test | 42 | 医療法人社団 蒼泉会 ひがし丘総合病院 | train_xlsx_highlight_context | train_xlsx_highlight_context | 蒼泉会 ひがし丘総合病院のtrain.xlsxのSheet1において、黄色ハイライトされている数値に対応するデータの抽出条件と集計内容を答えてください。 |
| test | 47 | 株式会社青嶺不動産アセットマネジメント | train_xlsx_highlight_context | train_xlsx_highlight_context | 青嶺不動産アセットマネジメントのtrain.xlsxにおいて、黄色ハイライトセルは予測と実際の誤差を計算していますが、その予測値の対象となっている不動産の建設年を算出してください。 |
| test | 51 | 白峰信用リスク評価株式会社 | schedule_tasks | schedule_tasks | 白峰信用リスク評価の提案書.pptxにおいて、モデルの高度化（説明性・セグメント分析）の実行予定スケジュールは案件開始から第何週目に実施予定でしょうか。 |
| test | 65 | 白峰信用リスク評価株式会社 | train_xlsx_highlight_context | train_xlsx_highlight_context | 白峰信用リスク評価のtrain.xlsxにおいて、表示されている相関係数シートで、黄色ハイライトになっているセルの条件を答えてください。 |
| test | 69 | 白峰信用リスク評価株式会社 | schedule_tasks | schedule_tasks | 白峰信用リスク評価の最終報告資料において、パイロット運用は本番化スケジュール上で第何週目から第何週目に実施予定ですか。 |
| test | 77 | 医療法人社団 蒼泉会 ひがし丘総合病院 | train_xlsx_highlight_context | train_xlsx_highlight_context | 蒼泉会 ひがし丘総合病院のtrain.xlsxのSheet2において、黄色ハイライトされている数値に対応するデータの抽出条件と集計内容を答えてください。 |
| test | 80 | 株式会社東都人材プラットフォーム | train_xlsx_highlight_context | train_xlsx_highlight_context | 東都人材プラットフォームのtrain.xlsxにおいて、Sheet2の黄色にハイライトされたセルの抽出条件と集計内容を答えてください。 |
| test | 82 | 医療法人社団 蒼泉会 ひがし丘総合病院 | schedule_tasks | schedule_tasks | 蒼泉会 ひがし丘総合病院のスケジュール.xlsxにおいて、WBSシートでオレンジ色にハイライトされている行のタスクIDをすべて教えてください。 |
| test | 88 | 医療法人社団 蒼樹会 みなみ野女性医療センター | schedule_tasks | schedule_tasks | 蒼樹会 みなみ野女性医療センターの提案書内のスケジュール案において、第5週目に実施することになっている項目は何ですか。 |
| test | 89 | 京橋信用ソリューションズ株式会社 | schedule_tasks | schedule_tasks | 京橋信用ソリューションズのスケジュール.xlsxにおいて、フェーズNo6にて最後に開始するタスク名は何ですか。 |
| test | 90 | 株式会社青潮モビリティサービス | schedule_tasks | schedule_tasks | 青潮モビリティサービスのスケジュール.xlsxにおいて、バッファとして使用した工数の合計は何時間ですか。 |
| test | 94 | 医療法人社団 蒼樹会 みなみ野女性医療センター | schedule_tasks | schedule_tasks | 蒼樹会 みなみ野女性医療センターのスケジュール.xlsxにおいて、MS3に紐づくタスクのうち、ビジネスアナリストが関わっているタスクIDを答えてください。 |
| test | 97 | 株式会社青葉バイオメディカル機器 | train_xlsx_highlight_context | train_xlsx_highlight_context | 青葉バイオメディカル機器のtrain.xlsxにおいて、黄色ハイライトが交差している2つのセルの値の差の絶対値を計算してください。 |

## partial / not_covered

| status | split | index | needed | note | question |
|---|---|---:|---|---|---|
| not_covered | valid | 1 | unknown | artifact missing or insufficient | KSSのfigure_06.pngにおいて、dayによる件数推移とあわせて表示されているTG平均が最も低い日は何日ですか。 |
| partial | valid | 6 | train_xlsx_visual_or_pivot | metadata exists, but chart/pivot/formula interpretation is still needed | 恒一会 かえで総合病院のtrain.xlsx内の PivotTable で集計されている表から、ALPの平均が最も高いものの抽出条件を教えてください。 |
| not_covered | valid | 7 | raw_table_calc | requires CSV/table calculation engine outside current Excel artifacts | 恒一会 かえで総合病院のプロジェクトデータ（train.csv）において、disease=1の女性の中で、ALT_GPTの平均値が最も高い年齢は何歳ですか。 |
| partial | valid | 11 | train_xlsx_visual_or_pivot | metadata exists, but chart/pivot/formula interpretation is still needed | 東都人材プラットフォームのtrain.xlsxにおいて、trainシートでフィルターで抽出されている条件を教えてください。 |
| not_covered | valid | 13 | raw_table_calc | requires CSV/table calculation engine outside current Excel artifacts | 青葉与信マネジメントの分析対象データにおいて、term=3 years、grade=B1、purpose=credit_cardに該当するloan_amntの平均を算出してください。四捨五入して整数値で出してください。 |
| partial | valid | 21 | train_xlsx_visual_or_pivot | metadata exists, but chart/pivot/formula interpretation is still needed | 青葉バイオメディカル機器のtrain.xlsxのPivotシートにおいて、平均月収が最も高い層の抽出条件を答えてください。 |
| not_covered | valid | 22 | unknown | artifact missing or insufficient | AOSHIOの NB01_eda.ipynbにおいて、観察結果サマリで出力されている「TGとの相関 上位5」の中で、相関係数が最も小さいカラム名を答えてください。 |
| not_covered | valid | 24 | unknown | artifact missing or insufficient | 白峰信用リスク評価の 01_eda.ipynb にある特徴量相関ヒートマップの図で可視化されている特徴量のうち、classとの相関係数の絶対値が最も小さい特徴量名を答えてください。 |
| not_covered | valid | 26 | raw_table_calc | requires CSV/table calculation engine outside current Excel artifacts | 青葉バイオメディカル機器のtrain.csvにおいて、EducationFieldがMarketingかつMonthlyIncomeが10000より大きいデータを抽出し、Ageの平均値を計算してください。その平均値に最も近い年齢のidをすべて答えてください。 |
| not_covered | valid | 27 | unknown | artifact missing or insufficient | 蒼泉会 ひがし丘総合病院案件において、中間報告資料に記載されたMacro F1スコアの詳細値と、最終分析出力metrics.jsonに記録されているMacro F1スコアの詳細値を用いて、改善幅を小数第6位まで答えてください。 |
| not_covered | test | 4 | unknown | artifact missing or insufficient | 蒼泉会 ひがし丘総合病院の01_eda.ipynbを確認して、目的変数と相関が最も高い数値特徴量を教えてください。 |
| not_covered | test | 8 | unknown | artifact missing or insufficient | 東都人材プラットフォームのデータサイエンティスト調査資料において、米国平均給与における機械学習（ML）エンジニアとデータエンジニアの差はいくらですか。 |
| partial | test | 10 | train_xlsx_visual_or_pivot | metadata exists, but chart/pivot/formula interpretation is still needed | 恒一会 かえで総合病院のtrain.xlsxにおいて、AG_ratioのヒストグラムで最も多いカウント数はいくつですか。 |
| not_covered | test | 12 | page_layout | requires page-level document extraction | 蒼泉会 ひがし丘総合病院の報告資料_2025-07-08.docxにおいて、WBS観点の進捗状況の見出しがあるのは何ページですか。 |
| not_covered | test | 24 | raw_table_calc | requires CSV/table calculation engine outside current Excel artifacts | 分析データの中で、1つでも欠損値がある行数が最も多い案件を、主略称で答えてください。 |
| not_covered | test | 28 | unknown | artifact missing or insufficient | 蒼樹会 みなみ野女性医療センターの分析結果として予測に影響が高いと報告されている特徴量の中で、最もターゲットとの相関が高い特徴量を答えてください。 |
| partial | test | 29 | train_xlsx_visual_or_pivot | metadata exists, but chart/pivot/formula interpretation is still needed | 恒一会 かえで総合病院のtrain.xlsx内のTPのヒストグラムで、3番目にカウント数が多いビンの範囲を小数第6位までで答えてください。 |
| not_covered | test | 30 | raw_table_calc | requires CSV/table calculation engine outside current Excel artifacts | 青葉与信マネジメントの分析対象データにおいて、標準化されたloan_amntが0未満の行のうち、purpose=credit_cardに該当し、かつloan_amntがpurpose=credit_card全体の平均を上回る行の割合は何%ですか。小数第2位まで答えてください。 |
| not_covered | test | 31 | unknown | artifact missing or insufficient | 固定金額契約の中で、分析データ1行あたりの契約金額（税込）が最も高い案件を、主略称と1行あたりの金額で答えてください。1行あたりの金額は円単位で切り上げてください。 |
| not_covered | test | 35 | unknown | artifact missing or insufficient | 京橋信用ソリューションズの京橋信用ソリューションズ株式会社_最終報告.pptxにおいて、F1スコアにてgradient_boostingに次ぐ順位のモデルの Accuracy はいくつですか。 |
| not_covered | test | 36 | unknown | artifact missing or insufficient | 恒一会 かえで総合病院案件において、中間報告時点のF1スコア実測値と最終報告時点のF1スコア実測値の差を絶対値で答えてください。 |
| not_covered | test | 38 | unknown | artifact missing or insufficient | 社内管理のAPRに照らして、APR-M3が必要な案件を主略称ですべて挙げ、それらの契約金額（税込）の合計を答えてください。 |
| partial | test | 39 | train_xlsx_visual_or_pivot | metadata exists, but chart/pivot/formula interpretation is still needed | 青潮モビリティサービスのtrain.xlsxのSheet1にあるグラフ1はどのカラムを可視化したものですか。 |
| not_covered | test | 57 | unknown | artifact missing or insufficient | 青葉のTXにて算出された回帰係数を用いて全データの予測値を計算し、正解データに対する F1 スコアが最大となるように閾値を設定したときの F1 スコアを答えてください。小数第5位まで求めてください。 |
| partial | test | 63 | train_xlsx_formula_cells | metadata exists, but chart/pivot/formula interpretation is still needed | 青葉与信マネジメントのtrain.xlsxにて算出された回帰係数を使ってid=0を予測した場合の予測値はいくらになりますか。小数第5位まで求めてください。 |
| not_covered | test | 64 | unknown | artifact missing or insufficient | 青潮モビリティサービスの最終報告PDFにおいて、将来のフェーズAとフェーズBを実施した場合の想定工数は合計で何時間ですか。 |
| not_covered | test | 83 | train_xlsx_formula_cells | metadata exists, but chart/pivot/formula interpretation is still needed | 蒼樹会 みなみ野女性医療センターのtrain.xlsxにおいて、回帰分析の結果として記載されている係数をindex=1770のデータに当てはめたときの予測値はいくつですか。小数第5位まで答えてください。 |
| not_covered | test | 84 | page_layout | requires page-level document extraction | 東都人材プラットフォームの最終報告書で分析結果が記載されている中で、モデル毎のF1スコアがランキング形式で記載されているページ数を教えてください。 |
| not_covered | test | 91 | raw_table_calc | requires CSV/table calculation engine outside current Excel artifacts | 京橋信用ソリューションズの顧客データにおいて、目的変数と最も強い負の相関を持つカラムは何ですか。 |
| not_covered | test | 92 | schedule_tasks | artifact missing or insufficient | 恒一会 かえで総合病院案件において、マイルストーンID、タスクID、アクションIDの3種類のIDは合計でいくつ発行されていますか。マークダウンファイル以外から算出してください。 |
| partial | test | 95 | spreadsheet_diff | artifact missing or insufficient | 青嶺不動産アセットマネジメントのスケジュール_r1.xlsxとスケジュール_r2.xlsxを比較したとき、未着手から完了への変更を除いて、案件遂行に関連する変更点を挙げてください。 |
