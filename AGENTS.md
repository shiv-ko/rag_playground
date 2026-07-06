# RAG Competition

- **セッション開始時はまず** `vault.md` **を読む**（計画・作業ログ・成果物の場所と最新状態の探し方）
- venv: `.venv/bin/python`
- テスト: `.venv/bin/pytest tests/ -v`
- 実行: `.venv/bin/python scripts/run_pipeline.py`
- データ: `data/raw/` に置くだけでパイプラインが動く（gitignore対象）
- **コンペ概要・ルール**: コンペティションの詳細（評価基準、禁止事項など）については `competition.md` を参照。
- **絶対制約: 回答は1000トークン以内**（超過はエラー）
- コンペ開始: 2026/7/3 12:00（本番データはその時に公開）

Skills: architecture / scoring / dev-process / experiments / step-review / reviewing-pipeline-stages