# 暗号化・抽出失敗ファイルキュー

## 目的

構造化抽出から漏れたファイルを一覧化し、復号または形式対応後に再抽出できるようにする。

## 集計

- queued files: 1
- encrypted/legacy containers: 1
- other failures: 0

| type | extractor | file | action | error |
|---|---|---|---|---|
| encrypted | office | `data/raw/share/共有ドライブ/プロジェクト/医療法人社団 恒一会 かえで総合病院/01.契約/契約書_pw-kaede20250902.docx` | derive password from filename/internal password rule and rerun extractor | `BadZipFile('File is not a zip file')` |

## 注意

- このキューは復号そのものは行わない。
- 復号済みコピーを作る場合は元ファイルを変更せず、一時ディレクトリまたは派生成果物として扱う。
