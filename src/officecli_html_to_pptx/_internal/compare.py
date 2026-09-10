"""Internal visual capture helpers used by the V0.2 build operation.

The public command is implemented in :mod:`officecli_html_to_pptx.cli`.  This
module intentionally contains no standalone comparison command: build owns
the temporary screenshot lifecycle and persists only combined per-slide
Comparison Images in its Evidence Bundle.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

SLIDE_WIDTH_PX = 1920
SLIDE_HEIGHT_PX = 1080


async def screenshot_html_slides(html_path: Path, out_dir: Path) -> list[Path]:
    """Screenshot each <section class="slide"> in the HTML file."""
    from playwright.async_api import async_playwright

    abs_path = str(html_path.resolve())
    screenshots: list[Path] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": SLIDE_WIDTH_PX, "height": SLIDE_HEIGHT_PX},
        )
        await page.goto(
            f"file://{abs_path}", wait_until="networkidle", timeout=30_000,
        )
        await page.wait_for_timeout(1000)

        slide_count = await page.evaluate(
            "document.querySelectorAll('.slide').length"
        )
        if slide_count == 0:
            logger.warning("No .slide sections found in %s", html_path.name)
            await browser.close()
            return screenshots

        for i in range(slide_count):
            await page.evaluate(
                """(idx) => {
                    document.querySelectorAll('.slide').forEach((s, i) => {
                        s.style.display = i === idx ? 'flex' : 'none';
                        if (i === idx) s.classList.add('active');
                        else s.classList.remove('active');
                    });
                }""",
                i,
            )
            await page.wait_for_timeout(200)

            out_path = out_dir / f"html_slide_{i}.png"
            await page.screenshot(path=str(out_path), full_page=False)
            screenshots.append(out_path)

        await browser.close()

    return screenshots


def pptx_to_pngs(pptx_path: Path, out_dir: Path) -> list[Path]:
    """Convert PPTX -> PDF via LibreOffice, then PDF pages -> PNGs via PyMuPDF."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        logger.error(
            "LibreOffice not found. Install it or add 'soffice' to PATH.\n"
            "  macOS:  brew install --cask libreoffice\n"
            "  Ubuntu: sudo apt install libreoffice\n"
        )
        return []

    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf",
         "--outdir", str(out_dir), str(pptx_path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        logger.error("LibreOffice PPTX->PDF failed:\n%s", result.stderr)
        return []

    pdf_path = out_dir / pptx_path.with_suffix(".pdf").name
    if not pdf_path.exists():
        logger.error("Expected PDF not found: %s", pdf_path)
        return []

    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error(
            "PyMuPDF not installed. Run: pip install html-to-pptx[compare]"
        )
        return []

    pngs: list[Path] = []
    doc = fitz.open(str(pdf_path))
    for i in range(len(doc)):
        page = doc[i]
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        png_path = out_dir / f"pptx_slide_{i}.png"
        pix.save(str(png_path))
        pngs.append(png_path)
    doc.close()

    return pngs


def create_comparison(
    html_pngs: list[Path],
    pptx_pngs: list[Path],
    out_dir: Path,
) -> list[Path]:
    """Create side-by-side comparison images (HTML left, PPTX right)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("Pillow not installed. Run: pip install html-to-pptx[compare]")
        return []

    comparisons: list[Path] = []
    count = min(len(html_pngs), len(pptx_pngs))

    for i in range(count):
        html_img = Image.open(str(html_pngs[i])).convert("RGB")
        pptx_img = Image.open(str(pptx_pngs[i])).convert("RGB")

        target_h = max(html_img.height, pptx_img.height)
        if html_img.height != target_h:
            scale = target_h / html_img.height
            html_img = html_img.resize(
                (int(html_img.width * scale), target_h), Image.LANCZOS,
            )
        if pptx_img.height != target_h:
            scale = target_h / pptx_img.height
            pptx_img = pptx_img.resize(
                (int(pptx_img.width * scale), target_h), Image.LANCZOS,
            )

        GAP_PX = 4
        LABEL_HEIGHT_PX = 32
        total_w = html_img.width + GAP_PX + pptx_img.width
        total_h = target_h + LABEL_HEIGHT_PX

        canvas = Image.new("RGB", (total_w, total_h), (240, 240, 240))

        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("Arial", 18)
        except OSError:
            font = ImageFont.load_default()
        slide_number = i + 1
        draw.text((8, 6), f"HTML (slide {slide_number})", fill=(80, 80, 80), font=font)
        draw.text(
            (html_img.width + GAP_PX + 8, 6),
            f"PPTX (slide {slide_number})", fill=(80, 80, 80), font=font,
        )

        canvas.paste(html_img, (0, LABEL_HEIGHT_PX))
        canvas.paste(pptx_img, (html_img.width + GAP_PX, LABEL_HEIGHT_PX))

        out_path = out_dir / f"compare_slide_{i}.png"
        canvas.save(str(out_path))
        comparisons.append(out_path)

    return comparisons
