"""Focused Product 0.6.2 public Inspector release checks for ticket #49."""

from __future__ import annotations

import json
from pathlib import Path
import re

from officecli_html_to_pptx import get_capabilities
from officecli_html_to_pptx.application import PUBLIC_COMMANDS
from officecli_html_to_pptx.contract import CONTRACT_VERSION, check_contract
from officecli_html_to_pptx.protocol import PRODUCT_VERSION
from officecli_html_to_pptx.runtime import FORMAL_OFFICECLI_VERSION
from officecli_html_to_pptx.workbench_preview import build_preview


ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "v06_02_inspector_corpus.html"
CORPUS_NOTES = ROOT / "tests" / "fixtures" / "v06_02_inspector_corpus.acceptance.md"
BASELINE = ROOT / "tests" / "fixtures" / "v06_01_full_suite_baseline.json"


def test_v062_public_authorities_publish_exact_inspector_scope() -> None:
    payload = get_capabilities().as_dict()
    workbench = payload["data"]["workbench"]

    assert PRODUCT_VERSION == "0.6.2"
    assert CONTRACT_VERSION == "1.3"
    assert payload["data"]["contract"]["version"] == CONTRACT_VERSION
    assert payload["data"]["rendering_compatibility"]["officecli"] == f">={FORMAL_OFFICECLI_VERSION}" == ">=1.0.151"
    assert PUBLIC_COMMANDS == ("capabilities", "doctor", "check", "build", "finalize", "workbench")
    inspector = workbench["inspector"]
    assert inspector["object_kinds"] == ["text", "shape", "picture", "table-cell", "chart", "localized-fallback"]
    assert inspector["text"]["editable_scope"] == "one_simple_leaf_or_run"
    assert inspector["shape"]["solid_fill_only"] is True
    assert inspector["picture"]["maximum_decoded_import_bytes"] == 10 * 1024 * 1024
    assert inspector["picture"]["object_fit"] == ["fill", "contain", "cover"]
    assert inspector["table_cell"] == {
        "ownership": "merged_region_anchor",
        "properties": ["text", "background-color"],
        "covered_cell": "anchor_or_read_only",
    }
    assert inspector["chart"]["families"] == ["column", "bar", "line", "pie", "doughnut"]
    assert inspector["chart"]["category_chart_series_counts"] == [1, 2, 3]
    assert inspector["chart"]["part_to_whole_series_counts"] == [1]
    assert inspector["chart"]["preview"] == "semantic_projection_from_the_unique_inert_chart_spec"
    assert inspector["mutation"]["draft_compare_and_swap"] == ["draft_revision", "draft_sha256"]
    assert inspector["mutation"]["preview_revision_required"] is True
    assert inspector["excluded"]
    assert workbench["preview_authoritative"] is False


def test_v062_public_corpus_passes_contract_and_covers_chart_matrix() -> None:
    source = CORPUS.read_text(encoding="utf-8")
    report = check_contract(CORPUS, "author")
    assert not report.blocked, report.as_dict()
    assert source.count('<section class="slide') == 7
    specs = [
        json.loads(value)
        for value in re.findall(
            r'<script type="application/json" data-pptx-chart-spec>(.*?)</script>',
            source,
            flags=re.DOTALL,
        )
    ]
    assert len(specs) == 11
    cardinalities: dict[str, set[int]] = {}
    for spec in specs:
        cardinalities.setdefault(spec["type"], set()).add(len(spec["series"]))
    assert cardinalities == {
        "column": {1, 2, 3},
        "bar": {1, 2, 3},
        "line": {1, 2, 3},
        "pie": {1},
        "doughnut": {1},
    }
    assert "addEventListener(\"DOMContentLoaded\"" in source
    assert "JSON.parse(node.textContent || \"\")" in source
    assert "data-pptx-rasterize=\"localized\"" in source
    assert "rowspan=\"2\" colspan=\"2\"" in source
    assert "#editable-text" in source and "#shared-sibling" in source
    assert CORPUS_NOTES.is_file()


def test_v062_workbench_preview_maps_all_public_object_kinds_without_source_markers() -> None:
    source = CORPUS.read_text(encoding="utf-8")
    preview = build_preview(
        source,
        asset_root=CORPUS.parent,
        resource_base_url="http://127.0.0.1/api/asset/",
        preview_origin="http://127.0.0.1",
    )
    kinds = {item["kind"] for item in preview.source_map.values()}
    assert {"text", "picture", "table-cell", "shape", "chart", "localized-fallback"} <= kinds
    assert sum(item["kind"] == "chart" for item in preview.source_map.values()) == 11
    assert len(preview.slides) == 7
    assert not preview.parser_repaired
    assert "workbench-chart-projection" in preview.html
    assert "data-workbench-marker" not in source
    assert "workbench-chart-projection" not in source
    assert '<div class="chart-semantic-preview">' not in source


def test_v061_full_suite_identity_baseline_is_frozen_for_release_comparison() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert baseline["baseline_commit"] == "f44c4163c1bbb5c7b90b03e61fff0e56cb2f8e8f"
    assert baseline["officecli_version"] == "1.0.152"
    assert baseline["summary"] == "21 failed, 738 passed, 5 skipped, 39 errors in 2285.39s"
    assert len(baseline["identities"]["FAILED"]) == 21
    assert len(baseline["identities"]["ERROR"]) == 39
