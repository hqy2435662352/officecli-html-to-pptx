"""Safe Shape and Picture Inspector patches for the Author Workbench."""

from __future__ import annotations

import base64
import binascii
from html import escape, unescape
from io import BytesIO
import re
import warnings
from typing import Any, Mapping
from urllib.parse import unquote_to_bytes
from xml.etree import ElementTree

from PIL import Image

from .contract import CSS_PROPERTY_CLASSIFICATIONS, SHAPE_GEOMETRY_TOKEN_SET, SHAPE_GEOMETRY_TOKENS
from .workbench_inspector import _event_for, _inline_declarations, _source_match_records


_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_DATA_URI_RE = re.compile(r"^data:(?P<mime>[^;,]+)(?P<meta>(?:;[^,]*)*),(?P<payload>.*)$", re.DOTALL)
_ALPHA = r"(?:0|1(?:\.0+)?|0?\.\d+)"
_COLOR_RE = re.compile(
    r"(?:#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})|"
    r"rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)|"
    rf"rgba\(\s*\d{{1,3}}\s*,\s*\d{{1,3}}\s*,\s*\d{{1,3}}\s*,\s*{_ALPHA}\s*\))",
    re.IGNORECASE,
)
_RGB_CHANNELS_RE = re.compile(
    rf"rgba?\(\s*(\d{{1,3}})\s*,\s*(\d{{1,3}})\s*,\s*(\d{{1,3}})(?:\s*,\s*{_ALPHA})?\s*\)",
    re.IGNORECASE,
)
_RELATED_PROPERTIES = {
    "background-color": frozenset({"background-color", "background"}),
    "border-color": frozenset(
        {
            "border", "border-color", "border-top", "border-right", "border-bottom", "border-left",
            "border-top-color", "border-right-color", "border-bottom-color", "border-left-color",
        }
    ),
    "border-width": frozenset(
        {
            "border", "border-width", "border-top", "border-right", "border-bottom", "border-left",
            "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
        }
    ),
    "border-radius": frozenset({"border-radius"}),
    "opacity": frozenset({"opacity"}),
    "object-fit": frozenset({"object-fit"}),
}


def _readable_image_source(value: Any) -> str:
    if not isinstance(value, str):
        return "No source attribute"
    match = _DATA_URI_RE.fullmatch(value)
    if match is None:
        return "Non-data or malformed image source"
    return f"{match.group('mime').lower()} data URI ({len(value)} characters)"


def _decode_import(value: Any) -> tuple[str, bytes]:
    if not isinstance(value, str):
        raise ValueError("Picture replacement must be a data:image URI.")
    match = _DATA_URI_RE.fullmatch(value)
    if match is None:
        raise ValueError("Picture replacement must be a well-formed data:image URI.")
    mime = match.group("mime").strip().lower()
    if not mime.startswith("image/"):
        raise ValueError("Picture replacement MIME must be image/*.")
    payload = match.group("payload")
    is_base64 = any(part.lower() == "base64" for part in match.group("meta").split(";") if part)
    if is_base64 and len(payload) > 4 * ((_MAX_IMAGE_BYTES + 2) // 3) + 4:
        raise ValueError("Picture replacement exceeds the 10 MiB decoded import limit.")
    try:
        if is_base64:
            data = base64.b64decode(payload.encode("ascii"), validate=True)
        else:
            data = unquote_to_bytes(payload)
    except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
        raise ValueError(f"Picture replacement payload is malformed: {exc}.") from exc
    if not data:
        raise ValueError("Picture replacement payload is empty.")
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError("Picture replacement exceeds the 10 MiB decoded import limit.")

    if mime == "image/svg+xml":
        try:
            root = ElementTree.fromstring(data)
        except Exception as exc:
            raise ValueError(f"Picture replacement is not valid SVG: {exc}.") from exc
        if root.tag.rsplit("}", 1)[-1].lower() != "svg":
            raise ValueError("Picture replacement MIME/content mismatch: expected an SVG image.")
    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    actual_mime = Image.MIME.get(image.format or "")
                    if actual_mime != mime:
                        raise ValueError(
                            f"Picture replacement MIME/content mismatch: declared {mime}, actual {actual_mime or 'unknown image format'}."
                        )
                    if image.width <= 0 or image.height <= 0:
                        raise ValueError("Picture replacement has invalid intrinsic dimensions.")
                    image.verify()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Picture replacement is not a supported image: {exc}.") from exc
    return mime, data


def _style_values(computed: Any) -> dict[str, Any]:
    if not isinstance(computed, dict) or not isinstance(computed.get("styles"), dict):
        return {}
    return computed["styles"]


def _simple_shape_text(text: str, event: Any) -> bool:
    return (
        event.end_start is not None
        and not event.self_closing
        and not event.has_element_child
        and not event.has_comment
        and "<" not in text[event.end : event.end_start]
    )


def _border_is_uniform(styles: Mapping[str, Any]) -> bool:
    colors = [styles.get(f"border-{side}-color") for side in ("top", "right", "bottom", "left")]
    widths = [styles.get(f"border-{side}-width") for side in ("top", "right", "bottom", "left")]
    borders = [styles.get(f"border-{side}-style") for side in ("top", "right", "bottom", "left")]
    return (
        all(isinstance(value, str) and value for value in (*colors, *widths, *borders))
        and len(set(colors)) == 1
        and len(set(widths)) == 1
        and set(borders) == {"solid"}
    )


def _shape_geometry_reason(
    event: Any,
    declarations: list[Any],
    style_error: str | None,
    sources: list[dict[str, Any]],
    rules_complete: bool,
) -> str | None:
    if "data-pptx-shape-geometry" not in event.attr_ranges:
        return "The supported native geometry attribute is missing or ambiguous."
    if not rules_complete:
        return "The Preview could not verify CSS rules needed to render the selected geometry."
    if style_error:
        return style_error
    inline_radius = [item for item in declarations if item.name == "border-radius"]
    matched_radius = [item for item in sources if item["property"] == "border-radius"]
    if len(inline_radius) > 1:
        return "The inline border-radius declaration occurs more than once."
    if any(item.important for item in inline_radius) or any(
        item["scope"] == "element" and item["important"] for item in matched_radius
    ):
        return "A matching !important border-radius prevents a safe geometry Preview."
    if any("var(" in item.value.lower() for item in inline_radius) or any(
        "var(" in item["value"].lower() for item in matched_radius
    ):
        return "CSS variables cannot be verified for this geometry Preview."
    return None


def _format_computed_value(name: str, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", value, re.IGNORECASE)
    if name in {"background-color", "border-color"} and match:
        channels = [int(part) for part in match.groups()]
        if all(0 <= channel <= 255 for channel in channels):
            return "#" + "".join(f"{channel:02X}" for channel in channels)
    return value


def _css_field(
    name: str,
    styles: Mapping[str, Any],
    declarations: list[Any],
    style_error: str | None,
    sources: list[dict[str, Any]],
    rules_complete: bool,
) -> dict[str, Any]:
    related = _RELATED_PROPERTIES.get(name, frozenset({name}))
    direct = [item for item in declarations if item.name in related]
    inline_shorthands = [item for item in direct if item.name != name]
    matched = [item for item in sources if item["property"] in related]
    if direct:
        source = " · ".join(f"{item.name}: {item.value}" for item in direct)
        origin = "inline style"
    elif matched:
        source = " · ".join(
            f"{item['selector'] or 'stylesheet rule'}: {item['value']}"
            for item in matched
        )
        origin = "; ".join(dict.fromkeys(item["selector"] or "stylesheet rule" for item in matched))
    else:
        source, origin = None, "browser default"

    reason = None
    if CSS_PROPERTY_CLASSIFICATIONS.get(name) != "rendered":
        reason = "This field is not a rendered Contract 1.3 property."
    elif not rules_complete:
        reason = "The Preview could not verify all matched CSS rules."
    elif style_error:
        reason = style_error
    elif sum(item.name == name for item in declarations) > 1:
        reason = "The inline declaration occurs more than once."
    elif any(
        item.important
        for item in direct
    ) or any(item["scope"] == "element" and item["important"] for item in matched):
        reason = "A matching !important or shorthand declaration may override a local edit."
    elif any("var(" in item.value.lower() for item in direct) or any("var(" in item["value"].lower() for item in matched):
        reason = "CSS variables cannot be verified for this field."
    elif inline_shorthands:
        reason = "An inline shorthand affects this field and cannot be overridden safely."
    elif name == "background-color" and styles.get("background-image") not in {None, "", "none"}:
        reason = "A background image or gradient prevents a trustworthy solid-fill edit."
    elif name in {"border-color", "border-width"} and not _border_is_uniform(styles):
        reason = "Only a uniform solid border can be edited in the Shape Inspector."
    return {
        "computed": styles.get(name),
        "source": source,
        "origin": origin,
        "edit_value": _format_computed_value(name, styles.get(name)),
        "editable": reason is None,
        "reason": reason,
        "local_override": not direct,
    }


def _readonly(reason: str) -> dict[str, Any]:
    return {
        "writable": False,
        "read_only_reason": reason,
        "text": {"source": None, "computed": None, "origin": "unverified", "editable": False, "reason": reason},
        "fields": {},
    }


def inspect_shape_picture_selection(
    text: str,
    selection: Mapping[str, Any],
    computed: Any,
    matched_styles: Any,
) -> dict[str, Any]:
    event, repaired = _event_for(text, selection)
    if repaired or event is None or selection.get("status") != "mapped":
        return _readonly("The selected object has no current, unambiguous source mapping.")

    styles = _style_values(computed)
    sources, rules_complete = _source_match_records(matched_styles)
    _, _, declarations, style_error = _inline_declarations(text, event)
    fields: dict[str, dict[str, Any]] = {}
    shape_text: dict[str, Any] = {"source": None, "computed": None, "origin": "Author HTML text node", "editable": False}
    if selection.get("kind") == "shape":
        attribute = "data-pptx-shape-geometry"
        geometry = event.attrs.get(attribute)
        geometry_reason = _shape_geometry_reason(event, declarations, style_error, sources, rules_complete)
        text_value = unescape(text[event.end : event.end_start]) if _simple_shape_text(text, event) else None
        fields[attribute] = {
            "computed": geometry,
            "source": geometry,
            "origin": f"Author HTML {attribute} attribute",
            "edit_value": geometry if geometry in SHAPE_GEOMETRY_TOKEN_SET else SHAPE_GEOMETRY_TOKENS[0],
            "editable": geometry_reason is None,
            "reason": geometry_reason,
            "local_override": False,
            "control": "select",
            "options": list(SHAPE_GEOMETRY_TOKENS),
            "preview_note": None if geometry in {"rect", "roundRect", "ellipse"} else (
                "This native preset has no CSS silhouette in the Contract 1.3 Preview; "
                "the Preview uses its rectangular source box while Build creates the selected native geometry."
            ),
        }
        for name in ("background-color", "border-color", "border-width", "opacity"):
            fields[name] = _css_field(name, styles, declarations, style_error, sources, rules_complete)
        text_reason = None if text_value is not None else "A single simple text leaf/run is required; mixed or nested shape text is read-only."
        shape_text.update(
            {
                "source": text_value,
                "computed": computed.get("text") if isinstance(computed, dict) else text_value,
                "editable": text_value is not None,
                "reason": text_reason,
            }
        )
    elif selection.get("kind") == "picture":
        if event.tag != "img":
            return _readonly("Only a standalone <img> with one source can be edited; <picture> and SVG source trees are read-only.")
        source = event.attrs.get("src")
        source_field = {
            "computed": "current Preview image",
            "source": _readable_image_source(source),
            "origin": "Author HTML <img src> attribute",
            "editable": "srcset" not in event.attrs,
            "reason": "Responsive srcset selection is not source-local and is read-only." if "srcset" in event.attrs else None,
            "local_override": False,
            "control": "image-file",
        }
        fields["src"] = source_field
        fit_field = _css_field("object-fit", styles, declarations, style_error, sources, rules_complete)
        fit_field.update({"control": "select", "options": ["fill", "contain", "cover"]})
        fit_field["edit_value"] = styles.get("object-fit") or "fill"
        fields["object-fit"] = fit_field
    else:
        return _readonly("This object kind is not editable by the Shape/Picture Inspector.")

    return {
        "writable": any(field.get("editable") for field in fields.values()) or shape_text["editable"],
        "read_only_reason": None,
        "text": shape_text,
        "fields": fields,
        "classes": str(event.attrs.get("class") or "").split(),
        "id": event.attrs.get("id"),
    }


def _validate_css_value(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a non-empty value.")
    normalized = value.strip()
    if len(normalized) > 200 or any(char in normalized for char in "\r\n\0;{}<>") or "!important" in normalized.lower() or "var(" in normalized.lower():
        raise ValueError("The value must be one simple Contract 1.3 CSS value.")
    lowered = normalized.lower()
    if name in {"background-color", "border-color"}:
        if _COLOR_RE.fullmatch(normalized) is None:
            raise ValueError(f"{name} must be a simple hex, rgb(), or rgba() color.")
        channels = _RGB_CHANNELS_RE.fullmatch(normalized)
        if channels and any(int(channel) > 255 for channel in channels.groups()[:3]):
            raise ValueError(f"{name} RGB channels must be between 0 and 255.")
    elif name == "border-width":
        match = re.fullmatch(r"(?:0(?:\.0+)?|(?:\d+(?:\.\d+)?|\.\d+)(?:px|pt))", lowered)
        if match is None:
            raise ValueError("border-width must be 0 or a non-negative px/pt value.")
    elif name == "border-radius":
        if re.fullmatch(r"(?:0(?:\.0+)?|(?:\d+(?:\.\d+)?|\.\d+)(?:px|pt)|50%)", lowered) is None:
            raise ValueError("Geometry border-radius must be 0, 50%, or a non-negative px/pt value.")
    elif name == "opacity":
        if re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)", lowered) is None:
            raise ValueError("opacity must be a number from 0 to 1.")
        amount = float(lowered)
        if not 0 <= amount <= 1:
            raise ValueError("opacity must be a number from 0 to 1.")
    elif name == "object-fit":
        if lowered not in {"fill", "contain", "cover"}:
            raise ValueError("object-fit must be fill, contain, or cover.")
    else:
        raise ValueError("This property is outside the Shape/Picture Inspector surface.")
    if CSS_PROPERTY_CLASSIFICATIONS.get(name) != "rendered":
        raise ValueError("This property is not a rendered Contract 1.3 property.")
    return normalized


def _patch_attribute(text: str, event: Any, name: str, value: str) -> tuple[str, str, str]:
    value_range = event.attr_ranges.get(name)
    if value_range is not None:
        before = text[value_range[0] : value_range[1]]
        after = escape(value, quote=True)
        return text[: value_range[0]] + after + text[value_range[1] :], before, after
    opening = text[event.start : event.end]
    closing = "/>" if opening.rstrip().endswith("/>") else ">"
    index = opening.rfind(closing)
    if index < 0:
        raise ValueError("The selected start tag cannot be patched safely.")
    after = f'{opening[:index]} {name}="{escape(value, quote=True)}"{opening[index:]}'
    return text[: event.start] + after + text[event.end :], opening, after


def _patch_inline_css(
    text: str,
    event: Any,
    name: str,
    value: Any,
    matched_styles: Any,
) -> tuple[str, str, str, bool]:
    normalized = _validate_css_value(name, value)
    sources, rules_complete = _source_match_records(matched_styles)
    if not rules_complete:
        raise ValueError("The Preview could not verify all matched CSS rules.")
    related = _RELATED_PROPERTIES.get(name, frozenset({name}))
    if any(item["scope"] == "element" and item["property"] in related and item["important"] for item in sources):
        raise ValueError("A matching !important or shorthand declaration may override a local edit.")
    if any(item["property"] in related and "var(" in item["value"].lower() for item in sources):
        raise ValueError("CSS variable precedence cannot be verified for this field.")

    style_range = event.attr_ranges.get("style")
    if style_range is None:
        opening = text[event.start : event.end]
        closing = "/>" if opening.rstrip().endswith("/>") else ">"
        index = opening.rfind(closing)
        if index < 0:
            raise ValueError("The selected start tag cannot be patched safely.")
        insertion = f' style="{name}: {escape(normalized, quote=True)}"'
        after = opening[:index] + insertion + opening[index:]
        return text[: event.start] + after + text[event.end :], opening, after, True

    raw, attr_start, declarations, error = _inline_declarations(text, event)
    if error or raw is None or attr_start is None:
        raise ValueError(error or "Inline style cannot be patched safely.")
    matching = [item for item in declarations if item.name == name]
    if len(matching) > 1:
        raise ValueError("The inline declaration occurs more than once.")
    if any(item.important for item in declarations if item.name in related):
        raise ValueError("A matching inline !important or shorthand declaration is read-only.")
    if any("var(" in item.value.lower() for item in declarations if item.name in related):
        raise ValueError("CSS variable precedence cannot be verified for this field.")
    if matching:
        item = matching[0]
        before = raw[item.value_start : item.value_end]
        after = escape(normalized, quote=True)
        patched_style = raw[: item.value_start] + after + raw[item.value_end :]
        local_override = False
    else:
        before = raw
        separator = "" if not raw or raw.rstrip().endswith(";") else ";"
        after = f"{raw}{separator} {name}: {escape(normalized, quote=True)}"
        patched_style = after
        local_override = True
    return text[:attr_start] + patched_style + text[style_range[1] :], before, after, local_override


def _patch_text(text: str, event: Any, value: Any) -> tuple[str, str, str]:
    if not isinstance(value, str) or not _simple_shape_text(text, event):
        raise ValueError("A single simple shape text leaf/run is required.")
    before = text[event.end : event.end_start]
    after = escape(value, quote=True)
    return text[: event.end] + after + text[event.end_start :], before, after


def _round_rect_radius(computed: Any) -> str:
    styles = _style_values(computed)
    dimensions = []
    for name in ("width", "height"):
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)px", str(styles.get(name, "")))
        if match is None:
            return "8px"
        dimensions.append(float(match.group(1)))
    radius = min(dimensions) * 0.16667
    return f"{radius:.4f}".rstrip("0").rstrip(".") + "px"


def _patch_shape_geometry(
    text: str,
    event: Any,
    selection: Mapping[str, Any],
    value: str,
    computed: Any,
    matched_styles: Any,
) -> tuple[str, str, str, bool]:
    current_geometry = event.attrs.get("data-pptx-shape-geometry")
    before = text[event.start : event.end]
    patched, _, _ = _patch_attribute(text, event, "data-pptx-shape-geometry", value)
    updated_selection = dict(selection)
    updated_selection["source_end"] = event.end + len(patched) - len(text)
    patched_event, repaired = _event_for(patched, updated_selection)
    if repaired or patched_event is None:
        raise ValueError("The selected Shape could not be remapped after the geometry patch.")

    if value == "ellipse":
        radius = "50%"
    elif value == "roundRect":
        current_radius = str(_style_values(computed).get("border-radius") or "")
        radius = (
            current_radius
            if current_geometry == "roundRect" and not re.fullmatch(r"0(?:\.0+)?(?:px|pt)?", current_radius)
            else _round_rect_radius(computed)
        )
    else:
        radius = "0"
    patched, _, _, local_override = _patch_inline_css(
        patched,
        patched_event,
        "border-radius",
        radius,
        matched_styles,
    )
    updated_selection["source_end"] += len(patched) - len(text) - (
        updated_selection["source_end"] - event.end
    )
    final_event, repaired = _event_for(patched, updated_selection)
    if repaired or final_event is None:
        raise ValueError("The selected Shape could not be remapped after its local Preview style patch.")
    return patched, before, patched[final_event.start : final_event.end], local_override


def apply_shape_picture_patch(
    text: str,
    selection: Mapping[str, Any],
    intent: Any,
    computed: Any,
    matched_styles: Any,
) -> dict[str, Any]:
    event, repaired = _event_for(text, selection)
    if repaired or event is None or selection.get("status") != "mapped":
        raise ValueError("The selected Preview object has no current safe source mapping.")
    if not isinstance(intent, dict):
        raise ValueError("Inspector edit must be one text or property intent.")
    inspected = inspect_shape_picture_selection(text, selection, computed, matched_styles)
    if intent.get("kind") == "text" and selection.get("kind") == "shape":
        if not inspected.get("text", {}).get("editable"):
            raise ValueError(inspected.get("text", {}).get("reason") or "Shape text is read-only.")
        patched, before, after = _patch_text(text, event, intent.get("value"))
        label, local_override = "shape text", False
    elif intent.get("kind") == "property":
        name = intent.get("name")
        if not isinstance(name, str):
            raise ValueError("Inspector property name is required.")
        name = name.lower()
        field = inspected.get("fields", {}).get(name, {})
        if not field.get("editable"):
            raise ValueError(field.get("reason") or "This field is read-only.")
        if selection.get("kind") == "shape" and name == "data-pptx-shape-geometry":
            normalized = intent.get("value")
            if not isinstance(normalized, str) or normalized not in SHAPE_GEOMETRY_TOKEN_SET:
                raise ValueError("Choose one of the officially supported native geometry tokens.")
            patched, before, after, local_override = _patch_shape_geometry(
                text, event, selection, normalized, computed, matched_styles
            )
        elif selection.get("kind") == "picture" and name == "src":
            _decode_import(intent.get("value"))
            patched, before, after = _patch_attribute(text, event, "src", intent["value"])
            local_override = False
        else:
            if selection.get("kind") == "picture" and event.tag != "img":
                raise ValueError("Only a standalone <img> can be edited by the Picture Inspector.")
            patched, before, after, local_override = _patch_inline_css(
                text, event, name, intent.get("value"), matched_styles
            )
        label = name
    else:
        raise ValueError("Inspector edit kind must be 'text' or 'property'.")

    diff = "\n".join(
        [
            f"--- Author HTML ({label})",
            f"+++ Draft ({label})",
            *[f"-{line}" for line in before.splitlines() or [""]],
            *[f"+{line}" for line in after.splitlines() or [""]],
        ]
    )
    return {
        "text": patched,
        "diff": diff,
        "before": before,
        "after": after,
        "local_override": local_override,
        "property": label,
    }


__all__ = ["apply_shape_picture_patch", "inspect_shape_picture_selection"]
