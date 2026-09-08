"""The versioned, profile-aware OfficeHTML contract checker.

The checker is intentionally small and dependency-light: the contract is a
runtime boundary for visible HTML, not a second browser layout engine.  The
compiler remains the authority for final geometry and OfficeCLI capabilities;
this module catches content that would otherwise disappear before compilation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from lxml import html as _lxml_html

CONTRACT_VERSION = "1.0"
OFFICECLI_COMPATIBILITY_BASELINE = "1.0.147"
SUPPORTED_PROFILES = ("author", "officehtml")
SUPPORTED_OBJECT_KINDS = frozenset({"shape", "textbox", "picture", "table"})
CSS_CLASSIFICATIONS = (
    "measurement-only",
    "rendered",
    "preview-only",
    "unsupported",
)

_RENDERED_CSS_PROPERTIES = frozenset(
    {
        "background",
        "background-color",
        "border",
        "border-bottom",
        "border-color",
        "border-left",
        "border-radius",
        "border-right",
        "border-style",
        "border-top",
        "border-width",
        "border-collapse",
        "color",
        "font",
        "font-family",
        "font-size",
        "font-style",
        "font-weight",
        "line-height",
        "margin",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "margin-top",
        "object-fit",
        "opacity",
        "padding",
        "padding-bottom",
        "padding-left",
        "padding-right",
        "padding-top",
        "text-align",
        "text-decoration",
        "text-transform",
        "transform",
        "vertical-align",
    }
)
_MEASUREMENT_ONLY_CSS_PROPERTIES = frozenset(
    {
        "align-content",
        "align-items",
        "align-self",
        "bottom",
        "box-sizing",
        "column-gap",
        "display",
        "flex",
        "flex-direction",
        "flex-flow",
        "flex-wrap",
        "gap",
        "grid",
        "grid-area",
        "grid-column",
        "grid-row",
        "grid-template",
        "grid-template-columns",
        "grid-template-rows",
        "height",
        "justify-content",
        "justify-items",
        "justify-self",
        "left",
        "letter-spacing",
        "max-height",
        "max-width",
        "min-height",
        "min-width",
        "overflow",
        "overflow-wrap",
        "position",
        "right",
        "row-gap",
        "table-layout",
        "top",
        "white-space",
        "width",
        "word-break",
        "writing-mode",
        "z-index",
    }
)
_PREVIEW_ONLY_CSS_PROPERTIES = frozenset(
    {
        "cursor",
        "pointer-events",
        "scroll-behavior",
        "user-select",
    }
)
_UNSUPPORTED_CSS_PROPERTIES = frozenset(
    {
        "animation",
        "animation-delay",
        "animation-duration",
        "animation-name",
        "background-attachment",
        "background-blend-mode",
        "background-image",
        "box-shadow",
        "clip-path",
        "filter",
        "mix-blend-mode",
        "text-shadow",
        "transition",
        "transition-delay",
        "transition-duration",
        "transition-property",
        "transition-timing-function",
        "-webkit-background-clip",
        "-webkit-text-fill-color",
        "-webkit-text-stroke",
    }
)
CSS_PROPERTY_CLASSIFICATIONS = {
    **{name: "rendered" for name in _RENDERED_CSS_PROPERTIES},
    **{name: "measurement-only" for name in _MEASUREMENT_ONLY_CSS_PROPERTIES},
    **{name: "preview-only" for name in _PREVIEW_ONLY_CSS_PROPERTIES},
    **{name: "unsupported" for name in _UNSUPPORTED_CSS_PROPERTIES},
}
SUPPORTED_CSS_PROPERTIES = frozenset(CSS_PROPERTY_CLASSIFICATIONS)

_CSS_BLOCK_RE = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", re.DOTALL)
_CSS_DECL_RE = re.compile(r"(?P<name>[a-zA-Z-]+)\s*:\s*(?P<value>[^;]+)")
_LENGTH_RE = re.compile(r"^\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*(?P<unit>px|pt|cm|mm|in|emu)?\s*$", re.I)
_OWNED_PATH_RE = re.compile(r"/slide\[(?P<slide>\d+)\]/(?P<kind>[a-z]+)\[", re.I)
_EXTERNAL_URL_RE = re.compile(r"(?:https?:|//|file:)", re.I)
_IMPORT_RE = re.compile(r"@import\b", re.I)

_AUTHOR_IGNORED_TAGS = frozenset(
    {"html", "head", "body", "script", "style", "link", "meta", "title", "base"}
)
_AUTHOR_PREVIEW_TOKENS = frozenset(
    {
        "preview-only",
        "viewer-chrome",
        "toolbar",
        "sidebar",
        "thumbnails",
        "thumbnail",
        "slide-counter",
        "progress",
        "navigation",
        "nav-controls",
        "controls",
    }
)
_UNSUPPORTED_VISIBLE_TAGS = frozenset(
    {"audio", "canvas", "embed", "iframe", "object", "video"}
)


@dataclass(frozen=True)
class ContractDiagnostic:
    """One contract finding; blocking findings cannot enter compilation."""

    profile: str
    severity: str
    code: str
    message: str
    source_object: str | None = None
    blocking: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "source_object": self.source_object,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class ContractReport:
    """Machine-readable result of checking one HTML input/profile pair."""

    input_path: str
    profile: str
    diagnostics: tuple[ContractDiagnostic, ...]
    css_classifications: tuple[dict[str, Any], ...] = ()

    @property
    def blocked(self) -> bool:
        return any(item.blocking for item in self.diagnostics)

    @property
    def status(self) -> str:
        return "BLOCK" if self.blocked else "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "officecli_compatibility_baseline": OFFICECLI_COMPATIBILITY_BASELINE,
            "input_path": self.input_path,
            "profile": self.profile,
            "status": self.status,
            "blocked": self.blocked,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "css_classifications": list(self.css_classifications),
            "css_properties": {
                item["property"]: item["classification"]
                for item in self.css_classifications
            },
        }


def _node_path(element: Any) -> str:
    try:
        return element.getroottree().getpath(element)
    except (AttributeError, TypeError):
        return f"<{element.tag}>"


def _class_tokens(element: Any) -> set[str]:
    return set(str(element.get("class", "") or "").split())


def _is_hidden(element: Any) -> bool:
    current = element
    while current is not None:
        if current.get("hidden") is not None:
            return True
        styles = _inline_styles(current)
        if styles.get("display", "").lower() == "none" or styles.get(
            "visibility", ""
        ).lower() in {"hidden", "collapse"}:
            return True
        current = current.getparent()
    return False


def _inline_styles(element: Any) -> dict[str, str]:
    return {
        match.group("name").strip().lower(): match.group("value").strip()
        for match in _CSS_DECL_RE.finditer(str(element.get("style", "") or ""))
    }


def _stylesheet_rules(document: Any) -> list[tuple[str, dict[str, str]]]:
    rules: list[tuple[str, dict[str, str]]] = []
    for style in document.xpath("//style"):
        for match in _CSS_BLOCK_RE.finditer(style.text or ""):
            selectors = match.group("selectors").strip()
            declarations = {
                item.group("name").strip().lower(): item.group("value").strip()
                for item in _CSS_DECL_RE.finditer(match.group("body"))
            }
            if declarations:
                rules.append((selectors, declarations))
    return rules


def _selector_has_preview_token(selector: str) -> bool:
    lowered = selector.lower()
    return any(token in lowered for token in _AUTHOR_PREVIEW_TOKENS)


def _selector_atom(selector: str) -> str:
    """Return the final simple selector used for a conservative visibility check."""
    selector = selector.strip()
    if not selector or selector.startswith("@"):
        return ""
    selector = re.sub(r"::?[a-zA-Z-]+(?:\([^)]*\))?", "", selector)
    selector = re.sub(r"\[[^\]]*\]", "", selector)
    parts = re.split(r"\s*(?:>|\+|~)\s*|\s+", selector)
    return parts[-1].strip()


def _simple_selector_matches(element: Any, selector: str) -> bool:
    atom = _selector_atom(selector)
    if not atom:
        return False
    tag_match = re.match(r"^(?P<tag>[a-zA-Z][a-zA-Z0-9_-]*|\*)", atom)
    identifier = re.search(r"#([a-zA-Z][a-zA-Z0-9_-]*)", atom)
    classes = re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)", atom)
    if not tag_match and not identifier and not classes:
        return False
    if tag_match and tag_match.group("tag") != "*":
        if str(element.tag).lower() != tag_match.group("tag").lower():
            return False
    if identifier and str(element.get("id", "")) != identifier.group(1):
        return False
    return set(classes).issubset(_class_tokens(element))


def _stylesheet_rule_has_visible_author_match(
    document: Any,
    selector: str,
    declarations: Mapping[str, str],
) -> bool:
    """Avoid blocking on CSS rules that cannot paint a visible slide object.

    This is intentionally a conservative selector probe, not a CSS engine.  It
    handles the tag/class/id and final-descendant selectors used by the author
    dialect and leaves the browser responsible for actual selector semantics.
    """
    if str(declarations.get("display", "")).lower() == "none":
        return False
    if str(declarations.get("visibility", "")).lower() in {"hidden", "collapse"}:
        return False
    selectors = [item.strip() for item in selector.split(",") if item.strip()]
    slide_elements = document.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]"
    )
    return any(
        _simple_selector_matches(element, alternative)
        and _is_visible_author_element(element)
        for alternative in selectors
        for slide in slide_elements
        for element in slide.iter()
    )


def _author_declarations(document: Any) -> Iterable[tuple[str, str, str]]:
    """Yield ``(property, value, source)`` for author-visible CSS rules."""
    for selector, declarations in _stylesheet_rules(document):
        if _selector_has_preview_token(selector):
            continue
        for name, value in declarations.items():
            yield name, value, f"style:{selector}"
    for element in document.iter():
        if _is_author_ignored(element):
            continue
        for name, value in _inline_styles(element).items():
            yield name, value, _node_path(element)


def _is_author_ignored(element: Any) -> bool:
    tag = str(element.tag).lower() if isinstance(element.tag, str) else ""
    if tag in _AUTHOR_IGNORED_TAGS:
        return True
    tokens = _class_tokens(element)
    identifier = str(element.get("id", "") or "")
    if tokens & _AUTHOR_PREVIEW_TOKENS or identifier in _AUTHOR_PREVIEW_TOKENS:
        return True
    return _has_ignored_ancestor(element)


def _has_ignored_ancestor(element: Any) -> bool:
    for parent in element.iterancestors():
        tag = str(parent.tag).lower() if isinstance(parent.tag, str) else ""
        if tag in _AUTHOR_IGNORED_TAGS - {"html", "head", "body"}:
            return True
        if _class_tokens(parent) & _AUTHOR_PREVIEW_TOKENS:
            return True
        if str(parent.get("id", "") or "") in _AUTHOR_PREVIEW_TOKENS:
            return True
    return False


def _in_slide(element: Any) -> bool:
    return bool(
        element.xpath(
            "ancestor-or-self::*[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]"
        )
    )


def _is_visible_author_element(element: Any) -> bool:
    return _in_slide(element) and not _is_author_ignored(element) and not _is_hidden(element)


def _parse_length(value: Any) -> tuple[float, str] | None:
    match = _LENGTH_RE.fullmatch(str(value or ""))
    if match is None:
        return None
    return float(match.group(1)), (match.group("unit") or "px").lower()


def _positive_length(value: Any) -> bool:
    parsed = _parse_length(value)
    return parsed is not None and parsed[0] > 0


def _emit(
    findings: list[ContractDiagnostic],
    profile: str,
    code: str,
    message: str,
    source_object: str | None = None,
    *,
    blocking: bool = True,
) -> None:
    severity = "error" if blocking else "warning"
    findings.append(
        ContractDiagnostic(profile, severity, code, message, source_object, blocking)
    )


def _css_classification(property_name: str, value: str) -> str:
    normalized_name = property_name.strip().lower()
    normalized_value = value.strip().lower()
    if normalized_name.startswith("--"):
        return "measurement-only"
    if normalized_name in {"background", "background-image"}:
        if normalized_name == "background-image":
            return "unsupported" if normalized_value not in {"none", "initial"} else "rendered"
        if "url(" in normalized_value or "gradient(" in normalized_value:
            return "unsupported"
        return "rendered"
    if normalized_name == "transform":
        if normalized_value in {"none", "initial"} or re.fullmatch(
            r"rotate\(\s*-?[\d.]+deg\s*\)", normalized_value
        ):
            return "rendered"
        return "unsupported"
    if normalized_name in {"border-style", "border-top-style", "border-right-style", "border-bottom-style", "border-left-style"}:
        return "rendered" if normalized_value in {"solid", "none", "initial"} else "unsupported"
    if normalized_name in CSS_PROPERTY_CLASSIFICATIONS:
        return CSS_PROPERTY_CLASSIFICATIONS[normalized_name]
    if normalized_name in {"content", "font-variant", "font-stretch", "font-feature-settings"}:
        return "measurement-only"
    return "unsupported"


def _record_css_classification(
    classifications: list[dict[str, Any]],
    profile: str,
    property_name: str,
    value: str,
    source_object: str,
    *,
    preview_only: bool = False,
) -> str:
    classification = "preview-only" if preview_only else _css_classification(property_name, value)
    classifications.append(
        {
            "profile": profile,
            "property": property_name.strip().lower(),
            "classification": classification,
            "value": value,
            "source_object": source_object,
        }
    )
    return classification


def _check_css_value(
    findings: list[ContractDiagnostic],
    profile: str,
    property_name: str,
    value: str,
    source_object: str,
    *,
    classification: str | None = None,
) -> None:
    normalized = value.strip().lower()
    classification = classification or _css_classification(property_name, value)
    if classification == "unsupported" and normalized not in {"none", "initial"}:
        _emit(
            findings,
            profile,
            "unsupported_visible_css",
            f"{property_name} is not supported by the OfficeCLI contract: {value!r}.",
            source_object,
        )
        return
    if property_name == "writing-mode" and normalized not in {"horizontal-tb", "initial"}:
        _emit(
            findings,
            profile,
            "unsupported_visible_css",
            "vertical writing modes are outside OfficeCLI Contract v1.",
            source_object,
        )


def _check_author(
    document: Any,
    findings: list[ContractDiagnostic],
    classifications: list[dict[str, Any]],
) -> None:
    slides = document.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]"
    )
    if not slides:
        _emit(findings, "author", "missing_slides", "Author profile requires at least one .slide element.")
        return

    rules = _stylesheet_rules(document)
    for index, slide in enumerate(slides, start=1):
        inline = _inline_styles(slide)
        width = inline.get("width")
        height = inline.get("height")
        for selector, declarations in rules:
            if ".slide" in selector and not _selector_has_preview_token(selector):
                width = declarations.get("width", width)
                height = declarations.get("height", height)
        valid_canvases = {(1920.0, "px", 1080.0, "px"), (960.0, "px", 540.0, "px")}
        parsed_canvas = (*(_parse_length(width) or (None, None)), *(_parse_length(height) or (None, None)))
        if parsed_canvas not in valid_canvases:
            _emit(
                findings,
                "author",
                "invalid_author_canvas",
                f"Author slide {index} must declare width:1920px and height:1080px (or the legacy 960px × 540px canvas); got {width!r} × {height!r}.",
                f"slide[{index}]",
            )

    for element in document.iter():
        if not _is_visible_author_element(element):
            continue
        tag = str(element.tag).lower() if isinstance(element.tag, str) else ""
        if tag in _UNSUPPORTED_VISIBLE_TAGS:
            _emit(
                findings,
                "author",
                "unsupported_visible_tag",
                f"<{tag}> is visible in the author content but has no OfficeCLI object mapping.",
                _node_path(element),
            )
        if tag == "img":
            source = str(element.get("src", "") or "")
            if not source.lower().startswith("data:image/"):
                _emit(
                    findings,
                    "author",
                    "unsupported_picture_source",
                    "Author pictures must use data:image/... sources.",
                    _node_path(element),
                )
        if tag in {"td", "th"}:
            if str(element.get("rowspan", "1")) != "1" or str(element.get("colspan", "1")) != "1":
                _emit(
                    findings,
                    "author",
                    "unsupported_table_span",
                    "Merged table cells are not supported in OfficeCLI Contract v1.",
                    _node_path(element),
                )

    for selector, declarations in _stylesheet_rules(document):
        preview_only = _selector_has_preview_token(selector)
        source = f"style:{selector}"
        for property_name, value in declarations.items():
            classification = _record_css_classification(
                classifications,
                "author",
                property_name,
                value,
                source,
                preview_only=preview_only,
            )
            if preview_only or not _stylesheet_rule_has_visible_author_match(
                document, selector, declarations
            ):
                continue
            if _EXTERNAL_URL_RE.search(value) and not value.strip().lower().startswith("data:"):
                _emit(
                    findings,
                    "author",
                    "external_resource",
                    f"External resource in {property_name} is not a deterministic compiler input.",
                    source,
                )
            _check_css_value(
                findings,
                "author",
                property_name,
                value,
                source,
                classification=classification,
            )
    for element in document.iter():
        tag = str(element.tag).lower() if isinstance(element.tag, str) else ""
        ignored = (
            _is_author_ignored(element)
            or _is_hidden(element)
            or not _in_slide(element)
        )
        source = _node_path(element)
        for property_name, value in _inline_styles(element).items():
            classification = _record_css_classification(
                classifications,
                "author",
                property_name,
                value,
                source,
                preview_only=ignored,
            )
            if ignored:
                continue
            if _EXTERNAL_URL_RE.search(value) and not value.strip().lower().startswith("data:"):
                _emit(
                    findings,
                    "author",
                    "external_resource",
                    f"External resource in {property_name} is not a deterministic compiler input.",
                    source,
                )
            _check_css_value(
                findings,
                "author",
                property_name,
                value,
                source,
                classification=classification,
            )

    for style in document.xpath("//style"):
        for match in _IMPORT_RE.finditer(style.text or ""):
            _emit(
                findings,
                "author",
                "external_resource",
                "External @import resources are not deterministic compiler inputs.",
                _node_path(style),
            )

    for link in document.xpath("//link[@href]"):
        if _has_ignored_ancestor(link):
            continue
        _emit(
            findings,
            "author",
            "external_resource",
            "External link resources are not deterministic compiler inputs.",
            _node_path(link),
        )
    for script in document.xpath("//script[@src]"):
        if _has_ignored_ancestor(script):
            continue
        _emit(
            findings,
            "author",
            "external_resource",
            "Authoring preview scripts must be inline.",
            _node_path(script),
        )


def _owned_officehtml_elements(document: Any) -> list[tuple[Any, str, str]]:
    slides = document.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]"
    )
    owned: list[tuple[Any, str, str]] = []
    for element in document.xpath("//*[@data-path]"):
        path = str(element.get("data-path") or "")
        match = _OWNED_PATH_RE.search(path)
        if match is None:
            continue
        slide_number = int(match.group("slide"))
        if slide_number < 1 or slide_number > len(slides) or not any(
            slide is element or slide in element.iterancestors() for slide in slides
        ):
            continue
        owned.append((element, path, match.group("kind").lower()))
    return owned


def _check_officehtml(
    document: Any,
    findings: list[ContractDiagnostic],
    classifications: list[dict[str, Any]],
) -> None:
    slides = document.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]"
    )
    if not slides:
        _emit(
            findings,
            "officehtml",
            "missing_slides",
            "OfficeHTML profile requires at least one .slide projection.",
        )
        return
    design_width = design_height = None
    for selector, declarations in _stylesheet_rules(document):
        if selector.strip().lower() == ":root":
            design_width = declarations.get("--slide-design-w", design_width)
            design_height = declarations.get("--slide-design-h", design_height)
    for index, slide in enumerate(slides, start=1):
        styles = _inline_styles(slide)
        # The OfficeCLI 1.0.147 parser uses the widescreen point canvas when a
        # minimal projection omits explicit slide bounds.  Keep the Contract
        # aligned with that public parser default while still rejecting a
        # partially declared or non-positive canvas.
        width = styles.get("width", design_width)
        height = styles.get("height", design_height)
        if width is None and height is None:
            width, height = "960pt", "540pt"
        if not _positive_length(width) or not _positive_length(height):
            _emit(
                findings,
                "officehtml",
                "invalid_officehtml_canvas",
                f"OfficeHTML slide {index} must expose positive point-based bounds.",
                f"slide[{index}]",
            )

    seen_paths: set[str] = set()
    for element, source, kind in _owned_officehtml_elements(document):
        if source in seen_paths:
            _emit(
                findings,
                "officehtml",
                "duplicate_source_identity",
                "Each slide-owned data-path must identify one object.",
                source,
            )
        seen_paths.add(source)
        if kind not in SUPPORTED_OBJECT_KINDS:
            _emit(
                findings,
                "officehtml",
                "unsupported_object_kind",
                f"OfficeHTML object kind {kind!r} is outside the supported object surface.",
                source,
            )
            continue
        if kind == "picture":
            images = element.xpath(".//img[@src]")
            if not images or not str(images[0].get("src", "")).lower().startswith("data:image/"):
                _emit(
                    findings,
                    "officehtml",
                    "unsupported_picture_source",
                    "OfficeHTML picture projections must retain a data:image/... source.",
                    source,
                )
        if kind == "table":
            cells = element.xpath(".//td | .//th")
            for cell in cells:
                if not cell.get("data-cell-path"):
                    _emit(
                        findings,
                        "officehtml",
                        "missing_table_cell_path",
                        "Every OfficeHTML table cell must expose data-cell-path.",
                        source,
                    )
                if str(cell.get("rowspan", "1")) != "1" or str(cell.get("colspan", "1")) != "1":
                    _emit(
                        findings,
                        "officehtml",
                        "unsupported_table_span",
                        "Merged table cells are not supported in OfficeCLI Contract v1.",
                        str(cell.get("data-cell-path") or source),
                    )
        for descendant in element.iter():
            if not isinstance(descendant.tag, str) or _is_hidden(descendant):
                continue
            tag = descendant.tag.lower()
            if tag in _UNSUPPORTED_VISIBLE_TAGS:
                _emit(
                    findings,
                    "officehtml",
                    "unsupported_visible_tag",
                    f"<{tag}> is visible inside slide-owned object {source}.",
                    _node_path(descendant),
                )
            for property_name, value in _inline_styles(descendant).items():
                classification = _record_css_classification(
                    classifications,
                    "officehtml",
                    property_name,
                    value,
                    source,
                )
                _check_css_value(
                    findings,
                    "officehtml",
                    property_name,
                    value,
                    source,
                    classification=classification,
                )


def check_contract(input_html: str | Path, profile: str = "author") -> ContractReport:
    """Check one HTML file against the explicit ``author`` or ``officehtml`` profile."""
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(
            f"Unsupported contract profile {profile!r}; choose 'author' or 'officehtml'."
        )
    path = Path(input_html).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"HTML input does not exist: {path}")
    try:
        document = _lxml_html.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"Unable to parse HTML input {path}: {exc}") from exc
    findings: list[ContractDiagnostic] = []
    classifications: list[dict[str, Any]] = []
    if profile == "author":
        _check_author(document, findings, classifications)
    else:
        _check_officehtml(document, findings, classifications)
    return ContractReport(str(path), profile, tuple(findings), tuple(classifications))


def main(argv: list[str] | None = None) -> int:
    """CLI for the profile-aware contract checker."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Check the OfficeCLI HTML Contract v1.")
    parser.add_argument("input", help="HTML input path")
    parser.add_argument("--profile", choices=SUPPORTED_PROFILES, default="author")
    parser.add_argument("--json", dest="json_path", help="write the report to a JSON file")
    args = parser.parse_args(argv)
    try:
        report = check_contract(args.input, args.profile)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
        return 3
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 2 if report.blocked else 0


__all__ = [
    "CONTRACT_VERSION",
    "OFFICECLI_COMPATIBILITY_BASELINE",
    "SUPPORTED_PROFILES",
    "SUPPORTED_OBJECT_KINDS",
    "CSS_CLASSIFICATIONS",
    "CSS_PROPERTY_CLASSIFICATIONS",
    "SUPPORTED_CSS_PROPERTIES",
    "ContractDiagnostic",
    "ContractReport",
    "check_contract",
]


if __name__ == "__main__":
    raise SystemExit(main())
