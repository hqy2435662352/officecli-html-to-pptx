"""OfficeCLI-backed PowerPoint object capture.

This module is the private reader half of the experimental V0.4.2 projection
seam.  It turns one source ``.pptx`` plus an explicit slide selection into the
PowerPoint Object Capture: slide bounds, paint-ordered slide-owned objects,
text structure, geometry, picture sources, native tables, and the exact
capability boundaries OfficeCLI reports.

The reader never writes to the source deck.  Its only inputs are the deck path,
the selected slide numbers, and the caller's ``source_key`` -- the stable
identity the projection uses to keep two decks' identical object paths apart --
so an OfficeHTML export is never a hidden runtime prerequisite.  Everything it
returns is either read from an OfficeCLI command or read out of the source
package's own parts.

One capture covers exactly one source deck.  A multi-source run calls this
function once per distinct deck and keeps the results keyed by ``source_key``;
nothing here discovers slides or reads a deck the caller did not name.

Two OfficeCLI readback facts drive the design:

* ``format`` values are unit-qualified (``960pt``, ``1.3cm``, ``2277795emu``),
  so every length is converted through :func:`length_to_points` instead of
  being parsed by position.
* ``effective.<property>.src`` names where a resolved value came from.  A
  source outside the shape's own tree (``/master[...]``, ``/layout[...]``,
  ``/theme/...``) is the machine-readable base-only signal this projection needs;
  it is recorded as :class:`BaseOnlyClaim` rather than being silently baked in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
import dataclasses
from functools import lru_cache
import json
import posixpath
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence
import zipfile
from xml.etree import ElementTree

OFFICECLI_TIMEOUT_SECONDS = 180
EMU_PER_POINT = 12_700.0
SCREENSHOT_RENDER = "html"
SCREENSHOT_VIEWPORT_WIDTH = 3200

_QUALIFIED_LENGTH_RE = re.compile(
    r"^(-?(?:\d+(?:\.\d*)?|\.\d+))\s*(pt|px|cm|mm|in|emu)$", re.IGNORECASE
)
_HEX_COLOR_RE = re.compile(r"^#?(?P<hex>[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_OWNED_SOURCE_PREFIX = "/shape"

# Object kinds whose native semantics this projection cannot express as a
# canonical editable Author object.  They are only ever emitted as object-local
# locked visual proxies.
NON_CANONICAL_KINDS = frozenset(
    {
        "chart",
        "comment",
        "connector",
        "diagram",
        "equation",
        "group",
        "media",
        "model3d",
        "moderncomment",
        "ole",
        "placeholder",
        "zoom",
    }
)
CONTAINER_KINDS = frozenset({"group"})

# Geometry presets whose native shape the canonical Author object surface can
# reproduce as an independent editable PowerPoint object.  ``roundRect`` is a
# rect with a corner radius, ``ellipse`` and ``rightArrow`` are the two simple
# presets V0.4.2 admits on top of the V0.4.1 surface; every other preset
# (callouts, chevrons, stars, other arrows, custom paths) still has no canonical
# equivalent, so it may only be emitted as a locked visual proxy.
CANONICAL_GEOMETRIES = {
    "rect": None,
    "roundRect": None,
    "ellipse": None,
    "rightArrow": None,
}

# The presets this slice admits beyond the V0.4.1 surface, declared once because
# two rules read the same set:
#
# * their native geometry cannot be *implied* by a CSS declaration the way a
#   rect (a block box) and a roundRect (``border-radius``) can, so the emitted
#   object declares it explicitly for the shape lowering path; and
# * the canonical object surface already carries the CSS ``transform`` a browser
#   and the OfficeCLI lowering both round-trip, so these are also the presets
#   whose own in-plane rotation the surface can express.
#
# ``rect`` and ``roundRect`` are deliberately outside this set: their V0.4.1
# behaviour -- including ``rotation_not_supported`` for a rotated object -- is
# unchanged by this slice.
ADMITTED_PRESET_GEOMETRIES = frozenset({"ellipse", "rightArrow"})

# A base-only claim only matters for a property the projection actually
# renders *and* cannot faithfully preserve.  Master paragraph-layout defaults
# (line spacing, space before/after) are deliberately excluded: the projection
# emits the resolved line spacing as an explicit CSS line-height, which the
# compiler lowers back onto the native paragraph, so the value is preserved
# rather than reconstructed.  What remains is the text formatting whose
# resolved value is a theme token (``text1+lumMod65``) rather than a color this
# projection can write.
VISIBLE_BASE_ONLY_PROPERTIES = frozenset(
    {
        "color",
        "font",
        "font.latin",
        "font.ea",
        "size",
        "bold",
        "italic",
        "underline",
    }
)
ALIGNMENT_DEFAULT = "left"


class PptxReadError(RuntimeError):
    """The source deck could not be read into a PowerPoint Object Capture."""

    # A stable, machine-readable failure class for the projection seam: every
    # read failure that is not a missing slide means the named source could not
    # be read at all.
    code = "unreadable_source"


class MissingSlideError(PptxReadError):
    """A requested slide number does not exist in the source deck."""

    code = "missing_page"

    def __init__(
        self, slide_number: int, slide_count: int, source: str | None = None
    ) -> None:
        message = (
            f"Selected slide {slide_number} does not exist; the source deck has "
            f"{slide_count} slide(s)."
        )
        if source:
            message = f"{message} Source: {source}"
        super().__init__(message)
        self.slide_number = slide_number
        self.slide_count = slide_count
        self.source = source

    def as_dict(self) -> dict[str, Any]:
        """Return the failure as one structured, machine-readable diagnostic."""
        payload: dict[str, Any] = {
            "code": self.code,
            "severity": "error",
            "message": str(self),
            "blocking": True,
            "source_slide": self.slide_number,
            "slide_count": self.slide_count,
        }
        if self.source:
            payload["source_path"] = self.source
        return payload


@dataclass(frozen=True)
class BaseOnlyClaim:
    """One resolved property whose value comes from outside the slide object."""

    property: str
    value: str
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {"property": self.property, "value": self.value, "source": self.source}


@dataclass(frozen=True)
class CapturedRun:
    """One OfficeCLI text run inside a captured paragraph."""

    text: str
    font_family: str
    font_size_pt: float
    bold: bool
    italic: bool
    underline: str
    color: str | None
    properties: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "font_family": self.font_family,
            "font_size_pt": self.font_size_pt,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "color": self.color,
        }


@dataclass(frozen=True)
class CapturedParagraph:
    """One captured PowerPoint paragraph with its runs in source order."""

    text: str
    align: str
    line_spacing: str | None
    space_before_pt: float
    space_after_pt: float
    direction: str
    bullet: str
    level: int
    runs: tuple[CapturedRun, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "align": self.align,
            "line_spacing": self.line_spacing,
            "space_before_pt": self.space_before_pt,
            "space_after_pt": self.space_after_pt,
            "direction": self.direction,
            "bullet": self.bullet,
            "level": self.level,
            "runs": [run.as_dict() for run in self.runs],
        }


@dataclass(frozen=True)
class CapturedPicture:
    """The picture-specific evidence captured for one picture object."""

    rel_id: str
    content_type: str
    media_part: str
    data_uri: str
    intrinsic_size_pt: tuple[float, float]
    source_rect: tuple[float, float, float, float] | None
    crop_raw: str | None
    content_fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        """Return the evidence without inlining the picture body."""
        return {
            "rel_id": self.rel_id,
            "content_type": self.content_type,
            "media_part": self.media_part,
            "intrinsic_size_pt": list(self.intrinsic_size_pt),
            "source_rect": list(self.source_rect) if self.source_rect else None,
            "crop_raw": self.crop_raw,
            "content_fingerprint": self.content_fingerprint,
            "data_uri_length": len(self.data_uri),
        }


@dataclass(frozen=True)
class CapturedTableCell:
    """One captured native table cell."""

    row: int
    column: int
    row_span: int
    column_span: int
    merged: bool
    text: str
    paragraphs: tuple[CapturedParagraph, ...]
    fill: str | None
    properties: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "column": self.column,
            "row_span": self.row_span,
            "column_span": self.column_span,
            "merged": self.merged,
            "text": self.text,
            "fill": self.fill,
            "paragraphs": [paragraph.as_dict() for paragraph in self.paragraphs],
        }


@dataclass(frozen=True)
class CapturedTable:
    """The native table evidence captured for one table object."""

    rows: int
    columns: int
    column_widths_pt: tuple[float, ...]
    row_heights_pt: tuple[float, ...]
    cells: tuple[CapturedTableCell, ...]
    borders: Mapping[str, Any] = field(default_factory=dict)

    def cell(self, row: int, column: int) -> CapturedTableCell | None:
        for item in self.cells:
            if item.row == row and item.column == column:
                return item
        return None


@dataclass
class CapturedObject:
    """One slide-owned PowerPoint object, in source paint order."""

    source_slide: int
    source_object: str
    source_kind: str
    name: str
    officecli_id: int | None
    z_order: int
    bounds_pt: tuple[float, float, float, float]
    geometry: str | None
    fill: str | None
    line_color: str | None
    line_width_pt: float
    rotation_deg: float
    explicit_properties: frozenset[str]
    base_only: tuple[BaseOnlyClaim, ...]
    opaque_properties: Mapping[str, Any]
    raw_format: Mapping[str, Any]
    text: str
    paragraphs: tuple[CapturedParagraph, ...]
    # The object's resolved opacity, and the alpha its own fill and outline
    # tokens carry.  OfficeCLI writes a semi-transparent fill as an eight-digit
    # hex token *and* reports ``opacity``, so both halves are read: the plain
    # colour is what the ledger records, and the alpha is what the canonical
    # declaration has to carry for the value to survive the round trip.
    opacity: float = 1.0
    fill_alpha: float = 1.0
    line_alpha: float = 1.0
    # A mirrored object's native transform.  A mirror is not an in-plane
    # rotation, so it is never representable by the canonical ``transform``.
    mirrored: bool = False
    # A paint-less container's own child coordinate space: OfficeCLI reports the
    # group's ``a:chOff``/``a:chExt`` as ``childOffset``/``childExtent``, which
    # is the only declaration of the space its children's rectangles are in.
    child_offset_pt: tuple[float, float] | None = None
    child_extent_pt: tuple[float, float] | None = None
    picture: CapturedPicture | None = None
    table: CapturedTable | None = None
    children: tuple["CapturedObject", ...] = ()
    # The stable identity of the deck this object was captured from.  Two decks
    # routinely report the same ``source_object`` path for different objects, so
    # ``(source_key, source_slide, source_object)`` -- never the path alone -- is
    # what identifies a captured object.
    source_key: str = ""
    # The container that owns this object, when it is not slide-owned.  An owned
    # object is represented by its container's own representation and is never
    # emitted as a top-level sibling.
    owner: str | None = None
    owner_kind: str | None = None

    @property
    def has_text(self) -> bool:
        return bool(
            self.text.strip()
            or any(paragraph.runs for paragraph in self.paragraphs)
        )

    @property
    def base_only_properties(self) -> frozenset[str]:
        return frozenset(claim.property for claim in self.base_only)

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "kind": self.source_kind,
                "name": self.name,
                "bounds": [round(value, 4) for value in self.bounds_pt],
                "geometry": self.geometry,
                "fill": self.fill,
                "line": self.line_color,
                "text": self.text,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        import hashlib

        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        """Return report-facing evidence without inlining binary payloads."""
        data: dict[str, Any] = {
            "source_slide": self.source_slide,
            "source_object": self.source_object,
            "source_kind": self.source_kind,
            "name": self.name,
            "officecli_id": self.officecli_id,
            "z_order": self.z_order,
            "bounds_pt": [round(value, 4) for value in self.bounds_pt],
            "geometry": self.geometry,
            "text": self.text,
            "paragraphs": [paragraph.as_dict() for paragraph in self.paragraphs],
            "base_only": [claim.as_dict() for claim in self.base_only],
            "explicit_properties": sorted(self.explicit_properties),
            "fingerprint": self.fingerprint(),
        }
        if self.source_key:
            data["source_key"] = self.source_key
        if abs(self.rotation_deg) > 0.01 or self.mirrored:
            data["transform"] = {
                "rotation_deg": self.rotation_deg,
                "mirrored": self.mirrored,
            }
        if self.opacity < 0.999 or self.fill_alpha < 0.999 or self.line_alpha < 0.999:
            data["alpha"] = {
                "opacity": round(self.opacity, 4),
                "fill": round(self.fill_alpha, 4),
                "line": round(self.line_alpha, 4),
            }
        if self.owner is not None:
            data["owner"] = self.owner
            data["owner_kind"] = self.owner_kind
        if self.fill is not None:
            data["fill"] = self.fill
        if self.line_color is not None or self.line_width_pt:
            data["line"] = {"color": self.line_color, "width_pt": self.line_width_pt}
        if self.picture is not None:
            data["picture"] = self.picture.as_dict()
        if self.table is not None:
            data["table"] = {
                "rows": self.table.rows,
                "columns": self.table.columns,
                "column_widths_pt": [
                    round(value, 4) for value in self.table.column_widths_pt
                ],
                "row_heights_pt": [
                    round(value, 4) for value in self.table.row_heights_pt
                ],
                "borders": dict(self.table.borders),
                "cells": [cell.as_dict() for cell in self.table.cells],
            }
        if self.children:
            data["children"] = [child.as_dict() for child in self.children]
        return data


@dataclass(frozen=True)
class CapturedSlide:
    """One captured slide: its bounds, identity, and paint-ordered objects."""

    source_slide: int
    layout: str
    layout_type: str
    width_pt: float
    height_pt: float
    background: str | None
    objects: tuple[CapturedObject, ...]
    # Which deck this page came from.  ``source_slide`` is always the original
    # page number in that deck, never a position in the caller's selection.
    source_key: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_slide": self.source_slide,
            "layout": self.layout,
            "layout_type": self.layout_type,
            "width_pt": self.width_pt,
            "height_pt": self.height_pt,
            "background": self.background,
            "object_count": len(self.objects),
            "objects": [item.as_dict() for item in self.objects],
        }
        if self.source_key:
            payload["source_key"] = self.source_key
        return payload


@dataclass(frozen=True)
class CapturedPresentation:
    """The whole PowerPoint Object Capture for one read."""

    source_path: str
    slide_size_pt: tuple[float, float]
    slide_count: int
    officecli_version: str
    slides: tuple[CapturedSlide, ...]
    source_key: str = ""

    def slide(self, number: int) -> CapturedSlide:
        for item in self.slides:
            if item.source_slide == number:
                return item
        raise MissingSlideError(number, self.slide_count, self.source_path)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_key": self.source_key,
            "slide_size_pt": list(self.slide_size_pt),
            "slide_count": self.slide_count,
            "officecli_version": self.officecli_version,
            "slides": [item.as_dict() for item in self.slides],
        }


def length_to_points(value: Any, default: float = 0.0) -> float:
    """Convert an OfficeCLI ``format`` length to points.

    OfficeCLI serializes the same property as ``emu``, ``pt``, ``cm``, ``mm``,
    or ``in`` depending on where in the document it was read.  Handling each
    unit explicitly keeps the projection free of the CSS physical-unit
    conversion (``96/72``) that would silently rescale a deck.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    match = _QUALIFIED_LENGTH_RE.match(text)
    if match is None:
        return default
    amount = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "pt":
        return amount
    if unit == "emu":
        return amount / EMU_PER_POINT
    if unit == "px":
        # An OfficeCLI length in pixels is a pixel the OfficeCLI projection
        # produced; it carries no physical-unit claim, so it is read at the
        # 1920x1080 Author canvas ratio of two device pixels per point.
        return amount / 2.0
    if unit == "cm":
        return amount * 72.0 / 2.54
    if unit == "mm":
        return amount * 72.0 / 25.4
    return amount * 72.0


def points_to_emu(value: float) -> int:
    return int(round(value * EMU_PER_POINT))


def parse_color(value: Any) -> str | None:
    """Return ``#RRGGBB`` for a plain hex fill or line, else ``None``.

    A theme token (``accent1``, ``text1+lumMod65``), a gradient, a pattern, or
    ``none`` is not a plain color and must not be reported as one.  An
    eight-digit token is a plain color *with* an alpha byte; the byte is read
    separately by :func:`alpha_of` so the colour claim stays six digits.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "transparent"}:
        return None
    match = _HEX_COLOR_RE.match(text)
    if match is None:
        return None
    raw = match.group("hex").upper()
    return f"#{raw[:6]}"


def alpha_of(value: Any) -> float:
    """Return the opacity a colour token itself carries, or ``1.0``.

    OfficeCLI encodes a semi-transparent solid fill as an eight-digit hex token
    (``#D9666680``) or as ``rgba(...)``.  Reading it here keeps the plain-colour
    claim of :func:`parse_color` and the alpha claim separate, so neither is
    silently invented for the other.
    """
    if value is None:
        return 1.0
    text = str(value).strip()
    if not text:
        return 1.0
    match = _HEX_COLOR_RE.match(text)
    if match is not None:
        raw = match.group("hex")
        if len(raw) == 8:
            return int(raw[6:8], 16) / 255.0
        return 1.0
    match = re.fullmatch(r"rgba?\(([^)]*)\)", text, re.IGNORECASE)
    if match is not None:
        parts = [part.strip() for part in match.group(1).split(",")]
        if len(parts) == 4:
            try:
                return max(0.0, min(1.0, float(parts[3])))
            except ValueError:
                return 1.0
    return 1.0


def _length_pair(value: Any) -> tuple[float, float] | None:
    """Return an OfficeCLI ``x,y`` length pair in points, or ``None``.

    OfficeCLI reports a container's child coordinate space as one comma-separated
    pair per property (``childOffset``, ``childExtent``).  Unlike its single
    lengths -- which carry a unit (``11638401emu``, ``1.5pt``) -- this pair is
    reported as bare EMU, so a member with no unit is read as EMU rather than
    being discarded as unqualified.
    """
    if value is None:
        return None
    parts = [part for part in re.split(r"[,\s]+", str(value).strip()) if part]
    if len(parts) != 2:
        return None
    members: list[float] = []
    for part in parts:
        if _QUALIFIED_LENGTH_RE.match(part) is not None:
            members.append(length_to_points(part))
            continue
        try:
            members.append(float(part) / EMU_PER_POINT)
        except ValueError:
            return None
    return (members[0], members[1])


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "h", "v"}


def _opacity(value: Any, default: float = 1.0) -> float:
    if value is None:
        return default
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _is_default_alignment(value: Any) -> bool:
    return str(value or ALIGNMENT_DEFAULT).strip().lower() in {ALIGNMENT_DEFAULT, "start"}


def _officecli_executable() -> str:
    executable = shutil.which("officecli")
    if executable is None:
        raise PptxReadError(
            "OfficeCLI was not found on PATH; the PowerPoint object reader "
            "requires OfficeCLI."
        )
    return executable


def _run_officecli(*args: str, check: bool = True, attempts: int = 6) -> str:
    """Run one OfficeCLI read command, retrying a transient failure.

    OfficeCLI keeps documents in a resident process and reads a whole
    presentation into memory.  On a loaded machine a read of a large deck can
    exit 1 with no message at all — measured at roughly two in five invocations
    under load — and the same command succeeds unchanged moments later.  A
    failed attempt is therefore retried with a growing pause, and only the last
    failure is reported, with its command, so a real error stays diagnosable.
    """
    command = [_officecli_executable(), *args]
    last: str = ""
    for attempt in range(max(1, attempts)):
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                timeout=OFFICECLI_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last = str(exc)
            if attempt + 1 >= attempts:
                if not check:
                    return ""
                raise PptxReadError(
                    f"{' '.join(command)} could not run: {exc}"
                ) from exc
            time.sleep(0.4 * (1.6**attempt))
            continue
        stdout = completed.stdout.decode("utf-8", errors="replace")
        if completed.returncode == 0 and stdout.strip():
            return stdout
        stderr = completed.stderr.decode("utf-8", errors="replace")
        last = (stderr or stdout).strip() or f"exit code {completed.returncode}"
        if attempt + 1 < attempts:
            time.sleep(0.4 * (1.6**attempt))
    if not check:
        return ""
    raise PptxReadError(f"{' '.join(command)} failed: {last}")


def _run_officecli_json(*args: str) -> Any:
    text = _run_officecli(*args, "--json")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PptxReadError(
            f"officecli {' '.join(args)} did not return JSON: {exc}"
        ) from exc
    results = payload.get("data", {}).get("results")
    if not isinstance(results, list) or not results:
        raise PptxReadError(
            f"officecli {' '.join(args)} returned no result for that path."
        )
    return results[0]


@lru_cache(maxsize=1)
def officecli_version() -> str:
    """Return the discovered OfficeCLI version, or ``"unknown"``."""
    try:
        first = _run_officecli("--version").strip().splitlines()
    except PptxReadError:
        return "unknown"
    return first[0].strip() if first else "unknown"


def _children(node: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = node.get("children")
    return list(value) if isinstance(value, list) else []


def _iter_nodes(node: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    yield node
    for child in _children(node):
        yield from _iter_nodes(child)


def _text_of(node: Mapping[str, Any]) -> str:
    value = node.get("text")
    return str(value) if value is not None else ""


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = mapping.get(name)
        if value is not None:
            return value
    return None


def _resolved(
    mappings: Sequence[Mapping[str, Any]], *names: str
) -> Any:
    """Return the first declared value for ``names`` across the fallbacks."""
    for mapping in mappings:
        value = _first(mapping, *names)
        if value is not None:
            return value
    return None


def _run_manifest(
    run: Mapping[str, Any],
    fallback: Mapping[str, Any],
    fallback_run: Mapping[str, Any],
) -> CapturedRun:
    """Read one run's resolved formatting.

    OfficeCLI omits a run property when the run does not declare it directly
    and exposes the inheritance-resolved value as ``effective.<property>``.
    Both spellings are resolved here so two runs the slide formats identically
    stay one Canonical Run instead of being split by which spelling happened to
    carry the value.
    """
    fmt = dict(run.get("format") or {})
    sources: tuple[Mapping[str, Any], ...] = (
        fmt,
        dict(fallback),
        dict(fallback_run),
    )
    underline = str(
        _resolved(sources, "underline", "effective.underline") or "none"
    ).lower()
    if underline in {"", "false", "no", "none"}:
        underline = "none"
    return CapturedRun(
        text=_text_of(run),
        font_family=_resolved_font_family(sources),
        font_size_pt=length_to_points(_resolved(sources, "size", "effective.size")),
        bold=bool(_resolved(sources, "bold", "effective.bold")),
        italic=bool(_resolved(sources, "italic", "effective.italic")),
        underline=underline,
        color=parse_color(_resolved(sources, "color", "effective.color")),
        properties=fmt,
    )


def _resolved_font_family(sources: Sequence[Mapping[str, Any]]) -> str:
    """Return the typeface the run's own script slot resolves to.

    PowerPoint keeps a separate Latin and East-Asian typeface per run.  The
    Latin slot is the one a browser actually draws Latin characters with, so it
    is read as its own value rather than being folded into the aggregate
    ``font`` token; without that the Latin text of a CJK-run body would be
    measured with the East-Asian face and reflow.
    """
    return str(
        _resolved(
            sources,
            "font.latin",
            "effective.font.latin",
            "font",
            "effective.font",
        )
        or ""
    )


def _slide_line_breaks(
    pptx_path: Path, slide_number: int
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    """Read every text body's intra-paragraph line breaks out of the slide part.

    OfficeCLI's readback drops ``<a:br/>``: it reports the paragraph as its two
    runs with nothing between them, so the *characters* survive the read while
    the break that separates them does not.  The break is source truth the reader
    must not lose, because without it the projection cannot tell a hard break
    from two runs that are simply adjacent -- and would publish the two authored
    lines as one line of run-together text.

    The break is therefore read from the package's own slide part, which is a
    document this reader already reads for picture media.  Each entry is the
    run-length layout of a paragraph that declares a break, paired with the
    zero-based run index each break follows.  The layout is the paragraph's own
    identity here: it is a partition of the paragraph's characters, so it is the
    one thing the readback and the source part state identically, and it is
    checked against the runs before anything is restored.
    """
    path = f"ppt/slides/slide{slide_number}.xml"
    try:
        with zipfile.ZipFile(pptx_path) as archive:
            raw = archive.read(path)
    except (KeyError, OSError, zipfile.BadZipFile):
        # A part this reader cannot open simply contributes no break evidence;
        # the capture then reads exactly as it did before this evidence existed.
        return ()
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return ()
    found: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for body in _text_bodies(root):
        for paragraph in body:
            positions = _paragraph_break_positions(paragraph)
            if positions:
                found.append((_paragraph_run_lengths(paragraph), positions))
    return tuple(found)


def _text_bodies(root: Any) -> Iterator[Any]:
    """Yield every ``p:txBody`` of one slide part, in document order."""
    for node in root.iter():
        if _local_name(node.tag) == "txBody":
            yield node


def _paragraph_run_lengths(paragraph: Any) -> tuple[int, ...]:
    """Return the length of each run of one paragraph, in document order."""
    lengths: list[int] = []
    for child in paragraph:
        name = _local_name(child.tag)
        if name not in {"r", "fld"}:
            continue
        lengths.append(
            sum(
                len(str(node.text or ""))
                for node in child.iter()
                if _local_name(node.tag) == "t"
            )
        )
    return tuple(lengths)


def _paragraph_break_positions(paragraph: Any) -> tuple[int, ...]:
    """Return the run index each ``<a:br/>`` of one paragraph follows."""
    positions: list[int] = []
    index = 0
    for child in paragraph:
        name = _local_name(child.tag)
        if name == "br":
            positions.append(index)
        elif name in {"r", "fld"}:
            index += 1
    return tuple(positions)


def _paragraphs(
    node: Mapping[str, Any],
    *,
    breaks: Sequence[tuple[tuple[int, ...], tuple[int, ...]]] = (),
) -> tuple[CapturedParagraph, ...]:
    """Read the paragraph/run structure OfficeCLI exposes for a text body.

    ``breaks`` pairs a paragraph's run-length layout with the run index each of
    its own ``<a:br/>`` elements follows, read from the source part because
    OfficeCLI's readback drops the break itself.  A paragraph whose layout
    matches one of them is re-partitioned on its breaks, so the two lines a hard
    break separates are two paragraphs of the projection -- which is the one
    separator the Canonical Author paragraph orthography has.
    """
    fmt = dict(node.get("format") or {})
    text_children = [
        child for child in _children(node) if str(child.get("type")) == "paragraph"
    ]
    if not text_children:
        return ()
    # The run-level fallback reads the first run's effective formatting, which
    # is the same object-level value OfficeCLI aggregates for a uniform body.
    first_run_format: dict[str, Any] = {}
    for paragraph in text_children:
        for run in _children(paragraph):
            if str(run.get("type")) == "run":
                first_run_format = dict(run.get("format") or {})
                break
        if first_run_format:
            break
    result: list[CapturedParagraph] = []
    for paragraph in text_children:
        paragraph_format = dict(paragraph.get("format") or {})
        runs = _with_line_breaks(
            tuple(
                _run_manifest(run, {**fmt, **paragraph_format}, first_run_format)
                for run in _children(paragraph)
                if str(run.get("type")) == "run"
            ),
            breaks,
        )
        text = _text_of(paragraph)
        if not text:
            text = "".join(run.text for run in runs)
        alignment = paragraph_format.get("align", fmt.get("align", ALIGNMENT_DEFAULT))
        result.append(
            CapturedParagraph(
                text=text,
                align=str(alignment or ALIGNMENT_DEFAULT),
                line_spacing=_line_spacing_value(
                    paragraph_format.get("lineSpacing", fmt.get("lineSpacing"))
                ),
                space_before_pt=length_to_points(
                    paragraph_format.get("spaceBefore", fmt.get("spaceBefore"))
                ),
                space_after_pt=length_to_points(
                    paragraph_format.get("spaceAfter", fmt.get("spaceAfter"))
                ),
                direction=str(
                    paragraph_format.get("direction", fmt.get("direction", "ltr"))
                    or "ltr"
                ),
                bullet=str(
                    paragraph_format.get("list", fmt.get("list", "none")) or "none"
                ),
                level=int(_number(paragraph_format.get("level")) or 0),
                runs=runs,
            )
        )
    return tuple(result)


def _with_line_breaks(
    runs: tuple[CapturedRun, ...],
    breaks: Sequence[tuple[tuple[int, ...], tuple[int, ...]]] | None,
) -> tuple[CapturedRun, ...]:
    """Return ``runs`` with PowerPoint's hard break restored between them.

    The break is put back where the source declares it -- after the run the
    source's own run index names -- so the paragraph's own characters are
    unchanged and the one thing the readback lost is the one thing this puts
    back.

    The two sides count runs differently: the source part's paragraph is split
    into runs by OfficeCLI's own readback, which can divide one authored run's
    characters across several runs.  The paragraph's *text* is what both sides
    state identically, so a recorded break is matched by its paragraph's whole
    text and the break's character offset inside it, and the run that owns that
    offset is the run the break follows.  The recorded position is used directly
    when the layouts do agree, and a paragraph that matches no recorded break is
    left exactly as it was read -- which is what keeps a body of ordinary
    adjacent runs adjacent.
    """
    if not breaks:
        return runs
    text = "".join(run.text for run in runs)
    if not text:
        return runs
    layout = tuple(len(run.text) for run in runs)
    for recorded, positions in breaks:
        if recorded == layout:
            return _break_after_indices(runs, positions)
        if sum(recorded) != len(text):
            continue
        offsets: set[int] = set()
        for index in positions:
            if index < len(recorded):
                # A break at run index N follows the first N runs, so its
                # character offset is the sum of their lengths.
                offsets.add(sum(recorded[:index]))
        if not offsets:
            continue
        return _break_after_offsets(runs, offsets)
    return runs


def _break_after_indices(
    runs: tuple[CapturedRun, ...], positions: Sequence[int]
) -> tuple[CapturedRun, ...]:
    """Append the hard break to the run at each recorded index."""
    wanted = set(positions)
    return tuple(
        dataclasses.replace(run, text=run.text + _HARD_BREAK)
        if index in wanted
        else run
        for index, run in enumerate(runs, start=1)
    )


def _break_after_offsets(
    runs: tuple[CapturedRun, ...], offsets: set[int]
) -> tuple[CapturedRun, ...]:
    """Append the hard break to the run that owns each character offset."""
    restored: list[CapturedRun] = []
    consumed = 0
    for run in runs:
        consumed += len(run.text)
        restored.append(
            dataclasses.replace(run, text=run.text + _HARD_BREAK)
            if consumed in offsets
            else run
        )
    return tuple(restored)


# PowerPoint's intra-paragraph line break.  It is a character in a text body and
# never a character of the document's text: the projection re-partitions on it.
_HARD_BREAK = "\x0b"


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _split_intra_paragraph_breaks(
    paragraphs: Sequence[CapturedParagraph],
) -> tuple[CapturedParagraph, ...]:
    """Re-partition paragraphs on PowerPoint's intra-paragraph line break.

    A text body that mixes runs and ``<a:br/>`` reads back with ``\\x0b`` inside
    one paragraph.  The Canonical Author paragraph orthography has one
    separator -- a paragraph boundary -- so such a body is re-partitioned on
    that break: every run's text is split in source order, so each side keeps
    exactly the characters it owned, and the run formatting is preserved.  Only
    the paragraph count changes, and the projection report records that.

    The break is looked for in the paragraph's *runs*, not in its aggregate text:
    the aggregate text OfficeCLI reports is the runs concatenated, so a paragraph
    whose break this reader restored onto a run would otherwise look unbroken.
    """
    if not _carries_hard_break(paragraphs):
        return tuple(paragraphs)
    reordered: list[CapturedParagraph] = []
    for paragraph in paragraphs:
        if not any("\x0b" in run.text for run in paragraph.runs):
            reordered.append(paragraph)
            continue
        pieces: list[list[CapturedRun]] = [[]]
        for run in paragraph.runs:
            segments = run.text.split("\x0b")
            for index, segment in enumerate(segments):
                if index:
                    pieces.append([])
                if segment:
                    pieces[-1].append(
                        CapturedRun(
                            text=segment,
                            font_family=run.font_family,
                            font_size_pt=run.font_size_pt,
                            bold=run.bold,
                            italic=run.italic,
                            underline=run.underline,
                            color=run.color,
                            properties=run.properties,
                        )
                    )
        for index, runs in enumerate(pieces):
            reordered.append(
                CapturedParagraph(
                    text="".join(item.text for item in runs),
                    align=paragraph.align,
                    line_spacing=paragraph.line_spacing,
                    space_before_pt=(
                        paragraph.space_before_pt if index == 0 else 0.0
                    ),
                    space_after_pt=(
                        paragraph.space_after_pt if index == len(pieces) - 1 else 0.0
                    ),
                    direction=paragraph.direction,
                    bullet=paragraph.bullet,
                    level=paragraph.level,
                    runs=tuple(runs),
                )
            )
    return tuple(reordered)


def _line_spacing_value(value: Any) -> str | None:
    """Normalize an OfficeCLI line-spacing token.

    The readback is either a ratio (``1.3x``), a length (``26pt``), or absent.
    A ratio of exactly one is the PowerPoint default and is reported as absent
    so it never becomes an explicit paragraph override in the projection.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered.endswith("x"):
        ratio = _number(lowered[:-1])
        if not ratio or abs(ratio - 1.0) <= 0.01:
            return None
        return f"{ratio:.4f}x"
    points = length_to_points(text)
    if points <= 0:
        return None
    return f"{points:.4f}pt"


def _base_only_claims(
    fmt: Mapping[str, Any],
    *,
    has_text: bool,
) -> tuple[BaseOnlyClaim, ...]:
    """Return the resolved properties the slide object does not own.

    OfficeCLI emits ``effective.<property>.src`` for values it resolved from a
    master, layout, or theme.  Only the properties this projection declares and
    cannot faithfully write are recorded, and only when the object actually
    paints them:

    * a text-free shape never paints a text property, so its inherited text
      defaults are not a base-only claim;
    * an alignment equal to the canonical default changes nothing;
    * a plain text property the projection writes explicitly is preserved, not
      reconstructed, so it is not a base-only claim.
    """
    claims: list[BaseOnlyClaim] = []
    for key, value in fmt.items():
        if not key.startswith("effective.") or not key.endswith(".src"):
            continue
        prop = key[len("effective.") : -len(".src")]
        if str(value).startswith(_OWNED_SOURCE_PREFIX):
            continue
        resolved = fmt.get(f"effective.{prop}")
        if prop == "align":
            if not has_text or _is_default_alignment(resolved):
                continue
        elif prop not in VISIBLE_BASE_ONLY_PROPERTIES:
            continue
        elif not has_text:
            # A property that is only ever rendered through text cannot make a
            # text-free shape base-only: the resolved value is never painted.
            continue
        claims.append(
            BaseOnlyClaim(property=prop, value=str(resolved), source=str(value))
        )
    claims.sort(key=lambda item: item.property)
    return tuple(claims)


def _rotation_degrees(fmt: Mapping[str, Any]) -> float:
    for key in ("rotation", "rotate", "rot"):
        if key in fmt:
            return _number(fmt[key])
    transform = str(fmt.get("transform", "") or "")
    match = re.search(r"rotate\(\s*(-?[\d.]+)\s*deg\s*\)", transform)
    return float(match.group(1)) if match else 0.0


def _borders(table_format: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in table_format.items()
        if str(key).startswith("border")
    }


def _crop_evidence(fmt: Mapping[str, Any]) -> tuple[
    tuple[float, float, float, float] | None, str | None
]:
    """Return OfficeCLI's picture crop percentages as a source rectangle."""
    raw = fmt.get("crop")
    if raw is None:
        return None, None
    text = str(raw).strip()
    values: list[float] = []
    for part in re.split(r"[,\s]+", text):
        if not part:
            continue
        try:
            values.append(float(part))
        except ValueError:
            return None, text
    if len(values) != 4:
        return None, text
    left, top, right, bottom = (max(0.0, min(99.5, value)) for value in values)
    # The percentages are read back as a per-side edge, so a picture is
    # addressable only when the retained rectangle stays positive.
    if left + right >= 100.0 or top + bottom >= 100.0:
        return None, text
    return (left / 100.0, top / 100.0, right / 100.0, bottom / 100.0), text


def _intrinsic_size_pt(data: bytes) -> tuple[float, float]:
    """Return an image's intrinsic size in points at its own pixel ratio."""
    try:
        from PIL import Image
        from io import BytesIO

        with Image.open(BytesIO(data)) as image:
            return (float(image.width), float(image.height))
    except Exception:
        pass
    try:
        root = ElementTree.fromstring(data)
        view_box = str(root.attrib.get("viewBox", "")).replace(",", " ").split()
        if len(view_box) == 4:
            return (float(view_box[2]), float(view_box[3]))
    except (ElementTree.ParseError, ValueError):
        pass
    return (0.0, 0.0)


def _slide_relationships(pptx_path: Path, slide_number: int) -> dict[str, str]:
    rels_path = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
    relationships: dict[str, str] = {}
    try:
        with zipfile.ZipFile(pptx_path) as archive:
            root = ElementTree.fromstring(archive.read(rels_path))
    except (KeyError, OSError, ElementTree.ParseError) as exc:
        raise PptxReadError(
            f"Source slide {slide_number} has no readable relationship part "
            f"({rels_path}): {exc}"
        ) from exc
    for relationship in root:
        identifier = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target")
        if identifier and target:
            relationships[identifier] = target
    return relationships


def _picture_source(
    pptx_path: Path, slide_number: int, fmt: Mapping[str, Any]
) -> CapturedPicture:
    """Extract the picture's own media part as a deterministic data URI."""
    rel_id = str(fmt.get("relId") or "")
    if not rel_id:
        raise PptxReadError(
            f"Picture on slide {slide_number} does not expose a relationship id."
        )
    relationships = _slide_relationships(pptx_path, slide_number)
    target = relationships.get(rel_id)
    if not target:
        raise PptxReadError(
            f"Picture relationship {rel_id} on slide {slide_number} is not "
            "declared by that slide."
        )
    media_part = (
        posixpath.normpath(target.lstrip("/"))
        if target.startswith("/")
        else posixpath.normpath(posixpath.join("ppt/slides", target))
    )
    try:
        with zipfile.ZipFile(pptx_path) as archive:
            data = archive.read(media_part)
    except (KeyError, OSError) as exc:
        raise PptxReadError(
            f"Picture media {media_part} on slide {slide_number} is not readable: {exc}"
        ) from exc
    content_type = str(fmt.get("contentType") or "").strip()
    if not content_type.startswith("image/"):
        raise PptxReadError(
            f"Picture media {media_part} has unsupported content type "
            f"{content_type or 'unknown'!r}."
        )
    import hashlib

    source_rect, crop_raw = _crop_evidence(fmt)
    return CapturedPicture(
        rel_id=rel_id,
        content_type=content_type,
        media_part=media_part,
        data_uri=f"data:{content_type};base64," + base64.b64encode(data).decode("ascii"),
        intrinsic_size_pt=_intrinsic_size_pt(data),
        source_rect=source_rect,
        crop_raw=crop_raw,
        content_fingerprint=hashlib.sha256(data).hexdigest(),
    )


def _table_cell_paragraphs(cell: Mapping[str, Any]) -> tuple[CapturedParagraph, ...]:
    """Read a table cell's paragraphs and runs from its own text body."""
    raw = str((cell.get("format") or {}).get("txBodyRaw") or "")
    cell_format = dict(cell.get("format") or {})
    if not raw:
        fallback = _text_of(cell)
        if not fallback:
            return ()
        return (
            CapturedParagraph(
                text=fallback,
                align=str(cell_format.get("align", ALIGNMENT_DEFAULT) or ALIGNMENT_DEFAULT),
                line_spacing=None,
                space_before_pt=0.0,
                space_after_pt=0.0,
                direction="ltr",
                bullet="none",
                level=0,
                runs=(
                    CapturedRun(
                        text=fallback,
                        font_family=str(cell_format.get("font.latin") or cell_format.get("font") or ""),
                        font_size_pt=length_to_points(cell_format.get("size")),
                        bold=bool(cell_format.get("bold")),
                        italic=bool(cell_format.get("italic")),
                        underline=str(cell_format.get("underline", "none") or "none"),
                        color=parse_color(cell_format.get("color")),
                    ),
                ),
            ),
        )
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return ()
    paragraphs: list[CapturedParagraph] = []
    default_size = length_to_points(cell_format.get("size"))
    default_font = str(cell_format.get("font.latin") or cell_format.get("font") or "")
    default_color = parse_color(cell_format.get("color"))
    for paragraph in [node for node in root.iter() if _local_name(node.tag) == "p"]:
        props = next(
            (node for node in paragraph if _local_name(node.tag) == "pPr"), None
        )
        align = {
            "l": "left",
            "ctr": "center",
            "r": "right",
            "just": "justify",
        }.get(str(props.attrib.get("algn", "l")) if props is not None else "l", ALIGNMENT_DEFAULT)
        bullet = "none"
        level = 0
        if props is not None:
            level = int(_number(props.attrib.get("lvl")) or 0)
            if any(_local_name(node.tag) == "buChar" for node in props):
                bullet = "bullet"
            elif any(_local_name(node.tag) == "buAutoNum" for node in props):
                bullet = "numbered"
        runs: list[CapturedRun] = []
        for run in [
            node for node in paragraph if _local_name(node.tag) in {"r", "fld", "br"}
        ]:
            if _local_name(run.tag) == "br":
                runs.append(
                    CapturedRun(
                        text="\n",
                        font_family=default_font,
                        font_size_pt=default_size,
                        bold=False,
                        italic=False,
                        underline="none",
                        color=default_color,
                    )
                )
                continue
            run_props = next(
                (node for node in run if _local_name(node.tag) == "rPr"), None
            )
            text = "".join(
                str(node.text or "")
                for node in run.iter()
                if _local_name(node.tag) == "t"
            )
            if not text:
                continue
            font_family = default_font
            font_size = default_size
            bold = bool(cell_format.get("bold"))
            italic = bool(cell_format.get("italic"))
            underline = str(cell_format.get("underline", "none") or "none")
            color = default_color
            if run_props is not None:
                raw_size = run_props.attrib.get("sz")
                if raw_size:
                    font_size = _number(raw_size) / 100.0
                bold = str(run_props.attrib.get("b", "")).lower() in {"1", "true"}
                italic = str(run_props.attrib.get("i", "")).lower() in {"1", "true"}
                raw_underline = str(run_props.attrib.get("u", "none") or "none")
                underline = "single" if raw_underline not in {"", "none"} else "none"
                latin = next(
                    (node for node in run_props if _local_name(node.tag) == "latin"),
                    None,
                )
                if latin is not None:
                    font_family = str(latin.attrib.get("typeface", "")) or font_family
                srgb = next(
                    (node for node in run_props.iter() if _local_name(node.tag) == "srgbClr"),
                    None,
                )
                if srgb is not None:
                    color = parse_color(f"#{srgb.attrib.get('val', '')}") or color
            runs.append(
                CapturedRun(
                    text=text,
                    font_family=font_family,
                    font_size_pt=font_size,
                    bold=bold,
                    italic=italic,
                    underline=underline,
                    color=color,
                )
            )
        text = _text_of(cell)
        if not text:
            text = "".join(run.text for run in runs)
        paragraphs.append(
            CapturedParagraph(
                text=text,
                align=align,
                line_spacing=None,
                space_before_pt=0.0,
                space_after_pt=0.0,
                direction="ltr",
                bullet=bullet,
                level=level,
                runs=tuple(runs),
            )
        )
    return tuple(paragraphs)


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _table_evidence(
    node: Mapping[str, Any], slide_number: int, source_object: str
) -> CapturedTable:
    fmt = dict(node.get("format") or {})
    rows = int(_number(fmt.get("rows")))
    columns = int(_number(fmt.get("cols")))
    if rows <= 0 or columns <= 0:
        raise PptxReadError(
            f"Table {source_object} on slide {slide_number} reports no matrix "
            f"(rows={fmt.get('rows')!r}, cols={fmt.get('cols')!r})."
        )
    column_widths = tuple(
        length_to_points(part.strip())
        for part in str(fmt.get("colWidths") or "").split(",")
        if part.strip()
    )
    row_nodes = [
        child for child in _children(node) if str(child.get("type")) == "tr"
    ]
    row_heights = tuple(
        length_to_points((row.get("format") or {}).get("height"))
        for row in row_nodes
    )
    cells: list[CapturedTableCell] = []
    for row_index, row in enumerate(row_nodes, start=1):
        cell_nodes = [
            child for child in _children(row) if str(child.get("type")) == "tc"
        ]
        for column_index, cell in enumerate(cell_nodes, start=1):
            cell_format = dict(cell.get("format") or {})
            row_span = int(_number(cell_format.get("rowspan")) or 1)
            column_span = int(_number(cell_format.get("colspan")) or 1)
            cells.append(
                CapturedTableCell(
                    row=row_index,
                    column=column_index,
                    row_span=row_span,
                    column_span=column_span,
                    merged=(
                        row_span > 1
                        or column_span > 1
                        or bool(cell_format.get("hMerge"))
                        or bool(cell_format.get("vMerge"))
                    ),
                    text=_text_of(cell),
                    paragraphs=_table_cell_paragraphs(cell),
                    fill=parse_color(cell_format.get("fill")),
                    properties=cell_format,
                )
            )
    return CapturedTable(
        rows=rows,
        columns=columns,
        column_widths_pt=column_widths,
        row_heights_pt=row_heights,
        cells=tuple(cells),
        borders=_borders(fmt),
    )


def _carries_hard_break(paragraphs: Sequence[CapturedParagraph]) -> bool:
    """Whether any paragraph's runs still carry a restored hard break."""
    return any(
        "\x0b" in run.text for paragraph in paragraphs for run in paragraph.runs
    )


def _captured_object(
    node: Mapping[str, Any],
    *,
    slide_number: int,
    pptx_path: Path,
    capture_pictures: bool,
    source_key: str = "",
    owner: str | None = None,
    owner_kind: str | None = None,
    line_breaks: Sequence[tuple[tuple[int, ...], tuple[int, ...]]] | None = None,
) -> CapturedObject:
    fmt = dict(node.get("format") or {})
    source_object = str(node.get("path") or "")
    kind = str(node.get("type") or "")
    bounds = tuple(
        length_to_points(fmt.get(key)) for key in ("x", "y", "width", "height")
    )
    paragraphs = _split_intra_paragraph_breaks(
        _paragraphs(node, breaks=line_breaks)
    )
    text = _text_of(node)
    if not text or "\x0b" in text or _carries_hard_break(paragraphs):
        # The paragraph list is the authority for the projected text: the
        # aggregate text OfficeCLI reports is the runs concatenated, so it
        # carries no hard break even where the source declares one.
        text = "\n".join(paragraph.text for paragraph in paragraphs)
    has_text = bool(text.strip() or any(paragraph.runs for paragraph in paragraphs))

    picture: CapturedPicture | None = None
    table: CapturedTable | None = None
    children: tuple[CapturedObject, ...] = ()
    if kind == "picture":
        if not capture_pictures:
            raise PptxReadError(
                f"Picture {source_object} on slide {slide_number} was read "
                "without picture capture enabled."
            )
        picture = _picture_source(pptx_path, slide_number, fmt)
    elif kind == "table":
        table = _table_evidence(node, slide_number, source_object)
    if kind in CONTAINER_KINDS:
        # An owned child is captured with its container's identity so the
        # projection can record ownership instead of inventing a second
        # top-level object for paint the container already carries.
        children = tuple(
            _captured_object(
                child,
                slide_number=slide_number,
                pptx_path=pptx_path,
                capture_pictures=capture_pictures,
                source_key=source_key,
                owner=source_object,
                owner_kind=kind,
                line_breaks=line_breaks,
            )
            for child in _children(node)
        )

    line_color = parse_color(fmt.get("line"))
    underline = str(fmt.get("underline", "none") or "none").lower()
    if underline in {"", "false", "no"}:
        underline = "none"
    return CapturedObject(
        source_slide=slide_number,
        source_object=source_object,
        source_kind=kind,
        name=str(fmt.get("name") or source_object),
        officecli_id=int(_number(fmt.get("id"))) if fmt.get("id") is not None else None,
        z_order=int(_number(fmt.get("zorder"))),
        bounds_pt=(bounds[0], bounds[1], bounds[2], bounds[3]),
        geometry=str(fmt["geometry"]) if "geometry" in fmt else None,
        fill=parse_color(fmt.get("fill")),
        line_color=line_color,
        line_width_pt=length_to_points(fmt.get("lineWidth")),
        rotation_deg=_rotation_degrees(fmt),
        explicit_properties=frozenset(fmt),
        base_only=_base_only_claims(fmt, has_text=has_text),
        opaque_properties=fmt,
        raw_format=fmt,
        text=text,
        paragraphs=paragraphs,
        opacity=_opacity(fmt.get("opacity")),
        fill_alpha=alpha_of(fmt.get("fill")),
        line_alpha=alpha_of(fmt.get("line")),
        mirrored=_truthy(fmt.get("flipH")) or _truthy(fmt.get("flipV")),
        child_offset_pt=_length_pair(fmt.get("childOffset")),
        child_extent_pt=_length_pair(fmt.get("childExtent")),
        picture=picture,
        table=table,
        children=children,
        source_key=source_key,
        owner=owner,
        owner_kind=owner_kind,
    )


def _slide_background(slide_format: Mapping[str, Any]) -> str | None:
    for key in ("background", "backgroundColor", "background.fill"):
        if key in slide_format:
            return parse_color(slide_format[key])
    return None


# ---------------------------------------------------------------------------
# Object-isolated rendering
# ---------------------------------------------------------------------------

# OfficeCLI addresses slide objects by their canonical element token.  Its
# ``get`` verb labels a text-bearing shape ``textbox``, but the removal verb
# only understands ``shape``, so every text-bearing shape is addressed through
# the ``shape`` counter.  Mapped from the discovered token surface:
# ``shape, picture, video, audio, table, chart, connector, group, zoom,
# 3dmodel, ole``.
_CANONICAL_TOKEN = {
    "shape": "shape",
    "textbox": "shape",
    "picture": "picture",
    "table": "table",
    "chart": "chart",
    "connector": "connector",
    "group": "group",
    "zoom": "zoom",
    "model3d": "3dmodel",
    "ole": "ole",
    "media": "video",
}
# The only tolerance allowed when checking a proxy render's density against the
# Author canvas density: whole-pixel rounding of the render itself.
PROXY_DENSITY_TOLERANCE = 0.01


class ObjectIsolationError(PptxReadError):
    """One object could not be rendered on its own."""


class ContainerReconciliationError(ObjectIsolationError):
    """A container's children could not be placed inside its own rectangle.

    This is narrower than a general isolation failure: the container was
    rebuilt, rendered and *measured*, and no reading of its children -- the
    declared group transform or the rectangles OfficeCLI reports -- put visible
    paint inside the container's own rectangle.  It is its own failure class
    because it is its own source condition, and the ledger reports it with its
    own reason code.
    """


# How far a proxy pixel may sit from the reconstruction deck's own background
# and still count as "the background".  OfficeCLI's renderer antialiases an
# object's edge, so the test is one of paint versus no paint, not of an exact
# colour.
PROXY_BACKGROUND_TOLERANCE = 6

# The same "is this pixel paint?" decision, as a 256-entry lookup table: PIL
# applies a list-valued ``point`` in C, where a callable would cost one Python
# call per pixel per channel over a full-slide raster.
_PAINT_LUT = [255 if value > PROXY_BACKGROUND_TOLERANCE else 0 for value in range(256)]

# OfficeCLI's screenshot draws a chrome line along the raster's own edge, which
# is viewer furniture rather than slide paint.  Both the background sampler and
# the paint-extent measurement start this far inside the raster.
_RASTER_INSET_PX = 3


def _carries_other_than(image: Any, background: tuple[int, int, int]) -> bool:
    """Return whether an image holds any paint that is not ``background``.

    The histogram is bucketed rather than scanned pixel by pixel: an image with
    more distinct colours than it has pixels cannot exist, so a complete colour
    count is always available and the test never has to iterate a large raster.
    """
    counts = image.getcolors(image.width * image.height + 1)
    if counts is None:  # pragma: no cover - unreachable for a finite raster
        return True
    return any(
        max(abs(channel - expected) for channel, expected in zip(colour, background))
        > PROXY_BACKGROUND_TOLERANCE
        for _count, colour in counts
    )


def _painted_extent(
    rgb: Any, background: tuple[int, int, int]
) -> tuple[int, int, int, int] | None:
    """Return the bounding box of the raster's paint, or ``None`` for none.

    "Paint" is the same per-channel test :func:`_carries_other_than` applies, so
    the two gates agree on what counts; a full-slide raster is measured through
    a difference image and a bounding box rather than a pixel loop.
    """
    from PIL import Image, ImageChops

    reference = Image.new("RGB", rgb.size, background)
    mask = Image.new("L", rgb.size, 0)
    for band in ImageChops.difference(rgb, reference).split():
        mask = ImageChops.lighter(mask, band.point(_PAINT_LUT))
    return mask.getbbox()


def _render_background(
    rgb: Any,
    bounds_pt: tuple[float, float, float, float],
    pixels_per_point: float,
    guard_px: int,
) -> tuple[int, int, int] | None:
    """Return the reconstruction render's bare background colour, or ``None``.

    The deck holds nothing but the placement under test, so any pixel outside
    the container's own rectangle is bare background -- provided the placement
    is one that keeps its paint inside, which is exactly what the caller is
    measuring.  A placement that strays outside can therefore cover at most a
    minority of the samples: the modal colour of the four points just outside
    the rectangle's corners is taken, and when the rectangle reaches all of them
    the raster's own inset corners stand in.  OfficeCLI's screenshot draws a
    one-pixel chrome line along the raster edge, so an un-inset corner is not
    the slide's background at all.  When the rectangle leaves no such point at
    all, no honest judgement can be made, so ``None`` is returned and the caller
    does not gate on paint.
    """
    left = int(round(bounds_pt[0] * pixels_per_point)) - guard_px
    top = int(round(bounds_pt[1] * pixels_per_point)) - guard_px
    right = left + int(round(bounds_pt[2] * pixels_per_point)) + guard_px * 2
    bottom = top + int(round(bounds_pt[3] * pixels_per_point)) + guard_px * 2
    inset = _RASTER_INSET_PX
    outside = (
        (left - inset, top - inset),
        (right + inset, top - inset),
        (left - inset, bottom + inset),
        (right + inset, bottom + inset),
    )
    fallback = (
        (inset, inset),
        (rgb.width - 1 - inset, inset),
        (inset, rgb.height - 1 - inset),
        (rgb.width - 1 - inset, rgb.height - 1 - inset),
    )
    for group in (outside, fallback):
        samples = [
            _rgb_triple(rgb.getpixel((x, y)))
            for x, y in group
            if 0 <= x < rgb.width
            and 0 <= y < rgb.height
            and (x < left or x >= right or y < top or y >= bottom)
        ]
        if samples:
            # The modal sample survives one candidate landing on a stray
            # antialiased edge without inventing a background that is not there.
            return max(set(samples), key=samples.count)
    return None


def _rgb_triple(pixel: Any) -> tuple[int, int, int]:
    return (int(pixel[0]), int(pixel[1]), int(pixel[2]))


def _raster_rgb(raster: Path) -> Any:
    """Open one render as RGB.

    The raster is a screenshot the caller has already written and validated; the
    returned image owns its pixels independently of the file handle, so callers
    may hold it while the file is closed.
    """
    from PIL import Image

    with Image.open(raster) as image:
        return image.convert("RGB")


# Properties an object's own paint is reproduced from when it is rebuilt into a
# fresh deck for its proxy.  ``crop`` is picture-specific; ``src`` is supplied
# separately because it is a file path, not a read-back property.
# Container kinds whose own shape carries no paint: everything visible about
# them belongs to their children, which live in the container's child coordinate
# space.
_CONTAINER_KINDS_WITHOUT_PAINT = frozenset({"group", "diagram", "smartart"})

# Object kinds whose proxy paint is *reconstructed* -- from the object's own
# stroke, or from a container's children -- rather than read back from a single
# object's geometry and fill.  For these, a render that carries no paint at all
# is a failed representation, never a legitimate blank proxy, so the crop is
# gated on actually showing something.
_RECONSTRUCTED_PAINT_KINDS = _CONTAINER_KINDS_WITHOUT_PAINT | {"connector"}

# Object kinds a container's proxy can be reconstructed from.  Anything else
# (a table, a chart, an OLE object) has no rebuild path, so the container is
# reported as unreconciled rather than published with a hole in it.
_RECONSTRUCTABLE_MEMBER_KINDS = frozenset(
    {"shape", "textbox", "connector", "picture"}
)

# OfficeCLI's ``add`` names a connector's stroke ``line`` while its readback
# names the same value ``color``; a connector's preset is ``shape`` on both
# sides.  Bridging the two spellings is what lets a connector -- and a container
# built from connectors -- be reconstructed at all.
#
# The same text properties are carried by a text-bearing object's own proxy: an
# object whose visible content is its text is not represented by an image of its
# bare rectangle.  A base-only text object is exactly that case -- its text
# colour is inherited, which is why it cannot be declared natively, and the
# inherited colour is not reproducible here, so the proxy carries the object's
# own text and its slide-owned text properties.  ``wrap`` is one of them and is
# load-bearing: a title authored with wrapping off is painted on one line that
# is allowed to overflow its own box, so reconstructing it with OfficeCLI's
# default wrapping on would re-break the line and the proxy would then show a
# clipped fragment of the object instead of the object.
#
# ``lineSpacing`` is load-bearing in the same way and for the same reason.  A
# text body's *empty* paragraphs are lines too: reconstructing a body whose
# leading blank lines are spaced at 0.57x with OfficeCLI's default spacing makes
# those two lines several times taller, which pushes the text the object really
# paints far outside its own rectangle -- and the proxy is then a crop of where
# the text is not.  Composing the object with its own line spacing is what keeps
# the reconstruction's layout the source's layout.
#
# ``valign`` places the body vertically the way the source does.  OfficeCLI's
# default centres a body that is taller than its box, which splits the same
# overflow half above and half below the rectangle; the source states ``top`` for
# a body whose lines run down from the top of its box, and the proxy is otherwise
# the right paint in the wrong place.
_TEXTUAL_KINDS = frozenset({"shape", "textbox"})
_TEXT_PROPERTIES = (
    "size",
    "font",
    "color",
    "align",
    "bold",
    "italic",
    "underline",
    "wrap",
    "lineSpacing",
    "valign",
)

# How a text-bearing proxy's reconstruction is authored to fit the object's own
# rectangle.
#
# The reconstruction is always composed with ``autoFit: none``.  Left to itself
# OfficeCLI fits a body to its box -- shrinking and re-wrapping the text -- and a
# proxy of a body the source draws at full size must not be a picture of text the
# source does not paint.  With the fit off, the body is drawn at its authored
# size and the crop decides what of it is shown, exactly as the source page does.
_PROXY_AUTOFIT = "none"


# How far past its declared rectangle a proxy's crop may reach before the
# expansion is refused.
#
# An expansion is only worth having while it is the *object's* own overflow: a
# line that hangs a little below the box the source drew it in.  A reconstruction
# whose substituted font metrics lay the body out several times taller than the
# box turns the same mechanism into a proxy that stands over the objects below it
# and buries a page the source shows clean, which is a worse representation than
# the clipped one it replaced.  The limit is one line's worth of slack beyond the
# declared rectangle -- enough for a single overflowing line at any size this
# projection handles -- and a body that needs more than that is reporting a
# layout mismatch rather than an object that overflows.
_PROXY_EXPANSION_SLACK_PX = 64.0


def _expansion_limit(declared_px: float) -> float:
    """Return how far a proxy's crop may reach past its declared rectangle."""
    return declared_px + _PROXY_EXPANSION_SLACK_PX


@dataclass(frozen=True)
class ProxyGeometry:
    """Where one published proxy image actually sits on the reconstruction render.

    A proxy is cropped out of the isolated render at the union of the object's
    *declared* rectangle and the rectangle its paint actually occupies, because
    PowerPoint paints a no-autofit line outside its own box and the source page
    shows that overflow.  The crop rectangle is therefore not always the declared
    one, and the emitted element has to be placed by what the image really is
    rather than by where the object was declared.

    ``rect_px`` is ``(left, top, width, height)`` in the reconstruction render's
    own pixels, ``origin_px`` is the same rectangle's top-left corner expressed in
    the declared rectangle's pixel origin -- which is exactly the offset the DOM
    has to apply to an image drawn at the declared bounds -- and ``clamped`` is
    true when the measured paint reached the render's own edge, so the crop could
    not have covered all of it even in principle.
    """

    rect_px: tuple[int, int, int, int]
    origin_px: tuple[int, int]
    clamped: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "rect_px": list(self.rect_px),
            "origin_px": list(self.origin_px),
            "clamped": self.clamped,
        }


@dataclass(frozen=True)
class ContainerMember:
    """One object of a paint-less container's own visible content.

    ``bounds_pt`` is the member's rectangle *in the slide's coordinate space*
    under one candidate reading of the source, so the reconstruction deck can
    place it where that reading says the container shows it.
    """

    source_object: str
    source_kind: str
    bounds_pt: tuple[float, float, float, float]
    properties: Mapping[str, Any] = field(default_factory=dict)
    text: str = ""
    picture: CapturedPicture | None = None
    # The extracted media file a picture member is rebuilt from.  It is written
    # by the caller that owns the proxy work directory, not by the reader.
    media_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_object": self.source_object,
            "source_kind": self.source_kind,
            "bounds_pt": [round(value, 4) for value in self.bounds_pt],
            "has_text": bool(self.text),
            "picture": self.picture.as_dict() if self.picture is not None else None,
        }


# The two readings of a paint-less container's children.  ``declared`` is the
# DrawingML group transform; ``reported`` is OfficeCLI's own rectangles.  They
# are tried in this order and the first one whose *measured* paint lands inside
# the container's own rectangle is what gets published.
CONTAINER_PLACEMENT_DECLARED = "declared"
CONTAINER_PLACEMENT_REPORTED = "reported"
# The one thing a non-container object is rebuilt from: itself.
_PLACEMENT_SINGLE_OBJECT = "object"

# How far outside the container's own rectangle a reconstructed placement's
# paint may still reach and be accepted as "inside" it: OfficeCLI's renderer
# antialiases an edge by a pixel, and the rectangle itself is rounded to whole
# device pixels.
CONTAINER_PAINT_TOLERANCE_PX = 2


@dataclass(frozen=True)
class ContainerPlacement:
    """One candidate placement of a paint-less container's children.

    ``label`` names the mapping that produced ``members``, and is what a
    refusal is reported against:

    * :data:`CONTAINER_PLACEMENT_DECLARED` -- the DrawingML group transform
      ``off + (child - chOff) * ext/chExt``, computed only when the source
      declares ``a:chOff``/``a:chExt`` (OfficeCLI reports those as
      ``childOffset``/``childExtent``); and
    * :data:`CONTAINER_PLACEMENT_REPORTED` -- the children's rectangles exactly
      as OfficeCLI reports them, which is the same reading every non-container
      object in this projection gets.

    A candidate is a candidate: nothing here decides that it is right.  The
    renderer rebuilds one, renders it, and measures where its paint lands.
    """

    label: str
    members: tuple[ContainerMember, ...]


@dataclass(frozen=True)
class ContainerPlacements:
    """Every candidate placement of a container's children, in trial order.

    ``reason`` is set exactly when no candidate can even be *built*: the
    container owns no object, reports a degenerate rectangle, or owns a nested
    container or an object with no reconstruction path.  A container whose
    candidates are all built but whose renders all fail the measured paint test
    is a different failure, and is reported by the renderer that ran them.

    ``unreconciled`` separates the two refusal causes, because they are
    different source conditions: a statement about the container's own content
    or child coordinate space (reported with the container-specific reason
    code), versus a container that cannot be isolated at all.
    """

    placements: tuple[ContainerPlacement, ...] = ()
    reason: str | None = None
    unreconciled: bool = False


def container_child_transform(
    container: CapturedObject,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Return a container's declared child transform, or ``None``.

    A container's children are addressed in the container's own child coordinate
    space; PowerPoint records that space as ``a:chOff``/``a:chExt`` and
    OfficeCLI reads it back as ``childOffset``/``childExtent``.  Without it there
    is no declared candidate at all -- only the rectangles OfficeCLI reports,
    which is what :func:`container_placements` then falls back to.
    """
    offset = container.child_offset_pt
    extent = container.child_extent_pt
    if offset is None or extent is None:
        return None
    if extent[0] <= 0 or extent[1] <= 0:
        return None
    return offset, extent


def map_child_bounds(
    bounds_pt: tuple[float, float, float, float],
    *,
    child_offset: tuple[float, float],
    child_extent: tuple[float, float],
    container_bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Map a child rectangle out of a container's child space onto the slide.

    OfficeCLI reports a group's own rectangle in slide coordinates and its
    children's rectangles in the group's child coordinates, so the two are
    related by the affine map PowerPoint itself applies::

        slide = group_off + (child - chOff) * group_ext / chExt
    """
    left = container_bounds[0] + (
        (bounds_pt[0] - child_offset[0]) * container_bounds[2] / child_extent[0]
    )
    top = container_bounds[1] + (
        (bounds_pt[1] - child_offset[1]) * container_bounds[3] / child_extent[1]
    )
    width = bounds_pt[2] * container_bounds[2] / child_extent[0]
    height = bounds_pt[3] * container_bounds[3] / child_extent[1]
    return (left, top, width, height)


def _container_member(
    descendant: CapturedObject,
    bounds_pt: tuple[float, float, float, float],
) -> ContainerMember:
    """Return one of a container's children as a member placed at ``bounds_pt``."""
    return ContainerMember(
        source_object=descendant.source_object,
        source_kind=descendant.source_kind,
        bounds_pt=bounds_pt,
        properties=descendant.opaque_properties,
        text=descendant.text,
        picture=descendant.picture,
    )


def container_placements(container: CapturedObject) -> ContainerPlacements:
    """Return the candidate placements of a container's own visible content.

    A paint-less container has no geometry, fill, or line of its own: what is
    visible about it is exactly its children.  Reconstructing the container
    therefore means reconstructing *those*, and the only open question is where
    they go.

    That question is not answered by a rule, because OfficeCLI does not follow
    one consistently: a group that declares ``a:chOff``/``a:chExt`` is rendered
    through the DrawingML transform, while one that declares none is rendered
    with its children's rectangles displaced by the group's own offset -- which
    is neither the transform nor the rectangles it reports.  So both readings of
    the source are returned, in a fixed order, and the renderer keeps the first
    one whose *measured* paint lands inside the container's own rectangle:

    1. :data:`CONTAINER_PLACEMENT_DECLARED` -- the DrawingML group transform,
       when the source declares the child space at all; then
    2. :data:`CONTAINER_PLACEMENT_REPORTED` -- the children's rectangles exactly
       as OfficeCLI reports them.

    The refusals here are statements about the source, never fallbacks: a
    container that owns nothing, or owns something with no reconstruction path,
    produces no candidate and no image.
    """
    if not container.children:
        return ContainerPlacements(
            reason=(
                f"{container.source_kind} {container.source_object} owns no "
                "objects, so it has no visible content to reconstruct."
            )
        )
    if container.bounds_pt[2] <= 0 or container.bounds_pt[3] <= 0:
        return ContainerPlacements(
            reason=(
                f"{container.source_kind} {container.source_object} reports a "
                f"degenerate rectangle {container.bounds_pt}, so its visible "
                "extent cannot be cropped."
            )
        )
    descendants = tuple(_walk_descendants(container))
    for descendant in descendants:
        if descendant.source_kind in _CONTAINER_KINDS_WITHOUT_PAINT:
            return ContainerPlacements(
                reason=(
                    f"{container.source_kind} {container.source_object} owns a "
                    f"nested {descendant.source_kind} "
                    f"{descendant.source_object}; a nested container's own child "
                    "space would have to be composed with the outer one, which "
                    "this slice does not attempt."
                ),
                unreconciled=True,
            )
        if descendant.source_kind not in _RECONSTRUCTABLE_MEMBER_KINDS:
            return ContainerPlacements(
                reason=(
                    f"{container.source_kind} {container.source_object} owns "
                    f"{descendant.source_kind} {descendant.source_object}, which "
                    "has no reconstruction path, so the container's visible "
                    "content could not be reproduced completely."
                ),
                unreconciled=True,
            )
    placements: list[ContainerPlacement] = []
    transform = container_child_transform(container)
    if transform is not None:
        child_offset, child_extent = transform
        placements.append(
            ContainerPlacement(
                label=CONTAINER_PLACEMENT_DECLARED,
                members=tuple(
                    _container_member(
                        descendant,
                        map_child_bounds(
                            descendant.bounds_pt,
                            child_offset=child_offset,
                            child_extent=child_extent,
                            container_bounds=container.bounds_pt,
                        ),
                    )
                    for descendant in descendants
                ),
            )
        )
    placements.append(
        ContainerPlacement(
            label=CONTAINER_PLACEMENT_REPORTED,
            members=tuple(
                _container_member(descendant, descendant.bounds_pt)
                for descendant in descendants
            ),
        )
    )
    return ContainerPlacements(placements=tuple(placements))


def _walk_descendants(obj: CapturedObject) -> Iterator[CapturedObject]:
    for child in obj.children:
        yield child
        yield from _walk_descendants(child)



_REBUILD_PROPERTIES = (
    "geometry",
    "fill",
    "line",
    "lineWidth",
    "adj",
    "rotation",
    "opacity",
    "crop",
)


def rebuild_keys(object_kind: str) -> tuple[str, ...]:
    """Return the readback properties an object's reconstruction carries.

    A connector is the one kind whose ``add`` spelling differs from its
    readback: OfficeCLI names its preset ``shape`` on both sides but names its
    stroke ``line`` on input and ``color`` on output, so it is rebuilt through
    a different key set and its stroke is bridged by
    :func:`connector_stroke`.
    """
    if object_kind == "connector":
        return ("shape", "lineWidth")
    return _REBUILD_PROPERTIES


# Text properties whose ``none`` is a declared value rather than the absence of
# one.  Everywhere else ``none`` in a readback means the property is not
# authored, which is why it is not written back.
_NONE_IS_A_VALUE = frozenset({"autoFit"})


def _add_text_paint(
    rebuild: dict[str, str], text: Any, properties: Mapping[str, Any]
) -> None:
    """Add the text that *is* a text-bearing object's paint to its reconstruction.

    One rule for both reconstructions that carry text -- a container's
    text-bearing member and a text-bearing object's own proxy -- so the two can
    never drift into disagreeing about what a text object's visible content is.
    The text properties are set only where the object's own readback supplies
    them, so an inherited value is never invented as if the slide owned it.

    ``none`` is a real value for ``autoFit`` -- it is the source saying the box
    does *not* fit its text -- so where a reconstruction carries the authored
    setting it is written back like any other value instead of being read as "not
    declared".
    """
    body = str(text or "")
    if body:
        rebuild["text"] = body
    for key in _TEXT_PROPERTIES:
        value = properties.get(key)
        if value is None:
            continue
        property_text = str(value).strip()
        if not property_text:
            continue
        if property_text.lower() == "none" and key not in _NONE_IS_A_VALUE:
            continue
        rebuild.setdefault(key, property_text)
    # The body is asked to fit the object's own rectangle: see ``_PROXY_AUTOFIT``.
    rebuild["autoFit"] = _PROXY_AUTOFIT


_GRADIENT_STOP_RE = re.compile(r"#[0-9a-fA-F]{6,8}")


def proxy_paint_value(
    key: str, value: Any, properties: Mapping[str, Any]
) -> str | None:
    """Return an OfficeCLI-acceptable colour for a proxy's ``fill``/``line``.

    OfficeCLI's readback names a non-solid paint by its *kind* -- a gradient
    shape reports ``fill=gradient`` and carries the stops in a separate
    ``gradient`` property -- but its write path only accepts an actual colour
    token, so writing the readback value straight back fails with
    ``Invalid color value: 'gradient'`` and the whole projection is refused.

    Such an object is not canonical-editable either way: a gradient is outside
    the canonical Author fill surface, so it is classified ``locked-visual-proxy``
    and only ever appears through an object-local proxy.  The proxy therefore
    reproduces the object's *representative* paint -- the first gradient stop --
    which keeps the proxy local to the object and honest about not reproducing
    the gradient, instead of failing the run.

    Returns ``None`` when the paint cannot be rendered at all, in which case the
    caller omits the property rather than writing an invalid token.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {"none", "transparent"}:
        return text
    if parse_color(text) is not None:
        return text
    if text.lower() in {"gradient", "gradfill"} or "gradient" in properties:
        stops = _GRADIENT_STOP_RE.findall(str(properties.get("gradient", "")))
        for stop in stops:
            parsed = parse_color(stop)
            if parsed is not None:
                return parsed
    return None


def connector_stroke(properties: Mapping[str, Any]) -> str | None:
    """Return a connector's stroke value under either OfficeCLI spelling."""
    for key in ("line", "color"):
        value = properties.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "none":
            return text
    return None


class IsolatedRenderer:
    """Render one source object at a time, with nothing else on the slide.

    A crop of the composited slide raster is *not* an object-local
    representation: any sibling painted inside the target's rectangle is
    captured with it, and the projection would then paint that sibling's content
    twice.

    Removing the slide's sibling objects from a copy of the deck is **also** not
    enough, and that is the subtle half.  Such a copy still renders the slide's
    layout and master, so a layout graphic inside the target's rectangle is
    baked into the proxy exactly the same way -- a proxy of a transparent object
    can come out as pure layout paint rather than as the object at all.  Culling
    the layout parts from the derived package would mean rewriting a 60 MB
    archive once per object.

    So the render is a **reconstruction**: a brand-new deck, one blank slide, and
    the target object re-created from the properties OfficeCLI read back for it.
    Nothing else can contribute, because nothing else exists in that deck.  The
    object's own rectangle is then cropped out of that render.
    """

    def __init__(self, source_path: str | Path, work_dir: str | Path) -> None:
        self.source_path = Path(source_path).expanduser().resolve()
        self.work_dir = Path(work_dir).expanduser().resolve()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        node = _run_officecli_json("get", str(self.source_path), "/", "--depth", "0")
        root_format = dict(node.get("format") or {})
        self.slide_width_pt = length_to_points(root_format.get("slideWidth"))
        self.slide_height_pt = length_to_points(root_format.get("slideHeight"))
        if self.slide_width_pt <= 0 or self.slide_height_pt <= 0:
            raise PptxReadError(
                "The presentation did not report its slide bounds, so an isolated "
                "render cannot be scaled to the object's rectangle."
            )

    def render(
        self,
        slide_number: int,
        source_object: str,
        bounds_pt: tuple[float, float, float, float],
        *,
        object_kind: str,
        properties: Mapping[str, Any],
        pixels_per_point: float,
        destination: str | Path,
        media_path: str | Path | None = None,
        guard_px: int = 2,
        placements: Sequence[ContainerPlacement] = (),
        text: str = "",
    ) -> tuple[Path, ProxyGeometry]:
        """Rebuild ``source_object`` alone and crop it to what it paints.

        ``properties`` is the object's OfficeCLI ``format`` mapping, ``text`` is
        its own captured text, and ``media_path`` is the extracted picture
        payload when the object is a picture.  All three come from the same read
        that produced ``bounds_pt``.  ``text`` is passed separately because
        OfficeCLI reports an object's text as its own field rather than as one of
        its ``format`` properties.

        The published image is cropped at the union of the object's declared
        rectangle and its measured painted extent, so a no-autofit line that
        overflows its own box is kept whole, and the returned
        :class:`ProxyGeometry` carries where that crop really is so the emitter
        can place the image by its real geometry rather than by the declared
        rectangle.

        A paint-less container has no paint of its own, so ``placements`` carries
        the candidate readings of its visible content: its own children, each
        candidate placed by a different mapping of the source.  The
        reconstruction is then the same technique extended from one object to a
        set of them, except that a container's candidates are tried in order --
        each is rebuilt as the *only* content of the fresh deck and rendered,
        and only one whose measured paint lands inside the container's own
        rectangle is published.  When none does, the container is reported as
        unreconciled rather than represented by an invented image.
        """
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)

        token = _CANONICAL_TOKEN.get(object_kind)
        is_container = object_kind in _CONTAINER_KINDS_WITHOUT_PAINT
        if is_container:
            if not placements:
                # The container's own shape has no geometry, fill, or line: all
                # of its visible content belongs to its children, and OfficeCLI
                # reports those in the container's own child coordinate space.
                # With no candidate placement there is nothing to rebuild, so say
                # so instead of publishing a blank proxy as if it represented
                # the object.
                raise ObjectIsolationError(
                    f"{object_kind!r} has no paint of its own; its visible content "
                    "belongs to its children, which cannot be rebuilt into the slide's "
                    "coordinate space without the group transform."
                )
            trials: tuple[tuple[str, Sequence[ContainerMember]], ...] = tuple(
                (placement.label, placement.members) for placement in placements
            )
        else:
            if token is None:
                raise ObjectIsolationError(
                    f"{object_kind!r} has no canonical OfficeCLI element to rebuild."
                )
            trials = ((_PLACEMENT_SINGLE_OBJECT, ()),)

        stem = f"isolated-{slide_number:03d}-{abs(hash(source_object)) % 10**8:08d}"
        isolated = False
        geometry: ProxyGeometry | None = None
        refusals: list[str] = []
        try:
            # A container has one candidate per reading of its children; every
            # other kind has exactly one thing to rebuild, and its single trial
            # either produces the proxy or raises.  Each trial gets its own deck
            # and raster: a rejected candidate has been rendered -- and so has
            # been opened by the viewer -- and a file another resident still
            # holds cannot be reused, let alone removed.
            for label, members in trials:
                deck = self.work_dir / f"{stem}-{label}.pptx"
                raster = deck.with_suffix(".png")
                target.unlink(missing_ok=True)
                deck.unlink(missing_ok=True)
                raster.unlink(missing_ok=True)
                try:
                    additions = (
                        [
                            (member.source_kind, self._member_properties(member))
                            for member in members
                        ]
                        if is_container
                        else [
                            (
                                object_kind,
                                self._rebuild_properties(
                                    object_kind, bounds_pt, properties,
                                    media_path=media_path,
                                    text=text,
                                ),
                            )
                        ]
                    )
                    self._rebuild_isolated(
                        deck, additions, source_object=source_object
                    )
                    self._screenshot(deck, 1, raster)
                    if is_container:
                        refusal = self._placement_refusal(
                            raster, bounds_pt, guard_px=guard_px
                        )
                        if refusal is not None:
                            refusals.append(f"its {label} placement {refusal}")
                            continue
                    # The render's bare background is sampled once for both gates
                    # that need it: the crop measures the object's painted extent
                    # against it, and the blank-proxy gate asks whether the crop
                    # carries any paint at all.
                    background = _render_background(
                        _raster_rgb(raster),
                        bounds_pt,
                        pixels_per_point,
                        guard_px,
                    )
                    crop = self._crop(
                        raster,
                        bounds_pt,
                        slide_width_pt=self.slide_width_pt,
                        pixels_per_point=pixels_per_point,
                        guard_px=guard_px,
                        destination=target,
                        background=background,
                    )
                    if object_kind in _RECONSTRUCTED_PAINT_KINDS:
                        self._assert_visible_paint(
                            raster, target, bounds_pt, object_kind=object_kind,
                            source_object=source_object,
                            pixels_per_point=pixels_per_point,
                            guard_px=guard_px,
                            background=background,
                        )
                    geometry = crop
                    isolated = True
                    # The first candidate whose measured paint lands inside the
                    # container is the representation; a later reading never gets
                    # to replace it.
                    break
                finally:
                    _run_officecli("close", str(deck), check=False, attempts=2)
                    deck.unlink(missing_ok=True)
                    raster.unlink(missing_ok=True)
            if not isolated:
                # Only a container reaches this: its trials are all candidates,
                # and every one of them was measured and refused.
                raise ContainerReconciliationError(
                    f"{object_kind} {source_object} is not represented: "
                    + "; ".join(refusals)
                    + ". No candidate placement of its children puts visible "
                    "content inside the container's own rectangle, and an "
                    "invented or out-of-bounds image is never published as a "
                    "representation of it."
                )
        finally:
            if not isolated:
                # A render that did not survive every gate leaves no image
                # behind: a rejected proxy must not stay on disk looking like a
                # published one.
                target.unlink(missing_ok=True)
        if not target.is_file() or geometry is None:
            raise ObjectIsolationError(
                f"Isolated render produced no image for {source_object}."
            )
        return target, geometry

    def _rebuild_isolated(
        self,
        deck: Path,
        additions: Sequence[tuple[str, Mapping[str, str]]],
        *,
        source_object: str,
    ) -> None:
        """Rebuild one placement as the only content of a fresh deck."""
        deck.unlink(missing_ok=True)
        _run_officecli("create", str(deck))
        commands: list[dict[str, Any]] = [
            {
                "command": "set",
                "path": "/",
                "props": {
                    "slideWidth": f"{self.slide_width_pt:g}pt",
                    "slideHeight": f"{self.slide_height_pt:g}pt",
                },
            },
            {
                "command": "add",
                "parent": "/",
                "type": "slide",
                "props": {"name": "isolated"},
            },
        ]
        for member_kind, rebuild in additions:
            member_token = _CANONICAL_TOKEN.get(member_kind)
            if member_token is None:
                raise ObjectIsolationError(
                    f"{member_kind!r} has no canonical OfficeCLI element to "
                    f"rebuild for {source_object}."
                )
            commands.append(
                {
                    "command": "add",
                    "parent": "/slide[1]",
                    "type": member_token,
                    "props": dict(rebuild),
                }
            )
        _run_officecli("batch", str(deck), "--commands", json.dumps(commands))
        _run_officecli("close", str(deck))

        rendered = _run_officecli_json("get", str(deck), "/slide[1]", "--depth", "0")
        present = list(_children(rendered))
        if len(present) != len(additions):
            raise ObjectIsolationError(
                f"The rebuild for {source_object} produced "
                f"{[str(item.get('path')) for item in present]} instead of exactly "
                f"{len(additions)} object(s)."
            )

    def _placement_refusal(
        self,
        raster: Path,
        bounds_pt: tuple[float, float, float, float],
        *,
        guard_px: int,
    ) -> str | None:
        """Return why one candidate placement is not a representation, or ``None``.

        The reconstruction deck holds the container's children and nothing else,
        so the paint in its render *is* those children, wherever the candidate
        put them.  It is measured rather than taken from the candidate's own
        rectangles, because those rectangles are exactly what is in doubt: the
        placement is accepted only when its paint is non-empty and lands inside
        the container's own rectangle, within the antialiasing tolerance.

        When the container's rectangle leaves no sample point outside itself,
        there is no honest background to measure against, so no judgement is
        made here -- the blank-proxy gate downstream cannot judge either.
        """
        from PIL import Image

        with Image.open(raster) as image:
            rgb = image.convert("RGB")
            if self.slide_width_pt <= 0:
                raise ObjectIsolationError(
                    "The slide's point width must be positive to scale a proxy."
                )
            factor = rgb.width / self.slide_width_pt
            background = _render_background(rgb, bounds_pt, factor, guard_px)
            if background is None:
                return None
            # The raster's own edge is viewer chrome, not slide paint, so the
            # extent is measured one inset in and mapped back out afterwards.
            inset = _RASTER_INSET_PX
            field = rgb.crop(
                (inset, inset, rgb.width - inset, rgb.height - inset)
            )
            extent = _painted_extent(field, background)
        if extent is None:
            return "painted no visible paint"
        extent = (
            extent[0] + inset,
            extent[1] + inset,
            extent[2] + inset,
            extent[3] + inset,
        )
        left = int(round(bounds_pt[0] * factor))
        top = int(round(bounds_pt[1] * factor))
        right = left + int(round(bounds_pt[2] * factor))
        bottom = top + int(round(bounds_pt[3] * factor))
        tolerance = CONTAINER_PAINT_TOLERANCE_PX
        if (
            extent[0] < left - tolerance
            or extent[1] < top - tolerance
            or extent[2] > right + tolerance
            or extent[3] > bottom + tolerance
        ):
            painted = (
                round(extent[0] / factor, 4),
                round(extent[1] / factor, 4),
                round((extent[2] - extent[0]) / factor, 4),
                round((extent[3] - extent[1]) / factor, 4),
            )
            return (
                f"painted {painted} on the slide, outside the container's own "
                f"rectangle {tuple(round(value, 4) for value in bounds_pt)}"
            )
        return None

    @staticmethod
    def _rebuild_properties(
        object_kind: str,
        bounds_pt: tuple[float, float, float, float],
        properties: Mapping[str, Any],
        *,
        media_path: str | Path | None,
        text: str = "",
    ) -> dict[str, str]:
        """Return the OfficeCLI ``add`` props that reproduce the object's paint.

        A text-bearing object's paint is its text, so a ``shape`` or ``textbox``
        proxy carries the object's own text and text properties exactly as a
        container's text-bearing member does.  Without them the proxy is an image
        of the object's bare rectangle: the paint the object is *for* is dropped
        from the rebuilt deck, which is the one thing a locked visual proxy may
        never do.  The inherited value that made the object base-only in the
        first place -- a theme colour, typically -- is still not reproduced, and
        the object is still reported as base-only scope evidence for it.
        """
        rebuild: dict[str, str] = {
            "name": "isolated-object",
            "x": f"{bounds_pt[0]:g}pt",
            "y": f"{bounds_pt[1]:g}pt",
            "width": f"{bounds_pt[2]:g}pt",
            "height": f"{bounds_pt[3]:g}pt",
        }
        for key in rebuild_keys(object_kind):
            value = properties.get(key)
            if value is None:
                continue
            # ``value`` is the property's own text.  It is deliberately NOT
            # called ``text``: the object's captured text is a separate argument
            # of this method, and reusing the name for a property value silently
            # replaced the object's text with whatever the last property happened
            # to be -- which is how a text proxy once came out as the word
            # "rect" instead of the words it was supposed to represent.
            value_text = str(value).strip()
            if not value_text:
                continue
            # ``none`` is a real value for fill and line, but OfficeCLI rejects
            # it for a length or a geometry.
            if value_text.lower() == "none" and key not in {"fill", "line"}:
                continue
            if key in {"fill", "line"}:
                # A non-solid paint (a gradient, say) is named by kind in the
                # readback and is not a colour OfficeCLI accepts on write, so the
                # proxy carries the object's representative stop instead.
                paint = proxy_paint_value(key, value_text, properties)
                if paint is None:
                    continue
                rebuild[key] = paint
                continue
            rebuild[key] = value_text
        if object_kind == "connector":
            # The stroke a connector read back as ``color`` is written back as
            # ``line``; without it the rebuilt connector has no paint at all.
            stroke = connector_stroke(properties)
            if stroke is not None:
                rebuild["line"] = stroke
        if object_kind in _TEXTUAL_KINDS:
            _add_text_paint(rebuild, text, properties)
        if object_kind == "picture":
            if not media_path:
                raise ObjectIsolationError(
                    "A picture proxy needs the picture's own media to rebuild from."
                )
            rebuild["src"] = str(media_path)
        return rebuild

    @staticmethod
    def _member_properties(member: ContainerMember) -> dict[str, str]:
        """Return the ``add`` props that reproduce one container member.

        A container member is rebuilt from its own readback, exactly as a
        single-object proxy is.  The two kind-specific differences are that a
        connector's stroke is written as ``line`` rather than the ``color`` its
        readback reports, and that a text-bearing member carries its text so the
        container's visible content is not silently reduced to its shapes.
        """
        bounds_pt = member.bounds_pt
        rebuild: dict[str, str] = {
            "name": f"isolated-member-{abs(hash(member.source_object)) % 10**8:08d}",
            "x": f"{max(0.0, bounds_pt[0]):g}pt",
            "y": f"{max(0.0, bounds_pt[1]):g}pt",
            "width": f"{max(0.0, bounds_pt[2]):g}pt",
            "height": f"{max(0.0, bounds_pt[3]):g}pt",
        }
        properties = member.properties
        for key in rebuild_keys(member.source_kind):
            value = properties.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            if text.lower() == "none" and key not in {"fill", "line"}:
                continue
            if key in {"fill", "line"}:
                # Same rule as a single-object proxy: a paint named by kind in
                # the readback becomes the member's representative colour so the
                # container's reconstruction still renders.
                paint = proxy_paint_value(key, text, properties)
                if paint is None:
                    continue
                rebuild[key] = paint
                continue
            rebuild[key] = text
        if member.source_kind == "connector":
            stroke = connector_stroke(properties)
            if stroke is not None:
                rebuild["line"] = stroke
        if member.source_kind in _TEXTUAL_KINDS:
            _add_text_paint(rebuild, member.text, properties)
        if member.source_kind == "picture":
            if not member.media_path:
                raise ObjectIsolationError(
                    f"A container's picture member {member.source_object} needs its "
                    "own media to rebuild from."
                )
            rebuild["src"] = str(member.media_path)
        return rebuild

    @staticmethod
    def _assert_visible_paint(
        raster: Path,
        cropped: Path,
        bounds_pt: tuple[float, float, float, float],
        *,
        object_kind: str,
        source_object: str,
        pixels_per_point: float,
        guard_px: int,
        background: tuple[int, int, int] | None = None,
    ) -> None:
        """Refuse a reconstructed proxy that carries no paint at all.

        A container is represented by its children and a connector by its own
        stroke, so a reconstruction of either that comes out as bare slide
        background is not a representation of the object: publishing it would
        paint an empty rectangle where the source has content.  The background
        is read from a point of the render that is *outside* the object's own
        rectangle, so an object that genuinely fills the slide is never judged
        against itself.
        """
        from PIL import Image

        if background is None:
            background = _render_background(
                _raster_rgb(raster), bounds_pt, pixels_per_point, guard_px
            )
        if background is None:
            return
        with Image.open(cropped) as crop_image:
            painted = _carries_other_than(crop_image.convert("RGB"), background)
        if painted:
            return
        raise ContainerReconciliationError(
            f"The isolated reconstruction of {object_kind} {source_object} carries no "
            "visible paint, so it is not a representation of the object; a blank "
            "image is never published as a proxy."
        )

    @staticmethod
    def _screenshot(deck: Path, slide_number: int, raster: Path) -> None:
        """Render one slide of the rebuilt deck, retrying a transient failure."""
        last_error: Exception | None = None
        for attempt in range(5):
            raster.unlink(missing_ok=True)
            try:
                _run_officecli(
                    "view",
                    str(deck),
                    "screenshot",
                    "--page",
                    str(slide_number),
                    "--render",
                    SCREENSHOT_RENDER,
                    "--screenshot-width",
                    str(SCREENSHOT_VIEWPORT_WIDTH),
                    "-o",
                    str(raster),
                    attempts=4,
                )
            except PptxReadError as error:
                last_error = error
                _run_officecli("close", str(deck), check=False, attempts=2)
                time.sleep(0.6 * (attempt + 1))
                continue
            if raster.is_file():
                return
            _run_officecli("close", str(deck), check=False, attempts=2)
            time.sleep(0.6 * (attempt + 1))
        raise ObjectIsolationError(
            f"OfficeCLI did not render the isolated object after 5 attempts: "
            f"{last_error or 'no image was produced'}"
        )

    @staticmethod
    def _crop(
        raster: Path,
        bounds_pt: tuple[float, float, float, float],
        *,
        slide_width_pt: float,
        pixels_per_point: float,
        guard_px: int,
        destination: Path,
        background: tuple[int, int, int] | None = None,
    ) -> ProxyGeometry:
        """Crop the target's painted rectangle out of an isolated slide render.

        The render's own density is measured from the raster and the slide's
        point width, and it must reach ``pixels_per_point`` -- the density the
        Author canvas draws the proxy at.  A render below that density would be
        upscaled in the DOM, so it is a hard failure rather than a silently
        softened proxy.  The only tolerance is whole-pixel rounding of the
        render; a raster that merely clears some lower floor is not accepted.

        The crop is the union of the object's declared rectangle and the
        rectangle its paint actually occupies, because PowerPoint paints a
        no-autofit line outside its own box: a text object whose content
        overflows its declared rectangle is *supposed* to show that overflow, and
        cropping to the declared rectangle would slice those lines mid-glyph.
        The deck holds nothing but this object, so a wider crop can only ever add
        more of the object's own paint.

        The union never shrinks below the declared rectangle plus the guard band,
        so an object whose paint is entirely inside its own rectangle keeps
        exactly the geometry it had before.  When the measured paint reaches the
        render's own edge the crop is clamped and says so: an expansion that
        would leave the slide is recorded rather than silently swallowed.
        """
        from PIL import Image

        with Image.open(raster) as image:
            rgb = image.convert("RGB")
            raster_width, raster_height = rgb.size
            if slide_width_pt <= 0:
                raise ObjectIsolationError(
                    "The slide's point width must be positive to scale a proxy."
                )
            factor = raster_width / slide_width_pt
            required = float(pixels_per_point)
            if factor + PROXY_DENSITY_TOLERANCE < required:
                raise ObjectIsolationError(
                    f"The isolated render is only {factor:.4f} px/pt "
                    f"({raster_width}px for a {slide_width_pt:g}pt slide) but the "
                    f"Author canvas draws this proxy at {required:.4f} px/pt; a "
                    "render below the canvas density would be upscaled, so the "
                    "object is reported as unsupported instead."
                )
            left = int(round(bounds_pt[0] * factor)) - guard_px
            top = int(round(bounds_pt[1] * factor)) - guard_px
            width = int(round(bounds_pt[2] * factor)) + guard_px * 2
            height = int(round(bounds_pt[3] * factor)) + guard_px * 2
            if width <= 0 or height <= 0:
                raise ObjectIsolationError(
                    "A proxy rectangle must be positive; got "
                    f"{width}x{height} for bounds {bounds_pt}."
                )
            declared_right = left + width
            declared_bottom = top + height
            crop_left, crop_top = left, top
            crop_right, crop_bottom = declared_right, declared_bottom
            escaped = False
            extent = IsolatedRenderer._painted_extent(
                rgb, bounds_pt, factor, guard_px, background
            )
            if extent is not None:
                # The declared rectangle is already the floor, so paint inside it
                # -- including the object's own antialiased edge -- changes
                # nothing.  Only paint that reaches past it widens the crop, and
                # only while the reach is the object's own overflow rather than a
                # reconstruction whose layout has drifted: see
                # :data:`_PROXY_EXPANSION_SLACK_PX`.
                if (
                    extent[2] - extent[0] <= _expansion_limit(width)
                    and extent[3] - extent[1] <= _expansion_limit(height)
                ):
                    escaped = (
                        extent[0] < crop_left
                        or extent[1] < crop_top
                        or extent[2] > crop_right
                        or extent[3] > crop_bottom
                    )
                    crop_left = min(crop_left, extent[0])
                    crop_top = min(crop_top, extent[1])
                    crop_right = max(crop_right, extent[2])
                    crop_bottom = max(crop_bottom, extent[3])
            clamped = (
                escaped
                and (
                    crop_left < 0
                    or crop_top < 0
                    or crop_right > raster_width
                    or crop_bottom > raster_height
                )
            )
            crop_left = max(0, crop_left)
            crop_top = max(0, crop_top)
            crop_right = max(crop_left + 1, min(crop_right, raster_width))
            crop_bottom = max(crop_top + 1, min(crop_bottom, raster_height))
            cropped = rgb.crop((crop_left, crop_top, crop_right, crop_bottom))
            if cropped.width < 2 or cropped.height < 2:
                raise ObjectIsolationError(
                    f"The isolated render clipped {destination.name} to "
                    f"{cropped.width}x{cropped.height}px; the object's rectangle "
                    "is not fully inside the rendered slide."
                )
            cropped.save(destination, format="PNG")
        return ProxyGeometry(
            rect_px=(
                crop_left,
                crop_top,
                crop_right - crop_left,
                crop_bottom - crop_top,
            ),
            origin_px=(crop_left - left, crop_top - top),
            clamped=clamped,
        )

    @staticmethod
    def _painted_extent(
        rgb: Any,
        bounds_pt: tuple[float, float, float, float],
        factor: float,
        guard_px: int,
        background: tuple[int, int, int] | None,
    ) -> tuple[int, int, int, int] | None:
        """Return where this render's paint actually is, in raster pixels.

        The render holds the target object and nothing else, so its paint *is*
        the object -- wherever the object's own overflow put it.  The background
        to measure against is the same bare-render background the container
        placement gate samples, and when the declared rectangle leaves no honest
        sample point the measurement is simply not made.
        """
        if background is None:
            background = _render_background(rgb, bounds_pt, factor, guard_px)
        if background is None:
            return None
        # The raster's own edge is viewer chrome rather than slide paint, so the
        # extent is measured one inset in and mapped back out afterwards.
        inset = _RASTER_INSET_PX
        field = rgb.crop((inset, inset, rgb.width - inset, rgb.height - inset))
        extent = _painted_extent(field, background)
        if extent is None:
            return None
        return (
            extent[0] + inset,
            extent[1] + inset,
            extent[2] + inset,
            extent[3] + inset,
        )


def _nested_pictures(obj: CapturedObject) -> tuple[CapturedObject, ...]:
    """Return the picture objects a container owns at any depth.

    Grouped pictures are real slide-owned pictures, but a container whose
    native semantics cannot be preserved is emitted as one locked proxy, so its
    nested pictures are represented by that proxy rather than by a second copy
    of the same pixels.  Identifying them lets the projection report say so
    instead of silently dropping them.
    """
    found: list[CapturedObject] = []
    for child in obj.children:
        if child.source_kind == "picture":
            found.append(child)
        found.extend(_nested_pictures(child))
    return tuple(found)


def capture_presentation(
    pptx_path: str | Path,
    slide_numbers: Sequence[int],
    *,
    source_key: str = "",
) -> CapturedPresentation:
    """Capture the selected slides of one source PPTX through OfficeCLI.

    The source deck is only ever read: no OfficeCLI write command is issued
    against it, and every requested slide must exist before anything is
    captured.  ``source_key`` is the caller's stable identity for this deck and
    is stamped onto every captured page and object, because two decks can report
    the same ``source_object`` path.

    Capture is per deck and never discovers pages: the requested numbers are the
    only slides read, in the order given.
    """
    path = Path(pptx_path).expanduser()
    if not path.is_file():
        raise PptxReadError(f"Source PPTX does not exist: {path}")
    if not slide_numbers:
        raise PptxReadError("At least one source slide number must be selected.")
    requested: list[int] = []
    for number in slide_numbers:
        value = int(number)
        if value < 1:
            raise PptxReadError(f"Source slide numbers start at 1; got {value}.")
        if value not in requested:
            requested.append(value)

    root = _run_officecli_json("get", str(path), "/", "--depth", "1")
    root_format = dict(root.get("format") or {})
    slide_nodes = [
        child for child in _children(root) if str(child.get("type")) == "slide"
    ]
    slide_count = len(slide_nodes)
    if slide_count == 0:
        raise PptxReadError(f"OfficeCLI found no slides in {path}.")
    for number in requested:
        if number > slide_count:
            raise MissingSlideError(number, slide_count, str(path.resolve()))

    width_pt = length_to_points(root_format.get("slideWidth"))
    height_pt = length_to_points(root_format.get("slideHeight"))
    if width_pt <= 0 or height_pt <= 0:
        raise PptxReadError(
            "OfficeCLI did not report the presentation slide bounds "
            f"(slideWidth={root_format.get('slideWidth')!r}, "
            f"slideHeight={root_format.get('slideHeight')!r}); the Author "
            "canvas cannot be normalized without them."
        )

    slides: list[CapturedSlide] = []
    for number in requested:
        node = _run_officecli_json(
            "get", str(path), f"/slide[{number}]", "--depth", "5"
        )
        slide_format = dict(node.get("format") or {})
        line_breaks = _slide_line_breaks(path, number)
        objects = tuple(
            sorted(
                (
                    _captured_object(
                        child,
                        slide_number=number,
                        pptx_path=path,
                        capture_pictures=True,
                        source_key=source_key,
                        line_breaks=line_breaks,
                    )
                    for child in _children(node)
                ),
                key=lambda item: (item.z_order, item.source_object),
            )
        )
        slides.append(
            CapturedSlide(
                source_slide=number,
                layout=str(slide_format.get("layout") or ""),
                layout_type=str(slide_format.get("layoutType") or ""),
                width_pt=width_pt,
                height_pt=height_pt,
                background=_slide_background(slide_format),
                objects=objects,
                source_key=source_key,
            )
        )
    return CapturedPresentation(
        source_path=str(path.resolve()),
        slide_size_pt=(width_pt, height_pt),
        slide_count=slide_count,
        officecli_version=officecli_version(),
        slides=tuple(slides),
        source_key=source_key,
    )


__all__ = [
    "ADMITTED_PRESET_GEOMETRIES",
    "ALIGNMENT_DEFAULT",
    "BaseOnlyClaim",
    "CANONICAL_GEOMETRIES",
    "CONTAINER_KINDS",
    "CONTAINER_PAINT_TOLERANCE_PX",
    "CONTAINER_PLACEMENT_DECLARED",
    "CONTAINER_PLACEMENT_REPORTED",
    "CapturedObject",
    "CapturedParagraph",
    "CapturedPicture",
    "CapturedPresentation",
    "CapturedRun",
    "CapturedSlide",
    "CapturedTable",
    "CapturedTableCell",
    "ContainerMember",
    "ContainerPlacement",
    "ContainerPlacements",
    "ContainerReconciliationError",
    "EMU_PER_POINT",
    "IsolatedRenderer",
    "MissingSlideError",
    "NON_CANONICAL_KINDS",
    "OFFICECLI_TIMEOUT_SECONDS",
    "ObjectIsolationError",
    "PROXY_BACKGROUND_TOLERANCE",
    "PROXY_DENSITY_TOLERANCE",
    "PptxReadError",
    "ProxyGeometry",
    "SCREENSHOT_RENDER",
    "SCREENSHOT_VIEWPORT_WIDTH",
    "VISIBLE_BASE_ONLY_PROPERTIES",
    "alpha_of",
    "capture_presentation",
    "connector_stroke",
    "container_child_transform",
    "container_placements",
    "length_to_points",
    "map_child_bounds",
    "nested_pictures",
    "officecli_version",
    "parse_color",
    "points_to_emu",
    "rebuild_keys",
]
