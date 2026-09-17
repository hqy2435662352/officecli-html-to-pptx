"""The V0.4.1 PPTX-to-Canonical-Author-HTML projection seam.

This is the one experimental high-level seam the V0.4.1 probe exposes::

    source PPTX + selected source slide numbers
      -> Canonical Author HTML
       + source map
       + projection report
       + structured diagnostics

Everything about how the HTML is produced -- which OfficeCLI read commands are
used, how geometry is normalized, how a locked visual proxy is obtained -- stays
behind this boundary.  The PPTX is the only required presentation input: an
OfficeCLI OfficeHTML export is never read, and no OfficeHTML profile, contract,
or document is produced by this module.

Design commitments this module holds to:

* **Clean fixed-coordinate Author DOM.**  One ``.slide`` per selected source
  slide at the current ``1920x1080`` Author canvas, one canonical object per
  supported source object, and no OfficeCLI viewer wrapper, sidebar, or script.
* **Slide-derived normalization.**  The pixel-per-point factor is derived from
  the source PPTX's own slide bounds, so the standard ``960pt x 540pt`` slide
  becomes exactly ``2px/pt``.  CSS physical-unit conversion is never used.
* **Honest classification.**  Every selected-slide source object receives
  exactly one disposition: ``canonical-editable``, ``locked-visual-proxy``,
  ``base-only-semantic``, ``unsupported``, or ``unresolved``.  A visually
  present object is never declared editable when its PowerPoint semantics were
  not preserved, and whole-slide screenshot fallback is never used.
* **Named source identity.**  Every emitted object carries non-authoritative
  source metadata bound to the source PPTX SHA-256, and the mapping is
  one-to-one in both directions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape as _esc
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .pptx_reader import (
    ALIGNMENT_DEFAULT,
    CANONICAL_GEOMETRIES,
    CONTAINER_KINDS,
    NON_CANONICAL_KINDS,
    BaseOnlyClaim,
    CapturedObject,
    CapturedParagraph,
    CapturedPresentation,
    CapturedSlide,
    CapturedTable,
    IsolatedRenderer,
    MissingSlideError,
    PptxReadError,
    capture_presentation,
)
from ..contract import check_contract

PROJECTION_SCHEMA_VERSION = 1
SOURCE_MAP_SCHEMA_VERSION = 1
PROJECTION_REPORT_SCHEMA_VERSION = 1
AUTHOR_CANVAS_WIDTH_PX = 1920.0
AUTHOR_CANVAS_HEIGHT_PX = 1080.0
DEFAULT_CANVAS_PT = (960.0, 540.0)
# A locked visual proxy is cropped out of the source slide raster with this
# many extra device pixels on each side, so the object's own antialiased edge
# stays inside the image and the emitted element can be offset back to the
# exact source bounds by the same amount.
PROXY_GUARD_PX = 2

# Disposition vocabulary.  Every selected-slide source object receives exactly
# one of these, and the counts are the review surface of the whole probe.
DISPOSITION_CANONICAL = "canonical-editable"
DISPOSITION_LOCKED = "locked-visual-proxy"
DISPOSITION_BASE_ONLY = "base-only-semantic"
DISPOSITION_UNSUPPORTED = "unsupported"
DISPOSITION_UNRESOLVED = "unresolved"
DISPOSITIONS = (
    DISPOSITION_CANONICAL,
    DISPOSITION_LOCKED,
    DISPOSITION_BASE_ONLY,
    DISPOSITION_UNSUPPORTED,
    DISPOSITION_UNRESOLVED,
)

# A locked proxy or an inherited listing is never counted as a native
# round-trip success.
NATIVE_DISPOSITIONS = frozenset({DISPOSITION_CANONICAL})
PROXY_DISPOSITIONS = frozenset({DISPOSITION_LOCKED, DISPOSITION_BASE_ONLY})

PROJECTED_KIND_SHAPE = "shape"
PROJECTED_KIND_TEXTBOX = "textbox"
PROJECTED_KIND_PICTURE = "picture"
PROJECTED_KIND_TABLE = "table"
PROJECTED_KIND_IMAGE = "image"

_INLINE_SEMANTIC = {
    ("bold", "single"): "strong",
    ("italic", "single"): "em",
    ("underline", "single"): "u",
}


class ProjectionError(RuntimeError):
    """A projection could not be produced or published.

    A reader failure is re-raised as this type at the seam, so a caller of
    :func:`project_pptx_to_author_html` only needs one exception family whether
    the failure came from reading the source deck or from publishing the
    result.
    """


class OutputCollisionError(ProjectionError):
    """The requested output destination already exists."""


@dataclass(frozen=True)
class ProjectedObject:
    """One emitted Canonical Author HTML object, mapped to its source object."""

    source_slide: int
    output_slide: int
    source_object: str
    source_kind: str
    source_name: str
    html_id: str
    emitted_ordinal: int
    projected_kind: str
    disposition: str
    reason: str | None
    bounds_pt: tuple[float, float, float, float]
    bounds_px: tuple[float, float, float, float]
    text: str
    capabilities: Mapping[str, bool]
    base_only: tuple[BaseOnlyClaim, ...]
    source_fingerprint: str
    proxy_reason: str | None = None
    proxy_asset: str | None = None
    unsupported_properties: tuple[str, ...] = ()

    @property
    def emitted_name(self) -> str:
        """The object name the New Deck compiler gives this projection slot.

        The compiler names every emitted object ``slide-NNN-<kind>-<ordinal>``
        where NNN is the *output* slide index and the ordinal counts every
        object that slide emitted before it, so the readback is located from
        the projection's own identity rather than by geometry or ordinal
        guessing.
        """
        return (
            f"slide-{self.output_slide:03d}-"
            f"{self.projected_kind}-{self.emitted_ordinal:03d}"
        )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_slide": self.source_slide,
            "output_slide": self.output_slide,
            "source_object": self.source_object,
            "source_kind": self.source_kind,
            "source_name": self.source_name,
            "html_id": self.html_id,
            "emitted_ordinal": self.emitted_ordinal,
            "emitted_name": self.emitted_name,
            "projected_kind": self.projected_kind,
            "disposition": self.disposition,
            "bounds_pt": [round(value, 4) for value in self.bounds_pt],
            "bounds_px": [round(value, 4) for value in self.bounds_px],
            "text": self.text,
            "source_fingerprint": self.source_fingerprint,
            "capabilities": dict(self.capabilities),
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.base_only:
            payload["base_only"] = [claim.as_dict() for claim in self.base_only]
        if self.proxy_reason:
            payload["proxy_reason"] = self.proxy_reason
        if self.proxy_asset:
            payload["proxy_asset"] = self.proxy_asset
        if self.unsupported_properties:
            payload["unsupported_properties"] = list(self.unsupported_properties)
        return payload


@dataclass(frozen=True)
class ProjectionDiagnostic:
    """One structured projection diagnostic."""

    code: str
    severity: str
    message: str
    source_slide: int | None = None
    source_object: str | None = None
    blocking: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "blocking": self.blocking,
        }
        if self.source_slide is not None:
            payload["source_slide"] = self.source_slide
        if self.source_object is not None:
            payload["source_object"] = self.source_object
        return payload


@dataclass(frozen=True)
class ProjectedSlide:
    """One projected slide: its source identity, canvas, and object list."""

    source_slide: int
    html_id: str
    width_px: float
    height_px: float
    background: str
    objects: tuple[ProjectedObject, ...]

    @property
    def native_objects(self) -> tuple[ProjectedObject, ...]:
        return tuple(
            item
            for item in self.objects
            if item.disposition in NATIVE_DISPOSITIONS
        )

    @property
    def proxy_objects(self) -> tuple[ProjectedObject, ...]:
        return tuple(
            item for item in self.objects if item.disposition in PROXY_DISPOSITIONS
        )


@dataclass(frozen=True)
class ProjectionResult:
    """The artifact set and structured projection facts of one probe run."""

    output_html: str
    html_sha256: str | None
    source_map_path: str | None
    source_map_sha256: str | None
    projection_report_path: str | None
    projection_report_sha256: str | None
    source_path: str
    source_sha256: str
    source_slide_size_pt: tuple[float, float]
    source_slide_count: int
    canvas_px: tuple[float, float]
    pixels_per_point: float
    officecli_version: str
    slides: tuple[ProjectedSlide, ...]
    objects: tuple[ProjectedObject, ...]
    source_map: Mapping[str, Any]
    projection_report: Mapping[str, Any]
    diagnostics: tuple[ProjectionDiagnostic, ...]
    published: bool

    @property
    def blocking(self) -> bool:
        return any(item.blocking for item in self.diagnostics)

    @property
    def html_path(self) -> Path:
        return Path(self.output_html)

    def disposition_counts(self) -> dict[str, int]:
        counts = {name: 0 for name in DISPOSITIONS}
        for item in self.objects:
            counts[item.disposition] = counts.get(item.disposition, 0) + 1
        return counts


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text_exact(path: Path, text: str) -> None:
    """Write UTF-8 text without any platform newline translation.

    ``Path.write_text`` opens in text mode, which rewrites ``\\n`` as ``\\r\\n``
    on Windows.  The Author HTML is a hashed artifact, so the file on disk must
    be the exact bytes the source map and projection report describe.
    """
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_dump(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _px(points: float, pixels_per_point: float) -> float:
    return round(points * pixels_per_point, 4)


def _style(pairs: Iterable[tuple[str, str]]) -> str:
    return "; ".join(f"{name}: {value}" for name, value in pairs if value)


def _round_rect_radius_px(obj: CapturedObject, pixels_per_point: float) -> float:
    """Return a rounded rectangle's corner radius.

    PowerPoint's ``roundRect`` default adjust handle is 16.667% of the shorter
    side.  OfficeCLI does not expose a different handle for the probe slides,
    so the canonical object surface reproduces the default; a shape carrying an
    explicit adjust value is treated as an unsupported geometry instead.
    """
    width_px = _px(obj.bounds_pt[2], pixels_per_point)
    height_px = _px(obj.bounds_pt[3], pixels_per_point)
    return round(min(width_px, height_px) * 0.16667, 4)


def _font_stack(family: str) -> str:
    """Return a deterministic CSS font stack for a PowerPoint typeface."""
    name = family.strip()
    if not name:
        return "sans-serif"
    if any(character in name for character in (" ", ",", "'", '"')):
        return f'"{name}", sans-serif'
    return f"{name}, sans-serif"


def _run_text_element(run_text: str, run_style: str, semantic: str) -> str:
    tag = semantic or "span"
    style = f' style="{_esc(run_style, quote=True)}"' if run_style else ""
    return f"<{tag}{style}>{_esc(run_text)}</{tag}>"


def _run_style(
    paragraph: CapturedParagraph,
    run: Any,
    *,
    pixels_per_point: float,
    inherited_family: str,
    inherited_size_pt: float,
    inherited_color: str | None,
    inherited_bold: bool,
    inherited_italic: bool,
) -> tuple[str, str]:
    """Return ``(style, semantic_tag)`` for one run.

    Only the values a run actually overrides are written, so the object's own
    text style remains the inherited value and the emitted DOM stays canonical
    instead of restating the same declaration on every run.
    """
    declarations: list[tuple[str, str]] = []
    if run.font_family and run.font_family != inherited_family:
        declarations.append(("font-family", _font_stack(run.font_family)))
    size_px = _px(run.font_size_pt, pixels_per_point)
    if size_px > 0 and abs(run.font_size_pt - inherited_size_pt) > 0.01:
        declarations.append(("font-size", f"{size_px:g}px"))
    if run.color and run.color.upper() != (inherited_color or "").upper():
        declarations.append(("color", run.color))
    bold = bool(run.bold)
    italic = bool(run.italic)
    underline = str(run.underline or "none").lower() not in {"", "none", "false", "no"}
    if bold != inherited_bold:
        declarations.append(("font-weight", "700" if bold else "400"))
    if italic != inherited_italic:
        declarations.append(("font-style", "italic" if italic else "normal"))
    if underline:
        declarations.append(("text-decoration", "underline"))
    # A bold/italic/underline run is expressed with the canonical inline
    # element whenever the whole run shares that one semantic, which keeps the
    # DOM readable; a mixed run falls back to a styled span.
    semantic = ""
    if not declarations and (bold, italic, underline) != (
        inherited_bold,
        inherited_italic,
        False,
    ):
        if bold and not italic and not underline:
            semantic = "strong"
        elif italic and not bold and not underline:
            semantic = "em"
        elif underline and not bold and not italic:
            semantic = "u"
    return _style(declarations), semantic


def _paragraph_style(paragraph: CapturedParagraph) -> str:
    declarations: list[tuple[str, str]] = []
    align = str(paragraph.align or ALIGNMENT_DEFAULT).lower()
    if align and align not in {ALIGNMENT_DEFAULT, "start"}:
        declarations.append(("text-align", align))
    if paragraph.direction == "rtl":
        declarations.append(("direction", "rtl"))
    return _style(declarations)


def _font_declarations(
    obj: CapturedObject,
    *,
    pixels_per_point: float,
    inherited_size_pt: float,
) -> list[tuple[str, str]]:
    """Return font-size and font-family declarations for one object.

    An explicit font size and the run's own typeface are always written.  A
    text body that omits either would otherwise inherit from the shape, from a
    paragraph, or from the environment's default — and a body authored in a
    CJK face would then draw its Latin characters with a fallback face at a
    different width, reflowing the line the source deck did not wrap.
    """
    declarations: list[tuple[str, str]] = []
    if inherited_size_pt > 0:
        font_size_px = _px(inherited_size_pt, pixels_per_point)
        declarations.append(("font-size", f"{font_size_px:g}px"))
    family = _object_font_family(obj)
    if family:
        declarations.append(("font-family", _font_stack(family)))
    return declarations


def _text_declarations(
    obj: CapturedObject,
    *,
    pixels_per_point: float,
    color: str | None,
    bold: bool,
    italic: bool,
) -> list[tuple[str, str]]:
    """Return the object-level text declarations every run inherits from."""
    declarations = _font_declarations(
        obj,
        pixels_per_point=pixels_per_point,
        inherited_size_pt=_object_font_size_pt(obj),
    )
    if color:
        declarations.append(("color", color))
    if bold:
        declarations.append(("font-weight", "700"))
    if italic:
        declarations.append(("font-style", "italic"))
    line_height = _object_line_height(obj, pixels_per_point=pixels_per_point)
    if line_height:
        declarations.append(("line-height", line_height))
    return declarations


def _object_font_size_pt(obj: CapturedObject) -> float:
    for paragraph in obj.paragraphs:
        for run in paragraph.runs:
            if run.font_size_pt > 0:
                return run.font_size_pt
    from .pptx_reader import length_to_points

    return length_to_points(
        obj.opaque_properties.get("size") or obj.opaque_properties.get("effective.size")
    )


def _object_font_family(obj: CapturedObject) -> str:
    for paragraph in obj.paragraphs:
        for run in paragraph.runs:
            if run.font_family:
                return run.font_family
    fmt = obj.opaque_properties
    return str(
        fmt.get("font.latin")
        or fmt.get("font")
        or fmt.get("effective.font.latin")
        or fmt.get("effective.font")
        or ""
    )


def _object_color(obj: CapturedObject) -> str | None:
    """Return the object's own text color.

    OfficeCLI suppresses the aggregate ``color`` when runs disagree, so the
    object-level value is authoritative whenever it is a plain color and the
    first run is only the fallback for a mixed body.
    """
    from .pptx_reader import parse_color

    fmt = obj.opaque_properties
    aggregate = parse_color(fmt.get("color") or fmt.get("effective.color"))
    if aggregate:
        return aggregate
    for paragraph in obj.paragraphs:
        for run in paragraph.runs:
            if run.color:
                return run.color
    return None


def _object_line_height(
    obj: CapturedObject, *, pixels_per_point: float
) -> str | None:
    """Return the object's CSS line-height, or ``None`` when it is a default.

    Only a line spacing the slide itself declares is emitted.  A spacing that
    OfficeCLI resolved from the master's body style is reported as a base-only
    claim instead, so it is never restated on the rebuilt object as if the
    slide had authored it.
    """
    fmt = obj.opaque_properties
    if "lineSpacing" not in fmt:
        return None
    for paragraph in obj.paragraphs:
        spacing = paragraph.line_spacing
        if spacing and spacing.endswith("x"):
            return f"{float(spacing[:-1]):.4f}"
    raw = fmt.get("lineSpacing")
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text.endswith("x"):
        ratio = float(text[:-1])
        return None if abs(ratio - 1.0) <= 0.01 else f"{ratio:.4f}"
    from .pptx_reader import length_to_points

    points = length_to_points(text)
    return f"{_px(points, pixels_per_point):g}px" if points > 0 else None


def _emit_paragraph_html(
    obj: CapturedObject,
    *,
    pixels_per_point: float,
    inherited_family: str,
    inherited_size_pt: float,
    inherited_color: str | None,
    inherited_bold: bool,
    inherited_italic: bool,
) -> str:
    parts: list[str] = []
    for index, paragraph in enumerate(obj.paragraphs):
        if index:
            parts.append("<br>")
        paragraph_style = _paragraph_style(paragraph)
        runs = list(paragraph.runs)
        if not runs:
            continue
        for run in runs:
            style, semantic = _run_style(
                paragraph,
                run,
                pixels_per_point=pixels_per_point,
                inherited_family=inherited_family,
                inherited_size_pt=inherited_size_pt,
                inherited_color=inherited_color,
                inherited_bold=inherited_bold,
                inherited_italic=inherited_italic,
            )
            element = _run_text_element(run.text, style, semantic)
            if paragraph_style and semantic:
                parts.append(f'<span style="{_esc(paragraph_style, quote=True)}">{element}</span>')
            else:
                parts.append(element)
    return "".join(parts)


def _object_capabilities(obj: CapturedObject) -> dict[str, bool]:
    return {
        "text": obj.has_text and obj.source_kind in {"shape", "textbox"},
        "bounds": True,
        "geometry": obj.geometry in CANONICAL_GEOMETRIES,
        "fill": True,
        "line": True,
        "picture_source": obj.picture is not None,
        "table": obj.table is not None,
        "native_semantics": obj.source_kind not in NON_CANONICAL_KINDS,
    }


def _classify(obj: CapturedObject) -> tuple[str, str | None, tuple[str, ...]]:
    """Return ``(disposition, reason, unsupported_properties)`` for one object.

    The classification reads only what OfficeCLI reported.  A value the slide
    does not own is never silently presented as a slide-owned editable object,
    and an object whose native geometry has no canonical equivalent is never
    declared editable merely because it is visually present.
    """
    if obj.source_kind in NON_CANONICAL_KINDS:
        return (
            DISPOSITION_LOCKED,
            f"OfficeCLI reports {obj.source_kind!r}, which the current Author "
            "object surface cannot reproduce with its native semantics.",
            (),
        )
    if obj.source_kind == "picture":
        if obj.picture is None:
            return (
                DISPOSITION_UNRESOLVED,
                "OfficeCLI reported a picture without a usable embedded source.",
                (),
            )
        if obj.base_only:
            return (
                DISPOSITION_BASE_ONLY,
                "The picture's visible appearance depends on a value the slide "
                "does not own.",
                (),
            )
        return DISPOSITION_CANONICAL, None, ()
    if obj.source_kind == "table":
        if obj.table is None:
            return (
                DISPOSITION_UNRESOLVED,
                "OfficeCLI reported a table without a readable matrix.",
                (),
            )
        merged = [cell for cell in obj.table.cells if cell.merged]
        if merged:
            return (
                DISPOSITION_UNSUPPORTED,
                "Merged table cells are outside the current Author table "
                f"surface ({len(merged)} merged cell(s)).",
                ("merged_cells",),
            )
        if not obj.table.column_widths_pt or len(obj.table.column_widths_pt) != obj.table.columns:
            return (
                DISPOSITION_UNRESOLVED,
                "The table's column widths do not match its reported column count.",
                ("column_widths",),
            )
        if any(width <= 0 for width in obj.table.column_widths_pt):
            return (
                DISPOSITION_UNSUPPORTED,
                "The table reports a non-positive column width.",
                ("column_widths",),
            )
        if any(value <= 0 for value in obj.table.row_heights_pt):
            return (
                DISPOSITION_UNSUPPORTED,
                "The table reports a non-positive row height.",
                ("row_heights",),
            )
        if obj.table.rows * obj.table.columns != len(obj.table.cells):
            return (
                DISPOSITION_UNRESOLVED,
                "The table's cell count does not match its reported matrix.",
                ("cell_matrix",),
            )
        if obj.base_only:
            return (
                DISPOSITION_BASE_ONLY,
                "The table's visible appearance depends on a value the slide "
                "does not own.",
                (),
            )
        return DISPOSITION_CANONICAL, None, ()
    if obj.source_kind in {"shape", "textbox"}:
        if obj.geometry is None:
            return (
                DISPOSITION_LOCKED,
                "OfficeCLI reported no geometry preset for this object, so its "
                "native outline cannot be declared.",
                ("geometry",),
            )
        if obj.geometry not in CANONICAL_GEOMETRIES:
            return (
                DISPOSITION_LOCKED,
                f"The {obj.geometry!r} preset has no canonical Author object "
                "equivalent.",
                ("geometry",),
            )
        if abs(obj.rotation_deg) > 0.01:
            return (
                DISPOSITION_LOCKED,
                "A rotated object's native transform is not part of the "
                "canonical Author object surface.",
                ("rotation",),
            )
        if obj.fill is None and _declares_fill(obj) and not _fill_is_none(obj):
            return (
                DISPOSITION_LOCKED,
                f"The slide fill {obj.opaque_properties.get('fill')!r} is not a "
                "plain solid color.",
                ("fill",),
            )
        if obj.line_color is None and _declares_line(obj) and not _line_is_none(obj):
            return (
                DISPOSITION_LOCKED,
                f"The slide outline {obj.opaque_properties.get('line')!r} is not "
                "a plain solid color.",
                ("line",),
            )
        if obj.base_only:
            return (
                DISPOSITION_BASE_ONLY,
                "The object's visible text appearance depends on a value the "
                "slide does not own: "
                + ", ".join(sorted(obj.base_only_properties)),
                (),
            )
        return DISPOSITION_CANONICAL, None, ()
    return (
        DISPOSITION_LOCKED,
        f"OfficeCLI reports {obj.source_kind!r}, which has no canonical Author "
        "object mapping.",
        (),
    )


def _declares_fill(obj: CapturedObject) -> bool:
    return "fill" in obj.opaque_properties


def _fill_is_none(obj: CapturedObject) -> bool:
    return str(obj.opaque_properties.get("fill", "")).strip().lower() in {
        "none",
        "transparent",
    }


def _declares_line(obj: CapturedObject) -> bool:
    return "line" in obj.opaque_properties


def _line_is_none(obj: CapturedObject) -> bool:
    return str(obj.opaque_properties.get("line", "")).strip().lower() in {
        "none",
        "transparent",
    }


def _requires_proxy(obj: CapturedObject, disposition: str) -> bool:
    """Whether a visible object needs an object-local visual representation."""
    if disposition in {DISPOSITION_LOCKED, DISPOSITION_BASE_ONLY}:
        return True
    return False


def _proxy_crop_pixels(
    crop: tuple[float, float, float, float],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    """Return the retained inner box of a cropped image in pixels."""
    left_pct, top_pct, right_pct, bottom_pct = crop
    width, height = image_size
    left = int(round(left_pct * width))
    top = int(round(top_pct * height))
    right = width - int(round(right_pct * width))
    bottom = height - int(round(bottom_pct * height))
    left = max(0, min(left, width - 1))
    top = max(0, min(top, height - 1))
    right = max(left + 1, min(right, width))
    bottom = max(top + 1, min(bottom, height))
    return left, top, right, bottom


def _cropped_picture_source(obj: CapturedObject) -> tuple[str, dict[str, Any]]:
    """Return a deterministic data URI whose content is the cropped picture.

    PowerPoint applies a picture's source rectangle at paint time.  The
    canonical Author picture surface has no source-rectangle property, so the
    retained content is baked into the emitted media instead of being silently
    dropped.  The projection report records that the source rectangle became a
    baked crop rather than a native ``srcRect``.
    """
    picture = obj.picture
    assert picture is not None
    evidence: dict[str, Any] = {
        "content_type": picture.content_type,
        "media_part": picture.media_part,
        "content_fingerprint": picture.content_fingerprint,
        "source_rect": list(picture.source_rect) if picture.source_rect else None,
        "crop_raw": picture.crop_raw,
    }
    if picture.source_rect is None:
        evidence["source_rect_handling"] = "none-declared"
        return picture.data_uri, evidence

    import base64
    import io
    from PIL import Image

    header, _, payload = picture.data_uri.partition(",")
    mime = header[5:].split(";", 1)[0]
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, TypeError) as exc:
        raise ProjectionError(
            f"Picture {obj.source_object} on slide {obj.source_slide} has an "
            f"undecodable embedded source: {exc}"
        ) from exc
    if mime == "image/svg+xml":
        evidence["source_rect_handling"] = "unsupported-vector-source"
        return picture.data_uri, evidence

    from PIL import ImageOps

    with Image.open(io.BytesIO(raw)) as image:
        oriented = ImageOps.exif_transpose(image)
        box = _proxy_crop_pixels(picture.source_rect, oriented.size)
        cropped = oriented.crop(box)
        if cropped.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
            cropped = cropped.convert("RGBA")
        buffer = io.BytesIO()
        cropped.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    evidence.update(
        {
            "source_rect_handling": "baked-into-emitted-media",
            "original_size_px": [int(oriented.size[0]), int(oriented.size[1])],
            "cropped_size_px": [int(cropped.size[0]), int(cropped.size[1])],
            "cropped_fingerprint": hashlib.sha256(buffer.getvalue()).hexdigest(),
        }
    )
    return "data:image/png;base64," + encoded, evidence


def _emit_object_html(
    obj: CapturedObject,
    *,
    projected: ProjectedObject,
    pixels_per_point: float,
    proxy_source: str | None,
) -> str:
    """Return the canonical Author DOM for one projected object."""
    bounds_px = projected.bounds_px
    common = (
        ("position", "absolute"),
        ("left", f"{bounds_px[0]:g}px"),
        ("top", f"{bounds_px[1]:g}px"),
        ("width", f"{bounds_px[2]:g}px"),
        ("height", f"{bounds_px[3]:g}px"),
    )
    identity = [
        ("data-source-slide", str(obj.source_slide)),
        ("data-source-object", obj.source_object),
        ("data-source-kind", obj.source_kind),
        ("data-projection-disposition", projected.disposition),
        ("data-projection-id", projected.html_id),
    ]
    attributes = " ".join(
        f'{name}="{_esc(value, quote=True)}"' for name, value in identity
    )
    image_style = _esc(_style([*common, ("object-fit", "fill")]), quote=True)
    proxy_style = _esc(
        _style(
            [
                (
                    "position",
                    "absolute",
                ),
                ("left", f"{bounds_px[0] - PROXY_GUARD_PX:g}px"),
                ("top", f"{bounds_px[1] - PROXY_GUARD_PX:g}px"),
                ("width", f"{bounds_px[2] + PROXY_GUARD_PX * 2:g}px"),
                ("height", f"{bounds_px[3] + PROXY_GUARD_PX * 2:g}px"),
                ("object-fit", "fill"),
            ]
        ),
        quote=True,
    )

    if projected.projected_kind == PROJECTED_KIND_PICTURE and obj.picture is not None:
        source, _ = _cropped_picture_source(obj)
        return (
            f'<img id="{projected.html_id}" {attributes} alt="" '
            f'src="{_esc(source, quote=True)}" style="{image_style}">'
        )

    if projected.projected_kind == PROJECTED_KIND_TABLE and obj.table is not None:
        return _emit_table_html(
            obj, projected=projected, pixels_per_point=pixels_per_point
        )

    if projected.projected_kind == PROJECTED_KIND_IMAGE and proxy_source:
        locked = _locked_attributes(projected)
        return (
            f'<img id="{projected.html_id}" {attributes}{locked} '
            f'alt="" src="{_esc(proxy_source, quote=True)}" style="{proxy_style}">'
        )

    return _emit_shape_html(
        obj,
        projected=projected,
        pixels_per_point=pixels_per_point,
        identity=identity,
    )


def _locked_attributes(projected: ProjectedObject) -> str:
    """Return the locked-proxy attributes, each already space-prefixed.

    The same two attributes are written on a proxy ``<img>`` and on a placeholder
    ``<div>``; building them once keeps the two emitters from drifting apart.
    """
    rendered = ""
    if projected.disposition in {DISPOSITION_LOCKED, DISPOSITION_BASE_ONLY}:
        rendered += ' data-projection-locked="true"'
    if projected.reason:
        rendered += f' data-projection-reason="{_esc(projected.reason, quote=True)}"'
    return rendered
    return f'data-projection-reason="{_esc(projected.reason, quote=True)}" '


def _emit_shape_html(
    obj: CapturedObject,
    *,
    projected: ProjectedObject,
    pixels_per_point: float,
    identity: list[tuple[str, str]],
) -> str:
    declarations: list[tuple[str, str]] = [
        ("position", "absolute"),
        ("left", f"{projected.bounds_px[0]:g}px"),
        ("top", f"{projected.bounds_px[1]:g}px"),
        ("width", f"{projected.bounds_px[2]:g}px"),
        ("height", f"{projected.bounds_px[3]:g}px"),
    ]
    # A text body must not soft-wrap where the source did not: the source
    # object's own bounds already encode the authored break, and a browser wrap
    # would silently repartition the paragraph into extra native paragraphs.
    # It is deliberately not clipped either: PowerPoint paints an oversized
    # no-autofit line outside its shape, so clipping here would hide text the
    # source deck shows.
    if obj.has_text:
        declarations.append(("white-space", "pre"))
    if obj.fill:
        declarations.append(("background-color", obj.fill))
    if obj.line_color and obj.line_width_pt > 0:
        width_px = _px(obj.line_width_pt, pixels_per_point)
        declarations.append(("border", f"{width_px:g}px solid {obj.line_color}"))
    if obj.geometry == "roundRect":
        declarations.append(
            ("border-radius", f"{_round_rect_radius_px(obj, pixels_per_point):g}px")
        )
    if obj.rotation_deg:
        declarations.append(("transform", f"rotate({obj.rotation_deg:g}deg)"))
    # The shape's own vertical anchor is deliberately not re-created with a
    # flex box: a flex container dissolves the paragraph into anonymous items
    # and the compiler's paragraph/run collection no longer sees one text body.
    # Keeping the canonical object block-level preserves the paragraph and run
    # structure, and the vertical anchor is outside the Contract's declared
    # capability surface.

    family = _object_font_family(obj)
    size_pt = _object_font_size_pt(obj)
    color = _object_color(obj)
    first_runs = obj.paragraphs[0].runs if obj.paragraphs else ()
    inherited_bold = bool(first_runs[0].bold) if first_runs else bool(
        obj.opaque_properties.get("bold")
    )
    inherited_italic = bool(first_runs[0].italic) if first_runs else bool(
        obj.opaque_properties.get("italic")
    )
    declarations.extend(
        _text_declarations(
            obj,
            pixels_per_point=pixels_per_point,
            color=color,
            bold=inherited_bold,
            italic=inherited_italic,
        )
    )

    align = (
        str(obj.paragraphs[0].align or "").lower()
        if obj.paragraphs
        else str(obj.opaque_properties.get("align", "") or "").lower()
    )
    if align and align not in {ALIGNMENT_DEFAULT, "start"}:
        declarations.append(("text-align", align))
    if str(obj.opaque_properties.get("direction", "") or "").lower() == "rtl":
        declarations.append(("direction", "rtl"))

    body = ""
    if obj.has_text:
        body = _emit_paragraph_html(
            obj,
            pixels_per_point=pixels_per_point,
            inherited_family=family,
            inherited_size_pt=size_pt,
            inherited_color=color,
            inherited_bold=inherited_bold,
            inherited_italic=inherited_italic,
        )
    elif projected.disposition in {DISPOSITION_UNSUPPORTED, DISPOSITION_UNRESOLVED}:
        # An unresolved object keeps its source identity in the workbench but
        # paints nothing, so it can never be mistaken for supported content.
        declarations.append(("display", "none"))

    attributes = " ".join(
        f'{name}="{_esc(value, quote=True)}"' for name, value in identity
    )
    if projected.disposition in {DISPOSITION_LOCKED, DISPOSITION_BASE_ONLY}:
        attributes += ' data-projection-locked="true"'
    if projected.reason:
        attributes += f' data-projection-reason="{_esc(projected.reason, quote=True)}"'
    return (
        f'<div id="{projected.html_id}" {attributes} '
        f'style="{_esc(_style(declarations), quote=True)}">{body}</div>'
    )


def _emit_table_html(
    obj: CapturedObject,
    *,
    projected: ProjectedObject,
    pixels_per_point: float,
) -> str:
    table = obj.table
    assert table is not None
    bounds_px = projected.bounds_px
    identity = " ".join(
        f'{name}="{_esc(value, quote=True)}"'
        for name, value in (
            ("data-source-slide", str(obj.source_slide)),
            ("data-source-object", obj.source_object),
            ("data-source-kind", obj.source_kind),
            ("data-projection-disposition", projected.disposition),
            ("data-projection-id", projected.html_id),
        )
    )
    wrapper_style = _style(
        [
            ("position", "absolute"),
            ("left", f"{bounds_px[0]:g}px"),
            ("top", f"{bounds_px[1]:g}px"),
            ("width", f"{bounds_px[2]:g}px"),
            ("height", f"{bounds_px[3]:g}px"),
            ("border-collapse", "collapse"),
            ("table-layout", "fixed"),
        ]
    )
    table_style = _style(
        [
            ("width", f"{bounds_px[2]:g}px"),
            ("border-collapse", "collapse"),
            ("table-layout", "fixed"),
            ("background-color", "#FFFFFF"),
        ]
    )
    columns = "".join(
        f'<col style="width: {_px(width, pixels_per_point):g}px">'
        for width in table.column_widths_pt
    )
    rows: list[str] = []
    for row_index in range(1, table.rows + 1):
        height_px = _px(
            table.row_heights_pt[row_index - 1]
            if row_index - 1 < len(table.row_heights_pt)
            else 0.0,
            pixels_per_point,
        )
        cells: list[str] = []
        for column_index in range(1, table.columns + 1):
            cell = table.cell(row_index, column_index)
            if cell is None:
                raise ProjectionError(
                    f"Table {obj.source_object} on slide {obj.source_slide} has "
                    f"no captured cell at row {row_index}, column {column_index}."
                )
            cells.append(_emit_table_cell(obj, cell, pixels_per_point=pixels_per_point))
        rows.append(
            f'<tr data-row="{row_index}" style="height: {height_px:g}px">'
            + "".join(cells)
            + "</tr>"
        )
    return (
        f'<div id="{projected.html_id}" {identity} '
        f'style="{_esc(wrapper_style, quote=True)}">'
        f'<table style="{_esc(table_style, quote=True)}">'
        f"<colgroup>{columns}</colgroup>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


def _emit_table_cell(
    obj: CapturedObject, cell: Any, *, pixels_per_point: float
) -> str:
    """Return one canonical table cell with its own text and borders."""
    from .pptx_reader import parse_color

    declarations: list[tuple[str, str]] = []
    if cell.fill:
        declarations.append(("background-color", cell.fill))
    border = None
    for key, value in (obj.table.borders if obj.table else {}).items():
        parsed = parse_color(str(value).split()[-1]) if value else None
        width = str(value).split()[0] if value else ""
        if parsed and key in {"border.all", "border.top", "border.left"}:
            border = (width, parsed)
            break
    if border is not None:
        from .pptx_reader import length_to_points

        width_px = _px(length_to_points(border[0]), pixels_per_point)
        if width_px > 0:
            declarations.append(("border", f"{width_px:g}px solid {border[1]}"))
    if cell.paragraphs:
        first = cell.paragraphs[0]
        align = str(first.align or ALIGNMENT_DEFAULT).lower()
        if align and align not in {ALIGNMENT_DEFAULT, "start"}:
            declarations.append(("text-align", align))
    size_pt = 0.0
    family = ""
    color = None
    bold = False
    italic = False
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            if run.font_size_pt and not size_pt:
                size_pt = run.font_size_pt
            if run.font_family and not family:
                family = run.font_family
            if run.color and not color:
                color = run.color
            bold = bold or bool(run.bold)
            italic = italic or bool(run.italic)
    if size_pt > 0:
        declarations.append(("font-size", f"{_px(size_pt, pixels_per_point):g}px"))
    if family:
        declarations.append(("font-family", _font_stack(family)))
    if color:
        declarations.append(("color", color))
    if bold:
        declarations.append(("font-weight", "700"))
    if italic:
        declarations.append(("font-style", "italic"))

    body_parts: list[str] = []
    for index, paragraph in enumerate(cell.paragraphs):
        if index:
            body_parts.append("<br>")
        for run in paragraph.runs:
            style, semantic = _run_style(
                paragraph,
                run,
                pixels_per_point=pixels_per_point,
                inherited_family=family,
                inherited_size_pt=size_pt,
                inherited_color=color,
                inherited_bold=bold,
                inherited_italic=italic,
            )
            body_parts.append(_run_text_element(run.text, style, semantic))
    body = "".join(body_parts)
    if not body:
        body = "".join(
            _esc(run.text)
            for paragraph in cell.paragraphs
            for run in paragraph.runs
        )
    attributes = (
        f'data-cell-path="{_esc(f"{obj.source_object}/tr[{cell.row}]/tc[{cell.column}]", quote=True)}" '
        f'data-cell-row="{cell.row}" data-cell-column="{cell.column}"'
    )
    return (
        f"<td {attributes} "
        f'style="{_esc(_style(declarations), quote=True)}">{body}</td>'
    )


def _slide_background_style(slide: CapturedSlide) -> str:
    if slide.background:
        return f"background-color: {slide.background};"
    return "background-color: #FFFFFF;"


def _document_html(
    *,
    source_name: str,
    source_sha256: str,
    slides: Sequence[CapturedSlide],
    projected_slides: Sequence[ProjectedSlide],
    object_html: Mapping[str, str],
    canvas_px: tuple[float, float],
    pixels_per_point: float,
) -> str:
    sections: list[str] = []
    for slide, projected in zip(slides, projected_slides):
        objects = "".join(
            object_html[item.html_id] for item in projected.objects
        )
        sections.append(
            f'<section class="slide" '
            f'data-source-slide="{slide.source_slide}" '
            f'data-slide-number="{slide.source_slide}" '
            f'style="position: relative; width: {canvas_px[0]:g}px; '
            f'height: {canvas_px[1]:g}px; overflow: hidden; '
            f'{_slide_background_style(slide)}">'
            f"{objects}</section>"
        )
    style = (
        "* { box-sizing: border-box; }\n"
        "html, body { margin: 0; padding: 0; background: #1f2227; }\n"
        ".slide { margin: 0 auto 24px auto; }\n"
        ".slide:first-of-type { margin-top: 0; }\n"
    )
    script = (
        "<script>\n"
        "(function () {\n"
        "  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));\n"
        "  var current = 0;\n"
        "  function show(index) {\n"
        "    current = Math.max(0, Math.min(slides.length - 1, index));\n"
        "    slides.forEach(function (slide, i) { slide.style.display = i === current ? 'block' : 'none'; });\n"
        "  }\n"
        "  window.addEventListener('keydown', function (event) {\n"
        "    if (['ArrowRight', 'PageDown', ' '].indexOf(event.key) !== -1) show(current + 1);\n"
        "    if (['ArrowLeft', 'PageUp'].indexOf(event.key) !== -1) show(current - 1);\n"
        "    if (event.key === 'Home') show(0);\n"
        "    if (event.key === 'End') show(slides.length - 1);\n"
        "  });\n"
        "  show(0);\n"
        "})();\n"
        "</script>"
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>Canonical Author HTML projection</title>\n"
        "<style>\n"
        f"{style}"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f'<div id="canonical-author-projection" '
        f'data-source-name="{_esc(source_name, quote=True)}" '
        f'data-source-sha256="{_esc(source_sha256, quote=True)}" '
        f'data-projection-schema="{PROJECTION_SCHEMA_VERSION}" '
        f'data-projection-canvas="{canvas_px[0]:g}x{canvas_px[1]:g}" '
        f'data-projection-pixels-per-point="{pixels_per_point:g}">\n'
        + "\n".join(sections)
        + "\n</div>\n"
        f"{script}\n"
        "</body>\n"
        "</html>\n"
    )


def _source_map_payload(
    *,
    source_path: str,
    source_sha256: str,
    source_slide_count: int,
    canvas_px: tuple[float, float],
    pixels_per_point: float,
    objects: Sequence[ProjectedObject],
    slides: Sequence[ProjectedSlide],
) -> dict[str, Any]:
    entries = [
        {
            "source_slide": item.source_slide,
            "source_object": item.source_object,
            "source_kind": item.source_kind,
            "source_name": item.source_name,
            "source_fingerprint": item.source_fingerprint,
            "html_id": item.html_id,
            "emitted_ordinal": item.emitted_ordinal,
            "emitted_name": item.emitted_name,
            "html_selector": f"#{item.html_id}",
            "projected_kind": item.projected_kind,
            "disposition": item.disposition,
            "capabilities": dict(item.capabilities),
            "bounds_pt": [round(value, 4) for value in item.bounds_pt],
            "bounds_px": [round(value, 4) for value in item.bounds_px],
            "base_only": [claim.as_dict() for claim in item.base_only],
            "proxy_reason": item.proxy_reason,
            "proxy_asset": item.proxy_asset,
        }
        for item in objects
    ]
    return {
        "schema_version": SOURCE_MAP_SCHEMA_VERSION,
        "source": {
            "path": source_path,
            "sha256": source_sha256,
            "slide_count": source_slide_count,
        },
        "canvas": {
            "width_px": canvas_px[0],
            "height_px": canvas_px[1],
            "pixels_per_point": pixels_per_point,
        },
        "slides": [
            {
                "source_slide": slide.source_slide,
                "html_id": slide.html_id,
                "html_selector": f"#{slide.html_id}",
                "object_count": len(slide.objects),
            }
            for slide in slides
        ],
        "objects": entries,
    }


def _projection_report_payload(
    *,
    source_path: str,
    source_sha256: str,
    source_slide_count: int,
    source_slide_size_pt: tuple[float, float],
    canvas_px: tuple[float, float],
    pixels_per_point: float,
    officecli_version: str,
    slides: Sequence[ProjectedSlide],
    objects: Sequence[ProjectedObject],
    diagnostics: Sequence[ProjectionDiagnostic],
    html_sha256: str | None,
) -> dict[str, Any]:
    counts = {name: 0 for name in DISPOSITIONS}
    for item in objects:
        counts[item.disposition] = counts.get(item.disposition, 0) + 1
    native = counts[DISPOSITION_CANONICAL]
    locks = counts[DISPOSITION_LOCKED] + counts[DISPOSITION_BASE_ONLY]
    return {
        "schema_version": PROJECTION_REPORT_SCHEMA_VERSION,
        "source": {
            "path": source_path,
            "sha256": source_sha256,
            "slide_count": source_slide_count,
            "slide_size_pt": list(source_slide_size_pt),
        },
        "canvas": {
            "width_px": canvas_px[0],
            "height_px": canvas_px[1],
            "pixels_per_point": pixels_per_point,
            "canvas_source": "pptx-slide-bounds",
        },
        "officecli_version": officecli_version,
        "selected_slides": [slide.source_slide for slide in slides],
        "counts": {
            "source_objects": len(objects),
            "canonical_editable": native,
            "locked_visual_proxy": counts[DISPOSITION_LOCKED],
            "base_only_semantic": counts[DISPOSITION_BASE_ONLY],
            "unsupported": counts[DISPOSITION_UNSUPPORTED],
            "unresolved": counts[DISPOSITION_UNRESOLVED],
            "native_round_trip": native,
            "excluded_from_native_round_trip": locks
            + counts[DISPOSITION_UNSUPPORTED]
            + counts[DISPOSITION_UNRESOLVED],
        },
        "whole_slide_screenshot_fallback": False,
        "author_html_sha256": html_sha256,
        "slides": [
            {
                "source_slide": slide.source_slide,
                "html_id": slide.html_id,
                "object_count": len(slide.objects),
                "canonical_editable": len(slide.native_objects),
                "locked_or_base_only": len(slide.proxy_objects),
                "objects": [item.as_dict() for item in slide.objects],
            }
            for slide in slides
        ],
        "diagnostics": [item.as_dict() for item in diagnostics],
    }


def _unique_html_id(source_slide: int, ordinal: int, source_object: str) -> str:
    slug = "".join(
        character if character.isalnum() else "-" for character in source_object
    ).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"s{source_slide:03d}-o{ordinal:03d}-{slug or 'object'}"


def _build_projection(
    capture: CapturedPresentation,
    *,
    source_sha256: str,
    proxy_dir: Path | None,
) -> tuple[
    list[CapturedSlide],
    list[ProjectedSlide],
    dict[str, str],
    list[ProjectionDiagnostic],
    float,
]:
    """Turn a PowerPoint Object Capture into canonical Author HTML fragments."""
    width_pt, height_pt = capture.slide_size_pt
    # The pixels-per-point factor is derived from the source PPTX's own slide
    # bounds.  The standard 960x540pt widescreen slide therefore becomes
    # exactly 2px/pt; CSS physical-unit conversion is never used.
    pixels_per_point = AUTHOR_CANVAS_WIDTH_PX / width_pt

    canvas_px = (
        _px(width_pt, pixels_per_point),
        _px(height_pt, pixels_per_point),
    )
    if abs(canvas_px[0] - AUTHOR_CANVAS_WIDTH_PX) > 0.5 or abs(
        canvas_px[1] - AUTHOR_CANVAS_HEIGHT_PX
    ) > 0.5:
        # The Author Contract accepts exactly the 1920x1080 canvas (or the legacy
        # 960x540), and the New Deck compiler measures against that slide.  A
        # differently proportioned deck cannot be normalized onto it without
        # either distorting the layout or discarding the scale factors just
        # derived from the deck's own bounds.  Refuse it rather than silently
        # snapping the canvas and contradicting the source geometry.
        raise ProjectionError(
            "The source deck's slides are "
            f"{width_pt:g}pt x {height_pt:g}pt, which normalizes to "
            f"{canvas_px[0]:g}px x {canvas_px[1]:g}px at "
            f"{pixels_per_point:g}px/pt and does not match the current Author "
            f"canvas of {AUTHOR_CANVAS_WIDTH_PX:g}px x "
            f"{AUTHOR_CANVAS_HEIGHT_PX:g}px. This probe is scoped to 16:9 decks; "
            "a different aspect ratio is its own canvas decision."
        )

    diagnostics: list[ProjectionDiagnostic] = []
    # Object-local proxies come from a render in which the target object is the
    # only object on its slide, so a proxy can never carry a sibling's content.
    renderer = (
        IsolatedRenderer(capture.source_path, proxy_dir / "isolated")
        if proxy_dir is not None
        else None
    )
    projected_slides: list[ProjectedSlide] = []
    object_html: dict[str, str] = {}
    html_objects: list[ProjectedObject] = []

    for output_slide, slide in enumerate(capture.slides, start=1):
        slide_objects: list[ProjectedObject] = []
        for ordinal, obj in enumerate(slide.objects, start=1):
            disposition, reason, unsupported = _classify(obj)
            proxy_source: str | None = None
            proxy_reason: str | None = None
            proxy_asset: str | None = None
            projected_kind = _projected_kind(obj, disposition)

            if _requires_proxy(obj, disposition):
                proxy_reason = reason or "locked projection"
                if proxy_dir is None:
                    diagnostics.append(
                        ProjectionDiagnostic(
                            code="proxy_assets_unavailable",
                            severity="error",
                            message=(
                                "An object-local visual proxy is required but no "
                                "proxy asset directory was provided."
                            ),
                            source_slide=obj.source_slide,
                            source_object=obj.source_object,
                            blocking=True,
                        )
                    )
                    disposition = DISPOSITION_UNRESOLVED
                    reason = "No object-local visual representation is available."
                    projected_kind = PROJECTED_KIND_SHAPE
                else:
                    try:
                        assert renderer is not None
                        proxy_source, asset = _isolated_proxy(
                            renderer,
                            obj,
                            pixels_per_point=pixels_per_point,
                            destination=proxy_dir
                            / f"proxy-slide-{obj.source_slide:03d}-{ordinal:03d}.png",
                        )
                        proxy_asset = str(asset.resolve())
                    except (PptxReadError, ProjectionError, OSError, ValueError) as exc:
                        diagnostics.append(
                            ProjectionDiagnostic(
                                code="proxy_isolation_unavailable",
                                severity="warning",
                                message=(
                                    "No object-local visual representation could be "
                                    f"produced, so the object is reported unsupported "
                                    f"rather than approximated: {exc}"
                                ),
                                source_slide=obj.source_slide,
                                source_object=obj.source_object,
                                blocking=False,
                            )
                        )
                        disposition = DISPOSITION_UNSUPPORTED
                        reason = (
                            "No object-local visual representation is available: "
                            f"{exc} A composited crop is not object-local and is "
                            "never used as a substitute."
                        )
                        # The proxy reason is what a reviewer reads, so keep the
                        # explanation instead of clearing it with the proxy.
                        proxy_reason = reason
                        projected_kind = PROJECTED_KIND_SHAPE

            html_id = _unique_html_id(obj.source_slide, ordinal, obj.source_object)
            bounds_px = (
                _px(obj.bounds_pt[0], pixels_per_point),
                _px(obj.bounds_pt[1], pixels_per_point),
                _px(obj.bounds_pt[2], pixels_per_point),
                _px(obj.bounds_pt[3], pixels_per_point),
            )
            projected = ProjectedObject(
                source_slide=obj.source_slide,
                output_slide=output_slide,
                source_object=obj.source_object,
                source_kind=obj.source_kind,
                source_name=obj.name,
                html_id=html_id,
                emitted_ordinal=ordinal,
                projected_kind=projected_kind,
                disposition=disposition,
                reason=reason,
                bounds_pt=obj.bounds_pt,
                bounds_px=bounds_px,
                text=obj.text,
                capabilities=_object_capabilities(obj),
                base_only=obj.base_only,
                source_fingerprint=obj.fingerprint(),
                proxy_reason=proxy_reason if proxy_source else None,
                proxy_asset=proxy_asset,
                unsupported_properties=unsupported,
            )
            object_html[html_id] = _emit_object_html(
                obj,
                projected=projected,
                pixels_per_point=pixels_per_point,
                proxy_source=proxy_source,
            )
            slide_objects.append(projected)
            html_objects.append(projected)
            if disposition in {DISPOSITION_UNSUPPORTED, DISPOSITION_UNRESOLVED}:
                diagnostics.append(
                    ProjectionDiagnostic(
                        code=(
                            "unsupported_source_object"
                            if disposition == DISPOSITION_UNSUPPORTED
                            else "unresolved_source_object"
                        ),
                        severity="warning",
                        message=reason or "The source object was not projected.",
                        source_slide=obj.source_slide,
                        source_object=obj.source_object,
                        blocking=False,
                    )
                )
            if obj.children:
                for child in _walk_children(obj):
                    diagnostics.append(
                        ProjectionDiagnostic(
                            code="nested_container_object",
                            severity="info",
                            message=(
                                f"A nested {child.source_kind!r} object is owned "
                                f"by {obj.source_kind} {obj.source_object} and is "
                                "represented by that container's locked proxy."
                            ),
                            source_slide=child.source_slide,
                            source_object=child.source_object,
                            blocking=False,
                        )
                    )

        projected_slides.append(
            ProjectedSlide(
                source_slide=slide.source_slide,
                html_id=f"slide-{slide.source_slide:03d}",
                width_px=canvas_px[0],
                height_px=canvas_px[1],
                background=slide.background or "#FFFFFF",
                objects=tuple(slide_objects),
            )
        )

    return (
        list(capture.slides),
        projected_slides,
        object_html,
        diagnostics,
        pixels_per_point,
    )


def _walk_children(obj: CapturedObject) -> Iterable[CapturedObject]:
    for child in obj.children:
        yield child
        yield from _walk_children(child)


def _projected_kind(obj: CapturedObject, disposition: str) -> str:
    """Return the canonical Author object kind a source object projects to."""
    if obj.source_kind == "picture":
        return PROJECTED_KIND_PICTURE
    if obj.source_kind == "table":
        return PROJECTED_KIND_TABLE
    if disposition in {DISPOSITION_LOCKED, DISPOSITION_BASE_ONLY}:
        return PROJECTED_KIND_IMAGE
    if obj.has_text and obj.fill is None and (
        obj.line_color is None or obj.line_width_pt <= 0
    ):
        return PROJECTED_KIND_TEXTBOX
    return PROJECTED_KIND_SHAPE


def _isolated_proxy(
    renderer: IsolatedRenderer,
    obj: CapturedObject,
    *,
    pixels_per_point: float,
    destination: Path,
) -> tuple[str, Path]:
    """Return a deterministic data URI for one object-local locked proxy.

    The proxy comes from a render of the target object *alone* -- rebuilt into a
    fresh deck, so neither a sibling nor the slide's layout and master paint can
    appear in it.  Cropping the composited slide, or culling only the slide's
    siblings from a copy, would both let other paint into the rectangle.
    """
    import base64
    import tempfile

    media_path: Path | None = None
    if obj.picture is not None:
        # OfficeCLI takes a picture source as a path or a data URI; a file keeps
        # the batch body small and is written outside the source deck.
        header, _, payload = obj.picture.data_uri.partition(",")
        suffix = "." + header[5:].split(";", 1)[0].split("/")[-1].replace("+xml", "")
        handle, name = tempfile.mkstemp(
            prefix="projection-media-", suffix=suffix, dir=str(destination.parent)
        )
        media_path = Path(name)
        with open(handle, "wb") as stream:
            stream.write(base64.b64decode(payload))

    try:
        asset = renderer.render(
            obj.source_slide,
            obj.source_object,
            obj.bounds_pt,
            object_kind=obj.source_kind,
            properties=obj.opaque_properties,
            pixels_per_point=pixels_per_point,
            destination=destination,
            media_path=media_path,
            guard_px=PROXY_GUARD_PX,
        )
    finally:
        if media_path is not None:
            media_path.unlink(missing_ok=True)
    return (
        "data:image/png;base64," + base64.b64encode(asset.read_bytes()).decode("ascii"),
        asset,
    )


def project_pptx_to_author_html(
    source_pptx: str | Path,
    source_slide_numbers: Sequence[int],
    output_html: str | Path,
    *,
    proxy_dir: str | Path | None = None,
) -> ProjectionResult:
    """Project selected slides of one PPTX into Canonical Author HTML.

    This is the one experimental high-level seam of the V0.4.1 probe.  It reads
    the source PPTX through OfficeCLI, emits the Canonical Author HTML document
    plus its source map and projection report, and returns the structured
    projection facts.  The source deck is never modified, and an existing
    output target is a collision rather than an overwrite.
    """
    source_path = Path(source_pptx).expanduser().resolve()
    destination = Path(output_html).expanduser().resolve()
    if not source_path.is_file():
        raise ProjectionError(f"Source PPTX does not exist: {source_path}")
    if destination.exists():
        raise OutputCollisionError(
            f"Projection output already exists: {destination}"
        )
    if not destination.parent.is_dir():
        raise ProjectionError(
            f"Projection output directory does not exist: {destination.parent}"
        )
    proxy_directory = (
        Path(proxy_dir).expanduser().resolve() if proxy_dir is not None else None
    )
    source_sha256 = _sha256_file(source_path)

    if not source_slide_numbers:
        raise ProjectionError(
            "A projection must select at least one source slide number."
        )
    capture = capture_presentation(source_path, source_slide_numbers)
    if proxy_directory is not None:
        proxy_directory.mkdir(parents=True, exist_ok=True)

    slides, projected_slides, object_html, diagnostics, pixels_per_point = (
        _build_projection(
            capture,
            source_sha256=source_sha256,
            proxy_dir=proxy_directory,
        )
    )
    canvas_px = (
        projected_slides[0].width_px if projected_slides else AUTHOR_CANVAS_WIDTH_PX,
        projected_slides[0].height_px if projected_slides else AUTHOR_CANVAS_HEIGHT_PX,
    )
    html_text = _document_html(
        source_name=source_path.name,
        source_sha256=source_sha256,
        slides=slides,
        projected_slides=projected_slides,
        object_html=object_html,
        canvas_px=canvas_px,
        pixels_per_point=pixels_per_point,
    )

    objects = [item for slide in projected_slides for item in slide.objects]
    source_map = _source_map_payload(
        source_path=str(source_path),
        source_sha256=source_sha256,
        source_slide_count=capture.slide_count,
        canvas_px=canvas_px,
        pixels_per_point=pixels_per_point,
        objects=objects,
        slides=projected_slides,
    )
    blocking = any(item.blocking for item in diagnostics)
    html_sha256 = _sha256_text(html_text)
    report = _projection_report_payload(
        source_path=str(source_path),
        source_sha256=source_sha256,
        source_slide_count=capture.slide_count,
        source_slide_size_pt=capture.slide_size_pt,
        canvas_px=canvas_px,
        pixels_per_point=pixels_per_point,
        officecli_version=capture.officecli_version,
        slides=projected_slides,
        objects=objects,
        diagnostics=diagnostics,
        html_sha256=html_sha256,
    )

    # A failed run must not leave a partial result that could be mistaken for a
    # completed projection, so every owned file is staged beside the output and
    # published only after all of them exist.
    source_map_path = destination.with_suffix(".source-map.json")
    report_path = destination.with_suffix(".projection-report.json")
    for owned in (source_map_path, report_path):
        if owned.exists():
            raise OutputCollisionError(
                f"Projection evidence already exists: {owned}"
            )

    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.stem}-projection-", dir=str(destination.parent))
    )
    published = False
    try:
        staged_html = staging / destination.name
        staged_map = staging / source_map_path.name
        staged_report = staging / report_path.name
        _write_text_exact(staged_html, html_text)
        _json_dump(staged_map, source_map)
        _json_dump(staged_report, report)
        if blocking:
            raise ProjectionError(
                "The projection reported a blocking diagnostic and was not "
                "published: "
                + "; ".join(item.message for item in diagnostics if item.blocking)
            )
        # "Canonical Author HTML" means the current Author Contract accepts it,
        # so the seam proves that for itself rather than publishing a document
        # whose name it has not earned.  The check runs against the staged file,
        # so it validates the exact bytes that would be published.
        contract = check_contract(staged_html, "author")
        if contract.blocked:
            raise ProjectionError(
                "The projected document is not Canonical Author HTML: the current "
                "author Contract rejected it with "
                + "; ".join(
                    f"{item.code}: {item.message}"
                    for item in contract.diagnostics
                    if item.blocking
                )
            )
        staged_html.replace(destination)
        staged_map.replace(source_map_path)
        staged_report.replace(report_path)
        published = True
    finally:
        import shutil

        shutil.rmtree(staging, ignore_errors=True)
        if not published:
            for owned in (destination, source_map_path, report_path):
                owned.unlink(missing_ok=True)

    return ProjectionResult(
        output_html=str(destination),
        html_sha256=_sha256_file(destination),
        source_map_path=str(source_map_path),
        source_map_sha256=_sha256_file(source_map_path),
        projection_report_path=str(report_path),
        projection_report_sha256=_sha256_file(report_path),
        source_path=str(source_path),
        source_sha256=source_sha256,
        source_slide_size_pt=capture.slide_size_pt,
        source_slide_count=capture.slide_count,
        canvas_px=canvas_px,
        pixels_per_point=pixels_per_point,
        officecli_version=capture.officecli_version,
        slides=tuple(projected_slides),
        objects=tuple(objects),
        source_map=source_map,
        projection_report=report,
        diagnostics=tuple(diagnostics),
        published=True,
    )


__all__ = [
    "AUTHOR_CANVAS_HEIGHT_PX",
    "AUTHOR_CANVAS_WIDTH_PX",
    "DISPOSITION_BASE_ONLY",
    "DISPOSITION_CANONICAL",
    "DISPOSITION_LOCKED",
    "DISPOSITION_UNRESOLVED",
    "DISPOSITION_UNSUPPORTED",
    "DISPOSITIONS",
    "NATIVE_DISPOSITIONS",
    "OutputCollisionError",
    "PROJECTION_SCHEMA_VERSION",
    "PROJECTION_REPORT_SCHEMA_VERSION",
    "PROXY_DISPOSITIONS",
    "ProjectedObject",
    "ProjectedSlide",
    "ProjectionDiagnostic",
    "ProjectionError",
    "ProjectionResult",
    "SOURCE_MAP_SCHEMA_VERSION",
    "MissingSlideError",
    "project_pptx_to_author_html",
]
