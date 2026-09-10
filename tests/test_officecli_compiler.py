"""Public-seam tests for the OfficeCLI shape/text compiler slice."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import officecli_html_to_pptx._internal.officecli_compiler as officecli_compiler
from officecli_html_to_pptx._internal.officecli_compiler import (
    OfficeCLICompilationError,
    compile_officecli,
)

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the OfficeCLI compiler tests",
)

_SVG_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
    b'<rect width="20" height="10" fill="#e60012"/></svg>'
).decode("ascii")


def _run_json(*args: str) -> dict:
    result = subprocess.run(
        ["officecli", *args, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return json.loads(result.stdout)


def _run_process(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["officecli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _points(value: str) -> float:
    if value.endswith("pt"):
        return float(value[:-2])
    if value.endswith("cm"):
        return float(value[:-2]) * 72 / 2.54
    raise AssertionError(f"unexpected OfficeCLI length: {value}")


def test_author_css_pixel_line_height_is_not_double_scaled() -> None:
    assert officecli_compiler._line_spacing({"fontSize": 42, "lineHeight": "42px"}) is None
    assert (
        officecli_compiler._line_spacing({"fontSize": 42, "lineHeight": "44.1px"})
        == "1.050x"
    )
    assert (
        officecli_compiler._line_spacing({"fontSize": 18, "lineHeight": "28.8px"})
        == "1.600x"
    )


def test_author_source_fidelity_exceptions_are_narrow_and_anchored() -> None:
    label = {"text": "ELITE", "fontSize": 30, "width": 75, "height": 40}
    number = {"text": "01", "fontSize": 42, "width": 48, "height": 56}
    model_range = {"text": "09K–24K", "fontSize": 19.5, "width": 84, "height": 26}
    ordinary_label = {"text": "ELITE", "fontSize": 15, "width": 75, "height": 40}
    large_title = {"text": "XPRO", "fontSize": 49, "width": 700, "height": 50}
    large_range_title = {"text": "09K–24K", "fontSize": 49, "width": 700, "height": 50}

    assert officecli_compiler._source_fidelity_text_anchor(label) == "left"
    assert officecli_compiler._source_fidelity_text_anchor(number) == "left"
    # A range is ordinary measured text.  It must not activate the old
    # source-fidelity width expansion: in a narrow browser card that moved the
    # entire text box outside its containing shape.
    assert officecli_compiler._source_fidelity_text_anchor(model_range) is None
    assert officecli_compiler._source_fidelity_text_anchor(ordinary_label) is None
    assert officecli_compiler._source_fidelity_text_anchor(large_title) is None
    assert officecli_compiler._source_fidelity_text_anchor(large_range_title) is None
    assert officecli_compiler._source_fidelity_text_bounds(
        label, (10, 20, 50, 12)
    ) == (10, 20, 67.5, 12)
    assert officecli_compiler._source_fidelity_text_bounds(
        model_range, (100, 20, 50, 12)
    ) == (100, 20, 50, 12)


def _wrapped_capacity_html() -> str:
    return """<!doctype html>
<html><head><style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; overflow: hidden; }
  .slide { width: 1920px; height: 1080px; position: relative; background: #ffffff; }
  .body { position: absolute; left: 72px; top: 283px; width: 1776px; height: 713px; }
  .panel { position: absolute; border: 1px solid #D9DEE2; border-radius: 24px; background: #F1F5F8; }
  .card { position: absolute; background: #ffffff; border: 1px solid #D9DEE2;
          border-radius: 18px; padding: 20px; }
  .card h3 { font-size: 29px; line-height: 1.2; color: #E60012; }
  .capacity { font-size: 24px; color: #343B41; font-weight: 600; line-height: 1.4; }
  .small { font-size: 21px; color: #70767B; line-height: 1.4; }
</style></head><body><section class="slide active">
  <div class="body">
    <div class="panel" style="left:0;top:0;width:872px;height:325px"></div>
    <div class="card" style="left:26px;top:110px;width:194.5px;height:187px">
      <h3>T-PLUS</h3>
      <p class="capacity" style="margin-top:22px;font-size:21px">09K / 12K / 18K / 24K</p>
      <p class="small" style="margin-top:12px;font-size:18px">RESIDENTIAL SPLIT</p>
    </div>
    <div class="panel" style="left:904px;top:0;width:872px;height:325px;background:#F6F2EE"></div>
    <div class="card" style="left:930px;top:110px;width:264px;height:187px">
      <h3>TPRO</h3>
      <p class="capacity" style="margin-top:22px;font-size:21px">09K / 12K / 18K / 24K</p>
      <p class="small" style="margin-top:12px;font-size:18px">RESIDENTIAL SPLIT</p>
    </div>
  </div>
</section></body></html>"""


def _author_html() -> str:
    return """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  body { overflow: hidden; font-family: Arial, sans-serif; }
  .slide { width: 960px; height: 540px; display: none; position: relative;
           background: #ffffff; }
  .slide.active { display: block; }
  .card { position: absolute; left: 96px; top: 72px; width: 480px; height: 180px;
          padding: 24px; border: 2px solid #d7d8da; border-radius: 18px;
          background: #fbecee; }
  .card h2 { margin: 0 0 12px; color: #202124; font-size: 30px;
             font-weight: 700; }
  .card p { margin: 0; color: #e60012; font-size: 18px; line-height: 1.5; }
  .accent { position: absolute; left: 624px; top: 72px; width: 6px; height: 180px;
            background: #e60012; }
</style></head><body>
  <section class="slide active">
    <div class="card"><h2>Source Notes</h2><p>Native editable text</p></div>
    <div class="accent"></div>
  </section>
</body></html>"""


@pytest.mark.asyncio
async def test_public_author_compiler_preserves_chromium_soft_wraps_inside_measured_box(
    tmp_path: Path,
):
    html_path = tmp_path / "wrapped-capacity.html"
    output_path = tmp_path / "wrapped-capacity.pptx"
    html_path.write_text(_wrapped_capacity_html(), encoding="utf-8")

    result = await compile_officecli(
        str(html_path), "author", str(output_path), slide_indices=[0]
    )

    capacities = [
        item
        for item in result.manifest["objects"]
        if item["text"] in {"09K / 12K / 18K\n/ 24K", "09K / 12K / 18K / 24K"}
    ]
    assert len(capacities) == 2
    wrapped = next(item for item in capacities if "\n" in item["text"])
    single_line = next(item for item in capacities if "\n" not in item["text"])

    assert wrapped["bounds_pt"] == pytest.approx(
        [59.5, 235.3984, 76.25, 29.390625], abs=0.01
    )
    assert [paragraph["text"] for paragraph in wrapped["paragraphs"]] == [
        "09K / 12K / 18K",
        "/ 24K",
    ]
    assert all(
        paragraph["space_before_pt"] == 0.0
        and paragraph["space_after_pt"] == 0.0
        for paragraph in wrapped["paragraphs"]
    )
    assert single_line["bounds_pt"] == pytest.approx(
        [511.5, 235.3984, 111.0, 14.6953125], abs=0.01
    )

    validation = _run_process("validate", str(output_path))
    assert validation.returncode == 0, validation.stdout + validation.stderr
    issues = _run_json("view", str(output_path), "issues")
    assert issues["data"].get("issues", []) == []


def _picture_deck_html() -> str:
    image_counts = (4, 4, 2, 2, 2, 2, 2, 0)
    slides = []
    for slide_index, image_count in enumerate(image_counts):
        images = "".join(
            f'<img src="{_SVG_DATA_URI}" alt="product {slide_index}-{image_index}" '
            f'style="position:absolute;left:{20 + image_index * 120}px;'
            f'top:30px;width:100px;height:70px;object-fit:contain">'
            for image_index in range(image_count)
        )
        active = " active" if slide_index == 0 else ""
        slides.append(f'<section class="slide{active}">{images}</section>')
    return """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  .slide { width: 960px; height: 540px; display: none; position: relative;
           background: #ffffff; }
  .slide.active { display: block; }
</style></head><body>""" + "".join(slides) + "</body></html>"


def _table_deck_html() -> str:
    return """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  .slide { width: 960px; height: 540px; display: none; position: relative;
           background: #ffffff; }
  .slide.active { display: block; }
  table { position: absolute; left: 80px; top: 60px; width: 500px; height: 230px;
          table-layout: fixed; border-collapse: collapse; font-family: Arial, sans-serif; }
  th, td { height: 25px; padding: 4px; text-align: center; vertical-align: middle;
           border: 1px solid #445566; font-size: 12px; }
  thead tr { height: 30px; }
  th { height: 30px; background: #112233; color: #ffffff; font-weight: 700; font-style: italic; }
  th:nth-child(1), td:nth-child(1) { width: 100px; }
  th:nth-child(2), td:nth-child(2) { width: 120px; }
  th:nth-child(3), td:nth-child(3) { width: 90px; }
  th:nth-child(4), td:nth-child(4) { width: 90px; }
  th:nth-child(5), td:nth-child(5) { width: 100px; }
  td:first-child { text-align: left; padding-left: 12px; background: #eef2f7; }
  tr.accent td { color: #e60012; font-weight: 700; }
</style></head><body>
  <section class="slide active">
    <table aria-label="native table">
      <thead><tr><th>MODEL</th><th>VARIANT</th><th>INDOOR SIZE</th><th>OUTDOOR SIZE</th><th>TCL CODE</th></tr></thead>
      <tbody>
        <tr><td>Capacity Class</td><td>12K, one</td><td>12K</td><td>18K</td><td>Z4U20101035061</td></tr>
        <tr><td>Cooling Capacity</td><td>12000</td><td>18100</td><td>22000</td><td>R32</td></tr>
        <tr><td>Heating Capacity</td><td>3500</td><td>5250</td><td>6400</td><td>3.52 / 2.58</td></tr>
        <tr><td>IDU Dimension</td><td>910×305×195</td><td>1005×321×220</td><td>1005×321×220</td><td>B;two</td></tr>
        <tr><td>ODU Dimension</td><td>795×305×549</td><td>853×349×602</td><td>920×380×699</td><td>R410A</td></tr>
        <tr><td>Refrigerant</td><td>R32</td><td>R32</td><td>R32</td><td>R32</td></tr>
        <tr class="accent"><td>CON</td><td>Φ7×2</td><td>Φ5×2</td><td>Φ7×2</td><td>甲</td></tr>
        <tr class="accent"><td>EVA</td><td>Φ5×1</td><td>Φ7×2</td><td>Φ7×2</td><td>乙</td></tr>
      </tbody>
    </table>
  </section>
    </body></html>"""


def _wbr_dimension_table_html() -> str:
    return """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  .slide { width: 960px; height: 540px; position: relative; background: #ffffff; }
  .slide table { position: absolute; left: 40px; top: 40px; width: 300px;
                 table-layout: fixed; border-collapse: collapse; }
  td { border: 1px solid #445566; padding: 14px; font-family: Arial, sans-serif;
       font-size: 18px; line-height: 1.14; overflow-wrap: anywhere; }
</style></head><body>
  <section class="slide active">
    <table><tbody><tr>
      <td>ODU DIMENSION (MM)</td>
      <td>927×<wbr>380×<wbr>699(Including valve)</td>
    </tr></tbody></table>
  </section>
</body></html>"""


def _paragraph_table_deck_html() -> str:
    return """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  .slide { width: 960px; height: 540px; position: relative; background: #ffffff; }
  table { position: absolute; left: 80px; top: 60px; width: 400px; height: 140px;
          table-layout: fixed; border-collapse: collapse; }
  td { padding: 4px; text-align: center; vertical-align: middle;
       border: 1px solid #445566; font-family: Arial, sans-serif;
       font-size: 16px; line-height: 1.5; }
  td p { margin: 4px 0; }
</style></head><body>
  <section class="slide active">
    <table><tbody><tr><td><p>First paragraph</p><p>Second paragraph</p></td></tr></tbody></table>
  </section>
</body></html>"""


def _unsupported_canvas_html() -> str:
    return """<!doctype html>
<html><head><style>
  .slide { width: 1920px; height: 1080px; position: relative; }
</style></head><body><section class="slide">
  <canvas width="100" height="100"></canvas>
</section></body></html>"""


def _mixed_runs_html() -> str:
    return """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  .slide { width: 960px; height: 540px; position: relative; background: #ffffff; }
  .copy { position: absolute; left: 40px; top: 40px; width: 600px; height: 160px;
          padding: 8px; }
  p { margin: 0; font-family: Arial, sans-serif; font-size: 24px; line-height: 1.25;
      text-align: left; }
  strong { font-family: 'Comic Sans MS', sans-serif; font-size: 30px; font-weight: 700;
           color: #e60012; }
  u { font-family: Arial, sans-serif; font-size: 20px; text-decoration: underline;
      color: #0000ff; }
</style></head><body><section class="slide">
  <div class="copy"><p>Plain <strong>bold</strong><br><u>underlined</u></p></div>
</section></body></html>"""


def _flex_labels_html() -> str:
    return """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  .slide { width: 960px; height: 540px; position: relative; background: #ffffff; }
  .header { position: absolute; left: 40px; top: 30px; width: 500px; height: 60px;
            display: flex; align-items: center; gap: 24px; }
  .header strong { font-size: 24px; }
  .header small { display: block; font-size: 10px; }
  .nav { position: absolute; left: 40px; top: 120px; display: flex; gap: 18px; }
  .nav span { font-size: 12px; }
</style></head><body><section class="slide">
  <div class="header"><strong>AIR CONDITIONER</strong><small>PRODUCT LINE-UP</small></div>
  <div class="nav"><span>COMFORT</span><span>RELIABILITY</span><span>INTELLIGENCE</span></div>
</section></body></html>"""


def _opacity_and_hard_breaks_html() -> str:
    return """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  .slide { width: 960px; height: 540px; position: relative; background: #ffffff; }
  .copy { position: absolute; left: 40px; top: 40px; width: 500px; height: 150px;
          padding: 8px; font-family: Arial, sans-serif; font-size: 24px;
          line-height: 1.25; opacity: 0.55; }
</style></head><body><section class="slide">
  <div class="copy">one<br><br>three<br></div>
</section></body></html>"""


@pytest.mark.asyncio
async def test_public_compiler_preserves_paragraphs_direct_runs_and_underline(
    tmp_path: Path,
):
    html_path = tmp_path / "mixed.html"
    output_path = tmp_path / "mixed.pptx"
    html_path.write_text(_mixed_runs_html(), encoding="utf-8")

    result = await compile_officecli(str(html_path), "author", str(output_path))

    text_objects = [
        item for item in result.manifest["objects"] if item["kind"] in {"shape", "textbox"}
    ]
    assert len(text_objects) == 1
    text_object = text_objects[0]
    assert [paragraph["text"] for paragraph in text_object["paragraphs"]] == [
        "Plain bold",
        "underlined",
    ]
    assert text_object["paragraphs"][0]["runs"][1]["font_family"] != text_object["paragraphs"][0]["runs"][0]["font_family"]
    assert text_object["paragraphs"][0]["runs"][1]["bold"] is True
    assert text_object["paragraphs"][1]["runs"][0]["underline"] == "single"

    document = _run_json("get", str(output_path), "/", "--depth", "5")
    shape = next(
        child
        for child in document["data"]["results"][0]["children"][0]["children"]
        if child["type"] in {"shape", "textbox"}
    )
    assert [paragraph["text"] for paragraph in shape["children"]] == [
        "Plain bold",
        "underlined",
    ]
    actual_runs = [
        run
        for paragraph in shape["children"]
        for run in paragraph["children"]
    ]
    assert [run["text"] for run in actual_runs] == ["Plain ", "bold", "underlined"]
    assert actual_runs[1]["format"]["font.latin"] == text_object["paragraphs"][0]["runs"][1]["font_family"]
    assert actual_runs[1]["format"]["bold"] is True
    assert actual_runs[2]["format"]["underline"] == "single"


@pytest.mark.asyncio
async def test_public_compiler_keeps_flex_children_as_separate_text_objects(
    tmp_path: Path,
):
    html_path = tmp_path / "flex-labels.html"
    output_path = tmp_path / "flex-labels.pptx"
    html_path.write_text(_flex_labels_html(), encoding="utf-8")

    result = await compile_officecli(str(html_path), "author", str(output_path))

    texts = [
        item["text"]
        for item in result.manifest["objects"]
        if item["kind"] in {"shape", "textbox"} and item["text"]
    ]
    assert "AIR CONDITIONER" in texts
    assert "PRODUCT LINE-UP" in texts
    assert "COMFORT" in texts
    assert "RELIABILITY" in texts
    assert "INTELLIGENCE" in texts
    assert "AIR CONDITIONERPRODUCT LINE-UP" not in texts
    assert "COMFORTRELIABILITYINTELLIGENCE" not in texts


@pytest.mark.asyncio
async def test_public_compiler_preserves_text_opacity_and_hard_break_paragraphs(
    tmp_path: Path,
):
    html_path = tmp_path / "breaks.html"
    output_path = tmp_path / "breaks.pptx"
    html_path.write_text(_opacity_and_hard_breaks_html(), encoding="utf-8")

    result = await compile_officecli(str(html_path), "author", str(output_path))

    text_object = next(
        item for item in result.manifest["objects"] if item["kind"] == "textbox"
    )
    assert text_object["properties"]["color"] == "#0000008C"
    assert [paragraph["text"] for paragraph in text_object["paragraphs"]] == [
        "one",
        "",
        "three",
        "",
    ]

    document = _run_json("get", str(output_path), "/", "--depth", "5")
    shape = next(
        child
        for child in document["data"]["results"][0]["children"][0]["children"]
        if child["type"] in {"shape", "textbox"}
    )
    assert shape["format"]["color"] == "#0000008C"
    assert [paragraph["text"] for paragraph in shape["children"]] == [
        "one",
        "",
        "three",
        "",
    ]


@pytest.mark.asyncio
async def test_public_compiler_blocks_visible_canvas_before_measurement(
    tmp_path: Path,
):
    html_path = tmp_path / "unsupported.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(_unsupported_canvas_html(), encoding="utf-8")

    with pytest.raises(OfficeCLICompilationError) as error:
        await compile_officecli(str(html_path), "author", str(output_path))

    assert any(item.code == "unsupported_visible_tag" for item in error.value.diagnostics)
    assert all(item.operation == "contract" for item in error.value.diagnostics)
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_public_author_compiler_emits_native_shapes_and_text(tmp_path: Path):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(_author_html(), encoding="utf-8")

    result = await compile_officecli(
        str(html_path), "author", str(output_path), slide_indices=[0]
    )

    assert result.output_path == str(output_path)
    assert result.profile == "author"
    assert result.slide_count == 1
    assert output_path.exists()

    validation = _run_process("validate", str(output_path))
    assert validation.returncode == 0, validation.stdout + validation.stderr

    document = _run_json("get", str(output_path), "/")
    slides = document["data"]["results"][0]["children"]
    assert len(slides) == 1
    objects = slides[0]["children"]
    assert not any(item["type"] == "picture" for item in objects)
    assert any(
        item["type"] == "shape"
        and item["format"].get("geometry") == "roundRect"
        and item["format"].get("fill") == "#FBECEE"
        for item in objects
    )
    assert {item["text"] for item in objects if item.get("text")} >= {
        "Source Notes",
        "Native editable text",
    }

    names = [item["format"]["name"] for item in objects]
    assert len(names) == len(set(names))
    assert all(name.startswith("slide-001-") for name in names)


@pytest.mark.asyncio
async def test_public_author_compiler_emits_one_editable_native_table(
    tmp_path: Path,
):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(_table_deck_html(), encoding="utf-8")

    result = await compile_officecli(
        str(html_path), "author", str(output_path), slide_indices=[0]
    )

    assert result.slide_count == 1
    assert result.manifest["object_kind_counts"] == {"table": 1}
    table_manifest = result.manifest["objects"][0]
    assert table_manifest["kind"] == "table"
    assert table_manifest["rows"] == 9
    assert table_manifest["columns"] == 5
    assert len(table_manifest["cells"]) == 45
    assert len({cell["name"] for cell in table_manifest["cells"]}) == 45
    assert all(cell["source_object"].startswith(table_manifest["source_object"] + "/tr[") for cell in table_manifest["cells"])
    assert table_manifest["bounds_pt"] == pytest.approx([80, 60, 501, 274])
    header_run = table_manifest["cells"][0]["paragraphs"][0]["runs"][0]
    assert header_run["font_family"] == "Arial"
    assert header_run["font_size_pt"] == pytest.approx(12)
    assert header_run["bold"] is True
    assert header_run["italic"] is True

    slide = _run_json("get", str(output_path), "/slide[1]", "--depth", "1")["data"]["results"][0]
    assert [child["type"] for child in slide["children"]] == ["table"]

    table = _run_json(
        "get", str(output_path), "/slide[1]/table[1]", "--depth", "5"
    )["data"]["results"][0]
    assert table["type"] == "table"
    assert table["format"]["rows"] == 9
    assert table["format"]["cols"] == 5
    assert len(table["children"]) == 9
    assert all(len(row["children"]) == 5 for row in table["children"])
    assert [row["format"]["height"] for row in table["children"]] == [
        "37pt",
        "25pt",
        "37pt",
        "37pt",
        "25pt",
        "37pt",
        "25pt",
        "25pt",
        "25pt",
    ]

    header = table["children"][0]["children"][0]
    assert header["text"] == "MODEL"
    assert header["format"]["fill"] == "#112233"
    assert header["format"]["font"] == "Arial"
    assert header["format"]["size"] == "12pt"
    assert header["format"]["bold"] is True
    assert header["format"]["italic"] is True
    assert header["format"]["color"] == "#FFFFFF"
    assert header["format"]["align"] == "center"
    assert header["format"]["valign"] == "center"
    assert header["format"]["padding.left"] == "4pt"
    assert header["format"]["border.all"] == "1pt solid #445566"
    assert 'i="1"' in header["format"]["txBodyRaw"]
    assert 'typeface="Arial"' in header["format"]["txBodyRaw"]

    first_body_cell = table["children"][1]["children"][0]
    assert first_body_cell["text"] == "Capacity Class"
    assert first_body_cell["format"]["padding.left"] == "12pt"
    assert _run_json("query", str(output_path), "table")["data"]["matches"] == 1


@pytest.mark.asyncio
async def test_public_author_compiler_accepts_wbr_dimension_text_ranges(
    tmp_path: Path,
):
    html_path = tmp_path / "wbr-dimension.html"
    output_path = tmp_path / "wbr-dimension.pptx"
    html_path.write_text(_wbr_dimension_table_html(), encoding="utf-8")

    result = await compile_officecli(
        str(html_path), "author", str(output_path), slide_indices=[0]
    )

    assert result.manifest["object_kind_counts"] == {"table": 1}
    table = result.manifest["objects"][0]
    assert table["cells"][1]["text"] == "927×380×699(Including valve)"
    validation = _run_process("validate", str(output_path))
    assert validation.returncode == 0, validation.stdout + validation.stderr


@pytest.mark.asyncio
async def test_native_table_projects_uniform_cell_paragraph_properties(
    tmp_path: Path,
):
    html_path = tmp_path / "paragraph-table.html"
    output_path = tmp_path / "paragraph-table.pptx"
    html_path.write_text(_paragraph_table_deck_html(), encoding="utf-8")

    result = await compile_officecli(
        str(html_path), "author", str(output_path), slide_indices=[0]
    )

    cell = result.manifest["objects"][0]["cells"][0]
    assert [paragraph["text"] for paragraph in cell["paragraphs"]] == [
        "First paragraph",
        "Second paragraph",
    ]
    assert cell["props"]["align"] == "center"
    assert cell["props"]["linespacing"] == "1.125x"
    assert cell["props"]["spacebefore"] == "4.0000pt"
    assert cell["props"]["spaceafter"] == "4.0000pt"

    table = _run_json(
        "get", str(output_path), "/slide[1]/table[1]", "--depth", "5"
    )["data"]["results"][0]
    rendered_cell = table["children"][0]["children"][0]
    assert rendered_cell["format"]["align"] == "center"
    assert rendered_cell["format"]["lineSpacing"] == "1.125x"
    assert rendered_cell["format"]["spaceBefore"] == "4pt"
    assert rendered_cell["format"]["spaceAfter"] == "4pt"
    assert rendered_cell["format"]["txBodyRaw"].count("<a:p>") == 2
    assert "First paragraph" in rendered_cell["format"]["txBodyRaw"]
    assert "Second paragraph" in rendered_cell["format"]["txBodyRaw"]


@pytest.mark.asyncio
async def test_native_table_rejects_non_unit_cell_spans_without_output(
    tmp_path: Path,
):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(
        _table_deck_html().replace("<td>12K, one</td>", '<td colspan="2">12K, one</td>'),
        encoding="utf-8",
    )

    with pytest.raises(OfficeCLICompilationError) as error:
        await compile_officecli(
            str(html_path), "author", str(output_path), slide_indices=[0]
        )

    assert error.value.diagnostics[0].code == "unsupported_table_span"
    assert error.value.diagnostics[0].source_object
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_public_author_compiler_emits_svg_data_uri_as_picture(
    tmp_path: Path,
):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(
        _author_html().replace(
            '<div class="accent"></div>',
            f'<img class="accent" src="{_SVG_DATA_URI}" alt="red mark">',
        ),
        encoding="utf-8",
    )

    result = await compile_officecli(
        str(html_path), "author", str(output_path), slide_indices=[0]
    )

    assert result.manifest["object_kind_counts"]["picture"] == 1
    document = _run_json("get", str(output_path), "/slide[1]/picture[1]")
    picture = document["data"]["results"][0]
    assert picture["type"] == "picture"
    assert picture["format"]["name"].startswith("slide-001-picture-")
    assert picture["format"]["contentType"].startswith("image/")
    assert picture["format"]["alt"] == "red mark"
    if picture["format"]["contentType"] == "image/png":
        assert picture["format"]["fileSize"] > 67
    assert _points(picture["format"]["x"]) == pytest.approx(624)
    assert _points(picture["format"]["y"]) == pytest.approx(72)
    assert _points(picture["format"]["width"]) == pytest.approx(6)
    assert _points(picture["format"]["height"]) == pytest.approx(180)


@pytest.mark.asyncio
async def test_public_author_compiler_preserves_four_and_eighteen_picture_inventory(
    tmp_path: Path,
):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(_picture_deck_html(), encoding="utf-8")

    result = await compile_officecli(str(html_path), "author", str(output_path))

    assert result.slide_count == 8
    assert result.manifest["object_kind_counts"] == {"picture": 18}
    pictures = _run_json("query", str(output_path), "picture")["data"]["results"]
    assert len(pictures) == 18
    first_slide = _run_json(
        "get", str(output_path), "/slide[1]", "--depth", "1"
    )["data"]["results"][0]
    assert sum(child["type"] == "picture" for child in first_slide["children"]) == 4


@pytest.mark.asyncio
async def test_public_author_compiler_selects_source_slide_without_rescaling(
    tmp_path: Path,
):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html = _author_html().replace(
        "</body></html>",
        '<section class="slide"><div class="card"><h2>Second</h2></div></section>'
        "</body></html>",
    )
    html_path.write_text(html, encoding="utf-8")

    result = await compile_officecli(
        str(html_path), "author", str(output_path), slide_indices=[1]
    )

    assert result.slide_count == 1
    document = _run_json("get", str(output_path), "/")
    slide = document["data"]["results"][0]["children"][0]
    assert slide["format"]["name"] == "slide-002"
    card = next(
        item
        for item in slide["children"]
        if item["type"] == "shape" and item["format"].get("geometry") == "roundRect"
    )
    assert _points(card["format"]["x"]) == pytest.approx(96)
    assert _points(card["format"]["y"]) == pytest.approx(72)


@pytest.mark.asyncio
async def test_public_author_compiler_does_not_overwrite_existing_output(
    tmp_path: Path,
):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(_author_html(), encoding="utf-8")
    output_path.write_bytes(b"keep this file")

    with pytest.raises(FileExistsError, match="Output already exists"):
        await compile_officecli(
            str(html_path), "author", str(output_path), slide_indices=[0]
        )

    assert output_path.read_bytes() == b"keep this file"


@pytest.mark.asyncio
async def test_undecodable_picture_has_source_diagnostic_and_no_output(
    tmp_path: Path,
):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(
        _author_html().replace(
            "<div class=\"accent\"></div>",
            '<img class="accent" src="data:image/png;base64,AA==" '
            'style="width: 12px; height: 12px;" alt="unsupported">',
        ),
        encoding="utf-8",
    )

    with pytest.raises(OfficeCLICompilationError) as error:
        await compile_officecli(
            str(html_path), "author", str(output_path), slide_indices=[0]
        )

    assert "source slide 1" in str(error.value)
    assert "undecodable_picture" in error.value.diagnostics[0].code
    assert error.value.diagnostics[0].source_object
    assert not output_path.exists()
