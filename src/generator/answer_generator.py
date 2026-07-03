"""回答生成。_call_llm() はAnthropic APIを呼び出す。"""
from __future__ import annotations

import os
import threading

from anthropic import Anthropic

from src.generator.citation_check import citation_supported
from src.generator.confidence_gate import ConfidenceGate, looks_like_missing
from src.models import Answer, ScoredDocument
from src.utils.question_classifier import classify_question

# 1000トークン制限（約4文字/トークン換算で4000文字を上限にする暫定値）
MAX_CHARS_APPROX = 3500

SYSTEM_PROMPT = """\
あなたは社内共有ドライブの文書を参照して質問に答えるアシスタントです。

【評価基準】
- Perfect (1点): 正確かつ虚偽のない回答
- Acceptable (0.5点): 有用だが軽微な誤りがある回答
- Missing (0点): 「わかりません」等の具体的回答なし
- Incorrect (-1点): 間違い・無関係な回答

【重要ルール】
1. 提供された参考文書の内容のみを根拠として回答すること
2. 文書に部分的にしか記載がない場合でも、確実に読み取れる範囲で具体的に回答すること。
   「わかりません」と答えてよいのは、参考文書に質問と関連する情報が全く含まれていない場合のみ。
   表紙・目次・タイトルしか無いなど、実質的な手がかりが無い場合に限り「わかりません」とする。
3. 回答は1000トークン以内に収めること
4. confidenceは「この回答がPerfectまたはAcceptableと評価される確率」を0.0〜1.0で表すこと。
   「わかりません」と回答する場合は、confidenceを必ず0.0〜0.2の範囲にすること
   （わからないのにconfidenceを高くすることは禁止）。
5. 回答の直接の根拠となった文書中の一節を、要約・言い換えせずそのまま "citation" に引用すること。
   引用文が参考文書中に一字一句存在しない場合、回答は無効として扱われます。

【出力形式】
{
  "answer": "回答テキスト",
  "confidence": 0.0〜1.0,
  "citation": "根拠として引用した文書中の一節（そのまま抜粋）",
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
        self.input_tokens = 0
        self.output_tokens = 0
        self._usage_lock = threading.Lock()

    def generate(self, question: str, contexts: list[ScoredDocument]) -> Answer:
        tags = classify_question(question)
        if self.gate.is_capability_blocked(tags):
            return Answer(
                text=self.gate.missing_text(),
                confidence=0.0,
                source_docs=contexts,
                was_gated=True,
            )

        if not contexts:
            return Answer(
                text=self.gate.missing_text(),
                confidence=0.0,
                source_docs=[],
                was_gated=True,
            )

        context_text = _build_context(contexts)
        raw = self._call_llm(question, context_text)
        answer_text, confidence, citation = self._parse_response(raw)

        if looks_like_missing(answer_text):
            return Answer(
                text=self.gate.missing_text(),
                confidence=confidence,
                source_docs=contexts,
                was_gated=True,
                raw_text=answer_text,
            )

        if not self.gate.should_answer(confidence, tags=tags):
            return Answer(
                text=self.gate.missing_text(),
                confidence=confidence,
                source_docs=contexts,
                was_gated=True,
                raw_text=answer_text,
            )

        if not citation_supported(citation, context_text):
            return Answer(
                text=self.gate.missing_text(),
                confidence=confidence,
                source_docs=contexts,
                was_gated=True,
                raw_text=answer_text,
            )

        # トークン制限チェック（暫定: 文字数で近似）
        if len(answer_text) > MAX_CHARS_APPROX:
            answer_text = answer_text[:MAX_CHARS_APPROX] + "…"

        return Answer(
            text=answer_text, confidence=confidence,
            source_docs=contexts, raw_text=answer_text,
        )

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _call_llm(self, question: str, context: str) -> str:
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
        message = self._get_client().messages.create(
            model=model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"【質問】\n{question}\n\n【参考文書】\n{context}",
            }],
        )
        usage = getattr(message, "usage", None)
        if usage is not None:
            with self._usage_lock:
                self.input_tokens += usage.input_tokens
                self.output_tokens += usage.output_tokens
        return "".join(block.text for block in message.content if hasattr(block, "text"))

    def _parse_response(self, raw: str) -> tuple[str, float, str]:
        import json
        import re

        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return (
                    str(data.get("answer", "")),
                    float(data.get("confidence", 0.0)),
                    str(data.get("citation", "")),
                )
        except (json.JSONDecodeError, ValueError):
            pass
        # JSON解析失敗時はそのままテキストを使い確信度0・引用なし
        return raw, 0.0, ""
