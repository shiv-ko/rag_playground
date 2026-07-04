# valid 失敗切り分け表（2026-07-05）

run: `exp_officegate_valid_1783176844.json` / retrieval: `retrieval_valid_1783178147.json` / raw判定judge: none

## 集計

| 分類 | 件数 |
|---|---|
| OK | 13 |
| 生成失敗 | 9 |
| 検索失敗 | 6 |
| 計測不能(手動確認) | 1 |
| 較正失敗(ゲート素通り) | 1 |

## 質問別

| # | type | 最終label | 検索hit | gated | 生回答判定 | 分類 | 質問 |
|---|---|---|---|---|---|---|---|
| 0 | office_style | Missing | × | ○ | - | 検索失敗 | 青潮モビリティサービスの最終報告における、モビリティ需要の要因分析のページで、マ |
| 1 | image_graph | Missing | ○ | ○ | - | 生成失敗 | KSSのfigure_06.pngにおいて、dayによる件数推移とあわせて表示さ |
| 2 | single_text | Missing | × | ○ | - | 検索失敗 | 恒一会 かえで総合病院の提案書内で、重視するとされている評価指標を答えてください |
| 3 | cross_project | Missing | × | ○ | - | 計測不能(手動確認) | 全案件で支払った税込金額をもとに、消費税額の総額を計算してください。 |
| 4 | code_static | Missing | ○ | ○ | - | 生成失敗 | 青嶺不動産アセットマネジメントの modeling.py において、前処理器の  |
| 5 | single_text | Perfect | ○ | - | - | OK | 白峰信用リスク評価の最終報告書において、「プロジェクト目的とスコープ」内でAPI |
| 6 | spreadsheet_state | Perfect | × | - | - | OK | 恒一会 かえで総合病院のtrain.xlsx内の PivotTable で集計さ |
| 7 | spreadsheet_calc | Perfect | × | - | - | OK | 恒一会 かえで総合病院のプロジェクトデータ（train.csv）において、dis |
| 8 | contract_rule | Perfect | ○ | - | - | OK | 蒼泉会 ひがし丘総合病院の契約条件において、仮に実績工数が見込工数の4分の3だっ |
| 9 | version_diff | Missing | ○ | ○ | - | 生成失敗 | 青嶺不動産アセットマネジメントの提案書について、oldフォルダ内の旧版と提案フォ |
| 10 | list_extraction | Missing | × | ○ | - | 検索失敗 | 蒼樹会 みなみ野女性医療センターの最終報告書にて、影響度が最も高いとされている残 |
| 11 | spreadsheet_state | Perfect | × | - | - | OK | 東都人材プラットフォームのtrain.xlsxにおいて、trainシートでフィル |
| 12 | contract_rule | Missing | ○ | ○ | - | 生成失敗 | 京橋信用ソリューションズの契約金額（税込）はいくらですか。 |
| 13 | spreadsheet_calc | Perfect | ○ | - | - | OK | 青葉与信マネジメントの分析対象データにおいて、term=3 years、grad |
| 14 | single_text | Acceptable | ○ | ○ | - | OK | 青葉バイオメディカル機器案件において、鈴木 美咲さんはどの役割としてアサインされ |
| 15 | internal_terms | Missing | ○ | ○ | - | 生成失敗 | 中間報告会または中間レビューが2025年7月1日以前に実施された案件を、主略称で |
| 16 | internal_terms | Missing | × | ○ | - | 検索失敗 | MINAMINOのPLにおいて、M01当日を1日目として数えた場合、M01の日か |
| 17 | single_text | Perfect | ○ | - | - | OK | 京橋信用ソリューションズのカラム説明において、カラム名pdaysの値-1は何を表 |
| 18 | internal_terms | Perfect | × | - | - | OK | 東都のCTにおいて、全14章のうち「本業務の対象データ、前提および制約」が記載さ |
| 19 | list_extraction | Missing | ○ | ○ | - | 生成失敗 | 青嶺不動産アセットマネジメント案件で分析設計を担当する人の名前をフルネームで抽出 |
| 20 | internal_terms | Perfect | ○ | - | - | OK | AYMのPLにおいて、探索的分析・仮説整理フェーズに一致するタスクIDをすべて挙 |
| 21 | spreadsheet_state | Missing | × | ○ | - | 検索失敗 | 青葉バイオメディカル機器のtrain.xlsxのPivotシートにおいて、平均月 |
| 22 | notebook_output | Missing | ○ | ○ | - | 生成失敗 | AOSHIOの NB01_eda.ipynbにおいて、観察結果サマリで出力されて |
| 23 | office_style | Acceptable | ○ | - | - | OK | AOSHIOのM02資料（docx）において、黄色でハイライトされている部分をす |
| 24 | notebook_output | Missing | ○ | ○ | - | 生成失敗 | 白峰信用リスク評価の 01_eda.ipynb にある特徴量相関ヒートマップの図 |
| 25 | office_style | Incorrect | ○ | - | - | 較正失敗(ゲート素通り) | 東都人材プラットフォームの提案書P7において、赤で強調されている箇所の文字列を抜 |
| 26 | spreadsheet_calc | Acceptable | × | - | - | OK | 青葉バイオメディカル機器のtrain.csvにおいて、EducationFiel |
| 27 | analysis_metrics | Missing | ○ | - | - | 生成失敗 | 蒼泉会 ひがし丘総合病院案件において、中間報告資料に記載されたMacro F1ス |
| 28 | code_static | Missing | × | ○ | - | 検索失敗 | 蒼泉会の分析コードにおいて、CATは dtype とユニーク数の条件でどのように |
| 29 | contract_rule | Perfect | ○ | - | - | OK | 蒼樹会 みなみ野女性医療センターの契約書第8条において、本契約終了後に秘密保持義 |

## 2026-07-05 追記: サブエージェント診断による再分類（レビュー済み）

PoC診断2本（`docs/pdf_highlight_feasibility.md` / `docs/pivot_cache_recovery_poc.md`）の結果、
上表の「検索失敗」6問のうち3問の分類を更新する:

| # | 旧分類 | 新分類 | 根拠 |
|---|---|---|---|
| 0 | 検索失敗 | **能力外（ラスタPDF）** | 対象の最終報告.pdfは全13ページがテキスト層なしの画像貼付。ハイライトはピクセルとしてのみ存在（OCRなしでは原理的に不可）。GTは画像目視で妥当性確認済み |
| 10 | 検索失敗 | **能力外（ラスタPDF）** | 対象のみなみ野最終報告.pdfも全15ページラスタ化。同案件は05.会議/06.報告書のPDFが全てこの形式 |
| 21 | 検索失敗 | **回収可能（設計確定）** | pivotTable XML＋pivotCache再計算のPoCがGT完全一致（argmax=17328.0）。9/9 pivotTableで0エラー。実装設計はレポート§5 |

データセット全体の含意: 全28PDF中18件（64%）が全ページラスタ化・ハイライト注釈は0件。
**PDF内の視覚情報（マーカー等）を問う質問は能力外ゲート維持が正**。残る検索失敗はQ2/Q16/Q28。
