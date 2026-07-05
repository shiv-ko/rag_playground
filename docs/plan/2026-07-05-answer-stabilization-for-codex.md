# 提出物の複数run安定化（正規化＋多数決 N=3）実装指示書 — Codex向け

> 位置づけ: plan_0703 §1.1.1 の2026-07-05行（LB 0への対応）。単発runの生成ゆらぎ
> （Q42型の値欠け不完全回答・Q18型の少数派誤答）が1/30粒度のLBで顕在化したため、
> **提出用predictions.csv生成時のみ**N=3多数決で安定化する。設計（一致基準=正規化＋多数決）は
> 既存 `exp_pivotagg_valid`×3 の机上実測に基づきユーザー承認済み（2026-07-05）。
> レビューは `.claude/skills/step-review` テンプレートのセルフレビューを各コミット前に1周。
> 開発規約は `.codex/skills/dev-process.md`（TDD）。

## 実行環境・検証の約束

- テスト: `.venv/bin/pytest tests/ -v`（現在**321件**、全件PASS維持）
- **CodexはLLM APIに接続できない**。test 3run生成・official較正・提出判断はClaudeが代行する。
  Codexは決定的検証のみ:
  1. ユニットテスト（合成回答リストのみ）
  2. オフライン検証: git管理済みの `experiments/exp_pivotagg_valid_*.json` 3本（LLM不要）に
     実装を適用して期待動作を確認（後述Task 3）
- 実装が終わったら**コミットして停止し、Claudeに引き継ぐ**
- NFC/NFD: 新しい文字列比較は必ず両辺 `unicodedata.normalize("NFC", ...)`（このリポジトリで6回目の
  事故を起こさない。回答文字列にも実データ由来の値が入る）
- 競技規約: 特定の案件名・質問・正解値のハードコード禁止。**正規化ルールは下記に固定仕様として
  列挙したもののみ実装する**（これは自前のrun出力の表記ゆれ実測に基づく一般則で、GT由来ではない）。
  テストのフィクスチャは合成値（「1,234円」「東京」等の架空回答）を使い、実データの回答値を書かない
- スコープ外（触らない）: `scripts/run_pipeline.py`・`scripts/majority_eval.py`（valid実験フローは
  従来通り生run比較）、検索レイヤ全般、`src/generator/`・`src/orchestrator/pipeline.py` の回答生成経路
- `--runs 1`（デフォルト）の挙動は**現状と完全同一**であること（安定化コードパスを通らない）

## 前提となる現状（2026-07-05、`3bcc255`時点）

- 提出履歴: phase2-remainder LB 0.03333 → pivotagg LB **0**（net -1/30）。差分8問中7問が
  生成ゆらぎ、第一容疑はQ42の値欠け不完全回答（plan_0703 §1.1.1参照）
- `exp_pivotagg_valid`×3（コミット済み）の実測: 回答あり16問中、13問はバイト同一3/3。
  ゆらぎ3問の内訳が設計根拠そのもの:
  - Q8型: 「¥1,168,750」「1,168,750円」「1,168,750円少なくなる」の3表記・**全部Perfect**
    → 素の一致判定では捨ててしまう。正規化で2/3が同一視でき採用可能
  - Q18型: 「3」「3」「4」（Perfect/Perfect/Incorrect）→ 多数決で-1を遮断し+1維持
  - Q28型: Missing/Missing/Incorrect回答 → 多数決でMissing化し-1を遮断

## 関連コードの事実（実装前に実物を確認）

- `scripts/make_predictions.py`: `pipeline.build_index()` → `results = pipeline.run(qa_pairs)` →
  `sorted(results, key=lambda r: int(r.question_id))` で `[r.question_id, r.answer]` をCSV書き出し。
  `run_judge=False`・`cache_dir`なしは意図的仕様（20260704_005800ログ）— 変えない
- `src/orchestrator/pipeline.py:51` `PipelineResult`: `question_id: str` / `answer: str` ほか。
  `run()` はindex構築後なら複数回呼べる（内部状態はindexのみ）
- Missing定型文は `src/generator/confidence_gate.py:6` の `MISSING_RESPONSE` 定数。
  **文字列を再定義せず必ずここからimportする**（二重管理ドリフト防止）

---

## Task 1: `src/orchestrator/answer_stabilizer.py`（新規） — 純粋関数のコアロジック

LLM・ファイルI/O・Pipeline依存を持たない純粋関数のみ。

```python
@dataclass(frozen=True)
class StabilizationDecision:
    question_id: str
    chosen: str               # 採用回答（不一致時は MISSING_RESPONSE）
    reason: str               # "unanimous" | "majority" | "no_majority" | "all_missing" | "single_run"
    cluster_sizes: dict[str, int]   # 正規化キー → run数（監査用）
    run_answers: list[str]    # 各runの生回答（監査用）

def normalize_answer(text: str) -> str: ...
def stabilize_answers(
    question_ids: list[str],
    per_run_answers: list[list[str]],   # [run][question] の生回答。全runで質問数一致が前提
) -> list[StabilizationDecision]: ...
```

**normalize_answer の固定仕様**（この順で適用。追加・変更しない）:
1. `unicodedata.normalize("NFC", text)`
2. `casefold()`
3. 次の文字を除去: 空白類（`\s`）・句読点/記号 `、。，,．.・:：;；()（）「」`・通貨記号 `¥￥＄$`
4. 単位語 `円` `ドル` `jpy` を除去（3の後に適用。casefold済みなのでJPYはjpyで消える）
5. `MISSING_RESPONSE`（正規化前の完全一致で判定）は専用センチネル（例 `"\x00missing"`）に写す —
   通常回答の正規化結果と衝突しない値にする

**stabilize_answers の固定仕様**:
- N = len(per_run_answers)。**N==1 は素通し**（chosen=生回答、reason="single_run"）
- 質問ごとに正規化キーでクラスタし、サイズ >= N//2+1 のクラスタがあれば採用:
  - 代表回答 = クラスタ内で最頻の**生文字列**。同数タイは**run番号が小さい方**（決定的）
  - Missingクラスタが過半 → `MISSING_RESPONSE`（reason="all_missing"）
- 過半クラスタなし → `MISSING_RESPONSE`（reason="no_majority"）

- TDD（`tests/test_answer_stabilizer.py` 新規。全て合成回答）:
  - normalize: 「1,234円」「¥1,234」「 1,234 JPY」が同一キー、「3」と「4」は別キー、
    NFD文字列とNFC文字列が同一キー
  - 多数決: 2/3一致で代表採用（代表は最頻生文字列）、3種割れ→MISSING_RESPONSE、
    Missing 2/3 + 回答1 → MISSING_RESPONSE
  - Q8型: 表記3種だが正規化で2/3一致するケース → 一致クラスタ内の生文字列（頻度タイならrun番号が
    小さい方）が採用されること
  - N=1素通し、N=2（1対1割れ→no_majority）の境界
  - 全run質問数不一致 → ValueError（黙って壊れない）
- 全テストPASS → セルフレビュー → コミット

## Task 2: `scripts/make_predictions.py` に `--runs N`（default 1）

- N>1のとき: `build_index()` 1回 → `pipeline.run(qa_pairs)` をN回 → 各runの
  `sorted(..., key=int(question_id))` 済み回答列を `stabilize_answers` へ → chosen をCSV書き出し
- 監査ファイル: `experiments/predictions_stability_<unixtime>.json` に
  `{"runs": N, "decisions": [StabilizationDecisionの辞書…]}` を保存（Claudeが提出前に目視し、
  証跡としてコミットする）
- `--runs 1` は既存コードパスのまま（stabilizerを通さない）。既存の出力と同一であること
- テスト: スクリプト本体はロジックを持たないので新規テスト不要（集約はTask 1でテスト済み）。
  ただし question_id とanswerの対応がrun間でズレない実装にすること（**必ずquestion_idでソートしてから
  突合**。pipeline.runの返却順は保証しない前提で書く）
- コミット（Task 1と分けること）

## Task 3: オフライン検証（Codexが実行して作業ログに記録）

git管理済みの実データrun 3本で期待動作を確認する（一時スクリプトでよい。コミット不要）:

```
experiments/exp_pivotagg_valid_1783181875.json / _1783181996.json / _1783182122.json
の results[*].answer を per_run_answers に組んで stabilize_answers を実行
```

確認項目（数値はこの3runの実測。**テストコードには書かない**）:
- 30問中、全runでMissingの14問 → reason="all_missing" でMissingのまま
- バイト同一13問 → reason="unanimous" で生回答そのまま
- Q8 → majority採用（クラスタ2/3）で「¥1,168,750」か「1,168,750円」のどちらか
- Q18 → 「3」採用 / Q28 → MISSING_RESPONSE
- 全30問で question_id と回答の対応ズレなし

結果（件数内訳）を作業ログに記録する。

## Task 4: 引き継ぎ（Codexはここで停止）

1. `.venv/bin/pytest tests/ -v` 全件PASSを最終確認
2. 作業ログ `docs/daily作業ログ/YYYYMMDD_HHMMSS.md`（実装サマリ・テスト件数・Task 3の内訳・迷った点）
3. コミットして**停止**。以降はClaude側:
   - 安定化後valid回答のofficial較正（既存3runから合成、悪化なし確認）
   - `make_predictions.py --runs 3` でtest生成 → 前回提出とのdiff目視 → zip → 提出判断
   - 監査ファイルの証跡コミット

## スコープ外（手を出さない）

- valid実験フロー（run_pipeline / majority_eval / calibrate_judge）の変更
- 正規化ルールの拡張（同義語・言い換えの吸収はしない — 記号と単位のみ）
- 検索レイヤ・生成プロンプト全般
