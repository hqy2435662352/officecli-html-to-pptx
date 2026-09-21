"""Focused Contract 1.1 merged-table acceptance tests for ticket #24."""

from __future__ import annotations

import subprocess
from pathlib import Path
import shutil

import pytest

from officecli_html_to_pptx._internal.acceptance import (
    _officecli_manifest,
    _run_officecli,
    compare_manifests,
)
from officecli_html_to_pptx._internal.officecli_compiler import (
    OfficeCLICompilationError,
    compile_officecli,
)
from officecli_html_to_pptx.contract import (
    TableTopologyError,
    author_capability_manifest,
    build_logical_table_grid,
    check_contract,
)
from officecli_html_to_pptx.measurement import extract_measurements


FIXTURE = Path(__file__).parent / "fixtures" / "v05_01_native_table.html"


def _table_rows(element: dict) -> list[dict]:
    if element.get("tag") == "tr":
        return [element]
    return [
        row
        for child in element.get("children", [])
        for row in _table_rows(child)
    ]


EXPECTED_TOPOLOGY = [
    {"anchorRow": 1, "anchorColumn": 1, "rowSpan": 2, "columnSpan": 2},
    {"anchorRow": 1, "anchorColumn": 3, "rowSpan": 1, "columnSpan": 1},
    {"anchorRow": 2, "anchorColumn": 3, "rowSpan": 1, "columnSpan": 1},
    {"anchorRow": 3, "anchorColumn": 1, "rowSpan": 1, "columnSpan": 2},
    {"anchorRow": 3, "anchorColumn": 3, "rowSpan": 1, "columnSpan": 1},
    {"anchorRow": 4, "anchorColumn": 1, "rowSpan": 1, "columnSpan": 1},
    {"anchorRow": 4, "anchorColumn": 2, "rowSpan": 1, "columnSpan": 1},
    {"anchorRow": 4, "anchorColumn": 3, "rowSpan": 1, "columnSpan": 1},
]


def _mutated_fixture(tmp_path: Path, mutation: str) -> Path:
    source = FIXTURE.read_text(encoding="utf-8")
    safe_name = "mutation-" + "-".join(
        part for part in mutation.replace('"', '').split() if part
    )
    path = tmp_path / f"{safe_name}.html"
    path.write_text(source.replace("rowspan=\"2\" colspan=\"2\"", mutation), encoding="utf-8")
    return path


def test_fixture_and_capability_manifest_publish_merged_tables() -> None:
    report = check_contract(FIXTURE, "author")
    assert not report.blocked, report.as_dict()
    assert author_capability_manifest()["table_cell_spans"] is True
    assert (FIXTURE.with_suffix(".acceptance.md")).is_file()


def _logical_grid_error(rows: list[list[dict[str, str]]]) -> str:
    with pytest.raises(TableTopologyError) as error:
        build_logical_table_grid(rows, source_object="slide[1]/table[1]")
    assert error.value.source_object
    return error.value.code


def test_logical_grid_rejects_overlap_and_covered_content_ambiguity() -> None:
    rows = [
        [
            {"source_object": "a", "rowspan": "1", "colspan": "1", "text": ""},
            {"source_object": "b", "rowspan": "2", "colspan": "1", "text": ""},
        ],
        [{"source_object": "c", "rowspan": "1", "colspan": "2", "text": ""}],
    ]
    assert _logical_grid_error(rows) == "table_span_overlap"
    rows[1][0]["text"] = "covered content"
    assert _logical_grid_error(rows) == "covered_cell_content_ambiguity"


def test_logical_grid_rejects_holes_and_competing_anchors() -> None:
    hole_rows = [
        [
            {"source_object": "a", "rowspan": "1", "colspan": "1", "text": ""},
            {"source_object": "b", "rowspan": "1", "colspan": "1", "text": ""},
            {"source_object": "c", "rowspan": "1", "colspan": "1", "text": ""},
        ],
        [{"source_object": "d", "rowspan": "1", "colspan": "1", "text": ""}],
    ]
    assert _logical_grid_error(hole_rows) == "table_hole"
    competing_rows = [
        [{"source_object": "same", "rowspan": "1", "colspan": "1", "text": ""}],
        [{"source_object": "same", "rowspan": "1", "colspan": "1", "text": ""}],
    ]
    assert _logical_grid_error(competing_rows) == "competing_table_anchor"


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
async def test_public_compiler_emits_one_native_table_with_normalized_topology(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "merged-table.pptx"
    result = await compile_officecli(str(FIXTURE), "author", str(output_path))

    assert result.manifest["object_kind_counts"] == {"table": 1}
    table = result.manifest["objects"][0]
    measured = await extract_measurements(str(FIXTURE), officecli_mode=True)
    source_slide = measured[0]
    source_table = next(
        element for element in source_slide["elements"] if element.get("tag") == "table"
    )
    assert (source_slide["width"], source_slide["height"]) == (1920, 1080)
    assert [source_table[key] for key in ("x", "y", "width", "height")] == pytest.approx(
        [160, 108, 1200, 600], abs=1.0
    )
    slide_size = result.manifest["slide_size_pt"]
    scale_x = slide_size["width"] / source_slide["width"]
    scale_y = slide_size["height"] / source_slide["height"]
    row_heights = [row["height"] for row in _table_rows(source_table)]
    assert len(row_heights) == 4
    # Chromium's collapsed-border table box includes the outer border; the
    # native table bounds are the logical row sum used by the compiler.
    normalized_source_bounds = [
        source_table["x"] * scale_x,
        source_table["y"] * scale_y,
        source_table["width"] * scale_x,
        sum(row_heights) * scale_y,
    ]
    assert table["bounds_pt"] == pytest.approx(normalized_source_bounds, abs=1.0)
    assert table["rows"] == 4
    assert table["columns"] == 3
    assert table["normalized_merge_topology"] == EXPECTED_TOPOLOGY
    assert len(table["cells"]) == 12

    anchor = next(cell for cell in table["cells"] if cell["row"] == 1 and cell["column"] == 1)
    assert anchor["anchor"] is True
    assert anchor["row_span"] == 2
    assert anchor["column_span"] == 2
    assert "Combined anchor owned" in anchor["text"]
    assert anchor["props"]["fill"] == "#FEF3C7"
    assert anchor["props"]["align"] == "left"
    assert all(
        anchor["props"][f"padding.{side}"] == "8.0000pt"
        for side in ("top", "right", "bottom", "left")
    )
    assert all(f"border.{side}" in anchor["props"] for side in ("top", "right", "bottom", "left"))
    assert len(anchor["paragraphs"]) == 1
    paragraph = anchor["paragraphs"][0]
    assert paragraph["text"] == "Combined anchor owned"
    assert paragraph["align"] == "left"
    assert paragraph["runs"][0]["bold"] is True

    covered = [
        cell for cell in table["cells"]
        if (cell["row"], cell["column"]) in {(1, 2), (2, 1), (2, 2)}
    ]
    assert all(cell["anchor"] is False and cell["text"] == "" for cell in covered)
    assert all(cell["props"] == {"text": ""} for cell in covered)


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
async def test_merged_table_readback_compares_topology_dimensions_and_native_identity(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "merged-table-readback.pptx"
    result = await compile_officecli(str(FIXTURE), "author", str(output_path))
    readback, _ = _officecli_manifest(output_path)
    table = next(item for item in readback["objects"] if item["kind"] == "table")

    assert table["normalized_merge_topology"] == EXPECTED_TOPOLOGY
    assert table["rows"] == 4
    assert table["columns"] == 3
    assert table["bounds_pt"] == pytest.approx(
        result.manifest["objects"][0]["bounds_pt"], abs=1.0
    )
    assert table["column_widths_pt"] == pytest.approx(
        result.manifest["objects"][0]["column_widths_pt"], abs=0.5
    )
    assert table["row_heights_pt"] == pytest.approx(
        result.manifest["objects"][0]["row_heights_pt"], abs=0.5
    )
    assert len(table["cells"]) == 12
    assert next(cell for cell in table["cells"] if cell["row"] == 1 and cell["column"] == 1)["text"] == (
        "Combined anchor owned"
    )
    covered = [cell for cell in table["cells"] if not cell["anchor"]]
    assert all(
        not any(
            key == "fill"
            or key.startswith("border.")
            or key.startswith("padding.")
            or key in {"align", "valign"}
            for key in cell["props"]
        )
        for cell in covered
    )
    status, findings = compare_manifests(result.manifest, readback)
    assert status == "PASS", findings

    validation = _run_officecli("validate", output_path)
    assert validation.strip()


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
async def test_merged_table_officehtml_projection_roundtrip_preserves_topology(
    tmp_path: Path,
) -> None:
    source_pptx = tmp_path / "merged-table-source.pptx"
    projected_html = tmp_path / "merged-table-projection.html"
    roundtrip_pptx = tmp_path / "merged-table-roundtrip.pptx"
    source_result = await compile_officecli(str(FIXTURE), "author", str(source_pptx))

    subprocess.run(
        ["officecli", "view", str(source_pptx), "html", "-o", str(projected_html)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    projection_report = check_contract(projected_html, "officehtml")
    assert not projection_report.blocked, projection_report.as_dict()

    roundtrip = await compile_officecli(
        str(projected_html), "officehtml", str(roundtrip_pptx)
    )
    source_table = source_result.manifest["objects"][0]
    roundtrip_table = roundtrip.manifest["objects"][0]
    assert roundtrip_table["normalized_merge_topology"] == EXPECTED_TOPOLOGY
    assert roundtrip_table["rows"] == source_table["rows"] == 4
    assert roundtrip_table["columns"] == source_table["columns"] == 3
    assert roundtrip_table["column_widths_pt"] == pytest.approx(
        source_table["column_widths_pt"], abs=0.5
    )
    assert roundtrip_table["row_heights_pt"] == pytest.approx(
        source_table["row_heights_pt"], abs=0.5
    )
    assert _run_officecli("validate", roundtrip_pptx).strip()


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ('rowspan="5" colspan="2"', "table_span_out_of_bounds"),
        ('rowspan="0" colspan="2"', "table_span_non_positive"),
        ('rowspan="2x" colspan="2"', "malformed_table_span"),
    ],
)
def test_invalid_merge_spans_block_before_output(
    tmp_path: Path, mutation: str, expected_code: str
) -> None:
    path = _mutated_fixture(tmp_path, mutation)
    report = check_contract(path, "author")
    assert report.blocked
    assert expected_code in {item.code for item in report.diagnostics}


@pytest.mark.asyncio
async def test_invalid_merge_fixture_never_creates_output(tmp_path: Path) -> None:
    path = _mutated_fixture(tmp_path, 'rowspan="5" colspan="2"')
    output_path = tmp_path / "invalid.pptx"

    with pytest.raises(OfficeCLICompilationError) as error:
        await compile_officecli(str(path), "author", str(output_path))

    assert any(item.code == "table_span_out_of_bounds" for item in error.value.diagnostics)
    assert not output_path.exists()
