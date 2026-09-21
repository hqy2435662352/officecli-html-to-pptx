"""Focused V0.5.2 part-to-whole chart tests for ticket #30.

The tests observe the public check/build seam and the independent native chart
Evidence.  Presentation fields are intentionally limited to the part-to-whole
label mode; the wider presentation surface belongs to ticket #31.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil

import pytest

from officecli_html_to_pptx._internal.charts import ChartSpecError, parse_chart_spec
from officecli_html_to_pptx.application import build_author_html, check_author_html


def _html(
    spec: str,
    *,
    chart_attributes: str = 'id="parts-chart"',
    style: str = "left:120px;top:120px;width:960px;height:480px;",
) -> str:
    return f"""<!doctype html>
<html><head><style>
  html, body {{ margin: 0; width: 100%; height: 100%; }}
  .slide {{ width: 1920px; height: 1080px; position: relative; background: #ffffff; }}
</style></head><body>
  <section class="slide">
    <div data-pptx-chart {chart_attributes} style="position:absolute;{style}">
      <script type="application/json" data-pptx-chart-spec>{spec}</script>
    </div>
  </section>
</body></html>
"""


def _spec(
    chart_type: str = "pie",
    *,
    categories: list[str] | None = None,
    values: list[float] | None = None,
    labels: str = "none",
    series: list[dict[str, object]] | None = None,
    presentation: dict[str, object] | None = None,
) -> str:
    if categories is None:
        categories = ["North", "South", "North"]
    if values is None:
        values = [10, 20, 30]
    body: dict[str, object] = {
        "type": chart_type,
        "categories": categories,
        "series": series
        if series is not None
        else [{"name": "Share", "values": values}],
        "presentation": {
            "labels": labels,
        },
    }
    if presentation is not None:
        body["presentation"] = presentation
    return json.dumps(body, separators=(",", ":"))


def _write(tmp_path: Path, source: str, name: str = "chart.html") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


@pytest.mark.parametrize("chart_type", ["pie", "doughnut"])
@pytest.mark.parametrize("labels", ["none", "value", "percent"])
def test_part_to_whole_spec_accepts_closed_label_modes(
    chart_type: str,
    labels: str,
) -> None:
    parsed = parse_chart_spec(
        _spec(chart_type, labels=labels),
        source_object="slide[1]/div[1]",
    )
    assert parsed.chart_type == chart_type
    assert parsed.categories == ("North", "South", "North")
    assert parsed.series[0].values == (10.0, 20.0, 30.0)
    assert parsed.data_labels == labels
    assert parsed.doughnut_hole_size == (50 if chart_type == "doughnut" else None)


@pytest.mark.parametrize("category_count", [2, 6])
def test_part_to_whole_category_boundaries_are_accepted(
    tmp_path: Path,
    category_count: int,
) -> None:
    categories = [f"C{index}" for index in range(category_count)]
    report = check_author_html(
        _write(
            tmp_path,
            _html(_spec(categories=categories, values=list(range(1, category_count + 1)))),
            f"valid-{category_count}.html",
        )
    )
    assert report.status == "PASS", report.as_dict()


@pytest.mark.parametrize(
    ("spec", "code"),
    [
        (_spec(categories=["C1"], values=[1]), "part_to_whole_category_limit"),
        (
            _spec(categories=["C1", "C2", "C3", "C4", "C5", "C6", "C7"], values=[1] * 7),
            "part_to_whole_category_limit",
        ),
        (
            _spec(series=[], categories=["C1", "C2"], values=[1, 2]),
            "part_to_whole_series_count",
        ),
        (
            _spec(
                series=[
                    {"name": "A", "values": [1, 2]},
                    {"name": "B", "values": [3, 4]},
                ],
                categories=["C1", "C2"],
            ),
            "part_to_whole_series_count",
        ),
        (_spec(categories=["C1", "C2"], values=[1, -1]), "part_to_whole_negative_value"),
        (_spec(categories=["C1", "C2"], values=[0, 0]), "part_to_whole_zero_total"),
        (
            _spec(categories=["C1", "C2"], values=[1]),
            "chart_series_length_mismatch",
        ),
        (_spec(chart_type="PIE"), "unsupported_chart_type"),
        (
            _spec(presentation={"categoryAxis": {"title": "Not meaningful"}}),
            "part_to_whole_axis_unsupported",
        ),
        (
            _spec(presentation={"valueAxis": {"title": "Not meaningful"}}),
            "part_to_whole_axis_unsupported",
        ),
        (
            _spec(presentation={"holeSize": 60}),
            "part_to_whole_hole_size_unsupported",
        ),
        (
            _spec(presentation={"labels": "category"}),
            "invalid_chart_labels",
        ),
        (
            _spec(presentation={"labels": "value,percent"}),
            "invalid_chart_labels",
        ),
    ],
)
def test_check_blocks_part_to_whole_invalid_specs(
    tmp_path: Path,
    spec: str,
    code: str,
) -> None:
    report = check_author_html(_write(tmp_path, _html(spec), f"invalid-{code}.html"))
    assert report.status == "BLOCK", report.as_dict()
    assert code in {item.code for item in report.diagnostics}


def test_part_to_whole_percent_labels_are_type_specific() -> None:
    with pytest.raises(ChartSpecError) as exc_info:
        parse_chart_spec(
            _spec("column", labels="percent"),
            source_object="slide[1]/div[1]",
        )
    assert exc_info.value.code == "chart_percent_labels_type"


@pytest.mark.parametrize(
    ("chart_type", "labels"),
    [("pie", "none"), ("pie", "value"), ("doughnut", "percent")],
)
@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
def test_build_proves_one_native_part_to_whole_chart_and_readback(
    tmp_path: Path,
    chart_type: str,
    labels: str,
) -> None:
    source_path = _write(tmp_path, _html(_spec(chart_type, labels=labels)), f"{chart_type}.html")
    output = tmp_path / f"{chart_type}.pptx"

    built = asyncio.run(build_author_html(source_path, output))
    assert built.status == "VISUAL_REVIEW_REQUIRED", built.as_dict()
    assert output.is_file()

    evidence = output.with_suffix(".evidence")
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    readback = json.loads((evidence / "readback.json").read_text(encoding="utf-8"))
    native = json.loads((evidence / "native-evidence.json").read_text(encoding="utf-8"))

    assert manifest["object_kind_counts"] == {"chart": 1}
    chart = manifest["objects"][0]
    assert chart["kind"] == "chart"
    assert chart["chart"]["type"] == chart_type
    assert chart["chart"]["categories"] == ["North", "South", "North"]
    assert chart["chart"]["series"] == [
        {"name": "Share", "values": [10.0, 20.0, 30.0]}
    ]
    assert chart["chart"]["labels"] == labels
    if chart_type == "doughnut":
        assert chart["chart"]["hole_size"] == 50
    else:
        assert "hole_size" not in chart["chart"]

    assert readback["object_kind_counts"] == {"chart": 1}
    assert readback["objects"][0]["chart"] == chart["chart"]
    assert readback["objects"][0]["native_kind"] == "chart"
    assert native["diagnostics"]["unsupported"] == 0
    assert native["diagnostics"]["unresolved"] == 0
    assert native["diagnostics"]["material_delta"] == 0
    assert native["charts"]["readback"][0]["chart_seam"]["native_kind"] == "chart"
    readback_seam = native["charts"]["readback"][0]["chart_seam"]
    if chart_type == "doughnut":
        assert readback_seam["hole_size"] == 50
    else:
        assert "hole_size" not in readback_seam
    assert readback["objects"][0]["bounds_pt"] == chart["bounds_pt"]
    assert (evidence / "visual-review.json").is_file()
    assert (evidence / "comparisons" / "slide-001.png").is_file()
    assert json.loads((evidence / "validate.json").read_text(encoding="utf-8"))["status"] == "PASS"
    assert json.loads((evidence / "issues.json").read_text(encoding="utf-8"))["status"] == "PASS"
