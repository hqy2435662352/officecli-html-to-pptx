"""OfficeCLI-first compiler for native shape, text, and picture slices.

The legacy :mod:`html_to_pptx.converter` renderer remains untouched.  This
module reuses its Chromium measurement stage, lowers the resulting plain
dictionaries into a small presentation-object IR, and sends one JSON batch to
OfficeCLI.
"""

from __future__ import annotations

import base64
import binascii
from io import BytesIO
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

from .converter import _resolve_pptx_font, extract_measurements

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
_INLINE_TAGS = {
    "span", "strong", "em", "b", "i", "a", "code", "mark", "sub",
    "sup", "small", "u", "s", "del", "abbr", "cite", "q", "time",
    "var", "kbd",
}


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

    def as_manifest(self) -> dict[str, Any]:
        return {
            "kind": "cell",
            "name": self.name,
            "source_slide": self.source_slide,
            "source_object": self.source_object,
            "bounds_pt": list(self.bounds),
            "text": self.text,
            "props": dict(self.props),
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
        }
        if self.kind == "table":
            manifest.update(
                {
                    "rows": len(self.row_heights),
                    "columns": len(self.column_widths),
                    "column_widths_pt": list(self.column_widths),
                    "row_heights_pt": list(self.row_heights),
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
            [CompilationDiagnostic("error", "officecli_unavailable", "Install OfficeCLI 1.0.147 and add it to PATH.")],
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
    runs = element.get("inlineRuns")
    if runs:
        return "".join(str(run.get("text", "")) for run in runs)
    return str(element.get("text", "") or "")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def _line_spacing(element: dict[str, Any]) -> str | None:
    font_size = _number(element.get("fontSize"))
    line_height = str(element.get("lineHeight", "") or "")
    match = re.fullmatch(r"\s*([\d.]+)px\s*", line_height)
    if not match or font_size <= 0:
        return None
    ratio = float(match.group(1)) / font_size
    if abs(ratio - 1.0) < 0.01:
        return None
    return f"{ratio:.3f}x"


def _text_alignment(element: dict[str, Any]) -> str:
    value = str(element.get("textAlign", "start") or "start").lower()
    direction = str(element.get("direction", "ltr") or "ltr").lower()
    if value == "start":
        return "right" if direction == "rtl" else "left"
    if value == "end":
        return "left" if direction == "rtl" else "right"
    return value if value in {"left", "center", "right", "justify"} else "left"


def _vertical_alignment(element: dict[str, Any]) -> str:
    value = str(element.get("alignItems", "") or "").lower()
    if value in {"center", "middle"}:
        return "middle"
    if value in {"flex-end", "end"}:
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


def _tight_single_line_font_scale(
    element: dict[str, Any],
    text: str,
) -> str | None:
    """Keep measured one-line labels on one line with OfficeCLI font metrics."""
    if not text or "\n" in text:
        return None
    font_size = _number(element.get("fontSize"))
    element_width = _number(element.get("width"))
    element_height = _number(element.get("height"))
    if font_size <= 0 or element_width <= 0 or element_height > font_size * 1.45:
        return None
    # A block whose measured width is close to the raw text width is vulnerable
    # to a substituted PowerPoint font wrapping one glyph.  Leave wider text
    # boxes and multi-line browser layout at their measured size.
    density = element_width / (font_size * max(1, len(text)))
    if density > 0.75:
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
        props["color"] = _hex(rgb if alpha >= 0.999 else _blend(rgb, alpha, backdrop))
    if _is_bold(element.get("fontWeight")):
        props["bold"] = "true"
    if str(element.get("fontStyle", "")).lower() in {"italic", "oblique"}:
        props["italic"] = "true"
    direction = str(element.get("direction", "ltr") or "ltr").lower()
    if direction == "rtl":
        props["direction"] = "rtl"
    margin = _margin(element, scale_x, scale_y)
    if margin is not None:
        props["margin"] = margin
    font_scale = _tight_single_line_font_scale(element, _text_of(element))
    if font_scale is not None:
        props["fontScale"] = font_scale
    line_spacing = _line_spacing(element)
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
    props["geometry"] = "roundRect" if _border_radius(element) > 0 else "rect"

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
    if radius > 0 and min_size > 0:
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


def _table_cell_props(
    element: dict[str, Any],
    scale_x: float,
    scale_y: float,
    backdrop: tuple[int, int, int],
    source_slide: int,
    source_object: str,
) -> dict[str, str]:
    props: dict[str, str] = {"text": _text_of(element)}
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

    for row_index, cells in enumerate(row_cells, start=1):
        for column_index, cell in enumerate(cells, start=1):
            cell_source = f"{source_object}/tr[{row_index}]/tc[{column_index}]"
            row_span = _number(cell.get("rowSpan"), 1)
            col_span = _number(cell.get("colSpan"), 1)
            if row_span != 1 or col_span != 1:
                raise _diagnostic(
                    "unsupported_table_span",
                    f"Unsupported merged table cell on source slide {source_slide}, {cell_source}: rowspan and colspan must both be 1.",
                    source_slide,
                    cell_source,
                )
            if cell.get("backgroundImage"):
                raise _diagnostic(
                    "unsupported_table_effect",
                    f"Unsupported cell fill on source slide {source_slide}, {cell_source}: image or gradient fills are not supported.",
                    source_slide,
                    cell_source,
                )

    column_count = len(row_cells[0])
    if any(len(cells) != column_count for cells in row_cells):
        raise _diagnostic(
            "invalid_table_matrix",
            f"Invalid table on source slide {source_slide}, {source_object}: every row must have {column_count} cells.",
            source_slide,
            source_object,
        )

    row_heights = tuple(_pt(_number(row.get("height")), scale_y) for row in rows)
    column_widths = tuple(
        _pt(_number(cell.get("width")), scale_x) for cell in row_cells[0]
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
        "height": _length(bounds[3]),
        "rows": str(len(rows)),
        "cols": str(column_count),
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
    for row_index, cells in enumerate(row_cells, start=1):
        for column_index, cell in enumerate(cells, start=1):
            cell_source = f"{source_object}/tr[{row_index}]/tc[{column_index}]"
            cell_name = f"{name}-cell-r{row_index:03d}-c{column_index:03d}"
            cell_bounds = _bounds(cell, scale_x, scale_y)
            table_cells.append(
                _TableCellIR(
                    cell_name,
                    source_slide,
                    cell_source,
                    cell_bounds,
                    _text_of(cell),
                    _table_cell_props(
                        cell,
                        scale_x,
                        scale_y,
                        backdrop,
                        source_slide,
                        cell_source,
                    ),
                )
            )
    return _ObjectIR(
        kind="table",
        name=name,
        source_slide=source_slide,
        source_object=source_object,
        bounds=bounds,
        props=table_props,
        table_cells=tuple(table_cells),
        row_heights=row_heights,
        column_widths=column_widths,
    )


def _lower_slide(source_index: int, slide_data: dict[str, Any]) -> _SlideIR:
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
    ) -> None:
        name = f"slide-{source_slide:03d}-{kind}-{len(result.objects) + 1:03d}"
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
            font_size = _number(element.get("fontSize"))
            element_height = _number(element.get("height"))
            if (
                "\n" not in text
                and font_size > 0
                and element_height <= font_size * 1.45
            ):
                object_props.setdefault("autoFit", "shrink")
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
            )
        )

    def walk(
        element: dict[str, Any],
        source_object: str,
        inherited_backdrop: tuple[int, int, int],
    ) -> None:
        tag = str(element.get("tag", "element") or "element").lower()
        text = _text_of(element)
        if element.get("isImage") or element.get("isSvg") or tag in {"img", "svg"}:
            picture_bounds = _bounds(element, scale_x, scale_y)
            picture_props, fallback_props = _picture_props(
                element,
                picture_bounds,
                source_slide,
                source_object,
            )
            add_object(
                element,
                source_object,
                "picture",
                "",
                picture_props,
                picture_bounds,
                fallback_props,
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

        child_backdrop = inherited_backdrop
        if fill is not None:
            fill_rgb, fill_alpha = fill
            effective_alpha = fill_alpha * max(0.0, min(1.0, _number(element.get("opacity"), 1.0)))
            child_backdrop = _blend(fill_rgb, effective_alpha, inherited_backdrop)

        if has_shape:
            props = _shape_props(element, bounds, scale_x_local, scale_y_local, inherited_backdrop)
            add_object(element, source_object, "shape", text, props, bounds)
        elif text:
            props = _text_props(element, bounds, scale_x_local, scale_y_local, inherited_backdrop)
            add_object(element, source_object, "textbox", text, props, bounds)

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

        child_elements = element.get("children", []) or []
        for position, child in enumerate(child_elements, start=1):
            child_tag = str(child.get("tag", "element") or "element").lower()
            if element.get("inlineRuns") and child_tag in _INLINE_TAGS:
                continue
            child_path = _source_path(source_slide, source_object, child_tag, position)
            walk(child, child_path, child_backdrop)

    for position, element in enumerate(slide_data.get("elements", []) or [], start=1):
        tag = str(element.get("tag", "element") or "element").lower()
        walk(element, _source_path(source_slide, "", tag, position), backdrop)
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
    return commands, sources


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


async def compile_officecli(
    input_html: str,
    profile: str,
    output_pptx: str,
    *,
    slide_indices: Sequence[int] | None = None,
) -> OfficeCLICompilationResult:
    """Compile Author HTML to a validated native-object PPTX with OfficeCLI.

    ``slide_indices`` is zero-based and exists so the first tracer-bullet can
    compile Algeria slide 8 as a one-slide deck.  Omitting it compiles every
    measured slide; later slices can extend the same public seam without
    changing the legacy renderer.
    """
    if profile != "author":
        raise ValueError(
            f"Unsupported input profile {profile!r}; this slice accepts only 'author'."
        )
    destination = Path(output_pptx).expanduser()
    if destination.exists():
        raise FileExistsError(f"Output already exists: {destination}")
    if not destination.parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {destination.parent}")

    measurements = await extract_measurements(
        input_html,
        include_picture_fallbacks=True,
    )
    selected = _select_measurements(measurements, slide_indices)
    slides = [_lower_slide(index, data) for index, data in selected]
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
            command_json = json.dumps(commands, ensure_ascii=False, separators=(",", ":"))
            retry_with_fallback = False
            try:
                _run_officecli(["create", str(temporary)])
                resident = True
                _run_officecli(["batch", str(temporary)], input_text=command_json)
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
