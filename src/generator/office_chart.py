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


import unicodedata

from src.generator.confidence_gate import ConfidenceGate
from src.models import Answer

_CHART_NUM_RE = re.compile(r"グラフ\s*(\d+)")
_X_VALUE_RE = re.compile(r"x\s*=\s*(\d+)")
_ROUND_RE = re.compile(r"小数第(\d+)位")
# 案件名部分（例:「青潮モビリティサービスの」）を巻き込まないよう、\w ではなく明示的な文字クラスを使う。
# \w はPython3のstrパターンではUnicodeの平仮名も含むため、「案件名+の+ファイル名」のような
# 助詞区切りの連続をそのまま貪欲マッチしてしまい、案件名までファイル名として抽出するバグになる
# （平仮名の「の」を境界として使えなくなる）。平仮名を除いたASCII+漢字+カタカナのみを許可することで、
# 助詞の直後からファイル名だけを正しく切り出す。
_FILE_RE = re.compile(r"([A-Za-z0-9_\-一-龠ァ-ヶー]+\.(?:xlsx|docx|pptx))")

_COLOR_WORDS: dict[str, str] = {
    "青色": "blue", "青": "blue",
    "赤色": "red", "赤": "red",
    "オレンジ": "orange", "橙色": "orange", "橙": "orange",
    "緑色": "green", "緑": "green",
    "黄色": "yellow", "黄": "yellow",
    "紫色": "purple", "紫": "purple",
    "灰色": "gray", "グレー": "gray",
}


def _find_color_word(question: str) -> str | None:
    for word, name in _COLOR_WORDS.items():
        if word in question:
            return name
    return None


def _find_project_file(data_dir: Path, project_name: str, filename: str) -> Path | None:
    # macOSのパスはNFDになりうるためNFCに揃えて比較する（既存_load_train_csvと同じ対策）。
    normalized_project = unicodedata.normalize("NFC", project_name)
    matching = sorted(
        p for p in data_dir.rglob(filename)
        if normalized_project in unicodedata.normalize("NFC", str(p))
    )
    return matching[0] if matching else None


class OfficeChartAnswerer:
    """xlsx/docx/pptxのネイティブ埋め込みチャートから機械抽出で回答する。VLM不要。"""

    def __init__(self, threshold: float = 0.4) -> None:
        self.gate = ConfidenceGate(threshold=threshold)

    def answer(self, question: str, project_name: str, data_dir: Path) -> Answer:
        file_match = _FILE_RE.search(question)
        chart_match = _CHART_NUM_RE.search(question)
        if not file_match or not chart_match:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="office_chart_no_pattern")

        file_path = _find_project_file(data_dir, project_name, file_match.group(1))
        if file_path is None:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="office_chart_file_not_found")

        chart_title = f"グラフ{chart_match.group(1)}"

        if file_path.suffix.lower() == ".xlsx":
            return self._answer_column_name(file_path, chart_title)
        # 色語の探索はグラフ番号より後ろの部分文字列に限定する。案件名（例:「青潮モビリティ
        # サービス」）が色語「青」を部分文字列として含むことがあり、質問全文を対象に探索すると
        # 案件名から誤って色を検出してしまう（_FILE_REで平仮名を除外したのと同種のバグ）。
        # 実データの質問文言はすべて「案件名の...グラフN...色語...」の語順で、色語は常に
        # グラフ番号より後ろに現れるため、この制限で誤検出を避けつつ実際の色語は取りこぼさない。
        return self._answer_point_value(question[chart_match.end():], file_path, chart_title)

    def _answer_column_name(self, xlsx_path: Path, chart_title: str) -> Answer:
        try:
            series_map = extract_xlsx_chart_series(xlsx_path)
        except (zipfile.BadZipFile, ET.ParseError):
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="office_chart_extract_failed")
        column = series_map.get(chart_title)
        if not column:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="office_chart_series_not_found")
        return Answer(text=column, confidence=0.9, was_gated=False, raw_text=column,
                      gate_reason="office_chart_column")

    def _answer_point_value(self, question: str, file_path: Path, chart_title: str) -> Answer:
        x_match = _X_VALUE_RE.search(question)
        if not x_match:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="office_chart_no_x")
        idx = int(x_match.group(1))

        try:
            chart_map = extract_office_chart_series(file_path)
        except (zipfile.BadZipFile, ET.ParseError):
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="office_chart_extract_failed")
        series_list = chart_map.get(chart_title)
        if not series_list:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="office_chart_series_not_found")

        if len(series_list) == 1:
            target = series_list[0]
        else:
            color = _find_color_word(question)
            candidates = [s for s in series_list if color is not None and s.color_name == color]
            if len(candidates) != 1:
                return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                               gate_reason="office_chart_ambiguous_series")
            target = candidates[0]

        if idx >= len(target.points):
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="office_chart_index_out_of_range")
        value = target.points[idx]

        round_match = _ROUND_RE.search(question)
        if round_match:
            digits = int(round_match.group(1))
            value_text = f"{round(value, digits):.{digits}f}"
        else:
            value_text = str(value)

        return Answer(text=value_text, confidence=0.9, was_gated=False, raw_text=value_text,
                      gate_reason="office_chart_point_value")
