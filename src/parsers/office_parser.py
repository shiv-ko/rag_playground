"""Word/Excel/PowerPoint パーサー。各ライブラリが未インストールならスタブを返す。"""
import logging
from pathlib import Path

from src.models import Document

logger = logging.getLogger(__name__)

SUPPORTED = {".docx", ".xlsx", ".pptx"}


class OfficeParser:
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in SUPPORTED

    def parse(self, file_path: Path) -> list[Document]:
        suffix = file_path.suffix.lower()
        if suffix == ".docx":
            return self._parse_docx(file_path)
        if suffix == ".xlsx":
            return self._parse_xlsx(file_path)
        if suffix == ".pptx":
            return self._parse_pptx(file_path)
        return []

    def _parse_docx(self, file_path: Path) -> list[Document]:
        try:
            import docx
        except ImportError:
            return [Document(text=f"[DOCX未解析: python-docx未インストール] {file_path.name}",
                             source_path=file_path, location="stub")]
        try:
            from docx.table import Table
            from docx.text.paragraph import Paragraph

            doc = docx.Document(str(file_path))
            texts: list[str] = []
            # iter_inner_content()は本文中の段落/表の出現順（body順）をそのまま
            # 返す公開API。生XML要素を手動でqn判定・再構築する必要がない。
            for item in doc.iter_inner_content():
                try:
                    if isinstance(item, Table):
                        texts.extend(self._extract_docx_table_rows(item, file_path))
                    elif isinstance(item, Paragraph):
                        if item.text.strip():
                            texts.append(item.text)
                except Exception:
                    # 個別の段落/表の解釈に失敗しても文書全体は読み進める
                    logger.warning(
                        "docx本文要素(段落/表)の抽出に失敗しスキップ: %s", file_path,
                        exc_info=True,
                    )
                    continue
            text = "\n".join(texts)
        except Exception:
            logger.warning("docx全体の解析に失敗: %s", file_path, exc_info=True)
            return [Document(
                text=f"[DOCX解析失敗: パスワード保護または破損の可能性] {file_path.name}",
                source_path=file_path,
                location="stub",
            )]
        return [Document(text=text, source_path=file_path, location="full")]

    def _extract_docx_table_rows(self, table, file_path: Path) -> list[str]:
        """Word表を行ごとに ' | ' 結合した文字列のリストへ変換する。

        結合セル・空セル・ネストした表があっても例外を出さないよう、各要素の
        アクセスを個別に防御し、セルの中身は常に文字列化して扱う。

        python-docxの`row.cells`は結合セルを実XML要素(tc)の同一性ではなく
        グリッド位置ベースで返すため、横結合(gridSpan)はスパン列数分、
        縦結合(vMerge)は継続行の分だけ同一tc要素を複数回yieldする。
        そのまま連結すると同じ内容が重複するため、tc要素で表単位にデデュープ
        する（表ごとに独立したスコープ。ネスト表は別スコープ）。

        注意: `id(cell._tc)`のようにint化して集合に入れてはいけない。
        lxmlのElementプロキシは短命な使い捨てオブジェクトとして再生成される
        ことがあり、参照を保持しないとGC直後にCPythonのアロケータが同じ
        メモリアドレスを別の（無関係な）オブジェクトに再利用するため、
        全く別のセル同士がid衝突で誤って「重複」判定されてしまう
        （実データの社内用語集.docxで実証: 123セル中119セルが誤って重複扱い
        されデータの大半が消失した）。そのためtc要素オブジェクト自体を
        集合に保持し、GCによるアドレス再利用を防ぐ。
        """
        rows_text: list[str] = []
        seen_tcs: set = set()
        try:
            rows = table.rows
        except Exception:
            logger.warning("docx表の行取得に失敗しスキップ: %s", file_path, exc_info=True)
            return rows_text
        for row in rows:
            try:
                row_cells = row.cells
            except Exception:
                logger.warning(
                    "docx表の行のセル取得に失敗しスキップ: %s", file_path, exc_info=True
                )
                continue
            cell_parts: list[str] = []
            nested_parts: list[str] = []
            for cell in row_cells:
                try:
                    tc = cell._tc  # noqa: SLF001 - 結合セルの同一性判定に必要
                except Exception:
                    tc = None
                if tc is not None:
                    if tc in seen_tcs:
                        # 横結合/縦結合による同一tc要素の重複yieldをスキップ
                        continue
                    seen_tcs.add(tc)
                try:
                    cell_text = " ".join(str(cell.text).split())
                except Exception:
                    logger.warning(
                        "docx表セルのテキスト取得に失敗しスキップ: %s", file_path,
                        exc_info=True,
                    )
                    cell_text = ""
                if cell_text:
                    cell_parts.append(cell_text)
                try:
                    nested_tables = cell.tables
                except Exception:
                    logger.warning(
                        "docx表セルのネスト表取得に失敗しスキップ: %s", file_path,
                        exc_info=True,
                    )
                    nested_tables = []
                for nested in nested_tables:
                    nested_parts.extend(self._extract_docx_table_rows(nested, file_path))
            if cell_parts:
                rows_text.append(" | ".join(cell_parts))
            rows_text.extend(nested_parts)
        return rows_text

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
                    if getattr(shape, "has_table", False):
                        for row in shape.table.rows:
                            # cell.textは複数段落/ソフト改行で\n・\vを含みうるため空白に正規化する
                            cells = [
                                " ".join(cell.text.split())
                                for cell in row.cells
                                if cell.text.strip()
                            ]
                            if cells:
                                texts.append(" | ".join(cells))
                        continue
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
