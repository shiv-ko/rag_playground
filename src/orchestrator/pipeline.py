"""パイプライン本体。パース→インデックス→検索→生成→評価のループを非同期で回す。"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from src.evaluator.judge import LocalJudge
from src.evaluator.metrics import EvalSummary, summarize
from src.generator.answer_generator import AnswerGenerator
from src.models import Answer, JudgeResult
from src.parsers.dispatcher import ParserDispatcher
from src.retriever.project_scoped_retriever import ProjectScopedRetriever
from src.utils.logging import setup_logging
from src.utils.parallel import estimate_remaining_time, run_with_semaphore


@dataclass
class QAPair:
    question_id: str
    question: str
    reference_answer: str = ""  # 評価用（本番では不明）


@dataclass
class PipelineResult:
    question_id: str
    question: str
    answer: str
    confidence: float
    was_gated: bool
    judge_label: str
    judge_score: float
    judge_reason: str


class Pipeline:
    def __init__(
        self,
        data_dir: Path,
        max_concurrent: int = 5,
        top_k: int = 5,
        confidence_threshold: float = 0.4,
        run_judge: bool = True,
    ) -> None:
        self.data_dir = data_dir
        self.max_concurrent = max_concurrent
        self.top_k = top_k
        self.run_judge = run_judge
        self.logger = setup_logging()

        self.dispatcher = ParserDispatcher()
        self.retriever = ProjectScopedRetriever()
        self.generator = AnswerGenerator(threshold=confidence_threshold)
        self.judge = LocalJudge()

    # ------------------------------------------------------------------ #
    # インデックス構築
    # ------------------------------------------------------------------ #

    def build_index(self) -> None:
        self.logger.info(f"インデックス構築開始: {self.data_dir}")
        docs = self.dispatcher.parse_directory(self.data_dir)
        self.logger.info(f"  {len(docs)} チャンク取得")
        self.retriever.add(docs)
        self.logger.info("インデックス構築完了")

    # ------------------------------------------------------------------ #
    # 1問処理
    # ------------------------------------------------------------------ #

    def _process_one(self, qa: QAPair) -> PipelineResult:
        contexts = self.retriever.search(qa.question, top_k=self.top_k)
        answer: Answer = self.generator.generate(qa.question, contexts)

        if self.run_judge:
            reference = qa.reference_answer or "\n".join(
                sd.document.text[:300] for sd in contexts
            )
            judge_result: JudgeResult = self.judge.score(
                question=qa.question,
                generated_answer=answer.text,
                reference_or_context=reference,
            )
            judge_label = judge_result.label.value
            judge_score = judge_result.score
            judge_reason = judge_result.reason
        else:
            judge_label, judge_score, judge_reason = "", 0.0, ""

        return PipelineResult(
            question_id=qa.question_id,
            question=qa.question,
            answer=answer.text,
            confidence=answer.confidence,
            was_gated=answer.was_gated,
            judge_label=judge_label,
            judge_score=judge_score,
            judge_reason=judge_reason,
        )

    # ------------------------------------------------------------------ #
    # バッチ実行（非同期）
    # ------------------------------------------------------------------ #

    async def _process_one_async(self, qa: QAPair) -> PipelineResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._process_one, qa)

    async def run_async(self, qa_pairs: list[QAPair]) -> list[PipelineResult]:
        total = len(qa_pairs)
        self.logger.info(f"パイプライン開始: {total} 問")
        start = time.time()

        tasks = [self._process_one_async(qa) for qa in qa_pairs]
        raw_results = await run_with_semaphore(tasks, self.max_concurrent)

        results: list[PipelineResult] = []
        for i, r in enumerate(raw_results, 1):
            if isinstance(r, Exception):
                self.logger.error(f"Q{i} エラー: {r}")
            else:
                results.append(r)
                elapsed = time.time() - start
                remaining = estimate_remaining_time(i, total, elapsed)
                self.logger.debug(
                    f"[{i}/{total}] {r.judge_label} (conf={r.confidence:.2f}) "
                    f"残り推定 {remaining/60:.1f}分"
                )

        return results

    def run(self, qa_pairs: list[QAPair]) -> list[PipelineResult]:
        return asyncio.run(self.run_async(qa_pairs))

    # ------------------------------------------------------------------ #
    # 結果保存
    # ------------------------------------------------------------------ #

    def save_results(
        self,
        results: list[PipelineResult],
        out_dir: Path,
        run_name: str = "run",
    ) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        out_path = out_dir / f"{run_name}_{ts}.json"

        judge_results = []
        from src.models import CRAGLabel, JudgeResult
        for r in results:
            judge_results.append(JudgeResult(label=CRAGLabel(r.judge_label), reason=r.judge_reason))

        summary: EvalSummary = summarize(judge_results)

        payload = {
            "summary": {
                "mean_score": summary.mean_score,
                "total": summary.total,
                "label_counts": summary.label_counts,
            },
            "results": [asdict(r) for r in results],
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        self.logger.info(f"結果保存: {out_path}")
        self.logger.info("\n" + summary.report())
