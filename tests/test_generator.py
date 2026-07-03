"""Generator コンポーネントの単体テスト（TDD）。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.generator.confidence_gate import ConfidenceGate
from src.generator.answer_generator import AnswerGenerator, MAX_CHARS_APPROX, SYSTEM_PROMPT
from src.models import Answer, Document, ScoredDocument


# ---------------------------------------------------------------------------
# ConfidenceGate
# ---------------------------------------------------------------------------


class TestConfidenceGate:
    def test_threshold_05_passes_exactly_05(self) -> None:
        """threshold=0.5 のとき 0.5 はちょうど通過する。"""
        gate = ConfidenceGate(threshold=0.5)
        assert gate.should_answer(0.5) is True

    def test_threshold_05_blocks_049(self) -> None:
        """threshold=0.5 のとき 0.49 は通過しない。"""
        gate = ConfidenceGate(threshold=0.5)
        assert gate.should_answer(0.49) is False

    def test_threshold_00_passes_all_values(self) -> None:
        """threshold=0.0 のとき 0.0 を含む全値が通過する。"""
        gate = ConfidenceGate(threshold=0.0)
        assert gate.should_answer(0.0) is True
        assert gate.should_answer(0.001) is True
        assert gate.should_answer(1.0) is True

    def test_missing_text_is_nonempty_string(self) -> None:
        """missing_text() は空でない文字列を返す。"""
        gate = ConfidenceGate()
        text = gate.missing_text()
        assert isinstance(text, str)
        assert len(text) > 0


# ---------------------------------------------------------------------------
# AnswerGenerator._parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    def setup_method(self) -> None:
        self.gen = AnswerGenerator()

    def test_parses_clean_json(self) -> None:
        """正常な JSON からアンサーと確信度を取得できる。"""
        raw = '{"answer": "foo", "confidence": 0.8, "reasoning": "some reason"}'
        answer, confidence = self.gen._parse_response(raw)
        assert answer == "foo"
        assert confidence == pytest.approx(0.8)

    def test_parses_json_surrounded_by_text(self) -> None:
        """JSON が前後テキストに囲まれていてもパースできる。"""
        raw = 'Here is the result: {"answer": "bar", "confidence": 0.7, "reasoning": "r"} done.'
        answer, confidence = self.gen._parse_response(raw)
        assert answer == "bar"
        assert confidence == pytest.approx(0.7)

    def test_invalid_json_returns_raw_and_zero_confidence(self) -> None:
        """不正な JSON のとき (raw_text, 0.0) を返す。"""
        raw = "this is not JSON at all"
        answer, confidence = self.gen._parse_response(raw)
        assert answer == raw
        assert confidence == 0.0

    def test_confidence_as_string_is_converted_to_float(self) -> None:
        """JSON 内の confidence が文字列 "0.8" でも float に変換される。"""
        raw = '{"answer": "baz", "confidence": "0.8", "reasoning": "r"}'
        answer, confidence = self.gen._parse_response(raw)
        assert answer == "baz"
        assert isinstance(confidence, float)
        assert confidence == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# AnswerGenerator.generate  ―  _call_llm をサブクラスでオーバーライド
# ---------------------------------------------------------------------------


class FakeGenerator(AnswerGenerator):
    """テスト用: _call_llm を固定レスポンスに差し替えた Generator。"""

    def __init__(self, fake_response: str, threshold: float = 0.4) -> None:
        super().__init__(threshold=threshold)
        self.fake_response = fake_response

    def _call_llm(self, question: str, context: str) -> str:
        return self.fake_response


def _scored_doc(tmp_path: Path, text: str = "some relevant text") -> ScoredDocument:
    return ScoredDocument(
        document=Document(text=text, source_path=tmp_path / "doc.txt"),
        score=0.9,
        retrieval_method="vector",
    )


class TestAnswerGeneratorGenerate:
    def test_high_confidence_answer_is_returned_ungated(self, tmp_path: Path) -> None:
        """確信度 0.9 の回答はゲートを通過してそのまま返る（was_gated=False）。"""
        fake_response = '{"answer": "correct answer", "confidence": 0.9, "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.was_gated is False
        assert answer.text == "correct answer"
        assert answer.confidence == pytest.approx(0.9)

    def test_low_confidence_answer_is_gated(self, tmp_path: Path) -> None:
        """確信度 0.1 の回答は ConfidenceGate でブロックされる（was_gated=True）。"""
        fake_response = '{"answer": "uncertain answer", "confidence": 0.1, "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.was_gated is True
        assert answer.text == gen.gate.missing_text()

    def test_empty_contexts_returns_gated_missing_answer(self) -> None:
        """contexts が空のとき was_gated=True で missing_text を返す。"""
        gen = FakeGenerator(fake_response="", threshold=0.4)
        answer = gen.generate("what?", [])
        assert answer.was_gated is True
        assert answer.text == gen.gate.missing_text()

    def test_long_answer_is_truncated_with_ellipsis(self, tmp_path: Path) -> None:
        """回答テキストが MAX_CHARS_APPROX を超えた場合、"…" で切り捨てられる。"""
        long_answer = "a" * (MAX_CHARS_APPROX + 100)
        fake_response = json.dumps(
            {"answer": long_answer, "confidence": 0.9, "reasoning": "r"}
        )
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.text.endswith("…")
        # MAX_CHARS_APPROX 文字 + "…" の 1 文字
        assert len(answer.text) == MAX_CHARS_APPROX + 1


# ---------------------------------------------------------------------------
# AnswerGenerator._call_llm  ―  実際のAnthropic API接続（モックで検証）
# ---------------------------------------------------------------------------


class TestCallLLMRealIntegration:
    def test_call_llm_sends_system_prompt_and_returns_text(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5")

        gen = AnswerGenerator()

        fake_content = type("C", (), {"text": '{"answer": "テスト回答", "confidence": 0.9, "reasoning": "r"}'})()
        fake_response = type("R", (), {"content": [fake_content]})()

        with patch("src.generator.answer_generator.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            raw = gen._call_llm("質問文です", "文脈です")

        assert raw == '{"answer": "テスト回答", "confidence": 0.9, "reasoning": "r"}'
        _, kwargs = MockAnthropic.return_value.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
        assert kwargs["temperature"] == 0.0
        assert kwargs["system"] == SYSTEM_PROMPT
        assert "質問文です" in kwargs["messages"][0]["content"]
        assert "文脈です" in kwargs["messages"][0]["content"]

    def test_call_llm_defaults_to_claude_sonnet_5_when_env_unset(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("CLAUDE_MODEL", raising=False)

        gen = AnswerGenerator()
        fake_content = type("C", (), {"text": "{}"})()
        fake_response = type("R", (), {"content": [fake_content]})()

        with patch("src.generator.answer_generator.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            gen._call_llm("質問", "文脈")

        _, kwargs = MockAnthropic.return_value.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
