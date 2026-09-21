"""Focused Contract 1.2 category-chart tests for ticket #29.

These tests exercise the public check/build seam and the independent OfficeCLI
chart readback.  They deliberately cover only the category-chart core; chart
presentation properties belong to the later presentation ticket.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil

import pytest

from officecli_html_to_pptx.application import build_author_html, check_author_html
from officecli_html_to_pptx._internal.charts import (
    ChartSpecError,
    parse_chart_spec,
)
from officecli_html_to_pptx.measurement import extract_measurements


def _html(
    spec: str,
    *,
    chart_attributes: str = 'id="sales-chart"',
    preview: str = "",
    style: str = "left:120px;top:120px;width:960px;height:480px;",
) -> str:
    return f"""<!doctype html>
<html><head><style>
  html, body {{ margin: 0; width: 100%; height: 100%; }}
  .slide {{ width: 1920px; height: 1080px; position: relative; background: #ffffff; }}
</style></head><body>
  <section class="slide">
    <div data-pptx-chart {chart_attributes} style="position:absolute;{style}">
      {preview}
      <script type="application/json" data-pptx-chart-spec>{spec}</script>
    </div>
  </section>
</body></html>
"""


VALID_SPEC = json.dumps(
    {
        "type": "column",
        "categories": ["Q1", "Q2", "Q3"],
        "series": [
            {"name": "Revenue", "values": [10, 20.5, 30]},
            {"name": "Cost", "values": [4, 12, 18]},
        ],
    }
)


def _write(tmp_path: Path, source: str, name: str = "chart.html") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_chart_spec_is_strict_and_typed() -> None:
    parsed = parse_chart_spec(VALID_SPEC, source_object="slide[1]/div[1]")
    assert parsed.chart_type == "column"
    assert parsed.categories == ("Q1", "Q2", "Q3")
    assert [series.name for series in parsed.series] == ["Revenue", "Cost"]
    assert parsed.series[0].values == (10.0, 20.5, 30.0)

    invalid_specs = (
        '{"type":"column","type":"bar","categories":["Q1"],"series":[{"name":"S","values":[1]}]}',
        '[]',
        'null',
        '{"type":"COLUMN","categories":["Q1"],"series":[{"name":"S","values":[1]}]}',
        '{"type":"column","categories":["Q1"],"series":[{"name":"S"}]}',
        '{"type":"column","categories":["Q1"],"series":[{"name":"S","values":["1"]}]}',
        '{"type":"column","categories":["Q1"],"series":[{"name":"S","values":[true]}]}',
        '{"type":"column","categories":["Q1"],"series":[{"name":"S","values":[null]}]}',
        '{"type":"column","categories":["Q1"],"series":[{"name":"S","values":[NaN]}]}',
        '{"type":"column","categories":["Q1"],"series":[{"name":"S","values":[1],"extra":true}]}',
        '{"type":"column","categories":["Q1"],"series":[{"name":"S","values":[1,2]}]}',
        '{"type":"column","categories":["Q1"],"series":[{"name":"S","values":[1]}] // comment}',
        '{"type":"column","categories":["Q1"],"series":[{"name":"S","values":[1,]}]}',
    )
    for raw in invalid_specs:
        with pytest.raises(ChartSpecError):
            parse_chart_spec(raw, source_object="slide[1]/div[1]")


def _spec_with_sizes(category_count: int, series_count: int) -> str:
    categories = [f"C{index}" for index in range(category_count)]
    series = [
        {
            "name": f"S{index}",
            "values": [index + value for value in range(category_count)],
        }
        for index in range(series_count)
    ]
    return json.dumps(
        {"type": "column", "categories": categories, "series": series}
    )


def test_category_and_series_limits_accept_boundaries_and_reject_overflow(
    tmp_path: Path,
) -> None:
    for category_count, series_count in ((1, 1), (12, 3)):
        report = check_author_html(
            _write(
                tmp_path,
                _html(_spec_with_sizes(category_count, series_count)),
                f"valid-{category_count}-{series_count}.html",
            )
        )
        assert report.status == "PASS", report.as_dict()

    category_overflow = check_author_html(
        _write(
            tmp_path,
            _html(_spec_with_sizes(13, 1)),
            "category-overflow.html",
        )
    )
    assert category_overflow.status == "BLOCK"
    assert "chart_category_limit" in {
        item.code for item in category_overflow.diagnostics
    }

    series_overflow = check_author_html(
        _write(
            tmp_path,
            _html(_spec_with_sizes(1, 4)),
            "series-overflow.html",
        )
    )
    assert series_overflow.status == "BLOCK"
    assert "chart_series_limit" in {
        item.code for item in series_overflow.diagnostics
    }


@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
def test_repeated_and_comma_categories_preserve_exact_order_in_native_readback(
    tmp_path: Path,
) -> None:
    spec = json.dumps(
        {
            "type": "column",
            "categories": ["North,East", "Repeat", "Repeat"],
            "series": [{"name": "Revenue", "values": [10, 20, 30]}],
        }
    )
    source_path = _write(tmp_path, _html(spec), "comma-categories.html")
    output = tmp_path / "comma-categories.pptx"

    built = asyncio.run(build_author_html(source_path, output))
    assert built.status == "VISUAL_REVIEW_REQUIRED", built.as_dict()
    evidence = output.with_suffix(".evidence")
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    readback = json.loads((evidence / "readback.json").read_text(encoding="utf-8"))
    native = json.loads((evidence / "native-evidence.json").read_text(encoding="utf-8"))

    expected_categories = ["North,East", "Repeat", "Repeat"]
    assert manifest["objects"][0]["chart"]["categories"] == expected_categories
    assert readback["objects"][0]["chart"]["categories"] == expected_categories
    assert native["diagnostics"]["material_delta"] == 0
    compiled_seam = native["charts"]["compiled"][0]["chart_seam"]
    readback_seam = native["charts"]["readback"][0]["chart_seam"]
    assert compiled_seam["source_identity"] == "sales-chart"
    assert compiled_seam["source_path"] == "slide[1]/div[1]"
    assert compiled_seam["bounds_pt"] == native["charts"]["compiled"][0]["bounds_pt"]
    assert readback_seam["source_path"].startswith("/slide[1]/chart[")
    assert readback_seam["bounds_pt"] == native["charts"]["readback"][0]["bounds_pt"]
    assert json.loads((evidence / "validate.json").read_text(encoding="utf-8"))["status"] == "PASS"
    assert json.loads((evidence / "issues.json").read_text(encoding="utf-8"))["status"] == "PASS"


def test_check_accepts_atomic_preview_and_measurement_excludes_descendants(
    tmp_path: Path,
) -> None:
    source = _html(
        VALID_SPEC,
        preview=(
            '<canvas width="800" height="400"></canvas>'
            '<div style="background:#e60012;width:40px;height:20px">preview</div>'
        ),
    )
    path = _write(tmp_path, source)

    checked = check_author_html(path)
    assert checked.status == "PASS", checked.as_dict()

    measurements = asyncio.run(
        extract_measurements(str(path), officecli_mode=True)
    )
    elements = measurements[0]["elements"]
    assert len(elements) == 1
    chart = elements[0]
    assert chart["isChart"] is True
    assert chart["chartSpecText"] == VALID_SPEC
    assert chart["children"] == []


@pytest.mark.parametrize(
    ("spec", "code"),
    [
        (
            '{"type":"column","categories":[],"series":[{"name":"S","values":[]}]}',
            "invalid_chart_categories",
        ),
        (
            '{"type":"column","categories":["Q1"],"series":[]}',
            "invalid_chart_series",
        ),
        (
            '{"type":"column","categories":["Q1"],"series":[{"name":"S","values":[1]},{"name":" S ","values":[2]}]}',
            "duplicate_chart_series_name",
        ),
    ],
)
def test_check_blocks_category_chart_validation_errors(
    tmp_path: Path,
    spec: str,
    code: str,
) -> None:
    report = check_author_html(_write(tmp_path, _html(spec)))
    assert report.status == "BLOCK"
    assert code in {item.code for item in report.diagnostics}


def test_check_blocks_nested_and_multiple_specs(tmp_path: Path) -> None:
    nested = _html(
        VALID_SPEC,
        preview=(
            '<div data-pptx-chart style="width:10px;height:10px">'
            '<script type="application/json" data-pptx-chart-spec>{}</script>'
            '</div>'
        ),
    )
    report = check_author_html(_write(tmp_path, nested, "nested.html"))
    assert report.status == "BLOCK"
    assert "nested_chart" in {item.code for item in report.diagnostics}

    multiple = _html(
        VALID_SPEC,
        preview='<script type="application/json" data-pptx-chart-spec>{}</script>',
    )
    report = check_author_html(_write(tmp_path, multiple, "multiple.html"))
    assert report.status == "BLOCK"
    assert "chart_spec_count" in {item.code for item in report.diagnostics}

    wrong_type = _html(VALID_SPEC).replace(
        'type="application/json"', 'type="text/javascript"'
    )
    report = check_author_html(_write(tmp_path, wrong_type, "wrong-type.html"))
    assert report.status == "BLOCK"
    assert "chart_spec_type" in {item.code for item in report.diagnostics}

    duplicate_id = _html(VALID_SPEC).replace(
        "</section>",
        (
            '<div data-pptx-chart id=" sales-chart " '
            'style="position:absolute;left:0;top:0;width:960px;height:480px;">'
            f'<script type="application/json" data-pptx-chart-spec>{VALID_SPEC}</script>'
            "</div></section>"
        ),
        1,
    )
    report = check_author_html(_write(tmp_path, duplicate_id, "duplicate-id.html"))
    assert report.status == "BLOCK"
    assert "duplicate_chart_identity" in {item.code for item in report.diagnostics}


@pytest.mark.parametrize(
    ("style", "code"),
    [
        ("position:absolute;left:0;top:0;width:0;height:480px;", "invalid_chart_geometry"),
        ("position:absolute;left:0;top:0;width:960px;height:480px;display:none;", "hidden_chart"),
    ],
)
def test_check_blocks_hidden_or_zero_size_chart(
    tmp_path: Path,
    style: str,
    code: str,
) -> None:
    report = check_author_html(_write(tmp_path, _html(VALID_SPEC, style=style)))
    assert report.status == "BLOCK"
    assert code in {item.code for item in report.diagnostics}


@pytest.mark.parametrize("chart_type", ["column", "bar", "line"])
@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
def test_build_creates_one_native_chart_and_zero_material_delta(
    tmp_path: Path,
    chart_type: str,
) -> None:
    typed_spec = VALID_SPEC.replace('"type": "column"', f'"type": "{chart_type}"')
    source_path = _write(tmp_path, _html(typed_spec), f"{chart_type}.html")
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
    assert chart["source_object"] == "sales-chart"
    assert chart["chart"]["type"] == chart_type
    assert chart["chart"]["categories"] == ["Q1", "Q2", "Q3"]
    assert [item["name"] for item in chart["chart"]["series"]] == ["Revenue", "Cost"]

    assert readback["object_kind_counts"] == {"chart": 1}
    assert readback["objects"][0]["chart"] == chart["chart"]
    assert native["diagnostics"]["unsupported"] == 0
    assert native["diagnostics"]["unresolved"] == 0
    assert native["diagnostics"]["material_delta"] == 0
    assert native["charts"]["compiled"][0]["bounds_pt"] == chart["bounds_pt"]
    assert native["charts"]["readback"][0]["native_kind"] == "chart"
    assert json.loads((evidence / "validate.json").read_text(encoding="utf-8"))["status"] == "PASS"
    assert json.loads((evidence / "issues.json").read_text(encoding="utf-8"))["status"] == "PASS"


@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
def test_build_uses_deterministic_source_path_without_html_id(tmp_path: Path) -> None:
    source_path = _write(
        tmp_path,
        _html(VALID_SPEC, chart_attributes=""),
        "no-id.html",
    )
    output = tmp_path / "no-id.pptx"
    built = asyncio.run(build_author_html(source_path, output))
    assert built.status == "VISUAL_REVIEW_REQUIRED", built.as_dict()
    manifest = json.loads(
        (output.with_suffix(".evidence") / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["objects"][0]["source_object"] == "slide[1]/div[1]"
