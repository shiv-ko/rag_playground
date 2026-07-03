# Office Marks Scan

`scripts/extract_office_marks.py` によるDOCX/PPTXの書式抽出PoC。PDFは対象外。

## Summary

| item | count |
|---|---:|
| marks | 9315 |
| failures | 1 |
| bold | 4596 |
| italic | 111 |
| underline | 18 |
| font_color | 8210 |
| highlight_color | 21 |

## By Extension

| extension | count |
|---|---:|
| `.pptx` | 8075 |
| `.docx` | 1240 |

## Highlight Colors

| color | count |
|---|---:|
| `YELLOW (7)` | 14 |
| `PINK (5)` | 4 |
| `BRIGHT_GREEN (4)` | 3 |

## Font Colors Top

| color | count |
|---|---:|
| `FFFFFF` | 1786 |
| `3D3D3D` | 1120 |
| `333333` | 773 |
| `4A4A4A` | 751 |
| `1A1A1A` | 602 |
| `8B2500` | 566 |
| `2B2B2B` | 241 |
| `2D3748` | 224 |
| `6B6B6B` | 214 |
| `1F1F1F` | 210 |
| `5A5A5A` | 194 |
| `2D2D2D` | 193 |
| `4A5568` | 162 |
| `5C5C5C` | 132 |
| `8C8C8C` | 126 |
| `A0332E` | 118 |
| `8B2D2D` | 82 |
| `7A7A7A` | 77 |
| `707070` | 63 |
| `718096` | 48 |

## Failures

| source | error |
|---|---|
| `data/raw/share/共有ドライブ/プロジェクト/医療法人社団 恒一会 かえで総合病院/01.契約/契約書_pw-kaede20250902.docx` | `BadZipFile('File is not a zip file')` |

## Notes

- PPTXは図形塗りや通常テーマ色も拾うため、回答時は質問条件に応じて色/太字/スライド番号で絞る。
- DOCXの黄色ハイライト、下線、イタリック、太字はrun単位で抽出できる。
- 失敗1件は暗号化DOCXで、パスワード導出/復号キューに回す。
