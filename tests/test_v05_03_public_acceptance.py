"""Public Product 0.5.3 integration gate for ticket #38.

The localized-fallback tickets own capture, safety, and evidence semantics.
This test proves that Contract 1.3 publishes those seams through the tracked
four-slide corpus and the current six-command Artifact Pair workflow.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil

import pytest

from officecli_html_to_pptx._internal.localized_evidence import (
    LOCALIZED_DIAGNOSTIC_KEYS,
)
from officecli_html_to_pptx.application import (
    build_author_html,
    check_author_html,
    diagnose_environment,
    finalize_build,
    get_capabilities,
)
from officecli_html_to_pptx.contract import CONTRACT_VERSION, check_contract
from officecli_html_to_pptx.protocol import PRODUCT_VERSION


FIXTURE = Path(__file__).parent / "fixtures" / "v05_03_public_corpus.html"


def test_public_localized_corpus_and_release_authority() -> None:
    source = FIXTURE.read_text(encoding="utf-8")
    assert source.count('<section class="slide') == 4
    assert source.count('data-pptx-rasterize="localized"') == 5
    assert source.count("data-pptx-chart") >= 1
    assert "<table" in source
    assert "data-pptx-shape-geometry" in source
    assert (FIXTURE.with_suffix(".acceptance.md")).is_file()

    report = check_contract(FIXTURE, "author")
    assert not report.blocked, report.as_dict()

    payload = get_capabilities().as_dict()
    assert PRODUCT_VERSION == "0.6.1"
    assert CONTRACT_VERSION == "1.3"
    assert payload["product"]["version"] == "0.6.1"
    assert payload["data"]["commands"] == [
        "capabilities",
        "doctor",
        "check",
        "build",
        "finalize",
        "workbench",
    ]
    contract = payload["data"]["contract"]
    assert contract["version"] == "1.3"
    assert {"textbox", "picture", "shape", "table", "chart"} <= set(
        contract["object_kinds"]
    )
    localized = contract["localized_fallback_surface"]
    assert localized["annotation"] == "data-pptx-rasterize"
    assert localized["token"] == "localized"
    assert localized["case_sensitive"] is True
    assert localized["atomic"] is True
    assert localized["geometry"]["source"] == "CSS border box"
    assert localized["density"]["pixels_per_point"] == 2.0
    assert localized["density"]["author_control"] is False
    assert localized["editability"]["content"] is False
    assert localized["dispositions"] == [
        "native",
        "rasterized",
        "unsupported",
        "unresolved",
    ]
    assert localized["blocking_dispositions"] == ["unsupported", "unresolved"]


@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
def test_public_four_slide_workflow_proves_localized_fallback_and_finalize(
    tmp_path: Path,
) -> None:
    output = tmp_path / "v05-03-public-corpus.pptx"

    doctor = diagnose_environment(output_path=output, temp_dir=tmp_path)
    assert doctor.status == "PASS", doctor.as_dict()
    checked = check_author_html(FIXTURE)
    assert checked.status == "PASS", checked.as_dict()

    built = asyncio.run(build_author_html(FIXTURE, output))
    assert built.status == "VISUAL_REVIEW_REQUIRED", built.as_dict()
    evidence = output.with_suffix(".evidence")
    assert output.is_file()
    assert evidence.is_dir()

    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    readback = json.loads((evidence / "readback.json").read_text(encoding="utf-8"))
    native = json.loads((evidence / "native-evidence.json").read_text(encoding="utf-8"))
    validation = json.loads((evidence / "validate.json").read_text(encoding="utf-8"))
    issues = json.loads((evidence / "issues.json").read_text(encoding="utf-8"))
    review_path = evidence / "visual-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))

    assert manifest["slide_count"] == 4
    assert manifest["object_kind_counts"] == {
        "textbox": 16,
        "picture": 5,
        "shape": 2,
        "table": 1,
        "chart": 1,
    }
    assert manifest["native_object_kind_counts"] == {
        "textbox": 16,
        "shape": 2,
        "table": 1,
        "chart": 1,
    }
    assert readback["slide_count"] == 4
    assert readback["object_kind_counts"] == manifest["object_kind_counts"]

    compiled_localized = [
        item for item in manifest["objects"] if item.get("disposition") == "rasterized"
    ]
    readback_localized = [
        item for item in readback["objects"] if item.get("disposition") == "rasterized"
    ]
    assert {item["source_identity"] for item in compiled_localized} == {
        "css-effects",
        "inline-svg",
        "region-a",
        "region-b",
        "integrated-fallback",
    }
    assert len(compiled_localized) == len(readback_localized) == 5
    assert all(
        item["kind"] == item["compiled_kind"] == "picture"
        for item in compiled_localized
    )
    assert all(item["editable"] is False for item in compiled_localized)
    assert {item["source_slide"] for item in compiled_localized} == {1, 2, 3, 4}

    localized = native["localized_fallback"]
    assert len(localized["records"]) == 5
    assert localized["counts"]["rasterized"] == 5
    assert localized["counts"]["native_object_count"] == 20
    assert localized["readback"] == {"picture_count": 5, "matched_count": 5}
    for record in localized["records"]:
        assert record["disposition"] == "rasterized"
        assert record["compiled_kind"] == "picture"
        assert record["editable"] is False
        assert record["approved"] is True
        assert record["asset"]["mime"] == "image/png"
        assert len(record["asset"]["sha256"]) == 64
        assert record["asset"]["density"] == 2.0
        assert record["asset"]["pixel_width"] > 0
        assert record["asset"]["pixel_height"] > 0
        assert record["paint"] == {"nonblank": True, "blank": False}
        assert record["isolation"]["isolated"] is True
        assert record["isolation"]["contaminated"] in (False, None)
        assert record["readback"]["kind"] == "picture"
        readback_metadata = record["readback"]["metadata"]["localized_fallback"]
        assert readback_metadata["readback"]["asset_present"] is True
        assert record["readback"]["bounds_pt"] == pytest.approx(record["bounds_pt"])

    assert native["counts"]["chart_counts"] == {
        "authored": 1,
        "compiled": 1,
        "readback": 1,
    }
    assert native["counts"]["rasterized_object_count"] == 5
    assert native["counts"]["native_object_kind_counts"] == manifest[
        "native_object_kind_counts"
    ]
    assert all(native["diagnostics"][key] == 0 for key in LOCALIZED_DIAGNOSTIC_KEYS)
    assert validation["status"] == "PASS"
    assert validation["returncode"] == 0
    assert issues["status"] == "PASS"
    assert issues["issue_count"] == 0
    assert len(review["comparisons"]) == 4
    assert len(review["slides"]) == 4
    assert native["gate3"]["status"] == "PENDING"

    review["status"] = "REVIEWED"
    for slide in review["slides"]:
        slide["status"] = "REVIEWED"
        slide["reviewed"] = True
        slide["notes"] = (
            "Semantic localized capture, native neighbors, picture placement, "
            "and absence of duplicate descendants reviewed."
        )
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    finalized = finalize_build(evidence)
    assert finalized.status == "PASS", finalized.as_dict()
    finalization = json.loads((evidence / "finalization.json").read_text(encoding="utf-8"))
    assert finalization["gate3"] == {"status": "PASS", "reviewed_slides": 4}
    final_native = json.loads((evidence / "native-evidence.json").read_text(encoding="utf-8"))
    assert final_native["gate3"]["status"] == "PASS"
