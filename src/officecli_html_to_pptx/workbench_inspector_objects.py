"""Private table and native-chart Inspector patches for the Workbench."""

from __future__ import annotations

from html import escape, unescape
import json
import math
import re
from typing import Any, Mapping

from ._internal.charts import ChartSpec, ChartSpecError, parse_chart_spec
from .contract import TableTopologyError, build_logical_table_grid
from .workbench_inspector import (
    _event_for,
    _inline_declarations,
    _source_match_records,
)
from .workbench_preview import _SourceParser, _StartEvent


_SOLID_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_LEGEND_POSITIONS = frozenset({"none", "top", "bottom", "left", "right"})
_LABEL_MODES = frozenset({"none", "value", "percent"})


def _simple_cell_text(text: str, event: _StartEvent) -> bool:
    return (
        event.tag in {"td", "th"}
        and not event.self_closing
        and not event.has_element_child
        and not event.has_comment
        and event.end_start is not None
        and "<" not in text[event.end : event.end_start]
    )


def _table_cell_grid_reason(text: str, selection: Mapping[str, Any]) -> str | None:
    cell = selection.get("table_cell")
    if not isinstance(cell, dict):
        return "The cell has no verified table ownership map."
    reason = cell.get("read_only_reason")
    if reason:
        return str(reason)
    if cell.get("ownership") != "anchor":
        return "Covered merged cells belong to their anchor and cannot be edited independently."
    # Recompute normalized ownership from this exact source before offering a
    # write control. The Preview map is advisory; current source is authority.
    parser = _SourceParser(text)
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        parser.repaired = True
    parser.finish()
    if parser.repaired:
        return "The Preview parser repaired this Candidate; table ownership is read-only."
    table_event, repaired = _event_for(text, selection)
    if repaired or table_event is None or table_event.tag not in {"td", "th"}:
        return "The selected table cell has no current source mapping."
    table_index = table_event.table_index
    if table_index is None:
        return "The selected cell has no owning table."
    rows = [
        index
        for index, event in enumerate(parser.events)
        if event.tag == "tr" and event.table_index == table_index
    ]
    row_cells: list[list[_StartEvent]] = []
    for row_index in rows:
        row_cells.append(
            [
                event
                for event in parser.events
                if event.tag in {"td", "th"}
                and event.table_index == table_index
                and _ancestor(parser.events, event.parent_index, "tr") == row_index
            ]
        )
    matrix = [
        [
            {
                "rowspan": event.attrs.get("rowspan"),
                "colspan": event.attrs.get("colspan"),
                "source_object": f"r{row_index + 1}c{column_index + 1}",
                "text": text[event.end : event.end_start] if event.end_start is not None else "",
            }
            for column_index, event in enumerate(row, start=1)
        ]
        for row_index, row in enumerate(row_cells)
    ]
    try:
        grid = build_logical_table_grid(matrix, source_object="selected table")
    except TableTopologyError as exc:
        return exc.message
    selected_row = next(
        (row_index for row_index, row in enumerate(row_cells) if table_event in row),
        None,
    )
    if selected_row is None:
        return "The selected cell is not in the current logical table grid."
    selected_column = row_cells[selected_row].index(table_event)
    region = next(
        (
            item
            for item in grid.regions
            if item.source_row == selected_row and item.source_column == selected_column
        ),
        None,
    )
    if region is None:
        return "The selected cell is not a reliable merged-region anchor."
    expected = [region.anchor_row, region.anchor_column, region.row_span, region.column_span]
    if cell.get("topology") != expected:
        return "The selected table merge topology changed; refresh Preview before editing."
    return None


def _ancestor(events: list[_StartEvent], index: int | None, tag: str) -> int | None:
    while index is not None:
        if events[index].tag == tag:
            return index
        index = events[index].parent_index
    return None


def _fill_field(
    text: str,
    event: _StartEvent,
    computed: Any,
    matched_styles: Any,
    mapping_reason: str | None,
) -> dict[str, Any]:
    computed_values = computed.get("styles") if isinstance(computed, dict) and isinstance(computed.get("styles"), dict) else {}
    computed_value = computed_values.get("background-color")
    sources, rules_complete = _source_match_records(matched_styles)
    _raw_style, _style_start, declarations, style_error = _inline_declarations(text, event)
    direct = [item for item in declarations if item.name == "background-color"]
    conflicts = [item for item in declarations if item.name in {"background", "all"}]
    matched = [
        item
        for item in sources
        if item["scope"] == "element"
        and item["property"] in {"background", "background-color", "all"}
    ]
    source_parts: list[str] = []
    for source in matched:
        where = source["selector"] or "stylesheet rule"
        if source["selector"] == "element.style":
            where = "inline style"
        if source["scope"] == "ancestor":
            where = f"inherited from {where}"
        source_parts.append(f"{where}: {source['value']}")
    inline_source = direct[0].value if len(direct) == 1 else None
    origin = "inline style" if inline_source is not None else "; ".join(dict.fromkeys(source_parts)) or "browser default or inherited value"
    source_value = inline_source if inline_source is not None else " · ".join(dict.fromkeys(source_parts)) or None

    reason = mapping_reason
    if reason is None and not rules_complete:
        reason = "The Preview could not verify all matched CSS rules."
    if reason is None and style_error:
        reason = style_error
    if reason is None and len(direct) > 1:
        reason = "The inline background-color declaration occurs more than once."
    if reason is None and conflicts:
        reason = "An inline background shorthand makes the selected solid fill ambiguous."
    if reason is None and (
        any(item["important"] for item in matched)
        or any(item.important for item in direct + conflicts)
    ):
        reason = "A matching !important declaration may override a local fill edit."
    if reason is None and (
        any("var(" in item["value"].lower() for item in matched)
        or any("var(" in item.value.lower() for item in direct + conflicts)
    ):
        reason = "CSS variables make the selected fill cascade ambiguous."
    if reason is None and any(
        item["scope"] == "element"
        and item["property"] == "background-image"
        and item["value"].strip().lower() not in {"", "none"}
        for item in sources
    ):
        reason = "A background image makes the selected fill read-only."
    return {
        "computed": computed_value,
        "source": source_value,
        "origin": origin,
        "editable": reason is None,
        "reason": reason,
        "local_override": inline_source is None,
        "intent": {"kind": "property", "name": "background-color"},
    }


def inspect_table_selection(
    text: str,
    selection: Mapping[str, Any],
    computed: Any,
    matched_styles: Any,
) -> dict[str, Any]:
    event, repaired = _event_for(text, selection)
    if repaired or event is None or selection.get("status") != "mapped" or event.tag not in {"td", "th"}:
        reason = "The selected cell has no current safe source mapping."
        return {"writable": False, "read_only_reason": reason, "text": {"editable": False, "reason": reason}, "fields": {}}
    mapping_reason = _table_cell_grid_reason(text, selection)
    editable_text = _simple_cell_text(text, event) and mapping_reason is None
    raw_text = text[event.end : event.end_start] if event.end_start is not None and _simple_cell_text(text, event) else None
    source_text = unescape(raw_text) if raw_text is not None else None
    computed_text = computed.get("text") if isinstance(computed, dict) and isinstance(computed.get("text"), str) else source_text
    text_reason = mapping_reason or (None if editable_text else str(selection.get("text_reason") or "A single simple table cell text leaf is required."))
    return {
        "writable": editable_text,
        "read_only_reason": mapping_reason,
        "table_cell": dict(selection.get("table_cell") or {}),
        "text": {
            "source": source_text,
            "computed": computed_text,
            "origin": "Author HTML table anchor cell text node",
            "editable": editable_text,
            "reason": text_reason,
        },
        "fields": {
            "background-color": _fill_field(text, event, computed, matched_styles, mapping_reason),
        },
    }


def _validate_fill(value: Any) -> str:
    if not isinstance(value, str) or not _SOLID_COLOR.fullmatch(value.strip()):
        raise ValueError("Solid cell fill must be a six-digit #RRGGBB color.")
    return value.strip().upper()


def _apply_fill(
    text: str,
    event: _StartEvent,
    value: Any,
    matched_styles: Any,
) -> tuple[str, str, str, bool]:
    normalized = _validate_fill(value)
    sources, rules_complete = _source_match_records(matched_styles)
    if not rules_complete:
        raise ValueError("The Preview could not verify all matched CSS rules.")
    relevant = [
        item for item in sources
        if item["scope"] == "element"
        and item["property"] in {"background", "background-color", "background-image", "all"}
        and (item["property"] != "background-image" or item["value"].strip().lower() not in {"", "none"})
    ]
    if any(item["important"] for item in relevant):
        raise ValueError("A matching !important declaration may override a local fill edit.")
    if any("var(" in item["value"].lower() for item in relevant):
        raise ValueError("CSS variables make the selected fill cascade ambiguous.")
    if any(item["property"] in {"background", "background-image", "all"} for item in relevant):
        raise ValueError("A background shorthand or image makes the selected solid fill ambiguous.")
    style_range = event.attr_ranges.get("style")
    if style_range is None:
        opening = text[event.start : event.end]
        insertion_at = opening.rfind("/>")
        if insertion_at < 0:
            insertion_at = opening.rfind(">")
        if insertion_at < 0:
            raise ValueError("The selected cell start tag cannot be patched safely.")
        insertion = f' style="background-color: {normalized}"'
        return text[: event.start + insertion_at] + insertion + text[event.start + insertion_at :], opening, opening + insertion, True

    raw, attr_start, declarations, error = _inline_declarations(text, event)
    if error or raw is None or attr_start is None:
        raise ValueError(error or "Inline style cannot be patched safely.")
    if any(item.name in {"background", "background-image", "all"} for item in declarations):
        raise ValueError("A background shorthand or image makes the selected solid fill ambiguous.")
    direct = [item for item in declarations if item.name == "background-color"]
    if len(direct) > 1:
        raise ValueError("The inline background-color declaration occurs more than once.")
    if direct and direct[0].important:
        raise ValueError("The inline background-color uses !important and is read-only.")
    if direct:
        target = direct[0]
        before = raw[target.value_start : target.value_end]
        after = escape(normalized, quote=True)
        patched = raw[: target.value_start] + after + raw[target.value_end :]
        return text[:attr_start] + patched + text[style_range[1] :], before, after, False
    before = raw
    separator = "" if not raw or raw.rstrip().endswith(";") else ";"
    after = f"{raw}{separator} background-color: {normalized}"
    return text[:attr_start] + after + text[style_range[1] :], before, after, True


def apply_table_patch(
    text: str,
    selection: Mapping[str, Any],
    intent: Any,
    matched_styles: Any,
) -> dict[str, Any]:
    event, repaired = _event_for(text, selection)
    if repaired or event is None or event.tag not in {"td", "th"} or selection.get("status") != "mapped":
        raise ValueError("The selected table cell has no current safe source mapping.")
    mapping_reason = _table_cell_grid_reason(text, selection)
    if mapping_reason:
        raise ValueError(mapping_reason)
    if not isinstance(intent, dict):
        raise ValueError("Table Inspector edit must be one cell text or fill change.")
    if intent.get("kind") == "text":
        if not isinstance(intent.get("value"), str):
            raise ValueError("Table cell text edit must be a string.")
        if not _simple_cell_text(text, event):
            raise ValueError("A single simple table cell text leaf is required.")
        before = text[event.end : event.end_start]
        after = escape(intent["value"], quote=True)
        patched = text[: event.end] + after + text[event.end_start :]
        label = "table cell text"
        local_override = False
    elif intent.get("kind") == "property" and str(intent.get("name", "")).lower() == "background-color":
        patched, before, after, local_override = _apply_fill(text, event, intent.get("value"), matched_styles)
        label = "table cell background-color"
    else:
        raise ValueError("Table Inspector supports cell text and background-color only.")
    diff = "\n".join([f"--- Author HTML ({label})", f"+++ Draft ({label})", *[f"-{line}" for line in before.splitlines() or [""]], *[f"+{line}" for line in after.splitlines() or [""]]])
    return {"text": patched, "property": label, "before": before, "after": after, "diff": diff, "local_override": local_override}


def _chart_events(text: str, selection: Mapping[str, Any]) -> tuple[_StartEvent | None, list[_StartEvent], bool]:
    parser = _SourceParser(text)
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        parser.repaired = True
    parser.finish()
    start, end = selection.get("source_start"), selection.get("source_end")
    chart = next((event for event in parser.events if event.start == start and event.end == end), None)
    if chart is None or "data-pptx-chart" not in chart.attrs:
        return None, [], parser.repaired
    chart_index = parser.events.index(chart)
    specs = [
        event
        for event in parser.events
        if event.tag == "script"
        and "data-pptx-chart-spec" in event.attrs
        and _chart_ancestor(parser.events, event.parent_index) == chart_index
    ]
    return chart, specs, parser.repaired


def _chart_ancestor(events: list[_StartEvent], index: int | None) -> int | None:
    while index is not None:
        if "data-pptx-chart" in events[index].attrs:
            return index
        index = events[index].parent_index
    return None


def _chart_context(text: str, selection: Mapping[str, Any]) -> tuple[dict[str, Any] | None, ChartSpec | None, str | None]:
    chart, specs, repaired = _chart_events(text, selection)
    if repaired or chart is None:
        return None, None, "The selected chart has no current safe source mapping."
    if len(specs) != 1:
        return None, None, "The selected chart must contain exactly one inert ChartSpec."
    spec_node = specs[0]
    if str(spec_node.attrs.get("type") or "").strip().lower() != "application/json" or spec_node.end_start is None:
        return None, None, "The chart spec must be one inert script type=application/json."
    start, end = spec_node.end, spec_node.end_start
    mapped_spec = selection.get("chart_spec")
    if not isinstance(mapped_spec, dict) or mapped_spec.get("spec_start") != start or mapped_spec.get("spec_end") != end:
        return None, None, "ChartSpec source range changed; refresh Preview before editing."
    root: dict[str, Any]
    try:
        spec = parse_chart_spec(text[start:end], source_object="selected chart")
        root = json.loads(text[start:end])
    except (ChartSpecError, json.JSONDecodeError) as exc:
        return None, None, str(exc)
    return root, spec, None


def _chart_field(
    computed: Any,
    source: Any,
    origin: str,
    intent: dict[str, Any] | None,
    *,
    editable: bool = True,
    reason: str | None = None,
    allowed_values: list[str] | None = None,
    input_type: str = "text",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "computed": computed,
        "source": f"{origin}: {source}" if source is not None else f"{origin}: (not authored)",
        "origin": origin,
        "editable": editable,
        "reason": reason,
        "input_type": input_type,
    }
    if intent is not None:
        result["intent"] = intent
    if allowed_values is not None:
        result["allowed_values"] = allowed_values
    return result


def inspect_chart_selection(
    text: str,
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    root, spec, reason = _chart_context(text, selection)
    if reason or root is None or spec is None:
        return {"writable": False, "read_only_reason": reason or "ChartSpec is unavailable.", "chart": None, "fields": {}}
    presentation = root.get("presentation", {})
    fields: dict[str, Any] = {
        "title": _chart_field(spec.title, presentation.get("title"), "ChartSpec.presentation.title", {"kind": "chart", "field": "title"}),
        "legend": _chart_field(spec.legend, presentation.get("legend", "none"), "ChartSpec.presentation.legend", {"kind": "chart", "field": "legend"}, allowed_values=sorted(_LEGEND_POSITIONS)),
        "labels": _chart_field(spec.data_labels, presentation.get("labels", "none"), "ChartSpec.presentation.labels", {"kind": "chart", "field": "labels"}, allowed_values=sorted(_LABEL_MODES if spec.chart_type in {"pie", "doughnut"} else {"none", "value"})),
    }
    for category_index, category in enumerate(spec.categories):
        fields[f"category[{category_index + 1}]"] = _chart_field(
            category,
            root["categories"][category_index],
            f"ChartSpec.categories[{category_index + 1}]",
            {"kind": "chart", "field": "category", "index": category_index},
        )
    raw_series = root["series"]
    for series_index, series in enumerate(spec.series):
        raw = raw_series[series_index]
        fields[f"series[{series_index + 1}].name"] = _chart_field(
            series.name,
            raw.get("name"),
            f"ChartSpec.series[{series_index + 1}].name",
            {"kind": "chart", "field": "series_name", "series": series_index},
        )
        fields[f"series[{series_index + 1}].color"] = _chart_field(
            series.color,
            raw.get("color", "auto"),
            f"ChartSpec.series[{series_index + 1}].color",
            {"kind": "chart", "field": "series_color", "series": series_index},
        )
        for category_index, value in enumerate(series.values):
            fields[f"series[{series_index + 1}].value[{category_index + 1}]"] = _chart_field(
                value,
                raw["values"][category_index],
                f"ChartSpec.series[{series_index + 1}].values[{category_index + 1}]",
                {"kind": "chart", "field": "series_value", "series": series_index, "index": category_index},
                input_type="number",
            )
    for field_name, field in fields.items():
        if field.get("intent") is not None:
            field["intent"]["field_key"] = field_name
    chart_semantics = spec.as_dict()
    chart_semantics["series"] = [
        {"name": series.name, "values": list(series.values), "color": series.color}
        for series in spec.series
    ]
    return {
        "writable": True,
        "read_only_reason": None,
        "chart": chart_semantics,
        "fields": fields,
    }


def _chart_edit(root: dict[str, Any], spec: ChartSpec, intent: Mapping[str, Any]) -> None:
    field = intent.get("field")
    if not isinstance(field, str):
        raise ValueError("Chart Inspector field is required.")
    if field == "title":
        presentation = _presentation_for_edit(root)
        value = intent.get("value")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Chart title must be a non-empty string.")
        presentation["title"] = value.strip()
    elif field == "legend":
        presentation = _presentation_for_edit(root)
        value = intent.get("value")
        if value not in _LEGEND_POSITIONS:
            raise ValueError("Legend must be none, top, bottom, left, or right.")
        presentation["legend"] = value
    elif field == "labels":
        presentation = _presentation_for_edit(root)
        value = intent.get("value")
        if value not in _LABEL_MODES:
            raise ValueError("Labels must be none, value, or percent.")
        presentation["labels"] = value
    elif field == "category":
        index, value = intent.get("index"), intent.get("value")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(root["categories"]):
            raise ValueError("Category index is outside the existing category structure.")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Category label must be a non-empty string.")
        root["categories"][index] = value
    elif field in {"series_name", "series_value", "series_color"}:
        series_index = intent.get("series")
        if isinstance(series_index, bool) or not isinstance(series_index, int) or not 0 <= series_index < len(root["series"]):
            raise ValueError("Series index is outside the existing series structure.")
        series = root["series"][series_index]
        value = intent.get("value")
        if field == "series_name":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Series name must be a non-empty string.")
            series["name"] = value
        elif field == "series_color":
            if value == "auto":
                series.pop("color", None)
            else:
                if not isinstance(value, str) or not _SOLID_COLOR.fullmatch(value.strip()):
                    raise ValueError("Series color must be auto or a six-digit #RRGGBB color.")
                series["color"] = value.strip().upper()
        else:
            index = intent.get("index")
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(series["values"]):
                raise ValueError("Value index is outside the existing category structure.")
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError("Chart value must be one finite JSON number.")
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Chart value must be one finite JSON number.") from exc
            if not math.isfinite(number):
                raise ValueError("Chart value must be one finite JSON number.")
            series["values"][index] = int(number) if number.is_integer() else number
    else:
        raise ValueError("Chart Inspector supports title, categories, series fields, legend, and labels only.")


def _presentation_for_edit(root: dict[str, Any]) -> dict[str, Any]:
    presentation = root.setdefault("presentation", {})
    if not isinstance(presentation, dict):
        raise ValueError("ChartSpec presentation must be an object.")
    return presentation


def apply_chart_patch(text: str, selection: Mapping[str, Any], intent: Any) -> dict[str, Any]:
    root, spec, reason = _chart_context(text, selection)
    if reason or root is None or spec is None:
        raise ValueError(reason or "ChartSpec is unavailable.")
    if not isinstance(intent, dict):
        raise ValueError("Chart Inspector edit must be one ChartSpec field intent.")
    original_type = spec.chart_type
    original_category_count = len(spec.categories)
    original_series_count = len(spec.series)
    _chart_edit(root, spec, intent)
    after_json = json.dumps(root, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    validated = parse_chart_spec(after_json, source_object="selected chart")
    if (
        validated.chart_type != original_type
        or len(validated.categories) != original_category_count
        or len(validated.series) != original_series_count
    ):
        raise ValueError("Chart Inspector cannot change chart type or category/series structure.")
    spec_info = selection["chart_spec"]
    start, end = int(spec_info["spec_start"]), int(spec_info["spec_end"])
    before = text[start:end]
    patched = text[:start] + after_json + text[end:]
    field = str(intent.get("field"))
    diff = "\n".join([f"--- Author HTML (ChartSpec {field})", f"+++ Draft (ChartSpec {field})", f"-{before}", f"+{after_json}"])
    return {
        "text": patched,
        "property": f"ChartSpec {field}",
        "before": before,
        "after": after_json,
        "diff": diff,
        "local_override": False,
    }


__all__ = [
    "apply_chart_patch",
    "apply_table_patch",
    "inspect_chart_selection",
    "inspect_table_selection",
]
