"""CRAG基準ローカルジャッジ。_call_llm() はAnthropic APIを呼び出す。"""
from __future__ import annotations

import json
import os
import re

from anthropic import Anthropic

from src.models import CRAGLabel, JudgeResult

JUDGE_PROMPT_TEMPLATE = """\
あなたはRAGシステムの回答品質を評価するジャッジです。
以下の基準で回答を評価してください。

【評価基準】
- Perfect: 質問に正確に答えており、虚偽の情報が含まれない
- Acceptable: 概ね有用だが軽微な誤りや不完全さがある
- Missing: 「わかりません」等の具体的回答なし、または回答拒否
- Incorrect: 間違い・無関係・有害な回答

【質問】
{question}

【参考文書（根拠）】
{reference}

【生成された回答】
{generated_answer}

上記を評価し、以下のJSON形式で出力してください:
{{"label": "Perfect|Acceptable|Missing|Incorrect", "reason": "判定理由"}}
"""


class LocalJudge:
    """
    CRAG基準ローカルジャッジ。_call_llm() でAnthropic APIを呼び出す。
    """

    def __init__(self) -> None:
        self._client: Anthropic | None = None

    def score(
        self,
        question: str,
        generated_answer: str,
        reference_or_context: str,
    ) -> JudgeResult:
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            question=question,
            reference=reference_or_context[:2000],
            generated_answer=generated_answer,
        )
        raw = self._call_llm(prompt)
        return self._parse(raw)

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _call_llm(self, prompt: str) -> str:
        model = os.environ.get("CLAUDE_JUDGE_MODEL", "claude-sonnet-5")
        message = self._get_client().messages.create(
            model=model,
            temperature=0.0,  # 実験の再現性と回答の安定性のため決定的にする
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in message.content if hasattr(block, "text"))

    def _parse(self, raw: str) -> JudgeResult:
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                label = CRAGLabel(data.get("label", "Missing"))
                reason = str(data.get("reason", ""))
                return JudgeResult(label=label, reason=reason)
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        return JudgeResult(label=CRAGLabel.MISSING, reason="判定解析エラー")
