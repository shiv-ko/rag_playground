# クラウド実装タスク（2026-07-08策定）— B: 実データ不要でTDD可能な実装タスク

> 位置づけ: `data/raw`（実データ）が無いクラウド環境でも、合成フィクスチャによるTDDで
> 安全に進められる実装タスク群。出典は `2026-07-07-contract-rule-followup-todo.md` の§1/§3/§4。
> 実データでの発火確認・レジストリ再生成は兄弟ドキュメント
> `2026-07-08-realdata-verification-block.md`（A）に委譲する。
> **注意**: Aブロック Task 1（`782aead`の採否）が未確定のうちは、検索まわりに触れる変更は避ける
> （本ドキュメントの3タスクはいずれも検索パス非依存なので並行可）。

## 開発規約（従来通り。厳守）

- TDD・1タスク1コミット・コミット前にstep-review（`.claude/skills/step-review`、
  サブエージェントはSonnet/Haikuを難易度で使い分け）
- テスト: `.venv/bin/pytest tests/ -v`（現在**464 passed**。全件PASS維持）
- venvが無い環境では `python3 -m venv .venv && .venv/bin/pip install -e ".[parsers,search,dev]" msoffcrypto-tool`
- NFC/NFD: 新しい文字列比較は必ず両辺 `unicodedata.normalize("NFC", ...)`（このリポジトリで4回起きた事故）
- 競技規約: 特定の案件名・ファイル名・質問文・正解のハードコード禁止（`competition.md` / `rule.md`）。
  復号やファイル特定は**汎用規則**（命名パターン・レジストリ由来値）で導出すること

## Task 1: 白峰の契約期間抽出regexバグ修正【低リスク・最初にやる】

出典: followup-todo §3。`scripts/build_contract_registry.py:139` の `extract_dates()` が
「日?から」「日?まで」の直前にスペースを許容しないため、白峰の契約書
（「2025-05-13 から 2025-07-22 まで」とスペース入り表記）で `start_date`/`end_date` が両方nullになる。

- [x] 該当regex 2箇所（139行の期間型・145行の起算型）に `\s*` を許容:
      `日?\s*から`, `日?\s*まで`, `日?\s*から起算して`（2026-07-08 `47d85b3`）
- [x] 回帰テスト追加: スペース入り表記（`2025-05-13 から 2025-07-22 まで`）で
      `start_date`/`end_date`/`contract_period_days` が正しく返ること＋既存表記の非退行（`47d85b3`）
- [ ] `contracts.jsonl` の再生成は実データ必須 → Aブロック Task 3に委譲（白峰行の確認項目を記載済み）

**期待効果**: 直接の設問影響は現状なし（白峰はQ26の指定期間と重複しない）が、
`contract_period_days` を使う横断集計全般への波及リスクを除去。

## Task 2: 復号ユーティリティの `build_contract_registry.py` への配線

出典: followup-todo §1。`src/utils/office_crypto.py`（`c011861`）は実装済みだが呼び出し側が未配線。
現状は `build_contract_registry()`（`scripts/build_contract_registry.py:212` 付近）で
`read_docx_text(path)` が暗号化ファイルで例外→`status=failed` に落ちる。

- [x] 配線方針: `read_docx_text` 失敗時（または暗号化検出時）に
      `derive_office_password(primary_alias, start_date, ext)` → `decrypt_office_file()` →
      復号済み一時ファイルに対して再度 `parse_contract_text` を試みるフォールバックを追加。
      復号失敗（`InvalidKeyError`）時は従来通り `status=failed` に落とす（挙動非退行）
      （2026-07-08 `2d715b5`。フォールバック適用範囲は`read_docx_text`失敗時のみに限定し、
      parse/report抽出の無関係な例外を握り潰さないようレビューで修正済み）
- [x] **設計上の論点（実装前に決める）**: パスワードの「開始年月日8桁」の入手元。
      契約書自体が暗号化されており中身から取れない鶏卵問題があるため、候補は
      ①ファイル名の汎用パターン（`pw-<alias><8桁>` 型の命名規則から抽出 — 特定ファイル名の
      ハードコードではなく正規表現による汎用規則なら規約適合）
      ②スケジュールxlsx等の別ソース由来の日付候補を順に試行（`InvalidKeyError`で棄却）。
      いずれも案件略号は `project_registry.json` の `primary_alias` を使う
      （＝Aブロック Task 2の再生成が実データ側の前提）
      → **採用: ①ファイル名パターンを最優先候補、`project_registry.json`の`primary_alias`を
      補助候補として順に試行**（`InvalidKeyError`は次候補へ）。②は未実装（実データでの
      検証が前提のためAブロックへ委譲）
- [x] TDD: 合成暗号化docxフィクスチャで「暗号化→配線経由で復号→抽出成功」「誤パスワード→
      `status=failed`」の両経路をテスト。**footgun**: `msoffcrypto-tool` 6.0.0は暗号化側に
      4KB未満ペイロードでmini-FAT/regular-FAT不整合バグがあるため、フィクスチャは
      パディングして4KB以上にする（`tests/` の既存フィクスチャ生成コードを流用）（`2d715b5`）
- [ ] 実データでの `contracts.jsonl` 再生成・Q38/Q79診断はAブロック Task 3に委譲

**期待効果**: Aブロック Task 3が「実行して確認するだけ」になる。復号は他の暗号化ファイル
（かえでスケジュールxlsx等）にも汎用的に効く。

## Task 3: Q87型（APR-M1該当・完了案件・サンプル数10000行以上）の実装

出典: followup-todo §4。未実装のcontract_rule系3問（Q46/Q67/Q87）のうち、
**Q87だけは既存部品の組み合わせで実データ調査なしに実装可能**（Q46は座席表registry、
Q67は提案書/FR金額突合の実データ調査が先行のため対象外）。

- [x] 部品はすべて既存: APR判定 = `determine_apr_level()`（`src/generator/approval_rule.py:7`、
      金額・医療・T&Mの決定的関数）、train.csv行数 = `src/generator/contract_calc.py:252`
      `_answer_fixed_per_row()` の `rglob("train.csv")` パターンを流用（`_project_row_count()`
      へ切り出し、`_answer_fixed_per_row`側もこれを使うよう統一。2026-07-08 `551e75e`）
- [x] 「完了案件」の判定基準を既存registry（`contracts.jsonl` の報告書由来フィールド等）から
      決める — 実装前に既存answerer（Q26/Q31/Q37系）がどう判定しているか実物確認
      → 採用: `final_amount_incl_tax`/`actual_hours`（06.報告書由来）のいずれかが非Noneなら完了
- [x] 質問ルーティング: `contract_rule` 系answerer（`src/generator/contract_calc.py` /
      `approval_rule.py` の既存ディスパッチ）に条件追加。**該当0件・判定不能はMissingへ**
      （ゲート厚めの原則）（`551e75e`）
- [x] TDD: 合成 `contracts.jsonl` フィクスチャ＋合成train.csvで「APR-M1×完了×10000行以上」の
      絞り込みを検証。実データでの発火確認（test Q87診断run）はAブロックに委譲（`551e75e`）

**期待効果**: +1問相当（test）。低コスト（既存パターン流用）。

## 推奨順序と完了条件

| 順 | タスク | 理由 |
|---|---|---|
| 1 | Task 1（白峰regex） | 最小リスク・即完了。Task 2のテストでも期間抽出を使う |
| 2 | Task 2（復号配線） | Aブロック Task 3の前提。設計論点1つのみ |
| 3 | Task 3（Q87） | 既存部品流用だが、ルーティングと完了判定の設計が必要 |

完了条件: 3タスクとも「実装→全件PASS→step-review→コミット」で main へ。
その後の実データ検証・診断run・提出はすべて `2026-07-08-realdata-verification-block.md`（A）で行う。

## 完了ログ（2026-07-08）

3タスクとも実装完了。テストは464 passed（開始時）→479 passed（完了時、全件維持）。
各タスクをSonnetサブエージェントに実装させ、別のSonnetサブエージェントにレビューさせる
step-reviewフローで進行。Task 2はレビューで「無関係な例外の握り潰し」CONFIRMED指摘が出て
親エージェントが修正、Task 3はレビューで「train.csv行数取得ロジックの二重管理」PLAUSIBLE
指摘が出て`_answer_fixed_per_row`側を共用メソッドへ統一。詳細は
`docs/daily作業ログ/20260708_085900.md` を参照。

- Task 1: `47d85b3`
- Task 2: `2d715b5`
- Task 3: `551e75e`
