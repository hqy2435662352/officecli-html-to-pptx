"""OfficeCLI-first compiler for native PowerPoint object slices.

The compiler lowers renderer-neutral Chromium measurements into a small
presentation-object IR and sends one JSON batch to OfficeCLI. The explicit
``officehtml`` profile consumes OfficeCLI's fixed-coordinate object projection
for internal object-level round trips.
"""

from __future__ import annotations

import base64
import binascii
from io import BytesIO
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from html import escape as _html_escape
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes
from xml.etree import ElementTree

from PIL import Image
from lxml import html as _lxml_html

from ..contract import (
    CANONICAL_RUN_IDENTITY_FIELDS,
    LIST_MARKER_PRESETS,
    SUPPORTED_INLINE_ELEMENTS,
    ContractReport,
    _inline_styles,
    _officehtml_parser,
    _officehtml_picture_source,
    _resolve_text_alignment,
    TableTopologyError,
    build_logical_table_grid,
    check_contract,
)
from ..measurement import extract_measurements
from ..styles import resolve_pptx_font as _resolve_pptx_font

SLIDE_WIDTH_PT = 960.0
SLIDE_HEIGHT_PT = 540.0
_COLOR_RE = re.compile(
    r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)"
    r"(?:\s*,\s*([\d.]+))?\s*\)"
)
_HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{3,8})$")
_BATCH_INDEX_RE = re.compile(r"\[(\d+)\]")
_DATA_URI_RE = re.compile(
    r"^data:(?P<mime>[^;,]+)(?P<meta>(?:;[^,]*)*),(?P<payload>.*)$",
    re.DOTALL,
)
_SVG_CAPABILITY_PROBE = (
    "data:image/svg+xml;base64," + base64.b64encode(
        b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="6">'
        b'<rect width="8" height="6" fill="#e60012"/></svg>'
    ).decode("ascii")
)
_OFFICECLI_SVG_SUPPORT: bool | None = None
_OFFICECLI_BATCH_MAX_BYTES = 32 * 1024 * 1024
# The accepted inline element set is owned by the Contract authority that
# ``capabilities`` publishes, so the lowered inline surface and the declared
# one cannot drift apart.
_INLINE_TAGS = frozenset(SUPPORTED_INLINE_ELEMENTS)
_CSS_LENGTH_RE = re.compile(
    r"^\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*(pt|px|cm|mm|in|emu)?\s*$",
    re.IGNORECASE,
)
_BORDER_RE = re.compile(
    r"^\s*(?P<width>-?(?:\d+(?:\.\d*)?|\.\d+)(?:pt|px|cm|mm|in|emu)?)\s+"
    r"(?P<style>solid|dashed|dotted|double|none|hidden)\s+"
    r"(?P<color>#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)|[a-zA-Z]+)\s*$",
    re.IGNORECASE,
)
_OFFICEHTML_PATH_KIND_RE = re.compile(r"/(table|picture|shape)\[", re.IGNORECASE)


@dataclass(frozen=True)
class CompilationDiagnostic:
    """A structured compiler diagnostic exposed on failures and results."""

    severity: str
    code: str
    message: str
    source_slide: int | None = None
    source_object: str | None = None
    operation: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "source_slide": self.source_slide,
            "source_object": self.source_object,
            "operation": self.operation,
        }


class OfficeCLICompilationError(RuntimeError):
    """Compilation failed before a final output was delivered."""

    def __init__(
        self,
        message: str,
        diagnostics: Iterable[CompilationDiagnostic] = (),
    ) -> None:
        super().__init__(message)
        self.diagnostics = tuple(diagnostics)


@dataclass(frozen=True)
class OfficeCLICompilationResult:
    """Result of a successful public compiler operation."""

    output_path: str
    profile: str
    slide_count: int
    object_count: int
    diagnostics: tuple[CompilationDiagnostic, ...]
    manifest: dict[str, Any]

    def __str__(self) -> str:
        return self.output_path

    def __fspath__(self) -> str:
        return self.output_path


@dataclass(frozen=True)
class _TableCellIR:
    name: str
    source_slide: int
    source_object: str
    bounds: tuple[float, float, float, float]
    text: str
    props: dict[str, str]
    paragraphs: tuple[dict[str, Any], ...] = ()
    row: int = 0
    column: int = 0
    row_span: int = 1
    column_span: int = 1
    anchor: bool = True

    def as_manifest(self) -> dict[str, Any]:
        return {
            "kind": "cell",
            "name": self.name,
            "source_slide": self.source_slide,
            "source_object": self.source_object,
            "bounds_pt": list(self.bounds),
            "text": self.text,
            "props": dict(self.props),
            "paragraphs": list(self.paragraphs),
            "row": self.row,
            "column": self.column,
            "row_span": self.row_span,
            "column_span": self.column_span,
            "anchor": self.anchor,
        }


@dataclass(frozen=True)
class _ObjectIR:
    kind: str
    name: str
    source_slide: int
    source_object: str
    bounds: tuple[float, float, float, float]
    props: dict[str, str]
    text: str = ""
    fallback_props: dict[str, str] | None = None
    paragraphs: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] | None = None
    table_cells: tuple[_TableCellIR, ...] = ()
    row_heights: tuple[float, ...] = ()
    column_widths: tuple[float, ...] = ()

    def as_manifest(self) -> dict[str, Any]:
        manifest = {
            "kind": self.kind,
            "name": self.name,
            "source_slide": self.source_slide,
            "source_object": self.source_object,
            "bounds_pt": list(self.bounds),
            "text": self.text,
            "properties": {
                key: value
                for key, value in self.props.items()
                if key not in {"name", "text", "src"}
            },
            "paragraphs": list(self.paragraphs),
        }
        if self.metadata and self.kind != "table":
            manifest["metadata"] = dict(self.metadata)
        if self.kind == "table":
            manifest.update(
                {
                    "rows": len(self.row_heights),
                    "columns": len(self.column_widths),
                    "column_widths_pt": list(self.column_widths),
                    "row_heights_pt": list(self.row_heights),
                    "normalized_merge_topology": list(
                        (self.metadata or {}).get("normalized_merge_topology", [])
                    ),
                    "cells": [cell.as_manifest() for cell in self.table_cells],
                }
            )
        return manifest


@dataclass
class _SlideIR:
    source_index: int
    name: str
    background: str
    objects: list[_ObjectIR]


class _OfficeCLICommandError(RuntimeError):
    def __init__(
        self,
        operation: str,
        args: Sequence[str],
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> None:
        self.operation = operation
        self.args = tuple(args)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        details = (stderr or stdout).strip() or f"exit code {returncode}"
        super().__init__(f"officecli {operation} failed: {details}")


def _officecli_executable() -> str:
    executable = shutil.which("officecli")
    if executable is None:
        raise OfficeCLICompilationError(
            "OfficeCLI executable was not found on PATH.",
            [CompilationDiagnostic("error", "officecli_unavailable", "Install OfficeCLI 1.0.151 and add it to PATH.")],
        )
    return executable


def _run_officecli(
    args: Sequence[str],
    *,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    executable = _officecli_executable()
    try:
        result = subprocess.run(
            [executable, *args],
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise OfficeCLICompilationError(
            "OfficeCLI executable could not be started.",
            [CompilationDiagnostic("error", "officecli_unavailable", str(exc))],
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise OfficeCLICompilationError(
            f"OfficeCLI {args[0] if args else 'command'} timed out.",
            [CompilationDiagnostic("error", "officecli_timeout", str(exc))],
        ) from exc

    if check and result.returncode != 0:
        raise _OfficeCLICommandError(
            args[0] if args else "command",
            args,
            result.returncode,
            result.stdout,
            result.stderr,
        )
    return result


def _officecli_supports_svg() -> bool:
    """Return whether OfficeCLI renders SVG data URIs instead of blank PNGs."""
    global _OFFICECLI_SVG_SUPPORT
    if _OFFICECLI_SVG_SUPPORT is not None:
        return _OFFICECLI_SVG_SUPPORT

    probe_directory = Path(tempfile.mkdtemp(prefix=".officecli-svg-probe-"))
    probe_pptx = probe_directory / "probe.pptx"
    probe_png = probe_directory / "probe.png"
    resident = False
    read_resident = False
    supported = False
    try:
        _run_officecli(["create", str(probe_pptx)])
        resident = True
        commands = [
            {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
            {"command": "add", "parent": "/", "type": "slide", "props": {"name": "probe-slide"}},
            {
                "command": "add",
                "parent": "/slide[1]",
                "type": "picture",
                "props": {
                    "name": "probe-picture",
                    "x": "0pt",
                    "y": "0pt",
                    "width": "8pt",
                    "height": "6pt",
                    "src": _SVG_CAPABILITY_PROBE,
                },
            },
        ]
        _run_officecli(
            ["batch", str(probe_pptx)],
            input_text=json.dumps(commands, separators=(",", ":")),
        )
        _run_officecli(["close", str(probe_pptx)], check=False)
        resident = False
        read_resident = True
        details = _run_officecli(
            ["get", str(probe_pptx), "/slide[1]/picture[1]", "--json"]
        )
        try:
            format_data = json.loads(details.stdout)["data"]["results"][0]["format"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            format_data = {}
        if format_data.get("contentType") == "image/svg+xml":
            supported = True
        else:
            _run_officecli(
                ["get", str(probe_pptx), "/slide[1]/picture[1]", "--save", str(probe_png)]
            )
            with Image.open(probe_png) as image:
                supported = image.size != (1, 1) and image.convert("RGBA").getbbox() is not None
    except (_OfficeCLICommandError, OfficeCLICompilationError, OSError):
        supported = False
    finally:
        if resident or read_resident:
            _run_officecli(["close", str(probe_pptx)], check=False)
        shutil.rmtree(probe_directory, ignore_errors=True)

    _OFFICECLI_SVG_SUPPORT = supported
    return supported


def _parse_css_color(value: Any) -> tuple[tuple[int, int, int], float] | None:
    if not isinstance(value, str) or not value or value == "transparent":
        return None
    match = _COLOR_RE.fullmatch(value.strip())
    if match:
        channels = (
            round(float(match.group(1))),
            round(float(match.group(2))),
            round(float(match.group(3))),
        )
        alpha = float(match.group(4)) if match.group(4) is not None else 1.0
        rgb = tuple(max(0, min(255, channel)) for channel in channels)
        return (rgb[0], rgb[1], rgb[2]), max(0.0, min(1.0, alpha))
    match = _HEX_COLOR_RE.fullmatch(value.strip())
    if not match:
        return None
    raw = match.group(1)
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    if len(raw) == 8:
        alpha = int(raw[6:8], 16) / 255
        raw = raw[:6]
    else:
        alpha = 1.0
    rgb = tuple(int(raw[offset:offset + 2], 16) for offset in (0, 2, 4))
    return (rgb[0], rgb[1], rgb[2]), alpha


def _hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _hex_with_alpha(rgb: tuple[int, int, int], alpha: float) -> str:
    alpha_byte = round(max(0.0, min(1.0, alpha)) * 255)
    return f"{_hex(rgb)}{alpha_byte:02X}"


def _blend(
    foreground: tuple[int, int, int],
    alpha: float,
    background: tuple[int, int, int],
) -> tuple[int, int, int]:
    return (
        round(foreground[0] * alpha + background[0] * (1 - alpha)),
        round(foreground[1] * alpha + background[1] * (1 - alpha)),
        round(foreground[2] * alpha + background[2] * (1 - alpha)),
    )


def _source_path(slide_number: int, parent: str, tag: str, position: int) -> str:
    prefix = f"slide[{slide_number}]"
    if parent:
        prefix = parent
    return f"{prefix}/{tag or 'element'}[{position}]"


def _text_of(element: dict[str, Any]) -> str:
    # ``visualLines`` is a browser measurement/evidence field.  It is never a
    # source-structure authority: soft wrapping must remain inside one native
    # paragraph, while an authored ``<br>`` is represented as ``\v`` by the
    # paragraph normalizer below.
    paragraphs = element.get("paragraphs")
    if paragraphs:
        return "\n".join(
            str(paragraph.get("text", "")) for paragraph in paragraphs
        )
    runs = element.get("inlineRuns")
    if runs:
        return "".join(str(run.get("text", "")) for run in runs)
    return str(element.get("text", "") or "")


def _paragraphs_text(paragraphs: Sequence[dict[str, Any]]) -> str:
    """Return the native text body for a normalized paragraph sequence.

    OfficeCLI creates one native paragraph per ``\\n`` in the text body, so the
    object text must be derived from exactly the paragraphs the run ranges are
    computed from.  Deriving them separately is what misaligns a range after a
    visual-line split or a supplementary Unicode character.
    """
    return "\n".join(str(paragraph.get("text", "")) for paragraph in paragraphs)


def _underline_value(value: Any) -> str:
    tokens = str(value or "").lower().replace(",", " ").split()
    if "underline" in tokens:
        return "single"
    return "none"


def _paragraph_line_spacing(
    paragraph: dict[str, Any],
    element: dict[str, Any],
    *,
    legacy_css_pixel_projection: bool = False,
    preserve_table_projection: bool = False,
) -> str | None:
    """Return one paragraph's leading as a ratio of its own font size.

    The font size a *pixel* line height is divided by is the **element's**, not the
    paragraph's first run's, and that is not a detail: a used ``lineHeight`` in px is
    the element's own ``font-size`` multiplied by the declared ratio, so the element
    is the only basis it can be attributed to.

    Dividing it by a run instead inflated a paragraph whose first run is smaller than
    the block's own font -- which is what a **re-partitioned** paragraph is: the
    independent review found the synthetic probe's hard-break body compiled at
    ``lnSpc 254500`` (the block's 40px-based 56px leading divided by the fragment's
    22px run), so the rebuilt page painted a blank line where the source paints two
    adjacent ones.  A unitless ``lineHeight`` needs no font size at all: the ratio is
    the value itself.
    """
    raw_line_height = paragraph.get("lineHeight") or element.get("lineHeight")
    if not raw_line_height:
        return None
    first_run = (paragraph.get("runs") or [{}])[0]
    run_size = _number(first_run.get("fontSize"))
    element_size = _number(element.get("fontSize"))
    pixels = re.search(r"(?:px|pt)\s*$", str(raw_line_height).strip(), re.IGNORECASE)
    font_size = element_size if pixels else (run_size or element_size)
    # The keyword arguments remain accepted for callers from the previous
    # compiler surface, but Contract 1.1 has one line-height rule for every
    # native paragraph: positive px is divided by the element font size with
    # no content- or profile-specific projection.
    return _line_spacing(
        {"fontSize": font_size, "lineHeight": str(raw_line_height)}
    )


def _canonical_run_key(run: dict[str, Any]) -> tuple[Any, ...]:
    """Return the Paragraph-local identity of one resolved run.

    A run boundary is a formatting boundary, not a DOM node boundary.  Two
    adjacent runs with the same resolved properties from the closed Contract
    1.1 matrix are one Canonical Run; anything else stays a boundary.
    The identity dimensions are exactly the ones
    ``contract.CANONICAL_RUN_IDENTITY`` declares, which is also the declaration
    ``capabilities`` publishes, so the published mixed-run surface and this key
    cannot drift apart.  Every value is read from the normalization above, which
    already produced the canonical type of each field (a bool for
    ``bold``/``italic``), so no coercion can distinguish two runs.
    """
    return tuple(run.get(field) for field in CANONICAL_RUN_IDENTITY_FIELDS)


def _canonical_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge adjacent identical runs and concatenate their text exactly.

    Merging never trims, normalizes, or otherwise mutates text, so an authored
    boundary space survives: ``North`` followed by `` Africa`` becomes the
    single Canonical Run ``North Africa``.  Merging is only ever applied to the
    runs of one paragraph, so it can never cross a paragraph, list-item, or
    <br> boundary.
    """
    merged: list[dict[str, Any]] = []
    for run in runs:
        if merged and _canonical_run_key(merged[-1]) == _canonical_run_key(run):
            merged[-1]["text"] = merged[-1]["text"] + run["text"]
            continue
        merged.append(dict(run))
    return merged


def _canonical_source_runs(
    raw_paragraph: dict[str, Any],
    element: dict[str, Any],
    scale_x: float,
    backdrop: tuple[int, int, int],
    element_opacity: float,
) -> list[dict[str, Any]]:
    """Normalize one measured paragraph's visible runs.

    ``<br>`` is an authored hard break inside the paragraph.  The visible
    runs on either side remain separate native ranges, while the paragraph
    text carries OfficeCLI's ``\v`` control character.  Soft browser wrapping
    is intentionally absent from this function.
    """
    runs, _text, _break_offsets = _canonical_source_runs_with_breaks(
        raw_paragraph, element, scale_x, backdrop, element_opacity
    )
    return runs


def _canonical_source_runs_with_breaks(
    raw_paragraph: dict[str, Any],
    element: dict[str, Any],
    scale_x: float,
    backdrop: tuple[int, int, int],
    element_opacity: float,
) -> tuple[list[dict[str, Any]], str, list[int]]:
    """Return canonical visible runs, native text, and hard-break offsets."""

    def normalize(raw_run: dict[str, Any], text: str) -> dict[str, Any]:
        color = _parse_css_color(raw_run.get("color"))
        if color is None:
            color_value = None
        else:
            rgb, alpha = color
            if element_opacity < 0.999:
                color_value = _hex_with_alpha(rgb, alpha * element_opacity)
            else:
                color_value = _hex(
                    rgb if alpha >= 0.999 else _blend(rgb, alpha, backdrop)
                )
        font_size = _number(
            raw_run.get("fontSize"), _number(element.get("fontSize"))
        )
        return {
            "text": text,
            "font_family": _resolve_pptx_font(
                str(raw_run.get("fontFamily") or element.get("fontFamily") or "")
            ),
            "font_size_pt": _pt(font_size, scale_x) if font_size > 0 else 0.0,
            "bold": _is_bold(raw_run.get("fontWeight", element.get("fontWeight"))),
            "italic": str(
                raw_run.get("fontStyle", element.get("fontStyle", ""))
            ).lower() in {"italic", "oblique"},
            "underline": _underline_value(
                raw_run.get("textDecoration", raw_run.get("text-decoration"))
            ),
            "color": color_value,
        }

    segments: list[list[dict[str, Any]]] = [[]]
    for raw_run in raw_paragraph.get("runs") or []:
        source = dict(raw_run)
        text = str(source.get("text", ""))
        is_break = bool(source.get("br"))
        if is_break:
            segments.append([])
            continue
        pieces = text.split("\n") if text else []
        for piece_index, piece in enumerate(pieces):
            if piece:
                segments[-1].append(normalize(source, piece))
            if piece_index < len(pieces) - 1:
                segments.append([])

    canonical_segments = [_canonical_runs(segment) for segment in segments]
    visible_texts = ["".join(run["text"] for run in segment) for segment in canonical_segments]
    paragraph_text = "\v".join(visible_texts)
    hard_break_offsets: list[int] = []
    offset = 0
    for index, visible_text in enumerate(visible_texts[:-1]):
        offset += _officecli_range_length(visible_text)
        hard_break_offsets.append(offset)
        # The native range scope does not count the hard-break control itself.
    return (
        [run for segment in canonical_segments for run in segment],
        paragraph_text,
        hard_break_offsets,
    )


def _text_paragraphs(
    element: dict[str, Any],
    scale_x: float,
    scale_y: float,
    backdrop: tuple[int, int, int],
    *,
    preserve_table_projection: bool = False,
    preserve_paragraph_spacing: bool = False,
) -> tuple[dict[str, Any], ...]:
    raw_paragraphs = element.get("paragraphs") or []
    element_opacity = max(0.0, min(1.0, _number(element.get("opacity"), 1.0)))
    if not raw_paragraphs:
        runs = element.get("inlineRuns") or []
        if runs:
            # ``paragraphs`` is the authored block boundary.  This fallback is
            # only for older measurement payloads that supplied inline runs but
            # no paragraph list; keep all runs in one paragraph and let ``br``
            # normalization preserve hard-break topology.
            raw_paragraphs = [{"runs": [dict(run) for run in runs]}]
        elif _text_of(element):
            raw_paragraphs = [{
                "runs": [{
                    "text": _text_of(element),
                    "color": element.get("color"),
                    "fontSize": element.get("fontSize"),
                    "fontFamily": element.get("fontFamily"),
                    "fontWeight": element.get("fontWeight"),
                    "fontStyle": element.get("fontStyle"),
                    "textDecoration": element.get("textDecoration"),
                }]
            }]

    result: list[dict[str, Any]] = []
    for raw_paragraph in raw_paragraphs:
        normalized_runs, paragraph_text, hard_break_offsets = _canonical_source_runs_with_breaks(
            raw_paragraph, element, scale_x, backdrop, element_opacity
        )
        direction = str(
            raw_paragraph.get("direction", element.get("direction", "ltr")) or "ltr"
        ).lower()
        alignment_source = {
            "textAlign": raw_paragraph.get(
                "align", element.get("textAlign", "left")
            ),
            "direction": direction,
        }
        line_spacing = _paragraph_line_spacing(raw_paragraph, element)
        result.append(
            {
                "text": paragraph_text,
                "align": _text_alignment(alignment_source),
                "line_spacing": line_spacing,
                # getBoundingClientRect() already includes the position caused
                # by a block's CSS margins.  Re-emitting those margins on a
                # standalone OfficeCLI text body double-counts the spacing and
                # can make a browser two-line block overflow vertically.  A
                # table cell is different: its child paragraphs are folded
                # into the cell body, so their spacing still needs projection.
                "space_before_pt": (
                    _pt(_number(raw_paragraph.get("spaceBefore")), scale_y)
                    if preserve_table_projection or preserve_paragraph_spacing
                    else 0.0
                ),
                "space_after_pt": (
                    _pt(_number(raw_paragraph.get("spaceAfter")), scale_y)
                    if preserve_table_projection or preserve_paragraph_spacing
                    else 0.0
                ),
                "direction": direction,
                "runs": normalized_runs,
                "hard_break_offsets": hard_break_offsets,
            }
        )
    return tuple(result)


def _paragraph_props(paragraph: dict[str, Any]) -> dict[str, str]:
    props: dict[str, str] = {"align": str(paragraph.get("align", "left"))}
    if paragraph.get("line_spacing"):
        props["lineSpacing"] = str(paragraph["line_spacing"])
    if _number(paragraph.get("space_before_pt")) > 0:
        props["spaceBefore"] = _length(_number(paragraph["space_before_pt"]))
    if _number(paragraph.get("space_after_pt")) > 0:
        props["spaceAfter"] = _length(_number(paragraph["space_after_pt"]))
    if str(paragraph.get("direction", "ltr")).lower() == "rtl":
        props["direction"] = "rtl"
    marker = str(paragraph.get("list") or "")
    if marker:
        # A Native List Paragraph keeps its bullet or automatic number, its
        # list level, and its indentation as native paragraph properties.  The
        # marker is never literal text: ``list`` writes ``a:buChar`` for the
        # bullet preset and ``a:buAutoNum`` for automatic numbering,
        # ``marginLeft`` writes the list's own @marL, and ``indent`` hangs the
        # marker box one em left of the item's text edge.
        props["list"] = marker
        props["level"] = str(int(_number(paragraph.get("level"))))
        props["marginLeft"] = _length(_number(paragraph.get("margin_left_pt")))
        indent_pt = _number(paragraph.get("indent_pt"))
        if indent_pt:
            props["indent"] = _length(indent_pt)
    return props


def _list_items(list_element: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the direct ``li`` children of a measured list, in source order."""
    return [
        child
        for child in list_element.get("children", []) or []
        if str(child.get("tag", "element") or "element").lower() == "li"
    ]


def _empty_item_paragraph(
    item: dict[str, Any],
    scale_y: float,
) -> dict[str, Any]:
    """One Native List Paragraph for an authored item that has no text.

    An authored empty item is still one Native List Paragraph; it keeps the
    item's own measured paragraph spacing so the items after it do not move.
    """
    raw = (item.get("paragraphs") or [{}])[0]
    return {
        "text": "",
        "align": _text_alignment(item),
        "line_spacing": _line_spacing(item),
        "space_before_pt": _pt(_number(raw.get("spaceBefore")), scale_y),
        "space_after_pt": _pt(_number(raw.get("spaceAfter")), scale_y),
        "direction": str(item.get("direction", "ltr") or "ltr"),
        "runs": [],
    }


def _list_paragraphs(
    list_element: dict[str, Any],
    scale_x: float,
    scale_y: float,
    backdrop: tuple[int, int, int],
    source_slide: int,
    source_object: str,
) -> tuple[dict[str, Any], ...]:
    """Return one Native List Paragraph per direct item of one measured list.

    The list keeps one object identity: every direct ``li`` contributes exactly
    one paragraph, in source order, carrying the item's own runs (Canonical Run
    normalization stays inside that one paragraph) plus the native list
    properties the list element and its items measured.
    """
    list_facts = list_element.get("list") or {}
    list_kind = str(list_facts.get("kind") or list_element.get("tag") or "")
    list_x = _number(list_element.get("x"))
    paragraphs: list[dict[str, Any]] = []
    for position, item in enumerate(_list_items(list_element), start=1):
        item_facts = item.get("listItem") or {}
        item_paragraphs = _text_paragraphs(
            item,
            scale_x,
            scale_y,
            backdrop,
            preserve_paragraph_spacing=True,
        )
        if not item_paragraphs:
            item_paragraphs = (_empty_item_paragraph(item, scale_y),)
        if len(item_paragraphs) != 1:
            raise _diagnostic(
                "multi_paragraph_list_item",
                f"List item {_source_path(source_slide, source_object, 'li', position)} "
                f"measures {len(item_paragraphs)} native paragraphs; the declared "
                "list surface is one Native List Paragraph per direct item.",
                source_slide,
                _source_path(source_slide, source_object, "li", position),
            )
        paragraph = dict(item_paragraphs[0])
        first_run = (paragraph.get("runs") or [{}])[0]
        font_size_pt = _number(
            first_run.get("font_size_pt"),
            _pt(_number(item.get("fontSize")), scale_x),
        )
        paragraph["list"] = str(
            item_facts.get("marker")
            or LIST_MARKER_PRESETS.get(list_kind, "bullet")
        )
        paragraph["level"] = int(_number(item_facts.get("level")))
        paragraph["margin_left_pt"] = _pt(_number(item.get("x")) - list_x, scale_x)
        paragraph["indent_pt"] = -font_size_pt if font_size_pt > 0 else 0.0
        paragraphs.append(paragraph)
    return tuple(paragraphs)


def _run_props(run: dict[str, Any]) -> dict[str, str]:
    props: dict[str, str] = {}
    if run.get("font_family"):
        props["font"] = str(run["font_family"])
    if _number(run.get("font_size_pt")) > 0:
        props["size"] = _length(_number(run["font_size_pt"]))
    if run.get("color"):
        props["color"] = str(run["color"])
    # Write explicit false/none values as well.  A direct run must be able to
    # reset a bold/italic/underline value inherited from the parent or a
    # preceding run; omitting the property silently flattens mixed formatting.
    props["bold"] = "true" if run.get("bold") else "false"
    props["italic"] = "true" if run.get("italic") else "false"
    props["underline"] = str(run.get("underline") or "none")
    return props


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _measured_table_span(value: Any) -> str | None:
    """Convert a measured span to strict integer text for topology validation."""

    if value is None:
        return None
    number = _number(value, float("nan"))
    if number == number and number.is_integer():
        return str(int(number))
    return str(value)


def _officehtml_style(element: Any) -> dict[str, str]:
    """Read the inline CSS emitted by OfficeCLI 1.0.151.

    OfficeHTML is a decompiler projection, not an authoring stylesheet.  Its
    slide-owned object geometry and formatting are serialized inline, which
    lets the reverse profile parse it without running a second browser layout
    pass or treating the viewer shell as slide content.
    """
    return _inline_styles(element)


def _officehtml_length(value: Any, default: float = 0.0) -> float:
    """Convert an OfficeHTML CSS length to points."""
    if value is None:
        return default
    match = _CSS_LENGTH_RE.fullmatch(str(value))
    if match is None:
        return default
    amount = float(match.group(1))
    unit = (match.group(2) or "pt").lower()
    return {
        "pt": amount,
        "px": amount * 0.75,
        "cm": amount * 72 / 2.54,
        "mm": amount * 72 / 25.4,
        "in": amount * 72,
        "emu": amount / 12_700,
    }[unit]


def _officehtml_box_values(value: Any) -> tuple[float, float, float, float]:
    parts = [part for part in str(value or "").split() if part]
    if not parts:
        return 0.0, 0.0, 0.0, 0.0
    values = [_officehtml_length(part) for part in parts]
    if len(values) == 1:
        return values[0], values[0], values[0], values[0]
    if len(values) == 2:
        return values[0], values[1], values[0], values[1]
    if len(values) == 3:
        return values[0], values[1], values[2], values[1]
    return tuple(values[:4])  # type: ignore[return-value]


def _officehtml_padding(styles: dict[str, str]) -> tuple[float, float, float, float]:
    values = list(_officehtml_box_values(styles.get("padding")))
    names = ("top", "right", "bottom", "left")
    for index, name in enumerate(names):
        property_name = f"padding-{name}"
        if property_name in styles:
            values[index] = _officehtml_length(styles[property_name])
    return tuple(values)  # type: ignore[return-value]


def _officehtml_border(
    styles: dict[str, str], side: str = "",
) -> tuple[str | None, float, str | None]:
    property_name = f"border-{side}" if side else "border"
    shorthand = styles.get(property_name)
    if shorthand:
        match = _BORDER_RE.fullmatch(shorthand)
        if match:
            return (
                match.group("color"),
                _officehtml_length(match.group("width")),
                match.group("style").lower(),
            )
    prefix = f"border-{side}-" if side else "border-"
    color = styles.get(prefix + "color")
    width = _officehtml_length(styles.get(prefix + "width"))
    style = styles.get(prefix + "style")
    return color, width, style.lower() if style else None


def _officehtml_background(styles: dict[str, str]) -> tuple[str | None, str | None]:
    image_value = styles.get("background-image")
    if image_value and image_value.lower() not in {"none", "transparent"}:
        return None, image_value
    value = styles.get("background-color") or styles.get("background")
    if not value or value.lower() in {"transparent", "none"}:
        return None, None
    if "gradient(" in value or "url(" in value:
        return None, value
    return value, None


def _officehtml_class_tokens(element: Any) -> set[str]:
    return set(str(element.get("class", "") or "").split())


def _officehtml_bounds(element: Any) -> tuple[float, float, float, float]:
    styles = _officehtml_style(element)
    return tuple(
        _officehtml_length(styles.get(name))
        for name in ("left", "top", "width", "height")
    )  # type: ignore[return-value]


def _officehtml_text(element: Any) -> str:
    paragraphs = element.xpath(
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' para ')]"
    )
    if not paragraphs:
        values = [str(value) for value in element.itertext()]
    else:
        values = ["".join(str(value) for value in para.itertext()) for para in paragraphs]
    normalized = [value.replace("\u00a0", " ") for value in values]
    # Preserve whitespace-only text bodies.  The OfficeHTML projection uses a
    # literal space in several otherwise-empty text boxes to retain a native
    # object.  Stripping it here changes the object kind on the B round trip
    # from textbox to transparent shape and shifts every following identity.
    if any(value for value in normalized):
        return "\n".join(normalized)
    return ""


def _officehtml_text_node(element: Any) -> Any | None:
    paragraphs = element.xpath(
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' para ')]"
    )
    for paragraph in paragraphs:
        if _officehtml_text(paragraph):
            spans = paragraph.xpath(".//span")
            return spans[0] if spans else paragraph
    return None


def _officehtml_paragraphs(
    element: Any,
    fallback: dict[str, str],
    *,
    undo_officecli_projection: bool = False,
) -> list[dict[str, Any]]:
    paragraph_nodes = element.xpath(
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' para ')]"
    )
    if not paragraph_nodes and _officehtml_text(element):
        paragraph_nodes = [element]
    result: list[dict[str, Any]] = []
    for paragraph in paragraph_nodes:
        paragraph_styles = dict(fallback)
        paragraph_styles.update(_officehtml_style(paragraph))
        spans = paragraph.xpath(".//span")
        if not spans and _officehtml_text(paragraph):
            spans = [paragraph]
        runs: list[dict[str, Any]] = []
        for span in spans:
            span_styles = dict(paragraph_styles)
            span_styles.update(_officehtml_style(span))
            text = "".join(str(value) for value in span.itertext())
            if not text or not text.replace("\u00a0", " ").strip():
                continue
            runs.append(
                {
                    "text": text.replace("\u00a0", " "),
                    "color": span_styles.get("color"),
                    "fontSize": _officehtml_length(span_styles.get("font-size")),
                    "fontFamily": span_styles.get("font-family", ""),
                    "fontWeight": span_styles.get("font-weight", "400"),
                    "fontStyle": span_styles.get("font-style", "normal"),
                    "textDecoration": span_styles.get("text-decoration", "none"),
                }
            )
        result.append(
            {
                "text": "".join(str(run["text"]) for run in runs),
                "align": paragraph_styles.get("text-align", "left"),
                "lineHeight": _officehtml_line_height(
                    paragraph_styles.get("line-height"),
                    undo_officecli_projection=undo_officecli_projection,
                ),
                "spaceBefore": _officehtml_length(
                    paragraph_styles.get("margin-top")
                ),
                "spaceAfter": _officehtml_length(
                    paragraph_styles.get("margin-bottom")
                ),
                "direction": paragraph_styles.get("direction", "ltr"),
                "runs": runs,
            }
        )
    return result


def _officehtml_line_height(
    value: str | None, *, undo_officecli_projection: bool = False
) -> str | None:
    """Return a line-height ready for the lowering path.

    ``undo_officecli_projection`` exists because the same declaration means two
    different things depending on which document it came from, and the two profiles
    need opposite treatment:

    * **officehtml** -- the HTML was serialized *by OfficeCLI*, which writes a
      unitless line height at a 4/3 projection of the native ratio (1.05x becomes
      1.4).  That projection must be undone before lowering.
    * **author** -- the HTML is Canonical Author HTML, where the unitless value is
      the ratio itself: the V0.4.1 projection emits the number it captured from the
      source deck.  Un-projecting it multiplies an author's "one and a half lines"
      by 0.75 and the rebuilt deck carries 1.125x.

    This function used to un-project unconditionally, so every Canonical Author
    document lost a quarter of its leading -- 22 objects on the three-deck corpus.
    The scale is documented in the Contract for the OfficeHTML boundary and is
    correct there; the defect was applying it outside that boundary.
    """
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized == "normal":
        return None
    if re.fullmatch(r"-?(?:\d+(?:\.\d*)?|\.\d+)", normalized):
        ratio = float(normalized)
        if undo_officecli_projection:
            ratio *= 0.75
        if abs(ratio - 1.0) <= 0.01:
            return None
        return str(ratio)
    if _CSS_LENGTH_RE.fullmatch(normalized):
        return normalized
    try:
        ratio = float(normalized)
    except ValueError:
        return None
    return str(ratio)


def _officehtml_rotation(styles: dict[str, str]) -> float:
    transform = styles.get("transform", "")
    match = re.search(r"rotate\(\s*(-?[\d.]+)deg\s*\)", transform)
    return float(match.group(1)) if match else 0.0


def _officehtml_text_fields(
    element: Any,
    styles: dict[str, str],
    fallback: dict[str, str],
    *,
    undo_officecli_projection: bool = False,
) -> dict[str, Any]:
    text_node = _officehtml_text_node(element)
    text_styles = _officehtml_style(text_node) if text_node is not None else {}
    paragraphs = element.xpath(
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' para ')]"
    )
    paragraph_styles = _officehtml_style(paragraphs[0]) if paragraphs else {}
    merged = dict(fallback)
    merged.update(styles)
    merged.update(paragraph_styles)
    merged.update(text_styles)
    padding_top, padding_right, padding_bottom, padding_left = _officehtml_padding(styles)
    shape_text = element.xpath(
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' shape-text ')]"
    )
    shape_tokens = _officehtml_class_tokens(shape_text[0]) if shape_text else set()
    valign = "center" if "valign-center" in shape_tokens else (
        "bottom" if "valign-bottom" in shape_tokens else "top"
    )
    paragraphs_data = _officehtml_paragraphs(
        element, fallback, undo_officecli_projection=undo_officecli_projection
    )
    return {
        "text": _officehtml_text(element),
        "color": merged.get("color"),
        "fontSize": _officehtml_length(merged.get("font-size")),
        "fontFamily": merged.get("font-family", ""),
        "fontWeight": merged.get("font-weight", "400"),
        "fontStyle": merged.get("font-style", "normal"),
        "textAlign": merged.get("text-align", "left"),
        "lineHeight": _officehtml_line_height(
            merged.get("line-height"),
            undo_officecli_projection=undo_officecli_projection,
        ),
        "direction": merged.get("direction", "ltr"),
        "alignItems": valign,
        "verticalAlign": merged.get("vertical-align", "top"),
        "writingMode": "horizontal-tb",
        "rotation": _officehtml_rotation(styles),
        "opacity": _officehtml_length(styles.get("opacity"), 1.0),
        "paddingLeft": padding_left,
        "paddingRight": padding_right,
        "paddingTop": padding_top,
        "paddingBottom": padding_bottom,
        "paragraphs": paragraphs_data,
    }


def _officehtml_base_element(
    element: Any,
    slide_styles: dict[str, str],
    *,
    tag: str,
    undo_officecli_projection: bool = False,
    text_element: Any | None = None,
) -> dict[str, Any]:
    styles = _officehtml_style(element)
    bounds = _officehtml_bounds(element)
    background, background_image = _officehtml_background(styles)
    border_color, border_width, border_style = _officehtml_border(styles)
    fallback = {
        "font-family": slide_styles.get("font-family", ""),
        "font-size": slide_styles.get("font-size", "18pt"),
        "color": slide_styles.get("color", "#000000"),
    }
    text_source = text_element if text_element is not None else element
    fields = _officehtml_text_fields(
        text_source,
        styles,
        fallback,
        undo_officecli_projection=undo_officecli_projection,
    )
    fields.update(
        {
            "tag": tag,
            "x": bounds[0],
            "y": bounds[1],
            "width": bounds[2],
            "height": bounds[3],
            "backgroundColor": background,
            "backgroundImage": background_image,
            "borderColor": border_color,
            "borderWidth": border_width,
            "borderStyle": border_style,
            "borderRadius": styles.get("border-radius", "0pt"),
            "borderLeftColor": None,
            "borderLeftWidth": 0.0,
            "borderLeftStyle": None,
        }
    )
    return fields


def _officehtml_shape(
    element: Any,
    slide_styles: dict[str, str],
    *,
    undo_officecli_projection: bool = False,
) -> dict[str, Any]:
    result = _officehtml_base_element(
        element,
        slide_styles,
        tag="shape",
        undo_officecli_projection=undo_officecli_projection,
    )
    result["dataPath"] = element.get("data-path")
    result["officeHtmlKind"] = "shape"
    if (
        result.get("text", "").strip() == ""
        and (result.get("backgroundColor") is not None or result.get("borderWidth", 0) > 0)
    ):
        # OfficeCLI uses a non-breaking space in filled/bordered shapes so the
        # viewer keeps a text body in its projection.  It is not authored
        # content and must not become black text on a colored native shape in
        # the OfficeHTML round trip.
        result["text"] = ""
        result["paragraphs"] = []
    return result


def _officehtml_picture(
    element: Any,
    slide_styles: dict[str, str],
    *,
    source_slide: int,
    undo_officecli_projection: bool = True,
) -> dict[str, Any]:
    result = _officehtml_base_element(
        element,
        slide_styles,
        tag="img",
        undo_officecli_projection=undo_officecli_projection,
    )
    images = element.xpath(".//img[@src]")
    source = _officehtml_picture_source(element)
    if source is None:
        raise _diagnostic(
            "undecodable_picture",
            f"OfficeHTML picture {element.get('data-path')!r} has no image source.",
            source_slide,
            str(element.get("data-path") or "picture"),
        )
    image = images[0] if images else None
    image_styles = _officehtml_style(image) if image is not None else {}
    result.update(
        {
            "dataPath": element.get("data-path"),
            "isImage": True,
            "isSvg": False,
            "src": source,
            "alt": image.get("alt") if image is not None else element.get("alt"),
            "objectFit": image_styles.get("object-fit", "fill"),
            "naturalWidth": 0,
            "naturalHeight": 0,
            "backgroundColor": None,
            "backgroundImage": None,
        }
    )
    return result


async def _rasterize_officehtml_svg_fallbacks(
    measurements: Sequence[dict[str, Any]],
) -> None:
    """Capture SVG picture projections as PNGs for OfficeCLI 1.0.151."""
    svg_elements = [
        element
        for slide in measurements
        for element in slide.get("elements", []) or []
        if str(element.get("src", "") or "").lower().startswith(
            "data:image/svg+xml"
        )
    ]
    if not svg_elements:
        return
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(viewport={"width": 2048, "height": 2048})
                for element in svg_elements:
                    try:
                        width = max(1.0, _number(element.get("width"), 1.0))
                        height = max(1.0, _number(element.get("height"), 1.0))
                        fit = str(element.get("objectFit", "fill") or "fill").lower()
                        if fit not in {"fill", "contain", "cover"}:
                            fit = "fill"
                        source = _html_escape(str(element["src"]), quote=True)
                        markup = (
                            '<!doctype html><html><body '
                            'style="margin:0;overflow:hidden;background:transparent">'
                            f'<img id="picture" src="{source}" '
                            f'style="display:block;width:{width:.4f}pt;'
                            f'height:{height:.4f}pt;object-fit:{fit};'
                            'object-position:center center"></body></html>'
                        )
                        await page.set_content(markup, wait_until="load")
                        await page.wait_for_function(
                            """() => {
                                const image = document.querySelector('#picture');
                                return image && image.complete && image.naturalWidth > 0;
                            }"""
                        )
                        png_bytes = await page.locator("#picture").screenshot(type="png")
                        encoded = base64.b64encode(png_bytes).decode("ascii")
                        element["rasterFallbackSrc"] = (
                            "data:image/png;base64," + encoded
                        )
                    except Exception:
                        # The compiler's final fallback gate reports the source
                        # context if any SVG still lacks a usable fallback.
                        continue
            finally:
                await browser.close()
    except Exception:
        # Keep the source intact; compile_officecli will emit the structured
        # picture_fallback_unavailable diagnostic below.
        return


def _officehtml_cell(
    element: Any,
    *,
    undo_officecli_projection: bool = True,
    row_index: int,
    column_index: int,
    x: float,
    y: float,
    width: float,
    height: float,
    slide_styles: dict[str, str],
    source_slide: int,
) -> dict[str, Any]:
    source = element.get("data-cell-path")
    if not source:
        raise _diagnostic(
            "missing_table_cell_path",
            f"OfficeHTML table cell at row {row_index}, column {column_index} has no data-cell-path.",
            source_slide,
            f"row[{row_index}]/cell[{column_index}]",
        )
    result = _officehtml_base_element(
        element,
        slide_styles,
        tag="td",
        undo_officecli_projection=undo_officecli_projection,
    )
    styles = _officehtml_style(element)
    result.update(
        {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "dataCellPath": source,
            "rowSpan": _number(element.get("rowspan"), 1),
            "colSpan": _number(element.get("colspan"), 1),
            "cellBorderTopColor": None,
            "cellBorderTopWidth": 0.0,
            "cellBorderTopStyle": None,
            "cellBorderRightColor": None,
            "cellBorderRightWidth": 0.0,
            "cellBorderRightStyle": None,
            "cellBorderBottomColor": None,
            "cellBorderBottomWidth": 0.0,
            "cellBorderBottomStyle": None,
            "cellBorderLeftColor": None,
            "cellBorderLeftWidth": 0.0,
            "cellBorderLeftStyle": None,
        }
    )
    for side in ("top", "right", "bottom", "left"):
        color, border_width, border_style = _officehtml_border(styles, side)
        result[f"cellBorder{side.capitalize()}Color"] = color
        result[f"cellBorder{side.capitalize()}Width"] = border_width
        result[f"cellBorder{side.capitalize()}Style"] = border_style
    return result


def _officehtml_table(
    element: Any,
    slide_styles: dict[str, str],
    *,
    source_slide: int,
    undo_officecli_projection: bool = True,
) -> dict[str, Any]:
    source = element.get("data-path")
    if not source:
        raise _diagnostic(
            "missing_table_path",
            "OfficeHTML table container has no data-path.",
            source_slide,
            "table",
        )
    table = element.xpath(".//table[1]")
    if not table:
        raise _diagnostic("invalid_table_matrix", "OfficeHTML table container has no table element.", source_slide, source)
    table_element = table[0]
    bounds = _officehtml_bounds(element)
    columns = [
        _officehtml_length(_officehtml_style(column).get("width"))
        for column in table_element.xpath("./colgroup/col")
    ]
    rows = table_element.xpath(".//tr")
    if not rows:
        raise _diagnostic("invalid_table_matrix", "OfficeHTML table has no rows.", source_slide, source)
    row_heights = [
        _officehtml_length(_officehtml_style(row).get("height"), bounds[3] / len(rows))
        for row in rows
    ]
    cell_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows, start=1):
        cells = row.xpath("./td|./th")
        cell_rows.append({"tag": "tr", "height": row_heights[row_index - 1], "children": cells})
    if not any(row["children"] for row in cell_rows):
        raise _diagnostic(
            "invalid_table_matrix",
            f"OfficeHTML table {source} has no cells.",
            source_slide,
            source,
        )
    topology_rows = [
        [
            {
                "rowspan": cell.get("rowspan"),
                "colspan": cell.get("colspan"),
                "source_object": str(
                    cell.get("data-cell-path")
                    or f"{source}/tr[{row_index}]/tc[{column_index}]"
                ),
                "text": "".join(cell.itertext()),
            }
            for column_index, cell in enumerate(row_data["children"], start=1)
        ]
        for row_index, row_data in enumerate(cell_rows, start=1)
    ]
    try:
        grid = build_logical_table_grid(topology_rows, source_object=source)
    except TableTopologyError as exc:
        raise _diagnostic(
            exc.code,
            exc.message,
            source_slide,
            exc.source_object or source,
        ) from exc
    column_count = grid.columns
    if not columns:
        columns = [bounds[2] / column_count for _ in range(column_count)]
    if len(columns) != column_count:
        raise _diagnostic(
            "invalid_table_matrix",
            f"OfficeHTML table {source} has {len(columns)} columns but rows contain {column_count} cells.",
            source_slide,
            source,
        )

    normalized_rows: list[dict[str, Any]] = []
    current_y = bounds[1]
    for row_index, row_data in enumerate(cell_rows, start=1):
        normalized_cells: list[dict[str, Any]] = []
        cells = row_data["children"]
        for source_column, cell in enumerate(cells):
            region = next(
                region
                for region in grid.regions
                if region.source_row == row_index - 1
                and region.source_column == source_column
            )
            logical_column = region.anchor_column - 1
            width = sum(columns[logical_column : logical_column + region.column_span])
            normalized_cells.append(
                _officehtml_cell(
                    cell,
                    undo_officecli_projection=undo_officecli_projection,
                    row_index=row_index,
                    column_index=region.anchor_column,
                    x=bounds[0] + sum(columns[:logical_column]),
                    y=current_y,
                    width=width,
                    height=row_data["height"],
                    slide_styles=slide_styles,
                    source_slide=source_slide,
                )
            )
        normalized_rows.append(
            {
                "tag": "tr",
                "height": row_data["height"],
                "children": normalized_cells,
            }
        )
        current_y += row_data["height"]

    result = _officehtml_base_element(
        element,
        slide_styles,
        tag="table",
        undo_officecli_projection=undo_officecli_projection,
    )
    result.update(
        {
            "dataPath": source,
            "tag": "table",
            "x": bounds[0],
            "y": bounds[1],
            "width": bounds[2],
            "height": bounds[3],
            "children": normalized_rows,
            "backgroundImage": None,
        }
    )
    return result


def _officehtml_owned_children(element: Any) -> Iterable[Any]:
    """Yield top-level slide-owned nodes, excluding chrome and pathless layers."""
    for child in element:
        if not isinstance(child.tag, str):
            continue
        if child.get("data-path"):
            yield child
            continue
        if child.tag.lower() in {"script", "style", "link", "meta"}:
            continue
        yield from _officehtml_owned_children(child)


def _parse_officehtml_measurements(input_html: str) -> list[dict[str, Any]]:
    """Parse OfficeCLI's fixed-coordinate object projection.

    ``data-path`` is retained as source identity and debugging metadata only;
    it is never used as a write-back address.  Only top-level nodes carrying
    that attribute enter the slide-owned measurement DTO.  This deliberately
    excludes the OfficeCLI viewer shell and pathless master/layout projections.
    """
    path = Path(input_html).expanduser()
    if not path.is_file():
        raise FileNotFoundError(input_html)
    try:
        root = _lxml_html.fromstring(
            path.read_bytes(),
            parser=_officehtml_parser(),
        )
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unable to parse OfficeHTML input {input_html!r}: {exc}") from exc

    slides = root.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]"
    )
    if not slides:
        raise ValueError("No slides found. Ensure the OfficeHTML contains .slide elements.")

    measurements: list[dict[str, Any]] = []
    # This parser serves the `officehtml` profile only, which is HTML
    # serialized by OfficeCLI.  Its unitless line height is a 4/3 projection of
    # the native ratio and must be un-projected.  The `author` profile takes a
    # different path and must NOT apply that scale: Canonical Author HTML states
    # the ratio itself.  Getting this wrong costs an author a quarter of the
    # leading they declared.
    undo_officecli_projection = True
    for slide_number, slide in enumerate(slides, start=1):
        slide_styles = _officehtml_style(slide)
        slide_width = _officehtml_length(slide_styles.get("width"), SLIDE_WIDTH_PT)
        slide_height = _officehtml_length(slide_styles.get("height"), SLIDE_HEIGHT_PT)
        background, background_image = _officehtml_background(slide_styles)
        elements: list[dict[str, Any]] = []
        for element in _officehtml_owned_children(slide):
            source = str(element.get("data-path") or "")
            path_lower = source.lower()
            classes = _officehtml_class_tokens(element)
            path_kind_match = _OFFICEHTML_PATH_KIND_RE.search(path_lower)
            path_kind = path_kind_match.group(1) if path_kind_match else None
            if path_kind == "table" or (
                path_kind is None and "table-container" in classes
            ):
                elements.append(
                    _officehtml_table(
                        element,
                        slide_styles,
                        source_slide=slide_number,
                        undo_officecli_projection=undo_officecli_projection,
                    )
                )
            elif path_kind == "picture" or (
                path_kind is None and "picture" in classes
            ):
                elements.append(
                    _officehtml_picture(
                        element,
                        slide_styles,
                        source_slide=slide_number,
                        undo_officecli_projection=undo_officecli_projection,
                    )
                )
            elif path_kind == "shape" or (
                path_kind is None and "shape" in classes
            ):
                elements.append(
                    _officehtml_shape(
                        element,
                        slide_styles,
                        undo_officecli_projection=undo_officecli_projection,
                    )
                )
            else:
                raise _diagnostic(
                    "unsupported_object_kind",
                    f"Unsupported OfficeHTML object on {source or 'a pathless node'}.",
                    slide_number,
                    source or None,
                )
        measurements.append(
            {
                "index": len(measurements),
                "width": slide_width,
                "height": slide_height,
                "backgroundColor": background,
                "backgroundImage": background_image,
                "elements": elements,
            }
        )
    return measurements


def _is_bold(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return value >= 600
    return str(value).lower() in {"bold", "bolder", "600", "700", "800", "900"}


def _pt(value_px: float, scale: float) -> float:
    return max(0.0, value_px * scale)


def _length(value: float) -> str:
    return f"{value:.4f}pt"


def _bounds(element: dict[str, Any], scale_x: float, scale_y: float) -> tuple[float, float, float, float]:
    return (
        _pt(_number(element.get("x")), scale_x),
        _pt(_number(element.get("y")), scale_y),
        _pt(_number(element.get("width")), scale_x),
        _pt(_number(element.get("height")), scale_y),
    )


def _border_radius(element: dict[str, Any]) -> float:
    value = str(element.get("borderRadius", "") or "")
    match = re.search(r"-?[\d.]+", value)
    return max(0.0, float(match.group(0))) if match else 0.0


# The preset geometries the Canonical Author shape surface carries as PowerPoint
# presets rather than inferring from CSS.  A block box is a rect and a
# border-radius is a roundRect; an ellipse and a right arrow cannot be inferred
# that way, so an emitted object declares the preset it must be rebuilt as and
# the declaration wins over the CSS inference.
DECLARED_SHAPE_GEOMETRIES = frozenset({"ellipse", "rightArrow"})


def _declared_shape_geometry(element: dict[str, Any]) -> str | None:
    value = str(element.get("shapeGeometry", "") or "").strip()
    return value if value in DECLARED_SHAPE_GEOMETRIES else None


def _shape_geometry(element: dict[str, Any]) -> str:
    declared = _declared_shape_geometry(element)
    if declared is not None:
        return declared
    return "roundRect" if _border_radius(element) > 0 else "rect"


def _line_spacing(
    element: dict[str, Any],
    *,
    legacy_css_pixel_projection: bool = False,
) -> str | None:
    font_size = _number(element.get("fontSize"))
    line_height = str(element.get("lineHeight", "") or "")
    if font_size <= 0:
        return None
    unitless = re.fullmatch(r"\s*((?:\d+(?:\.\d*)?|\.\d+))\s*", line_height)
    if unitless:
        ratio = float(unitless.group(1))
    else:
        match = re.fullmatch(
            r"\s*((?:\d+(?:\.\d*)?|\.\d+))px\s*", line_height, re.IGNORECASE
        )
        if not match:
            return None
        line_height_value = float(match.group(1))
        ratio = line_height_value / font_size
    if ratio <= 0:
        return None
    if abs(ratio - 1.0) < 0.01:
        return None
    return f"{ratio:.3f}x"


def _text_alignment(element: dict[str, Any]) -> str:
    """Native paragraph alignment, resolved by the declared Contract surface."""
    return _resolve_text_alignment(element)


def _vertical_alignment(element: dict[str, Any]) -> str:
    value = str(element.get("alignItems", "") or "").lower()
    if value in {"center", "middle"}:
        return "middle"
    if value in {"bottom", "flex-end", "end"}:
        return "bottom"
    return "top"


def _cell_vertical_alignment(element: dict[str, Any]) -> str:
    value = str(element.get("verticalAlign", "") or "").lower()
    if value in {"center", "middle"}:
        return "center"
    if value in {"bottom", "end"}:
        return "bottom"
    return "top"


def _margin(element: dict[str, Any], scale_x: float, scale_y: float) -> str | None:
    values = (
        _pt(_number(element.get("paddingLeft")), scale_x),
        _pt(_number(element.get("paddingTop")), scale_y),
        _pt(_number(element.get("paddingRight")), scale_x),
        _pt(_number(element.get("paddingBottom")), scale_y),
    )
    if not any(values):
        # OfficeCLI's native default insets are larger than the CSS default of
        # zero and can turn a measured one-line node into a wrapped line.
        return "0pt"
    if max(values) - min(values) < 0.001:
        return _length(values[0])
    return ",".join(_length(value) for value in values)


def _is_measured_single_line_text(element: dict[str, Any], text: str) -> bool:
    if not text or "\n" in text or "\v" in text:
        return False
    font_size = _number(element.get("fontSize"))
    element_height = _number(element.get("height"))
    return font_size > 0 and element_height <= font_size * 1.45


def _tight_single_line_font_scale(
    element: dict[str, Any],
    text: str,
) -> str | None:
    """Keep measured one-line labels on one line with OfficeCLI font metrics."""
    if not _is_measured_single_line_text(element, text):
        return None
    element_width = _number(element.get("width"))
    font_size = _number(element.get("fontSize"))
    if element_width <= 0:
        return None
    # A block whose measured width is close to the raw text width is vulnerable
    # to a substituted PowerPoint font wrapping one glyph.  Leave wider text
    # boxes and multi-line browser layout at their measured size.
    width_per_character_ratio = element_width / (font_size * max(1, len(text)))
    if width_per_character_ratio > 0.75:
        return None
    return "75" if _is_bold(element.get("fontWeight")) else "60"


def _text_props(
    element: dict[str, Any],
    bounds: tuple[float, float, float, float],
    scale_x: float,
    scale_y: float,
    backdrop: tuple[int, int, int],
) -> dict[str, str]:
    props: dict[str, str] = {
        "x": _length(bounds[0]),
        "y": _length(bounds[1]),
        "width": _length(bounds[2]),
        "height": _length(bounds[3]),
        "font": _resolve_pptx_font(str(element.get("fontFamily", "") or "")),
        "align": _text_alignment(element),
        "valign": _vertical_alignment(element),
    }
    font_size = _number(element.get("fontSize"))
    if font_size > 0:
        props["size"] = _length(_pt(font_size, scale_x))
    text_color = _parse_css_color(element.get("color"))
    if text_color:
        rgb, alpha = text_color
        opacity = max(0.0, min(1.0, _number(element.get("opacity"), 1.0)))
        if opacity < 0.999:
            # OfficeCLI's shape opacity is a fill-only property and rejects an
            # opacity value on a text-only object.  Preserve CSS element
            # opacity at the glyph level instead; DrawingML text colors carry
            # an alpha byte and OfficeCLI round-trips that value directly.
            props["color"] = _hex_with_alpha(rgb, alpha * opacity)
        else:
            props["color"] = _hex(rgb if alpha >= 0.999 else _blend(rgb, alpha, backdrop))
    if _is_bold(element.get("fontWeight")):
        props["bold"] = "true"
    if str(element.get("fontStyle", "")).lower() in {"italic", "oblique"}:
        props["italic"] = "true"
    direction = str(element.get("direction", "ltr") or "ltr").lower()
    if direction == "rtl":
        props["direction"] = "rtl"
    # A Native List Textbox carries the list's own indentation in its native
    # paragraph properties (marginLeft/indent), so its text body keeps no CSS
    # inset: a body inset would double-count the list padding.
    margin = "0pt" if element.get("list") else _margin(element, scale_x, scale_y)
    if margin is not None:
        props["margin"] = margin
    # The browser measurement is the visual source of truth.  A generic
    # shrink-to-fit heuristic changes the authored font size even when the
    # browser text already fits its measured box (S1 card copy is a concrete
    # example), so standalone Author text must keep its measured size.
    line_spacing = _line_spacing(element)
    if element.get("paragraphsFromChildren"):
        # A mixed authored paragraph flow cannot inherit one object-level
        # lineSpacing without flattening a paragraph that explicitly uses a
        # different leading. Leave the body default unset in that case; the
        # paragraph commands below carry each non-default authored ratio.
        paragraph_spacing = {
            _paragraph_line_spacing(paragraph, element)
            for paragraph in element.get("paragraphs", []) or []
        }
        if len(paragraph_spacing) > 1:
            line_spacing = None
    if line_spacing is not None:
        props["lineSpacing"] = line_spacing
    rotation = _number(element.get("rotation"))
    if abs(rotation) > 0.01:
        props["rotation"] = f"{rotation:.3f}"
    return props


def _shape_props(
    element: dict[str, Any],
    bounds: tuple[float, float, float, float],
    scale_x: float,
    scale_y: float,
    backdrop: tuple[int, int, int],
) -> dict[str, str]:
    props = _text_props(element, bounds, scale_x, scale_y, backdrop)
    props["geometry"] = _shape_geometry(element)

    fill = _parse_css_color(element.get("backgroundColor"))
    if fill:
        rgb, alpha = fill
        props["fill"] = _hex(rgb)
        combined_alpha = alpha * max(0.0, min(1.0, _number(element.get("opacity"), 1.0)))
        if combined_alpha < 0.999:
            props["opacity"] = f"{combined_alpha:.4f}"
    else:
        props["fill"] = "none"

    border = _parse_css_color(element.get("borderColor"))
    border_width = _number(element.get("borderWidth"))
    border_style = str(element.get("borderStyle", "solid") or "solid").lower()
    if border and border_width > 0 and border_style != "none":
        rgb, alpha = border
        line_width = _pt(border_width, scale_x)
        props["line"] = f"{_hex(rgb)}:{line_width:.4f}pt"
        if alpha < 0.999:
            props["lineOpacity"] = f"{alpha:.4f}"
    else:
        props["line"] = "none"

    radius = _border_radius(element)
    min_size = min(_number(element.get("width")), _number(element.get("height")))
    # An adjust handle is the rounded rectangle's corner radius; another preset
    # carries its own geometry and would reject or misread one, so it is only
    # written when the object really lowers to a roundRect.
    if radius > 0 and min_size > 0 and _shape_geometry(element) == "roundRect":
        adjustment = min(50000, round(radius / min_size * 100000))
        props["adj"] = f"adj:val {adjustment}"
    return props


def _diagnostic(
    code: str,
    message: str,
    source_slide: int,
    source_object: str,
) -> OfficeCLICompilationError:
    item = CompilationDiagnostic(
        "error", code, message, source_slide, source_object
    )
    return OfficeCLICompilationError(message, [item])


def _contract_failure(report: ContractReport) -> OfficeCLICompilationError:
    diagnostics: list[CompilationDiagnostic] = []
    for finding in report.diagnostics:
        match = re.search(r"slide\[(\d+)\]", finding.source_object or "", re.I)
        diagnostics.append(
            CompilationDiagnostic(
                "error",
                finding.code,
                f"OfficeCLI Contract {report.profile} blocked compilation: {finding.message}",
                int(match.group(1)) if match else None,
                finding.source_object,
                "contract",
            )
        )
    message = (
        f"OfficeCLI Contract {report.profile} rejected {report.input_path} "
        f"with {len(diagnostics)} blocking finding(s)."
    )
    return OfficeCLICompilationError(message, diagnostics)


def _decode_picture_source(
    element: dict[str, Any],
    source_slide: int,
    source_object: str,
) -> tuple[str, bytes]:
    source = element.get("src")
    if not isinstance(source, str) or not source.startswith("data:"):
        raise _diagnostic(
            "unsupported_picture_source",
            f"Unsupported picture source on source slide {source_slide}, {source_object}: only data-URI images are supported.",
            source_slide,
            source_object,
        )
    match = _DATA_URI_RE.fullmatch(source)
    if match is None:
        raise _diagnostic(
            "undecodable_picture",
            f"Undecodable picture on source slide {source_slide}, {source_object}: malformed data URI.",
            source_slide,
            source_object,
        )

    mime = match.group("mime").lower()
    if not mime.startswith("image/"):
        raise _diagnostic(
            "unsupported_picture_source",
            f"Unsupported picture source on source slide {source_slide}, {source_object}: {mime!r} is not an image MIME type.",
            source_slide,
            source_object,
        )
    payload = match.group("payload")
    try:
        if any(part.lower() == "base64" for part in match.group("meta").split(";") if part):
            data = base64.b64decode(payload.encode("ascii"), validate=True)
        else:
            data = unquote_to_bytes(payload)
    except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
        raise _diagnostic(
            "undecodable_picture",
            f"Undecodable picture on source slide {source_slide}, {source_object}: invalid {mime} data ({exc}).",
            source_slide,
            source_object,
        ) from exc
    if not data:
        raise _diagnostic(
            "undecodable_picture",
            f"Undecodable picture on source slide {source_slide}, {source_object}: the data URI is empty.",
            source_slide,
            source_object,
        )

    try:
        if mime == "image/svg+xml":
            root = ElementTree.fromstring(data)
            if root.tag.rsplit("}", 1)[-1].lower() != "svg":
                raise ValueError("root element is not <svg>")
        else:
            with Image.open(BytesIO(data)) as image:
                image.load()
    except Exception as exc:
        raise _diagnostic(
            "undecodable_picture",
            f"Undecodable picture on source slide {source_slide}, {source_object}: {exc}.",
            source_slide,
            source_object,
        ) from exc
    return mime, data


def _svg_boxed_source(
    data: bytes,
    box_width: float,
    box_height: float,
    natural_width: float,
    natural_height: float,
) -> str:
    """Wrap an image in an SVG box so CSS ``object-fit: contain`` is native."""
    scale = min(box_width / natural_width, box_height / natural_height)
    draw_width = natural_width * scale
    draw_height = natural_height * scale
    offset_x = (box_width - draw_width) / 2
    offset_y = (box_height - draw_height) / 2
    inner = "data:image/svg+xml;base64," + base64.b64encode(data).decode("ascii")
    values = (box_width, box_height, offset_x, offset_y, draw_width, draw_height)
    formatted = [f"{value:.6f}" for value in values]
    box_w, box_h, x, y, width, height = formatted
    source = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{box_w}" height="{box_h}" viewBox="0 0 {box_w} {box_h}">'
        f'<image x="{x}" y="{y}" width="{width}" height="{height}" '
        f'preserveAspectRatio="none" href="{_html_escape(inner, quote=True)}" '
        f'xlink:href="{_html_escape(inner, quote=True)}"/></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(source.encode()).decode("ascii")


def _raster_boxed_source(
    data: bytes,
    box_width: float,
    box_height: float,
) -> str:
    """Pad a raster image to a box while preserving its native aspect ratio."""
    canvas_size = (max(1, round(box_width)), max(1, round(box_height)))
    with Image.open(BytesIO(data)) as source_image:
        image = source_image.convert("RGBA")
    image.thumbnail(canvas_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    offset = (
        (canvas.width - image.width) // 2,
        (canvas.height - image.height) // 2,
    )
    canvas.alpha_composite(image, dest=offset)
    output = BytesIO()
    canvas.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _intrinsic_dimensions(mime: str, data: bytes) -> tuple[float, float]:
    if mime == "image/svg+xml":
        root = ElementTree.fromstring(data)
        view_box = root.attrib.get("viewBox", "").replace(",", " ").split()
        if len(view_box) == 4:
            try:
                width, height = float(view_box[2]), float(view_box[3])
                if width > 0 and height > 0:
                    return width, height
            except ValueError:
                pass
        return (
            _number(root.attrib.get("width")),
            _number(root.attrib.get("height")),
        )
    with Image.open(BytesIO(data)) as image:
        return float(image.width), float(image.height)


def _picture_props(
    element: dict[str, Any],
    bounds: tuple[float, float, float, float],
    source_slide: int,
    source_object: str,
) -> tuple[dict[str, str], dict[str, str] | None]:
    mime, data = _decode_picture_source(element, source_slide, source_object)
    fit = str(element.get("objectFit", "fill") or "fill").lower()
    if fit not in {"fill", "contain", "cover"}:
        raise _diagnostic(
            "unsupported_picture_fit",
            f"Unsupported object-fit on source slide {source_slide}, {source_object}: {fit!r}.",
            source_slide,
            source_object,
        )

    source = str(element["src"])
    natural_width = _number(element.get("naturalWidth"))
    natural_height = _number(element.get("naturalHeight"))
    box_width = _number(element.get("width"))
    box_height = _number(element.get("height"))
    if natural_width <= 0 or natural_height <= 0:
        natural_width, natural_height = _intrinsic_dimensions(mime, data)
    if fit in {"contain", "cover"} and any(
        value <= 0 for value in (natural_width, natural_height, box_width, box_height)
    ):
        raise _diagnostic(
            "unsupported_picture_fit",
            f"Cannot preserve object-fit on source slide {source_slide}, {source_object}: intrinsic image and picture dimensions are required.",
            source_slide,
            source_object,
        )
    if fit == "contain" and all(
        value > 0 for value in (natural_width, natural_height, box_width, box_height)
    ):
        box_aspect = box_width / box_height
        image_aspect = natural_width / natural_height
        if abs(box_aspect - image_aspect) >= 1e-3:
            if mime == "image/svg+xml":
                source = _svg_boxed_source(
                    data, box_width, box_height, natural_width, natural_height
                )
            else:
                source = _raster_boxed_source(data, box_width, box_height)

    props: dict[str, str] = {
        "x": _length(bounds[0]),
        "y": _length(bounds[1]),
        "width": _length(bounds[2]),
        "height": _length(bounds[3]),
        "src": source,
    }
    if fit == "cover" and all(
        value > 0 for value in (natural_width, natural_height, box_width, box_height)
    ):
        box_aspect = box_width / box_height
        image_aspect = natural_width / natural_height
        if abs(box_aspect - image_aspect) >= 1e-3:
            if image_aspect > box_aspect:
                crop = (1 - box_aspect / image_aspect) / 2
                props["cropLeft"] = f"{crop:.8f}"
                props["cropRight"] = f"{crop:.8f}"
            else:
                crop = (1 - image_aspect / box_aspect) / 2
                props["cropTop"] = f"{crop:.8f}"
                props["cropBottom"] = f"{crop:.8f}"

    opacity = _number(element.get("opacity"), 1.0)
    if opacity < 0.999:
        props["opacity"] = f"{max(0.0, min(1.0, opacity)):.4f}"
    rotation = _number(element.get("rotation"))
    if abs(rotation) > 0.01:
        props["rotation"] = f"{rotation:.3f}"
    alt = str(element.get("alt", "") or "")
    if alt:
        props["alt"] = alt

    fallback_source = element.get("rasterFallbackSrc")
    if not isinstance(fallback_source, str) or not fallback_source:
        return props, None
    fallback_props = dict(props)
    fallback_props["src"] = fallback_source
    for key in ("cropLeft", "cropRight", "cropTop", "cropBottom"):
        fallback_props.pop(key, None)
    return props, fallback_props


def _table_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def visit(element: dict[str, Any]) -> None:
        tag = str(element.get("tag", "") or "").lower()
        if tag == "tr":
            rows.append(element)
            return
        if tag not in {"table", "thead", "tbody", "tfoot"}:
            return
        for child in element.get("children", []) or []:
            visit(child)

    visit(table)
    return rows


def _table_cell_border(
    element: dict[str, Any],
    side: str,
    scale_x: float,
    backdrop: tuple[int, int, int],
    source_slide: int,
    source_object: str,
) -> str | None:
    suffix = side.capitalize()
    width = _number(element.get(f"cellBorder{suffix}Width"))
    style = str(element.get(f"cellBorder{suffix}Style", "") or "").lower()
    if width <= 0 or style in {"", "none", "hidden"}:
        return None
    dash = {"solid": "solid", "dotted": "dot", "dashed": "dash"}.get(style)
    if dash is None:
        raise _diagnostic(
            "unsupported_table_border",
            f"Unsupported table border on source slide {source_slide}, {source_object}: {style!r} is not supported.",
            source_slide,
            source_object,
        )
    color = _parse_css_color(element.get(f"cellBorder{suffix}Color"))
    if color is None:
        return None
    rgb, alpha = color
    if alpha < 0.999:
        rgb = _blend(rgb, alpha, backdrop)
    return f"{_pt(width, scale_x):.4f}pt {dash} {_hex(rgb)}"


def _table_cell_paragraph_props(
    paragraphs: Sequence[dict[str, Any]],
    source_slide: int,
    source_object: str,
) -> dict[str, str]:
    """Project uniform paragraph properties onto OfficeCLI's cell surface.

    OfficeCLI 1.0.151 exposes paragraph alignment, spacing, and direction for
    a table cell through the cell path; setting those properties fans them out
    to every paragraph in that cell.  Preserve the paragraph-level source
    values when they are uniform and reject a heterogeneous cell explicitly so
    the compiler cannot silently flatten a real paragraph-format difference.
    """
    if not paragraphs:
        return {}
    projected = [_paragraph_props(paragraph) for paragraph in paragraphs]
    first = projected[0]
    if any(props != first for props in projected[1:]):
        raise _diagnostic(
            "unsupported_table_paragraph_format",
            f"Table cell paragraph properties differ on source slide {source_slide}, {source_object}; OfficeCLI Contract v1 exposes these properties at cell scope.",
            source_slide,
            source_object,
        )
    return first


def _table_cell_props(
    element: dict[str, Any],
    scale_x: float,
    scale_y: float,
    backdrop: tuple[int, int, int],
    source_slide: int,
    source_object: str,
    paragraphs: Sequence[dict[str, Any]] = (),
) -> dict[str, str]:
    # The lowered paragraph tuple is the single structural authority.  In
    # particular, an authored ``<br>`` is ``\v`` inside one paragraph; reading
    # the raw measurement text here would turn it back into ``\n`` and make the
    # table cell disagree with the run ranges and readback model.
    props: dict[str, str] = {
        "text": _paragraphs_text(paragraphs) if paragraphs else _text_of(element)
    }
    fill = _parse_css_color(element.get("backgroundColor"))
    cell_backdrop = backdrop
    if fill is None:
        props["fill"] = "none"
    else:
        rgb, alpha = fill
        effective_alpha = alpha * max(
            0.0, min(1.0, _number(element.get("opacity"), 1.0))
        )
        props["fill"] = _hex(rgb)
        if effective_alpha < 0.999:
            props["opacity"] = f"{effective_alpha:.4f}"
        cell_backdrop = _blend(rgb, effective_alpha, backdrop)

    font_family = str(element.get("fontFamily", "") or "")
    if font_family:
        props["font"] = _resolve_pptx_font(font_family)
    font_size = _number(element.get("fontSize"))
    if font_size > 0:
        props["size"] = _length(_pt(font_size, scale_x))
    text_color = _parse_css_color(element.get("color"))
    if text_color:
        rgb, alpha = text_color
        props["color"] = _hex(rgb if alpha >= 0.999 else _blend(rgb, alpha, cell_backdrop))
    if _is_bold(element.get("fontWeight")):
        props["bold"] = "true"
    if str(element.get("fontStyle", "")).lower() in {"italic", "oblique"}:
        props["italic"] = "true"
    props["align"] = _text_alignment(element)
    props["valign"] = _cell_vertical_alignment(element)
    props["padding.left"] = _length(_pt(_number(element.get("paddingLeft")), scale_x))
    props["padding.right"] = _length(_pt(_number(element.get("paddingRight")), scale_x))
    props["padding.top"] = _length(_pt(_number(element.get("paddingTop")), scale_y))
    props["padding.bottom"] = _length(_pt(_number(element.get("paddingBottom")), scale_y))
    direction = str(element.get("direction", "ltr") or "ltr").lower()
    if direction == "rtl":
        props["direction"] = "rtl"
    line_spacing = _line_spacing(element)
    if line_spacing is not None:
        props["linespacing"] = line_spacing

    paragraph_props = _table_cell_paragraph_props(
        paragraphs, source_slide, source_object
    )
    if paragraph_props:
        props["align"] = paragraph_props.get("align", props["align"])
        if paragraph_props.get("lineSpacing"):
            props["linespacing"] = paragraph_props["lineSpacing"]
        if paragraph_props.get("spaceBefore"):
            props["spacebefore"] = paragraph_props["spaceBefore"]
        if paragraph_props.get("spaceAfter"):
            props["spaceafter"] = paragraph_props["spaceAfter"]
        if paragraph_props.get("direction"):
            props["direction"] = paragraph_props["direction"]

    for side in ("top", "right", "bottom", "left"):
        descriptor = _table_cell_border(
            element, side, scale_x, cell_backdrop, source_slide, source_object
        )
        if descriptor is not None:
            props[f"border.{side}"] = descriptor
    return props


def _lower_table(
    element: dict[str, Any],
    source_slide: int,
    source_object: str,
    name: str,
    scale_x: float,
    scale_y: float,
    backdrop: tuple[int, int, int],
) -> _ObjectIR:
    bounds = _bounds(element, scale_x, scale_y)
    if bounds[2] <= 0 or bounds[3] <= 0:
        raise _diagnostic(
            "invalid_table_geometry",
            f"Invalid table geometry on source slide {source_slide}, {source_object}: width and height must be positive.",
            source_slide,
            source_object,
        )
    if element.get("backgroundImage"):
        raise _diagnostic(
            "unsupported_table_effect",
            f"Unsupported table fill on source slide {source_slide}, {source_object}: image or gradient fills are not supported.",
            source_slide,
            source_object,
        )

    rows = _table_rows(element)
    if not rows:
        raise _diagnostic(
            "invalid_table_matrix",
            f"Invalid table on source slide {source_slide}, {source_object}: the table has no rows.",
            source_slide,
            source_object,
        )
    row_cells = [
        [
            child
            for child in row.get("children", []) or []
            if str(child.get("tag", "") or "").lower() in {"td", "th"}
        ]
        for row in rows
    ]
    if not row_cells or not row_cells[0]:
        raise _diagnostic(
            "invalid_table_matrix",
            f"Invalid table on source slide {source_slide}, {source_object}: the table has no cells.",
            source_slide,
            source_object,
        )

    topology_rows: list[list[dict[str, Any]]] = []
    for row_index, cells in enumerate(row_cells, start=1):
        topology_row: list[dict[str, Any]] = []
        for column_index, cell in enumerate(cells, start=1):
            cell_source = str(
                cell.get("dataCellPath")
                or f"{source_object}/tr[{row_index}]/tc[{column_index}]"
            )
            if cell.get("backgroundImage"):
                raise _diagnostic(
                    "unsupported_table_effect",
                    f"Unsupported cell fill on source slide {source_slide}, {cell_source}: image or gradient fills are not supported.",
                    source_slide,
                    cell_source,
                )
            topology_row.append(
                {
                    "rowspan": _measured_table_span(cell.get("rowSpan")),
                    "colspan": _measured_table_span(cell.get("colSpan")),
                    "source_object": cell_source,
                    "text": _text_of(cell),
                }
            )
        topology_rows.append(topology_row)
    try:
        grid = build_logical_table_grid(
            topology_rows,
            source_object=source_object,
        )
    except TableTopologyError as exc:
        raise _diagnostic(
            exc.code,
            f"Invalid merged table on source slide {source_slide}, {exc.source_object or source_object}: {exc.message}",
            source_slide,
            exc.source_object or source_object,
        ) from exc

    row_heights = tuple(_pt(_number(row.get("height")), scale_y) for row in rows)
    logical_height = sum(row_heights)
    logical_widths_px: list[float | None] = [None] * grid.columns
    for region in grid.regions:
        cell = row_cells[region.source_row][region.source_column]
        if region.column_span == 1:
            measured_width = _number(cell.get("width"))
            if measured_width > 0 and logical_widths_px[region.anchor_column - 1] is None:
                logical_widths_px[region.anchor_column - 1] = measured_width
    remaining_columns = [
        index for index, width in enumerate(logical_widths_px) if width is None
    ]
    if remaining_columns:
        known_width = sum(width or 0.0 for width in logical_widths_px)
        fallback_width = max(
            0.0,
            (_number(bounds[2]) / scale_x - known_width)
            / len(remaining_columns),
        )
        for index in remaining_columns:
            logical_widths_px[index] = fallback_width
    column_widths = tuple(
        _pt(float(width or 0.0), scale_x) for width in logical_widths_px
    )
    if any(height <= 0 for height in row_heights) or any(
        width <= 0 for width in column_widths
    ):
        raise _diagnostic(
            "invalid_table_geometry",
            f"Invalid table geometry on source slide {source_slide}, {source_object}: row heights and column widths must be positive.",
            source_slide,
            source_object,
        )

    table_props: dict[str, str] = {
        "name": name,
        "x": _length(bounds[0]),
        "y": _length(bounds[1]),
        "width": _length(bounds[2]),
        "height": _length(logical_height),
        "rows": str(grid.rows),
        "cols": str(grid.columns),
        "colWidths": ",".join(_length(width) for width in column_widths),
        "style": "none",
        "firstRow": "false",
        "lastRow": "false",
        "firstCol": "false",
        "lastCol": "false",
        "bandedRows": "false",
        "bandedCols": "false",
    }
    table_cells: list[_TableCellIR] = []
    for row_index in range(grid.rows):
        for column_index in range(grid.columns):
            region = grid.regions[grid.occupancy[row_index][column_index]]
            anchor = (
                row_index + 1 == region.anchor_row
                and column_index + 1 == region.anchor_column
            )
            cell_source = str(
                row_cells[region.source_row][region.source_column].get("dataCellPath")
                or f"{source_object}/tr[{region.source_row + 1}]/tc[{region.source_column + 1}]"
            )
            cell_name = f"{name}-cell-r{row_index + 1:03d}-c{column_index + 1:03d}"
            cell_x = bounds[0] + sum(column_widths[:column_index])
            cell_y = bounds[1] + sum(row_heights[:row_index])
            cell_width = column_widths[column_index]
            cell_height = row_heights[row_index]
            cell_paragraphs: tuple[dict[str, Any], ...] = ()
            if anchor:
                cell = row_cells[region.source_row][region.source_column]
                cell_paragraphs = _text_paragraphs(
                    cell,
                    scale_x,
                    scale_y,
                    backdrop,
                    preserve_table_projection=True,
                )
                cell_width = sum(
                    column_widths[
                        region.anchor_column - 1 : region.anchor_column - 1 + region.column_span
                    ]
                )
                cell_height = sum(
                    row_heights[
                        region.anchor_row - 1 : region.anchor_row - 1 + region.row_span
                    ]
                )
                cell_props = _table_cell_props(
                    cell,
                    scale_x,
                    scale_y,
                    backdrop,
                    source_slide,
                    cell_source,
                    cell_paragraphs,
                )
                if region.column_span > 1:
                    cell_props["colspan"] = str(region.column_span)
                if region.row_span > 1:
                    cell_props["rowspan"] = str(region.row_span)
            else:
                # Covered physical cells are intentionally blank and carry no
                # border/fill/text properties.  The anchor is the sole owner of
                # content, formatting, and the four canonical outer borders.
                cell_props = {"text": ""}
            table_cells.append(
                _TableCellIR(
                    cell_name,
                    source_slide,
                    cell_source,
                    (cell_x, cell_y, cell_width, cell_height),
                    _paragraphs_text(cell_paragraphs),
                    cell_props,
                    cell_paragraphs,
                    row_index + 1,
                    column_index + 1,
                    region.row_span if anchor else 1,
                    region.column_span if anchor else 1,
                    anchor,
                )
            )
    return _ObjectIR(
        kind="table",
        name=name,
        source_slide=source_slide,
        source_object=source_object,
        bounds=(bounds[0], bounds[1], bounds[2], logical_height),
        props=table_props,
        metadata={"normalized_merge_topology": grid.normalized_topology},
        table_cells=tuple(table_cells),
        row_heights=row_heights,
        column_widths=column_widths,
    )


def _lower_slide(
    source_index: int,
    slide_data: dict[str, Any],
    *,
    profile: str = "author",
) -> _SlideIR:
    width = _number(slide_data.get("width"))
    height = _number(slide_data.get("height"))
    source_slide = source_index + 1
    if width <= 0 or height <= 0:
        raise OfficeCLICompilationError(
            f"Source slide {source_slide} has no measurable rectangle.",
            [CompilationDiagnostic("error", "invalid_slide_geometry", "The measured slide width and height must be positive.", source_slide)],
        )
    scale_x = SLIDE_WIDTH_PT / width
    scale_y = SLIDE_HEIGHT_PT / height
    background = _parse_css_color(slide_data.get("backgroundColor"))
    if background is None:
        background_value = "none"
        backdrop = (255, 255, 255)
    else:
        rgb, alpha = background
        background_value = _hex(rgb) if alpha >= 0.999 else _hex(_blend(rgb, alpha, (255, 255, 255)))
        backdrop = rgb if alpha >= 0.999 else _blend(rgb, alpha, (255, 255, 255))
    if slide_data.get("backgroundImage"):
        raise _diagnostic(
            "unsupported_background",
            f"Unsupported visible background on source slide {source_slide}: background images are not part of the shape/text slice.",
            source_slide,
            f"slide[{source_slide}]",
        )

    result = _SlideIR(source_index, f"slide-{source_slide:03d}", background_value, [])

    def add_object(
        element: dict[str, Any],
        source_object: str,
        kind: str,
        text: str,
        props: dict[str, str],
        bounds: tuple[float, float, float, float],
        fallback_props: dict[str, str] | None = None,
        paragraphs: tuple[dict[str, Any], ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> None:
        name = f"slide-{source_slide:03d}-{kind}-{len(result.objects) + 1:03d}"
        if kind in {"shape", "textbox"} and not text and not paragraphs:
            # OfficeCLI creates one empty paragraph for every native text body,
            # including a text-bearing shape whose visible content is empty.
            # Keep that implementation detail in the source manifest so the
            # strict A -> OfficeCLI readback check does not confuse a native
            # default body with loss of an authored hard-break paragraph.
            paragraphs = (
                {
                    "text": "",
                    "align": _text_alignment(element),
                    "line_spacing": _line_spacing(element),
                    "space_before_pt": 0.0,
                    "space_after_pt": 0.0,
                    "direction": str(element.get("direction", "ltr") or "ltr"),
                    "runs": [],
                },
            )
        object_props = dict(props)
        object_props["name"] = name
        if fallback_props is not None:
            fallback_props = dict(fallback_props)
            fallback_props["name"] = name
        if text:
            object_props["text"] = text
            # Chromium measured these nodes as one visual line.  OfficeCLI and
            # the browser can use slightly different font metrics, so ask the
            # native text body to shrink instead of introducing a new wrap.
            if _is_measured_single_line_text(element, text):
                # OfficeCLI's normalized readback token for shrink-to-fit is
                # ``normal`` (its help documents ``shrink`` as an input alias).
                object_props.setdefault("autoFit", "normal")
        result.objects.append(
            _ObjectIR(
                kind,
                name,
                source_slide,
                source_object,
                bounds,
                object_props,
                text,
                fallback_props,
                paragraphs,
                metadata,
            )
        )

    def walk(
        element: dict[str, Any],
        source_object: str,
        inherited_backdrop: tuple[int, int, int],
    ) -> None:
        tag = str(element.get("tag", "element") or "element").lower()
        is_list = bool(element.get("list"))
        if is_list:
            # One supported top-level list is one Native List Textbox: its
            # direct items are the paragraphs of that one object, so no item is
            # ever emitted as its own textbox, picture, or marker-simulating
            # shape.  The item ``li`` children are folded in below and are never
            # walked as objects of their own.
            paragraphs = _list_paragraphs(
                element,
                scale_x,
                scale_y,
                inherited_backdrop,
                source_slide,
                source_object,
            )
        else:
            # One paragraph structure per element: the object text and every
            # OfficeCLI range offset below are computed from this same
            # structure, so a range can never address the wrong characters.
            paragraphs = _text_paragraphs(
                element,
                scale_x,
                scale_y,
                inherited_backdrop,
            )
        text = _paragraphs_text(paragraphs)
        if element.get("isImage") or element.get("isSvg") or tag in {"img", "svg"}:
            picture_bounds = _bounds(element, scale_x, scale_y)
            picture_props, fallback_props = _picture_props(
                element,
                picture_bounds,
                source_slide,
                source_object,
            )
            mime, picture_data = _decode_picture_source(
                element, source_slide, source_object
            )
            intrinsic_width, intrinsic_height = _intrinsic_dimensions(
                mime, picture_data
            )
            fallback_intrinsic_size: list[float] | None = None
            if fallback_props is not None:
                fallback_element = dict(element)
                fallback_element["src"] = fallback_props["src"]
                fallback_mime, fallback_data = _decode_picture_source(
                    fallback_element, source_slide, source_object
                )
                fallback_width, fallback_height = _intrinsic_dimensions(
                    fallback_mime, fallback_data
                )
                fallback_intrinsic_size = [fallback_width, fallback_height]
            picture_metadata: dict[str, Any] = {
                "mime": mime,
                "source_fingerprint": hashlib.sha256(picture_data).hexdigest(),
                "content_fingerprint": hashlib.sha256(picture_data).hexdigest(),
                "intrinsic_size": [intrinsic_width, intrinsic_height],
                "object_fit": str(element.get("objectFit", "fill") or "fill").lower(),
                "bounds_pt": list(picture_bounds),
                "fitting": {
                    key: value
                    for key, value in picture_props.items()
                    if key.startswith("crop")
                },
            }
            if fallback_intrinsic_size is not None:
                picture_metadata["fallback_intrinsic_size"] = fallback_intrinsic_size
            add_object(
                element,
                source_object,
                "picture",
                "",
                picture_props,
                picture_bounds,
                fallback_props,
                metadata={"picture": picture_metadata},
            )
            return
        if tag == "table":
            table_name = f"slide-{source_slide:03d}-table-{len(result.objects) + 1:03d}"
            result.objects.append(
                _lower_table(
                    element,
                    source_slide,
                    source_object,
                    table_name,
                    scale_x,
                    scale_y,
                    inherited_backdrop,
                )
            )
            return
        if element.get("backgroundImage"):
            raise _diagnostic(
                "unsupported_effect",
                f"Unsupported visible object on source slide {source_slide}, {source_object}: gradient or image fills are not part of the shape/text slice.",
                source_slide,
                source_object,
            )
        writing_mode = str(element.get("writingMode", "horizontal-tb") or "horizontal-tb")
        if writing_mode not in {"horizontal-tb", "horizontal-bt"}:
            raise _diagnostic(
                "unsupported_text_direction",
                f"Unsupported visible object on source slide {source_slide}, {source_object}: vertical text is deferred.",
                source_slide,
                source_object,
            )

        scale_x_local = scale_x
        scale_y_local = scale_y
        bounds = _bounds(element, scale_x_local, scale_y_local)
        fill = _parse_css_color(element.get("backgroundColor"))
        border = _parse_css_color(element.get("borderColor"))
        border_value = str(element.get("borderColor", "") or "")
        border_width = _number(element.get("borderWidth"))
        border_style = str(element.get("borderStyle", "solid") or "solid").lower()
        if border_width > 0 and border_style not in {"solid", "none"}:
            raise _diagnostic(
                "unsupported_outline",
                f"Unsupported visible object on source slide {source_slide}, {source_object}: only solid uniform outlines are supported.",
                source_slide,
                source_object,
            )
        if border_width > 0 and border is None and border_value not in {"", "transparent"}:
            raise _diagnostic(
                "unsupported_outline",
                f"Unsupported visible object on source slide {source_slide}, {source_object}: only uniform outlines are supported.",
                source_slide,
                source_object,
            )
        left_border = _parse_css_color(element.get("borderLeftColor"))
        has_left = (
            _number(element.get("borderLeftWidth")) > 0
            and str(element.get("borderLeftStyle", "") or "").lower() not in {"", "none"}
            and left_border is not None
        )
        has_shape = fill is not None or (border is not None and border_width > 0)
        if _declared_shape_geometry(element) is not None:
            # An object that names its own preset geometry is an explicit
            # PowerPoint shape even when its fill and outline are both absent,
            # exactly as an OfficeHTML slide-owned shape is: dropping it would
            # silently lose a source object from the rebuilt deck.
            has_shape = True
        if profile == "officehtml" and not text and not has_shape:
            # A slide-owned OfficeHTML shape is an explicit PowerPoint object
            # even when its fill is transparent and its text body is empty.
            # Pathless master/layout projections never reach this function.
            has_shape = bool(element.get("dataPath"))

        child_backdrop = inherited_backdrop
        if fill is not None:
            fill_rgb, fill_alpha = fill
            effective_alpha = fill_alpha * max(0.0, min(1.0, _number(element.get("opacity"), 1.0)))
            child_backdrop = _blend(fill_rgb, effective_alpha, inherited_backdrop)

        if has_shape:
            props = _shape_props(element, bounds, scale_x_local, scale_y_local, inherited_backdrop)
            add_object(
                element,
                source_object,
                "shape",
                text,
                props,
                bounds,
                paragraphs=paragraphs,
            )
        elif text or paragraphs:
            props = _text_props(element, bounds, scale_x_local, scale_y_local, inherited_backdrop)
            add_object(
                element,
                source_object,
                "textbox",
                text,
                props,
                bounds,
                paragraphs=paragraphs,
            )

        if has_left:
            assert left_border is not None
            left_width = _pt(_number(element.get("borderLeftWidth")), scale_x_local)
            left_props = {
                "x": _length(bounds[0]),
                "y": _length(bounds[1]),
                "width": _length(left_width),
                "height": _length(bounds[3]),
                "geometry": "rect",
                "fill": _hex(left_border[0]),
                "line": "none",
            }
            add_object(
                element,
                source_object,
                "shape",
                "",
                left_props,
                (bounds[0], bounds[1], left_width, bounds[3]),
            )

        # A list's own items are the paragraphs of the one list object, so they
        # are never walked as separate objects.
        child_elements = [] if is_list else (element.get("children", []) or [])
        for position, child in enumerate(child_elements, start=1):
            child_tag = str(child.get("tag", "element") or "element").lower()
            if element.get("paragraphsFromChildren") and child_tag == "p":
                # Direct authored <p> children were folded into the parent's
                # one native textbox above, including zero-height empties that
                # cannot survive as standalone measured objects.
                continue
            if element.get("inlineRuns") and child_tag in _INLINE_TAGS:
                continue
            child_path = _source_path(source_slide, source_object, child_tag, position)
            walk(child, child_path, child_backdrop)

    for position, element in enumerate(slide_data.get("elements", []) or [], start=1):
        tag = str(element.get("tag", "element") or "element").lower()
        source_object = (
            str(element.get("dataPath"))
            if profile == "officehtml" and element.get("dataPath")
            else _source_path(source_slide, "", tag, position)
        )
        walk(element, source_object, backdrop)
    return result


def _select_measurements(
    measurements: Sequence[dict[str, Any]],
    slide_indices: Sequence[int] | None,
) -> list[tuple[int, dict[str, Any]]]:
    if slide_indices is None:
        return list(enumerate(measurements))
    selected: list[tuple[int, dict[str, Any]]] = []
    seen: set[int] = set()
    for index in slide_indices:
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError("slide_indices must contain zero-based integer indexes")
        if index < 0 or index >= len(measurements):
            raise IndexError(f"Source slide index {index} is outside the measured deck")
        if index in seen:
            raise ValueError(f"Source slide index {index} was selected more than once")
        seen.add(index)
        selected.append((index, measurements[index]))
    if not selected:
        raise ValueError("slide_indices must select at least one source slide")
    return selected


def _batch_for_slides(
    slides: Sequence[_SlideIR],
    raster_fallbacks: set[str] | frozenset[str] = frozenset(),
) -> tuple[list[dict[str, Any]], list[_ObjectIR | None]]:
    commands: list[dict[str, Any]] = [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}}
    ]
    sources: list[_ObjectIR | None] = [None]
    for output_index, slide in enumerate(slides, start=1):
        commands.append(
            {
                "command": "add",
                "parent": "/",
                "type": "slide",
                "props": {"background": slide.background, "name": slide.name},
            }
        )
        sources.append(None)
        for obj in slide.objects:
            props = (
                obj.fallback_props
                if obj.name in raster_fallbacks and obj.fallback_props is not None
                else obj.props
            )
            commands.append(
                {
                    "command": "add",
                    "parent": f"/slide[{output_index}]",
                    "type": obj.kind,
                    "props": props,
                }
            )
            sources.append(obj)
            if obj.kind != "table":
                if obj.paragraphs:
                    object_path = f"/slide[{output_index}]/shape[@name={obj.name}]"
                    offset = 0
                    for paragraph_index, paragraph in enumerate(obj.paragraphs, start=1):
                        paragraph_props = _paragraph_props(paragraph)
                        if paragraph_props:
                            commands.append(
                                {
                                    "command": "set",
                                    "path": f"{object_path}/p[{paragraph_index}]",
                                    "props": paragraph_props,
                                }
                            )
                            sources.append(obj)
                        for run in paragraph.get("runs", []):
                            text = str(run.get("text", ""))
                            if not text:
                                continue
                            range_length = _officecli_range_length(text)
                            if not range_length:
                                continue
                            run_props = _run_props(run)
                            if run_props:
                                commands.append(
                                    {
                                        "command": "set",
                                        "path": object_path,
                                        "props": {
                                            "range": f"{offset}:{offset + range_length}",
                                            **run_props,
                                        },
                                    }
                                )
                                sources.append(obj)
                            offset += range_length
                continue
            table_path = f"/slide[{output_index}]/table[@name={obj.name}]"
            cell_index = 0
            for row_index, row_height in enumerate(obj.row_heights, start=1):
                commands.append(
                    {
                        "command": "set",
                        "path": f"{table_path}/tr[{row_index}]",
                        "props": {"height": _length(row_height)},
                    }
                )
                sources.append(obj)
                for column_index in range(1, len(obj.column_widths) + 1):
                    cell = obj.table_cells[cell_index]
                    cell_index += 1
                    commands.append(
                        {
                            "command": "set",
                            "path": f"{table_path}/tr[{row_index}]/tc[{column_index}]",
                            "props": cell.props,
                        }
                    )
                    sources.append(obj)
                    if cell.paragraphs:
                        cell_path = f"{table_path}/tr[{row_index}]/tc[{column_index}]"
                        # OfficeCLI's table-cell setter is the public paragraph
                        # formatting surface for Contract v1: align,
                        # linespacing, spacebefore, spaceafter, and direction
                        # fan out to every paragraph in the cell.  Those
                        # properties were projected into ``cell.props`` above;
                        # OfficeCLI range offsets address the concatenated
                        # character scope, so paragraph separators are not
                        # included in the later run offset.
                        offset = 0
                        for paragraph in cell.paragraphs:
                            for run in paragraph.get("runs", []):
                                text = str(run.get("text", ""))
                                if not text:
                                    continue
                                range_length = _officecli_range_length(text)
                                if not range_length:
                                    continue
                                run_props = _run_props(run)
                                commands.append(
                                    {
                                        "command": "set",
                                        "path": cell_path,
                                        "props": {
                                            "range": f"{offset}:{offset + range_length}",
                                            **run_props,
                                        },
                                    }
                                )
                                sources.append(obj)
                                offset += range_length
    return commands, sources


def _batch_chunks(
    commands: Sequence[dict[str, Any]],
    sources: Sequence[_ObjectIR | None],
    *,
    max_bytes: int = _OFFICECLI_BATCH_MAX_BYTES,
) -> Iterable[tuple[list[dict[str, Any]], list[_ObjectIR | None]]]:
    """Split large OfficeCLI JSON batches without splitting one command."""
    if len(commands) != len(sources):
        raise ValueError("OfficeCLI commands and source mappings must have equal lengths")
    if max_bytes <= 0:
        raise ValueError("OfficeCLI batch byte limit must be positive")

    current_commands: list[dict[str, Any]] = []
    current_sources: list[_ObjectIR | None] = []
    current_bytes = 2  # JSON array brackets.
    for command, source in zip(commands, sources):
        command_bytes = len(
            json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        comma_bytes = 1 if current_commands else 0
        if current_commands and current_bytes + comma_bytes + command_bytes > max_bytes:
            yield current_commands, current_sources
            current_commands = []
            current_sources = []
            current_bytes = 2
            comma_bytes = 0
        current_commands.append(command)
        current_sources.append(source)
        current_bytes += comma_bytes + command_bytes
    if current_commands:
        yield current_commands, current_sources


def _source_for_command_error(
    error: _OfficeCLICommandError,
    sources: Sequence[_ObjectIR | None],
) -> _ObjectIR | None:
    match = _BATCH_INDEX_RE.search(error.stdout + "\n" + error.stderr)
    if not match:
        return None
    batch_index = int(match.group(1))
    return sources[batch_index - 1] if 0 < batch_index <= len(sources) else None


def _failure_from_command(
    error: _OfficeCLICommandError,
    sources: Sequence[_ObjectIR | None],
) -> OfficeCLICompilationError:
    source = _source_for_command_error(error, sources)
    details = (error.stderr or error.stdout).strip() or f"exit code {error.returncode}"
    message = f"OfficeCLI {error.operation} failed"
    if source is not None:
        message += f" for source slide {source.source_slide}, {source.source_object}"
    message += f": {details}"
    diagnostic = CompilationDiagnostic(
        "error",
        "officecli_failure",
        message,
        source.source_slide if source else None,
        source.source_object if source else None,
        error.operation,
    )
    return OfficeCLICompilationError(message, [diagnostic])


def _manifest(slides: Sequence[_SlideIR]) -> dict[str, Any]:
    objects = [obj.as_manifest() for slide in slides for obj in slide.objects]
    counts: dict[str, int] = {}
    for obj in objects:
        counts[obj["kind"]] = counts.get(obj["kind"], 0) + 1
    return {
        "slide_count": len(slides),
        "slide_size_pt": {"width": SLIDE_WIDTH_PT, "height": SLIDE_HEIGHT_PT},
        "object_kind_counts": counts,
        "objects": objects,
    }


def _officecli_range_length(text: str) -> int:
    """Return the character count accepted by OfficeCLI's range setter.

    OfficeCLI ranges use UTF-16 code units, but paragraph line breaks are
    represented in the text body rather than the addressable character scope.
    """
    visible_text = text.replace("\r", "").replace("\n", "")
    return len(visible_text.encode("utf-16-le")) // 2


async def compile_officecli(
    input_html: str,
    profile: str,
    output_pptx: str,
    *,
    slide_indices: Sequence[int] | None = None,
) -> OfficeCLICompilationResult:
    """Compile Author HTML or OfficeCLI HTML to a validated native PPTX.

    ``slide_indices`` is zero-based and exists so the first tracer-bullet can
    compile Algeria slide 8 as a one-slide deck.  Omitting it compiles every
    measured slide.  The ``officehtml`` profile consumes OfficeCLI 1.0.151's
    fixed-coordinate projection; its ``data-path`` values remain source
    identity metadata and are not write-back instructions.
    """
    if profile not in {"author", "officehtml"}:
        raise ValueError(
            f"Unsupported input profile {profile!r}; choose 'author' or 'officehtml'."
        )
    destination = Path(output_pptx).expanduser()
    if destination.exists():
        raise FileExistsError(f"Output already exists: {destination}")
    if not destination.parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {destination.parent}")

    contract = check_contract(input_html, profile)
    if contract.blocked:
        raise _contract_failure(contract)

    if profile == "author":
        measurements = await extract_measurements(
            input_html,
            include_picture_fallbacks=True,
            officecli_mode=True,
        )
    else:
        measurements = _parse_officehtml_measurements(input_html)
        if any(
            str(element.get("src", "") or "").lower().startswith(
                "data:image/svg+xml"
            )
            for slide in measurements
            for element in slide.get("elements", []) or []
        ) and not _officecli_supports_svg():
            await _rasterize_officehtml_svg_fallbacks(measurements)
    selected = _select_measurements(measurements, slide_indices)
    slides = [
        _lower_slide(index, data, profile=profile)
        for index, data in selected
    ]
    manifest = _manifest(slides)
    raster_fallbacks: set[str] = set()
    svg_pictures = [
        obj
        for slide in slides
        for obj in slide.objects
        if obj.kind == "picture"
        and obj.props.get("src", "").lower().startswith("data:image/svg+xml")
    ]
    if svg_pictures and not _officecli_supports_svg():
        missing_fallback = next(
            (obj for obj in svg_pictures if obj.fallback_props is None),
            None,
        )
        if missing_fallback is not None:
            raise _diagnostic(
                "picture_fallback_unavailable",
                f"No deterministic raster fallback is available for the SVG picture on source slide {missing_fallback.source_slide}, {missing_fallback.source_object}.",
                missing_fallback.source_slide,
                missing_fallback.source_object,
            )
        raster_fallbacks.update(obj.name for obj in svg_pictures)

    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".pptx", dir=str(destination.parent)
    )
    os.close(temp_fd)
    temporary = Path(temp_name)
    temporary.unlink()
    resident = False
    try:
        while True:
            commands, sources = _batch_for_slides(slides, raster_fallbacks)
            retry_with_fallback = False
            try:
                _run_officecli(["create", str(temporary)])
                resident = True
                for batch_commands, batch_sources in _batch_chunks(commands, sources):
                    command_json = json.dumps(
                        batch_commands,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    try:
                        _run_officecli(
                            ["batch", str(temporary)], input_text=command_json
                        )
                    except _OfficeCLICommandError as error:
                        source = _source_for_command_error(error, batch_sources)
                        if (
                            source is not None
                            and source.fallback_props is not None
                            and source.name not in raster_fallbacks
                        ):
                            raster_fallbacks.add(source.name)
                            retry_with_fallback = True
                            break
                        raise _failure_from_command(error, batch_sources) from error
                if not retry_with_fallback:
                    _run_officecli(["validate", str(temporary)])
            except _OfficeCLICommandError as error:
                source = _source_for_command_error(error, sources)
                if (
                    error.operation == "batch"
                    and source is not None
                    and source.fallback_props is not None
                    and source.name not in raster_fallbacks
                ):
                    raster_fallbacks.add(source.name)
                    retry_with_fallback = True
                else:
                    raise _failure_from_command(error, sources) from error
            finally:
                if resident:
                    _run_officecli(["close", str(temporary)], check=False)
                    resident = False
            if not retry_with_fallback:
                break
            temporary.unlink(missing_ok=True)
        if destination.exists():
            raise FileExistsError(f"Output already exists: {destination}")
        os.replace(temporary, destination)
    finally:
        if resident:
            _run_officecli(["close", str(temporary)], check=False)
        if temporary.exists():
            temporary.unlink()

    return OfficeCLICompilationResult(
        str(destination),
        profile,
        len(slides),
        sum(len(slide.objects) for slide in slides),
        (),
        manifest,
    )


__all__ = [
    "CompilationDiagnostic",
    "OfficeCLICompilationError",
    "OfficeCLICompilationResult",
    "compile_officecli",
]
