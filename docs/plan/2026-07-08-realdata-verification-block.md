# 実データ検証ブロック（2026-07-08策定）— A: ローカル環境（data/raw あり）での検証タスク

> 位置づけ: 2026-07-07セッション（`docs/daily作業ログ/20260707_010823.md`、PR #2 = `7cd9756`）で
> クラウド環境（`data/raw`無し）のままmainに入ったコード変更群の**実データ検証**。
> このリポジトリの運用規約（1実験1変更・N=3多数決で採否確定してから次へ）に照らすと、
> これらを未検証のまま次の実装を重ねるのが現状最大のリスク。**新規実装より本ブロックを優先する。**
> 兄弟ドキュメント: `2026-07-08-cloud-implementable-tasks.md`（B: 実データ不要でTDD可能な実装タスク）。

## 検証対象（mainに入っている未検証コミット）

| コミット | 内容 | 影響範囲 | 検証タスク |
|---|---|---|---|
| `782aead` | 検索クエリからの案件名・エイリアストークン除去（タイトルスライド汚染対策・案A） | **全設問の検索結果**（プロジェクトスコープ確定時） | Task 1 |
| `1cec020` / `e7913aa` | `project_names()` NFC/NFD重複バグ修正＋回帰テスト | Q15型（`MilestoneThresholdListAnswerer`） | Task 2 |
| `c011861` | パスワード保護Office復号ユーティリティ（`src/utils/office_crypto.py`、**未配線**） | contract_rule（Q38/Q79） | Task 3 |

## 実行環境・判定の約束（`2026-07-05-coverage-block-for-codex.md` から継承。厳守）

- 評価コマンド:
  ```bash
  for i in 1 2 3; do .venv/bin/python scripts/run_pipeline.py \
    --data-dir "data/raw/share/共有ドライブ" \
    --questions "data/raw/share/質問回答/questions_valid.csv" --run-name <実験名> --no-cache; done
  .venv/bin/python scripts/majority_eval.py experiments/vdiff2_valid_*.json --vs experiments/<実験名>_*.json
  ```
- **比較元グループ**: `experiments/vdiff2_valid_*.json`（3run: `1783340518`/`1783340631`/`1783340743`、
  official mean **0.4667** = `judge_calibration_1783341078.json`、7/6時点の採用構成）
- 判定原則: mean単独で採否を判定しない。多数決＋不安定問一覧＋raw_answer目視＋official較正
  （`scripts/calibrate_judge.py <run.json>`）。**officialのIncorrect問の顔ぶれの変化**で読む。
  迷ったら保守側（不採用はrevertし、run JSONだけ証跡コミット）
- パースキャッシュはコード変更を検知しない（フィンガープリントはdata_dir構成のみ）。
  レジストリ・パーサに触れるTask 2/3では**必ず`--no-cache`か`rm -rf .cache`**
- NFC/NFD: ファイルパス由来文字列はNFD。新しい文字列比較は必ず両辺`unicodedata.normalize("NFC", ...)`

## Task 1: `exp_rankfix_valid` — 検索ランキング変更（`782aead`）の採否確定【最優先】

`2026-07-05-coverage-block-for-codex.md` Task 3の実験部分（コード実装は完了済み、実験のみ残）。

- [ ] N=3 run（`--run-name exp_rankfix_valid --no-cache`）→ vdiff2比較の多数決
- [ ] **判定ポイント**: タイトルスライド汚染組 **Q2 / Q12 / Q19** のMissing→回収があるか。
      既存Perfect勢（Q8/Q13/Q20/Q21/Q25/Q26等）に退行がないか
- [ ] 回答形式に関わらない変更だが、検索結果が広く変わるためofficial較正も1回実施
- [ ] **不採用なら`782aead`をrevert**（テスト`tests/`の回帰テストは実データ想定フィクスチャなので
      revert時はテストも巻き戻す）。採用なら`plan_0703.md`に実測を追記
- [ ] 案Aで不足なら案B（表紙スライドのチャンクレベル降格）の要否をここで判断

**期待効果**: Q2/Q12/Q19回収で+0.06〜0.10相当（valid）。test側はtext_only Missing 39問の一部に波及。

## Task 2: `project_registry.json` の `primary_alias` 付き再生成 ＋ Q15/Q16 診断run

internal_termsブロック（`done_2026-07-06-internal-terms-ms-date.md`）の未実施分＋NFC/NFD修正の実地確認。
**Task 3の前提**（パスワード導出 `DA-[案件略号]-…` の案件略号 = `primary_alias`）なので先に実施。

- [ ] `scripts/build_registries.py` を実データで再実行し、`artifacts/project_registry.json` に
      `primary_alias` フィールドが全案件分入ることを確認（KAEDE等、`社内用語集.docx`の主略称と一致）
- [ ] valid **Q15**（閾値リスト型）診断run: `1cec020`修正前に出ていた「AYM、AYM」重複が解消されているか
- [ ] valid **Q16**（期間計算型）診断run: `MilestoneDurationAnswerer`の発火と回答値を確認
- [ ] 効果があればN=3に含めて較正（Task 1の実験と混ぜない。1実験1変更）

## Task 3: かえで契約書の復号配線 → `contracts.jsonl` 再生成 → Q38/Q79 診断

`2026-07-07-contract-rule-followup-todo.md` §1の本実施。
**配線コード自体はBのTask 2（クラウドで先行TDD可能）** — 済んでいればここは実データ確認のみ。

- [ ] `build_contract_registry.py`で `契約書_pw-kaede20250902.docx`（CDFV2暗号化、現状`status=failed`）を
      `derive_office_password()` + `decrypt_office_file()` 経由で復号して抽出
- [ ] `contracts.jsonl` 再生成 → かえで行が `status=ok` になること、`start_date`/`amount`等が埋まることを確認
- [ ] **Q38診断run**: かえで（医療案件・金額帯次第で医療補正→APR-M3）が回答に加わるか。
      現状はMissingへ安全側後退中（`contract_fix_test_diag_1783351147.json`）
- [ ] 同規則でかえでの `02.計画/スケジュール.xlsx` も復号できるか確認（**Q79の前提条件**）
- [ ] 白峰の契約期間regex修正（B Task 1）が入っていれば、白峰行の
      `start_date`/`end_date`/`contract_period_days` が埋まることも同時に確認

**期待効果**: Q38が真に解ける可能性（+1問）＋Q79着手の前提解消。

## Task 4: 提出（Task 1〜3の採否確定後に1回）

- [ ] 採用構成でtest 100問を`--runs 3`安定化生成（7/5にLB 0.13333で効果実証済みの標準運用）
- [ ] 提出前にpredictions.csvの前回提出（`submission_20260706_pptxfix3run.zip`）とのdiffを確認し、
      変更問を`docs/daily作業ログ/`に記録（LB変動の切り分け材料）
- [ ] `plan_0703.md` §1.1.1 提出履歴にLB実測を追記

## 推奨順序

| 順 | タスク | 理由 |
|---|---|---|
| 1 | Task 1（rankfix検証） | 影響範囲が全設問に及ぶ変更を最初に白黒つける |
| 2 | Task 2（primary_alias再生成＋Q15/Q16） | Task 3のパスワード導出の前提 |
| 3 | Task 3（かえで復号→Q38/Q79） | B Task 2の配線が済んでいれば確認のみ |
| 4 | Task 4（提出） | 採否確定した構成でまとめて1回（無駄撃ちしない） |
