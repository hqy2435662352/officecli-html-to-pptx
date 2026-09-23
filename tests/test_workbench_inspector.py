from __future__ import annotations

from pathlib import Path

import pytest

from officecli_html_to_pptx.workbench_inspector import apply_text_patch, inspect_text_selection
from officecli_html_to_pptx.workbench_preview import build_preview


def _preview(html: str):
    return build_preview(
        html,
        asset_root=Path.cwd(),
        resource_base_url="http://127.0.0.1/api/asset/",
        preview_origin="http://127.0.0.1",
    )


def _select(html: str, tag: str = "p"):
    preview = _preview(html)
    selection = next(
        entry for entry in preview.source_map.values()
        if entry["kind"] == "text" and entry["tag"] == tag
    )
    return preview, selection


def test_preview_editor_offsets_account_for_textarea_newline_normalization() -> None:
    html = '<!doctype html>\r\n<html><head></head><body>\r\n<section class="slide">\r\n<p>Text</p>\r\n</section></body></html>'
    _, selection = _select(html)
    normalized = html.replace("\r\n", "\n")
    assert html[selection["source_start"] : selection["source_end"]].startswith("<p>")
    assert normalized[selection["editor_start"] :].startswith("<p>")
    assert normalized[selection["editor_end"] :].startswith("Text</p>")


def test_text_patch_preserves_markup_and_escapes_unicode_entities_and_quotes() -> None:
    html = (
        '<!doctype html><html><head></head><body><section class="slide">'
        '<p id="target">Old &amp; safe</p><p>Sibling</p>'
        '</section></body></html>'
    )
    _, selection = _select(html)

    patch = apply_text_patch(
        html,
        selection,
        {"kind": "text", "value": '中文 🙂 & <label> "quote"'},
        {"rules_complete": True, "sources": []},
    )

    assert patch["text"] == html.replace(
        "Old &amp; safe",
        "中文 🙂 &amp; &lt;label&gt; &quot;quote&quot;",
    )
    assert patch["diff"].startswith("--- Author HTML (text node)\n+++ Draft (text node)")
    assert "data-workbench-marker" not in patch["text"]


def test_mixed_parent_is_read_only_even_for_direct_property_apply() -> None:
    html = (
        '<!doctype html><html><head></head><body><section class="slide">'
        '<p>Before <strong>emphasized</strong> after</p>'
        '</section></body></html>'
    )
    _, parent = _select(html)
    inspection = inspect_text_selection(
        html,
        parent,
        {"text": "Before emphasized after", "styles": {"color": "rgb(0, 0, 0)"}},
        {"rules_complete": True, "sources": []},
    )

    assert not inspection["writable"]
    assert not inspection["text"]["editable"]
    assert all(not field["editable"] for field in inspection["fields"].values())
    with pytest.raises(ValueError, match="simple text leaf/run"):
        apply_text_patch(html, parent, {"kind": "property", "name": "color", "value": "#123456"}, {"rules_complete": True, "sources": []})


def test_class_rule_property_edit_is_an_object_local_override() -> None:
    html = (
        '<!doctype html><html><head><style>.label { color: #112233; }</style></head><body>'
        '<section class="slide"><p class="label">First</p><p class="label">Second</p></section>'
        '</body></html>'
    )
    _, selection = _select(html)
    matched = {
        "rules_complete": True,
        "sources": [{
            "property": "color", "value": "#112233", "important": False,
            "selector": ".label", "scope": "element",
        }],
    }
    inspection = inspect_text_selection(
        html,
        selection,
        {"text": "First", "styles": {"color": "rgb(17, 34, 51)"}},
        matched,
    )

    assert inspection["fields"]["color"]["computed"] == "rgb(17, 34, 51)"
    assert ".label: #112233" in inspection["fields"]["color"]["source"]
    assert inspection["fields"]["color"]["editable"]
    assert inspection["fields"]["color"]["local_override"]

    patch = apply_text_patch(html, selection, {"kind": "property", "name": "color", "value": "#445566"}, matched)
    assert patch["local_override"]
    assert '<p class="label" style="color: #445566">First</p>' in patch["text"]
    assert '<p class="label">Second</p>' in patch["text"]
    assert ".label { color: #112233; }" in patch["text"]


@pytest.mark.parametrize(
    ("matched", "reason"),
    [
        ({"rules_complete": True, "sources": [{"property": "color", "value": "#123456", "important": True, "selector": ".label", "scope": "element"}]}, "!important"),
        ({"rules_complete": True, "sources": [{"property": "color", "value": "var(--accent)", "important": False, "selector": ".label", "scope": "element"}]}, "CSS variable"),
        ({"rules_complete": False, "sources": []}, "verify all matched CSS rules"),
    ],
)
def test_unverifiable_cascade_is_read_only_and_never_patched(matched: dict, reason: str) -> None:
    html = '<!doctype html><html><head></head><body><section class="slide"><p class="label">Text</p></section></body></html>'
    _, selection = _select(html)
    inspection = inspect_text_selection(html, selection, {"text": "Text", "styles": {"color": "#123456"}}, matched)

    assert not inspection["fields"]["color"]["editable"]
    assert reason.lower() in inspection["fields"]["color"]["reason"].lower()
    with pytest.raises(ValueError, match=reason):
        apply_text_patch(html, selection, {"kind": "property", "name": "color", "value": "#abcdef"}, matched)


def test_property_value_domains_fail_closed_before_source_mutation() -> None:
    html = '<!doctype html><html><head></head><body><section class="slide"><p>Text</p></section></body></html>'
    _, selection = _select(html)
    for name, value in (
        ("font-size", "0px"),
        ("font-size", "-2pt"),
        ("color", "red"),
        ("font-weight", "bolder"),
        ("font-style", "oblique"),
        ("text-align", "initial"),
    ):
        with pytest.raises(ValueError):
            apply_text_patch(html, selection, {"kind": "property", "name": name, "value": value}, {"rules_complete": True, "sources": []})
    assert html.startswith('<!doctype html>')


def test_text_alignment_requires_a_verified_text_container_display() -> None:
    html = (
        '<!doctype html><html><head></head><body><section class="slide">'
        '<p>Block text</p><span>Inline run</span>'
        '</section></body></html>'
    )
    _, block = _select(html, "p")
    _, inline = _select(html, "span")
    matched = {"rules_complete": True, "sources": []}

    block_inspection = inspect_text_selection(
        html, block, {"text": "Block text", "styles": {"display": "block", "text-align": "left"}}, matched
    )
    inline_inspection = inspect_text_selection(
        html, inline, {"text": "Inline run", "styles": {"display": "inline", "text-align": "left"}}, matched
    )

    assert block_inspection["fields"]["text-align"]["editable"]
    assert not inline_inspection["fields"]["text-align"]["editable"]
    assert "block or table-cell" in inline_inspection["fields"]["text-align"]["reason"]


def test_inline_important_longhand_and_shorthand_remain_read_only() -> None:
    html = (
        '<!doctype html><html><head></head><body><section class="slide">'
        '<p style="color: #112233 !important; font: bold 14px Arial !important">Text</p>'
        '</section></body></html>'
    )
    _, selection = _select(html)
    matched = {
        "rules_complete": True,
        "sources": [
            {"property": "color", "value": "#112233", "important": True, "selector": "element.style", "scope": "element"},
            {"property": "font", "value": "bold 14px Arial", "important": True, "selector": "element.style", "scope": "element"},
        ],
    }
    inspection = inspect_text_selection(
        html,
        selection,
        {"text": "Text", "styles": {"color": "rgb(17, 34, 51)", "font-size": "14px", "display": "block"}},
        matched,
    )

    assert not inspection["fields"]["color"]["editable"]
    assert not inspection["fields"]["font-size"]["editable"]
    with pytest.raises(ValueError, match="!important"):
        apply_text_patch(html, selection, {"kind": "property", "name": "color", "value": "#445566"}, matched)
    with pytest.raises(ValueError, match="!important"):
        apply_text_patch(html, selection, {"kind": "property", "name": "font-size", "value": "16px"}, matched)
