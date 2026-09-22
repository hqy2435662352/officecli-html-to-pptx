"""Adversarial safety gates for Contract 1.3 localized captures.

These tests exercise the #36 seam before a browser/backend is involved: the
DOM policy rejects content that cannot be reproduced deterministically, while
the PNG audit treats every capture as untrusted bytes.  The end-to-end
compiler/Evidence tests remain owned by the adjacent #35/#37 slices.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from lxml import html
from PIL import Image

from officecli_html_to_pptx._internal.localized_capture import (
    LOCALIZED_CAPTURE_DENSITY,
    LocalizedRegion,
    audit_localized_capture,
    validate_localized_document,
    validate_localized_geometry,
    validate_localized_region_overlap,
)


def _document(body: str):
    return html.fromstring(
        f"""<!doctype html><html><head><style>
        .slide {{ width: 1920px; height: 1080px; position: relative; }}
        </style></head><body><section class="slide">{body}</section></body></html>"""
    )


def _png(size: tuple[int, int], *, mode: str = "RGBA", color=(20, 80, 180, 255)) -> bytes:
    image = Image.new(mode, size, color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_static_inline_svg_region_is_admitted_and_counts_descendants() -> None:
    document = _document(
        '<div id="hero" data-pptx-rasterize="localized">'
        '<svg width="20" height="20"><rect width="20" height="20" fill="#e60012"/></svg>'
        '</div>'
    )

    findings = validate_localized_document(document)

    assert findings == ()
    region = document.xpath('//*[@id="hero"]')[0]
    assert len(list(region.iter())) - 1 == 2


def test_adversarial_fixture_keeps_safe_region_and_blocks_unsafe_region() -> None:
    fixture = Path(__file__).parent / "fixtures" / "v05_03_negative" / "adversarial.html"
    findings = validate_localized_document(html.parse(str(fixture)).getroot())

    assert findings
    assert {item.code for item in findings} >= {
        "localized_executable_content",
        "localized_unsupported_tag",
        "localized_external_resource",
        "localized_interactive_content",
    }
    assert not any("safe-svg" in item.source_object for item in findings)


def test_region_rejects_executable_external_interactive_and_atomic_content() -> None:
    document = _document(
        '<div data-pptx-rasterize="localized" onclick="run()" style="animation: pulse 1s">'
        '<script>window.ran = true</script>'
        '<canvas></canvas><iframe src="https://example.test/frame"></iframe>'
        '<img src="https://example.test/image.png">'
        '<table><tr><td>owned</td></tr></table>'
        '<div data-pptx-chart="bar"></div>'
        '</div>'
    )

    codes = {item.code for item in validate_localized_document(document)}

    assert {
        "localized_executable_content",
        "localized_animation",
        "localized_external_resource",
        "localized_atomic_descendant",
    } <= codes
    assert "localized_unsupported_tag" in codes
    assert "localized_interactive_content" in codes


def test_region_rejects_nested_fallback_and_disallowed_casing() -> None:
    document = _document(
        '<div data-pptx-rasterize="Localized">bad token</div>'
        '<div data-pptx-rasterize="localized">'
        '<span data-pptx-rasterize="localized">nested</span>'
        '</div>'
    )

    codes = {item.code for item in validate_localized_document(document)}

    assert "localized_unknown_token" in codes
    assert "localized_nested_region" in codes


def test_geometry_rejects_zero_size_whole_slide_and_paint_overflow() -> None:
    slide = (0.0, 0.0, 960.0, 540.0)

    zero = validate_localized_geometry(
        "zero", (10.0, 20.0, 0.0, 40.0), slide
    )
    whole_slide = validate_localized_geometry(
        "whole", slide, slide, is_slide_root=True
    )
    overflow = validate_localized_geometry(
        "shadow", (100.0, 100.0, 100.0, 60.0), slide,
        paint_bounds_pt=(98.0, 98.0, 104.0, 64.0),
    )

    assert {item.code for item in zero} == {"localized_unmeasurable"}
    assert {item.code for item in whole_slide} == {"localized_whole_slide"}
    assert {item.code for item in overflow} == {"localized_visual_overflow"}


def test_overlapping_regions_are_blocked_before_capture() -> None:
    regions = (
        LocalizedRegion("first", 1, (10.0, 10.0, 100.0, 80.0)),
        LocalizedRegion("second", 1, (80.0, 20.0, 100.0, 80.0)),
        LocalizedRegion("other-slide", 2, (80.0, 20.0, 100.0, 80.0)),
    )

    findings = validate_localized_region_overlap(regions)

    assert [(item.code, item.source_object) for item in findings] == [
        ("localized_overlap", "second")
    ]


def test_capture_audit_accepts_exact_density_and_is_deterministic() -> None:
    payload = _png((200, 120))

    first = audit_localized_capture(
        payload,
        bounds_pt=(0.0, 0.0, 100.0, 60.0),
        source_object="/html/body/section[1]/div[1]",
        excluded_descendants=1,
    )
    second = audit_localized_capture(
        payload,
        bounds_pt=(0.0, 0.0, 100.0, 60.0),
        source_object="/html/body/section[1]/div[1]",
        excluded_descendants=1,
    )

    assert first.passed
    assert first.pixel_width == 200
    assert first.pixel_height == 120
    assert first.density == LOCALIZED_CAPTURE_DENSITY
    assert first.nonblank
    assert first.isolated
    assert first.asset_sha256 == second.asset_sha256
    assert first.as_dict()["source_object"] == "/html/body/section[1]/div[1]"


def test_capture_audit_blocks_blank_transparent_low_density_contamination_and_overflow() -> None:
    blank = _png((200, 120), color=(0, 0, 0, 0))
    transparent = audit_localized_capture(
        blank,
        bounds_pt=(0.0, 0.0, 100.0, 60.0),
        source_object="blank",
    )
    low_density = audit_localized_capture(
        _png((100, 60)),
        bounds_pt=(0.0, 0.0, 100.0, 60.0),
        source_object="low-density",
    )
    contaminated = audit_localized_capture(
        _png((200, 120)),
        bounds_pt=(0.0, 0.0, 100.0, 60.0),
        source_object="contaminated",
        contamination_fraction=0.01,
    )
    overflow = audit_localized_capture(
        _png((200, 120)),
        bounds_pt=(0.0, 0.0, 100.0, 60.0),
        source_object="overflow",
        overflow=True,
        isolated=False,
    )

    assert "localized_blank_capture" in transparent.failure_codes
    assert "localized_effectively_transparent" in transparent.failure_codes
    assert "localized_low_density" in low_density.failure_codes
    assert "localized_contaminated_capture" in contaminated.failure_codes
    assert "localized_capture_overflow" in overflow.failure_codes
    assert "localized_isolation_failed" in overflow.failure_codes
    assert not any(item.passed for item in (transparent, low_density, contaminated, overflow))


def test_capture_audit_blocks_missing_invalid_and_non_png_assets(tmp_path: Path) -> None:
    missing = audit_localized_capture(
        None,
        bounds_pt=(0.0, 0.0, 100.0, 60.0),
        source_object="missing",
    )
    invalid = audit_localized_capture(
        b"not-a-png",
        bounds_pt=(0.0, 0.0, 100.0, 60.0),
        source_object="invalid",
    )
    text_file = tmp_path / "asset.txt"
    text_file.write_text("not png", encoding="utf-8")
    invalid_path = audit_localized_capture(
        text_file,
        bounds_pt=(0.0, 0.0, 100.0, 60.0),
        source_object="invalid-path",
    )

    assert missing.failure_codes == ("localized_missing_asset",)
    assert invalid.failure_codes == ("localized_invalid_png",)
    assert invalid_path.failure_codes == ("localized_invalid_png",)


def test_capture_audit_treats_malformed_bounds_as_blocking() -> None:
    audit = audit_localized_capture(
        _png((200, 120)),
        bounds_pt=(0.0, 0.0, "not-a-number", 60.0),  # type: ignore[arg-type]
        source_object="malformed-bounds",
    )

    assert "localized_unmeasurable" in audit.failure_codes
    assert not audit.passed
