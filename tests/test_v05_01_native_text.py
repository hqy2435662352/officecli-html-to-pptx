"""Focused Contract 1.1 text-structure acceptance tests for ticket #23."""

from pathlib import Path
import shutil

import pytest

from officecli_html_to_pptx.contract import (
    CANONICAL_RUN_IDENTITY_FIELDS,
    CONTRACT_VERSION,
    OFFICECLI_COMPATIBILITY_BASELINE,
    SOFT_WRAP_MODEL,
    author_capability_manifest,
    check_contract,
)
from officecli_html_to_pptx._internal.officecli_compiler import (
    _paragraphs_text,
    _table_cell_props,
    _text_paragraphs,
    compile_officecli,
)
from officecli_html_to_pptx._internal.acceptance import _officecli_manifest
from officecli_html_to_pptx._internal.pptx_reader import (
    CapturedRun,
    _break_after_offsets,
    _with_line_breaks,
)
from officecli_html_to_pptx.measurement import extract_measurements
from officecli_html_to_pptx.runtime import FORMAL_OFFICECLI_VERSION


FIXTURE = Path(__file__).parent / "fixtures" / "v05_01_native_text.html"


def _element(*, paragraphs, visual_lines=None, font_size=30, line_height="1.35"):
    element = {
        "fontSize": font_size,
        "fontFamily": "Microsoft YaHei",
        "fontWeight": "400",
        "fontStyle": "normal",
        "lineHeight": line_height,
        "opacity": 1,
        "paragraphs": paragraphs,
    }
    if visual_lines is not None:
        element["visualLines"] = visual_lines
    return element


def _paragraph(text, runs=None, **extra):
    return {
        "text": text,
        "align": "left",
        "lineHeight": "1.35",
        "spaceBefore": 0,
        "spaceAfter": 0,
        "direction": "ltr",
        "runs": list(runs if runs is not None else ([{"text": text}] if text else [])),
        **extra,
    }


def test_contract_11_and_officecli_floor_are_published() -> None:
    assert CONTRACT_VERSION == "1.1"
    assert OFFICECLI_COMPATIBILITY_BASELINE == "1.0.151"
    assert FORMAL_OFFICECLI_VERSION == "1.0.151"
    manifest = author_capability_manifest()
    assert manifest["version"] == "1.1"
    assert manifest["paragraph_layout_surface"]["soft_wrap"]["representation"] == (
        "measurement-and-evidence-only"
    )
    assert CANONICAL_RUN_IDENTITY_FIELDS == (
        "font_family",
        "font_size_pt",
        "bold",
        "italic",
        "color",
        "underline",
    )


def test_visual_lines_never_lower_to_native_paragraphs() -> None:
    paragraphs = (_paragraph("one source paragraph", [{"text": "one source paragraph"}]),)
    lowered = _text_paragraphs(
        _element(
            paragraphs=paragraphs,
            visual_lines=["one source", "paragraph"],
        ),
        0.5,
        0.5,
        (255, 255, 255),
    )
    assert len(lowered) == 1
    assert lowered[0]["text"] == "one source paragraph"
    assert _paragraphs_text(lowered) == "one source paragraph"


def test_br_is_one_native_hard_break_inside_one_paragraph() -> None:
    source = _paragraph(
        "A\nB",
        [
            {"text": "A"},
            {"text": "\n", "br": True},
            {"text": "B"},
        ],
    )
    lowered = _text_paragraphs(
        _element(paragraphs=(source,)),
        0.5,
        0.5,
        (255, 255, 255),
    )
    assert len(lowered) == 1
    assert lowered[0]["text"] == "A\vB"
    assert lowered[0]["hard_break_offsets"] == [1]
    assert [run["text"] for run in lowered[0]["runs"]] == ["A", "B"]
    assert _paragraphs_text(lowered) == "A\vB"


def test_table_cell_text_uses_the_same_hard_break_structure() -> None:
    source = _paragraph(
        "A\nB",
        [
            {"text": "A"},
            {"text": "\n", "br": True},
            {"text": "B"},
        ],
    )
    element = _element(paragraphs=(source,))
    lowered = _text_paragraphs(
        element,
        0.5,
        0.5,
        (255, 255, 255),
        preserve_table_projection=True,
    )
    props = _table_cell_props(
        element,
        0.5,
        0.5,
        (255, 255, 255),
        1,
        "slide[1]/table[1]/tr[1]/tc[1]",
        lowered,
    )
    assert props["text"] == "A\vB"


def test_empty_paragraphs_are_not_normalized() -> None:
    source = (
        _paragraph(""),
        _paragraph("content"),
        _paragraph(""),
        _paragraph(""),
    )
    lowered = _text_paragraphs(
        _element(paragraphs=source),
        0.5,
        0.5,
        (255, 255, 255),
    )
    assert [paragraph["text"] for paragraph in lowered] == ["", "content", "", ""]
    assert _paragraphs_text(lowered) == "\ncontent\n\n"


@pytest.mark.parametrize(
    "style, expected_code",
    [
        ("line-height: normal", "unsupported_line_height"),
        ("line-height: 120%", "unsupported_line_height"),
        ("line-height: 2em", "unsupported_line_height"),
        ("line-height: 0px", "unsupported_line_height"),
        ("margin-top: 2em", "unsupported_paragraph_margin"),
        ("margin-bottom: -1px", "unsupported_paragraph_margin"),
        ("text-decoration: line-through", "unsupported_text_decoration"),
        ("text-decoration: underline dotted", "unsupported_text_decoration"),
        ("letter-spacing: 1px", "unsupported_visible_css"),
        ("text-align: distribute", "unsupported_text_alignment"),
    ],
)
def test_newly_explicit_typography_boundaries_block_before_output(
    tmp_path: Path, style: str, expected_code: str
) -> None:
    source = FIXTURE.read_text(encoding="utf-8")
    if style.startswith("text-align"):
        source = source.replace(
            '<div class="text" id="native-text">',
            '<div class="text" id="native-text" style="text-align: distribute">',
        )
    else:
        source = source.replace(
            "font-size: 30px;\n      line-height: 1.35;",
            f"font-size: 30px;\n      line-height: 1.35;\n      {style};",
        )
    path = tmp_path / "invalid.html"
    path.write_text(source, encoding="utf-8")
    report = check_contract(path, "author")
    assert report.blocked
    assert expected_code in {item.code for item in report.diagnostics}


def test_fixture_contains_the_complete_ticket_surface() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    assert 'font-family: "Microsoft YaHei"' in text
    assert "<br>" in text
    assert text.count("<p>") >= 6
    assert (FIXTURE.with_suffix(".acceptance.md")).is_file()


def test_hyperlink_targets_are_outside_the_frozen_run_matrix(tmp_path: Path) -> None:
    source = FIXTURE.read_text(encoding="utf-8").replace(
        "第一段 <span class=\"mixed\">mixed run</span>",
        "第一段 <a href=\"https://example.invalid\"><span class=\"mixed\">mixed run</span></a>",
    )
    path = tmp_path / "hyperlink.html"
    path.write_text(source, encoding="utf-8")
    report = check_contract(path, "author")
    assert report.blocked
    assert "unsupported_hyperlink" in {item.code for item in report.diagnostics}


@pytest.mark.asyncio
async def test_fixture_measurement_keeps_authored_paragraph_topology() -> None:
    measurements = await extract_measurements(str(FIXTURE), officecli_mode=True)
    text_block = measurements[0]["elements"][0]
    paragraphs = text_block["paragraphs"]
    assert text_block["paragraphsFromChildren"] is True
    assert [paragraph["text"] for paragraph in paragraphs] == [
        "",
        "第一段 mixed run before\nhard break after",
        "",
        "第三段：中文字体与软换行保持可编辑。",
        "اتجاه RTL",
        "trailing paragraph",
        "",
        "",
    ]
    assert text_block.get("visualLines") is None


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI is required")
async def test_fixture_officecli_readback_keeps_native_text_evidence(
    tmp_path: Path,
) -> None:
    output = tmp_path / "v05-01-01-native-text.pptx"
    await compile_officecli(str(FIXTURE), "author", str(output))
    manifest, _ = _officecli_manifest(output)
    text_object = next(
        item for item in manifest["objects"] if item["kind"] == "textbox"
    )
    paragraphs = text_object["paragraphs"]
    assert len(paragraphs) == 8
    assert paragraphs[1]["text"] == "第一段 mixed run before\vhard break after"
    assert paragraphs[1]["hard_break_offsets"] == [20]
    assert [index for index, paragraph in enumerate(paragraphs) if not paragraph["text"]] == [
        0,
        2,
        6,
        7,
    ]
    # Standalone text bounds already include the authored block margins.  The
    # compiler therefore keeps them out of native paragraph spacing; native
    # spacing is reserved for folded table-cell paragraphs.
    assert [paragraph["space_after_pt"] for paragraph in paragraphs] == [0.0] * 8
    assert text_object["properties"]["font.ea"] == "Microsoft YaHei"
    # OfficeCLI promotes the first paragraph's native leading to the body
    # summary; paragraph-local readback remains authoritative for the RTL
    # ratio that intentionally omits 1.0x.
    assert text_object["properties"]["lineSpacing"] == "1.35x"
    assert [paragraph["line_spacing"] for paragraph in paragraphs] == [
        "1.35x",
        "1.35x",
        "1.35x",
        "1.35x",
        None,
        "1.35x",
        "1.35x",
        "1.35x",
    ]


def test_readback_restores_consecutive_hard_breaks_without_repartitioning() -> None:
    def run(text: str) -> CapturedRun:
        return CapturedRun(
            text=text,
            font_family="Microsoft YaHei",
            font_size_pt=15.0,
            bold=False,
            italic=False,
            underline="none",
            color="#000000",
        )

    restored = _with_line_breaks(
        (run("A"), run("B")),
        [((1, 1), (1, 1))],
    )
    assert len(restored) == 2
    assert [item.text for item in restored] == ["A\v\v", "B"]


def test_readback_restores_a_break_inside_a_coalesced_run() -> None:
    def run(text: str) -> CapturedRun:
        return CapturedRun(
            text=text,
            font_family="Microsoft YaHei",
            font_size_pt=15.0,
            bold=False,
            italic=False,
            underline="none",
            color="#000000",
        )

    restored = _break_after_offsets((run("AB"),), [1])
    assert [item.text for item in restored] == ["A\vB"]
