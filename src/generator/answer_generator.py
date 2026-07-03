"""回答生成。_call_llm() はAnthropic APIを呼び出す。"""
from __future__ import annotations

import os

from anthropic import Anthropic

from src.generator.confidence_gate import ConfidenceGate
from src.models import Answer, ScoredDocument

# 1000トークン制限（約4文字/トークン換算で4000文字を上限にする暫定値）
MAX_CHARS_APPROX = 3500

SYSTEM_PROMPT = """\
あなたは社内共有ドライブの文書を参照して質問に答るアシスタントです。

【評価基準】
- Perfect (1点): 正確かつ虚偽のない回答
- Acceptable (0.5点): 有用だが軽微な誤りがある回答
- Missing (0点): 「わかりません」等の具体的回答なし
- Incorrect (-1点): 間違い・無関係な回答

【重要ルール】
1. 提供された参考文書の内容のみを根拠として回答すること
2. 文書に記載がない情報は「わかりません」と答えること（Incorrectより安全）
3. 回答は1000トークン以内に収めること
4. 確信度を0.0〜1.0で自己評価し、JSON形式で返すこと

【出力形式】
{
  "answer": "回答テキスト",
  "confidence": 0.0〜1.0,
  "reasoning": "根拠となった文書の箇所"
}
"""


def _build_context(contexts: list[ScoredDocument]) -> str:
    parts = []
    for i, sd in enumerate(contexts, 1):
        source = sd.document.source_path.name
        loc = sd.document.location
        parts.append(f"【参考文書 {i}】({source} / {loc})\n{sd.document.text[:800]}")
    return "\n\n".join(parts)


class AnswerGenerator:
    """
    _call_llm() は Claude API 呼び出しを行う。
    それ以外のロジック（プロンプト構築・ゲート・トークン制限）はそのまま使える。
    """

    def __init__(self, threshold: float = 0.4) -> None:
        self.gate = ConfidenceGate(threshold=threshold)
        self._client: Anthropic | None = None

    def generate(self, question: str, contexts: list[ScoredDocument]) -> Answer:
        if not contexts:
            return Answer(
                text=self.gate.missing_text(),
                confidence=0.0,
                source_docs=[],
                was_gated=True,
            )

        context_text = _build_context(contexts)
        raw = self._call_llm(question, context_text)
        answer_text, confidence = self._parse_response(raw)

        # 確信度ゲート
        if not self.gate.should_answer(confidence):
            return Answer(
                text=self.gate.missing_text(),
                confidence=confidence,
                source_docs=contexts,
                was_gated=True,
            )

        # トークン制限チェック（暫定: 文字数で近似）
        if len(answer_text) > MAX_CHARS_APPROX:
            answer_text = answer_text[:MAX_CHARS_APPROX] + "…"

        return Answer(text=answer_text, confidence=confidence, source_docs=contexts)

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _call_llm(self, question: str, context: str) -> str:
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
        message = self._get_client().messages.create(
            model=model,
            max_tokens=1500,
            temperature=0.0,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"【質問】\n{question}\n\n【参考文書】\n{context}",
            }],
        )
        return message.content[0].text

    def _parse_response(self, raw: str) -> tuple[str, float]:
        import json
        import re

        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return str(data.get("answer", "")), float(data.get("confidence", 0.0))
        except (json.JSONDecodeError, ValueError):
            pass
        # JSON解析失敗時はそのままテキストを使い確信度0
        return raw, 0.0
