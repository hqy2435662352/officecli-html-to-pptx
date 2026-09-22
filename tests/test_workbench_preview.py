"""Public browser/HTTP seams for the Product 0.6.1 live Preview slice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from playwright.async_api import async_playwright, expect

from officecli_html_to_pptx.workbench import WorkbenchSession


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _start(path: Path, recovery_root: Path) -> tuple[WorkbenchSession, object, threading.Thread]:
    session = WorkbenchSession.open(path, recovery_root=recovery_root)
    startup = session.start()
    thread = threading.Thread(target=session.serve_forever, daemon=True)
    thread.start()
    for _ in range(50):
        if session.is_running:
            break
        time.sleep(0.01)
    return session, startup, thread


def _request(
    startup: object,
    method: str,
    path: str,
    *,
    token: str,
    session_id: str | None = None,
    payload: dict | None = None,
) -> tuple[int, dict]:
    url = startup.base_url + path  # type: ignore[attr-defined]
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json", "X-Workbench-Token": token}
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if session_id is not None:
        headers["X-Workbench-Session"] = session_id
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_preview_protocol_renders_unsaved_draft_without_mutating_source(tmp_path: Path) -> None:
    source = tmp_path / "author.html"
    original = "<!doctype html><section class='slide active'><p>saved</p></section>"
    draft = """<!doctype html>
<html><head><style>
.slide { width: 1920px; height: 1080px; display: none; }
.slide.active { display: block; }
</style></head><body>
<section class="slide active"><h1>第一张</h1><img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20'%3E%3Crect width='20' height='20' fill='red'/%3E%3C/svg%3E"></section>
<section class="slide"><table><tr><td>第二张</td></tr></table></section>
</body></html>"""
    original_bytes = original.encode("utf-8")
    source.write_bytes(original_bytes)
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, response = _request(
            startup,
            "POST",
            "/api/preview",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": draft},
        )

        assert status == 200
        assert response["ok"] is True
        preview = response["preview"]
        assert preview["status"] == "CURRENT"
        assert preview["draft_sha256"] == _sha256_bytes(draft.encode("utf-8"))
        assert preview["slide_count"] == 2
        assert preview["html"] != draft
        assert "data-workbench-marker" in preview["html"]
        assert response["document"]["state"] == "DIRTY"
        assert source.read_bytes() == original_bytes
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_preview_source_map_selects_supported_objects_and_is_never_saved(tmp_path: Path) -> None:
    source = tmp_path / "author.html"
    draft = """<!doctype html><html><head><style>
    .slide { width: 1920px; height: 1080px; display: none; }
    .slide.active { display: block; }
    </style></head><body><section class="slide active">
    <p>Text</p><img alt="picture" src="data:image/png;base64,iVBORw0KGgo=">
    <table><tr><td>Cell</td></tr></table>
    <div data-pptx-shape-geometry="roundRect">Shape</div>
    <div data-pptx-chart id="chart"><svg></svg><script type="application/json">{"type":"column"}</script></div>
    <div data-pptx-rasterize="localized"><span>Fallback</span></div>
    </section></body></html>"""
    original = b"<p>disk source remains byte-for-byte</p>\r\n"
    source.write_bytes(original)
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, response = _request(
            startup,
            "POST",
            "/api/preview",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": draft},
        )
        assert status == 200
        assert response["preview"]["status"] == "CURRENT"
        assert {entry["kind"] for entry in response["preview"]["source_map"].values()} >= {
            "text",
            "picture",
            "table",
            "shape",
            "chart",
            "localized-fallback",
        }

        for marker, entry in response["preview"]["source_map"].items():
            status, selected = _request(
                startup,
                "POST",
                "/api/preview/select",
                token=startup.token,
                session_id=startup.session_id,
                payload={"marker": marker, "revision": response["preview"]["revision"]},
            )
            assert status == 200
            assert selected["selection"]["status"] == "mapped"
            assert selected["selection"]["source_start"] == entry["source_start"]
            assert draft[entry["source_start"] :].startswith(f"<{entry['tag']}")

        assert response["document"]["text"] == draft
        assert source.read_bytes() == original
        assert "data-workbench-marker" not in source.read_text(encoding="utf-8")

        status, saved = _request(
            startup,
            "POST",
            "/api/save",
            token=startup.token,
            session_id=startup.session_id,
            payload={"expected_sha256": _sha256_bytes(original), "text": draft},
        )
        assert status == 200
        assert saved["document"]["text"] == draft
        assert source.read_text(encoding="utf-8") == draft
        assert "data-workbench-marker" not in source.read_text(encoding="utf-8")
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_preview_marks_parser_repaired_candidate_unmapped(tmp_path: Path) -> None:
    source = tmp_path / "author.html"
    source.write_text("<p>saved</p>", encoding="utf-8")
    malformed = "<section class='slide'><p>unclosed"
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, response = _request(
            startup,
            "POST",
            "/api/preview",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": malformed},
        )
        assert status == 200
        assert response["preview"]["status"] == "CURRENT"
        assert response["preview"]["parser_repaired"] is True
        assert response["preview"]["source_map"]
        for marker in response["preview"]["source_map"]:
            assert response["preview"]["source_map"][marker]["status"] == "unmapped"
            status, selected = _request(
                startup,
                "POST",
                "/api/preview/select",
                token=startup.token,
                session_id=startup.session_id,
                payload={"marker": marker, "revision": response["preview"]["revision"]},
            )
            assert status == 200
            assert selected["selection"]["status"] == "unmapped"
            assert selected["selection"]["reason"] == "parser_repaired_candidate"
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_preview_becomes_stale_after_edit_and_recovers_after_transient_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "author.html"
    source.write_text("<section class='slide active'><p>saved</p></section>", encoding="utf-8")
    draft = "<section class='slide active'><p>draft</p></section>"
    changed = "<section class='slide active'><p>changed</p></section>"
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, current = _request(
            startup,
            "POST",
            "/api/preview",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": draft},
        )
        assert status == 200
        assert current["preview"]["status"] == "CURRENT"

        status, draft_response = _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": changed},
        )
        assert status == 200
        assert draft_response["preview"]["status"] == "STALE"

        def fail_preview(*args: object, **kwargs: object) -> object:
            raise RuntimeError("simulated browser preview failure")

        monkeypatch.setattr("officecli_html_to_pptx.workbench.build_preview", fail_preview)
        status, failed = _request(
            startup,
            "POST",
            "/api/preview",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": changed},
        )
        assert status == 200
        assert failed["ok"] is False
        assert failed["preview"]["status"] == "ERROR"
        assert "simulated browser preview failure" in failed["preview"]["error"]["message"]
        assert failed["document"]["text"] == changed

        monkeypatch.undo()
        status, recovered = _request(
            startup,
            "POST",
            "/api/preview",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": changed},
        )
        assert status == 200
        assert recovered["ok"] is True
        assert recovered["preview"]["status"] == "CURRENT"
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.asyncio
async def test_browser_preview_has_16_by_9_rail_thumbnails_and_source_selection(tmp_path: Path) -> None:
    source = tmp_path / "author.html"
    source.write_text(
        """<!doctype html><html><head><style>
        .slide { width: 1920px; height: 1080px; display: none; }
        .slide.active { display: block; }
        </style></head><body>
        <section class="slide active"><p>第一张</p></section>
        <section class="slide"><p>第二张</p></section>
        </body></html>""",
        encoding="utf-8",
    )
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            await page.goto(startup.url)
            await page.locator("#preview-frame").wait_for()
            await page.locator("#preview-frame").wait_for(state="visible")
            await page.wait_for_function("() => document.querySelectorAll('#slide-rail [data-slide-index]').length === 2")

            frame_box = await page.locator("#preview-frame").bounding_box()
            assert frame_box is not None
            assert frame_box["width"] / frame_box["height"] == pytest.approx(16 / 9, rel=0.02)
            assert await page.locator("#slide-rail [data-slide-index]").count() == 2
            assert await page.locator("#slide-rail .slide-thumbnail").count() == 2

            await page.locator("#slide-rail [data-slide-index='2']").click()
            await page.wait_for_function(
                "() => document.querySelector('#preview-frame').contentWindow !== null"
            )
            await page.wait_for_timeout(100)
            assert await page.locator("#preview-status").get_attribute("data-status") == "CURRENT"
            main_preview = page.locator("#preview-frame").content_frame
            assert await main_preview.locator(".slide").nth(1).get_attribute("data-workbench-slide-state") == "current"
            thumbnail_frame = page.locator("#slide-rail .slide-thumbnail iframe").nth(0).content_frame
            await thumbnail_frame.locator("body").evaluate(
                """() => window.top.frames[0].postMessage(
                    {channel: 'officecli-workbench-preview', type: 'show-slide', index: 0}, '*'
                )"""
            )
            await page.wait_for_timeout(100)
            assert await main_preview.locator(".slide").nth(1).get_attribute("data-workbench-slide-state") == "current"

            editor = page.locator("#editor")
            draft = await editor.input_value()
            selection_status = page.locator("#selection-status")
            await selection_status.evaluate(
                "element => { element.dataset.mapping = 'unchanged'; element.textContent = 'unchanged'; }"
            )
            await editor.focus()
            await editor.evaluate("element => element.setSelectionRange(1, 1)")
            before_selection = await editor.evaluate("element => [element.selectionStart, element.selectionEnd]")
            await page.evaluate(
                """() => window.postMessage(
                    {channel: 'officecli-workbench-preview', type: 'selection', marker: 'wb-0'}, '*'
                )"""
            )
            await page.wait_for_timeout(250)
            assert await selection_status.get_attribute("data-mapping") == "unchanged"
            assert await selection_status.text_content() == "unchanged"
            assert await editor.evaluate("element => [element.selectionStart, element.selectionEnd]") == before_selection

            await page.locator("#preview-frame").content_frame.locator("p").nth(1).click()
            await page.wait_for_function("() => document.activeElement && document.activeElement.id === 'editor'")
            assert await editor.input_value() == draft
            assert await page.locator("#selection-status").get_attribute("data-mapping") == "mapped"
            await browser.close()
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.asyncio
async def test_browser_preview_enforces_local_data_resource_policy_and_sandbox(tmp_path: Path) -> None:
    source = tmp_path / "author.html"
    local_asset = tmp_path / "inside.svg"
    outside_asset = tmp_path.parent / "outside.svg"
    local_asset.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'><rect width='20' height='20' fill='green'/></svg>",
        encoding="utf-8",
    )
    outside_asset.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'><rect width='20' height='20' fill='red'/></svg>",
        encoding="utf-8",
    )
    source.write_text(
        """<!doctype html><html><head><style>
        .slide { width: 1920px; height: 1080px; display: block; }
        </style><script type=module>window.top.location = 'https://example.com/escape';</script></head><body>
        <section class="slide">
          <img id="local" src=inside.svg>
          <img id="data" src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCI+PHJlY3Qgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiBmaWxsPSJibHVlIi8+PC9zdmc+">
          <img id="public" src=https://example.com/public.png>
          <img id="outside" src="../outside.svg">
          <a id="escape" href="https://example.com/top">escape</a>
        </section>
        </body></html>""",
        encoding="utf-8",
    )
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            public_requests: list[str] = []
            page.on("request", lambda request: public_requests.append(request.url) if "example.com" in request.url else None)
            await page.goto(startup.url)
            await page.locator("#preview-frame").wait_for()
            await page.wait_for_function(
                "() => document.querySelector('#preview-frame').contentWindow !== null"
            )
            await page.wait_for_timeout(400)

            assert await page.locator("#preview-frame").get_attribute("sandbox") == "allow-scripts"
            preview = page.locator("#preview-frame").content_frame
            assert await preview.locator("#local").evaluate("element => element.complete && element.naturalWidth > 0")
            assert await preview.locator("#data").evaluate("element => element.complete && element.naturalWidth > 0")
            assert await preview.locator("#public").get_attribute("src") == "about:blank"
            assert await preview.locator("#outside").get_attribute("src") == "about:blank"
            assert await preview.locator("script[type='application/workbench-blocked']").count() == 1
            assert public_requests == []
            await preview.locator("#escape").click()
            await page.wait_for_timeout(100)
            assert page.url == startup.url
            await browser.close()
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.asyncio
async def test_browser_preview_clicks_each_supported_object_kind_to_source(tmp_path: Path) -> None:
    source = tmp_path / "author.html"
    source.write_text(
        """<!doctype html><html><head><style>
        .slide { width: 1920px; height: 1080px; display: block; position: relative; }
        #picture { width: 20px; height: 20px; }
        #shape, #chart, #localized { position: absolute; left: 100px; width: 240px; height: 120px; }
        #shape { top: 100px; }
        #chart { top: 260px; }
        #localized { top: 420px; }
        </style></head><body><section class="slide">
        <div id="text">Text object</div>
        <img id="picture" src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCI+PC9zdmc+">
        <table id="table"><tr><td>Table</td></tr></table>
        <div id="shape" data-pptx-shape-geometry="roundRect">Shape</div>
        <div id="chart" data-pptx-chart><svg width="100" height="50"><rect width="80" height="40"></rect></svg><script type="application/json">{"type":"column"}</script></div>
        <div id="localized" data-pptx-rasterize="localized"><span>Fallback</span></div>
        </section></body></html>""",
        encoding="utf-8",
    )
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.goto(startup.url)
            await page.wait_for_function("() => document.querySelector('#preview-frame').contentWindow !== null")
            await page.wait_for_timeout(300)
            preview = page.locator("#preview-frame").content_frame
            for selector, kind in (
                ("#text", "text"),
                ("#picture", "picture"),
                ("#table td", "table"),
                ("#shape", "shape"),
                ("#chart svg", "chart"),
                ("#localized span", "localized-fallback"),
            ):
                await preview.locator(selector).click(force=True)
                await expect(page.locator("#selection-status")).to_contain_text(kind, timeout=5000)
                assert await page.locator("#selection-status").get_attribute("data-mapping") == "mapped"
            await browser.close()
    finally:
        session.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()
