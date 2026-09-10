"""Public-seam tests for V03-01 Chromium soft wrap and paragraph layout fidelity.

Every expectation below is an independent literal taken from the accepted
fixture (``tests/fixtures/v03_01_rich_text_paragraphs.html``) or from an
explicitly written expected paragraph-layout model.  Nothing is derived from the
compiler's own output.

The slice under test is Recorded Decision V03-01-004: V03-01 preserves V0.2
newline semantics and the existing ``visualLines`` behaviour.  A ``<br>`` is a
native paragraph boundary, soft wrapping stays browser/layout behaviour, and
**no new soft-line-break representation is introduced**.  Chromium-decided
visual lines therefore survive as the native paragraph boundaries of the one
authored text object, and the paragraph-layout surface that checking and
lowering really implement is declared by ``capabilities --json``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterator, Mapping

import pytest

from officecli_html_to_pptx._internal.officecli_compiler import compile_officecli
from officecli_html_to_pptx.application import get_capabilities
from officecli_html_to_pptx.contract import (
    LINE_HEIGHT_PX_PROJECTION_SCALE,
    _resolve_text_alignment,
)

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the V03-01 soft-wrap tests",
)

FIXTURE = Path(__file__).parent / "fixtures" / "v03_01_rich_text_paragraphs.html"

# ---------------------------------------------------------------------------
# Independent expected literals for the accepted fixture
# ---------------------------------------------------------------------------

# ``#soft-wrap`` is the seventh top-level slide child of the fixture.
SOFT_WRAP_SOURCE = "slide[1]/div[7]"

# The fixture declares #soft-wrap at left:170px top:640px width:650px
# height:220px on the 1920x1080 CSS canvas, which is the 960x540pt widescreen
# canvas at scale 0.5.
SOFT_WRAP_BOUNDS_PT = [85.0, 320.0, 325.0, 110.0]
# font-size: 31px at scale 0.5.
SOFT_WRAP_FONT_SIZE_PT = 15.5
SOFT_WRAP_COLOR = "#24324A"
# line-height: 1.35 on a 31px font computes to 41.85px; the existing V0.2
# projection divides that 0.75-scaled CSS pixel value by the 15.5pt font size
# and rounds to three decimals.  1.35 x 0.75 = 1.0125 -> 1.013.
SOFT_WRAP_LINE_SPACING = "1.013x"

# The authored source of #soft-wrap is one paragraph with no <br>:
#
#     Chromium decides this bilingual soft wrap：浏览器决定视觉换行，
#     PowerPoint 保留可编辑段落与原始阅读顺序。
#
# Chromium forms three visual lines inside the 650px box.  They are the native
# paragraph boundaries, in source order, and nothing is inserted between them.
EXPECTED_VISUAL_LINES: tuple[str, ...] = (
    "Chromium decides this bilingual soft wrap：浏",
    "览器决定视觉换行，PowerPoint 保留可编辑段",
    "落与原始阅读顺序。",
)
EXPECTED_AUTHORED_TEXT = (
    "Chromium decides this bilingual soft wrap：浏览器决定视觉换行，"
    "PowerPoint 保留可编辑段落与原始阅读顺序。"
)
EXPECTED_OBJECT_TEXT = "\n".join(EXPECTED_VISUAL_LINES)

# The neighbouring released-V0.2 line-height projections that this ticket must
# not disturb (criterion 11).  #mixed-runs is 30px/1.45 and #paragraphs is
# 28px/1.35; both keep the established CSS-pixel projection.
MIXED_RUNS_SOURCE = "slide[1]/div[3]"
MIXED_RUNS_LINE_SPACING = "1.087x"
PARAGRAPHS_SOURCE = "slide[1]/div[5]"
PARAGRAPHS_LINE_SPACING = "1.012x"

# ---------------------------------------------------------------------------
# Independent expected literals for the authored paragraph-spacing input
# ---------------------------------------------------------------------------

# A fresh authored input, never the accepted fixture: one standalone Author
# text block plus one 1x1 native table cell.  Both are 31px "Segoe UI" on a
# 1.35 line-height, i.e. the same sample as #soft-wrap.
LAYOUT_HTML = """<!doctype html>
<html><head><style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  .slide {{ width: 1920px; height: 1080px; position: relative; background: #ffffff; }}
  .copy {{ position: absolute; left: 120px; top: 120px; width: 800px; height: 180px;
          font-family: "Segoe UI", sans-serif; font-size: 31px; line-height: 1.35;
          color: #24324a; }}
  .copy p {{ margin: {block_margin}px 0 {block_margin}px 0; }}
  .cell {{ padding: 0; text-align: right; vertical-align: middle;
          font-family: "Segoe UI", sans-serif; font-size: 31px; line-height: 1.35;
          color: #24324a; }}
  .cell p {{ margin: {top_margin}px 0 {bottom_margin}px 0; }}
</style></head><body><section class="slide active" style="width: 1920px; height: 1080px;">
  <div class="copy"><p>Standalone spacing line</p></div>
  <table style="position: absolute; left: 1100px; top: 120px; width: 700px;
                table-layout: fixed; border-collapse: collapse;">
    <tr><td class="cell"><p>Native spacing one</p><p>Native spacing two</p></td></tr>
  </table>
</section></body></html>"""

# 24px of paragraph margin above and 36px below on the 0.5pt-per-px canvas.
AUTHORED_TOP_MARGIN_PX = 24
AUTHORED_BOTTOM_MARGIN_PX = 36
EXPECTED_SPACE_BEFORE_PT = [12.0, 12.0]
EXPECTED_SPACE_AFTER_PT = [18.0, 18.0]
EXPECTED_SPACE_BEFORE_READBACK = "12pt"
EXPECTED_SPACE_AFTER_READBACK = "18pt"
EXPECTED_CELL_PARAGRAPHS = ("Native spacing one", "Native spacing two")
EXPECTED_CELL_LINE_SPACING = "1.013x"
# The standalone text body keeps its block's margin *in its measured bounds*
# instead of re-emitting it as native paragraph spacing, so its margin must not
# be counted twice.  12px at scale 0.5 is 6pt.
STANDALONE_BLOCK_MARGIN_PX = 12
EXPECTED_STANDALONE_SPACE_BEFORE_PT = 0.0
EXPECTED_STANDALONE_SPACE_AFTER_PT = 0.0
EXPECTED_STANDALONE_TOP_MARGIN_PT = 6.0

# The independently written alignment surface; the manifest must declare
# exactly this, and the checker/lowering resolver must map each value to itself
# plus the two direction-relative CSS values.
EXPECTED_ALIGNMENT_VALUES = ["center", "justify", "left", "right"]
EXPECTED_ALIGNMENT_DEFAULT = "left"
EXPECTED_ALIGNMENT_MAPPING = {
    "start": {"ltr": "left", "rtl": "right"},
    "end": {"ltr": "right", "rtl": "left"},
}

# One non-default declared alignment on the same standalone block, so the
# tracer proves a declared value really lowers and reads back.
ALIGNMENT_HTML = f"""<!doctype html>
<html><head><style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  .slide {{ width: 1920px; height: 1080px; position: relative; background: #ffffff; }}
  .copy {{ position: absolute; left: 120px; top: 120px; width: 800px; height: 180px;
          font-family: "Segoe UI", sans-serif; font-size: 31px; line-height: 1.35;
          text-align: center; color: #24324a; }}
</style></head><body><section class="slide active" style="width: 1920px; height: 1080px;">
  <div class="copy">Centered native paragraph</div>
</section></body></html>"""
ALIGNMENT_SOURCE = "slide[1]/div[1]"

# The declared soft-wrap model: Chromium visual lines become native paragraph
# boundaries of the one authored text object.  No soft-line-break object,
# marker, or per-line text box may be introduced.
EXPECTED_SOFT_WRAP_MODEL = {
    "representation": "chromium-visual-lines-as-native-paragraph-boundaries",
    "measured_property": "visualLines",
    "unit": "native-paragraph",
    "requires": [
        "one-source-paragraph",
        "one-source-run",
        "visual-lines-rejoin-to-the-authored-text",
        "ordered-soft-wrap-sequence",
    ],
    "fallback": "authored-paragraph-when-the-visual-lines-are-not-a-repartition",
    "object_per_source": 1,
    "object_kind": "textbox",
    "new_soft_line_break_representation": False,
}

# ---------------------------------------------------------------------------
# Public readback helpers
# ---------------------------------------------------------------------------


def _run_officecli(*args: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["officecli", *args, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return json.loads(completed.stdout)


def _walk(node: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    yield node
    for child in node.get("children", []) or []:
        if isinstance(child, Mapping):
            yield from _walk(child)


def _slide_nodes(pptx: Path) -> list[dict[str, Any]]:
    document = _run_officecli("get", str(pptx), "/slide[1]", "--depth", "6")
    slide = document["data"]["results"][0]
    return list(_walk(slide))


def _object_by_name(pptx: Path, name: str) -> dict[str, Any]:
    for node in _slide_nodes(pptx):
        if (node.get("format") or {}).get("name") == name:
            return node
    raise AssertionError(f"OfficeCLI readback has no object named {name}")


def _readback_table_cell(pptx: Path) -> dict[str, Any]:
    """Return the first native table cell; OfficeCLI gives cells no name."""
    for node in _slide_nodes(pptx):
        if node.get("type") == "tc":
            return node
    raise AssertionError("OfficeCLI readback has no native table cell")


def _shape_by_source(
    manifest: Mapping[str, Any], source_object: str
) -> dict[str, Any]:
    matches = [
        item
        for item in manifest["objects"]
        if item["source_object"] == source_object
        and item["kind"] in {"shape", "textbox"}
    ]
    assert len(matches) == 1, (
        f"expected exactly one text-bearing object for {source_object}, got "
        f"{[(item['name'], item['kind']) for item in manifest['objects']]}"
    )
    return matches[0]


def _objects_by_source(
    manifest: Mapping[str, Any], source_object: str
) -> list[dict[str, Any]]:
    return [
        item for item in manifest["objects"] if item["source_object"] == source_object
    ]


def _readback_paragraphs(node: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read back paragraphs with their native alignment and spacing format."""
    return [
        {
            "text": paragraph.get("text", ""),
            "format": paragraph.get("format") or {},
        }
        for paragraph in node.get("children", []) or []
        if paragraph.get("type") == "paragraph"
    ]


def _write_layout_html(tmp_path: Path) -> Path:
    html = tmp_path / "paragraph-layout.html"
    html.write_text(
        LAYOUT_HTML.format(
            block_margin=STANDALONE_BLOCK_MARGIN_PX,
            top_margin=AUTHORED_TOP_MARGIN_PX,
            bottom_margin=AUTHORED_BOTTOM_MARGIN_PX,
        ),
        encoding="utf-8",
    )
    return html


# ---------------------------------------------------------------------------
# Criterion 1: the capability authority declares the paragraph-layout surface
# ---------------------------------------------------------------------------


def test_capabilities_declare_the_paragraph_layout_surface() -> None:
    payload = get_capabilities().as_dict()
    assert payload["status"] == "PASS"
    contract = payload["data"]["contract"]
    surface = contract["paragraph_layout_surface"]

    assert surface["alignment"]["values"] == EXPECTED_ALIGNMENT_VALUES
    assert surface["alignment"]["default"] == EXPECTED_ALIGNMENT_DEFAULT
    assert surface["alignment"]["mapping"] == EXPECTED_ALIGNMENT_MAPPING
    assert surface["alignment"]["property"] == "text-align"

    assert surface["line_height"]["property"] == "line-height"
    assert surface["line_height"]["native"] == "lineSpacing"
    # The released V0.2 CSS-pixel projection is declared, not invented here.
    assert surface["line_height"]["unitless"] == "line-height / font-size"
    assert surface["line_height"]["length_with_px_projection"] == (
        "(line-height x 0.75) / font-size"
    )
    assert surface["line_height"]["length_with_source_fidelity_projection"] == (
        "line-height / font-size"
    )
    assert surface["line_height"]["omitted_when_ratio_within"] == 0.01
    assert surface["line_height"]["precision"] == "0.001x"
    assert surface["line_height"]["default"] == "absent"
    # The declaration quotes the released projection scale as data, and the
    # compiler multiplies by that same constant, so the published number cannot
    # drift from the one the lowering pass applies.
    assert surface["line_height"]["length_with_px_projection"] == (
        f"(line-height x {LINE_HEIGHT_PX_PROJECTION_SCALE}) / font-size"
    )
    assert LINE_HEIGHT_PX_PROJECTION_SCALE == 0.75
    assert surface["line_height"]["source_fidelity_text"] == (
        "ALGERIA PRODUCT LINE-UP"
    )
    assert surface["line_height"]["source_fidelity_min_font_size_px"] == 45.0

    assert surface["paragraph_spacing"]["properties"] == ["margin-top", "margin-bottom"]
    assert surface["paragraph_spacing"]["native"] == ["spaceBefore", "spaceAfter"]
    assert surface["paragraph_spacing"]["unit"] == "pt"
    assert surface["paragraph_spacing"]["projection"] == (
        "css-margin-px-to-native-paragraph-points"
    )
    assert surface["paragraph_spacing"]["default"] == "absent"
    assert surface["paragraph_spacing"]["emitted_at"] == [
        "table-cell-paragraph"
    ]
    assert surface["paragraph_spacing"]["standalone_text_block"] == (
        "margins-are-already-in-the-measured-bounds"
    )

    assert surface["soft_wrap"] == EXPECTED_SOFT_WRAP_MODEL

    # The declared surface is the same data the checker classifies and the
    # lowering pass projects: every named CSS property really is a supported,
    # rendered property of this Contract.
    for name in (
        "text-align",
        "line-height",
        "margin-top",
        "margin-bottom",
    ):
        assert contract["css_properties"][name] == "rendered"
    assert "textbox" in contract["object_kinds"]


def test_declared_alignment_values_are_the_ones_that_resolve() -> None:
    """The declaration is the data the checker/lowering can be held to."""
    declared = get_capabilities().as_dict()["data"]["contract"][
        "paragraph_layout_surface"
    ]["alignment"]
    assert declared["values"] == EXPECTED_ALIGNMENT_VALUES

    # Every declared native value is its own resolution, so no declared value
    # can be one the compiler would silently rewrite.
    assert [
        _resolve_text_alignment({"textAlign": value, "direction": "ltr"})
        for value in declared["values"]
    ] == declared["values"]
    # The two direction-relative CSS values resolve into the declared set.
    for css_value, expected in EXPECTED_ALIGNMENT_MAPPING.items():
        for direction, native in expected.items():
            assert native in declared["values"]
            assert _resolve_text_alignment(
                {"textAlign": css_value, "direction": direction}
            ) == native
    # An unknown or absent value falls back to the declared default.
    assert declared["default"] in declared["values"]
    assert _resolve_text_alignment({"textAlign": "bogus"}) == declared["default"]
    assert _resolve_text_alignment({}) == declared["default"]


# ---------------------------------------------------------------------------
# Criterion 2: the supported surface passes public checking
# ---------------------------------------------------------------------------


def test_public_check_accepts_the_soft_wrap_and_layout_surface() -> None:
    from officecli_html_to_pptx.contract import check_contract

    report = check_contract(FIXTURE, "author")

    assert report.status == "PASS"
    assert report.diagnostics == ()


def test_public_check_accepts_the_authored_spacing_input(tmp_path: Path) -> None:
    from officecli_html_to_pptx.contract import check_contract

    report = check_contract(_write_layout_html(tmp_path), "author")

    assert report.status == "PASS"
    assert report.diagnostics == ()


# ---------------------------------------------------------------------------
# Criteria 3, 4, 5, 7: one native object, visual-line paragraphs, no new model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_wrapped_paragraph_stays_one_native_text_object(
    tmp_path: Path,
) -> None:
    """Criterion 3: one authored text object, never one textbox per line."""
    output = tmp_path / "soft-wrap-object.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    matches = _objects_by_source(result.manifest, SOFT_WRAP_SOURCE)
    assert len(matches) == 1, (
        "the soft-wrapped source paragraph must lower to exactly one object, got "
        f"{[(item['name'], item['kind']) for item in matches]}"
    )
    manifest_object = matches[0]
    assert manifest_object["kind"] == "textbox"
    assert manifest_object["bounds_pt"] == SOFT_WRAP_BOUNDS_PT
    assert manifest_object["properties"]["size"] == "15.5000pt"
    assert manifest_object["text"] == EXPECTED_OBJECT_TEXT

    # No per-line textbox and no raster substitute for the paragraph.
    assert result.manifest["object_kind_counts"].get("picture") is None
    line_names = set(EXPECTED_VISUAL_LINES)
    assert not [
        item
        for item in result.manifest["objects"]
        if item["kind"] in {"textbox", "shape"} and item.get("text") in line_names
    ]
    assert not [
        node
        for node in _slide_nodes(output)
        if node.get("type") in {"picture", "svg"}
        or str(node.get("path", "")).startswith("/slide[1]/picture")
    ]
    # The native paragraph count of the object is the visual-line count; a
    # per-line textbox flattening would show up as one text object per line.
    assert len(_readback_paragraphs(
        _object_by_name(output, manifest_object["name"])
    )) == len(EXPECTED_VISUAL_LINES)

    readback = _object_by_name(output, manifest_object["name"])
    assert readback["type"] == "textbox"
    assert readback["format"]["x"] == "85pt"
    assert readback["format"]["y"] == "320pt"
    assert readback["format"]["width"] == "325pt"
    assert readback["format"]["height"] == "110pt"
    assert readback["format"]["size"] == "15.5pt"
    assert readback["text"] == EXPECTED_OBJECT_TEXT


@pytest.mark.asyncio
async def test_chromium_visual_lines_are_the_native_paragraph_boundaries(
    tmp_path: Path,
) -> None:
    """Criterion 4 and 7: source order, one run each, no invented separators."""
    output = tmp_path / "soft-wrap-lines.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, SOFT_WRAP_SOURCE)
    assert [
        paragraph["text"] for paragraph in manifest_object["paragraphs"]
    ] == list(EXPECTED_VISUAL_LINES)
    assert len(manifest_object["paragraphs"]) == len(EXPECTED_VISUAL_LINES)
    assert [
        [run["text"] for run in paragraph["runs"]]
        for paragraph in manifest_object["paragraphs"]
    ] == [[line] for line in EXPECTED_VISUAL_LINES]
    # Re-joining the visual lines reproduces the authored paragraph exactly:
    # this is the repartition requirement the fallback tests, and it proves the
    # lowering split a real browser wrap instead of inventing a break.
    assert "".join(
        paragraph["text"] for paragraph in manifest_object["paragraphs"]
    ) == EXPECTED_AUTHORED_TEXT
    assert "\n".join(
        paragraph["text"] for paragraph in manifest_object["paragraphs"]
    ) == EXPECTED_OBJECT_TEXT

    readback = _object_by_name(output, manifest_object["name"])
    readback_paragraphs = _readback_paragraphs(readback)
    assert [
        paragraph["text"] for paragraph in readback_paragraphs
    ] == list(EXPECTED_VISUAL_LINES)
    # Each visual line stays one editable native run holding the whole line.
    assert [
        [run["text"] for run in paragraph.get("children", [])]
        for paragraph in readback["children"]
    ] == [[line] for line in EXPECTED_VISUAL_LINES]


@pytest.mark.asyncio
async def test_no_soft_line_break_representation_is_introduced(
    tmp_path: Path,
) -> None:
    """Criterion 5: the visual-line model is the only newline source.

    The authored paragraph has no ``<br>``, so the only native paragraph
    boundaries in the object are the three Chromium visual lines.  Nothing
    else -- no marker run, no empty paragraph, no ``\n`` inside a run, and no
    duplicate object -- represents a soft line break.
    """
    output = tmp_path / "soft-wrap-model.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, SOFT_WRAP_SOURCE)
    assert manifest_object["text"].count("\n") == len(EXPECTED_VISUAL_LINES) - 1
    assert "" not in [
        paragraph["text"] for paragraph in manifest_object["paragraphs"]
    ]
    for paragraph in manifest_object["paragraphs"]:
        assert paragraph["runs"], "every visual line keeps a text-bearing run"
        for run in paragraph["runs"]:
            assert "\n" not in run["text"]
            assert "\r" not in run["text"]
    assert manifest_object["paragraphs"] == [
        {
            **paragraph,
            "align": "left",
            "line_spacing": SOFT_WRAP_LINE_SPACING,
            "space_before_pt": 0.0,
            "space_after_pt": 0.0,
            "direction": "ltr",
        }
        for paragraph in manifest_object["paragraphs"]
    ]

    readback = _object_by_name(output, manifest_object["name"])
    assert readback["text"] == EXPECTED_OBJECT_TEXT
    assert not [
        node
        for node in _slide_nodes(output)
        if node.get("type") in {"picture", "svg"}
    ]


# ---------------------------------------------------------------------------
# Criterion 7: alignment and line height as literals, manifest and readback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alignment_line_height_and_spacing_read_back_as_literals(
    tmp_path: Path,
) -> None:
    output = tmp_path / "soft-wrap-layout.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, SOFT_WRAP_SOURCE)
    assert manifest_object["properties"]["align"] == "left"
    assert manifest_object["properties"]["lineSpacing"] == SOFT_WRAP_LINE_SPACING
    assert [
        paragraph["align"] for paragraph in manifest_object["paragraphs"]
    ] == ["left", "left", "left"]
    assert [
        paragraph["line_spacing"] for paragraph in manifest_object["paragraphs"]
    ] == [SOFT_WRAP_LINE_SPACING] * len(EXPECTED_VISUAL_LINES)
    assert [
        paragraph["space_before_pt"] for paragraph in manifest_object["paragraphs"]
    ] == [0.0] * len(EXPECTED_VISUAL_LINES)
    assert [
        paragraph["space_after_pt"] for paragraph in manifest_object["paragraphs"]
    ] == [0.0] * len(EXPECTED_VISUAL_LINES)
    # The ordinary font size and the color are unchanged by the wrap.
    assert [
        run["font_size_pt"] for paragraph in manifest_object["paragraphs"]
        for run in paragraph["runs"]
    ] == [SOFT_WRAP_FONT_SIZE_PT] * len(EXPECTED_VISUAL_LINES)
    assert [
        run["color"] for paragraph in manifest_object["paragraphs"]
        for run in paragraph["runs"]
    ] == [SOFT_WRAP_COLOR] * len(EXPECTED_VISUAL_LINES)

    readback = _object_by_name(output, manifest_object["name"])
    assert readback["format"]["align"] == "left"
    assert readback["format"]["lineSpacing"] == SOFT_WRAP_LINE_SPACING
    readback_paragraphs = _readback_paragraphs(readback)
    assert [
        paragraph["format"].get("align") for paragraph in readback_paragraphs
    ] == ["left", "left", "left"]
    assert [
        paragraph["format"].get("lineSpacing")
        for paragraph in readback_paragraphs
    ] == [SOFT_WRAP_LINE_SPACING] * len(EXPECTED_VISUAL_LINES)
    # An omitted native spaceBefore/spaceAfter is the zero projection: the
    # OfficeCLI default is no paragraph spacing.
    assert [
        paragraph["format"].get("spaceBefore") for paragraph in readback_paragraphs
    ] == [None] * len(EXPECTED_VISUAL_LINES)
    assert [
        paragraph["format"].get("spaceAfter") for paragraph in readback_paragraphs
    ] == [None] * len(EXPECTED_VISUAL_LINES)
    assert [
        run["format"]["size"]
        for paragraph in readback["children"]
        for run in paragraph.get("children", [])
    ] == ["15.5pt"] * len(EXPECTED_VISUAL_LINES)


@pytest.mark.asyncio
async def test_v02_line_height_projections_are_unchanged(tmp_path: Path) -> None:
    """Criterion 11: the released V0.2 CSS-pixel projection still applies."""
    output = tmp_path / "v02-line-height.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    mixed_runs = _shape_by_source(result.manifest, MIXED_RUNS_SOURCE)
    paragraphs = _shape_by_source(result.manifest, PARAGRAPHS_SOURCE)
    assert mixed_runs["properties"]["lineSpacing"] == MIXED_RUNS_LINE_SPACING
    assert paragraphs["properties"]["lineSpacing"] == PARAGRAPHS_LINE_SPACING
    assert [
        paragraph["line_spacing"] for paragraph in paragraphs["paragraphs"]
    ] == [PARAGRAPHS_LINE_SPACING] * 5

    mixed_readback = _object_by_name(output, mixed_runs["name"])
    paragraphs_readback = _object_by_name(output, paragraphs["name"])
    assert mixed_readback["format"]["lineSpacing"] == MIXED_RUNS_LINE_SPACING
    assert paragraphs_readback["format"]["lineSpacing"] == PARAGRAPHS_LINE_SPACING
    assert [
        (paragraph.get("format") or {}).get("lineSpacing")
        for paragraph in paragraphs_readback["children"]
    ] == [PARAGRAPHS_LINE_SPACING] * 5


# ---------------------------------------------------------------------------
# Criterion 7: authored paragraph spacing really lowers and reads back
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authored_paragraph_spacing_lowers_and_reads_back(
    tmp_path: Path,
) -> None:
    """Non-zero authored space before/after survives as native cell formatting.

    ``margin: 24px 0 36px 0`` on a 28px/1.35 paragraph cell is 24px and 36px of
    author spacing inside the cell's own text body, so the projection is 12pt
    and 18pt at the 0.5pt-per-px canvas scale.  OfficeCLI exposes paragraph
    alignment, spacing and direction for a cell through the cell path, which is
    where the compiler's ``_paragraph_props`` projection is applied.
    """
    output = tmp_path / "paragraph-spacing.pptx"

    result = await compile_officecli(
        str(_write_layout_html(tmp_path)), "author", str(output)
    )

    tables = [
        item for item in result.manifest["objects"] if item["kind"] == "table"
    ]
    assert len(tables) == 1
    table = tables[0]
    assert table["source_object"] == "slide[1]/table[2]"
    cell = table["cells"][0]
    assert [
        paragraph["text"] for paragraph in cell["paragraphs"]
    ] == list(EXPECTED_CELL_PARAGRAPHS)
    assert [
        paragraph["space_before_pt"] for paragraph in cell["paragraphs"]
    ] == EXPECTED_SPACE_BEFORE_PT
    assert [
        paragraph["space_after_pt"] for paragraph in cell["paragraphs"]
    ] == EXPECTED_SPACE_AFTER_PT
    assert [
        paragraph["line_spacing"] for paragraph in cell["paragraphs"]
    ] == [EXPECTED_CELL_LINE_SPACING] * len(EXPECTED_CELL_PARAGRAPHS)
    assert cell["props"]["spacebefore"] == "12.0000pt"
    assert cell["props"]["spaceafter"] == "18.0000pt"
    assert cell["props"]["linespacing"] == EXPECTED_CELL_LINE_SPACING
    assert cell["props"]["align"] == "right"

    rendered_cell = _readback_table_cell(output)
    assert rendered_cell["type"] == "tc"
    assert rendered_cell["text"] == "\n".join(EXPECTED_CELL_PARAGRAPHS)
    assert rendered_cell["format"]["spaceBefore"] == EXPECTED_SPACE_BEFORE_READBACK
    assert rendered_cell["format"]["spaceAfter"] == EXPECTED_SPACE_AFTER_READBACK
    assert rendered_cell["format"]["lineSpacing"] == EXPECTED_CELL_LINE_SPACING
    assert rendered_cell["format"]["align"] == "right"
    # One native paragraph per authored paragraph: the spacing is paragraph
    # formatting, not an extra empty paragraph used as a spacer.
    assert rendered_cell["format"]["txBodyRaw"].count("<a:p>") == len(
        EXPECTED_CELL_PARAGRAPHS
    )
    assert f'<a:spcPts val="{AUTHORED_TOP_MARGIN_PX * 50}"' in rendered_cell[
        "format"
    ]["txBodyRaw"]
    assert f'<a:spcPts val="{AUTHORED_BOTTOM_MARGIN_PX * 50}"' in rendered_cell[
        "format"
    ]["txBodyRaw"]


@pytest.mark.asyncio
async def test_standalone_block_margin_is_not_double_counted(
    tmp_path: Path,
) -> None:
    """The V0.2 text-body projection stays truthful about standalone blocks.

    A standalone Author paragraph already carries its own margin inside the
    Chromium-measured bounds, so the lowering must not re-emit that margin as
    native paragraph spacing; doing so would count the authored spacing twice.
    The block's top is therefore exactly one margin below its containing box's
    top (120px), and its own body reports no native space before/after.
    """
    output = tmp_path / "standalone-margin.pptx"

    result = await compile_officecli(
        str(_write_layout_html(tmp_path)), "author", str(output)
    )

    standalone = _shape_by_source(result.manifest, "slide[1]/div[1]/p[1]")
    assert standalone["kind"] == "textbox"
    assert [
        paragraph["text"] for paragraph in standalone["paragraphs"]
    ] == ["Standalone spacing line"]
    assert [
        paragraph["space_before_pt"] for paragraph in standalone["paragraphs"]
    ] == [EXPECTED_STANDALONE_SPACE_BEFORE_PT]
    assert [
        paragraph["space_after_pt"] for paragraph in standalone["paragraphs"]
    ] == [EXPECTED_STANDALONE_SPACE_AFTER_PT]
    assert standalone["paragraphs"][0]["line_spacing"] == EXPECTED_CELL_LINE_SPACING
    # Independent literal: 120px container top + 12px margin = 132px = 66pt, and
    # the margin is inside the measured box rather than added to the text body.
    assert standalone["bounds_pt"][1] == 60.0 + EXPECTED_STANDALONE_TOP_MARGIN_PT
    assert standalone["properties"]["y"] == "66.0000pt"

    readback = _object_by_name(output, standalone["name"])
    assert readback["type"] == "textbox"
    assert readback["format"]["y"] == "66pt"
    assert readback["format"]["size"] == "15.5pt"
    readback_paragraphs = _readback_paragraphs(readback)
    assert [paragraph["text"] for paragraph in readback_paragraphs] == [
        "Standalone spacing line"
    ]
    assert readback_paragraphs[0]["format"].get("spaceBefore") is None
    assert readback_paragraphs[0]["format"].get("spaceAfter") is None


@pytest.mark.asyncio
async def test_declared_alignment_lowers_and_reads_back(tmp_path: Path) -> None:
    """Criterion 2 and 7: a non-default declared alignment really lowers."""
    html = tmp_path / "alignment.html"
    html.write_text(ALIGNMENT_HTML, encoding="utf-8")
    output = tmp_path / "alignment.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    standalone = _shape_by_source(result.manifest, ALIGNMENT_SOURCE)
    assert standalone["properties"]["align"] == "center"
    assert [
        paragraph["align"] for paragraph in standalone["paragraphs"]
    ] == ["center"]

    readback = _object_by_name(output, standalone["name"])
    assert readback["format"]["align"] == "center"
    assert [
        paragraph["format"].get("align")
        for paragraph in _readback_paragraphs(readback)
    ] == ["center"]
