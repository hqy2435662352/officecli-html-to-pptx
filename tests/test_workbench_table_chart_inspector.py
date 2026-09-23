from __future__ import annotations

import json
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from playwright.async_api import async_playwright, expect

from officecli_html_to_pptx.contract import build_logical_table_grid
from officecli_html_to_pptx.workbench import WorkbenchError, WorkbenchSession
from officecli_html_to_pptx.workbench_inspector_objects import (
    apply_chart_patch,
    apply_table_patch,
    inspect_chart_selection,
    inspect_table_selection,
)
from officecli_html_to_pptx.workbench_preview import build_preview


def _preview(html: str):
    return build_preview(
        html,
        asset_root=Path.cwd(),
        resource_base_url="http://127.0.0.1/api/asset/",
        preview_origin="http://127.0.0.1",
    )


def _chart_html(chart_type: str, series_count: int = 1, chart_id: str = "chart") -> str:
    categories = ["North", "South"]
    series = [
        {"name": f"Series {index + 1}", "values": [index + 2, index + 3], "color": f"#{index + 1:02X}2233"}
        for index in range(series_count)
    ]
    if chart_type in {"pie", "doughnut"}:
        series = [series[0]]
        series[0]["values"] = [3, 2]
    spec = {
        "type": chart_type,
        "categories": categories,
        "series": series,
        "presentation": {"title": f"{chart_type.title()} title", "legend": "bottom", "labels": "value"},
    }
    return (
        f'<div id="{chart_id}" data-pptx-chart style="width:520px;height:260px">'
        f'<script type="application/json" data-pptx-chart-spec>{json.dumps(spec, separators=(",", ":"))}</script>'
        "</div>"
    )


def test_table_anchor_text_and_fill_patches_preserve_merge_topology() -> None:
    html = (
        '<!doctype html><html><head></head><body><section class="slide">'
        '<table id="sales"><tbody>'
        '<tr><td id="merged" rowspan="2" colspan="2" style="color:#000000">Anchor</td><td>North</td></tr>'
        '<tr><td>South</td></tr>'
        '</tbody></table></section></body></html>'
    )
    original = _preview(html)
    anchor = next(entry for entry in original.source_map.values() if entry.get("attributes", {}).get("id") == "merged")
    assert anchor["kind"] == "table-cell"
    assert anchor["table_cell"]["ownership"] == "anchor"
    assert anchor["table_cell"]["topology"] == [1, 1, 2, 2]
    computed = {"text": "Anchor", "styles": {"background-color": "rgba(0, 0, 0, 0)", "display": "table-cell"}}
    matched = {"rules_complete": True, "sources": []}
    inspector = inspect_table_selection(html, anchor, computed, matched)
    assert inspector["text"]["editable"]
    assert inspector["fields"]["background-color"]["editable"]

    text_patch = apply_table_patch(html, anchor, {"kind": "text", "value": "Merged update"}, matched)
    fill_preview = _preview(text_patch["text"])
    fill_anchor = next(entry for entry in fill_preview.source_map.values() if entry.get("attributes", {}).get("id") == "merged")
    fill_patch = apply_table_patch(
        text_patch["text"],
        fill_anchor,
        {"kind": "property", "name": "background-color", "value": "#112233"},
        matched,
    )
    assert 'rowspan="2" colspan="2"' in fill_patch["text"]
    assert 'background-color: #112233' in fill_patch["text"]
    assert "North</td>" in fill_patch["text"] and "South</td>" in fill_patch["text"]
    assert fill_patch["local_override"]

    after = _preview(fill_patch["text"])
    anchor_after = next(entry for entry in after.source_map.values() if entry.get("attributes", {}).get("id") == "merged")
    assert anchor_after["table_cell"]["topology"] == original.source_map[anchor["marker"]]["table_cell"]["topology"]
    grid = build_logical_table_grid(
        [[{"source_object": "a", "rowspan": "2", "colspan": "2"}, {"source_object": "b"}], [{"source_object": "c"}]],
        source_object="sales",
    )
    assert (grid.rows, grid.columns, grid.regions[0].row_span, grid.regions[0].column_span) == (2, 3, 2, 2)
    assert html not in {text_patch["text"], fill_patch["text"]}


def test_ambiguous_table_merge_is_read_only_and_never_patched() -> None:
    html = (
        '<section class="slide"><table><tr><td>One</td><td rowspan="2">Anchor</td></tr>'
        '<tr><td colspan="2">Covered content</td></tr></table></section>'
    )
    preview = _preview(html)
    cell = next(entry for entry in preview.source_map.values() if entry["kind"] == "table-cell")
    inspection = inspect_table_selection(html, cell, {"styles": {}}, {"rules_complete": True, "sources": []})
    assert not inspection["text"]["editable"]
    assert "covered-cell content" in (inspection["read_only_reason"] or "")
    with pytest.raises(ValueError, match="covered-cell content"):
        apply_table_patch(html, cell, {"kind": "text", "value": "Should not patch"}, {"rules_complete": True, "sources": []})
    assert "Should not patch" not in html


@pytest.mark.parametrize("chart_type,counts", [("column", (1, 2, 3)), ("bar", (1, 2, 3)), ("line", (1, 2, 3)), ("pie", (1,)), ("doughnut", (1,))])
def test_chart_inspector_projects_and_edits_contract_family_and_series_counts(chart_type: str, counts: tuple[int, ...]) -> None:
    html = '<section class="slide">' + "".join(
        _chart_html(chart_type, count, f"chart-{count}") for count in counts
    ) + "</section>"
    preview = _preview(html)
    charts = [entry for entry in preview.source_map.values() if entry["kind"] == "chart"]
    assert len(charts) == len(counts)
    assert f'"type":"{chart_type}"' in preview.html
    if chart_type == "doughnut":
        assert '"hole_size":50' in preview.html
        assert "Hole: ${spec.hole_size}%" in preview.html
    assert f'"aria-label": `${{spec.type}} chart semantic projection' in preview.html
    assert "const chartProjections =" in preview.html
    for count, chart in zip(counts, charts):
        inspector = inspect_chart_selection(html, chart)
        assert inspector["writable"]
        assert inspector["chart"]["type"] == chart_type
        assert len(inspector["chart"]["series"]) == count
        assert len(inspector["chart"]["categories"]) == 2
        assert inspector["fields"]["title"]["computed"] == f"{chart_type.title()} title"
        patch = apply_chart_patch(
            html,
            chart,
            {"kind": "chart", "field": "title", "field_key": "title", "value": f"Edited {chart_type} {count}"},
        )
        updated = _preview(patch["text"])
        updated_chart = next(
            entry
            for entry in updated.source_map.values()
            if entry["kind"] == "chart" and entry.get("attributes", {}).get("id") == chart.get("attributes", {}).get("id")
        )
        updated_inspector = inspect_chart_selection(patch["text"], updated_chart)
        assert updated_inspector["chart"]["title"] == f"Edited {chart_type} {count}"
        assert updated_inspector["chart"]["type"] == chart_type
        assert len(updated_inspector["chart"]["series"]) == count
        assert len(updated_inspector["chart"]["categories"]) == 2
        assert patch["diff"].startswith("--- Author HTML (ChartSpec title)")
        assert "data-workbench-marker" not in patch["text"]


@pytest.mark.parametrize(
    "spec",
    [
        '{"type":"column","type":"line","categories":["A"],"series":[{"name":"S","values":[1]}]}',
        '{"type":"column","categories":["A"],"series":[{"name":"S","values":[1],"mystery":3}]}',
        '{"type":"pie","categories":["A","B"],"series":[{"name":"S","values":[-1,2]}]}',
    ],
)
def test_invalid_or_duplicate_chart_spec_is_read_only(spec: str) -> None:
    html = f'<section class="slide"><div data-pptx-chart><script type="application/json" data-pptx-chart-spec>{spec}</script></div></section>'
    preview = _preview(html)
    chart = next(entry for entry in preview.source_map.values() if entry["kind"] == "chart")
    inspection = inspect_chart_selection(html, chart)
    assert not inspection["writable"]
    with pytest.raises(ValueError):
        apply_chart_patch(html, chart, {"kind": "chart", "field": "title", "value": "No change"})
    assert "No change" not in html


def test_chart_patch_edits_each_supported_field_without_changing_structure() -> None:
    html = '<section class="slide">' + _chart_html("line", 3) + "</section>"
    operations = [
        {"field": "title", "value": "Updated trend"},
        {"field": "category", "index": 0, "value": "West"},
        {"field": "series_name", "series": 1, "value": "Renewals"},
        {"field": "series_value", "series": 0, "index": 0, "value": -4.5},
        {"field": "series_color", "series": 0, "value": "#abcdef"},
        {"field": "legend", "value": "right"},
        {"field": "labels", "value": "value"},
    ]
    for operation in operations:
        preview = _preview(html)
        chart = next(entry for entry in preview.source_map.values() if entry["kind"] == "chart")
        patch = apply_chart_patch(html, chart, {"kind": "chart", "field_key": operation["field"], **operation})
        html = patch["text"]
    final_preview = _preview(html)
    final_chart = next(entry for entry in final_preview.source_map.values() if entry["kind"] == "chart")
    inspected = inspect_chart_selection(html, final_chart)
    semantics = inspected["chart"]
    assert semantics["type"] == "line"
    assert semantics["categories"] == ["West", "South"]
    assert len(semantics["series"]) == 3
    assert semantics["series"][0]["values"][0] == -4.5
    assert semantics["series"][0]["color"] == "#ABCDEF"
    assert semantics["series"][1]["name"] == "Renewals"
    assert semantics["legend"] == "right"
    assert semantics["labels"] == "value"
    assert semantics["title"] == "Updated trend"


def _start(path: Path, recovery_root: Path):
    session = WorkbenchSession.open(path, recovery_root=recovery_root)
    startup = session.start()
    thread = threading.Thread(target=session.serve_forever, daemon=True)
    thread.start()
    for _ in range(100):
        if session.is_running:
            break
        time.sleep(0.01)
    return session, startup, thread


def _api(startup, path: str, payload: dict | None = None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        startup.base_url + path,
        data=body,
        headers={
            "Accept": "application/json",
            "X-Workbench-Token": startup.token,
            "X-Workbench-Session": startup.session_id,
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
        method="POST" if body is not None else "GET",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_chart_inspector_uses_draft_and_preview_cas_and_rejects_stale_edit(tmp_path: Path) -> None:
    html = '<section class="slide">' + _chart_html("bar", 2) + "</section>"
    source = tmp_path / "author.html"
    source.write_text(html, encoding="utf-8")
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, initial = _api(startup, "/api/session")
        assert status == 200
        document = initial["document"]
        status, refreshed = _api(
            startup,
            "/api/preview/refresh",
            {
                "text": html,
                "expected_draft_revision": document["draft_revision"],
                "expected_draft_sha256": document["draft_sha256"],
            },
        )
        assert status == 200 and refreshed["preview"]["status"] == "CURRENT"
        chart = next(entry for entry in refreshed["preview"]["source_map"].values() if entry["kind"] == "chart")
        identity = {
            "preview_revision": refreshed["preview"]["revision"],
            "draft_revision": refreshed["preview"]["draft_revision"],
            "draft_sha256": refreshed["preview"]["draft_sha256"],
        }
        status, selected = _api(startup, "/api/preview/select", {"marker": chart["marker"], **identity})
        assert status == 200
        assert selected["selection"]["inspector"]["chart"]["type"] == "bar"
        status, applied = _api(
            startup,
            "/api/inspector/apply",
            {"marker": chart["marker"], **identity, "intent": {"kind": "chart", "field": "title", "field_key": "title", "value": "CAS edit"}},
        )
        assert status == 200
        assert applied["source_patch"]["draft_revision"] == 1
        assert "CAS edit" in applied["source_patch"]["diff"]
        assert applied["preview"]["status"] == "CURRENT"
        status, stale = _api(
            startup,
            "/api/inspector/apply",
            {"marker": chart["marker"], **identity, "intent": {"kind": "chart", "field": "title", "field_key": "title", "value": "stale edit"}},
        )
        assert status == 409
        assert stale["error"]["code"] == "stale_preview"
        assert "stale edit" not in session.document.text
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.asyncio
async def test_browser_selects_merged_anchor_and_applies_cell_text_diff_save_check(tmp_path: Path) -> None:
    html = (
        '<!doctype html><html><head><style>.slide{width:1920px;height:1080px;display:block}</style></head><body>'
        '<section class="slide"><table style="border-collapse:collapse"><tr>'
        '<td id="anchor" rowspan="2" colspan="2" style="width:300px;height:160px">Anchor</td><td>Top</td></tr>'
        '<tr><td>Bottom</td></tr></table></section></body></html>'
    )
    source = tmp_path / "author.html"
    source.write_text(html, encoding="utf-8")
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.goto(startup.url)
            await page.locator("#preview-frame").wait_for(state="visible")
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=5000)
            preview = page.locator("#preview-frame").content_frame
            anchor = preview.locator("#anchor")
            box = await anchor.bounding_box()
            assert box is not None
            await anchor.click(position={"x": min(10, box["width"] / 2), "y": max(1, box["height"] - 4)}, force=True)
            await expect(page.locator("#inspector-selection")).to_contain_text("table-cell", timeout=5000)
            assert "anchor" not in (await page.locator("#inspector-selection").inner_text()).lower()
            assert await page.locator("#inspector-text").is_enabled()
            await page.locator("#inspector-text").fill("Anchor changed")
            await page.locator("#apply-text").click()
            await expect(page.locator("#source-diff")).to_contain_text("Anchor changed", timeout=5000)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=5000)
            assert source.read_text(encoding="utf-8") == html
            await page.locator("#save").click()
            await expect(page.locator("#state")).to_have_text("SAVED", timeout=5000)
            await page.locator("#check").click()
            await expect(page.locator("#contract-status")).to_have_text("PASS", timeout=10000)
            saved = source.read_text(encoding="utf-8")
            assert 'rowspan="2" colspan="2"' in saved
            assert "Top</td>" in saved and "Bottom</td>" in saved
            assert "data-workbench-marker" not in saved
            await browser.close()
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.asyncio
async def test_browser_chart_family_data_edits_refresh_and_save_check(tmp_path: Path) -> None:
    types = ("column", "bar", "line", "pie", "doughnut")
    charts = []
    for chart_type in types:
        chart = _chart_html(chart_type, 2, f"chart-{chart_type}").replace(
            'style="width:520px;height:260px"',
            'class="chart"',
        )
        charts.append(chart)
    html = (
        '<!doctype html><html><head><style>.slide{width:1920px;height:1080px;display:block}'
        '.charts{display:grid;grid-template-columns:repeat(3,400px);grid-template-rows:repeat(2,220px);gap:20px}'
        '.chart{width:380px;height:180px}</style></head><body><section class="slide"><div class="charts">'
        + "".join(charts)
        + "</div></section></body></html>"
    )
    source = tmp_path / "charts.html"
    source.write_text(html, encoding="utf-8")
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            await page.goto(startup.url)
            await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=5000)
            preview = page.locator("#preview-frame").content_frame
            for chart_type in types:
                await preview.locator(f"#chart-{chart_type} .workbench-chart-projection").click(force=True)
                await expect(page.locator("#inspector-selection")).to_contain_text("chart", timeout=5000)
                category = page.get_by_label("category[1] value")
                await expect(category).to_be_enabled(timeout=5000)
                await category.fill(f"Updated {chart_type}")
                await page.get_by_role("button", name="Apply category[1]").click()
                await expect(page.locator("#source-diff")).to_contain_text(f"Updated {chart_type}", timeout=5000)
                await expect(page.locator("#preview-status")).to_have_attribute("data-status", "CURRENT", timeout=5000)
            await page.locator("#save").click()
            await expect(page.locator("#state")).to_have_text("SAVED", timeout=5000)
            await page.locator("#check").click()
            await expect(page.locator("#contract-status")).to_have_text("PASS", timeout=10000)
            saved = source.read_text(encoding="utf-8")
            for chart_type in types:
                assert f'"type":"{chart_type}"' in saved
                assert f'"Updated {chart_type}"' in saved
            assert "data-workbench-marker" not in saved
            await browser.close()
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()
