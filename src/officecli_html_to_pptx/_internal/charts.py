"""Private native-chart semantics and the narrow OfficeCLI chart adapter.

The Author Contract owns the JSON shape and its validation.  This module keeps
that normalized value model separate from OfficeCLI's string-based chart
properties so the compiler and independent readback never exchange raw backend
paths or command syntax.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, Mapping
from xml.etree import ElementTree
from xml.sax.saxutils import escape as xml_escape

from .pptx_reader import length_to_points


CATEGORY_CHART_TYPES = ("column", "bar", "line")
PART_TO_WHOLE_CHART_TYPES = ("pie", "doughnut")
CHART_TYPES = CATEGORY_CHART_TYPES + PART_TO_WHOLE_CHART_TYPES
_CHART_TYPE_SET = frozenset(CHART_TYPES)
_PART_TO_WHOLE_TYPE_SET = frozenset(PART_TO_WHOLE_CHART_TYPES)
_CHART_LABEL_MODES = frozenset({"none", "value", "percent"})
_CHART_LEGEND_POSITIONS = frozenset({"none", "top", "bottom", "left", "right"})
_CHART_NUMBER_FORMATS = frozenset(
    {
        "general",
        "integer",
        "integer-group",
        "decimal1",
        "decimal1-group",
        "percent0",
        "percent1",
    }
)
_NUMBER_FORMAT_MAP = {
    "general": "General",
    "integer": "0",
    "integer-group": "#,##0",
    "decimal1": "0.0",
    "decimal1-group": "#,##0.0",
    "percent0": "0%",
    "percent1": "0.0%",
}
_NUMBER_FORMAT_REVERSE_MAP = {
    value.lower(): key for key, value in _NUMBER_FORMAT_MAP.items()
}
_SERIES_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DOUGHNUT_HOLE_SIZE = 50


class ChartSpecError(ValueError):
    """A strict, source-independent chart-spec validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ChartSeriesSpec:
    """One ordered, named native-chart series."""

    name: str
    values: tuple[float, ...]
    color: str = "auto"
    office_color: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "values": list(self.values)}


@dataclass(frozen=True)
class ChartSpec:
    """Normalized Author semantics passed across the compiler seam."""

    source_identity: str
    source_path: str
    chart_type: str
    categories: tuple[str, ...]
    series: tuple[ChartSeriesSpec, ...]
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    data_labels: str = "none"
    doughnut_hole_size: int | None = None
    title: str | None = None
    legend: str = "none"
    category_axis_title: str | None = None
    value_axis_title: str | None = None
    value_axis_number_format: str = "general"

    def semantic_dict(self) -> dict[str, Any]:
        """Return only normalized material chart semantics."""
        result: dict[str, Any] = {
            "type": self.chart_type,
            "categories": list(self.categories),
            "series": [series.as_dict() for series in self.series],
            "labels": self.data_labels,
        }
        if self.doughnut_hole_size is not None:
            result["hole_size"] = self.doughnut_hole_size
        if self.title is not None:
            result["title"] = self.title
        if self.legend != "none":
            result["legend"] = self.legend
        if self.category_axis_title is not None:
            result["category_axis_title"] = self.category_axis_title
        if self.value_axis_title is not None:
            result["value_axis_title"] = self.value_axis_title
        if self.value_axis_number_format != "general":
            result["value_axis_number_format"] = self.value_axis_number_format
        if any(series.color != "auto" for series in self.series):
            result["series_colors"] = [series.color for series in self.series]
        return result

    def as_dict(self) -> dict[str, Any]:
        """Return seam metadata plus normalized chart semantics for Evidence."""
        return {
            "source_identity": self.source_identity,
            "source_path": self.source_path,
            "bounds_pt": list(self.bounds),
            "series_colors": [series.color for series in self.series],
            "presentation": {
                "title": self.title,
                "legend": self.legend,
                "labels": self.data_labels,
                "category_axis_title": self.category_axis_title,
                "value_axis_title": self.value_axis_title,
                "value_axis_number_format": self.value_axis_number_format,
            },
            **self.semantic_dict(),
        }


@dataclass(frozen=True)
class ChartReadback:
    """Normalized native chart data obtained independently from OfficeCLI."""

    source_identity: str
    source_path: str
    bounds: tuple[float, float, float, float]
    native_kind: str
    chart_type: str
    categories: tuple[str, ...]
    series: tuple[ChartSeriesSpec, ...]
    data_labels: str = "none"
    doughnut_hole_size: int | None = None
    title: str | None = None
    legend: str = "none"
    category_axis_title: str | None = None
    value_axis_title: str | None = None
    value_axis_number_format: str = "general"
    office_series_colors: tuple[str | None, ...] = ()

    def semantic_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.chart_type,
            "categories": list(self.categories),
            "series": [series.as_dict() for series in self.series],
        }
        result["labels"] = self.data_labels
        if self.doughnut_hole_size is not None:
            result["hole_size"] = self.doughnut_hole_size
        if self.title is not None:
            result["title"] = self.title
        if self.legend != "none":
            result["legend"] = self.legend
        if self.category_axis_title is not None:
            result["category_axis_title"] = self.category_axis_title
        if self.value_axis_title is not None:
            result["value_axis_title"] = self.value_axis_title
        if self.value_axis_number_format != "general":
            result["value_axis_number_format"] = self.value_axis_number_format
        if any(series.color != "auto" for series in self.series):
            result["series_colors"] = [series.color for series in self.series]
        return result

    def as_dict(self) -> dict[str, Any]:
        """Return independent native seam metadata and normalized semantics."""
        return {
            "source_identity": self.source_identity,
            "source_path": self.source_path,
            "bounds_pt": list(self.bounds),
            "native_kind": self.native_kind,
            "series_colors": [series.color for series in self.series],
            "presentation": {
                "title": self.title,
                "legend": self.legend,
                "labels": self.data_labels,
                "category_axis_title": self.category_axis_title,
                "value_axis_title": self.value_axis_title,
                "value_axis_number_format": self.value_axis_number_format,
            },
            **(
                {"office_series_colors": list(self.office_series_colors)}
                if self.office_series_colors
                else {}
            ),
            **self.semantic_dict(),
        }


class _DuplicateKey(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ChartSpecError(
        "invalid_chart_spec_constant",
        f"Chart spec contains non-finite JSON constant {value!r}.",
    )


def _parse_json(raw: str, source_object: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except _DuplicateKey as exc:
        raise ChartSpecError(
            "duplicate_chart_spec_key",
            f"Chart spec at {source_object} contains duplicate object key {exc.args[0]!r}.",
        ) from exc
    except ChartSpecError:
        raise
    except (TypeError, json.JSONDecodeError) as exc:
        raise ChartSpecError(
            "invalid_chart_spec_json",
            f"Chart spec at {source_object} is not strict JSON: {exc}.",
        ) from exc


def _expect_object(value: Any, source_object: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ChartSpecError(
            "invalid_chart_spec_object",
            f"Chart spec {label} at {source_object} must be a JSON object.",
        )
    return value


def _reject_unknown_fields(
    value: Mapping[str, Any],
    allowed: frozenset[str],
    source_object: str,
    label: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ChartSpecError(
            "unknown_chart_spec_field",
            f"Chart spec {label} at {source_object} has unknown field(s): {', '.join(unknown)}.",
        )


def _required_string(
    value: Mapping[str, Any],
    key: str,
    source_object: str,
    label: str,
) -> str:
    result = value.get(key)
    if not isinstance(result, str):
        raise ChartSpecError(
            "invalid_chart_spec_field",
            f"Chart spec {label} field {key!r} at {source_object} must be a string.",
        )
    return result


def parse_chart_spec(
    raw: str,
    *,
    source_object: str,
    source_identity: str | None = None,
    bounds: tuple[float, float, float, float] | None = None,
) -> ChartSpec:
    """Parse one strict native-chart spec without executing embedded data."""
    root = _parse_json(raw, source_object)
    root = _expect_object(root, source_object, "root")
    chart_type = _required_string(root, "type", source_object, "root")
    if chart_type not in _CHART_TYPE_SET:
        raise ChartSpecError(
            "unsupported_chart_type",
            f"Chart type {chart_type!r} at {source_object} is outside the native-chart surface.",
        )
    _reject_unknown_fields(
        root,
        frozenset({"type", "categories", "series", "presentation", "holeSize"}),
        source_object,
        "root",
    )

    if "holeSize" in root:
        raise ChartSpecError(
            "part_to_whole_hole_size_unsupported",
            f"Authored holeSize at {source_object} is not part of the native-chart Contract.",
        )

    categories_value = root.get("categories")
    if not isinstance(categories_value, list) or not categories_value:
        raise ChartSpecError(
            "invalid_chart_categories",
            f"Chart spec categories at {source_object} must be a non-empty JSON array.",
        )
    if chart_type in _PART_TO_WHOLE_TYPE_SET and not 2 <= len(categories_value) <= 6:
        raise ChartSpecError(
            "part_to_whole_category_limit",
            f"Chart spec at {source_object} supports 2 to 6 categories for {chart_type} charts.",
        )
    if chart_type in CATEGORY_CHART_TYPES and len(categories_value) > 12:
        raise ChartSpecError(
            "chart_category_limit",
            f"Chart spec at {source_object} supports at most 12 categories.",
        )
    categories: list[str] = []
    for index, category in enumerate(categories_value, start=1):
        if not isinstance(category, str) or not category.strip():
            raise ChartSpecError(
                "invalid_chart_category",
                f"Chart category {index} at {source_object} must be a non-empty string after trimming.",
            )
        categories.append(category.strip())

    series_value = root.get("series")
    if not isinstance(series_value, list):
        raise ChartSpecError(
            "invalid_chart_series",
            f"Chart spec series at {source_object} must be a non-empty JSON array.",
        )
    if chart_type in _PART_TO_WHOLE_TYPE_SET and len(series_value) != 1:
        raise ChartSpecError(
            "part_to_whole_series_count",
            f"Chart spec at {source_object} requires exactly one series for {chart_type} charts.",
        )
    if chart_type in CATEGORY_CHART_TYPES and not series_value:
        raise ChartSpecError(
            "invalid_chart_series",
            f"Chart spec series at {source_object} must be a non-empty JSON array.",
        )
    if chart_type in CATEGORY_CHART_TYPES and len(series_value) > 3:
        raise ChartSpecError(
            "chart_series_limit",
            f"Chart spec at {source_object} supports at most 3 series.",
        )

    series: list[ChartSeriesSpec] = []
    names: set[str] = set()
    for series_index, raw_series in enumerate(series_value, start=1):
        item = _expect_object(raw_series, source_object, f"series[{series_index}]")
        _reject_unknown_fields(
            item,
            frozenset({"name", "values", "color"}),
            source_object,
            f"series[{series_index}]",
        )
        name = _required_string(item, "name", source_object, f"series[{series_index}]")
        normalized_name = name.strip()
        if not normalized_name:
            raise ChartSpecError(
                "invalid_chart_series_name",
                f"Chart series {series_index} at {source_object} must have a non-empty name after trimming.",
            )
        if normalized_name in names:
            raise ChartSpecError(
                "duplicate_chart_series_name",
                f"Chart series names at {source_object} must be unique after trimming; {name!r} repeats one.",
            )
        names.add(normalized_name)

        values_value = item.get("values")
        if not isinstance(values_value, list):
            raise ChartSpecError(
                "invalid_chart_values",
                f"Chart series {series_index} values at {source_object} must be a JSON array.",
            )
        if len(values_value) != len(categories):
            raise ChartSpecError(
                "chart_series_length_mismatch",
                f"Chart series {series_index} at {source_object} has {len(values_value)} values for {len(categories)} categories.",
            )
        values: list[float] = []
        for value_index, number in enumerate(values_value, start=1):
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise ChartSpecError(
                    "invalid_chart_value",
                    f"Chart value {series_index}.{value_index} at {source_object} must be a finite JSON number.",
                )
            try:
                converted = float(number)
            except OverflowError as exc:
                raise ChartSpecError(
                    "invalid_chart_value",
                    f"Chart value {series_index}.{value_index} at {source_object} must be a finite JSON number.",
                ) from exc
            if not math.isfinite(converted):
                raise ChartSpecError(
                    "invalid_chart_value",
                    f"Chart value {series_index}.{value_index} at {source_object} must be a finite JSON number.",
                )
            values.append(converted)
        if "color" not in item:
            color = "auto"
        else:
            raw_color = item["color"]
            if not isinstance(raw_color, str) or not _SERIES_COLOR_RE.fullmatch(raw_color):
                raise ChartSpecError(
                    "invalid_chart_series_color",
                    f"Chart series {series_index} color at {source_object} must be a six-digit #RRGGBB value.",
                )
            color = raw_color.upper()
        series.append(ChartSeriesSpec(normalized_name, tuple(values), color=color))

    data_labels = "none"
    title: str | None = None
    legend = "none"
    category_axis_title: str | None = None
    value_axis_title: str | None = None
    value_axis_number_format = "general"
    if "presentation" in root:
        presentation_value = root["presentation"]
        presentation = _expect_object(presentation_value, source_object, "presentation")
        if "holeSize" in presentation:
            raise ChartSpecError(
                "part_to_whole_hole_size_unsupported",
                f"Authored holeSize at {source_object} is not part of the native-chart Contract.",
            )
        if chart_type in _PART_TO_WHOLE_TYPE_SET:
            if "categoryAxis" in presentation or "valueAxis" in presentation:
                raise ChartSpecError(
                    "part_to_whole_axis_unsupported",
                    f"Pie and doughnut charts at {source_object} cannot declare categoryAxis or valueAxis.",
                )
        _reject_unknown_fields(
            presentation,
            frozenset(
                {
                    "title",
                    "legend",
                    "labels",
                    "categoryAxis",
                    "valueAxis",
                }
            ),
            source_object,
            "presentation",
        )
        if "title" in presentation:
            raw_title = presentation["title"]
            if not isinstance(raw_title, str) or not raw_title.strip():
                raise ChartSpecError(
                    "invalid_chart_title",
                    f"Chart title at {source_object} must be a non-empty string after trimming.",
                )
            title = raw_title.strip()
        raw_legend = presentation.get("legend", "none")
        if not isinstance(raw_legend, str) or raw_legend not in _CHART_LEGEND_POSITIONS:
            raise ChartSpecError(
                "invalid_chart_legend",
                f"Chart legend at {source_object} must be one of none, top, bottom, left, or right.",
            )
        legend = raw_legend
        raw_labels = presentation.get("labels", "none")
        if not isinstance(raw_labels, str) or raw_labels not in _CHART_LABEL_MODES:
            raise ChartSpecError(
                "invalid_chart_labels",
                f"Chart labels at {source_object} must be one of none, value, or percent.",
            )
        data_labels = raw_labels

        if "categoryAxis" in presentation:
            category_axis = _expect_object(
                presentation["categoryAxis"], source_object, "categoryAxis"
            )
            _reject_unknown_fields(
                category_axis,
                frozenset({"title"}),
                source_object,
                "categoryAxis",
            )
            if "title" in category_axis:
                raw_axis_title = category_axis["title"]
                if not isinstance(raw_axis_title, str) or not raw_axis_title.strip():
                    raise ChartSpecError(
                        "invalid_chart_axis_title",
                        f"Category-axis title at {source_object} must be a non-empty string after trimming.",
                    )
                category_axis_title = raw_axis_title.strip()

        if "valueAxis" in presentation:
            value_axis = _expect_object(
                presentation["valueAxis"], source_object, "valueAxis"
            )
            _reject_unknown_fields(
                value_axis,
                frozenset({"title", "numberFormat"}),
                source_object,
                "valueAxis",
            )
            if "title" in value_axis:
                raw_axis_title = value_axis["title"]
                if not isinstance(raw_axis_title, str) or not raw_axis_title.strip():
                    raise ChartSpecError(
                        "invalid_chart_axis_title",
                        f"Value-axis title at {source_object} must be a non-empty string after trimming.",
                    )
                value_axis_title = raw_axis_title.strip()
            raw_number_format = value_axis.get("numberFormat", "general")
            if (
                not isinstance(raw_number_format, str)
                or raw_number_format not in _CHART_NUMBER_FORMATS
            ):
                raise ChartSpecError(
                    "invalid_chart_number_format",
                    f"Value-axis numberFormat at {source_object} must use a closed semantic token.",
                )
            value_axis_number_format = raw_number_format
    if data_labels == "percent" and chart_type in CATEGORY_CHART_TYPES:
        raise ChartSpecError(
            "chart_percent_labels_type",
            f"Percent labels are supported only for pie and doughnut charts at {source_object}.",
        )

    doughnut_hole_size: int | None = None
    if chart_type in _PART_TO_WHOLE_TYPE_SET:
        values = series[0].values
        if any(value < 0 for value in values):
            raise ChartSpecError(
                "part_to_whole_negative_value",
                f"{chart_type.title()} chart values at {source_object} must be non-negative.",
            )
        if sum(values) <= 0:
            raise ChartSpecError(
                "part_to_whole_zero_total",
                f"{chart_type.title()} chart values at {source_object} must have a positive total.",
            )
        if chart_type == "doughnut":
            doughnut_hole_size = DOUGHNUT_HOLE_SIZE

    identity = str(
        source_identity if source_identity is not None else source_object
    ).strip()
    if not identity:
        identity = source_object
    return ChartSpec(
        source_identity=identity,
        source_path=source_object,
        chart_type=chart_type,
        categories=tuple(categories),
        series=tuple(series),
        bounds=_normalize_bounds(bounds),
        data_labels=data_labels,
        doughnut_hole_size=doughnut_hole_size,
        title=title,
        legend=legend,
        category_axis_title=category_axis_title,
        value_axis_title=value_axis_title,
        value_axis_number_format=value_axis_number_format,
    )


def _normalize_bounds(
    bounds: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float]:
    if bounds is None:
        return (0.0, 0.0, 0.0, 0.0)
    if len(bounds) != 4:
        raise ValueError("Chart bounds must contain exactly four values.")
    normalized = tuple(float(value) for value in bounds)
    if not all(math.isfinite(value) for value in normalized):
        raise ValueError("Chart bounds must contain finite values.")
    return (normalized[0], normalized[1], normalized[2], normalized[3])


def _number_text(value: float) -> str:
    if value == 0:
        return "0"
    return format(value, ".15g")


class OfficeCLIChartAdapter:
    """Private mapping between normalized native charts and OfficeCLI props."""

    _TYPE_MAP = {chart_type: chart_type for chart_type in CHART_TYPES}
    _READBACK_TYPE_MAP = {
        "column": "column",
        "columnclustered": "column",
        "bar": "bar",
        "barclustered": "bar",
        "line": "line",
        "lineclustered": "line",
        "pie": "pie",
        "doughnut": "doughnut",
    }
    _LEGEND_READBACK_MAP = {
        "none": "none",
        "top": "top",
        "bottom": "bottom",
        "left": "left",
        "right": "right",
    }

    @classmethod
    def creation_props(
        cls,
        spec: ChartSpec,
        bounds: tuple[float, float, float, float],
    ) -> dict[str, str]:
        x, y, width, height = bounds
        # OfficeCLI's chart add surface accepts a compact series string. Use
        # backend-safe placeholders here; write_commands replaces category XML
        # literally and then writes ordered series values through native paths.
        placeholder_data = ";".join(
            f"Series{index}:{','.join(_number_text(value) for value in series.values)}"
            for index, series in enumerate(spec.series, start=1)
        )
        props = {
            "chartType": cls._TYPE_MAP[spec.chart_type],
            "data": placeholder_data,
            "categories": ",".join(
                f"Category{index}" for index in range(1, len(spec.categories) + 1)
            ),
            "x": f"{x:.4f}pt",
            "y": f"{y:.4f}pt",
            "width": f"{width:.4f}pt",
            "height": f"{height:.4f}pt",
        }
        # These are the adapter's private OfficeCLI property names.  The
        # Author Contract exposes only normalized tokens on ChartSpec.
        props["legend"] = spec.legend
        props["dataLabels"] = spec.data_labels
        if spec.chart_type in CATEGORY_CHART_TYPES:
            props["axisnumfmt"] = _NUMBER_FORMAT_MAP[spec.value_axis_number_format]
        if spec.title is not None:
            props["title"] = spec.title
        if spec.category_axis_title is not None:
            props["catTitle"] = spec.category_axis_title
        if spec.value_axis_title is not None:
            props["axistitle"] = spec.value_axis_title
        if spec.doughnut_hole_size is not None:
            props["holeSize"] = str(spec.doughnut_hole_size)
        return props

    @classmethod
    def write_commands(
        cls,
        spec: ChartSpec,
        chart_path: str,
        chart_part: str,
    ) -> list[dict[str, Any]]:
        commands: list[dict[str, Any]] = [
            {
                "command": "raw-set",
                "part": chart_part,
                "xpath": '//*[local-name()="cat"]',
                "action": "replace",
                "xml": cls._category_xml(spec.categories),
            }
        ]
        for index, series in enumerate(spec.series, start=1):
            series_props: dict[str, str] = {
                "name": series.name,
                "values": ",".join(_number_text(value) for value in series.values),
            }
            if series.color != "auto":
                series_props["color"] = series.color[1:]
            commands.append(
                {
                    "command": "set",
                    "path": f"{chart_path}/series[{index}]",
                    "props": series_props,
                }
            )
        return commands

    @staticmethod
    def _category_xml(categories: tuple[str, ...]) -> str:
        points = "".join(
            f'<c:pt idx="{index}"><c:v>{xml_escape(category)}</c:v></c:pt>'
            for index, category in enumerate(categories)
        )
        return (
            '<c:cat xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">'
            f"<c:strLit><c:ptCount val=\"{len(categories)}\"/>{points}</c:strLit>"
            "</c:cat>"
        )

    @staticmethod
    def _raw_points(node: ElementTree.Element | None) -> tuple[str, ...]:
        if node is None:
            return ()
        points: list[tuple[int, str]] = []
        for position, point in enumerate(node.findall("{*}pt")):
            try:
                index = int(point.get("idx", position))
            except (TypeError, ValueError):
                index = position
            value_node = point.find("{*}v")
            points.append((index, value_node.text if value_node is not None and value_node.text is not None else ""))
        return tuple(value for _, value in sorted(points, key=lambda item: item[0]))

    @staticmethod
    def _raw_series_color(node: ElementTree.Element) -> str | None:
        color_node = node.find(".//{*}spPr//{*}solidFill/{*}srgbClr")
        if color_node is None:
            return None
        value = str(color_node.get("val", "") or "").strip()
        if re.fullmatch(r"[0-9a-fA-F]{6}", value):
            return f"#{value.upper()}"
        return None

    @classmethod
    def _raw_chart_data(
        cls,
        raw_xml: str,
    ) -> tuple[tuple[str, ...], tuple[ChartSeriesSpec, ...]]:
        root = ElementTree.fromstring(raw_xml)
        series_nodes = root.findall(".//{*}ser")
        if not series_nodes:
            return (), ()

        categories: tuple[str, ...] = ()
        series: list[ChartSeriesSpec] = []
        for series_node in series_nodes:
            category_node = series_node.find("{*}cat")
            if not categories and category_node is not None:
                literal = category_node.find("{*}strLit")
                if literal is None:
                    reference = category_node.find("{*}strRef")
                    literal = reference.find("{*}strCache") if reference is not None else None
                categories = cls._raw_points(literal)

            tx = series_node.find("{*}tx")
            name = ""
            if tx is not None:
                name_node = tx.find("{*}v")
                if name_node is None:
                    reference = tx.find("{*}strRef")
                    cache = reference.find("{*}strCache") if reference is not None else None
                    name_node = cache.find("{*}pt/{*}v") if cache is not None else None
                name = name_node.text if name_node is not None and name_node.text is not None else ""

            value_node = series_node.find("{*}val")
            values_source = value_node.find("{*}numLit") if value_node is not None else None
            if values_source is None and value_node is not None:
                reference = value_node.find("{*}numRef")
                values_source = reference.find("{*}numCache") if reference is not None else None
            raw_values = cls._raw_points(values_source)
            try:
                values = tuple(float(value) for value in raw_values)
            except ValueError:
                values = ()
            office_color = cls._raw_series_color(series_node)
            series.append(
                ChartSeriesSpec(
                    name,
                    values,
                    color=office_color or "auto",
                    office_color=office_color,
                )
            )
        return categories, tuple(series)

    @staticmethod
    def _raw_presentation(
        raw_xml: str,
    ) -> dict[str, Any]:
        root = ElementTree.fromstring(raw_xml)
        chart_node = root.find("{*}chart")
        labels: str | None = None
        labels_node = (
            chart_node.find(".//{*}dLbls") if chart_node is not None else None
        )
        if labels_node is not None:
            show_value = labels_node.find("{*}showVal")
            show_percent = labels_node.find("{*}showPercent")
            value_enabled = show_value is not None and show_value.get("val") == "1"
            percent_enabled = show_percent is not None and show_percent.get("val") == "1"
            if percent_enabled:
                labels = "percent"
            elif value_enabled:
                labels = "value"
            else:
                labels = "none"
        hole_node = root.find(".//{*}doughnutChart/{*}holeSize")
        hole_size: int | None = None
        if hole_node is not None:
            try:
                hole_size = int(hole_node.get("val", ""))
            except (TypeError, ValueError):
                hole_size = None

        def title_text(node: ElementTree.Element | None) -> str | None:
            if node is None:
                return None
            text = "".join(
                item.text or "" for item in node.findall(".//{*}t")
            ).strip()
            return text or None

        title = title_text(chart_node.find("{*}title") if chart_node is not None else None)
        plot_area = chart_node.find("{*}plotArea") if chart_node is not None else None
        category_axis = plot_area.find("{*}catAx") if plot_area is not None else None
        value_axis = plot_area.find("{*}valAx") if plot_area is not None else None
        category_axis_title = title_text(
            category_axis.find("{*}title") if category_axis is not None else None
        )
        value_axis_title = title_text(
            value_axis.find("{*}title") if value_axis is not None else None
        )
        number_format_node = (
            value_axis.find("{*}numFmt") if value_axis is not None else None
        )
        raw_number_format = (
            str(number_format_node.get("formatCode", "") or "").strip().lower()
            if number_format_node is not None
            else ""
        )
        value_axis_number_format = _NUMBER_FORMAT_REVERSE_MAP.get(
            raw_number_format, "general"
        )
        legend_node = chart_node.find("{*}legend") if chart_node is not None else None
        legend_position = "none"
        if legend_node is not None:
            position_node = legend_node.find("{*}legendPos")
            legend_position = {
                "t": "top",
                "b": "bottom",
                "l": "left",
                "r": "right",
            }.get(
                str(position_node.get("val", "") if position_node is not None else "").lower(),
                "none",
            )
        return {
            "labels": labels,
            "hole_size": hole_size,
            "title": title,
            "legend": legend_position,
            "category_axis_title": category_axis_title,
            "value_axis_title": value_axis_title,
            "value_axis_number_format": value_axis_number_format,
        }

    @classmethod
    def readback(
        cls,
        node: Mapping[str, Any],
        raw_xml: str | None = None,
        expected_series_colors: tuple[str, ...] | None = None,
    ) -> ChartReadback:
        format_data = node.get("format", {})
        raw_chart_type = str(format_data.get("chartType", "") or "").lower()
        chart_type = cls._READBACK_TYPE_MAP.get(raw_chart_type, raw_chart_type)
        data_labels = str(format_data.get("dataLabels", "none") or "none").lower()
        if data_labels not in _CHART_LABEL_MODES:
            data_labels = "none"
        doughnut_hole_size: int | None = None
        raw_hole_size = format_data.get("holeSize")
        if raw_hole_size not in (None, ""):
            try:
                doughnut_hole_size = int(float(str(raw_hole_size).strip()))
            except (TypeError, ValueError):
                doughnut_hole_size = None
        presentation = (
            cls._raw_presentation(raw_xml) if raw_xml is not None else {}
        )
        title = presentation.get("title") or str(format_data.get("title", "") or "").strip() or None
        legend = presentation.get("legend") or str(format_data.get("legend", "none") or "none").lower()
        legend = cls._LEGEND_READBACK_MAP.get(legend, "none")
        category_axis_title = presentation.get("category_axis_title") or str(
            format_data.get("catTitle", "") or ""
        ).strip() or None
        value_axis_title = presentation.get("value_axis_title") or str(
            format_data.get("axisTitle", "") or ""
        ).strip() or None
        value_axis_number_format = presentation.get("value_axis_number_format")
        if value_axis_number_format is None:
            raw_number_format = str(format_data.get("axisNumFmt", "") or "").strip().lower()
            value_axis_number_format = _NUMBER_FORMAT_REVERSE_MAP.get(
                raw_number_format, "general"
            )

        series_nodes = [
            child
            for child in node.get("children", []) or []
            if str(child.get("type", "")).lower() == "series"
        ]
        series: list[ChartSeriesSpec] = []
        office_series_colors: list[str | None] = []
        for index, child in enumerate(series_nodes):
            child_format = child.get("format", {})
            name = str(child_format.get("name", child.get("text", "")) or "")
            raw_values = str(child_format.get("values", "") or "")
            values = tuple(float(value) for value in raw_values.split(",") if value != "")
            raw_color = str(child_format.get("color", "") or "").strip().upper()
            office_color = (
                raw_color if re.fullmatch(r"#[0-9A-F]{6}", raw_color) else None
            )
            office_series_colors.append(office_color)
            series.append(
                ChartSeriesSpec(
                    name,
                    values,
                    color=office_color or "auto",
                    office_color=office_color,
                )
            )

        raw_categories = str(format_data.get("categories", "") or "")
        categories = tuple(raw_categories.split(",")) if raw_categories else ()
        if raw_xml is not None:
            raw_categories, raw_series = cls._raw_chart_data(raw_xml)
            if raw_categories:
                categories = raw_categories
            if raw_series:
                series = list(raw_series)
            office_series_colors = [item.office_color for item in raw_series]
            raw_presentation = cls._raw_presentation(raw_xml)
            raw_labels = raw_presentation["labels"]
            raw_hole_size = raw_presentation["hole_size"]
            if raw_labels is not None:
                data_labels = raw_labels
            if raw_hole_size is not None:
                doughnut_hole_size = raw_hole_size
            title = raw_presentation["title"]
            legend = raw_presentation["legend"]
            category_axis_title = raw_presentation["category_axis_title"]
            value_axis_title = raw_presentation["value_axis_title"]
            value_axis_number_format = raw_presentation["value_axis_number_format"]

        if expected_series_colors is not None:
            normalized_series: list[ChartSeriesSpec] = []
            for index, item in enumerate(series):
                authored_color = (
                    expected_series_colors[index]
                    if index < len(expected_series_colors)
                    else "auto"
                )
                office_color = (
                    office_series_colors[index]
                    if index < len(office_series_colors)
                    else None
                )
                # An omitted author color is the one case where the expected
                # manifest supplies information the backend cannot preserve:
                # the authored mode is ``auto`` even if Office chose an RGB.
                # Explicit authored colors must remain the independent native
                # readback value so missing or changed backend colors produce
                # a material comparison finding.
                readback_color = "auto" if authored_color == "auto" else item.color
                normalized_series.append(
                    ChartSeriesSpec(
                        item.name,
                        item.values,
                        color=readback_color,
                        office_color=office_color,
                    )
                )
            series = normalized_series

        bounds = tuple(
            length_to_points(format_data.get(key))
            for key in ("x", "y", "width", "height")
        )
        return ChartReadback(
            source_identity=str(format_data.get("name", "") or node.get("path", "")),
            source_path=str(node.get("path", "") or ""),
            bounds=(bounds[0], bounds[1], bounds[2], bounds[3]),
            native_kind=str(node.get("type", "") or "").lower(),
            chart_type=chart_type,
            categories=categories,
            series=tuple(series),
            data_labels=data_labels,
            doughnut_hole_size=doughnut_hole_size,
            title=title,
            legend=legend,
            category_axis_title=category_axis_title,
            value_axis_title=value_axis_title,
            value_axis_number_format=value_axis_number_format,
            office_series_colors=tuple(office_series_colors),
        )


__all__ = [
    "CHART_TYPES",
    "CATEGORY_CHART_TYPES",
    "DOUGHNUT_HOLE_SIZE",
    "PART_TO_WHOLE_CHART_TYPES",
    "ChartReadback",
    "ChartSeriesSpec",
    "ChartSpec",
    "ChartSpecError",
    "OfficeCLIChartAdapter",
    "parse_chart_spec",
]
