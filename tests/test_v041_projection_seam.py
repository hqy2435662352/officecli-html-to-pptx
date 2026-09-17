"""V0.4.1 PPTX-to-Canonical-Author-HTML projection seam tests.

The external seam under test is::

    project_pptx_to_author_html(pptx, selected_slide_numbers, output_html)
        -> Canonical Author HTML + source map + projection report
         + structured diagnostics

Every test drives that one seam.  Nothing here freezes the private reader
calls, the OfficeCLI command shapes, or the normalization helpers, because a
caller must not have to depend on them.

The fixture is a minimal synthetic deck built through OfficeCLI itself, so the
real 63 MB acceptance deck is never committed and the probes stay narrow.  The
fixture deliberately contains one supported surface, one unsupported geometry,
and one container whose native semantics the current Author Contract cannot
express.

V0.4.2 supersedes exactly one expectation this file used to encode: the locked
proxy's fixture geometry was an ellipse, and an ellipse is now projected as a
native canonical shape.  The isolation boundary these tests exist for is
unchanged, so it is re-pointed at a preset that is still outside the canonical
surface -- ``chevron`` -- rather than being weakened; the promoted ellipse has
its own coverage in ``tests/test_v042_native_presets.py``.  Every assertion in
this file is otherwise exactly as V0.4.1 published it.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

import pytest

from officecli_html_to_pptx import (
    DISPOSITION_BASE_ONLY,
    DISPOSITION_CANONICAL,
    DISPOSITION_LOCKED,
    DISPOSITION_UNRESOLVED,
    DISPOSITION_UNSUPPORTED,
    OutputCollisionError,
    ProjectionError,
    project_pptx_to_author_html,
)
from officecli_html_to_pptx._internal import author_projector as projector
from officecli_html_to_pptx._internal.pptx_reader import (
    MissingSlideError,
    _drop_render_background,
    _raster_rgb,
)
from officecli_html_to_pptx.contract import check_contract

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the V0.4.1 projection-seam tests",
)

# A 4x3 opaque PNG, small enough to inline as a base64 literal in the fixture.
_PICTURE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAHElEQVQI12P8//8/AzbAxMDA"
    "wMDAwMDAwMDAwAAAJhwEAX8lErwAAAAASUVORK5CYII="
)
_PICTURE_URI = "data:image/png;base64," + base64.b64encode(_PICTURE_PNG).decode("ascii")

# The fixture's own literals.  Every expectation below is written from these,
# never from the projector's output.
SUPPORTED_TEXT = "V0.4.1 projection seam 中文 🚀"
SUPPORTED_SUBTITLE = "Second paragraph"
BOLD_RUN_TEXT = "Bold run"
# A preset the canonical Author object surface still has no equivalent for.  It
# was ``ellipse`` until V0.4.2 promoted the ellipse to a native shape; the
# boundary this file tests is "an unsupported geometry is a locked proxy", so
# the fixture now uses a preset that is still unsupported.
UNSUPPORTED_GEOMETRY = "chevron"
CONTAINER_CHILD_TEXT = "grouped label"
TABLE_CELLS = (("MODEL", "12K"), ("IDU SIZE", "910x305x195"))
FIXTURE_SLIDE_COUNT = 1

# The overlay probe: a text-free filled shape with three independent
# textboxes painted inside its rectangle, which is exactly the arrangement that
# a composited-raster crop cannot represent without capturing its neighbours.
OVERLAY_SHAPE_BOX = (40.0, 200.0, 120.0, 120.0)
OVERLAY_SHAPE_FILL = "#D96666"
OVERLAY_TEXT_LINES = ("In 2026", "9.50", "Million/USD")
OVERLAY_TEXTBOX_TOP_PT = (215.0, 245.0, 275.0)


def _officecli(*args: str, attempts: int = 6) -> str:
    """Run one OfficeCLI command, retrying a transient failure.

    OfficeCLI keeps documents resident and, on a loaded machine, an individual
    command can exit non-zero with no message and then succeed unchanged.  A
    retry of a command that names a document first closes any resident handle on
    that document, because a resident left over from a previous attempt is the
    one failure a blind retry cannot clear.  The last failure is still raised,
    with its command, so a genuine error is never hidden.
    """
    import time

    document = next(
        (argument for argument in args[1:] if argument.lower().endswith(".pptx")),
        None,
    )
    last = ""
    for attempt in range(attempts):
        completed = subprocess.run(
            ["officecli", *args],
            capture_output=True,
            check=False,
            timeout=300,
        )
        text = completed.stdout.decode("utf-8", errors="replace")
        if completed.returncode == 0 and text.strip():
            return text
        last = completed.stderr.decode("utf-8", errors="replace") or text
        if document is not None:
            subprocess.run(
                ["officecli", "close", document],
                capture_output=True,
                check=False,
                timeout=300,
            )
        time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"officecli {' '.join(args)} failed: {last}")


@pytest.fixture(scope="session")
def projection_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build one minimal synthetic deck through OfficeCLI.

    The deck is the PowerPoint Object Capture's input and nothing else: it is
    never produced from an OfficeHTML export, so the probe stays runnable from
    a PPTX alone.
    """
    directory = tmp_path_factory.mktemp("v041-fixture")
    deck = directory / "fixture.pptx"
    _officecli("create", str(deck))
    commands: list[dict[str, Any]] = [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
        {
            "command": "add",
            "parent": "/",
            "type": "slide",
            "props": {"name": "probe-slide"},
        },
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "textbox",
            "props": {
                "name": "supported-text",
                "text": f"{SUPPORTED_TEXT}\n{SUPPORTED_SUBTITLE}",
                "x": "40pt",
                "y": "40pt",
                "width": "400pt",
                "height": "80pt",
                "size": "18pt",
                "font": "Microsoft YaHei",
                "color": "#14243A",
                "fill": "none",
                "line": "none",
            },
        },
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "textbox",
            "props": {
                "name": "bold-text",
                "text": BOLD_RUN_TEXT,
                "x": "40pt",
                "y": "140pt",
                "width": "300pt",
                "height": "40pt",
                "size": "19.05pt",
                "bold": "true",
                "font": "Arial",
                "color": "#C00000",
                "fill": "none",
                "line": "none",
            },
        },
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "shape",
            "props": {
                "name": "unsupported-preset",
                "geometry": UNSUPPORTED_GEOMETRY,
                # Deliberately clear of the overlay probe's rectangle, so its own
                # proxy cannot be judged against another fixture object's paint.
                "x": "500pt",
                "y": "320pt",
                "width": "60pt",
                "height": "60pt",
                "fill": "#D96666",
                "line": "none",
            },
        },
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "shape",
            "props": {
                "name": "canonical-round-rect",
                "geometry": "roundRect",
                "x": "500pt",
                "y": "40pt",
                "width": "200pt",
                "height": "90pt",
                "fill": "#F5F5F5",
                "line": "#D9D9D9",
                "lineWidth": "1pt",
            },
        },
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "picture",
            "props": {
                "name": "independent-picture",
                "x": "500pt",
                "y": "160pt",
                "width": "80pt",
                "height": "60pt",
                "src": _PICTURE_URI,
            },
        },
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "shape",
            "props": {
                "name": "inline-ellipse-parent",
                "geometry": "rect",
                "x": "500pt",
                "y": "240pt",
                "width": "200pt",
                "height": "60pt",
                "fill": "none",
                "line": "none",
            },
        },
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "table",
            "props": {
                "name": "native-table",
                "x": "40pt",
                "y": "300pt",
                "width": "400pt",
                "height": "60pt",
                "rows": "2",
                "cols": "2",
                "colWidths": "200pt,200pt",
            },
        },
        {
            # A text-free filled shape whose rectangle is painted over by three
            # independent textboxes below.  Its locked proxy must carry only
            # the shape's own paint.
            "command": "add",
            "parent": "/slide[1]",
            "type": "shape",
            "props": {
                "name": "overlay-shape",
                "geometry": UNSUPPORTED_GEOMETRY,
                "x": f"{OVERLAY_SHAPE_BOX[0]}pt",
                "y": f"{OVERLAY_SHAPE_BOX[1]}pt",
                "width": f"{OVERLAY_SHAPE_BOX[2]}pt",
                "height": f"{OVERLAY_SHAPE_BOX[3]}pt",
                "fill": OVERLAY_SHAPE_FILL,
                "line": "none",
            },
        },
    ]
    # The three sibling textboxes sit inside the shape's rectangle.
    for offset, line in zip(OVERLAY_TEXTBOX_TOP_PT, OVERLAY_TEXT_LINES):
        commands.append(
            {
                "command": "add",
                "parent": "/slide[1]",
                "type": "textbox",
                "props": {
                    "name": f"overlay-text-{line.replace('/', '-')}",
                    "text": line,
                    "x": f"{OVERLAY_SHAPE_BOX[0] + 10}pt",
                    "y": f"{offset}pt",
                    "width": f"{OVERLAY_SHAPE_BOX[2] - 20}pt",
                    "height": "24pt",
                    "size": "14pt",
                    "font": "Arial",
                    "color": "#FFFFFF",
                    "fill": "none",
                    "line": "none",
                },
            }
        )
    _officecli(
        "batch",
        str(deck),
        "--commands",
        json.dumps(commands, ensure_ascii=False),
    )
    for row_index, row in enumerate(TABLE_CELLS, start=1):
        for column_index, value in enumerate(row, start=1):
            _officecli(
                "set",
                str(deck),
                f"/slide[1]/table[@name=native-table]/tr[{row_index}]/tc[{column_index}]",
                "--prop",
                f"text={value}",
            )
    _officecli("close", str(deck))
    return deck


@pytest.fixture
def projected(
    projection_fixture: Path, tmp_path: Path
) -> Any:
    """Project the fixture's only slide and return the sealed result."""
    return project_pptx_to_author_html(
        projection_fixture,
        [1],
        tmp_path / "canonical-author.html",
        proxy_dir=tmp_path / "proxies",
    )


def _objects(projected: Any) -> dict[str, Any]:
    return {item.source_object.rsplit("/", 1)[-1]: item for item in projected.objects}


def _object_named(projected: Any, name: str) -> Any:
    for item in projected.objects:
        if item.source_name == name:
            return item
    raise AssertionError(
        f"no projected object named {name!r}; got "
        f"{[item.source_name for item in projected.objects]}"
    )


# ---------------------------------------------------------------------------
# Criterion: the projection seam emits the whole artifact set
# ---------------------------------------------------------------------------


def test_seam_emits_html_source_map_and_report(projected: Any) -> None:
    """One call produces Canonical Author HTML plus both evidence documents."""
    assert projected.published is True
    assert projected.html_path.is_file()
    assert Path(projected.source_map_path).is_file()
    assert Path(projected.projection_report_path).is_file()
    # The source map is bound to the exact source PPTX hash, and the HTML hash
    # stored in the report matches the artifact that was published.
    assert projected.source_map["source"]["sha256"] == projected.source_sha256
    assert projected.projection_report["author_html_sha256"] == projected.html_sha256
    assert projected.officecli_version != "unknown"


def test_source_deck_is_identical_before_and_after(projected: Any) -> None:
    """The reader never writes to the source, so its hash cannot move."""
    import hashlib

    digest = hashlib.sha256(Path(projected.source_path).read_bytes()).hexdigest()
    assert digest == projected.source_sha256
    assert projected.source_map["source"]["sha256"] == digest


# ---------------------------------------------------------------------------
# Criterion: the current author Contract accepts the projection unchanged
# ---------------------------------------------------------------------------


def test_projection_passes_the_current_author_contract_unchanged(
    projected: Any,
) -> None:
    """The generated document is Canonical Author HTML by the existing meaning."""
    report = check_contract(projected.html_path, "author")
    assert report.status == "PASS", [item.message for item in report.diagnostics]
    assert report.blocked is False
    assert report.diagnostics == ()


def test_canvas_is_the_current_author_canvas_from_the_pptx_slide_bounds(
    projected: Any,
) -> None:
    """Normalization is derived from the source slide bounds, not CSS units.

    The fixture is a standard 960x540pt widescreen slide, so the factor is
    exactly 2 px/pt.  The CSS physical-unit conversion (96/72) would give
    1.3333... and is not what a PowerPoint point means here.
    """
    assert projected.source_slide_size_pt == (960.0, 540.0)
    assert projected.pixels_per_point == pytest.approx(2.0, abs=1e-9)
    assert projected.canvas_px == (1920.0, 1080.0)
    assert projected.source_map["canvas"]["pixels_per_point"] == pytest.approx(2.0)
    assert projected.source_map["canvas"]["width_px"] == 1920.0
    assert projected.source_map["canvas"]["height_px"] == 1080.0


# ---------------------------------------------------------------------------
# Criterion: one canonical object per supported source object, in paint order
# ---------------------------------------------------------------------------


def test_supported_text_survives_with_paragraph_and_run_structure(
    projected: Any,
) -> None:
    """Text, Unicode, paragraph boundaries, and run formatting are preserved."""
    text_object = _object_named(projected, "supported-text")
    assert text_object.disposition == DISPOSITION_CANONICAL
    assert text_object.projected_kind == "textbox"
    assert SUPPORTED_TEXT in text_object.text
    assert SUPPORTED_SUBTITLE in text_object.text
    html = projected.html_path.read_text(encoding="utf-8")
    element = html.split(f'id="{text_object.html_id}"', 1)[1]
    element = element.split("</div>", 1)[0]
    # The supplementary-plane character and the CJK text are emitted verbatim.
    assert "🚀" in element
    assert "中文" in element
    # Two authored paragraphs stay two lines, not one merged run of text.
    assert element.count("<br>") == 1


def test_supported_run_formatting_is_an_inline_semantic_element(
    projected: Any,
) -> None:
    """A bold source run is a canonical bold inline element, not a styled copy."""
    bold_object = _object_named(projected, "bold-text")
    assert bold_object.disposition == DISPOSITION_CANONICAL
    html = projected.html_path.read_text(encoding="utf-8")
    element = html.split(f'id="{bold_object.html_id}"', 1)[1]
    element = element.split("</div>", 1)[0]
    assert BOLD_RUN_TEXT in element
    assert "<strong>" in element or "font-weight: 700" in element


def test_object_bounds_are_normalized_at_the_canvas_factor(projected: Any) -> None:
    """Every emitted rectangle is the source rectangle at 2 px/pt.

    With one deliberate addition: an *extent* carries one Chromium layout unit more
    than the measurement.  Blink snaps layout to a 1/64 px grid, so a box declared
    at exactly its measured width is laid out a unit narrower, and a box whose text
    fills it then wraps where the source does not -- which is what happened to a
    page number on src3 pages 2 and 21.  Position is not biased, and the bias is
    bounded by that one unit, so this test still fails on a wrong scale or a moved
    object.
    """
    bias = projector._LAYOUT_UNIT_PX
    assert 0 < bias <= 0.02, "the extent bias is one layout unit, not a fudge factor"
    for item in projected.objects:
        # x and y are positions: unbiased.
        assert item.bounds_px[0] == pytest.approx(item.bounds_pt[0] * 2.0, abs=0.01)
        assert item.bounds_px[1] == pytest.approx(item.bounds_pt[1] * 2.0, abs=0.01)
        # width and height are extents: measured, plus one layout unit.
        for source_value, emitted_value in zip(item.bounds_pt[2:], item.bounds_px[2:]):
            assert emitted_value == pytest.approx(
                source_value * 2.0 + bias, abs=0.01
            ), (item.source_object, source_value, emitted_value)


def test_objects_are_emitted_in_source_paint_order(projected: Any) -> None:
    """Projection order is the source z-order, so no object is repainted under."""
    html = projected.html_path.read_text(encoding="utf-8")
    positions = [html.index(f'id="{item.html_id}"') for item in projected.objects]
    assert positions == sorted(positions)


def test_a_supported_picture_is_its_own_object_with_a_data_uri(projected: Any) -> None:
    """A picture stays one independent picture with a deterministic source."""
    picture = _object_named(projected, "independent-picture")
    assert picture.disposition == DISPOSITION_CANONICAL
    assert picture.projected_kind == "picture"
    html = projected.html_path.read_text(encoding="utf-8")
    element = html.split(f'id="{picture.html_id}"', 1)[1].split(">", 1)[0]
    assert "data:image/" in element
    # Never a whole-slide raster: the picture's own box is what is emitted.
    assert picture.bounds_px[2] == pytest.approx(160.0, abs=0.5)


def test_a_native_table_is_one_table_with_row_and_cell_identity(
    projected: Any,
) -> None:
    """A native table remains structurally editable, cell by cell."""
    table = _object_named(projected, "native-table")
    assert table.disposition == DISPOSITION_CANONICAL
    assert table.projected_kind == "table"
    html = projected.html_path.read_text(encoding="utf-8")
    element = html.split(f'id="{table.html_id}"', 1)[1]
    element = element.split("</div>", 1)[0]
    assert element.count("<tr") == len(TABLE_CELLS)
    assert element.count("<td") == sum(len(row) for row in TABLE_CELLS)
    for row in TABLE_CELLS:
        for value in row:
            assert value in element
    assert 'data-cell-path="' in element


# ---------------------------------------------------------------------------
# Criterion: capability boundaries are classified, never faked
# ---------------------------------------------------------------------------


def test_an_unsupported_geometry_is_a_locked_proxy_with_a_reason(
    projected: Any,
) -> None:
    """A preset with no canonical equivalent is never declared editable."""
    preset = _object_named(projected, "unsupported-preset")
    assert preset.disposition == DISPOSITION_LOCKED
    assert preset.proxy_reason
    assert UNSUPPORTED_GEOMETRY in preset.proxy_reason
    html = projected.html_path.read_text(encoding="utf-8")
    element = html.split(f'id="{preset.html_id}"', 1)[1].split(">", 1)[0]
    assert 'data-projection-locked="true"' in element


def test_locked_proxies_are_excluded_from_the_native_round_trip_count(
    projected: Any,
) -> None:
    """A proxy is never counted as a native round-trip success."""
    counts = projected.projection_report["counts"]
    assert counts["native_round_trip"] == counts["canonical_editable"]
    assert counts["excluded_from_native_round_trip"] == (
        counts["locked_visual_proxy"]
        + counts["base_only_semantic"]
        + counts["unsupported"]
        + counts["unresolved"]
    )
    assert counts["native_round_trip"] < counts["source_objects"]


def test_no_whole_slide_screenshot_fallback_is_declared_or_used(
    projected: Any,
) -> None:
    """The report declares the prohibition and the DOM upholds it."""
    assert projected.projection_report["whole_slide_screenshot_fallback"] is False
    html = projected.html_path.read_text(encoding="utf-8")
    # The slide is exactly the Author canvas, so a slide-sized image would be a
    # whole-slide fallback; every emitted image is object-local instead.
    for item in projected.objects:
        if item.projected_kind == "image":
            assert item.bounds_px[2] < projected.canvas_px[0]
            assert item.bounds_px[3] < projected.canvas_px[1]


def _enclosed_foreign_pixels(
    image: Any,
    fill: tuple[int, int, int],
    *,
    tolerance: int = 24,
    min_run: int = 4,
) -> int:
    """Count horizontal runs that the object's own fill encloses but does not own.

    Enclosure — not color distance — is what makes this a faithful reader of a
    proxy.  A filled circle with white glyphs on it produces white runs with the
    fill on both sides; the slide background is never enclosed that way because
    it lies outside the object.  A proxy that carries a sibling's content
    therefore has a positive count, and a genuinely object-local proxy has zero.
    """
    width, height = image.size
    pixels = image.load()

    def near(pixel: tuple[int, int, int]) -> bool:
        return all(
            abs(channel - expected) <= tolerance
            for channel, expected in zip(pixel, fill)
        )

    total = 0
    for y in range(height):
        column = 0
        while column < width:
            if near(pixels[column, y]):
                column += 1
                continue
            run_start = column
            while column < width and not near(pixels[column, y]):
                column += 1
            run_end = column
            if run_end - run_start < min_run:
                continue
            left_is_fill = run_start > 0 and near(pixels[run_start - 1, y])
            right_is_fill = run_end < width and near(pixels[run_end, y])
            if left_is_fill and right_is_fill:
                total += run_end - run_start
    return total


def test_the_enclosure_discriminator_fires_on_a_contaminated_image() -> None:
    """The proxy-contamination reader must be able to fail.

    A discriminator that never fires would make the isolation regression below
    vacuous, so it is proved against a synthetic pair: one flat fill, and the
    same fill with a contrasting bar enclosed by it.
    """
    from PIL import Image

    fill = (217, 102, 102)
    flat = Image.new("RGB", (160, 80), fill)
    contaminated = Image.new("RGB", (160, 80), fill)
    for x in range(40, 120):
        for y in range(30, 50):
            contaminated.putpixel((x, y), (255, 255, 255))

    assert _enclosed_foreign_pixels(flat, fill) == 0
    assert _enclosed_foreign_pixels(contaminated, fill) > 0


def test_a_locked_proxy_carries_only_its_own_object(projected: Any) -> None:
    """A proxy for a text-free shape must not contain a sibling's glyphs.

    The fixture paints three independent textboxes inside the shape's
    rectangle.  Cropping the composited slide would capture them, and the
    projection would then paint the same words twice — once inside the proxy
    image and once as the canonical text objects.  The proxy is therefore
    required to be a render of the object alone.
    """
    from PIL import Image

    overlay = _object_named(projected, "overlay-shape")
    assert overlay.disposition == DISPOSITION_LOCKED
    assert overlay.proxy_asset, "a locked proxy must publish its asset for review"
    fill = tuple(
        int(OVERLAY_SHAPE_FILL.lstrip("#")[index : index + 2], 16)
        for index in (0, 2, 4)
    )
    with Image.open(overlay.proxy_asset) as image:
        rgb = image.convert("RGB")
        assert _enclosed_foreign_pixels(rgb, fill) == 0

    # And the DOM emits exactly one element for the proxy: no text element is
    # nested inside the placeholder.
    html = projected.html_path.read_text(encoding="utf-8")
    element = html.split(f'id="{overlay.html_id}"', 1)[1].split(">", 1)[0]
    assert 'data-projection-locked="true"' in element

    # The sibling textboxes remain their own canonical objects, so the words
    # exist as native text and nowhere else.
    texts = {item.source_name: item for item in projected.objects}
    for line in OVERLAY_TEXT_LINES:
        match = texts.get(f"overlay-text-{line.replace('/', '-')}")
        assert match is not None, f"{line!r} was not projected as its own object"
        assert match.disposition == DISPOSITION_CANONICAL
        assert line in match.text


def test_a_locked_proxy_is_not_a_crop_of_the_composited_slide(projected: Any) -> None:
    """The proxy's own evidence must show it came from an isolated render."""
    overlay = _object_named(projected, "overlay-shape")
    assert overlay.proxy_asset
    asset = Path(overlay.proxy_asset)
    assert asset.is_file()
    # The proxy is the object's own rectangle at the canvas factor, with the
    # guard band on each side, and nothing larger.
    assert asset.stat().st_size > 0
    from PIL import Image

    with Image.open(asset) as image:
        size = image.size
    expected = (
        round(overlay.bounds_px[2]) + 4,
        round(overlay.bounds_px[3]) + 4,
    )
    assert size == expected


def test_the_proxy_density_gate_requires_the_canvas_density() -> None:
    """A proxy render below the Author canvas density is refused, not upscaled.

    The DOM draws a proxy at the object's rectangle in canvas pixels, so a
    render below ``pixels_per_point`` would be enlarged and softened.  The gate
    must therefore compare against that density rather than against some lower
    floor: a raster that merely clears a looser floor is exactly the case that
    would slip through and be shown at the wrong scale.

    This drives the crop stage directly, because the density guarantee is a
    property of that stage: whatever the renderer produced, the crop refuses a
    raster that is too coarse.
    """
    import tempfile

    from PIL import Image

    from officecli_html_to_pptx._internal.pptx_reader import IsolatedRenderer, ObjectIsolationError

    work = Path(tempfile.mkdtemp())
    bounds = (10.0, 10.0, 20.0, 20.0)
    canvas_density = 1920.0 / 960.0

    def render_at(width: int) -> str:
        raster = work / f"r{width}.png"
        Image.new("RGB", (width, int(width * 9 / 16)), (200, 30, 30)).save(raster)
        try:
            IsolatedRenderer._crop(
                raster,
                bounds,
                slide_width_pt=960.0,
                pixels_per_point=canvas_density,
                guard_px=2,
                destination=work / f"p{width}.png",
            )
        except ObjectIsolationError:
            return "BLOCK"
        return "PASS"

    # The canvas density itself, and one pixel of whole-raster rounding either
    # side of it, are accepted.
    assert render_at(1920) == "PASS"
    assert render_at(1921) == "PASS"
    assert render_at(1919) == "PASS"
    # Below the canvas density is refused: 1.6 px/pt and OfficeCLI's own 1280px
    # default both land here, and neither may be published as a proxy.
    assert render_at(1536) == "BLOCK"
    assert render_at(1280) == "BLOCK"


def test_every_source_object_receives_exactly_one_disposition(
    projected: Any,
) -> None:
    """No selected-slide object can disappear between capture and emission."""
    source_map = projected.source_map
    identities = [
        (item["source_slide"], item["source_object"]) for item in source_map["objects"]
    ]
    assert len(identities) == len(set(identities))
    assert len(identities) == len(projected.objects)
    for item in source_map["objects"]:
        assert item["disposition"] in {
            DISPOSITION_CANONICAL,
            DISPOSITION_LOCKED,
            DISPOSITION_BASE_ONLY,
            DISPOSITION_UNSUPPORTED,
        }


def test_source_map_carries_source_and_emitted_identity_for_every_object(
    projected: Any,
) -> None:
    """Every claim in the report can be traced to the source and the DOM."""
    html = projected.html_path.read_text(encoding="utf-8")
    for item in projected.source_map["objects"]:
        assert item["source_object"]
        assert item["html_id"]
        assert item["source_fingerprint"]
        assert f'id="{item["html_id"]}"' in html
        assert item["capabilities"]


def test_each_selected_slide_becomes_one_canonical_slide(projected: Any) -> None:
    """The document holds exactly the selected slides at the Author canvas."""
    html = projected.html_path.read_text(encoding="utf-8")
    assert html.count('class="slide"') == FIXTURE_SLIDE_COUNT
    assert 'data-slide-number="1"' in html
    assert "width: 1920px" in html
    assert "height: 1080px" in html


def test_the_dom_does_not_mirror_an_officecli_viewer_wrapper(projected: Any) -> None:
    """The output is clean fixed-position Author HTML, not a viewer page."""
    html = projected.html_path.read_text(encoding="utf-8")
    for viewer_token in (
        "officecli",
        "sidebar",
        "thumbnails",
        "viewer-chrome",
        "importmap",
        "three",
    ):
        assert viewer_token not in html.lower()


# ---------------------------------------------------------------------------
# Criterion: negative coverage with stable diagnostics
# ---------------------------------------------------------------------------


def _fresh_targets(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "out" / "canonical.html", tmp_path / "out" / "proxies"


def test_a_missing_slide_is_a_stable_diagnostic(
    projection_fixture: Path, tmp_path: Path
) -> None:
    """Selecting a slide the deck does not have fails before anything is read."""
    target, proxies = _fresh_targets(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(MissingSlideError) as error:
        project_pptx_to_author_html(
            projection_fixture, [1, 99], target, proxy_dir=proxies
        )
    assert "99" in str(error.value)
    assert str(FIXTURE_SLIDE_COUNT) in str(error.value)
    assert not target.exists()


def test_an_output_collision_is_a_collision_not_an_overwrite(
    projection_fixture: Path, tmp_path: Path
) -> None:
    """An existing target is never overwritten by a probe run."""
    target, proxies = _fresh_targets(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing author document", encoding="utf-8")
    with pytest.raises(OutputCollisionError):
        project_pptx_to_author_html(
            projection_fixture, [1], target, proxy_dir=proxies
        )
    assert target.read_text(encoding="utf-8") == "existing author document"


def test_a_missing_source_deck_is_a_stable_diagnostic(tmp_path: Path) -> None:
    """A nonexistent PPTX never produces a partial artifact set."""
    target, proxies = _fresh_targets(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ProjectionError) as error:
        project_pptx_to_author_html(
            tmp_path / "absent.pptx", [1], target, proxy_dir=proxies
        )
    assert "absent.pptx" in str(error.value)
    assert not target.exists()


def test_a_base_only_text_body_is_not_declared_slide_owned(
    projection_fixture: Path, tmp_path: Path
) -> None:
    """A text body whose visible formatting is theme-resolved is classified.

    OfficeCLI reports the resolved value together with its source, and a value
    the slide does not own cannot be presented as a slide-owned editable object.
    The fixture's own supported text declares its formatting, so this probes the
    boundary by projecting a body whose typeface comes from the theme.
    """
    deck = tmp_path / "theme-text.pptx"
    _officecli("create", str(deck))
    commands = [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
        {"command": "add", "parent": "/", "type": "slide", "props": {"name": "s"}},
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "textbox",
            "props": {
                "name": "theme-text",
                "text": "Theme resolved body",
                "x": "40pt",
                "y": "40pt",
                "width": "300pt",
                "height": "40pt",
                "size": "18pt",
                "fill": "none",
                "line": "none",
            },
        },
    ]
    _officecli("batch", str(deck), "--commands", json.dumps(commands))
    _officecli("close", str(deck))

    result = project_pptx_to_author_html(
        deck, [1], tmp_path / "theme.html", proxy_dir=tmp_path / "theme-proxies"
    )
    body = _object_named(result, "theme-text")
    assert body.disposition == DISPOSITION_BASE_ONLY
    assert any(claim.property == "font" for claim in body.base_only)
    assert all(claim.source.startswith("/theme") for claim in body.base_only)
    assert body.proxy_reason


def test_an_empty_slide_selection_is_rejected(
    projection_fixture: Path, tmp_path: Path
) -> None:
    """A probe must name the slides it evaluates."""
    target, proxies = _fresh_targets(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ProjectionError):
        project_pptx_to_author_html(projection_fixture, [], target, proxy_dir=proxies)
    assert not target.exists()


def test_a_failed_run_leaves_no_artifact_that_looks_complete(
    projection_fixture: Path, tmp_path: Path
) -> None:
    """A blocking diagnostic publishes neither the HTML nor its evidence."""
    target, _ = _fresh_targets(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # No proxy directory is a blocking condition: a locked visual proxy cannot
    # be produced, so the run must not present a finished projection.
    with pytest.raises(ProjectionError):
        project_pptx_to_author_html(projection_fixture, [1], target, proxy_dir=None)
    assert not target.exists()
    assert not target.with_suffix(".source-map.json").exists()
    assert not target.with_suffix(".projection-report.json").exists()


def test_the_source_map_binding_tracks_the_deck_it_was_made_from(
    projection_fixture: Path, tmp_path: Path
) -> None:
    """A projection binds the bytes it was made from, so a changed deck is visible.

    Two decks that differ in content must produce different bindings.  The
    earlier version of this test compared one run's recorded hash against itself
    and then against an unrelated literal, which could not fail.
    """
    changed = tmp_path / "changed.pptx"
    shutil.copy2(projection_fixture, changed)
    _officecli("close", str(changed))
    _officecli(
        "batch",
        str(changed),
        "--commands",
        json.dumps(
            [
                {
                    "command": "add",
                    "parent": "/slide[1]",
                    "type": "textbox",
                    "props": {
                        "name": "later-addition",
                        "text": "added after the first projection",
                        "x": "40pt",
                        "y": "480pt",
                        "width": "300pt",
                        "height": "30pt",
                        "fill": "none",
                        "line": "none",
                    },
                }
            ]
        ),
    )
    _officecli("close", str(changed))

    first = project_pptx_to_author_html(
        projection_fixture, [1], tmp_path / "first.html", proxy_dir=tmp_path / "p1"
    )
    second = project_pptx_to_author_html(
        changed, [1], tmp_path / "second.html", proxy_dir=tmp_path / "p2"
    )

    # The two decks really are different bytes ...
    assert first.source_sha256 != second.source_sha256
    # ... and each projection binds its own deck rather than a stale one.
    assert first.source_map["source"]["sha256"] == first.source_sha256
    assert second.source_map["source"]["sha256"] == second.source_sha256
    assert first.source_map["source"]["sha256"] != second.source_map["source"]["sha256"]


# ---------------------------------------------------------------------------
# The font resolution the projection relies on
# ---------------------------------------------------------------------------


def test_font_resolution_keeps_a_declared_face_but_never_a_non_face() -> None:
    """A declared typeface survives; something that names no face does not.

    The projection's text fidelity depends on this: a CJK deck's own face must
    reach the PPTX, while a CSS-wide keyword or a functional value names no
    typeface at all and must fall back rather than be written through and left
    to PowerPoint's substitution.
    """
    from officecli_html_to_pptx.styles import resolve_pptx_font

    # A declared family is a request for that family, including CJK faces.
    assert resolve_pptx_font("微软雅黑, sans-serif") == "微软雅黑"
    assert resolve_pptx_font("Microsoft YaHei, sans-serif") == "Microsoft YaHei"
    # A safe family later in the stack still wins over an unknown first entry.
    assert resolve_pptx_font("Sora, Arial") == "Arial"
    assert resolve_pptx_font("Arial, sans-serif") == "Arial"
    # Generic keywords ask the environment to choose.
    assert resolve_pptx_font("sans-serif") == "Calibri"
    assert resolve_pptx_font("fantasy") == "Segoe UI"
    assert resolve_pptx_font("math") == "Cambria Math"
    # Non-families must never be written through as a typeface.
    for non_face in (
        "inherit",
        "initial",
        "unset",
        "revert",
        "revert-layer",
        "var(--deck-font)",
    ):
        resolved = resolve_pptx_font(non_face)
        assert resolved not in {
            "inherit",
            "initial",
            "unset",
            "revert",
            "revert-layer",
            "var(--deck-font)",
        }, non_face
        assert resolved
    # Degenerate inputs still produce a usable typeface.
    assert resolve_pptx_font("") == "Calibri"
    assert resolve_pptx_font("   ") == "Calibri"


# ---------------------------------------------------------------------------
# A proxy carries the object's paint, not the reconstruction's background
# ---------------------------------------------------------------------------


def _png(path: Path, size: tuple[int, int], colour: tuple[int, int, int]) -> Path:
    from PIL import Image

    Image.new("RGB", size, colour).save(path, format="PNG")
    return path


def test_a_proxy_drops_the_reconstruction_background_and_keeps_the_paint(
    tmp_path: Path,
) -> None:
    """The object's own pixels stay; the blank slide's pixels become transparent.

    An object-local proxy is a crop of a render of a blank slide carrying one
    object, so the background in that crop belongs to the slide the object was
    reconstructed on, not to the object.  Keeping it made the proxy an opaque box:
    the independent visual review found a callout band reduced to a sliver and two
    product photos sitting on white rectangles over a lavender panel, both because
    the proxy painted the reconstruction's white over paint the source really has.
    """
    from PIL import Image

    blank = _png(tmp_path / "blank.png", (20, 10), (255, 255, 255))
    painted = _png(tmp_path / "object.png", (20, 10), (255, 255, 255))
    with Image.open(painted) as image:
        canvas = image.convert("RGB")
    for x in range(4, 8):
        for y in range(3, 6):
            canvas.putpixel((x, y), (200, 30, 30))
    canvas.save(painted, format="PNG")

    with Image.open(painted) as image:
        result = _drop_render_background(
            image.convert("RGB"), blank, (0, 0, 20, 10)
        )
    assert result.mode == "RGBA"
    assert result.getpixel((5, 4))[3] == 255, "the object's own paint stays opaque"
    assert result.getpixel((5, 4))[:3] == (200, 30, 30)
    assert result.getpixel((15, 8))[3] == 0, "the blank slide's pixels are dropped"
    assert result.getpixel((0, 0))[3] == 0


def test_the_background_key_is_exact_so_a_white_glyph_survives(
    tmp_path: Path,
) -> None:
    """White text on a white-rendered object is the case a tolerance would break.

    A run whose fill is the same colour as the reconstruction's background is
    genuinely ambiguous at one pixel, and both answers are wrong in one direction:
    keep it and an opaque white box covers the source's coloured panel, drop it and
    the text disappears.  The rule is that only pixels *identical* to the empty
    render are background, so a glyph that differs by even one unit in one channel
    is kept -- and the review's own finding shows the price of getting it wrong: on
    that page the source file's run is white with no outline, so nothing about it is
    painted at all and the proxy has nothing to keep.
    """
    from PIL import Image

    blank = _png(tmp_path / "blank.png", (12, 6), (255, 255, 255))
    faint = _png(tmp_path / "faint.png", (12, 6), (255, 255, 255))
    with Image.open(faint) as image:
        canvas = image.convert("RGB")
    canvas.putpixel((3, 3), (254, 255, 255))
    canvas.save(faint, format="PNG")

    with Image.open(faint) as image:
        result = _drop_render_background(
            image.convert("RGB"), blank, (0, 0, 12, 6)
        )
    assert result.getpixel((3, 3))[3] == 255, "a one-unit difference is still paint"
    assert result.getpixel((9, 3))[3] == 0


def test_an_unusable_reference_leaves_the_crop_alone(tmp_path: Path) -> None:
    """No reference, or one of the wrong size, means the old behaviour exactly."""
    from PIL import Image

    painted = _png(tmp_path / "object.png", (20, 10), (10, 20, 30))
    small = _png(tmp_path / "small.png", (4, 4), (255, 255, 255))
    missing = tmp_path / "not-there.png"
    with Image.open(painted) as image:
        for reference in (None, missing, small):
            result = _drop_render_background(
                image.convert("RGB"), reference, (0, 0, 20, 10)
            )
            assert result.mode == "RGB", reference
            assert result.getpixel((2, 2))[:3] == (10, 20, 30)


def test_a_flat_crop_is_left_alone_rather_than_emptied(tmp_path: Path) -> None:
    """An object that painted nothing keeps its raster for the gate to refuse.

    A fully transparent proxy would be indistinguishable from a decoding failure,
    and the blank-proxy gate is the thing that has to decide what an object with no
    paint means.  Handing it an empty alpha channel would take that decision away
    from the rule that owns it.
    """
    from PIL import Image

    blank = _png(tmp_path / "blank.png", (8, 8), (255, 255, 255))
    same = _png(tmp_path / "same.png", (8, 8), (255, 255, 255))
    with Image.open(same) as image:
        result = _drop_render_background(image.convert("RGB"), blank, (0, 0, 8, 8))
    assert result.mode == "RGB"


def test_a_transparent_raster_measures_as_unpainted(tmp_path: Path) -> None:
    """Every paint measurement flattens alpha onto the render's own background.

    The proofs compare a proxy's pixels against its sampled background, and a
    transparent pixel *is* that background.  Read as black it would make every
    blank proxy measure as fully painted, which is how a proxy that shows nothing
    would pass the gate that exists to refuse it.
    """
    from PIL import Image

    path = tmp_path / "transparent.png"
    image = Image.new("RGBA", (6, 6), (255, 255, 255, 0))
    image.putpixel((2, 2), (10, 20, 30, 255))
    image.save(path, format="PNG")

    flattened = _raster_rgb(path)
    assert flattened.mode == "RGB"
    assert flattened.getpixel((0, 0)) == (255, 255, 255)
    assert flattened.getpixel((2, 2)) == (10, 20, 30)


# ---------------------------------------------------------------------------
# Per-run formatting in a reconstruction
# ---------------------------------------------------------------------------


def _captured_run(
    text: str,
    *,
    color: str | None = "#000000",
    bold: bool = False,
    size: float = 11.0,
) -> Any:
    from officecli_html_to_pptx._internal.pptx_reader import CapturedRun

    return CapturedRun(
        text=text,
        font_family="Arial",
        font_size_pt=size,
        bold=bold,
        italic=False,
        underline="none",
        color=color,
    )


def _captured_paragraph(*runs: Any) -> Any:
    from officecli_html_to_pptx._internal.pptx_reader import CapturedParagraph

    return CapturedParagraph(
        text="".join(run.text for run in runs),
        align="left",
        line_spacing=None,
        space_before_pt=0.0,
        space_after_pt=0.0,
        direction="ltr",
        bullet="none",
        level=0,
        runs=tuple(runs),
    )


def test_a_reconstruction_writes_every_run_its_own_format() -> None:
    """An ``add`` states one format for a body; a range states one per run.

    A cell whose feature line is red inside black text cannot be rebuilt from the
    object-level colour alone -- the reconstruction painted it black, which the
    independent review found on six cells of src1 page 30 and on the two-line
    subtitle of src1 page 2.  Each run now gets the range the New Deck compiler
    would give it, with every property stated so a run can reset what it inherited.
    """
    from officecli_html_to_pptx._internal.pptx_reader import run_range_sets

    paragraphs = [
        _captured_paragraph(
            _captured_run("Lead-in", color="#C00000", bold=True),
            _captured_run(" rest"),
        ),
        _captured_paragraph(_captured_run("second 中文 line")),
    ]
    sets = run_range_sets("isolated-object", paragraphs)
    assert [item["range"] for item in sets] == ["0:7", "7:12", "12:26"]
    assert sets[0]["color"] == "#C00000"
    assert sets[0]["bold"] == "true"
    assert sets[1]["color"] == "#000000"
    assert sets[1]["bold"] == "false"
    # A paragraph break is part of the body's text, not of the addressable range,
    # so the second paragraph's run starts where the first one's text ended.
    assert sets[2]["range"] == "12:26"
    # Every property is stated on every run, so a run can reset an inherited value.
    for item in sets:
        assert set(item) == {"range", "font", "size", "color", "bold", "italic", "underline"}


def test_one_run_is_left_to_the_body_it_is_added_with() -> None:
    """A single run needs no range: the ``add`` already states its formatting."""
    from officecli_html_to_pptx._internal.pptx_reader import run_range_sets

    assert run_range_sets("x", [_captured_paragraph(_captured_run("only"))]) == []
    assert run_range_sets("x", []) == []


def test_the_range_arithmetic_counts_utf16_units_not_characters() -> None:
    """The count OfficeCLI addresses is UTF-16 code units, as its own writer uses.

    An emoji outside the basic plane is two units, and getting this wrong shifts
    every following range -- which would paint part of one run in the next run's
    colour rather than failing.
    """
    from officecli_html_to_pptx._internal.pptx_reader import (
        _officecli_range_length,
        run_range_sets,
    )

    assert _officecli_range_length("abc") == 3
    assert _officecli_range_length("🚀") == 2
    assert _officecli_range_length("a\nb") == 2, "a paragraph break is not addressed"
    assert _officecli_range_length("a\r\nb") == 2

    sets = run_range_sets(
        "x",
        [
            _captured_paragraph(
                _captured_run("🚀", color="#C00000"), _captured_run("tail")
            )
        ],
    )
    assert [item["range"] for item in sets] == ["0:2", "2:6"]
