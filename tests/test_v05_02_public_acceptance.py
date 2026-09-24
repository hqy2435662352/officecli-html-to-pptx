"""Public Product 0.5.2 integration gate for ticket #32.

The capability tickets own chart parsing, lowering, and independent readback.
This test only proves that the current public workflow publishes those
capabilities through one tracked four-slide Author corpus and a fresh Artifact
Pair.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil

import pytest

from officecli_html_to_pptx.application import (
    build_author_html,
    check_author_html,
    diagnose_environment,
    finalize_build,
    get_capabilities,
)
from officecli_html_to_pptx.contract import CONTRACT_VERSION, check_contract
from officecli_html_to_pptx.protocol import PRODUCT_VERSION


FIXTURE = Path(__file__).parent / "fixtures" / "v05_02_public_corpus.html"


def test_public_chart_corpus_and_release_authority() -> None:
    source = FIXTURE.read_text(encoding="utf-8")
    assert source.count('<section class="slide') == 4
    assert source.count('data-pptx-chart') >= 6
    assert source.count('data-pptx-chart-spec') >= 6
    assert (FIXTURE.with_suffix(".acceptance.md")).is_file()

    report = check_contract(FIXTURE, "author")
    assert not report.blocked, report.as_dict()

    payload = get_capabilities().as_dict()
    assert PRODUCT_VERSION == "0.6.2"
    assert CONTRACT_VERSION == "1.3"
    assert payload["product"]["version"] == "0.6.2"
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
    assert "chart" in contract["object_kinds"]
    chart_surface = contract["chart_surface"]
    assert chart_surface["annotation"] == "data-pptx-chart"
    assert chart_surface["spec_annotation"] == "data-pptx-chart-spec"
    assert chart_surface["types"] == ["column", "bar", "line", "pie", "doughnut"]
    assert chart_surface["preview_descendants"] == "excluded-from-generic-lowering"
    assert chart_surface["fallback"] == "unsupported"


@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
def test_public_four_slide_workflow_proves_native_charts_and_finalize(
    tmp_path: Path,
) -> None:
    output = tmp_path / "v05-02-public-corpus.pptx"

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

    assert manifest["slide_count"] == 4
    assert manifest["object_kind_counts"]["chart"] == 6
    assert readback["object_kind_counts"]["chart"] == 6
    expected_types = {"column", "bar", "line", "pie", "doughnut"}
    compiled_charts = [
        item for item in manifest["objects"] if item.get("kind") == "chart"
    ]
    readback_charts = [
        item for item in readback["objects"] if item.get("kind") == "chart"
    ]
    assert {item["chart"]["type"] for item in compiled_charts} == expected_types
    assert {item["chart"]["type"] for item in readback_charts} == expected_types
    assert all(item["native_kind"] == "chart" for item in readback_charts)
    assert len(compiled_charts) == len(readback_charts) == 6
    for chart in readback_charts:
        assert chart["chart_seam"]["bounds_pt"] == pytest.approx(
            chart["bounds_pt"]
        )

    assert validation["status"] == "PASS"
    assert validation["returncode"] == 0
    assert issues["status"] == "PASS"
    assert issues["issue_count"] == 0
    assert native["diagnostics"]["unsupported"] == 0
    assert native["diagnostics"]["unresolved"] == 0
    assert native["diagnostics"]["material_delta"] == 0
    assert native["counts"]["compiled_object_kind_counts"]["chart"] == 6
    assert native["counts"]["readback_object_kind_counts"]["chart"] == 6
    assert native["counts"]["chart_counts"] == {
        "authored": 6,
        "compiled": 6,
        "readback": 6,
    }
    assert len(native["charts"]["compiled"]) == 6
    assert len(native["charts"]["readback"]) == 6
    assert native["gate3"]["status"] == "PENDING"

    review_path = evidence / "visual-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["status"] = "REVIEWED"
    for slide in review["slides"]:
        slide["status"] = "REVIEWED"
        slide["reviewed"] = True
        slide["notes"] = "Semantic chart family, data order, readability, and native atomicity reviewed."
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    finalized = finalize_build(evidence)
    assert finalized.status == "PASS", finalized.as_dict()
    finalization = json.loads((evidence / "finalization.json").read_text(encoding="utf-8"))
    assert finalization["gate3"] == {"status": "PASS", "reviewed_slides": 4}
    final_native = json.loads((evidence / "native-evidence.json").read_text(encoding="utf-8"))
    assert final_native["gate3"]["status"] == "PASS"
