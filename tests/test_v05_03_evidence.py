"""Focused Contract 1.3 Evidence and finalization tests for ticket #37."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

import officecli_html_to_pptx.application as application
from officecli_html_to_pptx._internal.localized_evidence import (
    LOCALIZED_DISPOSITIONS,
    audit_localized_fallbacks,
    localized_fallback_surface,
)
from officecli_html_to_pptx.application import get_capabilities
from officecli_html_to_pptx.application import _native_slice_evidence
from officecli_html_to_pptx._internal.officecli_compiler import OfficeCLICompilationResult
from officecli_html_to_pptx.protocol import result


def _localized_manifest() -> tuple[dict[str, object], dict[str, object]]:
    record = {
        "name": "slide-001-picture-001",
        "source_slide": 1,
        "source_object": "slide[1]/div[1]",
        "source_identity": "hero",
        "disposition": "rasterized",
        "reason": "explicit_author_opt_in",
        "kind": "picture",
        "compiled_kind": "picture",
        "editable": False,
        "bounds_pt": [10.0, 20.0, 100.0, 50.0],
        "asset": {
            "mime": "image/png",
            "sha256": "a" * 64,
            "pixel_width": 200,
            "pixel_height": 100,
            "density": 2.0,
        },
        "paint": {"nonblank": True, "blank": False},
        "isolation": {"isolated": True, "contaminated": False},
        "excluded_descendant_count": 2,
        "approved": True,
        "readback": {
            "name": "slide-001-picture-001",
            "source_identity": "hero",
            "source_object": "slide[1]/div[1]",
            "kind": "picture",
            "native_kind": "picture",
            "bounds_pt": [10.0, 20.0, 100.0, 50.0],
            "asset_present": True,
            "asset_sha256": "b" * 64,
            "capture_sha256": "a" * 64,
        },
    }
    manifest = {
        "slide_count": 1,
        "object_kind_counts": {"textbox": 1, "picture": 1},
        "objects": [
            {
                "kind": "textbox",
                "name": "slide-001-textbox-001",
                "source_slide": 1,
                "source_object": "slide[1]/h1[1]",
                "bounds_pt": [1.0, 1.0, 10.0, 10.0],
            },
            record,
        ],
        "localized_fallbacks": [record],
    }
    readback = {
        "slide_count": 1,
        "object_kind_counts": {"textbox": 1, "picture": 1},
        "objects": [
            {
                "kind": "textbox",
                "name": "slide-001-textbox-001",
                "source_slide": 1,
                "source_object": "slide[1]/h1[1]",
                "bounds_pt": [1.0, 1.0, 10.0, 10.0],
            },
            record["readback"],
        ],
    }
    return manifest, readback


def test_capability_surface_publishes_only_public_localized_policy() -> None:
    surface = localized_fallback_surface()
    assert surface["annotation"] == "data-pptx-rasterize"
    assert surface["token"] == "localized"
    assert surface["case_sensitive"] is True
    assert surface["density"]["pixels_per_point"] == 2
    assert surface["dispositions"] == list(LOCALIZED_DISPOSITIONS)
    assert surface["editability"]["content"] is False
    assert "degraded" not in repr(surface)
    assert "locked-visual-proxy" not in repr(surface)

    contract = get_capabilities().data["contract"]
    assert contract["localized_fallback_surface"] == surface


def test_audit_excludes_rasterized_objects_from_native_counts() -> None:
    manifest, readback = _localized_manifest()
    evidence = audit_localized_fallbacks(manifest, readback)

    assert evidence["records"][0]["disposition"] == "rasterized"
    assert evidence["records"][0]["editable"] is False
    assert evidence["counts"]["rasterized"] == 1
    assert evidence["counts"]["native_object_count"] == 1
    assert evidence["counts"]["native_ratio"] == 0.5
    assert evidence["diagnostics"] == {
        "unapproved_rasterized": 0,
        "blank_rasterized": 0,
        "contaminated_rasterized": 0,
        "failed_isolation": 0,
        "unsupported": 0,
        "unresolved": 0,
        "material_delta": 0,
    }


def test_audit_does_not_compare_capture_and_packaged_media_hashes() -> None:
    manifest, readback = _localized_manifest()
    evidence = audit_localized_fallbacks(manifest, readback)
    assert evidence["diagnostics"]["material_delta"] == 0


def test_native_evidence_publishes_localized_audit_without_counting_it_as_native() -> None:
    manifest, readback = _localized_manifest()
    compiled = OfficeCLICompilationResult(
        "synthetic.pptx",
        "author",
        1,
        2,
        (),
        manifest,
    )
    evidence = _native_slice_evidence(
        compiled=compiled,
        readback=readback,
        runtime={"officecli": {"discovered_version": "1.0.151", "compatible": True}},
    )

    assert evidence["localized_fallback"]["counts"]["rasterized_count"] == 1
    assert evidence["counts"]["native_object_count"] == 1
    assert evidence["diagnostics"]["unapproved_rasterized"] == 0
    assert evidence["diagnostics"]["material_delta"] == 0


def test_audit_faults_are_material_and_blocking() -> None:
    manifest, readback = _localized_manifest()
    mutations = (
        ("disposition", "native", "unapproved_rasterized"),
        ("identity", "other", "material_delta"),
        ("path", "slide[1]/div[2]", "material_delta"),
        ("kind", "shape", "material_delta"),
        ("bounds", [11.0, 20.0, 100.0, 50.0], "material_delta"),
        ("hash", "c" * 64, "material_delta"),
        ("density", 1.0, "material_delta"),
        ("paint", False, "blank_rasterized"),
        ("contamination", True, "contaminated_rasterized"),
        ("isolation", False, "failed_isolation"),
        ("descendants", -1, "material_delta"),
        ("readback", "shape", "material_delta"),
    )
    for field, value, gate in mutations:
        current_manifest = deepcopy(manifest)
        current_readback = deepcopy(readback)
        record = current_manifest["localized_fallbacks"][0]
        if field == "disposition":
            record["disposition"] = value
        elif field == "identity":
            record["source_identity"] = value
            record["readback"]["source_identity"] = value
        elif field == "path":
            current_readback["objects"][1]["source_path"] = value
        elif field == "kind":
            record["compiled_kind"] = value
        elif field == "bounds":
            record["bounds_pt"] = value
        elif field == "hash":
            record["asset"]["sha256"] = value
        elif field == "density":
            record["asset"]["density"] = value
        elif field == "paint":
            record["paint"]["nonblank"] = value
            record["paint"]["blank"] = not value
        elif field == "contamination":
            record["isolation"]["contaminated"] = value
        elif field == "isolation":
            record["isolation"]["isolated"] = value
        elif field == "descendants":
            record["excluded_descendant_count"] = value
        elif field == "readback":
            current_readback["objects"][1]["kind"] = value
        result = audit_localized_fallbacks(current_manifest, current_readback)
        assert result["diagnostics"][gate] > 0, field


def test_finalize_rejects_a_tampered_localized_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, readback = _localized_manifest()
    author = tmp_path / "author.html"
    author.write_text(
        '<section class="slide" style="width:1920px;height:1080px"></section>',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        application,
        "diagnose_environment",
        lambda **_: result(
            "doctor",
            "PASS",
            data={
                "runtime": {
                    "officecli": {
                        "discovered_version": "1.0.151",
                        "compatible": True,
                    }
                }
            },
        ),
    )

    async def fake_compile(input_html: str, profile: str, output: str) -> OfficeCLICompilationResult:
        Path(output).write_bytes(b"fake-pptx")
        return OfficeCLICompilationResult(output, profile, 1, 2, (), manifest)

    monkeypatch.setattr(application, "compile_officecli", fake_compile)
    monkeypatch.setattr(application, "_run_officecli", lambda *args: "")
    monkeypatch.setattr(application, "_validate_build_output", lambda _: {"status": "PASS"})
    monkeypatch.setattr(
        application,
        "_collect_issues",
        lambda _: {"status": "PASS", "issue_count": 0},
    )
    monkeypatch.setattr(application, "_collect_readback", lambda *_: readback)

    async def fake_comparisons(_: Path, __: Path, destination: Path, ___: int) -> list[dict[str, str | int]]:
        destination.mkdir(parents=True, exist_ok=True)
        image = destination / "slide-001.png"
        image.write_bytes(b"comparison")
        return [{"slide": 1, "path": str(image), "sha256": application._sha256(image)}]

    monkeypatch.setattr(application, "_make_comparisons", fake_comparisons)
    output = tmp_path / "localized.pptx"
    built = asyncio.run(application.build_author_html(author, output))
    assert built.status == "VISUAL_REVIEW_REQUIRED", built.as_dict()
    evidence_path = output.with_suffix(".evidence")
    native_path = evidence_path / "native-evidence.json"
    native = json.loads(native_path.read_text(encoding="utf-8"))
    native["diagnostics"]["failed_isolation"] = 1
    native_path.write_text(json.dumps(native, indent=2), encoding="utf-8")
    review_path = evidence_path / "visual-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["status"] = "REVIEWED"
    review["slides"][0]["status"] = "PASS"
    review_path.write_text(json.dumps(review, indent=2), encoding="utf-8")

    finalized = application.finalize_build(evidence_path)
    assert finalized.status == "ERROR"
    assert finalized.diagnostics[0].code == "invalid_evidence"
