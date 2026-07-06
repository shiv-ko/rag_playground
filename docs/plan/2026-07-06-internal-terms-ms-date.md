# internal_terms: マイルストーン日付解決による日数計算・横断リスト（2026-07-06計画）

> 位置づけ: `plan_0703.md` Phase 3 `internal_terms`（test 11問）の着手。`docs/plan/2026-07-04-next-steps.md`
> §4 の「internal_terms（test 11問）はPhase 3扱いで追加検討: valid Q15/Q16はMS日付・営業日計算系」を具体化する。
>
> **このセッションの制約**: `data/raw/`・Anthropic/OpenAI APIキーが無いクラウド環境で計画された。
> そのため本計画は「実データを見ずに書く」のではなく、**既にgit管理下にある実データ由来artifacts**
> （`artifacts/schedule_tasks.jsonl` `artifacts/term_registry.json` `artifacts/project_registry.json`。
> いずれも前セッションが実データから生成済み・コミット済み）を根拠に設計している。version_diffの
> `version_diff_poc.jsonl`と同じ位置づけ。したがって実装・TDD検証はこのセッション同様、次のセッションでも
> `data/raw`無しで完結できる。
>
> 実装時は `.claude/skills/dev-process`（TDD厳守）・`.claude/skills/step-review`（コミット前レビュー）に従うこと。

## 1. 対象の実問題

- **valid Q16**（`docs/question_labels.csv` index 16, `internal_terms`, `numeric_exact`/`date_or_duration`）:
  > MINAMINOのPLにおいて、M01当日を1日目として数えた場合、M01の日からFR実施までの日数は何日ですか。
- **valid Q15**（同 index 15, `internal_terms`, `list_extraction`）:
  > 中間報告会または中間レビューが2025年7月1日以前に実施された案件を、主略称ですべて挙げてください。
- test側にも同型の設問が11問中に含まれる見込み（`primary_type=internal_terms`のうちMS日付系）。

## 2. 実データ実測済みの事実（根拠）

### 2.1 `artifacts/term_registry.json`（245件）にMSコードの一般語義が既に登録済み

```json
{"term": "M01", "expansion": "キックオフ", "note": "会議ID運用と合わせやすい"}
{"term": "M02", "expansion": "中間報告", "note": "同上"}
{"term": "M03", "expansion": "最終報告", "note": "同上"}
{"term": "FR", "expansion": "最終報告書", "note": "Final Report"}
```

### 2.2 `artifacts/schedule_tasks.jsonl`（473行・9案件）のマイルストーン表現は**案件ごとに書式がバラバラ**

9案件全件を実際にgrepして確認した実測（キックオフ/中間報告/最終報告に該当する行の`タスク名`/`備考`）:

| 案件 | キックオフ | 中間 | 最終 | 備考 |
|---|---|---|---|---|
| 青嶺不動産（AOM） | 備考=「M01 キックオフ会議」、MS=「MS1: キックオフ完了・前提固定」 | 備考=「M02 中間報告会議」 | 備考=「M03 最終報告会議」 | **`（M0N）`ではなく素の`M0N `**が備考に前置き |
| 東都（TOTO） | タスク名=「キックオフ会議実施（M01）」 | タスク名=「中間報告会議実施（M02）」 | タスク名=「最終報告会議実施（M03）」 | **`（M0N）`が taskname 末尾**の別書式・MS1〜MS7の別行(`MS1`,`MS4`等)も存在 |
| 白峰（SHI） | タスク名=「キックオフ実施（M01）」 | タスク名=「分析方針レビュー実施（M02）」→ **中間レビューはM03**「中間レビュー実施（M03）」 | **最終レビューはM04**「最終レビュー実施（M04）」 | **M番号の意味付けが他案件と異なる**（M02=分析方針、M03=中間、M04=最終） |
| みなみ野（MINAMINO） | 備考=「CP1：キックオフ完了」タスク名=「キックオフ実施・開始合意」 | タスク名=「中間レビュー実施」 | タスク名=「最終成果物提出・最終報告会」備考=「CP6：最終成果物提出・最終報告会完了」 | **M0N表記が一切無い**。キーワードのみ |
| 青潮(AOSHIO)/青葉バイオ(ABM)/青葉与信(AY)/蒼泉会(SOHK)/京橋(KSS) | 「キックオフ会議実施」等 | 「中間報告会実施」「中間レビュー実施」等 | 「最終報告会実施」「最終報告・検収会実施」等 | M0N表記なし、または`MS1対応`のように断片的 |

**結論**: `M0N→キックオフ/中間報告/最終報告`という`term_registry`の一般対応は**白峰では成立しない**
（白峰はM01=キックオフ、M02=分析方針、M03=中間、M04=最終という独自付番）。したがって解決ロジックは
**(a) 案件のスケジュール内に文字通り`(M0N)`表記があればそれを最優先**し、**(b) 無ければ
`term_registry`の語義キーワードで意味的に検索**という2段構えにする必要がある。

### 2.3 `artifacts/project_registry.json`の`aliases`は**アルファベット順ソートで「主略称」ではない**

`scripts/build_registries.py:71` の `aliases_for()` は `sorted(alias for alias in aliases if alias)` で
返しており、`src/utils/glossary.py:56` の `parse_project_aliases()` も
`aliases[name] = sorted(set(values))` と、**primary/alternatesの区別を捨てて丸ごとソート**している。

実測で確認した齟齬（実際の質問文で使われている略称 vs `aliases[0]`）:

| 案件 | `aliases`（ソート後） | `aliases[0]` | 実際に質問で使われる略称 | 一致？ |
|---|---|---|---|---|
| 青潮モビリティ | `['AOS','AOSHIO',...]` | `AOS` | `AOSHIO`（missing_triage Q23等で実測） | **不一致** |
| 青葉与信マネジメント | `['AY','AYM',...]` | `AY` | `AYM`（valid Q20等で実測） | **不一致** |
| 京橋信用ソリューションズ | `['KSS','KYO',...]` | `KSS` | `KSS` | 一致（偶然） |
| 東都人材プラットフォーム | `['TOTO','TTP',...]` | `TOTO` | `TOTO` | 一致（偶然） |

→ Q15「主略称ですべて挙げてください」を`aliases[0]`で実装すると**確実に一部の案件で誤答**する。
根本原因は`src/utils/glossary.py`の`parse_project_aliases()`が、元の社内用語集テーブルの
`primary`列（`row[1]`、`_clean(row[1])`）を`alternates`（`row[2]`）と区別せず1つの集合にまとめてから
ソートしている点。**`primary`列の情報はパース時点では存在する**（`glossary.py:51`）ため、
これを保持するよう直せば解決できる。

**注意**: この修正は`artifacts/project_registry.json`自体の再生成（`社内用語集.docx`の実データ再パース、
`data/raw`が必要）までは本セッションでは行えない。コード修正とユニットテスト（`tests/test_glossary.py`は
既に合成テーブルでテスト済みなので同様に拡張可能）まで行い、実データでの再生成は
`AGENTS.md`の再生成手順に従って別途行う（Phase運用ルール通り、artifacts手編集は禁止）。

## 3. 設計

### Task 0（前提修正）: `parse_project_aliases` にprimary/alternates区別を持たせる

- `src/utils/glossary.py`: `parse_project_aliases()`の返り値を
  `dict[str, dict[str, list[str] | str]]`（例: `{"primary": "AYM", "alternates": ["AY", "青葉", ...]}`）
  に変更するのではなく、**後方互換を保つため**別関数を追加する方針を推奨:
  - 既存の`parse_project_aliases()`はそのまま（`project_aliases: dict[str, list[str]]`、検索用の
    メンバーシップ判定にしか使われていないため、順序を変えても既存の呼び出し元
    （`ProjectScopedRetriever`, `retrieval_eval.py`）には影響しない）。
  - 新たに`parse_project_primary_aliases(tables) -> dict[str, str]`（project_name→primary1件）を追加し、
    `row[1]`（primaryカラム）だけを抽出する。
- `scripts/build_registries.py`: `build_project_registry()`に`"primary_alias"`フィールドを追加
  （`project_aliases`辞書に加えて`project_primary_aliases`辞書を渡す）。既存の`"aliases"`フィールドは
  そのまま維持（追加のみ、破壊的変更なし）。
- `src/structured/artifact_store.py` or 新規`project_registry`ロード箇所（`scripts/make_predictions.py`
  `scripts/run_pipeline.py`）で`primary_alias`を読めるようにする（cross_project一覧の回答生成で使う）。

**TDD**: `tests/test_glossary.py`に`test_parse_project_primary_aliases_*`を追加（既存の`ALIAS_TABLE`
フィクスチャを再利用）。`tests/test_build_registries.py`があれば同様に追加（無ければ
`scripts/build_registries.py`の対象テストファイルを新規作成するか、統合テストの範囲で確認）。

### Task 1: マイルストーン日付リゾルバ

新規モジュール `src/retriever/milestone_resolver.py`（案）:

```python
def resolve_milestone_date(
    schedule_rows: list[dict],  # StructuredArtifactStore.schedule_tasks_for(project) の返り値
    milestone_code: str,        # "M01" "M02" "FR" 等、質問文中のトークン
    term_registry: list[dict],
) -> str | None:
    """1) 案件のスケジュール内に文字通り (M0N) 表記があれば最優先でその日付を返す。
    2) 無ければ term_registry の語義キーワードで意味的に一致する行を探す。
    3) 複数の異なる日付に曖昧一致する場合は None（Missingに倒す。誤答よりMissing優先の原則）。
    """
```

- (1) 文字通り一致: `タスク名`/`備考`に `(M01)` `（M01）` のような括弧付きパターン、または
  東都の`MS1`のような行を正規表現で検出（`re.search(rf"[（(]{re.escape(code)}[）)]", text)`）。
  ヒットが複数ある場合は日付が同一かを確認、異なれば曖昧としてNoneに倒す。
- (2) 意味的一致: `term_registry`から`milestone_code`（例: "M01"）の`expansion`（例: "キックオフ"）を引き、
  **同義語セット**で`タスク名`/`備考`を検索する。同義語セットは一般的な業務プロセス語彙であり
  特定案件名・ファイル名ではないため規約上ハードコード可（既存の`_SUPERLATIVE_MAX`等と同じ扱い）:
  - キックオフ: `("キックオフ",)`
  - 中間: `("中間報告", "中間レビュー")`
  - 最終: `("最終報告", "最終レビュー", "最終成果物提出", "検収会")`
  - "FR"のような`term_registry`のexpansionが「最終報告書」（文書名）の場合は「最終」グループに
    フォールバックする（文書そのものでなく、それに対応するイベント日を探す設計にする）。
- 日付フィールドは`開始日`/`終了日`（1日で完結するタスクは同一値）。「完了」系は`終了日`、
  「実施」系は`開始日`（同日ならどちらでも同じ）を優先。

**TDD**: `tests/test_milestone_resolver.py`を新規作成。2.2節の3パターン（青嶺不動産型の`M0N `前置き、
東都型の`（M0N）`後置き、みなみ野型のキーワードのみ）を合成フィクスチャで再現し、正しい日付が
返ることを確認。白峰型（M03=中間、M04=最終という独自付番）で**文字通り一致が意味的一致より優先**
されることも回帰テストにする。曖昧一致→Noneのケースも用意。

### Task 2: Q16型（単一案件のMS間日数計算）

- 新規の質問検出（`src/utils/question_classifier.py`への追加、または専用関数）: 「M0N」相当のトークンと
  「日数」「何日」「1日目として数えた場合」等のフレーズが同時に出現する質問を検出する
  （既存の`internal_terms`とは独立のサブタグ、例: `"ms_date_duration"`）。
- 質問文からマイルストーントークンを2つ抽出する（正規表現 `M\d{2}` または `term_registry`に
  登録されたコード全部でマッチを試す。順序は文中に出現した順）。
- `resolve_milestone_date`で両方の日付を解決 → 両方解決できた場合のみ
  `(end - start).days + 1`（「当日を1日目として数える」という質問文の指示を**一般的な包含日数計算**
  として実装。特定の質問への分岐ではなく、文中に同種の指示があれば常に+1する）。
- 片方でも解決できない・曖昧な場合はMissingに委ねる（構造化パスからNoneを返し、既存の
  `_process_structured`のフォールバック機構に乗せる）。
- 回答はSpreadsheetCalcAnswererと同様、**LLMを介さずPythonで直接計算した数値を返す**
  （数値の完全一致のみPerfectという競技規約上、LLMに計算させるべきではない）。

**TDD**: `tests/test_pipeline.py`に新規テストクラス（office_style/spreadsheet_calcの既存パターンを踏襲、
FakeGenerator不要・直接answer検証）。

### Task 3: Q15型（横断・MS日付しきい値でのリスト回答）

- 質問検出: 「(中間報告会|中間レビュー|キックオフ|最終報告等)が」+ 日付 + 「以前/以降に実施された
  案件を」+「主略称で」+ 列挙指示、という組み合わせをキーワードで検出。
- 全案件をイテレート（`StructuredArtifactStore.project_names()`または`project_registry`から取得）、
  各案件で`resolve_milestone_date`を呼び、しきい値日付と比較。
- 該当した案件の`primary_alias`（Task 0で追加）を集めてリスト化。**`aliases[0]`は使わない**
  （2.3節の実測不一致のため）。
- 該当なし・全案件で解決できない場合はMissingに倒す。1案件でも解決できないケースをどう扱うか
  （その案件だけ除外 or 全体Missing）は要検討: 列挙系は部分一致=Incorrectの最危険カテゴリのため、
  **1案件でも判定不能なら全体をMissingに倒す**（安全側）ことを推奨。

**TDD**: 複数案件分のschedule_tasksを合成し、しきい値前後の日付で正しくフィルタされることを確認。

## 4. リスク・注意点（実装時に必ず確認する）

1. **白峰の特殊M番号**: 文字通り一致を意味的一致より必ず優先すること（2.2節）。テストを忘れない。
2. **「主略称」= `aliases[0]`という誤った前提を使わない**こと（2.3節）。Task 0を必ず先に実施する。
3. **規約遵守**: マイルストーン同義語セット（キックオフ/中間報告/中間レビュー/最終報告/最終レビュー/
   検収会）は一般的な日本語ビジネス語彙であり、特定の案件名・ファイル名・質問文のハードコードでは
   ない（既存の`_SCHEDULE_MATCH_KEY_PARTS`や`_SUPERLATIVE_MAX`と同じ扱い）。
4. **数値・列挙は誤答よりMissing優先**。曖昧一致・複数解決不能なケースは必ずNone/Missingに倒す
   実装にすること（LLMに推測させない）。
5. `artifacts/project_registry.json`の実ファイル再生成（`primary_alias`を含む形）は`data/raw`が
   ある環境でのみ可能。本計画のTask 0はコード修正とユニットテストまでが本セッションの範囲。
6. 実装後、実データでのvalid再実行（Q15/Q16のofficial較正）は別途`data/raw`＋APIキーがある環境で
   行う必要がある（このセッションでは検証不能）。

## 5. 完了条件

- Task 0〜3すべてTDDで実装し、`.venv/bin/pytest tests/ -v`が全件PASSする。
- 合成フィクスチャで以下を再現し、期待値通りになることを確認する:
  - MINAMINO型（キーワードのみ・M0N表記なし）のQ16相当シナリオ
  - 東都型・白峰型（M0N表記あり、白峰は独自付番）のTask 1回帰テスト
  - Q15相当の複数案件横断リスト（`primary_alias`使用、`aliases[0]`不使用）
- step-reviewのサブエージェントレビューで「問題なし」または CONFIRMED 修正完了。
- 本ドキュメントの「残課題」節（実データでの再生成・validのofficial較正）を
  `docs/daily作業ログ/`の新規ログに引き継ぐ。
