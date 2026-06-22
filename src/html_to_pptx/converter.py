"""HTML slide deck → editable PPTX converter.

Converts a structured HTML slide deck into an editable PowerPoint file
by measuring DOM elements in a headless browser (Playwright) and mapping
them to python-pptx shapes.

This module has no Agon framework dependencies and can be used standalone.

Pipeline:
  1. Load the HTML in headless Chromium via Playwright
  2. For each <section class="slide">, measure every visible element's
     bounding box, computed styles, text content, and image data
  3. Rasterize inline <svg> elements to PNG via Playwright screenshots
  4. Map each measurement to a python-pptx shape: text boxes, picture
     shapes, gradient fills, rounded rectangles, and translucent overlays
  5. Save the Presentation as a .pptx file

Supported HTML features:
  - CSS linear-gradient backgrounds (solid, transparent stops, any angle)
  - Gradient text fill (-webkit-background-clip: text) → PPTX gradient run
  - Inline <svg> icons → rasterized PNG pictures
  - Rounded corners on images and shapes (border-radius, including %)
  - Translucent overlays (rgba backgrounds with alpha)
  - Mixed inline content (<p>text <strong>bold</strong> more</p>)
  - RTL text direction
  - List markers (bullets and ordered numbers)
  - CSS pseudo-elements (::before/::after) for decorative accents
  - Border-left accent bars

The HTML canvas is fixed at 1920×1080 CSS pixels. Measurements are
converted to PowerPoint's coordinate system (13.333 × 7.5 inches).

Usage as CLI:
    html-to-pptx input.html [output.pptx]

Usage as library:
    from html_to_pptx import convert, extract_measurements, render_pptx

    # Full pipeline
    await convert("slides.html", "output.pptx")

    # Or step by step
    measurements = await extract_measurements("slides.html")
    prs = render_pptx(measurements)
    prs.save("output.pptx")

Requirements:
    pip install python-pptx playwright lxml
    python -m playwright install chromium
"""

from __future__ import annotations

import base64
import logging
import os
import re
import tempfile

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

# Standard widescreen slide dimensions (16:9)
SLIDE_WIDTH_INCHES = 13.333
SLIDE_HEIGHT_INCHES = 7.5

# HTML canvas dimensions — the deck is authored at this fixed resolution
SLIDE_CANVAS_WIDTH_PX = 1920
SLIDE_CANVAS_HEIGHT_PX = 1080

# px-to-inch conversion: Playwright reports CSS pixels, PPTX uses inches
PIXELS_TO_INCHES_X = SLIDE_WIDTH_INCHES / SLIDE_CANVAS_WIDTH_PX
PIXELS_TO_INCHES_Y = SLIDE_HEIGHT_INCHES / SLIDE_CANVAS_HEIGHT_PX

# Font size scaling: CSS px -> PowerPoint pt, adjusted for the same
# layout scale as position coordinates so text proportions match.
# 96 CSS px = 1 inch at standard DPI; the ratio ensures font sizes
# and element positions use the same scale factor.
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

EXTRACTION_JS = r"""
() => {
    const slides = document.querySelectorAll('.slide');
    const results = [];
    let _svgCounter = 0;
    const INLINE_TAGS = new Set([
        'span','strong','em','b','i','a','code','mark','sub','sup',
        'small','u','s','del','abbr','cite','q','time','var','kbd',
    ]);

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

    function collectInlineRuns(el) {
        const runs = [];
        const parentStyle = getComputedStyle(el);
        const nodes = el.childNodes;
        for (let ni = 0; ni < nodes.length; ni++) {
            const node = nodes[ni];
            if (node.nodeType === Node.TEXT_NODE) {
                // Collapse internal whitespace runs to single spaces (browser behavior)
                // but preserve boundary spaces between inline siblings
                let t = node.textContent.replace(/\s+/g, ' ');
                if (ni === 0) t = t.replace(/^\s+/, '');
                if (ni === nodes.length - 1) t = t.replace(/\s+$/, '');
                if (!t) continue;
                runs.push({
                    text: t,
                    color: parentStyle.color,
                    fontSize: parseFloat(parentStyle.fontSize),
                    fontFamily: parentStyle.fontFamily,
                    fontWeight: parentStyle.fontWeight,
                    fontStyle: parentStyle.fontStyle,
                    textTransform: parentStyle.textTransform,
                });
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const tag = node.tagName.toLowerCase();
                if (['script','style','link','meta'].includes(tag)) continue;
                const cs = getComputedStyle(node);
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                if (tag === 'br') {
                    runs.push({ text: '\\n', color: parentStyle.color, fontSize: parseFloat(parentStyle.fontSize), fontFamily: parentStyle.fontFamily, fontWeight: parentStyle.fontWeight, fontStyle: parentStyle.fontStyle, textTransform: 'none' });
                    continue;
                }
                const isInline = cs.display.startsWith('inline') || INLINE_TAGS.has(tag);
                if (isInline) {
                    const text = node.textContent.trim();
                    if (text) {
                        const childBgImage = cs.backgroundImage !== 'none' ? cs.backgroundImage : null;
                        const childFillColor = cs.webkitTextFillColor || '';
                        const childIsGradientText = (childFillColor === 'transparent' || childFillColor === 'rgba(0, 0, 0, 0)') && childBgImage && childBgImage.includes('gradient');
                        runs.push({
                            text: text,
                            color: cs.color,
                            fontSize: parseFloat(cs.fontSize),
                            fontFamily: cs.fontFamily,
                            fontWeight: cs.fontWeight,
                            fontStyle: cs.fontStyle,
                            textTransform: cs.textTransform,
                            href: tag === 'a' ? node.getAttribute('href') : null,
                            isGradientText: childIsGradientText,
                            backgroundImage: childIsGradientText ? childBgImage : null,
                        });
                    }
                }
            }
        }
        return runs;
    }

    function hasChildElementText(el) {
        for (const child of el.children) {
            if (child.textContent && child.textContent.trim()) return true;
        }
        return false;
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
        let markerPrefix = '';
        if (tag === 'li') {
            const parentTag = el.parentElement ? el.parentElement.tagName.toLowerCase() : '';
            const listStyle = getComputedStyle(el).listStyleType;
            if (parentTag === 'ol') {
                const index = Array.from(el.parentElement.children).indexOf(el) + 1;
                markerPrefix = index + '. ';
                directText = markerPrefix + directText;
            } else if (listStyle !== 'none') {
                markerPrefix = '\\u2022 ';
                directText = markerPrefix + directText;
            }
            try {
                const ms = getComputedStyle(el, '::marker');
                if (ms && ms.color) markerColor = ms.color;
            } catch(e) {}
        }

        const isImg = tag === 'img';
        const isSvg = tag === 'svg';
        const hasVisibleBg = style.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                             style.backgroundColor !== 'transparent';
        const hasBorder = style.borderWidth && style.borderWidth !== '0px' &&
                         style.borderStyle !== 'none';

        const bgImage = style.backgroundImage !== 'none' ? style.backgroundImage : null;
        const textFillColor = style.webkitTextFillColor || style.WebkitTextFillColor || '';
        const isFillTransparent = textFillColor === 'transparent' || textFillColor === 'rgba(0, 0, 0, 0)';
        const isGradientText = isFillTransparent && bgImage && bgImage.includes('gradient');

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
            direction: style.direction,
            opacity: parseFloat(style.opacity),
            borderRadius: style.borderRadius,
            borderColor: hasBorder ? style.borderColor : null,
            borderWidth: hasBorder ? parseFloat(style.borderWidth) : 0,
            borderStyle: hasBorder ? style.borderStyle : null,
            borderLeftColor: style.borderLeftColor !== style.borderColor ? style.borderLeftColor : null,
            borderLeftWidth: parseFloat(style.borderLeftWidth) || 0,
            borderLeftStyle: style.borderLeftColor !== style.borderColor ? style.borderLeftStyle : null,
            textTransform: style.textTransform,
            backgroundImage: bgImage,
            isGradientText: isGradientText,
            isImage: isImg,
            isSvg: isSvg,
            src: isImg ? el.getAttribute('src') : null,
            href: tag === 'a' ? el.getAttribute('href') : null,
            markerColor: markerColor,
            children: []
        };

        // Mark inline SVGs for rasterization in the Python post-pass
        if (isSvg) {
            const svgId = 'pptx-svg-' + (_svgCounter++);
            el.setAttribute('data-pptx-id', svgId);
            data.svgId = svgId;
        }

        for (const child of el.children) {
            if (['script', 'style', 'link', 'meta'].includes(child.tagName.toLowerCase())) continue;
            const childData = measureElement(child, slideRect, depth + 1);
            if (childData) data.children.push(childData);
        }

        // Measure ::before and ::after pseudo-elements as synthetic children
        for (const pseudo of ['::before', '::after']) {
            try {
                const ps = getComputedStyle(el, pseudo);
                if (!ps.content || ps.content === 'none' || ps.content === 'normal') continue;
                if (ps.display === 'none') continue;

                const psBg = ps.backgroundColor !== 'rgba(0, 0, 0, 0)' && ps.backgroundColor !== 'transparent';
                const pw = parseFloat(ps.width) || 0;
                const ph = parseFloat(ps.height) || 0;
                if (pw < 1 && ph < 1 && !psBg) continue;

                let px = relX, py = relY;
                const pt = parseFloat(ps.top); const pl = parseFloat(ps.left);
                const pr = parseFloat(ps.right); const pb = parseFloat(ps.bottom);
                if (ps.position === 'absolute') {
                    if (!isNaN(pl)) px = relX + pl;
                    else if (!isNaN(pr)) px = relX + rect.width - pw - pr;
                    if (!isNaN(pt)) py = relY + pt;
                    else if (!isNaN(pb)) py = relY + rect.height - ph - pb;
                }

                if (pw > 0 && ph > 0) {
                    data.children.push({
                        tag: '_pseudo',
                        x: px, y: py, width: pw, height: ph,
                        text: '',
                        color: ps.color,
                        backgroundColor: psBg ? ps.backgroundColor : null,
                        backgroundImage: ps.backgroundImage !== 'none' ? ps.backgroundImage : null,
                        fontSize: 0, fontFamily: '', fontWeight: '400', fontStyle: 'normal',
                        textAlign: 'left', lineHeight: 'normal', direction: 'ltr',
                        opacity: parseFloat(ps.opacity), borderRadius: ps.borderRadius,
                        borderColor: null, borderWidth: 0, borderStyle: null,
                        borderLeftColor: null, borderLeftWidth: 0, borderLeftStyle: null,
                        textTransform: 'none', isImage: false, src: null, href: null,
                        markerColor: null, children: [], isGradientText: false,
                    });
                }
            } catch(e) {}
        }

        if (directText && hasChildElementText(el)) {
            const runs = collectInlineRuns(el);
            if (runs.length > 0) {
                if (markerPrefix && runs.length > 0) {
                    runs[0].text = markerPrefix + runs[0].text;
                }
                data.inlineRuns = runs;
                data.text = '';
            }
        }

        const isContainer = !data.text && !isImg && !isSvg && !hasVisibleBg && !hasBorder &&
                           data.backgroundImage === null && !data.inlineRuns;
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
        const slideStyle = getComputedStyle(slide);
        const slideData = {
            index: slideIndex,
            width: slideRect.width,
            height: slideRect.height,
            backgroundColor: slideStyle.backgroundColor,
            backgroundImage: slideStyle.backgroundImage !== 'none' ? slideStyle.backgroundImage : null,
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


_GRADIENT_ANGLE_RE = re.compile(r"linear-gradient\(\s*([\d.]+)deg")
_GRADIENT_DIR_RE = re.compile(r"linear-gradient\(\s*to\s+([\w\s]+?)\s*,")

_CSS_DIR_TO_DEG = {
    "top": 0, "right": 90, "bottom": 180, "left": 270,
    "top right": 45, "right top": 45,
    "bottom right": 135, "right bottom": 135,
    "bottom left": 225, "left bottom": 225,
    "top left": 315, "left top": 315,
}


def _parse_css_gradient(
    css_val: str,
) -> list[tuple[RGBColor, float, float]] | None:
    """Parse CSS linear-gradient into [(RGBColor, position, alpha), ...].

    Handles both opaque and transparent stops. Returns None if not a gradient.
    """
    if not css_val or "linear-gradient" not in css_val:
        return None
    stops: list[tuple[RGBColor, float, float]] = []
    for m in _RGB_RE.finditer(css_val):
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = float(m.group(4)) if m.group(4) else 1.0
        stops.append((RGBColor(r, g, b), 0.0, a))
    if len(stops) < 2:
        return None
    # Distribute positions evenly
    for i, (color, _, alpha) in enumerate(stops):
        stops[i] = (color, i / (len(stops) - 1), alpha)
    return stops


def _gradient_angle_emu(css_val: str) -> int:
    """Extract CSS gradient angle and convert to OOXML EMU angle (60000ths of degree).

    CSS: 0deg=to-top, 90deg=to-right, 180deg=to-bottom (clockwise from top).
    OOXML: 0=right-to-left, 5400000=top-to-bottom (clockwise from right).
    Supports both degree angles and direction keywords (to right, to bottom left, etc.).
    """
    m = _GRADIENT_ANGLE_RE.search(css_val or "")
    if m:
        css_deg = float(m.group(1))
    else:
        dm = _GRADIENT_DIR_RE.search(css_val or "")
        css_deg = _CSS_DIR_TO_DEG.get(dm.group(1).strip(), 180) if dm else 180.0
    ooxml_deg = (css_deg + 270) % 360
    return int(ooxml_deg * 60000)


def _apply_gradient_fill(xml_ancestor, css_val: str) -> bool:
    """Apply a CSS linear-gradient by manipulating OOXML directly.

    Args:
        xml_ancestor: The lxml element to search for <a:gradFill> —
            typically shape._element or slide.background._element.
        css_val: CSS linear-gradient string.
    """
    stops = _parse_css_gradient(css_val)
    if not stops:
        return False
    angle = _gradient_angle_emu(css_val)

    # Find or create the <a:gradFill> element
    grad_fill = xml_ancestor.find(".//" + qn("a:gradFill"))
    if grad_fill is None:
        # Find the properties container (spPr for shapes, bgPr for backgrounds)
        props = (
            xml_ancestor.find(qn("p:spPr"))
            or xml_ancestor.find(qn("p:bgPr"))
            or xml_ancestor.find(".//" + qn("a:spPr"))
            or xml_ancestor
        )
        # Remove any existing fill
        for tag in ("a:solidFill", "a:noFill", "a:pattFill", "a:blipFill"):
            for old in props.findall(qn(tag)):
                props.remove(old)
        grad_fill = etree.SubElement(props, qn("a:gradFill"))

    grad_fill.set("rotWithShape", "0")

    # Replace gradient stops
    gs_lst = grad_fill.find(qn("a:gsLst"))
    if gs_lst is None:
        gs_lst = etree.SubElement(grad_fill, qn("a:gsLst"))
    for old in gs_lst.findall(qn("a:gs")):
        gs_lst.remove(old)

    for color, pos, alpha in stops:
        gs = etree.SubElement(gs_lst, qn("a:gs"))
        gs.set("pos", str(int(pos * 100000)))
        srgb = etree.SubElement(gs, qn("a:srgbClr"))
        srgb.set("val", f"{color[0]:02X}{color[1]:02X}{color[2]:02X}")
        if alpha < 0.99:
            alpha_el = etree.SubElement(srgb, qn("a:alpha"))
            alpha_el.set("val", str(int(alpha * 100000)))

    # Set angle
    lin = grad_fill.find(qn("a:lin"))
    if lin is None:
        lin = etree.SubElement(grad_fill, qn("a:lin"))
    lin.set("ang", str(angle))
    lin.set("scaled", "1")

    return True


def _apply_gradient_text(run, css_val: str) -> bool:
    """Apply a CSS gradient as text fill color via OOXML <a:gradFill> on the run.

    PPTX supports gradient text — the gradient goes inside <a:rPr> on the run,
    replacing the solid <a:solidFill>.
    """
    stops = _parse_css_gradient(css_val)
    if not stops:
        return False
    angle = _gradient_angle_emu(css_val)

    rPr = run._r.get_or_add_rPr()

    # Remove existing solid fill
    for old in rPr.findall(qn("a:solidFill")):
        rPr.remove(old)

    grad = etree.SubElement(rPr, qn("a:gradFill"))
    gs_lst = etree.SubElement(grad, qn("a:gsLst"))
    for color, pos, alpha in stops:
        gs = etree.SubElement(gs_lst, qn("a:gs"))
        gs.set("pos", str(int(pos * 100000)))
        srgb = etree.SubElement(gs, qn("a:srgbClr"))
        srgb.set("val", f"{color[0]:02X}{color[1]:02X}{color[2]:02X}")

    lin = etree.SubElement(grad, qn("a:lin"))
    lin.set("ang", str(angle))
    lin.set("scaled", "1")

    return True


def _first_gradient_color(css_val: str) -> RGBColor | None:
    """Extract the first opaque color from a CSS gradient for use as a solid fallback."""
    stops = _parse_css_gradient(css_val)
    if not stops:
        return None
    for color, _, alpha in stops:
        if alpha > 0.3:
            return color
    return stops[0][0]


def _resolve_font_color(el: dict) -> RGBColor:
    """Determine the visible text color, handling gradient-text fallback.

    CSS gradient text uses -webkit-text-fill-color: transparent with a
    background-image gradient. PPTX can't do gradient text, so we use
    the first gradient stop color as a solid approximation.
    """
    if el.get("isGradientText"):
        grad_color = _first_gradient_color(el.get("backgroundImage", ""))
        if grad_color:
            return grad_color

    result = _css_color_to_rgb(el.get("color", "rgb(255,255,255)"))
    return result[0] if result else RGBColor(0xFF, 0xFF, 0xFF)


def _parse_font_family(css_font: str) -> str:
    """Extract the first font family name from a CSS font-family string."""
    first = css_font.split(",")[0].strip()
    return first.strip("'\"")


# ---------------------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------------------


def _add_image_from_data_uri(slide, data_uri: str, left, top, width, height,
                             border_radius_px: float = 0,
                             width_px: float = 0, height_px: float = 0):
    """Decode a base64 data URI and add it as a picture shape.

    When border_radius_px > 0, clips the image to a rounded rectangle
    by swapping the shape geometry from 'rect' to 'roundRect'.
    """
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
        pic = slide.shapes.add_picture(tmp.name, left, top, width, height)

        if border_radius_px > 0 and width_px > 0 and height_px > 0:
            sp_pr = pic._element.find(qn("p:spPr"))
            if sp_pr is not None:
                prst_geom = sp_pr.find(qn("a:prstGeom"))
                if prst_geom is not None:
                    prst_geom.set("prst", "roundRect")
                    _set_corner_radius(pic, border_radius_px, width_px, height_px)

        return pic
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
    run,
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
    """Extract border-radius in pixels from an element measurement.

    Handles both pixel values ('16px') and percentages ('50%').
    Percentages are resolved against the element's smaller dimension.
    """
    br = str(el.get("borderRadius", "0")).strip().split()[0]
    if not br or br == "0":
        return 0
    try:
        if "%" in br:
            pct = float(br.replace("%", "")) / 100
            min_dim = min(el.get("width", 0), el.get("height", 0))
            return pct * min_dim
        return float(br.replace("px", ""))
    except (ValueError, IndexError):
        return 0


def _set_corner_radius(
    shape, radius_px: float, width_px: float, height_px: float,
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


def _apply_fill_alpha(shape_or_txbox, alpha: float) -> None:
    """Set fill opacity via OOXML alpha child element.

    OOXML represents alpha as a child of srgbClr, not an attribute:
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
    slide,
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
    has_gradient = bool(_parse_css_gradient(el.get("backgroundImage", "")))

    border_color_str = el.get("borderColor")
    border_width = el.get("borderWidth", 0)
    has_border = bool(border_color_str) and border_width > 0

    if not has_fill and not has_border and not has_gradient:
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

    if has_gradient:
        _apply_gradient_fill(shape._element, el["backgroundImage"])
    elif has_fill:
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
        if border_result and border_result[1] > 0.15:
            shape.line.color.rgb = border_result[0]
            shape.line.width = Pt(max(border_width * 0.75, 0.5))
            if border_result[1] < 0.99:
                ln = shape._element.find(".//" + qn("a:ln"))
                if ln is not None:
                    srgb = ln.find(".//" + qn("a:srgbClr"))
                    if srgb is not None:
                        alpha_el = etree.SubElement(srgb, qn("a:alpha"))
                        alpha_el.set("val", str(int(border_result[1] * 100000)))
        else:
            shape.line.fill.background()
    else:
        shape.line.fill.background()

    # Accent bar: any visible left-border rendered as a separate filled rectangle
    left_border_color = el.get("borderLeftColor")
    left_border_width = el.get("borderLeftWidth", 0)
    left_border_style = el.get("borderLeftStyle")
    if (
        left_border_color
        and left_border_width > 0
        and left_border_style not in (None, "none")
    ):
        left_result = _css_color_to_rgb(left_border_color)
        if left_result:
            bar_w = max(left_border_width * PIXELS_TO_INCHES_X, 0.03)
            bar = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(x_in), Inches(y_in),
                Inches(bar_w), Inches(h_in),
            )
            bar.fill.solid()
            bar.fill.fore_color.rgb = left_result[0]
            bar.line.fill.background()


def _apply_shape_bg(
    shape_or_txbox,
    el: dict,
    opacity: float,
) -> None:
    """Apply background fill (solid or gradient) to a shape or textbox."""
    gradient_css = el.get("backgroundImage", "")
    is_gradient_text = el.get("isGradientText", False)

    # Don't apply gradient as bg fill when the gradient is for text coloring
    if not is_gradient_text and _parse_css_gradient(gradient_css):
        _apply_gradient_fill(shape_or_txbox._element, gradient_css)
        return

    bg_result = _css_color_to_rgb(el.get("backgroundColor", ""))
    if bg_result:
        bg_color, bg_alpha = bg_result
        effective_alpha = bg_alpha * opacity
        shape_or_txbox.fill.solid()
        shape_or_txbox.fill.fore_color.rgb = bg_color
        if effective_alpha < 0.99:
            _apply_fill_alpha(shape_or_txbox, effective_alpha)


def _render_text_element(
    slide,
    el: dict,
    x_in: float,
    y_in: float,
    w_in: float,
    h_in: float,
    has_visual_bg: bool,
    opacity: float,
) -> None:
    """Render a text box with optional background (solid, gradient, or translucent)."""
    # Gradient-text elements use backgroundImage for text coloring, not as a fill
    if el.get("isGradientText"):
        has_visual_bg = False

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

    font_color = _resolve_font_color(el)
    font_family = _parse_font_family(el.get("fontFamily", "Calibri"))
    is_bold = el.get("fontWeight", "400") in ("bold", "600", "700", "800", "900")
    is_italic = el.get("fontStyle", "normal") == "italic"

    is_rtl = el.get("direction") == "rtl"
    alignment = {
        "center": PP_ALIGN.CENTER,
        "right": PP_ALIGN.RIGHT,
        "left": PP_ALIGN.LEFT,
        "justify": PP_ALIGN.JUSTIFY,
        "start": PP_ALIGN.RIGHT if is_rtl else PP_ALIGN.LEFT,
        "end": PP_ALIGN.LEFT if is_rtl else PP_ALIGN.RIGHT,
    }.get(el.get("textAlign", "right" if is_rtl else "left"),
          PP_ALIGN.RIGHT if is_rtl else PP_ALIGN.LEFT)

    radius_px = _parse_border_radius_px(el)

    if has_visual_bg and radius_px > 0:
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
        )
        _set_corner_radius(shape, radius_px, el.get("width", 100), el.get("height", 100))
        _apply_shape_bg(shape, el, opacity)
        shape.line.fill.background()
        tf = shape.text_frame
    else:
        txbox = slide.shapes.add_textbox(
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
        )
        if has_visual_bg:
            _apply_shape_bg(txbox, el, opacity)
        tf = txbox.text_frame

    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    p = tf.paragraphs[0]

    marker_color_str = el.get("markerColor")
    has_bullet = text.startswith("\u2022 ") or (
        len(text) >= 3 and text[0].isdigit() and text[:3].rstrip().endswith(".")
    )

    primary_run: object
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

    if el.get("isGradientText") and el.get("backgroundImage"):
        _apply_gradient_text(primary_run, el["backgroundImage"])

    p.alignment = alignment

    href = el.get("href")
    if href and not href.startswith("#"):
        try:
            primary_run.hyperlink.address = href
        except Exception:
            pass


def _render_inline_runs(
    slide,
    el: dict,
    x_in: float,
    y_in: float,
    w_in: float,
    h_in: float,
    has_bg: bool,
    opacity: float,
) -> None:
    """Render a text box with multiple styled runs from inline mixed content.

    Handles elements like <p>Hello <strong>bold</strong> more text</p>
    where text nodes and inline children are interleaved.
    """
    runs_data = el.get("inlineRuns", [])
    if not runs_data:
        return

    is_rtl = el.get("direction") == "rtl"
    alignment = {
        "center": PP_ALIGN.CENTER,
        "right": PP_ALIGN.RIGHT,
        "justify": PP_ALIGN.JUSTIFY,
        "start": PP_ALIGN.RIGHT if is_rtl else PP_ALIGN.LEFT,
        "end": PP_ALIGN.LEFT if is_rtl else PP_ALIGN.RIGHT,
    }.get(el.get("textAlign", "left"), PP_ALIGN.RIGHT if is_rtl else PP_ALIGN.LEFT)

    font_size_pt = el.get("fontSize", 20) * CSS_PX_TO_PT
    font_size_pt = max(MIN_FONT_SIZE_PT, min(font_size_pt, MAX_FONT_SIZE_PT))
    min_text_height = font_size_pt * 1.5 / 72
    h_in = max(h_in, min_text_height)

    radius_px = _parse_border_radius_px(el)

    if has_bg and radius_px > 0:
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
        )
        _set_corner_radius(shape, radius_px, el.get("width", 100), el.get("height", 100))
        bg_result = _css_color_to_rgb(el.get("backgroundColor", ""))
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
            bg_result = _css_color_to_rgb(el.get("backgroundColor", ""))
            if bg_result:
                txbox.fill.solid()
                txbox.fill.fore_color.rgb = bg_result[0]
                if bg_result[1] * opacity < 0.99:
                    _apply_fill_alpha(txbox, bg_result[1] * opacity)
        tf = txbox.text_frame

    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    p = tf.paragraphs[0]
    p.alignment = alignment

    for run_data in runs_data:
        text = run_data.get("text", "")
        if text == "\n":
            p = tf.add_paragraph()
            p.alignment = alignment
            continue
        if not text.strip():
            continue

        transform = run_data.get("textTransform", "none")
        if transform == "uppercase":
            text = text.upper()
        elif transform == "lowercase":
            text = text.lower()
        elif transform == "capitalize":
            text = text.title()

        run_size = run_data.get("fontSize", el.get("fontSize", 20)) * CSS_PX_TO_PT
        run_size = max(MIN_FONT_SIZE_PT, min(run_size, MAX_FONT_SIZE_PT))

        run_is_gradient = run_data.get("isGradientText", False)
        run_bg_image = run_data.get("backgroundImage", "")

        color_result = _css_color_to_rgb(run_data.get("color", el.get("color", "rgb(255,255,255)")))
        if run_is_gradient and run_bg_image:
            run_color = _first_gradient_color(run_bg_image) or RGBColor(0xFF, 0xFF, 0xFF)
        elif color_result:
            run_color = color_result[0]
        else:
            run_color = _resolve_font_color(el)

        run_bold = run_data.get("fontWeight", "400") in ("bold", "600", "700", "800", "900")
        run_italic = run_data.get("fontStyle", "normal") == "italic"
        run_family = _parse_font_family(run_data.get("fontFamily", el.get("fontFamily", "Calibri")))

        r = p.add_run()
        r.text = text
        _apply_font(r, size_pt=run_size, color=run_color, bold=run_bold, italic=run_italic, family=run_family)

        if run_is_gradient and run_bg_image:
            _apply_gradient_text(r, run_bg_image)

        href = run_data.get("href")
        if href and not href.startswith("#"):
            try:
                r.hyperlink.address = href
            except Exception:
                pass


# ---------------------------------------------------------------------------
# PPTX rendering (element tree -> slide shapes)
# ---------------------------------------------------------------------------


def _render_measured_element(slide, el: dict) -> None:
    """Render a single measured element onto a PPTX slide.

    Traversal strategy:
    - Image → render picture shape, stop
    - Inline runs (mixed content like <p>text <strong>bold</strong> more</p>)
        → render background if any, render multi-run text box, then
          recurse only non-inline (block) children
    - Text leaf (has text, no descendant text) → render text box, stop
    - Non-leaf with background/gradient → render shape, recurse children
    - Pure container → recurse children only
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
    is_gradient_text = el.get("isGradientText", False)
    has_gradient = (
        bool(_parse_css_gradient(el.get("backgroundImage", "")))
        and not is_gradient_text
    )
    has_border = bool(el.get("borderColor")) and el.get("borderWidth", 0) > 0
    has_visual_bg = has_bg or has_gradient
    has_text = bool(el.get("text", "").strip())
    has_inline_runs = bool(el.get("inlineRuns"))
    children = el.get("children", [])
    opacity = el.get("opacity", 1.0)

    # Detect standalone left-border accents (common decorative pattern)
    has_left_accent = (
        el.get("borderLeftWidth", 0) > 0
        and el.get("borderLeftStyle") not in (None, "none")
        and bool(_css_color_to_rgb(el.get("borderLeftColor", "")))
    )

    if (is_image or el.get("isSvg")) and el.get("src", "").startswith("data:image/"):
        _add_image_from_data_uri(
            slide, el["src"],
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
            border_radius_px=_parse_border_radius_px(el),
            width_px=el.get("width", 0),
            height_px=el.get("height", 0),
        )
        return

    # Unreasterized SVGs: skip (no python-pptx SVG support)
    if el.get("isSvg"):
        return

    if has_inline_runs:
        if has_visual_bg or has_border or has_left_accent:
            _render_bg_shape(slide, el, x_in, y_in, w_in, h_in, opacity)
        _render_inline_runs(slide, el, x_in, y_in, w_in, h_in, has_visual_bg, opacity)
        for child in children:
            if child.get("tag") not in (
                "span", "strong", "em", "b", "i", "a", "code", "mark",
                "sub", "sup", "small", "u", "s", "del",
            ):
                _render_measured_element(slide, child)
        return

    is_text_leaf = has_text and not _any_descendant_has_text(el)
    if is_text_leaf:
        _render_text_element(slide, el, x_in, y_in, w_in, h_in, has_visual_bg, opacity)
        return

    if has_visual_bg or has_border or has_left_accent:
        _render_bg_shape(slide, el, x_in, y_in, w_in, h_in, opacity)

    for child in children:
        _render_measured_element(slide, child)


# ---------------------------------------------------------------------------
# Pipeline stages (public API)
# ---------------------------------------------------------------------------


def _walk_elements(elements: list[dict]):
    """Yield every element in a measurement tree (depth-first)."""
    for el in elements:
        yield el
        yield from _walk_elements(el.get("children", []))


async def _rasterize_inline_svgs(page, measurements: list[dict]) -> None:
    """Screenshot inline <svg> elements and patch them as raster images.

    SVGs can't be added directly to python-pptx. This second pass shows
    each slide, finds marked SVGs, screenshots them at 2x, and converts
    the measurement to an image element.
    """
    for i, slide_data in enumerate(measurements):
        svg_els = [e for e in _walk_elements(slide_data.get("elements", []))
                   if e.get("isSvg") and e.get("svgId")]
        if not svg_els:
            continue

        await page.evaluate(f"""
            document.querySelectorAll('.slide').forEach((s, idx) => {{
                s.style.display = idx === {i} ? 'flex' : 'none';
                if (idx === {i}) s.classList.add('active');
                else s.classList.remove('active');
            }});
        """)
        await page.wait_for_timeout(200)

        for el in svg_els:
            try:
                handle = await page.query_selector(
                    f'[data-pptx-id="{el["svgId"]}"]'
                )
                if not handle:
                    continue
                png_bytes = await handle.screenshot(type="png")
                encoded = base64.b64encode(png_bytes).decode()
                el["isImage"] = True
                el["isSvg"] = False
                el["src"] = f"data:image/png;base64,{encoded}"
                el["children"] = []
            except Exception:
                logger.debug("Failed to rasterize SVG %s", el.get("svgId", "?"))


async def extract_measurements(html_path: str) -> list[dict]:
    """Open an HTML slide deck in headless Chromium and measure every element.

    Args:
        html_path: Path to the HTML file.

    Returns:
        List of slide measurement dicts, each containing:
          - index, width, height, backgroundColor
          - elements: recursive tree of measured DOM nodes

    Raises:
        FileNotFoundError: If html_path does not exist.
        ValueError: If the file exceeds the size limit or contains no slides.
        ImportError: If Playwright is not installed.
    """
    from playwright.async_api import async_playwright

    abs_path = os.path.abspath(html_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"HTML file not found: {abs_path}")

    file_size_mb = os.path.getsize(abs_path) / (1024 * 1024)
    if file_size_mb > MAX_HTML_SIZE_MB:
        raise ValueError(
            f"HTML file is {file_size_mb:.1f} MB, exceeds {MAX_HTML_SIZE_MB} MB limit"
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

        await _rasterize_inline_svgs(page, measurements)

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

    Args:
        measurements: Output of extract_measurements() — one dict per slide,
            each with a backgroundColor and a recursive elements tree.

    Returns:
        A python-pptx Presentation ready to be saved.
    """
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_WIDTH_INCHES)
    prs.slide_height = Inches(SLIDE_HEIGHT_INCHES)
    blank_layout = prs.slide_layouts[6]

    for slide_data in measurements:
        slide = prs.slides.add_slide(blank_layout)

        gradient_css = slide_data.get("backgroundImage", "")
        if gradient_css and _parse_css_gradient(gradient_css):
            slide.background.fill.gradient()
            _apply_gradient_fill(slide.background._element, gradient_css)
        else:
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

    Args:
        input_html: Path to the HTML file containing <section class="slide"> elements.
        output_pptx: Path where the .pptx file will be written.

    Returns:
        The output_pptx path.

    Raises:
        FileNotFoundError: If input_html does not exist.
        ValueError: If the file exceeds the size limit or contains no slides.
        ImportError: If Playwright is not installed.
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


