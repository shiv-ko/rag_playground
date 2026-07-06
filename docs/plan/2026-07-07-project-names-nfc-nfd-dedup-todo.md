# 2026-07-07 project_names() のNFC/NFD重複バグ修正TODO

> 位置づけ: `done_2026-07-06-internal-terms-ms-date.md`（Task 3: `MilestoneThresholdListAnswerer`）の
> 実データ検証で発見。本体の計画は完了扱いだが、実データで動かして初めて見つかった新規バグのため
> 別TODOとして切り出す。

## 現状（2026-07-07時点で確認済み）

`src/structured/artifact_store.py`の`StructuredArtifactStore.project_names()`が案件名を
NFC/NFD正規化せず素の`set()`で重複排除しているため、同一案件が異なるUnicode正規化形式で
複数のレジストリに格納されていると、返り値のリストに**同一案件が2件として重複出現する**。

### 実データでの確認結果

`artifacts/`配下のレジストリを調査したところ、「青葉与信マネジメント株式会社」が以下のように
正規化形式が割れて格納されている:

| ファイル | 格納形式 |
|---|---|
| `schedule_tasks.jsonl` / `office_marks.jsonl` / `train_xlsx_sheets.jsonl` / `spreadsheet_sheets.jsonl` / `train_xlsx_small_sheet_cells.jsonl` / `version_diff_poc.jsonl` / `highlight_cells.jsonl` | NFD（macOSファイルパス由来） |
| `contracts.jsonl` | NFC（`build_contract_registry.py`の`normalize_text`が明示的に正規化） |

この結果、`store.project_names()`は「青葉与信マネジメント株式会社」を2つの別文字列として返す。

### 影響が実際に出た箇所

`src/generator/milestone_date_answerer.py:128`の`MilestoneThresholdListAnswerer.answer()`が
`store.project_names()`を直接イテレートして該当案件のprimary_aliasをリストに追加しており、
実際のvalid Q15（「中間報告会または中間レビューが2025年7月1日以前に実施された案件を、
主略称ですべて挙げてください」）で **`AYM、AYM、MINAMINO、SHR`** という重複出力を確認済み
（`experiments/contract_fix_valid_1783350883.json`、judge_label=Acceptable。重複が
原因でPerfectを逃した可能性が高い）。

他の呼び出し箇所（`src/orchestrator/pipeline.py:142`の`_resolve_project_name`）は最初の
一致で早期returnするため実害なし。現時点で実害があるのは`MilestoneThresholdListAnswerer`のみ。

## 修正方針

- [ ] `StructuredArtifactStore.project_names()`をNFC正規化してから重複排除するよう修正する
      （`names.update(unicodedata.normalize("NFC", name) for name in by_project if name)`）
- [ ] 回帰テスト追加: `tests/test_artifact_store.py`（無ければ新規）に、同一案件がNFCとNFDの
      両方の文字列キーで別々のレジストリ辞書に登録されているケースを合成し、
      `project_names()`が1件にまとまることを確認するテストを追加
- [ ] `tests/test_milestone_date_answerer.py`にも、`MilestoneThresholdListAnswerer`が
      NFC/NFD重複下で二重列挙しないことを確認する回帰テストを追加（実データの再現ケース）
- [ ] 修正後、`.venv/bin/pytest tests/ -v`全件PASSを確認
- [ ] 実データで`experiments/`診断runを再実行し、Q15が`AYM、MINAMINO、SHR`（重複なし）に
      なることを確認する
- [ ] `_get()`メソッド（同ファイル内）は既にNFC正規化フォールバックを持っているため、
      同様のロジックを踏襲する

**優先度**: 中（1問への影響は確認済みだが、影響範囲は`project_names()`を直接使う横断列挙系の
今後の実装すべてに波及しうるため、早めに直す方が安全）。
