# Phase 1（守り強化＋レジストリ接続） Codex実装計画

> **実行者向け:** これはCodex CLI（またはこのリポジトリで作業する別のAIコーディングエージェント）にそのまま渡す自己完結型のタスク指示書です。superpowers系のスキルには依存しません。タスクは**上から順番に**実行し、各タスクの最後で `.venv/bin/pytest tests/ -v` を実行して**全件PASS**することを確認してからコミットしてください。1タスク＝1コミット。疑問点があれば実装を進める前に確認すること（推測でコードを変えない）。

**Goal:** `docs/plan/plan_0703.md` Phase 1 の「守り」2項目（タイプ別確信度ゲート・根拠引用の強制）と「攻め（土台）」のうち2項目（term/project registryのクエリ処理接続・生成プロンプト調整）を実装する。Phase 1 の残り1項目「チャンク・検索の修正」はPhase 0の検索失敗切り分け結果が出てから着手する別スコープであり、**本計画には含まない**。

**Architecture:** `src/generator/answer_generator.py` の `AnswerGenerator.generate()` に、(1) 設問タイプ別の確信度ゲート、(2) 根拠引用の実在チェック、(3) 「わかりません」自己申告と確信度の矛盾を機械的に潰す安全網、を追加する。あわせて `src/retriever/project_scoped_retriever.py` と新設の `src/retriever/query_expander.py` で、`artifacts/project_registry.json` / `artifacts/term_registry.json`（実行時にdata/raw内の実データから生成される、案件名・略称・社内用語のレジストリ）をクエリ処理に接続する。

**Tech Stack:** Python 3.11+ (`.venv/bin/python`), pytest, 既存のFakeサブクラスパターン（LLM呼び出しを排除してテストを決定的にする）。

## 前提（重要・着手前に必ず確認）

1. **本計画は commit `8ceb314`（`main`）を基点にしています。** このコミットには「社内用語集.docxから案件エイリアス・用語辞書を実行時に抽出する」修正（`scripts/build_registries.py`, `src/utils/glossary.py`）と、Unicode正規化バグ修正（`src/retriever/project_scoped_retriever.py` の NFD/NFC）が含まれます。`git log --oneline -1` でこのコミット以降にいることを確認してから着手してください。
2. **Phase 0（計測基盤: `docs/superpowers/plans/2026-07-03-phase0-measurement-infra.md`）が別のエージェントによって並行して進んでいる可能性があります。** Phase 0は `src/models.py`（`Answer.raw_text` 追加）・`src/generator/answer_generator.py`・`src/orchestrator/pipeline.py`（`PipelineResult` にフィールド追加、`cache_dir` 引数追加）に**フィールド追加のみ**の変更を加えます。本計画とのコード上の意味的な衝突はない設計ですが、着手前に **`main` の現状（`git log`, 該当ファイルの中身）を確認し**、もしPhase 0が既にマージされていて本計画のコード例と行番号や周辺コードが一致しない場合は、差分の意図（何をどう変えるか）を保ったまま実際のファイルに合わせて適用してください。判断に迷う場合は先に進まず人間に確認すること。
3. 着手前に `.venv/bin/pytest tests/ -v` を実行し、全件PASSすることを確認する（ベースライン確認）。

## Global Constraints

- **回答は1000トークン以内**（`CLAUDE.md`）。`MAX_CHARS_APPROX` truncation ロジックは変更しない。
- **ハードコード禁止**（`competition.md`）: 特定の案件名・ファイル名・質問文をキーにした分岐を書かない。案件名・略称・社内用語などのデータは必ず `artifacts/*.json`（`scripts/build_registries.py` が実データから実行時生成）経由で読み込む。新しい辞書やマッピングをコードに手入力しない。
- テストは決定的にする: LLM呼び出しは `_call_llm()` をサブクラスでオーバーライドして排除する（`FakeGenerator` パターン、`tests/test_generator.py` 参照）。
- すべてのテスト実行は `.venv/bin/pytest tests/ -v`。各タスック完了時点で全件PASSを維持すること（既存150件＋新規分）。
- 実装は日本語コメント・docstringのスタイルを既存コードに合わせる。
- コミットメッセージは変更内容の要約を日本語で書く。末尾のCo-Authored-Byトレーラーは、使用しているツール自身の規約に従う（Claude用の "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" をそのまま流用しないこと）。

## 前提となる既存コードの事実（実装者向け）

- `AnswerGenerator.generate(question, contexts)`（`src/generator/answer_generator.py`）: contextsが空なら即Missing。`_call_llm`→`_parse_response`→`ConfidenceGate.should_answer(confidence)`でゲート→通過したら`MAX_CHARS_APPROX`で切り詰めて返す。
- `ConfidenceGate`（`src/generator/confidence_gate.py`）: `should_answer(confidence: float) -> bool` と `missing_text() -> str` のみ。
- `classify_question(question: str) -> list[str]`（`src/utils/question_classifier.py`）: 質問文だけからヒューリスティックにタグ付けする。返るタグは `"image_or_graph"`, `"version_diff"`, `"password_protected"`, `"multi_hop"`, `"text_only"` のいずれか1つ以上（該当なしなら `"text_only"`）。質問文だけで判定するため生成時に呼べる（人手ラベルの `question_labels.csv` は使わない＝規約上安全）。
- `_build_context(contexts: list[ScoredDocument]) -> str`（`src/generator/answer_generator.py`）: 各文書を800文字に切り詰め、`【参考文書 N】(ファイル名 / location)\n本文` の形式で連結した文字列を返す。LLMに渡すcontextそのもの。
- `ProjectScopedRetriever`（`src/retriever/project_scoped_retriever.py`）: `add()`時に`Document.metadata["project"]`から案件名を収集。`detect_project(query)`は現状**案件の正式名称そのものが質問文に含まれる場合のみ**検出する（略称は見ない＝Phase 1で塞ぐギャップ）。`_normalize_project_name`は法人格などの接頭辞・接尾辞を除去し、かつNFC正規化する（`8ceb314`で修正済み）。
- `artifacts/project_registry.json`: `[{"project_name": str, "aliases": list[str], "file_count": int, "sections": list[str]}, ...]`。`aliases`には正式名称・略称（KSS, TOTO, MINAMINO等）が含まれる。
- `artifacts/term_registry.json`: `[{"term": str, "expansion": str, "note": str}, ...]`（例: `{"term": "TG", "expansion": "目的変数", "note": "Target"}`）。245件。
- 両JSONは `scripts/build_registries.py` が `data/raw/share/共有ドライブ/社内管理/社内用語集.docx` を実行時にパースして生成する（手入力禁止の対象なので絶対にこの2ファイルの中身をコードに書き写さないこと）。
- `Pipeline`（`src/orchestrator/pipeline.py`）: `_process_one(qa)` が `self.retriever.search(qa.question, top_k=...)` → `self.generator.generate(qa.question, contexts)` → judge、の順で1問処理する。

---

### Task 1: タイプ別確信度ゲート

**目的:** (a) 現在の回答パイプラインが対応できない設問タイプ（画像・グラフ読解、パスワード保護ファイル復号）は確信度に関わらず無条件でMissingにする。(b) 複数案件を横断する設問（`multi_hop`）は誤答リスクが高いため確信度の閾値を引き上げる。CRAGの非対称性（Incorrect=-1点、Missing=0点）への直接対策。

**Files:**
- Modify: `src/generator/confidence_gate.py`
- Modify: `src/generator/answer_generator.py`
- Modify: `tests/test_generator.py`

**Interfaces:**
- Consumes: `classify_question(question: str) -> list[str]`（`src/utils/question_classifier.py`、変更しない）
- Produces: `ConfidenceGate.is_capability_blocked(tags: Sequence[str] = ()) -> bool`、`ConfidenceGate.should_answer(confidence: float, tags: Sequence[str] = ()) -> bool`（**tags引数を追加、省略時は従来通り動く**）。Task 2・4がこの`generate()`の続きに手を加える。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_generator.py` の `TestConfidenceGate` クラスの直後に追記:

```python
class TestConfidenceGateTags:
    def test_capability_blocked_tag_forces_false_regardless_of_confidence(self) -> None:
        gate = ConfidenceGate(threshold=0.0)
        assert gate.should_answer(1.0, tags=["image_or_graph"]) is False
        assert gate.should_answer(1.0, tags=["password_protected"]) is False

    def test_high_risk_tag_raises_effective_threshold(self) -> None:
        gate = ConfidenceGate(threshold=0.4)
        assert gate.should_answer(0.5, tags=["multi_hop"]) is False  # 0.4+0.2=0.6必要
        assert gate.should_answer(0.7, tags=["multi_hop"]) is True

    def test_normal_tags_do_not_change_threshold(self) -> None:
        gate = ConfidenceGate(threshold=0.4)
        assert gate.should_answer(0.4, tags=["text_only"]) is True

    def test_should_answer_without_tags_argument_still_works(self) -> None:
        """既存呼び出し（tags省略）の後方互換性。"""
        gate = ConfidenceGate(threshold=0.4)
        assert gate.should_answer(0.5) is True
        assert gate.should_answer(0.3) is False

    def test_is_capability_blocked(self) -> None:
        gate = ConfidenceGate()
        assert gate.is_capability_blocked(["image_or_graph"]) is True
        assert gate.is_capability_blocked(["text_only"]) is False
        assert gate.is_capability_blocked([]) is False
```

`TestAnswerGeneratorGenerate` クラスの末尾（`test_long_answer_is_truncated_with_ellipsis`の後）に追記:

```python
    def test_capability_blocked_question_skips_llm_call(self, tmp_path: Path) -> None:
        """image_or_graph等の能力外タイプはLLMを呼ばずに即Missing。"""

        class BoomGenerator(AnswerGenerator):
            def _call_llm(self, question: str, context: str) -> str:
                raise AssertionError("能力外タイプでLLMを呼んではいけない")

        gen = BoomGenerator(threshold=0.4)
        answer = gen.generate("この画像の意味を教えてください", [_scored_doc(tmp_path)])
        assert answer.was_gated is True
        assert answer.text == gen.gate.missing_text()

    def test_multi_hop_question_needs_higher_confidence(self, tmp_path: Path) -> None:
        fake_response = '{"answer": "回答", "confidence": 0.5, "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("すべての案件の合計金額を教えてください", [_scored_doc(tmp_path)])
        assert answer.was_gated is True

    def test_multi_hop_question_passes_with_high_confidence(self, tmp_path: Path) -> None:
        fake_response = '{"answer": "回答", "confidence": 0.8, "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("すべての案件の合計金額を教えてください", [_scored_doc(tmp_path)])
        assert answer.was_gated is False
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_generator.py -v`
Expected: 新規テストがFAIL（`TypeError: should_answer() got an unexpected keyword argument 'tags'` 等）

- [ ] **Step 3: 実装**

`src/generator/confidence_gate.py` を全面書き換え:

```python
"""確信度が閾値未満、または能力外の設問タイプなら回答をMissing相当に差し替えるゲート。"""
from __future__ import annotations

from collections.abc import Sequence

MISSING_RESPONSE = "提供された資料からは、ご質問に対する回答を見つけることができませんでした。"

# 現在の回答パイプラインには画像・グラフ読解、パスワード保護ファイルの復号能力がない。
# 該当タイプは確信度に関わらず無条件でMissingにする（CRAGのIncorrect=-1非対称性への対策）。
CAPABILITY_BLOCKED_TAGS = frozenset({"image_or_graph", "password_protected"})
# 複数案件を横断する設問は集計ミスのリスクが高いため、閾値を引き上げる。
HIGH_RISK_TAGS = frozenset({"multi_hop"})
HIGH_RISK_THRESHOLD_BONUS = 0.2


class ConfidenceGate:
    def __init__(self, threshold: float = 0.4) -> None:
        self.threshold = threshold

    def is_capability_blocked(self, tags: Sequence[str] = ()) -> bool:
        return any(tag in CAPABILITY_BLOCKED_TAGS for tag in tags)

    def should_answer(self, confidence: float, tags: Sequence[str] = ()) -> bool:
        if self.is_capability_blocked(tags):
            return False
        effective_threshold = self.threshold
        if any(tag in HIGH_RISK_TAGS for tag in tags):
            effective_threshold = min(1.0, self.threshold + HIGH_RISK_THRESHOLD_BONUS)
        return confidence >= effective_threshold

    def missing_text(self) -> str:
        return MISSING_RESPONSE
```

`src/generator/answer_generator.py` の `generate()` を書き換え、importを追加:

```python
from src.utils.question_classifier import classify_question
```

```python
    def generate(self, question: str, contexts: list[ScoredDocument]) -> Answer:
        tags = classify_question(question)
        if self.gate.is_capability_blocked(tags):
            return Answer(
                text=self.gate.missing_text(),
                confidence=0.0,
                source_docs=contexts,
                was_gated=True,
            )

        if not contexts:
            return Answer(
                text=self.gate.missing_text(),
                confidence=0.0,
                source_docs=[],
                was_gated=True,
            )

        context_text = _build_context(contexts)
        raw = self._call_llm(question, context_text)
        answer_text, confidence = self._parse_response(raw)

        if not self.gate.should_answer(confidence, tags=tags):
            return Answer(
                text=self.gate.missing_text(),
                confidence=confidence,
                source_docs=contexts,
                was_gated=True,
            )

        if len(answer_text) > MAX_CHARS_APPROX:
            answer_text = answer_text[:MAX_CHARS_APPROX] + "…"

        return Answer(text=answer_text, confidence=confidence, source_docs=contexts)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_generator.py -v`
Expected: 全件PASS

- [ ] **Step 5: 全テスト実行＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/generator/confidence_gate.py src/generator/answer_generator.py tests/test_generator.py
git commit -m "Phase1 Task1: タイプ別確信度ゲート（能力外タイプの強制Missing・高リスクタイプの閾値引き上げ）"
```

---

### Task 2: 根拠引用の強制（ハルシネーション機械検出）

**目的:** 生成時に「回答の根拠となった文書中の一節」を引用させ、その引用が実際にLLMへ渡したcontext内に一字一句存在しない場合は、confidenceが高くてもMissingへ落とす。confidenceの自己申告だけに頼らない、独立した安全網。

**Files:**
- Create: `src/generator/citation_check.py`
- Create: `tests/test_citation_check.py`
- Modify: `src/generator/answer_generator.py`
- Modify: `tests/test_generator.py`

**Interfaces:**
- Consumes: Task 1後の`generate()`（`context_text`変数、`self.gate.should_answer`呼び出し）
- Produces: `citation_supported(citation: str, context_text: str) -> bool`。`AnswerGenerator._parse_response`の返り値が**2要素タプルから3要素タプル `(answer, confidence, citation)` に変わる**（Task 3・4はこの3要素版を前提にする）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_citation_check.py`:

```python
"""citation_check のテスト（純粋関数）。"""
from __future__ import annotations

from src.generator.citation_check import citation_supported


def test_citation_present_in_context_is_supported() -> None:
    assert citation_supported(
        "宿泊費の上限は15,000円です。", "前略。宿泊費の上限は15,000円です。後略。"
    ) is True


def test_citation_absent_from_context_is_not_supported() -> None:
    assert citation_supported("架空の引用文です。", "宿泊費の上限は15,000円です。") is False


def test_empty_citation_is_not_supported() -> None:
    assert citation_supported("", "何らかのcontext") is False


def test_citation_with_surrounding_whitespace_is_stripped_before_check() -> None:
    assert citation_supported(
        "  宿泊費の上限は15,000円です。  ", "宿泊費の上限は15,000円です。"
    ) is True
```

`tests/test_generator.py` の `TestParseResponse` クラスを次の内容に**全面置換**（2要素→3要素タプルになるため）:

```python
class TestParseResponse:
    def setup_method(self) -> None:
        self.gen = AnswerGenerator()

    def test_parses_clean_json(self) -> None:
        """正常な JSON からアンサー・確信度・引用を取得できる。"""
        raw = '{"answer": "foo", "confidence": 0.8, "citation": "bar", "reasoning": "some reason"}'
        answer, confidence, citation = self.gen._parse_response(raw)
        assert answer == "foo"
        assert confidence == pytest.approx(0.8)
        assert citation == "bar"

    def test_parses_json_surrounded_by_text(self) -> None:
        """JSON が前後テキストに囲まれていてもパースできる。"""
        raw = 'Here is the result: {"answer": "bar", "confidence": 0.7, "citation": "baz", "reasoning": "r"} done.'
        answer, confidence, citation = self.gen._parse_response(raw)
        assert answer == "bar"
        assert confidence == pytest.approx(0.7)
        assert citation == "baz"

    def test_invalid_json_returns_raw_zero_confidence_and_empty_citation(self) -> None:
        """不正な JSON のとき (raw_text, 0.0, "") を返す。"""
        raw = "this is not JSON at all"
        answer, confidence, citation = self.gen._parse_response(raw)
        assert answer == raw
        assert confidence == 0.0
        assert citation == ""

    def test_confidence_as_string_is_converted_to_float(self) -> None:
        """JSON 内の confidence が文字列 "0.8" でも float に変換される。"""
        raw = '{"answer": "baz", "confidence": "0.8", "citation": "c", "reasoning": "r"}'
        answer, confidence, citation = self.gen._parse_response(raw)
        assert answer == "baz"
        assert isinstance(confidence, float)
        assert confidence == pytest.approx(0.8)

    def test_missing_citation_key_defaults_to_empty_string(self) -> None:
        """citationキーが無いJSONでも空文字にフォールバックする。"""
        raw = '{"answer": "foo", "confidence": 0.8, "reasoning": "r"}'
        _, _, citation = self.gen._parse_response(raw)
        assert citation == ""
```

`TestAnswerGeneratorGenerate` クラス内の既存2テストを次のように**修正**（citationフィールドを追加しないとTask 2実装後に落ちるため）:

```python
    def test_high_confidence_answer_is_returned_ungated(self, tmp_path: Path) -> None:
        """確信度 0.9 かつ引用が実在する回答はゲートを通過してそのまま返る（was_gated=False）。"""
        fake_response = '{"answer": "correct answer", "confidence": 0.9, "citation": "some relevant text", "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.was_gated is False
        assert answer.text == "correct answer"
        assert answer.confidence == pytest.approx(0.9)
```

```python
    def test_long_answer_is_truncated_with_ellipsis(self, tmp_path: Path) -> None:
        """回答テキストが MAX_CHARS_APPROX を超えた場合、"…" で切り捨てられる。"""
        long_answer = "a" * (MAX_CHARS_APPROX + 100)
        fake_response = json.dumps(
            {"answer": long_answer, "confidence": 0.9, "citation": "some relevant text", "reasoning": "r"}
        )
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.text.endswith("…")
        assert len(answer.text) == MAX_CHARS_APPROX + 1
```

Task 1で追加した `test_multi_hop_question_passes_with_high_confidence` も同様に修正（citationが無いとTask 2実装後にゲートされてしまい `was_gated is False` のアサーションが落ちるため）:

```python
    def test_multi_hop_question_passes_with_high_confidence(self, tmp_path: Path) -> None:
        fake_response = '{"answer": "回答", "confidence": 0.8, "citation": "some relevant text", "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("すべての案件の合計金額を教えてください", [_scored_doc(tmp_path)])
        assert answer.was_gated is False
```

`TestAnswerGeneratorGenerate` クラスの末尾に追記:

```python
    def test_fabricated_citation_is_gated_even_with_high_confidence(self, tmp_path: Path) -> None:
        """confidenceが高くても、citationが参考文書に実在しなければMissingにする。"""
        fake_response = '{"answer": "捏造回答", "confidence": 0.95, "citation": "文書に存在しない架空の一節", "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.was_gated is True
        assert answer.text == gen.gate.missing_text()

    def test_missing_citation_field_is_gated(self, tmp_path: Path) -> None:
        """citationフィールド自体が無い場合もMissingにする。"""
        fake_response = '{"answer": "回答", "confidence": 0.9, "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.was_gated is True
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_citation_check.py tests/test_generator.py -v`
Expected: `test_citation_check.py`は`ModuleNotFoundError`でFAIL。`test_generator.py`は`ValueError: too many values to unpack`等でFAIL。

- [ ] **Step 3: 実装**

`src/generator/citation_check.py`:

```python
"""生成された回答の根拠引用が、実際にLLMへ渡したcontext内に存在するかを確認する。

confidenceの自己申告が高くても、引用が捏造（ハルシネーション）されている場合は
Missingへ落とすための機械的チェック。
"""
from __future__ import annotations


def citation_supported(citation: str, context_text: str) -> bool:
    citation = citation.strip()
    if not citation:
        return False
    return citation in context_text
```

`src/generator/answer_generator.py`:

- import追加: `from src.generator.citation_check import citation_supported`
- `SYSTEM_PROMPT` を次の内容に置換（出力形式にcitationを追加。confidence定義の見直しはTask 4で行うのでここでは最小限の追記のみ）:

```python
SYSTEM_PROMPT = """\
あなたは社内共有ドライブの文書を参照して質問に答るアシスタントです。

【評価基準】
- Perfect (1点): 正確かつ虚偽のない回答
- Acceptable (0.5点): 有用だが軽微な誤りがある回答
- Missing (0点): 「わかりません」等の具体的回答なし
- Incorrect (-1点): 間違い・無関係な回答

【重要ルール】
1. 提供された参考文書の内容のみを根拠として回答すること
2. 文書に記載がない情報は「わかりません」と答えること（Incorrectより安全）
3. 回答は1000トークン以内に収めること
4. 確信度を0.0〜1.0で自己評価し、JSON形式で返すこと
5. 回答の直接の根拠となった文書中の一節を、要約・言い換えせずそのまま "citation" に引用すること。
   引用文が参考文書中に一字一句存在しない場合、回答は無効として扱われます。

【出力形式】
{
  "answer": "回答テキスト",
  "confidence": 0.0〜1.0,
  "citation": "根拠として引用した文書中の一節（そのまま抜粋）",
  "reasoning": "根拠となった文書の箇所"
}
"""
```

- `_parse_response` を書き換え:

```python
    def _parse_response(self, raw: str) -> tuple[str, float, str]:
        import json
        import re

        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return (
                    str(data.get("answer", "")),
                    float(data.get("confidence", 0.0)),
                    str(data.get("citation", "")),
                )
        except (json.JSONDecodeError, ValueError):
            pass
        # JSON解析失敗時はそのままテキストを使い確信度0・引用なし
        return raw, 0.0, ""
```

- `generate()` 内の `_parse_response` 呼び出しと、その後段を書き換え:

```python
        answer_text, confidence, citation = self._parse_response(raw)

        if not self.gate.should_answer(confidence, tags=tags):
            return Answer(
                text=self.gate.missing_text(),
                confidence=confidence,
                source_docs=contexts,
                was_gated=True,
            )

        if not citation_supported(citation, context_text):
            return Answer(
                text=self.gate.missing_text(),
                confidence=confidence,
                source_docs=contexts,
                was_gated=True,
            )

        if len(answer_text) > MAX_CHARS_APPROX:
            answer_text = answer_text[:MAX_CHARS_APPROX] + "…"

        return Answer(text=answer_text, confidence=confidence, source_docs=contexts)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_citation_check.py tests/test_generator.py -v`
Expected: 全件PASS

- [ ] **Step 5: 既存の他テストへの影響を確認**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS。`tests/test_pipeline.py::test_e2e_stub` のフェイク応答にはcitationが無いため、この変更後は生成結果がゲートされる（`was_gated=True`）ようになるが、同テストのアサーションは `answer.text != ""` のみなので依然PASSする（`missing_text()`は非空文字列）。念のため出力を確認し、予期せぬFAILがないことを確かめること。

- [ ] **Step 6: Commit**

```bash
git add src/generator/citation_check.py src/generator/answer_generator.py tests/test_citation_check.py tests/test_generator.py
git commit -m "Phase1 Task2: 根拠引用の実在チェックによるハルシネーション機械検出ゲート"
```

---

### Task 3: 案件・用語レジストリのクエリ処理接続

**目的:** 質問文中の案件略称（KSS, TOTO, MINAMINO…）でも案件ルーティングが機能するようにする。また社内用語の略語（TG, PP, CT…）が質問文に含まれる場合、正式名称を検索クエリに併記してBM25検索の再現率を上げる。`artifacts/project_registry.json` / `artifacts/term_registry.json`（実行時に実データから生成される）をはじめて回答パイプラインに接続するタスク。

**Files:**
- Create: `src/retriever/query_expander.py`
- Create: `tests/test_query_expander.py`
- Modify: `src/retriever/project_scoped_retriever.py`
- Modify: `tests/test_project_scoped_retriever.py`
- Modify: `src/orchestrator/pipeline.py`
- Modify: `scripts/run_pipeline.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `artifacts/project_registry.json`（`project_name`, `aliases` キー）、`artifacts/term_registry.json`（`term`, `expansion` キー）
- Produces: `QueryExpander(term_registry: list[dict]).expand_terms(query: str) -> str`。`ProjectScopedRetriever(project_aliases: dict[str, list[str]] | None = None)`（**新しい任意引数、省略時は従来通り**）。`Pipeline(..., project_aliases: dict[str, list[str]] | None = None, term_registry: list[dict] | None = None)`（新しい任意引数）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_query_expander.py`:

```python
"""QueryExpander のテスト（純粋関数的なクラス）。"""
from __future__ import annotations

from src.retriever.query_expander import QueryExpander


def test_expand_terms_appends_expansion_when_term_present() -> None:
    expander = QueryExpander([{"term": "TG", "expansion": "目的変数", "note": "Target"}])
    assert expander.expand_terms("TGの分布を教えて") == "TGの分布を教えて 目的変数"


def test_expand_terms_returns_original_when_no_term_matches() -> None:
    expander = QueryExpander([{"term": "TG", "expansion": "目的変数"}])
    assert expander.expand_terms("関係ない質問です") == "関係ない質問です"


def test_expand_terms_dedupes_identical_expansions() -> None:
    registry = [
        {"term": "PL", "expansion": "計画"},
        {"term": "PLAN", "expansion": "計画"},
    ]
    expander = QueryExpander(registry)
    result = expander.expand_terms("PLANとPLの違いは？")
    assert result.count("計画") == 1


def test_expand_terms_with_empty_registry_returns_original() -> None:
    expander = QueryExpander([])
    assert expander.expand_terms("TGの分布を教えて") == "TGの分布を教えて"
```

`tests/test_project_scoped_retriever.py` の `TestProjectScopedRetriever` クラスの末尾に追記:

```python
    def test_detect_project_matches_via_alias(self) -> None:
        """project_registry.json由来のエイリアス（略称）でも案件を検出できる。"""
        retriever = ProjectScopedRetriever(
            project_aliases={"株式会社青潮モビリティサービス": ["AOSHIO", "青潮"]}
        )
        docs = [_doc("需要予測データです。", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)

        assert retriever.detect_project("AOSHIOの需要予測について") == "株式会社青潮モビリティサービス"

    def test_detect_project_alias_does_not_leak_to_other_project(self) -> None:
        retriever = ProjectScopedRetriever(
            project_aliases={
                "株式会社青潮モビリティサービス": ["AOSHIO"],
                "医療法人社団 恒一会 かえで総合病院": ["KAEDE"],
            }
        )
        docs = [
            _doc("需要予測データです。", project="株式会社青潮モビリティサービス"),
            _doc("患者数データです。", project="医療法人社団 恒一会 かえで総合病院"),
        ]
        retriever.add(docs)

        assert retriever.detect_project("KAEDEの患者数について") == "医療法人社団 恒一会 かえで総合病院"

    def test_detect_project_without_aliases_arg_still_works(self) -> None:
        """project_aliases省略時は従来通り正式名称のみで検出する（後方互換性）。"""
        retriever = ProjectScopedRetriever()
        docs = [_doc("テキスト", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)

        assert retriever.detect_project("青潮モビリティサービスについて") == "株式会社青潮モビリティサービス"
```

`tests/test_pipeline.py` の末尾に追記:

```python
def test_pipeline_expands_search_query_with_term_registry(tmp_path: Path) -> None:
    """term_registryが渡されると検索クエリに用語展開が反映される（LLMへの質問文は元のまま）。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    pipeline = Pipeline(
        data_dir=tmp_path,
        run_judge=False,
        term_registry=[{"term": "TG", "expansion": "目的変数", "note": "Target"}],
    )
    pipeline.generator._call_llm = lambda q, c: '{"answer": "回答", "confidence": 0.9, "citation": "", "reasoning": "r"}'

    captured_queries: list[str] = []
    original_search = pipeline.retriever.search

    def _spy_search(query: str, top_k: int = 5):
        captured_queries.append(query)
        return original_search(query, top_k=top_k)

    pipeline.retriever.search = _spy_search

    (tmp_path / "a.txt").write_text("目的変数についての説明です。", encoding="utf-8")
    pipeline.build_index()

    pipeline._process_one(QAPair(question_id="0", question="TGの定義は？"))

    assert captured_queries == ["TGの定義は？ 目的変数"]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_query_expander.py tests/test_project_scoped_retriever.py tests/test_pipeline.py -v`
Expected: `test_query_expander.py`は`ModuleNotFoundError`でFAIL。エイリアス系テストは`TypeError: __init__() got an unexpected keyword argument 'project_aliases'`等でFAIL。

- [ ] **Step 3: 実装**

`src/retriever/query_expander.py`:

```python
"""社内用語（略語）が質問文に含まれる場合、正式名称を検索クエリに併記する。

用語レジストリはartifacts/term_registry.jsonから実行時に読み込んだものを
呼び出し側から渡す（このクラス自体はレジストリの中身を知らない＝ハードコードしない）。
"""
from __future__ import annotations


class QueryExpander:
    def __init__(self, term_registry: list[dict]) -> None:
        self._term_registry = term_registry

    def expand_terms(self, query: str) -> str:
        expansions: list[str] = []
        for entry in self._term_registry:
            term = entry.get("term", "")
            expansion = entry.get("expansion", "")
            if term and expansion and term in query and expansion not in expansions:
                expansions.append(expansion)
        if not expansions:
            return query
        return query + " " + " ".join(expansions)
```

`src/retriever/project_scoped_retriever.py` を書き換え:

```python
    def __init__(self, project_aliases: dict[str, list[str]] | None = None) -> None:
        self._global_store = KeywordStore()
        self._project_stores: dict[str, KeywordStore] = {}
        self._project_names: list[str] = []
        self._aliases_by_normalized_name: dict[str, list[str]] = {
            _normalize_project_name(name): aliases
            for name, aliases in (project_aliases or {}).items()
        }
```

`detect_project` を書き換え:

```python
    def detect_project(self, query: str) -> str | None:
        normalized_query = unicodedata.normalize("NFC", query)
        for name in self._project_names:
            normalized = _normalize_project_name(name)
            if normalized and normalized in normalized_query:
                return name
        for name in self._project_names:
            aliases = self._aliases_by_normalized_name.get(_normalize_project_name(name), [])
            for alias in aliases:
                if alias and _normalize_project_name(alias) in normalized_query:
                    return name
        return None
```

（`clear()`は`_aliases_by_normalized_name`を消さない。レジストリはインデックス再構築とは独立したデータのため。既存の`clear()`実装はそのままでよい。）

`src/orchestrator/pipeline.py`:

- import追加: `from src.retriever.query_expander import QueryExpander`
- `Pipeline.__init__` のシグネチャと本体を書き換え:

```python
    def __init__(
        self,
        data_dir: Path,
        max_concurrent: int = 5,
        top_k: int = 5,
        confidence_threshold: float = 0.4,
        run_judge: bool = True,
        project_aliases: dict[str, list[str]] | None = None,
        term_registry: list[dict] | None = None,
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
```

- `_process_one` の検索呼び出しを書き換え（LLMへ渡す質問文`qa.question`自体は変えない。展開後クエリは検索にのみ使う）:

```python
    def _process_one(self, qa: QAPair) -> PipelineResult:
        search_query = self.query_expander.expand_terms(qa.question)
        contexts = self.retriever.search(search_query, top_k=self.top_k)
        answer: Answer = self.generator.generate(qa.question, contexts)
```

`scripts/run_pipeline.py`:

- import追加: `from pathlib import Path`は既存。`json`は既存importを流用。
- argparseに追加: `parser.add_argument("--artifacts-dir", type=Path, default=ROOT / "artifacts", help="レジストリJSONのディレクトリ")`
- `main()`冒頭、`pipeline = Pipeline(...)`より前に追加:

```python
    project_aliases: dict[str, list[str]] = {}
    term_registry: list[dict] = []
    projects_path = args.artifacts_dir / "project_registry.json"
    terms_path = args.artifacts_dir / "term_registry.json"
    if projects_path.exists():
        projects = json.loads(projects_path.read_text(encoding="utf-8"))
        project_aliases = {p["project_name"]: p.get("aliases", []) for p in projects}
    if terms_path.exists():
        term_registry = json.loads(terms_path.read_text(encoding="utf-8"))
```

- `pipeline = Pipeline(...)` 呼び出しに引数を追加:

```python
    pipeline = Pipeline(
        data_dir=args.data_dir,
        max_concurrent=args.concurrent,
        top_k=args.top_k,
        confidence_threshold=args.threshold,
        project_aliases=project_aliases,
        term_registry=term_registry,
    )
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_query_expander.py tests/test_project_scoped_retriever.py tests/test_pipeline.py -v`
Expected: 全件PASS

- [ ] **Step 5: 全テスト実行＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/retriever/query_expander.py src/retriever/project_scoped_retriever.py src/orchestrator/pipeline.py scripts/run_pipeline.py tests/test_query_expander.py tests/test_project_scoped_retriever.py tests/test_pipeline.py
git commit -m "Phase1 Task3: 案件エイリアス・社内用語レジストリのクエリ処理接続"
```

---

### Task 4: 生成プロンプト調整（わかりません過剰逃避の是正）

**目的:** 「根拠が部分的にしか無い場合でも具体的に回答する」よう促し、`confidence`の定義（何を表す数値か）をプロンプトで明確に固定する。あわせて、LLMが「わかりません」と回答しつつ`confidence`を高く自己申告する矛盾（`confidence`の意味が壊れているケース）を、プロンプト任せにせずコードでも機械的に検出してMissingへ落とす安全網を追加する。

**Files:**
- Modify: `src/generator/confidence_gate.py`
- Modify: `src/generator/answer_generator.py`
- Modify: `tests/test_generator.py`

**Interfaces:**
- Consumes: Task 1〜3後の`generate()`
- Produces: `looks_like_missing(text: str) -> bool`（`src/generator/confidence_gate.py`に追加）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_generator.py` の先頭importに追記:

```python
from src.generator.confidence_gate import ConfidenceGate, looks_like_missing
```

`TestConfidenceGateTags` クラスの後に追記:

```python
class TestLooksLikeMissing:
    def test_detects_wakarimasen(self) -> None:
        assert looks_like_missing("提供された資料からはわかりません") is True

    def test_detects_mitsukarimasen(self) -> None:
        assert looks_like_missing("該当箇所が見つかりません") is True

    def test_normal_answer_is_not_missing(self) -> None:
        assert looks_like_missing("宿泊費の上限は15,000円です。") is False
```

`TestAnswerGeneratorGenerate` クラスの末尾に追記:

```python
    def test_missing_phrase_answer_is_gated_even_with_high_confidence(self, tmp_path: Path) -> None:
        """LLMが「わかりません」と答えつつconfidenceを高く自己申告しても機械的にMissing扱いする。"""
        fake_response = '{"answer": "わかりません", "confidence": 0.9, "citation": "some relevant text", "reasoning": "r"}'
        gen = FakeGenerator(fake_response=fake_response, threshold=0.4)
        answer = gen.generate("what?", [_scored_doc(tmp_path)])
        assert answer.was_gated is True
        assert answer.text == gen.gate.missing_text()
```

新しいテストクラスを`tests/test_generator.py`の末尾に追記（SYSTEM_PROMPTの退行防止）:

```python
class TestSystemPromptConfidenceSemantics:
    def test_prompt_defines_low_confidence_for_missing_answers(self) -> None:
        assert "わからない" in SYSTEM_PROMPT or "わかりません" in SYSTEM_PROMPT
        assert "0.0" in SYSTEM_PROMPT and "0.2" in SYSTEM_PROMPT

    def test_prompt_instructs_partial_answers_over_refusal(self) -> None:
        assert "部分的" in SYSTEM_PROMPT
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_generator.py -v`
Expected: `looks_like_missing`のimportで`ImportError`、および`test_missing_phrase_answer_is_gated_even_with_high_confidence`と`TestSystemPromptConfidenceSemantics`がFAIL

- [ ] **Step 3: 実装**

`src/generator/confidence_gate.py` に追記（ファイル末尾）:

```python
_MISSING_PHRASES = ("わかりません", "見つかりません", "不明です")


def looks_like_missing(text: str) -> bool:
    """LLMが「わかりません」系の文言で逃げた回答かどうかを判定する。

    confidenceの自己申告が高くても、内容がMissing相当なら機械的にMissing扱いにする
    （confidenceの意味が壊れているケースへの防御）。
    """
    return any(phrase in text for phrase in _MISSING_PHRASES)
```

`src/generator/answer_generator.py`:

- import修正: `from src.generator.confidence_gate import ConfidenceGate, looks_like_missing`
- `SYSTEM_PROMPT` を次の内容に置換:

```python
SYSTEM_PROMPT = """\
あなたは社内共有ドライブの文書を参照して質問に答るアシスタントです。

【評価基準】
- Perfect (1点): 正確かつ虚偽のない回答
- Acceptable (0.5点): 有用だが軽微な誤りがある回答
- Missing (0点): 「わかりません」等の具体的回答なし
- Incorrect (-1点): 間違い・無関係な回答

【重要ルール】
1. 提供された参考文書の内容のみを根拠として回答すること
2. 文書に部分的にしか記載がない場合でも、確実に読み取れる範囲で具体的に回答すること。
   「わかりません」と答えてよいのは、参考文書に質問と関連する情報が全く含まれていない場合のみ。
   表紙・目次・タイトルしか無いなど、実質的な手がかりが無い場合に限り「わかりません」とする。
3. 回答は1000トークン以内に収めること
4. confidenceは「この回答がPerfectまたはAcceptableと評価される確率」を0.0〜1.0で表すこと。
   「わかりません」と回答する場合は、confidenceを必ず0.0〜0.2の範囲にすること
   （わからないのにconfidenceを高くすることは禁止）。
5. 回答の直接の根拠となった文書中の一節を、要約・言い換えせずそのまま "citation" に引用すること。
   引用文が参考文書中に一字一句存在しない場合、回答は無効として扱われます。

【出力形式】
{
  "answer": "回答テキスト",
  "confidence": 0.0〜1.0,
  "citation": "根拠として引用した文書中の一節（そのまま抜粋）",
  "reasoning": "根拠となった文書の箇所"
}
"""
```

- `generate()` 内、`_parse_response`直後・`should_answer`チェックより前に追加:

```python
        answer_text, confidence, citation = self._parse_response(raw)

        if looks_like_missing(answer_text):
            return Answer(
                text=self.gate.missing_text(),
                confidence=confidence,
                source_docs=contexts,
                was_gated=True,
            )

        if not self.gate.should_answer(confidence, tags=tags):
```

（以降のcitationチェック・truncate・returnはTask 2の実装のまま変更しない）

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_generator.py -v`
Expected: 全件PASS

- [ ] **Step 5: 全テスト実行＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add src/generator/confidence_gate.py src/generator/answer_generator.py tests/test_generator.py
git commit -m "Phase1 Task4: 生成プロンプト調整（部分回答の推奨・confidence定義の明確化・わかりません矛盾の機械検出）"
```

---

### Task 5: E2E確認・plan_0703.md更新

**目的:** 実データ・実APIでvalid 30問を再実行し、Incorrectが増えていないこと（守りの原則）と、スコアが悪化していないことを確認する。`docs/plan/plan_0703.md`に結果を追記する。**このタスクはAPIコストが発生する。**

**Files:**
- Create: `experiments/phase1_valid_<ts>.json`（パイプライン出力）
- Modify: `docs/plan/plan_0703.md`

**Interfaces:**
- Consumes: Task 1〜4の全成果物
- Produces: Phase 1完了条件の実測確認

- [ ] **Step 1: valid 30問をフルパイプラインで再実行**

```bash
.venv/bin/python scripts/run_pipeline.py \
  --data-dir "data/raw/share/共有ドライブ" \
  --questions "data/raw/share/質問回答/questions_valid.csv" \
  --run-name phase1_valid
```

Expected: `experiments/phase1_valid_<ts>.json` が生成される。

- [ ] **Step 2: ベースラインと比較する**

`experiments/baseline_valid_1783069301.json`（mean 0.05, Missing 26 / Incorrect 1 / Acceptable 1 / Perfect 2）と、今回生成したJSONの `summary` を見比べる。`scripts/run_eval.py` がこの時点で存在する場合（Phase 0が既にマージされている場合）は使う:

```bash
.venv/bin/python scripts/run_eval.py experiments/baseline_valid_1783069301.json experiments/phase1_valid_<ts>.json
```

存在しない場合は、両JSONの `results[].judge_label` を手動で比較する。

**必須確認事項（守りの原則、`plan_0703.md` §4）:**
- Incorrectの件数がベースライン（1件）以下であること。増えている場合は原因を特定し、該当パスのゲートを強化してから完了とすること。
- mean_scoreがベースライン（0.05）を下回っていないこと。

- [ ] **Step 3: `docs/plan/plan_0703.md` に結果を追記**

`docs/plan/plan_0703.md` の Phase 1 の節（`### Phase 1: 守りの再設計と土台修正`）の直後に、以下のテンプレートで実測値を埋めて追記する:

```markdown
#### Phase 1 実装結果（YYYY-MM-DD、Codexにより実装）

run: `experiments/phase1_valid_<ts>.json`（比較対象: `experiments/baseline_valid_1783069301.json`）

| 指標 | ベースライン | Phase 1後 |
|---|---:|---:|
| mean_score | 0.05 | X.XX |
| Perfect | 2 | N |
| Acceptable | 1 | N |
| Missing | 26 | N |
| Incorrect | 1 | N |

- 実装内容: タイプ別確信度ゲート／根拠引用の実在チェック／案件エイリアス・社内用語レジストリのクエリ接続／生成プロンプト調整
- 未着手: チャンク・検索の修正（Phase 0の検索失敗切り分け結果待ち）
```

- [ ] **Step 4: 最終確認＋Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

```bash
git add experiments/ docs/plan/plan_0703.md
git commit -m "Phase1 Task5: valid30問での実測確認とplan_0703.md更新"
```

---

## 完了条件

- Task 1〜4の全変更後、`.venv/bin/pytest tests/ -v` が全件PASSする。
- valid 30問再実行でIncorrectがベースライン（1件）以下、mean_scoreがベースライン（0.05）以上。
- `docs/plan/plan_0703.md` に実測結果が追記されている。
- 「チャンク・検索の修正」（Phase 1の残り1項目）には着手していない（別スコープ）。
