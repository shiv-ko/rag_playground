# 提出方法

## 1. 提供ファイル（SIGNATEコンペページ）

| ファイル名 | 内容 | サイズ |
|---|---|---|
| `share.zip` | データアステル社の案件資料一式（共有ドライブ相当） | 74.41 MB |
| `evaluation.zip` | RAGシステムの回答精度を評価するためのコード | 13.47 KB |
| `sample_submit.zip` | 投稿ファイルのサンプル（投稿テスト用） | 393 B |

## 2. 提出ファイルの形式

- ファイル名は **`predictions.csv`** 固定（拡張子は`csv`）
- **ヘッダーなし**、カラムは `index, answer` の2列のみ
  ```
  0,わかりません
  1,4
  2,20日
  ...
  ```
- `index` は `questions_test.csv` に存在する全問を過不足なく網羅する（欠損不可）
- 各回答は **1000トークン以内**（超過するとバリデーションエラー）
- `predictions.csv` を **zip形式に圧縮**して提出する
  - zipファイル名は任意だが、**英数字・アンダースコア（_）・ハイフン（-）のみ**を想定
- 回答は日本語を前提とする
- 応答時間制限は3時間（全質問の回答生成をこの時間内に完了させる想定）

## 3. 提出前のローカル検証（`evaluation/`）

`evaluation/crag.py` を使うと、SIGNATE本番と同じ形式でローカル採点できる。

### 環境構築
Docker利用が推奨（`evaluation/docker-compose.yml`がSIGNATE評価環境=Linux/amd64を再現）。

```bash
cd evaluation
docker compose up -d
docker exec -it rag_env bash
```

Dockerを使わない場合は以下をインストール:
```
numpy==1.26.4
pandas==2.2.2
openai==1.57.1
tiktoken==0.7.0
torch==2.3.1+cpu
sentence-transformers==3.0.1
```

コンテナ内で `OPENAI_API_KEY` を環境変数として設定する（`crag.py`の採点LLM呼び出しに必要）。

### 実行
1. 模範解答（`index,answer`のヘッダーなしcsv）を `evaluation/data/` に用意する。ローカル検証には `questions_valid.csv`（30問・正解付き）が使える
2. 予測結果を `evaluation/submit/predictions.csv` として出力する
3. 実行:
   ```bash
   python crag.py
   ```
4. `./result/scoring.csv`（各問の評価結果・トークン数）と最終スコアが出力される

### 採点ロジック（CRAG方式、4分類）

| 評価結果 | 点数 | 基準 |
|---|---|---|
| Perfect | 1 | 正確かつ虚偽なし |
| Acceptable | 0.5 | 有用だが軽微な誤りあり |
| Missing | 0 | 「わかりません」など具体的回答なし |
| Incorrect | -1 | 誤り・無関係な回答 |

- 最終スコアは全問の平均（本番はLLM採点を1回のみ実施、`temperature=0`・シード固定）
- **数値問題**: 完全一致のみPerfect。所定桁数で四捨五入して一致する場合のみAcceptable。単位や接尾辞の違い（「5」と「5ページ」）は同一とみなす
- **要素列挙問題**: 全要素完全一致のみPerfect。部分一致はすべてIncorrect（Acceptableなし）
- **Incorrect(-1)とMissing(0)は非対称**: 自信のない回答を無理に出すとPerfect2問分の損失になりうるため、確信度が低い場合は「わかりません」を選ぶ設計が安全

## 4. SIGNATE CLI（Beta）での提出

データダウンロードから結果提出までCLIで一括対応可能。インストール手順・使用方法はSIGNATE公式ガイドを参照。おおまかな流れ:

```bash
pip install signate
signate login              # APIトークンで認証
signate files --competition-id <ID>   # データ一覧確認
signate download --competition-id <ID>
signate submit --competition-id <ID> --file <zipファイルパス>
```

## 5. 実装上の制約（審査対象外になる行為）

- データの事前加工・回答のハードコード・質問ごとの手動回答は禁止
- 特定の質問/案件/ファイル名に対する個別分岐（固定回答）は禁止
- 未知の案件フォルダ・未知の資料・未知の質問が追加されても同じ処理方針で動作する、コードで再現可能なRAGシステムとして実装する必要がある
- 回答生成に使えるのは提供された未加工の共有ドライブ内データと質問文のみ（外部知識・外部Web検索の利用は不可）
