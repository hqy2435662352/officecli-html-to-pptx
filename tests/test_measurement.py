"""Measurement input-size behaviour.

Author HTML inlines pictures as ``data:image/...`` URIs, so a real business deck
routinely reaches tens or hundreds of megabytes.  An undocumented hardcoded
10 MB cap used to reject those inputs before Chromium was ever launched, while
the pipeline itself handles them (a 204.4 MB / 27-slide deck measures and
compiles).  These tests pin the absence of that cap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import officecli_html_to_pptx.measurement as measurement


def _playwright_available() -> bool:
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:  # pragma: no cover - dependency is declared
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _playwright_available(),
    reason="Playwright Chromium is required for measurement",
)


def _slide(css_probe: str = "") -> str:
    """One valid 1920x1080 Author slide, optionally carrying extra markup."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  .slide {{ width: 1920px; height: 1080px; position: relative; background: #ffffff; }}
  .copy {{ position: absolute; left: 120px; top: 200px; width: 800px; height: 200px;
          font-family: "Segoe UI", sans-serif; font-size: 40px; color: #172033; }}
</style></head><body>
{css_probe}
<section class="slide active"><div class="copy">Measured</div></section>
</body></html>"""


def test_the_measurement_module_has_no_input_size_cap() -> None:
    """The cap is gone, not merely raised: nothing may reject by file size."""
    assert not hasattr(measurement, "MAX_HTML_SIZE_MB")


@pytest.mark.asyncio
async def test_author_html_far_over_the_old_cap_is_measured(tmp_path: Path) -> None:
    """An 11 MB Author deck measures; the old 10 MB cap rejected it outright."""
    # A body comment outside .slide is not painted, so the measurement result is
    # the same as for the small deck while the file is over the old limit.
    padding = "<!-- " + ("x" * (11 * 1024 * 1024)) + " -->"
    html = tmp_path / "large-deck.html"
    html.write_text(_slide(padding), encoding="utf-8")
    assert html.stat().st_size > 10 * 1024 * 1024

    slides = await measurement.extract_measurements(str(html), officecli_mode=True)

    assert len(slides) == 1
    texts = [
        element.get("text")
        for element in slides[0]["elements"]
        if element.get("text")
    ]
    assert "Measured" in texts
