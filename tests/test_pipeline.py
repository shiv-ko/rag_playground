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


def test_e2e_stub(tmp_path: Path, sample_docs: list[Document]) -> None:
    """スタブ実装でパイプライン全体が通ることを確認する。"""
    from src.generator.answer_generator import AnswerGenerator
    from src.evaluator.judge import LocalJudge

    retriever = HybridRetriever()
    retriever.add(sample_docs)

    generator = AnswerGenerator(threshold=0.4)
    judge = LocalJudge()

    question = "宿泊費の上限は？"
    contexts = retriever.search(question, top_k=3)
    answer = generator.generate(question, contexts)
    result = judge.score(question, answer.text, contexts[0].document.text if contexts else "")

    assert answer.text != ""
    assert result.label in CRAGLabel
