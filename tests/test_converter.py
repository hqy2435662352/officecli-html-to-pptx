"""Tests for the core conversion pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest
from pptx import Presentation

from html_to_pptx import convert, extract_measurements, render_pptx


@pytest.mark.asyncio
async def test_convert_creates_pptx(minimal_html: Path, tmp_pptx: Path):
    result = await convert(str(minimal_html), str(tmp_pptx))
    assert Path(result).exists()
    assert Path(result).stat().st_size > 0


@pytest.mark.asyncio
async def test_convert_returns_output_path(minimal_html: Path, tmp_pptx: Path):
    result = await convert(str(minimal_html), str(tmp_pptx))
    assert result == str(tmp_pptx)


@pytest.mark.asyncio
async def test_extract_measurements_returns_slides(minimal_html: Path):
    measurements = await extract_measurements(str(minimal_html))
    assert len(measurements) == 2
    for slide in measurements:
        assert "index" in slide
        assert "elements" in slide
        assert "backgroundColor" in slide


@pytest.mark.asyncio
async def test_extract_measurements_captures_text(minimal_html: Path):
    measurements = await extract_measurements(str(minimal_html))

    def find_text(elements: list[dict], target: str) -> bool:
        for el in elements:
            if target in el.get("text", ""):
                return True
            if find_text(el.get("children", []), target):
                return True
        return False

    assert find_text(measurements[0]["elements"], "Title Slide")
    assert find_text(measurements[1]["elements"], "Content Slide")


@pytest.mark.asyncio
async def test_extract_measurements_captures_styles(minimal_html: Path):
    measurements = await extract_measurements(str(minimal_html))
    slide_0 = measurements[0]
    assert slide_0["backgroundColor"] is not None


@pytest.mark.asyncio
async def test_render_pptx_creates_correct_slide_count(minimal_html: Path):
    measurements = await extract_measurements(str(minimal_html))
    prs = render_pptx(measurements)
    assert len(prs.slides) == 2


@pytest.mark.asyncio
async def test_render_pptx_sets_slide_dimensions(minimal_html: Path):
    measurements = await extract_measurements(str(minimal_html))
    prs = render_pptx(measurements)
    from pptx.util import Inches
    assert abs(prs.slide_width - Inches(13.333)) < Inches(0.01)
    assert prs.slide_height == Inches(7.5)


@pytest.mark.asyncio
async def test_render_pptx_adds_shapes(minimal_html: Path):
    measurements = await extract_measurements(str(minimal_html))
    prs = render_pptx(measurements)
    for slide in prs.slides:
        assert len(slide.shapes) > 0


@pytest.mark.asyncio
async def test_saved_pptx_is_valid(minimal_html: Path, tmp_pptx: Path):
    await convert(str(minimal_html), str(tmp_pptx))
    prs = Presentation(str(tmp_pptx))
    assert len(prs.slides) == 2


@pytest.mark.asyncio
async def test_file_not_found_raises():
    with pytest.raises(FileNotFoundError):
        await extract_measurements("/nonexistent/path.html")


@pytest.mark.asyncio
async def test_empty_html_raises(tmp_path: Path):
    empty = tmp_path / "empty.html"
    empty.write_text("<html><body></body></html>")
    with pytest.raises(ValueError, match="No slides found"):
        await extract_measurements(str(empty))
