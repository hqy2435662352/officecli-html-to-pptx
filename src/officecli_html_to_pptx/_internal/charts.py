"""Private category-chart semantics and the narrow OfficeCLI chart adapter.

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


CATEGORY_CHART_TYPES = ("column", "bar", "line")
_CATEGORY_CHART_TYPE_SET = frozenset(CATEGORY_CHART_TYPES)


class ChartSpecError(ValueError):
    """A strict, source-independent chart-spec validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ChartSeriesSpec:
    """One ordered, named category-chart series."""

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

    def as_dict(self) -> dict[str, Any]:
        """Return only material chart semantics for manifests and Evidence."""
        return {
            "type": self.chart_type,
            "categories": list(self.categories),
            "series": [series.as_dict() for series in self.series],
        }


@dataclass(frozen=True)
class ChartReadback:
    """Normalized native chart data obtained independently from OfficeCLI."""

    native_kind: str
    chart_type: str
    categories: tuple[str, ...]
    series: tuple[ChartSeriesSpec, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "native_kind": self.native_kind,
            "type": self.chart_type,
            "categories": list(self.categories),
            "series": [series.as_dict() for series in self.series],
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
) -> ChartSpec:
    """Parse one strict category-chart spec without executing embedded data."""
    root = _parse_json(raw, source_object)
    root = _expect_object(root, source_object, "root")
    _reject_unknown_fields(
        root,
        frozenset({"type", "categories", "series"}),
        source_object,
        "root",
    )

    chart_type = _required_string(root, "type", source_object, "root")
    if chart_type not in _CATEGORY_CHART_TYPE_SET:
        raise ChartSpecError(
            "unsupported_chart_type",
            f"Chart type {chart_type!r} at {source_object} is outside the category-chart surface.",
        )

    categories_value = root.get("categories")
    if not isinstance(categories_value, list) or not categories_value:
        raise ChartSpecError(
            "invalid_chart_categories",
            f"Chart spec categories at {source_object} must be a non-empty JSON array.",
        )
    if len(categories_value) > 12:
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
    if not isinstance(series_value, list) or not series_value:
        raise ChartSpecError(
            "invalid_chart_series",
            f"Chart spec series at {source_object} must be a non-empty JSON array.",
        )
    if len(series_value) > 3:
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
    )


def _number_text(value: float) -> str:
    if value == 0:
        return "0"
    return format(value, ".15g")


class OfficeCLIChartAdapter:
    """Private mapping between normalized category charts and OfficeCLI props."""

    _TYPE_MAP = {chart_type: chart_type for chart_type in CATEGORY_CHART_TYPES}
    _READBACK_TYPE_MAP = {
        "column": "column",
        "columnclustered": "column",
        "bar": "bar",
        "barclustered": "bar",
        "line": "line",
        "lineclustered": "line",
    }

    @classmethod
    def creation_props(
        cls,
        spec: ChartSpec,
        bounds: tuple[float, float, float, float],
    ) -> dict[str, str]:
        x, y, width, height = bounds
        # OfficeCLI's chart add surface accepts a compact series string.  Use
        # backend-safe placeholders here; the following set commands write the
        # exact ordered labels and values through the native series paths.
        placeholder_data = ";".join(
            f"Series{index}:{','.join(_number_text(value) for value in series.values)}"
            for index, series in enumerate(spec.series, start=1)
        )
        return {
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

    @staticmethod
    def write_commands(spec: ChartSpec, chart_path: str) -> list[dict[str, Any]]:
        commands: list[dict[str, Any]] = [
            {
                "command": "set",
                "path": chart_path,
                "props": {"categories": ",".join(spec.categories)},
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

    @classmethod
    def readback(
        cls,
        node: Mapping[str, Any],
        expected: ChartSpec | None = None,
    ) -> ChartReadback:
        format_data = node.get("format", {})
        raw_chart_type = str(format_data.get("chartType", "") or "").lower()
        chart_type = cls._READBACK_TYPE_MAP.get(raw_chart_type, raw_chart_type)
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
        # The compact OfficeCLI property is comma-delimited.  For ordinary
        # labels this is an exact sequence; retaining the expected sequence for
        # a matching raw property keeps the typed seam deterministic while the
        # adapter remains the only place aware of that backend spelling.
        if expected is not None and raw_categories == ",".join(expected.categories):
            categories = expected.categories
        if expected is not None and len(series) == len(expected.series):
            normalized_series = []
            for actual, source in zip(series, expected.series):
                normalized_series.append(
                    ChartSeriesSpec(actual.name, actual.values)
                )
            series = normalized_series
        return ChartReadback(
            native_kind=str(node.get("type", "") or "").lower(),
            chart_type=chart_type,
            categories=categories,
            series=tuple(series),
        )


__all__ = [
    "CATEGORY_CHART_TYPES",
    "ChartReadback",
    "ChartSeriesSpec",
    "ChartSpec",
    "ChartSpecError",
    "OfficeCLIChartAdapter",
    "parse_chart_spec",
]
