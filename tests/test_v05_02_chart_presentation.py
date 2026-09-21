"""Focused V0.5.2 closed chart-presentation tests for ticket #31.

These tests observe the public ``ChartSpec``/``ChartReadback`` seam and the
public check/build artifact pair.  OfficeCLI property names and format strings
remain private to the adapter; only the Contract tokens appear in Author HTML
or Evidence.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from officecli_html_to_pptx._internal.charts import (
    ChartSpecError,
    OfficeCLIChartAdapter,
    parse_chart_spec,
)
from officecli_html_to_pptx.application import (
    _native_material_delta_count,
    build_author_html,
    check_author_html,
)


def _html(spec: str, *, chart_type: str = "column") -> str:
    return f"""<!doctype html>
<html><head><style>
  html, body {{ margin: 0; width: 100%; height: 100%; }}
  .slide {{ width: 1920px; height: 1080px; position: relative; background: #ffffff; }}
</style></head><body>
  <section class="slide">
    <div data-pptx-chart id="presentation-chart" style="position:absolute;left:120px;top:120px;width:960px;height:480px">
      <script type="application/json" data-pptx-chart-spec>{spec}</script>
    </div>
  </section>
</body></html>
"""


def _spec(
    chart_type: str = "column",
    *,
    presentation: dict[str, object] | None = None,
    series: list[dict[str, object]] | None = None,
) -> str:
    body: dict[str, object] = {
        "type": chart_type,
        "categories": ["Q1", "Q2", "Q3"],
        "series": series
        if series is not None
        else [
            {"name": "Revenue", "values": [10, 20, 30], "color": "#aa00bb"},
            {"name": "Cost", "values": [4, 12, 18]},
        ],
    }
    if presentation is not None:
        body["presentation"] = presentation
    return json.dumps(body, separators=(",", ":"))


def _write(tmp_path: Path, source: str, name: str = "chart.html") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _fault_injection_node() -> dict[str, object]:
    return {
        "type": "chart",
        "path": "/slide[1]/chart[1]",
        "format": {
            "name": "presentation-chart",
            "chartType": "column",
            "categories": "Q1,Q2,Q3",
            "x": "0pt",
            "y": "0pt",
            "width": "100pt",
            "height": "100pt",
        },
        "children": [
            {
                "type": "series",
                "format": {"name": "Revenue", "values": "10,20,30"},
            }
        ],
    }


def _fault_injection_xml(series_color: str | None) -> str:
    color = (
        f'<c:spPr><a:solidFill><a:srgbClr val="{series_color[1:]}"/>'
        "</a:solidFill></c:spPr>"
        if series_color is not None
        else ""
    )
    return f"""<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <c:chart><c:plotArea><c:barChart><c:ser>
    <c:tx><c:v>Revenue</c:v></c:tx>
    <c:cat><c:strLit><c:ptCount val="3"/><c:pt idx="0"><c:v>Q1</c:v></c:pt><c:pt idx="1"><c:v>Q2</c:v></c:pt><c:pt idx="2"><c:v>Q3</c:v></c:pt></c:strLit></c:cat>
    <c:val><c:numLit><c:ptCount val="3"/><c:pt idx="0"><c:v>10</c:v></c:pt><c:pt idx="1"><c:v>20</c:v></c:pt><c:pt idx="2"><c:v>30</c:v></c:pt></c:numLit></c:val>
    {color}
  </c:ser></c:barChart></c:plotArea></c:chart>
</c:chartSpace>"""


def _fault_injection_manifest(
    chart: dict[str, object], seam: dict[str, object]
) -> dict[str, object]:
    return {
        "slide_count": 1,
        "slide_size_pt": {"width": 1920.0, "height": 1080.0},
        "object_kind_counts": {"chart": 1},
        "objects": [
            {
                "kind": "chart",
                "name": "presentation-chart",
                "native_kind": "chart",
                "bounds_pt": [0.0, 0.0, 100.0, 100.0],
                "chart": chart,
                "chart_seam": seam,
            }
        ],
    }


def _fault_injection_expected(color: str) -> dict[str, object]:
    chart: dict[str, object] = {
        "type": "column",
        "categories": ["Q1", "Q2", "Q3"],
        "series": [{"name": "Revenue", "values": [10.0, 20.0, 30.0]}],
        "labels": "none",
    }
    if color != "auto":
        chart["series_colors"] = [color]
    return _fault_injection_manifest(
        chart,
        {"series_colors": [color]},
    )


@pytest.mark.parametrize("length", ["25.4cm", "10in", "9144000emu"])
def test_chart_readback_normalizes_physical_lengths_to_points(length: str) -> None:
    node = _fault_injection_node()
    node["format"]["width"] = length

    readback = OfficeCLIChartAdapter.readback(node)

    assert readback.bounds == pytest.approx((0.0, 0.0, 720.0, 100.0))


@pytest.mark.parametrize("native_color", ["#112233", None])
def test_explicit_color_fault_injection_is_material(
    native_color: str | None,
) -> None:
    readback = OfficeCLIChartAdapter.readback(
        _fault_injection_node(),
        raw_xml=_fault_injection_xml(native_color),
        expected_series_colors=("#AA00BB",),
    )

    assert readback.series[0].color == (native_color or "auto")
    actual = _fault_injection_manifest(
        readback.semantic_dict(),
        readback.as_dict(),
    )
    assert _native_material_delta_count(
        _fault_injection_expected("#AA00BB"), actual
    ) > 0


def test_auto_color_fault_injection_ignores_office_rgb_materially() -> None:
    readback = OfficeCLIChartAdapter.readback(
        _fault_injection_node(),
        raw_xml=_fault_injection_xml("#112233"),
        expected_series_colors=("auto",),
    )

    assert readback.series[0].color == "auto"
    assert readback.office_series_colors == ("#112233",)
    actual = _fault_injection_manifest(
        readback.semantic_dict(),
        readback.as_dict(),
    )
    assert _native_material_delta_count(_fault_injection_expected("auto"), actual) == 0


def test_chart_presentation_is_normalized_at_the_existing_typed_seam() -> None:
    parsed = parse_chart_spec(
        _spec(
            presentation={
                "title": "  Revenue review  ",
                "legend": "right",
                "labels": "value",
                "categoryAxis": {"title": "  Quarter  "},
                "valueAxis": {"title": "  USD  ", "numberFormat": "integer-group"},
            }
        ),
        source_object="slide[1]/div[1]",
    )

    assert parsed.title == "Revenue review"
    assert parsed.legend == "right"
    assert parsed.data_labels == "value"
    assert parsed.category_axis_title == "Quarter"
    assert parsed.value_axis_title == "USD"
    assert parsed.value_axis_number_format == "integer-group"
    assert [series.color for series in parsed.series] == ["#AA00BB", "auto"]

    semantics = parsed.semantic_dict()
    assert semantics["title"] == "Revenue review"
    assert semantics["legend"] == "right"
    assert semantics["labels"] == "value"
    assert semantics["category_axis_title"] == "Quarter"
    assert semantics["value_axis_title"] == "USD"
    assert semantics["value_axis_number_format"] == "integer-group"
    assert semantics["series_colors"] == ["#AA00BB", "auto"]


@pytest.mark.parametrize("legend", ["none", "top", "bottom", "left", "right"])
@pytest.mark.parametrize("labels", ["none", "value"])
@pytest.mark.parametrize(
    "number_format",
    ["general", "integer", "integer-group", "decimal1", "decimal1-group", "percent0", "percent1"],
)
def test_closed_cartesian_presentation_tokens_parse(
    legend: str,
    labels: str,
    number_format: str,
) -> None:
    parsed = parse_chart_spec(
        _spec(
            presentation={
                "legend": legend,
                "labels": labels,
                "valueAxis": {"numberFormat": number_format},
            }
        ),
        source_object="slide[1]/div[1]",
    )
    assert parsed.legend == legend
    assert parsed.data_labels == labels
    assert parsed.value_axis_number_format == number_format


@pytest.mark.parametrize(
    ("spec", "code"),
    [
        (_spec(presentation={"unknown": {}}), "unknown_chart_spec_field"),
        (_spec(presentation={"valueAxis": {"unknown": "x"}}), "unknown_chart_spec_field"),
        (_spec(presentation={"valueAxis": {"numberFormat": "#,##0"}}), "invalid_chart_number_format"),
        (_spec(presentation={"legend": "topRight"}), "invalid_chart_legend"),
        (_spec(presentation={"title": "   "}), "invalid_chart_title"),
        (_spec(series=[{"name": "Revenue", "values": [1, 2, 3], "color": "red"}]), "invalid_chart_series_color"),
        (_spec(series=[{"name": "Revenue", "values": [1, 2, 3], "color": "#12345"}]), "invalid_chart_series_color"),
        (_spec(series=[{"name": "Revenue", "values": [1, 2, 3], "color": None}]), "invalid_chart_series_color"),
        (
            '{"type":"column","categories":["Q1"],"series":[{"name":"S","values":[1]}],"presentation":null}',
            "invalid_chart_spec_object",
        ),
        (_spec(presentation={"categoryAxis": {"numberFormat": "integer"}}), "unknown_chart_spec_field"),
        (
            _spec(
                "pie",
                series=[{"name": "Share", "values": [10, 20, 30]}],
                presentation={"valueAxis": {"numberFormat": "integer"}},
            ),
            "part_to_whole_axis_unsupported",
        ),
        (_spec(presentation={"labels": "percent"}), "chart_percent_labels_type"),
    ],
)
def test_closed_presentation_rejects_recursive_unknowns_and_invalid_values(
    spec: str,
    code: str,
) -> None:
    with pytest.raises(ChartSpecError) as exc_info:
        parse_chart_spec(spec, source_object="slide[1]/div[1]")
    assert exc_info.value.code == code


def test_adapter_keeps_backend_format_strings_private() -> None:
    parsed = parse_chart_spec(
        _spec(
            presentation={
                "title": "Revenue",
                "legend": "bottom",
                "labels": "value",
                "categoryAxis": {"title": "Quarter"},
                "valueAxis": {"title": "USD", "numberFormat": "decimal1-group"},
            }
        ),
        source_object="slide[1]/div[1]",
        bounds=(10.0, 20.0, 300.0, 200.0),
    )
    props = OfficeCLIChartAdapter.creation_props(parsed, parsed.bounds)
    assert props["title"] == "Revenue"
    assert props["legend"] == "bottom"
    assert props["dataLabels"] == "value"
    assert props["catTitle"] == "Quarter"
    assert props["axistitle"] == "USD"
    assert props["axisnumfmt"] == "#,##0.0"
    assert "numberFormat" not in props

    commands = OfficeCLIChartAdapter.write_commands(
        parsed,
        "/slide[1]/chart[@name=chart]",
        "/ppt/slides/charts/chart1.xml",
    )
    series_commands = [item for item in commands if item["command"] == "set"]
    assert series_commands[0]["props"]["color"] == "AA00BB"
    assert "color" not in series_commands[1]["props"]


def test_build_round_trips_closed_presentation_and_auto_color_evidence(
    tmp_path: Path,
) -> None:
    source_path = _write(
        tmp_path,
        _html(
            _spec(
                presentation={
                    "title": "  Revenue review  ",
                    "legend": "right",
                    "labels": "value",
                    "categoryAxis": {"title": "Quarter"},
                    "valueAxis": {"title": "USD", "numberFormat": "integer-group"},
                }
            )
        ),
    )
    output = tmp_path / "presentation.pptx"

    built = asyncio.run(build_author_html(source_path, output))
    assert built.status == "VISUAL_REVIEW_REQUIRED", built.as_dict()

    evidence = output.with_suffix(".evidence")
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    readback = json.loads((evidence / "readback.json").read_text(encoding="utf-8"))
    native = json.loads((evidence / "native-evidence.json").read_text(encoding="utf-8"))

    expected = manifest["objects"][0]["chart"]
    actual = readback["objects"][0]["chart"]
    for key in (
        "title",
        "legend",
        "labels",
        "category_axis_title",
        "value_axis_title",
        "value_axis_number_format",
        "series_colors",
    ):
        assert actual[key] == expected[key]
    assert readback["objects"][0]["chart_seam"]["series_colors"] == ["#AA00BB", "auto"]
    office_colors = readback["objects"][0]["chart_seam"]["office_series_colors"]
    assert office_colors[0] == "#AA00BB"
    assert "auto" not in office_colors
    assert native["diagnostics"]["unsupported"] == 0
    assert native["diagnostics"]["unresolved"] == 0
    assert native["diagnostics"]["material_delta"] == 0
    assert json.loads((evidence / "validate.json").read_text(encoding="utf-8"))["status"] == "PASS"
    assert json.loads((evidence / "issues.json").read_text(encoding="utf-8"))["status"] == "PASS"


@pytest.mark.parametrize("chart_type", ["column", "bar", "line", "pie", "doughnut"])
def test_property_matrix_clean_runtime_probe_covers_every_chart_family(
    tmp_path: Path,
    chart_type: str,
) -> None:
    if chart_type in {"pie", "doughnut"}:
        categories = ["North", "South", "West"]
        series = [{"name": "Share", "values": [10, 20, 30], "color": "#123456"}]
        presentation: dict[str, object] = {
            "title": "Mix",
            "legend": "left",
            "labels": "percent",
        }
    else:
        categories = ["Q1", "Q2", "Q3"]
        series = [
            {"name": "Revenue", "values": [10, 20, 30], "color": "#123456"},
            {"name": "Cost", "values": [4, 12, 18]},
        ]
        presentation = {
            "title": "Trend",
            "legend": "top",
            "labels": "value",
            "categoryAxis": {"title": "Quarter"},
            "valueAxis": {"title": "USD", "numberFormat": "decimal1-group"},
        }
    body = {"type": chart_type, "categories": categories, "series": series, "presentation": presentation}
    source_path = _write(tmp_path, _html(json.dumps(body)), f"{chart_type}.html")
    output = tmp_path / f"{chart_type}.pptx"

    built = asyncio.run(build_author_html(source_path, output))
    assert built.status == "VISUAL_REVIEW_REQUIRED", built.as_dict()
    native = json.loads(
        (output.with_suffix(".evidence") / "native-evidence.json").read_text(encoding="utf-8")
    )
    assert native["runtime"]["officecli"]["discovered_version"] == "1.0.151"
    assert native["diagnostics"]["material_delta"] == 0


def test_clean_runtime_property_matrix_probe_covers_every_public_token(
    tmp_path: Path,
) -> None:
    """Tracked release-floor probe: one clean 1.0.151 run covers the matrix."""

    entries: list[tuple[str, dict[str, object]]] = [
        (
            "column-none",
            {
                "type": "column",
                "categories": ["Q1", "Q2", "Q3"],
                "series": [{"name": "Revenue", "values": [10, 20, 30]}],
                "presentation": {"title": "Column", "legend": "none", "labels": "none"},
            },
        ),
        (
            "bar-top",
            {
                "type": "bar",
                "categories": ["Q1", "Q2", "Q3"],
                "series": [{"name": "Revenue", "values": [10, 20, 30], "color": "#123456"}],
                "presentation": {"title": "Bar", "legend": "top", "labels": "value"},
            },
        ),
        (
            "line-bottom",
            {
                "type": "line",
                "categories": ["Q1", "Q2", "Q3"],
                "series": [
                    {"name": "Revenue", "values": [10, 20, 30], "color": "#123456"},
                    {"name": "Cost", "values": [4, 12, 18]},
                ],
                "presentation": {
                    "title": "Line",
                    "legend": "bottom",
                    "labels": "none",
                    "categoryAxis": {"title": "Quarter"},
                    "valueAxis": {"title": "USD", "numberFormat": "integer"},
                },
            },
        ),
        (
            "pie-left",
            {
                "type": "pie",
                "categories": ["North", "South", "West"],
                "series": [{"name": "Share", "values": [10, 20, 30], "color": "#123456"}],
                "presentation": {"title": "Pie", "legend": "left", "labels": "value"},
            },
        ),
        (
            "doughnut-right",
            {
                "type": "doughnut",
                "categories": ["North", "South", "West"],
                "series": [{"name": "Share", "values": [10, 20, 30]}],
                "presentation": {"title": "Doughnut", "legend": "right", "labels": "percent"},
            },
        ),
    ]
    for index, token in enumerate(
        ["general", "integer", "integer-group", "decimal1", "decimal1-group", "percent0", "percent1"],
        start=1,
    ):
        entries.append(
            (
                f"number-{token}",
                {
                    "type": "column",
                    "categories": ["Q1", "Q2", "Q3"],
                    "series": [{"name": "Value", "values": [10, 20, 30]}],
                    "presentation": {
                        "title": f"Format {token}",
                        "legend": "none",
                        "labels": "none",
                        "valueAxis": {"numberFormat": token},
                    },
                },
            )
        )

    chart_markup = []
    for index, (identity, spec) in enumerate(entries):
        column = index % 4
        row = index // 4
        x = 20 + column * 475
        y = 20 + row * 265
        chart_markup.append(
            f'<div data-pptx-chart id="{identity}" style="position:absolute;left:{x}px;top:{y}px;width:440px;height:230px;">'
            f'<script type="application/json" data-pptx-chart-spec>{json.dumps(spec, separators=(",", ":"))}</script></div>'
        )
    source = _write(
        tmp_path,
        """<!doctype html><html><head><style>
html,body { margin:0; width:100%; height:100%; }
.slide { width:1920px; height:1080px; position:relative; background:#fff; }
</style></head><body><section class="slide">"""
        + "".join(chart_markup)
        + "</section></body></html>",
        "property-matrix.html",
    )
    output = tmp_path / "property-matrix.pptx"

    built = asyncio.run(build_author_html(source, output))
    assert built.status == "VISUAL_REVIEW_REQUIRED", built.as_dict()
    evidence = output.with_suffix(".evidence")
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    readback = json.loads((evidence / "readback.json").read_text(encoding="utf-8"))
    native = json.loads((evidence / "native-evidence.json").read_text(encoding="utf-8"))

    assert len(manifest["objects"]) == len(entries) == 12
    assert len(readback["objects"]) == len(entries)
    assert native["runtime"]["officecli"]["discovered_version"] == "1.0.151"
    assert native["diagnostics"]["unsupported"] == 0
    assert native["diagnostics"]["unresolved"] == 0
    assert native["diagnostics"]["material_delta"] == 0
    for expected, actual in zip(manifest["objects"], readback["objects"]):
        assert expected["chart"] == actual["chart"]
        assert expected["chart_seam"]["series_colors"] == actual["chart_seam"]["series_colors"]
        assert actual["native_kind"] == "chart"
    doughnut = next(item for item in manifest["objects"] if item["source_object"] == "doughnut-right")
    assert doughnut["chart"]["hole_size"] == 50
