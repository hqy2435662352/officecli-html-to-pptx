"""Public-seam tests for V03-01 paragraph-local hard breaks and empty paragraphs.

Every expectation below is an independent literal taken from the accepted
fixture (``tests/fixtures/v03_01_rich_text_paragraphs.html``) or from an
explicitly written expected paragraph/run model.  Nothing is derived from the
compiler's own output.

The slice under test is Contract 1.1 native hard-break topology: a ``<br>`` is
inside its authored native paragraph, consecutive ``<br>`` controls are kept,
and authored empty ``<p>`` elements (covered by the V05 fixture) remain native
paragraphs.  Every run is paragraph-local and no range covers a paragraph
separator.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

import pytest

from officecli_html_to_pptx._internal.officecli_compiler import (
    OfficeCLICompilationError,
    compile_officecli,
)

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the V03-01 hard-break tests",
)

FIXTURE = Path(__file__).parent / "fixtures" / "v03_01_rich_text_paragraphs.html"

# ``#paragraphs`` is the fifth top-level slide child of the fixture.
PARAGRAPHS_SOURCE = "slide[1]/div[5]"

# The authored fixture's ``#paragraphs`` textbox declares
# ``font-size: 28px; line-height: 1.35; color: #24324a`` at 1920x1080 CSS
# pixels, which is the 960x540pt widescreen canvas at scale 0.5: 28px -> 14pt.
SEGO_UI_14PT = "Segoe UI"
PARAGRAPHS_FONT_SIZE_PT = 14.0
PARAGRAPHS_COLOR = "#24324A"
# 1.35 x 28px CSS line-height on a 28px font, sampled at the 0.5pt scale.
PARAGRAPHS_LINE_SPACING = "1.350x"
PARAGRAPHS_READBACK_LINE_SPACING = "1.35x"

# The authored source of ``#paragraphs``, in reading order:
#
#     <span style="font-weight: 700; color: #9a3412;">跨段样式 A<br>Cross-break
#     style B</span><br><br>Second paragraph after an empty paragraph.<br>第三段：
#     显式换行后仍可编辑。
#
# so the styled inline element that crosses the first <br> stays two visible
# ranges in one paragraph with identical resolved formatting; consecutive
# <br> controls stay in that same native paragraph.
EXPECTED_PARAGRAPH_TEXTS: tuple[str, ...] = (
    "跨段样式 A\vCross-break style B\v\vSecond paragraph after an empty paragraph.\v第三段：显式换行后仍可编辑。",
)
EXPECTED_PARAGRAPH_COUNT = 1
EXPECTED_OBJECT_TEXT = EXPECTED_PARAGRAPH_TEXTS[0]

# The fixture's inline style on ``[data-run-across-br]`` is
# ``font-weight: 700; color: #9a3412`` on the textbox's 28px "Segoe UI"
# default, so both sides of the hard break resolve to the same formatting.
EXPECTED_STYLED_RUNS: tuple[Mapping[str, Any], ...] = (
    {
        "text": "跨段样式 A",
        "font_family": SEGO_UI_14PT,
        "font_size_pt": PARAGRAPHS_FONT_SIZE_PT,
        "bold": True,
        "italic": False,
        "underline": "none",
        "color": "#9A3412",
    },
    {
        "text": "Cross-break style B",
        "font_family": SEGO_UI_14PT,
        "font_size_pt": PARAGRAPHS_FONT_SIZE_PT,
        "bold": True,
        "italic": False,
        "underline": "none",
        "color": "#9A3412",
    },
)
EXPECTED_PLAIN_RUNS: tuple[Mapping[str, Any], ...] = (
    {
        "text": "Second paragraph after an empty paragraph.",
        "font_family": SEGO_UI_14PT,
        "font_size_pt": PARAGRAPHS_FONT_SIZE_PT,
        "bold": False,
        "italic": False,
        "underline": "none",
        "color": PARAGRAPHS_COLOR,
    },
    {
        "text": "第三段：显式换行后仍可编辑。",
        "font_family": SEGO_UI_14PT,
        "font_size_pt": PARAGRAPHS_FONT_SIZE_PT,
        "bold": False,
        "italic": False,
        "underline": "none",
        "color": PARAGRAPHS_COLOR,
    },
)
# Four visible runs remain in one authored paragraph; hard-break controls are
# represented by paragraph-local offsets rather than synthetic runs.
EXPECTED_PARAGRAPHS_RUN_COUNT = 4


# ---------------------------------------------------------------------------
# Public readback helpers
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


def _text_objects(pptx: Path) -> list[dict[str, Any]]:
    """Return every native text-bearing object of the first slide."""
    document = _run_officecli("get", str(pptx), "/slide[1]", "--depth", "6")
    slide = document["data"]["results"][0]
    objects = []
    for node in _walk(slide):
        children = node.get("children") or []
        if children and all(
            isinstance(child, Mapping) and child.get("type") == "paragraph"
            for child in children
        ):
            objects.append(node)
    return objects


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
        f"{[(item['name'], item['kind']) for item in manifest['objects']]}"
    )
    return matches[0]


def _points(value: str) -> float:
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
    """Read back paragraphs and their *text-bearing* runs.

    OfficeCLI materializes one empty ``run`` child for a native empty
    paragraph, so an empty paragraph reads back as zero text-bearing runs.
    """
    fallback = node.get("format", {})
    paragraphs = []
    for paragraph in node.get("children", []) or []:
        runs = []
        text_parts = []
        for child in paragraph.get("children", []) or []:
            if child.get("type") == "linebreak":
                text_parts.append("\v")
            elif child.get("type") == "run":
                text = str(child.get("text", ""))
                if text:
                    text_parts.append(text)
                    runs.append(_readback_run(child, paragraph.get("format", fallback)))
        paragraphs.append(
            {
                "text": "".join(text_parts),
                "line_spacing": (paragraph.get("format") or {}).get("lineSpacing"),
                "runs": runs,
            }
        )
    return paragraphs


def _expected_run(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "text": run["text"],
        "font_family": run["font_family"],
        "font_size_pt": run["font_size_pt"],
        "bold": run["bold"],
        "italic": run["italic"],
        "underline": run["underline"],
        "color": run["color"],
    }


def _manifest_run(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "text": run["text"],
        "font_family": run["font_family"],
        "font_size_pt": run["font_size_pt"],
        "bold": run["bold"],
        "italic": run["italic"],
        "underline": run["underline"],
        "color": run["color"],
    }


def _utf16_length(text: str) -> int:
    """OfficeCLI ranges are UTF-16 code units and exclude paragraph marks."""
    return len(
        text.replace("\r", "").replace("\n", "").replace("\v", "").encode("utf-16-le")
    ) // 2


def _write_fixture(tmp_path: Path, name: str, body: str, css: str = "") -> Path:
    html = tmp_path / name
    html.write_text(
        f"""<!doctype html>
<html><head><style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  .slide {{ width: 1920px; height: 1080px; position: relative; background: #ffffff; }}
  .copy {{ position: absolute; left: 100px; top: 100px; width: 900px; height: 400px;
          font-family: "Segoe UI", sans-serif; font-size: 28px; line-height: 1.35;
          text-align: left; color: #24324a; }}
  .across {{ font-weight: 700; color: #9a3412; }}
{css}
</style></head><body><section class="slide active">
  <div class="copy">{body}</div>
</section></body></html>""",
        encoding="utf-8",
    )
    return html


# ---------------------------------------------------------------------------
# Criterion 1: the supported <br> surface passes public checking
# ---------------------------------------------------------------------------


def test_public_check_accepts_hard_break_and_empty_paragraph_input() -> None:
    from officecli_html_to_pptx.contract import check_contract

    report = check_contract(FIXTURE, "author")

    assert report.status == "PASS"
    assert report.diagnostics == ()


# ---------------------------------------------------------------------------
# Criterion 2, 3, 4, 7, 8: the exact authored paragraph/run table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hard_breaks_and_empty_paragraph_survive_manifest_and_readback(
    tmp_path: Path,
) -> None:
    """The fixture's ``#paragraphs`` object is one paragraph, four runs total.

    Independent literals: paragraph count, every paragraph text in source
    order, the empty-paragraph position, one run per paragraph, and the
    resolved formatting on both sides of the hard break that the styled
    ``[data-run-across-br]`` element spans.
    """
    output = tmp_path / "paragraphs.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, PARAGRAPHS_SOURCE)
    assert manifest_object["kind"] == "textbox"
    assert manifest_object["text"] == EXPECTED_OBJECT_TEXT

    manifest_paragraphs = manifest_object["paragraphs"]
    assert len(manifest_paragraphs) == EXPECTED_PARAGRAPH_COUNT
    assert [
        paragraph["text"] for paragraph in manifest_paragraphs
    ] == list(EXPECTED_PARAGRAPH_TEXTS)
    assert [
        [run["text"] for run in paragraph["runs"]]
        for paragraph in manifest_paragraphs
    ] == [
        [
            "跨段样式 A",
            "Cross-break style B",
            "Second paragraph after an empty paragraph.",
            "第三段：显式换行后仍可编辑。",
        ],
    ]
    assert [len(paragraph["runs"]) for paragraph in manifest_paragraphs] == [4]
    assert [_manifest_run(run) for run in manifest_paragraphs[0]["runs"]] == [
        _expected_run(EXPECTED_STYLED_RUNS[0]),
        _expected_run(EXPECTED_STYLED_RUNS[1]),
        _expected_run(EXPECTED_PLAIN_RUNS[0]),
        _expected_run(EXPECTED_PLAIN_RUNS[1]),
    ]
    assert manifest_paragraphs[0]["hard_break_offsets"] == [6, 25, 25, 67]
    # The paragraph keeps the authored 1.35 line-height ratio.
    assert [
        paragraph["line_spacing"] for paragraph in manifest_paragraphs
    ] == [PARAGRAPHS_LINE_SPACING]

    # The independent expected literal and the OfficeCLI readback are compared
    # paragraph by paragraph, so a merged or swallowed <br> cannot pass.
    readback = _object_by_name(output, manifest_object["name"])
    assert readback["text"] == EXPECTED_OBJECT_TEXT
    readback_paragraphs = _readback_paragraphs(readback)
    assert len(readback_paragraphs) == EXPECTED_PARAGRAPH_COUNT
    assert [paragraph["text"] for paragraph in readback_paragraphs] == list(
        EXPECTED_PARAGRAPH_TEXTS
    )
    assert [
        paragraph["line_spacing"] for paragraph in readback_paragraphs
    ] == [PARAGRAPHS_READBACK_LINE_SPACING]
    assert [
        [_expected_run(run) for run in paragraph["runs"]]
        for paragraph in readback_paragraphs
    ] == [
        [
            _expected_run(EXPECTED_STYLED_RUNS[0]),
            _expected_run(EXPECTED_STYLED_RUNS[1]),
            _expected_run(EXPECTED_PLAIN_RUNS[0]),
            _expected_run(EXPECTED_PLAIN_RUNS[1]),
        ],
    ]


@pytest.mark.asyncio
async def test_styled_element_spanning_a_hard_break_keeps_identical_formatting(
    tmp_path: Path,
) -> None:
    """Criterion 4: one Paragraph-local Run per side, same resolved formatting.

    The two runs are in different paragraphs, so identical formatting must not
    let Canonical Run normalization merge them: the cross-break boundary is a
    run boundary even when both sides resolve to ``bold`` ``#9A3412``.
    """
    output = tmp_path / "cross-break.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, PARAGRAPHS_SOURCE)
    first, second = manifest_object["paragraphs"][0]["runs"][:2]
    assert first["text"] == "跨段样式 A"
    assert second["text"] == "Cross-break style B"
    # Identical resolved formatting on both sides of the break ...
    assert {
        key: first[key]
        for key in ("font_family", "font_size_pt", "bold", "italic", "underline", "color")
    } == {
        key: second[key]
        for key in ("font_family", "font_size_pt", "bold", "italic", "underline", "color")
    }
    assert first["color"] == "#9A3412"
    assert first["bold"] is True
    # ... and still two visible runs in one paragraph, never one merged run.
    assert len(manifest_object["paragraphs"]) == 1
    assert "跨段样式 ACross-break style B" not in {
        run["text"]
        for paragraph in manifest_object["paragraphs"]
        for run in paragraph["runs"]
    }

    readback = _object_by_name(output, manifest_object["name"])
    readback_paragraphs = _readback_paragraphs(readback)
    assert len(readback_paragraphs) == 1
    assert len(readback_paragraphs[0]["runs"]) == 4
    assert _expected_run(readback_paragraphs[0]["runs"][0]) == _expected_run(
        EXPECTED_STYLED_RUNS[0]
    )
    assert _expected_run(readback_paragraphs[0]["runs"][1]) == _expected_run(
        EXPECTED_STYLED_RUNS[1]
    )


@pytest.mark.asyncio
async def test_consecutive_hard_breaks_keep_exactly_one_empty_paragraph(
    tmp_path: Path,
) -> None:
    """Criterion 3: ``A<br><br>B`` keeps two native hard-break controls."""
    html = _write_fixture(
        tmp_path,
        "consecutive-breaks.html",
        "First<br><br>Second",
    )
    output = tmp_path / "consecutive-breaks.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[1]")
    assert [paragraph["text"] for paragraph in manifest_object["paragraphs"]] == [
        "First\v\vSecond",
    ]
    assert manifest_object["paragraphs"][0]["hard_break_offsets"] == [5, 5]
    assert manifest_object["text"] == "First\v\vSecond"

    readback = _object_by_name(output, manifest_object["name"])
    paragraphs = _readback_paragraphs(readback)
    assert [paragraph["text"] for paragraph in paragraphs] == ["First\v\vSecond"]
    assert [len(paragraph["runs"]) for paragraph in paragraphs] == [2]


@pytest.mark.asyncio
async def test_nested_break_inside_an_inline_element_is_a_native_hard_break(
    tmp_path: Path,
) -> None:
    """A ``<br>`` nested in an inline element is a real break, not text."""
    html = _write_fixture(
        tmp_path,
        "nested-break.html",
        '<span class="across">跨段样式 A<br>Cross-break style B</span>'
        "<br><br>Second paragraph after an empty paragraph."
        "<br>第三段：显式换行后仍可编辑。",
    )
    output = tmp_path / "nested-break.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[1]")
    assert [paragraph["text"] for paragraph in manifest_object["paragraphs"]] == [
        EXPECTED_OBJECT_TEXT
    ]
    assert manifest_object["text"] == EXPECTED_OBJECT_TEXT

    readback = _object_by_name(output, manifest_object["name"])
    paragraphs = _readback_paragraphs(readback)
    assert [paragraph["text"] for paragraph in paragraphs] == [EXPECTED_OBJECT_TEXT]
    assert _expected_run(paragraphs[0]["runs"][0]) == _expected_run(
        EXPECTED_STYLED_RUNS[0]
    )
    assert _expected_run(paragraphs[0]["runs"][1]) == _expected_run(
        EXPECTED_STYLED_RUNS[1]
    )


@pytest.mark.asyncio
async def test_nested_inline_element_style_wins_inside_a_styled_span(
    tmp_path: Path,
) -> None:
    """Recursion keeps the *nearest* inline element's computed style."""
    html = _write_fixture(
        tmp_path,
        "nearest-style.html",
        '<span class="across">outer <em>inner</em> tail</span>',
        css="  .across em { font-style: italic; color: #4338ca; }",
    )
    output = tmp_path / "nearest-style.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[1]")
    assert [paragraph["text"] for paragraph in manifest_object["paragraphs"]] == [
        "outer inner tail"
    ]
    runs = manifest_object["paragraphs"][0]["runs"]
    assert [run["text"] for run in runs] == ["outer ", "inner", " tail"]
    assert [run["color"] for run in runs] == ["#9A3412", "#4338CA", "#9A3412"]
    assert [run["italic"] for run in runs] == [False, True, False]

    readback = _object_by_name(output, manifest_object["name"])
    assert [
        [run["text"] for run in paragraph["runs"]]
        for paragraph in _readback_paragraphs(readback)
    ] == [["outer ", "inner", " tail"]]


# ---------------------------------------------------------------------------
# Criterion 5 and 6: paragraph-local runs and UTF-16 range offsets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_normalized_run_contains_a_newline(tmp_path: Path) -> None:
    """Criterion 5: paragraph separators live between runs, never inside one."""
    output = tmp_path / "paragraph-local.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, PARAGRAPHS_SOURCE)
    runs = [
        run
        for paragraph in manifest_object["paragraphs"]
        for run in paragraph["runs"]
    ]
    assert len(runs) == EXPECTED_PARAGRAPHS_RUN_COUNT
    for run in runs:
        assert "\n" not in run["text"]
        assert "\r" not in run["text"]
    assert "".join(run["text"] for run in runs) == (
        "跨段样式 ACross-break style BSecond paragraph after an empty "
        "paragraph.第三段：显式换行后仍可编辑。"
    )

    readback = _object_by_name(output, manifest_object["name"])
    readback_runs = [
        run
        for paragraph in _readback_paragraphs(readback)
        for run in paragraph["runs"]
    ]
    assert [run["text"] for run in readback_runs] == [
        "跨段样式 A",
        "Cross-break style B",
        "Second paragraph after an empty paragraph.",
        "第三段：显式换行后仍可编辑。",
    ]
    for run in readback_runs:
        assert "\n" not in run["text"]


@pytest.mark.asyncio
async def test_range_offsets_are_paragraph_local_across_an_empty_paragraph(
    tmp_path: Path,
) -> None:
    """Criterion 6: an empty paragraph and a supplementary character keep alignment.

    The authored body is ``plain<br><br>after 🚀<strong>Bold</strong>``: the
    empty paragraph contributes no addressable character, so the bold range
    must begin at UTF-16 offset 9 ("after " is 6 units and 🚀 is a surrogate
    pair worth 2), and it must end exactly at the paragraph boundary.
    """
    html = _write_fixture(
        tmp_path,
        "offset-alignment.html",
        "plain<br><br>after 🚀<strong>Bold</strong>",
        css='  strong { font-weight: 700; color: #e60012; }',
    )
    output = tmp_path / "offset-alignment.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[1]")
    assert [paragraph["text"] for paragraph in manifest_object["paragraphs"]] == [
        "plain\v\vafter 🚀Bold",
    ]

    offset = 0
    seen: list[tuple[str, int, int]] = []
    for paragraph in manifest_object["paragraphs"]:
        for run in paragraph["runs"]:
            length = _utf16_length(run["text"])
            seen.append((run["text"], offset, offset + length))
            offset += length
    # Independent literal: "after \U0001F680" is 6 + 2 = 8 UTF-16 units, and the
    # empty paragraph adds nothing between them.
    assert seen == [
        ("plain", 0, 5),
        ("after 🚀", 5, 13),
        ("Bold", 13, 17),
    ]
    assert manifest_object["paragraphs"][0]["runs"][2]["bold"] is True
    # "plain" is 5 units, so the addressable body (object text minus its two
    # paragraph separators) is 5 + 0 + 12 = 17 units.
    assert offset == _utf16_length("plainafter 🚀Bold") == 17

    # The OfficeCLI range write landed on exactly the authored characters: only
    # "Bold" reads back bold/red, and the paragraph after the empty paragraph is
    # not shifted by a missing or extra unit.
    readback = _object_by_name(output, manifest_object["name"])
    paragraphs = _readback_paragraphs(readback)
    assert [paragraph["text"] for paragraph in paragraphs] == [
        "plain\v\vafter 🚀Bold",
    ]
    assert [_expected_run(run) for run in paragraphs[0]["runs"]] == [
        {
            "text": "plain",
            "font_family": "Segoe UI",
            "font_size_pt": 14.0,
            "bold": False,
            "italic": False,
            "underline": "none",
            "color": "#24324A",
        },
        {
            "text": "after 🚀",
            "font_family": "Segoe UI",
            "font_size_pt": 14.0,
            "bold": False,
            "italic": False,
            "underline": "none",
            "color": "#24324A",
        },
        {
            "text": "Bold",
            "font_family": "Segoe UI",
            "font_size_pt": 14.0,
            "bold": True,
            "italic": False,
            "underline": "none",
            "color": "#E60012",
        },
    ]


@pytest.mark.asyncio
async def test_top_level_break_range_offsets_end_at_each_paragraph(
    tmp_path: Path,
) -> None:
    """The fixture's own offsets: 6 + 19 units, then the empty paragraph."""
    output = tmp_path / "fixture-offsets.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, PARAGRAPHS_SOURCE)
    offset = 0
    seen: list[tuple[str, int, int]] = []
    for paragraph in manifest_object["paragraphs"]:
        for run in paragraph["runs"]:
            length = _utf16_length(run["text"])
            seen.append((run["text"], offset, offset + length))
            offset += length
    assert seen == [
        ("跨段样式 A", 0, 6),
        ("Cross-break style B", 6, 25),
        ("Second paragraph after an empty paragraph.", 25, 67),
        ("第三段：显式换行后仍可编辑。", 67, 81),
    ]
    # No range covers a paragraph separator: the total addressable length is
    # the object text minus its four "\n" separators.
    assert offset == _utf16_length(EXPECTED_OBJECT_TEXT) == 81


@pytest.mark.asyncio
async def test_white_space_pre_keeps_significant_newlines_and_runs(
    tmp_path: Path,
) -> None:
    """``white-space: pre`` keeps its newlines and indentation unchanged.

    ``pre`` text is never whitespace-collapsed, so a newline in a text node is
    a paragraph break and a newline inside a styled inline element splits the
    styled text into paragraph-local runs without the element's decoration
    leaking out of its own line.
    """
    html = _write_fixture(
        tmp_path,
        "pre-mode.html",
        "alpha\nbeta <span class=\"across\">gamma\ndelta</span> epsilon",
        css='  .copy { white-space: pre; }',
    )
    output = tmp_path / "pre-mode.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[1]")
    assert [paragraph["text"] for paragraph in manifest_object["paragraphs"]] == [
        "alpha\vbeta gamma\vdelta epsilon"
    ]
    assert [
        [run["text"] for run in paragraph["runs"]]
        for paragraph in manifest_object["paragraphs"]
    ] == [["alpha", "beta ", "gamma", "delta", " epsilon"]]
    assert manifest_object["paragraphs"][0]["runs"][2]["bold"] is True
    assert manifest_object["paragraphs"][0]["runs"][3]["bold"] is True

    readback = _object_by_name(output, manifest_object["name"])
    paragraphs = _readback_paragraphs(readback)
    assert [paragraph["text"] for paragraph in paragraphs] == [
        "alpha\vbeta gamma\vdelta epsilon",
    ]
    assert [run["bold"] for run in paragraphs[0]["runs"]] == [
        False,
        False,
        True,
        True,
        False,
    ]


@pytest.mark.asyncio
async def test_adjacent_same_format_spans_keep_their_authored_boundary_space(
    tmp_path: Path,
) -> None:
    """A boundary space owned by a second same-format span is never dropped.

    The authored line is ``Canonical: <span>North</span><span> Africa</span>``
    where both spans resolve to identical bold formatting.  The space belongs to
    the second span, so normalizing the two spans into one Canonical Run must
    produce ``North Africa`` rather than ``NorthAfrica``.
    """
    html = _write_fixture(
        tmp_path,
        "boundary-space.html",
        'Canonical: <span class="across">North</span>'
        '<span class="across"> Africa</span>',
    )
    output = tmp_path / "boundary-space.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[1]")
    assert manifest_object["text"] == "Canonical: North Africa"
    assert [
        run["text"] for run in manifest_object["paragraphs"][0]["runs"]
    ] == ["Canonical: ", "North Africa"]

    readback = _object_by_name(output, manifest_object["name"])
    assert readback["text"] == "Canonical: North Africa"
    assert [
        run["text"] for run in _readback_paragraphs(readback)[0]["runs"]
    ] == ["Canonical: ", "North Africa"]


# ---------------------------------------------------------------------------
# Regressions: authored whitespace is not a break, and an anchor keeps its href
# ---------------------------------------------------------------------------

# ``<strong>Alpha</strong>\n<em>Beta</em> Gamma``: the text node between the two
# inline elements is exactly one source newline of ordinary ``white-space:
# normal`` content, which a browser renders as one line.  It is authored
# whitespace, so it collapses to a single boundary space -- which the V03-01-01
# attribution rule gives to the run before it -- and never closes a paragraph.
EXPECTED_INLINE_SIBLING_TEXT = "Alpha Beta Gamma"
EXPECTED_INLINE_SIBLING_RUNS: tuple[Mapping[str, Any], ...] = (
    {
        "text": "Alpha ",
        "font_family": SEGO_UI_14PT,
        "font_size_pt": PARAGRAPHS_FONT_SIZE_PT,
        "bold": True,
        "italic": False,
        "underline": "none",
        "color": PARAGRAPHS_COLOR,
    },
    {
        "text": "Beta",
        "font_family": SEGO_UI_14PT,
        "font_size_pt": PARAGRAPHS_FONT_SIZE_PT,
        "bold": False,
        "italic": True,
        "underline": "none",
        "color": PARAGRAPHS_COLOR,
    },
    {
        "text": " Gamma",
        "font_family": SEGO_UI_14PT,
        "font_size_pt": PARAGRAPHS_FONT_SIZE_PT,
        "bold": False,
        "italic": False,
        "underline": "none",
        "color": PARAGRAPHS_COLOR,
    },
)

# The authored anchor target of the href guard below.
ANCHOR_TARGET = "https://example.com/report"
# ``See <a href="...">the report</a> now``: only the run descended from the
# anchor carries the target, and the runs before and after it stay ``None``.
EXPECTED_ANCHOR_RUNS: tuple[tuple[str, str | None], ...] = (
    ("See ", None),
    ("the report", ANCHOR_TARGET),
    (" now", None),
)
# ``See <a href="..."><strong>the bold report</strong> here</a> now``: the
# nearest enclosing anchor target reaches every run of the anchor's subtree,
# including the text that a nested inline element styles.
EXPECTED_NESTED_ANCHOR_RUNS: tuple[tuple[str, str | None], ...] = (
    ("See ", None),
    ("the bold report", ANCHOR_TARGET),
    (" here", ANCHOR_TARGET),
    (" now", None),
)
# ``<span class="across">Canonical: <a href="..." style="color: inherit;
# text-decoration: none;">North</a> Africa</span>``: the anchor run and its
# plain neighbour resolve to identical formatting, so only the supported
# semantic attribute (``href``) keeps them apart.
EXPECTED_SEMANTIC_ANCHOR_RUNS: tuple[str, ...] = ("Canonical: ", "North", " Africa")


@pytest.mark.asyncio
async def test_source_newline_between_inline_siblings_stays_one_paragraph(
    tmp_path: Path,
) -> None:
    """A whitespace-only text node is authored whitespace, never a hard break.

    The authored body is ``<strong>Alpha</strong>\\n<em>Beta</em> Gamma``: the
    newline between the two inline elements is source formatting, so the copy
    is one paragraph whose text is exactly ``Alpha Beta Gamma``, and the bold,
    italic and plain words stay their own runs.
    """
    html = _write_fixture(
        tmp_path,
        "inline-sibling-newline.html",
        "<strong>Alpha</strong>\n<em>Beta</em> Gamma",
    )
    output = tmp_path / "inline-sibling-newline.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[1]")
    assert manifest_object["text"] == EXPECTED_INLINE_SIBLING_TEXT
    assert len(manifest_object["paragraphs"]) == 1
    manifest_paragraph = manifest_object["paragraphs"][0]
    assert manifest_paragraph["text"] == EXPECTED_INLINE_SIBLING_TEXT
    assert [
        _manifest_run(run) for run in manifest_paragraph["runs"]
    ] == [_expected_run(run) for run in EXPECTED_INLINE_SIBLING_RUNS]

    readback = _object_by_name(output, manifest_object["name"])
    assert readback["text"] == EXPECTED_INLINE_SIBLING_TEXT
    readback_paragraphs = _readback_paragraphs(readback)
    assert len(readback_paragraphs) == 1
    assert readback_paragraphs[0]["text"] == EXPECTED_INLINE_SIBLING_TEXT
    assert [
        _expected_run(run) for run in readback_paragraphs[0]["runs"]
    ] == [_expected_run(run) for run in EXPECTED_INLINE_SIBLING_RUNS]


@pytest.mark.asyncio
async def test_anchor_run_is_outside_the_frozen_native_matrix(
    tmp_path: Path,
) -> None:
    """Hyperlink targets are rejected before a lossy native run can be emitted."""
    html = _write_fixture(
        tmp_path,
        "anchor-href.html",
        f'See <a href="{ANCHOR_TARGET}">the report</a> now<br>'
        f'See <a href="{ANCHOR_TARGET}"><strong>the bold report</strong> here</a>'
        " now<br>"
        f'<span class="across">Canonical: <a href="{ANCHOR_TARGET}" '
        'style="color: inherit; text-decoration: none;">North</a> Africa</span>',
    )
    output = tmp_path / "anchor-href.pptx"

    with pytest.raises(OfficeCLICompilationError) as error:
        await compile_officecli(str(html), "author", str(output))
    assert "unsupported_hyperlink" in {
        item.code for item in error.value.diagnostics
    }
    assert not output.exists()


# ---------------------------------------------------------------------------
# Criterion 12: the V0.2 top-level behaviour is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v02_top_level_hard_break_semantics_are_unchanged(
    tmp_path: Path,
) -> None:
    """``one<br><br>three<br>`` stays one paragraph with three hard breaks."""
    html = _write_fixture(
        tmp_path,
        "v02-breaks.html",
        "one<br><br>three<br>",
    )
    output = tmp_path / "v02-breaks.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[1]")
    assert [paragraph["text"] for paragraph in manifest_object["paragraphs"]] == [
        "one\v\vthree\v",
    ]

    readback = _object_by_name(output, manifest_object["name"])
    assert [
        paragraph["text"] for paragraph in _readback_paragraphs(readback)
    ] == ["one\v\vthree\v"]
