"""画像・グラフの読解生成。_call_vlm() はAnthropic Vision APIを呼び出す。"""
from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
from pathlib import Path

from anthropic import Anthropic

from src.generator.confidence_gate import ConfidenceGate
from src.models import Answer

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

VLM_SYSTEM_PROMPT = """\
あなたは画像として提供されたグラフ・図表を読み取り、質問に答えるアシスタントです。

【重要ルール】
1. 画像に実際に描画されている内容のみを根拠に回答すること。読み取れない場合は正直に「わかりません」と答える
2. confidenceは「この回答が正しい確率」を0.0〜1.0で表すこと。読み取りに自信が持てない場合は0.4未満にすること
   （わからないのにconfidenceを高くすることは禁止）
3. 設問が特定の数値・日付・ラベルを問う場合、"answer" には値そのものだけを入れ、説明文を続けないこと
4. 回答は1000トークン以内に収めること

【出力形式】
{
  "answer": "回答テキスト",
  "confidence": 0.0〜1.0,
  "reasoning": "画像のどの部分から読み取ったか"
}
"""


class VLMImageAnswerer:
    """独立画像ファイル（png等）をClaude Vision APIに直接渡して質問に答える。"""

    def __init__(self, threshold: float = 0.4) -> None:
        self.gate = ConfidenceGate(threshold=threshold)
        self._client: Anthropic | None = None

    def answer(self, question: str, image_path: Path) -> Answer:
        media_type = _MEDIA_TYPES.get(image_path.suffix.lower())
        if media_type is None:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="vlm_unsupported_format")
        try:
            image_bytes = image_path.read_bytes()
        except OSError:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="vlm_file_not_found")

        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        raw = self._call_vlm(question, image_b64, media_type)
        answer_text, confidence, _reasoning = self._parse_response(raw)

        if not answer_text or not self.gate.should_answer(confidence):
            return Answer(text=self.gate.missing_text(), confidence=confidence, was_gated=True,
                           raw_text=answer_text, gate_reason="vlm_confidence")

        return Answer(text=answer_text, confidence=confidence, was_gated=False,
                      raw_text=answer_text, gate_reason="vlm_image")

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _call_vlm(self, question: str, image_b64: str, media_type: str) -> str:
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
        message = self._get_client().messages.create(
            model=model,
            max_tokens=1000,
            system=VLM_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": f"【質問】\n{question}"},
                ],
            }],
        )
        return "".join(block.text for block in message.content if hasattr(block, "text"))

    def _parse_response(self, raw: str) -> tuple[str, float, str]:
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group(), strict=False)
                return (
                    str(data.get("answer", "")),
                    float(data.get("confidence", 0.0)),
                    str(data.get("reasoning", "")),
                )
        except (json.JSONDecodeError, ValueError):
            pass
        return raw, 0.0, ""


# office_chart.pyの_FILE_REと同じ理由（\wが平仮名を含みUnicodeの助詞境界を吸収してしまう）で、
# 明示的な文字クラス（平仮名を除くASCII+漢字+カタカナ）を使う。
_IMAGE_FILE_RE = re.compile(r"([A-Za-z0-9_\-一-龠ァ-ヶー]+\.(?:png|jpg|jpeg|gif|webp))", re.IGNORECASE)


def find_referenced_image(question: str, project_name: str, data_dir: Path) -> Path | None:
    """質問文中に明示されたファイル名（例: figure_06.png）を案件ディレクトリ配下から探す。"""
    match = _IMAGE_FILE_RE.search(question)
    if match is None:
        return None
    filename = match.group(1)
    normalized_project = unicodedata.normalize("NFC", project_name)
    matching = sorted(
        p for p in data_dir.rglob(filename)
        if normalized_project in unicodedata.normalize("NFC", str(p))
    )
    return matching[0] if matching else None
