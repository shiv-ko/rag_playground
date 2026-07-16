"""CRAG基準ローカルジャッジ。_call_llm() はAnthropic APIを呼び出す。"""
from __future__ import annotations

import json
import os
import re
import threading

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

【判定順序（最優先）】
1. 生成された回答と、以下に表示された比較基準の文字列が完全一致する場合は必ずPerfectとする。
2. Missingは、空回答・回答拒否など具体的な回答がない場合だけとする。
   具体的な回答がある場合はMissingにしない。比較基準に照らして誤りならIncorrectとする。
3. 正解が短い語句でも、質問を独自に解き直した推測で覆さず、正解との比較を優先する。
4. 質問が文字列・語句・数値などの短答を求め、比較基準も短い場合、生成された回答は
   比較基準の主要な文字列・数値をそのまま保持する必要がある。
   それを含まない同義の言い換えだけならIncorrectとし、Acceptableにはしない。
5. 短い正答に説明を加えた回答は、比較基準で裏付けられない事実主張があれば
   Perfectにしない。追加主張が重大・無関係ならIncorrect、軽微な不完全さなら
   Acceptableとする。

【質問】
{question}

【正解または参考文書（比較基準）】
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
        self.input_tokens = 0
        self.output_tokens = 0
        self._usage_lock = threading.Lock()

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
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = getattr(message, "usage", None)
        if usage is not None:
            with self._usage_lock:
                self.input_tokens += usage.input_tokens
                self.output_tokens += usage.output_tokens
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
