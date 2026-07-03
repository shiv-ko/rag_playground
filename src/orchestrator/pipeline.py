"""パイプライン本体。パース→インデックス→検索→生成→評価のループを非同期で回す。"""
from __future__ import annotations

import asyncio
import json
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from src.evaluator.judge import LocalJudge
from src.evaluator.metrics import EvalSummary, summarize
from src.generator.answer_generator import AnswerGenerator
from src.generator.enumeration_gate import is_enumeration_complete
from src.generator.spreadsheet_calc import SpreadsheetCalcAnswerer
from src.models import Answer, JudgeResult, ScoredDocument
from src.parsers.dispatcher import ParserDispatcher
from src.retriever.project_scoped_retriever import ProjectScopedRetriever
from src.retriever.query_expander import QueryExpander
from src.retriever.structured_context import (
    build_office_style_context,
    build_spreadsheet_state_context,
    question_mentions_spreadsheet,
)
from src.structured.artifact_store import StructuredArtifactStore
from src.utils.logging import setup_logging
from src.utils.parallel import estimate_remaining_time, run_with_semaphore
from src.utils.question_classifier import classify_question


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
        project_aliases: dict[str, list[str]] | None = None,
        term_registry: list[dict] | None = None,
        artifacts_dir: Path | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.max_concurrent = max_concurrent
        self.top_k = top_k
        self.run_judge = run_judge
        self.logger = setup_logging()

        self.dispatcher = ParserDispatcher()
        self.retriever = ProjectScopedRetriever(project_aliases=project_aliases)
        self.query_expander = QueryExpander(term_registry or [])
        self.generator = AnswerGenerator(threshold=confidence_threshold)
        self.judge = LocalJudge()
        self.structured_store = (
            StructuredArtifactStore.from_artifacts_dir(artifacts_dir) if artifacts_dir else None
        )
        self.spreadsheet_calc_answerer = SpreadsheetCalcAnswerer(threshold=confidence_threshold)

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

    def _resolve_project_name(self, question: str) -> str | None:
        project = self.retriever.detect_project(question)
        if project is not None:
            return project
        if self.structured_store is None:
            return None
        normalized_question = unicodedata.normalize("NFC", question)
        for name in self.structured_store.project_names():
            if name and unicodedata.normalize("NFC", name) in normalized_question:
                return name
        return None

    def _load_train_csv(self, project_name: str):
        import pandas as pd

        # 案件名にマッチしないtrain.csvは使わない（別案件のデータで計算するとIncorrect直行）。
        # macOSのパスはNFDになりうるためNFCに揃えて比較する。
        normalized_project = unicodedata.normalize("NFC", project_name)
        matching = sorted(
            p for p in self.data_dir.rglob("train.csv")
            if normalized_project in unicodedata.normalize("NFC", str(p))
        )
        if not matching:
            return None
        try:
            return pd.read_csv(matching[0])
        except Exception:
            return None

    def _process_structured(self, qa: QAPair, tags: list[str]) -> Answer | None:
        project_name = self._resolve_project_name(qa.question)
        if project_name is None:
            return None

        if "spreadsheet_calc" in tags:
            df = self._load_train_csv(project_name)
            if df is None:
                return None
            calc_answer = self.spreadsheet_calc_answerer.answer(qa.question, df)
            # 集計仕様に落とせなかった質問はMissing固定にせず通常の検索パスへ委ねる
            return None if calc_answer.was_gated else calc_answer

        if self.structured_store is None:
            return None

        # 「ハイライト」等のキーワードは両タグに付きうるため排他にせず、
        # 質問中のファイル種別ヒントで優先順を決め、空なら他方も試す
        builders = [
            ("office_style", build_office_style_context),
            ("spreadsheet_state", build_spreadsheet_state_context),
        ]
        if question_mentions_spreadsheet(qa.question):
            builders.reverse()

        contexts: list[ScoredDocument] = []
        used_tag = ""
        for tag, builder in builders:
            if tag in tags:
                contexts = builder(qa.question, project_name, self.structured_store)
                if contexts:
                    used_tag = tag
                    break

        if not contexts:
            return None
        # 完全性ゲート: 構造化パスはartifacts全件をコードで走査するため、走査した
        # 候補プールが非空でマッチが取れていれば「条件に該当する全件」を渡せている。
        # プール件数は実際に走査した対象から取る（マッチ件数の写しにしない）。
        pool_size = self._structured_pool_size(used_tag, project_name)
        if not is_enumeration_complete(len(contexts), pool_size, "structured_attribute_filter"):
            return None
        return self.generator.generate(qa.question, contexts)

    def _structured_pool_size(self, tag: str, project_name: str) -> int:
        if self.structured_store is None:
            return 0
        if tag == "office_style":
            return len(self.structured_store.office_marks_for(project_name))
        if tag == "spreadsheet_state":
            return (
                len(self.structured_store.train_xlsx_highlight_blocks_for(project_name))
                + len(self.structured_store.spreadsheet_sheets_for(project_name))
                + len(self.structured_store.schedule_tasks_for(project_name))
            )
        return 0

    def _process_one(self, qa: QAPair) -> PipelineResult:
        tags = classify_question(qa.question)
        answer = None
        if any(t in tags for t in ("office_style", "spreadsheet_state", "spreadsheet_calc")):
            answer = self._process_structured(qa, tags)

        if answer is None:
            search_query = self.query_expander.expand_terms(qa.question)
            contexts = self.retriever.search(search_query, top_k=self.top_k)
            answer = self.generator.generate(qa.question, contexts)
        else:
            contexts = answer.source_docs

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
