"""Safety gates for Contract 1.3 localized raster captures.

Ticket #35 owns discovery/lowering of an accepted region.  This module owns
the narrow safety boundary that #36 can test independently: static-content
admission, geometry/ownership checks, and validation of the PNG bytes handed
to the existing picture lowering path.  It intentionally contains no browser
or screenshot-backend abstraction; the capture owner supplies bytes and the
facts that only its rendering context can observe.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlparse

from PIL import Image, UnidentifiedImageError


LOCALIZED_RASTERIZE_ATTRIBUTE = "data-pptx-rasterize"
LOCALIZED_RASTERIZE_TOKEN = "localized"
LOCALIZED_CAPTURE_DENSITY = 2.0
_PIXEL_ROUNDING_TOLERANCE = 1
_DENSITY_TOLERANCE = 0.01
_EFFECTIVE_ALPHA_THRESHOLD = 8
_EFFECTIVE_PAINT_FRACTION = 0.001

_UNSUPPORTED_TAGS = frozenset(
    {
        "audio",
        "canvas",
        "embed",
        "iframe",
        "object",
        "video",
    }
)
_MEDIA_TAGS = frozenset({"audio", "source", "track", "video"})
_NON_INLINE_RESOURCE_TAGS = frozenset({"link"})
_ATOMIC_TAGS = frozenset({"table"})
_EXTERNAL_SCHEMES = frozenset(
    {
        "about",
        "blob",
        "data+https",
        "file",
        "ftp",
        "http",
        "https",
        "javascript",
        "ws",
        "wss",
    }
)
_URL_RE = re.compile(r"url\(\s*(?P<quote>[\"']?)(?P<value>.*?)(?P=quote)\s*\)", re.I | re.S)
_IMPORT_RE = re.compile(r"@import\b", re.I)
_KEYFRAMES_RE = re.compile(r"@(?:-webkit-)?keyframes\b", re.I)
_ANIMATION_PROPERTY_RE = re.compile(r"^(?:-webkit-)?(?:animation|transition)(?:-.+)?$")
_EVENT_ATTRIBUTE_RE = re.compile(r"^on[a-z][a-z0-9_-]*$", re.I)


@dataclass(frozen=True)
class LocalizedPolicyFinding:
    """One deterministic, source-bound safety failure."""

    code: str
    message: str
    source_object: str

    @property
    def blocking(self) -> bool:
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": "error",
            "code": self.code,
            "message": self.message,
            "source_object": self.source_object,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class LocalizedRegion:
    """Measured ownership facts used to reject ambiguous regions."""

    source_object: str
    slide: int
    bounds_pt: tuple[float, float, float, float]


@dataclass(frozen=True)
class LocalizedCaptureAudit:
    """Validation of one untrusted localized PNG and its capture evidence."""

    source_object: str | None
    asset_sha256: str | None
    mime: str
    pixel_width: int
    pixel_height: int
    expected_pixel_width: int
    expected_pixel_height: int
    density: float
    required_density: float
    nonblank: bool
    effectively_transparent: bool
    paint_fraction: float
    contamination_fraction: float
    overflow: bool
    isolated: bool
    excluded_descendants: int
    failure_codes: tuple[str, ...]
    isolation_evidence: dict[str, Any]

    @property
    def passed(self) -> bool:
        return not self.failure_codes

    def as_dict(self) -> dict[str, Any]:
        """Return the stable evidence vocabulary consumed by later tickets."""
        return {
            "source_object": self.source_object,
            "asset_sha256": self.asset_sha256,
            "mime": self.mime,
            "pixel_dimensions": {
                "width": self.pixel_width,
                "height": self.pixel_height,
            },
            "expected_pixel_dimensions": {
                "width": self.expected_pixel_width,
                "height": self.expected_pixel_height,
            },
            "density": self.density,
            "required_density": self.required_density,
            "nonblank": self.nonblank,
            "effectively_transparent": self.effectively_transparent,
            "paint_fraction": self.paint_fraction,
            "contamination_fraction": self.contamination_fraction,
            "overflow": self.overflow,
            "isolated": self.isolated,
            "excluded_descendants": self.excluded_descendants,
            "isolation_evidence": dict(self.isolation_evidence),
            "failure_codes": list(self.failure_codes),
            "passed": self.passed,
        }


def localized_source_path(element: Any) -> str:
    """Return the deterministic Author path for one DOM element."""
    try:
        tree = element.getroottree()
        slides = tree.getroot().xpath(
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]"
        )
        ancestors = element.xpath(
            "ancestor-or-self::*[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]"
        )
        if not ancestors:
            return str(tree.getpath(element))
        slide = ancestors[-1]
        slide_path = str(tree.getpath(slide))
        slide_index = next(
            (
                index
                for index, candidate in enumerate(slides, start=1)
                if str(tree.getpath(candidate)) == slide_path
            ),
            None,
        )
        if slide_index is None:
            return str(tree.getpath(element))

        parts: list[str] = []
        current = element
        while str(tree.getpath(current)) != slide_path:
            parent = current.getparent()
            if parent is None:
                return str(tree.getpath(element))
            position = next(
                (
                    index
                    for index, sibling in enumerate(parent, start=1)
                    if str(tree.getpath(sibling)) == str(tree.getpath(current))
                ),
                None,
            )
            if position is None:
                return str(tree.getpath(element))
            parts.append(f"{str(current.tag).lower()}[{position}]")
            current = parent
        parts.reverse()
        return f"slide[{slide_index}]" + (
            "/" + "/".join(parts) if parts else ""
        )
    except (AttributeError, TypeError, ValueError):
        return f"<{getattr(element, 'tag', 'region')}>"


def _source_object(element: Any) -> str:
    explicit_id = str(element.get("id", "") or "").strip()
    if explicit_id:
        return explicit_id
    return localized_source_path(element)


def _iter_elements(element: Any) -> Iterable[Any]:
    for child in element.iter():
        if isinstance(getattr(child, "tag", None), str):
            yield child


def _split_declarations(value: str) -> list[str]:
    """Split CSS declarations without breaking quoted function arguments."""
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
    raw = str(element.get("style", "") or "")
    for declaration in _split_declarations(raw):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        name = name.strip().lower()
        if name:
            styles[name] = value.strip()
    return styles


def _is_external_or_unsafe_url(value: str, *, base_dir: Path | None) -> bool:
    value = value.strip().strip("\"'")
    if not value:
        return False
    lowered = value.lower()
    if lowered.startswith("data:image/"):
        return False
    parsed = urlparse(value)
    if parsed.scheme.lower() in _EXTERNAL_SCHEMES:
        if parsed.scheme.lower() == "file":
            if base_dir is None:
                return True
            candidate = Path(unquote(parsed.path))
            return not candidate.is_file()
        return True
    if value.startswith("//"):
        return True
    if parsed.scheme:
        return True
    # Relative local resources are deterministic only when they exist beside
    # the source.  With no base directory the caller is doing an in-memory
    # policy check; preserving that relative source is safe to defer to the
    # existing input-path resolver.
    if base_dir is None:
        return False
    candidate = (base_dir / unquote(parsed.path)).resolve()
    return not candidate.is_file() or not candidate.is_relative_to(base_dir)


def _finding(code: str, message: str, source: str) -> LocalizedPolicyFinding:
    return LocalizedPolicyFinding(code, message, source)


def validate_localized_document(
    document: Any,
    *,
    base_dir: str | Path | None = None,
) -> tuple[LocalizedPolicyFinding, ...]:
    """Validate every explicitly annotated region in an HTML document.

    This is a structural gate, deliberately independent of browser layout.
    A caller may run it before generic object discovery so a rejected region
    cannot leak descendants into the native lowering path.
    """
    source_dir = Path(base_dir).expanduser().resolve() if base_dir is not None else None
    findings: list[LocalizedPolicyFinding] = []
    regions: list[Any] = []

    for element in _iter_elements(document):
        if LOCALIZED_RASTERIZE_ATTRIBUTE not in getattr(element, "attrib", {}):
            continue
        source = _source_object(element)
        token = str(element.get(LOCALIZED_RASTERIZE_ATTRIBUTE) or "")
        if token != LOCALIZED_RASTERIZE_TOKEN:
            findings.append(
                _finding(
                    "localized_unknown_token",
                    f"{LOCALIZED_RASTERIZE_ATTRIBUTE} must equal {LOCALIZED_RASTERIZE_TOKEN!r}; got {token!r}.",
                    source,
                )
            )
            continue
        regions.append(element)

    for element in regions:
        source = _source_object(element)
        descendants = list(_iter_elements(element))[1:]
        root_tag = str(getattr(element, "tag", "")).lower()
        tags = [str(getattr(item, "tag", "")).lower() for item in descendants]
        unsupported_tags = [tag for tag in [root_tag, *tags] if tag in _UNSUPPORTED_TAGS]
        if unsupported_tags:
            bad_tag = unsupported_tags[0]
            findings.append(
                _finding(
                    "localized_unsupported_tag",
                    f"<{bad_tag}> is not permitted inside a localized static region.",
                    source,
                )
            )
        if root_tag in _MEDIA_TAGS or any(tag in _MEDIA_TAGS for tag in tags):
            findings.append(
                _finding(
                    "localized_unsupported_tag",
                    "Audio/video media is not permitted inside a localized region.",
                    source,
                )
            )
        if root_tag == "script" or any(tag == "script" for tag in tags):
            findings.append(
                _finding(
                    "localized_executable_content",
                    "Scripts remain inert and are rejected inside a localized region.",
                    source,
                )
            )
        if root_tag in _NON_INLINE_RESOURCE_TAGS or any(
            tag in _NON_INLINE_RESOURCE_TAGS for tag in tags
        ):
            findings.append(
                _finding(
                    "localized_external_resource",
                    "Linked stylesheets are not copied into an isolated localized capture; use inline CSS.",
                    source,
                )
            )
        if root_tag == "table" or any(
            tag == "table" or item.get("data-pptx-chart") is not None
            for item, tag in zip(descendants, tags)
        ):
            findings.append(
                _finding(
                    "localized_atomic_descendant",
                    "A localized region cannot own another atomic table or chart object.",
                    source,
                )
            )
        if any(item.get(LOCALIZED_RASTERIZE_ATTRIBUTE) is not None for item in descendants):
            findings.append(
                _finding(
                    "localized_nested_region",
                    "Nested localized regions have ambiguous object ownership.",
                    source,
                )
            )
        if any("slide" in str(item.get("class", "")).split() for item in descendants):
            findings.append(
                _finding(
                    "localized_cross_slide",
                    "A localized region cannot contain another slide.",
                    source,
                )
            )
        if "slide" in str(element.get("class", "")).split():
            findings.append(
                _finding(
                    "localized_whole_slide",
                    "A slide root cannot be a localized fallback region.",
                    source,
                )
            )

        for item in _iter_elements(element):
            item_source = _source_object(item)
            for attribute, raw_value in item.attrib.items():
                name = str(attribute).lower()
                value = str(raw_value or "")
                if _EVENT_ATTRIBUTE_RE.match(name) or name in {
                    "contenteditable",
                    "draggable",
                    "tabindex",
                }:
                    findings.append(
                        _finding(
                            "localized_interactive_content",
                            f"Interactive attribute {attribute!r} is not permitted in a localized region.",
                            item_source,
                        )
                    )
                if name in {"src", "href", "poster", "xlink:href"} and _is_external_or_unsafe_url(
                    value, base_dir=source_dir
                ):
                    findings.append(
                        _finding(
                            "localized_external_resource",
                            f"External or unavailable local resource in {attribute!r} is not deterministic.",
                            item_source,
                        )
                    )

            for property_name, value in _inline_styles(item).items():
                if _ANIMATION_PROPERTY_RE.match(property_name):
                    findings.append(
                        _finding(
                            "localized_animation",
                            f"CSS {property_name} is not permitted in a static localized region.",
                            item_source,
                        )
                    )
                for match in _URL_RE.finditer(value):
                    if _is_external_or_unsafe_url(match.group("value"), base_dir=source_dir):
                        findings.append(
                            _finding(
                                "localized_external_resource",
                                "External or unavailable local CSS resources are not deterministic.",
                                item_source,
                            )
                        )

        for style in element.xpath(".//style") if hasattr(element, "xpath") else ():
            css = str(style.text or "")
            if _IMPORT_RE.search(css):
                findings.append(
                    _finding(
                        "localized_external_resource",
                        "@import is not permitted in a localized region.",
                        _source_object(style),
                    )
                )
            if _KEYFRAMES_RE.search(css):
                findings.append(
                    _finding(
                        "localized_animation",
                        "CSS keyframes are not permitted in a static localized region.",
                        _source_object(style),
                    )
                )
            if any(
                _is_external_or_unsafe_url(match.group("value"), base_dir=source_dir)
                for match in _URL_RE.finditer(css)
            ):
                findings.append(
                    _finding(
                        "localized_external_resource",
                        "External or unavailable local CSS resources are not deterministic.",
                        _source_object(style),
                    )
                )

    return tuple(findings)


def _valid_box(bounds: Sequence[float]) -> bool:
    try:
        return len(bounds) == 4 and all(math.isfinite(float(value)) for value in bounds)
    except (TypeError, ValueError):
        return False


def _box_size(bounds: Sequence[float]) -> tuple[float, float]:
    if not _valid_box(bounds):
        return 0.0, 0.0
    return float(bounds[2]), float(bounds[3])


def _contains(outer: Sequence[float], inner: Sequence[float], *, tolerance: float = 0.01) -> bool:
    ox, oy, ow, oh = (float(value) for value in outer)
    ix, iy, iw, ih = (float(value) for value in inner)
    return (
        ix >= ox - tolerance
        and iy >= oy - tolerance
        and ix + iw <= ox + ow + tolerance
        and iy + ih <= oy + oh + tolerance
    )


def _intersects(first: Sequence[float], second: Sequence[float]) -> bool:
    ax, ay, aw, ah = (float(value) for value in first)
    bx, by, bw, bh = (float(value) for value in second)
    return min(ax + aw, bx + bw) > max(ax, bx) and min(ay + ah, by + bh) > max(ay, by)


def validate_localized_geometry(
    source_object: str,
    bounds_pt: Sequence[float],
    slide_bounds_pt: Sequence[float],
    *,
    paint_bounds_pt: Sequence[float] | None = None,
    is_slide_root: bool = False,
) -> tuple[LocalizedPolicyFinding, ...]:
    """Validate canonical border-box geometry before capture/lowering."""
    findings: list[LocalizedPolicyFinding] = []
    width_pt, height_pt = _box_size(bounds_pt)
    if width_pt <= 0 or height_pt <= 0:
        findings.append(
            _finding(
                "localized_unmeasurable",
                "Localized capture bounds must be finite and have positive width and height.",
                source_object,
            )
        )
        return tuple(findings)
    slide_width_pt, slide_height_pt = _box_size(slide_bounds_pt)
    if slide_width_pt <= 0 or slide_height_pt <= 0:
        findings.append(
            _finding(
                "localized_unmeasurable",
                "Slide bounds must be finite and have positive width and height.",
                source_object,
            )
        )
        return tuple(findings)
    same_bounds = all(
        abs(float(first) - float(second)) <= 0.01
        for first, second in zip(bounds_pt, slide_bounds_pt)
    )
    if is_slide_root or same_bounds:
        findings.append(
            _finding(
                "localized_whole_slide",
                "Localized fallback cannot cover the complete slide border box.",
                source_object,
            )
        )
    if not _contains(slide_bounds_pt, bounds_pt):
        findings.append(
            _finding(
                "localized_cross_slide",
                "Localized capture bounds must remain inside one slide.",
                source_object,
            )
        )
    if paint_bounds_pt is not None:
        if not _valid_box(paint_bounds_pt) or not _contains(bounds_pt, paint_bounds_pt):
            findings.append(
                _finding(
                    "localized_visual_overflow",
                    "Paint extends outside the authored border box; add wrapper padding instead of clipping.",
                    source_object,
                )
            )
    return tuple(findings)


def validate_localized_region_overlap(
    regions: Sequence[LocalizedRegion],
) -> tuple[LocalizedPolicyFinding, ...]:
    """Reject overlap only within the same slide; different slides are safe."""
    findings: list[LocalizedPolicyFinding] = []
    for index, region in enumerate(regions):
        for previous in regions[:index]:
            if region.slide == previous.slide and _intersects(region.bounds_pt, previous.bounds_pt):
                findings.append(
                    _finding(
                        "localized_overlap",
                        f"Localized region overlaps {previous.source_object!r} on slide {region.slide}.",
                        region.source_object,
                    )
                )
                break
    return tuple(findings)


def _capture_failure_codes(
    *,
    payload: bytes | None,
    image: Image.Image | None,
    bounds_pt: Sequence[float],
    contamination_fraction: float,
    overflow: bool,
    isolated: bool,
    excluded_descendants: int,
) -> tuple[str, ...]:
    failures: list[str] = []
    if payload is None:
        failures.append("localized_missing_asset")
        if overflow:
            failures.append("localized_capture_overflow")
        if not isolated:
            failures.append("localized_isolation_failed")
        return tuple(failures)
    if image is None:
        failures.append("localized_invalid_png")
        if overflow:
            failures.append("localized_capture_overflow")
        if not isolated:
            failures.append("localized_isolation_failed")
        return tuple(failures)
    width_pt, height_pt = _box_size(bounds_pt)
    if width_pt <= 0 or height_pt <= 0:
        failures.append("localized_unmeasurable")
    width, height = image.size
    expected_width = round(width_pt * LOCALIZED_CAPTURE_DENSITY)
    expected_height = round(height_pt * LOCALIZED_CAPTURE_DENSITY)
    density = min(
        width / width_pt if width_pt > 0 else 0.0,
        height / height_pt if height_pt > 0 else 0.0,
    )
    if density + _DENSITY_TOLERANCE < LOCALIZED_CAPTURE_DENSITY:
        failures.append("localized_low_density")
    if (
        abs(width - expected_width) > _PIXEL_ROUNDING_TOLERANCE
        or abs(height - expected_height) > _PIXEL_ROUNDING_TOLERANCE
    ):
        failures.append("localized_pixel_dimensions")
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    alpha_histogram = alpha.histogram()
    pixel_count = max(1, width * height)
    painted_pixels = pixel_count - alpha_histogram[0]
    paint_fraction = painted_pixels / pixel_count
    max_alpha = alpha.getextrema()[1]
    if painted_pixels == 0:
        failures.append("localized_blank_capture")
    if max_alpha < _EFFECTIVE_ALPHA_THRESHOLD or paint_fraction < _EFFECTIVE_PAINT_FRACTION:
        failures.append("localized_effectively_transparent")
    if contamination_fraction > 0:
        failures.append("localized_contaminated_capture")
    if overflow:
        failures.append("localized_capture_overflow")
    if not isolated:
        failures.append("localized_isolation_failed")
    if excluded_descendants < 0:
        failures.append("localized_invalid_descendant_count")
    return tuple(failures)


def audit_localized_capture(
    asset: bytes | bytearray | memoryview | str | Path | None,
    *,
    bounds_pt: Sequence[float],
    source_object: str | None = None,
    contamination_fraction: float = 0.0,
    overflow: bool = False,
    isolated: bool = True,
    excluded_descendants: int = 0,
    isolation_evidence: Mapping[str, Any] | None = None,
) -> LocalizedCaptureAudit:
    """Audit a PNG capture against fixed 2 px/pt and safety evidence.

    The function does not upscale, repair, or reinterpret a failed asset.  A
    caller that only has a low-density or composited screenshot receives a
    blocking audit, which keeps the existing picture lowering from publishing
    misleading bytes.
    """
    payload: bytes | None
    if asset is None:
        payload = None
    elif isinstance(asset, (str, Path)):
        try:
            payload = Path(asset).read_bytes()
        except (OSError, ValueError):
            payload = None
    else:
        payload = bytes(asset)

    image: Image.Image | None = None
    if payload:
        try:
            with Image.open(BytesIO(payload)) as opened:
                if opened.format != "PNG":
                    raise UnidentifiedImageError("localized fallback assets must be PNG")
                opened.load()
                image = opened.copy()
        except (OSError, UnidentifiedImageError, ValueError):
            image = None

    pixel_width, pixel_height = image.size if image is not None else (0, 0)
    width_pt, height_pt = _box_size(bounds_pt)
    expected_width = round(width_pt * LOCALIZED_CAPTURE_DENSITY)
    expected_height = round(height_pt * LOCALIZED_CAPTURE_DENSITY)
    density = min(
        pixel_width / width_pt if width_pt > 0 else 0.0,
        pixel_height / height_pt if height_pt > 0 else 0.0,
    )
    rgba = image.convert("RGBA") if image is not None else None
    if rgba is None:
        nonblank = False
        effectively_transparent = False
        paint_fraction = 0.0
    else:
        alpha = rgba.getchannel("A")
        histogram = alpha.histogram()
        pixel_count = max(1, pixel_width * pixel_height)
        paint_fraction = (pixel_count - histogram[0]) / pixel_count
        nonblank = histogram[0] < pixel_count
        effectively_transparent = (
            alpha.getextrema()[1] < _EFFECTIVE_ALPHA_THRESHOLD
            or paint_fraction < _EFFECTIVE_PAINT_FRACTION
        )
    failures = _capture_failure_codes(
        payload=payload,
        image=image,
        bounds_pt=bounds_pt,
        contamination_fraction=contamination_fraction,
        overflow=overflow,
        isolated=isolated,
        excluded_descendants=excluded_descendants,
    )
    return LocalizedCaptureAudit(
        source_object=source_object,
        asset_sha256=sha256(payload).hexdigest() if payload is not None else None,
        mime="image/png",
        pixel_width=pixel_width,
        pixel_height=pixel_height,
        expected_pixel_width=expected_width,
        expected_pixel_height=expected_height,
        density=density,
        required_density=LOCALIZED_CAPTURE_DENSITY,
        nonblank=nonblank,
        effectively_transparent=effectively_transparent,
        paint_fraction=paint_fraction,
        contamination_fraction=contamination_fraction,
        overflow=overflow,
        isolated=isolated,
        excluded_descendants=excluded_descendants,
        failure_codes=failures,
        isolation_evidence=dict(isolation_evidence or {}),
    )


__all__ = [
    "LOCALIZED_CAPTURE_DENSITY",
    "LOCALIZED_RASTERIZE_ATTRIBUTE",
    "LOCALIZED_RASTERIZE_TOKEN",
    "LocalizedCaptureAudit",
    "LocalizedPolicyFinding",
    "LocalizedRegion",
    "audit_localized_capture",
    "localized_source_path",
    "validate_localized_document",
    "validate_localized_geometry",
    "validate_localized_region_overlap",
]
