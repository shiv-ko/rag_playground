from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.generator.vlm_answerer import VLMImageAnswerer

_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8ffff3f0005fe02fea739669f0000000049454e44ae426082"
)


class TestVLMImageAnswererCallConstruction:
    def test_sends_image_block_and_question(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5")
        image_path = tmp_path / "figure_06.png"
        image_path.write_bytes(_PNG_1PX)

        fake_content = type("C", (), {
            "text": '{"answer": "20\\u65e5", "confidence": 0.85, "reasoning": "r"}'
        })()
        fake_response = type("R", (), {"content": [fake_content]})()

        answerer = VLMImageAnswerer()
        with patch("src.generator.vlm_answerer.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            result = answerer.answer("dayによる件数推移で件数が最も高いのは何日ですか。", image_path)

        assert result.was_gated is False
        assert result.text == "20日"

        _, kwargs = MockAnthropic.return_value.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
        content_blocks = kwargs["messages"][0]["content"]
        image_blocks = [b for b in content_blocks if b["type"] == "image"]
        text_blocks = [b for b in content_blocks if b["type"] == "text"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["source"]["media_type"] == "image/png"
        assert "件数が最も高い" in text_blocks[0]["text"]

    def test_low_confidence_is_gated(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        image_path = tmp_path / "figure_06.png"
        image_path.write_bytes(_PNG_1PX)

        fake_content = type("C", (), {
            "text": '{"answer": "わかりません", "confidence": 0.1, "reasoning": "r"}'
        })()
        fake_response = type("R", (), {"content": [fake_content]})()

        answerer = VLMImageAnswerer()
        with patch("src.generator.vlm_answerer.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            result = answerer.answer("質問", image_path)

        assert result.was_gated is True

    def test_missing_file_is_gated_without_api_call(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        answerer = VLMImageAnswerer()

        with patch("src.generator.vlm_answerer.Anthropic") as MockAnthropic:
            result = answerer.answer("質問", tmp_path / "not_exist.png")

        assert result.was_gated is True
        MockAnthropic.return_value.messages.create.assert_not_called()

    def test_unsupported_extension_is_gated_without_api_call(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        file_path = tmp_path / "report.pdf"
        file_path.write_bytes(b"%PDF-1.4")
        answerer = VLMImageAnswerer()

        with patch("src.generator.vlm_answerer.Anthropic") as MockAnthropic:
            result = answerer.answer("質問", file_path)

        assert result.was_gated is True
        MockAnthropic.return_value.messages.create.assert_not_called()
