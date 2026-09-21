"""Public-seam integration checks for the #36 localized safety boundary."""

from __future__ import annotations

import asyncio
from base64 import b64decode
from io import BytesIO
from pathlib import Path
import shutil

import pytest
from PIL import Image

from officecli_html_to_pptx._internal.acceptance import _officecli_manifest
from officecli_html_to_pptx._internal.officecli_compiler import (
    OfficeCLICompilationError,
    compile_officecli,
)
from officecli_html_to_pptx.application import build_author_html, check_author_html
from officecli_html_to_pptx.measurement import extract_measurements


def _svg_html(*, sibling: bool = False) -> str:
    sibling_markup = (
        '<div class="sibling" aria-label="must not be captured"></div>'
        if sibling
        else ""
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  .slide {{ width: 960px; height: 540px; position: relative; background: #ffffff; }}
  .localized {{ position: absolute; left: 80px; top: 70px; width: 240px; height: 120px; }}
  .sibling {{ position: absolute; left: 80px; top: 70px; width: 240px; height: 120px; background: #e60012; z-index: 10; }}
</style></head><body><section class="slide active">
  {sibling_markup}
  <div id="svg-fallback" class="localized" data-pptx-rasterize="localized">
    <svg viewBox="0 0 240 120" width="240" height="120" aria-label="static visual">
      <defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#172033"/><stop offset="1" stop-color="#4f8cff"/></linearGradient></defs>
      <rect width="240" height="120" rx="14" fill="url(#g)"/>
      <circle cx="180" cy="60" r="30" fill="#ffffff" fill-opacity=".75"/>
    </svg>
  </div>
</section></body></html>"""


def _adversarial_html() -> str:
    return """<!doctype html>
<html><head><meta charset="utf-8"><style>
  .slide { width: 960px; height: 540px; position: relative; }
  .bad { position: absolute; left: 40px; top: 40px; width: 240px; height: 120px;
         animation: pulse 1s; }
  @keyframes pulse { from { opacity: .5; } to { opacity: 1; } }
</style></head><body><section class="slide active">
  <div id="bad" class="bad" data-pptx-rasterize="localized" onclick="run()">
    <script>window.ran = true</script>
    <canvas width="100" height="40"></canvas>
    <iframe src="https://example.test/frame"></iframe>
    <img src="https://example.test/image.png">
    <table><tr><td>owned atomic object</td></tr></table>
  </div>
</section></body></html>"""


def _computed_animation_html() -> str:
    return _svg_html().replace(
        ".localized { position: absolute; left: 80px; top: 70px; width: 240px; height: 120px; }",
        ".localized { position: absolute; left: 80px; top: 70px; width: 240px; height: 120px; animation: pulse 1s; }\n"
        "  @keyframes pulse { from { opacity: .8; } to { opacity: 1; } }",
    )


def _computed_external_resource_html() -> str:
    return _svg_html().replace(
        ".localized { position: absolute; left: 80px; top: 70px; width: 240px; height: 120px; }",
        ".localized { position: absolute; left: 80px; top: 70px; width: 240px; height: 120px; background-image: url('https://example.test/remote.png'); }",
    )


def _multi_slide_localized_html() -> str:
    regions = (
        ("one", 40, 50, 200, 100, "#e85d04"),
        ("two", 260, 90, 220, 110, "#0077b6"),
        ("three", 500, 150, 180, 90, "#2a9d8f"),
        ("four", 700, 300, 160, 80, "#8338ec"),
    )
    slides = []
    for index, (name, left, top, width, height, color) in enumerate(regions, 1):
        slides.append(
            f'''<section class="slide{' active' if index == 1 else ''}">
  <div id="localized-{name}" class="localized localized-{name}"
       data-pptx-rasterize="localized">
    <svg viewBox="0 0 {width} {height}" width="{width}" height="{height}">
      <rect width="{width}" height="{height}" rx="12" fill="{color}"/>
      <circle cx="{width - 35}" cy="{height // 2}" r="18" fill="#ffffff" fill-opacity=".8"/>
    </svg>
  </div>
</section>'''
        )
    position_rules = "\n".join(
        f"  .localized-{name} {{ left: {left}px; top: {top}px; width: {width}px; height: {height}px; }}"
        for name, left, top, width, height, _ in regions
    )
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  .slide {{ width: 960px; height: 540px; position: relative; background: #ffffff; }}
  .localized {{ position: absolute; }}
{position_rules}
</style></head><body>{''.join(slides)}</body></html>'''


@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
@pytest.mark.asyncio
async def test_public_inline_svg_localized_fallback_is_one_picture(
    tmp_path: Path,
) -> None:
    source = tmp_path / "inline-svg.html"
    output = tmp_path / "inline-svg.pptx"
    source.write_text(_svg_html(), encoding="utf-8")

    checked = check_author_html(source)
    assert checked.status == "PASS", checked.as_dict()
    compiled = await compile_officecli(str(source), "author", str(output))
    assert compiled.manifest["object_kind_counts"] == {"picture": 1}
    assert compiled.manifest["native_object_kind_counts"] == {}
    picture = compiled.manifest["objects"][0]
    assert picture["kind"] == "picture"
    assert picture["source_identity"] == "svg-fallback"
    assert picture["disposition"] == "rasterized"
    assert picture["editable"] is False
    persisted_isolation = picture["localized_fallback"]["isolation"]["evidence"]
    assert persisted_isolation["passed"] is True
    assert persisted_isolation["target_id_match"] is True
    assert persisted_isolation["outside_paint_pixels"] == 0

    readback, _ = _officecli_manifest(output, compiled.manifest)
    assert len(readback["objects"]) == 1
    assert readback["objects"][0]["kind"] == "picture"
    assert readback["objects"][0]["source_identity"] == "svg-fallback"


def test_public_adversarial_localized_content_blocks_without_artifact_pair(
    tmp_path: Path,
) -> None:
    source = tmp_path / "adversarial.html"
    output = tmp_path / "adversarial.pptx"
    source.write_text(_adversarial_html(), encoding="utf-8")

    checked = check_author_html(source)
    assert checked.status == "BLOCK", checked.as_dict()
    codes = {item.code for item in checked.diagnostics}
    assert {
        "localized_executable_content",
        "localized_unsupported_tag",
        "localized_external_resource",
        "localized_interactive_content",
        "localized_atomic_descendant",
    } <= codes

    built = asyncio.run(build_author_html(source, output))
    assert built.status == "BLOCK", built.as_dict()
    assert not output.exists()
    assert not output.with_suffix(".evidence").exists()


@pytest.mark.asyncio
async def test_computed_styles_block_stylesheet_animation_before_capture(
    tmp_path: Path,
) -> None:
    source = tmp_path / "computed-animation.html"
    output = tmp_path / "computed-animation.pptx"
    source.write_text(_computed_animation_html(), encoding="utf-8")

    # The source-only Contract preflight deliberately does not implement CSS
    # selector matching. Chromium's computed style is the authority here.
    checked = check_author_html(source)
    assert checked.status == "PASS", checked.as_dict()
    measurements = await extract_measurements(str(source), officecli_mode=True)
    element = next(
        item
        for item in measurements[0]["elements"]
        if "localizedFallback" in item
    )
    assert "localized_animation" in element["localizedFallback"][
        "captureFailureCodes"
    ]
    assert "src" not in element

    built = await build_author_html(source, output)
    assert built.status == "BLOCK", built.as_dict()
    assert not output.exists()
    assert not output.with_suffix(".evidence").exists()


@pytest.mark.asyncio
async def test_computed_styles_block_applied_external_resource_before_capture(
    tmp_path: Path,
) -> None:
    source = tmp_path / "computed-resource.html"
    source.write_text(_computed_external_resource_html(), encoding="utf-8")

    checked = check_author_html(source)
    assert checked.status == "PASS", checked.as_dict()
    measurements = await extract_measurements(str(source), officecli_mode=True)
    element = next(
        item
        for item in measurements[0]["elements"]
        if "localizedFallback" in item
    )
    fallback = element["localizedFallback"]
    assert "localized_external_resource" in fallback["captureFailureCodes"]
    assert fallback["computedSafety"]["resourceStates"]
    assert "src" not in element


@pytest.mark.asyncio
async def test_localized_capture_activates_every_source_slide(
    tmp_path: Path,
) -> None:
    source = tmp_path / "multi-slide-localized.html"
    source.write_text(_multi_slide_localized_html(), encoding="utf-8")

    measurements = await extract_measurements(str(source), officecli_mode=True)

    expected = (
        (40, 50, 200, 100),
        (260, 90, 220, 110),
        (500, 150, 180, 90),
        (700, 300, 160, 80),
    )
    assert len(measurements) == len(expected)
    for slide_index, (slide, bounds) in enumerate(zip(measurements, expected), 1):
        elements = [
            item for item in slide["elements"] if "localizedFallback" in item
        ]
        assert len(elements) == 1
        element = elements[0]
        left, top, width, height = bounds
        assert element["x"] == pytest.approx(left)
        assert element["y"] == pytest.approx(top)
        assert element["width"] == pytest.approx(width)
        assert element["height"] == pytest.approx(height)
        assert "src" in element

        fallback = element["localizedFallback"]
        audit = fallback["captureAudit"]
        assert fallback["captureFailureCodes"] == []
        assert audit["pixel_dimensions"]["width"] == width * 2
        assert audit["pixel_dimensions"]["height"] == height * 2
        assert audit["expected_pixel_dimensions"]["width"] == width * 2
        assert audit["expected_pixel_dimensions"]["height"] == height * 2
        assert audit["density"] == pytest.approx(2.0)
        assert audit["isolated"] is True
        assert audit["isolation_evidence"]["passed"] is True
        assert audit["isolation_evidence"]["target_id_match"] is True
        assert audit["isolation_evidence"]["outside_paint_pixels"] == 0
        assert fallback["sourcePath"].startswith(f"slide[{slide_index}]/")


@pytest.mark.asyncio
async def test_isolated_capture_excludes_overlapping_sibling_and_overflow_blocks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "isolated.html"
    source.write_text(_svg_html(sibling=True), encoding="utf-8")

    measurements = await extract_measurements(str(source), officecli_mode=True)
    element = next(
        item
        for item in measurements[0]["elements"]
        if "localizedFallback" in item
    )
    fallback = element["localizedFallback"]
    assert fallback["isolated"] is True
    assert fallback["captureAudit"]["contamination_fraction"] == 0.0
    isolation = fallback["captureAudit"]["isolation_evidence"]
    assert isolation["passed"] is True
    assert isolation["target_id_match"] is True
    assert isolation["authored_top_level_target_count"] == 1
    assert isolation["authored_top_level_target"] is True
    assert isolation["authored_sibling_count"] == 0
    assert isolation["no_authored_siblings"] is True
    assert isolation["master_layout_background_count"] == 0
    assert isolation["no_master_layout_background"] is True
    assert isolation["transparent_cleared_container"] is True
    assert isolation["outside_paint_pixels"] == 0
    assert isolation["outside_pixel_count"] > 0
    assert isolation["pixel_outside_wrapper_zero"] is True
    image = Image.open(BytesIO(b64decode(element["src"].split(",", 1)[1]))).convert(
        "RGBA"
    )
    assert image.getpixel((image.width // 2, image.height // 2))[:3] != (230, 0, 18)

    overflow_source = tmp_path / "overflow.html"
    overflow_source.write_text(
        _svg_html().replace(
            ".localized { position: absolute; left: 80px; top: 70px; width: 240px; height: 120px; }",
            ".localized { position: absolute; left: 80px; top: 70px; width: 240px; height: 120px; box-shadow: 0 20px 20px rgba(0,0,0,.4); }",
        ),
        encoding="utf-8",
    )
    overflow_measurements = await extract_measurements(
        str(overflow_source), officecli_mode=True
    )
    overflow_element = next(
        item
        for item in overflow_measurements[0]["elements"]
        if "localizedFallback" in item
    )
    overflow_fallback = overflow_element["localizedFallback"]
    assert "localized_capture_overflow" in overflow_fallback["captureFailureCodes"]
    assert "src" not in overflow_element

    with pytest.raises(OfficeCLICompilationError) as failure:
        await compile_officecli(
            str(overflow_source), "author", str(tmp_path / "overflow.pptx")
        )
    assert failure.value.diagnostics[0].code == "unresolved_localized_fallback_capture"
