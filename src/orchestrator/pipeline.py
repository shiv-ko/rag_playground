"""パイプライン本体。パース→インデックス→検索→生成→評価のループを非同期で回す。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from src.evaluator.judge import LocalJudge
from src.evaluator.metrics import EvalSummary, summarize
from src.generator.answer_generator import AnswerGenerator
from src.generator.analysis_answerer import AnalysisAnswerer
from src.generator.confidence_gate import MISSING_RESPONSE
from src.generator.contract_calc import ContractCalcAnswerer
from src.generator.enumeration_gate import is_enumeration_complete
from src.generator.milestone_date_answerer import (
    MilestoneDurationAnswerer,
    MilestoneThresholdListAnswerer,
)
from src.generator.office_chart import OfficeChartAnswerer
from src.generator.spreadsheet_calc import SpreadsheetCalcAnswerer
from src.generator.vlm_answerer import VLMImageAnswerer, find_referenced_image
from src.models import Answer, CRAGLabel, JudgeResult, ScoredDocument
from src.parsers.dispatcher import ParserDispatcher
from src.retriever.project_scoped_retriever import ProjectScopedRetriever
from src.retriever.query_expander import QueryExpander
from src.retriever.structured_context import (
    build_office_style_context,
    build_spreadsheet_state_context,
    build_version_diff_context,
    is_regression_prediction_request,
    question_mentions_spreadsheet,
)
from src.structured.artifact_store import StructuredArtifactStore
from src.utils.logging import setup_logging
from src.utils.parallel import estimate_remaining_time, run_with_semaphore
from src.utils.paths import to_repo_relative
from src.utils.question_classifier import classify_question

# 「〜を（すべて）抜き出す/抽出する」の動詞用法のみ抽出意図とみなす。
# 「抽出条件」のような名詞複合語（装飾内容の説明を求める質問）は含めない。
_STYLE_EXTRACTION_INTENT = re.compile(r"を(?:すべて|全て)?\s*(?:抜き出|抽出)")


def is_style_extraction_request(question: str) -> bool:
    return bool(_STYLE_EXTRACTION_INTENT.search(unicodedata.normalize("NFC", question)))


# office_style直接回答（装飾箇所の値を「、」連結して返す）の過剰列挙ガード。
# 実データ（questions_valid.csv等）で観測された正答の件数は1〜4件程度（例:
# 「hr、weekday、weathersit、temp」の4件、「1. データ理解・EDA」の1件）。
# 一方、抽出条件・絞り込みが破綻した場合は装飾条件を満たすマークが数百件単位で
# 混入する（実測: 375件・437件・646件）。桁が2つ以上違うため、閾値はどちらの
# 集団からも十分離れた20件に設定し、超過時は直接回答を諦めて既存のフォールバック
# （同じ構造化contextsをgenerate()に渡すLLM生成経路。ゲートで確信度不足なら
# Missingになる）に委ねる。
_DIRECT_OFFICE_STYLE_MAX_MATCHES = 20


def _requests_pivot_condition_and_aggregation(question: str) -> bool:
    normalized = unicodedata.normalize("NFC", question)
    has_superlative = any(
        term in normalized
        for term in ("最も高い", "最も多い", "最大", "最も低い", "最も少ない", "最小")
    )
    return (
        ("pivot" in normalized.casefold() or "ピボット" in normalized)
        and has_superlative
        and "抽出条件" in normalized
        and "集計内容" in normalized
    )


def _has_pivot_aggregate_context(contexts: list[ScoredDocument]) -> bool:
    return any(
        "_pivot_" in context.document.location
        and re.search(r"^集計:\s*.+$", context.document.text, re.MULTILINE)
        for context in contexts
    )


def _direct_pivot_condition_and_aggregation_answer(
    question: str, contexts: list[ScoredDocument]
) -> Answer | None:
    """機械抽出済みPivot集計から、条件・集計内容が完全な場合だけ直答する。"""
    want_max = any(term in question for term in ("最も高い", "最も多い", "最大"))
    want_min = any(term in question for term in ("最も低い", "最も少ない", "最小"))
    if want_max == want_min:
        return None
    direction = "最大" if want_max else "最小"

    answers: list[str] = []
    for context in contexts:
        text = context.document.text
        aggregate = re.search(r"^集計:\s*(.+?)（[^）]+）$", text, re.MULTILINE)
        group = re.search(
            rf"^{direction}のグループ:\s*(.+?)（値:\s*(.+?)）$", text, re.MULTILINE
        )
        if not aggregate or not group:
            continue
        labels, value = group.group(1).strip(), group.group(2).strip()
        if not labels or not value or value.casefold() in {"none", "null", "nan"}:
            continue
        answers.append(f"抽出条件: {labels}、集計内容: {aggregate.group(1).strip()}")

    if len(answers) != 1:
        return None
    return Answer(
        text=answers[0],
        confidence=0.95,
        source_docs=contexts,
        was_gated=False,
        raw_text=answers[0],
    )


# 回帰予測直接計算answerer用の解析ユーティリティ。
# build_spreadsheet_state_contextが埋め込む「切片: ...」「係数: name=val, ...」形式の
# docテキストを再パースする（既存の_direct_pivot_condition_and_aggregation_answerと
# 同じ「contextsのテキストを正規表現で読み戻す」設計パターン）。
_REGRESSION_INTERCEPT_RE = re.compile(r"^切片:\s*(.+)$", re.MULTILINE)
_REGRESSION_COEFFICIENTS_RE = re.compile(r"^係数:\s*(.+)$", re.MULTILINE)
# 質問文中の行指定（id=0 / index=1770 等）。全角=・全角数字はNFKC正規化後に吸収する。
_REGRESSION_ROW_SELECTOR_RE = re.compile(r"(id|index)\s*=\s*(\d+)", re.IGNORECASE)
# 「小数第5位まで」のような丸め桁指定。指定が無ければ出力フォーマットを確定できない
# ため直接回答しない（曖昧な丸めよりMissingを優先）。
_REGRESSION_DECIMAL_PLACES_RE = re.compile(r"小数第\s*(\d+)\s*位")


def _parse_regression_grid_from_contexts(
    contexts: list[ScoredDocument],
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for context in contexts:
        text = context.document.text
        intercept_m = _REGRESSION_INTERCEPT_RE.search(text)
        coef_m = _REGRESSION_COEFFICIENTS_RE.search(text)
        if not intercept_m or not coef_m:
            continue
        try:
            intercept = float(intercept_m.group(1).strip())
        except ValueError:
            continue
        coefficients: dict[str, float] = {}
        ok = True
        for part in coef_m.group(1).split(","):
            part = part.strip()
            if not part or "=" not in part:
                ok = False
                break
            name, raw_value = part.split("=", 1)
            try:
                coefficients[name.strip()] = float(raw_value.strip())
            except ValueError:
                ok = False
                break
        if not ok or not coefficients:
            continue
        matches.append({"intercept": intercept, "coefficients": coefficients})

    if len(matches) != 1:
        return None  # 回帰係数doc0件、または複数（曖昧）なら回答しない
    return matches[0]


def _extract_regression_row_selector(question: str) -> tuple[str, int] | None:
    normalized = unicodedata.normalize("NFKC", question)
    matches = _REGRESSION_ROW_SELECTOR_RE.findall(normalized)
    if len(matches) != 1:
        return None  # 指定なし、または複数の指定があり曖昧
    key, value = matches[0]
    return key.lower(), int(value)


def _extract_regression_decimal_places(question: str) -> int | None:
    matches = _REGRESSION_DECIMAL_PLACES_RE.findall(question)
    if len(matches) != 1:
        return None
    return int(matches[0])


def _select_regression_row(df, selector: tuple[str, int]):
    """selectorのキー("id"/"index")と同名の列がtrain.csvにあればその列の値一致で
    行を選ぶ。"index"指定で該当列が無い場合のみ、pandasの位置参照(0始まり)に
    フォールバックする（"id"指定で該当列が無い場合は位置参照との対応が不明なため
    フォールバックしない＝None）。一致行が0件/複数なら曖昧としてNone。"""
    key, value = selector
    matching_cols = [c for c in df.columns if str(c).strip().casefold() == key]
    if matching_cols:
        matched = df[df[matching_cols[0]] == value]
        if len(matched) != 1:
            return None
        return matched.iloc[0]
    if key == "index" and 0 <= value < len(df):
        return df.iloc[value]
    return None


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
    raw_answer: str = ""
    retrieved_sources: list[str] = field(default_factory=list)
    gate_reason: str = ""
    # 診断用の経路トレース。評価ラベルには依存せず、回答内容にも影響しない。
    routing_tags: list[str] = field(default_factory=list)
    answer_path: str = ""


class Pipeline:
    def __init__(
        self,
        data_dir: Path,
        max_concurrent: int = 5,
        top_k: int = 5,
        confidence_threshold: float = 0.4,
        run_judge: bool = True,
        project_aliases: dict[str, list[str]] | None = None,
        project_primary_aliases: dict[str, str] | None = None,
        term_registry: list[dict] | None = None,
        artifacts_dir: Path | None = None,
        cache_dir: Path | None = None,
        exclude_dirs: list[Path] | None = None,
        use_hybrid_search: bool = False,
    ) -> None:
        self.data_dir = data_dir
        self.max_concurrent = max_concurrent
        self.top_k = top_k
        self.run_judge = run_judge
        self.cache_dir = cache_dir
        # 評価用質問CSVのディレクトリ等、コーパスに含めてはいけない場所
        self.exclude_dirs = exclude_dirs
        self.logger = setup_logging()

        self.dispatcher = ParserDispatcher()
        self.embedder = None
        if use_hybrid_search:
            from src.indexer.embedder import CachedEmbedder, JapaneseEmbedder
            cache_path = (cache_dir / "embeddings_ruri-base.pkl") if cache_dir is not None else None
            self.embedder = CachedEmbedder(JapaneseEmbedder(), cache_path=cache_path)
        self.retriever = ProjectScopedRetriever(project_aliases=project_aliases, embedder=self.embedder)
        self.project_aliases = project_aliases or {}
        self.term_registry = term_registry or []
        self.project_primary_aliases = project_primary_aliases or {}
        self.query_expander = QueryExpander(self.term_registry)
        self.generator = AnswerGenerator(threshold=confidence_threshold)
        self.analysis_answerer = AnalysisAnswerer(data_dir=data_dir)
        self.judge = LocalJudge()
        self.structured_store = (
            StructuredArtifactStore.from_artifacts_dir(artifacts_dir) if artifacts_dir else None
        )
        self.spreadsheet_calc_answerer = SpreadsheetCalcAnswerer(threshold=confidence_threshold)
        self.contract_calc_answerer = ContractCalcAnswerer(
            threshold=confidence_threshold,
            data_dir=data_dir,
        )
        self.milestone_duration_answerer = MilestoneDurationAnswerer(threshold=confidence_threshold)
        self.milestone_threshold_list_answerer = MilestoneThresholdListAnswerer(
            threshold=confidence_threshold
        )
        self.office_chart_answerer = OfficeChartAnswerer(threshold=confidence_threshold)
        self.vlm_answerer = VLMImageAnswerer(threshold=confidence_threshold)

    # ------------------------------------------------------------------ #
    # インデックス構築
    # ------------------------------------------------------------------ #

    def build_index(self) -> None:
        self.logger.info(f"インデックス構築開始: {self.data_dir}")
        if self.cache_dir is not None:
            from src.utils.parse_cache import load_or_parse
            docs = load_or_parse(self.data_dir, self.cache_dir, exclude_dirs=self.exclude_dirs)
        else:
            docs = self.dispatcher.parse_directory(self.data_dir, exclude_dirs=self.exclude_dirs)
        self.logger.info(f"  {len(docs)} チャンク取得")
        if self.embedder is not None:
            from src.indexer import embedding_budget

            decision = embedding_budget.evaluate_embedding_budget(
                self.embedder, [d.text for d in docs]
            )
            if not decision.use_vectors:
                # embeddingは途中で安全に中断できないため、encode開始前に退避する
                # （cold indexが本番3時間制限を超えると全問スコア喪失になる）。
                self.logger.warning(
                    "embedding時間予算の見積もり超過のためBM25単体検索へ退避: "
                    f"未処理={decision.pending_count}件, "
                    f"推定={decision.estimated_seconds}秒, 理由={decision.reason}"
                )
                # probeで計算済みのembeddingはリトライ時に再利用できるよう永続化してから破棄する
                self.embedder.flush()
                self.embedder = None
                self.retriever = ProjectScopedRetriever(
                    project_aliases=self.project_aliases, embedder=None
                )
        self.retriever.add(docs)
        if self.embedder is not None:
            self.embedder.flush()
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

    def _process_structured(self, qa: QAPair, tags: list[str]) -> tuple[Answer, str] | None:
        if "ms_date_cross_project_list" in tags and self.structured_store is not None:
            # Q15型は単一案件に紐づかない横断質問のため、project_name解決より先に処理する
            list_answer = self.milestone_threshold_list_answerer.answer(
                qa.question, self.structured_store, self.project_primary_aliases
            )
            if not list_answer.was_gated:
                return list_answer, "structured:ms_date_cross_project_list"
            # 解決できなければMissing固定にせず後続のパスへ委ねる

        project_name = self._resolve_project_name(qa.question)
        if self.structured_store is not None and "contract_rule" in tags:
            contract_answer = self.contract_calc_answerer.answer(
                qa.question,
                project_name,
                self.structured_store,
                self.project_primary_aliases,
                self.project_aliases,
            )
            if not contract_answer.was_gated:
                return contract_answer, "structured:contract_rule"

        if self.structured_store is not None and "cross_project" in tags:
            # contract_ruleと異なり、cross_projectタグは横断集計問い専用のキーワード
            # （§1.1）で汎用語による誤タグ付けのリスクが低いため、Missing判定も
            # 「該当なし」ではなく最終回答として確定させる（generate()へのフォール
            # スルーは、確信のない生成LLMがIncorrectを出すリスクを再び持ち込むため禁止）。
            return self.contract_calc_answerer.answer(
                qa.question,
                project_name,
                self.structured_store,
                self.project_primary_aliases,
                self.project_aliases,
            ), "structured:cross_project"

        if project_name is None:
            return None

        if self.structured_store is not None and ({"analysis_json", "analysis_code", "analysis_notebook", "analysis_report"} & set(tags)):
            analysis_answer = self.analysis_answerer.answer(
                qa.question, project_name, self.structured_store
            )
            if analysis_answer is not None:
                return analysis_answer, "structured:analysis"

        if "image_or_graph" in tags:
            chart_answer = self.office_chart_answerer.answer(qa.question, project_name, self.data_dir)
            if not chart_answer.was_gated:
                return chart_answer, "structured:office_chart"
            # 抽出できなければMissing固定にせず後続のパス（VLM等）へ委ねる

        if "image_or_graph" in tags:
            image_path = find_referenced_image(qa.question, project_name, self.data_dir)
            if image_path is not None:
                vlm_answer = self.vlm_answerer.answer(qa.question, image_path)
                if not vlm_answer.was_gated:
                    return vlm_answer, "structured:vlm_image"
            # 画像が見つからない・VLMが確信を持てない場合はMissing固定にせず
            # 既存のimage_or_graph能力ブロック（安全側のMissing）へ委ねる

        if "spreadsheet_calc" in tags:
            df = self._load_train_csv(project_name)
            if df is not None:
                calc_answer = self.spreadsheet_calc_answerer.answer(qa.question, df)
                if not calc_answer.was_gated:
                    return calc_answer, "structured:spreadsheet_calc"
            # train.csvが無い・集計仕様に落とせなかった場合はMissing固定にせず
            # 後続の構造化ビルダー（state/office）→通常の検索パスへ委ねる
            # （calc早期returnがQ6/Q21型のPivot質問を殺していた実測に基づく）

        if "ms_date_duration" in tags and self.structured_store is not None:
            duration_answer = self.milestone_duration_answerer.answer(
                qa.question, project_name, self.structured_store, self.term_registry
            )
            if not duration_answer.was_gated:
                return duration_answer, "structured:ms_date_duration"
            # 解決できなければMissing固定にせず後続のパスへ委ねる

        if self.structured_store is None:
            return None

        # 「ハイライト」等のキーワードは両タグに付きうるため排他にせず、
        # 質問中のファイル種別ヒントで優先順を決め、空なら他方も試す
        pair = [
            ("office_style", build_office_style_context),
            ("spreadsheet_state", build_spreadsheet_state_context),
        ]
        if question_mentions_spreadsheet(qa.question):
            pair.reverse()
        # version_diffを先頭に置く: 新旧比較の明示的な言い回しでのみ付く狭いタグな上、
        # build_version_diff_context自体がペアを1つに絞れた時だけ非空を返す（絞れなければ[]で
        # 後続に委ねる）。一方spreadsheet_stateの schedule_tasks 照合は「未着手/完了」のような
        # 一般的なステータス語がそのまま質問文に含まれるだけで多数行にマッチしうるため、
        # xlsx新旧比較の質問（例:「スケジュール_r1.xlsxとスケジュール_r2.xlsxを比較したとき、
        # 未着手から完了への変更を除いて」）でspreadsheet_stateを先に試すと無関係な行が
        # 大量にヒットしてversion_diffが一度も呼ばれなくなる（実測: 44行 vs 正しいdiff1件）。
        builders = [("version_diff", build_version_diff_context)] + pair

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
        if used_tag == "office_style" and is_style_extraction_request(qa.question):
            direct = self._direct_office_style_answer(contexts)
            if direct is not None:
                return direct, "structured:office_style"
        if (
            used_tag == "spreadsheet_state"
            and _requests_pivot_condition_and_aggregation(qa.question)
        ):
            direct = _direct_pivot_condition_and_aggregation_answer(qa.question, contexts)
            if direct is not None:
                return direct, "structured:spreadsheet_state"
            if _has_pivot_aggregate_context(contexts):
                return Answer(
                    text=MISSING_RESPONSE,
                    confidence=0.0,
                    source_docs=contexts,
                    was_gated=True,
                    gate_reason="spreadsheet_state_incomplete",
                ), "structured:spreadsheet_state"
        if used_tag == "spreadsheet_state" and is_regression_prediction_request(qa.question):
            direct = self._direct_regression_prediction_answer(qa.question, contexts, project_name)
            if direct is not None:
                return direct, "structured:spreadsheet_state"
            # 係数・行指定・特徴量値・丸め桁のいずれかが欠ける/曖昧な場合はMissing固定にせず
            # 既存のgenerate()フォールバック（後続のゲートでMissingになりうる）へ委ねる
        return self.generator.generate(qa.question, contexts), f"structured:{used_tag}"

    def _direct_office_style_answer(self, contexts: list[ScoredDocument]) -> Answer | None:
        if len(contexts) > _DIRECT_OFFICE_STYLE_MAX_MATCHES:
            # 絞り込みが破綻して無関係なマークまで大量に混入しているサイン。
            # 誤った大量列挙（Incorrect）よりは、同じcontextsをgenerate()に渡す
            # 後続経路（ゲート経由でのMissing化を含む）に委ねる方が安全側。
            return None
        values = []
        for context in contexts:
            text = context.document.text
            match = re.search(r"装飾箇所（[^）]+）:\s*(.+)$", text)
            if not match:
                return None
            value = match.group(1).strip()
            if value:
                values.append(value)
        if not values:
            return None
        return Answer(
            text="、".join(values),
            confidence=0.95,
            source_docs=contexts,
            was_gated=False,
            raw_text="、".join(values),
        )

    def _direct_regression_prediction_answer(
        self, question: str, contexts: list[ScoredDocument], project_name: str
    ) -> Answer | None:
        """回帰分析シートの係数グリッド（build_spreadsheet_state_contextが埋め込んだ
        contextsのテキストから復元）＋train.csvの該当行から、予測値=切片+Σ(係数×特徴量値)
        をLLMを介さず直接計算する。必要な係数・行・特徴量値・丸め桁のいずれかが
        欠ける/曖昧な場合はNone（既存のgenerate()フォールバックへ委ねる）。"""
        grid = _parse_regression_grid_from_contexts(contexts)
        if grid is None:
            return None
        selector = _extract_regression_row_selector(question)
        if selector is None:
            return None
        decimals = _extract_regression_decimal_places(question)
        if decimals is None:
            return None
        df = self._load_train_csv(project_name)
        if df is None:
            return None
        row = _select_regression_row(df, selector)
        if row is None:
            return None

        import pandas as pd

        prediction = grid["intercept"]
        for feature, coef in grid["coefficients"].items():
            if feature not in row.index:
                return None
            value = row[feature]
            if pd.isna(value):
                return None
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                return None
            prediction += coef * numeric_value

        # Pythonのformat()はround-half-even（banker's rounding）だが、日本語の
        # 「小数第N位まで求めてください」という丸め指定は四捨字（ROUND_HALF_UP）を
        # 期待する（実測: f"{0.125:.2f}"→"0.12"だが四捨五入なら"0.13"）。CRAGは数値
        # 完全一致のみPerfectのため、丸め桁の次が5になる境界値でのズレはIncorrect
        # 直行のリスクがある。既存のsrc/generator/analysis_answerer.pyと同じ
        # Decimal+ROUND_HALF_UP方式に揃える。
        try:
            quantized = Decimal(str(prediction)).quantize(
                Decimal(f"1e-{decimals}"), rounding=ROUND_HALF_UP
            )
        except InvalidOperation:
            return None
        formatted = format(quantized, f".{decimals}f")
        return Answer(
            text=formatted,
            confidence=0.95,
            source_docs=contexts,
            was_gated=False,
            raw_text=formatted,
        )

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
                # Task 3で追加した供給源（autoFilter条件・Pivot小型シートセル）も
                # 候補プールに数える — 漏れると該当案件で完全性ゲートがpool=0棄却する
                + len(self.structured_store.train_xlsx_sheets_for(project_name))
                + len(self.structured_store.small_sheet_cells_for(project_name))
                + len(self.structured_store.pivot_aggregates_for(project_name))
            )
        if tag == "version_diff":
            return len(self.structured_store.version_diff_pairs_for(project_name))
        return 0

    def _process_one(self, qa: QAPair) -> PipelineResult:
        tags = classify_question(qa.question)
        answer = None
        answer_path = "retrieval"
        if any(
            t in tags
            for t in (
                "office_style",
                "spreadsheet_state",
                "spreadsheet_calc",
                "version_diff",
                "ms_date_duration",
                "ms_date_cross_project_list",
                "contract_rule",
                "cross_project",
                "image_or_graph",
                "analysis_json",
                "analysis_code",
                "analysis_notebook",
                "analysis_report",
            )
        ):
            structured_result = self._process_structured(qa, tags)
            if structured_result is not None:
                answer, answer_path = structured_result

        if answer is None:
            search_query = self.query_expander.expand_terms(qa.question)
            term_hints = self.query_expander.applied_expansions(qa.question)
            contexts = self.retriever.search(
                search_query, top_k=self.top_k, term_hints=term_hints
            )
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

        retrieved_sources = [
            f"{to_repo_relative(sd.document.source_path)}::{sd.document.location}"
            for sd in contexts
        ]
        return PipelineResult(
            question_id=qa.question_id,
            question=qa.question,
            answer=answer.text,
            confidence=answer.confidence,
            was_gated=answer.was_gated,
            judge_label=judge_label,
            judge_score=judge_score,
            judge_reason=judge_reason,
            raw_answer=answer.raw_text,
            retrieved_sources=retrieved_sources,
            gate_reason=answer.gate_reason,
            routing_tags=tags,
            answer_path=answer_path,
        )

    # ------------------------------------------------------------------ #
    # バッチ実行（非同期）
    # ------------------------------------------------------------------ #

    async def _process_one_async(self, qa: QAPair) -> PipelineResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._process_one, qa)

    def _missing_result_for_exception(self, qa: QAPair, error: Exception) -> PipelineResult:
        # 提出物は1問1行が前提のため、例外で行ごと消えるとpredictionsが壊れる。
        # judgeは呼ばずMissing相当を直接埋める（例外がAPI障害由来だと再度落ちうるため）。
        return PipelineResult(
            question_id=qa.question_id,
            question=qa.question,
            answer=MISSING_RESPONSE,
            confidence=0.0,
            was_gated=True,
            judge_label=CRAGLabel.MISSING.value if self.run_judge else "",
            judge_score=CRAGLabel.MISSING.score if self.run_judge else 0.0,
            judge_reason=f"question processing raised an exception: {error}",
            gate_reason="exception",
            routing_tags=classify_question(qa.question),
            answer_path="exception",
        )

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
                result = self._missing_result_for_exception(qa_pairs[i - 1], r)
            else:
                result = r
            results.append(result)
            elapsed = time.time() - start
            remaining = estimate_remaining_time(i, total, elapsed)
            self.logger.debug(
                f"[{i}/{total}] {result.judge_label} (conf={result.confidence:.2f}) "
                f"残り推定 {remaining/60:.1f}分"
            )

        self.last_elapsed = time.time() - start
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

        from src.models import CRAGLabel, JudgeResult
        # run_judge=False（診断run）ではjudge_labelが空なのでスコア集計をスキップする
        judged = [r for r in results if r.judge_label]
        if judged:
            judge_results = [
                JudgeResult(label=CRAGLabel(r.judge_label), reason=r.judge_reason)
                for r in judged
            ]
            summary: EvalSummary | None = summarize(judge_results)
        else:
            summary = None

        payload = {
            "summary": {
                "mean_score": summary.mean_score if summary else None,
                "total": summary.total if summary else len(results),
                "label_counts": summary.label_counts if summary else {},
                "elapsed_seconds": round(getattr(self, "last_elapsed", 0.0), 1),
                "generator_tokens": {
                    "input": self.generator.input_tokens,
                    "output": self.generator.output_tokens,
                },
                "judge_tokens": {
                    "input": self.judge.input_tokens,
                    "output": self.judge.output_tokens,
                },
                "models": {
                    "generator": os.environ.get("CLAUDE_MODEL", "claude-sonnet-5"),
                    "judge": os.environ.get("CLAUDE_JUDGE_MODEL", "claude-sonnet-5"),
                },
            },
            "results": [asdict(r) for r in results],
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        self.logger.info(f"結果保存: {out_path}")
        if summary:
            self.logger.info("\n" + summary.report())
