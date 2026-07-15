# 次アクション計画（2026-07-16）

## 現在地

- 拡張子なしの実在ファイルstemを質問文から検出し、該当ファイルを検索上位へ補完する修正を実装済み（`45a2048`）。
- valid検索recallはハイブリッド検索導入時の0.793から **0.862（25/29）** へ改善。Q17は`カラム説明.md`がrank 1、single_textは4/4。
- 629 tests pass、step-reviewのCONFIRMED 2件（助詞境界、全件検索の性能問題）も修正済み。

## 次に行うこと

- [ ] ユーザーが社内文書・valid質問の生成/judge API送信を明示承認した場合のみ、`q17_filescope_valid_r1〜r3`を実行する。
- [ ] N=3完了後、r1をofficial較正し、Q17のPerfect/Incorrectと新規Incorrectの有無で採否を確定する。
- [ ] 採用確定後、test predictions.csvをN=3で再生成し、提出物を作る。
- [ ] API送信を承認しない場合は、検索recall改善までを根拠に実装を維持し、Phase 5のローカル作業へ進む。

