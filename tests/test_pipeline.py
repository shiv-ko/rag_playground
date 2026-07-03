"""パイプラインのエンドツーエンドスモークテスト（API呼び出しなし）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models import CRAGLabel, Document, JudgeResult, ScoredDocument
from src.evaluator.metrics import summarize
from src.generator.confidence_gate import ConfidenceGate
from src.indexer.keyword_store import KeywordStore
from src.indexer.vector_store import VectorStore
from src.retriever.hybrid_retriever import HybridRetriever


@pytest.fixture
def sample_docs(tmp_path: Path) -> list[Document]:
    return [
        Document(text="宿泊費の上限は15,000円です。東京は20,000円。", source_path=tmp_path / "a.txt"),
        Document(text="交通費は1回10,000円まで精算できます。", source_path=tmp_path / "b.txt"),
        Document(text="Model Xのバッテリーは18時間持続します。", source_path=tmp_path / "c.txt"),
    ]


def test_keyword_store(sample_docs: list[Document]) -> None:
    store = KeywordStore()
    store.add(sample_docs)
    results = store.search("宿泊費 上限", top_k=2)
    assert len(results) > 0
    assert results[0].score > 0


def test_vector_store(sample_docs: list[Document]) -> None:
    store = VectorStore()
    store.add(sample_docs)
    results = store.search("宿泊費", top_k=2)
    assert len(results) > 0


def test_hybrid_retriever(sample_docs: list[Document]) -> None:
    retriever = HybridRetriever()
    retriever.add(sample_docs)
    results = retriever.search("交通費 精算", top_k=2)
    assert len(results) > 0


def test_confidence_gate() -> None:
    gate = ConfidenceGate(threshold=0.4)
    assert gate.should_answer(0.8)
    assert not gate.should_answer(0.2)
    assert gate.missing_text() != ""


def test_metrics_summarize() -> None:
    results = [
        JudgeResult(label=CRAGLabel.PERFECT, reason="ok"),
        JudgeResult(label=CRAGLabel.PERFECT, reason="ok"),
        JudgeResult(label=CRAGLabel.MISSING, reason="no answer"),
        JudgeResult(label=CRAGLabel.INCORRECT, reason="wrong"),
    ]
    summary = summarize(results)
    assert summary.total == 4
    assert abs(summary.mean_score - (1 + 1 + 0 - 1) / 4) < 1e-9
    assert summary.label_counts["Perfect"] == 2


def test_pipeline_uses_project_scoped_retriever(tmp_path: Path) -> None:
    """PipelineはHybridRetrieverではなくProjectScopedRetrieverを使う（ベースライン方針）。"""
    from src.orchestrator.pipeline import Pipeline
    from src.retriever.project_scoped_retriever import ProjectScopedRetriever

    pipeline = Pipeline(data_dir=tmp_path)
    assert isinstance(pipeline.retriever, ProjectScopedRetriever)


def test_e2e_stub(tmp_path: Path, sample_docs: list[Document], monkeypatch) -> None:
    """パイプライン全体が通ることを確認する（Anthropic APIはモック）。"""
    from unittest.mock import patch
    from src.generator.answer_generator import AnswerGenerator
    from src.evaluator.judge import LocalJudge

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("CLAUDE_JUDGE_MODEL", "claude-sonnet-5")

    retriever = HybridRetriever()
    retriever.add(sample_docs)

    generator = AnswerGenerator(threshold=0.4)
    judge = LocalJudge()

    question = "宿泊費の上限は？"
    contexts = retriever.search(question, top_k=3)

    fake_content = type("C", (), {"text": '{"answer": "5万円です。", "confidence": 0.9, "reasoning": "r"}'})()
    fake_response = type("R", (), {"content": [fake_content]})()

    with patch("src.generator.answer_generator.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = fake_response
        answer = generator.generate(question, contexts)

    fake_judge_content = type("C", (), {"text": '{"label": "Perfect", "reason": "r"}'})()
    fake_judge_response = type("R", (), {"content": [fake_judge_content]})()

    with patch("src.evaluator.judge.Anthropic") as MockJudgeAnthropic:
        MockJudgeAnthropic.return_value.messages.create.return_value = fake_judge_response
        result = judge.score(question, answer.text, contexts[0].document.text if contexts else "")

    assert answer.text != ""
    assert result.label in CRAGLabel


def test_pipeline_skips_judge_when_run_judge_false(tmp_path: Path) -> None:
    """run_judge=False のとき judge_label は空文字で、Judge._call_llmは呼ばれない"""
    from unittest.mock import MagicMock
    from src.orchestrator.pipeline import Pipeline, QAPair

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False)
    pipeline.judge._call_llm = MagicMock(return_value='{"label": "Perfect", "reason": "r"}')
    pipeline.generator._call_llm = lambda q, c: '{"answer": "回答", "confidence": 0.9, "reasoning": "r"}'

    (tmp_path / "a.txt").write_text("参考テキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(question_id="0", question="質問"))

    assert result.judge_label == ""
    pipeline.judge._call_llm.assert_not_called()


def test_pipeline_expands_search_query_with_term_registry(tmp_path: Path) -> None:
    """term_registryが渡されると検索クエリに用語展開が反映される。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    pipeline = Pipeline(
        data_dir=tmp_path,
        run_judge=False,
        term_registry=[{"term": "TG", "expansion": "目的変数", "note": "Target"}],
    )
    pipeline.generator._call_llm = (
        lambda q, c: '{"answer": "回答", "confidence": 0.9, "citation": "", "reasoning": "r"}'
    )

    captured_queries: list[str] = []
    original_search = pipeline.retriever.search

    def _spy_search(query: str, top_k: int = 5):
        captured_queries.append(query)
        return original_search(query, top_k=top_k)

    pipeline.retriever.search = _spy_search

    (tmp_path / "a.txt").write_text("目的変数についての説明です。", encoding="utf-8")
    pipeline.build_index()

    pipeline._process_one(QAPair(question_id="0", question="TGの定義は？"))

    assert captured_queries == ["TGの定義は？ 目的変数"]
