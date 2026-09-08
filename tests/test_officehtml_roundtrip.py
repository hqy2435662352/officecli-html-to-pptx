"""Public-seam tests for the OfficeCLI HTML reverse profile."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from html_to_pptx import compile_officecli


_DEFAULT_AUTHOR_HTML = (
    Path(r"D:\Opencodeworkspace\html-to-pptx\workspace\algeria\algeria")
    / "Algeria_AC_Product_Portfolio_20260906_v3_pptx.html"
)
_AUTHOR_HTML = Path(
    os.environ.get("HTML_TO_PPTX_ALGERIA_AUTHOR_HTML", _DEFAULT_AUTHOR_HTML)
)

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the OfficeHTML compiler tests",
)

_SVG_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
    b'<rect width="20" height="10" fill="#e60012"/></svg>'
).decode("ascii")


def _roundtrip_author_html() -> str:
    return f"""<!doctype html>
<html><head><style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  body {{ overflow: hidden; font-family: Arial, sans-serif; }}
  .slide {{ width: 960px; height: 540px; display: none; position: relative;
           background: #ffffff; }}
  .slide.active {{ display: block; }}
  .card {{ position: absolute; left: 48px; top: 36px; width: 320px; height: 120px;
          padding: 12px; border: 2px solid #d7d8da; border-radius: 12px;
          background: #fbecee; }}
  .card h2 {{ margin: 0 0 6px; color: #202124; font-size: 24px;
             font-weight: 700; }}
  .card p {{ margin: 0; color: #e60012; font-size: 16px; line-height: 1.5; }}
  img {{ position: absolute; left: 420px; top: 36px; width: 80px; height: 40px; }}
  table {{ position: absolute; left: 48px; top: 210px; width: 360px; height: 80px;
           table-layout: fixed; border-collapse: collapse; font-family: Arial, sans-serif; }}
  td {{ height: 40px; padding: 4px; text-align: center; vertical-align: middle;
        border: 1px solid #445566; font-size: 12px; }}
  td:nth-child(1) {{ width: 180px; }}
  td:nth-child(2) {{ width: 180px; }}
</style></head><body>
  <section class="slide active">
    <div class="card"><h2>Source Notes</h2><p>Native editable text</p></div>
    <img src="{_SVG_DATA_URI}" alt="red mark">
    <table><tbody><tr><td>MODEL</td><td>Φ7×2</td></tr><tr><td>STATUS</td><td>Ready</td></tr></tbody></table>
  </section>
</body></html>"""


def _project_to_officehtml(source: Path, destination: Path) -> None:
    result = subprocess.run(
        ["officecli", "view", str(source), "html", "-o", str(destination)],
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        result.stdout.decode("utf-8", errors="replace")
        + result.stderr.decode("utf-8", errors="replace")
    )


@pytest.mark.asyncio
async def test_public_officehtml_profile_round_trips_supported_objects(
    tmp_path: Path,
) -> None:
    author_html = tmp_path / "author.html"
    pptx_a = tmp_path / "a.pptx"
    officehtml = tmp_path / "a.html"
    pptx_b = tmp_path / "b.pptx"
    author_html.write_text(_roundtrip_author_html(), encoding="utf-8")

    first = await compile_officecli(str(author_html), "author", str(pptx_a))
    _project_to_officehtml(pptx_a, officehtml)
    second = await compile_officecli(str(officehtml), "officehtml", str(pptx_b))

    assert second.profile == "officehtml"
    assert second.manifest["slide_count"] == first.manifest["slide_count"]
    assert second.manifest["object_kind_counts"] == first.manifest[
        "object_kind_counts"
    ]
    assert [obj["name"] for obj in second.manifest["objects"]] == [
        obj["name"] for obj in first.manifest["objects"]
    ]
    assert [obj["text"] for obj in second.manifest["objects"]] == [
        obj["text"] for obj in first.manifest["objects"]
    ]

    first_tables = [
        (obj["rows"], obj["columns"], [cell["text"] for cell in obj["cells"]])
        for obj in first.manifest["objects"]
        if obj["kind"] == "table"
    ]
    second_tables = [
        (obj["rows"], obj["columns"], [cell["text"] for cell in obj["cells"]])
        for obj in second.manifest["objects"]
        if obj["kind"] == "table"
    ]
    assert second_tables == first_tables

    for first_object, second_object in zip(
        first.manifest["objects"], second.manifest["objects"]
    ):
        assert second_object["bounds_pt"] == pytest.approx(
            first_object["bounds_pt"], abs=1.0
        )

    validation = subprocess.run(
        ["officecli", "validate", str(pptx_b)],
        capture_output=True,
        timeout=120,
    )
    assert validation.returncode == 0, (
        validation.stdout.decode("utf-8", errors="replace")
        + validation.stderr.decode("utf-8", errors="replace")
    )


@pytest.mark.asyncio
async def test_officehtml_profile_does_not_treat_viewer_chrome_as_objects(
    tmp_path: Path,
) -> None:
    officehtml = tmp_path / "projection.html"
    output = tmp_path / "output.pptx"
    officehtml.write_text(
        """<!doctype html><html><body>
        <div class="sidebar"><button data-path="/viewer/button">Ignore</button></div>
        <div class="main"><div class="slide-container" data-slide="1">
          <div class="slide" style="background:#FFFFFF">
            <div class="shape" style="left:0pt;top:0pt;width:20pt;height:20pt;background:#000000">master</div>
            <div class="picture" data-path="/slide[1]/shape[@id=2]" style="left:12pt;top:18pt;width:60pt;height:24pt;background:#E60012">
              <div class="shape-text valign-center"><div class="para" style="text-align:center;font-size:12pt"><span style="font-size:12pt;color:#FFFFFF">Owned</span></div></div>
            </div>
          </div>
        </div></div>
        <script>document.body.append('Ignore')</script>
        </body></html>""",
        encoding="utf-8",
    )

    result = await compile_officecli(str(officehtml), "officehtml", str(output))

    assert result.manifest["object_kind_counts"] == {"shape": 1}
    assert result.manifest["objects"][0]["source_object"] == "/slide[1]/shape[@id=2]"
    assert result.manifest["objects"][0]["text"] == "Owned"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("projected_line_height", "expected_line_spacing"),
    [("1.4", "1.050x"), ("0.8", "0.600x")],
)
async def test_officehtml_profile_restores_unitless_line_height_projection(
    tmp_path: Path,
    projected_line_height: str,
    expected_line_spacing: str,
) -> None:
    officehtml = tmp_path / "projection.html"
    output = tmp_path / "output.pptx"
    officehtml.write_text(
        f"""<!doctype html><html><body>
        <div class="slide" style="width:960pt;height:540pt;background:#FFFFFF">
          <div class="shape" data-path="/slide[1]/shape[@id=1]"
               style="left:10pt;top:10pt;width:200pt;height:60pt">
            <div class="shape-text valign-top">
              <div class="para" style="text-align:left;font-size:12pt;line-height:{projected_line_height}">
                <span style="font-size:12pt;color:#202124">Unitless spacing</span>
              </div>
            </div>
          </div>
        </div></body></html>""",
        encoding="utf-8",
    )

    result = await compile_officecli(str(officehtml), "officehtml", str(output))

    assert len(result.manifest["objects"]) == 1
    obj = result.manifest["objects"][0]
    assert obj["properties"]["lineSpacing"] == expected_line_spacing
    assert obj["paragraphs"][0]["line_spacing"] == expected_line_spacing


def _normalized_text(value: object) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _AUTHOR_HTML.is_file(),
    reason="The external Algeria Author HTML is required",
)
async def test_algeria_officehtml_roundtrip_preserves_the_supported_manifest(
    tmp_path: Path,
) -> None:
    pptx_a = tmp_path / "algeria-a.pptx"
    officehtml = tmp_path / "algeria-a.html"
    pptx_b = tmp_path / "algeria-b.pptx"

    first = await compile_officecli(str(_AUTHOR_HTML), "author", str(pptx_a))
    _project_to_officehtml(pptx_a, officehtml)
    second = await compile_officecli(str(officehtml), "officehtml", str(pptx_b))

    assert second.manifest["slide_count"] == 8
    assert second.manifest["object_kind_counts"] == {
        "shape": 89,
        "textbox": 154,
        "picture": 18,
        "table": 9,
    }
    assert second.manifest["object_kind_counts"] == first.manifest[
        "object_kind_counts"
    ]
    assert [obj["name"] for obj in second.manifest["objects"]] == [
        obj["name"] for obj in first.manifest["objects"]
    ]

    for left, right in zip(
        first.manifest["objects"], second.manifest["objects"]
    ):
        assert _normalized_text(left["text"]) == _normalized_text(right["text"])
        assert right["bounds_pt"] == pytest.approx(left["bounds_pt"], abs=1.0)
        if left["kind"] == "table":
            assert (right["rows"], right["columns"]) == (
                left["rows"],
                left["columns"],
            )
            assert right["column_widths_pt"] == pytest.approx(
                left["column_widths_pt"], abs=0.5
            )
            assert right["row_heights_pt"] == pytest.approx(
                left["row_heights_pt"], abs=0.5
            )
            assert [
                _normalized_text(cell["text"]) for cell in right["cells"]
            ] == [
                _normalized_text(cell["text"]) for cell in left["cells"]
            ]
            assert all(
                cell["source_object"].startswith(
                    f"{right['source_object']}/"
                )
                for cell in right["cells"]
            )

    validation = subprocess.run(
        ["officecli", "validate", str(pptx_b)],
        capture_output=True,
        timeout=120,
    )
    assert validation.returncode == 0, (
        validation.stdout.decode("utf-8", errors="replace")
        + validation.stderr.decode("utf-8", errors="replace")
    )
