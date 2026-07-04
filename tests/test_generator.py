"""Generator コンポーネントの単体テスト（TDD）。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.generator.confidence_gate import ConfidenceGate, looks_like_missing
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


class TestConfidenceGateTags:
    def test_capability_blocked_tag_forces_false_regardless_of_confidence(self) -> None:
        gate = ConfidenceGate(threshold=0.0)
        assert gate.should_answer(1.0, tags=["image_or_graph"]) is False
        assert gate.should_answer(1.0, tags=["password_protected"]) is False

    def test_high_risk_tag_raises_effective_threshold(self) -> None:
        gate = ConfidenceGate(threshold=0.4)
        assert gate.should_answer(0.5, tags=["multi_hop"]) is False
        assert gate.should_answer(0.7, tags=["multi_hop"]) is True

    def test_normal_tags_do_not_change_threshold(self) -> None:
        gate = ConfidenceGate(threshold=0.4)
        assert gate.should_answer(0.4, tags=["text_only"]) is True

    def test_should_answer_without_tags_argument_still_works(self) -> None:
        gate = ConfidenceGate(threshold=0.4)
        assert gate.should_answer(0.5) is True
        assert gate.should_answer(0.3) is False

    def test_is_capability_blocked(self) -> None:
        gate = ConfidenceGate()
        assert gate.is_capability_blocked(["image_or_graph"]) is True
        assert gate.is_capability_blocked(["text_only"]) is False
        assert gate.is_capability_blocked([]) is False


class TestLooksLikeMissing:
    def test_detects_wakarimasen(self) -> None:
        assert looks_like_missing("提供された資料からはわかりません") is True

    def test_detects_mitsukarimasen(self) -> None:
        assert looks_like_missing("該当箇所が見つかりません") is True

    def test_normal_answer_is_not_missing(self) -> None:
        assert looks_like_missing("宿泊費の上限は15,000円です。") is False

    def test_partial_answer_containing_missing_phrase_is_not_missing(self) -> None:
        """実質的な回答を含む部分回答は、末尾に「わかりません」があってもMissing扱いしない
        （プロンプトの部分回答推奨と矛盾する過剰ゲートの緩和）。"""
        assert looks_like_missing(
            "宿泊費の上限は15,000円です。日当については資料に記載がなくわかりません。"
        ) is False

    def test_multi_sentence_pure_missing_is_still_missing(self) -> None:
        assert looks_like_missing("わかりません。該当箇所が見つかりません。") is True


# ---------------------------------------------------------------------------
# AnswerGenerator._parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    def setup_method(self) -> None:
        self.gen = AnswerGenerator()

    def test_parses_clean_json(self) -> None:
        """正常な JSON からアンサー・確信度・引用を取得できる。"""
        raw = '{"answer": "foo", "confidence": 0.8, "citation": "bar", "reasoning": "some reason"}'
        answer, confidence, citation = self.gen._parse_response(raw)
        assert answer == "foo"
        assert confidence == pytest.approx(0.8)
        assert citation == "bar"

    def test_parse_response_allows_raw_newline_in_strings(self) -> None:
        """citation内の生改行（制御文字）でパース失敗しない（実測valid Q18の真因）。"""
        raw = '{"answer": "第3章に記載", "confidence": 0.55, "citation": "3. 業務範囲\n乙が本契約に基づき"}'
        answer, confidence, citation = self.gen._parse_response(raw)
        assert answer == "第3章に記載"
        assert confidence == pytest.approx(0.55)
        assert "業務範囲" in citation

    def test_parses_json_surrounded_by_text(self) -> None:
        """JSON が前後テキストに囲まれていてもパースできる。"""
        raw = 'Here is the result: {"answer": "bar", "confidence": 0.7, "citation": "baz", "reasoning": "r"} done.'
        answer, confidence, citation = self.gen._parse_response(raw)
        assert answer == "bar"
        assert confidence == pytest.approx(0.7)
        assert citation == "baz"

    def test_invalid_json_returns_raw_zero_confidence_and_empty_citation(self) -> None:
        """不正な JSON のとき (raw_text, 0.0, "") を返す。"""
        raw = "this is not JSON at all"
        answer, confidence, citation = self.gen._parse_response(raw)
        assert answer == raw
        assert confidence == 0.0
        assert citation == ""

    def test_confidence_as_string_is_converted_to_float(self) -> None:
        """JSON 内の confidence が文字列 "0.8" でも float に変換される。"""
        raw = '{"answer": "baz", "confidence": "0.8", "citation": "c", "reasoning": "r"}'
        answer, confidence, citation = self.gen._parse_response(raw)
        assert answer == "baz"
        assert isinstance(confidence, float)
        assert confidence == pytest.approx(0.8)
        assert citation == "c"

    def test_missing_citation_key_defaults_to_empty_string(self) -> None:
        """citationキーが無いJSONでも空文字にフォールバックする。"""
        raw = '{"answer": "foo", "confidence": 0.8, "reasoning": "r"}'
        _, _, citation = self.gen._parse_response(raw)
        assert citation == ""


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
        """確信度 0.9 かつ引用が実在する回答はゲートを通過してそのまま返る。"""
        fake_response = '{"answer": "correct answer", "confidence": 0.9, "citation": "some relevant text", "reasoning": "r"}'
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
            {
                "answer": long_answer,
                "confidence": 0.9,
                "citation": "some relevant text",
                "reasoning": "r",
            }
        )
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.text.endswith("…")
        # MAX_CHARS_APPROX 文字 + "…" の 1 文字
        assert len(answer.text) == MAX_CHARS_APPROX + 1

    def test_capability_blocked_question_skips_llm_call(self, tmp_path: Path) -> None:
        """image_or_graph等の能力外タイプはLLMを呼ばずに即Missing。"""

        class BoomGenerator(AnswerGenerator):
            def _call_llm(self, question: str, context: str) -> str:
                raise AssertionError("能力外タイプでLLMを呼んではいけない")

        gen = BoomGenerator(threshold=0.4)
        answer = gen.generate("この画像の意味を教えてください", [_scored_doc(tmp_path)])
        assert answer.was_gated is True
        assert answer.text == gen.gate.missing_text()

    def test_multi_hop_question_needs_higher_confidence(self, tmp_path: Path) -> None:
        fake_response = '{"answer": "回答", "confidence": 0.5, "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("すべての案件の合計金額を教えてください", [_scored_doc(tmp_path)])
        assert answer.was_gated is True

    def test_multi_hop_question_passes_with_high_confidence(self, tmp_path: Path) -> None:
        fake_response = '{"answer": "回答", "confidence": 0.8, "citation": "some relevant text", "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("すべての案件の合計金額を教えてください", [_scored_doc(tmp_path)])
        assert answer.was_gated is False

    def test_fabricated_citation_is_gated_even_with_high_confidence(self, tmp_path: Path) -> None:
        """confidenceが高くても、citationが参考文書に実在しなければMissingにする。"""
        fake_response = '{"answer": "捏造回答", "confidence": 0.95, "citation": "文書に存在しない架空の一節", "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.was_gated is True
        assert answer.text == gen.gate.missing_text()

    def test_missing_citation_field_is_gated(self, tmp_path: Path) -> None:
        """citationフィールド自体が無い場合もMissingにする。"""
        fake_response = '{"answer": "回答", "confidence": 0.9, "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.was_gated is True

    def test_missing_phrase_answer_is_gated_even_with_high_confidence(self, tmp_path: Path) -> None:
        """「わかりません」と答えつつconfidenceが高い場合もMissing扱いする。"""
        fake_response = '{"answer": "わかりません", "confidence": 0.9, "citation": "some relevant text", "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.was_gated is True
        assert answer.text == gen.gate.missing_text()


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
        assert "temperature" not in kwargs
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


class TestSystemPromptConfidenceSemantics:
    def test_prompt_defines_low_confidence_for_missing_answers(self) -> None:
        assert "わからない" in SYSTEM_PROMPT or "わかりません" in SYSTEM_PROMPT
        assert "0.0" in SYSTEM_PROMPT and "0.2" in SYSTEM_PROMPT

    def test_prompt_instructs_partial_answers_over_refusal(self) -> None:
        assert "部分的" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# raw_text（ゲート前の生回答を保持する）
# ---------------------------------------------------------------------------


def test_gated_answer_keeps_raw_text():
    """ゲートで落ちてもゲート前の回答が raw_text に残る。"""

    class FakeGen(AnswerGenerator):
        def _call_llm(self, question, context):
            return '{"answer": "生の回答", "confidence": 0.1, "citation": "本文", "reasoning": "低確信"}'

    gen = FakeGen(threshold=0.4)
    doc = ScoredDocument(
        document=Document(text="本文", source_path=Path("dummy.txt")), score=1.0
    )
    ans = gen.generate("質問", [doc])
    assert ans.was_gated is True
    assert ans.raw_text == "生の回答"


def test_citation_gated_answer_keeps_raw_text():
    """引用実在チェックで落ちた場合もゲート前の回答が raw_text に残る。"""

    class FakeGen(AnswerGenerator):
        def _call_llm(self, question, context):
            return '{"answer": "捏造回答", "confidence": 0.9, "citation": "存在しない引用", "reasoning": "r"}'

    gen = FakeGen(threshold=0.4)
    doc = ScoredDocument(
        document=Document(text="本文", source_path=Path("dummy.txt")), score=1.0
    )
    ans = gen.generate("質問", [doc])
    assert ans.was_gated is True
    assert ans.raw_text == "捏造回答"


def test_ungated_answer_raw_text_equals_text():
    class FakeGen(AnswerGenerator):
        def _call_llm(self, question, context):
            return '{"answer": "採用された回答", "confidence": 0.9, "citation": "本文", "reasoning": "高確信"}'

    gen = FakeGen(threshold=0.4)
    doc = ScoredDocument(
        document=Document(text="本文", source_path=Path("dummy.txt")), score=1.0
    )
    ans = gen.generate("質問", [doc])
    assert ans.was_gated is False
    assert ans.raw_text == ans.text == "採用された回答"


# ---------------------------------------------------------------------------
# gate_reason（どのゲートで落ちたかをrun JSONに残す）
# ---------------------------------------------------------------------------


def _fake_gen(response: str, threshold: float = 0.4):
    class FakeGen(AnswerGenerator):
        def _call_llm(self, question, context):
            return response
    return FakeGen(threshold=threshold)


def _doc():
    return ScoredDocument(
        document=Document(text="本文の根拠", source_path=Path("dummy.txt")), score=1.0
    )


def test_gate_reason_no_context():
    gen = _fake_gen('{"answer": "x", "confidence": 0.9, "citation": "本文の根拠"}')
    ans = gen.generate("質問", [])
    assert ans.was_gated is True
    assert ans.gate_reason == "no_context"


def test_gate_reason_missing_text():
    gen = _fake_gen('{"answer": "わかりません", "confidence": 0.1, "citation": ""}')
    ans = gen.generate("質問", [_doc()])
    assert ans.gate_reason == "missing_text"


def test_gate_reason_confidence():
    gen = _fake_gen('{"answer": "低確信の回答", "confidence": 0.1, "citation": "本文の根拠"}')
    ans = gen.generate("質問", [_doc()])
    assert ans.gate_reason == "confidence"


def test_gate_reason_citation():
    gen = _fake_gen('{"answer": "回答", "confidence": 0.9, "citation": "文書に存在しない一節"}')
    ans = gen.generate("質問", [_doc()])
    assert ans.gate_reason == "citation"


def test_gate_reason_capability():
    gen = _fake_gen('{"answer": "x", "confidence": 0.9, "citation": "本文の根拠"}')
    ans = gen.generate("このグラフの色は何色ですか", [_doc()])  # image_or_graphタグ
    assert ans.gate_reason == "capability"


def test_gate_reason_empty_when_answered():
    gen = _fake_gen('{"answer": "採用される回答", "confidence": 0.9, "citation": "本文の根拠"}')
    ans = gen.generate("質問", [_doc()])
    assert ans.was_gated is False
    assert ans.gate_reason == ""
