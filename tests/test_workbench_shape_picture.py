"""Focused Shape/Picture Inspector checks at the source-patch boundary."""

from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import zlib

from PIL import Image
import pytest

from officecli_html_to_pptx.workbench_preview import build_preview
from officecli_html_to_pptx.workbench import WorkbenchSession
from officecli_html_to_pptx.runtime import officecli_runtime_snapshot
from officecli_html_to_pptx.workbench_shape_picture import (
    apply_shape_picture_patch,
    inspect_shape_picture_selection,
)


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 1), (32, 96, 160)).save(output, format="PNG")
    return output.getvalue()


def _browser_fixture_html() -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: 1920px; height: 1080px; }}
.slide {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; background-color: #ffffff; }}
.shape {{ position: absolute; left: 60px; top: 60px; width: 400px; height: 200px; background-color: #ccfbf1; color: #134e4a; border: 4px solid #0f766e; opacity: .9; font-size: 30px; }}
.picture {{ position: absolute; left: 520px; top: 60px; width: 320px; height: 180px; object-fit: contain; }}
</style></head><body><section class="slide">
<div id="shape" class="shape" data-pptx-shape-geometry="roundRect">Start</div>
<img id="picture" class="picture" alt="acceptance image" src="{_png_uri()}">
</section></body></html>"""


def _start_workbench(path: Path, recovery_root: Path) -> tuple[WorkbenchSession, object, threading.Thread]:
    session = WorkbenchSession.open(path, recovery_root=recovery_root)
    startup = session.start()
    thread = threading.Thread(target=session.serve_forever, daemon=True)
    thread.start()
    for _ in range(100):
        if session.is_running:
            break
        time.sleep(0.01)
    return session, startup, thread


def _png_uri(data: bytes | None = None, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(data or _png_bytes()).decode("ascii")


def _png_with_size(size: int) -> bytes:
    base = _png_bytes()
    payload_size = size - len(base) - 12
    assert payload_size >= 0
    chunk_data = b"x" * payload_size
    chunk_type = b"npTc"
    chunk = (
        len(chunk_data).to_bytes(4, "big")
        + chunk_type
        + chunk_data
        + zlib.crc32(chunk_type + chunk_data).to_bytes(4, "big")
    )
    return base[:-12] + chunk + base[-12:]


def _shape_html() -> str:
    return """<!doctype html><html><head><style>
.slide { width: 1920px; height: 1080px; }
.shared { background-color: #ccfbf1; border-color: #0f766e; border-width: 4px; border-style: solid; opacity: .9; }
</style></head><body><section class="slide">
<div id="first" class="shared" data-pptx-shape-geometry="roundRect">Old &amp; safe</div>
<div id="sibling" class="shared" data-pptx-shape-geometry="rect">Keep sibling</div>
</section></body></html>"""


def _picture_html(src: str | None = None, *, extra_attrs: str = "") -> str:
    source = src or _png_uri()
    return (
        '<!doctype html><html><head><style>.slide { width:1920px; height:1080px; }</style></head><body>'
        '<section class="slide"><img id="photo" alt="keep this text" width="320" height="180" '
        f'{extra_attrs} src="{source}" style="object-fit: contain"></section></body></html>'
    )


def _preview_selection(html: str, kind: str, asset_root: Path) -> dict:
    preview = build_preview(
        html,
        asset_root=asset_root,
        resource_base_url="http://127.0.0.1:8234/api/preview/resource/token/",
        preview_origin="http://127.0.0.1:8234",
    )
    marker, entry = next(
        (marker, item)
        for marker, item in preview.source_map.items()
        if item["kind"] == kind
    )
    return {"preview": preview, "marker": marker, "selection": preview.selection(marker)}


def _shape_styles() -> dict:
    styles = {
        "background-color": "rgb(204, 251, 241)",
        "background-image": "none",
        "border-color": "rgb(15, 118, 110)",
        "border-width": "4px",
        "opacity": "0.9",
    }
    for side in ("top", "right", "bottom", "left"):
        styles[f"border-{side}-color"] = "rgb(15, 118, 110)"
        styles[f"border-{side}-width"] = "4px"
        styles[f"border-{side}-style"] = "solid"
    return styles


def _shape_rules() -> dict:
    return {
        "rules_complete": True,
        "sources": [
            {"property": "background-color", "value": "#ccfbf1", "important": False, "selector": ".shared", "scope": "element"},
            {"property": "border-color", "value": "#0f766e", "important": False, "selector": ".shared", "scope": "element"},
            {"property": "border-width", "value": "4px", "important": False, "selector": ".shared", "scope": "element"},
            {"property": "border-style", "value": "solid", "important": False, "selector": ".shared", "scope": "element"},
            {"property": "opacity", "value": ".9", "important": False, "selector": ".shared", "scope": "element"},
        ],
    }


def _picture_styles(fit: str = "contain") -> dict:
    return {"object-fit": fit}


def _picture_rules(fit: str = "contain") -> dict:
    return {
        "rules_complete": True,
        "sources": [
            {"property": "object-fit", "value": fit, "important": False, "selector": "element.style", "scope": "element"},
        ],
    }


def test_shape_controls_patch_only_selected_source_and_preserve_simple_text(tmp_path: Path) -> None:
    html = _shape_html()
    selected = _preview_selection(html, "shape", tmp_path)
    inspector = inspect_shape_picture_selection(html, selected["selection"], {"text": "Old & safe", "styles": _shape_styles()}, _shape_rules())
    fields = inspector["fields"]
    assert fields["data-pptx-shape-geometry"]["options"][0] == "rect"
    assert fields["data-pptx-shape-geometry"]["editable"]
    assert fields["background-color"]["editable"] and fields["background-color"]["local_override"]
    assert fields["border-color"]["editable"]
    assert fields["border-width"]["editable"]
    assert fields["opacity"]["editable"]
    assert inspector["text"]["editable"]

    fill_patch = apply_shape_picture_patch(
        html,
        selected["selection"],
        {"kind": "property", "name": "background-color", "value": "#123456"},
        {"text": "Old & safe", "styles": _shape_styles()},
        _shape_rules(),
    )
    assert fill_patch["local_override"] is True
    assert 'style="background-color: #123456"' in fill_patch["text"]
    assert ".shared { background-color: #ccfbf1;" in fill_patch["text"]
    assert 'id="sibling" class="shared" data-pptx-shape-geometry="rect">Keep sibling' in fill_patch["text"]
    rgba_patch = apply_shape_picture_patch(
        html,
        selected["selection"],
        {"kind": "property", "name": "background-color", "value": "rgba(12, 34, 56, 0.999)"},
        {"text": "Old & safe", "styles": _shape_styles()},
        _shape_rules(),
    )
    assert "rgba(12, 34, 56, 0.999)" in rgba_patch["text"]

    geometry_selection = _preview_selection(html, "shape", tmp_path)["selection"]
    geometry_patch = apply_shape_picture_patch(
        html,
        geometry_selection,
        {"kind": "property", "name": "data-pptx-shape-geometry", "value": "ellipse"},
        {"text": "Old & safe", "styles": _shape_styles()},
        _shape_rules(),
    )
    assert 'data-pptx-shape-geometry="ellipse"' in geometry_patch["text"]
    assert 'style="border-radius: 50%"' in geometry_patch["text"]
    triangle_html = html.replace('data-pptx-shape-geometry="roundRect"', 'data-pptx-shape-geometry="triangle"')
    triangle_selection = _preview_selection(triangle_html, "shape", tmp_path)["selection"]
    triangle_inspector = inspect_shape_picture_selection(
        triangle_html, triangle_selection, {"styles": _shape_styles()}, _shape_rules()
    )
    assert "rectangular source box" in triangle_inspector["fields"]["data-pptx-shape-geometry"]["preview_note"]
    text_patch = apply_shape_picture_patch(
        html,
        geometry_selection,
        {"kind": "text", "value": '新文字 & <shape> "x"'},
        {"text": "Old & safe", "styles": _shape_styles()},
        _shape_rules(),
    )
    assert "新文字 &amp; &lt;shape&gt; &quot;x&quot;" in text_patch["text"]


def test_shape_rejects_unsupported_values_and_nonuniform_borders_without_mutation(tmp_path: Path) -> None:
    html = _shape_html()
    selected = _preview_selection(html, "shape", tmp_path)["selection"]
    bad_styles = _shape_styles()
    bad_styles["border-left-width"] = "7px"
    read_only = inspect_shape_picture_selection(html, selected, {"styles": bad_styles}, _shape_rules())
    assert not read_only["fields"]["border-width"]["editable"]
    assert "uniform solid border" in read_only["fields"]["border-width"]["reason"]
    with pytest.raises(ValueError, match="native geometry tokens"):
        apply_shape_picture_patch(
            html,
            selected,
            {"kind": "property", "name": "data-pptx-shape-geometry", "value": "freeform"},
            {"styles": _shape_styles()},
            _shape_rules(),
        )
    with pytest.raises(ValueError, match="simple hex"):
        apply_shape_picture_patch(
            html,
            selected,
            {"kind": "property", "name": "background-color", "value": "linear-gradient(red, blue)"},
            {"styles": _shape_styles()},
            _shape_rules(),
        )
    for invalid_color in ("rgb(12, 34, 56, 0.5)", "rgba(12, 34, 56, 1.01)", "rgba(256, 0, 0, 0.5)"):
        with pytest.raises(ValueError):
            apply_shape_picture_patch(
                html,
                selected,
                {"kind": "property", "name": "background-color", "value": invalid_color},
                {"styles": _shape_styles()},
                _shape_rules(),
            )
    zero_width_patch = apply_shape_picture_patch(
        html,
        selected,
        {"kind": "property", "name": "border-width", "value": "0px"},
        {"styles": _shape_styles()},
        _shape_rules(),
    )
    assert "border-width: 0px" in zero_width_patch["text"]


def test_shape_reports_inline_shorthand_origin_and_keeps_it_read_only(tmp_path: Path) -> None:
    html = _shape_html().replace(
        'data-pptx-shape-geometry="roundRect">Old',
        'data-pptx-shape-geometry="roundRect" style="background: #123456">Old',
    )
    selected = _preview_selection(html, "shape", tmp_path)["selection"]
    styles = _shape_styles()
    styles["background-color"] = "rgb(18, 52, 86)"
    inspector = inspect_shape_picture_selection(html, selected, {"styles": styles}, _shape_rules())
    fill = inspector["fields"]["background-color"]
    assert fill["source"] == "background: #123456"
    assert fill["origin"] == "inline style"
    assert not fill["editable"]
    assert not fill["local_override"]


def test_picture_replacement_and_fit_preserve_unrelated_markup(tmp_path: Path) -> None:
    html = _picture_html(extra_attrs='data-owner="source"')
    selected = _preview_selection(html, "picture", tmp_path)["selection"]
    inspector = inspect_shape_picture_selection(html, selected, {"styles": _picture_styles()}, _picture_rules())
    assert inspector["fields"]["src"]["editable"]
    assert inspector["fields"]["object-fit"]["editable"]
    assert inspector["fields"]["src"]["source"].startswith("image/png data URI")

    replacement = _png_uri(_png_bytes())
    source_patch = apply_shape_picture_patch(
        html,
        selected,
        {"kind": "property", "name": "src", "value": replacement},
        {"styles": _picture_styles()},
        _picture_rules(),
    )
    assert f'src="{replacement}"' in source_patch["text"]
    assert 'alt="keep this text" width="320" height="180" data-owner="source"' in source_patch["text"]

    fit_patch = apply_shape_picture_patch(
        html,
        selected,
        {"kind": "property", "name": "object-fit", "value": "cover"},
        {"styles": _picture_styles()},
        _picture_rules(),
    )
    assert 'style="object-fit: cover"' in fit_patch["text"]
    assert 'alt="keep this text" width="320" height="180"' in fit_patch["text"]


def test_picture_import_enforces_decoded_limit_and_actual_mime(tmp_path: Path) -> None:
    html = _picture_html()
    selected = _preview_selection(html, "picture", tmp_path)["selection"]
    at_limit = _png_uri(_png_with_size(10 * 1024 * 1024))
    accepted = apply_shape_picture_patch(
        html,
        selected,
        {"kind": "property", "name": "src", "value": at_limit},
        {"styles": _picture_styles()},
        _picture_rules(),
    )
    assert 'src="' + at_limit + '"' in accepted["text"]

    too_large = _png_uri(_png_with_size(10 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="10 MiB decoded import limit"):
        apply_shape_picture_patch(
            html,
            selected,
            {"kind": "property", "name": "src", "value": too_large},
            {"styles": _picture_styles()},
            _picture_rules(),
        )

    with pytest.raises(ValueError, match="MIME/content mismatch"):
        apply_shape_picture_patch(
            html,
            selected,
            {"kind": "property", "name": "src", "value": _png_uri(mime="image/jpeg")},
            {"styles": _picture_styles()},
            _picture_rules(),
        )
    with pytest.raises(ValueError, match="malformed"):
        apply_shape_picture_patch(
            html,
            selected,
            {"kind": "property", "name": "src", "value": "data:image/png;base64,%%%"},
            {"styles": _picture_styles()},
            _picture_rules(),
        )


def test_ambiguous_picture_sources_and_important_properties_are_read_only(tmp_path: Path) -> None:
    html = _picture_html(extra_attrs='srcset="data:image/png;base64,AAAA 1x"')
    selected = _preview_selection(html, "picture", tmp_path)["selection"]
    inspector = inspect_shape_picture_selection(html, selected, {"styles": _picture_styles()}, _picture_rules())
    assert not inspector["fields"]["src"]["editable"]
    assert "srcset" in inspector["fields"]["src"]["reason"]
    with pytest.raises(ValueError, match="srcset"):
        apply_shape_picture_patch(
            html,
            selected,
            {"kind": "property", "name": "src", "value": _png_uri()},
            {"styles": _picture_styles()},
            _picture_rules(),
        )

    important = _picture_rules()
    important["sources"][0]["important"] = True
    ordinary_html = _picture_html()
    ordinary_selection = _preview_selection(ordinary_html, "picture", tmp_path)["selection"]
    read_only_fit = inspect_shape_picture_selection(ordinary_html, ordinary_selection, {"styles": _picture_styles()}, important)
    assert not read_only_fit["fields"]["object-fit"]["editable"]


@pytest.mark.asyncio
async def test_browser_shape_picture_patch_save_check_and_native_build(tmp_path: Path) -> None:
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright, expect

    if not shutil.which("officecli") or not officecli_runtime_snapshot().get("compatible"):
        pytest.skip("The focused native acceptance requires a compatible OfficeCLI runtime.")
    source = tmp_path / "author.html"
    original = _browser_fixture_html()
    source.write_text(original, encoding="utf-8")
    session, startup, thread = _start_workbench(source, tmp_path / "recovery")
    replacement_path = tmp_path / "replacement.png"
    replacement = BytesIO()
    Image.new("RGB", (4, 2), (210, 40, 80)).save(replacement, format="PNG")
    replacement_path.write_bytes(replacement.getvalue())
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            await page.goto(startup.url)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=10000)
            preview = page.locator("#preview-frame").content_frame
            assert await preview.locator("#shape").evaluate(
                "element => parseFloat(getComputedStyle(element).borderRadius)"
            ) > 0

            await preview.locator("#shape").click(force=True)
            await expect(page.locator("#inspector-selection")).to_contain_text("Slide 1 · shape · <div>", timeout=5000)
            await expect(page.locator('select[aria-label="data-pptx-shape-geometry value"]')).to_be_enabled()
            await expect(page.locator("#inspector-fields")).to_contain_text("Local override:")
            await page.locator('select[aria-label="data-pptx-shape-geometry value"]').select_option("ellipse")
            await expect(page.locator("#source-diff")).to_contain_text("ellipse", timeout=5000)
            await expect(page.locator("#source-diff")).to_contain_text("border-radius: 50%", timeout=5000)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=10000)
            assert await preview.locator("#shape").evaluate("element => getComputedStyle(element).borderRadius") == "50%"

            await preview.locator("#shape").click(force=True)
            fill = page.locator('input[aria-label="background-color value"]')
            await expect(fill).to_be_enabled(timeout=5000)
            await fill.fill("#00aacc")
            await page.get_by_role("button", name="Apply background-color").click()
            await expect(page.locator("#source-diff")).to_contain_text("#00aacc", timeout=5000)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=10000)
            assert await preview.locator("#shape").evaluate("element => getComputedStyle(element).backgroundColor") == "rgb(0, 170, 204)"

            await preview.locator("#shape").click(force=True)
            border_color = page.locator('input[aria-label="border-color value"]')
            await expect(border_color).to_be_enabled(timeout=5000)
            await border_color.fill("#ff0000")
            await page.get_by_role("button", name="Apply border-color").click()
            await expect(page.locator("#source-diff")).to_contain_text("#ff0000", timeout=5000)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=10000)

            await preview.locator("#shape").click(force=True)
            border_width = page.locator('input[aria-label="border-width value"]')
            await expect(border_width).to_be_enabled(timeout=5000)
            await border_width.fill("6px")
            await page.get_by_role("button", name="Apply border-width").click()
            await expect(page.locator("#source-diff")).to_contain_text("6px", timeout=5000)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=10000)

            await preview.locator("#shape").click(force=True)
            opacity = page.locator('input[aria-label="opacity value"]')
            await expect(opacity).to_be_enabled(timeout=5000)
            await opacity.fill("0.5")
            await page.get_by_role("button", name="Apply opacity").click()
            await expect(page.locator("#source-diff")).to_contain_text("0.5", timeout=5000)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=10000)

            await preview.locator("#shape").click(force=True)
            await page.locator("#inspector-text").fill("Ready <A>")
            await page.locator("#apply-text").click()
            await expect(page.locator("#source-diff")).to_contain_text("Ready &lt;A&gt;", timeout=5000)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=10000)
            assert await preview.locator("#shape").inner_text() == "Ready <A>"

            await preview.locator("#picture").click(force=True)
            await expect(page.locator("#inspector-selection")).to_contain_text("Slide 1 · picture · <img>", timeout=5000)
            await page.locator('input[aria-label="Replacement image file, up to 10 MiB"]').set_input_files(str(replacement_path))
            await expect(page.locator("#source-diff")).to_contain_text("data:image/png", timeout=10000)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=10000)

            await preview.locator("#picture").click(force=True)
            await page.locator('select[aria-label="object-fit value"]').select_option("cover")
            await expect(page.locator("#source-diff")).to_contain_text("object-fit: cover", timeout=5000)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=10000)
            assert await preview.locator("#picture").evaluate("element => getComputedStyle(element).objectFit") == "cover"

            await page.locator("#save").click()
            await expect(page.locator("#state")).to_have_text("SAVED", timeout=10000)
            await page.locator("#check").click()
            await expect(page.locator("#contract-status")).to_have_text("PASS", timeout=30000)
            await expect(page.locator("#build")).to_be_enabled()
            await page.locator("#build").click()
            await expect(page.locator("#build-status")).to_have_text(
                re.compile(r"^(PASS|PASS_WITH_FINDINGS|VISUAL_REVIEW_REQUIRED)$"), timeout=180000
            )
            await browser.close()

        build = session.document.snapshot()["build"]
        assert build["artifact_pair_complete"]
        pptx = Path(build["target_pptx"])
        assert pptx.is_file()
        evidence = Path(build["target_evidence"])
        assert evidence.is_dir()
        validation = subprocess.run(["officecli", "validate", str(pptx)], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert validation.returncode == 0, validation.stdout + validation.stderr
        slide_readback = subprocess.run(
            ["officecli", "get", str(pptx), "/slide[1]", "--depth", "3", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert slide_readback.returncode == 0, slide_readback.stdout + slide_readback.stderr
        slide = json.loads(slide_readback.stdout)["data"]["results"][0]
        native_shape = next(child for child in slide["children"] if child["type"] == "shape")
        native_picture = next(child for child in slide["children"] if child["type"] == "picture")
        assert native_shape["format"]["geometry"] == "ellipse"
        assert native_shape["format"]["fill"].startswith("#00AACC")
        assert native_shape["format"]["opacity"] == "0.5"
        assert native_shape["format"]["line"].startswith("#FF0000")
        assert native_shape["format"]["lineWidth"] == "3pt"
        assert native_shape["text"] == "Ready <A>"
        payload_path = tmp_path / "native-picture-readback.png"
        picture_readback = subprocess.run(
            ["officecli", "get", str(pptx), native_picture["path"], "--save", str(payload_path), "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert picture_readback.returncode == 0, picture_readback.stdout + picture_readback.stderr
        native_picture_data = json.loads(picture_readback.stdout)["data"]["results"][0]
        assert native_picture_data["type"] == "picture"
        assert native_picture_data["format"]["contentType"] == "image/png"
        assert payload_path.read_bytes() == replacement_path.read_bytes()
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()
