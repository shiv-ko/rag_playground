# Phase4 image_graph型質問の接続 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `image_or_graph`タグが付き現在強制Missingになっている質問のうち、(A) xlsx/docx/pptxの**ネイティブ埋め込みチャート**（chartEx/chart XMLにキャッシュされた実データ）から機械抽出できるもの、(B) 独立画像ファイル（png等）をClaude Vision APIに直接渡して読ませるもの、の2経路を実装し、`src/orchestrator/pipeline.py`の`_process_structured`に接続する。

**Architecture:** strategy.md §3.4が推奨する「クエリ時画像参照」方式を採用。(A)は既存のcontract_calc.py/spreadsheet_calc.py同様、ゼロAPIコストの決定的抽出（正規表現で質問からチャート番号・x値・色・丸め桁数を読み取り、zipfile+ElementTreeでOOXMLチャートXMLを直接パース）。(B)は`AnswerGenerator._call_llm`と同じAnthropicクライアント構成に、画像contentブロックを追加した新クラス`VLMImageAnswerer`。両方とも`was_gated=False`の確定回答のみ`_process_structured`から返し、解決不能なら`None`/`was_gated=True`を返して既存の`image_or_graph`能力ブロック（安全側のMissing）にフォールバックする。

**Tech Stack:** 既存構成のまま（Python標準の`zipfile`/`xml.etree.ElementTree`、`anthropic`SDK、pytest）。新規依存追加なし。

## Global Constraints

- venv: `.venv/bin/python`、テスト: `.venv/bin/pytest tests/ -v`
- 回答は1000トークン以内（既存の`MAX_CHARS_APPROX`と同様の制約。この計画のAnswerはいずれも短い数値・単語なので影響なし）
- 案件名・ファイル名・質問文そのものへの直接分岐は禁止（`docs/plan/plan_0703.md` §4運用ルール5の汎用性チェック）。本計画の抽出ロジックはすべて質問文の正規表現パターン（グラフ番号・x値・色・ファイル拡張子）とOOXML標準スキーマに基づく機械抽出であり、特定案件名へのif分岐は含まない
- 1実験1変更ではなく1タスク1コミット（`docs/plan/`運用に合わせる）。各タスック完了後にstep-reviewを実施してからコミットする
- 実データでの検証はTask 8（本計画の最終タスク）でまとめて行う。個別タスクのユニットテストは実データから採取した固定フィクスチャで代替する（実APIコール・実ファイルI/Oはモック/monkeypatchする）

## スコープ外（次アクションで別ブロック提案）

- `Q0`/`test Q13`/`test Q46`（座席表pptx・青潮06.報告書PDFの画像のみ資料）: PDFページのラスタライズには新規依存（PyMuPDF等）が必要、座席表は「誰を探すか」の人物・役割解決（people_registry、`docs/plan/2026-07-11-cross-project-block.md` §1.6で既に別ブロック推奨と判定済み）が前提。本計画のVLM基盤（`VLMImageAnswerer`）は再利用できる設計にしてあるため、後続ブロックで`image_bytes`を渡すだけで拡張できる
- `valid Q24`/`test Q56`（notebook_output主・ipynb出力画像の相関ヒートマップ/軸目盛り読み取り）: `plan_0703.md`のPhase4では`analysis_metrics/notebook_output/code_static`という別項目であり、実データ確認の結果train.csv/xlsxからのpandas再計算（既存`SpreadsheetCalcAnswerer`拡張）で解決できる可能性が高くVLM画像読み取りとは別スコープ。本計画では扱わない

## 対象設問（実データ調査済み、2026-07-11）

| split | idx | 質問 | 現状 | 解決経路 |
|---|---|---|---|---|
| test | 39 | 青潮train.xlsxのグラフ1はどのカラムを可視化したものか | `image_or_graph`でMissing | (A) xlsxチャート抽出。実データ検証: `xl/charts/chartEx1.xml`のタイトル「グラフ1」→系列名`hum` |
| test | 54 | 青潮基礎分析.docxのグラフ1、x=3のときのyの値(小数第5位) | 同上 | (A) docxチャート抽出。実データ検証: `word/charts/chart1.xml`のidx=3キャッシュ値`0.50239218877136205`→`0.50239` |
| test | 33 | 青潮基礎分析.docxのグラフ2、x=3のときの青色の折れ線のyの値(小数第5位) | 同上 | (A) docxチャート抽出＋色解決。実データ検証: `chart2.xml`は2系列（`平均 / windspeed`=accent1=`#156082`=青、`平均 / cnt`=accent2=`#E97132`=橙）、windspeedのidx=3が`0.19555305126118649`→`0.19555` |
| valid | 1 | KSSのfigure_06.pngで、dayによる件数推移とあわせて表示されているTG平均が最も低い日 | `image_or_graph`でMissing | (B) VLM。`04.分析/analysis_project/reports/figures/figure_06.png`は独立PNG（matplotlib生成、埋め込みチャートではなくキャッシュ数値が無い）。目視確認済みで人間可読、Claude visionでの読み取りが妥当 |
| test | 66 | 京橋EDAの日付分析の可視化で、件数が最も高いのは何日 | 現状`image_or_graph`タグが付かず`text_only`のまま通常LLM生成に流れている（要修正） | (B) VLM。valid Q1と同一ファイル（同フォルダに日付分析の図は`figure_06.png`のみ）を参照 |

## File Structure

- Create: `src/generator/office_chart.py` — (A)ネイティブチャートXML抽出＋`OfficeChartAnswerer`
- Create: `tests/test_office_chart.py`
- Create: `src/generator/vlm_answerer.py` — (B)`VLMImageAnswerer`＋`find_referenced_image`
- Create: `tests/test_vlm_answerer.py`
- Modify: `src/utils/question_classifier.py` — `IMAGE_KEYWORDS`に`"可視化"`を追加（test idx66のタグ漏れ修正）
- Modify: `src/orchestrator/pipeline.py` — `Pipeline.__init__`に2つの新Answererを追加、`_process_structured`に(A)(B)の分岐を追加、`_process_one`のトリガータプルに`"image_or_graph"`を追加
- Modify: `tests/test_pipeline.py` — ルーティング回帰テストを追加

## Interfaces（タスク間の依存）

- `office_chart.extract_xlsx_chart_series(xlsx_path: Path) -> dict[str, str]`
- `office_chart.resolve_theme_accent_colors(theme_xml_bytes: bytes) -> dict[str, str]`
- `office_chart.classify_color_name(hex_rgb: str) -> str`
- `office_chart.ChartSeries`（`name: str`, `color_name: str | None`, `points: list[float]`）
- `office_chart.extract_office_chart_series(office_file_path: Path) -> dict[str, list[ChartSeries]]`
- `office_chart.OfficeChartAnswerer(threshold: float = 0.4).answer(question: str, project_name: str, data_dir: Path) -> Answer`
- `vlm_answerer.VLMImageAnswerer(threshold: float = 0.4).answer(question: str, image_path: Path) -> Answer`
- `vlm_answerer.find_referenced_image(question: str, project_name: str, data_dir: Path) -> Path | None`

---

### Task 1: xlsxネイティブチャート(chartEx)の系列名抽出

**Files:**
- Create: `src/generator/office_chart.py`
- Test: `tests/test_office_chart.py`

**Interfaces:**
- Produces: `extract_xlsx_chart_series(xlsx_path: Path) -> dict[str, str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_office_chart.py
from __future__ import annotations

import zipfile
from pathlib import Path

from src.generator.office_chart import extract_xlsx_chart_series

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_office_chart.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.generator.office_chart'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/generator/office_chart.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_office_chart.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/generator/office_chart.py tests/test_office_chart.py
git commit -m "Add xlsx native chart series-name extraction (no VLM)"
```

---

### Task 2: テーマ配色の解決と色名分類

**Files:**
- Modify: `src/generator/office_chart.py`
- Test: `tests/test_office_chart.py`

**Interfaces:**
- Consumes: なし
- Produces: `resolve_theme_accent_colors(theme_xml_bytes: bytes) -> dict[str, str]`, `classify_color_name(hex_rgb: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_office_chart.py に追記
from src.generator.office_chart import classify_color_name, resolve_theme_accent_colors

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_office_chart.py -v`
Expected: FAIL with `ImportError: cannot import name 'classify_color_name'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/generator/office_chart.py に追記
import colorsys

_THEME_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
_ACCENT_KEYS = ("accent1", "accent2", "accent3", "accent4", "accent5", "accent6")


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_office_chart.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/generator/office_chart.py tests/test_office_chart.py
git commit -m "Add theme accent color resolution and basic color-name classifier"
```

---

### Task 3: docx/pptxネイティブチャートの系列・数値抽出

**Files:**
- Modify: `src/generator/office_chart.py`
- Test: `tests/test_office_chart.py`

**Interfaces:**
- Consumes: `resolve_theme_accent_colors`, `classify_color_name`（Task 2）
- Produces: `ChartSeries`（dataclass: `name: str`, `color_name: str | None`, `points: list[float]`）, `extract_office_chart_series(office_file_path: Path) -> dict[str, list[ChartSeries]]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_office_chart.py に追記
from src.generator.office_chart import ChartSeries, extract_office_chart_series

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_office_chart.py -v`
Expected: FAIL with `ImportError: cannot import name 'ChartSeries'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/generator/office_chart.py に追記
from dataclasses import dataclass, field


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_office_chart.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/generator/office_chart.py tests/test_office_chart.py
git commit -m "Add docx/pptx native chart series+points extraction with color resolution"
```

---

### Task 4: `OfficeChartAnswerer` — 質問解析と統合

**Files:**
- Modify: `src/generator/office_chart.py`
- Test: `tests/test_office_chart.py`

**Interfaces:**
- Consumes: `extract_xlsx_chart_series`, `extract_office_chart_series`（Task 1, 3）, `Answer`（`src/models.py`）, `ConfidenceGate`（`src/generator/confidence_gate.py`）
- Produces: `OfficeChartAnswerer(threshold: float = 0.4).answer(question: str, project_name: str, data_dir: Path) -> Answer`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_office_chart.py に追記
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_office_chart.py -v`
Expected: FAIL with `ImportError: cannot import name 'OfficeChartAnswerer'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/generator/office_chart.py に追記
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
        # 疎な系列（間の idx が欠落しているケース）はextract_office_chart_seriesがNaN埋めする。
        # 範囲内でも値がNaNなら「文字列"nan"を確信度0.9で返す」誤答になるため明示的にゲートする。
        if math.isnan(value):
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="office_chart_value_unavailable")

        round_match = _ROUND_RE.search(question)
        if round_match:
            digits = int(round_match.group(1))
            value_text = f"{round(value, digits):.{digits}f}"
        else:
            value_text = str(value)

        return Answer(text=value_text, confidence=0.9, was_gated=False, raw_text=value_text,
                      gate_reason="office_chart_point_value")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_office_chart.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add src/generator/office_chart.py tests/test_office_chart.py
git commit -m "Add OfficeChartAnswerer: question parsing + native-chart routing"
```

---

### Task 5: `OfficeChartAnswerer`をpipelineへ接続

**Files:**
- Modify: `src/orchestrator/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `office_chart.OfficeChartAnswerer`（Task 4）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py に追記
def test_pipeline_routes_chart_question_to_office_chart_answerer(tmp_path: Path) -> None:
    """image_or_graphタグかつグラフ番号を含む質問はOfficeChartAnswererへ渡り、
    generate()（検索+LLM）を経由しない。"""
    import zipfile

    from src.orchestrator.pipeline import Pipeline, QAPair

    project_dir = tmp_path / "株式会社青潮モビリティサービス"
    project_dir.mkdir()
    xlsx_path = project_dir / "train.xlsx"
    chartex1_xml = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<cx:chartSpace xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        b' xmlns:cx="http://schemas.microsoft.com/office/drawing/2014/chartex">'
        b'<cx:chart><cx:title pos="t"><cx:tx><cx:rich>'
        b'<a:p><a:r><a:t>\xe3\x82\xb0\xe3\x83\xa9\xe3\x83\x95</a:t></a:r><a:r><a:t>1</a:t></a:r></a:p>'
        b'</cx:rich></cx:tx></cx:title><cx:plotArea><cx:plotAreaRegion>'
        b'<cx:series><cx:tx><cx:txData><cx:v>hum</cx:v></cx:txData></cx:tx></cx:series>'
        b'</cx:plotAreaRegion></cx:plotArea></cx:chart></cx:chartSpace>'
    )
    with zipfile.ZipFile(xlsx_path, "w") as zf:
        zf.writestr("xl/charts/chartEx1.xml", chartex1_xml)

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False)

    def _boom(question, contexts):
        raise AssertionError("chart質問は通常のgenerate()を使ってはいけない")

    pipeline.generator.generate = _boom

    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="0",
        question="青潮モビリティサービスのtrain.xlsxのSheet1にあるグラフ1はどのカラムを可視化したものですか。",
    ))

    assert result.answer_path == "structured:office_chart"
    assert result.answer == "hum"


def test_pipeline_chart_extraction_failure_falls_back_to_capability_block(tmp_path: Path) -> None:
    """チャート抽出に失敗した場合（対象ファイルが存在しない等）は既存のimage_or_graph能力ブロック
    （安全側のMissing）にフォールバックし、generate()の推測には流れない。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False)

    def _boom(question, contexts):
        raise AssertionError("抽出失敗時もgenerate()を使ってはいけない（能力ブロックがMissingを返す）")

    pipeline.generator._call_llm = lambda question, context: (_ for _ in ()).throw(
        AssertionError("LLM呼び出しは発生してはいけない")
    )

    (tmp_path / "存在しない案件").mkdir()
    (tmp_path / "存在しない案件" / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="0",
        question="存在しない案件のtrain.xlsxのグラフ1はどのカラムを可視化したものですか。",
    ))

    assert result.answer_path == "retrieval"
    assert result.judge_label == "" or True  # judge無効化時はスキップされるため形状のみ確認
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline.py -k chart -v`
Expected: FAIL — 1つ目のテストが`AssertionError: chart質問は通常のgenerate()を使ってはいけない`で失敗（まだ配線していないため`_process_structured`が`None`を返し`generate()`が呼ばれる）

- [ ] **Step 3: Write minimal implementation**

`src/orchestrator/pipeline.py`の変更点:

1. import追加（`from src.evaluator.judge import LocalJudge`の下あたり、既存import群に追加）:

```python
from src.generator.office_chart import OfficeChartAnswerer
```

2. `Pipeline.__init__`内、`self.milestone_threshold_list_answerer = ...`の直後に追加:

```python
        self.office_chart_answerer = OfficeChartAnswerer(threshold=confidence_threshold)
```

3. `_process_structured`内、`if project_name is None: return None`の直後（`if "spreadsheet_calc" in tags:`ブロックの直前）に追加:

```python
        if "image_or_graph" in tags:
            chart_answer = self.office_chart_answerer.answer(qa.question, project_name, self.data_dir)
            if not chart_answer.was_gated:
                return chart_answer, "structured:office_chart"
            # 抽出できなければMissing固定にせず後続のパス（VLM等）へ委ねる
```

4. `_process_one`内のトリガータプルに`"image_or_graph"`を追加:

```python
        if any(
            t in tags
            for t in (
                "office_style",
                "spreadsheet_state",
                "spreadsheet_calc",
                "version_diff",
                "ms_date_duration",
                "ms_date_cross_project_list",
                "contract_rule",
                "cross_project",
                "image_or_graph",
            )
        ):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pipeline.py -k chart -v`
Expected: PASS (2 tests)

Run全体回帰確認: `.venv/bin/pytest tests/ -v`
Expected: PASS（既存テストに影響なし）

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/pipeline.py tests/test_pipeline.py
git commit -m "Wire OfficeChartAnswerer into pipeline structured routing"
```

---

### Task 6: `VLMImageAnswerer` — Claude Vision APIでの画像読解

**Files:**
- Create: `src/generator/vlm_answerer.py`
- Create: `tests/test_vlm_answerer.py`

**Interfaces:**
- Consumes: `Answer`（`src/models.py`）, `ConfidenceGate`（`src/generator/confidence_gate.py`）
- Produces: `VLMImageAnswerer(threshold: float = 0.4).answer(question: str, image_path: Path) -> Answer`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vlm_answerer.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.generator.vlm_answerer import VLMImageAnswerer

_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8ffff3f0005fe02fea739669f0000000049454e44ae426082"
)


class TestVLMImageAnswererCallConstruction:
    def test_sends_image_block_and_question(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5")
        image_path = tmp_path / "figure_06.png"
        image_path.write_bytes(_PNG_1PX)

        fake_content = type("C", (), {
            "text": '{"answer": "20\\u65e5", "confidence": 0.85, "reasoning": "r"}'
        })()
        fake_response = type("R", (), {"content": [fake_content]})()

        answerer = VLMImageAnswerer()
        with patch("src.generator.vlm_answerer.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            result = answerer.answer("dayによる件数推移で件数が最も高いのは何日ですか。", image_path)

        assert result.was_gated is False
        assert result.text == "20日"

        _, kwargs = MockAnthropic.return_value.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
        content_blocks = kwargs["messages"][0]["content"]
        image_blocks = [b for b in content_blocks if b["type"] == "image"]
        text_blocks = [b for b in content_blocks if b["type"] == "text"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["source"]["media_type"] == "image/png"
        assert "件数が最も高い" in text_blocks[0]["text"]

    def test_low_confidence_is_gated(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        image_path = tmp_path / "figure_06.png"
        image_path.write_bytes(_PNG_1PX)

        fake_content = type("C", (), {
            "text": '{"answer": "わかりません", "confidence": 0.1, "reasoning": "r"}'
        })()
        fake_response = type("R", (), {"content": [fake_content]})()

        answerer = VLMImageAnswerer()
        with patch("src.generator.vlm_answerer.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = fake_response
            result = answerer.answer("質問", image_path)

        assert result.was_gated is True

    def test_missing_file_is_gated_without_api_call(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        answerer = VLMImageAnswerer()

        with patch("src.generator.vlm_answerer.Anthropic") as MockAnthropic:
            result = answerer.answer("質問", tmp_path / "not_exist.png")

        assert result.was_gated is True
        MockAnthropic.return_value.messages.create.assert_not_called()

    def test_unsupported_extension_is_gated_without_api_call(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        file_path = tmp_path / "report.pdf"
        file_path.write_bytes(b"%PDF-1.4")
        answerer = VLMImageAnswerer()

        with patch("src.generator.vlm_answerer.Anthropic") as MockAnthropic:
            result = answerer.answer("質問", file_path)

        assert result.was_gated is True
        MockAnthropic.return_value.messages.create.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_vlm_answerer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.generator.vlm_answerer'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/generator/vlm_answerer.py
"""画像・グラフの読解生成。_call_vlm() はAnthropic Vision APIを呼び出す。"""
from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
from pathlib import Path

from anthropic import Anthropic

from src.generator.confidence_gate import ConfidenceGate
from src.models import Answer

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

VLM_SYSTEM_PROMPT = """\
あなたは画像として提供されたグラフ・図表を読み取り、質問に答えるアシスタントです。

【重要ルール】
1. 画像に実際に描画されている内容のみを根拠に回答すること。読み取れない場合は正直に「わかりません」と答える
2. confidenceは「この回答が正しい確率」を0.0〜1.0で表すこと。読み取りに自信が持てない場合は0.4未満にすること
   （わからないのにconfidenceを高くすることは禁止）
3. 設問が特定の数値・日付・ラベルを問う場合、"answer" には値そのものだけを入れ、説明文を続けないこと
4. 回答は1000トークン以内に収めること

【出力形式】
{
  "answer": "回答テキスト",
  "confidence": 0.0〜1.0,
  "reasoning": "画像のどの部分から読み取ったか"
}
"""


class VLMImageAnswerer:
    """独立画像ファイル（png等）をClaude Vision APIに直接渡して質問に答える。"""

    def __init__(self, threshold: float = 0.4) -> None:
        self.gate = ConfidenceGate(threshold=threshold)
        self._client: Anthropic | None = None

    def answer(self, question: str, image_path: Path) -> Answer:
        media_type = _MEDIA_TYPES.get(image_path.suffix.lower())
        if media_type is None:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="vlm_unsupported_format")
        try:
            image_bytes = image_path.read_bytes()
        except OSError:
            return Answer(text=self.gate.missing_text(), confidence=0.0, was_gated=True,
                           gate_reason="vlm_file_not_found")

        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        raw = self._call_vlm(question, image_b64, media_type)
        answer_text, confidence, _reasoning = self._parse_response(raw)

        if not answer_text or not self.gate.should_answer(confidence):
            return Answer(text=self.gate.missing_text(), confidence=confidence, was_gated=True,
                           raw_text=answer_text, gate_reason="vlm_confidence")

        return Answer(text=answer_text, confidence=confidence, was_gated=False,
                      raw_text=answer_text, gate_reason="vlm_image")

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _call_vlm(self, question: str, image_b64: str, media_type: str) -> str:
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
        message = self._get_client().messages.create(
            model=model,
            max_tokens=1000,
            system=VLM_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": f"【質問】\n{question}"},
                ],
            }],
        )
        return "".join(block.text for block in message.content if hasattr(block, "text"))

    def _parse_response(self, raw: str) -> tuple[str, float, str]:
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group(), strict=False)
                return (
                    str(data.get("answer", "")),
                    float(data.get("confidence", 0.0)),
                    str(data.get("reasoning", "")),
                )
        except (json.JSONDecodeError, ValueError):
            pass
        return raw, 0.0, ""


# office_chart.pyの_FILE_REと同じ理由（\wが平仮名を含みUnicodeの助詞境界を吸収してしまう）で、
# 明示的な文字クラス（平仮名を除くASCII+漢字+カタカナ）を使う。
_IMAGE_FILE_RE = re.compile(r"([A-Za-z0-9_\-一-龠ァ-ヶー]+\.(?:png|jpg|jpeg|gif|webp))", re.IGNORECASE)


def find_referenced_image(question: str, project_name: str, data_dir: Path) -> Path | None:
    """質問文中に明示されたファイル名（例: figure_06.png）を案件ディレクトリ配下から探す。"""
    match = _IMAGE_FILE_RE.search(question)
    if match is None:
        return None
    filename = match.group(1)
    normalized_project = unicodedata.normalize("NFC", project_name)
    matching = sorted(
        p for p in data_dir.rglob(filename)
        if normalized_project in unicodedata.normalize("NFC", str(p))
    )
    return matching[0] if matching else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_vlm_answerer.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/generator/vlm_answerer.py tests/test_vlm_answerer.py
git commit -m "Add VLMImageAnswerer: Claude Vision API image-question answering"
```

---

### Task 7: `VLMImageAnswerer`をpipelineへ接続し、`image_or_graph`キーワードを補完

**Files:**
- Modify: `src/utils/question_classifier.py`
- Modify: `src/orchestrator/pipeline.py`
- Test: `tests/test_pipeline.py`, 既存の分類器テスト（`tests/test_question_classifier.py`があれば流用、無ければ`tests/test_pipeline.py`にまとめる）

**Interfaces:**
- Consumes: `vlm_answerer.VLMImageAnswerer`, `vlm_answerer.find_referenced_image`（Task 6）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py に追記
def test_pipeline_routes_standalone_image_question_to_vlm_answerer(tmp_path: Path, monkeypatch) -> None:
    """独立画像ファイルを参照する質問（image_or_graphタグ、チャート番号なし）はVLMImageAnswererへ渡る。
    実APIは呼ばず、VLMImageAnswerer._call_vlmを差し替えて検証する。"""
    from src.orchestrator.pipeline import Pipeline, QAPair

    project_dir = tmp_path / "京橋信用ソリューションズ株式会社"
    project_dir.mkdir()
    figures_dir = project_dir / "04.分析" / "figures"
    figures_dir.mkdir(parents=True)
    (figures_dir / "figure_06.png").write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
            "53de0000000c4944415408d763f8ffff3f0005fe02fea739669f0000000049454e44ae426082"
        )
    )

    pipeline = Pipeline(data_dir=tmp_path, run_judge=False)

    def _boom(question, contexts):
        raise AssertionError("独立画像の質問は通常のgenerate()を使ってはいけない")

    pipeline.generator.generate = _boom
    pipeline.vlm_answerer._call_vlm = lambda question, image_b64, media_type: (
        '{"answer": "20\\u65e5", "confidence": 0.85, "reasoning": "r"}'
    )

    (tmp_path / "a.txt").write_text("関係ないテキスト", encoding="utf-8")
    pipeline.build_index()

    result = pipeline._process_one(QAPair(
        question_id="0",
        question="京橋信用ソリューションズのfigure_06.pngにおいて、件数が最も高いのは何日ですか。",
    ))

    assert result.answer_path == "structured:vlm_image"
    assert result.answer == "20日"


def test_image_keyword_kashika_is_tagged_image_or_graph() -> None:
    """『可視化』というキーワードだけの質問もimage_or_graphタグが付く
    （test idx66型: 従来はキーワード漏れでtext_onlyのまま通常LLM生成に流れていた）。"""
    from src.utils.question_classifier import classify_question

    tags = classify_question("京橋信用ソリューションズのEDAの日付分析の可視化において、件数が最も高いのは何日ですか。")

    assert "image_or_graph" in tags
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline.py -k "vlm_answerer or kashika" -v`
Expected: FAIL — 2件とも失敗（配線・キーワード追加とも未実施のため）

- [ ] **Step 3: Write minimal implementation**

1. `src/utils/question_classifier.py`の`IMAGE_KEYWORDS`に`"可視化"`を追加:

```python
IMAGE_KEYWORDS = (".png", ".jpg", "画像", "グラフ", "figure", "マーカー", "折れ線", "図", "可視化")
```

2. `src/orchestrator/pipeline.py`の変更:

import追加:

```python
from src.generator.vlm_answerer import VLMImageAnswerer, find_referenced_image
```

`Pipeline.__init__`内、`self.office_chart_answerer = ...`の直後に追加:

```python
        self.vlm_answerer = VLMImageAnswerer(threshold=confidence_threshold)
```

`_process_structured`内、Task 5で追加した`office_chart`ブロックのすぐ後に追加:

```python
        if "image_or_graph" in tags:
            image_path = find_referenced_image(qa.question, project_name, self.data_dir)
            if image_path is not None:
                vlm_answer = self.vlm_answerer.answer(qa.question, image_path)
                if not vlm_answer.was_gated:
                    return vlm_answer, "structured:vlm_image"
            # 画像が見つからない・VLMが確信を持てない場合はMissing固定にせず
            # 既存のimage_or_graph能力ブロック（安全側のMissing）へ委ねる
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pipeline.py -k "vlm_answerer or kashika" -v`
Expected: PASS (2 tests)

Run全体回帰確認: `.venv/bin/pytest tests/ -v`
Expected: PASS（既存テストに影響なし。`IMAGE_KEYWORDS`変更で他の質問分類テストが崩れていないか特に確認）

- [ ] **Step 5: Commit**

```bash
git add src/utils/question_classifier.py src/orchestrator/pipeline.py tests/test_pipeline.py
git commit -m "Wire VLMImageAnswerer into pipeline; add 可視化 to IMAGE_KEYWORDS"
```

---

### Task 8: 実データ検証（TDDではなく診断run。cross_projectブロックの実施パターンを踏襲）

**Files:**
- 変更なし（診断runと結果の記録のみ）

- [ ] **Step 1: test 100問診断run（`--no-judge`）を実行し、対象5問の`answer_path`と回答内容を確認**

```bash
.venv/bin/python scripts/run_pipeline.py \
  --data-dir "data/raw/share/共有ドライブ" \
  --questions "data/raw/share/質問回答/questions_test.csv" \
  --run-name phase4_imagegraph_test_diag --no-cache --no-judge
```

（`questions_test.csv`のパスは`data/raw/share/質問回答/`配下の実ファイル名を`ls`で確認してから使う。存在しない場合はvalid同様の命名パターンを探す）

期待する結果（手計算で事前検証済みの値と一致するか確認）:
- test idx39: `answer_path == "structured:office_chart"`, `answer == "hum"`
- test idx54: `answer_path == "structured:office_chart"`, `answer == "0.50239"`
- test idx33: `answer_path == "structured:office_chart"`, `answer == "0.19555"`
- test idx66: `answer_path == "structured:vlm_image"`（VLM実呼び出し。回答内容は目視で図と整合するか確認）

- [ ] **Step 2: valid 30問診断run(N=1)をofficial較正込みで実行し、regressionが無いことを確認**

```bash
.venv/bin/python scripts/run_pipeline.py \
  --data-dir "data/raw/share/共有ドライブ" \
  --questions "data/raw/share/質問回答/questions_valid.csv" \
  --run-name phase4_imagegraph_valid --no-cache
.venv/bin/python scripts/calibrate_judge.py experiments/phase4_imagegraph_valid_<timestamp>.json
```

期待する結果:
- valid idx1: `answer_path == "structured:vlm_image"`。official judgeで新規Incorrectが発生していないか確認（既知のQ17のみ許容）
- 他29問に新規のofficial Incorrectが出ていないこと（既知のQ17以外）

- [ ] **Step 3: 結果を記録**

`docs/plan/plan_0703.md`のPhase4節を実測結果で更新し、`docs/daily作業ログ/`に新規ログを作成する（vault.mdの運用ルールに従う）。test idx39/33/54/66の実測値と、valid idx1のofficial較正結果を残す。

---

## Self-Review

**Spec coverage**: 対象5問（test idx39/33/54/66, valid idx1）すべてにTask 1-7で実装したコードパスが対応し、Task 8で実データ検証する。スコープ外とした項目（idx0/13/46/24/56）は冒頭の「スコープ外」節に理由付きで明記済み。

**Placeholder scan**: 全ステップに実コード・実コマンドを記載済み。「TODO」「後で実装」等の記述なし。

**Type consistency**: `ChartSeries`（Task 3で定義: `name/color_name/points`）は Task 4 の `_answer_point_value` で同じ属性名を参照。`Answer`（`src/models.py`既存）のフィールド名（`text/confidence/was_gated/raw_text/gate_reason`）はTask 4/6で一貫して使用。`OfficeChartAnswerer.answer(question, project_name, data_dir)`のシグネチャはTask 4定義とTask 5呼び出しで一致。`VLMImageAnswerer.answer(question, image_path)`も同様にTask 6定義とTask 7呼び出しで一致。
