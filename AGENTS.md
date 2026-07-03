# RAG Competition

- venv: `.venv/bin/python`
- テスト: `.venv/bin/pytest tests/ -v`
- 実行: `.venv/bin/python scripts/run_pipeline.py`
- データ: `data/raw/` に置くだけでパイプラインが動く（gitignore対象）
- **コンペ概要・ルール**: コンペティションの詳細（評価基準、禁止事項など）については `competition.md` を参照。
- **絶対制約: 回答は1000トークン以内**（超過はエラー）
- コンペ開始: 2026/7/3 12:00（本番データはその時に公開）

Skills: architecture / scoring / dev-process / experiments

## 構造化artifactsの再生成（新しい案件データが来たら必須）

`artifacts/*.jsonl` は `data/raw` の実データから機械的に生成されるファイルで、
構造化回答パス（spreadsheet_state / office_style / spreadsheet_calc）が静的に読み込む。
**`data/raw` を差し替えたら以下を順に実行して再生成すること**（全て決定的・API不使用）:

```bash
.venv/bin/python scripts/build_registries.py            # project/term registry（社内用語集.docxから）
.venv/bin/python scripts/extract_spreadsheets.py        # xlsxセル・シート・スケジュール行
.venv/bin/python scripts/scan_train_xlsx_xml.py         # 壊れたtrain.xlsxのXML直接スキャン
.venv/bin/python scripts/build_train_xlsx_highlight_context.py  # ハイライトブロック＋周辺文脈
.venv/bin/python scripts/extract_office_marks.py        # docx/pptxの装飾run
```

再生成後は `.venv/bin/pytest tests/ -v` と少数の実データスモーク
（`StructuredArtifactStore.from_artifacts_dir(Path('artifacts'))` で件数確認）を行うこと。