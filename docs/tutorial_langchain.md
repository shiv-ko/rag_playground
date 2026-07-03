# LangChainチュートリアル: 基本的なRAGの構築

このドキュメントは、提供されたチュートリアルコードを元に作成されたものです。LangChainを用いて基本的なRAG（Retrieval-Augmented Generation）システムを構築する手順を説明します。

## 1. 概要

このチュートリアルでは、SIGNATE AI Engineering Challenge「煩雑な社内ドライブをハックせよ」の課題に対し、基本的なRAGシステムを構築することを目標とします。

- **使用するLLM**: OpenAI APIの `gpt-5.4`
- **注意**:
    - API利用料金は自己負担となります。
    - ここで構築するRAGはベースラインであり、精度が十分でない可能性があります。改善が主要な課題となります。

### 1.1. ライブラリ環境

チュートリアルが動作したライブラリのバージョンは以下の通りです。

- `pandas==3.0.1`
- `numpy==2.4.3`
- `langchain==1.2.10`
- `langchain-classic==1.0.2`
- `langchain-community==0.4.1`
- `langchain-core==1.2.23`
- `langchain-openai==1.1.11`
- `langchain-text-splitters==1.1.1`
- `pypdf==6.8.0`
- `python-pptx==1.0.2`
- `unstructured==0.21.5`
- `docx2txt==0.9`
- `msoffcrypto-tool==6.0.0`
- `chromadb==1.5.5`

## 2. 実装手順

### 2.1. APIキーの読み込み

1.  Notebookと同じディレクトリに `.env` ファイルを作成します。
2.  ファイルにOpenAIのAPIキーを以下のように記述して保存します。
    ```
    OPENAI_API_KEY=sk-your-api-key
    ```
3.  以下のコードでAPIキーを読み込みます。

```python
import os
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

# APIキーを取得
api_key = os.getenv("OPENAI_API_KEY")
```

### 2.2. 質問データの読み込み

コンペティションの質問データを読み込みます。

- `questions_valid.csv`: モデルの精度検証用データ。
- `questions_test.csv`: 最終提出用の質問データ。

`validation`フラグを切り替えることで、どちらのデータセットを使用するか選択できます。

```python
import pandas as pd

# Trueにすると検証用データ、Falseにすると提出用データを読み込む
validation = False

if validation:
    data = pd.read_csv("share/質問回答/questions_valid.csv")
else:
    data = pd.read_csv("share/質問回答/questions_test.csv")

print(data.head(3))
print(data.shape)
```

### 2.3. ドキュメントの読み込みと準備

RAGシステムのために、`share/共有ドライブ/` 内にある様々な形式のドキュメントを読み込み、ベクトル化の準備をします。

#### 2.3.1. ファイルパスの取得

```python
from pathlib import Path

dir_path = Path("share/共有ドライブ/")
file_paths = [p for p in dir_path.rglob("*") if p.is_file() and p.name != ".DS_Store"]

print(f"対象ファイル数: {len(file_paths)}")
```

#### 2.3.2. ドキュメントローダーの定義

LangChainの`Document Loader`を使い、ファイル形式ごとに対応したローダーを定義します。

```python
from langchain_core.documents import Document
from langchain_community.document_loaders import (
    TextLoader,
    CSVLoader,
    PyPDFLoader,
    Docx2txtLoader,
    UnstructuredExcelLoader,
    UnstructuredPowerPointLoader,
)

# train.csv, train.xlsx はデータ量が多いため、先頭20行のみ読み込む
TARGET_HEAD_FILES = {"train.csv", "train.xlsx"}

def should_load_head_only(file_path):
    return file_path.name.lower() in TARGET_HEAD_FILES

def load_docs(file_path):
    ext = file_path.suffix.lower()
    loaded = None
    try:
        if ext in [".txt", ".md", ".py", ".json", ".jsonl", ".yml", ".yaml"]:
            loaded = TextLoader(str(file_path), encoding="utf-8").load()
        elif ext == ".docx":
            loaded = Docx2txtLoader(str(file_path)).load()
        elif ext == ".csv":
            if should_load_head_only(file_path):
                loaded = CSVLoader(str(file_path), encoding="utf-8").load()[:20]
            else:
                loaded = CSVLoader(str(file_path), encoding="utf-8").load()
        elif ext == ".pdf":
            loaded = PyPDFLoader(str(file_path)).load()
        elif ext in {".xlsx", ".xls"}:
            if should_load_head_only(file_path):
                loaded = UnstructuredExcelLoader(str(file_path)).load()[:20]
            else:
                loaded = UnstructuredExcelLoader(str(file_path)).load()
        elif ext in {".pptx", ".ppt"}:
            loaded = UnstructuredPowerPointLoader(str(file_path)).load()
        else:
            print(f"未対応のファイル形式です: {file_path}")
    except Exception as e:
        print(f"読み込みスキップ: {file_path} (エラー: {e})")
    
    return loaded
```

#### 2.3.3. 全ドキュメントの読み込み

定義したローダーを使って、すべてのファイルを読み込みます。

```python
all_files = []
for file_path in file_paths:
    if not file_path.exists():
        continue

    doc = load_docs(file_path)
    
    if doc:
        for d in doc:
            d.metadata["file_name"] = str(file_path.name)
        all_files.extend(doc)

print(f"読み込み完了。合計 {len(all_files)} 個のドキュメントチャンク。")
```

### 2.4. テキストのベクトル化と保存

読み込んだテキストをOpenAIのEmbeddingモデル (`text-embedding-3-large`) を使ってベクトル化し、`Chroma`（ベクトルデータベース）に保存します。

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

save_dir = "sample_vector"
collection_name = "sample"

if os.path.exists(save_dir):
    # 既存のベクトルストアを読み込む
    vs = Chroma(
        persist_directory=save_dir,
        embedding_function=OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-large"),
        collection_name=collection_name
    )
    print(f"既存のベクトルストアを読み込みました。チャンク数: {vs._collection.count()}")
else:
    # テキストを分割 (Chunking)
    splitter = RecursiveCharacterTextSplitter(chunk_size=2048, chunk_overlap=256)
    chunks = splitter.split_documents(all_files)
    
    if len(chunks) == 0:
        raise ValueError("チャンク数が0です。ドキュメントの読み込みを確認してください。")

    # ベクトル化してChromaに保存
    vs = Chroma.from_documents(
        documents=chunks,
        embedding=OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-large"),
        collection_name=collection_name,
        persist_directory=save_dir
    )
    print(f"ベクトルストアを新規作成しました。チャンク数: {len(chunks)}")
```

### 2.5. RAGによる回答生成

ベクトルストアを使って質問に関連するドキュメントを検索し、それをコンテキストとしてLLMに渡して回答を生成させます。

```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import json

# プロンプトテンプレートの定義
prompt = ChatPromptTemplate.from_template("""
あなたはドキュメントQAのアシスタントです。
以下のコンテキストだけを根拠に、質問へ日本語で回答してください。

# 回答条件
- 回答は#出力JSONに従うものとします。
- 与えられた情報を元に確実な回答が難しい場合は answer を「わかりません」にしてください。
- 与えられていない情報から推論を行なって回答することは絶対にしないでください。
- また回答(answer)は質問文対する回答にのみとします。回答に至った経緯はreasonに記入してください。

# 質問
{question}

# コンテキスト
{context}

# 出力JSON:
{{"answer": "回答", "reason": "根拠"}}
""")

# LLMとChainの定義
llm = ChatOpenAI(api_key=api_key, model="gpt-5.4", temperature=0)
chain = prompt | llm

answer_list = []
usage_list = []

for i, d in data.iterrows():
    question = d["question"]
    
    # 関連ドキュメントを検索
    results = vs.similarity_search(query=question, k=5)

    # コンテキストを作成
    context = "\n\n---\n\n".join(
        [f"[source: {r.metadata.get('source')}]\n{r.page_content}" for r in results]
    )
    
    # 回答生成
    llm_answer = chain.invoke({"question": question, "context": context})
    
    try:
        answer_json = json.loads(llm_answer.content)
        answer_list.append(answer_json)
        usage_list.append(llm_answer.response_metadata.get('token_usage', {}))
        print(f"質問: {question[:30]}... -> 回答: {answer_json.get('answer', '')[:30]}...")
    except json.JSONDecodeError:
        # JSON形式でない場合のフォールバック
        answer_list.append({"answer": llm_answer.content, "reason": "JSON parse error"})
        print(f"質問: {question[:30]}... -> 回答(非JSON): {llm_answer.content[:30]}...")

print("FINISH!")
```

### 2.6. 提出ファイルの作成

生成した回答を `predictions.csv` として保存し、zip形式に圧縮します。

```python
import zipfile

output_df = pd.DataFrame(answer_list)

# 回答内の改行を削除
output_df["answer"] = output_df["answer"].str.replace("\n", " ", regex=False).str.replace("\r", " ", regex=False)

# 提出用CSVの作成 (ヘッダーなし、インデックスあり)
# validation=Trueの場合は "predictions_valid.csv" が作成される
if validation:
    output_df[["answer"]].to_csv("predictions_valid.csv", header=False)
else:
    output_df[["answer"]].to_csv("predictions.csv", header=False)

# zipファイルに圧縮
if not validation:
    with zipfile.ZipFile("tutorial_submit.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write("predictions.csv")
    print("提出ファイル 'tutorial_submit.zip' を作成しました。")

```

## 3. 次のステップ (Next Action)

このチュートリアルで構築したRAGシステムには、以下のような改善点が考えられます。

- **未対応ファイルの処理**:
    - PNG, Jupyter Notebook (`.ipynb`), パスワード付きファイルなどを読み込めるようにする。
    - OCR（画像からの文字認識）などを活用する。
- **書式情報の活用**:
    - WordやPowerPointの太字、文字色、ハイライトなどの情報を抽出する。
- **検索精度の向上**:
    - 質問文に含まれるファイル名や企業名で検索対象を絞り込む（事前フィルタリング）。
    - テキストの分割（Chunking）方法を工夫する。
- **高度な手法の導入**:
    - 複数の処理を組み合わせるエージェント（Agent）を活用する。
    - 複数の検索結果を統合して順序付けするRerankerを導入する。

## 4. ローカルでの評価（おまけ）

`evaluation.zip` に含まれる評価コードを使うと、検証用データ (`questions_valid.csv`) に対するスコアをローカルで確認できます。

```bash
# 1. 検証モードで回答ファイルを生成 (validation=True)
# 2. 生成された predictions_valid.csv を evaluation/submit/predictions.csv にコピー
# shutil.copy("predictions_valid.csv", "evaluation/submit/predictions.csv")

# 3. 評価スクリプトを実行
# !python evaluation/crag.py --result-name predictions.csv --result-dir evaluation/submit --ans-dir evaluation/data
```
**注意**: 評価環境を正確に再現するには、`evaluation/readme.md` に従いDockerを使用することが推奨されます。