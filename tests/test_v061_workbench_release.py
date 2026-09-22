"""Focused Product 0.6.1 release-integration checks for ticket #44."""

from __future__ import annotations

import json
from pathlib import Path

from officecli_html_to_pptx import get_capabilities
from officecli_html_to_pptx.application import PUBLIC_COMMANDS
from officecli_html_to_pptx.contract import CONTRACT_VERSION, check_contract
from officecli_html_to_pptx.protocol import PRODUCT_VERSION
from officecli_html_to_pptx.workbench_assets import INDEX_HTML
from officecli_html_to_pptx.workbench import WorkbenchSession


ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "v06_01_workbench_corpus.html"
CORPUS_NOTES = ROOT / "tests" / "fixtures" / "v06_01_workbench_corpus.acceptance.md"
NEGATIVE = ROOT / "tests" / "fixtures" / "v06_01_negative" / "contract-violation.html"
SCENARIOS = ROOT / "tests" / "fixtures" / "v06_01_workbench_scenarios.md"


def test_v061_release_authorities_publish_six_commands_and_workbench_policy() -> None:
    payload = get_capabilities().as_dict()

    assert PRODUCT_VERSION == "0.6.1"
    assert CONTRACT_VERSION == "1.3"
    assert payload["product"]["version"] == "0.6.1"
    assert PUBLIC_COMMANDS == (
        "capabilities",
        "doctor",
        "check",
        "build",
        "finalize",
        "workbench",
    )
    assert payload["data"]["commands"] == list(PUBLIC_COMMANDS)
    assert payload["data"]["workbench"] == {
        "command": "workbench",
        "source_authority": "saved_author_html_sha256",
        "preview_authoritative": False,
        "draft_check": True,
        "save_invalid_candidate": True,
        "build_requires": [
            "draft_sha256_equals_disk_sha256",
            "no_external_modification_conflict",
            "exact_saved_sha_contract_pass",
        ],
        "bind": "loopback-only",
        "session_token": "unguessable",
        "remote_network": False,
    }
    assert payload["data"]["scope"]["existing_pptx_editing"] is False


def test_v061_workbench_ui_is_embedded_and_offline() -> None:
    assert "<textarea id=\"editor\"" in INDEX_HTML
    assert "id=\"preview-frame\"" in INDEX_HTML
    assert "id=\"slide-rail\"" in INDEX_HTML
    assert "data-workbench-marker" not in INDEX_HTML
    assert "cdn." not in INDEX_HTML.lower()
    assert "unpkg.com" not in INDEX_HTML.lower()
    assert "jsdelivr.net" not in INDEX_HTML.lower()
    assert "npm install" not in INDEX_HTML.lower()


def test_v061_tracked_corpus_covers_workbench_acceptance_surface() -> None:
    source = CORPUS.read_text(encoding="utf-8")
    assert source.count('<section class="slide') == 4
    for marker in (
        "&#x5DE5;",
        "<style>",
        "data:image/svg+xml;base64,",
        "data-pptx-shape-geometry=\"roundRect\"",
        "<table",
        "rowspan=\"2\"",
        "data-pptx-chart",
        "data-pptx-chart-spec",
        "JSON.parse(specNode.textContent || \"\")",
        'class: "chart-projection"',
        "data-pptx-rasterize=\"localized\"",
    ):
        assert marker in source
    report = check_contract(CORPUS, "author")
    assert not report.blocked, report.as_dict()
    assert CORPUS_NOTES.is_file()


def test_v061_negative_and_security_scenarios_are_tracked() -> None:
    report = check_contract(NEGATIVE, "author")
    assert report.blocked
    assert any(item.code for item in report.diagnostics)
    scenarios = SCENARIOS.read_text(encoding="utf-8")
    for marker in (
        "CONFLICT",
        "recovery",
        "loopback",
        "session token",
        "authorized asset root",
        "public network",
    ):
        assert marker.lower() in scenarios.lower()


def test_v061_corpus_preview_produces_verified_source_navigation(tmp_path: Path) -> None:
    session = WorkbenchSession.open(
        CORPUS,
        recovery_root=tmp_path / "recovery",
        output_root=tmp_path / "output",
    )
    try:
        session.start()
        preview = session.render_preview(CORPUS.read_text(encoding="utf-8"))
        assert preview["status"] == "CURRENT"
        assert preview["aspect_ratio"] == "16:9"
        assert preview["slide_count"] == 4
        assert preview["source_map"]
        kinds = {item["kind"] for item in preview["source_map"].values()}
        assert {"text", "picture", "table", "shape", "chart", "localized-fallback"} <= kinds
        for marker in preview["source_map"]:
            selection = session.preview_selection(marker, preview["revision"])
            assert selection["status"] == "mapped"
    finally:
        session.close()


def test_v061_plugin_manifest_uses_product_version() -> None:
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.6.1"
    assert "Workbench" in manifest["description"]
