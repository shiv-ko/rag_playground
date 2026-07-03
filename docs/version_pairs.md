# Version Pairs

`scripts/build_version_pairs.py` による旧版/新版ペア候補。差分抽出前に、比較対象ファイルを固定するための中間成果物。

## Summary

| key | count |
|---|---:|
| pairs | 11 |
| confidence=high | 11 |

## By Document Type

| document_type | count |
|---|---:|
| `proposal` | 6 |
| `final_report` | 2 |
| `plan` | 1 |
| `contract` | 1 |
| `notebook` | 1 |

## Pairs

| confidence | project | type | old | new | reason |
|---|---|---|---|---|---|
| `high` | 京橋信用ソリューションズ株式会社 | `proposal` | `提案書_v1.pptx` | `提案書_final.pptx` | ordered explicit version tags: v1->final |
| `high` | 医療法人社団 恒一会 かえで総合病院 | `final_report` | `医療法人社団 恒一会 かえで総合病院_最終報告_old.pptx` | `医療法人社団 恒一会 かえで総合病院_最終報告.pptx` | explicit old version to untagged latest candidate: old->untagged |
| `high` | 株式会社青嶺不動産アセットマネジメント | `proposal` | `提案書.pptx` | `提案書.pptx` | explicit old version to untagged latest candidate: old->untagged |
| `high` | 株式会社青嶺不動産アセットマネジメント | `plan` | `スケジュール_r1.xlsx` | `スケジュール_r2.xlsx` | ordered explicit version tags: r1->r2 |
| `high` | 株式会社青葉バイオメディカル機器 | `contract` | `契約書_draft.docx` | `契約書.docx` | explicit old version to untagged latest candidate: draft->untagged |
| `high` | 白峰信用リスク評価株式会社 | `proposal` | `提案書old.pptx` | `提案書.pptx` | explicit old version to untagged latest candidate: old->untagged |
| `high` | 白峰信用リスク評価株式会社 | `notebook` | `01_eda_old.ipynb` | `01_eda.ipynb` | explicit old version to untagged latest candidate: old->untagged |
| `high` | 青葉与信マネジメント株式会社 | `proposal` | `提案書_v1.pptx` | `提案書_v2.pptx` | ordered explicit version tags: v1->v2 |
| `high` | 青葉与信マネジメント株式会社 | `proposal` | `提案書_v1.pptx` | `提案書_v3.pptx` | ordered explicit version tags: v1->v3 |
| `high` | 青葉与信マネジメント株式会社 | `proposal` | `提案書_v2.pptx` | `提案書_v3.pptx` | ordered explicit version tags: v2->v3 |
| `high` | 青葉与信マネジメント株式会社 | `final_report` | `青葉与信マネジメント株式会社_最終報告.pptx` | `青葉与信マネジメント株式会社_最終報告.pptx` | explicit old version to untagged latest candidate: old->untagged |
