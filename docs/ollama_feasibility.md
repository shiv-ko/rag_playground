# Ollama（ローカルLLM）によるAPI無し実験の実現可能性調査

> 2026-07-12調査。目的: 現在Anthropic/OpenAI APIに依存している実験ループ（`experiments/`配下に141件のrun）
> をローカルLLM（Ollama）に置き換え、API費用・レート制限・オフライン制約を減らせないか検討する。
> 実装はまだ行っていない（調査・提案のみ）。

## 0. 前提確認

- **コンペ規約上は問題なし**（`competition.md`）:「生成AIの使用に制限はありません。商用API、ローカルLLM、
  マルチモーダルモデル、エージェントフレームワークなどを自由に利用できます」と明記。ハードコード等の禁止事項は
  モデルの実行場所（クラウドAPI/ローカル）とは無関係。
- **実行環境**: MacBook Air, Apple M4, メモリ16GB。
- **Ollama自体は導入済み**（`ollama --version` → `0.31.1`）だが、サーバーは起動しておらず
  （`Warning: could not connect to a running Ollama instance`）、Python用`ollama`パッケージも
  `.venv`未インストール。`pyproject.toml`にも依存追加なし。

## 1. 現在API呼び出しをしている箇所の棚卸し

| ファイル | クラス/関数 | 呼び出し先 | 用途 | 1回あたりの出力 |
|---|---|---|---|---|
| `src/generator/answer_generator.py` | `AnswerGenerator._call_llm` | Anthropic (`CLAUDE_MODEL`) | **本番回答生成**（answer/confidence/citation/reasoningのJSON） | 構造化JSON、最大1500トークン |
| `src/generator/vlm_answerer.py` | `VLMImageAnswerer._call_vlm` | Anthropic Vision | 画像ファイル直接参照質問への回答 | 構造化JSON、最大1000トークン |
| `src/generator/spreadsheet_calc.py` | `SpreadsheetCalcAnswerer._call_llm` | Anthropic (`CLAUDE_MODEL`) | 表計算質問→計算スペックJSON変換 | 小さいJSON、最大500トークン |
| `src/evaluator/judge.py` | `LocalJudge._call_llm` | Anthropic (`CLAUDE_JUDGE_MODEL`) | **開発用の簡易CRAGジャッジ**（実験のたびにvalid setを自己採点） | 小さいJSON、最大300トークン |
| `src/evaluator/openai_judge.py` | `OpenAICragJudge._call_llm` | OpenAI (`gpt-5.2-2025-12-11`固定) | 本番採点ジャッジ（gpt-5.2）を**一字一句再現**した較正用ジャッジ | 小さいJSON |
| `src/indexer/vector_store.py` | `VectorStore._embed` | なし（現状スタブ） | 埋め込み。今は文字コードハッシュの疑似ベクトル | — |
| `src/parsers/image_parser.py` | `ImageParser.parse` | なし（スタブ） | パース時の画像キャプション化は未実装（ファイル名を返すのみ） | — |

`data/raw/share/質問回答/questions_valid.csv`は30問、`questions_test.csv`は100問。1実験run（valid）あたり
生成30回＋ジャッジ30回＝最大60API呼び出しがあり、`experiments/`の141ファイルから見て、これまでに
数千回オーダーのAPI呼び出しが発生している。ここがコスト・レート制限・待ち時間の主因。

## 2. Ollamaに置き換える価値の評価（箇所ごと）

### 2.1 `LocalJudge`（開発用ジャッジ）— 最有力候補

- **役割**: 実験のたびに「この回答はPerfect/Acceptable/Missing/Incorrectか」を自己採点し、
  ゲート閾値やプロンプト変更の効果を素早く見るための内部ツール。**本番のLB採点には一切関与しない**
  （本番はSIGNATE側のgpt-5.2ジャッジ）。
- 較正用の`OpenAICragJudge`（gpt-5.2レプリカ）と`LocalJudge`の判定一致率を比べる仕組みが既にある
  （`experiments/judge_calibration_*.json`, `phase2_recheck_valid_*.json`）ので、Ollama版に切り替えても
  「本番ジャッジとの一致率」で品質を定量評価できる。
- 出力は`{"label": ..., "reason": ...}`程度の小さいJSONなので、7B級ローカルモデルでも十分再現できる可能性が高い。
- **結論**: 最も置き換えやすく、置き換える理由（コスト・速度・オフライン）が最も強い箇所。

### 2.2 `VectorStore._embed`（埋め込み）— Ollama云々以前に改善価値あり

- 現状は**API未使用のハッシュ疑似ベクトル**（文字コード頻度ベース、意味を捉えない）。これはAPI費用の問題ではなく
  純粋な検索精度の問題。
- Ollamaは`nomic-embed-text`や`mxbai-embed-large`等の埋め込み専用モデルをローカルで無料・無制限に叩ける。
  ネットワーク不要・レート制限なしで実質「タダで本物の埋め込みに置き換えられる」。
- **結論**: Ollama採用の有無に関わらず優先度が高いが、Ollama経由なら外部埋め込みAPIキーを増やさずに実現できる。

### 2.3 `SpreadsheetCalcAnswerer`（表計算スペック変換）— 中程度の候補

- 出力は列名の中から計算対象を選ぶだけの小さい構造化JSON。タスクが限定的なので、ローカルモデルでの精度劣化が
  比較的小さいと推測される。実験的に切り替えて`execute_calc_spec`後の結果一致率で検証可能。

### 2.4 `AnswerGenerator`（本番回答生成）— 実験用途は○、本番提出は慎重に

- 検索・ゲート・引用チェックなど周辺ロジックの検証（「正しい文書を引けているか」「ゲートが正しく発火するか」）は、
  生成モデルの絶対的な賢さに強く依存しない。この種の実験イテレーションはOllamaのローカルモデルで代替し、
  API消費を抑えつつ高速に回せる。
- 一方、**最終スコアは生成された回答の質そのもの**（多段推論・日本語ビジネス文書の読解・社内用語処理・数値の
  丸め処理など）に直結する。16GBという制約下で動く7〜14B級モデルは、Claude Sonnet 5のような大規模モデルと
  比べて要約・多段推論精度で劣る可能性が高く、本番提出用の置き換えはスコア悪化リスクがある。
- **結論**: 「実験用バックエンド」として追加し、本番提出直前にClaude版と比較のうえ採否判断する2段構えを推奨。

### 2.5 `VLMImageAnswerer`（画像・グラフ読解）— 同様に実験用途止まり推奨

- Ollamaには`qwen2.5vl`（chart/document QAに強いとされる）や`llama3.2-vision`等のビジョンモデルがあるが、
  16GB環境では7B級が上限に近く、グラフの数値読み取り精度はClaude Visionに劣る可能性が高い。
- 画像読解はコンペのタスク説明でも明示的に重視されている領域（「画像埋め込みやグラフなどから読み取る情報」）
  なので、ここでの精度劣化は本番スコアへの影響が大きい。実験・ハーネス検証用途に留めるのが無難。

## 3. ハードウェア制約（M4 / 16GB）のガイドライン

- 実測はしていないが、一般的な目安として:
  - **安全圏**: 7〜8B級モデルのQ4量子化（`qwen2.5:7b-instruct`, `llama3.1:8b`など）。他プロセス
    （pandas/pypdf等のパース処理）と同時実行してもメモリを圧迫しにくい。
  - **要検証**: 14B級Q4量子化は単体なら動くが、パイプライン本体（Pythonプロセス＋パーサー）と同時実行時に
    スワップが発生しうるため、実験時はOllama単独実行での速度・メモリ計測を先に行うべき。
  - **非推奨**: 32B以上は16GB環境では実用的な速度で動かない可能性が高い。
- ビジョンモデルはテキストモデルよりメモリ消費が大きい傾向があるため、7B級ビジョンモデル1本に絞って検証するのが
  現実的。

## 4. 再現性の観点（コンペ要件との相性）

競技規約は「乱数、LLM出力、OCR結果などに揺らぎがある場合は、可能な範囲でseed固定、ログ保存、使用モデル名の記録」
を求めている。Ollamaはローカル実行のためAPI側のサーバー更新・レート制限・バージョン差分による揺らぎがなく、
`temperature=0`＋固定モデルタグ（例: `qwen2.5:7b-instruct-q4_0`のようにタグまで固定）であれば、
クラウドAPIより**再現性の担保はむしろ容易**。ただし本番提出をOllamaにする場合はモデルタグとOllamaバージョンを
提出書類に明記する必要がある（検収時の要求事項）。

## 5. 提案（実装はまだ行っていない）

導入は小さく始めて安全に広げる順序を推奨する。

1. **`LocalJudge`をOllamaバックエンドに切り替え**（`LLM_JUDGE_BACKEND=ollama|anthropic`のような環境変数で
   両対応にし、既存のAnthropic版はそのまま残す）。既存の`OpenAICragJudge`との一致率比較の仕組み
   （`judge_calibration_*.json`系）でOllama版ジャッジの信頼度を定量評価してから常用に切り替える。
2. **`VectorStore._embed`をOllamaの埋め込みモデルに置き換え**。API有無に関係なく効果が見込める改善であり、
   実装コストも小さい（インターフェース`add/search/clear`は変えない設計に既になっている）。
3. **`AnswerGenerator`/`VLMImageAnswerer`に実験専用のOllamaバックエンドを追加**し、retrieval/gate/citation
   ロジックの検証をローカルモデルで高速に回す。本番投入は、Claude版とのvalidスコア比較で明確な劣化がないことを
   確認してから判断する（現状のLB乖離の大きさ・分散を踏まえると、この比較には複数run必要）。
4. `SpreadsheetCalcAnswerer`は3.と並行して低リスクで試す。

### 想定される作業

- `pyproject.toml`に`ollama`（Python SDK）を追加、`ollama serve`起動、モデルpull（例:
  `ollama pull qwen2.5:7b-instruct`, `ollama pull nomic-embed-text`, `ollama pull qwen2.5vl:7b`）。
- 各`_call_llm`/`_call_vlm`/`_embed`を「バックエンド切り替え可能」にする薄いラッパーを挟む
  （既存のAnthropic/OpenAI呼び出しコードは変更せず、環境変数で分岐を追加する形が既存設計方針と親和的）。
- OllamaのJSON出力安定性はAnthropicの構造化出力ほど高くない可能性があるため、Ollamaの`format`（JSON強制）
  オプションの利用と、失敗時のフォールバック（現状の`_parse_response`と同様の緩い正規表現抽出）を維持する。

## 6. リスク・留意点まとめ

- 本番提出の回答生成・画像読解をOllamaに全面置換するのは、スコア（gpt-5.2ジャッジ基準）への悪影響リスクが
  高く、**まず実験用途から始めて数値で確認してから判断すべき**。
- `OpenAICragJudge`（gpt-5.2レプリカ）は本番ジャッジの忠実な再現が存在意義なので、これはAPI継続利用のままで良い
  （較正用途のみで呼び出し頻度は低い）。
- 16GBメモリでの同時実行（Ollama＋パースパイプライン）のメモリ挙動は未実測。実装に着手する前に、まず
  `ollama run`単体でのレイテンシ・メモリを計測するステップを挟むと手戻りが少ない。
