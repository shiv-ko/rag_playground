# ハイブリッド検索（BM25＋日本語埋め込みベクトル）実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BM25単体の検索（文字bigram方式）が「冗長な自然文クエリ vs 簡潔な構造化文書」の組み合わせで構造的に失敗する問題（valid Q17等、実測5問確認済み）を、日本語埋め込みモデルによるベクトル検索をBM25と融合することで解消する。

**Architecture:** 既存の`VectorStore`（ダミーhash埋め込みのプレースホルダ、`_embed()`が「本番差し替えポイント」と明記済み）に実際の日本語埋め込みモデル（`cl-nagoya/ruri-base`）を接続し、既存だが未使用の`HybridRetriever`（BM25+ベクトル統合）をReciprocal Rank Fusion方式に置き換えた上で、本番で使われている`ProjectScopedRetriever`の内部ストアとして接続する。埋め込みは重い処理（102,263チャンク、社内共通文書は全40+案件ストアに重複追加される既存設計のため素朴にやると2〜3倍の無駄が出る）なので、テキストハッシュキー付きキャッシュ層で重複排除・ディスク永続化する。

**Tech Stack:** `sentence-transformers`（`cl-nagoya/ruri-base`、日本語特化・111Mパラメータ・768次元・Apache 2.0）、`numpy`（既存依存）、既存の`rank-bm25`はそのまま。

## Global Constraints

- 既存のパブリックインターフェース（`VectorStore.add/search/clear`、`HybridRetriever.add/search/clear`、`ProjectScopedRetriever.add/search/clear/detect_project`）の**シグネチャ後方互換を壊さない**。すべて新パラメータはオプショナル（デフォルト値で既存呼び出し元は無変更で動く）。
- `.venv/bin/pytest tests/ -v` は各タスック完了時に**全件PASS**を維持する（既存597件を含む）。
- 実モデル（`cl-nagoya/ruri-base`）をダウンロードする単体テストは書かない — ネットワーク/ダウンロード時間に依存させない。実モデル検証は Task 8（実データ検証）で行う。
- 新規依存は`pyproject.toml`の`[project.optional-dependencies]`に**新グループ`embeddings`として追加**する（既存の`parsers`/`search`/`dev`と同じパターン）。既存グループは変更しない。
- コミットは1タスク1コミット。CLAUDE.mdの制約に従い、サブエージェント使用時はSonnet-5.0かHaikuを使う。

---

## タスク一覧サマリ

| # | 内容 | 新規/変更ファイル |
|---|---|---|
| 1 | Embedder抽象化 + HashEmbedder抽出 | `src/indexer/embedder.py`（新規） |
| 2 | VectorStoreへの接続 + numpy高速化 | `src/indexer/vector_store.py`（変更） |
| 3 | JapaneseEmbedder（実モデル） | `src/indexer/embedder.py`（追記） |
| 4 | CachedEmbedder（重複排除・永続化） | `src/indexer/embedder.py`（追記） |
| 5 | HybridRetrieverをRRF方式に | `src/retriever/hybrid_retriever.py`（変更） |
| 6 | ProjectScopedRetrieverへのopt-in接続 | `src/retriever/project_scoped_retriever.py`（変更） |
| 7 | Pipeline/CLI配線 + 依存追加 | `src/orchestrator/pipeline.py`, `scripts/run_pipeline.py`, `scripts/make_predictions.py`, `scripts/eval_retrieval.py`, `pyproject.toml`（変更） |
| 8 | 実データ検証（コード変更なし） | 手順書のみ |

---

### Task 1: Embedder抽象化 + HashEmbedder抽出

既存の`VectorStore`内にベタ書きされているダミーhash埋め込みロジック（`_simple_embed`/`_cosine`）を、差し替え可能な`Embedder`という共通インターフェースに切り出す。この時点ではまだ`VectorStore`は変更しない（Task 2で接続）。

**Files:**
- Create: `src/indexer/embedder.py`
- Test: `tests/test_embedder.py`

**Interfaces:**
- Produces: `Embedder`（`embed_documents(texts: list[str]) -> np.ndarray`, `embed_query(text: str) -> np.ndarray`を持つduck-typed protocol）、`HashEmbedder`クラス（引数なしで構築可、L2正規化済みベクトルを返す）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_embedder.py`を新規作成:

```python
"""HashEmbedderの単体テスト（ネットワーク/実モデル不要）。"""
from __future__ import annotations

import numpy as np

from src.indexer.embedder import HashEmbedder


def test_hash_embedder_returns_normalized_vectors():
    embedder = HashEmbedder(dim=16)
    vecs = embedder.embed_documents(["宿泊費の上限は15,000円です。", "交通費は1回10,000円まで。"])
    assert vecs.shape == (2, 16)
    norms = np.linalg.norm(vecs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_hash_embedder_is_deterministic():
    embedder = HashEmbedder(dim=16)
    v1 = embedder.embed_query("宿泊費の上限")
    v2 = embedder.embed_query("宿泊費の上限")
    assert np.array_equal(v1, v2)


def test_hash_embedder_similar_text_higher_similarity():
    embedder = HashEmbedder(dim=64)
    a = embedder.embed_query("宿泊費の上限は15,000円です")
    b = embedder.embed_query("宿泊費の上限は15,000円")
    c = embedder.embed_query("Model Xのバッテリーは18時間")
    assert float(a @ b) > float(a @ c)
```

- [ ] **Step 2: テストを実行し失敗を確認する**

Run: `.venv/bin/pytest tests/test_embedder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.indexer.embedder'`

- [ ] **Step 3: 最小実装を書く**

`src/indexer/embedder.py`を新規作成:

```python
"""埋め込みベクトル生成の抽象化。本番差し替えポイント: 埋め込みモデルをここで差し替える。"""
from __future__ import annotations

import math
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def _simple_embed(text: str, dim: int) -> list[float]:
    """埋め込みAPIが使えない間のハッシュベース疑似ベクトル。単体テスト・デフォルト値用。"""
    vec = [0.0] * dim
    for i, ch in enumerate(text[:500]):
        vec[ord(ch) % dim] += 1.0 / (i + 1)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class HashEmbedder:
    """埋め込みAPI/モデルなしで動くハッシュベース疑似埋め込み。単体テスト・デフォルト値用。"""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.array([_simple_embed(t, self.dim) for t in texts], dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return np.array(_simple_embed(text, self.dim), dtype=np.float32)
```

- [ ] **Step 4: テストを実行し成功を確認する**

Run: `.venv/bin/pytest tests/test_embedder.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 全体テストを実行し既存への影響がないことを確認する**

Run: `.venv/bin/pytest tests/ -v`
Expected: 既存件数 + 3件 PASS、失敗0件

- [ ] **Step 6: コミット**

```bash
git add src/indexer/embedder.py tests/test_embedder.py
git commit -m "feat: add Embedder abstraction with HashEmbedder default"
```

---

### Task 2: VectorStoreへの接続 + numpy高速化

`VectorStore`が独自に持っていた`_simple_embed`/`_cosine`を削除し、Task 1の`Embedder`に委譲する。あわせて内部のスコアリングをPythonループからnumpy行列積に変更する（プロジェクトスコープあたり最大7000件超のドキュメントを扱うため）。

**Files:**
- Modify: `src/indexer/vector_store.py`
- Test: `tests/test_vector_store.py`（新規、既存`tests/test_pipeline.py`内の`test_vector_store`はそのまま残す＝重複しても害はない）

**Interfaces:**
- Consumes: `Embedder`（Task 1、`src.indexer.embedder.Embedder`/`HashEmbedder`）
- Produces: `VectorStore(embedder: Embedder | None = None)`。`embedder`省略時は`HashEmbedder()`で既存動作と完全互換。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_vector_store.py`を新規作成:

```python
"""VectorStoreの単体テスト（HashEmbedderのみ使用、実モデル不要）。"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.indexer.embedder import Embedder
from src.indexer.vector_store import VectorStore
from src.models import Document


class _FixedEmbedder:
    """テキストに関わらず固定ベクトルを返すフェイクEmbedder（注入テスト用）。"""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.array([self._vectors[t] for t in texts], dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return np.array(self._vectors[text], dtype=np.float32)


def test_vector_store_uses_injected_embedder():
    fixed = _FixedEmbedder({
        "近い文書": [1.0, 0.0],
        "遠い文書": [0.0, 1.0],
        "近いクエリ": [0.9, 0.1],
    })
    store = VectorStore(embedder=fixed)
    store.add([
        Document(text="近い文書", source_path=Path("a.txt")),
        Document(text="遠い文書", source_path=Path("b.txt")),
    ])
    results = store.search("近いクエリ", top_k=1)
    assert results[0].document.text == "近い文書"


def test_vector_store_default_embedder_is_hash_embedder():
    store = VectorStore()
    store.add([Document(text="宿泊費の上限は15,000円です。", source_path=Path("a.txt"))])
    results = store.search("宿泊費", top_k=1)
    assert len(results) == 1
    assert results[0].retrieval_method == "vector"


def test_vector_store_empty_search_returns_empty():
    store = VectorStore()
    assert store.search("何か", top_k=5) == []


def test_vector_store_clear_resets_state():
    store = VectorStore()
    store.add([Document(text="宿泊費", source_path=Path("a.txt"))])
    store.clear()
    assert store.search("宿泊費", top_k=5) == []
```

- [ ] **Step 2: テストを実行し失敗を確認する**

Run: `.venv/bin/pytest tests/test_vector_store.py -v`
Expected: FAIL — `VectorStore(embedder=fixed)` は `TypeError: __init__() got an unexpected keyword argument 'embedder'`

- [ ] **Step 3: 実装を書く**

`src/indexer/vector_store.py`を全面置き換え:

```python
"""ベクトル検索ストア。本番差し替えポイント: 埋め込みモデルをEmbedder経由で差し替える。"""
from __future__ import annotations

import numpy as np

from src.indexer.embedder import Embedder, HashEmbedder
from src.models import Document, ScoredDocument


class VectorStore:
    """
    本番差し替えポイント:
      - embedder引数に実モデル（例: JapaneseEmbedder）を渡す
      インターフェース(add/search/clear)は変えない。
    """

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder: Embedder = embedder or HashEmbedder()
        self._docs: list[Document] = []
        self._matrix: np.ndarray | None = None

    def add(self, documents: list[Document]) -> None:
        if not documents:
            return
        vecs = np.asarray(self._embedder.embed_documents([d.text for d in documents]), dtype=np.float32)
        self._docs.extend(documents)
        self._matrix = vecs if self._matrix is None else np.vstack([self._matrix, vecs])

    def clear(self) -> None:
        self._docs = []
        self._matrix = None

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        if not self._docs or self._matrix is None:
            return []
        q_vec = np.asarray(self._embedder.embed_query(query), dtype=np.float32)
        scores = self._matrix @ q_vec
        top_idx = np.argsort(-scores)[:top_k]
        return [
            ScoredDocument(document=self._docs[i], score=float(scores[i]), retrieval_method="vector")
            for i in top_idx
        ]
```

- [ ] **Step 4: テストを実行し成功を確認する**

Run: `.venv/bin/pytest tests/test_vector_store.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 全体テストを実行する（既存test_pipeline.pyのtest_vector_storeも含む）**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS、失敗0件

- [ ] **Step 6: コミット**

```bash
git add src/indexer/vector_store.py tests/test_vector_store.py
git commit -m "refactor: delegate VectorStore embedding to injectable Embedder, vectorize scoring"
```

---

### Task 3: JapaneseEmbedder（実モデル `cl-nagoya/ruri-base`）

**Files:**
- Modify: `src/indexer/embedder.py`（`JapaneseEmbedder`クラスを追記）
- Test: `tests/test_embedder.py`（追記）

**Interfaces:**
- Consumes: `sentence-transformers`パッケージ（Task 7でpyproject.tomlに追加。このタスクではimportを遅延させるためテストはモック注入で実施しネットワーク不要）
- Produces: `JapaneseEmbedder(model_name: str = "cl-nagoya/ruri-base", batch_size: int = 64)`。`embed_documents`は`"文章: "`プレフィックス、`embed_query`は`"クエリ: "`プレフィックスを付与してモデルへ渡す。モデルは初回呼び出し時まで遅延ロード（`_load_model()`）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_embedder.py`に追記:

```python
from src.indexer.embedder import JapaneseEmbedder


class _FakeSTModel:
    """sentence_transformers.SentenceTransformerの最小フェイク。呼び出された引数を記録する。"""

    def __init__(self) -> None:
        self.encode_calls: list[dict] = []

    def encode(self, texts, batch_size=None, normalize_embeddings=None):
        self.encode_calls.append({
            "texts": texts,
            "batch_size": batch_size,
            "normalize_embeddings": normalize_embeddings,
        })
        is_batch = isinstance(texts, list)
        n = len(texts) if is_batch else 1
        vecs = np.tile(np.array([1.0, 0.0], dtype=np.float32), (n, 1))
        return vecs if is_batch else vecs[0]


def test_japanese_embedder_applies_document_prefix():
    embedder = JapaneseEmbedder()
    fake = _FakeSTModel()
    embedder._model = fake  # 遅延ロードをバイパスしてフェイクを注入

    embedder.embed_documents(["これはテスト文書です。"])

    assert fake.encode_calls[0]["texts"] == ["文章: これはテスト文書です。"]
    assert fake.encode_calls[0]["normalize_embeddings"] is True


def test_japanese_embedder_applies_query_prefix():
    embedder = JapaneseEmbedder()
    fake = _FakeSTModel()
    embedder._model = fake

    embedder.embed_query("これは質問です。")

    assert fake.encode_calls[0]["texts"] == "クエリ: これは質問です。"


def test_japanese_embedder_lazy_loads_model_once():
    embedder = JapaneseEmbedder()
    fake = _FakeSTModel()
    embedder._model = fake

    embedder.embed_documents(["a"])
    embedder.embed_query("b")

    # _load_model()が_modelを上書きしていない（既にセット済みならそのまま使う）ことを確認
    assert embedder._model is fake
```

- [ ] **Step 2: テストを実行し失敗を確認する**

Run: `.venv/bin/pytest tests/test_embedder.py -v`
Expected: FAIL — `ImportError: cannot import name 'JapaneseEmbedder'`

- [ ] **Step 3: 実装を書く**

`src/indexer/embedder.py`の末尾に追記:

```python
_QUERY_PREFIX = "クエリ: "
_DOC_PREFIX = "文章: "


class JapaneseEmbedder:
    """日本語特化の埋め込みモデル（cl-nagoya/ruri-base）。本番用。
    要install: sentence-transformers, fugashi, unidic-lite, sentencepiece（pyproject.tomlの[embeddings]グループ）。"""

    def __init__(self, model_name: str = "cl-nagoya/ruri-base", batch_size: int = 64) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        model = self._load_model()
        prefixed = [_DOC_PREFIX + t for t in texts]
        vecs = model.encode(prefixed, batch_size=self.batch_size, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        model = self._load_model()
        vec = model.encode(_QUERY_PREFIX + text, normalize_embeddings=True)
        return np.asarray(vec, dtype=np.float32)
```

- [ ] **Step 4: テストを実行し成功を確認する**

Run: `.venv/bin/pytest tests/test_embedder.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: 全体テストを実行する**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS（`sentence_transformers`は`_load_model()`内でのみimportされるため、未インストールでもこのタスクのテストは通る）

- [ ] **Step 6: コミット**

```bash
git add src/indexer/embedder.py tests/test_embedder.py
git commit -m "feat: add JapaneseEmbedder (cl-nagoya/ruri-base) with lazy model loading"
```

---

### Task 4: CachedEmbedder（テキストハッシュ重複排除・ディスク永続化）

`ProjectScopedRetriever.add()`は社内共通文書（`is_internal=True`）を全プロジェクトストアに複製追加する既存設計（`src/retriever/project_scoped_retriever.py:62`）のため、素朴に各ストアで埋め込みを計算すると同一テキストが数十回重複して埋め込まれる。テキストのSHA256ハッシュをキーにしたキャッシュで重複を排除し、`cache_dir`が指定されていればディスクにも永続化する（run間の再計算を避ける）。

**Files:**
- Modify: `src/indexer/embedder.py`（`CachedEmbedder`クラスを追記）
- Test: `tests/test_embedder.py`（追記）

**Interfaces:**
- Consumes: 任意の`Embedder`（Task 1〜3のいずれか）をラップする
- Produces: `CachedEmbedder(inner: Embedder, cache_path: Path | None = None)`。`embed_documents`は内部で未キャッシュ分のみ`inner.embed_documents()`を呼ぶ。`flush()`メソッドでディスクへ書き込む（`embed_documents`の呼び出しごとには自動保存しない — 大きなキャッシュを何十回も書き込むのを避けるため、呼び出し側が明示的に`flush()`する）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_embedder.py`に追記:

```python
from src.indexer.embedder import CachedEmbedder


class _CountingEmbedder:
    """embed_documentsの呼び出し回数と実際に埋め込んだテキストを記録するフェイク。"""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        self.calls.append(list(texts))
        return np.array([[float(len(t)), 0.0] for t in texts], dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return np.array([float(len(text)), 0.0], dtype=np.float32)


def test_cached_embedder_dedupes_repeated_texts_within_session():
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner)

    cached.embed_documents(["共通文書A", "固有文書1"])
    cached.embed_documents(["共通文書A", "固有文書2"])  # "共通文書A"は既にキャッシュ済み

    # 2回目の呼び出しでは新規分（"固有文書2"）のみinner側に渡る
    assert inner.calls[0] == ["共通文書A", "固有文書1"]
    assert inner.calls[1] == ["固有文書2"]


def test_cached_embedder_returns_correct_vectors_in_order():
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner)

    vecs1 = cached.embed_documents(["共通文書A", "固有文書1"])
    vecs2 = cached.embed_documents(["固有文書2", "共通文書A"])  # 順序が変わっても正しく揃う

    assert vecs2[0][0] == float(len("固有文書2"))
    assert vecs2[1][0] == vecs1[0][0]  # "共通文書A"は同じベクトル


def test_cached_embedder_persists_to_disk(tmp_path):
    cache_path = tmp_path / "emb_cache.pkl"
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner, cache_path=cache_path)
    cached.embed_documents(["文書A"])
    cached.flush()

    assert cache_path.exists()

    # 新しいCachedEmbedderインスタンスがディスクキャッシュを読み込み、再計算しない
    inner2 = _CountingEmbedder()
    cached2 = CachedEmbedder(inner2, cache_path=cache_path)
    cached2.embed_documents(["文書A"])
    assert inner2.calls == []  # 全てキャッシュヒットのためinner2は一度も呼ばれない


def test_cached_embedder_embed_query_passthrough():
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner)
    result = cached.embed_query("質問文")
    assert result[0] == float(len("質問文"))
```

- [ ] **Step 2: テストを実行し失敗を確認する**

Run: `.venv/bin/pytest tests/test_embedder.py -v`
Expected: FAIL — `ImportError: cannot import name 'CachedEmbedder'`

- [ ] **Step 3: 実装を書く**

`src/indexer/embedder.py`の末尾に追記:

```python
import hashlib
import pickle
from pathlib import Path


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


class CachedEmbedder:
    """テキストのSHA256ハッシュをキーに埋め込みをキャッシュするラッパー。
    同一テキストが複数プロジェクトストアに重複追加されても埋め込み計算を1回で済ませる
    （社内共通文書が全プロジェクトストアへ複製される既存設計のため重要）。"""

    def __init__(self, inner: Embedder, cache_path: Path | None = None) -> None:
        self._inner = inner
        self._cache_path = cache_path
        self._cache: dict[str, np.ndarray] = {}
        if cache_path is not None and cache_path.exists():
            self._cache = pickle.loads(cache_path.read_bytes())

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        hashes = [_hash_text(t) for t in texts]
        missing_positions = [i for i, h in enumerate(hashes) if h not in self._cache]
        if missing_positions:
            missing_texts = [texts[i] for i in missing_positions]
            new_vecs = self._inner.embed_documents(missing_texts)
            for i, vec in zip(missing_positions, new_vecs):
                self._cache[hashes[i]] = np.asarray(vec, dtype=np.float32)
        return np.stack([self._cache[h] for h in hashes])

    def embed_query(self, text: str) -> np.ndarray:
        return self._inner.embed_query(text)

    def flush(self) -> None:
        if self._cache_path is None:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._cache_path.with_suffix(self._cache_path.suffix + ".tmp")
        tmp_path.write_bytes(pickle.dumps(self._cache))
        tmp_path.replace(self._cache_path)
```

このコードはファイル冒頭の`import numpy as np`より下に置けば良いが、`hashlib`/`pickle`/`Path`のimportはファイル先頭のimportブロックへ移動して整理する（ファイル末尾への追記だが、importは慣習的にファイル先頭にまとめる）。

- [ ] **Step 4: テストを実行し成功を確認する**

Run: `.venv/bin/pytest tests/test_embedder.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: 全体テストを実行する**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS

- [ ] **Step 6: コミット**

```bash
git add src/indexer/embedder.py tests/test_embedder.py
git commit -m "feat: add CachedEmbedder to dedupe repeated-text embeddings across project stores"
```

---

### Task 5: HybridRetrieverをReciprocal Rank Fusion方式に

既存の`HybridRetriever`（min-max正規化＋重み付き合算、`vector_weight=0.6`/`keyword_weight=0.4`固定値）を、スコアスケールの異なるBM25とコサイン類似度をチューニングなしで統合できるReciprocal Rank Fusion（RRF）に置き換える。あわせて`embedder`引数を追加できるようにする。

**Files:**
- Modify: `src/retriever/hybrid_retriever.py`
- Modify: `tests/test_indexer.py`（`test_vector_only_weight_matches_vector_store_top_result`を削除——`vector_weight`/`keyword_weight`重み付け合成を直接テストしており、RRF化で意図的に廃止されるため）
- Test: 既存`tests/test_pipeline.py`の`test_hybrid_retriever`はそのまま（`assert len(results) > 0`のみなのでRRF化で壊れない）。新規アサーションを追加。

**事前チェックで判明した既存テストとの矛盾**: `tests/test_indexer.py`の`TestHybridRetriever.test_vector_only_weight_matches_vector_store_top_result`（339-363行目）は`HybridRetriever(vector_weight=1.0, keyword_weight=0.0)`を直接構築し、`VectorStore`単体と同じ先頭結果になることを検証している。このテストは「重み付け合成」という廃止対象の機能そのものを前提にしているため、Step 0としてこのテストメソッドを削除する（ユーザー承認済み、2026-07-13）。

**Interfaces:**
- Consumes: `VectorStore`（Task 2）, `KeywordStore`（既存）, `Embedder`（Task 1〜3のいずれか、`VectorStore`へ渡す）
- Produces: `HybridRetriever(embedder: Embedder | None = None, rerank_top_n: int = 3)`。`search(query, top_k)`は`ScoredDocument`のリストを返す（`retrieval_method="hybrid"`）。

- [ ] **Step 0: 廃止対象のテストを削除する**

`tests/test_indexer.py`の`TestHybridRetriever`クラスから、`test_vector_only_weight_matches_vector_store_top_result`メソッド全体（339〜363行目、直前の空行1行を含む）を削除する。このテストは`vector_weight=1.0, keyword_weight=0.0`という廃止対象のパラメータを直接検証しているため。同クラスの他のテスト（`test_add_and_search_returns_integrated_results`等5件）はパラメータなし構築のみなので変更不要。

Run: `.venv/bin/pytest tests/test_indexer.py -v`
Expected: 削除後、残りの5件がPASS（この時点ではまだ`HybridRetriever`本体は変更していないので、既存パラメータのままでも通る）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pipeline.py`の`test_hybrid_retriever`の直後に追記(同ファイル、`from src.retriever.hybrid_retriever import HybridRetriever`は既にimport済み):

```python
def test_hybrid_retriever_surfaces_doc_that_loses_on_keyword_alone(sample_docs: list[Document]) -> None:
    """BM25単体では上位に来ない文書でも、ベクトル側で強く一致していればRRFで浮上することを確認する。"""
    from src.indexer.embedder import Embedder
    import numpy as np

    class _VectorFavoringEmbedder:
        """"Model X"を含む文書だけがクエリと強く一致するベクトルを返すフェイク。"""

        def embed_documents(self, texts: list[str]) -> np.ndarray:
            return np.array(
                [[1.0, 0.0] if "Model X" in t else [0.0, 1.0] for t in texts],
                dtype=np.float32,
            )

        def embed_query(self, text: str) -> np.ndarray:
            return np.array([1.0, 0.0], dtype=np.float32)

    retriever = HybridRetriever(embedder=_VectorFavoringEmbedder())
    retriever.add(sample_docs)
    # クエリはキーワード的には宿泊費関連の文書に近いが、ベクトル側はModel X文書を最優先する
    results = retriever.search("何かのバッテリー時間について教えてください", top_k=1)
    assert "Model X" in results[0].document.text
```

- [ ] **Step 2: テストを実行し失敗を確認する**

Run: `.venv/bin/pytest tests/test_pipeline.py::test_hybrid_retriever_surfaces_doc_that_loses_on_keyword_alone -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'embedder'`

- [ ] **Step 3: 実装を書く**

`src/retriever/hybrid_retriever.py`を全面置き換え:

```python
"""ベクトル検索とキーワード検索をReciprocal Rank Fusion(RRF)で統合するHybridRetriever。"""
from __future__ import annotations

from src.indexer.embedder import Embedder
from src.indexer.keyword_store import KeywordStore
from src.indexer.vector_store import VectorStore
from src.models import Document, ScoredDocument

_RRF_K = 60  # Cormack et al. (2009) の標準値。文献値をそのまま使い、valid過適合の対象にしない。


class HybridRetriever:
    def __init__(
        self,
        embedder: Embedder | None = None,
        rerank_top_n: int = 3,
    ) -> None:
        self.vector_store = VectorStore(embedder=embedder)
        self.keyword_store = KeywordStore()
        self.rerank_top_n = rerank_top_n

    def add(self, documents: list[Document]) -> None:
        self.vector_store.add(documents)
        self.keyword_store.add(documents)

    def clear(self) -> None:
        self.vector_store.clear()
        self.keyword_store.clear()

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        fetch_k = max(top_k * 6, 30)
        vec_results = self.vector_store.search(query, fetch_k)
        kw_results = self.keyword_store.search(query, fetch_k)
        fused = _reciprocal_rank_fusion([vec_results, kw_results])
        return fused[:top_k]


def _reciprocal_rank_fusion(
    result_lists: list[list[ScoredDocument]], k: int = _RRF_K
) -> list[ScoredDocument]:
    scores: dict[int, float] = {}
    doc_by_key: dict[int, ScoredDocument] = {}
    for results in result_lists:
        for rank, r in enumerate(results, start=1):
            key = id(r.document)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in doc_by_key:
                doc_by_key[key] = r
    fused = [
        ScoredDocument(document=doc_by_key[key].document, score=score, retrieval_method="hybrid")
        for key, score in scores.items()
    ]
    fused.sort(key=lambda x: x.score, reverse=True)
    return fused
```

- [ ] **Step 4: テストを実行し成功を確認する**

Run: `.venv/bin/pytest tests/test_pipeline.py -k hybrid_retriever -v`
Expected: PASS (両テストとも)

- [ ] **Step 5: 全体テストを実行する**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS

- [ ] **Step 6: コミット**

```bash
git add src/retriever/hybrid_retriever.py tests/test_pipeline.py tests/test_indexer.py
git commit -m "refactor: switch HybridRetriever score fusion from weighted-normalize to RRF"
```

---

### Task 6: ProjectScopedRetrieverへのopt-in接続

`ProjectScopedRetriever`が内部で使うストアを、`embedder`が渡された場合のみ`KeywordStore`から`HybridRetriever`に切り替える。`embedder`省略時（既存の全呼び出し元）は**完全に既存動作のまま**（`KeywordStore`のみ）。

**Files:**
- Modify: `src/retriever/project_scoped_retriever.py`
- Test: `tests/test_project_scoped_retriever.py`（追記、既存9テストは無変更）

**Interfaces:**
- Consumes: `Embedder`（Task 1〜3）, `HybridRetriever`（Task 5）
- Produces: `ProjectScopedRetriever(project_aliases=None, embedder: Embedder | None = None)`。`embedder`が`None`でない場合、`_global_store`と各`_project_stores[project]`は`HybridRetriever(embedder=embedder)`になる（**同一の`embedder`インスタンスを共有**——Task 4の`CachedEmbedder`による重複排除が全ストアを横断して効くために必須）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_project_scoped_retriever.py`の末尾に追記:

```python
def test_search_uses_hybrid_retriever_when_embedder_given():
    import numpy as np
    from src.indexer.embedder import Embedder

    class _StubEmbedder:
        def embed_documents(self, texts: list[str]) -> np.ndarray:
            return np.zeros((len(texts), 2), dtype=np.float32)

        def embed_query(self, text: str) -> np.ndarray:
            return np.zeros(2, dtype=np.float32)

    retriever = ProjectScopedRetriever(embedder=_StubEmbedder())
    retriever.add([_doc("スケジュール タスク 進捗", "data/A社/02.計画/計画.xlsx")])

    from src.retriever.hybrid_retriever import HybridRetriever
    assert isinstance(retriever._global_store, HybridRetriever)

    results = retriever.search("A社のスケジュールでタスクの進捗は？", top_k=1)
    assert len(results) == 1


def test_search_without_embedder_still_uses_keyword_store():
    from src.indexer.keyword_store import KeywordStore

    retriever = ProjectScopedRetriever()
    retriever.add([_doc("スケジュール タスク 進捗", "data/A社/02.計画/計画.xlsx")])
    assert isinstance(retriever._global_store, KeywordStore)
```

- [ ] **Step 2: テストを実行し失敗を確認する**

Run: `.venv/bin/pytest tests/test_project_scoped_retriever.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'embedder'`

- [ ] **Step 3: 実装を書く**

`src/retriever/project_scoped_retriever.py`の該当箇所を変更:

```python
from src.indexer.embedder import Embedder
from src.indexer.keyword_store import KeywordStore
from src.retriever.hybrid_retriever import HybridRetriever
from src.models import Document, ScoredDocument
from src.retriever.question_file_scope import (
    find_named_files,
    find_stem_matches,
    question_mentions_extension,
)
```

（既存importに`Embedder`と`HybridRetriever`を追加。`KeywordStore`のimportはそのまま残す。）

`__init__`と`add`を変更:

```python
class ProjectScopedRetriever:
    """
    add() は全ドキュメントを1回でまとめて渡す想定（Pipeline.build_indexの使い方と一致）。
    embedderを渡すとBM25+ベクトルのハイブリッド検索になる（未指定時は既存のBM25単体のまま）。
    """

    def __init__(
        self,
        project_aliases: dict[str, list[str]] | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._embedder = embedder
        self._global_store = self._make_store()
        self._project_stores: dict[str, KeywordStore | HybridRetriever] = {}
        self._project_names: list[str] = []
        self._aliases_by_normalized_name: dict[str, list[str]] = {
            _normalize_project_name(name): aliases
            for name, aliases in (project_aliases or {}).items()
        }

    def _make_store(self) -> KeywordStore | HybridRetriever:
        if self._embedder is not None:
            return HybridRetriever(embedder=self._embedder)
        return KeywordStore()

    def add(self, documents: list[Document]) -> None:
        self._global_store.add(documents)

        internal_docs = [d for d in documents if d.metadata.get("is_internal")]
        by_project: dict[str, list[Document]] = {}
        for doc in documents:
            project = doc.metadata.get("project")
            if project:
                by_project.setdefault(project, []).append(doc)

        for project, docs in by_project.items():
            if project not in self._project_stores:
                self._project_stores[project] = self._make_store()
                self._project_names.append(project)
            self._project_stores[project].add(docs)
            if internal_docs:
                self._project_stores[project].add(internal_docs)
```

`search`メソッド内の型ヒントは変更不要（`store.search(query, top_k)`インターフェースは`KeywordStore`と`HybridRetriever`で共通のため、以降のロジックは無変更）。

- [ ] **Step 4: テストを実行し成功を確認する**

Run: `.venv/bin/pytest tests/test_project_scoped_retriever.py -v`
Expected: PASS (11 tests — 既存9件 + 新規2件)

- [ ] **Step 5: 全体テストを実行する**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS

- [ ] **Step 6: コミット**

```bash
git add src/retriever/project_scoped_retriever.py tests/test_project_scoped_retriever.py
git commit -m "feat: make ProjectScopedRetriever opt into HybridRetriever via embedder param"
```

---

### Task 7: Pipeline/CLI配線 + 依存追加

`Pipeline`に`use_hybrid_search`フラグを追加（デフォルト`False`＝既存動作のまま）。`True`の場合、`JapaneseEmbedder`を`CachedEmbedder`でラップし（`cache_dir`があればディスク永続化）、`ProjectScopedRetriever`へ渡す。`run_pipeline.py`・`make_predictions.py`・`eval_retrieval.py`に`--hybrid-search`フラグを追加する。

**Files:**
- Modify: `src/orchestrator/pipeline.py`
- Modify: `scripts/run_pipeline.py`
- Modify: `scripts/make_predictions.py`
- Modify: `scripts/eval_retrieval.py`
- Modify: `pyproject.toml`
- Test: `tests/test_pipeline.py`（追記）

**Interfaces:**
- Consumes: `CachedEmbedder`, `JapaneseEmbedder`（Task 3〜4）, `ProjectScopedRetriever(embedder=...)`（Task 6）
- Produces: `Pipeline(..., use_hybrid_search: bool = False)`。`build_index()`完了後、ハイブリッド有効時は`self.embedder.flush()`を呼ぶ。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pipeline.py`に追記（`test_pipeline_uses_project_scoped_retriever`の直後）:

```python
def test_pipeline_hybrid_search_flag_wires_embedder(tmp_path: Path) -> None:
    """use_hybrid_search=Trueの場合、retrieverの内部ストアがHybridRetrieverになる。"""
    from src.orchestrator.pipeline import Pipeline
    from src.retriever.hybrid_retriever import HybridRetriever

    pipeline = Pipeline(data_dir=tmp_path, use_hybrid_search=True)
    assert pipeline.retriever._embedder is not None
    pipeline.retriever.add([])  # 空addでも_global_storeの型は初期化時点で決まる
    assert isinstance(pipeline.retriever._global_store, HybridRetriever)


def test_pipeline_default_no_hybrid_search(tmp_path: Path) -> None:
    from src.orchestrator.pipeline import Pipeline
    from src.indexer.keyword_store import KeywordStore

    pipeline = Pipeline(data_dir=tmp_path)
    assert pipeline.retriever._embedder is None
    assert isinstance(pipeline.retriever._global_store, KeywordStore)
```

- [ ] **Step 2: テストを実行し失敗を確認する**

Run: `.venv/bin/pytest tests/test_pipeline.py -k hybrid_search_flag -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'use_hybrid_search'`

- [ ] **Step 3: 実装を書く**

`src/orchestrator/pipeline.py`の`__init__`（78行目付近）を変更。既存の`exclude_dirs: list[Path] | None = None,`パラメータの直後に追加:

```python
        exclude_dirs: list[Path] | None = None,
        use_hybrid_search: bool = False,
    ) -> None:
```

`self.dispatcher = ParserDispatcher()`の直前、`self.retriever = ProjectScopedRetriever(...)`の行を置き換え:

```python
        self.dispatcher = ParserDispatcher()
        self.embedder = None
        if use_hybrid_search:
            from src.indexer.embedder import CachedEmbedder, JapaneseEmbedder
            cache_path = (cache_dir / "embeddings_ruri-base.pkl") if cache_dir is not None else None
            self.embedder = CachedEmbedder(JapaneseEmbedder(), cache_path=cache_path)
        self.retriever = ProjectScopedRetriever(project_aliases=project_aliases, embedder=self.embedder)
```

（この2行は既存の`self.retriever = ProjectScopedRetriever(project_aliases=project_aliases)`という1行を置き換える形になる。`self.dispatcher = ParserDispatcher()`の行は既存のまま重複させない。）

`build_index()`メソッドの末尾（`self.logger.info("インデックス構築完了")`の直後）に追記:

```python
    def build_index(self) -> None:
        self.logger.info(f"インデックス構築開始: {self.data_dir}")
        if self.cache_dir is not None:
            from src.utils.parse_cache import load_or_parse
            docs = load_or_parse(self.data_dir, self.cache_dir, exclude_dirs=self.exclude_dirs)
        else:
            docs = self.dispatcher.parse_directory(self.data_dir, exclude_dirs=self.exclude_dirs)
        self.logger.info(f"  {len(docs)} チャンク取得")
        self.retriever.add(docs)
        if self.embedder is not None:
            self.embedder.flush()
        self.logger.info("インデックス構築完了")
```

`pyproject.toml`の`[project.optional-dependencies]`ブロックに新グループを追加（`dev = [...]`の直前）:

```toml
embeddings = [
    "sentence-transformers>=3.0",
    "fugashi>=1.3",
    "unidic-lite>=1.0.8",
    "sentencepiece>=0.2",
]
```

`scripts/run_pipeline.py`の`--no-judge`引数の直後に追加:

```python
    parser.add_argument("--hybrid-search", action="store_true",
                        help="BM25+日本語埋め込みベクトルのハイブリッド検索を使う（要 pip install -e '.[embeddings]'）")
```

`pipeline = Pipeline(`呼び出しの`exclude_dirs=[args.questions.parent],`の直後に追加:

```python
        use_hybrid_search=args.hybrid_search,
```

`scripts/make_predictions.py`にも同様に、`--runs`引数の直後に追加:

```python
    parser.add_argument("--hybrid-search", action="store_true",
                        help="BM25+日本語埋め込みベクトルのハイブリッド検索を使う（要 pip install -e '.[embeddings]'）")
```

`pipeline = Pipeline(`呼び出しの`exclude_dirs=[args.questions.parent],`の直後に追加:

```python
        use_hybrid_search=args.hybrid_search,
```

`scripts/eval_retrieval.py`の`--no-cache`引数の直後に追加:

```python
    parser.add_argument("--hybrid-search", action="store_true",
                        help="BM25+日本語埋め込みベクトルのハイブリッド検索を使う（要 pip install -e '.[embeddings]'）")
```

`retriever = ProjectScopedRetriever(project_aliases=project_aliases)`の行を置き換え:

```python
    embedder = None
    if args.hybrid_search:
        from src.indexer.embedder import CachedEmbedder, JapaneseEmbedder
        embedder = CachedEmbedder(JapaneseEmbedder(), cache_path=ROOT / ".cache" / "embeddings_ruri-base.pkl")
    retriever = ProjectScopedRetriever(project_aliases=project_aliases, embedder=embedder)
    retriever.add(docs)
    if embedder is not None:
        embedder.flush()
```

（この`retriever.add(docs)`は既存の`retriever.add(docs)`と重複するので、既存の1行をこのブロックで置き換える。）

- [ ] **Step 4: テストを実行し成功を確認する**

Run: `.venv/bin/pytest tests/test_pipeline.py -k hybrid_search -v`
Expected: PASS (2 tests)

- [ ] **Step 5: 全体テストを実行する**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件PASS（`sentence_transformers`をインストールしていなくても、`use_hybrid_search=False`がデフォルトなので既存テストはすべて通る。Step 1のテストは`use_hybrid_search=True`だが、`JapaneseEmbedder`は遅延ロードなので構築時点ではimportされない——ただしこのテストは`pipeline.retriever.add([])`しか呼ばないため`embed_documents`は空リストで早期returnし、実モデルはロードされない）

- [ ] **Step 6: コミット**

```bash
git add src/orchestrator/pipeline.py scripts/run_pipeline.py scripts/make_predictions.py scripts/eval_retrieval.py pyproject.toml tests/test_pipeline.py
git commit -m "feat: wire opt-in hybrid search flag through Pipeline and CLI scripts"
```

---

### Task 8: 実データ検証（コード変更なし・手順書）

Task 1〜7はコード実装のみで、実モデルでの効果測定はまだ行っていない。ここで初めて依存をインストールし、実データで効果を検証する。**このタスクはTDDタスクではなく、検証結果に応じて次の判断（デフォルト化するか・追加チューニングするか）をユーザーと相談するためのチェックリスト。**

- [ ] **Step 1: 依存をインストール**

```bash
.venv/bin/pip install -e ".[embeddings]"
```

初回は`cl-nagoya/ruri-base`（約450MB）がHugging Face Hubからダウンロードされる。

- [ ] **Step 2: 検索recallの前後比較**

```bash
.venv/bin/python scripts/eval_retrieval.py --data-dir "data/raw/share/共有ドライブ" --top-k 5 --out-dir experiments
.venv/bin/python scripts/eval_retrieval.py --data-dir "data/raw/share/共有ドライブ" --top-k 5 --hybrid-search --out-dir experiments
```

2つの実行結果（`experiments/retrieval_valid_*.json`）を比較し、特にvalid#0・#10・#14・#17・#19（本セッションの調査で確認済みの生成LLM検索依存パスの失敗5問）の`hit`/`first_hit_rank`が改善しているかを確認する。**わざわざQ17用に何かを調整しない**——ここでの目的は5問全体の底上げを機械的に確認すること。

- [ ] **Step 3: インデックス構築時間の実測**

```bash
time .venv/bin/python scripts/run_pipeline.py --data-dir "data/raw/share/共有ドライブ" --questions "data/raw/share/質問回答/questions_valid.csv" --hybrid-search --run-name hybrid_smoke --no-judge
```

初回（キャッシュなし）の`インデックス構築完了`までの時間を記録する。本番3時間制限に対して許容範囲かをdaily作業ログに残す。2回目の実行（同じ`.cache`ディレクトリで再実行）で埋め込みキャッシュがヒットし大幅に短縮されることも確認する。

- [ ] **Step 4: valid N=3 + official較正（ユーザー承認必須）**

Step 2・3の結果が良好であれば、既存の確立された手順（`docs/daily作業ログ/20260713_213900.md`と同じパターン）でハイブリッド検索を検証する:
1. AskUserQuestionでAnthropic/OpenAI課金の承認を得る。
2. `run_pipeline.py --hybrid-search`でvalid N=3実行（run-name衝突回避のため`_r1`/`_r2`/`_r3`サフィックス必須）。
3. `scripts/calibrate_judge.py`でofficial較正、新規Incorrectがないか確認。
4. 問題なければ`Pipeline`・`run_pipeline.py`・`make_predictions.py`・`eval_retrieval.py`の`use_hybrid_search`/`--hybrid-search`のデフォルトを`True`に切り替えるコミットを別途作成し、`docs/plan/plan_0703.md`に結果を記録する。

- [ ] **Step 5: daily作業ログに記録**

`docs/daily作業ログ/`に新規ログを作成し、Step 2〜4の結果（recall改善の実測値、indexing時間、採否判断）を記録する。

---

## Self-Review

- **Spec coverage**: 「BM25単体の検索recall欠陥をベクトル検索で補う」という目的に対し、Task1-2(Embedder抽象化)→Task3(実モデル)→Task4(重複排除キャッシュ、性能上必須)→Task5(RRF統合)→Task6(本番retrieverへのopt-in接続)→Task7(CLI配線・依存追加)→Task8(実データ検証)で一気通貫している。既存の「本番差し替えポイント」コメント・`retrieval_method="vector"/"hybrid"`という既存設計の意図とも整合。
- **Placeholder scan**: 全タスクに実コード・実コマンド・期待値を明記済み。「TODO」「適切なエラーハンドリングを追加」等の曖昧表現なし。
- **Type consistency**: `Embedder`（Task1）→`VectorStore(embedder=...)`（Task2）→`JapaneseEmbedder`/`CachedEmbedder`（Task3-4、いずれも`Embedder`互換）→`HybridRetriever(embedder=...)`（Task5）→`ProjectScopedRetriever(embedder=...)`（Task6）→`Pipeline(use_hybrid_search=...)`（Task7）の型・引数名は一貫している。
