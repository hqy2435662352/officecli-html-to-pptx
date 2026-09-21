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
        "localized_animation",
        "localized_interactive_content",
        "localized_atomic_descendant",
    } <= codes

    built = asyncio.run(build_author_html(source, output))
    assert built.status == "BLOCK", built.as_dict()
    assert not output.exists()
    assert not output.with_suffix(".evidence").exists()


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
