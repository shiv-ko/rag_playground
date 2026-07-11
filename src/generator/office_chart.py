"""xlsx/docx/pptxのネイティブ埋め込みチャート(OOXML)からの機械抽出。VLMを使わない。"""
from __future__ import annotations

import colorsys
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

_CX_NS = {
    "cx": "http://schemas.microsoft.com/office/drawing/2014/chartex",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}

_THEME_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
_ACCENT_KEYS = ("accent1", "accent2", "accent3", "accent4", "accent5", "accent6")


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


def resolve_theme_accent_colors(theme_xml_bytes: bytes) -> dict[str, str]:
    """テーマXMLから {'accent1': '156082', ...} のRGB16進(先頭#無し)を返す。"""
    root = ET.fromstring(theme_xml_bytes)
    scheme = root.find(".//a:clrScheme", _THEME_NS)
    result: dict[str, str] = {}
    if scheme is None:
        return result
    for key in _ACCENT_KEYS:
        el = scheme.find(f"a:{key}/a:srgbClr", _THEME_NS)
        if el is not None:
            val = el.get("val")
            if val:
                result[key] = val
    return result


def classify_color_name(hex_rgb: str) -> str:
    """RGB16進文字列(6桁)を基本色名(blue/orange/red/green/yellow/purple/gray)に分類する。

    HSV色相での単純な角度分類。案件・ファイル固有の分岐ではなく、質問文の色語彙
    （青/赤/オレンジ等）とチャート系列の描画色を一般的に対応付けるための分類器。
    """
    r = int(hex_rgb[0:2], 16) / 255
    g = int(hex_rgb[2:4], 16) / 255
    b = int(hex_rgb[4:6], 16) / 255
    h, s, _v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.15:
        return "gray"
    deg = h * 360
    if deg < 15 or deg >= 345:
        return "red"
    if deg < 45:
        return "orange"
    if deg < 70:
        return "yellow"
    if deg < 170:
        return "green"
    if deg < 255:
        return "blue"
    if deg < 320:
        return "purple"
    return "red"


@dataclass
class ChartSeries:
    name: str
    color_name: str | None
    points: list[float] = field(default_factory=list)


_C_NS = {
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def extract_office_chart_series(office_file_path: Path) -> dict[str, list[ChartSeries]]:
    """docx/pptx埋め込みの標準チャート(c:chart)から {チャートタイトル: [系列, ...]} を返す。

    系列の描画色は同一zip内のtheme1.xmlのaccent配色から解決する
    （解決できない場合はcolor_name=Noneとし、呼び出し側が単一系列時のみ許容する）。
    """
    result: dict[str, list[ChartSeries]] = {}
    with zipfile.ZipFile(office_file_path) as zf:
        names = zf.namelist()
        is_docx = any(n.startswith("word/") for n in names)
        chart_prefix = "word/charts/" if is_docx else "ppt/charts/"
        theme_prefix = "word/theme/" if is_docx else "ppt/theme/"

        theme_names = sorted(n for n in names if n.startswith(theme_prefix) and n.endswith(".xml"))
        accents: dict[str, str] = {}
        if theme_names:
            accents = resolve_theme_accent_colors(zf.read(theme_names[0]))

        chart_names = sorted(
            n for n in names
            if re.fullmatch(rf"{re.escape(chart_prefix)}chart\d+\.xml", n)
        )
        for name in chart_names:
            root = ET.fromstring(zf.read(name))
            title_runs = root.findall(".//c:title//a:t", _C_NS)
            title = "".join(t.text or "" for t in title_runs).strip()
            if not title:
                continue
            series_list: list[ChartSeries] = []
            for ser in root.findall(".//c:ser", _C_NS):
                sname_el = ser.find("./c:tx//c:v", _C_NS)
                sname = (sname_el.text or "").strip() if sname_el is not None else ""

                color_name: str | None = None
                scheme_el = ser.find("./c:spPr//a:schemeClr", _C_NS)
                if scheme_el is not None:
                    hex_val = accents.get(scheme_el.get("val", ""))
                    if hex_val:
                        color_name = classify_color_name(hex_val)

                points: list[float] = []
                for pt in ser.findall("./c:val//c:pt", _C_NS):
                    idx = int(pt.get("idx", "0"))
                    v_el = pt.find("c:v", _C_NS)
                    if v_el is not None and v_el.text is not None:
                        while len(points) <= idx:
                            points.append(float("nan"))
                        points[idx] = float(v_el.text)

                series_list.append(ChartSeries(name=sname, color_name=color_name, points=points))
            if series_list:
                result[title] = series_list
    return result
