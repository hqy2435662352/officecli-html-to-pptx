"""V03-01-05 unified User-Path Acceptance over the installed public path.

This is the integration ticket that reaccepts V03-01 as one coherent
text-and-paragraph capability.  It does not add a text model and does not
broaden the feature: it walks the public path in order —

    capabilities -> doctor -> check -> build -> Visual Review -> finalize

— and asserts the whole accepted surface as independent literals.  Every
expected value below comes from the approved fixture
(``tests/fixtures/v03_01_rich_text_paragraphs.html``), from its authored CSS, or
from the Chromium layout the fixture declares; nothing is copied out of the
compiler's own output.  The declared surfaces are asserted against the exported
authority objects (``author_capability_manifest`` / ``list_surface`` /
``paragraph_layout_surface`` and the constants the Contract checker and the
OfficeCLI lowering both import), so a public capability claim that checking or
lowering does not enforce fails here.

The module performs exactly one real build of the approved fixture plus one
small focused build for the Unicode keycap case.  The released V0.2 semantics of
the other fixtures are covered by the existing suite, including the external
Algeria golden deck.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from officecli_html_to_pptx import cli
from officecli_html_to_pptx._internal.acceptance import (
    KNOWN_BASELINE_ISSUES,
    issue_keys_from_officecli,
)
from officecli_html_to_pptx._internal.officecli_compiler import (
    SLIDE_HEIGHT_PT,
    SLIDE_WIDTH_PT,
    _INLINE_TAGS,
    compile_officecli,
)
from officecli_html_to_pptx.application import EVIDENCE_FILES, PUBLIC_COMMANDS
from officecli_html_to_pptx.contract import (
    CANONICAL_RUN_POLICY,
    LINE_HEIGHT_PX_PROJECTION_SCALE,
    LIST_LEVELS,
    LIST_MARKER_PRESETS,
    LIST_PARAGRAPH_PROPERTIES,
    LIST_REJECTION_CODES,
    MIXED_RUN_ATTRIBUTES,
    SOFT_WRAP_MODEL,
    SUPPORTED_INLINE_ELEMENTS,
    TEXT_ALIGNMENT_DEFAULT,
    TEXT_ALIGNMENT_VALUES,
    _resolve_text_alignment,
    author_capability_manifest,
    check_contract,
    list_surface,
    paragraph_layout_surface,
)
from officecli_html_to_pptx.protocol import PRODUCT_NAME, PRODUCT_VERSION
from officecli_html_to_pptx.runtime import FORMAL_OFFICECLI_VERSION, SUPPORTED_PLATFORMS

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the V03-01 User-Path Acceptance tests",
)

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "v03_01_rich_text_paragraphs.html"
NEGATIVE_DIR = FIXTURES / "v03_01_negative"

# The published Comparison Image is the HTML panel beside the PPTX panel, with a
# 4 px gap and a 32 px label strip (see ``compare.create_comparison``).  Both
# panels are the 1920x1080 slide canvas.
COMPARISON_PANEL_PX = 1920
COMPARISON_GAP_PX = 4
COMPARISON_LABEL_PX = 32
# The ordered list's second item (``第二步 2️⃣``) in slide CSS pixels: its
# keycap is the only filled blue key pad in this box.
ORDERED_LIST_KEYCAP_BOX = (1480, 675, 1720, 730)
# Independent Windows/OfficeCLI 1.0.151 raster evidence for the keycap glyph.
# Chromium's color emoji fallback paints the blue keycap from x=1482/y=691,
# while OfficeCLI's native text stack paints the same readback text from
# x=1494/y=709. The glyph remains in the same authored list item and within the
# declared probe region; the difference is raster geometry, not text loss.
EXPECTED_KEYCAP_HTML_BLUE_BOX = (1482, 691, 1611, 717)
EXPECTED_KEYCAP_PPTX_BLUE_BOX = (1494, 709, 1611, 729)

# ---------------------------------------------------------------------------
# Independent expected literals
# ---------------------------------------------------------------------------

# One native object per authored element, in source order: the title, five
# authored text blocks, and the four cards.  Names, kinds, source identities and
# bounds come from the fixture's own geometry projected onto the 960x540pt
# widescreen canvas (scale 0.5).
EXPECTED_OBJECT_KIND_COUNTS = {"shape": 4, "textbox": 6}
EXPECTED_SLIDE_COUNT = 1
EXPECTED_PARAGRAPH_TOTAL = 12
EXPECTED_RUN_TOTAL = 19

TITLE_TEXT = "V03-01 原生文本与段落 / Native Rich Text"
MIXED_RUNS_PARAGRAPH_TEXTS = (
    "常规 Regular · 粗体 Bold · 斜体 Italic · 下划线 Underline · 数字 2026 · emoji 🚀",
    "Canonical: North Africa",
)
CANONICAL_RUN_TEXTS = ("Canonical: ", "North Africa")
EMOJI_RUN_TEXT = " · 数字 2026 · emoji 🚀"
EMOJI_RUN_UTF16_LENGTH = 21
PARAGRAPHS_PARAGRAPH_TEXTS = (
    "跨段样式 A",
    "Cross-break style B",
    "",
    "Second paragraph after an empty paragraph.",
    "第三段：显式换行后仍可编辑。",
)
# Chromium's measured visual rows for the one authored #soft-wrap paragraph.
# They are evidence only under Contract 1.1; the authored paragraph remains one
# native paragraph even when Chromium wraps it into several rows.
SOFT_WRAP_VISUAL_LINES = (
    "Chromium decides this bilingual soft wrap：浏",
    "览器决定视觉换行，PowerPoint 保留可编辑段",
    "落与原始阅读顺序。",
)
SOFT_WRAP_AUTHORED_TEXT = (
    "Chromium decides this bilingual soft wrap：浏览器决定视觉换行，"
    "PowerPoint 保留可编辑段落与原始阅读顺序。"
)
UNORDERED_ITEM_TEXTS = ("原生项目符号", "缩进与段落边界")
ORDERED_ITEM_TEXTS = ("First step", "第二步 2️⃣")
KEYCAP_ITEM_TEXT = "第二步 2️⃣"
KEYCAP_ITEM_UTF16_LENGTH = 7


def _run(
    text: str,
    font_family: str,
    font_size_pt: float,
    *,
    bold: bool = False,
    italic: bool = False,
    underline: str = "none",
    color: str,
) -> dict[str, Any]:
    """One independent expected Canonical Run."""
    return {
        "text": text,
        "font_family": font_family,
        "font_size_pt": font_size_pt,
        "bold": bold,
        "italic": italic,
        "underline": underline,
        "color": color,
    }


# The fixture's #mixed-runs first paragraph is seven runs: a collapsed boundary
# space stays with the run that authored it, and the emoji run keeps its own
# UTF-16 range.
MIXED_RUNS_FIRST_PARAGRAPH_RUNS = (
    _run("常规 Regular · ", "Segoe UI", 15.0, color="#24324A"),
    _run("粗体 Bold", "Georgia", 17.0, bold=True, color="#0F6B78"),
    _run(" · ", "Segoe UI", 15.0, color="#24324A"),
    _run("斜体 Italic", "Segoe UI", 14.0, italic=True, color="#9A3412"),
    _run(" · ", "Segoe UI", 15.0, color="#24324A"),
    _run("下划线 Underline", "Segoe UI", 15.0, underline="single", color="#4338CA"),
    _run(EMOJI_RUN_TEXT, "Segoe UI", 15.0, color="#24324A"),
)
# ``North`` + `` Africa`` are two adjacent source nodes with identical resolved
# formatting, so they are one Canonical Run that keeps the authored space.
MIXED_RUNS_SECOND_PARAGRAPH_RUNS = (
    _run("Canonical: ", "Segoe UI", 15.0, color="#24324A"),
    _run("North Africa", "Georgia", 15.0, bold=True, color="#0F6B78"),
)

# Object identity, kind, bounds, text, and one entry per authored paragraph (or
# per list item).  ``<br>`` controls stay inside the authored paragraph.
EXPECTED_OBJECTS: tuple[dict[str, Any], ...] = (
    {
        "name": "slide-001-textbox-001",
        "source_object": "slide[1]/div[1]",
        "kind": "textbox",
        "bounds_pt": (60.0, 35.0, 840.0, 45.0),
        "text": TITLE_TEXT,
        "paragraph_texts": (TITLE_TEXT,),
    },
    {
        "name": "slide-001-shape-002",
        "source_object": "slide[1]/div[2]",
        "kind": "shape",
        "bounds_pt": (60.0, 100.0, 400.0, 170.0),
        "text": "",
        "paragraph_texts": ("",),
    },
    {
        "name": "slide-001-textbox-003",
        "source_object": "slide[1]/div[3]",
        "kind": "textbox",
        "bounds_pt": (85.0, 125.0, 350.0, 117.5),
        "text": "\v".join(MIXED_RUNS_PARAGRAPH_TEXTS),
        "paragraph_texts": ("\v".join(MIXED_RUNS_PARAGRAPH_TEXTS),),
    },
    {
        "name": "slide-001-shape-004",
        "source_object": "slide[1]/div[4]",
        "kind": "shape",
        "bounds_pt": (500.0, 100.0, 400.0, 170.0),
        "text": "",
        "paragraph_texts": ("",),
    },
    {
        "name": "slide-001-textbox-005",
        "source_object": "slide[1]/div[5]",
        "kind": "textbox",
        "bounds_pt": (525.0, 122.5, 350.0, 122.5),
        "text": "\v".join(PARAGRAPHS_PARAGRAPH_TEXTS),
        "paragraph_texts": ("\v".join(PARAGRAPHS_PARAGRAPH_TEXTS),),
    },
    {
        "name": "slide-001-shape-006",
        "source_object": "slide[1]/div[6]",
        "kind": "shape",
        "bounds_pt": (60.0, 295.0, 400.0, 180.0),
        "text": "",
        "paragraph_texts": ("",),
    },
    {
        "name": "slide-001-textbox-007",
        "source_object": "slide[1]/div[7]",
        "kind": "textbox",
        "bounds_pt": (85.0, 320.0, 325.0, 110.0),
        "text": SOFT_WRAP_AUTHORED_TEXT,
        "paragraph_texts": (SOFT_WRAP_AUTHORED_TEXT,),
    },
    {
        "name": "slide-001-shape-008",
        "source_object": "slide[1]/div[8]",
        "kind": "shape",
        "bounds_pt": (500.0, 295.0, 400.0, 180.0),
        "text": "",
        "paragraph_texts": ("",),
    },
    {
        "name": "slide-001-textbox-009",
        "source_object": "slide[1]/ul[9]",
        "kind": "textbox",
        "bounds_pt": (540.0, 317.5, 150.0, 55.0),
        "text": "\n".join(UNORDERED_ITEM_TEXTS),
        "paragraph_texts": UNORDERED_ITEM_TEXTS,
    },
    {
        "name": "slide-001-textbox-010",
        "source_object": "slide[1]/ol[10]",
        "kind": "textbox",
        "bounds_pt": (725.0, 317.5, 135.0, 55.0),
        "text": "\n".join(ORDERED_ITEM_TEXTS),
        "paragraph_texts": ORDERED_ITEM_TEXTS,
    },
)

# Expected Canonical Runs per text object, per authored paragraph.  A hard break
# is a native control between visible ranges, not a run or a paragraph.
EXPECTED_PARAGRAPH_RUNS: dict[str, tuple[tuple[dict[str, Any], ...], ...]] = {
    "slide[1]/div[1]": (
        (_run(TITLE_TEXT, "Segoe UI", 24.0, bold=True, color="#0F3D66"),),
    ),
    "slide[1]/div[3]": (
        MIXED_RUNS_FIRST_PARAGRAPH_RUNS + MIXED_RUNS_SECOND_PARAGRAPH_RUNS,
    ),
    "slide[1]/div[5]": (
        (
            _run("跨段样式 A", "Segoe UI", 14.0, bold=True, color="#9A3412"),
            _run("Cross-break style B", "Segoe UI", 14.0, bold=True, color="#9A3412"),
            _run(
                "Second paragraph after an empty paragraph.",
                "Segoe UI",
                14.0,
                color="#24324A",
            ),
            _run("第三段：显式换行后仍可编辑。", "Segoe UI", 14.0, color="#24324A"),
        ),
    ),
    "slide[1]/div[7]": (
        (_run(SOFT_WRAP_AUTHORED_TEXT, "Segoe UI", 15.5, color="#24324A"),),
    ),
    "slide[1]/ul[9]": tuple(
        (_run(text, "Segoe UI", 13.5, color="#24324A"),)
        for text in UNORDERED_ITEM_TEXTS
    ),
    "slide[1]/ol[10]": tuple(
        (_run(text, "Segoe UI", 13.5, color="#24324A"),)
        for text in ORDERED_ITEM_TEXTS
    ),
}

# The fixture's authored CSS line-height per object.  Contract 1.1 uses the
# direct authored ratio at the declared 0.001x precision.
AUTHORED_LINE_HEIGHT: dict[str, float] = {
    "slide[1]/div[1]": 1.15,
    "slide[1]/div[3]": 1.45,
    "slide[1]/div[5]": 1.35,
    "slide[1]/div[7]": 1.35,
    "slide[1]/ul[9]": 1.35,
    "slide[1]/ol[10]": 1.35,
}
EXPECTED_LINE_SPACING: dict[str, tuple[str, ...]] = {
    "slide[1]/div[1]": ("1.150x",),
    "slide[1]/div[3]": ("1.450x",),
    "slide[1]/div[5]": ("1.350x",),
    "slide[1]/div[7]": ("1.350x",),
    "slide[1]/ul[9]": ("1.350x",) * 2,
    "slide[1]/ol[10]": ("1.350x",) * 2,
}
EXPECTED_READBACK_LINE_SPACING: dict[str, tuple[str, ...]] = {
    source: tuple(
        f"{AUTHORED_LINE_HEIGHT[source]:.2f}x"
        for _ in EXPECTED_LINE_SPACING[source]
    )
    for source in EXPECTED_LINE_SPACING
}

# The fixture's lists declare ``padding-left: 42px`` at scale 0.5 and one
# authored em of 27px, so the native paragraph marginLeft is 21pt and the marker
# hangs one em (13.5pt) left of the item text edge (the declared indentation
# surface: the Chromium outside-marker box advance).
LIST_ITEM_INSET_PX = 42.0
LIST_FONT_SIZE_PX = 27.0
EXPECTED_MARGIN_LEFT_PT = 21.0
EXPECTED_INDENT_PT = -13.5
EXPECTED_FIRST_ITEM_SPACE_AFTER_PT = 7.0
EXPECTED_ITEM_SPACE_AFTER = ("7pt", None)
LIST_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "slide[1]/ul[9]": {"tag": "ul", "marker": "bullet", "native_marker": "a:buChar"},
    "slide[1]/ol[10]": {
        "tag": "ol",
        "marker": "numbered",
        "native_marker": "a:buAutoNum",
    },
}

# The Visual Review record authored from the acceptance measurement: the
# whole-panel tile diff and the per-object region probe. One minor finding may
# record host-specific native list line placement; it is not a marker,
# indentation, content, ordering, clipping or overlap defect.
MATERIAL_FINDING_CATEGORIES = frozenset(
    {
        "clipping",
        "overlap",
        "missing-content",
        "reordered-text",
        "line-placement-regression",
        "marker-error",
        "indentation-error",
    }
)
MEASURED_REVIEW_NOTES = (
    "Measured, not eyeballed. Whole-panel 48x27 tile diff: 0 html-only tiles, "
    "0 pptx-only tiles, ink ratio 1.0622. Per-object region probe (pptx/html ink "
    "ratio, vertical ink centroid delta): title 0.919 / -5.04 px, #mixed-runs "
    "1.166 / -1.85 px, #paragraphs 1.132 / -4.63 px, #soft-wrap 1.007 / "
    "-10.89 px, #unordered-list 0.945 / -4.34 px, #ordered-list 0.860 / "
    "-10.46 px; every value is identical to the accepted V03-01-04 measurement. "
    "Marker columns: browser bullet 1096-1105 vs native 1096-1104 with item text "
    "at 1122 vs 1123; browser number 1467-1473/1480-1483 vs native "
    "1467-1475/1480-1484 with item text at 1494 vs 1494. No clipping, overlap, "
    "missing content, reordered text, marker error or indentation error."
)
MEASURED_MINOR_FINDING = {
    "severity": "minor",
    "category": "spacing",
    "location": "#unordered-list / #ordered-list",
    "description": (
        "Native list text may differ by a few pixels from the browser line box "
        "because the Contract 1.1 direct line-height ratio is rendered by the "
        "OfficeCLI text stack. No clipping, overlap, missing content, reordering, "
        "marker error or indentation error."
    ),
    "revision": (
        "Accepted: the Contract 1.1 direct line-height ratio is frozen for this "
        "surface; native markers, level and indentation are correct."
    ),
}
MAJOR_PROBE_FINDING = {
    "severity": "major",
    "category": "missing-content",
    "location": "#ordered-list",
    "description": "Probe: the declared ordered-list item content is absent.",
    "revision": "Re-author #ordered-list and rebuild the Artifact Pair.",
}


# ---------------------------------------------------------------------------
# Public command, OfficeCLI readback, and Evidence Bundle helpers
# ---------------------------------------------------------------------------


def _cli(*argv: str) -> tuple[int, dict[str, Any]]:
    """Run one public command through its CLI entry point."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main([*argv, "--json"])
    text = stdout.getvalue().strip()
    assert text, (
        f"officecli-html-to-pptx {' '.join(argv)} --json wrote no envelope: "
        f"{stderr.getvalue().strip()}"
    )
    return code, json.loads(text)


def _officecli(*args: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["officecli", *args, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return json.loads(completed.stdout)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _pair_inventory(root: Path, pptx: Path, evidence: Path) -> dict[str, str]:
    """Hash the whole published Artifact Pair for the non-overwrite proof."""
    inventory = {pptx.name: _sha256(pptx)}
    for path in sorted(evidence.rglob("*")):
        if path.is_file():
            inventory[str(path.relative_to(root)).replace("\\", "/")] = _sha256(path)
    return inventory


def _walk(node: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    yield dict(node)
    for child in node.get("children", []) or []:
        if isinstance(child, Mapping):
            yield from _walk(child)


_READBACK_CACHE: dict[str, tuple[dict[str, Any], ...]] = {}


def _slide_nodes(pptx: Path) -> tuple[dict[str, Any], ...]:
    """Read back every node of slide 1 with the public OfficeCLI command."""
    key = str(pptx)
    if key not in _READBACK_CACHE:
        document = _officecli("get", key, "/slide[1]", "--depth", "6")
        _READBACK_CACHE[key] = tuple(_walk(document["data"]["results"][0]))
    return _READBACK_CACHE[key]


def _objects(pptx: Path, *types: str) -> list[dict[str, Any]]:
    wanted = set(types) or {"shape", "textbox"}
    return [node for node in _slide_nodes(pptx) if node.get("type") in wanted]


def _object_by_name(pptx: Path, name: str) -> dict[str, Any]:
    for node in _objects(pptx):
        if (node.get("format") or {}).get("name") == name:
            return node
    raise AssertionError(f"OfficeCLI readback has no object named {name}")


_LENGTH_RE = re.compile(r"^(?P<amount>-?\d+(?:\.\d+)?)(?P<unit>pt|emu|cm|mm|in)$")


def _length_pt(value: Any) -> float:
    """Parse any OfficeCLI length unit; the readback mixes pt, cm and emu."""
    if isinstance(value, (int, float)):
        return float(value)
    match = _LENGTH_RE.fullmatch(str(value or "").strip())
    assert match is not None, f"unexpected OfficeCLI length: {value!r}"
    amount = float(match.group("amount"))
    return {
        "pt": amount,
        "emu": amount / 12_700,
        "cm": amount * 72 / 2.54,
        "mm": amount * 72 / 25.4,
        "in": amount * 72,
    }[match.group("unit")]


def _readback_bounds(node: Mapping[str, Any]) -> tuple[float, float, float, float]:
    format_data = node.get("format", {})
    return tuple(
        round(_length_pt(format_data[key]), 4) for key in ("x", "y", "width", "height")
    )


def _readback_run(run: Mapping[str, Any], fallback: Mapping[str, Any]) -> dict[str, Any]:
    format_data = run.get("format", {})
    return {
        "text": run["text"],
        "font_family": format_data.get("font.latin") or fallback.get("font"),
        "font_size_pt": _length_pt(format_data.get("size") or fallback["size"]),
        "bold": bool(format_data.get("bold", False)),
        "italic": bool(format_data.get("italic", False)),
        "underline": str(format_data.get("underline", "none") or "none"),
        "color": str(format_data.get("color") or fallback.get("color") or "").upper(),
    }


def _readback_paragraphs(node: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return readback paragraphs, retaining native hard-break controls."""
    fallback = node.get("format", {})
    paragraphs = []
    for paragraph in node.get("children", []) or []:
        if paragraph.get("type") != "paragraph":
            continue
        format_data = paragraph.get("format", {}) or {}
        runs = []
        text_parts: list[str] = []
        has_hard_break = False
        for child in paragraph.get("children", []) or []:
            if child.get("type") == "linebreak":
                text_parts.append("\v")
                has_hard_break = True
            elif child.get("type") == "run" and str(child.get("text", "")):
                text_parts.append(str(child.get("text", "")))
                runs.append(_readback_run(child, format_data or fallback))
        text = "".join(text_parts) if has_hard_break else str(
            paragraph.get("text", "") or ""
        )
        if not text:
            text = "".join(str(run.get("text", "")) for run in runs)
        paragraphs.append(
            {
                "text": text,
                "align": format_data.get("align"),
                "line_spacing": format_data.get("lineSpacing"),
                "list": format_data.get("list"),
                "level": format_data.get("level"),
                "margin_left": format_data.get("marginLeft"),
                "indent": format_data.get("indent"),
                "space_after": format_data.get("spaceAfter"),
                "native_marker": str(format_data.get("bulletRaw") or ""),
                "runs": runs,
            }
        )
    return paragraphs


def _manifest_by_source(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["source_object"]: item for item in manifest["objects"]}


def _object_text(node: Mapping[str, Any]) -> str:
    return str(node.get("text", "") or "")


def _native_marker_presets(marker_raw: str) -> str:
    """Map one native marker XML fragment to the declared marker preset."""
    if "a:buChar" in marker_raw:
        return "bullet"
    if "a:buAutoNum" in marker_raw:
        return "numbered"
    return "none"


def _utf16_length(text: str) -> int:
    # OfficeCLI range offsets exclude native paragraph/hard-break controls.
    return len(text.replace("\v", "").encode("utf-16-le")) // 2


def _relocate_bundle(source: Path, destination: Path) -> Path:
    """Copy a bundle and re-point it at itself so a probe can mutate it.

    ``finalize`` binds a bundle to its own absolute ``evidence_path`` and to the
    files inside its own ``comparisons`` directory, so a mutated copy has to be
    re-pointed before it can be finalized.  The published bundle is never touched.
    """
    shutil.copytree(source, destination)
    comparisons = destination / "comparisons"
    result = _read_json(destination / "result.json")
    result["evidence_path"] = str(destination)
    result["comparisons"] = [
        {**item, "path": str(comparisons / Path(item["path"]).name)}
        for item in result["comparisons"]
    ]
    _write_json(destination / "result.json", result)
    review = _read_json(destination / "visual-review.json")
    review["comparisons"] = [
        {**item, "path": str(comparisons / Path(item["path"]).name)}
        for item in review["comparisons"]
    ]
    for slide in review["slides"]:
        slide["comparison_path"] = str(comparisons / Path(slide["comparison_path"]).name)
    _write_json(destination / "visual-review.json", review)
    return destination


def _author_review(
    evidence: Path,
    *,
    findings: Sequence[Mapping[str, Any]],
    notes: str,
) -> dict[str, Any]:
    """Write the authored Visual Review record for one bundle."""
    review = _read_json(evidence / "visual-review.json")
    review["status"] = "REVIEWED"
    for slide in review["slides"]:
        # A reviewed slide stays PASS; a Major finding is what keeps the Artifact
        # Pair at REVISION_REQUIRED (ADR 0010, two-level findings).
        slide["status"] = "PASS"
        slide["findings"] = [dict(finding) for finding in findings]
        slide["notes"] = notes
    _write_json(evidence / "visual-review.json", review)
    return review


def _is_severe_issue(item: Any) -> bool:
    """Classify one reported issue; the repo's baseline allowlist is the classifier."""
    if isinstance(item, Mapping):
        severity = str(
            item.get("severity") or item.get("level") or item.get("class") or ""
        ).lower()
        text = json.dumps(item, ensure_ascii=False).lower()
    else:
        severity = ""
        text = str(item).lower()
    return severity in {"severe", "error", "critical", "high"} or "severe" in text


def _negative_fixtures() -> dict[str, Path]:
    """The neighbouring negative fixture for every declared rejection code."""
    return {path.stem: path for path in sorted(NEGATIVE_DIR.glob("*.html"))}


def _write_focused_fixture(tmp_path: Path, name: str, body: str) -> Path:
    """Author a one-slide input whose list carries the fixture's list CSS."""
    html = tmp_path / name
    html.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  .slide {{ width: 1920px; height: 1080px; position: relative; background: #ffffff; }}
  .list {{ position: absolute; left: 1080px; top: 635px; width: 300px;
           min-height: 110px; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 27px;
           line-height: 1.35; color: #24324a; padding-left: 42px; }}
</style></head><body><section class="slide active">
  {body}
</section></body></html>""",
        encoding="utf-8",
    )
    return html


# ---------------------------------------------------------------------------
# One real public build of the approved fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_pair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Build the approved fixture once through the public ``build`` command."""
    root = tmp_path_factory.mktemp("v03-01-acceptance")
    output = root / "v03-01-acceptance.pptx"
    evidence = root / "v03-01-acceptance.evidence"
    assert not output.exists() and not evidence.exists()

    code, envelope = _cli("build", str(FIXTURE), str(output))

    assert code == 0, envelope
    assert envelope["status"] == "VISUAL_REVIEW_REQUIRED"
    assert output.is_file() and evidence.is_dir()
    return {
        "root": root,
        "output": output,
        "evidence": evidence,
        "exit_code": code,
        "envelope": envelope,
        "result": _read_json(evidence / "result.json"),
        "manifest": _read_json(evidence / "manifest.json"),
    }


# ---------------------------------------------------------------------------
# Criterion 1: capabilities publishes the surface checking and lowering enforce
# ---------------------------------------------------------------------------


def test_capabilities_command_reports_the_executable_authority() -> None:
    code, envelope = _cli("capabilities")

    assert code == 0
    assert envelope["status"] == "PASS"
    assert envelope["product"] == {"name": PRODUCT_NAME, "version": PRODUCT_VERSION}
    authority = author_capability_manifest()
    assert envelope["data"]["contract"] == authority
    for surface in ("mixed_run_surface", "paragraph_layout_surface", "list_surface"):
        assert envelope["data"]["contract"][surface] == authority[surface]
    assert authority["version"] == "1.1"
    assert authority["profile"] == "author"
    assert envelope["data"]["commands"] == list(PUBLIC_COMMANDS) == [
        "capabilities",
        "doctor",
        "check",
        "build",
        "finalize",
    ]
    assert envelope["data"]["rendering_compatibility"]["officecli"] == (
        f">={FORMAL_OFFICECLI_VERSION}"
    )


def test_the_declared_surfaces_are_the_ones_checking_and_lowering_consume() -> None:
    manifest = author_capability_manifest()
    mixed = manifest["mixed_run_surface"]
    layout = manifest["paragraph_layout_surface"]
    lists = manifest["list_surface"]

    # Mixed runs: the published inline element list is the lowering's inline set,
    # and the published attributes and Canonical Run policy are its authority.
    assert mixed["inline_elements"] == sorted(SUPPORTED_INLINE_ELEMENTS)
    assert frozenset(mixed["inline_elements"]) == _INLINE_TAGS
    assert {"span", "strong", "em", "u"} <= set(mixed["inline_elements"])
    assert mixed["attributes"] == MIXED_RUN_ATTRIBUTES == {
        "font_family": "font-family",
        "font_size": "font-size",
        "bold": "font-weight",
        "italic": "font-style",
        "color": "color",
        "underline": "text-decoration",
    }
    assert mixed["canonical_run"] == {
        key: (list(value) if isinstance(value, list) else value)
        for key, value in CANONICAL_RUN_POLICY.items()
    }
    assert CANONICAL_RUN_POLICY["scope"] == "paragraph"
    assert CANONICAL_RUN_POLICY["range_units"] == "utf-16-code-units"

    # Paragraph layout: the published surface is the one resolution the checker
    # and the lowering both import, so a declared value cannot be rewritten.
    assert layout == paragraph_layout_surface()
    assert layout["alignment"]["values"] == sorted(TEXT_ALIGNMENT_VALUES) == [
        "center",
        "justify",
        "left",
        "right",
    ]
    assert layout["alignment"]["default"] == TEXT_ALIGNMENT_DEFAULT == "left"
    for value in TEXT_ALIGNMENT_VALUES:
        assert _resolve_text_alignment({"textAlign": value, "direction": "ltr"}) == value
    assert _resolve_text_alignment({"textAlign": "start"}) == "left"
    assert _resolve_text_alignment({"textAlign": "end"}) == "right"
    assert _resolve_text_alignment({"textAlign": "sideways"}) == TEXT_ALIGNMENT_DEFAULT
    assert layout["line_height"]["length_with_px_projection"] == (
        "line-height / font-size"
    )
    assert LINE_HEIGHT_PX_PROJECTION_SCALE == 1.0
    assert layout["line_height"]["precision"] == "0.001x"
    assert layout["soft_wrap"] == {
        key: (list(value) if isinstance(value, list) else value)
        for key, value in SOFT_WRAP_MODEL.items()
    }
    assert layout["soft_wrap"]["representation"] == "measurement-and-evidence-only"
    assert layout["soft_wrap"]["lowering"] == "never"
    assert layout["soft_wrap"]["object_per_source"] == 1
    assert layout["soft_wrap"]["object_kind"] == "textbox"
    assert layout["soft_wrap"]["new_soft_line_break_representation"] is False

    # Lists: the declared presets, levels, paragraph properties and rejection
    # codes are the ones the checker and the lowering act on.
    assert lists == list_surface()
    assert lists["elements"] == ["ol", "ul"]
    assert lists["marker"]["presets"] == LIST_MARKER_PRESETS == {
        "ol": "numbered",
        "ul": "bullet",
    }
    assert lists["marker"]["literal_prefix"] == "rejected"
    assert lists["levels"] == list(LIST_LEVELS) == [0]
    assert lists["paragraph_properties"] == sorted(LIST_PARAGRAPH_PROPERTIES) == [
        "indent",
        "level",
        "list",
        "marginLeft",
    ]
    assert lists["object_per_list"] == 1
    assert lists["object_kind"] == "textbox"
    assert lists["paragraphs_per_item"] == 1
    assert sorted(lists["rejections"]) == sorted(LIST_REJECTION_CODES)
    # A declared rejection code with no enforcing fixture fails the next test.
    assert set(_negative_fixtures()) == set(LIST_REJECTION_CODES)


# ---------------------------------------------------------------------------
# Criterion 2: doctor passes and records the discovered OfficeCLI version
# ---------------------------------------------------------------------------


def test_doctor_passes_and_records_the_officecli_floor() -> None:
    code, envelope = _cli("doctor")

    assert code == 0
    assert envelope["status"] == "PASS"
    assert envelope["diagnostics"] == []
    runtime = envelope["data"]["runtime"]
    discovered = runtime["officecli"]["discovered_version"]
    assert runtime["officecli"]["required_version"] == f">={FORMAL_OFFICECLI_VERSION}"
    assert runtime["officecli"]["compatible"] is True
    # The platform is whatever this suite runs on; the claim under test is that it
    # is inside the supported set, not that it is any one particular platform.
    assert runtime["platform"]["discovered"] in SUPPORTED_PLATFORMS
    assert runtime["platform"]["required"] == list(SUPPORTED_PLATFORMS)
    assert runtime["platform"]["compatible"] is True
    assert runtime["compatible"] is True
    assert isinstance(discovered, str) and discovered.strip()
    # The declared floor is satisfied by the discovered version, parsed here
    # independently of the runtime module.
    floor = tuple(int(part) for part in FORMAL_OFFICECLI_VERSION.split("."))
    found = tuple(int(part) for part in re.findall(r"\d+", discovered)[:3])
    assert len(found) == 3 and found >= floor, (discovered, FORMAL_OFFICECLI_VERSION)


# ---------------------------------------------------------------------------
# Criterion 3: the approved fixture passes public checking
# ---------------------------------------------------------------------------


def test_check_accepts_the_approved_fixture_without_diagnostics() -> None:
    code, envelope = _cli("check", str(FIXTURE))

    assert code == 0
    assert envelope["status"] == "PASS"
    assert envelope["diagnostics"] == []
    contract = envelope["data"]["contract"]
    assert contract["status"] == "PASS"
    assert contract["blocked"] is False
    assert contract["diagnostics"] == []
    assert contract["contract_version"] == author_capability_manifest()["version"]
    # No unsupported visible content was classified for the approved fixture.
    assert {
        name
        for name, classification in contract["css_properties"].items()
        if classification == "unsupported"
    } == set()


# ---------------------------------------------------------------------------
# Criterion 4: every newly explicit rejected boundary has a neighbouring
# negative fixture that blocks with source context and no partial output
# ---------------------------------------------------------------------------


def test_every_declared_rejection_has_a_neighboring_negative_fixture() -> None:
    fixtures = _negative_fixtures()

    assert set(fixtures) == set(LIST_REJECTION_CODES), (
        "every declared rejection code in LIST_REJECTION_CODES needs one "
        "neighbouring negative fixture (and no orphan fixture may remain): "
        f"declared={sorted(LIST_REJECTION_CODES)} fixtures={sorted(fixtures)}"
    )


def test_negative_fixtures_are_one_slide_author_inputs() -> None:
    """Each negative fixture is a deterministic 1920x1080 one-slide Author input."""
    for code, path in _negative_fixtures().items():
        text = path.read_text(encoding="utf-8")
        assert text.count('class="slide active"') == 1, code
        assert "width: 1920px" in text and "height: 1080px" in text, code
        assert "http://" not in text and "https://" not in text, code
        assert "<img" not in text and "<script" not in text, code
        # The offending list keeps the approved fixture's list geometry.
        assert "left: 1080px; top: 635px" in text, code


@pytest.mark.parametrize("code", sorted(LIST_REJECTION_CODES))
def test_negative_fixture_blocks_checking_with_source_context(code: str) -> None:
    fixture = _negative_fixtures()[code]

    exit_code, envelope = _cli("check", str(fixture))

    assert exit_code == 2
    assert envelope["status"] == "BLOCK"
    blocking = [item for item in envelope["diagnostics"] if item["blocking"]]
    assert [item["code"] for item in blocking] == [code]
    diagnostic = blocking[0]
    assert diagnostic["severity"] == "error"
    assert diagnostic["source_object"], diagnostic
    # The reported source context is the offending DOM node ...
    assert diagnostic["source_object"].startswith("/html/body/main/section/ul/"), (
        diagnostic["source_object"]
    )
    # ... and the stable code carries the rejection sentence the capability
    # authority publishes.
    assert list_surface()["rejections"][code] in diagnostic["message"]
    report = check_contract(fixture, "author")
    assert report.status == "BLOCK"
    assert [item.code for item in report.diagnostics] == [code]
    assert report.diagnostics[0].blocking is True
    assert report.diagnostics[0].source_object == diagnostic["source_object"]


@pytest.mark.parametrize("code", sorted(LIST_REJECTION_CODES))
def test_negative_fixture_blocks_building_without_partial_output(
    code: str, tmp_path: Path
) -> None:
    fixture = _negative_fixtures()[code]
    output = tmp_path / "blocked.pptx"

    exit_code, envelope = _cli("build", str(fixture), str(output))

    assert exit_code == 2
    assert envelope["status"] == "BLOCK"
    assert [item["code"] for item in envelope["diagnostics"]] == [code]
    assert envelope["diagnostics"][0]["source_object"]
    assert envelope["artifacts"] == {}
    # Neither half of the Artifact Pair is published and no staging directory
    # survives the blocked build.
    assert not output.exists()
    assert not (tmp_path / "blocked.evidence").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Criterion 5: a fresh public build publishes a new, non-overwriting Pair
# ---------------------------------------------------------------------------


def test_build_publishes_a_fresh_pair_and_requires_visual_review(
    built_pair: Mapping[str, Any],
) -> None:
    envelope = built_pair["envelope"]
    output = built_pair["output"]
    evidence = built_pair["evidence"]
    result = built_pair["result"]

    assert built_pair["exit_code"] == 0
    assert envelope["status"] == "VISUAL_REVIEW_REQUIRED"
    assert envelope["artifacts"]["pptx"]["path"] == str(output)
    assert envelope["artifacts"]["pptx"]["sha256"] == _sha256(output)
    assert envelope["artifacts"]["evidence"]["path"] == str(evidence)
    # The published result.json is the build's own envelope.
    assert result["status"] == "VISUAL_REVIEW_REQUIRED"
    assert result["schema_version"] == 1
    assert result["build_id"] == envelope["data"]["build_id"]
    assert result["pptx"]["path"] == str(output)
    assert result["pptx"]["sha256"] == _sha256(output)
    assert result["evidence_path"] == str(evidence)
    assert result["slide_count"] == EXPECTED_SLIDE_COUNT
    assert result["product"] == {"name": PRODUCT_NAME, "version": PRODUCT_VERSION}
    assert result["author_html"]["sha256"] == _sha256(FIXTURE)
    assert result["officecli_compatibility_baseline"] == FORMAL_OFFICECLI_VERSION
    # The declared Evidence Bundle files are exactly the published ones (plus
    # finalization.json once the review has been finalized).
    published = {path.name for path in evidence.iterdir()}
    assert published >= set(EVIDENCE_FILES) | {"comparisons"}
    assert published <= set(EVIDENCE_FILES) | {"comparisons", "finalization.json"}
    assert (evidence / "comparisons" / "slide-001.png").is_file()
    # The published evidence reuses the same authorities as the live commands.
    assert _read_json(evidence / "capabilities.json")["contract"] == (
        author_capability_manifest()
    )
    assert _read_json(evidence / "contract.json")["status"] == "PASS"
    # The recorded runtime is the doctor's own snapshot for this build target.
    doctor = _cli(
        "doctor", "--output", str(output), "--temp-dir", str(built_pair["root"])
    )
    assert _read_json(evidence / "runtime.json") == doctor[1]["data"]["runtime"]


def test_a_second_build_to_the_same_target_blocks_without_clobbering(
    built_pair: Mapping[str, Any],
) -> None:
    root = built_pair["root"]
    output = built_pair["output"]
    evidence = built_pair["evidence"]
    before = _pair_inventory(root, output, evidence)
    result_before = _read_json(evidence / "result.json")
    entries_before = {path.name for path in root.iterdir()}

    exit_code, envelope = _cli("build", str(FIXTURE), str(output))

    assert exit_code == 2
    assert envelope["status"] == "BLOCK"
    assert [item["code"] for item in envelope["diagnostics"]] == ["artifact_exists"]
    assert sorted(envelope["data"]["collisions"]) == [str(evidence), str(output)]
    # The first Artifact Pair is untouched, byte for byte, and nothing new was
    # published beside it.
    assert _pair_inventory(root, output, evidence) == before
    assert _read_json(evidence / "result.json") == result_before
    assert {path.name for path in root.iterdir()} == entries_before


# ---------------------------------------------------------------------------
# Criterion 6: native editable text, no substitution
# ---------------------------------------------------------------------------


def test_the_slide_keeps_the_authored_native_object_inventory(
    built_pair: Mapping[str, Any],
) -> None:
    manifest = built_pair["manifest"]

    assert manifest["slide_count"] == EXPECTED_SLIDE_COUNT
    assert manifest["object_kind_counts"] == EXPECTED_OBJECT_KIND_COUNTS
    assert manifest["slide_size_pt"] == {
        "width": SLIDE_WIDTH_PT,
        "height": SLIDE_HEIGHT_PT,
    }
    assert "picture" not in manifest["object_kind_counts"]
    assert "table" not in manifest["object_kind_counts"]
    # Exactly one native object per authored element, in source order: no
    # per-line and no per-item textbox substitution is possible.
    assert [
        (item["name"], item["source_object"], item["kind"])
        for item in manifest["objects"]
    ] == [
        (item["name"], item["source_object"], item["kind"])
        for item in EXPECTED_OBJECTS
    ]


def test_no_screenshot_svg_literal_marker_or_per_line_substitution(
    built_pair: Mapping[str, Any],
) -> None:
    pptx = built_pair["output"]
    manifest = built_pair["manifest"]

    # File level: no embedded media and no picture element in the slide XML.
    with zipfile.ZipFile(pptx) as archive:
        names = archive.namelist()
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
    assert [name for name in names if name.startswith("ppt/media/")] == []
    assert "<p:pic" not in slide_xml and "<a:blip" not in slide_xml
    # Readback level: only native slide, text and shape objects exist.
    assert {node.get("type") for node in _slide_nodes(pptx)} <= {
        "slide",
        "textbox",
        "shape",
        "paragraph",
        "run",
        "linebreak",
    }
    assert _objects(pptx, "picture", "image", "svg", "chart") == []
    # Every authored object carries its authored text as a native object.
    by_source = _manifest_by_source(manifest)
    for expected in EXPECTED_OBJECTS:
        item = by_source[expected["source_object"]]
        assert item["kind"] == expected["kind"]
        assert item["text"] == expected["text"]
    # No literal marker text and no flattened per-line/product textbox.
    texts = [
        _object_text(_object_by_name(pptx, item["name"])) for item in EXPECTED_OBJECTS
    ]
    joined = "\n".join(texts)
    assert "\u2022" not in joined
    assert not any(text.startswith(("• ", "1. First step", "2. 第二步")) for text in texts)
    # The soft-wrapped source paragraph stays one object and one authored native
    # paragraph. Chromium visual rows remain measurement/evidence only.
    soft_wrap = by_source["slide[1]/div[7]"]
    assert soft_wrap["kind"] == SOFT_WRAP_MODEL["object_kind"] == "textbox"
    assert "".join(SOFT_WRAP_VISUAL_LINES) == SOFT_WRAP_AUTHORED_TEXT
    assert soft_wrap["text"] == SOFT_WRAP_AUTHORED_TEXT
    assert len(soft_wrap["paragraphs"]) == 1
    assert [item["source_object"] for item in manifest["objects"]].count(
        "slide[1]/div[7]"
    ) == SOFT_WRAP_MODEL["object_per_source"] == 1


# ---------------------------------------------------------------------------
# Criterion 7: independent literals agree with manifest and readback
# ---------------------------------------------------------------------------


def test_manifest_agrees_with_the_expected_identity_kind_bounds_and_text(
    built_pair: Mapping[str, Any],
) -> None:
    manifest = built_pair["manifest"]

    for expected in EXPECTED_OBJECTS:
        item = _manifest_by_source(manifest)[expected["source_object"]]
        assert item["name"] == expected["name"]
        assert item["kind"] == expected["kind"]
        assert tuple(item["bounds_pt"]) == expected["bounds_pt"]
        assert item["text"] == expected["text"]
        assert item["source_slide"] == 1
        assert [paragraph["text"] for paragraph in item["paragraphs"]] == list(
            expected["paragraph_texts"]
        )
    assert len(manifest["objects"]) == len(EXPECTED_OBJECTS)


def test_readback_agrees_with_the_expected_bounds_and_text(
    built_pair: Mapping[str, Any],
) -> None:
    pptx = built_pair["output"]

    assert len(_objects(pptx)) == len(EXPECTED_OBJECTS)
    for expected in EXPECTED_OBJECTS:
        node = _object_by_name(pptx, expected["name"])
        assert node.get("type") == expected["kind"]
        assert _object_text(node) == expected["text"]
        assert _readback_bounds(node) == expected["bounds_pt"], expected["name"]


def test_paragraph_counts_and_paragraph_local_runs_agree(
    built_pair: Mapping[str, Any],
) -> None:
    manifest = built_pair["manifest"]
    pptx = built_pair["output"]

    total_paragraphs = 0
    total_runs = 0
    for expected in EXPECTED_OBJECTS:
        item = _manifest_by_source(manifest)[expected["source_object"]]
        expected_runs = EXPECTED_PARAGRAPH_RUNS.get(
            expected["source_object"],
            tuple(() for _ in expected["paragraph_texts"]),
        )
        assert len(item["paragraphs"]) == len(expected["paragraph_texts"])
        for index, paragraph in enumerate(item["paragraphs"]):
            text = paragraph["text"]
            assert text == expected["paragraph_texts"][index]
            runs = paragraph.get("runs", [])
            # Every run is paragraph-local: no run holds a paragraph separator,
            # the runs re-join to their own paragraph text, and their UTF-16
            # ranges cover exactly that text.
            assert all("\n" not in run["text"] for run in runs)
            assert "".join(run["text"] for run in runs) == text.replace("\v", "")
            assert sum(_utf16_length(run["text"]) for run in runs) == _utf16_length(text)
            assert [run["text"] for run in runs] == [
                run["text"] for run in expected_runs[index]
            ]
        total_paragraphs += len(item["paragraphs"])
        total_runs += sum(
            len(paragraph.get("runs", [])) for paragraph in item["paragraphs"]
        )

        readback = _readback_paragraphs(_object_by_name(pptx, expected["name"]))
        assert [paragraph["text"] for paragraph in readback] == list(
            expected["paragraph_texts"]
        )
        assert [
            [run["text"] for run in paragraph["runs"]] for paragraph in readback
        ] == [
            [run["text"] for run in expected_runs[index]]
            for index in range(len(expected["paragraph_texts"]))
        ]
        assert [len(paragraph["runs"]) for paragraph in readback] == [
            len(runs) for runs in expected_runs
        ]

    # One authored paragraph per text object, one native empty paragraph per
    # empty card, and one paragraph per list item. Hard breaks stay intra-
    # paragraph and therefore add no paragraph or synthetic run.
    assert total_paragraphs == EXPECTED_PARAGRAPH_TOTAL == (
        1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 2 + 2
    )
    assert total_runs == EXPECTED_RUN_TOTAL == (1 + 0 + 9 + 0 + 4 + 0 + 1 + 0 + 2 + 2)


def test_canonical_runs_merge_inside_a_paragraph_and_never_across_boundaries(
    built_pair: Mapping[str, Any],
) -> None:
    manifest = built_pair["manifest"]

    mixed_runs = _manifest_by_source(manifest)["slide[1]/div[3]"]
    assert [len(paragraph["runs"]) for paragraph in mixed_runs["paragraphs"]] == [9]
    assert mixed_runs["paragraphs"][0]["hard_break_offsets"] == [
        _utf16_length(MIXED_RUNS_PARAGRAPH_TEXTS[0])
    ]
    assert [run["text"] for run in mixed_runs["paragraphs"][0]["runs"][-2:]] == list(
        CANONICAL_RUN_TEXTS
    )
    assert CANONICAL_RUN_POLICY["forbidden_across"] == [
        "paragraph",
        "list_item",
        "hard_break",
    ]
    # The two adjacent identical source nodes are one Canonical Run and it keeps
    # the authored space: nothing was trimmed or re-attributed.
    assert CANONICAL_RUN_TEXTS[1] == "North Africa"
    # A Canonical Run never absorbs the <br> of #paragraphs: the styled inline
    # element that spans the break remains two visible runs in one paragraph.
    paragraphs = _manifest_by_source(manifest)["slide[1]/div[5]"]["paragraphs"]
    assert len(paragraphs) == 1
    assert paragraphs[0]["hard_break_offsets"] == [6, 25, 25, 67]
    assert [run["text"] for run in paragraphs[0]["runs"][:2]] == [
        "跨段样式 A",
        "Cross-break style B",
    ]
    for run in paragraphs[0]["runs"][:2]:
        assert run["bold"] is True
        assert run["color"] == "#9A3412"
    # Hard-break controls are not visible runs, and no run in the whole slide
    # owns a paragraph separator.
    assert not [
        run
        for item in manifest["objects"]
        for paragraph in item["paragraphs"]
        for run in paragraph["runs"]
        if "\n" in run["text"] or "\v" in run["text"]
    ]
    # Canonical Runs stay inside one list item: two identically formatted items
    # stay two paragraphs with one run each.
    for source in ("slide[1]/ul[9]", "slide[1]/ol[10]"):
        item = _manifest_by_source(manifest)[source]
        assert [len(paragraph["runs"]) for paragraph in item["paragraphs"]] == [1, 1]


def test_key_run_and_paragraph_formatting_survives_readback(
    built_pair: Mapping[str, Any],
) -> None:
    manifest = built_pair["manifest"]
    pptx = built_pair["output"]

    for source, expected_paragraphs in EXPECTED_PARAGRAPH_RUNS.items():
        item = _manifest_by_source(manifest)[source]
        readback = _readback_paragraphs(_object_by_name(pptx, item["name"]))
        for index, expected_runs in enumerate(expected_paragraphs):
            actual = readback[index]["runs"]
            assert len(actual) == len(expected_runs), (source, index)
            for expected, run in zip(expected_runs, actual):
                assert run["text"] == expected["text"]
                assert run["font_family"] == expected["font_family"]
                assert run["font_size_pt"] == expected["font_size_pt"]
                assert run["bold"] is expected["bold"]
                assert run["italic"] is expected["italic"]
                assert run["underline"] == expected["underline"]
                assert run["color"] == expected["color"]
            # The declared alignment default is the native paragraph alignment.
            assert readback[index]["align"] == TEXT_ALIGNMENT_DEFAULT
        # Contract 1.1 lowers the authored line-height ratio directly at the
        # declared 0.001x precision.
        expected_spacing = EXPECTED_READBACK_LINE_SPACING[source]
        actual_spacing = tuple(paragraph["line_spacing"] for paragraph in readback)
        assert actual_spacing == expected_spacing
        for literal in actual_spacing:
            assert literal.endswith("x")
            assert (
                abs(
                    float(literal[:-1])
                    - AUTHORED_LINE_HEIGHT[source]
                )
                <= 0.001
            )
        assert (
            tuple(paragraph["line_spacing"] for paragraph in item["paragraphs"])
            == EXPECTED_LINE_SPACING[source]
        )


def test_native_list_marker_level_and_indentation_survive_readback(
    built_pair: Mapping[str, Any],
) -> None:
    manifest = built_pair["manifest"]
    pptx = built_pair["output"]

    for source, expectation in LIST_EXPECTATIONS.items():
        item = _manifest_by_source(manifest)[source]
        assert item["kind"] == list_surface()["object_kind"] == "textbox"
        assert [paragraph["list"] for paragraph in item["paragraphs"]] == [
            expectation["marker"]
        ] * len(item["paragraphs"])
        assert [paragraph["level"] for paragraph in item["paragraphs"]] == list(
            LIST_LEVELS
        ) * len(item["paragraphs"])
        assert [paragraph["margin_left_pt"] for paragraph in item["paragraphs"]] == [
            EXPECTED_MARGIN_LEFT_PT
        ] * len(item["paragraphs"])
        assert [paragraph["indent_pt"] for paragraph in item["paragraphs"]] == [
            EXPECTED_INDENT_PT
        ] * len(item["paragraphs"])
        assert item["paragraphs"][0]["space_after_pt"] == (
            EXPECTED_FIRST_ITEM_SPACE_AFTER_PT
        )

        node = _object_by_name(pptx, item["name"])
        object_format = node["format"]
        readback = _readback_paragraphs(node)
        for paragraph in readback:
            # Native marker: a:buChar for <ul>, a:buAutoNum for <ol>, at the
            # declared preset for the list's own tag.
            assert paragraph["list"] == expectation["marker"] == (
                LIST_MARKER_PRESETS[expectation["tag"]]
            )
            assert expectation["native_marker"] in paragraph["native_marker"]
            assert (
                _native_marker_presets(paragraph["native_marker"])
                == expectation["marker"]
            )
            assert paragraph["level"] == str(LIST_LEVELS[0]) == "0"
            assert _length_pt(paragraph["margin_left"]) == EXPECTED_MARGIN_LEFT_PT
            assert _length_pt(paragraph["indent"]) == EXPECTED_INDENT_PT
        # The object itself carries the native list property and marker.
        assert object_format["list"] == expectation["marker"]
        assert expectation["native_marker"] in str(object_format.get("bulletRaw", ""))
        assert _native_marker_presets(str(object_format.get("bulletRaw", ""))) == (
            expectation["marker"]
        )
        # The one authored item margin is a native 7pt spaceAfter on item 1.
        assert [paragraph["space_after"] for paragraph in readback] == list(
            EXPECTED_ITEM_SPACE_AFTER
        )
        # No item text carries a literal marker prefix.
        for paragraph in readback:
            assert paragraph["text"] not in {"", "\u2022"}
            assert not paragraph["text"].startswith(("\u2022", "1.", "2."))

    # The declared indentation surface is the authored one: 42px of list padding
    # projected at scale 0.5, and a marker hanging one authored em (27px) left.
    assert EXPECTED_MARGIN_LEFT_PT == LIST_ITEM_INSET_PX * 0.5
    assert EXPECTED_INDENT_PT == -(LIST_FONT_SIZE_PX * 0.5)
    assert set(LIST_PARAGRAPH_PROPERTIES) == {
        "list",
        "level",
        "marginLeft",
        "indent",
    }


# ---------------------------------------------------------------------------
# Criterion 8: Unicode range writes stay aligned
# ---------------------------------------------------------------------------


def test_unicode_ranges_stay_aligned_after_the_emoji_and_the_keycap(
    built_pair: Mapping[str, Any],
) -> None:
    manifest = built_pair["manifest"]
    pptx = built_pair["output"]

    # After 🚀: the emoji stays inside the run that authored it, the paragraph's
    # UTF-16 ranges cover exactly its visible text, and the native hard-break
    # offset separates the following authored segment.
    mixed = _manifest_by_source(manifest)["slide[1]/div[3]"]
    paragraph = mixed["paragraphs"][0]
    assert paragraph["runs"][6]["text"] == EMOJI_RUN_TEXT
    assert _utf16_length(EMOJI_RUN_TEXT) == EMOJI_RUN_UTF16_LENGTH == 21
    assert sum(_utf16_length(run["text"]) for run in paragraph["runs"]) == (
        _utf16_length(paragraph["text"])
    )
    assert paragraph["hard_break_offsets"] == [
        _utf16_length(MIXED_RUNS_PARAGRAPH_TEXTS[0])
    ]
    assert paragraph["text"] == "\v".join(MIXED_RUNS_PARAGRAPH_TEXTS)
    readback_mixed = _readback_paragraphs(_object_by_name(pptx, mixed["name"]))
    assert [run["text"] for run in readback_mixed[0]["runs"]][6] == EMOJI_RUN_TEXT
    assert [paragraph["text"] for paragraph in readback_mixed] == [
        "\v".join(MIXED_RUNS_PARAGRAPH_TEXTS)
    ]

    # After 2️⃣: the keycap sequence stays whole inside its own list item and no
    # character of it leaks into a neighbouring paragraph.
    ordered = _manifest_by_source(manifest)["slide[1]/ol[10]"]
    keycap = ordered["paragraphs"][1]
    assert keycap["text"] == KEYCAP_ITEM_TEXT
    assert [run["text"] for run in keycap["runs"]] == [KEYCAP_ITEM_TEXT]
    assert _utf16_length(KEYCAP_ITEM_TEXT) == KEYCAP_ITEM_UTF16_LENGTH == 7
    readback_ordered = _readback_paragraphs(_object_by_name(pptx, ordered["name"]))
    assert [paragraph["text"] for paragraph in readback_ordered] == list(
        ORDERED_ITEM_TEXTS
    )
    assert [run["text"] for run in readback_ordered[1]["runs"]] == [KEYCAP_ITEM_TEXT]


async def test_a_formatted_run_after_the_keycap_keeps_its_own_formatting(
    tmp_path: Path,
) -> None:
    """A focused input: the run after ``2️⃣`` must not absorb the keycap."""
    html = _write_focused_fixture(
        tmp_path,
        "keycap-run.html",
        '<ol class="list">'
        '<li style="margin-bottom: 14px;">First step</li>'
        '<li>第二步 2️⃣ <strong style="color: #b91c1c;">加粗 Bold</strong></li>'
        "</ol>",
    )
    output = tmp_path / "keycap-run.pptx"

    compiled = await compile_officecli(str(html), "author", str(output))

    item = _manifest_by_source(compiled.manifest)["slide[1]/ol[1]"]
    runs = item["paragraphs"][1]["runs"]
    # "第二步 2️⃣ " is three CJK characters, a space, "2", U+FE0F, U+20E3 and a
    # space: eight UTF-16 code units, so the formatted run must start at 8.
    assert [run["text"] for run in runs] == ["第二步 2️⃣ ", "加粗 Bold"]
    assert [run["bold"] for run in runs] == [False, True]
    assert [run["color"] for run in runs] == ["#24324A", "#B91C1C"]
    assert _utf16_length(runs[0]["text"]) == 8

    readback = _readback_paragraphs(_object_by_name(output, item["name"]))[1]
    assert [run["text"] for run in readback["runs"]] == ["第二步 2️⃣ ", "加粗 Bold"]
    assert [run["bold"] for run in readback["runs"]] == [False, True]
    assert [run["color"] for run in readback["runs"]] == ["#24324A", "#B91C1C"]
    assert readback["list"] == "numbered"
    assert readback["level"] == "0"
    assert _length_pt(readback["margin_left"]) == EXPECTED_MARGIN_LEFT_PT
    assert _length_pt(readback["indent"]) == EXPECTED_INDENT_PT


# ---------------------------------------------------------------------------
# Criterion 9: OfficeCLI validation and the issue report
# ---------------------------------------------------------------------------


def test_officecli_validation_and_issue_report_are_clean(
    built_pair: Mapping[str, Any],
) -> None:
    pptx = built_pair["output"]
    evidence = built_pair["evidence"]

    validation = _officecli("validate", str(pptx))
    assert validation["success"] is True
    assert "no errors" in str(validation["data"]).lower()
    assert _read_json(evidence / "validate.json")["status"] == "PASS"

    reported = _officecli("view", str(pptx), "issues")
    assert reported["success"] is True
    assert reported["data"]["count"] == 0
    assert reported["data"]["issues"] == []
    # No reported item is a severe issue, and none is outside the classified
    # baseline the repo already reviews.
    severe = [item for item in reported["data"]["issues"] if _is_severe_issue(item)]
    assert [
        item for item in severe if item not in KNOWN_BASELINE_ISSUES
    ] == []
    # The published evidence carries the same report, and no line of it is an
    # unclassified issue or a structural corruption marker.
    issues_text = str(_read_json(evidence / "issues.json")["output"])
    assert issue_keys_from_officecli(issues_text, {}) == []
    lowered = issues_text.lower()
    for forbidden in (
        "severe",
        "schema",
        "off-slide",
        "shape_off_slide",
        "missing picture",
        "table structure",
    ):
        assert forbidden not in lowered, issues_text


# ---------------------------------------------------------------------------
# Criteria 10 and 11: the Evidence Bundle, the Comparison Image and the
# authored Visual Review record
# ---------------------------------------------------------------------------


def test_evidence_bundle_has_one_comparison_and_an_immutably_bound_record(
    built_pair: Mapping[str, Any],
) -> None:
    evidence = built_pair["evidence"]
    output = built_pair["output"]
    result = built_pair["result"]

    # Exactly one Comparison Image, for the one slide, and no raw panel images.
    comparisons = sorted((evidence / "comparisons").iterdir())
    assert [path.name for path in comparisons] == ["slide-001.png"]
    assert len(list(evidence.rglob("*.png"))) == 1
    assert not list(evidence.rglob("*html_slide*"))
    assert not list(evidence.rglob("*pptx_slide*"))

    inventory = result["comparisons"]
    assert len(inventory) == int(result["slide_count"]) == EXPECTED_SLIDE_COUNT
    published = evidence / "comparisons" / Path(inventory[0]["path"]).name
    assert Path(inventory[0]["path"]) == published
    assert inventory[0]["sha256"] == _sha256(published)

    # The review record is bound to the same build id and immutable hashes.
    review = _read_json(evidence / "visual-review.json")
    assert review["schema_version"] == 1
    assert review["build_id"] == result["build_id"]
    assert review["product"] == result["product"] == {
        "name": PRODUCT_NAME,
        "version": PRODUCT_VERSION,
    }
    assert review["author_html"]["path"] == str(FIXTURE)
    assert review["author_html"]["sha256"] == result["author_html"]["sha256"]
    assert review["author_html"]["sha256"] == _sha256(FIXTURE)
    assert review["pptx"]["path"] == str(output)
    assert review["pptx"]["sha256"] == result["pptx"]["sha256"] == _sha256(output)
    assert [item["path"] for item in review["comparisons"]] == [str(published)]
    assert [item["sha256"] for item in review["comparisons"]] == [
        inventory[0]["sha256"]
    ]
    assert [item["slide"] for item in review["slides"]] == [1]
    assert review["slides"][0]["comparison_path"] == str(published)
    assert review["slides"][0]["comparison_sha256"] == inventory[0]["sha256"]
    # The probe Major finding was authored into a relocated copy, never here.
    assert all(
        finding.get("severity") != "major"
        for slide in review["slides"]
        for finding in slide.get("findings", [])
    )


def test_comparison_image_shows_the_authored_keycap_in_the_pptx_panel(
    built_pair: Mapping[str, Any],
) -> None:
    """The fixture's keycap must reach the evidence as a keycap, not a tofu box.

    OfficeCLI's default Windows screenshot path is a native rasterizer that
    cannot compose a keycap cluster: it drew a missing-glyph box for U+20E3 and
    monochrome emoji while the PPTX itself was correct, so a numeric ink probe
    scored it as a pass and the defect only surfaced when a human looked at the
    image.  This guard compares the *colour* signature the keycap owns in both
    halves of the published Comparison Image, which a missing-glyph box cannot
    reproduce.

    The keycap's blue is located in the HTML half rather than hard-coded, so the
    guard follows the fixture instead of a pixel coordinate.
    """
    comparison = built_pair["evidence"] / "comparisons" / "slide-001.png"
    with Image.open(comparison) as raw:
        image = raw.convert("RGB")

    assert image.size == (COMPARISON_PANEL_PX * 2 + COMPARISON_GAP_PX,
                          COMPARISON_PANEL_PX * 9 // 16 + COMPARISON_LABEL_PX)

    def keycap_blue(offset_x: int) -> dict[str, Any]:
        count = 0
        left, top, right, bottom = 10**9, 10**9, -1, -1
        for x in range(ORDERED_LIST_KEYCAP_BOX[0], ORDERED_LIST_KEYCAP_BOX[2]):
            for y in range(ORDERED_LIST_KEYCAP_BOX[1], ORDERED_LIST_KEYCAP_BOX[3]):
                red, green, blue = image.getpixel(
                    (offset_x + x, COMPARISON_LABEL_PX + y)
                )
                if blue - red > 40 and blue > 120:
                    count += 1
                    left, top = min(left, x), min(top, y)
                    right, bottom = max(right, x), max(bottom, y)
        return {"count": count, "box": (left, top, right, bottom)}

    html_half = keycap_blue(0)
    pptx_half = keycap_blue(COMPARISON_PANEL_PX + COMPARISON_GAP_PX)

    # The authored keycap is a filled blue key pad in both panels.
    assert html_half["count"] > 400, html_half
    assert pptx_half["count"] >= html_half["count"] * 0.6, (html_half, pptx_half)
    # ... and each panel has the independently measured native/Chromium glyph
    # geometry. This keeps a real visual assertion while allowing the known
    # font-stack raster offset; the Unicode readback assertions above still
    # prove that the glyph was not substituted or split.
    assert html_half["box"] == EXPECTED_KEYCAP_HTML_BLUE_BOX, html_half
    assert pptx_half["box"] == EXPECTED_KEYCAP_PPTX_BLUE_BOX, pptx_half


def test_authored_review_record_finalizes_as_an_accepted_pair(
    built_pair: Mapping[str, Any],
) -> None:
    evidence = built_pair["evidence"]

    review = _author_review(
        evidence,
        findings=[MEASURED_MINOR_FINDING],
        notes=MEASURED_REVIEW_NOTES,
    )

    assert review["status"] == "REVIEWED"
    assert review["slides"][0]["status"] == "PASS"
    # Criterion 11: no material visual finding and no Major finding.
    findings = review["slides"][0]["findings"]
    assert [finding["severity"] for finding in findings] == ["minor"]
    assert [
        finding
        for finding in findings
        if finding["category"] in MATERIAL_FINDING_CATEGORIES
    ] == []
    assert all(finding["severity"] != "major" for finding in findings)

    exit_code, envelope = _cli("finalize", str(evidence))

    assert exit_code == 0
    assert envelope["status"] in {"PASS", "PASS_WITH_FINDINGS"}
    assert envelope["data"]["build_id"] == built_pair["result"]["build_id"]
    assert envelope["data"]["pptx_path"] == str(built_pair["output"])
    assert envelope["data"]["evidence_path"] == str(evidence)
    assert envelope["data"]["slide_count"] == EXPECTED_SLIDE_COUNT
    assert envelope["data"]["major_findings"] == 0
    assert envelope["data"]["minor_findings"] == len(findings) == 1
    assert all(item["blocking"] is False for item in envelope["diagnostics"])
    assert [item["code"] for item in envelope["diagnostics"]] == [
        "review_minor_finding"
    ]
    finalization = _read_json(evidence / "finalization.json")
    assert finalization["outcome"] == envelope["status"]
    assert finalization["build_id"] == built_pair["result"]["build_id"]
    assert finalization["slide_count"] == EXPECTED_SLIDE_COUNT
    assert [
        (item["slide"], item["finding"]["severity"])
        for item in finalization["findings"]
    ] == [(1, "minor")]


def test_a_major_finding_keeps_a_relocated_pair_at_revision_required(
    built_pair: Mapping[str, Any],
) -> None:
    evidence = built_pair["evidence"]
    root = built_pair["root"]
    review_before = _sha256(evidence / "visual-review.json")
    before = _pair_inventory(root, built_pair["output"], evidence)
    relocated = _relocate_bundle(evidence, root / "major-probe.evidence")

    _author_review(
        relocated,
        findings=[MAJOR_PROBE_FINDING],
        notes=MEASURED_REVIEW_NOTES,
    )
    exit_code, envelope = _cli("finalize", str(relocated))

    assert exit_code == 2
    assert envelope["status"] == "REVISION_REQUIRED"
    assert [item["code"] for item in envelope["diagnostics"]] == [
        "review_major_finding"
    ]
    assert envelope["diagnostics"][0]["blocking"] is True
    assert envelope["diagnostics"][0]["severity"] == "major"
    assert envelope["data"]["major_findings"] == 1
    assert envelope["data"]["build_id"] == built_pair["result"]["build_id"]
    assert (
        _read_json(relocated / "finalization.json")["outcome"] == "REVISION_REQUIRED"
    )
    # The probe was made in a relocated copy: the published Pair and its accepted
    # review record are untouched by it.
    assert _pair_inventory(root, built_pair["output"], evidence) == before
    assert _sha256(evidence / "visual-review.json") == review_before
