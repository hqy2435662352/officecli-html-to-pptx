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
from typing import Any, Iterable, Mapping, Sequence

from lxml import html as _lxml_html

CONTRACT_VERSION = "1.1"
OFFICECLI_COMPATIBILITY_BASELINE = "1.0.151"
SUPPORTED_PROFILES = ("author", "officehtml")
SUPPORTED_OBJECT_KINDS = frozenset({"shape", "textbox", "picture", "table"})
AUTHOR_CANVAS_SIZES = ((1920.0, "px", 1080.0, "px"), (960.0, "px", 540.0, "px"))
AUTHOR_PICTURE_SOURCE = "data:image/..."
AUTHOR_EXTERNAL_RESOURCES_ALLOWED = False
AUTHOR_TABLE_CELL_SPANS = True
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
        "direction",
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
        "transform",
        "vertical-align",
    }
)
# ``list-style-type`` is a declaration of a list item's *marker*, not a painted
# style: the measurement reads the item's computed value, the lowering writes the
# ``list`` preset from it, and OfficeCLI renders it as a native ``a:buChar`` or
# ``a:buAutoNum`` -- the marker is never literal marker text.  It is what lets one
# list carry a bullet item and a numbered item, which is exactly what a source
# deck's own list object can contain.
# ``text-transform`` is measured but never lowered: no Canonical Run key, run
# property or readback carries the case transform, so a browser that shows
# ``uppercase`` text would be silently checked as supported while the PPTX keeps
# the authored case.  It is therefore declared unsupported and blocked until
# lowering, readback and visual evidence exist for it.
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
        "list-style-type",
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
        # Measured but never lowered: see the note above.
        "text-transform",
        "text-shadow",
        # Letter spacing is measurable by Chromium but is not part of the
        # Contract 1.1 native run matrix.  It must fail closed rather than
        # silently disappear in the PowerPoint text body.
        "letter-spacing",
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

# The mixed-run surface is the inline formatting surface this product really
# supports end to end.  It is declared once here and consumed by both the
# Contract checker (``check``) and the OfficeCLI lowering pass, so the public
# capability manifest cannot drift from what is actually enforced.
SUPPORTED_INLINE_ELEMENTS = (
    "span",
    "strong",
    "em",
    "b",
    "i",
    "a",
    "code",
    "mark",
    "sub",
    "sup",
    "small",
    "u",
    "s",
    "del",
    "abbr",
    "cite",
    "q",
    "time",
    "var",
    "kbd",
)
# Canonical Run identity is declared exactly once, here.  A Canonical Run
# boundary is a formatting boundary, so the published mixed-run surface and the
# lowering pass that merges a paragraph's runs must read one declaration instead
# of each restating it.  Each row is
#
#   (normalized lowering field, published mixed-run attribute, CSS property)
#
# Every row is part of the closed native run matrix.  The capability manifest
# derives its published attributes from this declaration and the lowering pass
# builds its merge key from the same rows, so an identity dimension cannot be
# published without being implemented, or implemented without being published.
CANONICAL_RUN_IDENTITY = (
    ("font_family", "font_family", "font-family"),
    ("font_size_pt", "font_size", "font-size"),
    ("bold", "bold", "font-weight"),
    ("italic", "italic", "font-style"),
    ("color", "color", "color"),
    ("underline", "underline", "text-decoration"),
)
CANONICAL_RUN_IDENTITY_FIELDS = tuple(
    field for field, _attribute, _property in CANONICAL_RUN_IDENTITY
)
MIXED_RUN_ATTRIBUTES = {
    attribute: css_property
    for _field, attribute, css_property in CANONICAL_RUN_IDENTITY
    if attribute is not None
}
CANONICAL_RUN_POLICY = {
    "scope": "paragraph",
    "requires": [
        "identical resolved formatting",
        # Retain the public capability token for schema compatibility; the
        # concrete identity dimensions are the six closed-matrix rows above.
        "identical supported semantic attributes",
    ],
    "forbidden_across": ["paragraph", "list_item", "hard_break"],
    "range_units": "utf-16-code-units",
}

# The paragraph-layout surface is the block-level text surface this product
# really supports end to end.  Like ``SUPPORTED_INLINE_ELEMENTS`` it is declared
# once here and consumed by both the checker and the lowering pass, so the
# public capability manifest cannot drift from the paragraph alignment and
# soft-wrap behavior the compiler applies.
TEXT_ALIGNMENT_VALUES = ("center", "justify", "left", "right")
TEXT_ALIGNMENT_DEFAULT = "left"
TEXT_ALIGNMENT_MAPPING = {
    "start": {"ltr": "left", "rtl": "right"},
    "end": {"ltr": "right", "rtl": "left"},
}
LINE_HEIGHT_PROPERTY = "line-height"
PARAGRAPH_SPACING_PROPERTIES = ("margin-top", "margin-bottom")
# Contract 1.1 deliberately has no CSS-pixel projection: a used line-height in
# px is divided by the element font size directly.  The scale constant remains
# public for older callers, but its only valid value is the identity scale.
LINE_HEIGHT_PX_PROJECTION_SCALE = 1.0
# These names existed in the pre-1.1 compiler and remain as inert compatibility
# symbols while downstream callers migrate.  Contract 1.1 never consults them
# to select a formatting or geometry exception.
SOURCE_FIDELITY_LINE_SPACING_TEXT = ""
SOURCE_FIDELITY_LINE_SPACING_MIN_FONT_SIZE_PX = 0.0
# Chromium's measured visual lines are evidence only.  They never become native
# paragraph boundaries or hard breaks in Contract 1.1.
SOFT_WRAP_MODEL = {
    "representation": "measurement-and-evidence-only",
    "measured_property": "visualLines",
    "unit": "measurement-line",
    "requires": ["ordered-soft-wrap-sequence"],
    "fallback": "authored-paragraph-structure",
    "lowering": "never",
    "object_per_source": 1,
    "object_kind": "textbox",
    "new_soft_line_break_representation": False,
}

# The list surface is the top-level HTML list surface this product really
# supports end to end: one ``ul``/``ol`` becomes one Native List Textbox and
# every direct ``li`` one Native List Paragraph whose bullet or automatic number,
# level, and indentation are native PowerPoint paragraph properties.  It is
# declared once here and consumed by both the Contract checker (which blocks the
# structures outside it) and the OfficeCLI lowering pass, so the published
# capability manifest cannot drift from what is enforced.
LIST_SURFACE_ELEMENTS = ("ol", "ul")
LIST_MARKER_PRESETS = {"ol": "numbered", "ul": "bullet"}
LIST_PARAGRAPH_PROPERTIES = ("list", "level", "marginLeft", "indent")
LIST_LEVELS = (0,)
LIST_ITEM_SOFT_WRAP = "native-re-wrap-inside-the-measured-list-bounds"
# One stable, descriptive blocking code per structure outside the surface; each
# diagnostic carries the source context of the offending DOM node.
LIST_REJECTION_CODES = (
    "nested_list",
    "list_item_hard_break",
    "multi_paragraph_list_item",
)
LIST_REJECTIONS = {
    "nested_list": (
        "A <ul>/<ol> nested inside another <ul>/<ol> is outside the initial "
        "top-level list surface."
    ),
    "list_item_hard_break": (
        "A list item containing a <br> would need more than one Native List "
        "Paragraph."
    ),
    "multi_paragraph_list_item": (
        "A list item with block-level children would need more than one Native "
        "List Paragraph."
    ),
}


@dataclass(frozen=True)
class TableRegion:
    """One anchor-owned rectangular region in a logical table grid."""

    anchor_row: int
    anchor_column: int
    row_span: int
    column_span: int
    source_row: int
    source_column: int
    source_object: str

    def as_dict(self) -> dict[str, int]:
        return {
            "anchorRow": self.anchor_row,
            "anchorColumn": self.anchor_column,
            "rowSpan": self.row_span,
            "columnSpan": self.column_span,
        }


@dataclass(frozen=True)
class LogicalTableGrid:
    """Validated logical topology shared by Contract and native lowering."""

    rows: int
    columns: int
    regions: tuple[TableRegion, ...]
    occupancy: tuple[tuple[int, ...], ...]

    @property
    def normalized_topology(self) -> list[dict[str, int]]:
        return [region.as_dict() for region in self.regions]


class TableTopologyError(ValueError):
    """A stable, source-bound failure while constructing a logical table grid."""

    def __init__(self, code: str, message: str, source_object: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.source_object = source_object


def _table_span_value(
    raw_value: Any,
    *,
    attribute: str,
    source_object: str,
) -> int:
    """Parse one HTML span without inheriting browser ``parseInt`` leniency."""

    if raw_value is None:
        return 1
    text = str(raw_value).strip()
    if not re.fullmatch(r"[+-]?\d+", text):
        raise TableTopologyError(
            "malformed_table_span",
            f"{attribute} must be a positive integer on {source_object}; got {raw_value!r}.",
            source_object,
        )
    value = int(text)
    if value <= 0:
        raise TableTopologyError(
            "table_span_non_positive",
            f"{attribute} must be greater than zero on {source_object}; got {raw_value!r}.",
            source_object,
        )
    return value


def build_logical_table_grid(
    rows: Sequence[Sequence[Mapping[str, Any]]],
    *,
    source_object: str,
) -> LogicalTableGrid:
    """Build a rectangular logical grid and fail closed on ambiguous topology.

    ``rows`` contains lightweight cell mappings with ``rowspan``, ``colspan``,
    ``source_object``, and optional ``text`` keys.  The function deliberately
    does not infer a missing cell: every logical slot must be owned by exactly
    one anchor region after HTML row-span placement.
    """

    if not rows:
        raise TableTopologyError(
            "invalid_table_matrix",
            f"Table {source_object} has no rows.",
            source_object,
        )

    occupancy: list[dict[int, int]] = [dict() for _ in rows]
    regions: list[TableRegion] = []
    seen_sources: set[str] = set()
    max_column = 0

    for row_index, row in enumerate(rows):
        if not row:
            raise TableTopologyError(
                "table_hole",
                f"Table {source_object} row {row_index + 1} has no cells.",
                f"{source_object}/tr[{row_index + 1}]",
            )
        cursor = 0
        for source_column, cell in enumerate(row):
            cell_source = str(
                cell.get("source_object")
                or f"{source_object}/tr[{row_index + 1}]/tc[{source_column + 1}]"
            )
            if cell_source in seen_sources:
                raise TableTopologyError(
                    "competing_table_anchor",
                    f"Table {source_object} has competing anchors with source identity {cell_source!r}.",
                    cell_source,
                )
            seen_sources.add(cell_source)

            row_span = _table_span_value(
                cell.get("rowspan"),
                attribute="rowspan",
                source_object=cell_source,
            )
            column_span = _table_span_value(
                cell.get("colspan"),
                attribute="colspan",
                source_object=cell_source,
            )
            if row_index + row_span > len(rows):
                raise TableTopologyError(
                    "table_span_out_of_bounds",
                    f"Table span at {cell_source} reaches past the {len(rows)}-row logical grid.",
                    cell_source,
                )

            # A source cell starts at the first unoccupied slot in its row, as
            # HTML table layout specifies.  A span that would then cross a
            # row-spanned region is ambiguous rather than something to guess.
            while cursor in occupancy[row_index]:
                cursor += 1
            end_column = cursor + column_span
            collisions = [
                (target_row, target_column)
                for target_row in range(row_index, row_index + row_span)
                for target_column in range(cursor, end_column)
                if target_column in occupancy[target_row]
            ]
            if collisions:
                has_content = bool(str(cell.get("text", "") or "").strip())
                code = (
                    "covered_cell_content_ambiguity"
                    if has_content
                    else "table_span_overlap"
                )
                detail = "covered-cell content is ambiguous" if has_content else "table spans overlap"
                raise TableTopologyError(
                    code,
                    f"{detail} at {cell_source} in table {source_object}.",
                    cell_source,
                )

            region_index = len(regions)
            region = TableRegion(
                anchor_row=row_index + 1,
                anchor_column=cursor + 1,
                row_span=row_span,
                column_span=column_span,
                source_row=row_index,
                source_column=source_column,
                source_object=cell_source,
            )
            regions.append(region)
            for target_row in range(row_index, row_index + row_span):
                for target_column in range(cursor, end_column):
                    occupancy[target_row][target_column] = region_index
            cursor = end_column
            max_column = max(max_column, end_column)

    if max_column <= 0:
        raise TableTopologyError(
            "invalid_table_matrix",
            f"Table {source_object} has no logical columns.",
            source_object,
        )
    for row_index in range(len(rows)):
        missing = [column for column in range(max_column) if column not in occupancy[row_index]]
        if missing:
            raise TableTopologyError(
                "table_hole",
                f"Table {source_object} row {row_index + 1} has uncovered logical columns {missing!r}.",
                f"{source_object}/tr[{row_index + 1}]",
            )

    normalized_occupancy = tuple(
        tuple(occupancy[row_index][column] for column in range(max_column))
        for row_index in range(len(rows))
    )
    return LogicalTableGrid(
        rows=len(rows),
        columns=max_column,
        regions=tuple(regions),
        occupancy=normalized_occupancy,
    )


def list_surface() -> dict[str, Any]:
    """Declare the top-level list surface from its single authority.

    ``author_capability_manifest`` publishes this, ``_check_lists`` blocks the
    structures outside it, and the OfficeCLI lowering pass consumes the same
    marker presets and paragraph properties, so checking and lowering are held
    to one declaration instead of a parallel handwritten matrix.
    """
    return {
        "elements": list(LIST_SURFACE_ELEMENTS),
        "nesting": "top-level-only",
        "levels": list(LIST_LEVELS),
        "object_per_list": 1,
        "object_kind": "textbox",
        "paragraphs_per_item": 1,
        "marker": {
            "property": "list",
            "presets": dict(LIST_MARKER_PRESETS),
            "unmarked": "none",
            "literal_prefix": "rejected",
            "native": ["a:buChar", "a:buAutoNum"],
        },
        "indentation": {
            "properties": ["marginLeft", "indent", "level"],
            "native": ["@marL", "@indent", "@lvl"],
            "margin_left": "measured item text edge minus the list border-box left edge",
            "indent": "negative one em (the Chromium outside-marker box advance)",
            "body_inset": "0pt",
        },
        "paragraph_properties": sorted(LIST_PARAGRAPH_PROPERTIES),
        "item_soft_wrap": LIST_ITEM_SOFT_WRAP,
        "rejections": dict(LIST_REJECTIONS),
    }


def paragraph_layout_surface() -> dict[str, Any]:
    """Declare the paragraph-layout surface from its single authority.

    ``author_capability_manifest`` publishes this, and both the Contract
    checker and the OfficeCLI lowering pass resolve alignment through
    ``_resolve_text_alignment`` in this module, so the published surface is the
    same data the pipeline is held to rather than a parallel handwritten matrix.
    """
    return {
        "alignment": {
            "property": "text-align",
            "values": sorted(TEXT_ALIGNMENT_VALUES),
            "accepted_relative": ["start", "end"],
            "rejected": ["unknown-values"],
            "default": TEXT_ALIGNMENT_DEFAULT,
            "mapping": {
                name: dict(directions)
                for name, directions in TEXT_ALIGNMENT_MAPPING.items()
            },
            "native": "paragraph-align",
        },
        "line_height": {
            "property": LINE_HEIGHT_PROPERTY,
            "native": "lineSpacing",
            "accepted": ["positive-unitless", "positive-px"],
            "unitless": "line-height / font-size",
            "length_with_px_projection": "line-height / font-size",
            "rejected": [
                "normal",
                "percentage",
                "relative-unit",
                "non-px-absolute-unit",
                "unresolved-css-variable",
                "non-positive",
            ],
            "omitted_when_ratio_within": 0.01,
            "precision": "0.001x",
            "readback_tolerance": 0.01,
            "default": "absent",
        },
        "paragraph_spacing": {
            "properties": list(PARAGRAPH_SPACING_PROPERTIES),
            "native": ["spaceBefore", "spaceAfter"],
            "unit": "pt",
            "accepted": ["unitless-zero", "non-negative-px"],
            "rejected": ["negative", "relative-unit", "non-px-absolute-unit", "auto"],
            "projection": "css-margin-px-to-native-paragraph-points-at-measured-slide-scale",
            "readback_tolerance_pt": 0.25,
            "default": "absent",
            "emitted_at": ["table-cell-paragraph"],
            "standalone_text_block": "margins-are-already-in-the-measured-bounds",
        },
        "soft_wrap": {
            key: (list(value) if isinstance(value, list) else value)
            for key, value in SOFT_WRAP_MODEL.items()
        },
    }


def _resolve_text_alignment(element: Mapping[str, Any]) -> str:
    """Resolve a measured ``text-align`` to its native paragraph alignment.

    The OfficeCLI lowering of a text body, a shape, and a table cell all use
    this one resolution, so a declared alignment value cannot be one the
    compiler would silently rewrite.
    """
    value = str(element.get("textAlign", "start") or "start").lower()
    direction = str(element.get("direction", "ltr") or "ltr").lower()
    relative = TEXT_ALIGNMENT_MAPPING.get(value)
    if relative is not None:
        return relative["rtl"] if direction == "rtl" else relative["ltr"]
    return value if value in TEXT_ALIGNMENT_VALUES else TEXT_ALIGNMENT_DEFAULT


def author_capability_manifest() -> dict[str, Any]:
    """Return the Author support claims owned by the Contract checker."""
    return {
        "version": CONTRACT_VERSION,
        "profile": "author",
        "object_kinds": sorted(SUPPORTED_OBJECT_KINDS),
        "css_properties": {
            name: CSS_PROPERTY_CLASSIFICATIONS[name]
            for name in sorted(CSS_PROPERTY_CLASSIFICATIONS)
        },
        "mixed_run_surface": {
            "attributes": dict(MIXED_RUN_ATTRIBUTES),
            "inline_elements": sorted(SUPPORTED_INLINE_ELEMENTS),
            "canonical_run": {
                key: (
                    list(value) if isinstance(value, list) else value
                )
                for key, value in CANONICAL_RUN_POLICY.items()
            },
        },
        "paragraph_layout_surface": paragraph_layout_surface(),
        "list_surface": list_surface(),
        "accepted_resources": {
            "picture_source": AUTHOR_PICTURE_SOURCE,
            "external_resources": AUTHOR_EXTERNAL_RESOURCES_ALLOWED,
        },
        "table_cell_spans": AUTHOR_TABLE_CELL_SPANS,
    }

_CSS_BLOCK_RE = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", re.DOTALL)
_CSS_DECL_RE = re.compile(r"(?P<name>[a-zA-Z-]+)\s*:\s*(?P<value>[^;]+)")
_CSS_DATA_IMAGE_URL_RE = re.compile(
    r'''url\(\s*(?P<quote>["']?)(?P<source>data:image/.*?)(?P=quote)\s*\)''',
    re.IGNORECASE | re.DOTALL,
)
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


def _officehtml_parser() -> Any:
    """Create the HTML parser used for OfficeCLI's large data-URI projections."""
    return _lxml_html.HTMLParser(huge_tree=True)


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
        try:
            if float(styles.get("opacity", "1")) <= 0:
                return True
        except (TypeError, ValueError):
            pass
        current = current.getparent()
    return False


def _split_inline_declarations(value: str) -> list[str]:
    """Split inline CSS without breaking semicolons inside functions/strings."""
    declarations: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escaped = False
    for index, character in enumerate(value):
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        elif character == ";" and depth == 0:
            declarations.append(value[start:index])
            start = index + 1
    declarations.append(value[start:])
    return declarations


def _inline_styles(element: Any) -> dict[str, str]:
    styles: dict[str, str] = {}
    value = element.get("style", "") if element is not None else ""
    for declaration in _split_inline_declarations(
        str(value or "")
    ):
        if ":" not in declaration:
            continue
        name, raw_value = declaration.split(":", 1)
        name = name.strip().lower()
        if name:
            styles[name] = raw_value.strip()
    return styles


def _data_image_source(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _CSS_DATA_IMAGE_URL_RE.search(value)
    if match is None:
        return None
    return match.group("source").strip()


def _officehtml_picture_source(element: Any) -> str | None:
    """Return an OfficeHTML picture's img or CSS data-image source."""
    images = element.xpath(".//img[@src]")
    for image in images:
        source = str(image.get("src", "") or "")
        if source.lower().startswith("data:image/"):
            return source
    for descendant in element.iter():
        source = _data_image_source(
            _inline_styles(descendant).get("background-image")
        )
        if source is not None:
            return source
    return None


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


def _selector_matches_element(element: Any, selector: str) -> bool:
    """Conservatively match tag/class/id descendant selectors.

    This is only used to decide whether a stylesheet rule hides an author
    node.  It deliberately does not try to implement the full CSS selector
    grammar; unsupported selector constructs simply do not count as a hidden
    match and remain subject to the normal visible-content contract.
    """
    selector = selector.strip()
    if not selector or selector.startswith("@"):
        return False
    parts = [
        part.strip()
        for part in re.split(r"\s*(?:>|\+|~)\s*|\s+", selector)
        if part.strip()
    ]
    if not parts or not _simple_selector_matches(element, parts[-1]):
        return False
    current = element.getparent()
    for part in reversed(parts[:-1]):
        while current is not None and not _simple_selector_matches(current, part):
            current = current.getparent()
        if current is None:
            return False
        current = current.getparent()
    return True


def _is_slide_element(element: Any) -> bool:
    return "slide" in _class_tokens(element)


def _stylesheet_hides_element(document: Any, element: Any) -> bool:
    """Apply the small visibility subset needed by the author contract.

    Inline declarations win over stylesheet declarations.  A rule targeting a
    slide root is not treated as hiding that root because the compiler activates
    one slide at a time before measurement; the same declaration does not hide
    descendants in CSS and is therefore not inherited here either.
    """
    current = element
    rules = _stylesheet_rules(document)
    while current is not None:
        # The compiler intentionally activates each .slide during browser
        # measurement, so a stylesheet's display:none on the slide root is
        # not an author-content visibility decision.  Descendant visibility is
        # still checked normally below.
        if not _is_slide_element(current):
            computed: dict[str, str] = {}
            for selector, declarations in rules:
                if any(
                    _selector_matches_element(current, alternative)
                    for alternative in selector.split(",")
                ):
                    for name in ("display", "visibility", "opacity"):
                        if name in declarations:
                            computed[name] = declarations[name]
            computed.update(
                {
                    name: value
                    for name, value in _inline_styles(current).items()
                    if name in {"display", "visibility", "opacity"}
                }
            )
            if computed.get("display", "").lower() == "none":
                return True
            if computed.get("visibility", "").lower() in {"hidden", "collapse"}:
                return True
            try:
                if float(computed.get("opacity", "1")) <= 0:
                    return True
            except (TypeError, ValueError):
                pass
        current = current.getparent()
    return False


def _selector_targets_slide(selector: str, slide: Any) -> bool:
    """Match only a compound selector whose target is the slide itself."""
    for alternative in selector.split(","):
        alternative = alternative.strip()
        if not alternative or re.search(r"\s|[>+~]", alternative):
            continue
        if _simple_selector_matches(slide, alternative):
            return True
    return False


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
        and _is_visible_author_element(element, document)
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


def _is_visible_author_element(element: Any, document: Any | None = None) -> bool:
    return (
        _in_slide(element)
        and not _is_author_ignored(element)
        and not _is_hidden(element)
        and (document is None or not _stylesheet_hides_element(document, element))
    )


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


def _element_tag(element: Any) -> str:
    return str(element.tag).lower() if isinstance(element.tag, str) else ""


def _descendant_tag(element: Any, tag: str) -> Any | None:
    for descendant in element.iterdescendants():
        if _element_tag(descendant) == tag:
            return descendant
    return None


def _child_tag(element: Any, tags: set[str]) -> Any | None:
    for child in element:
        if _element_tag(child) in tags:
            return child
    return None


def _list_stray_text(element: Any) -> str:
    """Return list-owned text that no direct ``li`` accounts for."""
    parts = [element.text or ""]
    parts.extend(child.tail or "" for child in element)
    return "".join(parts).strip()


def _check_lists(document: Any, findings: list[ContractDiagnostic]) -> None:
    """Reject the list structures outside the declared top-level list surface.

    The accepted surface is one ``ul``/``ol`` per Native List Textbox with one
    Native List Paragraph per direct, single-paragraph ``li``.  A list nested in
    another list, an item with a hard break, and an item with block-level
    children all need paragraph structures the surface does not have, so they
    block before any output exists.  A list's position in the DOM (inside a
    ``div`` or ``section``) is not a rejection: only nesting and item structure
    are.
    """
    list_tags = set(LIST_SURFACE_ELEMENTS)
    for element in document.iter():
        tag = _element_tag(element)
        if tag not in list_tags:
            continue
        if not _is_visible_author_element(element, document):
            continue
        source = _node_path(element)
        nested = _descendant_tag(element, "ul")
        if nested is None:
            nested = _descendant_tag(element, "ol")
        if nested is not None:
            _emit(
                findings,
                "author",
                "nested_list",
                f"{LIST_REJECTIONS['nested_list']} (found <{_element_tag(nested)}> at {_node_path(nested)}.)",
                _node_path(nested),
            )
            continue
        strays = [child for child in element if _element_tag(child) != "li"]
        if strays:
            _emit(
                findings,
                "author",
                "multi_paragraph_list_item",
                "Only direct <li> items are part of the Native List Textbox "
                f"surface; found <{_element_tag(strays[0])}> instead.",
                _node_path(strays[0]),
            )
            continue
        if _list_stray_text(element):
            _emit(
                findings,
                "author",
                "multi_paragraph_list_item",
                "List text that no direct <li> item owns is outside the Native List "
                "Textbox surface.",
                source,
            )
            continue
        for item in element:
            hard_break = _descendant_tag(item, "br")
            if hard_break is not None:
                _emit(
                    findings,
                    "author",
                    "list_item_hard_break",
                    f"{LIST_REJECTIONS['list_item_hard_break']} (found <br> at {_node_path(hard_break)}.)",
                    _node_path(hard_break),
                )
                continue
            block_child = _child_tag(
                item, {"p", "div", "section", "ul", "ol", "table", "blockquote", "pre"}
            )
            if block_child is not None:
                _emit(
                    findings,
                    "author",
                    "multi_paragraph_list_item",
                    f"{LIST_REJECTIONS['multi_paragraph_list_item']} (found <{_element_tag(block_child)}> at {_node_path(block_child)}.)",
                    _node_path(block_child),
                )


def _css_classification(
    property_name: str,
    value: str,
    *,
    allow_data_image_background: bool = False,
) -> str:
    normalized_name = property_name.strip().lower()
    normalized_value = value.strip().lower()
    if normalized_name.startswith("--"):
        return "measurement-only"
    if normalized_name in {"background", "background-image"}:
        if normalized_name == "background-image":
            if allow_data_image_background and _data_image_source(value) is not None:
                return "rendered"
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
    allow_data_image_background: bool = False,
) -> str:
    classification = (
        "preview-only"
        if preview_only
        else _css_classification(
            property_name,
            value,
            allow_data_image_background=allow_data_image_background,
        )
    )
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
    if property_name == LINE_HEIGHT_PROPERTY:
        parsed = _parse_length(value)
        raw = value.strip().lower()
        if parsed is None or parsed[0] <= 0 or parsed[1] not in {"px"}:
            # A unitless positive number is the one non-length line-height
            # form accepted by Contract 1.1.  ``_parse_length`` normalizes a
            # missing unit to px for the general geometry grammar, so inspect
            # the source spelling separately here.
            if not re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)", raw) or float(raw) <= 0:
                _emit(
                    findings,
                    profile,
                    "unsupported_line_height",
                    "line-height must be a positive unitless number or positive px value.",
                    source_object,
                )
        return
    if property_name.startswith("margin"):
        values = value.split()
        if not values:
            values = [value]
        invalid = False
        for item in values:
            if re.fullmatch(r"0(?:\.0+)?", item) or re.fullmatch(
                r"(?:\d+(?:\.\d*)?|\.\d+)px", item, re.IGNORECASE
            ):
                continue
            invalid = True
            break
        if invalid:
            _emit(
                findings,
                profile,
                "unsupported_paragraph_margin",
                "paragraph margins must be unitless zero or non-negative px values.",
                source_object,
            )
        return
    if property_name == "text-decoration":
        if normalized not in {"none", "underline"}:
            _emit(
                findings,
                profile,
                "unsupported_text_decoration",
                "text-decoration must be exactly none or underline.",
                source_object,
            )
        return
    if property_name == "direction" and normalized not in {"ltr", "rtl", "initial"}:
        _emit(
            findings,
            profile,
            "unsupported_text_direction",
            "direction must be ltr, rtl, or initial.",
            source_object,
        )
        return
    if property_name == "text-align" and normalized not in {
        *TEXT_ALIGNMENT_VALUES,
        "start",
        "end",
        "initial",
    }:
        _emit(
            findings,
            profile,
            "unsupported_text_alignment",
            "text-align must be left, center, right, justify, start, end, or initial.",
            source_object,
        )
        return
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
            if _selector_targets_slide(selector, slide) and not _selector_has_preview_token(
                selector
            ):
                width = declarations.get("width", width)
                height = declarations.get("height", height)
        valid_canvases = set(AUTHOR_CANVAS_SIZES)
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
        if not _is_visible_author_element(element, document):
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
        if tag == "a" and element.get("href"):
            _emit(
                findings,
                "author",
                "unsupported_hyperlink",
                "Hyperlink targets are outside the Contract 1.1 native run matrix.",
                _node_path(element),
            )
        if tag == "table":
            table_rows: list[list[dict[str, Any]]] = []
            for row in element.xpath(".//tr"):
                nearest_table = row.xpath("ancestor::table[1]")
                if nearest_table and nearest_table[0] is not element:
                    continue
                cells = row.xpath("./td|./th")
                table_rows.append(
                    [
                        {
                            "rowspan": cell.get("rowspan"),
                            "colspan": cell.get("colspan"),
                            "source_object": _node_path(cell),
                            "text": "".join(cell.itertext()),
                        }
                        for cell in cells
                    ]
                )
            try:
                build_logical_table_grid(
                    table_rows,
                    source_object=_node_path(element),
                )
            except TableTopologyError as exc:
                _emit(
                    findings,
                    "author",
                    exc.code,
                    exc.message,
                    exc.source_object or _node_path(element),
                )

    _check_lists(document, findings)

    for selector, declarations in _stylesheet_rules(document):
        preview_only = _selector_has_preview_token(selector)
        source = f"style:{selector}"
        if selector.strip().lower().startswith("@font-face"):
            # @font-face has no painted DOM target, so the ordinary visible
            # selector probe cannot protect it.  Local/data fonts are allowed
            # as deterministic inputs; network/file-backed font sources are
            # rejected explicitly before they can affect browser measurement.
            for property_name, value in declarations.items():
                classification = _record_css_classification(
                    classifications,
                    "author",
                    property_name,
                    value,
                    source,
                    preview_only=False,
                )
                if (
                    property_name == "src"
                    and _EXTERNAL_URL_RE.search(value)
                    and not value.strip().lower().startswith("data:")
                ):
                    _emit(
                        findings,
                        "author",
                        "external_resource",
                        "External @font-face sources are not deterministic compiler inputs.",
                        source,
                    )
            continue
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
        author_ignored = _is_author_ignored(element)
        ignored = (
            author_ignored
            or _is_hidden(element)
            or _stylesheet_hides_element(document, element)
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
                preview_only=author_ignored,
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
        # The OfficeCLI 1.0.151 parser uses the widescreen point canvas when a
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
            if _officehtml_picture_source(element) is None:
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
            table_nodes = element.xpath(".//table[1]")
            table_root = table_nodes[0] if table_nodes else element
            table_rows: list[list[dict[str, Any]]] = []
            for row in table_root.xpath(".//tr"):
                nearest_table = row.xpath("ancestor::table[1]")
                if nearest_table and nearest_table[0] is not table_root:
                    continue
                table_rows.append(
                    [
                        {
                            "rowspan": cell.get("rowspan"),
                            "colspan": cell.get("colspan"),
                            "source_object": str(
                                cell.get("data-cell-path") or _node_path(cell)
                            ),
                            "text": "".join(cell.itertext()),
                        }
                        for cell in row.xpath("./td|./th")
                    ]
                )
            try:
                build_logical_table_grid(table_rows, source_object=source)
            except TableTopologyError as exc:
                _emit(
                    findings,
                    "officehtml",
                    exc.code,
                    exc.message,
                    exc.source_object or source,
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
                    allow_data_image_background=kind == "picture",
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
        document = _lxml_html.fromstring(
            path.read_text(encoding="utf-8"),
            parser=_officehtml_parser(),
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"Unable to parse HTML input {path}: {exc}") from exc
    findings: list[ContractDiagnostic] = []
    classifications: list[dict[str, Any]] = []
    if profile == "author":
        _check_author(document, findings, classifications)
    else:
        _check_officehtml(document, findings, classifications)
    return ContractReport(str(path), profile, tuple(findings), tuple(classifications))


__all__ = [
    "CONTRACT_VERSION",
    "OFFICECLI_COMPATIBILITY_BASELINE",
    "AUTHOR_CANVAS_SIZES",
    "AUTHOR_PICTURE_SOURCE",
    "AUTHOR_EXTERNAL_RESOURCES_ALLOWED",
    "AUTHOR_TABLE_CELL_SPANS",
    "TableRegion",
    "LogicalTableGrid",
    "TableTopologyError",
    "build_logical_table_grid",
    "SUPPORTED_PROFILES",
    "SUPPORTED_OBJECT_KINDS",
    "SUPPORTED_INLINE_ELEMENTS",
    "CANONICAL_RUN_IDENTITY",
    "CANONICAL_RUN_IDENTITY_FIELDS",
    "MIXED_RUN_ATTRIBUTES",
    "CANONICAL_RUN_POLICY",
    "TEXT_ALIGNMENT_VALUES",
    "TEXT_ALIGNMENT_DEFAULT",
    "TEXT_ALIGNMENT_MAPPING",
    "LINE_HEIGHT_PROPERTY",
    "LINE_HEIGHT_PX_PROJECTION_SCALE",
    "SOURCE_FIDELITY_LINE_SPACING_TEXT",
    "SOURCE_FIDELITY_LINE_SPACING_MIN_FONT_SIZE_PX",
    "PARAGRAPH_SPACING_PROPERTIES",
    "SOFT_WRAP_MODEL",
    "LIST_SURFACE_ELEMENTS",
    "LIST_MARKER_PRESETS",
    "LIST_PARAGRAPH_PROPERTIES",
    "LIST_LEVELS",
    "LIST_ITEM_SOFT_WRAP",
    "LIST_REJECTION_CODES",
    "LIST_REJECTIONS",
    "CSS_CLASSIFICATIONS",
    "CSS_PROPERTY_CLASSIFICATIONS",
    "SUPPORTED_CSS_PROPERTIES",
    "ContractDiagnostic",
    "ContractReport",
    "author_capability_manifest",
    "paragraph_layout_surface",
    "list_surface",
    "check_contract",
]


if __name__ == "__main__":
    raise SystemExit(main())
