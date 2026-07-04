"""train.csv構造化フィルタ＋集計。"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import pandas as pd
from anthropic import Anthropic

from src.generator.confidence_gate import ConfidenceGate
from src.models import Answer

_OPS = {
    "==": lambda s, v: s == v,
    "!=": lambda s, v: s != v,
    ">": lambda s, v: s > v,
    "<": lambda s, v: s < v,
    ">=": lambda s, v: s >= v,
    "<=": lambda s, v: s <= v,
}

_AGGS = {
    "mean": lambda s: s.mean(),
    "sum": lambda s: s.sum(),
    "count": lambda s: s.count(),
    "max": lambda s: s.max(),
    "min": lambda s: s.min(),
}

SYSTEM_PROMPT = """\
あなたはExcel/CSVデータに対する集計質問を、フィルタ条件と集計方法のJSON仕様に変換するアシスタントです。
実際の計算はあなたが行う必要はありません。列名は与えられた一覧から選び、存在しない列名を作らないこと。

【出力形式】
{
  "filters": [{"column": "列名", "op": "==|!=|>|<|>=|<=", "value": "値"}],
  "target_column": "集計対象の列名",
  "aggregation": "mean|sum|count|max|min",
  "round_to": 0,
  "group_by": "グループ化する列名",
  "select": "argmax|argmin"
}

"round_to"は四捨五入する小数桁数（整数なら0）。指定が無ければnullにすること。
"group_by"と"select"は、グループ別に集計して「最も大きい/小さいグループ」を答える場合だけ指定し、
指定が無ければnullにすること。返す値はグループ値そのもの。
質問がこの形式で表現できない場合（複数列の組み合わせ等）や、与えられた列名では答えられない場合は
{"not_applicable": true} のみを返すこと。
"""

# CalcSpec（単一フィルタ＋単一集計）で表現できない質問のヒント。
# もっともらしいspecで誤った数値を返す（Incorrect=-1）よりゲートしてフォールバックさせる。
_UNSUPPORTED_QUESTION_HINTS = ("ごとの", "ごとに", "毎に", "それぞれ")
_SPREADSHEET_STATE_HINTS = (".xlsx", "train.xlsx", "Pivot", "pivot", "ピボット", "シート")


@dataclass(frozen=True)
class FilterCondition:
    column: str
    op: str
    value: str | float


@dataclass
class CalcSpec:
    filters: list[FilterCondition] = field(default_factory=list)
    target_column: str = ""
    aggregation: str = ""
    round_to: int | None = None
    group_by: str | None = None
    select: str | None = None


def parse_calc_spec(raw_json: str) -> CalcSpec | None:
    try:
        m = re.search(r"\{.*\}", raw_json, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group())
        target_column = data.get("target_column")
        aggregation = data.get("aggregation")
        if not target_column or aggregation not in _AGGS:
            return None
        group_by = data.get("group_by")
        select = data.get("select")
        if select is not None and select not in ("argmax", "argmin"):
            return None
        if bool(group_by) != bool(select):
            return None
        filters = [
            FilterCondition(column=f["column"], op=f["op"], value=f["value"])
            for f in data.get("filters", [])
            if f.get("column") and f.get("op") in _OPS
        ]
        return CalcSpec(
            filters=filters,
            target_column=target_column,
            aggregation=aggregation,
            round_to=data.get("round_to"),
            group_by=group_by,
            select=select,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def execute_calc_spec(spec: CalcSpec, df: pd.DataFrame) -> float | int | str | None:
    if spec.target_column not in df.columns:
        return None
    if spec.group_by and spec.group_by not in df.columns:
        return None
    filtered = df
    for cond in spec.filters:
        if cond.column not in filtered.columns:
            return None
        op_fn = _OPS.get(cond.op)
        if op_fn is None:
            return None
        try:
            filtered = filtered[op_fn(filtered[cond.column], cond.value)]
        except TypeError:
            return None
    if len(filtered) == 0:
        return None
    agg_fn = _AGGS.get(spec.aggregation)
    if agg_fn is None:
        return None

    if spec.group_by:
        if spec.select not in ("argmax", "argmin"):
            return None
        grouped = filtered.groupby(spec.group_by, dropna=False)[spec.target_column].agg(spec.aggregation)
        if len(grouped) == 0:
            return None
        selected = grouped.idxmax() if spec.select == "argmax" else grouped.idxmin()
        if pd.isna(selected):
            return None
        return selected

    result = agg_fn(filtered[spec.target_column])
    if pd.isna(result):
        return None
    if spec.round_to is not None:
        result = round(float(result), spec.round_to)
        if spec.round_to == 0:
            result = int(result)
    return result


class SpreadsheetCalcAnswerer:
    def __init__(self, threshold: float = 0.4) -> None:
        self.gate = ConfidenceGate(threshold=threshold)
        self._client: Anthropic | None = None

    def answer(self, question: str, df: pd.DataFrame) -> Answer:
        if any(hint in question for hint in _UNSUPPORTED_QUESTION_HINTS):
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)
        if any(hint in question for hint in _SPREADSHEET_STATE_HINTS):
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)

        columns_preview = ", ".join(df.columns)
        raw = self._call_llm(question, columns_preview)
        spec = parse_calc_spec(raw)
        if spec is None:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)

        result = execute_calc_spec(spec, df)
        if result is None:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True)

        return Answer(text=str(result), confidence=0.9, was_gated=False)

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _call_llm(self, question: str, columns_preview: str) -> str:
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
        message = self._get_client().messages.create(
            model=model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"【質問】\n{question}\n\n【利用可能な列名】\n{columns_preview}",
            }],
        )
        return "".join(block.text for block in message.content if hasattr(block, "text"))
