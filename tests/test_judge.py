"""Judge コンポーネントの TDD テスト。

テスト対象:
- src/models.py の CRAGLabel, JudgeResult
- src/evaluator/judge.py の LocalJudge._parse, LocalJudge.score
- src/evaluator/metrics.py の summarize, EvalSummary.report
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.models import CRAGLabel, JudgeResult
from src.evaluator.judge import LocalJudge
from src.evaluator.metrics import EvalSummary, summarize


# ---------------------------------------------------------------------------
# CRAGLabel のテスト
# ---------------------------------------------------------------------------


class TestCRAGLabelScore:
    def test_perfect_score_is_1(self) -> None:
        assert CRAGLabel.PERFECT.score == 1.0

    def test_acceptable_score_is_0_5(self) -> None:
        assert CRAGLabel.ACCEPTABLE.score == 0.5

    def test_missing_score_is_0(self) -> None:
        assert CRAGLabel.MISSING.score == 0.0

    def test_incorrect_score_is_minus_1(self) -> None:
        assert CRAGLabel.INCORRECT.score == -1.0

    def test_label_can_be_constructed_from_string(self) -> None:
        assert CRAGLabel("Perfect") == CRAGLabel.PERFECT

    def test_acceptable_can_be_constructed_from_string(self) -> None:
        assert CRAGLabel("Acceptable") == CRAGLabel.ACCEPTABLE

    def test_missing_can_be_constructed_from_string(self) -> None:
        assert CRAGLabel("Missing") == CRAGLabel.MISSING

    def test_incorrect_can_be_constructed_from_string(self) -> None:
        assert CRAGLabel("Incorrect") == CRAGLabel.INCORRECT


# ---------------------------------------------------------------------------
# JudgeResult のテスト
# ---------------------------------------------------------------------------


class TestJudgeResult:
    def test_label_and_reason_are_set_correctly(self) -> None:
        result = JudgeResult(label=CRAGLabel.PERFECT, reason="正確な回答")
        assert result.label == CRAGLabel.PERFECT
        assert result.reason == "正確な回答"

    def test_score_matches_label_score_for_perfect(self) -> None:
        result = JudgeResult(label=CRAGLabel.PERFECT, reason="ok")
        assert result.score == CRAGLabel.PERFECT.score

    def test_score_matches_label_score_for_acceptable(self) -> None:
        result = JudgeResult(label=CRAGLabel.ACCEPTABLE, reason="ok")
        assert result.score == CRAGLabel.ACCEPTABLE.score

    def test_score_matches_label_score_for_missing(self) -> None:
        result = JudgeResult(label=CRAGLabel.MISSING, reason="no answer")
        assert result.score == CRAGLabel.MISSING.score

    def test_score_matches_label_score_for_incorrect(self) -> None:
        result = JudgeResult(label=CRAGLabel.INCORRECT, reason="wrong")
        assert result.score == CRAGLabel.INCORRECT.score

    def test_score_is_set_automatically_via_post_init(self) -> None:
        """score は __post_init__ で自動設定されるため init では指定しない。"""
        result = JudgeResult(label=CRAGLabel.INCORRECT, reason="誤り")
        assert result.score == -1.0


# ---------------------------------------------------------------------------
# LocalJudge._parse のテスト（内部メソッド）
# ---------------------------------------------------------------------------


class TestLocalJudgeParse:
    def setup_method(self) -> None:
        self.judge = LocalJudge()

    def test_parse_perfect_label(self) -> None:
        raw = '{"label": "Perfect", "reason": "正確"}'
        result = self.judge._parse(raw)
        assert result.label == CRAGLabel.PERFECT
        assert result.reason == "正確"

    def test_parse_acceptable_label(self) -> None:
        raw = '{"label": "Acceptable", "reason": "概ね正確"}'
        result = self.judge._parse(raw)
        assert result.label == CRAGLabel.ACCEPTABLE
        assert result.reason == "概ね正確"

    def test_parse_missing_label(self) -> None:
        raw = '{"label": "Missing", "reason": "回答なし"}'
        result = self.judge._parse(raw)
        assert result.label == CRAGLabel.MISSING
        assert result.reason == "回答なし"

    def test_parse_incorrect_label(self) -> None:
        raw = '{"label": "Incorrect", "reason": "誤り"}'
        result = self.judge._parse(raw)
        assert result.label == CRAGLabel.INCORRECT
        assert result.reason == "誤り"

    def test_invalid_json_falls_back_to_missing(self) -> None:
        raw = "これは不正なJSONです"
        result = self.judge._parse(raw)
        assert result.label == CRAGLabel.MISSING

    def test_invalid_json_does_not_raise_exception(self) -> None:
        raw = "not json at all {broken"
        # 例外を投げずに Missing を返すことを確認
        result = self.judge._parse(raw)
        assert result.label == CRAGLabel.MISSING

    def test_parse_json_surrounded_by_text(self) -> None:
        """JSON の前後にテキストがあっても正しくパースできる。"""
        raw = 'この回答を評価します。\n{"label": "Perfect", "reason": "正確"}\n以上です。'
        result = self.judge._parse(raw)
        assert result.label == CRAGLabel.PERFECT

    def test_parse_json_with_markdown_fences(self) -> None:
        """LLM が markdown コードブロックで返す場合でもパースできる。"""
        raw = '```json\n{"label": "Acceptable", "reason": "おおよそ正確"}\n```'
        result = self.judge._parse(raw)
        assert result.label == CRAGLabel.ACCEPTABLE


# ---------------------------------------------------------------------------
# LocalJudge.score のテスト（FakeJudge による振る舞いテスト）
# ---------------------------------------------------------------------------


class FakeJudge(LocalJudge):
    """_call_llm をオーバーライドして任意の応答を返すテスト用サブクラス。"""

    def __init__(self, fake_response: str) -> None:
        self.fake_response = fake_response

    def _call_llm(self, prompt: str) -> str:
        return self.fake_response


class RecordingJudge(FakeJudge):
    def _call_llm(self, prompt: str) -> str:
        self.prompt = prompt
        return super()._call_llm(prompt)


class SequenceJudge(LocalJudge):
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = iter(responses)
        self.call_count = 0

    def _call_llm(self, prompt: str) -> str:
        self.call_count += 1
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class TestLocalJudgeScore:
    def test_score_retries_once_after_parse_error(self) -> None:
        judge = SequenceJudge(
            ["invalid", '{"label": "Perfect", "reason": "retry success"}']
        )

        result = judge.score("質問", "回答", "正解")

        assert result.label == CRAGLabel.PERFECT
        assert judge.call_count == 2

    def test_score_returns_missing_when_retry_also_has_parse_error(self) -> None:
        judge = SequenceJudge(["invalid-first", "invalid-second"])

        result = judge.score("質問", "回答", "正解")

        assert result.label == CRAGLabel.MISSING
        assert result.reason == "判定解析エラー"
        assert judge.call_count == 2

    def test_score_does_not_retry_successful_response(self) -> None:
        judge = SequenceJudge(['{"label": "Acceptable", "reason": "success"}'])

        result = judge.score("質問", "回答", "正解")

        assert result.label == CRAGLabel.ACCEPTABLE
        assert judge.call_count == 1

    def test_score_does_not_retry_valid_json_with_parse_error_reason(self) -> None:
        judge = SequenceJudge(
            ['{"label": "Missing", "reason": "判定解析エラー"}']
        )

        result = judge.score("質問", "回答", "正解")

        assert result.label == CRAGLabel.MISSING
        assert judge.call_count == 1

    def test_score_does_not_retry_api_exception(self) -> None:
        judge = SequenceJudge([RuntimeError("api failure")])

        with pytest.raises(RuntimeError, match="api failure"):
            judge.score("質問", "回答", "正解")

        assert judge.call_count == 1

    def test_score_prompt_prioritizes_exact_reference_match(self) -> None:
        judge = RecordingJudge('{"label": "Perfect", "reason": "一致"}')

        judge.score("質問", "同じ回答", "同じ回答")

        assert "以下に表示された比較基準の文字列が完全一致する場合は必ずPerfect" in judge.prompt

    def test_score_prompt_does_not_treat_concrete_mismatch_as_missing(self) -> None:
        judge = RecordingJudge('{"label": "Incorrect", "reason": "不一致"}')

        judge.score("質問", "具体的だが異なる回答", "正解")

        assert "具体的な回答がある場合はMissingにしない" in judge.prompt
        assert "比較基準に照らして誤りならIncorrect" in judge.prompt

    def test_score_prompt_requires_literal_value_for_short_answer(self) -> None:
        judge = RecordingJudge('{"label": "Incorrect", "reason": "言い換え"}')

        judge.score("短い値を答える質問", "意味が近い別表現", "基準値")

        assert "比較基準の主要な文字列・数値をそのまま保持" in judge.prompt
        assert "含まない同義の言い換えだけならIncorrect" in judge.prompt

    def test_score_prompt_penalizes_unsupported_extra_claims(self) -> None:
        judge = RecordingJudge('{"label": "Acceptable", "reason": "余分"}')

        judge.score("短い値を答える質問", "基準値と長い説明", "基準値")

        assert "比較基準で裏付けられない事実主張" in judge.prompt
        assert "Perfectにしない" in judge.prompt

    def test_score_prompt_prioritizes_literal_mismatch_over_acceptable(self) -> None:
        judge = RecordingJudge('{"label": "Incorrect", "reason": "言い換え"}')

        judge.score("短い値を答える質問", "意味が近い別表現", "基準値")

        assert "ルール4を優先し、Acceptableにしない" in judge.prompt

    def test_score_returns_perfect_when_llm_says_perfect(self) -> None:
        judge = FakeJudge('{"label": "Perfect", "reason": "非常に正確"}')
        result = judge.score(
            question="宿泊費の上限は？",
            generated_answer="15,000円です。",
            reference_or_context="宿泊費の上限は15,000円です。",
        )
        assert result.label == CRAGLabel.PERFECT

    def test_score_returns_incorrect_when_llm_says_incorrect(self) -> None:
        judge = FakeJudge('{"label": "Incorrect", "reason": "金額が間違い"}')
        result = judge.score(
            question="宿泊費の上限は？",
            generated_answer="100万円です。",
            reference_or_context="宿泊費の上限は15,000円です。",
        )
        assert result.label == CRAGLabel.INCORRECT

    def test_score_falls_back_to_missing_on_invalid_response(self) -> None:
        judge = FakeJudge("これは無効な応答です。JSON ではありません。")
        result = judge.score(
            question="何かの質問",
            generated_answer="何かの回答",
            reference_or_context="文脈",
        )
        assert result.label == CRAGLabel.MISSING

    def test_score_returns_judge_result_type(self) -> None:
        judge = FakeJudge('{"label": "Acceptable", "reason": "概ね正確"}')
        result = judge.score("質問", "回答", "文脈")
        assert isinstance(result, JudgeResult)

    def test_score_sets_correct_score_value(self) -> None:
        judge = FakeJudge('{"label": "Perfect", "reason": "正確"}')
        result = judge.score("質問", "回答", "文脈")
        assert result.score == 1.0


# ---------------------------------------------------------------------------
# metrics.summarize のテスト
# ---------------------------------------------------------------------------


class TestSummarize:
    def _make_results(self) -> list[JudgeResult]:
        return [
            JudgeResult(label=CRAGLabel.PERFECT, reason="ok"),
            JudgeResult(label=CRAGLabel.PERFECT, reason="ok"),
            JudgeResult(label=CRAGLabel.MISSING, reason="no answer"),
            JudgeResult(label=CRAGLabel.INCORRECT, reason="wrong"),
        ]

    def test_mean_score_is_correct(self) -> None:
        results = self._make_results()
        summary = summarize(results)
        expected = (1.0 + 1.0 + 0.0 + (-1.0)) / 4  # == 0.25
        assert abs(summary.mean_score - expected) < 1e-9

    def test_label_counts_perfect_is_2(self) -> None:
        summary = summarize(self._make_results())
        assert summary.label_counts.get("Perfect") == 2

    def test_label_counts_missing_is_1(self) -> None:
        summary = summarize(self._make_results())
        assert summary.label_counts.get("Missing") == 1

    def test_label_counts_incorrect_is_1(self) -> None:
        summary = summarize(self._make_results())
        assert summary.label_counts.get("Incorrect") == 1

    def test_total_is_correct(self) -> None:
        summary = summarize(self._make_results())
        assert summary.total == 4

    def test_report_returns_non_empty_string(self) -> None:
        summary = summarize(self._make_results())
        report = summary.report()
        assert isinstance(report, str)
        assert len(report) > 0

    def test_report_contains_total(self) -> None:
        summary = summarize(self._make_results())
        assert "Total: 4" in summary.report()

    def test_report_contains_mean_score(self) -> None:
        summary = summarize(self._make_results())
        assert "Mean score" in summary.report()

    def test_summarize_empty_list_returns_zero_mean(self) -> None:
        summary = summarize([])
        assert summary.mean_score == 0.0
        assert summary.total == 0

    def test_summarize_single_result(self) -> None:
        results = [JudgeResult(label=CRAGLabel.ACCEPTABLE, reason="ok")]
        summary = summarize(results)
        assert summary.total == 1
        assert summary.mean_score == 0.5


# ---------------------------------------------------------------------------
# LocalJudge._call_llm  ―  実際のAnthropic API接続（モックで検証）
# ---------------------------------------------------------------------------


class TestJudgeCallLLMRealIntegration:
    def test_call_llm_sends_prompt_and_returns_text(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CLAUDE_JUDGE_MODEL", "claude-sonnet-5")

        judge = LocalJudge()
        fake_content = type("C", (), {"text": '{"label": "Perfect", "reason": "正確"}'})()
        fake_response = type("R", (), {"content": [fake_content]})()

        with patch("src.evaluator.judge.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            raw = judge._call_llm("この回答を評価してください")

        assert raw == '{"label": "Perfect", "reason": "正確"}'
        _, kwargs = MockAnthropic.return_value.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
        assert "temperature" not in kwargs
        assert kwargs["messages"][0]["content"] == "この回答を評価してください"

    def test_call_llm_defaults_to_claude_sonnet_5_when_env_unset(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("CLAUDE_JUDGE_MODEL", raising=False)

        judge = LocalJudge()
        fake_content = type("C", (), {"text": "{}"})()
        fake_response = type("R", (), {"content": [fake_content]})()

        with patch("src.evaluator.judge.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            judge._call_llm("プロンプト")

        _, kwargs = MockAnthropic.return_value.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
