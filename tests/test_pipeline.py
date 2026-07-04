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


def test_pipeline_routes_office_style_question_through_structured_context(tmp_path: Path) -> None:
    """office_styleタグの質問は構造化コンテキストを使う。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "office_marks.jsonl").write_text(
        json.dumps({
            "source_path": "data/raw/x/提案書.pptx",
            "project_name": "テスト社",
            "file_name": "提案書.pptx",
            "slide_number": 1,
            "text": "太字の重要事項",
            "bold": True,
            "italic": False,
            "underline": False,
            "font_color": None,
            "fill_color": None,
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False, artifacts_dir=artifacts_dir)
    pipeline.generator._call_llm = lambda q, c: json.dumps({
        "answer": "太字の重要事項",
        "confidence": 0.9,
        "citation": "太字の重要事項",
        "reasoning": "r",
    })

    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(
        QAPair(question_id="0", question="太字で記載されている箇所を抽出してください。案件はテスト社です。")
    )

    assert "太字の重要事項" in result.answer


def test_pipeline_answers_single_office_style_match_without_llm_refusal(tmp_path: Path) -> None:
    """office_styleはartifactで抽出済みの文字列を返せるため、LLM拒否でMissingにしない。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "office_marks.jsonl").write_text(
        json.dumps({
            "source_path": "data/raw/x/提案書.pptx",
            "project_name": "テスト社",
            "file_name": "提案書.pptx",
            "extension": ".pptx",
            "slide_number": 7,
            "text": "1. データ理解・EDA",
            "bold": True,
            "italic": False,
            "underline": False,
            "font_color": "FFFFFF",
            "fill_color": "A23B2C",
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False, artifacts_dir=artifacts_dir)

    def _boom(question, contexts):
        raise AssertionError("office_styleの単一構造化抽出はLLMに委ねない")

    pipeline.generator.generate = _boom
    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="25",
        question="テスト社の提案書P7において、赤で強調されている箇所の文字列を抜き出してください。",
    ))

    assert result.answer == "1. データ理解・EDA"


def test_pipeline_routes_spreadsheet_calc_question_to_calc_answerer(tmp_path: Path) -> None:
    """spreadsheet_calcタグの質問はSpreadsheetCalcAnswererへ渡る。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    csv_dir = tmp_path / "data" / "raw" / "share" / "共有ドライブ" / "プロジェクト" / "テスト社" / "03.データ"
    csv_dir.mkdir(parents=True)
    (csv_dir / "train.csv").write_text("term,loan_amnt\n3 years,1000\n3 years,2000\n", encoding="utf-8")

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False)

    def _boom(question, contexts):
        raise AssertionError("spreadsheet_calcは通常のgenerate()を使ってはいけない")

    pipeline.generator.generate = _boom
    pipeline.spreadsheet_calc_answerer._call_llm = lambda q, cols: json.dumps({
        "filters": [{"column": "term", "op": "==", "value": "3 years"}],
        "target_column": "loan_amnt",
        "aggregation": "mean",
        "round_to": 0,
    })

    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="0",
        question="テスト社のtrain.csvにおいて、term=3 yearsの中でloan_amntの平均を算出してください。",
    ))

    assert "1500" in result.answer


def test_pipeline_falls_through_to_spreadsheet_state_when_office_style_has_no_match(tmp_path: Path) -> None:
    """「黄色ハイライトされている」等の質問はoffice_styleタグも付くが、
    office_marksに該当が無ければspreadsheet_stateパスを試す（elifで排他にしない）。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "train_xlsx_highlight_blocks.jsonl").write_text(
        json.dumps({
            "source_path": "data/raw/x/train.xlsx",
            "project_name": "テスト社",
            "sheet_name": "Pivot",
            "range": "F22",
            "fill_color_name": "yellow",
            "first_value": "35.95",
            "column_header": {"cell": "F3", "value": "平均 / bmi", "formula": None},
            "same_row_values": [{"cell": "E22", "value": "39", "formula": None}],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False, artifacts_dir=artifacts_dir)
    captured_contexts: list[str] = []

    def _fake_llm(question: str, context: str) -> str:
        captured_contexts.append(context)
        return json.dumps({
            "answer": "列見出し「平均 / bmi」のF22セル（値35.95）です。",
            "confidence": 0.9,
            "citation": "平均 / bmi",
            "reasoning": "r",
        }, ensure_ascii=False)

    pipeline.generator._call_llm = _fake_llm

    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="0",
        question="テスト社のtrain.xlsxのPivotシートで黄色ハイライトされているセルの抽出条件を教えてください。",
    ))

    assert captured_contexts and "平均 / bmi" in captured_contexts[0]
    assert "平均 / bmi" in result.answer


def test_pipeline_prefers_spreadsheet_state_for_xlsx_questions_over_office_marks(tmp_path: Path) -> None:
    """xlsx系の手がかり（.xlsx/シート/セル）がある質問では、同じ案件のpptx/docxの
    ハイライトrunではなくspreadsheet_state側のコンテキストを使う。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "office_marks.jsonl").write_text(
        json.dumps({
            "source_path": "data/raw/x/提案書.pptx",
            "project_name": "テスト社",
            "file_name": "提案書.pptx",
            "slide_number": 1,
            "text": "無関係な黄色ハイライトのスライド文言",
            "bold": False,
            "italic": False,
            "underline": False,
            "font_color": None,
            "fill_color": "FFFF00",
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (artifacts_dir / "train_xlsx_highlight_blocks.jsonl").write_text(
        json.dumps({
            "source_path": "data/raw/x/train.xlsx",
            "project_name": "テスト社",
            "sheet_name": "Pivot",
            "range": "F22",
            "fill_color_name": "yellow",
            "first_value": "35.95",
            "column_header": {"cell": "F3", "value": "平均 / bmi", "formula": None},
            "same_row_values": [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False, artifacts_dir=artifacts_dir)
    captured_contexts: list[str] = []

    def _fake_llm(question: str, context: str) -> str:
        captured_contexts.append(context)
        return json.dumps({
            "answer": "F22", "confidence": 0.9, "citation": "F22", "reasoning": "r",
        }, ensure_ascii=False)

    pipeline.generator._call_llm = _fake_llm

    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    pipeline._process_one(QAPair(
        question_id="0",
        question="テスト社のtrain.xlsxのPivotシートで黄色ハイライトされているセルの抽出条件を教えてください。",
    ))

    assert captured_contexts
    assert "平均 / bmi" in captured_contexts[0]
    assert "無関係な黄色ハイライトのスライド文言" not in captured_contexts[0]


def test_pipeline_falls_through_to_state_when_calc_has_no_train_csv(tmp_path: Path) -> None:
    """spreadsheet_calcとspreadsheet_stateの両タグが付く質問（例: Pivotの「平均が最も高い」）で、
    train.csvが無い場合はcalc分岐で離脱せずspreadsheet_stateビルダーへ委ねる（実測valid Q6/Q21の死にパス）。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    cells = [
        {"source_path": "data/raw/x/train.xlsx", "project_name": "テスト社",
         "file_name": "train.xlsx", "sheet_name": "Pivot", "cell": "A3", "row": 3, "value": "層"},
        {"source_path": "data/raw/x/train.xlsx", "project_name": "テスト社",
         "file_name": "train.xlsx", "sheet_name": "Pivot", "cell": "B3", "row": 3, "value": "平均 / bmi"},
        {"source_path": "data/raw/x/train.xlsx", "project_name": "テスト社",
         "file_name": "train.xlsx", "sheet_name": "Pivot", "cell": "A4", "row": 4, "value": "20代"},
        {"source_path": "data/raw/x/train.xlsx", "project_name": "テスト社",
         "file_name": "train.xlsx", "sheet_name": "Pivot", "cell": "B4", "row": 4, "value": "10.5"},
        {"source_path": "data/raw/x/train.xlsx", "project_name": "テスト社",
         "file_name": "train.xlsx", "sheet_name": "Pivot", "cell": "A5", "row": 5, "value": "30代"},
        {"source_path": "data/raw/x/train.xlsx", "project_name": "テスト社",
         "file_name": "train.xlsx", "sheet_name": "Pivot", "cell": "B5", "row": 5, "value": "99.9"},
    ]
    (artifacts_dir / "train_xlsx_small_sheet_cells.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in cells), encoding="utf-8",
    )

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False, artifacts_dir=artifacts_dir)
    captured_contexts: list[str] = []

    def _fake_llm(question: str, context: str) -> str:
        captured_contexts.append(context)
        return json.dumps({
            "answer": "30代",
            "confidence": 0.9,
            "citation": "30代",
            "reasoning": "r",
        }, ensure_ascii=False)

    pipeline.generator._call_llm = _fake_llm

    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="0",
        question="テスト社のtrain.xlsxのPivotシートで、bmiの平均が最も高い層の抽出条件を教えてください。",
    ))

    # train.csvが無くてもstateビルダーのargmax行docが生成器に渡ること
    assert captured_contexts and "30代" in captured_contexts[0] and "99.9" in captured_contexts[0]
    assert result.answer == "30代"


def test_pipeline_falls_back_to_search_when_calc_answer_is_gated(tmp_path: Path) -> None:
    """spreadsheet_calcパスがspecを解釈できずゲートした場合、Missing固定にせず
    通常のBM25検索パスへフォールバックする。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    csv_dir = tmp_path / "data" / "raw" / "share" / "共有ドライブ" / "プロジェクト" / "テスト社" / "03.データ"
    csv_dir.mkdir(parents=True)
    (csv_dir / "train.csv").write_text("term,loan_amnt\n3 years,1000\n", encoding="utf-8")

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False)
    pipeline.spreadsheet_calc_answerer._call_llm = lambda q, cols: "not json"
    pipeline.generator._call_llm = lambda q, c: json.dumps({
        "answer": "通常パスの回答", "confidence": 0.9,
        "citation": "宿泊費の上限は15,000円です", "reasoning": "r",
    }, ensure_ascii=False)

    # 案件スコープ検索で拾われるよう、テキストもテスト社のフォルダ内に置く
    (csv_dir / "旅費規程.txt").write_text("宿泊費の上限は15,000円です。", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="0",
        question="テスト社のtrain.csvにおいて、宿泊費の平均を算出してください。",
    ))

    assert result.answer == "通常パスの回答"


def test_load_train_csv_does_not_fall_back_to_other_projects_csv(tmp_path: Path) -> None:
    """案件名にマッチしないtrain.csvは、全体で1つしか無くても使わない
    （別案件のデータで計算した数値はIncorrect直行のため）。"""
    from src.orchestrator.pipeline import Pipeline

    csv_dir = tmp_path / "data" / "raw" / "share" / "共有ドライブ" / "プロジェクト" / "別社" / "03.データ"
    csv_dir.mkdir(parents=True)
    (csv_dir / "train.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False)

    assert pipeline._load_train_csv("テスト社") is None
    assert pipeline._load_train_csv("別社") is not None

def test_pipeline_result_has_diagnostics(tmp_path: Path) -> None:
    """runの結果に raw_answer / retrieved_sources が入り、summaryに時間・トークンが入る。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.txt").write_text("宿泊費の上限は15,000円です。", encoding="utf-8")

    pipeline = Pipeline(data_dir=data_dir, run_judge=True)
    pipeline.generator._call_llm = (
        lambda q, c: '{"answer": "5万円です。", "confidence": 0.9, "reasoning": "r"}'
    )
    pipeline.judge._call_llm = lambda p: '{"label": "Perfect", "reason": "ok"}'
    pipeline.build_index()

    results = pipeline.run([QAPair(question_id="0", question="宿泊費の上限は？")])

    out_dir = tmp_path / "out"
    pipeline.save_results(results, out_dir, run_name="diag")

    out_file = next(out_dir.glob("diag_*.json"))
    payload = json.loads(out_file.read_text(encoding="utf-8"))

    result0 = payload["results"][0]
    assert "raw_answer" in result0
    assert "retrieved_sources" in result0
    assert "gate_reason" in result0
    for source in result0["retrieved_sources"]:
        assert "::" in source

    summary = payload["summary"]
    assert "elapsed_seconds" in summary
    assert "generator_tokens" in summary
    assert "judge_tokens" in summary
    assert "models" in summary
