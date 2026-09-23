"""Safe text Inspector operations over the current Author HTML source."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape, unescape
import re
from typing import Any, Mapping

from .contract import CSS_PROPERTY_CLASSIFICATIONS, SUPPORTED_INLINE_ELEMENTS, TEXT_ALIGNMENT_VALUES
from .workbench_preview import _SourceParser, _kind_for


_TEXT_PROPERTIES = (
    "font-family",
    "font-size",
    "color",
    "font-weight",
    "font-style",
    "text-align",
)
_ALLOWED_PROPERTIES = frozenset(
    name for name in _TEXT_PROPERTIES if CSS_PROPERTY_CLASSIFICATIONS.get(name) == "rendered"
)
_TEXT_ALIGN_DISPLAYS = frozenset({"block", "flow-root", "list-item", "table-cell", "table-caption"})


@dataclass(frozen=True)
class _Declaration:
    name: str
    value: str
    value_start: int
    value_end: int
    important: bool


def _event_for(text: str, selection: Mapping[str, Any]) -> tuple[Any | None, bool]:
    parser = _SourceParser(text)
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        parser.repaired = True
    parser.finish()
    start = selection.get("source_start")
    end = selection.get("source_end")
    event = next(
        (item for item in parser.events if item.start == start and item.end == end),
        None,
    )
    return event, parser.repaired


def _simple_text_leaf(text: str, event: Any) -> bool:
    return (
        _kind_for(event) == "text"
        and not event.has_element_child
        and not event.has_comment
        and event.end_start is not None
        and "<" not in text[event.end : event.end_start]
    )


def _inline_declarations(text: str, event: Any) -> tuple[str | None, int | None, list[_Declaration], str | None]:
    style_range = event.attr_ranges.get("style")
    if style_range is None:
        return None, None, [], None
    raw = text[style_range[0] : style_range[1]]
    if raw != unescape(raw):
        return raw, style_range[0], [], "Style attribute contains entities, so its declaration range cannot be edited safely."

    declarations: list[_Declaration] = []
    start = 0
    quote_char: str | None = None
    escaped = False
    depth = 0
    for index, char in enumerate(raw + ";"):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote_char:
            if char == quote_char:
                quote_char = None
            continue
        if char in {"'", '"'}:
            quote_char = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return raw, style_range[0], [], "The inline style syntax is ambiguous."
        elif char == ";" and depth == 0:
            segment = raw[start:index]
            colon = segment.find(":")
            if segment.strip():
                if colon < 0:
                    return raw, style_range[0], [], "The inline style syntax is ambiguous."
                name = segment[:colon].strip().lower()
                value_source = segment[colon + 1 :]
                leading = len(value_source) - len(value_source.lstrip())
                trailing = len(value_source.rstrip())
                value_start = start + colon + 1 + leading
                value_end = start + colon + 1 + trailing
                value = raw[value_start:value_end]
                important_match = re.search(r"\s*!\s*important\s*$", value, re.IGNORECASE)
                important = important_match is not None
                if important_match:
                    value = value[: important_match.start()].rstrip()
                    value_end = value_start + len(value)
                declarations.append(_Declaration(name, value, value_start, value_end, important))
            start = index + 1
    if quote_char or depth:
        return raw, style_range[0], [], "The inline style syntax is ambiguous."
    return raw, style_range[0], declarations, None


def _property_value(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, "Enter a non-empty value."
    normalized = value.strip()
    if len(normalized) > 200 or any(character in normalized for character in "\r\n\0;{}<>"):
        return None, "The value contains characters that cannot be written as one CSS value."
    if "!important" in normalized.lower() or "var(" in normalized.lower():
        return None, "Priority declarations and CSS variables are read-only in this Inspector."
    if normalized.startswith("--"):
        return None, "Custom CSS properties are outside Contract 1.3 text editing."
    return normalized, None


def _validate_property_value(name: str, value: Any) -> str:
    normalized, error = _property_value(value)
    if error or normalized is None:
        raise ValueError(error or "Invalid property value.")
    if name not in _ALLOWED_PROPERTIES:
        raise ValueError("This property is outside the Contract 1.3 text Inspector surface.")
    lowered = normalized.lower()
    family = r"(?:[A-Za-z0-9_\u0080-\uffff-]+|\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')"
    if name == "font-family" and not re.fullmatch(rf"\s*{family}(?:\s*,\s*{family})*\s*", normalized):
        raise ValueError("font-family must contain simple family names and optional fallbacks.")
    size = re.fullmatch(r"(\d+(?:\.\d+)?|\.\d+)(?:px|pt)", lowered)
    if name == "font-size" and (size is None or float(size.group(1)) <= 0):
        raise ValueError("font-size must be a positive px or pt value.")
    if name == "color" and not re.fullmatch(r"#[0-9a-f]{3}(?:[0-9a-f]{3})?", lowered):
        raise ValueError("color must be a #RGB or #RRGGBB value.")
    if name == "font-weight" and lowered not in {"normal", "bold", *(str(value) for value in range(100, 1000, 100))}:
        raise ValueError("font-weight must be normal, bold, or a numeric weight from 100 to 900.")
    if name == "font-style" and lowered not in {"normal", "italic"}:
        raise ValueError("font-style must be normal or italic.")
    if name == "text-align" and lowered not in {*TEXT_ALIGNMENT_VALUES, "start", "end"}:
        raise ValueError("text-align must be left, center, right, justify, start, or end.")
    return normalized


def _source_match_records(value: Any) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(value, dict):
        return [], False
    complete = value.get("rules_complete") is True
    raw_sources = value.get("sources")
    if not isinstance(raw_sources, list) or len(raw_sources) > 200:
        return [], False
    sources: list[dict[str, Any]] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            return [], False
        name, raw_value = item.get("property"), item.get("value")
        if not isinstance(name, str) or not isinstance(raw_value, str) or len(raw_value) > 2000:
            return [], False
        scope = item.get("scope")
        if scope not in {"element", "ancestor"}:
            return [], False
        sources.append(
            {
                "property": name.lower(),
                "value": raw_value,
                "important": item.get("important") is True,
                "selector": str(item.get("selector", ""))[:300],
                "scope": scope,
            }
        )
    return sources, complete


def inspect_text_selection(
    text: str,
    selection: Mapping[str, Any],
    computed: Any,
    matched_styles: Any,
) -> dict[str, Any]:
    event, repaired = _event_for(text, selection)
    if event is None or repaired or selection.get("status") != "mapped":
        reason = "parser_repaired_candidate" if repaired else "source_mapping_unavailable"
        return {
            "writable": False,
            "read_only_reason": reason,
            "text": {"source": selection.get("text_value"), "computed": None, "origin": "unverified", "editable": False, "reason": reason},
            "fields": {},
        }

    leaf = _simple_text_leaf(text, event)
    source_text = unescape(text[event.end : event.end_start]) if leaf else None
    direct_text = computed.get("text") if isinstance(computed, dict) and isinstance(computed.get("text"), str) else None
    computed_values = computed.get("styles") if isinstance(computed, dict) and isinstance(computed.get("styles"), dict) else {}
    sources, rules_complete = _source_match_records(matched_styles)
    _, _, declarations, style_error = _inline_declarations(text, event)
    by_name: dict[str, list[_Declaration]] = {}
    for declaration in declarations:
        by_name.setdefault(declaration.name, []).append(declaration)

    fields: dict[str, dict[str, Any]] = {}
    for name in _TEXT_PROPERTIES:
        direct = by_name.get(name, [])
        inline_source = direct[0].value if len(direct) == 1 else None
        candidates = [source for source in sources if source["property"] in {name, "font", "all"}]
        unique_sources: list[str] = []
        for source in candidates:
            descriptor = "inline style" if source["selector"] == "element.style" else source["selector"] or "stylesheet rule"
            if source["scope"] == "ancestor":
                descriptor = f"inherited from {descriptor}"
            value_text = f"{descriptor}: {source['value']}"
            if value_text not in unique_sources:
                unique_sources.append(value_text)
        if inline_source is not None:
            origin = "inline style"
            source_value = inline_source
        elif unique_sources:
            origin = "; ".join(unique_sources)
            source_value = " · ".join(unique_sources)
        else:
            origin = "browser default or inherited value"
            source_value = None

        reason = None
        if not leaf:
            reason = "A single simple text leaf/run is required."
        elif CSS_PROPERTY_CLASSIFICATIONS.get(name) != "rendered":
            reason = "This field is not a rendered Contract 1.3 property."
        elif name == "text-align" and computed_values.get("display") not in _TEXT_ALIGN_DISPLAYS:
            reason = "text-align is writable only on a verified block or table-cell text container."
        elif not rules_complete:
            reason = "The Preview could not verify all matched CSS rules."
        elif style_error:
            reason = style_error
        elif len(direct) > 1:
            reason = "The inline declaration occurs more than once."
        elif any(
            item["important"]
            for item in sources
            if item["scope"] == "element"
            and item["property"] in {name, "font", "all"}
        ) or any(item.important for item in direct):
            reason = "A matching !important declaration may override a local edit."
        elif any(
            "var(" in item["value"].lower()
            for item in sources
            if item["property"] in {name, "font", "all"}
        ) or any("var(" in item.value.lower() for item in direct):
            reason = "CSS variable cascade cannot be verified for this field."

        fields[name] = {
            "computed": computed_values.get(name),
            "source": source_value,
            "origin": origin,
            "editable": reason is None,
            "reason": reason,
            "local_override": inline_source is None,
        }

    text_reason = None if leaf else str(selection.get("text_reason") or "A single simple text leaf/run is required.")
    return {
        "writable": leaf,
        "read_only_reason": None if leaf else text_reason,
        "text": {
            "source": source_text,
            "computed": direct_text if direct_text is not None else source_text,
            "origin": "Author HTML text node",
            "editable": leaf,
            "reason": text_reason,
        },
        "fields": fields,
        "classes": str(event.attrs.get("class") or "").split(),
        "id": event.attrs.get("id"),
    }


def _patch_leaf_text(text: str, event: Any, value: Any) -> tuple[str, str, str]:
    if not isinstance(value, str):
        raise ValueError("Text edit must be a string.")
    if not _simple_text_leaf(text, event):
        raise ValueError("A single simple text leaf/run is required.")
    before = text[event.end : event.end_start]
    if "<" in before:
        raise ValueError("The text leaf contains markup that cannot be patched safely.")
    after = escape(value, quote=True)
    return text[: event.end] + after + text[event.end_start :], before, after


def _patch_inline_property(text: str, event: Any, name: str, value: Any, sources: list[dict[str, Any]], rules_complete: bool) -> tuple[str, str, str, bool]:
    normalized = _validate_property_value(name, value)
    if not rules_complete:
        raise ValueError("The Preview could not verify all matched CSS rules.")
    if any(
        source["scope"] == "element"
        and source["property"] in {name, "font", "all"}
        and source["important"]
        for source in sources
    ):
        raise ValueError("A matching !important declaration may override a local edit.")
    if any(
        source["property"] in {name, "font", "all"}
        and "var(" in source["value"].lower()
        for source in sources
    ):
        raise ValueError("CSS variable cascade cannot be verified for this field.")

    style_range = event.attr_ranges.get("style")
    if style_range is None:
        opening = text[event.start : event.end]
        closing_index = opening.rfind("/>")
        if closing_index < 0:
            closing_index = opening.rfind(">")
        if closing_index < 0:
            raise ValueError("The selected start tag cannot be patched safely.")
        insertion = f' style="{name}: {escape(normalized, quote=True)}"'
        new_text = text[: event.start + closing_index] + insertion + text[event.start + closing_index :]
        return new_text, opening, text[event.start : event.end + len(insertion)], True

    raw, attr_start, declarations, error = _inline_declarations(text, event)
    if error or raw is None or attr_start is None:
        raise ValueError(error or "Inline style cannot be patched safely.")
    matching = [item for item in declarations if item.name == name]
    if len(matching) > 1:
        raise ValueError("The inline declaration occurs more than once.")
    if matching and matching[0].important:
        raise ValueError("The inline declaration uses !important and is read-only.")
    if any(
        item.important and item.name in {"font", "all"}
        for item in declarations
    ):
        raise ValueError("An inline !important shorthand may override a local edit.")
    if any(
        "var(" in item.value.lower() and item.name in {name, "font", "all"}
        for item in declarations
    ):
        raise ValueError("CSS variable cascade cannot be verified for this field.")

    if matching:
        declaration = matching[0]
        before = raw[declaration.value_start : declaration.value_end]
        after = escape(normalized, quote=True)
        patched_style = raw[: declaration.value_start] + after + raw[declaration.value_end :]
        local_override = False
    else:
        before = raw
        separator = "" if not raw or raw.rstrip().endswith(";") else ";"
        after = f"{raw}{separator} {name}: {escape(normalized, quote=True)}"
        patched_style = after
        local_override = True
    new_text = text[:attr_start] + patched_style + text[style_range[1] :]
    return new_text, before, after, local_override


def apply_text_patch(
    text: str,
    selection: Mapping[str, Any],
    intent: Any,
    matched_styles: Any,
) -> dict[str, Any]:
    event, repaired = _event_for(text, selection)
    if repaired or event is None or selection.get("status") != "mapped":
        raise ValueError("The selected Preview object has no current safe text source mapping.")
    if not _simple_text_leaf(text, event):
        raise ValueError("A single simple text leaf/run is required.")
    if not isinstance(intent, dict):
        raise ValueError("Inspector edit must be one text or property intent.")

    if intent.get("kind") == "text":
        patched, before, after = _patch_leaf_text(text, event, intent.get("value"))
        label = "text node"
        local_override = False
    elif intent.get("kind") == "property":
        name = intent.get("name")
        if not isinstance(name, str):
            raise ValueError("Inspector property name is required.")
        sources, rules_complete = _source_match_records(matched_styles)
        patched, before, after, local_override = _patch_inline_property(
            text, event, name.lower(), intent.get("value"), sources, rules_complete
        )
        label = name.lower()
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


__all__ = ["apply_text_patch", "inspect_text_selection"]
