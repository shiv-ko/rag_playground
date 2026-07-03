# AI Engineering Challenge - 事前準備ドキュメント（Claude Code向け）

## 0. このドキュメントの目的

SIGNATE主催「AI Engineering Challenge ～煩雑な社内ドライブをハックせよ～」（NTTデータ・NTTデータ先端技術・NTTデータ・ニューソン共催、2026/7/3 12:00開始）に向けた事前準備。

**本番データはまだ公開されていない**（投稿開始時に公開予定）。そのため、このフェーズでは「データが来た瞬間に高速にループを回せる骨組み」を作ることが目的。データの中身に依存する部分は差し替え可能な抽象化にしておく。

Claude Codeにはこのドキュメントを渡し、まず**セットアップフェーズ（1〜7章）**を実装してもらう。8章以降はデータ到着後に着手する。

---

## 1. コンペ概要（確定している情報）

- **テーマ**：社内共有ドライブを模したデータ群から、質問に対してRAGで根拠に基づく回答を生成する
- **データ特性**：形式・粒度が不統一、情報が複数箇所に分散、画像埋め込みやグラフからの読み取りが必要（マルチモーダル対応必須）
- **評価**：CRAGベースの4分類評価
  | 分類 | 得点 | 基準 |
  |---|---|---|
  | Perfect | 1 | 正確かつ虚偽なし |
  | Acceptable | 0.5 | 有用だが軽微な誤りあり |
  | Missing | 0 | 「わかりません」等、具体的回答なし |
  | Incorrect | -1 | 間違い・無関係な回答 |
  - 判定はLLM（gpt-5.2）が1回のみ実施、temperature=0・シード固定
  - スコアはこの得点の質問数平均（-1〜1）
- **制約**：
  - 回答は1000トークン以内（超過はエラー）
  - 応答時間制限3時間（全質問への回答生成をこの時間内に完了させる必要があると想定）
  - 入力に使えるのは「未加工の共有ドライブ内データ」と「質問文のみ」（外部知識の付加は不可）
  - コードで再現可能なRAGシステムとして実装する必要がある

### 戦略上の要点
- **Incorrect(-1) と Missing(0) の非対称性**：自信がない回答は無理に出さず「わかりません」を選んだほうが安全。過信して間違えるとPerfectの回答2つ分の損失になる。→ 生成パイプラインに「確信度が低ければ回答を控える」ロジックを組み込む
- 画像・グラフ読み取りが明記されているため、マルチモーダル処理（VLM or OCR）は後回しにできない
- Long-Context QA一発読み（RAG-1グランプリで有効だった手法）は今回はデータが分散・複数形式なので効果が薄いと予想。優先度は低い

---

## 2. 技術スタック

- **言語**：Python 3.11+
- **方針**：フレームワーク（LangChain/LlamaIndex等）は使わない。軽量な自前実装で、各処理ステップを差し替え可能なインターフェースとして実装する
- **LLM**：Anthropic API（Claude）をメイン生成エンジンとして使用。モデル名は環境変数で切り替え可能にする（例：`claude-opus-4-8` / `claude-sonnet-5`）
- **依存ライブラリの最小方針**：
  - PDF/Office解析：後述（未確定、抽象化しておく）
  - ベクトル検索：後述（未確定、抽象化しておく）
  - 並列処理：`asyncio` + `anyio` or `concurrent.futures`（Claude APIの並列呼び出し用）
  - 設定管理：`.env` + `pydantic-settings` or シンプルな `config.yaml`

---

## 3. ディレクトリ構成（案）

```
ai-engineering-challenge/
├── README.md
├── pyproject.toml
├── .env.example
├── config.yaml
├── data/
│   ├── raw/                  # 提供される生データ置き場（未着手、gitignore対象にする）
│   └── sample/               # 動作確認用のダミーデータ（自作）
├── src/
│   ├── parsers/               # ファイル形式ごとのパーサー（差し替え可能）
│   │   ├── base.py            # Parser Protocol/ABC
│   │   ├── pdf_parser.py
│   │   ├── office_parser.py   # Word/Excel/PowerPoint
│   │   └── image_parser.py    # 画像・グラフのVLMキャプション化
│   ├── indexer/
│   │   ├── base.py            # Indexer Protocol（add/search インターフェース）
│   │   ├── vector_store.py    # 埋め込みベースの検索（未確定：後で実装差し替え）
│   │   └── keyword_store.py   # BM25等キーワード検索（未確定：後で実装差し替え）
│   ├── retriever/
│   │   └── hybrid_retriever.py # vector + keyword の統合、re-ranking含む
│   ├── generator/
│   │   ├── answer_generator.py # 質問+根拠→回答生成（Claude API呼び出し）
│   │   └── confidence_gate.py  # 確信度が低い場合はMissing相当の回答を返す
│   ├── evaluator/
│   │   ├── judge.py            # CRAG基準でのローカル自己評価（Claudeをジャッジに使う）
│   │   └── metrics.py          # スコア集計
│   ├── orchestrator/
│   │   └── pipeline.py         # パース→索引→検索→生成→評価のループを回す本体
│   └── utils/
│       ├── logging.py
│       └── parallel.py         # 並列実行ユーティリティ
├── scripts/
│   ├── run_pipeline.py         # エンドツーエンド実行
│   ├── run_eval.py             # 評価のみ実行
│   └── make_sample_data.py     # ダミーデータ生成
├── experiments/                # 実験ログ（設定・スコア・失敗ケースの記録）
└── tests/
```

---

## 4. コンポーネント別インターフェース仕様

Claude Codeには、まず各コンポーネントを **Protocol（もしくはABC）で抽象定義**させ、ダミー実装を1つずつ添える形で進めてもらう。データが来た段階で、具体実装だけ差し替えれば動くようにする。

### 4.1 Parser
```python
class Parser(Protocol):
    def parse(self, file_path: Path) -> list[Document]:
        """ファイルをパースして Document(text, metadata, source_path, page/sheet等) のリストを返す"""
```
- 画像・グラフを含むファイルは、VLM（Claude）に画像を渡してキャプション/構造化テキスト化する専用パーサーを用意
- 表はMarkdown形式に変換してテキストチャンクに含める

### 4.2 Indexer / Retriever
```python
class Indexer(Protocol):
    def add(self, documents: list[Document]) -> None: ...
    def search(self, query: str, top_k: int) -> list[ScoredDocument]: ...
```
- ベクトル検索とキーワード検索を両方実装し、`HybridRetriever` で統合・re-rankingする構成
- 検索バックエンドの実装（Chroma/FAISS/その他）は**まだ決めない**。`Indexer` インターフェースにさえ従っていれば後から何を挿しても動くようにする

### 4.3 Generator
```python
class AnswerGenerator(Protocol):
    def generate(self, question: str, contexts: list[ScoredDocument]) -> Answer:
        """Answer には回答テキストと確信度スコアを含む"""
```
- プロンプトには評価基準（Perfect/Acceptable/Missing/Incorrectの定義）をそのまま埋め込み、モデル自身に「自信がなければMissing相当の回答を返す」よう指示する
- 1000トークン制限のチェックをここで行う

### 4.4 Judge（ローカル評価用）
```python
class Judge(Protocol):
    def score(self, question: str, generated_answer: str, reference_or_context: str) -> JudgeResult:
        """Perfect/Acceptable/Missing/Incorrect の分類と根拠を返す"""
```
- 本番はgpt-5.2が判定するが、手元評価用にClaudeでジャッジハーネスを先に作る
- ジャッジ用プロンプトは、コンペのEvaluation Description文言をそのまま使う（配点の再現性を優先）

### 4.5 Orchestrator
- 全質問に対して並列でパイプラインを実行し、進捗・エラー・スコアをログに残す
- 失敗ケース（Missing/Incorrectになった質問）だけを抽出して再分析できるようにする

---

## 5. 並列処理・時間制約対応

- 3時間の応答時間制限があるため、質問を**バッチで並列処理**する仕組みを最初から入れておく（`asyncio.gather` + セマフォでレート制限）
- API呼び出しのリトライ・タイムアウト処理も最初から組み込む
- パイプライン全体の実行時間を計測し、「このペースで全質問処理すると何分かかるか」を実行前に見積もれるようにする

---

## 6. ダミーデータでの動作確認

本番データが来る前に、パイプライン全体が動くことを確認するため：
- `scripts/make_sample_data.py` で、社内文書っぽいダミーデータ（表・簡単な図を含むPDF/Excel数点、想定質問10問程度）を生成する
- これでParser→Indexer→Retriever→Generator→Judgeの一連の流れをエンドツーエンドでテストする
- 本番データが来たら、`data/raw/` に配置するだけでパイプラインが動くことを目標にする

---

## 7. ロギング・実験管理

- `experiments/` 配下に、実行ごとの設定（config snapshot）・スコア・質問ごとの回答と判定結果をJSON/CSVで保存
- どのパイプライン変更がスコアにどう影響したかを後から追えるようにする（Shivさんの他プロジェクトのjournal運用と揃える形でも良い）

---

## 8. データ到着後（明日）にやること（着手待ち）

1. 実データを見て、ファイル形式・分散度・画像/グラフの量を確認
2. Parser実装をデータに合わせて差し替え・調整
3. Indexer/Retrieverの具体実装を選定・実装（Chroma vs FAISS等はここで決める）
4. サンプル質問でエンドツーエンドを回し、ローカルJudgeでスコアを見る
5. 失敗ケース分析→パイプライン改善のループを回す

---

## 9. Claude Codeへの依頼順序（推奨）

1. `pyproject.toml` / `.env.example` / `config.yaml` の雛形作成
2. 4章のインターフェース（Protocol/ABC）を全部定義（実装はダミーでOK）
3. `make_sample_data.py` でダミーデータ生成
4. Parserのダミー実装（テキスト抽出のみの最小版）
5. Indexer/Retrieverのダミー実装（単純な文字列一致検索でも可、後で差し替え前提）
6. Generatorの実装（Claude API呼び出し、確信度ゲート込み）
7. Judgeの実装（Claude APIでCRAG基準ジャッジ）
8. Orchestrator（並列パイプライン）の実装
9. ダミーデータでエンドツーエンドを1回通し、ログ・スコア集計が機能することを確認



---

## 10. 未確定事項（本ドキュメントでは意図的に決めていない）

- ベクトル検索・キーワード検索の具体的な実装ライブラリ
- Parserで使う具体的なPDF/Office/画像処理ライブラリ
- 提出フォーマットの詳細（sample_submission.csv等、公開待ち）
- 「コードで再現可能なRAGシステム」の提出要件の詳細（コード提出が必須か、実行環境の指定があるか等）

これらは7/3 12:00のデータ公開後、実際の要件を見てから決定する。
