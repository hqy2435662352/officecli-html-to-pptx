"""Public V0.2 application and protocol seam tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import io
import json
import sys
from pathlib import Path

import pytest

import officecli_html_to_pptx.application as application
from officecli_html_to_pptx import cli
from officecli_html_to_pptx._internal.officecli_compiler import OfficeCLICompilationResult
from officecli_html_to_pptx.protocol import Diagnostic, exit_code_for_status, result
from officecli_html_to_pptx.runtime import (
    SUPPORTED_PLATFORMS,
    UNVALIDATED_PLATFORM_NOTE,
    VALIDATED_PLATFORM_SCOPE,
)


AUTHOR_HTML = """<!doctype html><html><head><style>
.slide { width: 1920px; height: 1080px; }
</style></head><body><section class="slide"><h1>Hello</h1></section></body></html>"""


def _author(tmp_path: Path) -> Path:
    path = tmp_path / "author.html"
    path.write_text(AUTHOR_HTML, encoding="utf-8")
    return path


def test_capabilities_are_author_only_and_use_product_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Inject the platform reader so this test asserts the published contract
    # rather than whichever host it happens to run on: on a platform outside the
    # supported set the membership assertion below would otherwise fail for a
    # reason that has nothing to do with the capability manifest.
    monkeypatch.setattr(application, "current_platform", lambda: "Windows")
    payload = application.get_capabilities().as_dict()

    assert payload["status"] == "PASS"
    assert payload["product"] == {
        "name": "officecli-html-to-pptx",
        "version": "0.6.2",
    }
    assert payload["data"]["commands"] == [
        "capabilities",
        "doctor",
        "check",
        "build",
        "finalize",
        "workbench",
    ]
    assert payload["data"]["contract"]["profile"] == "author"
    # ``platform`` answers "where am I running"; ``supported_platforms`` answers
    # "what does this build support".  Both are needed to decide "supported here".
    assert payload["data"]["platform"] == "Windows"
    assert payload["data"]["supported_platforms"] == list(SUPPORTED_PLATFORMS)
    assert payload["data"]["platform"] in payload["data"]["supported_platforms"]
    # A supported key is coarse ("Linux" matches every distribution), so the
    # accepted environment and the not-implied list are published beside it and a
    # key cannot be read as a broader claim than the acceptance evidence.
    scope = payload["data"]["validated_platform_scope"]
    assert scope["accepted"] == VALIDATED_PLATFORM_SCOPE
    assert scope["not_implied"] == UNVALIDATED_PLATFORM_NOTE
    # The real invariant: every supported key has a declared scope and vice versa.
    # Asserting membership by re-iterating SUPPORTED_PLATFORMS could only raise
    # KeyError, so it would never catch a key added without a scope.
    assert set(payload["data"]["supported_platforms"]) == set(scope["accepted"])
    # The gate does not verify the scope, and that is published rather than implied.
    assert scope["enforced"] is False
    assert "other Linux distributions" in scope["not_implied"]
    assert "macOS" in scope["not_implied"]
    assert payload["data"]["rendering_compatibility"]["officecli"] == ">=1.0.151"
    assert payload["data"]["scope"]["officehtml_import"] is False
    assert "profile" not in payload["data"]["contract"]["css_properties"]


def test_protocol_exit_classes_and_cli_json_stdout_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert exit_code_for_status("PASS") == 0
    assert exit_code_for_status("VISUAL_REVIEW_REQUIRED") == 0
    assert exit_code_for_status("BLOCK") == 2
    assert exit_code_for_status("REVISION_REQUIRED") == 2
    assert exit_code_for_status(
        "ERROR",
        (Diagnostic("invalid_input", "error", "bad"),),
    ) == 3
    assert exit_code_for_status(
        "ERROR",
        (Diagnostic("unexpected_error", "error", "bad"),),
    ) == 4

    code = cli.main(["check", str(tmp_path / "missing.html"), "--json"])
    captured = capsys.readouterr()
    assert code == 3
    assert captured.err == ""
    assert json.loads(captured.out)["status"] == "ERROR"


def test_json_envelope_survives_a_console_code_page_that_cannot_encode_the_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The machine-readable channel is UTF-8, not the console's code page.

    A Chinese Windows console is GBK by default, which cannot encode the
    fixture's ``2\u20e3`` keycap or its emoji.  The envelope used to die with
    ``UnicodeEncodeError`` instead of reporting the finding that quoted them.
    """
    buffer = io.BytesIO()
    monkeypatch.setattr(
        sys, "stdout", io.TextIOWrapper(buffer, encoding="gbk", newline="")
    )
    monkeypatch.setattr(
        sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="gbk", newline="")
    )
    envelope = result(
        "finalize",
        "REVISION_REQUIRED",
        diagnostics=(
            Diagnostic(
                "review_major_finding",
                "major",
                "The PPTX panel rendered 2\u20e3 as a missing-glyph box.",
                True,
            ),
        ),
    )

    code = cli._emit(envelope, json_mode=True)
    sys.stdout.flush()

    assert code == 2
    payload = json.loads(buffer.getvalue().decode("utf-8"))
    assert payload["status"] == "REVISION_REQUIRED"
    assert "2\u20e3" in payload["diagnostics"][0]["message"]


def test_check_pass_and_block_keep_contract_detail(tmp_path: Path) -> None:
    author = _author(tmp_path)
    passed = application.check_author_html(author)
    assert passed.status == "PASS"
    assert passed.data["contract"]["profile"] == "author"

    blocked = tmp_path / "blocked.html"
    blocked.write_text(
        AUTHOR_HTML.replace("<h1>Hello</h1>", "<canvas>bad</canvas>"),
        encoding="utf-8",
    )
    result_value = application.check_author_html(blocked)
    assert result_value.status == "BLOCK"
    assert result_value.exit_code == 2
    assert any(item.code == "unsupported_visible_tag" for item in result_value.diagnostics)
    assert result_value.data["contract"]["css_classifications"]


def test_check_invalid_input_is_exit_class_three(tmp_path: Path) -> None:
    result_value = application.check_author_html(tmp_path / "missing.html")
    assert result_value.status == "ERROR"
    assert result_value.exit_code == 3
    assert result_value.diagnostics[0].code == "invalid_input"


def test_publish_file_retries_windows_sharing_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []
    sleeps: list[float] = []

    def fake_rename(source: Path, target: Path) -> Path:
        calls.append((source, target))
        if len(calls) < 3:
            error = OSError("file is still in use")
            error.winerror = 32  # type: ignore[attr-defined]
            raise error
        return target

    monkeypatch.setattr(Path, "rename", fake_rename)
    monkeypatch.setattr(application.time, "sleep", sleeps.append)

    source = Path("C:/staged.pptx")
    target = Path("C:/published.pptx")
    application._publish_file(source, target)

    assert calls == [(source, target)] * 3
    assert sleeps == [application._PUBLISH_RETRY_DELAY_SECONDS] * 2


def _patch_successful_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        application,
        "diagnose_environment",
        lambda **_: result(
            "doctor",
            "PASS",
            data={
                "runtime": {
                    "formal_pair": {"officecli": ">=1.0.151"},
                    "officecli": {
                        "required_version": ">=1.0.151",
                        "discovered_version": "1.0.151",
                        "compatible": True,
                    },
                }
            },
        ),
    )

    async def fake_compile(input_html: str, profile: str, output: str) -> OfficeCLICompilationResult:
        assert profile == "author"
        Path(output).write_bytes(b"fake-pptx")
        return OfficeCLICompilationResult(
            output,
            "author",
            1,
            1,
            (),
            {
                "slide_count": 1,
                "object_kind_counts": {"shape": 1},
                "objects": [
                    {
                        "kind": "shape",
                        "name": "shape-1",
                        "bounds_pt": [0.0, 0.0, 10.0, 10.0],
                        "text": "",
                        "paragraphs": [],
                        "properties": {"geometry": "rect"},
                    }
                ],
            },
        )

    monkeypatch.setattr(application, "compile_officecli", fake_compile)
    monkeypatch.setattr(application, "_run_officecli", lambda *args: "")
    monkeypatch.setattr(application, "_validate_build_output", lambda _: {"status": "PASS"})
    monkeypatch.setattr(application, "_collect_issues", lambda _: {"status": "PASS", "output": ""})
    monkeypatch.setattr(
        application,
        "_collect_readback",
        lambda *_: {
            "slide_count": 1,
            "slide_size_pt": {"width": 960.0, "height": 540.0},
            "object_kind_counts": {"shape": 1},
            "objects": [
                {
                    "kind": "shape",
                    "name": "shape-1",
                    "source_slide": 1,
                    "bounds_pt": [0.0, 0.0, 10.0, 10.0],
                    "paragraphs": [],
                    "properties": {"geometry": "rect"},
                }
            ],
        },
    )

    async def fake_comparisons(_: Path, __: Path, destination: Path, ___: int) -> list[dict[str, str | int]]:
        destination.mkdir(parents=True, exist_ok=True)
        image = destination / "slide-001.png"
        image.write_bytes(b"comparison")
        return [{"slide": 1, "path": str(image), "sha256": application._sha256(image)}]

    monkeypatch.setattr(application, "_make_comparisons", fake_comparisons)


def _material_manifest() -> dict[str, object]:
    run = {
        "text": "Body",
        "font_family": "Microsoft YaHei",
        "font_size_pt": 12.0,
        "bold": False,
        "italic": False,
        "underline": "none",
        "color": "#000000",
    }
    paragraph = {
        "text": "Body",
        "align": "left",
        "line_spacing": "1.200x",
        "space_before_pt": 1.0,
        "space_after_pt": 2.0,
        "direction": "ltr",
        "runs": [run],
        "hard_break_offsets": [],
    }
    cell_props = {
        "fill": "#FFFFFF",
        "border.top": "1pt solid #000000",
        "border.right": "1pt solid #000000",
        "border.bottom": "1pt solid #000000",
        "border.left": "1pt solid #000000",
        "padding.left": "4pt",
        "padding.right": "4pt",
        "padding.top": "3pt",
        "padding.bottom": "3pt",
        "align": "center",
        "valign": "center",
    }
    cells = []
    for row in range(2):
        for column in range(2):
            cells.append(
                {
                    "bounds_pt": [column * 50.0, row * 20.0, 50.0, 20.0],
                    "text": f"Cell {row},{column}",
                    "props": deepcopy(cell_props),
                    "paragraphs": [deepcopy(paragraph)],
                }
            )
    return {
        "slide_count": 1,
        "object_kind_counts": {"textbox": 1, "shape": 1, "table": 1},
        "objects": [
            {
                "kind": "textbox",
                "name": "textbox-1",
                "bounds_pt": [0.0, 0.0, 100.0, 50.0],
                "text": "Body",
                "properties": {"margin": "0pt"},
                "paragraphs": [deepcopy(paragraph)],
            },
            {
                "kind": "shape",
                "name": "shape-1",
                "bounds_pt": [110.0, 0.0, 100.0, 50.0],
                "text": "",
                "properties": {
                    "geometry": "rect",
                    "fill": "#DCEEFF",
                    "opacity": "0.7800",
                    "line": "#223344:1.5000pt",
                    "lineOpacity": "0.7800",
                    "rotation": "17.000",
                    "margin": "6.0000pt",
                },
                "paragraphs": [],
            },
            {
                "kind": "table",
                "name": "table-1",
                "bounds_pt": [0.0, 60.0, 100.0, 40.0],
                "text": "Cell 0,0Cell 0,1Cell 1,0Cell 1,1",
                "properties": {},
                "rows": 2,
                "columns": 2,
                "column_widths_pt": [50.0, 50.0],
                "row_heights_pt": [20.0, 20.0],
                "normalized_merge_topology": [
                    {"row": 0, "column": 0, "row_span": 1, "column_span": 1},
                    {"row": 0, "column": 1, "row_span": 1, "column_span": 1},
                    {"row": 1, "column": 0, "row_span": 1, "column_span": 1},
                    {"row": 1, "column": 1, "row_span": 1, "column_span": 1},
                ],
                "cells": cells,
            },
        ],
    }


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        (
            "run formatting",
            lambda manifest: manifest["objects"][0]["paragraphs"][0]["runs"][0].update(
                font_size_pt=13.0
            ),
        ),
        (
            "paragraph spacing",
            lambda manifest: manifest["objects"][0]["paragraphs"][0].update(
                space_before_pt=3.0
            ),
        ),
        (
            "shape rotation",
            lambda manifest: manifest["objects"][1]["properties"].update(rotation="18.000"),
        ),
        (
            "shape opacity",
            lambda manifest: manifest["objects"][1]["properties"].update(opacity="0.6200"),
        ),
        (
            "shape line opacity",
            lambda manifest: manifest["objects"][1]["properties"].update(
                lineOpacity="0.6200"
            ),
        ),
        (
            "shape fill",
            lambda manifest: manifest["objects"][1]["properties"].update(fill="#DCEEFE"),
        ),
        (
            "shape outline",
            lambda manifest: manifest["objects"][1]["properties"].update(
                line="#223355:1.5000pt"
            ),
        ),
        (
            "shape margin",
            lambda manifest: manifest["objects"][1]["properties"].update(margin="8.0000pt"),
        ),
        (
            "table column width",
            lambda manifest: manifest["objects"][2].update(column_widths_pt=[52.0, 48.0]),
        ),
        (
            "table row height",
            lambda manifest: manifest["objects"][2].update(row_heights_pt=[22.0, 18.0]),
        ),
        (
            "table cell bounds",
            lambda manifest: manifest["objects"][2]["cells"][0].update(
                bounds_pt=[0.0, 0.0, 48.0, 20.0]
            ),
        ),
        (
            "table cell fill",
            lambda manifest: manifest["objects"][2]["cells"][0]["props"].update(
                fill="#FEF3C7"
            ),
        ),
        (
            "table cell border",
            lambda manifest: manifest["objects"][2]["cells"][0]["props"].update(
                **{"border.top": "2pt solid #000000"}
            ),
        ),
        (
            "table cell padding",
            lambda manifest: manifest["objects"][2]["cells"][0]["props"].update(
                **{"padding.left": "8pt"}
            ),
        ),
        (
            "table cell alignment",
            lambda manifest: manifest["objects"][2]["cells"][0]["props"].update(
                align="right"
            ),
        ),
        (
            "table cell vertical alignment",
            lambda manifest: manifest["objects"][2]["cells"][0]["props"].update(
                valign="top"
            ),
        ),
        (
            "table topology",
            lambda manifest: manifest["objects"][2].update(
                normalized_merge_topology=[
                    {"row": 0, "column": 0, "row_span": 2, "column_span": 1}
                ]
            ),
        ),
        (
            "table cell paragraph formatting",
            lambda manifest: manifest["objects"][2]["cells"][0]["paragraphs"][0].update(
                space_after_pt=4.0
            ),
        ),
    ],
)
def test_native_material_delta_detects_supported_field_mutations(
    label: str,
    mutate: object,
) -> None:
    expected = _material_manifest()
    actual = deepcopy(expected)
    mutate(actual)  # type: ignore[operator]
    assert application._native_material_delta_count(expected, actual) > 0, label


def test_native_material_delta_only_normalizes_confirmed_readback_noise() -> None:
    expected = _material_manifest()
    empty_paragraph = {
        "text": "",
        "align": "left",
        "line_spacing": "1.200x",
        "space_before_pt": 0.0,
        "space_after_pt": 0.0,
        "direction": "ltr",
        "runs": [],
        "hard_break_offsets": [],
    }
    expected["objects"][0]["paragraphs"].append(empty_paragraph)
    actual = deepcopy(expected)
    actual["objects"][0]["paragraphs"][-1]["runs"] = [{"text": ""}]
    actual["objects"][1]["properties"].update(
        fill="#DCEEFFC7",
        line="#223344C7:1.5000pt",
    )

    assert application._native_material_delta_count(expected, actual) == 0

    alpha_mutation = deepcopy(expected)
    alpha_mutation["objects"][1]["properties"]["fill"] = "#DCEEFFC0"
    assert application._native_material_delta_count(expected, alpha_mutation) > 0


def test_finalize_rejects_nonzero_native_material_delta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_successful_build(monkeypatch)
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"
    asyncio.run(application.build_author_html(author, output))
    evidence = tmp_path / "deck.evidence"

    native_path = evidence / "native-evidence.json"
    native_evidence = json.loads(native_path.read_text(encoding="utf-8"))
    native_evidence["diagnostics"]["material_delta"] = 1
    native_path.write_text(
        json.dumps(native_evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    review_path = evidence / "visual-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["status"] = "REVIEWED"
    review["slides"][0]["status"] = "PASS"
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    finalized = application.finalize_build(evidence)
    assert finalized.status == "ERROR"
    assert finalized.exit_code == 3
    assert finalized.diagnostics[0].code == "invalid_evidence"


def test_build_publishes_bound_pair_and_finalize_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_build(monkeypatch)
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"

    built = asyncio.run(application.build_author_html(author, output))
    evidence = tmp_path / "deck.evidence"
    assert built.status == "VISUAL_REVIEW_REQUIRED"
    assert built.exit_code == 0
    assert output.is_file()
    assert evidence.is_dir()
    assert sorted(item.name for item in evidence.iterdir()) == sorted(
        [
            "capabilities.json",
            "comparisons",
            "contract.json",
            "issues.json",
            "manifest.json",
            "native-evidence.json",
            "readback.json",
            "result.json",
            "runtime.json",
            "validate.json",
            "visual-review.json",
        ]
    )
    assert (evidence / "comparisons" / "slide-001.png").is_file()
    assert not list(evidence.rglob("*html_slide*"))
    assert not list(evidence.rglob("*pptx_slide*"))
    native_evidence = json.loads(
        (evidence / "native-evidence.json").read_text(encoding="utf-8")
    )
    assert native_evidence["diagnostics"] == {
        "unsupported": 0,
        "unresolved": 0,
        "material_delta": 0,
        "compiler": [],
    }
    assert native_evidence["counts"]["readback_object_count"] == 1

    review_path = evidence / "visual-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["status"] = "REVIEWED"
    review["slides"][0]["status"] = "PASS"
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    finalized = application.finalize_build(evidence)
    assert finalized.status == "PASS"
    assert finalized.exit_code == 0
    assert (evidence / "finalization.json").is_file()
    finalized_native = json.loads(
        (evidence / "native-evidence.json").read_text(encoding="utf-8")
    )
    assert finalized_native["gate3"] == {
        "status": "PASS",
        "slide_count": 1,
        "reviewed_slides": 1,
    }


def test_build_refuses_either_pair_target_before_compilation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"
    (tmp_path / "deck.evidence").mkdir()
    called = False

    async def should_not_compile(*_: object, **__: object) -> OfficeCLICompilationResult:
        nonlocal called
        called = True
        raise AssertionError("compiler should not run on collision")

    monkeypatch.setattr(application, "compile_officecli", should_not_compile)
    value = asyncio.run(application.build_author_html(author, output))
    assert value.status == "BLOCK"
    assert value.diagnostics[0].code == "artifact_exists"
    assert not called
    assert not output.exists()


def test_build_failure_removes_staging_and_publishes_neither_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_successful_build(monkeypatch)
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"

    async def fail_comparisons(*_: object, **__: object) -> list[dict[str, str | int]]:
        raise RuntimeError("comparison failed")

    monkeypatch.setattr(application, "_make_comparisons", fail_comparisons)
    value = asyncio.run(application.build_author_html(author, output))
    assert value.status == "ERROR"
    assert value.exit_code == 4
    assert not output.exists()
    assert not (tmp_path / "deck.evidence").exists()
    assert not list(tmp_path.glob(".deck-*-*"))


def test_finalize_derives_minor_and_major_outcomes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_build(monkeypatch)
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"
    asyncio.run(application.build_author_html(author, output))
    evidence = tmp_path / "deck.evidence"
    review_path = evidence / "visual-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["slides"][0]["status"] = "PASS"
    review["slides"][0]["findings"] = [
        {
            "severity": "minor",
            "category": "spacing",
            "location": "title",
            "description": "Two pixels of extra space.",
        }
    ]
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    minor = application.finalize_build(evidence)
    assert minor.status == "PASS_WITH_FINDINGS"
    assert minor.exit_code == 0

    review["slides"][0]["findings"][0] = {
        "severity": "major",
        "category": "content",
        "location": "title",
        "description": "Title is missing.",
        "revision": "Restore the title text.",
    }
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    major = application.finalize_build(evidence)
    assert major.status == "REVISION_REQUIRED"
    assert major.exit_code == 2


def test_finalize_rejects_tampered_comparison_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_build(monkeypatch)
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"
    asyncio.run(application.build_author_html(author, output))
    evidence = tmp_path / "deck.evidence"
    comparison = evidence / "comparisons" / "slide-001.png"
    comparison.write_bytes(b"tampered")
    value = application.finalize_build(evidence)
    assert value.status == "ERROR"
    assert value.exit_code == 3
    assert value.diagnostics[0].code == "invalid_evidence"
