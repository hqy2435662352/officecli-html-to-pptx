"""OfficeCLI-first compiler for the first native shape/text slice.

The legacy :mod:`html_to_pptx.converter` renderer remains untouched.  This
module reuses its Chromium measurement stage, lowers the resulting plain
dictionaries into a small presentation-object IR, and sends one JSON batch to
OfficeCLI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .converter import _resolve_pptx_font, extract_measurements

SLIDE_WIDTH_PT = 960.0
SLIDE_HEIGHT_PT = 540.0
_COLOR_RE = re.compile(
    r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)"
    r"(?:\s*,\s*([\d.]+))?\s*\)"
)
_HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{3,8})$")
_BATCH_INDEX_RE = re.compile(r"\[(\d+)\]")
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
class _ObjectIR:
    kind: str
    name: str
    source_slide: int
    source_object: str
    bounds: tuple[float, float, float, float]
    props: dict[str, str]
    text: str = ""

    def as_manifest(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "source_slide": self.source_slide,
            "source_object": self.source_object,
            "bounds_pt": list(self.bounds),
            "text": self.text,
        }


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
    ) -> None:
        name = f"slide-{source_slide:03d}-{kind}-{len(result.objects) + 1:03d}"
        object_props = dict(props)
        object_props["name"] = name
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
            _ObjectIR(kind, name, source_slide, source_object, bounds, object_props, text)
        )

    def walk(
        element: dict[str, Any],
        source_object: str,
        inherited_backdrop: tuple[int, int, int],
    ) -> None:
        tag = str(element.get("tag", "element") or "element").lower()
        text = _text_of(element)
        if element.get("isImage") or element.get("isSvg") or tag in {"img", "svg"}:
            raise _diagnostic(
                "unsupported_picture",
                f"Unsupported visible object on source slide {source_slide}, {source_object}: pictures are deferred to the picture slice.",
                source_slide,
                source_object,
            )
        if tag == "table":
            raise _diagnostic(
                "unsupported_table",
                f"Unsupported visible object on source slide {source_slide}, {source_object}: native tables are deferred to the table slice.",
                source_slide,
                source_object,
            )
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
            commands.append(
                {
                    "command": "add",
                    "parent": f"/slide[{output_index}]",
                    "type": obj.kind,
                    "props": obj.props,
                }
            )
            sources.append(obj)
    return commands, sources


def _failure_from_command(
    error: _OfficeCLICommandError,
    sources: Sequence[_ObjectIR | None],
) -> OfficeCLICompilationError:
    batch_index: int | None = None
    match = _BATCH_INDEX_RE.search(error.stdout + "\n" + error.stderr)
    if match:
        batch_index = int(match.group(1))
    source = sources[batch_index - 1] if batch_index and batch_index <= len(sources) else None
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

    measurements = await extract_measurements(input_html)
    selected = _select_measurements(measurements, slide_indices)
    slides = [_lower_slide(index, data) for index, data in selected]
    commands, sources = _batch_for_slides(slides)
    command_json = json.dumps(commands, ensure_ascii=False, separators=(",", ":"))
    manifest = _manifest(slides)

    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".pptx", dir=str(destination.parent)
    )
    os.close(temp_fd)
    temporary = Path(temp_name)
    temporary.unlink()
    resident = False
    try:
        try:
            _run_officecli(["create", str(temporary)])
            resident = True
            _run_officecli(["batch", str(temporary)], input_text=command_json)
            _run_officecli(["validate", str(temporary)])
        except _OfficeCLICommandError as error:
            raise _failure_from_command(error, sources) from error
        finally:
            if resident:
                _run_officecli(["close", str(temporary)], check=False)
                resident = False
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
