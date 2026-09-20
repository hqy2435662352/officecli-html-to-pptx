"""Public-seam tests for V03-01 top-level HTML lists as Native List Textboxes.

Every expectation below is an independent literal taken from the accepted
fixture (``tests/fixtures/v03_01_rich_text_paragraphs.html``), from a freshly
authored input, or from the browser layout the fixture declares.  Nothing is
derived from the compiler's own output.

The slice under test is Recorded Decision
``docs/adr/0027-map-html-lists-to-one-native-textbox.md``: one top-level
``ul``/``ol`` becomes exactly one Native List Textbox, every direct ``li``
becomes exactly one Native List Paragraph inside it, and the bullet or
automatic number, the list level, and the indentation are native PowerPoint
paragraph properties (never literal marker text and never one textbox per
item).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

import pytest

from officecli_html_to_pptx import application, cli
from officecli_html_to_pptx._internal.officecli_compiler import compile_officecli
from officecli_html_to_pptx.contract import (
    LIST_MARKER_PRESETS,
    LIST_REJECTION_CODES,
    author_capability_manifest,
    check_contract,
)

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the V03-01 list tests",
)

FIXTURE = Path(__file__).parent / "fixtures" / "v03_01_rich_text_paragraphs.html"

# The fixture's ``#unordered-list`` is the ninth top-level slide child and
# ``#ordered-list`` the tenth (four cards, five text boxes, then the two lists).
UNORDERED_SOURCE = "slide[1]/ul[9]"
ORDERED_SOURCE = "slide[1]/ol[10]"
LIST_SOURCES = (UNORDERED_SOURCE, ORDERED_SOURCE)

# The authored fixture's 1920x1080 CSS canvas is the 960x540pt widescreen
# canvas at scale 0.5, so the measured list rects project as:
#   ul: left 1080px top 635px width 300px height 86.875px
#   ol: left 1450px top 635px width 270px height 86.875px
UNORDERED_BOUNDS_PT = (540.0, 317.5, 150.0, 43.4375)
ORDERED_BOUNDS_PT = (725.0, 317.5, 135.0, 43.4375)

# One Native List Paragraph per direct ``li``, in source order, with the item's
# own content only: no ``•``, no ``1.``/``2.`` prefix is content.
UNORDERED_ITEM_TEXTS = ("原生项目符号", "缩进与段落边界")
ORDERED_ITEM_TEXTS = ("First step", "第二步 2️⃣")
LIST_ITEM_TEXTS = {
    UNORDERED_SOURCE: UNORDERED_ITEM_TEXTS,
    ORDERED_SOURCE: ORDERED_ITEM_TEXTS,
}
LIST_OBJECT_TEXT = {
    UNORDERED_SOURCE: "原生项目符号\n缩进与段落边界",
    ORDERED_SOURCE: "First step\n第二步 2️⃣",
}
LIST_BOUNDS_PT = {
    UNORDERED_SOURCE: UNORDERED_BOUNDS_PT,
    ORDERED_SOURCE: ORDERED_BOUNDS_PT,
}
# The fixture's list items declare 27px at scale 0.5 and a direct 1.35
# line-height ratio under Contract 1.1.
ITEM_FONT_SIZE_PT = 13.5
ITEM_COLOR = "#24324A"
ITEM_LINE_SPACING = "1.350x"
ITEM_READBACK_LINE_SPACING = "1.35x"

# The fixture's lists declare ``padding-left: 42px``: the item boxes start 42px
# (21pt) right of the list's border box, which is the native paragraph left
# margin.  ``indent`` hangs the marker box one em to the left of the item's text
# edge — the Chromium outside-marker advance this ticket calibrated against
# (measured: the HTML disc marker spans x 1096..1105 and the item text starts at
# x 1122; the ordered marker spans x 1465..1483 and its item text starts at
# x 1492).
LIST_INDENT_EM = 1.0
EXPECTED_MARGIN_LEFT_PT = 21.0
EXPECTED_INDENT_PT = -13.5

# ``margin-bottom: 14px`` on the fixture's first item is a 7pt native
# ``spaceAfter``: the second item box starts at 317.5pt + 18.21875pt + 7pt.
# Chromium's used line box for these items is 36.4375px (1.35 x 27px rounded to
# the 1/64px layout unit), so the item pitch is 25.21875pt.
FIRST_ITEM_SPACE_AFTER_PT = 7.0
SECOND_ITEM_SPACE_AFTER_PT = 0.0
ITEM_LINE_BOX_PT = 18.21875
EXPECTED_ITEM_TOP_PT = (317.5, 342.71875)

# Before this ticket the fixture produced four item textboxes; after it the two
# lists are two textboxes, so the slide has six text-bearing objects and the
# four authored cards stay four shapes.
EXPECTED_OBJECT_KIND_COUNTS = {"shape": 4, "textbox": 6}
EXPECTED_TEXT_OBJECT_COUNT = 6
EXPECTED_SHAPE_COUNT = 4

MARKER_PRESET_BY_SOURCE = {
    UNORDERED_SOURCE: "bullet",
    ORDERED_SOURCE: "numbered",
}


# ---------------------------------------------------------------------------
# Public readback helpers (the same conventions the sibling V03-01 modules use)
# ---------------------------------------------------------------------------


def _run_officecli(*args: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["officecli", *args, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return json.loads(completed.stdout)


def _walk(node: Mapping[str, Any]):
    yield node
    for child in node.get("children", []) or []:
        if isinstance(child, Mapping):
            yield from _walk(child)


def _slide_nodes(pptx: Path) -> list[dict[str, Any]]:
    document = _run_officecli("get", str(pptx), "/slide[1]", "--depth", "6")
    return list(_walk(document["data"]["results"][0]))


def _objects_by_type(pptx: Path, type_name: str) -> list[dict[str, Any]]:
    return [node for node in _slide_nodes(pptx) if node.get("type") == type_name]


def _text_objects(pptx: Path) -> list[dict[str, Any]]:
    """Return every native text-bearing object of the first slide."""
    return _objects_by_type(pptx, "textbox")


def _object_by_name(pptx: Path, name: str) -> dict[str, Any]:
    for node in _text_objects(pptx):
        if (node.get("format") or {}).get("name") == name:
            return node
    raise AssertionError(f"OfficeCLI readback has no text object named {name}")


def _shape_by_source(
    manifest: Mapping[str, Any], source_object: str
) -> dict[str, Any]:
    matches = [
        item
        for item in manifest["objects"]
        if item["source_object"] == source_object
        and item["kind"] in {"shape", "textbox"}
    ]
    assert len(matches) == 1, (
        f"expected exactly one text-bearing object for {source_object}, got "
        f"{[(item['name'], item['kind'], item['source_object']) for item in manifest['objects']]}"
    )
    return matches[0]


def _points(value: Any) -> float:
    assert isinstance(value, str), f"unexpected OfficeCLI length: {value!r}"
    assert value.endswith("pt"), f"unexpected OfficeCLI length: {value!r}"
    return float(value[:-2])


def _readback_run(run: Mapping[str, Any], fallback: Mapping[str, Any]) -> dict[str, Any]:
    format_data = run.get("format", {})
    return {
        "text": run["text"],
        "font_family": format_data.get("font.latin") or fallback.get("font"),
        "font_size_pt": _points(format_data.get("size") or fallback["size"]),
        "bold": bool(format_data.get("bold", False)),
        "italic": bool(format_data.get("italic", False)),
        "underline": str(format_data.get("underline", "none") or "none"),
        "color": str(format_data.get("color") or fallback.get("color") or "").upper(),
    }


def _readback_paragraphs(node: Mapping[str, Any]) -> list[dict[str, Any]]:
    fallback = node.get("format", {})
    paragraphs = []
    for paragraph in node.get("children", []) or []:
        format_data = paragraph.get("format", {}) or {}
        runs = [
            _readback_run(run, format_data or fallback)
            for run in paragraph.get("children", []) or []
            if run.get("type") == "run" and str(run.get("text", ""))
        ]
        paragraphs.append(
            {
                "text": paragraph.get("text", ""),
                "list": format_data.get("list"),
                "level": format_data.get("level"),
                "margin_left": format_data.get("marginLeft"),
                "indent": format_data.get("indent"),
                "space_after": format_data.get("spaceAfter"),
                "line_spacing": format_data.get("lineSpacing"),
                "runs": runs,
            }
        )
    return paragraphs


def _write_list_fixture(
    tmp_path: Path,
    name: str,
    body: str,
    css: str = "",
) -> Path:
    """Author a one-slide input whose list carries the fixture's list CSS."""
    html = tmp_path / name
    html.write_text(
        f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  .slide {{ width: 1920px; height: 1080px; position: relative; background: #ffffff; }}
  .list {{ position: absolute; left: 1080px; top: 635px; width: 300px;
          font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 27px;
          line-height: 1.35; color: #24324a; padding-left: 42px; }}
{css}
</style></head><body><section class="slide active">
  {body}
</section></body></html>""",
        encoding="utf-8",
    )
    return html


# ---------------------------------------------------------------------------
# Criterion 1: the public capability authority declares the list surface
# ---------------------------------------------------------------------------


def test_capability_authority_declares_the_native_list_surface() -> None:
    surface = author_capability_manifest()["list_surface"]

    assert surface["elements"] == ["ol", "ul"]
    assert surface["nesting"] == "top-level-only"
    assert surface["levels"] == [0]
    assert surface["object_per_list"] == 1
    assert surface["object_kind"] == "textbox"
    assert surface["paragraphs_per_item"] == 1
    assert surface["marker"]["presets"] == {"ol": "numbered", "ul": "bullet"}
    assert surface["marker"]["literal_prefix"] == "rejected"
    assert surface["paragraph_properties"] == [
        "indent",
        "level",
        "list",
        "marginLeft",
    ]
    assert sorted(surface["rejections"]) == sorted(LIST_REJECTION_CODES)
    # The published surface is the same data checking and lowering use.
    assert LIST_MARKER_PRESETS == {"ol": "numbered", "ul": "bullet"}


# ---------------------------------------------------------------------------
# Criterion 2: supported top-level list input passes public checking
# ---------------------------------------------------------------------------


def test_public_check_accepts_the_top_level_list_fixture() -> None:
    report = check_contract(FIXTURE, "author")

    assert report.status == "PASS"
    assert report.diagnostics == ()


def test_public_check_accepts_a_list_that_sits_inside_a_div(tmp_path: Path) -> None:
    """The rejected surface is list nesting and item structure, not position."""
    nested_in_div = _write_list_fixture(
        tmp_path,
        "lists-in-div.html",
        '<div><ul class="list"><li>原生项目符号</li><li>缩进与段落边界</li></ul></div>',
    )

    report = check_contract(nested_in_div, "author")

    assert report.status == "PASS", [item.as_dict() for item in report.diagnostics]


# ---------------------------------------------------------------------------
# Criteria 3, 4, 5, 7, 10: one textbox per list, one paragraph per item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_list_lowers_to_one_native_list_textbox(tmp_path: Path) -> None:
    output = tmp_path / "lists.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    assert result.manifest["object_kind_counts"] == EXPECTED_OBJECT_KIND_COUNTS
    # No item is emitted as its own textbox: the four authored card shapes plus
    # the six authored text objects are the whole slide.
    assert [
        item
        for item in result.manifest["objects"]
        if item["source_object"].startswith(UNORDERED_SOURCE + "/")
        or item["source_object"].startswith(ORDERED_SOURCE + "/")
    ] == []

    for source in LIST_SOURCES:
        item = _shape_by_source(result.manifest, source)
        assert item["kind"] == "textbox"
        assert item["name"].startswith("slide-001-textbox-")
        assert tuple(item["bounds_pt"]) == LIST_BOUNDS_PT[source]
        assert item["text"] == LIST_OBJECT_TEXT[source]
        assert [paragraph["text"] for paragraph in item["paragraphs"]] == list(
            LIST_ITEM_TEXTS[source]
        )


@pytest.mark.asyncio
async def test_the_whole_slide_keeps_exactly_six_text_objects(tmp_path: Path) -> None:
    output = tmp_path / "no-item-objects.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    assert "picture" not in result.manifest["object_kind_counts"]
    assert "table" not in result.manifest["object_kind_counts"]

    text_objects = _text_objects(output)
    assert len(text_objects) == EXPECTED_TEXT_OBJECT_COUNT
    shapes = _objects_by_type(output, "shape")
    assert len(shapes) == EXPECTED_SHAPE_COUNT
    # No list item is an image, an SVG, or a marker-simulating shape.
    assert {
        node.get("type") for node in _slide_nodes(output)
    } <= {"slide", "textbox", "shape", "paragraph", "run", "linebreak"}
    # Every list item text appears inside exactly one list object, and no
    # readback object carries a literal marker prefix.
    texts = [node.get("text", "") for node in text_objects]
    for source in LIST_SOURCES:
        assert LIST_OBJECT_TEXT[source] in texts
    for text in texts:
        for item_text in LIST_ITEM_TEXTS[UNORDERED_SOURCE] + LIST_ITEM_TEXTS[ORDERED_SOURCE]:
            assert not text.startswith("• " + item_text)
            assert not text.startswith("1. " + item_text)
            assert not text.startswith("2. " + item_text)
    assert "•" not in "".join(texts)


@pytest.mark.asyncio
async def test_every_item_is_one_paragraph_in_source_order(tmp_path: Path) -> None:
    output = tmp_path / "paragraphs-per-item.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    for source in LIST_SOURCES:
        item = _shape_by_source(result.manifest, source)
        paragraphs = item["paragraphs"]
        expected_texts = LIST_ITEM_TEXTS[source]

        assert len(paragraphs) == 2, source
        assert [paragraph["text"] for paragraph in paragraphs] == list(expected_texts)
        assert [len(paragraph["runs"]) for paragraph in paragraphs] == [1, 1]
        assert [
            [run["text"] for run in paragraph["runs"]] for paragraph in paragraphs
        ] == [[text] for text in expected_texts]
        assert [
            paragraph["space_after_pt"] for paragraph in paragraphs
        ] == [FIRST_ITEM_SPACE_AFTER_PT, SECOND_ITEM_SPACE_AFTER_PT]
        assert [paragraph["line_spacing"] for paragraph in paragraphs] == [
            ITEM_LINE_SPACING,
            ITEM_LINE_SPACING,
        ]
        assert [
            run["font_size_pt"] for paragraph in paragraphs for run in paragraph["runs"]
        ] == [ITEM_FONT_SIZE_PT, ITEM_FONT_SIZE_PT]
        assert [
            run["color"] for paragraph in paragraphs for run in paragraph["runs"]
        ] == [ITEM_COLOR, ITEM_COLOR]
        # The native list paragraph properties the lowering must carry.
        assert [paragraph["list"] for paragraph in paragraphs] == [
            MARKER_PRESET_BY_SOURCE[source]
        ] * 2
        assert [paragraph["level"] for paragraph in paragraphs] == [0, 0]
        assert [paragraph["margin_left_pt"] for paragraph in paragraphs] == [
            EXPECTED_MARGIN_LEFT_PT
        ] * 2
        assert [paragraph["indent_pt"] for paragraph in paragraphs] == [
            EXPECTED_INDENT_PT
        ] * 2


@pytest.mark.asyncio
async def test_native_marker_level_and_indentation_survive_readback(
    tmp_path: Path,
) -> None:
    output = tmp_path / "list-readback.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    for source in LIST_SOURCES:
        item = _shape_by_source(result.manifest, source)
        readback = _object_by_name(output, item["name"])
        paragraphs = _readback_paragraphs(readback)
        expected_texts = LIST_ITEM_TEXTS[source]

        assert readback.get("text") == LIST_OBJECT_TEXT[source]
        assert [paragraph["text"] for paragraph in paragraphs] == list(expected_texts)
        # Native marker: the bullet preset for <ul>, automatic numbering for <ol>.
        assert [paragraph["list"] for paragraph in paragraphs] == [
            MARKER_PRESET_BY_SOURCE[source]
        ] * 2
        # Native level and indentation, quoted as read back.
        assert [paragraph["level"] for paragraph in paragraphs] == ["0", "0"]
        assert [
            _points(paragraph["margin_left"]) for paragraph in paragraphs
        ] == [EXPECTED_MARGIN_LEFT_PT] * 2
        assert [
            _points(paragraph["indent"]) for paragraph in paragraphs
        ] == [EXPECTED_INDENT_PT] * 2
        assert [paragraph["space_after"] for paragraph in paragraphs] == [
            "7pt",
            None,
        ]
        assert [paragraph["line_spacing"] for paragraph in paragraphs] == [
            ITEM_READBACK_LINE_SPACING,
            ITEM_READBACK_LINE_SPACING,
        ]
        # No item text carries a literal marker prefix.
        for paragraph in paragraphs:
            assert paragraph["text"] not in {"", "•"}
            assert not paragraph["text"].startswith(("•", "1.", "2."))
        for run in [run for paragraph in paragraphs for run in paragraph["runs"]]:
            assert run["font_family"]
            assert run["font_size_pt"] == ITEM_FONT_SIZE_PT
            assert run["color"] == ITEM_COLOR


@pytest.mark.asyncio
async def test_item_boxes_keep_the_authored_inter_item_gap(tmp_path: Path) -> None:
    """``margin-bottom: 14px`` must stay a 7pt gap, not a collapsed item."""
    output = tmp_path / "item-gap.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    item = _shape_by_source(result.manifest, UNORDERED_SOURCE)
    first_top, second_top = EXPECTED_ITEM_TOP_PT
    assert second_top - first_top == ITEM_LINE_BOX_PT + FIRST_ITEM_SPACE_AFTER_PT
    assert item["bounds_pt"][1] == first_top
    assert item["bounds_pt"][3] == 2 * ITEM_LINE_BOX_PT + FIRST_ITEM_SPACE_AFTER_PT
    assert item["paragraphs"][0]["space_after_pt"] == FIRST_ITEM_SPACE_AFTER_PT

    readback = _object_by_name(output, item["name"])
    assert _readback_paragraphs(readback)[0]["space_after"] == "7pt"


# ---------------------------------------------------------------------------
# Criterion 8: Canonical Runs stay inside one list item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_canonical_runs_never_cross_a_list_item_boundary(tmp_path: Path) -> None:
    """Two items with identical formatting stay two paragraphs with own runs."""
    html = _write_list_fixture(
        tmp_path,
        "canonical-runs.html",
        '<ul class="list">'
        '<li><span class="same">North</span><span class="same"> Africa</span></li>'
        '<li><span class="same">North</span><span class="same"> Africa</span></li>'
        "</ul>",
        css="  .same { font-family: Georgia, serif; color: #0f6b78; }",
    )
    output = tmp_path / "canonical-runs.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    item = _shape_by_source(result.manifest, "slide[1]/ul[1]")
    paragraphs = item["paragraphs"]
    assert [paragraph["text"] for paragraph in paragraphs] == [
        "North Africa",
        "North Africa",
    ]
    # Merging happens inside one item ...
    assert [len(paragraph["runs"]) for paragraph in paragraphs] == [1, 1]
    assert [paragraph["runs"][0]["text"] for paragraph in paragraphs] == [
        "North Africa",
        "North Africa",
    ]
    # ... and never across the item boundary: no run holds both items.
    assert [
        run["text"]
        for paragraph in paragraphs
        for run in paragraph["runs"]
        if run["text"].count("North") > 1
    ] == []

    readback = _object_by_name(output, item["name"])
    readback_paragraphs = _readback_paragraphs(readback)
    assert [paragraph["text"] for paragraph in readback_paragraphs] == [
        "North Africa",
        "North Africa",
    ]
    assert [len(paragraph["runs"]) for paragraph in readback_paragraphs] == [1, 1]
    assert [paragraph["list"] for paragraph in readback_paragraphs] == [
        "bullet",
        "bullet",
    ]


@pytest.mark.asyncio
async def test_a_wrapped_item_stays_one_list_paragraph(tmp_path: Path) -> None:
    """A soft-wrapped item is one Native List Paragraph, not one per line."""
    html = _write_list_fixture(
        tmp_path,
        "wrapped-item.html",
        '<ul class="list" style="width: 240px;">'
        "<li>Chromium decides this bilingual soft wrap：浏览器决定视觉换行，PowerPoint"
        " 保留可编辑段落与原始阅读顺序。</li>"
        "<li>缩进与段落边界</li>"
        "</ul>",
    )
    output = tmp_path / "wrapped-item.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    item = _shape_by_source(result.manifest, "slide[1]/ul[1]")
    paragraphs = item["paragraphs"]
    assert len(paragraphs) == 2
    assert paragraphs[0]["text"] == (
        "Chromium decides this bilingual soft wrap：浏览器决定视觉换行，PowerPoint"
        " 保留可编辑段落与原始阅读顺序。"
    )
    assert paragraphs[1]["text"] == "缩进与段落边界"
    assert [len(paragraph["runs"]) for paragraph in paragraphs] == [1, 1]

    readback = _object_by_name(output, item["name"])
    assert [paragraph["text"] for paragraph in _readback_paragraphs(readback)] == [
        paragraphs[0]["text"],
        paragraphs[1]["text"],
    ]


# ---------------------------------------------------------------------------
# Criterion 9: unsupported list structures block before any output
# ---------------------------------------------------------------------------


NESTED_LIST_BODY = (
    '<ul class="list"><li>外层项目<ul><li>内层项目</li></ul></li></ul>'
)
HARD_BREAK_BODY = (
    '<ul class="list"><li>原生项目符号<br>缩进与段落边界</li></ul>'
)
MULTI_PARAGRAPH_BODY = (
    '<ul class="list"><li><p>第一段</p><p>第二段</p></li></ul>'
)
NON_ITEM_CHILD_BODY = '<ul class="list"><div>块级内容</div></ul>'

NEGATIVE_CASES = (
    (
        "nested-list.html",
        NESTED_LIST_BODY,
        "nested_list",
        "/html/body/section/ul/li/ul",
    ),
    (
        "list-item-hard-break.html",
        HARD_BREAK_BODY,
        "list_item_hard_break",
        "/html/body/section/ul/li/br",
    ),
    (
        "multi-paragraph-item.html",
        MULTI_PARAGRAPH_BODY,
        "multi_paragraph_list_item",
        "/html/body/section/ul/li/p[1]",
    ),
    (
        "non-item-child.html",
        NON_ITEM_CHILD_BODY,
        "multi_paragraph_list_item",
        "/html/body/section/ul/div",
    ),
)


@pytest.mark.parametrize(("name", "body", "code", "source_object"), NEGATIVE_CASES)
def test_unsupported_list_structures_block_checking(
    tmp_path: Path,
    name: str,
    body: str,
    code: str,
    source_object: str,
) -> None:
    html = _write_list_fixture(tmp_path, name, body)

    report = check_contract(html, "author")

    assert report.status == "BLOCK"
    blocking = [item for item in report.diagnostics if item.blocking]
    assert [item.code for item in blocking] == [code]
    assert blocking[0].source_object == source_object
    assert blocking[0].message
    # The same failure travels the public command seam with a blocking status.
    checked = application.check_author_html(html)
    assert checked.status == "BLOCK"
    assert [item.code for item in checked.diagnostics] == [code]
    assert checked.diagnostics[0].source_object == source_object
    assert cli.main(["check", str(html), "--json"]) == 2


@pytest.mark.parametrize(
    ("name", "body", "code", "source_object"),
    NEGATIVE_CASES,
)
def test_unsupported_list_structures_block_building_without_partial_output(
    tmp_path: Path,
    name: str,
    body: str,
    code: str,
    source_object: str,
) -> None:
    html = _write_list_fixture(tmp_path, name, body)
    output = tmp_path / "blocked.pptx"

    built = asyncio.run(application.build_author_html(str(html), str(output)))

    assert built.status == "BLOCK"
    assert built.exit_code == 2
    assert [item.code for item in built.diagnostics] == [code]
    assert built.diagnostics[0].source_object == source_object
    # Neither half of the Artifact Pair exists.
    assert not output.exists()
    assert not (tmp_path / "blocked.evidence").exists()
    assert not list(tmp_path.glob(".blocked-*-*"))


def test_supported_list_surface_is_the_declared_one() -> None:
    """The rejection codes the checker emits are the declared surface's."""
    assert LIST_REJECTION_CODES == (
        "nested_list",
        "list_item_hard_break",
        "multi_paragraph_list_item",
    )
    assert set(LIST_REJECTION_CODES) <= set(
        author_capability_manifest()["list_surface"]["rejections"]
    )


# ---------------------------------------------------------------------------
# Criterion 10: independent expected literals for the emoji-bearing item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_after_an_emoji_keeps_its_utf16_alignment(tmp_path: Path) -> None:
    """A formatted run after ``2️⃣`` must not absorb any of the emoji."""
    html = _write_list_fixture(
        tmp_path,
        "emoji-item.html",
        '<ol class="list" style="width: 270px;">'
        '<li style="margin-bottom: 14px;">First step</li>'
        '<li>第二步 2️⃣ <strong style="color: #b91c1c;">加粗 Bold</strong></li>'
        "</ol>",
    )
    output = tmp_path / "emoji-item.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    item = _shape_by_source(result.manifest, "slide[1]/ol[1]")
    paragraphs = item["paragraphs"]
    assert [paragraph["text"] for paragraph in paragraphs] == [
        "First step",
        "第二步 2️⃣ 加粗 Bold",
    ]
    runs = paragraphs[1]["runs"]
    # "第二步 2️⃣ " is 3 CJK characters, a space, "2", U+FE0F, U+20E3 and a space:
    # eight UTF-16 code units, so the bold run must start at offset 8.
    assert [run["text"] for run in runs] == ["第二步 2️⃣ ", "加粗 Bold"]
    assert [run["bold"] for run in runs] == [False, True]
    assert [run["color"] for run in runs] == [ITEM_COLOR, "#B91C1C"]
    prefix = runs[0]["text"]
    assert len(prefix.encode("utf-16-le")) // 2 == 8

    readback = _object_by_name(output, item["name"])
    readback_runs = _readback_paragraphs(readback)[1]["runs"]
    assert [run["text"] for run in readback_runs] == ["第二步 2️⃣ ", "加粗 Bold"]
    assert [run["bold"] for run in readback_runs] == [False, True]
    assert [run["color"] for run in readback_runs] == [ITEM_COLOR, "#B91C1C"]
    assert _readback_paragraphs(readback)[1]["list"] == "numbered"
