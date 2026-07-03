---
name: dev-process
description: 実装・テスト・レビューの進め方を確認したいとき（TDD・並列エージェント・完了基準）
---

## TDD ルール（厳守）

本番差し替え時（Claude API接続・実パーサー・ベクトル検索）は必ずこの順序:

1. `tests/test_<対象>.py` にテストを書く
2. `.venv/bin/pytest tests/test_<対象>.py -v` → **失敗を確認する**
3. 最小限の実装でテストを通す
4. `.venv/bin/pytest tests/ -v` → 全94件以上が通ることを確認
5. 失敗→通過の出力を完了報告に貼る

サブクラスパターン（LLM呼び出しを排除してテストを決定的にする）:
```python
class FakeGenerator(AnswerGenerator):
    def _call_llm(self, question, context):
        return '{"answer": "テスト回答", "confidence": 0.9, "reasoning": "..."}'
```

## 並列エージェント

Parser / Indexer / Generator / Judge は独立しているため、実装タスクは4エージェントに分散する。  
共有状態（同じファイルを同時編集）がある場合は順次実行に切り替える。

## 完了報告の条件

「実装しました」で終わらせない。  
必ず `.venv/bin/pytest tests/ -v` の出力全体を貼ること。
