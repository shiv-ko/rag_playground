---
name: experiments
description: 実験管理・データ到着後の手順・未確定事項を確認したいとき
---

## 実験管理

`experiments/run_<timestamp>.json` に保存される内容:
- `summary`: mean_score / total / label_counts
- `results`: 質問ごとの回答・確信度・judge_label

```bash
# 集計・Incorrect 抽出
.venv/bin/python scripts/run_eval.py
```

## ベースライン確立の手順（詳細は `docs/todo_and_experiments.md`）

1. `data/raw/` にデータを配置（済・`docs/dataset_overview.md` 参照）
2. Parser実装を実データに合わせて調整（`src/parsers/`、ノイズ除外込み）
3. BM25索引ビルド＋案件フォルダ絞り込み検索（ベクトル検索はバックログ送り）
4. `_call_llm()` を Claude API に差し替え（generator + judge）
5. `scripts/run_pipeline.py --data-dir data/raw` でE2Eを回す
6. ローカルJudgeでスコアを確認 → 失敗ケース分析 → 改善ループ

## 未確定事項

- ベクトル検索バックエンド (Chroma / FAISS) ※ベースライン後の実験バックログで選定
- 埋め込みモデル（Claude / OpenAI / ローカル）
- PDF/Office/画像の具体的パーサーライブラリ（pypdf / python-docx / pptx / pillow）

提出フォーマットは確定済み → `docs/submission.md` 参照
