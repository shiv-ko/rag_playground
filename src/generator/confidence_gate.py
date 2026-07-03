"""確信度が閾値未満なら回答をMissing相当に差し替えるゲート。"""

MISSING_RESPONSE = "提供された資料からは、ご質問に対する回答を見つけることができませんでした。"


class ConfidenceGate:
    def __init__(self, threshold: float = 0.4) -> None:
        self.threshold = threshold

    def should_answer(self, confidence: float) -> bool:
        return confidence >= self.threshold

    def missing_text(self) -> str:
        return MISSING_RESPONSE
