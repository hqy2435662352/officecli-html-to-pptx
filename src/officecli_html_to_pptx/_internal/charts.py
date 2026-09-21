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
from typing import Any, Mapping
from xml.etree import ElementTree
from xml.sax.saxutils import escape as xml_escape


CATEGORY_CHART_TYPES = ("column", "bar", "line")
PART_TO_WHOLE_CHART_TYPES = ("pie", "doughnut")
CHART_TYPES = CATEGORY_CHART_TYPES + PART_TO_WHOLE_CHART_TYPES
_CHART_TYPE_SET = frozenset(CHART_TYPES)
_PART_TO_WHOLE_TYPE_SET = frozenset(PART_TO_WHOLE_CHART_TYPES)
_CHART_LABEL_MODES = frozenset({"none", "value", "percent"})
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
        return result

    def as_dict(self) -> dict[str, Any]:
        """Return seam metadata plus normalized chart semantics for Evidence."""
        return {
            "source_identity": self.source_identity,
            "source_path": self.source_path,
            "bounds_pt": list(self.bounds),
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

    def semantic_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.chart_type,
            "categories": list(self.categories),
            "series": [series.as_dict() for series in self.series],
        }
        result["labels"] = self.data_labels
        if self.doughnut_hole_size is not None:
            result["hole_size"] = self.doughnut_hole_size
        return result

    def as_dict(self) -> dict[str, Any]:
        """Return independent native seam metadata and normalized semantics."""
        return {
            "source_identity": self.source_identity,
            "source_path": self.source_path,
            "bounds_pt": list(self.bounds),
            "native_kind": self.native_kind,
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
            frozenset({"name", "values"}),
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
        series.append(ChartSeriesSpec(normalized_name, tuple(values)))

    data_labels = "none"
    presentation_value = root.get("presentation")
    if presentation_value is not None:
        presentation = _expect_object(presentation_value, source_object, "presentation")
        if chart_type in _PART_TO_WHOLE_TYPE_SET:
            if "categoryAxis" in presentation or "valueAxis" in presentation:
                raise ChartSpecError(
                    "part_to_whole_axis_unsupported",
                    f"Pie and doughnut charts at {source_object} cannot declare categoryAxis or valueAxis.",
                )
            if "holeSize" in presentation:
                raise ChartSpecError(
                    "part_to_whole_hole_size_unsupported",
                    f"Authored holeSize at {source_object} is not part of the native-chart Contract.",
                )
        _reject_unknown_fields(
            presentation,
            frozenset({"labels"}),
            source_object,
            "presentation",
        )
        raw_labels = presentation.get("labels", "none")
        if not isinstance(raw_labels, str) or raw_labels not in _CHART_LABEL_MODES:
            raise ChartSpecError(
                "invalid_chart_labels",
                f"Chart labels at {source_object} must be one of none, value, or percent.",
            )
        data_labels = raw_labels
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
        props["dataLabels"] = spec.data_labels
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
            commands.append(
                {
                    "command": "set",
                    "path": f"{chart_path}/series[{index}]",
                    "props": {
                        "name": series.name,
                        "values": ",".join(_number_text(value) for value in series.values),
                    },
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
            series.append(ChartSeriesSpec(name, values))
        return categories, tuple(series)

    @staticmethod
    def _raw_presentation(
        raw_xml: str,
    ) -> tuple[str | None, int | None]:
        root = ElementTree.fromstring(raw_xml)
        labels: str | None = None
        labels_node = root.find(".//{*}dLbls")
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
        return labels, hole_size

    @classmethod
    def readback(
        cls,
        node: Mapping[str, Any],
        raw_xml: str | None = None,
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
        series_nodes = [
            child
            for child in node.get("children", []) or []
            if str(child.get("type", "")).lower() == "series"
        ]
        series: list[ChartSeriesSpec] = []
        for index, child in enumerate(series_nodes):
            child_format = child.get("format", {})
            name = str(child_format.get("name", child.get("text", "")) or "")
            raw_values = str(child_format.get("values", "") or "")
            values = tuple(float(value) for value in raw_values.split(",") if value != "")
            series.append(ChartSeriesSpec(name, values))

        raw_categories = str(format_data.get("categories", "") or "")
        categories = tuple(raw_categories.split(",")) if raw_categories else ()
        if raw_xml is not None:
            raw_categories, raw_series = cls._raw_chart_data(raw_xml)
            if raw_categories:
                categories = raw_categories
            if raw_series:
                series = list(raw_series)
            raw_labels, raw_hole_size = cls._raw_presentation(raw_xml)
            if raw_labels is not None:
                data_labels = raw_labels
            if raw_hole_size is not None:
                doughnut_hole_size = raw_hole_size

        def point_value(value: Any) -> float:
            text = str(value or "").strip().lower()
            for suffix in ("pt", "emu", "cm", "mm", "in"):
                if text.endswith(suffix):
                    text = text[: -len(suffix)].strip()
                    break
            try:
                return float(text)
            except ValueError:
                return 0.0

        bounds = tuple(
            point_value(format_data.get(key))
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
