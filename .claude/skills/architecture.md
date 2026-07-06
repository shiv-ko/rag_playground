---
name: architecture
description: パイプライン構成・コンポーネントの役割・スタブ/本番接続の状態を確認したいとき
---

> 本表は執筆時点（2026-07-05, commit 38882c6 ごろ）のスナップショット。
> **実際の `src/` と食い違ったら `src/` が正**。作業前に `ls src/` と対象ディレクトリを必ず確認する。

## パイプライン（`scripts/run_pipeline.py` / 提出は `scripts/make_predictions.py`）

```
ParserDispatcher（.cache/ にパース結果キャッシュ）
  → ProjectScopedRetriever（案件名検出→案件フォルダ絞り込み＋BM25。未検出時は全体BM25）
      ＋ QueryExpander / question_file_scope（質問中のファイル名でスコープ）
  → 構造化コンテキスト（structured_context: spreadsheet_state / office_style）
      スプレッドシート集計質問は SpreadsheetCalcAnswerer が直答を試みる
  → AnswerGenerator（Claude API）
  → enumeration_gate / citation_check / ConfidenceGate（confidence < 0.4 → Missing）
  → LocalJudge（CRAG, Claude API）
提出時: make_predictions.py が複数run → answer_stabilizer（多数決）で回答を安定化
```

## ステージ一覧（src/ 全8ディレクトリ — レビューや調査はこの単位で漏れなく）

| ステージ | ディレクトリ | 主なファイルと役割 |
|---|---|---|
| パース | `src/parsers/` | `dispatcher.py`（拡張子振り分け）、`chunker.py`、pdf/office/notebook/text/image の各パーサー、`pivot_cache.py` |
| インデックス | `src/indexer/` | `keyword_store.py`（BM25/TF-IDF、CJKバイグラム）、`vector_store.py` |
| 検索 | `src/retriever/` | `project_scoped_retriever.py`、`query_expander.py`、`question_file_scope.py`、`structured_context.py`、`hybrid_retriever.py` |
| 生成 | `src/generator/` | `answer_generator.py`、`spreadsheet_calc.py`（構造化集計の直答）、`enumeration_gate.py`、`citation_check.py`、`confidence_gate.py`、`color_names.py` |
| 評価 | `src/evaluator/` | `judge.py`（ローカルCRAGジャッジ）、`openai_judge.py`、`majority.py`、`metrics.py`、`triage.py`、`flip.py`、`ground_truth.py`、`retrieval_eval.py` |
| 構造化データ | `src/structured/` | `artifact_store.py`（artifacts/ のレジストリ・jsonl読み込み） |
| オーケストレーション | `src/orchestrator/` | `pipeline.py`（E2E非同期ループ本体）、`answer_stabilizer.py`（複数run多数決） |
| 共通基盤 | `src/utils/` | `question_classifier.py`、`question_loader.py`、`glossary.py`、`parse_cache.py`、`parallel.py`、`paths.py`、`logging.py` |

## スタブ/本番接続の状態

| 箇所 | 状態 |
|---|---|
| `src/generator/answer_generator.py` `_call_llm()` | **Claude API 接続済み** |
| `src/evaluator/judge.py` `_call_llm()` | **Claude API 接続済み**（モデルは `CLAUDE_JUDGE_MODEL`） |
| `src/evaluator/openai_judge.py` | 本番ジャッジ互換のローカル検証用 |
| `src/parsers/image_parser.py` `parse()` | スタブのまま（ファイル名のみ返す。VLM未接続） |
| `src/indexer/vector_store.py` `_embed()` | 疑似埋め込みのまま（BM25が主。ベクトルはバックログ） |

差し替えルール: インターフェース（`can_handle/parse`, `add/search/clear`, `_call_llm`）を守れば中身は何でも良い。
