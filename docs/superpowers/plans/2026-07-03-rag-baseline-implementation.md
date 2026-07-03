# RAGベースライン実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docs/todo_and_experiments.md` のTODOリスト(1〜10番)を実装し、実データ(`data/raw/share/共有ドライブ`)に対して「テキストのみ・keyword_store(BM25)・案件フォルダ絞り込み・Claude生成・確信度ゲート」で構成される最小構成ベースラインを動かせる状態にする。

**Architecture:** 既存のセットアップ済みスケルトン（Protocol定義＋ダミー実装、94件のテスト）を土台に、(1) 実データのパース耐性向上、(2) 案件フォルダ絞り込み＋BM25の新規Retriever、(3) Generator/JudgeのClaude API接続、(4) CSV形式の質問ファイル読み込み、を積み上げる。`image_parser`・`vector_store`の実装、社内用語集展開、パスワード復号は今回のスコープ外（`docs/todo_and_experiments.md`の実験バックログ）。

**Tech Stack:** Python 3.11+, pytest, anthropic SDK, pypdf, python-docx, openpyxl, python-pptx, rank-bm25。フレームワーク（LangChain等）は使わない自前実装。

## Global Constraints

- 回答は1000トークン以内（`CLAUDE.md` の絶対制約。超過はエラー）
- TDD厳守: テストを先に書く→失敗を確認する→最小実装→全テスト通過を確認する（`.claude/skills/dev-process.md`）
- 本番差し替えポイントのインターフェース（`can_handle/parse`, `add/search/clear`, `_call_llm`）は変えない（`.claude/skills/architecture.md`）
- LLM呼び出しを含むコンポーネントは、サブクラスで `_call_llm` をオーバーライドしてテストを決定的にする（既存の `FakeGenerator`/`FakeJudge` パターンを踏襲）
- このリポジトリはgitで管理されていない（`Is a git repository: false`）。そのため各タスクにコミット手順は含めない
- 完了報告時は必ず `.venv/bin/pytest tests/ -v` の出力全体を貼ること（既存94件 + 本計画で追加する分すべてが通ること）

---

## 事前確認済みの環境状態

- `anthropic==0.115.0` のみインストール済み。`pypdf`/`python-docx`/`openpyxl`/`python-pptx`/`rank-bm25` は未インストール（Task 1で導入）
- `.env` の `ANTHROPIC_API_KEY` はプレースホルダーのまま（実キー未設定）。Task 8・9（Claude API接続）はモックでテストするが、Task 12・13（実データでのライブ実行）にはユーザーが実キーを設定する必要がある

---

### Task 1: 依存ライブラリのインストール

**Files:**
- Modify: なし（環境のみ）

- [ ] **Step 1: parsers/search extrasをインストール**

Run: `.venv/bin/pip install -e ".[parsers,search,dev]"`

- [ ] **Step 2: インポート確認**

Run:
```bash
.venv/bin/python -c "import pypdf, docx, openpyxl, pptx, rank_bm25; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: 既存テストが引き続き全件通ることを確認**

Run: `.venv/bin/pytest tests/ -v`
Expected: `94 passed`（ライブラリ導入により `PDFParser`/`OfficeParser`/`KeywordStore` の一部テストが「未インストール時スタブ」から実際のライブラリ経由の分岐に変わるが、`patch.dict(sys.modules, {...: None})` で強制的にImportErrorを起こしているため既存テストの結果は変わらない）

---

### Task 2: dispatcherへのメタデータ抽出・ノイズファイル除外

**Files:**
- Modify: `src/parsers/dispatcher.py`
- Test: `tests/test_parsers.py`

**Interfaces:**
- Produces: `ParserDispatcher.parse_directory(directory: Path) -> list[Document]` は各 `Document.metadata` に `project: str | None`, `category: str | None`, `is_internal: bool` を設定する

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_parsers.py` の `TestParserDispatcher` クラスに追記:

```python
    def test_parse_directory_extracts_project_metadata(self, tmp_path: Path) -> None:
        """プロジェクト/<企業名>/<カテゴリ>/ 配下のファイルにproject/categoryメタデータを付与する"""
        proj_dir = tmp_path / "プロジェクト" / "サンプル株式会社" / "00.提案"
        proj_dir.mkdir(parents=True)
        (proj_dir / "doc.txt").write_text("提案内容", encoding="utf-8")

        dispatcher = ParserDispatcher()
        docs = dispatcher.parse_directory(tmp_path)

        assert len(docs) == 1
        assert docs[0].metadata["project"] == "サンプル株式会社"
        assert docs[0].metadata["category"] == "00.提案"
        assert docs[0].metadata["is_internal"] is False

    def test_parse_directory_marks_internal_docs(self, tmp_path: Path) -> None:
        """社内管理/ 配下のファイルは is_internal=True, project=None になる"""
        internal_dir = tmp_path / "社内管理"
        internal_dir.mkdir()
        (internal_dir / "用語集.txt").write_text("用語", encoding="utf-8")

        dispatcher = ParserDispatcher()
        docs = dispatcher.parse_directory(tmp_path)

        assert docs[0].metadata["is_internal"] is True
        assert docs[0].metadata["project"] is None

    def test_parse_directory_skips_noise_files(self, tmp_path: Path) -> None:
        """__pycache__/*.pyc, *.lock, ~$で始まる一時ファイルを除外する"""
        (tmp_path / "a.txt").write_text("残す", encoding="utf-8")
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "mod.cpython-311.pyc").write_bytes(b"stub")
        (tmp_path / "uv.lock").write_text("lock", encoding="utf-8")
        (tmp_path / "~$temp.xlsx").write_bytes(b"lock")

        dispatcher = ParserDispatcher()
        docs = dispatcher.parse_directory(tmp_path)

        texts = [d.text for d in docs]
        assert len(docs) == 1
        assert any("残す" in t for t in texts)
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_parsers.py -v -k "extracts_project_metadata or marks_internal_docs or skips_noise_files"`
Expected: 3件 FAIL（`KeyError` または `AssertionError`。`metadata` に project/category/is_internal が存在しない、またはノイズファイルが除外されず件数が合わない）

- [ ] **Step 3: dispatcher.pyを実装する**

`src/parsers/dispatcher.py` を以下に置き換える:

```python
"""ファイル拡張子に応じて適切なパーサーへ振り分ける。"""
from pathlib import Path

from src.models import Document
from src.parsers.image_parser import ImageParser
from src.parsers.office_parser import OfficeParser
from src.parsers.pdf_parser import PDFParser
from src.parsers.text_parser import TextParser

_NOISE_SUFFIXES = {".pyc", ".lock"}
_NOISE_DIR_NAMES = {"__pycache__"}


def _is_noise(file_path: Path) -> bool:
    if file_path.name.startswith("~$"):
        return True
    if file_path.suffix.lower() in _NOISE_SUFFIXES:
        return True
    if any(part in _NOISE_DIR_NAMES for part in file_path.parts):
        return True
    return False


def _extract_metadata(root: Path, file_path: Path) -> dict:
    try:
        rel_parts = file_path.relative_to(root).parts
    except ValueError:
        rel_parts = file_path.parts

    metadata: dict = {"project": None, "category": None, "is_internal": False}
    if "プロジェクト" in rel_parts:
        idx = rel_parts.index("プロジェクト")
        if idx + 1 < len(rel_parts):
            metadata["project"] = rel_parts[idx + 1]
        if idx + 2 < len(rel_parts):
            metadata["category"] = rel_parts[idx + 2]
    elif "社内管理" in rel_parts:
        metadata["is_internal"] = True
    return metadata


class ParserDispatcher:
    def __init__(self) -> None:
        self._parsers = [
            TextParser(),
            PDFParser(),
            OfficeParser(),
            ImageParser(),
        ]

    def parse(self, file_path: Path) -> list[Document]:
        for parser in self._parsers:
            if parser.can_handle(file_path):
                return parser.parse(file_path)
        return [Document(
            text=f"[未対応形式: {file_path.suffix}] {file_path.name}",
            source_path=file_path,
            location="unsupported",
        )]

    def parse_directory(self, directory: Path) -> list[Document]:
        docs: list[Document] = []
        for file_path in sorted(directory.rglob("*")):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            if _is_noise(file_path):
                continue
            file_docs = self.parse(file_path)
            metadata = _extract_metadata(directory, file_path)
            for doc in file_docs:
                doc.metadata.update(metadata)
            docs.extend(file_docs)
        return docs
```

- [ ] **Step 4: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_parsers.py -v`
Expected: 全件 PASS（既存テスト含む）

---

### Task 3: チャンク分割ユーティリティの実装とdispatcherへの統合

**Files:**
- Create: `src/parsers/chunker.py`
- Modify: `src/parsers/dispatcher.py`
- Test: `tests/test_chunker.py`

**Interfaces:**
- Produces: `chunk_documents(documents: list[Document], chunk_size: int = 800, overlap: int = 100) -> list[Document]`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_chunker.py` を新規作成:

```python
"""チャンク分割ユーティリティのテスト。"""
from __future__ import annotations

from pathlib import Path

from src.models import Document
from src.parsers.chunker import chunk_documents


def test_short_document_is_not_split(tmp_path: Path) -> None:
    doc = Document(text="短いテキスト", source_path=tmp_path / "a.txt", location="full")
    result = chunk_documents([doc])
    assert len(result) == 1
    assert result[0].text == "短いテキスト"
    assert result[0].location == "full"


def test_long_document_is_split_into_multiple_chunks(tmp_path: Path) -> None:
    long_text = "あ" * 2000
    doc = Document(text=long_text, source_path=tmp_path / "b.txt", location="full")
    result = chunk_documents([doc], chunk_size=800, overlap=100)
    assert len(result) > 1
    assert all(len(c.text) <= 800 for c in result)
    assert result[0].location == "full_chunk1"
    assert result[1].location == "full_chunk2"


def test_chunks_preserve_metadata(tmp_path: Path) -> None:
    long_text = "い" * 2000
    doc = Document(
        text=long_text,
        source_path=tmp_path / "c.txt",
        metadata={"project": "サンプル社"},
    )
    result = chunk_documents([doc], chunk_size=800, overlap=100)
    assert all(c.metadata["project"] == "サンプル社" for c in result)


def test_consecutive_chunks_overlap(tmp_path: Path) -> None:
    long_text = "0123456789" * 200  # 2000文字
    doc = Document(text=long_text, source_path=tmp_path / "d.txt")
    result = chunk_documents([doc], chunk_size=800, overlap=100)
    assert result[1].text[:100] == result[0].text[-100:]


def test_reconstructs_full_directory_via_dispatcher(tmp_path: Path) -> None:
    """dispatcher.parse_directory が長文ファイルをチャンク分割して返す"""
    from src.parsers.dispatcher import ParserDispatcher

    (tmp_path / "long.txt").write_text("う" * 2000, encoding="utf-8")
    dispatcher = ParserDispatcher()
    docs = dispatcher.parse_directory(tmp_path)
    assert len(docs) > 1
    assert all(len(d.text) <= 800 for d in docs)
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_chunker.py -v`
Expected: `ModuleNotFoundError: No module named 'src.parsers.chunker'` で全件FAIL

- [ ] **Step 3: chunker.pyを実装する**

`src/parsers/chunker.py` を新規作成:

```python
"""長文Documentを固定長・オーバーラップ付きでチャンク分割するユーティリティ。"""
from __future__ import annotations

from src.models import Document

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def chunk_documents(
    documents: list[Document],
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[Document]:
    """text が chunk_size を超える Document を overlap 分重複させながら分割する。"""
    result: list[Document] = []
    for doc in documents:
        if len(doc.text) <= chunk_size:
            result.append(doc)
            continue

        step = chunk_size - overlap
        start = 0
        chunk_index = 0
        while start < len(doc.text):
            end = start + chunk_size
            chunk_index += 1
            result.append(Document(
                text=doc.text[start:end],
                source_path=doc.source_path,
                location=f"{doc.location}_chunk{chunk_index}",
                metadata=dict(doc.metadata),
            ))
            if end >= len(doc.text):
                break
            start += step
    return result
```

- [ ] **Step 4: dispatcher.pyのparse_directoryを更新する**

`src/parsers/dispatcher.py` の先頭に `from src.parsers.chunker import chunk_documents` を追加し、`parse_directory` の `return docs` を `return chunk_documents(docs)` に変更する。

- [ ] **Step 5: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_chunker.py tests/test_parsers.py -v`
Expected: 全件 PASS

---

### Task 4: JSON/TSV/Notebook(.ipynb)のテキスト系パーサー対応

**Files:**
- Modify: `src/parsers/text_parser.py`
- Create: `src/parsers/notebook_parser.py`
- Modify: `src/parsers/dispatcher.py`
- Test: `tests/test_parsers.py`

**Interfaces:**
- Produces: `NotebookParser` は `Parser` プロトコル（`can_handle`, `parse`）を満たす

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_parsers.py` に追記（`TestTextParser` クラス内）:

```python
    def test_can_handle_json(self, tmp_path: Path) -> None:
        parser = TextParser()
        assert parser.can_handle(tmp_path / "metrics.json") is True

    def test_can_handle_tsv(self, tmp_path: Path) -> None:
        parser = TextParser()
        assert parser.can_handle(tmp_path / "data.tsv") is True
```

ファイル末尾に新規クラスを追記:

```python
# ─────────────────────── NotebookParser ───────────────────────

class TestNotebookParser:
    def test_can_handle_ipynb(self, tmp_path: Path) -> None:
        from src.parsers.notebook_parser import NotebookParser
        parser = NotebookParser()
        assert parser.can_handle(tmp_path / "01_eda.ipynb") is True

    def test_cannot_handle_txt(self, tmp_path: Path) -> None:
        from src.parsers.notebook_parser import NotebookParser
        parser = NotebookParser()
        assert parser.can_handle(tmp_path / "file.txt") is False

    def test_extracts_markdown_and_code_cell_text(self, tmp_path: Path) -> None:
        import json as jsonlib
        from src.parsers.notebook_parser import NotebookParser

        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# EDA\n", "欠損値を確認する"]},
                {"cell_type": "code", "source": ["df.isnull().sum()"]},
                {"cell_type": "code", "source": [""]},
            ]
        }
        f = tmp_path / "01_eda.ipynb"
        f.write_text(jsonlib.dumps(notebook), encoding="utf-8")

        parser = NotebookParser()
        docs = parser.parse(f)

        assert len(docs) == 2  # 空セルは除外される
        assert any("欠損値を確認する" in d.text for d in docs)
        assert any("df.isnull().sum()" in d.text for d in docs)

    def test_invalid_notebook_returns_stub(self, tmp_path: Path) -> None:
        from src.parsers.notebook_parser import NotebookParser

        f = tmp_path / "broken.ipynb"
        f.write_text("not valid json {{{", encoding="utf-8")

        parser = NotebookParser()
        docs = parser.parse(f)

        assert len(docs) == 1
        assert "解析失敗" in docs[0].text


# ─────────────────────── dispatcherへのNotebook登録 ───────────────────────

class TestDispatcherHandlesNotebook:
    def test_dispatch_ipynb_file(self, tmp_path: Path) -> None:
        import json as jsonlib
        notebook = {"cells": [{"cell_type": "markdown", "source": ["EDAメモ"]}]}
        f = tmp_path / "01_eda.ipynb"
        f.write_text(jsonlib.dumps(notebook), encoding="utf-8")

        dispatcher = ParserDispatcher()
        docs = dispatcher.parse(f)
        assert any("EDAメモ" in d.text for d in docs)
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_parsers.py -v -k "json or tsv or Notebook"`
Expected: FAIL（`can_handle`がFalseを返す／`ModuleNotFoundError`）

- [ ] **Step 3: text_parser.pyを更新する**

`src/parsers/text_parser.py` の `SUPPORTED` を変更:

```python
SUPPORTED = {".txt", ".md", ".csv", ".json", ".tsv"}
```

- [ ] **Step 4: notebook_parser.pyを実装する**

`src/parsers/notebook_parser.py` を新規作成:

```python
"""Jupyter Notebook (.ipynb) 用パーサー。Markdown/コードセルのテキストのみ抽出する。"""
from __future__ import annotations

import json
from pathlib import Path

from src.models import Document

SUPPORTED = {".ipynb"}


class NotebookParser:
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in SUPPORTED

    def parse(self, file_path: Path) -> list[Document]:
        try:
            data = json.loads(file_path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            return [Document(
                text=f"[Notebook解析失敗] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]

        docs: list[Document] = []
        for i, cell in enumerate(data.get("cells", [])):
            source = cell.get("source", "")
            text = "".join(source) if isinstance(source, list) else str(source)
            if text.strip():
                cell_type = cell.get("cell_type", "unknown")
                docs.append(Document(
                    text=text,
                    source_path=file_path,
                    location=f"cell_{i+1}_{cell_type}",
                ))
        return docs or [Document(text="", source_path=file_path, location="empty")]
```

- [ ] **Step 5: dispatcher.pyにNotebookParserを登録する**

`src/parsers/dispatcher.py` の import に `from src.parsers.notebook_parser import NotebookParser` を追加し、`self._parsers` リストの `ImageParser()` の前に `NotebookParser()` を追加する。

- [ ] **Step 6: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_parsers.py -v`
Expected: 全件 PASS

---

### Task 5: 破損・パスワード保護ファイルへの耐性

**Files:**
- Modify: `src/parsers/office_parser.py`
- Modify: `src/parsers/pdf_parser.py`
- Test: `tests/test_parsers.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_parsers.py` の `TestOfficeParser` クラスに追記:

```python
    def test_docx_parse_failure_returns_stub_not_raises(self, tmp_path: Path) -> None:
        """壊れた/パスワード保護されたdocxでも例外を投げずスタブを返す"""
        f = tmp_path / "broken.docx"
        f.write_bytes(b"not a real docx file, definitely not a valid zip")
        parser = OfficeParser()
        docs = parser.parse(f)
        assert len(docs) == 1
        assert "解析失敗" in docs[0].text

    def test_xlsx_parse_failure_returns_stub_not_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.xlsx"
        f.write_bytes(b"not a real xlsx file")
        parser = OfficeParser()
        docs = parser.parse(f)
        assert len(docs) == 1
        assert "解析失敗" in docs[0].text

    def test_pptx_parse_failure_returns_stub_not_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.pptx"
        f.write_bytes(b"not a real pptx file")
        parser = OfficeParser()
        docs = parser.parse(f)
        assert len(docs) == 1
        assert "解析失敗" in docs[0].text
```

`TestPDFParser` クラスに追記:

```python
    def test_pdf_parse_failure_returns_stub_not_raises(self, tmp_path: Path) -> None:
        """暗号化・破損したPDFでも例外を投げずスタブを返す"""
        f = tmp_path / "broken.pdf"
        f.write_bytes(b"%PDF-1.4 this is not a valid pdf structure")
        parser = PDFParser()
        docs = parser.parse(f)
        assert len(docs) == 1
        assert "解析失敗" in docs[0].text or "empty" == docs[0].location
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_parsers.py -v -k "parse_failure"`
Expected: FAIL（例外が投げられてテストがエラー終了する、または「解析失敗」の文言がない）

- [ ] **Step 3: office_parser.pyを更新する**

`src/parsers/office_parser.py` の3つの `_parse_*` メソッドを、実際のパース処理を `try/except Exception` で囲むように変更する:

```python
    def _parse_docx(self, file_path: Path) -> list[Document]:
        try:
            import docx
        except ImportError:
            return [Document(text=f"[DOCX未解析: python-docx未インストール] {file_path.name}",
                             source_path=file_path, location="stub")]
        try:
            doc = docx.Document(str(file_path))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            return [Document(
                text=f"[DOCX解析失敗: パスワード保護または破損の可能性] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]
        return [Document(text=text, source_path=file_path, location="full")]

    def _parse_xlsx(self, file_path: Path) -> list[Document]:
        try:
            import openpyxl
        except ImportError:
            return [Document(text=f"[XLSX未解析: openpyxl未インストール] {file_path.name}",
                             source_path=file_path, location="stub")]
        try:
            wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
            docs = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = []
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) if c is not None else "" for c in row]
                    if any(c.strip() for c in cells):
                        rows.append(" | ".join(cells))
                if rows:
                    docs.append(Document(
                        text="\n".join(rows),
                        source_path=file_path,
                        location=f"sheet_{sheet_name}",
                    ))
        except Exception:
            return [Document(
                text=f"[XLSX解析失敗: パスワード保護または破損の可能性] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]
        return docs or [Document(text="", source_path=file_path, location="empty")]

    def _parse_pptx(self, file_path: Path) -> list[Document]:
        try:
            from pptx import Presentation
        except ImportError:
            return [Document(text=f"[PPTX未解析: python-pptx未インストール] {file_path.name}",
                             source_path=file_path, location="stub")]
        try:
            prs = Presentation(str(file_path))
            docs = []
            for i, slide in enumerate(prs.slides):
                texts = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        texts.append(shape.text)
                if texts:
                    docs.append(Document(
                        text="\n".join(texts),
                        source_path=file_path,
                        location=f"slide_{i+1}",
                    ))
        except Exception:
            return [Document(
                text=f"[PPTX解析失敗: パスワード保護または破損の可能性] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]
        return docs or [Document(text="", source_path=file_path, location="empty")]
```

- [ ] **Step 4: pdf_parser.pyを更新する**

`src/parsers/pdf_parser.py` の `parse` メソッドを、実際のパース処理を `try/except Exception` で囲むように変更する:

```python
    def parse(self, file_path: Path) -> list[Document]:
        try:
            import pypdf  # optional dependency
        except ImportError:
            return [Document(
                text=f"[PDF未解析: pypdfが未インストール] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]

        try:
            docs: list[Document] = []
            reader = pypdf.PdfReader(str(file_path))
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    docs.append(Document(
                        text=text,
                        source_path=file_path,
                        location=f"page_{i+1}",
                    ))
        except Exception:
            return [Document(
                text=f"[PDF解析失敗: パスワード保護または破損の可能性] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]
        return docs or [Document(text="", source_path=file_path, location="empty")]
```

- [ ] **Step 5: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_parsers.py -v`
Expected: 全件 PASS

---

### Task 6: 案件フォルダ絞り込み＋BM25検索（ProjectScopedRetriever）

**Files:**
- Create: `src/retriever/project_scoped_retriever.py`
- Test: `tests/test_project_scoped_retriever.py`

**Interfaces:**
- Consumes: `KeywordStore` (`src/indexer/keyword_store.py`) の `add(documents)`, `search(query, top_k)`, `clear()`
- Produces: `ProjectScopedRetriever` クラス。`add(documents: list[Document]) -> None`, `search(query: str, top_k: int = 5) -> list[ScoredDocument]`, `clear() -> None`, `detect_project(query: str) -> str | None`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_project_scoped_retriever.py` を新規作成:

```python
"""ProjectScopedRetriever (案件フォルダ絞り込み＋BM25) のテスト。"""
from __future__ import annotations

from pathlib import Path

from src.models import Document
from src.retriever.project_scoped_retriever import (
    ProjectScopedRetriever,
    _normalize_project_name,
)


def _doc(text: str, project: str | None = None, is_internal: bool = False, path: str = "x.txt") -> Document:
    return Document(
        text=text,
        source_path=Path(path),
        metadata={"project": project, "is_internal": is_internal},
    )


class TestNormalizeProjectName:
    def test_strips_kabushiki_gaisha_prefix(self) -> None:
        assert _normalize_project_name("株式会社青潮モビリティサービス") == "青潮モビリティサービス"

    def test_strips_kabushiki_gaisha_suffix(self) -> None:
        assert _normalize_project_name("白峰信用リスク評価株式会社") == "白峰信用リスク評価"

    def test_strips_iryouhoujin_prefix(self) -> None:
        assert _normalize_project_name("医療法人社団 恒一会 かえで総合病院") == "恒一会 かえで総合病院"


class TestProjectScopedRetriever:
    def test_query_mentioning_project_is_scoped_to_that_project(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [
            _doc("青潮モビリティサービスの需要予測結果です。", project="株式会社青潮モビリティサービス"),
            _doc("かえで総合病院の患者数データです。", project="医療法人社団 恒一会 かえで総合病院"),
        ]
        retriever.add(docs)

        results = retriever.search("青潮モビリティサービスの需要予測について教えてください", top_k=5)

        assert len(results) == 1
        assert "青潮モビリティサービス" in results[0].document.text

    def test_internal_docs_are_always_included_in_project_scope(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [
            _doc("青潮モビリティサービスの需要予測結果です。", project="株式会社青潮モビリティサービス"),
            _doc("社内用語集: TGは目的変数の略。", is_internal=True),
        ]
        retriever.add(docs)

        results = retriever.search("青潮モビリティサービスのTGについて教えてください", top_k=5)

        texts = [r.document.text for r in results]
        assert any("社内用語集" in t for t in texts)

    def test_query_without_known_project_falls_back_to_global_search(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [
            _doc("青潮モビリティサービスの需要予測結果です。", project="株式会社青潮モビリティサービス"),
            _doc("かえで総合病院の患者数データです。", project="医療法人社団 恒一会 かえで総合病院"),
        ]
        retriever.add(docs)

        results = retriever.search("患者数データについて教えてください", top_k=5)

        assert any("かえで総合病院" in r.document.text for r in results)

    def test_detect_project_returns_none_when_no_match(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [_doc("テキスト", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)

        assert retriever.detect_project("無関係な質問です") is None

    def test_detect_project_returns_matching_project_name(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [_doc("テキスト", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)

        assert retriever.detect_project("青潮モビリティサービスについて") == "株式会社青潮モビリティサービス"

    def test_clear_resets_all_stores(self) -> None:
        retriever = ProjectScopedRetriever()
        docs = [_doc("テキスト", project="株式会社青潮モビリティサービス")]
        retriever.add(docs)
        retriever.clear()

        assert retriever.detect_project("青潮モビリティサービス") is None
        assert retriever.search("青潮モビリティサービス", top_k=5) == []
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_project_scoped_retriever.py -v`
Expected: `ModuleNotFoundError: No module named 'src.retriever.project_scoped_retriever'` で全件FAIL

- [ ] **Step 3: project_scoped_retriever.pyを実装する**

`src/retriever/project_scoped_retriever.py` を新規作成:

```python
"""案件フォルダ絞り込み＋BM25検索を行うRetriever。

質問文から案件名を検出できた場合はその案件＋社内管理配下のみを対象にBM25検索し、
検出できない場合は全体（社内管理含む）を対象に検索する。
案件名リストはadd()時にDocument.metadata["project"]から動的に導出する（ハードコードしない）。
"""
from __future__ import annotations

from src.indexer.keyword_store import KeywordStore
from src.models import Document, ScoredDocument

_CORPORATE_AFFIXES = ("株式会社", "医療法人社団", "有限会社", "合同会社")


def _normalize_project_name(name: str) -> str:
    result = name
    for affix in _CORPORATE_AFFIXES:
        result = result.replace(affix, "")
    return result.strip()


class ProjectScopedRetriever:
    """
    add() は全ドキュメントを1回でまとめて渡す想定（Pipeline.build_indexの使い方と一致）。
    """

    def __init__(self) -> None:
        self._global_store = KeywordStore()
        self._project_stores: dict[str, KeywordStore] = {}
        self._project_names: list[str] = []

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
                self._project_stores[project] = KeywordStore()
                self._project_names.append(project)
            self._project_stores[project].add(docs)
            if internal_docs:
                self._project_stores[project].add(internal_docs)

    def clear(self) -> None:
        self._global_store.clear()
        self._project_stores = {}
        self._project_names = []

    def detect_project(self, query: str) -> str | None:
        for name in self._project_names:
            normalized = _normalize_project_name(name)
            if normalized and normalized in query:
                return name
        return None

    def search(self, query: str, top_k: int = 5) -> list[ScoredDocument]:
        project = self.detect_project(query)
        if project is not None:
            return self._project_stores[project].search(query, top_k)
        return self._global_store.search(query, top_k)
```

- [ ] **Step 4: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_project_scoped_retriever.py -v`
Expected: 全件 PASS

---

### Task 7: PipelineをProjectScopedRetrieverに接続

**Files:**
- Modify: `src/orchestrator/pipeline.py`
- Modify: `.claude/skills/architecture.md`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pipeline.py` に追記:

```python
def test_pipeline_uses_project_scoped_retriever(tmp_path: Path) -> None:
    """PipelineはHybridRetrieverではなくProjectScopedRetrieverを使う（ベースライン方針）。"""
    from src.orchestrator.pipeline import Pipeline
    from src.retriever.project_scoped_retriever import ProjectScopedRetriever

    pipeline = Pipeline(data_dir=tmp_path)
    assert isinstance(pipeline.retriever, ProjectScopedRetriever)
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_pipeline.py -v -k project_scoped`
Expected: `AssertionError`（`pipeline.retriever` が `HybridRetriever` のインスタンスのため）

- [ ] **Step 3: pipeline.pyを更新する**

`src/orchestrator/pipeline.py` の import を変更:
```python
from src.retriever.hybrid_retriever import HybridRetriever
```
を
```python
from src.retriever.project_scoped_retriever import ProjectScopedRetriever
```
に置き換え、`__init__` 内の `self.retriever = HybridRetriever()` を `self.retriever = ProjectScopedRetriever()` に変更する。

- [ ] **Step 4: architecture.mdを更新する**

`.claude/skills/architecture.md` のコンポーネント表の Retriever 行を更新:

```
| Retriever | `src/retriever/project_scoped_retriever.py` | 質問文から案件名検出→案件フォルダ絞り込み＋BM25（未検出時は全体BM25にフォールバック） |
```

パイプライン図も `HybridRetriever(Vector+Keyword)` から `ProjectScopedRetriever(BM25)` に更新する。

- [ ] **Step 5: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 全件 PASS

---

### Task 8: AnswerGenerator._call_llmをClaude API接続に差し替え

**Files:**
- Modify: `src/generator/answer_generator.py`
- Modify: `.env`, `.env.example`
- Test: `tests/test_generator.py`

**Interfaces:**
- Produces: `AnswerGenerator._call_llm(question: str, context: str) -> str` は実際にAnthropic APIを呼び出す（`ANTHROPIC_API_KEY`, `CLAUDE_MODEL` 環境変数を使用）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_generator.py` 冒頭のimportに `from unittest.mock import patch` を追加し、ファイル末尾に追記:

```python
# ---------------------------------------------------------------------------
# AnswerGenerator._call_llm  ―  実際のAnthropic API接続（モックで検証）
# ---------------------------------------------------------------------------


class TestCallLLMRealIntegration:
    def test_call_llm_sends_system_prompt_and_returns_text(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5")

        gen = AnswerGenerator()

        fake_content = type("C", (), {"text": '{"answer": "テスト回答", "confidence": 0.9, "reasoning": "r"}'})()
        fake_response = type("R", (), {"content": [fake_content]})()

        with patch("src.generator.answer_generator.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            raw = gen._call_llm("質問文です", "文脈です")

        assert raw == '{"answer": "テスト回答", "confidence": 0.9, "reasoning": "r"}'
        _, kwargs = MockAnthropic.return_value.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
        assert kwargs["temperature"] == 0.0
        assert kwargs["system"] == SYSTEM_PROMPT
        assert "質問文です" in kwargs["messages"][0]["content"]
        assert "文脈です" in kwargs["messages"][0]["content"]

    def test_call_llm_defaults_to_claude_sonnet_5_when_env_unset(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("CLAUDE_MODEL", raising=False)

        gen = AnswerGenerator()
        fake_content = type("C", (), {"text": "{}"})()
        fake_response = type("R", (), {"content": [fake_content]})()

        with patch("src.generator.answer_generator.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            gen._call_llm("質問", "文脈")

        _, kwargs = MockAnthropic.return_value.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
```

`from src.generator.answer_generator import AnswerGenerator, MAX_CHARS_APPROX` の行を `from src.generator.answer_generator import AnswerGenerator, MAX_CHARS_APPROX, SYSTEM_PROMPT` に変更する。

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_generator.py -v -k RealIntegration`
Expected: `ModuleNotFoundError` または `AttributeError`（`Anthropic` が `answer_generator` モジュールにまだ存在しない／スタブがハードコード文字列を返すため）

- [ ] **Step 3: answer_generator.pyを更新する**

`src/generator/answer_generator.py` の先頭のimportを変更:

```python
"""回答生成。_call_llm() はAnthropic APIを呼び出す。"""
from __future__ import annotations

import os

from anthropic import Anthropic

from src.generator.confidence_gate import ConfidenceGate
from src.models import Answer, ScoredDocument
```

`AnswerGenerator` クラスを変更:

```python
class AnswerGenerator:
    def __init__(self, threshold: float = 0.4) -> None:
        self.gate = ConfidenceGate(threshold=threshold)
        self._client: Anthropic | None = None

    def generate(self, question: str, contexts: list[ScoredDocument]) -> Answer:
        # (変更なし、既存のまま)
        ...

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _call_llm(self, question: str, context: str) -> str:
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
        message = self._get_client().messages.create(
            model=model,
            max_tokens=1500,
            temperature=0.0,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"【質問】\n{question}\n\n【参考文書】\n{context}",
            }],
        )
        return message.content[0].text
```

（`generate` メソッドの中身自体は変更しない。`_parse_response` も変更しない。）

- [ ] **Step 4: .env / .env.exampleのモデルデフォルトを更新する**

`.env` と `.env.example` の以下2行を:
```
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_JUDGE_MODEL=claude-sonnet-4-6
```
に変更:
```
CLAUDE_MODEL=claude-sonnet-5
CLAUDE_JUDGE_MODEL=claude-sonnet-5
```

- [ ] **Step 5: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_generator.py -v`
Expected: 全件 PASS（`FakeGenerator` を使う既存テストは `_call_llm` をオーバーライドしているため影響を受けない）

---

### Task 9: LocalJudge._call_llmをClaude API接続に差し替え

**Files:**
- Modify: `src/evaluator/judge.py`
- Test: `tests/test_judge.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_judge.py` の import に `from unittest.mock import patch` を追加し、ファイル末尾に追記:

```python
# ---------------------------------------------------------------------------
# LocalJudge._call_llm  ―  実際のAnthropic API接続（モックで検証）
# ---------------------------------------------------------------------------


class TestJudgeCallLLMRealIntegration:
    def test_call_llm_sends_prompt_and_returns_text(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CLAUDE_JUDGE_MODEL", "claude-sonnet-5")

        judge = LocalJudge()
        fake_content = type("C", (), {"text": '{"label": "Perfect", "reason": "正確"}'})()
        fake_response = type("R", (), {"content": [fake_content]})()

        with patch("src.evaluator.judge.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            raw = judge._call_llm("この回答を評価してください")

        assert raw == '{"label": "Perfect", "reason": "正確"}'
        _, kwargs = MockAnthropic.return_value.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
        assert kwargs["temperature"] == 0.0
        assert kwargs["messages"][0]["content"] == "この回答を評価してください"

    def test_call_llm_defaults_to_claude_sonnet_5_when_env_unset(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("CLAUDE_JUDGE_MODEL", raising=False)

        judge = LocalJudge()
        fake_content = type("C", (), {"text": "{}"})()
        fake_response = type("R", (), {"content": [fake_content]})()

        with patch("src.evaluator.judge.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            judge._call_llm("プロンプト")

        _, kwargs = MockAnthropic.return_value.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_judge.py -v -k RealIntegration`
Expected: `ModuleNotFoundError` または `AttributeError`

- [ ] **Step 3: judge.pyを更新する**

`src/evaluator/judge.py` の先頭のimportを変更:

```python
"""CRAG基準ローカルジャッジ。_call_llm() はAnthropic APIを呼び出す。"""
from __future__ import annotations

import json
import os
import re

from anthropic import Anthropic

from src.models import CRAGLabel, JudgeResult
```

`LocalJudge` クラスを変更:

```python
class LocalJudge:
    def __init__(self) -> None:
        self._client: Anthropic | None = None

    def score(
        self,
        question: str,
        generated_answer: str,
        reference_or_context: str,
    ) -> JudgeResult:
        # (変更なし、既存のまま)
        ...

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _call_llm(self, prompt: str) -> str:
        model = os.environ.get("CLAUDE_JUDGE_MODEL", "claude-sonnet-5")
        message = self._get_client().messages.create(
            model=model,
            max_tokens=300,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def _parse(self, raw: str) -> JudgeResult:
        # (変更なし、既存のまま)
        ...
```

- [ ] **Step 4: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_judge.py -v`
Expected: 全件 PASS（`FakeJudge` を使う既存テストは `_call_llm` をオーバーライドしているため影響を受けない）

---

### Task 10: CSV形式の質問ファイル読み込み・Judgeスキップ・predictions.csv生成

**Files:**
- Create: `src/utils/question_loader.py`
- Modify: `src/orchestrator/pipeline.py`
- Modify: `scripts/run_pipeline.py`
- Create: `scripts/make_predictions.py`
- Test: `tests/test_question_loader.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `load_questions_csv(path: Path) -> list[QAPair]`
- Modifies: `Pipeline.__init__(..., run_judge: bool = True)`

- [ ] **Step 1: 失敗するテストを書く（question_loader）**

`tests/test_question_loader.py` を新規作成:

```python
"""CSV形式の質問ファイル読み込みのテスト。"""
from __future__ import annotations

from pathlib import Path

from src.utils.question_loader import load_questions_csv


def test_loads_questions_with_answer_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "questions_valid.csv"
    csv_path.write_text(
        "index,question,answer\n0,質問A,回答A\n1,質問B,回答B\n",
        encoding="utf-8-sig",
    )
    pairs = load_questions_csv(csv_path)
    assert len(pairs) == 2
    assert pairs[0].question_id == "0"
    assert pairs[0].question == "質問A"
    assert pairs[0].reference_answer == "回答A"


def test_loads_questions_without_answer_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "questions_test.csv"
    csv_path.write_text("index,question\n0,質問A\n1,質問B\n", encoding="utf-8-sig")
    pairs = load_questions_csv(csv_path)
    assert len(pairs) == 2
    assert pairs[0].reference_answer == ""


def test_handles_bom_in_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "q.csv"
    csv_path.write_bytes("﻿index,question\n0,質問A\n".encode("utf-8"))
    pairs = load_questions_csv(csv_path)
    assert pairs[0].question_id == "0"
    assert pairs[0].question == "質問A"
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_question_loader.py -v`
Expected: `ModuleNotFoundError: No module named 'src.utils.question_loader'`

- [ ] **Step 3: question_loader.pyを実装する**

`src/utils/question_loader.py` を新規作成:

```python
"""questions_valid.csv / questions_test.csv 形式のCSVを読み込むローダー。"""
from __future__ import annotations

import csv
from pathlib import Path

from src.orchestrator.pipeline import QAPair


def load_questions_csv(path: Path) -> list[QAPair]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [
            QAPair(
                question_id=row["index"],
                question=row["question"],
                reference_answer=row.get("answer") or "",
            )
            for row in reader
        ]
```

- [ ] **Step 4: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_question_loader.py -v`
Expected: 全件 PASS

- [ ] **Step 5: 失敗するテストを書く（Pipelineのrun_judgeフラグ）**

`tests/test_pipeline.py` に追記:

```python
def test_pipeline_skips_judge_when_run_judge_false(tmp_path: Path) -> None:
    """run_judge=False のとき judge_label は空文字で、Judge._call_llmは呼ばれない"""
    from unittest.mock import MagicMock
    from src.orchestrator.pipeline import Pipeline, QAPair

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False)
    pipeline.judge._call_llm = MagicMock(return_value='{"label": "Perfect", "reason": "r"}')
    pipeline.generator._call_llm = lambda q, c: '{"answer": "回答", "confidence": 0.9, "reasoning": "r"}'

    (tmp_path / "a.txt").write_text("参考テキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(question_id="0", question="質問"))

    assert result.judge_label == ""
    pipeline.judge._call_llm.assert_not_called()
```

- [ ] **Step 6: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_pipeline.py -v -k skips_judge`
Expected: `TypeError: __init__() got an unexpected keyword argument 'run_judge'`

- [ ] **Step 7: pipeline.pyにrun_judgeフラグを実装する**

`src/orchestrator/pipeline.py` の `Pipeline.__init__` シグネチャに `run_judge: bool = True` を追加し、`self.run_judge = run_judge` を保存する。`_process_one` を以下に変更:

```python
    def _process_one(self, qa: QAPair) -> PipelineResult:
        contexts = self.retriever.search(qa.question, top_k=self.top_k)
        answer: Answer = self.generator.generate(qa.question, contexts)

        if self.run_judge:
            reference = qa.reference_answer or "\n".join(
                sd.document.text[:300] for sd in contexts
            )
            judge_result: JudgeResult = self.judge.score(
                question=qa.question,
                generated_answer=answer.text,
                reference_or_context=reference,
            )
            judge_label = judge_result.label.value
            judge_score = judge_result.score
            judge_reason = judge_result.reason
        else:
            judge_label, judge_score, judge_reason = "", 0.0, ""

        return PipelineResult(
            question_id=qa.question_id,
            question=qa.question,
            answer=answer.text,
            confidence=answer.confidence,
            was_gated=answer.was_gated,
            judge_label=judge_label,
            judge_score=judge_score,
            judge_reason=judge_reason,
        )
```

- [ ] **Step 8: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 全件 PASS

- [ ] **Step 9: run_pipeline.pyにCSV対応を追加する**

`scripts/run_pipeline.py` の `main()` 内、質問ファイル読み込み部分を変更:

```python
    if args.questions.suffix.lower() == ".csv":
        from src.utils.question_loader import load_questions_csv
        qa_pairs = load_questions_csv(args.questions)
    else:
        qa_raw = json.loads(args.questions.read_text(encoding="utf-8"))
        qa_pairs = [
            QAPair(
                question_id=item["id"],
                question=item["question"],
                reference_answer=item.get("answer", ""),
            )
            for item in qa_raw
        ]
```

- [ ] **Step 10: make_predictions.pyを作成する**

`scripts/make_predictions.py` を新規作成:

```python
"""パイプライン結果からSIGNATE提出用のpredictions.csv（ヘッダーなし, index,answer）を生成する。"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.orchestrator.pipeline import Pipeline
from src.utils.question_loader import load_questions_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="predictions.csv 生成")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "predictions.csv")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--concurrent", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.4)
    args = parser.parse_args()

    qa_pairs = load_questions_csv(args.questions)

    pipeline = Pipeline(
        data_dir=args.data_dir,
        max_concurrent=args.concurrent,
        top_k=args.top_k,
        confidence_threshold=args.threshold,
        run_judge=False,
    )
    pipeline.build_index()
    results = pipeline.run(qa_pairs)

    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for r in sorted(results, key=lambda r: int(r.question_id)):
            writer.writerow([r.question_id, r.answer])

    print(f"書き出し完了: {args.out} ({len(results)}件)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 11: 全テストを再実行し、回帰がないことを確認する**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全件 PASS（Task 1〜10で追加した分すべて含む）

---

### Task 11: questions_valid.csvの設問分類・理論上限スコア見積もりスクリプト

**Files:**
- Create: `src/utils/question_classifier.py`
- Create: `scripts/classify_questions.py`
- Test: `tests/test_question_classifier.py`

**Interfaces:**
- Produces: `classify_question(question: str) -> list[str]`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_question_classifier.py` を新規作成:

```python
"""質問文の要求能力タグ分類のテスト。"""
from __future__ import annotations

from src.utils.question_classifier import classify_question


def test_detects_image_or_graph_question() -> None:
    q = "figure_06.pngにおいて、dayによる件数推移を教えてください。"
    assert "image_or_graph" in classify_question(q)


def test_detects_version_diff_question() -> None:
    q = "提案書old.pptxから提案書.pptxへの更新内容のうち、実質的な変更を挙げてください。"
    assert "version_diff" in classify_question(q)


def test_detects_password_protected_question() -> None:
    q = "契約書のパスワードを教えてください。"
    assert "password_protected" in classify_question(q)


def test_detects_multi_hop_question() -> None:
    q = "すべての案件のうち、契約金額が最大のものはどれですか。"
    assert "multi_hop" in classify_question(q)


def test_plain_question_is_text_only() -> None:
    q = "宿泊費の上限はいくらですか。"
    assert classify_question(q) == ["text_only"]


def test_question_can_have_multiple_tags() -> None:
    q = "old版のfigure_06.pngとの差分を教えてください。"
    tags = classify_question(q)
    assert "image_or_graph" in tags
    assert "version_diff" in tags
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/bin/pytest tests/test_question_classifier.py -v`
Expected: `ModuleNotFoundError: No module named 'src.utils.question_classifier'`

- [ ] **Step 3: question_classifier.pyを実装する**

`src/utils/question_classifier.py` を新規作成:

```python
"""質問文を要求能力タグに分類するヒューリスティック。ベースラインの理論上限スコア見積もりに使う。"""
from __future__ import annotations

IMAGE_KEYWORDS = (".png", ".jpg", "画像", "グラフ", "figure", "マーカー", "折れ線", "図")
VERSION_DIFF_KEYWORDS = ("old", "旧版", "新旧", "更新内容", "実質的な変更", "最新版")
PASSWORD_KEYWORDS = ("パスワード", "password", "保護されたファイル")
MULTI_HOP_KEYWORDS = ("すべての案件", "各案件", "複数の案件", "全案件")


def classify_question(question: str) -> list[str]:
    tags: list[str] = []
    lower = question.lower()
    if any(k.lower() in lower for k in IMAGE_KEYWORDS):
        tags.append("image_or_graph")
    if any(k in question for k in VERSION_DIFF_KEYWORDS):
        tags.append("version_diff")
    if any(k.lower() in lower for k in PASSWORD_KEYWORDS):
        tags.append("password_protected")
    if any(k in question for k in MULTI_HOP_KEYWORDS):
        tags.append("multi_hop")
    if not tags:
        tags.append("text_only")
    return tags
```

- [ ] **Step 4: テストを再実行し、通過を確認する**

Run: `.venv/bin/pytest tests/test_question_classifier.py -v`
Expected: 全件 PASS

- [ ] **Step 5: classify_questions.pyを作成する**

`scripts/classify_questions.py` を新規作成:

```python
"""questions_valid.csv の設問をタグ分類し、ベースラインの理論上限スコアを見積もる。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.question_classifier import classify_question
from src.utils.question_loader import load_questions_csv

# ベースライン（テキストのみ）が原理的に正答できないタグ
UNSUPPORTED_TAGS = {"image_or_graph", "version_diff", "password_protected"}


def main() -> None:
    questions_path = ROOT / "data" / "raw" / "share" / "質問回答" / "questions_valid.csv"
    qa_pairs = load_questions_csv(questions_path)

    tag_counts: dict[str, int] = {}
    supportable = 0
    for qa in qa_pairs:
        tags = classify_question(qa.question)
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
        if not (set(tags) & UNSUPPORTED_TAGS):
            supportable += 1

    total = len(qa_pairs)
    print(f"設問総数: {total}")
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {tag}: {count} ({100*count/total:.1f}%)")

    best_case_mean = supportable / total
    print(f"\nベースライン(テキストのみ)で対応可能と推定: {supportable}/{total}")
    print(f"理論上限スコア（対応可能分が全てPerfectと仮定）: {best_case_mean:.3f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 実行して結果を確認する**

Run: `.venv/bin/python scripts/classify_questions.py`
Expected: 設問総数・タグ別内訳・理論上限スコアが出力される（例外なく完了すること）

---

### Task 12（運用手順・ANTHROPIC_API_KEY必須）: questions_valid.csvでE2E実行

このタスクは実際のClaude APIを呼び出す（30問 × 生成+ジャッジ = 最大60コール）。**実行前に `.env` の `ANTHROPIC_API_KEY` を実キーに置き換えること。** 実キー未設定のままではコスト・時間がかからないため、ユーザーの承認を得てから進める。

- [ ] **Step 1: .envに実キーを設定する（ユーザー作業）**

`.env` の `ANTHROPIC_API_KEY=sk-ant-...` を実際のAPIキーに置き換える。

- [ ] **Step 2: 実データでE2E実行する**

Run:
```bash
.venv/bin/python scripts/run_pipeline.py \
  --data-dir "data/raw/share/共有ドライブ" \
  --questions "data/raw/share/質問回答/questions_valid.csv" \
  --run-name baseline_valid
```
Expected: 例外なく完了し、`experiments/baseline_valid_<timestamp>.json` が生成される。実行時間をログから記録する（3時間制限に対する余裕の判断材料）。

- [ ] **Step 3: スコアを集計する**

Run: `.venv/bin/python scripts/run_eval.py`
Expected: `mean_score` と `Perfect/Acceptable/Missing/Incorrect` の内訳が出力される

- [ ] **Step 4: 画像・パスワード系設問がIncorrectでなくMissingになっていることを確認する**

`scripts/classify_questions.py` の分類結果と `experiments/baseline_valid_*.json` の `judge_label` を突き合わせ、`image_or_graph`/`version_diff`/`password_protected` タグの設問が `Missing`（0点）になっており `Incorrect`（-1点）になっていないことを確認する。もし `Incorrect` になっている設問があれば、確信度ゲートの閾値（`confidence_threshold`、既定0.4）が緩すぎる可能性があるため、`docs/todo_and_experiments.md` の実験バックログ「confidence_thresholdのチューニング」に記録する。

---

### Task 13（運用手順・ANTHROPIC_API_KEY必須）: questions_test.csvでpredictions.csv生成

- [ ] **Step 1: 本番用predictions.csvを生成する**

Run:
```bash
.venv/bin/python scripts/make_predictions.py \
  --data-dir "data/raw/share/共有ドライブ" \
  --questions "data/raw/share/質問回答/questions_test.csv" \
  --out predictions.csv
```
Expected: `predictions.csv` が100行（ヘッダーなし、`index,answer`）で生成される。実行時間を記録する。

- [ ] **Step 2: evaluation/crag.pyでフォーマット検証する**

`predictions.csv` を `evaluation/submit/predictions.csv` にコピーし、以下を実行:
```bash
cp predictions.csv evaluation/submit/predictions.csv
cd evaluation && OPENAI_API_KEY=<設定済みなら> python crag.py --ans-txt valid_txt.csv
```
（本番の `questions_test.csv` には正解がないため、フォーマットチェック=Validationフェーズが通ることのみを確認する。スコア自体は模範解答がある `valid_txt.csv` 相当でのみ意味を持つ）
Expected: `Validation: ... Done` のログが出て、拡張子・カラム数・サンプル数・欠損・データ型・トークン数のチェックがすべて通る

- [ ] **Step 3: 提出するかどうかをユーザーに確認する**

`predictions.csv` をzip圧縮してSIGNATEに提出するかどうかは、スコアの見通しがついてからユーザーが判断する（`docs/todo_and_experiments.md` のTODO 11、`docs/submission.md` 参照）。このタスクでは自動提出は行わない。

---

## Self-Review メモ

- **仕様カバレッジ**: `docs/todo_and_experiments.md` のTODO 1〜10すべてにTaskが対応（1→Task2, 2→Task4/5, 3→Task4(json/tsv)+Task3(chunk方針), 4→Task1/6, 5→Task6, 6→Task8, 7→Task9, 8→Task11, 9→Task12, 10→Task13）。TODO 11（提出）はTask13 Step3で「自動実行しない」ことを明記
- **プレースホルダ**: なし。全ステップに実コードまたは実コマンドを記載
- **型/シグネチャの一貫性**: `QAPair`, `PipelineResult`, `Document`, `ScoredDocument` は既存定義のまま変更していないため後方互換。`Pipeline.__init__` に `run_judge` を追加した点のみ既存呼び出し元（`scripts/run_pipeline.py`）に影響しないことを確認済み（デフォルト値`True`）
