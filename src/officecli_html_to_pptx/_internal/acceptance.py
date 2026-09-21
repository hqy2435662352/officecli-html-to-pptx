"""Internal OfficeCLI acceptance helpers for the Algeria regression asset.

The V0.2 public product uses :mod:`officecli_html_to_pptx.application`; this
module is retained only for focused release-regression evidence and build
visual capture.  It is not a public command or API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import hashlib
import json
import os
import posixpath
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable, Mapping
from xml.etree import ElementTree
import zipfile

from PIL import Image

from .compare import create_comparison, screenshot_html_slides
from ..contract import (
    CONTRACT_VERSION,
    OFFICECLI_COMPATIBILITY_BASELINE,
    ContractReport,
    check_contract,
)
from .officecli_compiler import OfficeCLICompilationError, compile_officecli
from .charts import OfficeCLIChartAdapter
from ..runtime import PPTX_SCREENSHOT_DEFAULT_RENDER, officecli_pptx_screenshot_render

PASS = "PASS"
PENDING = "PENDING"
KNOWN_BASELINE_DIFFERENCE = "KNOWN_BASELINE_DIFFERENCE"
UNSUPPORTED_INPUT = "UNSUPPORTED_INPUT"
REGRESSION = "REGRESSION"

DEFAULT_AUTHOR_HTML = Path(
    os.environ.get(
        "HTML_TO_PPTX_ALGERIA_AUTHOR_HTML",
        r"D:\Opencodeworkspace\html-to-pptx\workspace\algeria\algeria\Algeria_AC_Product_Portfolio_20260906_v3_pptx.html",
    )
)

# These are intentionally keyed by the generated stable object name and issue
# subtype.  A total count is not enough to tell a known baseline from a new
# regression when object order changes.  They are the measured OfficeCLI
# 1.0.151 baseline for the current native compiler output; the B gate still
# requires every round-trip issue to be present in A.
KNOWN_BASELINE_ISSUES = frozenset(
    {
        (1, "slide-001-textbox-012", "text_overflow"),
        (8, "slide-008-textbox-024", "text_overflow"),
        (8, "slide-008-textbox-028", "text_overflow"),
    }
)

# A new issue in B is a regression unless it was explicitly reviewed as a
# stable tool-side allowance.  Keep this empty by default: an allowlist entry
# is an acceptance decision, not a convenient way to hide a compiler change.
STABLE_ISSUE_ALLOWLIST = frozenset()

_ISSUE_RE = re.compile(
    r"\[[A-Z]\d+\]\s+/slide\[(?P<slide>\d+)\]/"
    r"(?P<kind>[a-zA-Z]+)\[@id=(?P<id>\d+)\]:\s*(?P<message>.*)",
    re.I,
)
_PATH_LENGTH_RE = re.compile(
    r"^\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*(pt|emu|cm|mm|in)\s*$", re.I
)
_STRUCTURAL_ISSUE_MARKERS = (
    "schema",
    "shape_off_slide",
    "off-slide",
    "missing picture",
    "missing-picture",
    "table structure",
    "table-structure",
)

_TEXT_AGGREGATE_PROPERTIES = frozenset(
    {"font", "size", "color", "bold", "italic", "underline", "lineSpacing", "direction"}
)
_EMPTY_SHAPE_TEXT_PROPERTIES = frozenset(
    {
        "font",
        "font.latin",
        "font.ea",
        "size",
        "color",
        "bold",
        "italic",
        "underline",
        "lineSpacing",
        "direction",
        "margin",
    }
)

# The Algeria golden case is intentionally checked as a native-object contract,
# not merely by comparing whatever object inventory the compiler happened to
# produce.  These counts make a whole-slide raster fallback or a table rebuilt
# from one-shape-per-cell fail the authoritative gate.
_ALGERIA_EXPECTED_OBJECT_KIND_COUNTS = {
    "shape": 89,
    "textbox": 154,
    "picture": 18,
    "table": 9,
}
_ALGERIA_EXPECTED_TABLE_LAYOUT = {
    2: ((5, 8), (8, 8), (5, 8), (5, 8)),
    3: ((15, 4),),
    4: ((13, 5),),
    5: ((13, 5),),
    6: ((13, 5),),
    7: ((9, 5),),
}
_ALGERIA_EXPECTED_SLIDE_COUNT = 8
_ALGERIA_EXPECTED_ROW_COUNT = 86
_ALGERIA_EXPECTED_CELL_COUNT = 484
_LENGTH_VALUE_RE = re.compile(
    r"^-?(?:\d+(?:\.\d*)?|\.\d+)\s*(?:pt|emu|cm|mm|in|px)$", re.I
)
_HEX_VALUE_RE = re.compile(r"#[0-9a-f]{3,8}", re.I)
_NUMERIC_VALUE_RE = re.compile(r"^-?(?:\d+(?:\.\d*)?|\.\d+)$")


@dataclass(frozen=True)
class AcceptanceCheck:
    name: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class AcceptanceReport:
    status: str
    input_html: str
    output_dir: str
    checks: list[AcceptanceCheck] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "officecli_compatibility_baseline": OFFICECLI_COMPATIBILITY_BASELINE,
            "status": self.status,
            "input_html": self.input_html,
            "output_dir": self.output_dir,
            "checks": [check.as_dict() for check in self.checks],
            "findings": list(self.findings),
            "artifacts": dict(self.artifacts),
            "error": self.error,
        }

    def write(self) -> None:
        destination = Path(self.output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "acceptance-report.json").write_text(
            json.dumps(self.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        lines = [
            "# Algeria OfficeCLI Acceptance Report",
            "",
            f"- Status: `{self.status}`",
            f"- Contract: `{CONTRACT_VERSION}`",
            f"- OfficeCLI baseline: `{OFFICECLI_COMPATIBILITY_BASELINE}`",
            f"- Input: `{self.input_html}`",
            "",
            "## Checks",
            "",
        ]
        for check in self.checks:
            lines.append(f"- `{check.status}` **{check.name}** — {check.message}")
        if self.findings:
            lines.extend(["", "## Findings", ""])
            for finding in self.findings:
                lines.append(f"- `{finding.get('status', REGRESSION)}` {finding.get('message', finding)}")
        if self.artifacts:
            lines.extend(["", "## Artifacts", ""])
            for name, path in sorted(self.artifacts.items()):
                lines.append(f"- `{name}`: `{path}`")
        if self.error:
            lines.extend(["", "## Error", "", self.error])
        (destination / "acceptance-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _normal_text(value: Any, *, normalize_nbsp: bool = False) -> str:
    """Return text, optionally normalizing OfficeHTML's display-only NBSP."""
    text = str(value or "")
    return text.replace("\u00a0", " ") if normalize_nbsp else text


def _issue_subtype(message: str) -> str:
    lowered = message.lower()
    if "text overflow" in lowered:
        return "text_overflow"
    first = re.split(r"[:.]", lowered, maxsplit=1)[0]
    return re.sub(r"[^a-z0-9]+", "_", first).strip("_") or "unknown"


def issue_keys_from_officecli(
    issues: str,
    id_to_name: Mapping[tuple[int, int], str],
) -> list[dict[str, Any]]:
    """Extract stable issue identities from ``officecli view ... issues``."""
    keys: list[dict[str, Any]] = []
    for line in issues.splitlines():
        match = _ISSUE_RE.search(line)
        if match is None:
            continue
        slide = int(match.group("slide"))
        object_id = int(match.group("id"))
        object_identity = id_to_name.get((slide, object_id))
        if object_identity is None:
            object_identity = f"/slide[{slide}]/{match.group('kind')}[@id={object_id}]"
        keys.append(
            {
                "slide": slide,
                "object": object_identity,
                "subtype": _issue_subtype(match.group("message")),
            }
        )
    return keys


def _issue_tuple(item: Mapping[str, Any]) -> tuple[int, str, str]:
    return int(item["slide"]), str(item["object"]), str(item["subtype"])


def _points(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    match = _PATH_LENGTH_RE.fullmatch(str(value or ""))
    if match is None:
        raise ValueError(f"Unexpected OfficeCLI length: {value!r}")
    amount, unit = match.groups()
    number = float(amount)
    return {
        "pt": number,
        "emu": number / 12_700,
        "cm": number * 72 / 2.54,
        "mm": number * 72 / 25.4,
        "in": number * 72,
    }[unit.lower()]


def _approx_equal(left: Iterable[Any], right: Iterable[Any], tolerance: float) -> bool:
    left_values = list(left)
    right_values = list(right)
    return len(left_values) == len(right_values) and all(
        abs(float(a) - float(b)) <= tolerance for a, b in zip(left_values, right_values)
    )


def _normalized_line(value: Any) -> tuple[Any, ...] | str:
    """Normalize OfficeCLI's two equivalent line syntaxes.

    The compiler writes ``#RRGGBB:2pt`` while OfficeCLI commonly reads the
    same outline back as ``2pt solid #RRGGBB``.  Comparing the semantic tuple
    keeps the gate strict about width and color without making it depend on a
    serializer spelling.
    """
    text = str(value or "").strip()
    colors = _HEX_VALUE_RE.findall(text)
    lengths = re.findall(
        r"-?(?:\d+(?:\.\d*)?|\.\d+)\s*(?:pt|emu|cm|mm|in|px)",
        text,
        re.I,
    )
    if not colors or not lengths:
        return text
    color = colors[-1].upper()
    width = round(_points(lengths[-1]), 4)
    style = "solid" if "solid" in text.lower() or ":" in text else ""
    return width, style, color


def _normalized_property_value(key: str, value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(child_key): _normalized_property_value(str(child_key), child_value)
            for child_key, child_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return tuple(_normalized_property_value(key, item) for item in value)
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip()
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if key == "fontScale":
        try:
            scale = float(text)
            return round(scale / 1000 if abs(scale) > 100 else scale, 4)
        except ValueError:
            pass
    if key.lower() == "linespacing":
        spacing = re.fullmatch(r"(-?(?:\d+(?:\.\d*)?|\.\d+))x", lowered)
        if spacing:
            return round(float(spacing.group(1)), 4)
    if key == "line" or key.startswith("border."):
        normalized_line = _normalized_line(text)
        if isinstance(normalized_line, tuple):
            return normalized_line
    if "," in text and all(
        _LENGTH_VALUE_RE.fullmatch(part.strip()) for part in text.split(",")
    ):
        return tuple(round(_points(part.strip()), 4) for part in text.split(","))
    if _LENGTH_VALUE_RE.fullmatch(text):
        return round(_points(text), 4)
    if _NUMERIC_VALUE_RE.fullmatch(text):
        return round(float(text), 4)
    return _HEX_VALUE_RE.sub(lambda match: match.group(0).upper(), text)


def _font_scale_factor(properties: Mapping[str, Any] | None) -> float:
    """Return the effective text-size factor represented by ``fontScale``."""
    if not properties or properties.get("fontScale") is None:
        return 1.0
    try:
        raw_scale = float(str(properties["fontScale"]).strip())
    except (TypeError, ValueError):
        return 1.0
    if abs(raw_scale) > 100:
        raw_scale /= 1000
    return raw_scale / 100 if raw_scale > 0 else 1.0


def _paragraph_signature(
    paragraphs: Iterable[Mapping[str, Any]],
    *,
    run_size_scale: float = 1.0,
    normalize_nbsp: bool = False,
) -> tuple[Any, ...]:
    signature: list[Any] = []
    for paragraph in paragraphs:
        raw_spacing = paragraph.get("line_spacing")
        if raw_spacing is None:
            spacing = "normal"
        else:
            spacing = _normalized_property_value("lineSpacing", raw_spacing)
            if isinstance(spacing, (int, float)) and abs(float(spacing) - 1.33) <= 0.01:
                spacing = "normal"
        runs = []
        for run in paragraph.get("runs", []) or []:
            runs.append(
                (
                    _display_text(run.get("text", ""), normalize_nbsp=normalize_nbsp),
                    str(run.get("font_family", "")),
                    round(float(run.get("font_size_pt", 0.0)) * run_size_scale, 2),
                    bool(run.get("bold")),
                    bool(run.get("italic")),
                    str(run.get("underline", "none")),
                    _normalize_color(run.get("color")),
                )
            )
        signature.append(
            (
                _display_text(
                    paragraph.get("text", ""), normalize_nbsp=normalize_nbsp
                ),
                str(paragraph.get("align", "left")),
                spacing,
                round(float(paragraph.get("space_before_pt", 0.0)), 2),
                round(float(paragraph.get("space_after_pt", 0.0)), 2),
                str(paragraph.get("direction", "ltr")),
                tuple(runs),
            )
        )
    return tuple(signature)


def _line_spacing_equivalent(expected: Any, actual: Any) -> bool:
    if expected == actual:
        return True
    try:
        expected_value = float(expected)
        actual_value = float(actual)
    except (TypeError, ValueError):
        return False
    # OfficeCLI 1.0.151's HTML projection has one retained fixed-coordinate
    # line-spacing projection in the current Algeria golden case.  Keep it
    # explicit rather than accepting arbitrary spacing drift in A -> B.
    known_projections = ((1.6, 1.2),)
    return any(
        abs(expected_value - authored) <= 0.01
        and abs(actual_value - projected) <= 0.01
        for authored, projected in known_projections
    )


def _paragraphs_equivalent(
    expected: Iterable[Mapping[str, Any]],
    actual: Iterable[Mapping[str, Any]],
    *,
    allow_projection_defaults: bool = False,
    expected_properties: Mapping[str, Any] | None = None,
    allow_single_empty_projection: bool = False,
) -> bool:
    expected_list = list(expected)
    actual_list = list(actual)
    expected_signature = _paragraph_signature(
        expected_list,
        run_size_scale=(
            _font_scale_factor(expected_properties)
            if allow_projection_defaults
            else 1.0
        ),
        normalize_nbsp=allow_projection_defaults,
    )
    actual_signature = _paragraph_signature(
        actual_list, normalize_nbsp=allow_projection_defaults
    )
    if expected_signature == actual_signature:
        return True
    # OfficeHTML can materialize one empty default paragraph for an otherwise
    # empty shape.  That projection is safe to tolerate, but blank paragraph
    # positions are meaningful for explicit hard breaks and must not be
    # collapsed (for example, four authored paragraphs cannot become one).
    if allow_projection_defaults and len(expected_list) == len(actual_list) == 1:
        if all(
            not _display_text(
                paragraph.get("text", ""), normalize_nbsp=allow_projection_defaults
            ).strip()
            for paragraph in [expected_list[0], actual_list[0]]
        ):
            return True
    if allow_projection_defaults and allow_single_empty_projection:
        if not expected_list and len(actual_list) == 1 and not _display_text(
            actual_list[0].get("text", ""), normalize_nbsp=True
        ).strip():
            return True
        if not actual_list and len(expected_list) == 1 and not _display_text(
            expected_list[0].get("text", ""), normalize_nbsp=True
        ).strip():
            return True
    if not allow_projection_defaults or len(expected_signature) != len(actual_signature):
        return False
    # OfficeCLI's HTML projection omits paragraph spaceBefore/spaceAfter and
    # materializes a browser-normal line height as 1.33x.  A and B are still
    # checked strictly against their own OfficeCLI readbacks; this narrow
    # tolerance applies only to the explicit A -> OfficeHTML -> B comparison.
    for left, right in zip(expected_signature, actual_signature):
        if (
            left[:2] != right[:2]
            or not _line_spacing_equivalent(left[2], right[2])
            or left[5] != right[5]
            or left[6] != right[6]
        ):
            return False
        # OfficeHTML may omit authored paragraph spacing, which reads back as
        # zero.  The reverse direction (zero in the source becoming non-zero)
        # is a real round-trip change and must remain a regression.
        if not _projection_spacing_equivalent(left[3], right[3]):
            return False
        if not _projection_spacing_equivalent(left[4], right[4]):
            return False
    return True


def _projection_spacing_equivalent(expected: Any, actual: Any) -> bool:
    """Allow only authored non-zero spacing being omitted by OfficeHTML."""
    try:
        expected_value = float(expected)
        actual_value = float(actual)
    except (TypeError, ValueError):
        return expected == actual
    if abs(expected_value - actual_value) <= 0.01:
        return True
    return abs(expected_value) > 0.01 and abs(actual_value) <= 0.01


def _property_mismatches(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    has_paragraphs: bool = False,
    blank_paragraphs: bool = False,
    empty_text: bool = False,
    allow_projection_defaults: bool = False,
) -> dict[str, Any]:
    missing: dict[str, Any] = {}
    different: dict[str, Any] = {}
    for key, expected_value in expected.items():
        # Relationship ids are regenerated when OfficeCLI writes a new PPTX;
        # picture content/intrinsic metadata is compared separately below.
        if key == "relId":
            continue
        # Mixed text is authoritative at paragraph/run granularity.  OfficeCLI
        # intentionally omits aggregate size/color when runs disagree, so the
        # object-level property is not a loss of fidelity in that case.
        if has_paragraphs and key in _TEXT_AGGREGATE_PROPERTIES:
            continue
        # OfficeHTML does not preserve unused text defaults on empty shapes.
        # Their geometry/fill/line is still compared, while font/color/margin
        # defaults are intentionally projection-only for the A -> B check.
        if allow_projection_defaults and empty_text and key in _EMPTY_SHAPE_TEXT_PROPERTIES:
            continue
        if blank_paragraphs and key == "margin":
            continue
        if allow_projection_defaults and has_paragraphs and key in {
            "autoFit",
            "fontScale",
            "margin",
        }:
            continue
        if key not in actual:
            if (
                allow_projection_defaults
                and key in {"spaceAfter", "spaceBefore"}
                and _projection_spacing_equivalent(
                    _property_length_in_points(expected_value), 0.0
                )
            ):
                continue
            missing[key] = expected_value
            continue
        actual_value = actual[key]
        if (
            allow_projection_defaults
            and key in {"spaceAfter", "spaceBefore"}
            and _projection_spacing_equivalent(
                _property_length_in_points(expected_value),
                _property_length_in_points(actual_value),
            )
        ):
            continue
        if key in {"x", "y", "width", "height"}:
            try:
                if abs(_points(expected_value) - _points(actual_value)) <= 1.0:
                    continue
            except ValueError:
                pass
        if key == "size":
            try:
                if abs(_points(expected_value) - _points(actual_value)) <= 0.25:
                    continue
            except ValueError:
                pass
        if key == "colWidths":
            expected_widths = _normalized_property_value(key, expected_value)
            actual_widths = _normalized_property_value(key, actual_value)
            if (
                isinstance(expected_widths, tuple)
                and isinstance(actual_widths, tuple)
                and len(expected_widths) == len(actual_widths)
                and all(abs(float(left) - float(right)) <= 0.5 for left, right in zip(expected_widths, actual_widths))
            ):
                continue
        if _normalized_property_value(key, expected_value) != _normalized_property_value(
            key, actual_value
        ):
            different[key] = {"expected": expected_value, "actual": actual_value}
    return {"missing": missing, "different": different} if missing or different else {}


def _normalize_color(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _HEX_VALUE_RE.fullmatch(text)
    return match.group(0).upper() if match else text


def _property_length_in_points(value: Any) -> float:
    """Convert a spacing property to points for projection comparison."""
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return _points(value)
    except (TypeError, ValueError):
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return float("nan")


def _display_text(value: Any, *, normalize_nbsp: bool = False) -> str:
    """Return display text with an explicit OfficeHTML projection boundary."""
    return _normal_text(value, normalize_nbsp=normalize_nbsp)


def _officecli_properties(format_data: Mapping[str, Any]) -> dict[str, Any]:
    ignored = {"name", "id", "isTitle", "zorder", "preview", "childCount"}
    properties = {
        str(key): value
        for key, value in format_data.items()
        if str(key) not in ignored and not str(key).startswith("effective.")
    }
    if "font" not in properties and properties.get("font.latin"):
        properties["font"] = properties["font.latin"]
    if properties.get("line") and properties.get("lineWidth"):
        line = str(properties["line"])
        if _HEX_VALUE_RE.fullmatch(line.strip()):
            properties["line"] = f"{line}:{properties['lineWidth']}"
    return properties


def _officecli_run_manifest(run: Mapping[str, Any], fallback: Mapping[str, Any]) -> dict[str, Any]:
    format_data = run.get("format", {})
    font_family = (
        format_data.get("font.latin")
        or format_data.get("font")
        or fallback.get("font.latin")
        or fallback.get("font")
        or ""
    )
    size = format_data.get("size") or fallback.get("size")
    try:
        font_size = _points(size) if size else 0.0
    except ValueError:
        font_size = 0.0
    underline = str(format_data.get("underline", "none") or "none").lower()
    if underline in {"", "false", "none", "no"}:
        underline = "none"
    return {
        "text": str(run.get("text", "") or ""),
        "font_family": str(font_family),
        "font_size_pt": font_size,
        "bold": bool(format_data.get("bold", fallback.get("bold", False))),
        "italic": bool(format_data.get("italic", fallback.get("italic", False))),
        "underline": underline,
        "color": _normalize_color(format_data.get("color", fallback.get("color"))),
    }


def _officecli_paragraphs(node: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    fallback = node.get("format", {})
    paragraph_nodes = [
        child for child in node.get("children", []) or [] if child.get("type") == "paragraph"
    ]
    for paragraph in paragraph_nodes:
        runs: list[dict[str, Any]] = []
        text_parts: list[str] = []
        hard_break_offsets: list[int] = []
        visible_offset = 0
        has_hard_break = False
        for child in paragraph.get("children", []) or []:
            if child.get("type") == "run":
                run = _officecli_run_manifest(child, paragraph.get("format", {}))
                runs.append(run)
                run_text = str(run.get("text", "") or "")
                text_parts.append(run_text)
                visible_offset += len(run_text.encode("utf-16-le")) // 2
            elif child.get("type") in {"linebreak", "line-break", "br"}:
                text_parts.append("\v")
                hard_break_offsets.append(visible_offset)
                has_hard_break = True
        text = "".join(text_parts) if has_hard_break else str(
            paragraph.get("text", "") or ""
        )
        if not text:
            text = "".join(str(run.get("text", "")) for run in runs)
        paragraph_format = paragraph.get("format", {})
        try:
            space_before = _points(
                paragraph_format.get("spaceBefore", "0pt")
            )
        except ValueError:
            space_before = 0.0
        try:
            space_after = _points(
                paragraph_format.get("spaceAfter", "0pt")
            )
        except ValueError:
            space_after = 0.0
        result.append(
            {
                "text": text,
                "align": str(paragraph_format.get("align", fallback.get("align", "left"))),
                # A paragraph format is authoritative for paragraph-local
                # leading. Falling back to the text body's lineSpacing would
                # report the body's default as if it were explicit on a
                # paragraph whose source ratio is intentionally omitted.
                "line_spacing": paragraph_format.get("lineSpacing"),
                "space_before_pt": space_before,
                "space_after_pt": space_after,
                "direction": str(paragraph_format.get("direction", "ltr")),
                "runs": runs,
                "hard_break_offsets": hard_break_offsets,
            }
        )
    return result


def _xml_local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _officecli_cell_paragraphs(cell: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = str(cell.get("format", {}).get("txBodyRaw", "") or "")
    if not raw:
        return []
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return []
    fallback = cell.get("format", {})
    paragraphs: list[dict[str, Any]] = []
    for paragraph in [node for node in root.iter() if _xml_local_name(node.tag) == "p"]:
        paragraph_props = next(
            (node for node in paragraph if _xml_local_name(node.tag) == "pPr"), None
        )
        alignment = "left"
        if paragraph_props is not None:
            alignment = {
                "l": "left",
                "ctr": "center",
                "r": "right",
                "just": "justify",
            }.get(str(paragraph_props.attrib.get("algn", "l")), "left")
        line_spacing: str | None = None
        if paragraph_props is not None:
            line_spacing_node = next(
                (node for node in paragraph_props if _xml_local_name(node.tag) == "lnSpc"),
                None,
            )
            if line_spacing_node is not None:
                percentage = next(
                    (node for node in line_spacing_node if _xml_local_name(node.tag) == "spcPct"),
                    None,
                )
                points = next(
                    (node for node in line_spacing_node if _xml_local_name(node.tag) == "spcPts"),
                    None,
                )
                if percentage is not None:
                    try:
                        line_spacing = f"{float(percentage.attrib.get('val', '0')) / 100000:.3f}x"
                    except ValueError:
                        line_spacing = None
                elif points is not None:
                    try:
                        line_spacing = f"{float(points.attrib.get('val', '0')) / 100:.3f}pt"
                    except ValueError:
                        line_spacing = None
        if line_spacing is None:
            line_spacing = fallback.get(
                "linespacing", fallback.get("lineSpacing")
            )
        try:
            space_before = _points(fallback.get("spaceBefore", "0pt"))
        except ValueError:
            space_before = 0.0
        try:
            space_after = _points(fallback.get("spaceAfter", "0pt"))
        except ValueError:
            space_after = 0.0
        runs: list[dict[str, Any]] = []
        text_parts: list[str] = []
        hard_break_offsets: list[int] = []
        visible_offset = 0
        for run in [
            node
            for node in paragraph
            if _xml_local_name(node.tag) in {"r", "fld", "br"}
        ]:
            if _xml_local_name(run.tag) == "br":
                text_parts.append("\v")
                hard_break_offsets.append(visible_offset)
                continue
            run_props = next(
                (node for node in run if _xml_local_name(node.tag) == "rPr"), None
            )
            text = "".join(
                str(node.text or "")
                for node in run.iter()
                if _xml_local_name(node.tag) == "t"
            )
            if not text:
                continue
            font_family = ""
            color = None
            font_size = 0.0
            bold = False
            italic = False
            underline = "none"
            if run_props is not None:
                raw_size = run_props.attrib.get("sz")
                try:
                    font_size = float(raw_size or 0) / 100
                except ValueError:
                    font_size = 0.0
                bold = str(run_props.attrib.get("b", "")).lower() in {"1", "true"}
                italic = str(run_props.attrib.get("i", "")).lower() in {"1", "true"}
                raw_underline = str(run_props.attrib.get("u", "none") or "none")
                underline = "single" if raw_underline not in {"", "none"} else "none"
                latin = next(
                    (node for node in run_props if _xml_local_name(node.tag) == "latin"),
                    None,
                )
                if latin is not None:
                    font_family = str(latin.attrib.get("typeface", ""))
                srgb = next(
                    (node for node in run_props.iter() if _xml_local_name(node.tag) == "srgbClr"),
                    None,
                )
                if srgb is not None:
                    color = _normalize_color(f"#{srgb.attrib.get('val', '')}")
            runs.append(
                {
                    "text": text,
                    "font_family": font_family or str(fallback.get("font", "")),
                    "font_size_pt": font_size or _points(fallback.get("size", "0pt")),
                    "bold": bold,
                    "italic": italic,
                    "underline": underline,
                    "color": color or _normalize_color(fallback.get("color")),
                }
            )
            text_parts.append(text)
            visible_offset += len(text.encode("utf-16-le")) // 2
        paragraphs.append(
            {
                "text": "".join(text_parts),
                "align": alignment,
                "line_spacing": line_spacing,
                "space_before_pt": space_before,
                "space_after_pt": space_after,
                "direction": str(fallback.get("direction", "ltr")),
                "runs": runs,
                "hard_break_offsets": hard_break_offsets,
            }
        )
    return paragraphs


def _manifest_objects(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(item["name"]): item for item in manifest.get("objects", [])}


def _picture_metadata_mismatches(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare picture identity and fitting while allowing one explicit fallback.

    OfficeCLI may rasterize an SVG to PNG before embedding it.  That is the
    only permitted MIME/fingerprint change.  The fallback must still preserve
    the source image's aspect ratio; same-encoding metadata changes are never
    projection defaults.
    """
    missing: list[str] = []
    different: dict[str, Any] = {}
    for key in ("object_fit", "bounds_pt", "fitting"):
        if key not in expected:
            continue
        if key not in actual:
            missing.append(key)
            continue
        if key == "bounds_pt":
            if not _approx_equal(expected[key], actual[key], 1.0):
                different[key] = {"expected": expected[key], "actual": actual[key]}
        elif key == "fitting":
            if expected[key] != actual[key]:
                different[key] = {"expected": expected[key], "actual": actual[key]}
        elif (
            expected[key] != "unknown"
            and actual[key] not in {"unknown", expected[key]}
            and not (expected[key] in {"contain", "cover"} and actual[key] == "fill")
        ):
            different[key] = {"expected": expected[key], "actual": actual[key]}
    def picture_type(container: Mapping[str, Any]) -> str:
        return str(container.get("mime") or container.get("content_type") or "").lower()

    def valid_intrinsic_size(value: Any) -> tuple[float, float] | None:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return None
        try:
            width, height = (float(item) for item in value)
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return width, height

    for label, container in (("expected", expected), ("actual", actual)):
        if not picture_type(container):
            missing.append(f"{label}.mime")
        fingerprint = container.get("source_fingerprint") or container.get("content_fingerprint")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            missing.append(f"{label}.content_fingerprint")
        if valid_intrinsic_size(container.get("intrinsic_size")) is None:
            missing.append(f"{label}.intrinsic_size")
    expected_type = picture_type(expected)
    actual_type = picture_type(actual)
    if expected_type and actual_type and expected_type != actual_type:
        fallback_allowed = (expected_type, actual_type) == ("image/svg+xml", "image/png")
        if not fallback_allowed:
            different["mime"] = {"expected": expected_type, "actual": actual_type}

    expected_fingerprint = expected.get("content_fingerprint") or expected.get(
        "source_fingerprint"
    )
    actual_fingerprint = actual.get("content_fingerprint") or actual.get(
        "source_fingerprint"
    )
    if (
        isinstance(expected_fingerprint, str)
        and isinstance(actual_fingerprint, str)
        and re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint)
        and re.fullmatch(r"[0-9a-f]{64}", actual_fingerprint)
        and expected_fingerprint != actual_fingerprint
    ):
        # SVG-to-PNG rasterization is the one intentional OfficeCLI fallback.
        # A changed image in the same encoding, or an unrelated MIME change,
        # must fail instead of being accepted merely because both fingerprints
        # are well-formed.
        if (expected_type, actual_type) != ("image/svg+xml", "image/png"):
            different["content_fingerprint"] = {
                "expected": expected_fingerprint,
                "actual": actual_fingerprint,
            }

    expected_intrinsic = valid_intrinsic_size(expected.get("intrinsic_size"))
    actual_intrinsic = valid_intrinsic_size(actual.get("intrinsic_size"))
    if expected_intrinsic is not None and actual_intrinsic is not None:
        if expected_type == actual_type:
            if not _approx_equal(expected_intrinsic, actual_intrinsic, 0.5):
                different["intrinsic_size"] = {
                    "expected": list(expected_intrinsic),
                    "actual": list(actual_intrinsic),
                }
        elif (expected_type, actual_type) == ("image/svg+xml", "image/png"):
            # The compiler records the measured PNG fallback dimensions when
            # available.  Synthetic/legacy manifests without that field fall
            # back to the source SVG dimensions, which still catches a changed
            # fallback aspect ratio rather than accepting any PNG.
            fallback_intrinsic = valid_intrinsic_size(expected.get("fallback_intrinsic_size"))
            reference_intrinsic = fallback_intrinsic or expected_intrinsic
            expected_ratio = reference_intrinsic[0] / reference_intrinsic[1]
            actual_ratio = actual_intrinsic[0] / actual_intrinsic[1]
            if abs(expected_ratio - actual_ratio) > max(0.01, abs(expected_ratio) * 0.01):
                different["intrinsic_aspect_ratio"] = {
                    "expected": expected_ratio,
                    "actual": actual_ratio,
                }
    return {"missing": missing, "different": different} if missing or different else {}


def compare_manifests(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    known_issue_keys: Iterable[Mapping[str, Any] | tuple[int, str, str]] = (),
    allow_officehtml_projection_defaults: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    """Compare supported normalized fields without comparing source paths."""
    findings: list[dict[str, Any]] = []

    def mismatch(message: str, **details: Any) -> None:
        findings.append({"status": REGRESSION, "message": message, **details})

    if expected.get("slide_count") != actual.get("slide_count"):
        mismatch("slide count differs", expected=expected.get("slide_count"), actual=actual.get("slide_count"))
    if expected.get("slide_size_pt") and actual.get("slide_size_pt"):
        left_size = expected["slide_size_pt"]
        right_size = actual["slide_size_pt"]
        if not _approx_equal(
            [left_size.get("width"), left_size.get("height")],
            [right_size.get("width"), right_size.get("height")],
            1.0,
        ):
            mismatch("slide size differs", expected=left_size, actual=right_size)
    if expected.get("object_kind_counts") != actual.get("object_kind_counts"):
        mismatch(
            "object-kind counts differ",
            expected=expected.get("object_kind_counts"),
            actual=actual.get("object_kind_counts"),
        )

    expected_objects = _manifest_objects(expected)
    actual_objects = _manifest_objects(actual)
    for name in sorted(set(expected_objects) | set(actual_objects)):
        left = expected_objects.get(name)
        right = actual_objects.get(name)
        if left is None or right is None:
            mismatch("stable object identity is missing", object=name)
            continue
        if left.get("kind") != right.get("kind"):
            mismatch("object kind differs", object=name, expected=left.get("kind"), actual=right.get("kind"))
        if not _approx_equal(left.get("bounds_pt", ()), right.get("bounds_pt", ()), 1.0):
            mismatch("object bounds differ by more than 1pt", object=name)
        if left.get("kind") == "chart" and right.get("kind") == "chart":
            if right.get("native_kind") != "chart":
                mismatch(
                    "native chart kind differs",
                    object=name,
                    actual=right.get("native_kind"),
                )
            if left.get("chart", {}) != right.get("chart", {}):
                mismatch(
                    "chart semantics differ",
                    object=name,
                    expected=left.get("chart", {}),
                    actual=right.get("chart", {}),
                )
            expected_chart_seam = left.get("chart_seam", {}) or {}
            actual_chart_seam = right.get("chart_seam", {}) or {}
            if (
                "series_colors" in expected_chart_seam
                and expected_chart_seam.get("series_colors")
                != actual_chart_seam.get("series_colors")
            ):
                mismatch(
                    "authored chart series colors differ",
                    object=name,
                    expected=expected_chart_seam.get("series_colors"),
                    actual=actual_chart_seam.get("series_colors"),
                )
            continue
        if _normal_text(
            left.get("text"), normalize_nbsp=allow_officehtml_projection_defaults
        ) != _normal_text(
            right.get("text"), normalize_nbsp=allow_officehtml_projection_defaults
        ):
            mismatch("object text differs", object=name)
        property_details = _property_mismatches(
            left.get("properties", {}),
            right.get("properties", {}),
            has_paragraphs=bool(left.get("paragraphs") or right.get("paragraphs")),
            empty_text=(
                not _normal_text(
                    left.get("text"), normalize_nbsp=allow_officehtml_projection_defaults
                )
                and not _normal_text(
                    right.get("text"), normalize_nbsp=allow_officehtml_projection_defaults
                )
                and not left.get("paragraphs")
                and not right.get("paragraphs")
            ),
            blank_paragraphs=bool(
                (left.get("paragraphs") or right.get("paragraphs"))
                and all(
                    not str(paragraph.get("text", "")).strip()
                    for paragraph in [*(left.get("paragraphs", []) or []), *(right.get("paragraphs", []) or [])]
                )
            ),
            allow_projection_defaults=allow_officehtml_projection_defaults,
        )
        if property_details:
            mismatch(
                "object supported properties differ",
                object=name,
                expected=left.get("properties", {}),
                actual=right.get("properties", {}),
                details=property_details,
            )
        if not _paragraphs_equivalent(
            left.get("paragraphs", []),
            right.get("paragraphs", []),
            allow_projection_defaults=allow_officehtml_projection_defaults,
            expected_properties=left.get("properties", {}),
            allow_single_empty_projection=(
                allow_officehtml_projection_defaults
                and not _normal_text(
                    left.get("text"), normalize_nbsp=allow_officehtml_projection_defaults
                )
                and not _normal_text(
                    right.get("text"), normalize_nbsp=allow_officehtml_projection_defaults
                )
                and (
                    (
                        not left.get("paragraphs")
                        and len(right.get("paragraphs", []) or []) == 1
                    )
                    or (
                        not right.get("paragraphs")
                        and len(left.get("paragraphs", []) or []) == 1
                    )
                )
            ),
        ):
            mismatch(
                "object paragraph/run formatting differs",
                object=name,
                expected=left.get("paragraphs", []),
                actual=right.get("paragraphs", []),
            )
        left_metadata = left.get("metadata", {})
        right_metadata = right.get("metadata", {})
        if "picture" in left_metadata or "picture" in right_metadata:
            metadata_details = _picture_metadata_mismatches(
                left_metadata.get("picture", {}), right_metadata.get("picture", {})
            )
        else:
            metadata_details = (
                {"expected": left_metadata, "actual": right_metadata}
                if left_metadata != right_metadata
                else {}
            )
        if metadata_details:
            mismatch(
                "object metadata differs",
                object=name,
                expected=left_metadata,
                actual=right_metadata,
                details=metadata_details,
            )
        if left.get("kind") == "table" and right.get("kind") == "table":
            for field_name in ("rows", "columns"):
                if left.get(field_name) != right.get(field_name):
                    mismatch(f"table {field_name} differ", object=name)
            if left.get("normalized_merge_topology", []) != right.get(
                "normalized_merge_topology", []
            ):
                mismatch(
                    "table normalized merge topology differs",
                    object=name,
                    expected=left.get("normalized_merge_topology", []),
                    actual=right.get("normalized_merge_topology", []),
                )
            if not _approx_equal(left.get("column_widths_pt", ()), right.get("column_widths_pt", ()), 0.5):
                mismatch("table column widths differ by more than 0.5pt", object=name)
            if not _approx_equal(left.get("row_heights_pt", ()), right.get("row_heights_pt", ()), 0.5):
                mismatch("table row heights differ by more than 0.5pt", object=name)
            left_cells = left.get("cells", ())
            right_cells = right.get("cells", ())
            if len(left_cells) != len(right_cells):
                mismatch("table cell count differs", object=name)
            for index, (left_cell, right_cell) in enumerate(zip(left_cells, right_cells)):
                if not _approx_equal(
                    left_cell.get("bounds_pt", ()), right_cell.get("bounds_pt", ()), 1.0
                ):
                    mismatch("table cell bounds differ by more than 1pt", object=name, cell=index)
                if _normal_text(
                    left_cell.get("text"), normalize_nbsp=allow_officehtml_projection_defaults
                ) != _normal_text(
                    right_cell.get("text"), normalize_nbsp=allow_officehtml_projection_defaults
                ):
                    mismatch("table cell text differs", object=name, cell=index)
                cell_property_details = _property_mismatches(
                    left_cell.get("props", {}), right_cell.get("props", {})
                )
                if cell_property_details:
                    mismatch(
                        "table cell supported properties differ",
                        object=name,
                        cell=index,
                        details=cell_property_details,
                    )
                if not _paragraphs_equivalent(
                    left_cell.get("paragraphs", []),
                    right_cell.get("paragraphs", []),
                    allow_projection_defaults=allow_officehtml_projection_defaults,
                    allow_single_empty_projection=(
                        allow_officehtml_projection_defaults
                        and not _normal_text(
                            left_cell.get("text"),
                            normalize_nbsp=allow_officehtml_projection_defaults,
                        )
                        and not _normal_text(
                            right_cell.get("text"),
                            normalize_nbsp=allow_officehtml_projection_defaults,
                        )
                        and (
                            (
                                not left_cell.get("paragraphs")
                                and len(right_cell.get("paragraphs", []) or []) == 1
                            )
                            or (
                                not right_cell.get("paragraphs")
                                and len(left_cell.get("paragraphs", []) or []) == 1
                            )
                        )
                    ),
                ):
                    mismatch(
                        "table cell paragraph/run formatting differs",
                        object=name,
                        cell=index,
                        expected=left_cell.get("paragraphs", []),
                        actual=right_cell.get("paragraphs", []),
                    )

    known = {
        item if isinstance(item, tuple) else _issue_tuple(item)
        for item in known_issue_keys
    }
    status = REGRESSION if findings else (KNOWN_BASELINE_DIFFERENCE if known else PASS)
    return status, findings


class _AcceptanceToolError(RuntimeError):
    pass


def _run_officecli(*args: str | Path, json_output: bool = False) -> Any:
    command = ["officecli", *(str(arg) for arg in args)]
    if json_output:
        command.append("--json")
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _AcceptanceToolError(f"{' '.join(command)} could not run: {exc}") from exc
    if result.returncode != 0:
        raise _AcceptanceToolError(
            f"{' '.join(command)} failed with exit code {result.returncode}:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return json.loads(result.stdout) if json_output else result.stdout


def _walk(node: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield node
    for child in node.get("children", []) or []:
        yield from _walk(child)


def _children_by_slide(root: Mapping[str, Any]) -> list[list[Mapping[str, Any]]]:
    return [slide.get("children", []) for slide in root.get("children", []) or []]


def _pptx_picture_media(
    pptx_path: Path,
    slide_number: int,
    relationship_id: Any,
) -> dict[str, Any]:
    """Read the embedded media addressed by a picture relationship."""
    relationship_id = str(relationship_id or "")
    if not relationship_id:
        return {}
    rels_path = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
    try:
        with zipfile.ZipFile(pptx_path) as archive:
            relationships = ElementTree.fromstring(archive.read(rels_path))
            target = None
            for relationship in relationships:
                if relationship.attrib.get("Id") == relationship_id:
                    target = relationship.attrib.get("Target")
                    break
            if not target:
                return {}
            media_path = (
                posixpath.normpath(target.lstrip("/"))
                if target.startswith("/")
                else posixpath.normpath(posixpath.join("ppt/slides", target))
            )
            data = archive.read(media_path)
    except (KeyError, OSError, ElementTree.ParseError):
        return {}

    intrinsic_size = (0.0, 0.0)
    try:
        with Image.open(BytesIO(data)) as image:
            intrinsic_size = (float(image.width), float(image.height))
    except Exception:
        try:
            root = ElementTree.fromstring(data)
            view_box = str(root.attrib.get("viewBox", "")).replace(",", " ").split()
            if len(view_box) == 4:
                intrinsic_size = (float(view_box[2]), float(view_box[3]))
        except (ElementTree.ParseError, ValueError):
            pass
    return {
        "content_fingerprint": hashlib.sha256(data).hexdigest(),
        "intrinsic_size": list(intrinsic_size),
    }


def _officecli_picture_metadata(
    pptx_path: Path,
    slide_number: int,
    format_data: Mapping[str, Any],
    bounds: list[float],
) -> dict[str, Any]:
    media = _pptx_picture_media(pptx_path, slide_number, format_data.get("relId"))
    fitting = {
        str(key): value
        for key, value in format_data.items()
        if str(key).startswith("crop")
    }
    return {
        "picture": {
            "content_type": format_data.get("contentType"),
            "content_fingerprint": media.get("content_fingerprint"),
            "intrinsic_size": media.get("intrinsic_size", [0.0, 0.0]),
            # PowerPoint readback does not expose the originating CSS
            # object-fit token.  Keep the field explicit instead of silently
            # dropping it; crop props remain the native fitting evidence.
            "object_fit": "unknown",
            "bounds_pt": list(bounds),
            "fitting": fitting,
        }
    }


def _officecli_chart_parts(pptx_path: Path) -> dict[tuple[int, str], str]:
    """Map native chart names to their private Office Open XML chart parts."""
    chart_parts: dict[tuple[int, str], str] = {}
    relationship_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    try:
        with zipfile.ZipFile(pptx_path) as archive:
            slide_names = sorted(
                (
                    name
                    for name in archive.namelist()
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                ),
                key=lambda name: int(re.search(r"slide(\d+)", name).group(1)),
            )
            for slide_name in slide_names:
                match = re.search(r"slide(\d+)", slide_name)
                if match is None:
                    continue
                slide_number = int(match.group(1))
                slide_root = ElementTree.fromstring(archive.read(slide_name))
                rels_name = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
                relationships = ElementTree.fromstring(archive.read(rels_name))
                rel_targets = {
                    relationship.attrib.get("Id", ""): relationship.attrib.get("Target", "")
                    for relationship in relationships
                }
                for frame in (
                    node
                    for node in slide_root.iter()
                    if str(node.tag).rsplit("}", 1)[-1] == "graphicFrame"
                ):
                    chart_node = next(
                        (
                            node
                            for node in frame.iter()
                            if str(node.tag).rsplit("}", 1)[-1] == "chart"
                        ),
                        None,
                    )
                    if chart_node is None:
                        continue
                    name_node = next(
                        (
                            node
                            for node in frame.iter()
                            if str(node.tag).rsplit("}", 1)[-1] == "cNvPr"
                        ),
                        None,
                    )
                    name = str(
                        name_node.attrib.get("name", "")
                        if name_node is not None
                        else ""
                    )
                    relationship_id = chart_node.attrib.get(
                        f"{{{relationship_namespace}}}id",
                        chart_node.attrib.get("r:id", ""),
                    )
                    target = rel_targets.get(relationship_id, "")
                    if not name or not target:
                        continue
                    part = (
                        posixpath.normpath(
                            posixpath.join("ppt/slides", target)
                        )
                        if not target.startswith("/")
                        else posixpath.normpath(target.lstrip("/"))
                    )
                    chart_parts[(slide_number, name)] = f"/{part}"
    except (KeyError, OSError, ElementTree.ParseError, AttributeError):
        return {}
    return chart_parts


def _officecli_manifest(
    pptx_path: Path,
    expected_manifest: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[tuple[int, int], str]]:
    shallow = _run_officecli("get", pptx_path, "/", "--depth", "1", json_output=True)["data"]["results"][0]
    deep = _run_officecli("get", pptx_path, "/", "--depth", "5", json_output=True)["data"]["results"][0]
    slides = _children_by_slide(shallow)
    deep_by_name = {
        str(node.get("format", {}).get("name")): node
        for node in _walk(deep)
        if node.get("format", {}).get("name")
        and str(node.get("type", ""))
        in {"shape", "textbox", "picture", "table", "chart"}
    }
    chart_parts = _officecli_chart_parts(pptx_path)
    expected_by_name = {
        str(item.get("name")): item
        for item in (expected_manifest or {}).get("objects", []) or []
        if isinstance(item, Mapping) and item.get("name")
    }
    objects: list[dict[str, Any]] = []
    id_to_name: dict[tuple[int, int], str] = {}
    for slide_index, children in enumerate(slides, start=1):
        for child in children:
            kind = str(child.get("type", ""))
            if kind not in {"shape", "textbox", "picture", "table", "chart"}:
                continue
            format_data = child.get("format", {})
            name = str(format_data.get("name", ""))
            if not name:
                raise _AcceptanceToolError(f"OfficeCLI object on slide {slide_index} has no stable name")
            if format_data.get("id") is not None:
                id_to_name[(slide_index, int(format_data["id"]))] = name
            object_data: dict[str, Any] = {
                "kind": kind,
                "name": name,
                "source_slide": slide_index,
                "source_object": child.get("path", ""),
                "bounds_pt": [_points(format_data.get(key)) for key in ("x", "y", "width", "height")],
                "text": child.get("text", "") or "",
            }
            detailed = deep_by_name.get(name, child)
            detailed_format = detailed.get("format", format_data)
            if kind == "table":
                object_data.update(_officecli_table_manifest(detailed))
            elif kind == "chart":
                chart_part = chart_parts.get((slide_index, name))
                if chart_part is None:
                    raise _AcceptanceToolError(
                        f"OfficeCLI chart {name!r} on slide {slide_index} has no chart XML part"
                    )
                chart_xml = _run_officecli("raw", pptx_path, chart_part)
                object_data.update(
                    _officecli_chart_manifest(
                        detailed,
                        chart_xml,
                        expected=expected_by_name.get(name),
                    )
                )
            else:
                object_data["properties"] = _officecli_properties(detailed_format)
                object_data["paragraphs"] = _officecli_paragraphs(detailed)
                if kind == "picture":
                    object_data["metadata"] = _officecli_picture_metadata(
                        pptx_path, slide_index, detailed_format, object_data["bounds_pt"]
                    )
            objects.append(object_data)
    slide_width = _points(shallow.get("format", {}).get("slideWidth"))
    slide_height = _points(shallow.get("format", {}).get("slideHeight"))
    counts: dict[str, int] = {}
    for item in objects:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    return {
        "slide_count": len(slides),
        "slide_size_pt": {"width": slide_width, "height": slide_height},
        "object_kind_counts": counts,
        "objects": objects,
    }, id_to_name


def _officecli_chart_manifest(
    chart: Mapping[str, Any],
    chart_xml: str,
    *,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read only the material typed chart semantics from a native chart node."""
    expected_seam = expected.get("chart_seam", {}) if isinstance(expected, Mapping) else {}
    expected_colors = expected_seam.get("series_colors")
    if not isinstance(expected_colors, list):
        expected_colors = None
    readback = OfficeCLIChartAdapter.readback(
        chart,
        raw_xml=chart_xml,
        expected_series_colors=(tuple(str(item) for item in expected_colors) if expected_colors is not None else None),
    )
    return {
        "chart": readback.semantic_dict(),
        "chart_seam": readback.as_dict(),
        "native_kind": readback.native_kind,
    }


def _officecli_table_manifest(table: Mapping[str, Any]) -> dict[str, Any]:
    format_data = table.get("format", {})
    rows = int(format_data.get("rows", 0))
    columns = int(format_data.get("cols", 0))
    column_widths = [_points(item) for item in str(format_data.get("colWidths", "")).split(",") if str(item).strip()]
    row_nodes = [node for node in table.get("children", []) or [] if node.get("type") == "tr"]
    row_heights = [_points(row.get("format", {}).get("height")) for row in row_nodes]
    table_x = _points(format_data.get("x"))
    table_y = _points(format_data.get("y"))
    cells: list[dict[str, Any]] = []
    normalized_topology: list[dict[str, int]] = []
    for row_index, row in enumerate(row_nodes):
        cell_x = table_x
        for column_index, cell in enumerate(row.get("children", []) or []):
            if cell.get("type") != "tc":
                continue
            cell_format = cell.get("format", {})
            row_span = int(cell_format.get("rowspan") or 1)
            column_span = int(cell_format.get("colspan") or 1)
            is_horizontal_continuation = bool(
                cell_format.get("hmerge") or cell_format.get("hMerge")
            )
            is_vertical_continuation = bool(
                cell_format.get("vmerge") or cell_format.get("vMerge")
            )
            anchor = not is_horizontal_continuation and not is_vertical_continuation
            if anchor:
                normalized_topology.append(
                    {
                        "anchorRow": row_index + 1,
                        "anchorColumn": column_index + 1,
                        "rowSpan": row_span,
                        "columnSpan": column_span,
                    }
                )
            base_width = (
                column_widths[column_index] if column_index < len(column_widths) else 0.0
            )
            cell_width = (
                sum(column_widths[column_index : column_index + column_span])
                if anchor and column_span > 1
                else base_width
            )
            cell_height = row_heights[row_index] if row_index < len(row_heights) else 0.0
            cell_properties = {
                key: value
                for key, value in _officecli_properties(cell_format).items()
                if str(key).lower() not in {"hmerge", "vmerge"}
            }
            if "spaceBefore" in cell_properties:
                cell_properties["spacebefore"] = cell_properties.pop("spaceBefore")
            if "spaceAfter" in cell_properties:
                cell_properties["spaceafter"] = cell_properties.pop("spaceAfter")
            cells.append(
                {
                    "kind": "cell",
                    "name": (
                        f"{format_data.get('name', 'table')}-cell-"
                        f"r{row_index + 1:03d}-c{column_index + 1:03d}"
                    ),
                    "source_object": cell.get("path", ""),
                    "bounds_pt": [
                        cell_x,
                        table_y + sum(row_heights[:row_index]),
                        cell_width,
                        (
                            sum(row_heights[row_index : row_index + row_span])
                            if anchor and row_span > 1
                            else cell_height
                        ),
                    ],
                    "text": cell.get("text", "") or "",
                    "props": {
                        **cell_properties,
                        "linespacing": cell_format.get(
                            "linespacing", cell_format.get("lineSpacing")
                        ),
                        "text": cell.get("text", "") or "",
                    },
                    "paragraphs": _officecli_cell_paragraphs(cell),
                    "row": row_index + 1,
                    "column": column_index + 1,
                    "row_span": row_span if anchor else 1,
                    "column_span": column_span if anchor else 1,
                    "anchor": anchor,
                }
            )
            cell_x += base_width
    return {
        "properties": _officecli_properties(format_data),
        "rows": rows,
        "columns": columns,
        "column_widths_pt": column_widths,
        "row_heights_pt": row_heights,
        "normalized_merge_topology": normalized_topology,
        "cells": cells,
    }


def _validate_with_officecli(pptx_path: Path) -> str:
    return str(_run_officecli("validate", pptx_path))


def _project_to_officehtml(pptx_path: Path, html_path: Path) -> None:
    _run_officecli("view", pptx_path, "html", "--out", html_path)


def _screenshot_pptx(pptx_path: Path, output_dir: Path, slide_count: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots: list[Path] = []
    # The Comparison Image is Gate 3 evidence, so its PPTX panel must come from
    # a renderer that can draw the authored text.  OfficeCLI's default Windows
    # path is a native rasterizer that cannot compose a keycap cluster (U+20E3
    # comes out as a missing-glyph box) and draws monochrome emoji, which
    # presents a correct PPTX as broken content.  Its HTML projection renders
    # both correctly; ``doctor`` records which path the runtime in force uses.
    screenshot_render = officecli_pptx_screenshot_render()
    render_arguments: tuple[str, ...] = (
        ("--render", screenshot_render)
        if screenshot_render != PPTX_SCREENSHOT_DEFAULT_RENDER
        else ()
    )
    for slide_number in range(1, slide_count + 1):
        path = output_dir / f"slide_{slide_number:02d}.png"
        _run_officecli(
            "view",
            pptx_path,
            "screenshot",
            *render_arguments,
            "--page",
            str(slide_number),
            "--out",
            path,
        )
        if not path.is_file():
            # OfficeCLI exits 0 and writes nothing when it cannot find a headless
            # browser, so the process status carries no information here.  Name
            # the requirement, because this is the likeliest failure on a
            # non-Windows host and the raw message would be a dead end.
            raise _AcceptanceToolError(
                f"OfficeCLI did not create screenshot {path}. The screenshot "
                "path renders through a headless browser that OfficeCLI "
                "discovers itself; when none is discoverable it warns, exits 0 "
                "and writes no file. Activate the environment that owns the "
                "pinned Playwright Chromium so its executable is on PATH, or "
                "install a system Chromium, then retry."
            )
        screenshots.append(path)
    return screenshots


def _record_manifest_check(
    report: AcceptanceReport,
    name: str,
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    allow_officehtml_projection_defaults: bool = False,
) -> bool:
    status, findings = compare_manifests(
        expected,
        actual,
        allow_officehtml_projection_defaults=allow_officehtml_projection_defaults,
    )
    if findings:
        report.findings.extend(findings)
        report.checks.append(AcceptanceCheck(name, REGRESSION, "normalized manifest differs", {"findings": findings}))
        return False
    report.checks.append(AcceptanceCheck(name, PASS, "normalized manifest matches"))
    return True


def _record_algeria_native_structure_check(
    report: AcceptanceReport,
    name: str,
    manifest: Mapping[str, Any],
) -> bool:
    """Enforce the golden deck's native object inventory independently.

    A compiler-generated manifest can be internally self-consistent even when
    an implementation has silently flattened a slide or replaced a native
    table with hundreds of ordinary shapes.  This check therefore compares
    the OfficeCLI readback directly with the acceptance fixture's published
    native structure and keeps the table matrix distribution explicit.
    """
    objects = [
        item for item in manifest.get("objects", []) if isinstance(item, Mapping)
    ]
    counts: dict[str, int] = {}
    for item in objects:
        kind = str(item.get("kind", ""))
        counts[kind] = counts.get(kind, 0) + 1
    tables = [item for item in objects if item.get("kind") == "table"]
    layout_by_slide: dict[int, list[tuple[int, int]]] = {}
    for table in tables:
        slide = int(table.get("source_slide", 0))
        layout_by_slide.setdefault(slide, []).append(
            (int(table.get("rows", 0)), int(table.get("columns", 0)))
        )
    observed_layout = {
        slide: tuple(values) for slide, values in sorted(layout_by_slide.items())
    }
    expected_layout = {
        slide: tuple(values)
        for slide, values in sorted(_ALGERIA_EXPECTED_TABLE_LAYOUT.items())
    }
    slide_size = manifest.get("slide_size_pt", {})
    slide_width = float(slide_size.get("width", 0.0) or 0.0)
    slide_height = float(slide_size.get("height", 0.0) or 0.0)
    whole_slide_pictures = [
        str(item.get("name", ""))
        for item in objects
        if item.get("kind") == "picture"
        and _approx_equal(
            item.get("bounds_pt", ()),
            (0.0, 0.0, slide_width, slide_height),
            1.0,
        )
    ]
    shape_per_cell = [
        str(item.get("name", ""))
        for item in objects
        if item.get("kind") in {"shape", "textbox"}
        and "/tc[" in str(item.get("source_object", ""))
    ]
    row_count = sum(int(table.get("rows", 0)) for table in tables)
    cell_count = sum(len(table.get("cells", []) or []) for table in tables)
    observed = {
        "slide_count": int(manifest.get("slide_count", 0) or 0),
        "object_kind_counts": counts,
        "table_layout": observed_layout,
        "table_count": len(tables),
        "row_count": row_count,
        "cell_count": cell_count,
        "whole_slide_pictures": whole_slide_pictures,
        "shape_per_cell": shape_per_cell,
    }
    problems: list[str] = []
    if observed["slide_count"] != _ALGERIA_EXPECTED_SLIDE_COUNT:
        problems.append(
            f"slide count {observed['slide_count']} != {_ALGERIA_EXPECTED_SLIDE_COUNT}"
        )
    if counts != _ALGERIA_EXPECTED_OBJECT_KIND_COUNTS:
        problems.append("object-kind counts differ from the native golden inventory")
    if observed_layout != expected_layout:
        problems.append("native table row/column distribution differs")
    if row_count != _ALGERIA_EXPECTED_ROW_COUNT:
        problems.append(f"native table row count {row_count} != {_ALGERIA_EXPECTED_ROW_COUNT}")
    if cell_count != _ALGERIA_EXPECTED_CELL_COUNT:
        problems.append(f"native table cell count {cell_count} != {_ALGERIA_EXPECTED_CELL_COUNT}")
    if whole_slide_pictures:
        problems.append("a picture occupies the complete slide canvas")
    if shape_per_cell:
        problems.append("table cells were expanded into ordinary shapes or textboxes")
    if problems:
        finding = {
            "status": REGRESSION,
            "message": "Algeria native-object structure differs from the authoritative golden inventory",
            "problems": problems,
            "observed": observed,
            "expected": {
                "slide_count": _ALGERIA_EXPECTED_SLIDE_COUNT,
                "object_kind_counts": _ALGERIA_EXPECTED_OBJECT_KIND_COUNTS,
                "table_layout": expected_layout,
                "row_count": _ALGERIA_EXPECTED_ROW_COUNT,
                "cell_count": _ALGERIA_EXPECTED_CELL_COUNT,
                "whole_slide_pictures": [],
                "shape_per_cell": [],
            },
        }
        report.findings.append(finding)
        report.checks.append(
            AcceptanceCheck(
                name,
                REGRESSION,
                "native-object inventory does not match the authoritative golden structure",
                finding,
            )
        )
        return False
    report.checks.append(
        AcceptanceCheck(
            name,
            PASS,
            "native object counts, table distribution, and non-flattening checks passed",
            observed,
        )
    )
    return True


def _final_status(report: AcceptanceReport, issue_keys: Iterable[Mapping[str, Any]]) -> str:
    if report.error or any(check.status == REGRESSION for check in report.checks):
        return REGRESSION
    if any(check.status == PENDING for check in report.checks):
        return PENDING
    tuples = {_issue_tuple(item) for item in issue_keys}
    unexpected = tuples - KNOWN_BASELINE_ISSUES
    if unexpected:
        report.findings.extend(
            {
                "status": REGRESSION,
                "message": "unallowlisted OfficeCLI issue",
                "issue": {"slide": slide, "object": name, "subtype": subtype},
            }
            for slide, name, subtype in sorted(unexpected)
        )
        return REGRESSION
    if tuples & KNOWN_BASELINE_ISSUES:
        for slide, object_name, subtype in sorted(tuples & KNOWN_BASELINE_ISSUES):
            report.findings.append(
                {
                    "status": KNOWN_BASELINE_DIFFERENCE,
                    "message": "known baseline OfficeCLI issue",
                    "issue": {
                        "slide": slide,
                        "object": object_name,
                        "subtype": subtype,
                    },
                }
            )
        return KNOWN_BASELINE_DIFFERENCE
    return PASS


def _record_officecli_issue_gate(
    report: AcceptanceReport,
    issues: str,
    *,
    label: str = "PPTX A issue gate",
) -> None:
    lowered = issues.lower()
    forbidden = [marker for marker in _STRUCTURAL_ISSUE_MARKERS if marker in lowered]
    if forbidden:
        finding = {
            "status": REGRESSION,
            "message": "OfficeCLI reported a forbidden structural issue",
            "markers": forbidden,
        }
        report.findings.append(finding)
        report.checks.append(
            AcceptanceCheck(
                label,
                REGRESSION,
                "OfficeCLI structural issue is not allowlisted",
                finding,
            )
        )
    else:
        report.checks.append(
            AcceptanceCheck(label, PASS, "no forbidden structural OfficeCLI issue")
        )


def _record_issue_subset_gate(
    report: AcceptanceReport,
    issue_keys_a: Iterable[Mapping[str, Any]],
    issue_keys_b: Iterable[Mapping[str, Any]],
) -> None:
    issue_keys_a = list(issue_keys_a)
    issue_keys_b = list(issue_keys_b)
    issues_a = {_issue_tuple(item) for item in issue_keys_a}
    unexpected = issue_subset_regressions(issues_a, issue_keys_b)
    if unexpected:
        finding = {
            "status": REGRESSION,
            "message": "PPTX B introduced an OfficeCLI issue not present in PPTX A",
            "issues": unexpected,
        }
        report.findings.append(finding)
        report.checks.append(
            AcceptanceCheck(
                "PPTX B issue subset gate",
                REGRESSION,
                "PPTX B issues must be a subset of PPTX A or an explicit stable allowlist",
                finding,
            )
        )
        return
    report.checks.append(
        AcceptanceCheck(
            "PPTX B issue subset gate",
            PASS,
            "PPTX B issues are contained in PPTX A",
            {"a_count": len(issues_a), "b_count": len(issue_keys_b)},
        )
    )


def issue_subset_regressions(
    issue_keys_a: Iterable[Mapping[str, Any] | tuple[int, str, str]],
    issue_keys_b: Iterable[Mapping[str, Any] | tuple[int, str, str]],
) -> list[dict[str, Any]]:
    """Return B issue identities that are absent from A and not allowlisted."""
    issues_a = {
        item if isinstance(item, tuple) else _issue_tuple(item)
        for item in issue_keys_a
    }
    issues_b = {
        item if isinstance(item, tuple) else _issue_tuple(item)
        for item in issue_keys_b
    }
    return [
        {"slide": slide, "object": name, "subtype": subtype}
        for slide, name, subtype in sorted(
            issues_b - issues_a - STABLE_ISSUE_ALLOWLIST
        )
    ]


def _visual_review_payload(
    review: str | Path | Mapping[str, Any] | None,
    slide_count: int,
) -> dict[str, Any]:
    if review is None:
        source: Mapping[str, Any] = {}
    elif isinstance(review, Mapping):
        source = review
    else:
        review_path = Path(review).expanduser()
        if not review_path.is_file():
            raise _AcceptanceToolError(f"Visual review file does not exist: {review_path}")
        try:
            loaded = json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _AcceptanceToolError(f"Visual review file is not valid JSON: {review_path}") from exc
        if not isinstance(loaded, Mapping):
            raise _AcceptanceToolError("Visual review JSON must contain an object")
        source = loaded

    by_slide: dict[int, Mapping[str, Any]] = {}
    raw_slides = source.get("slides", [])
    if not isinstance(raw_slides, list):
        raise _AcceptanceToolError("Visual review 'slides' must be a list")
    for raw_slide in raw_slides:
        if not isinstance(raw_slide, Mapping):
            raise _AcceptanceToolError("Each visual review slide entry must be an object")
        try:
            slide_number = int(raw_slide.get("slide"))
        except (TypeError, ValueError) as exc:
            raise _AcceptanceToolError("Each visual review slide needs an integer 'slide'") from exc
        if slide_number in by_slide:
            raise _AcceptanceToolError(f"Visual review repeats slide {slide_number}")
        by_slide[slide_number] = raw_slide

    slides: list[dict[str, Any]] = []
    for slide_number in range(1, slide_count + 1):
        raw_slide = by_slide.get(slide_number, {})
        status = str(raw_slide.get("status", PENDING)).upper()
        if status not in {PASS, PENDING, "FAIL"}:
            raise _AcceptanceToolError(
                f"Visual review slide {slide_number} has unsupported status {status!r}"
            )
        findings = raw_slide.get("findings", [])
        if not isinstance(findings, list):
            raise _AcceptanceToolError(f"Visual review slide {slide_number} findings must be a list")
        normalized_findings = [dict(item) if isinstance(item, Mapping) else {"message": str(item)} for item in findings]
        slides.append(
            {
                "slide": slide_number,
                "status": status,
                "findings": normalized_findings,
                "notes": str(raw_slide.get("notes", "") or ""),
            }
        )

    gate = PASS
    for slide in slides:
        severities = {
            str(finding.get("severity", "")).lower()
            for finding in slide["findings"]
            if isinstance(finding, Mapping)
        }
        if slide["status"] == "FAIL" or severities & {"blocker", "major"}:
            gate = REGRESSION
            break
        if slide["status"] == PENDING:
            gate = PENDING
    return {
        "schema_version": 1,
        "gate": gate,
        "slides": slides,
        "notes": str(source.get("notes", "") or ""),
    }


def normalize_visual_review(
    review: str | Path | Mapping[str, Any] | None,
    slide_count: int,
) -> dict[str, Any]:
    """Normalize a visual review document and compute its Gate 3 status."""
    return _visual_review_payload(review, slide_count)


def _record_visual_review(
    report: AcceptanceReport,
    destination: Path,
    slide_count: int,
    review: str | Path | Mapping[str, Any] | None,
) -> str:
    payload = _visual_review_payload(review, slide_count)
    review_path = destination / "visual-review.json"
    review_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report.artifacts["visual-review"] = str(review_path)
    gate = str(payload["gate"])
    if gate == REGRESSION:
        report.findings.extend(
            {
                "status": REGRESSION,
                "message": "visual review reported a blocker or major finding",
                "slide": slide["slide"],
                "findings": slide["findings"],
            }
            for slide in payload["slides"]
            if slide["status"] == "FAIL"
            or any(
                str(finding.get("severity", "")).lower() in {"blocker", "major"}
                for finding in slide["findings"]
                if isinstance(finding, Mapping)
            )
        )
        message = "visual review contains a blocker or major finding"
    elif gate == PENDING:
        message = "visual review is pending for one or more slides"
    else:
        message = "visual review has one PASS result for every slide"
    report.checks.append(
        AcceptanceCheck(
            "Gate 3 visual review",
            gate,
            message,
            {"slide_count": slide_count, "review": str(review_path)},
        )
    )
    return gate


async def run_algeria_acceptance(
    author_html: str | Path = DEFAULT_AUTHOR_HTML,
    output_dir: str | Path = "acceptance-output/algeria",
    visual_review: str | Path | Mapping[str, Any] | None = None,
) -> AcceptanceReport:
    """Run the complete Algeria compilation, round-trip, inventory and visual gate."""
    input_path = Path(author_html).expanduser()
    destination = Path(output_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    report = AcceptanceReport(PASS, str(input_path), str(destination.resolve()))
    issue_keys: list[dict[str, Any]] = []
    issue_keys_b: list[dict[str, Any]] = []

    try:
        contract = check_contract(input_path, "author")
        report.checks.append(
            AcceptanceCheck(
                "author contract",
                UNSUPPORTED_INPUT if contract.blocked else PASS,
                "author profile is blocked" if contract.blocked else "author profile is compatible",
                contract.as_dict(),
            )
        )
        report.artifacts["author-contract"] = str(destination / "author-contract.json")
        Path(report.artifacts["author-contract"]).write_text(
            json.dumps(contract.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if contract.blocked:
            report.status = UNSUPPORTED_INPUT
            report.error = "Author HTML contains blocking contract findings."
            report.write()
            return report

        pptx_a = destination / "algeria-a.pptx"
        officehtml_a = destination / "algeria-a.officehtml.html"
        pptx_b = destination / "algeria-b.pptx"
        first = await compile_officecli(str(input_path), "author", str(pptx_a))
        report.artifacts["pptx-a"] = str(pptx_a)
        report.checks.append(AcceptanceCheck("author compilation", PASS, "OfficeCLI PPTX A was compiled"))

        _validate_with_officecli(pptx_a)
        report.checks.append(AcceptanceCheck("PPTX A validation", PASS, "OfficeCLI validation passed"))
        observed_a, id_to_name = _officecli_manifest(pptx_a)
        report.checks.append(
            AcceptanceCheck(
                "PPTX A OfficeCLI inventory",
                PASS,
                "OfficeCLI inventory collected",
                {"object_kind_counts": observed_a["object_kind_counts"]},
            )
        )
        _record_algeria_native_structure_check(
            report, "PPTX A authoritative native structure", observed_a
        )
        _record_manifest_check(report, "PPTX A normalized structure", first.manifest, observed_a)

        issues_a = str(_run_officecli("view", pptx_a, "issues"))
        issue_keys = issue_keys_from_officecli(issues_a, id_to_name)
        _record_officecli_issue_gate(report, issues_a)
        report.artifacts["pptx-a-issues"] = str(destination / "algeria-a.issues.txt")
        Path(report.artifacts["pptx-a-issues"]).write_text(issues_a, encoding="utf-8")

        _project_to_officehtml(pptx_a, officehtml_a)
        report.artifacts["officehtml-a"] = str(officehtml_a)
        report.checks.append(AcceptanceCheck("OfficeHTML projection", PASS, "OfficeCLI HTML projection was generated"))
        officehtml_contract = check_contract(officehtml_a, "officehtml")
        report.checks.append(
            AcceptanceCheck(
                "OfficeHTML contract",
                UNSUPPORTED_INPUT if officehtml_contract.blocked else PASS,
                "OfficeHTML projection is blocked" if officehtml_contract.blocked else "OfficeHTML projection is compatible",
                officehtml_contract.as_dict(),
            )
        )
        if officehtml_contract.blocked:
            report.status = UNSUPPORTED_INPUT
            report.error = "OfficeCLI HTML projection contains blocking contract findings."
            report.write()
            return report

        second = await compile_officecli(str(officehtml_a), "officehtml", str(pptx_b))
        report.artifacts["pptx-b"] = str(pptx_b)
        report.checks.append(AcceptanceCheck("OfficeHTML round-trip compilation", PASS, "PPTX B was compiled"))
        _validate_with_officecli(pptx_b)
        report.checks.append(AcceptanceCheck("PPTX B validation", PASS, "OfficeCLI validation passed"))
        observed_b, id_to_name_b = _officecli_manifest(pptx_b)
        _record_algeria_native_structure_check(
            report, "PPTX B authoritative native structure", observed_b
        )
        _record_manifest_check(report, "PPTX B normalized structure", second.manifest, observed_b)
        _record_manifest_check(
            report,
            "round-trip normalized manifest",
            first.manifest,
            second.manifest,
            allow_officehtml_projection_defaults=True,
        )
        issues_b = str(_run_officecli("view", pptx_b, "issues"))
        issue_keys_b = issue_keys_from_officecli(issues_b, id_to_name_b)
        _record_officecli_issue_gate(report, issues_b, label="PPTX B issue gate")
        _record_issue_subset_gate(report, issue_keys, issue_keys_b)
        report.artifacts["pptx-b-issues"] = str(destination / "algeria-b.issues.txt")
        Path(report.artifacts["pptx-b-issues"]).write_text(issues_b, encoding="utf-8")

        visuals = destination / "visuals"
        (visuals / "author-html").mkdir(parents=True, exist_ok=True)
        (visuals / "side-by-side").mkdir(parents=True, exist_ok=True)
        html_shots = await screenshot_html_slides(input_path, visuals / "author-html")
        pptx_shots = _screenshot_pptx(pptx_a, visuals / "pptx-a", first.slide_count)
        comparisons = create_comparison(html_shots, pptx_shots, visuals / "side-by-side")
        if (
            len(html_shots) != first.slide_count
            or len(pptx_shots) != first.slide_count
            or len(comparisons) != first.slide_count
        ):
            raise _AcceptanceToolError(
                "Visual acceptance requires one Author HTML, PPTX, and side-by-side "
                f"screenshot per slide; got {len(html_shots)}, {len(pptx_shots)}, "
                f"and {len(comparisons)} for {first.slide_count} slides."
            )
        report.artifacts["author-html-screenshots"] = str((visuals / "author-html").resolve())
        report.artifacts["pptx-screenshots"] = str((visuals / "pptx-a").resolve())
        report.artifacts["side-by-side-screenshots"] = str((visuals / "side-by-side").resolve())
        report.checks.append(
            AcceptanceCheck(
                "visual screenshots",
                PASS,
                f"generated {len(html_shots)} HTML, {len(pptx_shots)} PPTX and {len(comparisons)} comparison images",
            )
        )
        _record_visual_review(report, destination, first.slide_count, visual_review)
    except Exception as exc:
        report.error = str(exc)
        if isinstance(exc, OfficeCLICompilationError) and any(
            diagnostic.code.startswith(("unsupported_", "undecodable_", "invalid_"))
            for diagnostic in exc.diagnostics
        ):
            report.status = UNSUPPORTED_INPUT
        else:
            report.status = REGRESSION
    report.status = (
        report.status
        if report.status == UNSUPPORTED_INPUT
        else _final_status(report, [*issue_keys, *issue_keys_b])
    )
    report.write()
    return report


__all__ = [
    "PASS",
    "PENDING",
    "KNOWN_BASELINE_DIFFERENCE",
    "UNSUPPORTED_INPUT",
    "REGRESSION",
    "KNOWN_BASELINE_ISSUES",
    "STABLE_ISSUE_ALLOWLIST",
    "AcceptanceCheck",
    "AcceptanceReport",
    "compare_manifests",
    "issue_subset_regressions",
    "issue_keys_from_officecli",
    "normalize_visual_review",
    "run_algeria_acceptance",
]
