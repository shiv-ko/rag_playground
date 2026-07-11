"""xlsx/docx/pptxのネイティブ埋め込みチャート(OOXML)からの機械抽出。VLMを使わない。"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

_CX_NS = {
    "cx": "http://schemas.microsoft.com/office/drawing/2014/chartex",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def extract_xlsx_chart_series(xlsx_path: Path) -> dict[str, str]:
    """xlsx埋め込みの拡張チャート(chartEx)から {チャートタイトル: 系列名} を返す。

    タイトル・系列名のどちらかが機械抽出できないチャートは結果に含めない（安全側フォールバック）。
    """
    result: dict[str, str] = {}
    with zipfile.ZipFile(xlsx_path) as zf:
        chart_names = sorted(
            n for n in zf.namelist()
            if re.fullmatch(r"xl/charts/chartEx\d+\.xml", n)
        )
        for name in chart_names:
            root = ET.fromstring(zf.read(name))
            title_runs = root.findall(".//cx:title//a:t", _CX_NS)
            title = "".join(t.text or "" for t in title_runs).strip()
            series_v = root.find(".//cx:series/cx:tx/cx:txData/cx:v", _CX_NS)
            if title and series_v is not None and series_v.text:
                result[title] = series_v.text.strip()
    return result
