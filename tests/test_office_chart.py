from __future__ import annotations

import zipfile
from pathlib import Path

from src.generator.office_chart import (
    extract_xlsx_chart_series,
    classify_color_name,
    resolve_theme_accent_colors,
    ChartSeries,
    extract_office_chart_series,
)

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


_CHART1_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<c:chart>
<c:title><c:tx><c:rich><a:p><a:r><a:t>\xe3\x82\xb0\xe3\x83\xa9\xe3\x83\x95</a:t></a:r><a:r><a:t>1</a:t></a:r></a:p></c:rich></c:tx></c:title>
<c:plotArea><c:lineChart>
<c:ser>
<c:idx val="0"/><c:order val="0"/>
<c:spPr><a:ln><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:ln></c:spPr>
<c:val><c:numRef><c:f>Sheet2!$J$4:$J$10</c:f><c:numCache>
<c:ptCount val="7"/>
<c:pt idx="0"><c:v>0.48274573517465574</c:v></c:pt>
<c:pt idx="1"><c:v>0.49839676113360443</c:v></c:pt>
<c:pt idx="2"><c:v>0.50533551554828282</c:v></c:pt>
<c:pt idx="3"><c:v>0.50239218877136205</c:v></c:pt>
</c:numCache></c:numRef></c:val>
</c:ser>
</c:lineChart></c:plotArea>
</c:chart></c:chartSpace>"""

_CHART2_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<c:chart>
<c:title><c:tx><c:rich><a:p><a:r><a:t>\xe3\x82\xb0\xe3\x83\xa9\xe3\x83\x95</a:t></a:r><a:r><a:t>2</a:t></a:r></a:p></c:rich></c:tx></c:title>
<c:plotArea><c:lineChart>
<c:ser>
<c:idx val="0"/><c:order val="0"/>
<c:tx><c:strRef><c:f>Sheet2!$K$3</c:f><c:strCache><c:pt idx="0"><c:v>\xe5\xb9\xb3\xe5\x9d\x87 / cnt</c:v></c:pt></c:strCache></c:strRef></c:tx>
<c:spPr><a:ln><a:solidFill><a:schemeClr val="accent2"/></a:solidFill></a:ln></c:spPr>
<c:val><c:numRef><c:f>Sheet2!$K$4:$K$10</c:f><c:numCache>
<c:ptCount val="7"/>
<c:pt idx="3"><c:v>137.64768104149715</c:v></c:pt>
</c:numCache></c:numRef></c:val>
</c:ser>
<c:ser>
<c:idx val="1"/><c:order val="1"/>
<c:tx><c:strRef><c:f>Sheet2!$L$3</c:f><c:strCache><c:pt idx="0"><c:v>\xe5\xb9\xb3\xe5\x9d\x87 / windspeed</c:v></c:pt></c:strCache></c:strRef></c:tx>
<c:spPr><a:ln><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:ln></c:spPr>
<c:val><c:numRef><c:f>Sheet2!$L$4:$L$10</c:f><c:numCache>
<c:ptCount val="7"/>
<c:pt idx="3"><c:v>0.19555305126118649</c:v></c:pt>
</c:numCache></c:numRef></c:val>
</c:ser>
</c:lineChart></c:plotArea>
</c:chart></c:chartSpace>"""


def _make_docx_with_charts(tmp_path: Path) -> Path:
    docx_path = tmp_path / "基礎分析.docx"
    with zipfile.ZipFile(docx_path, "w") as zf:
        zf.writestr("word/document.xml", "<document/>")
        zf.writestr("word/charts/chart1.xml", _CHART1_XML)
        zf.writestr("word/charts/chart2.xml", _CHART2_XML)
        zf.writestr("word/theme/theme1.xml", _THEME1_XML)
    return docx_path


class TestExtractOfficeChartSeries:
    def test_single_series_chart_has_no_color_ambiguity(self, tmp_path: Path) -> None:
        docx_path = _make_docx_with_charts(tmp_path)

        result = extract_office_chart_series(docx_path)

        assert "グラフ1" in result
        series = result["グラフ1"]
        assert len(series) == 1
        assert series[0].color_name == "blue"
        assert series[0].points[3] == 0.50239218877136205

    def test_multi_series_chart_resolves_each_color(self, tmp_path: Path) -> None:
        docx_path = _make_docx_with_charts(tmp_path)

        result = extract_office_chart_series(docx_path)

        series = result["グラフ2"]
        assert len(series) == 2
        by_color = {s.color_name: s for s in series}
        assert by_color["orange"].name == "平均 / cnt"
        assert by_color["blue"].name == "平均 / windspeed"
        assert by_color["blue"].points[3] == 0.19555305126118649

    def test_pptx_file_uses_ppt_charts_prefix(self, tmp_path: Path) -> None:
        pptx_path = tmp_path / "presentation.pptx"
        with zipfile.ZipFile(pptx_path, "w") as zf:
            zf.writestr("ppt/presentation.xml", "<presentation/>")
            zf.writestr("ppt/charts/chart1.xml", _CHART1_XML)
            zf.writestr("ppt/theme/theme1.xml", _THEME1_XML)

        result = extract_office_chart_series(pptx_path)

        assert "グラフ1" in result
        series = result["グラフ1"]
        assert len(series) == 1
        assert series[0].color_name == "blue"
        assert series[0].points[3] == 0.50239218877136205


import unicodedata

from src.generator.office_chart import OfficeChartAnswerer


def _make_project_dir(tmp_path: Path, project_name: str) -> Path:
    project_dir = tmp_path / project_name
    project_dir.mkdir()
    return project_dir


class TestOfficeChartAnswererXlsxColumn:
    def test_answers_column_name_from_xlsx_chart(self, tmp_path: Path) -> None:
        project_dir = _make_project_dir(tmp_path, "株式会社青潮モビリティサービス")
        xlsx_path = project_dir / "train.xlsx"
        with zipfile.ZipFile(xlsx_path, "w") as zf:
            zf.writestr("xl/charts/chartEx1.xml", _CHARTEX1_XML)

        answerer = OfficeChartAnswerer()
        result = answerer.answer(
            "青潮モビリティサービスのtrain.xlsxのSheet1にあるグラフ1はどのカラムを可視化したものですか。",
            "株式会社青潮モビリティサービス",
            tmp_path,
        )

        assert result.was_gated is False
        assert result.text == "hum"

    def test_missing_chart_number_is_gated(self, tmp_path: Path) -> None:
        answerer = OfficeChartAnswerer()
        result = answerer.answer(
            "train.xlsxのSheet1について教えてください。",
            "存在しない案件",
            tmp_path,
        )

        assert result.was_gated is True


class TestOfficeChartAnswererDocxPointValue:
    def test_single_series_needs_no_color_word(self, tmp_path: Path) -> None:
        project_dir = _make_project_dir(tmp_path, "株式会社青潮モビリティサービス")
        docx_path = project_dir / "基礎分析.docx"
        with zipfile.ZipFile(docx_path, "w") as zf:
            zf.writestr("word/document.xml", "<document/>")
            zf.writestr("word/charts/chart1.xml", _CHART1_XML)
            zf.writestr("word/theme/theme1.xml", _THEME1_XML)

        answerer = OfficeChartAnswerer()
        result = answerer.answer(
            "青潮モビリティサービスの基礎分析.docxのグラフ1で、x=3のときのyの値を小数第5位で答えてください。",
            "株式会社青潮モビリティサービス",
            tmp_path,
        )

        assert result.was_gated is False
        assert result.text == "0.50239"

    def test_multi_series_uses_color_word_to_disambiguate(self, tmp_path: Path) -> None:
        project_dir = _make_project_dir(tmp_path, "株式会社青潮モビリティサービス")
        docx_path = project_dir / "基礎分析.docx"
        with zipfile.ZipFile(docx_path, "w") as zf:
            zf.writestr("word/document.xml", "<document/>")
            zf.writestr("word/charts/chart2.xml", _CHART2_XML)
            zf.writestr("word/theme/theme1.xml", _THEME1_XML)

        answerer = OfficeChartAnswerer()
        result = answerer.answer(
            "青潮モビリティサービスの基礎分析.docxのグラフ2で、x=3のときの青色の折れ線のyの値を小数第5位で答えてください。",
            "株式会社青潮モビリティサービス",
            tmp_path,
        )

        assert result.was_gated is False
        assert result.text == "0.19555"

    def test_multi_series_without_color_word_is_gated(self, tmp_path: Path) -> None:
        project_dir = _make_project_dir(tmp_path, "株式会社青潮モビリティサービス")
        docx_path = project_dir / "基礎分析.docx"
        with zipfile.ZipFile(docx_path, "w") as zf:
            zf.writestr("word/document.xml", "<document/>")
            zf.writestr("word/charts/chart2.xml", _CHART2_XML)
            zf.writestr("word/theme/theme1.xml", _THEME1_XML)

        answerer = OfficeChartAnswerer()
        result = answerer.answer(
            "青潮モビリティサービスの基礎分析.docxのグラフ2で、x=3のときのyの値を小数第5位で答えてください。",
            "株式会社青潮モビリティサービス",
            tmp_path,
        )

        assert result.was_gated is True
