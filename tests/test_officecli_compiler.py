"""Public-seam tests for the OfficeCLI shape/text compiler slice."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from html_to_pptx import (
    OfficeCLICompilationError,
    compile_officecli,
)

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the OfficeCLI compiler tests",
)


def _run_json(*args: str) -> dict:
    result = subprocess.run(
        ["officecli", *args, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return json.loads(result.stdout)


def _run_process(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["officecli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _points(value: str) -> float:
    if value.endswith("pt"):
        return float(value[:-2])
    if value.endswith("cm"):
        return float(value[:-2]) * 72 / 2.54
    raise AssertionError(f"unexpected OfficeCLI length: {value}")


def _author_html() -> str:
    return """<!doctype html>
<html><head><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  body { overflow: hidden; font-family: Arial, sans-serif; }
  .slide { width: 960px; height: 540px; display: none; position: relative;
           background: #ffffff; }
  .slide.active { display: block; }
  .card { position: absolute; left: 96px; top: 72px; width: 480px; height: 180px;
          padding: 24px; border: 2px solid #d7d8da; border-radius: 18px;
          background: #fbecee; }
  .card h2 { margin: 0 0 12px; color: #202124; font-size: 30px;
             font-weight: 700; }
  .card p { margin: 0; color: #e60012; font-size: 18px; line-height: 1.5; }
  .accent { position: absolute; left: 624px; top: 72px; width: 6px; height: 180px;
            background: #e60012; }
</style></head><body>
  <section class="slide active">
    <div class="card"><h2>Source Notes</h2><p>Native editable text</p></div>
    <div class="accent"></div>
  </section>
</body></html>"""


@pytest.mark.asyncio
async def test_public_author_compiler_emits_native_shapes_and_text(tmp_path: Path):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(_author_html(), encoding="utf-8")

    result = await compile_officecli(
        str(html_path), "author", str(output_path), slide_indices=[0]
    )

    assert result.output_path == str(output_path)
    assert result.profile == "author"
    assert result.slide_count == 1
    assert output_path.exists()

    validation = _run_process("validate", str(output_path))
    assert validation.returncode == 0, validation.stdout + validation.stderr

    document = _run_json("get", str(output_path), "/")
    slides = document["data"]["results"][0]["children"]
    assert len(slides) == 1
    objects = slides[0]["children"]
    assert not any(item["type"] == "picture" for item in objects)
    assert any(
        item["type"] == "shape"
        and item["format"].get("geometry") == "roundRect"
        and item["format"].get("fill") == "#FBECEE"
        for item in objects
    )
    assert {item["text"] for item in objects if item.get("text")} >= {
        "Source Notes",
        "Native editable text",
    }

    names = [item["format"]["name"] for item in objects]
    assert len(names) == len(set(names))
    assert all(name.startswith("slide-001-") for name in names)


@pytest.mark.asyncio
async def test_public_author_compiler_selects_source_slide_without_rescaling(
    tmp_path: Path,
):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html = _author_html().replace(
        "</body></html>",
        '<section class="slide"><div class="card"><h2>Second</h2></div></section>'
        "</body></html>",
    )
    html_path.write_text(html, encoding="utf-8")

    result = await compile_officecli(
        str(html_path), "author", str(output_path), slide_indices=[1]
    )

    assert result.slide_count == 1
    document = _run_json("get", str(output_path), "/")
    slide = document["data"]["results"][0]["children"][0]
    assert slide["format"]["name"] == "slide-002"
    card = next(
        item
        for item in slide["children"]
        if item["type"] == "shape" and item["format"].get("geometry") == "roundRect"
    )
    assert _points(card["format"]["x"]) == pytest.approx(96)
    assert _points(card["format"]["y"]) == pytest.approx(72)


@pytest.mark.asyncio
async def test_public_author_compiler_does_not_overwrite_existing_output(
    tmp_path: Path,
):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(_author_html(), encoding="utf-8")
    output_path.write_bytes(b"keep this file")

    with pytest.raises(FileExistsError, match="Output already exists"):
        await compile_officecli(
            str(html_path), "author", str(output_path), slide_indices=[0]
        )

    assert output_path.read_bytes() == b"keep this file"


@pytest.mark.asyncio
async def test_unsupported_picture_has_source_diagnostic_and_no_output(
    tmp_path: Path,
):
    html_path = tmp_path / "author.html"
    output_path = tmp_path / "output.pptx"
    html_path.write_text(
        _author_html().replace(
            "<div class=\"accent\"></div>",
            '<img class="accent" src="data:image/png;base64,AA==" '
            'style="width: 12px; height: 12px;" alt="unsupported">',
        ),
        encoding="utf-8",
    )

    with pytest.raises(OfficeCLICompilationError) as error:
        await compile_officecli(
            str(html_path), "author", str(output_path), slide_indices=[0]
        )

    assert "source slide 1" in str(error.value)
    assert "unsupported_picture" in error.value.diagnostics[0].code
    assert error.value.diagnostics[0].source_object
    assert not output_path.exists()
