"""Public-seam tests for V03-01 mixed native runs and Canonical Run normalization.

Every expectation below is an independent literal taken from the accepted
fixture (``tests/fixtures/v03_01_rich_text_paragraphs.html``) or from an
explicitly written expected run model.  Nothing is derived from the compiler's
own output.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

import pytest

from officecli_html_to_pptx._internal.officecli_compiler import compile_officecli
from officecli_html_to_pptx.application import get_capabilities

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the V03-01 mixed-run tests",
)

FIXTURE = Path(__file__).parent / "fixtures" / "v03_01_rich_text_paragraphs.html"

# The authored fixture measures #mixed-runs at left:170px top:250px on a
# 1920x1080 canvas, which projects to the widescreen 960x540pt slide canvas.
MIXED_RUNS_BOUNDS_PT = [85.0, 125.0, 350.0, 117.5]

# Independent expected model of the first #mixed-runs paragraph.  Family,
# size, weight, style, underline, and color come from the fixture's own CSS
# plus the "Segoe UI" textbox default.
#
# Each collapsed boundary space stays with the run that authored it: the space
# before <strong> belongs to the textbox text node, the " · " around <em> and
# <u> belong to their own text nodes.  A space that migrates backwards across a
# formatting boundary would move a 15pt space into the 17pt bold run and widen
# the underline by one space.
EXPECTED_PREFIX_RUNS: tuple[Mapping[str, Any], ...] = (
    {
        "text": "常规 Regular · ",
        "font_family": "Segoe UI",
        "font_size_pt": 15.0,
        "bold": False,
        "italic": False,
        "underline": "none",
        "color": "#24324A",
    },
    {
        "text": "粗体 Bold",
        "font_family": "Georgia",
        "font_size_pt": 17.0,
        "bold": True,
        "italic": False,
        "underline": "none",
        "color": "#0F6B78",
    },
    {
        "text": " · ",
        "font_family": "Segoe UI",
        "font_size_pt": 15.0,
        "bold": False,
        "italic": False,
        "underline": "none",
        "color": "#24324A",
    },
    {
        "text": "斜体 Italic",
        "font_family": "Segoe UI",
        "font_size_pt": 14.0,
        "bold": False,
        "italic": True,
        "underline": "none",
        "color": "#9A3412",
    },
    {
        "text": " · ",
        "font_family": "Segoe UI",
        "font_size_pt": 15.0,
        "bold": False,
        "italic": False,
        "underline": "none",
        "color": "#24324A",
    },
    {
        "text": "下划线 Underline",
        "font_family": "Segoe UI",
        "font_size_pt": 15.0,
        "bold": False,
        "italic": False,
        "underline": "single",
        "color": "#4338CA",
    },
    {
        "text": " · 数字 2026 · emoji 🚀",
        "font_family": "Segoe UI",
        "font_size_pt": 15.0,
        "bold": False,
        "italic": False,
        "underline": "none",
        "color": "#24324A",
    },
)

# The same paragraph as bare text, so the boundary-space attribution is pinned
# to an independent literal instead of to the readback it is compared with.
EXPECTED_PREFIX_RUN_TEXTS: tuple[str, ...] = tuple(
    str(run["text"]) for run in EXPECTED_PREFIX_RUNS
)
EXPECTED_PREFIX_TEXT = (
    "常规 Regular · 粗体 Bold · 斜体 Italic · 下划线 Underline · 数字 2026 · emoji 🚀"
)

# `North` and `Africa` are adjacent source nodes of the second #mixed-runs
# paragraph: the space belongs to the ` Africa` node, and the two nodes carry
# identical resolved formatting.
EXPECTED_CANONICAL_RUN_TEXTS: tuple[str, ...] = ("Canonical: ", "North Africa")

# `North` and ` Africa` are two adjacent source nodes (data-canonical-part 1
# and 2) with identical resolved formatting, so they are one Canonical Run.
EXPECTED_CANONICAL_RUN: Mapping[str, Any] = {
    "text": "North Africa",
    "font_family": "Georgia",
    "font_size_pt": 15.0,
    "bold": True,
    "italic": False,
    "underline": "none",
    "color": "#0F6B78",
}


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


def _slide_objects(pptx: Path) -> list[dict[str, Any]]:
    document = _run_officecli("get", str(pptx), "/", "--depth", "6")
    slide = document["data"]["results"][0]["children"][0]
    return [
        child
        for child in slide["children"]
        if child["type"] in {"shape", "textbox"}
    ]


def _object_by_name(pptx: Path, name: str) -> dict[str, Any]:
    for child in _slide_objects(pptx):
        if child["format"].get("name") == name:
            return child
    raise AssertionError(f"OfficeCLI readback has no object named {name}")


def _shape_by_source(manifest: Mapping[str, Any], source_object: str) -> dict[str, Any]:
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
    fallback = node.get("format", {})
    paragraphs = []
    for paragraph in node.get("children", []):
        runs = [
            _readback_run(run, paragraph.get("format", fallback))
            for run in paragraph.get("children", [])
            if run["type"] == "run"
        ]
        paragraphs.append(
            {
                "text": paragraph.get("text", ""),
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


# ---------------------------------------------------------------------------
# Tracer bullets on the accepted fixture
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capabilities_declare_the_mixed_run_surface() -> None:
    payload = get_capabilities().as_dict()
    assert payload["status"] == "PASS"
    surface = payload["data"]["contract"]["mixed_run_surface"]

    assert surface["attributes"] == {
        "font_family": "font-family",
        "font_size": "font-size",
        "bold": "font-weight",
        "italic": "font-style",
        "color": "color",
        "underline": "text-decoration",
    }
    assert surface["inline_elements"] == [
        "a",
        "abbr",
        "b",
        "cite",
        "code",
        "del",
        "em",
        "i",
        "kbd",
        "mark",
        "q",
        "s",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "time",
        "u",
        "var",
    ]
    assert surface["canonical_run"] == {
        "scope": "paragraph",
        "requires": [
            "identical resolved formatting",
            "identical supported semantic attributes",
        ],
        "forbidden_across": ["paragraph", "list_item", "hard_break"],
        "range_units": "utf-16-code-units",
    }


def test_contract_check_accepts_the_mixed_run_fixture_without_diagnostics() -> None:
    from officecli_html_to_pptx.contract import check_contract

    report = check_contract(FIXTURE, "author")

    assert report.status == "PASS"
    assert report.diagnostics == ()


@pytest.mark.asyncio
async def test_mixed_runs_build_reads_back_one_object_with_expected_runs(
    tmp_path: Path,
) -> None:
    output = tmp_path / "mixed-runs.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[3]")
    assert manifest_object["kind"] == "textbox"
    # The first source line ends with an authored <br>, so the native body has
    # exactly two paragraphs: the mixed-format line and the canonical line.
    assert manifest_object["text"] == (
        "常规 Regular · 粗体 Bold · 斜体 Italic · 下划线 Underline · "
        "数字 2026 · emoji 🚀\nCanonical: North Africa"
    )
    assert [paragraph["text"] for paragraph in manifest_object["paragraphs"]] == [
        "常规 Regular · 粗体 Bold · 斜体 Italic · 下划线 Underline · "
        "数字 2026 · emoji 🚀",
        "Canonical: North Africa",
    ]

    readback = _object_by_name(output, manifest_object["name"])
    assert readback["type"] == "textbox"
    assert readback["format"]["x"] == "85pt"
    assert readback["format"]["y"] == "125pt"
    assert readback["text"] == manifest_object["text"]

    paragraphs = _readback_paragraphs(readback)
    assert [paragraph["text"] for paragraph in paragraphs] == [
        "常规 Regular · 粗体 Bold · 斜体 Italic · 下划线 Underline · "
        "数字 2026 · emoji 🚀",
        "Canonical: North Africa",
    ]
    assert [_expected_run(run) for run in paragraphs[0]["runs"]] == [
        _expected_run(run) for run in EXPECTED_PREFIX_RUNS
    ]
    # A formatting change is still its own native run boundary: the prefix
    # paragraph must not collapse into a single run.
    assert len(paragraphs[0]["runs"]) == len(EXPECTED_PREFIX_RUNS)


@pytest.mark.asyncio
async def test_boundary_spaces_stay_on_the_run_that_authored_them(
    tmp_path: Path,
) -> None:
    """A collapsed boundary space never migrates into the neighbouring format.

    The authored source of the first #mixed-runs line is
    ``常规 Regular · <strong>粗体 Bold</strong> · <em>斜体 Italic</em> · …``: the
    space after the first ``·`` belongs to the textbox's own text node, and the
    ``" · "`` between the formatted spans belongs to their own text nodes.
    Falling a boundary space back onto the *preceding* run moves it across a
    formatting boundary, so the 15pt space is rendered 17pt bold and the
    underline grows one space wide.  Every expected value below is an
    independent literal from the fixture, never the compiler's own output.
    """
    output = tmp_path / "boundary-space-attribution.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[3]")
    assert [
        run["text"] for run in manifest_object["paragraphs"][0]["runs"]
    ] == list(EXPECTED_PREFIX_RUN_TEXTS)
    assert [
        run["text"] for run in manifest_object["paragraphs"][1]["runs"]
    ] == list(EXPECTED_CANONICAL_RUN_TEXTS)

    readback = _object_by_name(output, manifest_object["name"])
    paragraphs = _readback_paragraphs(readback)
    assert [
        run["text"] for run in paragraphs[0]["runs"]
    ] == list(EXPECTED_PREFIX_RUN_TEXTS)
    # The spaces are attributed, never added or dropped: the paragraph still
    # reads exactly like the authored line.
    assert "".join(EXPECTED_PREFIX_RUN_TEXTS) == EXPECTED_PREFIX_TEXT
    assert paragraphs[0]["text"] == EXPECTED_PREFIX_TEXT
    # The space between <strong> and <em> is the 15pt Segoe UI text node's own,
    # so it stays out of the 17pt bold Georgia run.
    assert [run["font_size_pt"] for run in paragraphs[0]["runs"]] == [
        15.0,
        17.0,
        15.0,
        14.0,
        15.0,
        15.0,
        15.0,
    ]
    assert [run["font_family"] for run in paragraphs[0]["runs"]] == [
        "Segoe UI",
        "Georgia",
        "Segoe UI",
        "Segoe UI",
        "Segoe UI",
        "Segoe UI",
        "Segoe UI",
    ]
    # The underline covers the authored <u> text only, not a trailing space.
    assert [run["underline"] for run in paragraphs[0]["runs"]] == [
        "none",
        "none",
        "none",
        "none",
        "none",
        "single",
        "none",
    ]
    # The second paragraph keeps its two Canonical Runs: "North" + " Africa"
    # is one run with a single internal space, not two runs.
    assert [
        run["text"] for run in paragraphs[1]["runs"]
    ] == list(EXPECTED_CANONICAL_RUN_TEXTS)
    assert paragraphs[1]["text"] == "Canonical: North Africa"


@pytest.mark.asyncio
async def test_adjacent_same_format_sources_read_back_as_one_canonical_run(
    tmp_path: Path,
) -> None:
    output = tmp_path / "canonical-run.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[3]")
    canonical_paragraph = manifest_object["paragraphs"][1]
    assert canonical_paragraph["text"] == "Canonical: North Africa"
    assert [run["text"] for run in canonical_paragraph["runs"]] == [
        "Canonical: ",
        "North Africa",
    ]

    readback = _object_by_name(output, manifest_object["name"])
    paragraphs = _readback_paragraphs(readback)
    assert paragraphs[1]["text"] == "Canonical: North Africa"
    assert [_expected_run(run) for run in paragraphs[1]["runs"]] == [
        _expected_run(
            {
                "text": "Canonical: ",
                "font_family": "Segoe UI",
                "font_size_pt": 15.0,
                "bold": False,
                "italic": False,
                "underline": "none",
                "color": "#24324A",
            }
        ),
        _expected_run(EXPECTED_CANONICAL_RUN),
    ]


@pytest.mark.asyncio
async def test_canonical_merging_never_crosses_a_paragraph_boundary(
    tmp_path: Path,
) -> None:
    html = tmp_path / "paragraph-boundary.html"
    html.write_text(
        """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  .slide { width: 1920px; height: 1080px; position: relative; background: #ffffff; }
  .copy { position: absolute; left: 100px; top: 100px; width: 800px; height: 300px;
          font-family: Georgia, serif; font-size: 30px; font-weight: 700;
          color: #0f6b78; }
</style></head><body><section class="slide active">
  <div class="copy">North<br>Africa</div>
</section></body></html>""",
        encoding="utf-8",
    )
    output = tmp_path / "paragraph-boundary.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[1]")
    assert [paragraph["text"] for paragraph in manifest_object["paragraphs"]] == [
        "North",
        "Africa",
    ]
    assert [
        [run["text"] for run in paragraph["runs"]]
        for paragraph in manifest_object["paragraphs"]
    ] == [["North"], ["Africa"]]

    readback = _object_by_name(output, manifest_object["name"])
    paragraphs = _readback_paragraphs(readback)
    assert [paragraph["text"] for paragraph in paragraphs] == ["North", "Africa"]
    assert [[run["text"] for run in paragraph["runs"]] for paragraph in paragraphs] == [
        ["North"],
        ["Africa"],
    ]
    assert paragraphs[0]["runs"][0]["bold"] is True
    assert paragraphs[1]["runs"][0]["font_family"] == "Georgia"


@pytest.mark.asyncio
async def test_soft_wrapped_paragraph_keeps_browser_visual_lines(
    tmp_path: Path,
) -> None:
    """A CJK soft wrap splits between characters with no space to re-join on."""
    output = tmp_path / "soft-wrap.pptx"

    result = await compile_officecli(str(FIXTURE), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[7]")
    assert [paragraph["text"] for paragraph in manifest_object["paragraphs"]] == [
        "Chromium decides this bilingual soft wrap：浏",
        "览器决定视觉换行，PowerPoint 保留可编辑段",
        "落与原始阅读顺序。",
    ]
    assert (
        "".join(paragraph["text"] for paragraph in manifest_object["paragraphs"])
        == "Chromium decides this bilingual soft wrap：浏览器决定视觉换行，"
        "PowerPoint 保留可编辑段落与原始阅读顺序。"
    )

    readback = _object_by_name(output, manifest_object["name"])
    assert [paragraph["text"] for paragraph in _readback_paragraphs(readback)] == [
        "Chromium decides this bilingual soft wrap：浏",
        "览器决定视觉换行，PowerPoint 保留可编辑段",
        "落与原始阅读顺序。",
    ]


@pytest.mark.asyncio
async def test_later_formatted_runs_stay_aligned_after_an_emoji(tmp_path: Path) -> None:
    """OfficeCLI ranges are UTF-16 code units, so 🚀 advances the offset by two.

    ``before 🚀`` is 9 UTF-16 code units, which is exactly where the second
    range must begin.  A code-point offset model would start the second range
    one unit early and reject the write ("The surrogate pair is invalid") or
    format the wrong characters.
    """
    html = tmp_path / "emoji-alignment.html"
    html.write_text(
        """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  .slide { width: 1920px; height: 1080px; position: relative; background: #ffffff; }
  .copy { position: absolute; left: 100px; top: 100px; width: 900px; height: 200px;
          font-family: "Segoe UI", sans-serif; font-size: 24px; color: #24324a; }
  strong { font-family: Georgia, serif; font-size: 18px; font-weight: 700;
           color: #e60012; }
</style></head><body><section class="slide active">
  <div class="copy">before 🚀<strong>after</strong></div>
</section></body></html>""",
        encoding="utf-8",
    )
    output = tmp_path / "emoji-alignment.pptx"

    result = await compile_officecli(str(html), "author", str(output))

    manifest_object = _shape_by_source(result.manifest, "slide[1]/div[1]")
    assert [paragraph["text"] for paragraph in manifest_object["paragraphs"]] == [
        "before 🚀after"
    ]
    assert [
        [run["text"] for run in paragraph["runs"]]
        for paragraph in manifest_object["paragraphs"]
    ] == [["before 🚀", "after"]]
    assert manifest_object["paragraphs"][0]["runs"][1]["bold"] is True

    readback = _object_by_name(output, manifest_object["name"])
    assert readback["text"] == "before 🚀after"
    paragraphs = _readback_paragraphs(readback)
    assert [paragraph["text"] for paragraph in paragraphs] == ["before 🚀after"]
    assert paragraphs[0]["runs"] == [
        {
            "text": "before 🚀",
            "font_family": "Segoe UI",
            "font_size_pt": 12.0,
            "bold": False,
            "italic": False,
            "underline": "none",
            "color": "#24324A",
        },
        {
            "text": "after",
            "font_family": "Georgia",
            "font_size_pt": 9.0,
            "bold": True,
            "italic": False,
            "underline": "none",
            "color": "#E60012",
        },
    ]
