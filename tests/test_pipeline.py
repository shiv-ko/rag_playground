"""パイプラインのエンドツーエンドスモークテスト（API呼び出しなし）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluator.metrics import summarize
from src.generator.confidence_gate import ConfidenceGate
from src.indexer.keyword_store import KeywordStore
from src.indexer.vector_store import VectorStore
from src.models import CRAGLabel, Document, JudgeResult
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

    from src.evaluator.judge import LocalJudge
    from src.generator.answer_generator import AnswerGenerator

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


def test_style_extraction_intent_detection() -> None:
    """装飾文字列そのものを求める質問だけが抽出意図と判定される。"""
    from src.orchestrator.pipeline import is_style_extraction_request

    assert is_style_extraction_request("マーカーされている単語をすべて抜き出してください。")
    assert is_style_extraction_request("赤で強調されている箇所の文字列を抜き出してください。")
    assert is_style_extraction_request("太字で記載されている部分を抽出してください。")
    assert is_style_extraction_request("黄色でハイライトされている部分を全て抜き出してください。")
    # 「抽出条件」は名詞複合語であり抽出意図ではない（説明要求型）
    assert not is_style_extraction_request(
        "黄色ハイライトされている数値に対応するデータの抽出条件と集計内容を答えてください。"
    )
    assert not is_style_extraction_request("太字で強調されている項目は何を表していますか。")


def test_pipeline_office_style_explanation_request_not_answered_with_raw_strings(tmp_path: Path) -> None:
    """装飾文字列そのものを求めない質問（条件・集計内容の説明要求）はoffice_style直返ししない。"""
    from src.models import Answer
    from src.orchestrator.pipeline import Pipeline, QAPair

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "office_marks.jsonl").write_text(
        json.dumps({
            "source_path": "data/raw/x/基礎分析.pptx",
            "project_name": "テスト社",
            "file_name": "基礎分析.pptx",
            "slide_number": 3,
            "text": "4,675,000",
            "bold": True,
            "italic": False,
            "underline": False,
            "font_color": None,
            "fill_color": None,
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False, artifacts_dir=artifacts_dir)

    generate_calls: list[str] = []

    def _fake_generate(question, contexts):
        generate_calls.append(question)
        return Answer(text="LLM経由の回答", confidence=0.9)

    pipeline.generator.generate = _fake_generate
    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="7",
        question="テスト社の基礎分析.pptxで太字で強調されている数値に対応するデータの抽出条件と集計内容を答えてください。",
    ))

    assert generate_calls, "説明要求型は装飾文字列を直返しせずLLM生成へ渡す"
    assert result.answer == "LLM経由の回答"


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


def test_pipeline_routes_version_diff_question_through_structured_context(tmp_path: Path) -> None:
    """version_diffタグの質問は該当ペアのdiffを構造化コンテキストとしてLLMに渡す。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "version_diff_poc.jsonl").write_text(
        json.dumps({
            "project_name": "テスト社",
            "normalized_title": "提案書",
            "old_path": "data/raw/x/提案書_old.pptx",
            "new_path": "data/raw/x/提案書.pptx",
            "old_file_name": "提案書_old.pptx",
            "new_file_name": "提案書.pptx",
            "old_version_tag": "old",
            "new_version_tag": None,
            "status": "ok",
            "added_count": 0, "removed_count": 0, "changed_count": 1,
            "added_samples": [], "removed_samples": [],
            "changed_samples": [{"before": "料金体系：固定", "after": "料金体系：Time & Materials"}],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False, artifacts_dir=artifacts_dir)
    captured_contexts: list[str] = []

    def _fake_llm(question: str, context: str) -> str:
        captured_contexts.append(context)
        return json.dumps({
            "answer": "料金体系が固定からTime & Materialsに変更されました。",
            "confidence": 0.9,
            "citation": "料金体系：Time & Materials",
            "reasoning": "r",
        }, ensure_ascii=False)

    pipeline.generator._call_llm = _fake_llm

    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="0",
        question="テスト社の提案書old.pptxから提案書.pptxへの更新内容のうち、案件遂行に関連する実質的な変更を挙げてください。",
    ))

    assert captured_contexts and "料金体系：固定" in captured_contexts[0]
    assert "Time & Materials" in result.answer


def test_pipeline_prefers_version_diff_over_schedule_status_overmatch(tmp_path: Path) -> None:
    """xlsx新旧比較の質問（例:「スケジュール_r1.xlsxとスケジュール_r2.xlsxを比較したとき、
    未着手から完了への変更を除いて」）は version_diff タグと spreadsheet_state タグの両方が付く。
    schedule_tasksの「ステータス」列の値（未着手/完了）は一般的な語で質問文にそのまま含まれるため、
    spreadsheet_stateを先に試すと無関係な行が大量にヒットしてversion_diffへ辿り着けない
    （実データ実測: 44行 vs 正しいdiff1件）。version_diffを優先することを固定する回帰テスト。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    schedule_rows = [
        {
            "project_name": "テスト社",
            "sheet_name": "WBSタスク一覧",
            "source_path": "data/raw/x/スケジュール_r2.xlsx",
            "values": {"タスクID": f"T{i:02d}", "ステータス": "未着手" if i % 2 == 0 else "完了"},
        }
        for i in range(20)
    ]
    (artifacts_dir / "schedule_tasks.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in schedule_rows), encoding="utf-8",
    )
    (artifacts_dir / "version_diff_poc.jsonl").write_text(
        json.dumps({
            "project_name": "テスト社",
            "normalized_title": "スケジュール",
            "old_path": "data/raw/x/スケジュール_r1.xlsx",
            "new_path": "data/raw/x/スケジュール_r2.xlsx",
            "old_file_name": "スケジュール_r1.xlsx",
            "new_file_name": "スケジュール_r2.xlsx",
            "old_version_tag": "r1",
            "new_version_tag": "r2",
            "status": "ok",
            "added_count": 0, "removed_count": 0, "changed_count": 1,
            "added_samples": [], "removed_samples": [],
            "changed_samples": [{"before": "担当: 鈴木", "after": "担当: 高橋"}],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False, artifacts_dir=artifacts_dir)
    captured_contexts: list[str] = []

    def _fake_llm(question: str, context: str) -> str:
        captured_contexts.append(context)
        return json.dumps({
            "answer": "担当が鈴木から高橋に変更されました。",
            "confidence": 0.9,
            "citation": "担当: 高橋",
            "reasoning": "r",
        }, ensure_ascii=False)

    pipeline.generator._call_llm = _fake_llm
    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="0",
        question="テスト社のスケジュール_r1.xlsxとスケジュール_r2.xlsxを比較したとき、"
                 "未着手から完了への変更を除いて、案件遂行に関連する変更点を挙げてください。",
    ))

    assert captured_contexts and "担当: 鈴木" in captured_contexts[0]
    assert "T00" not in captured_contexts[0]
    assert "高橋" in result.answer


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

def test_save_results_without_judge_does_not_crash(tmp_path: Path) -> None:
    """run_judge=False（--no-judge診断run）でもsave_resultsが落ちず、診断フィールドは保存される。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.txt").write_text("宿泊費の上限は15,000円です。", encoding="utf-8")

    pipeline = Pipeline(data_dir=data_dir, run_judge=False)
    pipeline.generator._call_llm = (
        lambda q, c: '{"answer": "15,000円", "confidence": 0.9, "reasoning": "r"}'
    )
    pipeline.build_index()

    results = pipeline.run([QAPair(question_id="0", question="宿泊費の上限は？")])

    out_dir = tmp_path / "out"
    pipeline.save_results(results, out_dir, run_name="nojudge")

    payload = json.loads(next(out_dir.glob("nojudge_*.json")).read_text(encoding="utf-8"))
    assert payload["summary"]["mean_score"] is None
    assert payload["summary"]["total"] == 1
    result0 = payload["results"][0]
    assert "gate_reason" in result0
    assert "retrieved_sources" in result0
