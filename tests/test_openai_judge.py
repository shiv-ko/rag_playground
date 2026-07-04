"""OpenAICragJudge のテスト。_call_llm をオーバーライドしてAPI呼び出しを排除。"""
from src.evaluator.openai_judge import OFFICIAL_SYSTEM_PROMPT, OpenAICragJudge
from src.models import CRAGLabel


class FakeJudge(OpenAICragJudge):
    def __init__(self, response: str) -> None:
        super().__init__()
        self._response = response
        self.last_user_prompt = ""

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        self.last_user_prompt = user_prompt
        return self._response


def test_score_parses_label():
    judge = FakeJudge('{"judged": "Perfect"}')
    result = judge.score(generated_answer="20日", ground_truth="20日")
    assert result.label == CRAGLabel.PERFECT
    assert result.score == 1.0


def test_prompt_format_matches_official():
    """本番evaluatorと同じ 'ground_truth: {} answer: {}' 形式。"""
    judge = FakeJudge('{"judged": "Missing"}')
    judge.score(generated_answer="わかりません", ground_truth="正解X")
    assert judge.last_user_prompt == "ground_truth: 正解X answer: わかりません\n"


def test_official_prompt_has_crag_rules():
    """本番プロンプトの要点（部分一致=Incorrect等）が含まれている。"""
    assert "Perfect" in OFFICIAL_SYSTEM_PROMPT
    assert "部分一致" in OFFICIAL_SYSTEM_PROMPT


def test_parse_failure_returns_missing():
    judge = FakeJudge("not json")
    result = judge.score(generated_answer="x", ground_truth="y")
    assert result.label == CRAGLabel.MISSING
