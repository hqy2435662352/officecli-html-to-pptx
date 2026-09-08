"""Golden acceptance test for the complete external Algeria Author deck."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from html_to_pptx import compile_officecli, extract_measurements


_DEFAULT_AUTHOR_HTML = (
    Path(r"D:\Opencodeworkspace\html-to-pptx\workspace\algeria\algeria")
    / "Algeria_AC_Product_Portfolio_20260906_v3_pptx.html"
)
_AUTHOR_HTML = Path(
    os.environ.get("HTML_TO_PPTX_ALGERIA_AUTHOR_HTML", _DEFAULT_AUTHOR_HTML)
)
_EXPECTED_TABLES = (
    (),
    ((5, 8), (8, 8), (5, 8), (5, 8)),
    ((15, 4),),
    ((13, 5),),
    ((13, 5),),
    ((13, 5),),
    ((9, 5),),
    (),
)
_ALLOWED_OVERFLOW_OBJECTS = frozenset(
    {
        "slide-001-textbox-012",
        "slide-008-textbox-024",
        "slide-008-textbox-028",
    }
)
_LENGTH_RE = re.compile(r"^(-?\d+(?:\.\d+)?)(pt|emu|cm|in)$")

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None or not _AUTHOR_HTML.is_file(),
    reason="OfficeCLI and the external Algeria Author HTML are required",
)


def _officecli(*args: str | Path, json_output: bool = False) -> Any:
    command = ["officecli", *(str(arg) for arg in args)]
    if json_output:
        command.append("--json")
    result = subprocess.run(
        command,
        capture_output=True,
        timeout=120,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise AssertionError(f"{' '.join(command)} failed:\n{stdout}\n{stderr}")
    return json.loads(stdout) if json_output else stdout


def _points(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    match = _LENGTH_RE.fullmatch(str(value).strip())
    if match is None:
        raise AssertionError(f"unexpected OfficeCLI length: {value!r}")
    amount, unit = match.groups()
    number = float(amount)
    return {
        "pt": number,
        "emu": number / 12_700,
        "cm": number * 72 / 2.54,
        "in": number * 72,
    }[unit]


def _normal_text(value: Any) -> str:
    """Normalize only display whitespace introduced by OfficeCLI projection."""
    return " ".join(str(value).replace("\u00a0", " ").split())


def _measurement_nodes(
    elements: list[dict[str, Any]],
    slide_index: int,
    parent: str = "",
    parent_has_inline_runs: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    nodes: list[tuple[str, dict[str, Any]]] = []
    for position, element in enumerate(elements, start=1):
        tag = str(element.get("tag", "element") or "element").lower()
        if parent_has_inline_runs and tag in {
            "span", "strong", "em", "b", "i", "a", "code", "mark",
            "sub", "sup", "small", "u", "s", "del", "abbr", "cite",
            "q", "time", "var", "kbd",
        }:
            continue
        path = f"{parent}/{tag}[{position}]" if parent else f"slide[{slide_index}]/{tag}[{position}]"
        nodes.append((path, element))
        nodes.extend(
            _measurement_nodes(
                element.get("children", []) or [],
                slide_index,
                path,
                bool(element.get("inlineRuns")),
            )
        )
    return nodes


def _measurement_text(element: dict[str, Any]) -> str:
    runs = element.get("inlineRuns")
    if runs:
        return "".join(str(run.get("text", "")) for run in runs)
    return str(element.get("text", "") or "")


async def _author_visible_text_and_images() -> tuple[str, int, list[str]]:
    measurements = await extract_measurements(
        str(_AUTHOR_HTML),
        include_picture_fallbacks=False,
    )
    nodes = [
        node
        for slide_index, slide in enumerate(measurements, start=1)
        for _, node in _measurement_nodes(
            slide.get("elements", []), slide_index
        )
    ]
    text = _normal_text(" ".join(_measurement_text(node) for node in nodes))
    picture_paths = [
        path
        for slide_index, slide in enumerate(measurements, start=1)
        for path, node in _measurement_nodes(
            slide.get("elements", []), slide_index
        )
        if node.get("isImage") or node.get("isSvg")
    ]
    return text, len(picture_paths), picture_paths


def _walk(node: dict[str, Any]) -> list[dict[str, Any]]:
    descendants = [node]
    for child in node.get("children", []) or []:
        descendants.extend(_walk(child))
    return descendants


def _direct_text(node: dict[str, Any]) -> list[str]:
    if node.get("type") not in {"shape", "textbox", "tc"} or not node.get("text"):
        return []
    return [_normal_text(node["text"])]


def _manifest_text(manifest: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for obj in manifest["objects"]:
        if obj.get("text"):
            values.append(_normal_text(obj["text"]))
        values.extend(
            _normal_text(cell["text"])
            for cell in obj.get("cells", [])
            if cell.get("text")
        )
    return values


def _children_by_slide(root: dict[str, Any]) -> list[list[dict[str, Any]]]:
    return [slide.get("children", []) for slide in root.get("children", [])]


def _assert_no_unallowlisted_issues(
    issues: str,
    shallow_root: dict[str, Any],
) -> None:
    lowered = issues.lower()
    for forbidden in (
        "shape_off_slide",
        "off-slide",
        "missing picture",
        "missing-picture",
        "table structure",
        "table-structure",
        "schema",
    ):
        assert forbidden not in lowered

    id_to_name = {
        (slide_index, int(child["format"]["id"])): child["format"]["name"]
        for slide_index, children in enumerate(_children_by_slide(shallow_root), 1)
        for child in children
        if child.get("type") in {"shape", "textbox"}
        and child.get("format", {}).get("id") is not None
    }
    issue_lines = [
        line.strip()
        for line in issues.splitlines()
        if re.match(r"^\s+\[[A-Z]\d+\]\s", line)
    ]
    for line in issue_lines:
        assert "text overflow" in line.lower(), line
        match = re.search(r"/slide\[(\d+)\]/shape\[@id=(\d+)\]", line)
        assert match is not None, line
        slide_index, object_id = match.groups()
        name = id_to_name.get((int(slide_index), int(object_id)))
        assert name in _ALLOWED_OVERFLOW_OBJECTS


@pytest.mark.asyncio
async def test_algeria_author_compiles_to_the_complete_native_deck(
    tmp_path: Path,
) -> None:
    output = tmp_path / "algeria_issue04.pptx"
    result = await compile_officecli(str(_AUTHOR_HTML), "author", str(output))
    repeat = await compile_officecli(
        str(_AUTHOR_HTML), "author", str(tmp_path / "algeria_issue04_repeat.pptx")
    )
    source_text, source_image_count, source_picture_paths = (
        await _author_visible_text_and_images()
    )

    assert output.is_file()
    assert result.profile == "author"
    assert not result.diagnostics
    assert [obj["name"] for obj in repeat.manifest["objects"]] == [
        obj["name"] for obj in result.manifest["objects"]
    ]
    assert result.slide_count == 8
    assert result.manifest["slide_count"] == 8
    assert result.manifest["object_kind_counts"]["picture"] == 18
    assert source_image_count == 18
    assert result.manifest["object_kind_counts"]["table"] == 9
    assert sum(
        obj["rows"]
        for obj in result.manifest["objects"]
        if obj["kind"] == "table"
    ) == 86
    assert sum(
        len(obj["cells"])
        for obj in result.manifest["objects"]
        if obj["kind"] == "table"
    ) == 484

    validation = subprocess.run(
        ["officecli", "validate", str(output)],
        capture_output=True,
        timeout=120,
    )
    assert validation.returncode == 0, (
        validation.stdout.decode("utf-8", errors="replace")
        + validation.stderr.decode("utf-8", errors="replace")
    )

    shallow_root = _officecli("get", output, "/", "--depth", "1", json_output=True)[
        "data"
    ]["results"][0]
    deep_root = _officecli("get", output, "/", "--depth", "3", json_output=True)[
        "data"
    ]["results"][0]
    slides = _children_by_slide(shallow_root)
    assert [slide["format"]["name"] for slide in shallow_root["children"]] == [
        f"slide-{index:03d}" for index in range(1, 9)
    ]

    observed_tables = tuple(
        tuple(
            (int(child["format"]["rows"]), int(child["format"]["cols"]))
            for child in children
            if child.get("type") == "table"
        )
        for children in slides
    )
    assert observed_tables == _EXPECTED_TABLES

    output_objects = [child for children in slides for child in children]
    output_counts = Counter(child["type"] for child in output_objects)
    assert dict(output_counts) == result.manifest["object_kind_counts"]
    assert len(output_objects) == result.object_count
    effect_keys = {
        key
        for child in output_objects
        for key in child.get("format", {})
        if any(
            term in key.lower()
            for term in ("shadow", "glow", "reflection", "softedge", "bevel")
        )
    }
    assert not effect_keys

    output_names = [child["format"]["name"] for child in output_objects]
    manifest_names = [obj["name"] for obj in result.manifest["objects"]]
    assert len(output_names) == len(set(output_names))
    assert len(manifest_names) == len(set(manifest_names))
    assert output_names == manifest_names

    output_by_name = {child["format"]["name"]: child for child in output_objects}
    for obj in result.manifest["objects"]:
        actual = output_by_name[obj["name"]]["format"]
        assert [
            _points(actual[key]) for key in ("x", "y", "width", "height")
        ] == pytest.approx(obj["bounds_pt"], abs=1.0)

    output_tables = {
        node["format"]["name"]: node
        for node in _walk(deep_root)
        if node.get("type") == "table"
    }
    table_manifests = [
        obj for obj in result.manifest["objects"] if obj["kind"] == "table"
    ]
    assert set(output_tables) == {obj["name"] for obj in table_manifests}
    for obj in table_manifests:
        table = output_tables[obj["name"]]
        assert int(table["format"]["rows"]) == obj["rows"]
        assert int(table["format"]["cols"]) == obj["columns"]
        actual_column_widths = [
            _points(value)
            for value in str(table["format"]["colWidths"]).split(",")
            if value.strip()
        ]
        assert actual_column_widths == pytest.approx(obj["column_widths_pt"], abs=0.5)
        actual_rows = [
            row for row in table.get("children", []) if row.get("type") == "tr"
        ]
        assert [_points(row["format"]["height"]) for row in actual_rows] == pytest.approx(
            obj["row_heights_pt"], abs=0.5
        )
        actual_cells = [
            cell
            for row in actual_rows
            for cell in row.get("children", [])
            if cell.get("type") == "tc"
        ]
        assert len(actual_cells) == obj["rows"] * obj["columns"]
        assert [_normal_text(cell.get("text", "")) for cell in actual_cells] == [
            _normal_text(cell["text"]) for cell in obj["cells"]
        ]

    actual_text = [
        text
        for node in _walk(deep_root)
        for text in _direct_text(node)
    ]
    assert _normal_text(" ".join(actual_text)) == source_text
    assert Counter(actual_text) == Counter(_manifest_text(result.manifest))
    assert source_text.count("Φ") == 60
    assert source_text.count("×") == 212
    assert sum(text.count("Φ") for text in actual_text) == 60
    assert sum(text.count("×") for text in actual_text) == 212

    pictures = [obj for obj in result.manifest["objects"] if obj["kind"] == "picture"]
    assert len(pictures) == 18
    assert all(
        obj["bounds_pt"] != [0.0, 0.0, 960.0, 540.0] for obj in pictures
    )
    picture_names = {obj["name"] for obj in pictures}
    assert [obj["source_object"] for obj in pictures] == source_picture_paths
    assert all(
        node.get("type") == "picture"
        for node in output_objects
        if node["format"]["name"] in picture_names
    )

    issues = _officecli("view", output, "issues")
    _assert_no_unallowlisted_issues(issues, shallow_root)
