"""Focused #35 tests for the first localized fallback vertical slice."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil

import pytest

from officecli_html_to_pptx._internal.officecli_compiler import compile_officecli
from officecli_html_to_pptx._internal.acceptance import _officecli_manifest
from officecli_html_to_pptx._internal.localized_evidence import audit_localized_fallbacks
from officecli_html_to_pptx.application import build_author_html, check_author_html
from officecli_html_to_pptx.contract import check_contract
from officecli_html_to_pptx.measurement import extract_measurements


def _html(token: str = "localized") -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  .slide {{ width: 960px; height: 540px; position: relative; background: #ffffff; }}
  .localized {{ position: absolute; left: 80px; top: 70px; width: 240px; height: 120px;
                padding: 34px; color: #ffffff; font: 24px Arial, sans-serif;
                background: transparent; }}
  .localized-visual {{ width: 100%; height: 100%;
                background: linear-gradient(135deg, #e60012, #172033);
                box-shadow: inset 0 0 20px rgba(0,0,0,.35); }}
  .localized span {{ display: block; border: 2px solid #ffffff; padding: 8px; }}
</style></head><body><section class="slide active">
  <div id="hero" class="localized" data-pptx-rasterize="{token}">
    <div class="localized-visual"><span>Local visual</span></div>
  </div>
</section></body></html>"""


@pytest.mark.asyncio
async def test_localized_region_is_one_captured_atomic_measurement(tmp_path: Path) -> None:
    source = tmp_path / "localized.html"
    source.write_text(_html(), encoding="utf-8")

    report = check_contract(source, "author")
    assert not report.blocked, report.as_dict()

    measurements = await extract_measurements(str(source), officecli_mode=True)
    root = measurements[0]["elements"][0]
    assert root["localizedFallback"]["sourceIdentity"] == "hero"
    assert root["children"] == []
    assert root["localizedFallback"]["isolated"] is True
    assert root["localizedFallback"]["density"] == 2.0
    assert root["localizedFallback"]["nonblank"] is True
    assert root["localizedFallback"]["pixelWidth"] == 480
    assert root["localizedFallback"]["pixelHeight"] == 240
    assert root["src"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_localized_region_lowers_to_one_picture_with_readable_asset(
    tmp_path: Path,
) -> None:
    source = tmp_path / "localized.html"
    output = tmp_path / "localized.pptx"
    source.write_text(_html(), encoding="utf-8")

    result = await compile_officecli(str(source), "author", str(output))
    assert result.manifest["object_kind_counts"] == {"picture": 1}
    assert result.manifest["native_object_kind_counts"] == {}
    obj = result.manifest["objects"][0]
    assert obj["kind"] == "picture"
    assert obj["source_identity"] == "hero"
    assert obj["disposition"] == "rasterized"
    assert obj["editable"] is False
    assert obj["metadata"]["localized_fallback"]["asset_sha256"]
    localized = obj["localized_fallback"]
    assert localized["asset"]["pixel_dimensions"] == [480, 240]
    assert localized["asset"]["pixel_width"] == 480
    assert localized["asset"]["pixel_height"] == 240
    assert localized["asset"]["density"] == 2.0
    assert localized["paint"] == {"nonblank": True, "blank": False}
    assert localized["approved"] is True
    assert localized["reason"] == "explicit_author_opt_in"

    readback, _ = _officecli_manifest(output, result.manifest)
    readback_obj = readback["objects"][0]
    assert readback_obj["kind"] == "picture"
    assert readback_obj["source_identity"] == "hero"
    assert readback_obj["localized_fallback"]["readback"]["asset_present"] is True
    assert readback_obj["bounds_pt"] == pytest.approx(obj["bounds_pt"])
    evidence = audit_localized_fallbacks(result.manifest, readback)
    assert evidence["diagnostics"] == {
        "unapproved_rasterized": 0,
        "blank_rasterized": 0,
        "contaminated_rasterized": 0,
        "failed_isolation": 0,
        "unsupported": 0,
        "unresolved": 0,
        "material_delta": 0,
    }
    assert output.is_file()


@pytest.mark.asyncio
async def test_localized_region_without_id_uses_deterministic_source_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "localized-no-id.html"
    source.write_text(_html().replace(' id="hero"', ""), encoding="utf-8")
    measurements = await extract_measurements(str(source), officecli_mode=True)
    assert measurements[0]["elements"][0]["localizedFallback"]["sourceIdentity"] is None

    output = tmp_path / "localized-no-id.pptx"
    result = await compile_officecli(str(source), "author", str(output))
    assert result.manifest["objects"][0]["source_identity"] == "slide[1]/div[1]"


def test_localized_fallback_token_is_exact_and_required(tmp_path: Path) -> None:
    source = tmp_path / "localized.html"
    source.write_text(_html("LOCALIZED"), encoding="utf-8")
    report = check_contract(source, "author")
    assert report.blocked
    assert any(
        item.code == "unsupported_localized_fallback_token"
        for item in report.diagnostics
    )

    source.write_text(_html().replace('data-pptx-rasterize="localized"', ""), encoding="utf-8")
    report = check_contract(source, "author")
    assert report.blocked
    assert any(item.code == "unsupported_visible_css" for item in report.diagnostics)


def test_public_check_reports_localized_fixture(tmp_path: Path) -> None:
    source = tmp_path / "localized.html"
    source.write_text(_html(), encoding="utf-8")
    checked = check_author_html(source)
    assert checked.status == "PASS", checked.as_dict()


@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
def test_public_build_publishes_minimum_localized_evidence(tmp_path: Path) -> None:
    source = tmp_path / "localized.html"
    output = tmp_path / "localized.pptx"
    source.write_text(_html(), encoding="utf-8")

    built = asyncio.run(build_author_html(source, output))
    assert built.status == "VISUAL_REVIEW_REQUIRED", built.as_dict()
    evidence = output.with_suffix(".evidence")
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    readback = json.loads((evidence / "readback.json").read_text(encoding="utf-8"))
    native = json.loads((evidence / "native-evidence.json").read_text(encoding="utf-8"))
    validation = json.loads((evidence / "validate.json").read_text(encoding="utf-8"))
    issues = json.loads((evidence / "issues.json").read_text(encoding="utf-8"))

    assert manifest["object_kind_counts"] == {"picture": 1}
    assert manifest["native_object_kind_counts"] == {}
    assert readback["objects"][0]["disposition"] == "rasterized"
    assert readback["objects"][0]["kind"] == "picture"
    assert validation["status"] == "PASS"
    assert issues["status"] == "PASS"
    assert issues["issue_count"] == 0
    assert native["localized_fallbacks"]["compiled"][0]["editable"] is False
    assert native["localized_fallbacks"]["readback"][0]["disposition"] == "rasterized"
    assert native["diagnostics"]["material_delta"] == 0
