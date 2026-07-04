"""本番評価と同一プロンプト・設定のCRAGジャッジ（judge較正用）。

data/raw/evaluation/src/evaluator.py の CRAGEvaluator._judge_by_crag を再現する。
- モデル: gpt-5.2-2025-12-11 / temperature=0 / seed=0 / json_schema強制
- プロンプトは ground_truth と answer のみ比較（質問文を見ない）
"""
from __future__ import annotations

import json
import os
import re
import time

from src.models import CRAGLabel, JudgeResult

# data/raw/evaluation/src/evaluator.py から一字一句コピー（変更禁止）
OFFICIAL_SYSTEM_PROMPT = """
        与えられた問題のground_truthとanswerを比較してその結果を"Perfect", "Acceptable", "Missing", "Incorrect"の中から一つだけ選んで答えてください. それぞれの定義と規則は以下の通り.
        # 定義
        Perfect: answerが問題に正しく回答しており, 幻覚的な内容を含んでいない.
        Acceptable: answerが問題の回答として有効な内容を含んでいるが, わずかな誤りも含んでいる. ただし, 有効性を壊すほどではない.
        Missing: answerが「わかりません」,「見つかりません」, 空の回答, または元の質問を明確にするための要求を含んでいる.
        Incorrect: answerが間違っているか問題と無関係な内容を含んでいる.

        # 数値問題に関する規則
        正解と完全一致する場合のみ「Perfect」とする。
        「Acceptable」と判定できるのは、正解値を所定の桁数で四捨五入した結果と一致する場合に限る。
        単位の有無や接尾辞・補足語の違い（例：「5」と「5ページ」）は同一とみなす。

        # 要素列挙問題に関する規則
        すべての要素が完全一致した場合のみ「Perfect」とする。
        部分一致はすべて「Incorrect」とする。
        「Acceptable」は使用しない。

        JSON形式でkeyとして"judged"を含みそのvalueに結果を記載して出力すること.
        """

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "judgement_schema",
        "schema": {
            "type": "object",
            "properties": {
                "judged": {
                    "type": "string",
                    "enum": ["Perfect", "Acceptable", "Missing", "Incorrect"],
                }
            },
            "required": ["judged"],
            "additionalProperties": False,
        },
    },
}


class OpenAICragJudge:
    def __init__(self, model: str = "gpt-5.2-2025-12-11") -> None:
        self.model = model
        self._client = None

    def score(self, generated_answer: str, ground_truth: str) -> JudgeResult:
        user_prompt = "ground_truth: {} answer: {}\n".format(ground_truth, generated_answer)
        raw = self._call_llm(OFFICIAL_SYSTEM_PROMPT, user_prompt)
        return self._parse(raw)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        return self._client

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        last_error: Exception | None = None
        for _ in range(3):
            try:
                response = self._get_client().chat.completions.create(
                    model=self.model,
                    temperature=0,
                    seed=0,
                    timeout=1200,
                    response_format=_RESPONSE_FORMAT,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                return response.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001 - リトライして最後に投げ直す
                last_error = e
                time.sleep(10)
        raise RuntimeError(f"OpenAI judge 3回失敗: {last_error}")

    def _parse(self, raw: str) -> JudgeResult:
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return JudgeResult(
                    label=CRAGLabel(data["judged"]),
                    reason="official CRAG judge",
                )
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        return JudgeResult(label=CRAGLabel.MISSING, reason="判定解析エラー")
