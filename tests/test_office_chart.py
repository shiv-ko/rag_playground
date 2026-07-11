from __future__ import annotations

import zipfile
from pathlib import Path

from src.generator.office_chart import extract_xlsx_chart_series, classify_color_name, resolve_theme_accent_colors

_CHARTEX1_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cx:chartSpace xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:cx="http://schemas.microsoft.com/office/drawing/2014/chartex">
<cx:chartData><cx:data id="0"><cx:numDim type="val"><cx:f>_xlchart.v1.3</cx:f></cx:numDim></cx:data></cx:chartData>
<cx:chart>
<cx:title pos="t" align="ctr" overlay="0"><cx:tx><cx:rich>
<a:p><a:r><a:t>\xe3\x82\xb0\xe3\x83\xa9\xe3\x83\x95</a:t></a:r><a:r><a:t>1</a:t></a:r></a:p>
</cx:rich></cx:tx></cx:title>
<cx:plotArea><cx:plotAreaRegion>
<cx:series layoutId="clusteredColumn" uniqueId="{0CEA9ABE-A7B9-4EC2-99A7-217D2E5218E5}">
<cx:tx><cx:txData><cx:f>_xlchart.v1.2</cx:f><cx:v>hum</cx:v></cx:txData></cx:tx>
<cx:dataId val="0" />
</cx:series>
</cx:plotAreaRegion></cx:plotArea>
</cx:chart></cx:chartSpace>"""

_THEME1_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office">
<a:themeElements>
<a:clrScheme name="Office">
<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
<a:dk2><a:srgbClr val="0E2841"/></a:dk2>
<a:lt2><a:srgbClr val="E8E8E8"/></a:lt2>
<a:accent1><a:srgbClr val="156082"/></a:accent1>
<a:accent2><a:srgbClr val="E97132"/></a:accent2>
<a:accent3><a:srgbClr val="196B24"/></a:accent3>
<a:accent4><a:srgbClr val="0F9ED5"/></a:accent4>
<a:accent5><a:srgbClr val="A02B93"/></a:accent5>
<a:accent6><a:srgbClr val="4EA72E"/></a:accent6>
</a:clrScheme>
</a:themeElements>
</a:theme>"""


def _make_xlsx_with_chart(tmp_path: Path, chart_xml: bytes, chart_name: str = "chartEx1.xml") -> Path:
    xlsx_path = tmp_path / "train.xlsx"
    with zipfile.ZipFile(xlsx_path, "w") as zf:
        zf.writestr(f"xl/charts/{chart_name}", chart_xml)
    return xlsx_path


class TestExtractXlsxChartSeries:
    def test_extracts_title_to_series_name(self, tmp_path: Path) -> None:
        xlsx_path = _make_xlsx_with_chart(tmp_path, _CHARTEX1_XML)

        result = extract_xlsx_chart_series(xlsx_path)

        assert result == {"グラフ1": "hum"}

    def test_multiple_charts_are_all_extracted(self, tmp_path: Path) -> None:
        xlsx_path = tmp_path / "train.xlsx"
        chart2_xml = _CHARTEX1_XML.replace(b">1<", b">2<").replace(b">hum<", b">windspeed<")
        with zipfile.ZipFile(xlsx_path, "w") as zf:
            zf.writestr("xl/charts/chartEx1.xml", _CHARTEX1_XML)
            zf.writestr("xl/charts/chartEx2.xml", chart2_xml)

        result = extract_xlsx_chart_series(xlsx_path)

        assert result == {"グラフ1": "hum", "グラフ2": "windspeed"}

    def test_no_charts_returns_empty_dict(self, tmp_path: Path) -> None:
        xlsx_path = tmp_path / "empty.xlsx"
        with zipfile.ZipFile(xlsx_path, "w") as zf:
            zf.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")

        result = extract_xlsx_chart_series(xlsx_path)

        assert result == {}


class TestResolveThemeAccentColors:
    def test_resolves_accent1_and_accent2(self) -> None:
        result = resolve_theme_accent_colors(_THEME1_XML)

        assert result["accent1"] == "156082"
        assert result["accent2"] == "E97132"


class TestClassifyColorName:
    def test_accent1_is_blue(self) -> None:
        assert classify_color_name("156082") == "blue"

    def test_accent2_is_orange(self) -> None:
        assert classify_color_name("E97132") == "orange"

    def test_pure_red(self) -> None:
        assert classify_color_name("FF0000") == "red"

    def test_gray_low_saturation(self) -> None:
        assert classify_color_name("808080") == "gray"
