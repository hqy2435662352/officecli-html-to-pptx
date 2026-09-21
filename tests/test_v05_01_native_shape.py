"""Focused public-seam tests for V0.5.1 native shape geometry."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from officecli_html_to_pptx.application import get_capabilities
from officecli_html_to_pptx.contract import SHAPE_GEOMETRY_TOKENS, check_contract
from officecli_html_to_pptx._internal.officecli_compiler import (
    OfficeCLICompilationError,
    _shape_geometry,
    compile_officecli,
)


FIXTURE = Path(__file__).parent / "fixtures" / "v05_01_native_shape.html"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "shape.html"
    path.write_text(
        "<!doctype html><html><head><style>.slide{width:1920px;height:1080px;position:relative}</style></head>"
        f"<body><section class='slide'>{body}</section></body></html>",
        encoding="utf-8",
    )
    return path


def test_shape_geometry_manifest_is_closed_and_public() -> None:
    payload = get_capabilities().data["contract"]["shape_geometry_surface"]
    assert payload["attribute"] == "data-pptx-shape-geometry"
    assert payload["tokens"] == list(SHAPE_GEOMETRY_TOKENS)
    assert "data-shape-geometry" not in json.dumps(payload)
    assert "data-pptx-kind" not in json.dumps(payload)


def test_public_authoring_guide_documents_only_namespaced_geometry() -> None:
    guide = (
        Path(__file__).parents[1]
        / "skills"
        / "build-a-pptx-with-html"
        / "references"
        / "author-html.md"
    ).read_text(encoding="utf-8")
    assert "data-pptx-shape-geometry" in guide
    assert "data-shape-geometry" not in guide


def test_author_contract_accepts_exact_public_geometry_tokens(tmp_path: Path) -> None:
    body = "".join(
        f'<div data-pptx-shape-geometry="{token}" '
        "style='position:absolute;left:10px;top:10px;width:100px;height:50px;background:#fff'>x</div>"
        for token in SHAPE_GEOMETRY_TOKENS
    )
    report = check_contract(_write(tmp_path, body), "author")
    assert report.status == "PASS", report.as_dict()


def test_private_projection_alias_is_accepted_only_with_projection_identity(
    tmp_path: Path,
) -> None:
    report = check_contract(
        _write(
            tmp_path,
            '<div data-source-object="/slide[1]/shape[1]" data-source-kind="shape" '
            'data-projection-disposition="native" data-projection-id="projection-shape-1" '
            'data-shape-geometry="ellipse" '
            'style="position:absolute;left:10px;top:10px;width:100px;height:100px;background:#fff">x</div>',
        ),
        "author",
    )
    assert report.status == "PASS", report.as_dict()


@pytest.mark.parametrize(
    "annotation",
    [
        'data-pptx-shape-geometry="RECT"',
        'data-pptx-shape-geometry="freeform"',
        'data-pptx-shape-geometry=""',
        'data-shape-geometry="ellipse"',
        'data-pptx-kind="ellipse"',
        'data-pptx-shape-path="M0 0 L1 1"',
        'data-pptx-shape-adjust="adj:val 50000"',
    ],
)
def test_author_contract_rejects_private_or_unsupported_geometry_annotations(
    tmp_path: Path, annotation: str
) -> None:
    report = check_contract(
        _write(
            tmp_path,
            f'<div {annotation} style="position:absolute;left:10px;top:10px;width:100px;height:50px;background:#fff">x</div>',
        ),
        "author",
    )
    assert report.blocked, report.as_dict()


def test_ellipse_inference_uses_square_tolerance_only() -> None:
    assert _shape_geometry({"width": 100, "height": 100, "borderRadius": "50%"}) == "ellipse"
    assert _shape_geometry({"width": 100, "height": 100.9, "borderRadius": "50%"}) == "ellipse"
    assert _shape_geometry({"width": 100, "height": 102, "borderRadius": "50%"}) == "roundRect"
    assert _shape_geometry({"width": 100, "height": 100, "borderRadius": "12px"}) == "roundRect"


@pytest.mark.asyncio
async def test_public_non_round_shape_adjustment_fails_before_output(tmp_path: Path) -> None:
    html = _write(
        tmp_path,
        '<div data-pptx-shape-geometry="triangle" '
        'style="position:absolute;left:10px;top:10px;width:100px;height:50px;'
        'border-radius:8px;background:#fff">x</div>',
    )
    output = tmp_path / "adjustment.pptx"
    report = check_contract(html, "author")
    assert "unsupported_shape_adjustment" in {
        item.code for item in report.diagnostics
    }
    with pytest.raises(OfficeCLICompilationError) as error:
        await compile_officecli(str(html), "author", str(output))
    assert any(item.code == "unsupported_shape_adjustment" for item in error.value.diagnostics)
    assert not output.exists()


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
async def test_fixture_readback_has_one_native_shape_for_every_token(tmp_path: Path) -> None:
    output = tmp_path / "shape.pptx"
    result = await compile_officecli(str(FIXTURE), "author", str(output), slide_indices=[0])
    assert result.manifest["object_kind_counts"]["shape"] >= len(SHAPE_GEOMETRY_TOKENS)
    validation = subprocess.run(
        ["officecli", "validate", str(output)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert validation.returncode == 0, validation.stdout + validation.stderr
    issues = subprocess.run(
        ["officecli", "view", str(output), "issues"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert issues.returncode == 0, issues.stdout + issues.stderr
    document = subprocess.run(
        ["officecli", "get", str(output), "/slide[1]", "--depth", "1", "--json"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    objects = json.loads(document.stdout)["data"]["results"][0]["children"]
    shapes = {
        item["format"].get("name"): item
        for item in objects
        if item.get("type") == "shape"
    }
    for index, token in enumerate(SHAPE_GEOMETRY_TOKENS):
        name = result.manifest["objects"][index]["name"]
        item = shapes[name]
        assert item["format"]["geometry"] == token
    text_name = result.manifest["objects"][-1]["name"]
    assert shapes[text_name]["text"] == "rotated opaque shape \u4e2d\u6587"
    assert not any(item.get("type") == "picture" for item in objects)
