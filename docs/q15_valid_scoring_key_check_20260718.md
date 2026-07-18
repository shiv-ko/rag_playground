# Q15 valid採点キー順序不一致 検証レポート（2026-07-18）

対象: メモリ `eval-data-update-0716-q15-order-mismatch` で指摘された、`questions_valid.csv` index=15 の回答順序と採点キー `valid_txt.csv` の順序の食い違いについて、実在性と実害の有無を検証した。**本レポートは検証のみ。データ修正は未実施。**

## ① 結論

- **不一致は実在する。** `questions_valid.csv`（新順序: `AYM、SHR、MINAMINO`）と `valid_txt.csv`（旧順序のまま: `MINAMINO、SHR、AYM`）は現時点（2026-07-18）でも食い違ったまま。運営からの追加修正連絡はまだ来ていない。
- **ただし実害は確認できなかった。** ローカルjudge（Claude製 `LocalJudge`）・公式CRAG judgeの再現版（OpenAI gpt-5.2、実際にAPIを呼んで得た既存の較正記録）のいずれも、Q15のような「要素列挙」問題では**要素の順序に関わらず内容が一致していればPerfect判定**を一貫して下している。この傾向は0716更新の前後を通じて20件以上の記録で確認でき、順序違いによる誤判定（本来Perfectのものが誤ってIncorrect/Acceptableになる等）の実例は1件も見つからなかった。
- 結論として、**採点キーの不一致自体は解消すべき技術的負債だが、現状のjudge運用では実スコアへの実害は生じていない。**

## ② 証拠

### 不一致の実在確認

`data/raw/share/質問回答/questions_valid.csv`（2026-07-16 22:37更新、パイプラインが実際に読む質問ファイル）index=15:

```
15,中間報告会または中間レビューが2025年7月1日以前に実施された案件を、主略称ですべて挙げてください。,AYM、SHR、MINAMINO
```

`data/raw/evaluation/data/valid_txt.csv`（2026-06-23 11:51時点のまま、mtime変化なし。ヘッダなしindex,answer形式の公式採点キー）15行目:

```
15,MINAMINO、SHR、AYM
```

→ 要素の集合（AYM・SHR・MINAMINO）は同じだが、記載順序が異なる。`data/evaluation/`（未追跡展開先）と `data/raw/evaluation/`（実際にコードが参照する場所）の `valid_txt.csv` は内容・mtimeとも完全一致しており、二重化されているだけで独立した差分ではない。

`data/raw/evaluation/readme.md` に0716更新で追記された順序規則:

```
なお、要素列挙問題に関する順序規則は以下のようになっている。
- ID列挙: 番号の若い順
- 人物名: 座席表の若い順
- その他案件名・人物名など数値が振られていないもの: ドキュメントの出現順通り
```

Q15の回答（案件略称の列挙）はこの「その他案件名」規則に該当し、`questions_valid.csv`側は新規則（ドキュメント出現順と推定される `AYM、SHR、MINAMINO`）に更新済みだが、`valid_txt.csv`は旧順序 `MINAMINO、SHR、AYM` のまま追随していない。

### 実害の検証（既存run/較正記録、新規API呼び出しなし）

**ローカルjudge（`src/orchestrator/pipeline.py` の `run_pipeline.py` 実行時、`LocalJudge`）**: `qa.reference_answer` は `questions_valid.csv` の answer列から直接供給される（`src/utils/question_loader.py`）。0716更新前後を通じ、`experiments/*.json` の複数run（例: `chunkerfix_valid_*`, `crossproj_task12_valid_*`, `q6_noextra_valid_r1_1784184029`）でQ15の回答順序が参考文書と異なっていても、judge_reasonに明示的な順序非依存判定が繰り返し記録されている:

```
"judge_label": "Perfect",
"judge_reason": "参考文書に記載された案件(MINAMINO、SHR、AYM)がすべて回答に含まれており、
順序が異なるだけで内容は完全に一致しているため。"
```

**公式CRAG judge再現版（`src/evaluator/openai_judge.py`、実際にOpenAI APIを呼んで得た既存の較正記録 `experiments/judge_calibration_*.json`、`calibrate_judge.py` が `valid_txt.csv` からGTを読み込んで生成）**: 20件のQ15較正記録すべてで `ground_truth="MINAMINO、SHR、AYM"`（旧順序、valid_txt.csv由来）固定。回答が `AYM、MINAMINO、SHR`（GTとも新順序ともさらに異なる第3の順序）であっても:

```
"answer": "AYM、MINAMINO、SHR",
"ground_truth": "MINAMINO、SHR、AYM",
"local_label": "Perfect",
"official_label": "Perfect",
"official_score": 1.0
```

— `judge_calibration_1783520472.json` 以降 `1784184775.json`（2026-07-16 15:52、0716更新直前）まで一貫してPerfect。回答・GT双方の順序が異なっていても公式judge（gpt-5.2, temperature=0, seed=0）は要素集合の一致のみでPerfectと判定しており、順序規則の追記（readme.md）は判定挙動そのものには反映されていないとみられる。

## ③ 影響を受けた過去runの有無

上記較正記録・パイプラインrun記録を精査した限り、**Q15の順序不一致が原因で誤判定（本来Perfectがincorrect等に誤判定）になった事例は確認できなかった**。valid official mean等の集計値への影響もないと考えられる。

## ④ 修正提案（未実施）

実害は現状なしと判断されるが、採点キーの内部整合性・将来的な運営側の判定厳格化リスクに備え、以下の同期を推奨する。

1. `data/raw/evaluation/data/valid_txt.csv` の15行目（index=15の行）を
   `15,MINAMINO、SHR、AYM` → `15,AYM、SHR、MINAMINO` に変更（`questions_valid.csv`のanswer列・readme.mdの順序規則に合わせる）。
2. `data/evaluation/data/valid_txt.csv`（未追跡の展開先コピー、`data/raw/evaluation/`と内容が完全一致している二重化ファイル）も同一の変更を適用し、2ファイルの整合を維持する。
3. 修正後、`scripts/calibrate_judge.py` を1回再実行し、Q15の `official_label` が引き続きPerfectで安定していることを確認する（judge自体の順序非依存性は既に実証済みのため退行リスクは低いと見込まれるが、念のための確認）。
4. 運営への確認は未実施のまま。可能であれば運営に「`valid_txt.csv`側のQ15順序更新予定の有無」を問い合わせ、非公式コピーでの独自修正が今後の公式データ更新で上書き・再度食い違う事態を避けるのが望ましい。
