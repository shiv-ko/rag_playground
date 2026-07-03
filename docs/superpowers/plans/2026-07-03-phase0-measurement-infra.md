# Phase 0: 計測基盤 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「変更→valid 30問評価→flip確認」を数分＋既知コストで回せる計測基盤を作り、Missing 26問を「検索失敗/生成失敗/較正失敗」に機械的に切り分ける（`docs/plan/plan_0703.md` Phase 0）。

**Architecture:** 既存パイプライン（parse→BM25検索→生成→ゲート→judge）に (1) パース結果のディスクキャッシュ、(2) 実行結果への診断情報（検索ソース・ゲート前回答・所要時間・トークン数）の追加、(3) 検索単体評価（`question_labels.csv` の source_section × project_registry から機械的に正解候補ファイルを絞る）、(4) run間flip分析、(5) 本番同一プロンプトのOpenAI CRAGジャッジ、を足す。最後に valid 30問を再実行して切り分け表を生成する。

**Tech Stack:** Python 3.12 (`.venv/bin/python`), pytest, pickle キャッシュ, Anthropic API（生成・ローカルjudge）, OpenAI API（較正用judge, `gpt-5.2-2025-12-11`）

## Global Constraints

- 回答は1000トークン以内（`CLAUDE.md`）。本プランでは回答生成ロジックは変更しない。
- 特定の質問・案件・ファイルへのハードコード禁止（`competition.md` Rules）。正解候補ファイルの導出は `question_labels.csv` のメタデータ（source_section）と実行時構築の registry のみを使い、**回答生成には一切使わない**（評価専用スクリプトに限定する）。
- テストは決定的にする: LLM呼び出しは `_call_llm()` をサブクラスでオーバーライドして排除（`.claude/skills/dev-process.md` のFakeパターン）。
- すべてのテスト実行は `.venv/bin/pytest tests/ -v`。既存 約94件＋新規が全部通ること。
- 実験結果は `experiments/` にJSON保存。分析ドキュメントは `docs/plan/` に置く。
- コミットメッセージ末尾: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## 前提となる既存コードの事実（実装者向け）

- `Pipeline`（`src/orchestrator/pipeline.py`）: `build_index()` が `ParserDispatcher.parse_directory(data_dir)` → `ProjectScopedRetriever.add(docs)`。`_process_one()` が検索→生成→judge。結果は `PipelineResult` dataclass → `experiments/<run_name>_<ts>.json` に `{"summary": {...}, "results": [...]}` 形式で保存。
- `Answer`（`src/models.py`）: `text / confidence / source_docs / was_gated`。ゲートで落ちると `text` がMissing定型文に**置き換えられ、ゲート前の回答は失われる**（これがTask 2で直す点）。
- `ProjectScopedRetriever.search(query, top_k)` → `list[ScoredDocument]`。`ScoredDocument.document.source_path` は**絶対パス**、`document_registry.jsonl` の `source_path` は**リポジトリ相対**（例 `data/raw/share/共有ドライブ/プロジェクト/...`）。突合には正規化が必要。
- `docs/question_labels.csv`: 列 = `split,index,question,primary_type,secondary_types,source_section,answer_shape,risk,required_extractor,notes`。`source_section` は `;` 区切り複数可、`unknown` / `cross_project` という特殊値あり。valid 30行 / test 100行。
- `artifacts/project_registry.json`: `[{"project_name": "...", "aliases": ["KSS", ...], "sections": [...]}]`
- `artifacts/document_registry.jsonl`: 1行1ファイル。`source_path / project_name / section / file_name` 等。
- 正解回答: `data/raw/evaluation/data/valid_txt.csv`（**ヘッダなし** `index,answer`）。`data/raw/share/質問回答/questions_valid.csv`（ヘッダあり `index,question,answer`、BOM付き）。
- 本番judge実装: `data/raw/evaluation/src/evaluator.py` の `CRAGEvaluator._judge_by_crag`。システムプロンプトは ground_truth と answer のみ比較（**質問文を見ない**）。`temperature=0, seed=0`、json_schema強制。モデル `gpt-5.2-2025-12-11`。
- `.env` に `ANTHROPIC_API_KEY` と `OPENAI_API_KEY` が**両方ある**（judge較正は実施可能）。ただし `openai` パッケージは**未インストール**。
- データディレクトリ: パイプラインの対象は `data/raw/share/共有ドライブ`（この下に `プロジェクト/` と `社内管理/` がある）。`data/raw/share` を渡すと `質問回答/questions_*.csv` までインデックスされるので使わないこと。
- 最新のベースラインrun: `experiments/baseline_valid_1783069301.json`（mean 0.05, Missing 26 / Incorrect 1 / Acceptable 1 / Perfect 2）。

---

### Task 1: パース結果のディスクキャッシュ

30問評価のたびに416ファイルを再パースしているのをやめ、`data_dir` 配下のファイル構成（相対パス・mtime・サイズ）が変わらない限りpickleキャッシュを読む。

**Files:**
- Create: `src/utils/parse_cache.py`
- Create: `tests/test_parse_cache.py`
- Modify: `src/orchestrator/pipeline.py`（`__init__` と `build_index`）
- Modify: `scripts/run_pipeline.py`（`--no-cache` フラグ）
- Modify: `.gitignore`（`.cache/` を追加）

**Interfaces:**
- Consumes: `ParserDispatcher.parse_directory(directory: Path) -> list[Document]`
- Produces: `compute_fingerprint(data_dir: Path) -> str`、`load_or_parse(data_dir: Path, cache_dir: Path) -> list[Document]`。`Pipeline.__init__(..., cache_dir: Path | None = None)` — cache_dir指定時のみキャッシュ利用。Task 3・7 が `load_or_parse` を使う。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_parse_cache.py`:

```python
"""parse_cache のテスト。実パーサーは呼ばず、txtファイルで検証する。"""
from pathlib import Path

from src.utils.parse_cache import compute_fingerprint, load_or_parse


def _make_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.txt").write_text("こんにちは、テスト文書です。", encoding="utf-8")
    return data_dir


def test_fingerprint_stable(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    assert compute_fingerprint(data_dir) == compute_fingerprint(data_dir)


def test_fingerprint_changes_on_file_change(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    fp1 = compute_fingerprint(data_dir)
    (data_dir / "b.txt").write_text("新しいファイル", encoding="utf-8")
    assert compute_fingerprint(data_dir) != fp1


def test_load_or_parse_caches(tmp_path, monkeypatch):
    data_dir = _make_data_dir(tmp_path)
    cache_dir = tmp_path / "cache"

    docs1 = load_or_parse(data_dir, cache_dir)
    assert len(docs1) >= 1

    # 2回目はパーサーを呼ばずにキャッシュから返す
    import src.utils.parse_cache as pc

    def _boom(self, directory):
        raise AssertionError("キャッシュがあるのに再パースした")

    monkeypatch.setattr(pc.ParserDispatcher, "parse_directory", _boom)
    docs2 = load_or_parse(data_dir, cache_dir)
    assert [d.text for d in docs2] == [d.text for d in docs1]
    assert [str(d.source_path) for d in docs2] == [str(d.source_path) for d in docs1]


def test_load_or_parse_reparses_on_change(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    cache_dir = tmp_path / "cache"
    load_or_parse(data_dir, cache_dir)

    (data_dir / "b.txt").write_text("追加ファイル", encoding="utf-8")
    docs = load_or_parse(data_dir, cache_dir)
    assert any("追加ファイル" in d.text for d in docs)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_parse_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.utils.parse_cache'`

- [ ] **Step 3: 最小実装**

`src/utils/parse_cache.py`:

```python
"""パース＋チャンク結果のディスクキャッシュ。

data_dir 配下のファイル構成（相対パス・mtime・サイズ）が変わらない限り、
ParserDispatcher.parse_directory() を再実行せず pickle から復元する。
"""
from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

from src.models import Document
from src.parsers.dispatcher import ParserDispatcher


def compute_fingerprint(data_dir: Path) -> str:
    entries = []
    for p in sorted(data_dir.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        stat = p.stat()
        entries.append(f"{p.relative_to(data_dir)}|{stat.st_mtime_ns}|{stat.st_size}")
    digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return digest[:16]


def load_or_parse(data_dir: Path, cache_dir: Path) -> list[Document]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"parsed_{compute_fingerprint(data_dir)}.pkl"
    if cache_path.exists():
        return pickle.loads(cache_path.read_bytes())
    docs = ParserDispatcher().parse_directory(data_dir)
    cache_path.write_bytes(pickle.dumps(docs))
    return docs
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_parse_cache.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Pipeline と run_pipeline.py に配線**

`src/orchestrator/pipeline.py` の `__init__` シグネチャに `cache_dir` を追加:

```python
    def __init__(
        self,
        data_dir: Path,
        max_concurrent: int = 5,
        top_k: int = 5,
        confidence_threshold: float = 0.4,
        run_judge: bool = True,
        cache_dir: Path | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.max_concurrent = max_concurrent
        self.top_k = top_k
        self.run_judge = run_judge
        self.cache_dir = cache_dir
        self.logger = setup_logging()
```

`build_index` を差し替え:

```python
    def build_index(self) -> None:
        self.logger.info(f"インデックス構築開始: {self.data_dir}")
        if self.cache_dir is not None:
            from src.utils.parse_cache import load_or_parse
            docs = load_or_parse(self.data_dir, self.cache_dir)
        else:
            docs = self.dispatcher.parse_directory(self.data_dir)
        self.logger.info(f"  {len(docs)} チャンク取得")
        self.retriever.add(docs)
        self.logger.info("インデックス構築完了")
```

`scripts/run_pipeline.py`: argparse に `parser.add_argument("--no-cache", action="store_true", help="パース結果キャッシュを使わない")` を追加し、`Pipeline(...)` 生成を:

```python
    pipeline = Pipeline(
        data_dir=args.data_dir,
        max_concurrent=args.concurrent,
        top_k=args.top_k,
        confidence_threshold=args.threshold,
        cache_dir=None if args.no_cache else ROOT / ".cache",
    )
```

`.gitignore` に1行追加: `.cache/`

- [ ] **Step 6: 全テスト実行**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS（既存 約94件＋新規4件）

- [ ] **Step 7: Commit**

```bash
git add src/utils/parse_cache.py tests/test_parse_cache.py src/orchestrator/pipeline.py scripts/run_pipeline.py .gitignore
git commit -m "Phase0 Task1: パース結果のディスクキャッシュ（実験サイクル高速化）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: 実行結果への診断情報の追加（検索ソース・ゲート前回答・時間・トークン）

Missing切り分け（Task 6）に必要な情報を run JSON に残す。ゲートに落ちた場合もゲート前の生回答を保持し、どのチャンクが検索されたかを記録する。所要時間と消費トークンも summary に入れる（Phase 0 完了条件「既知コスト」の実測）。

**Files:**
- Create: `src/utils/paths.py`
- Modify: `src/models.py`（`Answer` に `raw_text` 追加）
- Modify: `src/generator/answer_generator.py`（`raw_text` 設定＋トークン集計）
- Modify: `src/evaluator/judge.py`（トークン集計）
- Modify: `src/orchestrator/pipeline.py`（`PipelineResult` 拡張・summary拡張）
- Test: `tests/test_generator.py`（追記）、`tests/test_pipeline.py`（追記）

**Interfaces:**
- Consumes: 既存の `Answer` / `PipelineResult` / `save_results`
- Produces:
  - `src.utils.paths.ROOT: Path`（リポジトリルート）と `to_repo_relative(path: Path) -> str`
  - `Answer.raw_text: str`（ゲート前のLLM回答。コンテキスト0件時は `""`）
  - `PipelineResult.raw_answer: str` / `PipelineResult.retrieved_sources: list[str]`（`"<repo相対パス>::<location>"` 形式）
  - run JSON の `summary` に `elapsed_seconds: float`, `generator_tokens: {"input": int, "output": int}`, `judge_tokens: {...}`, `models: {"generator": str, "judge": str}`
  - Task 6 の triage が `raw_answer` / `retrieved_sources` / `was_gated` を消費する

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_generator.py` に追記（既存のFakeパターンに合わせる。既存importを確認しつつ）:

```python
def test_gated_answer_keeps_raw_text():
    """ゲートで落ちてもゲート前の回答が raw_text に残る。"""
    from src.generator.answer_generator import AnswerGenerator
    from src.models import Document, ScoredDocument

    class FakeGen(AnswerGenerator):
        def _call_llm(self, question, context):
            return '{"answer": "生の回答", "confidence": 0.1, "reasoning": "低確信"}'

    gen = FakeGen(threshold=0.4)
    doc = ScoredDocument(
        document=Document(text="本文", source_path=Path("dummy.txt")), score=1.0
    )
    ans = gen.generate("質問", [doc])
    assert ans.was_gated is True
    assert ans.raw_text == "生の回答"


def test_ungated_answer_raw_text_equals_text():
    from src.generator.answer_generator import AnswerGenerator
    from src.models import Document, ScoredDocument

    class FakeGen(AnswerGenerator):
        def _call_llm(self, question, context):
            return '{"answer": "採用された回答", "confidence": 0.9, "reasoning": "高確信"}'

    gen = FakeGen(threshold=0.4)
    doc = ScoredDocument(
        document=Document(text="本文", source_path=Path("dummy.txt")), score=1.0
    )
    ans = gen.generate("質問", [doc])
    assert ans.was_gated is False
    assert ans.raw_text == ans.text == "採用された回答"
```

（`from pathlib import Path` が既存importになければ足す）

`tests/test_pipeline.py` に追記。既存のE2EスモークテストのFake構成（mock Anthropicクライアント）を確認し、それに倣って `PipelineResult` の新フィールドを検証するテストを追加する:

```python
def test_pipeline_result_has_diagnostics(tmp_path):
    """runの結果に raw_answer / retrieved_sources が入り、summaryに時間・トークンが入る。"""
    # 既存のE2Eスモークテストと同じ Fake/mock 構成でパイプラインを組み、
    # save_results 後のJSONを読んで以下を確認する:
    # - results[0] に "raw_answer" キーと "retrieved_sources" キーがある
    # - retrieved_sources の各要素は "::" を含む文字列
    # - summary に "elapsed_seconds" / "generator_tokens" / "judge_tokens" / "models" がある
```

（具体的なFake構成は既存 `tests/test_pipeline.py` のE2Eスモークテストをコピーして流用する。アサーション部分だけ上記の通り）

`tests/test_parse_cache.py` の隣に paths のテストも足す（新規 `tests/test_paths.py`）:

```python
from pathlib import Path

from src.utils.paths import ROOT, to_repo_relative


def test_root_is_repo_root():
    assert (ROOT / "CLAUDE.md").exists()


def test_to_repo_relative_inside():
    p = ROOT / "data" / "raw" / "x.txt"
    assert to_repo_relative(p) == "data/raw/x.txt"


def test_to_repo_relative_outside_returns_str():
    assert to_repo_relative(Path("/etc/hosts")) == "/etc/hosts"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_paths.py tests/test_generator.py tests/test_pipeline.py -v`
Expected: 新規テストがFAIL（`No module named 'src.utils.paths'`、`raw_text` AttributeError 等）

- [ ] **Step 3: 実装**

`src/utils/paths.py`:

```python
"""リポジトリルート基準のパス正規化。document_registry.jsonl のsource_path（repo相対）との突合に使う。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def to_repo_relative(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)
```

`src/models.py` の `Answer` に1フィールド追加:

```python
@dataclass
class Answer:
    text: str
    confidence: float          # 0.0〜1.0
    source_docs: list[ScoredDocument] = field(default_factory=list)
    was_gated: bool = False    # 確信度ゲートによってMissingになった場合True
    raw_text: str = ""         # ゲート適用前のLLM回答（切り分け分析用）
```

`src/generator/answer_generator.py` の `generate` を修正（ゲート分岐と正常系の両方で `raw_text` を渡す）:

```python
        # 確信度ゲート
        if not self.gate.should_answer(confidence):
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
```

トークン集計: `AnswerGenerator.__init__` に追加:

```python
        self.input_tokens = 0
        self.output_tokens = 0
        self._usage_lock = threading.Lock()
```

（ファイル先頭に `import threading`）。`_call_llm` の `return` 直前に:

```python
        if message.usage is not None:
            with self._usage_lock:
                self.input_tokens += message.usage.input_tokens
                self.output_tokens += message.usage.output_tokens
```

`src/evaluator/judge.py` の `LocalJudge` にも同じパターンで `input_tokens` / `output_tokens` / `_usage_lock` を追加（`__init__` と `_call_llm`）。

`src/orchestrator/pipeline.py`:

`PipelineResult` に2フィールド追加:

```python
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
```

（`from dataclasses import asdict, dataclass, field` に `field` を足す）

`_process_one` の return を:

```python
        from src.utils.paths import to_repo_relative

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
        )
```

（importはファイル先頭にまとめて移してよい）

`run_async` の冒頭 `start = time.time()` の結果を使い、末尾で `self.last_elapsed = time.time() - start` を保存。`save_results` の `payload["summary"]` を:

```python
        import os
        payload = {
            "summary": {
                "mean_score": summary.mean_score,
                "total": summary.total,
                "label_counts": summary.label_counts,
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS。既存テストが `Answer` / `PipelineResult` のフィールド追加で壊れていないこと（デフォルト値付き追加なので壊れないはず。壊れたら該当テストのアサーションを確認）

- [ ] **Step 5: Commit**

```bash
git add src/utils/paths.py src/models.py src/generator/answer_generator.py src/evaluator/judge.py src/orchestrator/pipeline.py tests/test_paths.py tests/test_generator.py tests/test_pipeline.py
git commit -m "Phase0 Task2: run結果に検索ソース・ゲート前回答・時間・トークン数を記録

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 検索単体評価（retrieval recall）

質問ごとに「正解根拠ファイル候補」を `question_labels.csv` の source_section × project_registry のエイリアス照合で機械的に絞り、retriever の top-k にその候補が入ったかを判定する。LLMを呼ばないので無料・高速。

**Files:**
- Create: `src/evaluator/retrieval_eval.py`
- Create: `tests/test_retrieval_eval.py`
- Create: `scripts/eval_retrieval.py`

**Interfaces:**
- Consumes: `ProjectScopedRetriever.search(query, top_k) -> list[ScoredDocument]`、`load_or_parse`（Task 1）、`to_repo_relative`（Task 2）、`docs/question_labels.csv`、`artifacts/project_registry.json`、`artifacts/document_registry.jsonl`
- Produces:
  - `QuestionLabel` dataclass（`split, index, question, primary_type, source_section: list[str]`）
  - `load_labels(path: Path, split: str) -> list[QuestionLabel]`
  - `resolve_projects(question: str, project_registry: list[dict]) -> list[str]`
  - `CandidateSet` dataclass（`measurable: bool, files: frozenset[str], reason: str`）
  - `candidate_files(label: QuestionLabel, doc_registry: list[dict], project_registry: list[dict]) -> CandidateSet`
  - `RetrievalRecord` dataclass（`question_id, primary_type, measurable, hit, first_hit_rank, retrieved: list[str], candidate_count`）
  - `evaluate_one(search_fn, label, cand, top_k) -> RetrievalRecord`
  - `summarize_records(records: list[RetrievalRecord]) -> str`（タイプ別recallのmarkdown表）
  - 出力JSON: `experiments/retrieval_<split>_<ts>.json` = `{"summary": {"recall": float, "measurable": int, "total": int, "by_type": {...}}, "records": [...]}`。Task 6 の triage が `records` の `measurable` / `hit` を消費する

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_retrieval_eval.py`:

```python
"""retrieval_eval の純粋関数テスト。実データ・実インデックスは使わない。"""
from pathlib import Path

from src.evaluator.retrieval_eval import (
    CandidateSet,
    QuestionLabel,
    candidate_files,
    evaluate_one,
    load_labels,
    resolve_projects,
    summarize_records,
)
from src.models import Document, ScoredDocument

PROJECT_REGISTRY = [
    {"project_name": "株式会社東都人材プラットフォーム",
     "aliases": ["TOTO", "東都", "東都人材プラットフォーム", "株式会社東都人材プラットフォーム"]},
    {"project_name": "京橋信用ソリューションズ株式会社",
     "aliases": ["KSS", "京橋", "京橋信用ソリューションズ"]},
]

DOC_REGISTRY = [
    {"source_path": "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/00.提案/提案書.pptx",
     "project_name": "株式会社東都人材プラットフォーム", "section": "00.提案"},
    {"source_path": "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/06.報告書/最終報告書.pptx",
     "project_name": "株式会社東都人材プラットフォーム", "section": "06.報告書"},
    {"source_path": "data/raw/share/共有ドライブ/プロジェクト/京橋信用ソリューションズ株式会社/06.報告書/最終報告書.pptx",
     "project_name": "京橋信用ソリューションズ株式会社", "section": "06.報告書"},
]


def _label(question, section, index="0"):
    return QuestionLabel(split="valid", index=index, question=question,
                         primary_type="single_text",
                         source_section=section.split(";") if section else [])


def test_load_labels(tmp_path):
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text(
        "split,index,question,primary_type,secondary_types,source_section,"
        "answer_shape,risk,required_extractor,notes\n"
        "valid,0,質問A,single_text,,06.報告書,single_text,low,text_retriever,x\n"
        "valid,1,質問B,internal_terms,list_extraction,02.計画;06.報告書,list,high,term_registry,x\n"
        "test,0,質問C,single_text,,unknown,single_text,low,text_retriever,x\n",
        encoding="utf-8",
    )
    labels = load_labels(csv_path, split="valid")
    assert len(labels) == 2
    assert labels[1].source_section == ["02.計画", "06.報告書"]


def test_resolve_projects_alias():
    assert resolve_projects("TOTOのPLについて", PROJECT_REGISTRY) == ["株式会社東都人材プラットフォーム"]
    assert resolve_projects("東都人材プラットフォームの提案書", PROJECT_REGISTRY) == ["株式会社東都人材プラットフォーム"]
    assert resolve_projects("該当なしの質問", PROJECT_REGISTRY) == []


def test_candidate_files_project_and_section():
    label = _label("東都の最終報告書について", "06.報告書")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)
    assert cand.measurable is True
    assert cand.files == frozenset({
        "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/06.報告書/最終報告書.pptx"
    })


def test_candidate_files_section_only():
    """案件が特定できなくてもセクションがあれば全案件の該当セクションが候補。"""
    label = _label("すべての最終報告書を確認", "06.報告書")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)
    assert cand.measurable is True
    assert len(cand.files) == 2


def test_candidate_files_unmeasurable():
    label = _label("全案件の消費税合計は", "cross_project")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)
    assert cand.measurable is False


def test_candidate_files_unknown_section_with_project():
    """sectionがunknownでも案件が特定できれば案件全ファイルが候補。"""
    label = _label("東都の何か", "unknown")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)
    assert cand.measurable is True
    assert len(cand.files) == 2  # 東都の2ファイル


def test_evaluate_one_hit_and_rank():
    label = _label("東都の最終報告書について", "06.報告書")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)

    from src.utils.paths import ROOT
    hit_path = ROOT / "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/06.報告書/最終報告書.pptx"
    miss_path = ROOT / "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/00.提案/提案書.pptx"

    def fake_search(query, top_k):
        return [
            ScoredDocument(document=Document(text="x", source_path=miss_path), score=2.0),
            ScoredDocument(document=Document(text="y", source_path=hit_path), score=1.0),
        ]

    rec = evaluate_one(fake_search, label, cand, top_k=5)
    assert rec.hit is True
    assert rec.first_hit_rank == 2


def test_evaluate_one_miss():
    label = _label("京橋の最終報告書", "06.報告書")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)

    from src.utils.paths import ROOT
    other = ROOT / "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/00.提案/提案書.pptx"

    def fake_search(query, top_k):
        return [ScoredDocument(document=Document(text="x", source_path=other), score=1.0)]

    rec = evaluate_one(fake_search, label, cand, top_k=5)
    assert rec.hit is False
    assert rec.first_hit_rank == 0


def test_summarize_records_contains_type_table():
    label = _label("東都の最終報告書について", "06.報告書")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)

    def fake_search(query, top_k):
        return []

    rec = evaluate_one(fake_search, label, cand, top_k=5)
    text = summarize_records([rec])
    assert "single_text" in text
    assert "0/1" in text or "0.0" in text
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_retrieval_eval.py -v`
Expected: FAIL — `No module named 'src.evaluator.retrieval_eval'`

- [ ] **Step 3: 実装**

`src/evaluator/retrieval_eval.py`:

```python
"""検索単体評価（retrieval recall）。

question_labels.csv の source_section と project_registry のエイリアス照合から
「正解根拠ファイル候補」を機械的に導出し、retriever の top-k にその候補が
入ったかを判定する。LLMは呼ばない。

注意: このモジュールは評価専用。回答生成パスから import してはならない
（question_labels.csv は人手ラベルであり、回答生成に使うと規約違反になる）。
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from src.models import ScoredDocument
from src.utils.paths import to_repo_relative

_UNSPECIFIC_SECTIONS = {"unknown", "cross_project", ""}


@dataclass
class QuestionLabel:
    split: str
    index: str
    question: str
    primary_type: str
    source_section: list[str]


def load_labels(path: Path, split: str) -> list[QuestionLabel]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] == split]
    return [
        QuestionLabel(
            split=r["split"],
            index=r["index"],
            question=r["question"],
            primary_type=r["primary_type"],
            source_section=[s for s in r["source_section"].split(";") if s],
        )
        for r in rows
    ]


def resolve_projects(question: str, project_registry: list[dict]) -> list[str]:
    hits = []
    for proj in project_registry:
        if any(alias in question for alias in proj["aliases"]):
            hits.append(proj["project_name"])
    return hits


@dataclass
class CandidateSet:
    measurable: bool
    files: frozenset[str]
    reason: str = ""


def candidate_files(
    label: QuestionLabel,
    doc_registry: list[dict],
    project_registry: list[dict],
) -> CandidateSet:
    projects = resolve_projects(label.question, project_registry)
    sections = [s for s in label.source_section if s not in _UNSPECIFIC_SECTIONS]

    if not projects and not sections:
        return CandidateSet(
            measurable=False, files=frozenset(),
            reason="案件もセクションも機械特定できない（cross_project等）",
        )

    files = set()
    for entry in doc_registry:
        if projects and entry.get("project_name") not in projects:
            continue
        if sections and entry.get("section") not in sections:
            continue
        files.add(entry["source_path"])

    if not files:
        return CandidateSet(measurable=False, files=frozenset(), reason="候補0件")
    return CandidateSet(measurable=True, files=frozenset(files))


@dataclass
class RetrievalRecord:
    question_id: str
    primary_type: str
    measurable: bool
    hit: bool
    first_hit_rank: int  # 1始まり。ヒットなしは0
    retrieved: list[str]
    candidate_count: int
    reason: str = ""


SearchFn = Callable[[str, int], list[ScoredDocument]]


def evaluate_one(
    search_fn: SearchFn,
    label: QuestionLabel,
    cand: CandidateSet,
    top_k: int,
) -> RetrievalRecord:
    retrieved = search_fn(label.question, top_k)
    sources = [to_repo_relative(sd.document.source_path) for sd in retrieved]
    first_hit_rank = 0
    for rank, src in enumerate(sources, 1):
        if src in cand.files:
            first_hit_rank = rank
            break
    return RetrievalRecord(
        question_id=label.index,
        primary_type=label.primary_type,
        measurable=cand.measurable,
        hit=first_hit_rank > 0,
        first_hit_rank=first_hit_rank,
        retrieved=sources,
        candidate_count=len(cand.files),
        reason=cand.reason,
    )


def summarize_records(records: list[RetrievalRecord]) -> str:
    measurable = [r for r in records if r.measurable]
    by_type: dict[str, list[RetrievalRecord]] = defaultdict(list)
    for r in measurable:
        by_type[r.primary_type].append(r)

    lines = [
        f"計測可能: {len(measurable)}/{len(records)}問",
    ]
    if measurable:
        hits = sum(r.hit for r in measurable)
        lines.append(f"recall@top-k: {hits}/{len(measurable)} ({100 * hits / len(measurable):.0f}%)")
    lines.append("")
    lines.append("| primary_type | recall | hit/計測可能 |")
    lines.append("|---|---|---|")
    for ptype in sorted(by_type):
        recs = by_type[ptype]
        hits = sum(r.hit for r in recs)
        lines.append(f"| {ptype} | {100 * hits / len(recs):.0f}% | {hits}/{len(recs)} |")
    return "\n".join(lines)


def records_to_payload(records: list[RetrievalRecord]) -> dict:
    measurable = [r for r in records if r.measurable]
    by_type: dict[str, dict] = {}
    for ptype in sorted({r.primary_type for r in measurable}):
        recs = [r for r in measurable if r.primary_type == ptype]
        by_type[ptype] = {"hit": sum(r.hit for r in recs), "measurable": len(recs)}
    return {
        "summary": {
            "recall": (sum(r.hit for r in measurable) / len(measurable)) if measurable else 0.0,
            "measurable": len(measurable),
            "total": len(records),
            "by_type": by_type,
        },
        "records": [asdict(r) for r in records],
    }
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_retrieval_eval.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: 実行スクリプトを書く**

`scripts/eval_retrieval.py`:

```python
"""検索単体評価スクリプト。実インデックスを組み、valid質問のretrieval recallを出す。

LLMは呼ばないため無料。パース結果はキャッシュされる（Task 1）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluator.retrieval_eval import (
    candidate_files,
    evaluate_one,
    load_labels,
    records_to_payload,
    summarize_records,
)
from src.retriever.project_scoped_retriever import ProjectScopedRetriever
from src.utils.parse_cache import load_or_parse


def main() -> None:
    parser = argparse.ArgumentParser(description="retrieval recall 評価")
    parser.add_argument("--data-dir", type=Path,
                        default=ROOT / "data" / "raw" / "share" / "共有ドライブ")
    parser.add_argument("--labels", type=Path, default=ROOT / "docs" / "question_labels.csv")
    parser.add_argument("--split", default="valid")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments")
    args = parser.parse_args()

    docs = load_or_parse(args.data_dir, ROOT / ".cache")
    retriever = ProjectScopedRetriever()
    retriever.add(docs)

    labels = load_labels(args.labels, split=args.split)
    doc_registry = [
        json.loads(line)
        for line in (ROOT / "artifacts" / "document_registry.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    project_registry = json.loads(
        (ROOT / "artifacts" / "project_registry.json").read_text(encoding="utf-8")
    )

    records = []
    for label in labels:
        cand = candidate_files(label, doc_registry, project_registry)
        records.append(evaluate_one(retriever.search, label, cand, top_k=args.top_k))

    print(summarize_records(records))
    misses = [r for r in records if r.measurable and not r.hit]
    if misses:
        print("\n[検索失敗（候補ファイルがtop-kに無い）]")
        for r in misses:
            print(f"  {args.split}#{r.question_id} ({r.primary_type}) 候補{r.candidate_count}件")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"retrieval_{args.split}_{int(time.time())}.json"
    out_path.write_text(
        json.dumps(records_to_payload(records), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n結果保存: {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 実データで実行して動作確認**

Run: `.venv/bin/python scripts/eval_retrieval.py`
Expected: 初回はパースに数分かかる（キャッシュ生成）。タイプ別recall表が表示され、`experiments/retrieval_valid_<ts>.json` が生成される。2回目の実行はインデックス構築が数秒で終わることを確認（キャッシュ効果の実測）。実行時間を控えておく（Task 7 で使う）。

- [ ] **Step 7: 全テスト＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/evaluator/retrieval_eval.py tests/test_retrieval_eval.py scripts/eval_retrieval.py
git commit -m "Phase0 Task3: retrieval recall 単体評価（正解候補ファイルの機械導出＋top-kヒット判定）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: flip分析（run間差分）

2つの run JSON を突き合わせ、質問ごとのラベル遷移（改善/悪化/不変）とスコア差分を出す。`scripts/run_eval.py` を拡張。

**Files:**
- Create: `src/evaluator/flip.py`
- Create: `tests/test_flip.py`
- Modify: `scripts/run_eval.py`

**Interfaces:**
- Consumes: run JSON の `{"summary": ..., "results": [{"question_id", "question", "judge_label", ...}]}` 形式
- Produces: `compare_runs(base: dict, new: dict, base_name: str, new_name: str) -> FlipReport`。`FlipReport` は `improved / worsened / unchanged_count / base_mean / new_mean` を持ち、`report() -> str` で人間可読の表を返す

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_flip.py`:

```python
from src.evaluator.flip import compare_runs


def _run(labels: dict[str, str]) -> dict:
    return {
        "summary": {},
        "results": [
            {"question_id": qid, "question": f"質問{qid}", "judge_label": label,
             "answer": "回答"}
            for qid, label in labels.items()
        ],
    }


def test_compare_runs_detects_flips():
    base = _run({"0": "Missing", "1": "Perfect", "2": "Incorrect", "3": "Missing"})
    new = _run({"0": "Perfect", "1": "Missing", "2": "Incorrect", "3": "Missing"})
    rep = compare_runs(base, new, base_name="base", new_name="new")

    assert [f["question_id"] for f in rep.improved] == ["0"]
    assert [f["question_id"] for f in rep.worsened] == ["1"]
    assert rep.unchanged_count == 2
    assert rep.base_mean == (0 + 1 - 1 + 0) / 4
    assert rep.new_mean == (1 + 0 - 1 + 0) / 4


def test_compare_runs_handles_missing_ids():
    """片方にしか無いquestion_idは無視（共通部分のみ比較）。"""
    base = _run({"0": "Missing", "9": "Perfect"})
    new = _run({"0": "Perfect"})
    rep = compare_runs(base, new)
    assert [f["question_id"] for f in rep.improved] == ["0"]
    assert rep.unchanged_count == 0


def test_report_is_readable():
    base = _run({"0": "Missing"})
    new = _run({"0": "Perfect"})
    text = compare_runs(base, new).report()
    assert "Missing" in text and "Perfect" in text and "0" in text
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_flip.py -v`
Expected: FAIL — `No module named 'src.evaluator.flip'`

- [ ] **Step 3: 実装**

`src/evaluator/flip.py`:

```python
"""run間flip分析。前回runとの差分（改善/悪化した問題）を出す。"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.models import CRAGLabel


def _score(label: str) -> float:
    try:
        return CRAGLabel(label).score
    except ValueError:
        return 0.0


@dataclass
class FlipReport:
    base_name: str
    new_name: str
    base_mean: float
    new_mean: float
    improved: list[dict] = field(default_factory=list)
    worsened: list[dict] = field(default_factory=list)
    unchanged_count: int = 0

    def report(self) -> str:
        lines = [
            f"=== flip分析: {self.base_name} → {self.new_name} ===",
            f"mean: {self.base_mean:.4f} → {self.new_mean:.4f} "
            f"({self.new_mean - self.base_mean:+.4f})",
            f"改善 {len(self.improved)} / 悪化 {len(self.worsened)} / 不変 {self.unchanged_count}",
        ]
        if self.improved:
            lines.append("\n[改善]")
            for f in self.improved:
                lines.append(f"  {f['question_id']}: {f['base_label']} → {f['new_label']}  {f['question'][:50]}")
        if self.worsened:
            lines.append("\n[悪化]")
            for f in self.worsened:
                lines.append(f"  {f['question_id']}: {f['base_label']} → {f['new_label']}  {f['question'][:50]}")
                lines.append(f"    新回答: {f.get('new_answer', '')[:80]}")
        return "\n".join(lines)


def compare_runs(
    base: dict, new: dict, base_name: str = "base", new_name: str = "new"
) -> FlipReport:
    base_by_id = {r["question_id"]: r for r in base["results"]}
    new_by_id = {r["question_id"]: r for r in new["results"]}
    common_ids = [qid for qid in base_by_id if qid in new_by_id]

    base_scores = [_score(base_by_id[q]["judge_label"]) for q in common_ids]
    new_scores = [_score(new_by_id[q]["judge_label"]) for q in common_ids]

    report = FlipReport(
        base_name=base_name,
        new_name=new_name,
        base_mean=sum(base_scores) / len(base_scores) if base_scores else 0.0,
        new_mean=sum(new_scores) / len(new_scores) if new_scores else 0.0,
    )

    for qid in common_ids:
        b, n = base_by_id[qid], new_by_id[qid]
        bs, ns = _score(b["judge_label"]), _score(n["judge_label"])
        entry = {
            "question_id": qid,
            "question": n["question"],
            "base_label": b["judge_label"],
            "new_label": n["judge_label"],
            "new_answer": n.get("answer", ""),
        }
        if ns > bs:
            report.improved.append(entry)
        elif ns < bs:
            report.worsened.append(entry)
        else:
            report.unchanged_count += 1
    return report
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_flip.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: run_eval.py に配線**

`scripts/run_eval.py` を全面書き換え:

```python
"""実験結果JSONの再集計＋run間flip分析。

使い方:
  .venv/bin/python scripts/run_eval.py                # 全run集計＋最新2runのflip
  .venv/bin/python scripts/run_eval.py A.json B.json  # 指定2runのflip（A=base, B=new）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluator.flip import compare_runs
from src.evaluator.metrics import summarize
from src.models import CRAGLabel, JudgeResult


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _print_summary(path: Path, data: dict) -> None:
    results = [
        JudgeResult(label=CRAGLabel(r["judge_label"]), reason=r["judge_reason"])
        for r in data["results"]
        if r["judge_label"]
    ]
    print(f"\n=== {path.name} ===")
    print(summarize(results).report())

    incorrects = [r for r in data["results"] if r["judge_label"] == "Incorrect"]
    if incorrects:
        print(f"\n[要分析: Incorrect {len(incorrects)}件]")
        for r in incorrects:
            print(f"  {r['question_id']}: {r['question'][:60]}")
            print(f"    -> {r['answer'][:80]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="実験結果の集計とflip分析")
    parser.add_argument("runs", nargs="*", type=Path,
                        help="比較する2つのrun JSON（省略時は全run集計＋最新2runのflip）")
    args = parser.parse_args()

    if len(args.runs) == 2:
        base_path, new_path = args.runs
    elif len(args.runs) == 0:
        # retrieval_*.json などpipeline以外の結果は除外する
        candidates = sorted(
            p for p in (ROOT / "experiments").glob("*.json")
            if not p.name.startswith(("retrieval_", "judge_calibration_"))
        )
        if not candidates:
            print("experiments/ に結果ファイルがありません。run_pipeline.py を先に実行してください。")
            return
        for path in candidates:
            _print_summary(path, _load(path))
        if len(candidates) < 2:
            return
        base_path, new_path = sorted(candidates, key=lambda p: p.stat().st_mtime)[-2:]
    else:
        parser.error("run JSONは0個か2個で指定してください")

    base, new = _load(base_path), _load(new_path)
    if len(args.runs) == 2:
        _print_summary(base_path, base)
        _print_summary(new_path, new)
    print()
    print(compare_runs(base, new, base_name=base_path.name, new_name=new_path.name).report())


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 実データで動作確認**

Run: `.venv/bin/python scripts/run_eval.py experiments/baseline_valid_1783063973.json experiments/baseline_valid_1783069301.json`
Expected: 両runのサマリと flip分析（改善/悪化/不変）が表示される

- [ ] **Step 7: 全テスト＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/evaluator/flip.py tests/test_flip.py scripts/run_eval.py
git commit -m "Phase0 Task4: run間flip分析（改善/悪化した問題の差分出力）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: 本番同一プロンプトのOpenAI CRAGジャッジ＋較正スクリプト

本番評価（`data/raw/evaluation/src/evaluator.py`）と同一のシステムプロンプト・モデル・`temperature=0, seed=0`・json_schema でジャッジする `OpenAICragJudge` を作り、既存runのローカルjudge結果との乖離表を出す。LB -0.067 とローカル 0.05 の乖離解釈に使う。

**Files:**
- Create: `src/evaluator/openai_judge.py`
- Create: `tests/test_openai_judge.py`
- Create: `scripts/calibrate_judge.py`
- Modify: `pyproject.toml`（dependencies に `openai` 追加）

**Interfaces:**
- Consumes: run JSON の `results`（`question_id`, `answer`, `judge_label`）、正解 `data/raw/evaluation/data/valid_txt.csv`（ヘッダなし `index,answer`）
- Produces: `OpenAICragJudge(model: str = "gpt-5.2-2025-12-11")` with `score(generated_answer: str, ground_truth: str) -> JudgeResult`。`_call_llm(system_prompt, user_prompt) -> str` はテストでオーバーライド可能。出力: `experiments/judge_calibration_<ts>.json` と乖離表の標準出力

- [ ] **Step 1: openai パッケージを入れる**

```bash
.venv/bin/pip install openai
```

`pyproject.toml` の `dependencies` 配列に `"openai"` を追加（既存の書式に合わせる）。

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_openai_judge.py`:

```python
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
```

- [ ] **Step 3: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_openai_judge.py -v`
Expected: FAIL — `No module named 'src.evaluator.openai_judge'`

- [ ] **Step 4: 実装**

`src/evaluator/openai_judge.py`。`OFFICIAL_SYSTEM_PROMPT` は `data/raw/evaluation/src/evaluator.py` の `_judge_by_crag` 内の `system_prompt` を**インデントごと一字一句コピー**すること（先頭・末尾の改行や全角スペース含む。判定の再現性に直結する）:

```python
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
```

- [ ] **Step 5: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_openai_judge.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: 較正スクリプトを書く**

`scripts/calibrate_judge.py`:

```python
"""judge較正: 既存runの回答を本番同一プロンプトのOpenAI CRAGジャッジで再採点し、
ローカルClaude judgeとの乖離表を出す。

使い方:
  .venv/bin/python scripts/calibrate_judge.py experiments/baseline_valid_XXXX.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.evaluator.openai_judge import OpenAICragJudge
from src.models import CRAGLabel


def load_ground_truth(path: Path) -> dict[str, str]:
    """valid_txt.csv（ヘッダなし index,answer）を読む。"""
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {row[0]: row[1] for row in csv.reader(f) if row}


def main() -> None:
    parser = argparse.ArgumentParser(description="ローカルjudgeとOpenAI CRAG judgeの較正")
    parser.add_argument("run_json", type=Path, help="対象run（experiments/*.json）")
    parser.add_argument("--answers", type=Path,
                        default=ROOT / "data" / "raw" / "evaluation" / "data" / "valid_txt.csv")
    parser.add_argument("--model", default="gpt-5.2-2025-12-11")
    args = parser.parse_args()

    run = json.loads(args.run_json.read_text(encoding="utf-8"))
    truth = load_ground_truth(args.answers)
    judge = OpenAICragJudge(model=args.model)

    rows = []
    for r in run["results"]:
        gt = truth.get(r["question_id"])
        if gt is None:
            print(f"警告: 正解なし question_id={r['question_id']}")
            continue
        official = judge.score(generated_answer=r["answer"], ground_truth=gt)
        rows.append({
            "question_id": r["question_id"],
            "question": r["question"],
            "answer": r["answer"],
            "ground_truth": gt,
            "local_label": r["judge_label"],
            "official_label": official.label.value,
            "official_score": official.score,
        })
        print(f"  {r['question_id']}: local={r['judge_label']:>10} / official={official.label.value}")

    official_mean = sum(row["official_score"] for row in rows) / len(rows)
    local_mean = sum(CRAGLabel(row["local_label"]).score for row in rows) / len(rows)
    agree = sum(row["local_label"] == row["official_label"] for row in rows)

    print(f"\n=== 較正結果 ({args.run_json.name}, {len(rows)}問) ===")
    print(f"official mean: {official_mean:.4f} / local mean: {local_mean:.4f}")
    print(f"一致率: {agree}/{len(rows)} ({100 * agree / len(rows):.0f}%)")

    matrix = Counter((row["local_label"], row["official_label"]) for row in rows)
    print("\n[乖離マトリクス local → official]")
    for (local, official), count in sorted(matrix.items()):
        marker = "" if local == official else "  ← 乖離"
        print(f"  {local:>10} → {official:<10} {count}件{marker}")

    out_path = ROOT / "experiments" / f"judge_calibration_{int(time.time())}.json"
    out_path.write_text(json.dumps({
        "run": args.run_json.name,
        "model": args.model,
        "official_mean": official_mean,
        "local_mean": local_mean,
        "agreement": agree / len(rows),
        "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n結果保存: {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: 実データで実行**

Run: `.venv/bin/python scripts/calibrate_judge.py experiments/baseline_valid_1783069301.json`
Expected: 30問分の local/official ラベル比較、一致率、乖離マトリクスが表示され `experiments/judge_calibration_<ts>.json` が保存される。
（注意: OpenAI APIを30回呼ぶ。`gpt-5.2-2025-12-11` へのアクセス権が無い等で失敗したら、エラーメッセージを記録し `--model` で代替モデルを試すか、このStepをスキップして Task 7 の切り分けでは LocalJudge を使う。**モデル名を勝手に別物へ差し替えて「較正完了」と報告しないこと**——本番と同一モデルでない結果はその旨を明記する）

- [ ] **Step 8: 全テスト＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/evaluator/openai_judge.py tests/test_openai_judge.py scripts/calibrate_judge.py pyproject.toml
git commit -m "Phase0 Task5: 本番同一プロンプトのOpenAI CRAGジャッジとjudge較正スクリプト

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Missing切り分けロジック（triage）

run JSON（Task 2 の診断情報付き）× retrieval eval JSON（Task 3）× 正解回答を突き合わせ、各問を「OK / 検索失敗 / 生成失敗 / 較正失敗(過剰ゲート) / 較正失敗(ゲート素通り) / 計測不能」に分類する。

**Files:**
- Create: `src/evaluator/triage.py`
- Create: `tests/test_triage.py`
- Create: `scripts/triage_failures.py`

**Interfaces:**
- Consumes: run JSON の `results[]`（`judge_label`, `was_gated`, `raw_answer`, `retrieved_sources`）、retrieval JSON の `records[]`（`question_id`, `measurable`, `hit`）、`OpenAICragJudge.score`（ゲート前回答の正誤判定用）
- Produces: `classify(judge_label: str, was_gated: bool, measurable: bool, hit: bool, raw_judge_label: str | None) -> str`（分類定数 `CLASS_OK` 等を同モジュールで定義）、`needs_raw_judge(judge_label, was_gated, measurable, hit, raw_answer) -> bool`。スクリプト出力: `docs/plan/missing_triage_<YYYYMMDD>.md`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_triage.py`:

```python
from src.evaluator.triage import (
    CLASS_CALIBRATION_OVERGATE,
    CLASS_CALIBRATION_PASSTHROUGH,
    CLASS_GENERATION,
    CLASS_OK,
    CLASS_RETRIEVAL,
    CLASS_UNMEASURABLE,
    classify,
    needs_raw_judge,
)


def test_ok():
    assert classify("Perfect", False, True, True, None) == CLASS_OK
    assert classify("Acceptable", False, True, True, None) == CLASS_OK


def test_unmeasurable():
    assert classify("Missing", True, False, False, None) == CLASS_UNMEASURABLE


def test_retrieval_failure():
    assert classify("Missing", True, True, False, None) == CLASS_RETRIEVAL


def test_calibration_overgate():
    """検索は当たり、ゲート前回答も正しいのにゲートで落とした。"""
    assert classify("Missing", True, True, True, "Perfect") == CLASS_CALIBRATION_OVERGATE
    assert classify("Missing", True, True, True, "Acceptable") == CLASS_CALIBRATION_OVERGATE


def test_generation_failure_gated_wrong_raw():
    """検索は当たったがゲート前回答も間違っていた。"""
    assert classify("Missing", True, True, True, "Incorrect") == CLASS_GENERATION
    assert classify("Missing", True, True, True, "Missing") == CLASS_GENERATION


def test_generation_failure_refused():
    """ゲートは通ったのにLLMが「わかりません」と答えた。"""
    assert classify("Missing", False, True, True, None) == CLASS_GENERATION


def test_calibration_passthrough():
    """間違った回答がゲートを素通りしてIncorrectになった。"""
    assert classify("Incorrect", False, True, True, None) == CLASS_CALIBRATION_PASSTHROUGH


def test_needs_raw_judge():
    """ゲート落ち＋検索ヒット＋生回答ありの場合だけ生回答judgeが要る。"""
    assert needs_raw_judge("Missing", True, True, True, "生回答") is True
    assert needs_raw_judge("Missing", True, True, True, "") is False
    assert needs_raw_judge("Missing", True, True, False, "生回答") is False
    assert needs_raw_judge("Perfect", False, True, True, "生回答") is False
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_triage.py -v`
Expected: FAIL — `No module named 'src.evaluator.triage'`

- [ ] **Step 3: 実装**

`src/evaluator/triage.py`:

```python
"""失敗切り分け（triage）: 各問を検索失敗/生成失敗/較正失敗に分類する。

plan_0703.md §2 の3類型:
1. 検索失敗 — 正解候補ファイルがtop-kに入っていない
2. 生成失敗 — 根拠はあるのにLLMが答えない/間違える
3. 較正失敗 — 正しく答えたのにゲートで落ちた（過剰ゲート）、
              または間違いがゲートを通った（素通り）
"""
from __future__ import annotations

CLASS_OK = "OK"
CLASS_RETRIEVAL = "検索失敗"
CLASS_GENERATION = "生成失敗"
CLASS_CALIBRATION_OVERGATE = "較正失敗(過剰ゲート)"
CLASS_CALIBRATION_PASSTHROUGH = "較正失敗(ゲート素通り)"
CLASS_UNMEASURABLE = "計測不能(手動確認)"

_GOOD_LABELS = ("Perfect", "Acceptable")


def classify(
    judge_label: str,
    was_gated: bool,
    measurable: bool,
    hit: bool,
    raw_judge_label: str | None,
) -> str:
    if judge_label in _GOOD_LABELS:
        return CLASS_OK
    if not measurable:
        return CLASS_UNMEASURABLE
    if not hit:
        return CLASS_RETRIEVAL
    if was_gated:
        if raw_judge_label in _GOOD_LABELS:
            return CLASS_CALIBRATION_OVERGATE
        return CLASS_GENERATION
    if judge_label == "Incorrect":
        return CLASS_CALIBRATION_PASSTHROUGH
    return CLASS_GENERATION


def needs_raw_judge(
    judge_label: str,
    was_gated: bool,
    measurable: bool,
    hit: bool,
    raw_answer: str,
) -> bool:
    """ゲート前回答のjudgeが分類に必要なケースか（API節約のため必要時のみ呼ぶ）。"""
    return (
        judge_label not in _GOOD_LABELS
        and was_gated
        and measurable
        and hit
        and bool(raw_answer.strip())
    )
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_triage.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: スクリプトを書く**

`scripts/triage_failures.py`:

```python
"""Missing切り分け表の生成。

run JSON（raw_answer/retrieved_sources付き・Task 2以降のrun）と
retrieval eval JSON（Task 3）を突き合わせ、各問を分類して
docs/plan/missing_triage_<YYYYMMDD>.md に書き出す。

使い方:
  .venv/bin/python scripts/triage_failures.py \
      experiments/phase0_valid_XXXX.json experiments/retrieval_valid_YYYY.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.evaluator.triage import classify, needs_raw_judge


def load_ground_truth(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {row[0]: row[1] for row in csv.reader(f) if row}


def load_label_types(path: Path, split: str) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {
            r["index"]: r["primary_type"]
            for r in csv.DictReader(f)
            if r["split"] == split
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="失敗切り分け表の生成")
    parser.add_argument("run_json", type=Path)
    parser.add_argument("retrieval_json", type=Path)
    parser.add_argument("--answers", type=Path,
                        default=ROOT / "data" / "raw" / "evaluation" / "data" / "valid_txt.csv")
    parser.add_argument("--labels", type=Path, default=ROOT / "docs" / "question_labels.csv")
    parser.add_argument("--split", default="valid")
    parser.add_argument("--judge", choices=["openai", "local", "none"], default="openai",
                        help="ゲート前回答の正誤判定に使うjudge")
    args = parser.parse_args()

    run = json.loads(args.run_json.read_text(encoding="utf-8"))
    retrieval = json.loads(args.retrieval_json.read_text(encoding="utf-8"))
    truth = load_ground_truth(args.answers)
    types = load_label_types(args.labels, args.split)
    ret_by_id = {r["question_id"]: r for r in retrieval["records"]}

    raw_judge = None
    if args.judge == "openai":
        from src.evaluator.openai_judge import OpenAICragJudge
        raw_judge = OpenAICragJudge()
    elif args.judge == "local":
        from src.evaluator.judge import LocalJudge
        local = LocalJudge()
        class _Wrapper:
            def score(self, generated_answer, ground_truth):
                return local.score(question="", generated_answer=generated_answer,
                                   reference_or_context=ground_truth)
        raw_judge = _Wrapper()

    rows = []
    for r in run["results"]:
        qid = r["question_id"]
        ret = ret_by_id.get(qid, {"measurable": False, "hit": False})
        raw_label = None
        if raw_judge is not None and needs_raw_judge(
            r["judge_label"], r["was_gated"], ret["measurable"], ret["hit"],
            r.get("raw_answer", ""),
        ):
            gt = truth.get(qid, "")
            raw_label = raw_judge.score(
                generated_answer=r["raw_answer"], ground_truth=gt
            ).label.value

        cls = classify(r["judge_label"], r["was_gated"], ret["measurable"],
                       ret["hit"], raw_label)
        rows.append({
            "question_id": qid,
            "primary_type": types.get(qid, "?"),
            "judge_label": r["judge_label"],
            "hit": ret["hit"],
            "was_gated": r["was_gated"],
            "raw_judge_label": raw_label or "-",
            "class": cls,
            "question": r["question"],
        })
        print(f"  {qid}: {cls} ({types.get(qid, '?')})")

    counts = Counter(row["class"] for row in rows)

    lines = [
        f"# valid 失敗切り分け表（{date.today().isoformat()}）",
        "",
        f"run: `{args.run_json.name}` / retrieval: `{args.retrieval_json.name}` / raw判定judge: {args.judge}",
        "",
        "## 集計",
        "",
        "| 分類 | 件数 |",
        "|---|---|",
    ]
    for cls, count in counts.most_common():
        lines.append(f"| {cls} | {count} |")
    lines += [
        "",
        "## 質問別",
        "",
        "| # | type | 最終label | 検索hit | gated | 生回答判定 | 分類 | 質問 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['question_id']} | {row['primary_type']} | {row['judge_label']} "
            f"| {'○' if row['hit'] else '×'} | {'○' if row['was_gated'] else '-'} "
            f"| {row['raw_judge_label']} | {row['class']} | {row['question'][:40]} |"
        )

    out_path = ROOT / "docs" / "plan" / f"missing_triage_{date.today().strftime('%Y%m%d')}.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n分類集計: {dict(counts)}")
    print(f"切り分け表: {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 全テスト＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/evaluator/triage.py tests/test_triage.py scripts/triage_failures.py
git commit -m "Phase0 Task6: 失敗切り分け（検索/生成/較正）のtriageロジックとスクリプト

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: E2E実行 — valid 30問再実行・切り分け表生成・plan_0703.md 更新

コードは全部揃ったので、実データ・実APIで一連を回し、Phase 0 の成果物（切り分け表・較正表・サイクルタイム実測）を作る。**このタスクはAPIコストが発生する**（Anthropic: 生成30問＋judge30問＋ゲート前判定数問 / OpenAI: 較正30問＋triage数問）。

**Files:**
- Create: `experiments/phase0_valid_<ts>.json`（パイプライン出力）
- Create: `experiments/retrieval_valid_<ts>.json`（Task 3 で未生成なら）
- Create: `docs/plan/missing_triage_<YYYYMMDD>.md`
- Modify: `docs/plan/plan_0703.md`（§2 に結果を追記）

**Interfaces:**
- Consumes: Task 1〜6 の全成果物
- Produces: Phase 0 完了条件の充足（「変更→30問評価→flip確認が数分＋既知コストで回る」「切り分け表が存在する」）

- [ ] **Step 1: valid 30問をフルパイプラインで再実行（診断情報付き）**

```bash
time .venv/bin/python scripts/run_pipeline.py \
  --data-dir "data/raw/share/共有ドライブ" \
  --questions "data/raw/share/質問回答/questions_valid.csv" \
  --run-name phase0_valid
```

Expected: `experiments/phase0_valid_<ts>.json` が生成される。`summary` に `elapsed_seconds` / `generator_tokens` / `judge_tokens` / `models` が入っていること。`results[]` に `raw_answer` / `retrieved_sources` が入っていること。wall time を控える（2回目以降=キャッシュありのインデックス構築時間も別途control: 事前に Task 3 Step 6 でキャッシュ生成済みのはず）。

- [ ] **Step 2: 前回ベースラインとのflip確認**

```bash
.venv/bin/python scripts/run_eval.py experiments/baseline_valid_1783069301.json experiments/phase0_valid_<ts>.json
```

Expected: flip分析が出る。コード変更は診断情報の追加だけなのでラベルはほぼ不変のはず（LLMの揺らぎによる±1〜2問は許容。**悪化が3問以上あれば原因を調べてから進む**）。

- [ ] **Step 3: retrieval recall 評価（未実行なら）＋judge較正（Task 5 Step 7 未実行なら）**

```bash
.venv/bin/python scripts/eval_retrieval.py
.venv/bin/python scripts/calibrate_judge.py experiments/phase0_valid_<ts>.json
```

- [ ] **Step 4: 切り分け表の生成**

```bash
.venv/bin/python scripts/triage_failures.py \
  experiments/phase0_valid_<ts>.json experiments/retrieval_valid_<ts>.json
```

（OpenAIが使えない場合は `--judge local` にフォールバック）
Expected: `docs/plan/missing_triage_<YYYYMMDD>.md` が生成され、Missing 26問＋Incorrect 1問が「検索失敗/生成失敗/較正失敗/計測不能」に分類されている。

- [ ] **Step 5: plan_0703.md の §2 に実測結果を追記**

`docs/plan/plan_0703.md` の §2 末尾に、以下のテンプレートで実測値を埋めて追記する:

```markdown
### 2.1 実測結果（YYYY-MM-DD, Phase 0 完了時点）

切り分け表: [`missing_triage_YYYYMMDD.md`](missing_triage_YYYYMMDD.md)

| 分類 | 件数 | 対応フェーズ |
|---|---|---|
| 検索失敗 | N | Phase 1（チャンク・検索の修正） |
| 生成失敗 | N | Phase 1（生成プロンプト調整） |
| 較正失敗(過剰ゲート) | N | Phase 1（タイプ別ゲート） |
| 較正失敗(ゲート素通り) | N | Phase 1（タイプ別ゲート） |
| 計測不能(手動確認) | N | 個別確認 |

- retrieval recall（計測可能N問）: XX%（タイプ別は retrieval_valid_<ts>.json 参照）
- judge較正: official (gpt-5.2) mean X.XX vs local mean X.XX、一致率 XX%（LB乖離の解釈: …）
- 実験サイクル実測: 30問フル評価 約X分 / トークン: 生成 in X out X, judge in X out X（≒$X.XX）
- Phase 1 優先度への影響: （検索失敗が支配的なら §3 Phase 1 の記述通り。違えば修正内容をここに書く）
```

- [ ] **Step 6: 最終確認＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add experiments/ docs/plan/
git commit -m "Phase0 Task7: valid30問の失敗切り分け表・judge較正・サイクルタイム実測

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review 済みの注意点（実装者向け）

1. **パス突合が最頻出バグ**: `document_registry.jsonl` の `source_path` はrepo相対、パイプライン内の `Document.source_path` は絶対。突合は必ず `to_repo_relative()`（Task 2）経由で行う。Task 3 のテストが `ROOT` 基準の絶対パスでfake documentを作っているのはこのため。
2. **valid_txt.csv はヘッダなし**（`0,hr、weekday…` で始まる）。`questions_valid.csv` はヘッダあり・BOM付き。ローダーを混同しない。
3. **question_labels.csv は評価専用**。回答生成パス（`src/generator/`, `src/orchestrator/` の生成側, `src/retriever/`）から import したら規約違反（人手ラベルの回答利用）。評価スクリプト・分析のみで使う。
4. **OFFICIAL_SYSTEM_PROMPT は一字一句コピー**。整形・翻訳・要約をしない。
5. Task 2 の `Answer` / `PipelineResult` 変更はデフォルト値付き追加なので既存テストを壊さない想定だが、`asdict` でJSONに新キーが増える。既存runとの flip 比較（Task 4）は `judge_label` しか見ないので互換。
6. 実行系タスク（Task 3 Step 6, Task 5 Step 7, Task 7）はAPIキー・実データ前提。失敗時はエラーを記録して代替（--judge local 等）へ。**結果の捏造・「たぶん動く」報告は禁止**（verification-before-completion）。
