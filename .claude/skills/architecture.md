---
name: architecture
description: パイプライン構成・コンポーネントの役割・本番差し替えポイントを確認したいとき
---

## パイプライン

```
ParserDispatcher → ProjectScopedRetriever(BM25) → AnswerGenerator → ConfidenceGate
                                                                            ↓
                                                                     LocalJudge (CRAG)
```

## コンポーネント

| レイヤー | ファイル | 役割 |
|---|---|---|
| Parser | `src/parsers/dispatcher.py` | 拡張子で振り分け |
| Indexer | `src/indexer/keyword_store.py` | BM25/TF-IDF（CJKバイグラム対応） |
| Indexer | `src/indexer/vector_store.py` | コサイン類似度（疑似埋め込み） |
| Retriever | `src/retriever/project_scoped_retriever.py` | 質問文から案件名検出→案件フォルダ絞り込み＋BM25（未検出時は全体BM25にフォールバック） |
| Generator | `src/generator/answer_generator.py` | スタブ → Claude API に差し替え |
| Gate | `src/generator/confidence_gate.py` | confidence < 0.4 → Missing |
| Judge | `src/evaluator/judge.py` | スタブ → Claude API に差し替え |

## 本番差し替えポイント

| ファイル | メソッド | やること |
|---|---|---|
| `src/generator/answer_generator.py` | `_call_llm()` | Claude API で回答生成 |
| `src/evaluator/judge.py` | `_call_llm()` | Claude API でCRAGジャッジ |
| `src/parsers/image_parser.py` | `parse()` | Claude VLM で画像キャプション |
| `src/indexer/vector_store.py` | `_embed()` | 埋め込みAPI + Chroma/FAISS |

差し替えルール: インターフェース（`can_handle/parse`, `add/search/clear`, `_call_llm`）を守れば中身は何でも良い。
