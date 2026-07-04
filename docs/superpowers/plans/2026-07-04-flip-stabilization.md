# フリップ層の安定化（next-steps §2） Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> コミット前に `/step-review`（haikuレビュー）を挟む運用（`.claude/skills/step-review`）。

**Goal:** ゲート境界と引用ゆらぎで落ちるフリップ層（Q5/Q14/Q18/Q27型）を安定回収し（期待+0.10〜0.15）、以後の実験判定をN=3多数決で標準化する（`docs/plan/2026-07-04-next-steps.md` §2）。

**Architecture:** (1) どのゲートで落ちたかを`gate_reason`としてrun JSONに記録（診断）、(2) N run多数決の評価ツール（判定基盤）、(3) JSONパースの堅牢化（Q18真因の決定的修正）、(4) 引用プロンプト強化、(5) 直答形式プロンプト強化 — 3〜5は各々独立の実験としてN=3 valid評価で採否判定（1実験1変更）。

**Tech Stack:** Python 3.12 (`.venv/bin/python`), pytest, Anthropic API（valid評価時のみ）

## Global Constraints

- 回答は1000トークン以内（`CLAUDE.md`）。
- 特定の質問・案件・ファイル・正解のハードコード禁止（`competition.md`）。`question_labels.csv`は評価専用。
- テストは決定的に: LLM呼び出しは`_call_llm()`オーバーライドのFakeパターンで排除。
- 全テスト `.venv/bin/pytest tests/ -v` が全件PASS（現在285件）。
- **しきい値（threshold=0.4）はいじらない**（Phase 5のグリッドサーチまで温存 — next-steps §2の明記事項）。
- 各実験の採否判定は「多数決mean悪化なし AND 多数決Incorrect増加なし AND 対象問の改善」。不採用ならgit revertし、結果はどちらでも`plan_0703.md`に記録。
- コミットメッセージ末尾: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## 前提となる既存コードの事実（実装者向け）

- `AnswerGenerator.generate()`（`src/generator/answer_generator.py`）のゲートは5段: ①能力外（`is_capability_blocked`）→②contexts空→（LLM呼び出し）→③`looks_like_missing`→④確信度（`should_answer`）→⑤引用（`citation_supported`）。ゲート発火時は`text`がMissing定型文に置換され`was_gated=True`。①②は`raw_text=""`。
- `_parse_response(raw)`は`re.search(r"\{.*\}", raw, re.DOTALL)`→`json.loads`。**失敗時は`(raw, 0.0, "")`を返す**（この仕様が実測Q18を殺した: citation内の生改行でJSON不正→conf 0.0→④で落ちる。修正はTask 3）。
- `citation_supported`（`src/generator/citation_check.py`）は空白類除去後の部分一致。省略記号「…/...」入り引用は実在しないので偽陰性になる（Task 4のプロンプトで抑制）。
- `SYSTEM_PROMPT`は`answer_generator.py`冒頭のモジュール定数。ルール5が引用、【出力形式】にcitationキーの説明。
- `Answer`（`src/models.py`）: `text/confidence/source_docs/was_gated/raw_text`。`PipelineResult`（`src/orchestrator/pipeline.py`）はrun JSONの`results[]`要素。
- run JSONは`experiments/<run-name>_<unixtime>.json`。実行: `.venv/bin/python scripts/run_pipeline.py --data-dir "data/raw/share/共有ドライブ" --questions "data/raw/share/質問回答/questions_valid.csv" --run-name <名前>`（1run約2分・生成in70k/out12k＋judge in11k/out4kトークン）。
- flip分析は`scripts/run_eval.py A.json B.json`（Task 4で導入済み）。`src.evaluator.flip.compare_runs(base: dict, new: dict, base_name, new_name) -> FlipReport`。
- CRAGスコアは`src.models.CRAGLabel(label).score`（Perfect=1.0/Acceptable=0.5/Missing=0.0/Incorrect=-1.0）。二重定義禁止。
- **ベースライン多数決グループ（同一挙動コードの3run・実測済み）**: `experiments/phase2final_valid_1783092422.json` / `experiments/phase2final_valid_1783093012.json` / `experiments/phase0_valid_1783125252.json`（診断情報の有無だけが差で挙動同一）。
- 実測の現状（`docs/plan/missing_triage_20260704.md`）: 過剰ゲート=Q18のみ。Q18のraw_textはJSON文字列のまま（パース失敗の証跡）。Q17はconf 0.85で回答したが用語言い換え（正解「未連絡」→回答「前回未接触」）でofficial Incorrect。

---

### Task 1: gate_reason の記録（どのゲートで落ちたかをrun JSONに残す）

診断強化のみで挙動不変。以後の全実験で「どのゲートが発火したか」をJSONだけで読めるようにする。

**Files:**
- Modify: `src/models.py`（`Answer`に`gate_reason`追加）
- Modify: `src/generator/answer_generator.py`（5ゲート各所で設定）
- Modify: `src/orchestrator/pipeline.py`（`PipelineResult.gate_reason`＋受け渡し）
- Test: `tests/test_generator.py`（追記）、`tests/test_pipeline.py`（追記）

**Interfaces:**
- Produces: `Answer.gate_reason: str`（`""`=非ゲート, `"capability"`, `"no_context"`, `"missing_text"`, `"confidence"`, `"citation"`）。`PipelineResult.gate_reason: str`。run JSONの`results[]`に`gate_reason`キー。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_generator.py`に追記（既存のFakeパターン・importに合わせる）:

```python
def _fake_gen(response: str, threshold: float = 0.4):
    class FakeGen(AnswerGenerator):
        def _call_llm(self, question, context):
            return response
    return FakeGen(threshold=threshold)


def _doc():
    return ScoredDocument(
        document=Document(text="本文の根拠", source_path=Path("dummy.txt")), score=1.0
    )


def test_gate_reason_no_context():
    gen = _fake_gen('{"answer": "x", "confidence": 0.9, "citation": "本文の根拠"}')
    ans = gen.generate("質問", [])
    assert ans.was_gated is True
    assert ans.gate_reason == "no_context"


def test_gate_reason_missing_text():
    gen = _fake_gen('{"answer": "わかりません", "confidence": 0.1, "citation": ""}')
    ans = gen.generate("質問", [_doc()])
    assert ans.gate_reason == "missing_text"


def test_gate_reason_confidence():
    gen = _fake_gen('{"answer": "低確信の回答", "confidence": 0.1, "citation": "本文の根拠"}')
    ans = gen.generate("質問", [_doc()])
    assert ans.gate_reason == "confidence"


def test_gate_reason_citation():
    gen = _fake_gen('{"answer": "回答", "confidence": 0.9, "citation": "文書に存在しない一節"}')
    ans = gen.generate("質問", [_doc()])
    assert ans.gate_reason == "citation"


def test_gate_reason_capability():
    gen = _fake_gen('{"answer": "x", "confidence": 0.9, "citation": "本文の根拠"}')
    ans = gen.generate("このグラフの色は何色ですか", [_doc()])  # image_or_graphタグ
    assert ans.gate_reason == "capability"


def test_gate_reason_empty_when_answered():
    gen = _fake_gen('{"answer": "採用される回答", "confidence": 0.9, "citation": "本文の根拠"}')
    ans = gen.generate("質問", [_doc()])
    assert ans.was_gated is False
    assert ans.gate_reason == ""
```

（`test_gate_reason_capability`の質問文は`src/utils/question_classifier.py`の`IMAGE_KEYWORDS`に実際にマッチするものを使う。「グラフ」がキーワードに無ければ実物を確認して合わせる）

`tests/test_pipeline.py`の診断情報テスト（`test_pipeline_result_has_diagnostics`相当）に1アサーション追加: `results[0]`に`"gate_reason"`キーがあること。

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_generator.py tests/test_pipeline.py -v`
Expected: 新規テストがFAIL（`gate_reason` AttributeError）

- [ ] **Step 3: 実装**

`src/models.py`の`Answer`に1フィールド追加:

```python
    gate_reason: str = ""      # どのゲートで落ちたか（""=非ゲート。capability/no_context/missing_text/confidence/citation）
```

`src/generator/answer_generator.py`の`generate()`内、5つの`return Answer(...)`にそれぞれ`gate_reason="capability"` / `"no_context"` / `"missing_text"` / `"confidence"` / `"citation"`を追加（正常系は変更なし＝デフォルト`""`）。

`src/orchestrator/pipeline.py`: `PipelineResult`に`gate_reason: str = ""`を追加し、`_process_one`の`return PipelineResult(...)`に`gate_reason=answer.gate_reason,`を追加。

- [ ] **Step 4: 全テスト実行**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS（285＋新規7）

- [ ] **Step 5: step-review→Commit**

step-review（haiku・観点は`.claude/skills/step-review`のテンプレート。ゲート分岐を触るので排他ミス重点）→CONFIRMEDのみ修正→

```bash
git add src/models.py src/generator/answer_generator.py src/orchestrator/pipeline.py tests/test_generator.py tests/test_pipeline.py
git commit -m "flip安定化1: gate_reasonの記録（どのゲートで落ちたかをrun JSONに残す）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: N run多数決評価（ゆらぎ対策の判定基盤）

同一コードN runの質問別多数決ラベルを出し、2グループ（before/after）の多数決同士をflip比較できるようにする。以後の実験判定はこれを標準とする。

**Files:**
- Create: `src/evaluator/majority.py`
- Create: `tests/test_majority.py`
- Create: `scripts/majority_eval.py`

**Interfaces:**
- Consumes: run JSONのdict（`{"results": [{"question_id", "question", "judge_label", ...}]}`）、`src.evaluator.flip.compare_runs`、`src.models.CRAGLabel`
- Produces:
  - `majority_labels(runs: list[dict]) -> dict[str, dict]` — qid→`{"label": str, "votes": int, "total": int, "question": str}`。多数決同数（3すくみ等）は**スコア最小のラベル**を採用（保守側）
  - `unstable_questions(runs: list[dict]) -> list[dict]` — 全会一致でないqidの一覧（`{"question_id", "labels": [...], "question"}`）
  - `to_pseudo_run(majority: dict[str, dict]) -> dict` — `compare_runs`にそのまま渡せる`{"results": [...]}`形式（`answer`は`""`）
  - スクリプト: `scripts/majority_eval.py A1.json A2.json A3.json [--vs B1.json B2.json B3.json]` — グループAの多数決mean・不安定問一覧を表示し、`--vs`指定時はA多数決→B多数決のflipを表示

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_majority.py`:

```python
from src.evaluator.majority import majority_labels, to_pseudo_run, unstable_questions


def _run(labels: dict[str, str]) -> dict:
    return {
        "summary": {},
        "results": [
            {"question_id": qid, "question": f"質問{qid}", "judge_label": label, "answer": "a"}
            for qid, label in labels.items()
        ],
    }


RUNS = [
    _run({"0": "Perfect", "1": "Missing", "2": "Perfect"}),
    _run({"0": "Perfect", "1": "Perfect", "2": "Missing"}),
    _run({"0": "Perfect", "1": "Missing", "2": "Incorrect"}),
]


def test_majority_unanimous_and_split():
    m = majority_labels(RUNS)
    assert m["0"]["label"] == "Perfect" and m["0"]["votes"] == 3
    assert m["1"]["label"] == "Missing" and m["1"]["votes"] == 2


def test_majority_three_way_tie_takes_worst():
    # Q2はPerfect/Missing/Incorrectの3すくみ → スコア最小のIncorrectを採用（保守側）
    m = majority_labels(RUNS)
    assert m["2"]["label"] == "Incorrect"


def test_unstable_questions_lists_non_unanimous():
    unstable = unstable_questions(RUNS)
    ids = {u["question_id"] for u in unstable}
    assert ids == {"1", "2"}


def test_to_pseudo_run_feeds_compare_runs():
    from src.evaluator.flip import compare_runs

    m = majority_labels(RUNS)
    pseudo = to_pseudo_run(m)
    rep = compare_runs(pseudo, pseudo)
    assert rep.unchanged_count == 3
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_majority.py -v`
Expected: FAIL — `No module named 'src.evaluator.majority'`

- [ ] **Step 3: 実装**

`src/evaluator/majority.py`:

```python
"""同一コードN runの多数決ラベル。±0.05のrun間ゆらぎ対策（next-steps §1 Task 4）。

多数決が同数（例: N=3で3ラベルが割れる）の場合はCRAGスコア最小のラベルを採用する
（楽観的な誤判定で実験を採択するより保守側に倒す）。
"""
from __future__ import annotations

from collections import Counter

from src.models import CRAGLabel


def _score(label: str) -> float:
    try:
        return CRAGLabel(label).score
    except ValueError:
        return 0.0


def majority_labels(runs: list[dict]) -> dict[str, dict]:
    by_id: dict[str, list[dict]] = {}
    for run in runs:
        for r in run["results"]:
            by_id.setdefault(r["question_id"], []).append(r)

    out: dict[str, dict] = {}
    for qid, records in by_id.items():
        counts = Counter(r["judge_label"] for r in records)
        top = max(counts.values())
        winners = [label for label, c in counts.items() if c == top]
        label = min(winners, key=_score)  # 同数はスコア最小（保守側）
        out[qid] = {
            "label": label,
            "votes": counts[label],
            "total": len(records),
            "question": records[0]["question"],
        }
    return out


def unstable_questions(runs: list[dict]) -> list[dict]:
    majority = majority_labels(runs)
    unstable = []
    for qid, m in majority.items():
        labels = sorted(
            r["judge_label"]
            for run in runs
            for r in run["results"]
            if r["question_id"] == qid
        )
        if len(set(labels)) > 1:
            unstable.append({"question_id": qid, "labels": labels, "question": m["question"]})
    return sorted(unstable, key=lambda u: u["question_id"])


def to_pseudo_run(majority: dict[str, dict]) -> dict:
    return {
        "summary": {},
        "results": [
            {
                "question_id": qid,
                "question": m["question"],
                "judge_label": m["label"],
                "answer": "",
            }
            for qid, m in sorted(majority.items())
        ],
    }
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_majority.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: スクリプトを書く**

`scripts/majority_eval.py`:

```python
"""N run多数決の評価。同一コードのrunを3つ渡すと多数決mean・不安定問を出す。

使い方:
  .venv/bin/python scripts/majority_eval.py A1.json A2.json A3.json
  .venv/bin/python scripts/majority_eval.py A1.json A2.json A3.json --vs B1.json B2.json B3.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluator.flip import compare_runs
from src.evaluator.majority import majority_labels, to_pseudo_run, unstable_questions
from src.models import CRAGLabel


def _load_group(paths: list[Path]) -> list[dict]:
    runs = []
    for p in paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        if "results" not in data:
            sys.exit(f"{p.name} はpipelineのrun JSONではありません（resultsキーなし）")
        runs.append(data)
    return runs


def _report_group(name: str, runs: list[dict]) -> dict:
    majority = majority_labels(runs)
    scores = [CRAGLabel(m["label"]).score for m in majority.values()]
    mean = sum(scores) / len(scores) if scores else 0.0
    print(f"\n=== {name}: 多数決mean {mean:.4f}（{len(runs)} run, {len(majority)}問） ===")
    unstable = unstable_questions(runs)
    if unstable:
        print(f"[不安定（全会一致でない）: {len(unstable)}問]")
        for u in unstable:
            print(f"  {u['question_id']}: {'/'.join(u['labels'])}  {u['question'][:50]}")
    return majority


def main() -> None:
    parser = argparse.ArgumentParser(description="N run多数決評価")
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--vs", nargs="+", type=Path, default=None,
                        help="比較先グループ（多数決同士でflip）")
    args = parser.parse_args()

    base_majority = _report_group("グループA", _load_group(args.runs))
    if args.vs:
        new_majority = _report_group("グループB", _load_group(args.vs))
        print()
        print(compare_runs(
            to_pseudo_run(base_majority), to_pseudo_run(new_majority),
            base_name="A多数決", new_name="B多数決",
        ).report())


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 実データで動作確認**

Run: `.venv/bin/python scripts/majority_eval.py experiments/phase2final_valid_1783092422.json experiments/phase2final_valid_1783093012.json experiments/phase0_valid_1783125252.json`
Expected: ベースライン多数決mean（0.13〜0.15近辺）と不安定問一覧（Q5/Q14等が出るはず）。この出力を**ベースライン多数決として控える**（Task 3〜5の比較元）。

- [ ] **Step 7: 全テスト→step-review→Commit**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS → step-review（haiku）→

```bash
git add src/evaluator/majority.py tests/test_majority.py scripts/majority_eval.py
git commit -m "flip安定化2: N run多数決評価（ゆらぎ対策の標準判定ツール）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: JSONパース堅牢化（実験①: Q18真因の決定的修正）

`_parse_response`が citation内の生改行（制御文字）で`json.loads`に失敗し、正しい回答をconf 0.0に落としていた（実測Q18）。`strict=False`で制御文字を許容する。

**Files:**
- Modify: `src/generator/answer_generator.py`（`_parse_response`1行）
- Test: `tests/test_generator.py`（追記）

**Interfaces:**
- Consumes/Produces: `_parse_response(raw: str) -> tuple[str, float, str]`（シグネチャ不変）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_generator.py`の`_parse_response`テスト群に追記:

```python
def test_parse_response_allows_raw_newline_in_strings():
    """citation内の生改行（制御文字）でパース失敗しない（実測Q18の真因）。"""
    gen = AnswerGenerator(threshold=0.4)
    raw = '{"answer": "第3章に記載", "confidence": 0.55, "citation": "3. 業務範囲\n乙が本契約に基づき"}'
    text, conf, citation = gen._parse_response(raw)
    assert text == "第3章に記載"
    assert conf == 0.55
    assert "業務範囲" in citation
```

（Pythonの通常文字列リテラルなので`\n`は生の改行としてJSONに入る＝再現条件）

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_generator.py -v -k parse_response`
Expected: 新規テストFAIL（現状は`(raw全文, 0.0, "")`が返る）。既存の`test_invalid_json_returns_raw_zero_confidence_and_empty_citation`はPASSのまま。

- [ ] **Step 3: 実装**

`src/generator/answer_generator.py`の`_parse_response`内:

```python
                data = json.loads(m.group(), strict=False)
```

（`strict=False`は文字列内の制御文字を許容するだけ。壊れたJSONのフォールバック挙動は不変）

- [ ] **Step 4: 全テスト実行**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS

- [ ] **Step 5: N=3実験**

```bash
for i in 1 2 3; do
  .venv/bin/python scripts/run_pipeline.py \
    --data-dir "data/raw/share/共有ドライブ" \
    --questions "data/raw/share/質問回答/questions_valid.csv" \
    --run-name flipfix_parse_valid
done
.venv/bin/python scripts/majority_eval.py \
  experiments/phase2final_valid_1783092422.json experiments/phase2final_valid_1783093012.json experiments/phase0_valid_1783125252.json \
  --vs experiments/flipfix_parse_valid_*.json
```

Expected: 多数決mean悪化なし・Incorrect増加なし。Q18は引用に省略記号が残る場合`gate_reason="citation"`に移るだけの可能性あり（それでも診断上の前進。回収はTask 4で）。判定基準（Global Constraints）で採否を決め、悪化なら`git revert`。

- [ ] **Step 6: step-review→Commit**

step-review（haiku。**生成経路の変更なのでリスク高め→sonnetでも可**）→

```bash
git add src/generator/answer_generator.py tests/test_generator.py experiments/flipfix_parse_valid_*.json
git commit -m "flip安定化3: JSONパースstrict=False（citation内制御文字でconf 0.0落ちするQ18型を修正）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 引用プロンプトの強化（実験②: 短い連続引用・省略記号禁止）

長い引用・中略入り引用は`citation_supported`の実在チェックに落ちる（写し間違い・省略記号）。SYSTEM_PROMPTのルール5を強化する。

**Files:**
- Modify: `src/generator/answer_generator.py`（`SYSTEM_PROMPT`のみ）
- Test: `tests/test_generator.py`（プロンプト退行ガード1本）

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_system_prompt_constrains_citation_length_and_ellipsis():
    from src.generator.answer_generator import SYSTEM_PROMPT
    assert "30字" in SYSTEM_PROMPT
    assert "省略" in SYSTEM_PROMPT
```

- [ ] **Step 2: 失敗確認**

Run: `.venv/bin/pytest tests/test_generator.py -v -k system_prompt`
Expected: FAIL

- [ ] **Step 3: SYSTEM_PROMPTのルール5を差し替え**

```python
5. 回答の直接の根拠となった文書中の一節を、そのまま "citation" に引用すること。
   - 引用は文書中に連続して現れる短い一節（30字以内）を一字一句そのまま抜き出す
   - 要約・言い換え・中略・改行・省略記号（… や ...）を含めることは禁止
   - 引用文が参考文書中に一字一句存在しない場合、回答は無効として扱われます
```

【出力形式】の`"citation"`の説明も`"根拠の一節（30字以内・連続部分をそのまま抜粋）"`に合わせる。

- [ ] **Step 4: 全テスト実行**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

- [ ] **Step 5: N=3実験**

```bash
for i in 1 2 3; do
  .venv/bin/python scripts/run_pipeline.py \
    --data-dir "data/raw/share/共有ドライブ" \
    --questions "data/raw/share/質問回答/questions_valid.csv" \
    --run-name flipfix_cite_valid
done
.venv/bin/python scripts/majority_eval.py \
  experiments/flipfix_parse_valid_*.json \
  --vs experiments/flipfix_cite_valid_*.json
```

（比較元はTask 3採用後の3run。Task 3を革命的に不採用にした場合はベースライン3runと比較）
Expected: Q18が多数決Perfect側へ、`gate_reason="citation"`の件数減。不安定問（Q5/Q27等）の全会一致化が進む。判定基準で採否。

- [ ] **Step 6: step-review→Commit**

```bash
git add src/generator/answer_generator.py tests/test_generator.py experiments/flipfix_cite_valid_*.json
git commit -m "flip安定化4: 引用は30字以内の連続一節・省略記号禁止（citation実在チェック偽陰性の抑制）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: 直答形式の強化（実験③: Q17型の用語言い換え対策）

Q17はconf 0.85で正答相当を出したが「未連絡」を「前回未接触」と言い換えてofficial Incorrect。文書中の表記そのままの短い直答を冒頭に置くルールを足す。

**Files:**
- Modify: `src/generator/answer_generator.py`（`SYSTEM_PROMPT`にルール6追加）
- Test: `tests/test_generator.py`（プロンプト退行ガード1本）

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_system_prompt_requires_direct_answer_with_document_wording():
    from src.generator.answer_generator import SYSTEM_PROMPT
    assert "言い換えない" in SYSTEM_PROMPT
```

- [ ] **Step 2: 失敗確認**

Run: `.venv/bin/pytest tests/test_generator.py -v -k direct_answer`
Expected: FAIL

- [ ] **Step 3: SYSTEM_PROMPTの【重要ルール】にルール6を追加**

```python
6. 設問が特定の用語・数値・名称・章番号など短い事実を問う場合、文書中の表記をそのまま使って
   回答の冒頭で短く直答し、必要な補足はその後に続けること（文書の用語を別の言葉に言い換えない。
   例: 文書が「未連絡」と書いていれば「前回未接触」等に言い換えず「未連絡」と答える）。
```

**注意**: 例に使う語は上記の一般語のみ。特定の案件名・質問文・正解値をプロンプトに入れない（規約）。※「未連絡」は汎用語だが、気になる場合は「文書の表記を優先する」の抽象例に差し替えてよい — 実装者は`competition.md`のハードコード禁止規定を読んで判断すること。

- [ ] **Step 4: 全テスト実行**

Run: `.venv/bin/pytest tests/ -v` → 全件PASS

- [ ] **Step 5: N=3実験**

```bash
for i in 1 2 3; do
  .venv/bin/python scripts/run_pipeline.py \
    --data-dir "data/raw/share/共有ドライブ" \
    --questions "data/raw/share/質問回答/questions_valid.csv" \
    --run-name flipfix_direct_valid
done
.venv/bin/python scripts/majority_eval.py \
  experiments/flipfix_cite_valid_*.json \
  --vs experiments/flipfix_direct_valid_*.json
```

Expected: Q17型の改善、悪化なし。**回答が短くなることでlocal judgeの判定が変わる問（Q27型）への影響も不安定問一覧で確認**。判定基準で採否。

- [ ] **Step 6: step-review→Commit**

```bash
git add src/generator/answer_generator.py tests/test_generator.py experiments/flipfix_direct_valid_*.json
git commit -m "flip安定化5: 短答系設問は文書表記そのままの直答を冒頭に（用語言い換えによるIncorrect対策）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: 結果の記録と計画更新

- [ ] **Step 1: `docs/plan/plan_0703.md`に実験結果を追記**（§2.1の下に「2.2 フリップ層安定化の実測（YYYY-MM-DD）」節: 各実験の多数決mean before/after・採否・flip内訳・不安定問数の推移）
- [ ] **Step 2: `docs/plan/2026-07-04-next-steps.md` §2のチェックボックスを更新**（完了項目に日付とコミットSHA）
- [ ] **Step 3: `docs/daily作業ログ/`に新規ログ**（目的→結果→やったこと（SHA付き）→学び→残課題）
- [ ] **Step 4: Commit**

```bash
git add docs/plan/ "docs/daily作業ログ/"
git commit -m "flip安定化: 実験結果の記録と計画更新

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review 済みの注意点（実装者向け）

1. **ゲート順序を変えない**。gate_reasonは記録のみ（Task 1）。looks_like_missing→confidence→citationの順は既存テストが前提にしている。
2. **threshold=0.4は不変**（Phase 5まで温存。next-steps §2の明記事項）。
3. Task 3のstrict=Falseは「文字列内の制御文字許容」のみ。既存の壊れJSONフォールバック（`(raw, 0.0, "")`）のテストを壊さないこと。壊れたら実装が過剰。
4. プロンプト変更（Task 4・5）の効果検証はユニットテストでは不可能 — N=3多数決が唯一の判定。**単一runの比較で採否を判断しない**（±0.05ゆらぎ）。
5. 実験がプラマイゼロでも「不安定問の全会一致化」が進んでいれば安定化としては成功（目的はゆらぎ回収）。mean だけで判断せず不安定問一覧を見る。
6. 各実験はrun JSON（`experiments/flipfix_*_valid_*.json`）をコミットに含める（再現性・台帳）。
7. `make_predictions.py`はSYSTEM_PROMPT等を`answer_generator.py`から共有しているため今回の変更が自動で提出経路にも効く（二重管理なし）。念のためTask 5完了後に`grep -n "SYSTEM_PROMPT" scripts/make_predictions.py src/`で単一定義を確認。
