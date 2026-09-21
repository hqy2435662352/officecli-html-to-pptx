"""Public release integration checks for V0.5.1 ticket #26.

The four-slide corpus is intentionally small and attributable.  The full public
Artifact Pair run is performed as the release evidence; these tests keep the
corpus contract and the release-only runtime boundary fast to diagnose.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import officecli_html_to_pptx._internal.officecli_compiler as compiler
from officecli_html_to_pptx._internal.officecli_compiler import OfficeCLICompilationError
from officecli_html_to_pptx.application import get_capabilities
from officecli_html_to_pptx.contract import CONTRACT_VERSION, check_contract
from officecli_html_to_pptx.protocol import PRODUCT_VERSION


FIXTURE = Path(__file__).parent / "fixtures" / "v05_01_public_corpus.html"


def test_public_corpus_is_four_author_slides_and_keeps_projection_corpus_separate() -> None:
    source = FIXTURE.read_text(encoding="utf-8")
    assert source.count('<section class="slide') == 4
    assert source.count('class="slide active"') == 1
    assert "data-pptx-shape-geometry" in source
    assert "rowspan=\"2\" colspan=\"2\"" in source
    assert "<br>" in source
    assert (FIXTURE.with_suffix(".acceptance.md")).is_file()
    report = check_contract(FIXTURE, "author")
    assert not report.blocked, report.as_dict()


def test_release_authorities_publish_product_contract_and_five_commands() -> None:
    payload = get_capabilities().as_dict()
    assert PRODUCT_VERSION == "0.5.2"
    assert CONTRACT_VERSION == "1.2"
    assert payload["product"]["version"] == "0.5.2"
    assert payload["data"]["contract"]["version"] == "1.2"
    assert payload["data"]["commands"] == [
        "capabilities",
        "doctor",
        "check",
        "build",
        "finalize",
    ]
    assert not {"rasterized", "degraded", "fallback_taxonomy"} & set(
        payload["data"]
    )
    assert "data-pptx-shape-geometry" in str(payload["data"]["contract"])


def test_officecli_floor_fails_before_measurement_or_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A below-floor runtime must not enter Chromium or create a PPTX."""

    monkeypatch.setattr(
        compiler,
        "_officecli_runtime_snapshot",
        lambda: {
            "required_version": ">=1.0.151",
            "executable": "C:/runtime/officecli.exe",
            "discovered_version": "1.0.150",
            "compatible": False,
        },
    )

    async def should_not_measure(*_: object, **__: object) -> list[dict[str, object]]:
        raise AssertionError("measurement must not run below the OfficeCLI floor")

    monkeypatch.setattr(compiler, "extract_measurements", should_not_measure)
    output = tmp_path / "blocked.pptx"

    with pytest.raises(OfficeCLICompilationError) as error:
        asyncio.run(compiler.compile_officecli(str(FIXTURE), "author", str(output)))

    assert any(
        item.code == "officecli_version_mismatch"
        and "1.0.150" in item.message
        for item in error.value.diagnostics
    )
    assert not output.exists()


def test_malformed_officecli_version_fails_before_measurement_or_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        compiler,
        "_officecli_runtime_snapshot",
        lambda: {
            "required_version": ">=1.0.151",
            "executable": "C:/runtime/officecli.exe",
            "discovered_version": "not-a-version",
            "compatible": False,
        },
    )

    async def should_not_measure(*_: object, **__: object) -> list[dict[str, object]]:
        raise AssertionError("measurement must not run with a malformed OfficeCLI version")

    monkeypatch.setattr(compiler, "extract_measurements", should_not_measure)
    output = tmp_path / "malformed.pptx"

    with pytest.raises(OfficeCLICompilationError) as error:
        asyncio.run(compiler.compile_officecli(str(FIXTURE), "author", str(output)))

    assert any(
        item.code == "malformed_officecli_version" for item in error.value.diagnostics
    )
    assert not output.exists()
