"""HTML-to-PPTX slide conversion pipeline.

Converts a structured HTML slide deck into an editable PowerPoint file
by measuring DOM elements in a headless browser and mapping them to
python-pptx shapes.

Pipeline:
  1. Load the HTML in headless Chromium (Playwright)
  2. For each <section class="slide">, measure every visible element's
     bounding box, computed styles, text content, and image data
  3. Map each measurement to a python-pptx shape: text boxes for text
     leaves, picture shapes for base64 images, filled rectangles for
     backgrounds and borders
  4. Save the Presentation as a .pptx file

The HTML canvas is fixed at 1920x1080 CSS pixels. Measurements are
converted to PowerPoint's coordinate system (13.333 x 7.5 inches)
using a fixed px-to-inch ratio.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import tempfile
from typing import Any

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLIDE_WIDTH_INCHES = 13.333
SLIDE_HEIGHT_INCHES = 7.5

SLIDE_CANVAS_WIDTH_PX = 1920
SLIDE_CANVAS_HEIGHT_PX = 1080

PIXELS_TO_INCHES_X = SLIDE_WIDTH_INCHES / SLIDE_CANVAS_WIDTH_PX
PIXELS_TO_INCHES_Y = SLIDE_HEIGHT_INCHES / SLIDE_CANVAS_HEIGHT_PX

_LAYOUT_SCALE = SLIDE_WIDTH_INCHES / (SLIDE_CANVAS_WIDTH_PX / 96.0)
CSS_PX_TO_PT = 0.75 * _LAYOUT_SCALE

MIN_FONT_SIZE_PT = 8
MAX_FONT_SIZE_PT = 72

MAX_HTML_SIZE_MB = 10

PLAYWRIGHT_TIMEOUT_MS = 30_000
FONT_LOAD_WAIT_MS = 1_000


# ---------------------------------------------------------------------------
# DOM measurement script (injected into the page via Playwright)
#
# Shows each slide in isolation (hiding siblings), clears ancestor CSS
# transforms so getBoundingClientRect returns layout-space coordinates,
# then recursively measures every visible element.
#
# Pure containers (no text, no image, no visible background, single child)
# are collapsed to reduce nesting without losing visual information.
# ---------------------------------------------------------------------------

EXTRACTION_JS = """
() => {
    const slides = document.querySelectorAll('.slide');
    const results = [];

    function getDirectText(el) {
        let text = '';
        for (const node of el.childNodes) {
            if (node.nodeType === Node.TEXT_NODE) {
                const t = node.textContent.trim();
                if (t) text += (text ? ' ' : '') + t;
            }
        }
        return text;
    }

    function clearAncestorTransforms(el) {
        const saved = [];
        let current = el;
        while (current && current !== document.documentElement) {
            const computed = getComputedStyle(current);
            if (computed.transform && computed.transform !== 'none') {
                saved.push({el: current, original: current.style.transform});
                current.style.transform = 'none';
            }
            current = current.parentElement;
        }
        return saved;
    }

    function restoreTransforms(saved) {
        for (const item of saved) {
            item.el.style.transform = item.original;
        }
    }

    function measureElement(el, slideRect, depth) {
        if (depth > 15) return null;

        const style = getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return null;
        if (parseFloat(style.opacity) === 0) return null;

        const rect = el.getBoundingClientRect();
        const relX = rect.left - slideRect.left;
        const relY = rect.top - slideRect.top;

        if (rect.width < 1 || rect.height < 1) return null;
        if (relX + rect.width <= 0 || relY + rect.height <= 0) return null;
        if (relX >= slideRect.width || relY >= slideRect.height) return null;

        let directText = getDirectText(el);
        const tag = el.tagName.toLowerCase();

        let markerColor = null;
        if (tag === 'li') {
            const parentTag = el.parentElement ? el.parentElement.tagName.toLowerCase() : '';
            const listStyle = getComputedStyle(el).listStyleType;
            if (parentTag === 'ol') {
                const index = Array.from(el.parentElement.children).indexOf(el) + 1;
                directText = index + '. ' + directText;
            } else if (listStyle !== 'none') {
                directText = '\\u2022 ' + directText;
            }
            try {
                const ms = getComputedStyle(el, '::marker');
                if (ms && ms.color) markerColor = ms.color;
            } catch(e) {}
        }

        const isImg = tag === 'img';
        const hasVisibleBg = style.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                             style.backgroundColor !== 'transparent';
        const hasBorder = style.borderWidth && style.borderWidth !== '0px' &&
                         style.borderStyle !== 'none';

        const data = {
            tag: tag,
            x: relX,
            y: relY,
            width: rect.width,
            height: rect.height,
            text: directText,
            color: style.color,
            backgroundColor: hasVisibleBg ? style.backgroundColor : null,
            fontSize: parseFloat(style.fontSize),
            fontFamily: style.fontFamily,
            fontWeight: style.fontWeight,
            fontStyle: style.fontStyle,
            textAlign: style.textAlign,
            lineHeight: style.lineHeight,
            opacity: parseFloat(style.opacity),
            borderRadius: style.borderRadius,
            borderColor: hasBorder ? style.borderColor : null,
            borderWidth: hasBorder ? parseFloat(style.borderWidth) : 0,
            borderStyle: hasBorder ? style.borderStyle : null,
            borderLeftColor: style.borderLeftColor !== style.borderColor ? style.borderLeftColor : null,
            borderLeftWidth: parseFloat(style.borderLeftWidth) || 0,
            textTransform: style.textTransform,
            backgroundImage: style.backgroundImage !== 'none' ? style.backgroundImage : null,
            isImage: isImg,
            src: isImg ? el.getAttribute('src') : null,
            href: tag === 'a' ? el.getAttribute('href') : null,
            markerColor: markerColor,
            children: []
        };

        for (const child of el.children) {
            if (['script', 'style', 'link', 'meta'].includes(child.tagName.toLowerCase())) continue;
            const childData = measureElement(child, slideRect, depth + 1);
            if (childData) data.children.push(childData);
        }

        const isContainer = !directText && !isImg && !hasVisibleBg && !hasBorder &&
                           data.backgroundImage === null;
        if (isContainer && data.children.length === 1 && depth > 0) {
            return data.children[0];
        }

        return data;
    }

    slides.forEach((slide, slideIndex) => {
        slides.forEach((s, i) => {
            if (i === slideIndex) {
                s.style.display = 'flex';
                s.classList.add('active');
            } else {
                s.style.display = 'none';
                s.classList.remove('active');
            }
        });

        const savedTransforms = clearAncestorTransforms(slide);
        slide.offsetHeight;

        const slideRect = slide.getBoundingClientRect();
        const slideData = {
            index: slideIndex,
            width: slideRect.width,
            height: slideRect.height,
            backgroundColor: getComputedStyle(slide).backgroundColor,
            elements: []
        };

        for (const child of slide.children) {
            if (['script', 'style', 'link', 'meta'].includes(child.tagName.toLowerCase())) continue;
            const measured = measureElement(child, slideRect, 0);
            if (measured) slideData.elements.push(measured);
        }

        restoreTransforms(savedTransforms);
        results.push(slideData);
    });

    return results;
}
"""


# ---------------------------------------------------------------------------
# Color and font parsing
# ---------------------------------------------------------------------------

_RGB_RE = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)"
)


def _css_color_to_rgb(css_color: str) -> tuple[RGBColor, float] | None:
    """Parse a CSS color string to (RGBColor, opacity). Returns None for transparent."""
    if not css_color or css_color == "transparent":
        return None
    match = _RGB_RE.match(css_color)
    if match:
        r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
        a = float(match.group(4)) if match.group(4) else 1.0
        if a < 0.01:
            return None
        return RGBColor(r, g, b), a
    if css_color.startswith("#"):
        h = css_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)), 1.0
    return None


def _parse_font_family(css_font: str) -> str:
    """Extract the first font family name from a CSS font-family string."""
    first = css_font.split(",")[0].strip()
    return first.strip("'\"")


# ---------------------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------------------


def _add_image_from_data_uri(slide: Any, data_uri: str, left: int, top: int, width: int, height: int) -> Any | None:
    """Decode a base64 data URI and add it as a picture shape."""
    match = re.match(r"data:image/(\w+);base64,(.*)", data_uri, re.DOTALL)
    if not match:
        return None
    ext = match.group(1)
    try:
        img_bytes = base64.b64decode(match.group(2))
    except Exception:
        logger.warning("Failed to decode base64 image data")
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
    try:
        tmp.write(img_bytes)
        tmp.close()
        return slide.shapes.add_picture(tmp.name, left, top, width, height)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Element tree helpers
# ---------------------------------------------------------------------------


def _any_descendant_has_text(el: dict) -> bool:
    """True if any child/grandchild has non-empty direct text."""
    for child in el.get("children", []):
        if child.get("text", "").strip():
            return True
        if _any_descendant_has_text(child):
            return True
    return False


def _count_elements(elements: list[dict]) -> int:
    """Count total elements in a measurement tree (including nested children)."""
    total = len(elements)
    for el in elements:
        total += _count_elements(el.get("children", []))
    return total


# ---------------------------------------------------------------------------
# PPTX rendering helpers
# ---------------------------------------------------------------------------


def _apply_font(
    run: Any,
    *,
    size_pt: float,
    color: RGBColor,
    bold: bool,
    italic: bool,
    family: str,
) -> None:
    """Apply font properties to a text run."""
    run.font.size = Pt(size_pt)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = family


def _parse_border_radius_px(el: dict) -> float:
    """Extract border-radius in pixels from an element measurement."""
    br = el.get("borderRadius", "0")
    if not br:
        return 0
    try:
        return float(str(br).replace("px", "").strip().split()[0])
    except (ValueError, IndexError):
        return 0


def _set_corner_radius(
    shape: Any, radius_px: float, width_px: float, height_px: float,
) -> None:
    """Set rounded-rectangle corner radius via the OOXML 'adj' guide.

    The guide value is a ratio of the minimum dimension:
    50000 = fully rounded (pill shape), 0 = sharp corners.
    """
    min_dim = min(width_px, height_px)
    if min_dim <= 0:
        return
    ratio = min(radius_px / min_dim, 0.5)
    adj_val = int(ratio * 100000)

    prstGeom = shape._element.find(".//" + qn("a:prstGeom"))
    if prstGeom is None:
        return
    avLst = prstGeom.find(qn("a:avLst"))
    if avLst is None:
        avLst = etree.SubElement(prstGeom, qn("a:avLst"))
    for old in avLst.findall(qn("a:gd")):
        avLst.remove(old)
    gd = etree.SubElement(avLst, qn("a:gd"))
    gd.set("name", "adj")
    gd.set("fmla", f"val {adj_val}")


def _apply_fill_alpha(shape_or_txbox: Any, alpha: float) -> None:
    """Set fill opacity via OOXML alpha child element.

    OOXML represents alpha as a child of srgbClr:
      <a:srgbClr val="0F172A"><a:alpha val="70000"/></a:srgbClr>
    Value is in 1/100000ths (70000 = 70% opacity).
    """
    srgb = shape_or_txbox._element.find(".//" + qn("a:srgbClr"))
    if srgb is not None:
        for old in srgb.findall(qn("a:alpha")):
            srgb.remove(old)
        alpha_el = etree.SubElement(srgb, qn("a:alpha"))
        alpha_el.set("val", str(int(alpha * 100000)))


def _render_bg_shape(
    slide: Any,
    el: dict,
    x_in: float,
    y_in: float,
    w_in: float,
    h_in: float,
    opacity: float,
) -> None:
    """Render a background/border rectangle (optionally rounded)."""
    bg_result = _css_color_to_rgb(el.get("backgroundColor", ""))
    has_fill = bg_result is not None

    border_color_str = el.get("borderColor")
    border_width = el.get("borderWidth", 0)
    has_border = bool(border_color_str) and border_width > 0

    if not has_fill and not has_border:
        return

    radius_px = _parse_border_radius_px(el)
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius_px > 0 else MSO_SHAPE.RECTANGLE

    shape = slide.shapes.add_shape(
        shape_type,
        Inches(x_in), Inches(y_in),
        Inches(w_in), Inches(h_in),
    )

    if radius_px > 0:
        _set_corner_radius(
            shape, radius_px, el.get("width", 100), el.get("height", 100),
        )

    if has_fill:
        bg_color, bg_alpha = bg_result
        effective_alpha = bg_alpha * opacity
        shape.fill.solid()
        shape.fill.fore_color.rgb = bg_color
        if effective_alpha < 0.99:
            _apply_fill_alpha(shape, effective_alpha)
    else:
        shape.fill.background()

    if has_border:
        border_result = _css_color_to_rgb(border_color_str)
        if border_result:
            shape.line.color.rgb = border_result[0]
            shape.line.width = Pt(border_width * _LAYOUT_SCALE)
    else:
        shape.line.fill.background()

    left_border_color = el.get("borderLeftColor")
    left_border_width = el.get("borderLeftWidth", 0)
    if left_border_color and left_border_width > 2:
        left_result = _css_color_to_rgb(left_border_color)
        if left_result:
            bar_w = left_border_width * PIXELS_TO_INCHES_X * 1.5
            bar = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(x_in), Inches(y_in),
                Inches(bar_w), Inches(h_in),
            )
            bar.fill.solid()
            bar.fill.fore_color.rgb = left_result[0]
            bar.line.fill.background()


def _render_text_element(
    slide: Any,
    el: dict,
    x_in: float,
    y_in: float,
    w_in: float,
    h_in: float,
    has_bg: bool,
    opacity: float,
) -> None:
    """Render a text box, optionally with a background fill."""
    text = el["text"].strip()

    transform = el.get("textTransform", "none")
    if transform == "uppercase":
        text = text.upper()
    elif transform == "lowercase":
        text = text.lower()
    elif transform == "capitalize":
        text = text.title()

    font_size_pt = el.get("fontSize", 20) * CSS_PX_TO_PT
    font_size_pt = max(MIN_FONT_SIZE_PT, min(font_size_pt, MAX_FONT_SIZE_PT))

    min_text_height = font_size_pt * 1.5 / 72
    h_in = max(h_in, min_text_height)

    color_result = _css_color_to_rgb(el.get("color", "rgb(255,255,255)"))
    font_color = color_result[0] if color_result else RGBColor(0xFF, 0xFF, 0xFF)

    font_family = _parse_font_family(el.get("fontFamily", "Calibri"))
    is_bold = el.get("fontWeight", "400") in ("bold", "600", "700", "800", "900")
    is_italic = el.get("fontStyle", "normal") == "italic"

    alignment = {
        "center": PP_ALIGN.CENTER,
        "right": PP_ALIGN.RIGHT,
        "justify": PP_ALIGN.JUSTIFY,
    }.get(el.get("textAlign", "left"), PP_ALIGN.LEFT)

    radius_px = _parse_border_radius_px(el)

    if has_bg and radius_px > 0:
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
        )
        _set_corner_radius(
            shape, radius_px, el.get("width", 100), el.get("height", 100),
        )
        bg_result = _css_color_to_rgb(el["backgroundColor"])
        if bg_result:
            shape.fill.solid()
            shape.fill.fore_color.rgb = bg_result[0]
            if bg_result[1] * opacity < 0.99:
                _apply_fill_alpha(shape, bg_result[1] * opacity)
        shape.line.fill.background()
        tf = shape.text_frame
    else:
        txbox = slide.shapes.add_textbox(
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
        )
        if has_bg:
            bg_result = _css_color_to_rgb(el["backgroundColor"])
            if bg_result:
                txbox.fill.solid()
                txbox.fill.fore_color.rgb = bg_result[0]
                if bg_result[1] * opacity < 0.99:
                    _apply_fill_alpha(txbox, bg_result[1] * opacity)
        tf = txbox.text_frame

    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    p = tf.paragraphs[0]

    marker_color_str = el.get("markerColor")
    has_bullet = text.startswith("\u2022 ") or (
        len(text) >= 3 and text[0].isdigit() and text[:3].rstrip().endswith(".")
    )

    primary_run: Any
    if marker_color_str and has_bullet:
        marker_result = _css_color_to_rgb(marker_color_str)
        if marker_result and text.startswith("\u2022 "):
            bullet_run = p.add_run()
            bullet_run.text = "\u2022 "
            _apply_font(
                bullet_run,
                size_pt=font_size_pt,
                color=marker_result[0],
                bold=is_bold,
                italic=False,
                family=font_family,
            )
            primary_run = p.add_run()
            primary_run.text = text[2:]
        else:
            primary_run = p.add_run()
            primary_run.text = text
    else:
        primary_run = p.add_run()
        primary_run.text = text

    _apply_font(
        primary_run,
        size_pt=font_size_pt,
        color=font_color,
        bold=is_bold,
        italic=is_italic,
        family=font_family,
    )

    p.alignment = alignment

    href = el.get("href")
    if href and not href.startswith("#"):
        try:
            primary_run.hyperlink.address = href
        except Exception:
            pass


# ---------------------------------------------------------------------------
# PPTX rendering (element tree -> slide shapes)
# ---------------------------------------------------------------------------


def _render_measured_element(slide: Any, el: dict) -> None:
    """Render a single measured element onto a PPTX slide.

    Traversal strategy (leaf-only text rendering):
    - Image -> render picture shape, stop
    - Text leaf (has text, no descendant text) -> render text box, stop
    - Non-leaf with background -> render background shape, recurse children
    - Pure container -> recurse children only

    This prevents double-rendering where a parent's text box would overlap
    with its children's text boxes at the same position.
    """
    x_in = el["x"] * PIXELS_TO_INCHES_X
    y_in = el["y"] * PIXELS_TO_INCHES_Y
    w_in = el["width"] * PIXELS_TO_INCHES_X
    h_in = el["height"] * PIXELS_TO_INCHES_Y

    if x_in >= SLIDE_WIDTH_INCHES or y_in >= SLIDE_HEIGHT_INCHES:
        return
    if x_in + w_in <= 0 or y_in + h_in <= 0:
        return

    if x_in < 0:
        w_in += x_in
        x_in = 0
    if y_in < 0:
        h_in += y_in
        y_in = 0
    w_in = min(w_in, SLIDE_WIDTH_INCHES - x_in)
    h_in = min(h_in, SLIDE_HEIGHT_INCHES - y_in)

    if w_in < 0.01 or h_in < 0.01:
        return

    is_image = el.get("isImage", False)
    has_bg = el.get("backgroundColor") is not None
    has_border = bool(el.get("borderColor")) and el.get("borderWidth", 0) > 0
    has_text = bool(el.get("text", "").strip())
    children = el.get("children", [])
    opacity = el.get("opacity", 1.0)

    if is_image and el.get("src", "").startswith("data:image/"):
        _add_image_from_data_uri(
            slide, el["src"],
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
        )
        return

    is_text_leaf = has_text and not _any_descendant_has_text(el)
    if is_text_leaf:
        _render_text_element(slide, el, x_in, y_in, w_in, h_in, has_bg, opacity)
        return

    if has_bg or has_border:
        _render_bg_shape(slide, el, x_in, y_in, w_in, h_in, opacity)

    for child in children:
        _render_measured_element(slide, child)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract_measurements(html_path: str) -> list[dict]:
    """Open an HTML slide deck in headless Chromium and measure every element.

    Each ``<section class="slide">`` is shown in isolation. For every visible
    DOM node, the function records its bounding box, computed styles, text
    content, font properties, colors, borders, and embedded images.

    Args:
        html_path: Path to the HTML file.

    Returns:
        List of slide measurement dicts, each containing:
          - ``index``, ``width``, ``height``, ``backgroundColor``
          - ``elements``: recursive tree of measured DOM nodes

    Raises:
        FileNotFoundError: If *html_path* does not exist.
        ValueError: If the file exceeds the size limit or contains no slides.
    """
    from playwright.async_api import async_playwright

    abs_path = os.path.abspath(html_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"HTML file not found: {abs_path}")

    file_size_mb = os.path.getsize(abs_path) / (1024 * 1024)
    if file_size_mb > MAX_HTML_SIZE_MB:
        raise ValueError(
            f"HTML file is {file_size_mb:.1f} MB, exceeds {MAX_HTML_SIZE_MB} limit"
        )

    logger.info("Loading %s (%.1f MB)", abs_path, file_size_mb)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={
                "width": SLIDE_CANVAS_WIDTH_PX,
                "height": SLIDE_CANVAS_HEIGHT_PX,
            },
        )

        await page.goto(
            f"file://{abs_path}",
            wait_until="networkidle",
            timeout=PLAYWRIGHT_TIMEOUT_MS,
        )
        await page.wait_for_timeout(FONT_LOAD_WAIT_MS)

        measurements = await page.evaluate(EXTRACTION_JS)
        await browser.close()

    if not measurements:
        raise ValueError(
            'No slides found. Ensure the HTML contains <section class="slide"> elements.'
        )

    total_elements = sum(
        _count_elements(s.get("elements", [])) for s in measurements
    )
    logger.info(
        "Extracted %d slides, %d total elements", len(measurements), total_elements,
    )
    return measurements


def render_pptx(measurements: list[dict]) -> Presentation:
    """Convert DOM measurements into a python-pptx Presentation.

    Takes the output of :func:`extract_measurements` and builds an editable
    PowerPoint file with one slide per measurement entry. Each measured DOM
    element is mapped to the closest PPTX shape: text boxes for text, picture
    shapes for images, filled rectangles for backgrounds and borders.

    Args:
        measurements: Output of :func:`extract_measurements`.

    Returns:
        A :class:`pptx.Presentation` ready to be saved with ``prs.save(path)``.
    """
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_WIDTH_INCHES)
    prs.slide_height = Inches(SLIDE_HEIGHT_INCHES)
    blank_layout = prs.slide_layouts[6]

    for slide_data in measurements:
        slide = prs.slides.add_slide(blank_layout)

        bg_result = _css_color_to_rgb(slide_data.get("backgroundColor", ""))
        if bg_result:
            bg_color, _ = bg_result
            fill = slide.background.fill
            fill.solid()
            fill.fore_color.rgb = bg_color

        for el in slide_data.get("elements", []):
            _render_measured_element(slide, el)

    return prs


async def convert(input_html: str, output_pptx: str = "output.pptx") -> str:
    """Convert an HTML slide deck to an editable PPTX file.

    This is the high-level convenience function that runs the full pipeline:
    measure DOM elements in a headless browser, then render them as PPTX shapes.

    Args:
        input_html: Path to the HTML file containing ``<section class="slide">``
            elements.
        output_pptx: Path where the ``.pptx`` file will be written.
            Defaults to ``"output.pptx"``.

    Returns:
        The *output_pptx* path.

    Raises:
        FileNotFoundError: If *input_html* does not exist.
        ValueError: If the file exceeds the size limit or contains no slides.
    """
    measurements = await extract_measurements(input_html)
    prs = render_pptx(measurements)
    prs.save(output_pptx)

    file_size_mb = os.path.getsize(output_pptx) / (1024 * 1024)
    logger.info(
        "Saved %s (%.1f MB, %d slides)",
        output_pptx, file_size_mb, len(measurements),
    )
    return output_pptx
