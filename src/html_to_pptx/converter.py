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
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
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

# 1 CSS px ≈ 0.5pt on this canvas, so small UI text (e.g. 14px tags → 7pt) must
# be allowed below the old 8pt floor or it renders larger than the source and
# overflows its box. Keep a low floor for legibility only.
MIN_FONT_SIZE_PT = 5
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
({ officecliMode = false } = {}) => {
    const slides = document.querySelectorAll('.slide');
    const results = [];
    let _svgCounter = 0;
    let _imageCounter = 0;
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
        const pre = parentStyle.whiteSpace && parentStyle.whiteSpace.indexOf('pre') === 0;
        const nodes = el.childNodes;
        for (let ni = 0; ni < nodes.length; ni++) {
            const node = nodes[ni];
            if (node.nodeType === Node.TEXT_NODE) {
                // In white-space:pre*, newlines and runs of spaces are significant
                // (e.g. a terminal/code block). Preserve them: emit '\\n' runs at
                // line breaks and keep the raw text (including indentation).
                if (pre) {
                    const segs = node.textContent.split('\\n');
                    for (let si = 0; si < segs.length; si++) {
                        if (si > 0) runs.push({ text: '\\n', color: parentStyle.color, fontSize: parseFloat(parentStyle.fontSize), fontFamily: parentStyle.fontFamily, fontWeight: parentStyle.fontWeight, fontStyle: parentStyle.fontStyle, textTransform: 'none', ...(officecliMode ? {textDecoration: parentStyle.textDecorationLine} : {}) });
                        if (segs[si].length) runs.push({ text: segs[si], color: parentStyle.color, fontSize: parseFloat(parentStyle.fontSize), fontFamily: parentStyle.fontFamily, fontWeight: parentStyle.fontWeight, fontStyle: parentStyle.fontStyle, textTransform: parentStyle.textTransform, ...(officecliMode ? {textDecoration: parentStyle.textDecorationLine} : {}) });
                    }
                    continue;
                }
                // Collapse internal whitespace runs to single spaces (browser behavior)
                // but preserve boundary spaces between inline siblings
                let t = node.textContent.replace(/\\s+/g, ' ');
                if (ni === 0) t = t.replace(/^\\s+/, '');
                if (ni === nodes.length - 1) t = t.replace(/\\s+$/, '');
                if (!t) continue;
                runs.push({
                    text: t,
                    color: parentStyle.color,
                    fontSize: parseFloat(parentStyle.fontSize),
                    fontFamily: parentStyle.fontFamily,
                    fontWeight: parentStyle.fontWeight,
                    fontStyle: parentStyle.fontStyle,
                    textTransform: parentStyle.textTransform,
                    ...(officecliMode ? {textDecoration: parentStyle.textDecorationLine} : {}),
                });
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const tag = node.tagName.toLowerCase();
                if (['script','style','link','meta'].includes(tag)) continue;
                const cs = getComputedStyle(node);
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                if (tag === 'br') {
                    runs.push({ text: '\\n', color: parentStyle.color, fontSize: parseFloat(parentStyle.fontSize), fontFamily: parentStyle.fontFamily, fontWeight: parentStyle.fontWeight, fontStyle: parentStyle.fontStyle, textTransform: 'none', ...(officecliMode ? {textDecoration: parentStyle.textDecorationLine} : {}) });
                    continue;
                }
                // Only collect true inline-flow children as runs.  A tag such
                // as <b> or <small> can be a flex/grid item whose computed
                // display is blockified; treating it as an inline run loses
                // the layout gap/line break and concatenates sibling labels.
                const isInline = officecliMode
                    ? cs.display.startsWith('inline')
                    : cs.display.startsWith('inline') || INLINE_TAGS.has(tag);
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
                            ...(officecliMode ? {textDecoration: cs.textDecorationLine} : {}),
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

    function textParagraphs(el, runs, directText) {
        const style = getComputedStyle(el);
        const sourceRuns = runs.length ? runs : (directText ? [{
            text: directText,
            color: style.color,
            fontSize: parseFloat(style.fontSize),
            fontFamily: style.fontFamily,
            fontWeight: style.fontWeight,
            fontStyle: style.fontStyle,
            textTransform: style.textTransform,
            ...(officecliMode ? {textDecoration: style.textDecorationLine} : {}),
        }] : []);
        const paragraphs = [];
        let current = [];
        let breakAtEnd = false;
        const pushParagraph = (force = false) => {
            if (current.length || paragraphs.length === 0 || force) {
                paragraphs.push({
                    text: current.map(run => run.text).join(''),
                    align: style.textAlign,
                    lineHeight: style.lineHeight,
                    spaceBefore: parseFloat(style.marginTop) || 0,
                    spaceAfter: parseFloat(style.marginBottom) || 0,
                    direction: style.direction,
                    runs: current,
                });
            }
            current = [];
        };
        for (const run of sourceRuns) {
            const pieces = String(run.text || '').split('\\n');
            for (let index = 0; index < pieces.length; index++) {
                if (pieces[index]) current.push({ ...run, text: pieces[index] });
                if (index < pieces.length - 1) {
                    pushParagraph(true);
                    breakAtEnd = true;
                } else if (pieces[index]) {
                    breakAtEnd = false;
                }
            }
        }
        if (officecliMode) {
            if (current.length || paragraphs.length === 0 || breakAtEnd) pushParagraph(breakAtEnd);
        } else if (current.length || paragraphs.length === 0) {
            pushParagraph();
        }
        return paragraphs;
    }

    function hasChildElementText(el) {
        for (const child of el.children) {
            if (child.textContent && child.textContent.trim()) return true;
        }
        return false;
    }

    function hasNonInlineTextChild(el) {
        for (const child of el.children) {
            if (!child.textContent || !child.textContent.trim()) continue;
            const childStyle = getComputedStyle(child);
            if (!childStyle.display.startsWith('inline')) return true;
        }
        return false;
    }

    // A browser can soft-wrap a text node at a position that OfficeCLI's
    // substituted font metrics would choose differently.  Preserve those
    // visual line boundaries for the OfficeCLI profile as explicit paragraph
    // breaks; this keeps the text editable while removing renderer-dependent
    // reflow from the final PPTX.
    function visualLineTexts(el) {
        if (!officecliMode) return [];
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        const rows = [];
        let node;
        while (node = walker.nextNode()) {
            const parent = node.parentElement;
            if (!parent) continue;
            const parentTag = parent.tagName.toLowerCase();
            if (['script', 'style', 'link', 'meta'].includes(parentTag)) continue;
            const raw = node.textContent || '';
            for (let index = 0; index < raw.length; index++) {
                const range = document.createRange();
                range.setStart(node, index);
                range.setEnd(node, index + 1);
                const rect = range.getBoundingClientRect();
                if (rect.width < 0.01 && rect.height < 0.01) continue;
                const tolerance = Math.max(
                    1.5,
                    parseFloat(getComputedStyle(el).fontSize || '16') * 0.12,
                );
                let row = rows.find(item => Math.abs(item.top - rect.top) <= tolerance);
                if (!row) {
                    row = { top: rect.top, text: '' };
                    rows.push(row);
                }
                row.text += raw[index];
            }
        }
        return rows
            .sort((left, right) => left.top - right.top)
            .map(row => row.text.replace(/\\s+/g, ' ').trim())
            .filter(text => text.length > 0);
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

        // A CSS rotate makes getBoundingClientRect return the (larger) enclosing
        // box. Detect the angle, then measure the element with its own transform
        // neutralized so we get the true unrotated box; PPTX re-applies the angle
        // about the shape center. (Restored immediately to avoid side effects.)
        let ownRotation = 0;
        const _tf = style.transform;
        if (_tf && _tf.indexOf('matrix') === 0) {
            const mm = _tf.match(/matrix\\(([^)]+)\\)/);
            if (mm) {
                const p = mm[1].split(',').map(parseFloat);
                const ang = Math.atan2(p[1], p[0]) * 180 / Math.PI;
                if (Math.abs(ang) > 0.5) ownRotation = ang;
            }
        }
        let _savedT = null;
        if (ownRotation) { _savedT = el.style.transform; el.style.transform = 'none'; el.getBoundingClientRect(); }

        const rect = el.getBoundingClientRect();
        if (ownRotation) { el.style.transform = _savedT; }
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
        const isTableElement = ['table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th'].includes(tag);
        const isTableCell = tag === 'td' || tag === 'th';
        const imageSource = isImg ? (el.getAttribute('src') || '') : '';
        const isSvgDataUri = isImg && /^data:image\\/svg\\+xml(?:[;,]|$)/i.test(imageSource);
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
            letterSpacing: (style.letterSpacing === 'normal' ? 0 : (parseFloat(style.letterSpacing) || 0)),
            direction: style.direction,
            position: style.position,
            display: style.display,
            justifyContent: style.justifyContent,
            alignItems: style.alignItems,
            verticalAlign: style.verticalAlign,
            writingMode: style.writingMode,
            rotation: ownRotation,
            opacity: parseFloat(style.opacity),
            paddingLeft: parseFloat(style.paddingLeft) || 0,
            paddingRight: parseFloat(style.paddingRight) || 0,
            paddingTop: parseFloat(style.paddingTop) || 0,
            paddingBottom: parseFloat(style.paddingBottom) || 0,
            objectFit: isImg ? style.objectFit : null,
            naturalWidth: isImg ? (el.naturalWidth || 0) : 0,
            naturalHeight: isImg ? (el.naturalHeight || 0) : 0,
            borderRadius: style.borderRadius,
            borderColor: hasBorder ? style.borderColor : null,
            borderWidth: hasBorder ? parseFloat(style.borderWidth) : 0,
            borderStyle: hasBorder ? style.borderStyle : null,
            cellBorderTopColor: style.borderTopColor,
            cellBorderTopWidth: parseFloat(style.borderTopWidth) || 0,
            cellBorderTopStyle: style.borderTopStyle,
            cellBorderRightColor: style.borderRightColor,
            cellBorderRightWidth: parseFloat(style.borderRightWidth) || 0,
            cellBorderRightStyle: style.borderRightStyle,
            cellBorderBottomColor: style.borderBottomColor,
            cellBorderBottomWidth: parseFloat(style.borderBottomWidth) || 0,
            cellBorderBottomStyle: style.borderBottomStyle,
            cellBorderLeftColor: style.borderLeftColor,
            cellBorderLeftWidth: parseFloat(style.borderLeftWidth) || 0,
            cellBorderLeftStyle: style.borderLeftStyle,
            borderLeftColor: style.borderLeftColor !== style.borderColor ? style.borderLeftColor : null,
            borderLeftWidth: parseFloat(style.borderLeftWidth) || 0,
            borderLeftStyle: style.borderLeftColor !== style.borderColor ? style.borderLeftStyle : null,
            rowSpan: isTableCell
                ? (el.hasAttribute('rowspan') ? (parseInt(el.getAttribute('rowspan'), 10) || 0) : 1)
                : 1,
            colSpan: isTableCell
                ? (el.hasAttribute('colspan') ? (parseInt(el.getAttribute('colspan'), 10) || 0) : 1)
                : 1,
            textTransform: style.textTransform,
            backgroundImage: bgImage,
            isGradientText: isGradientText,
            isImage: isImg,
            isSvg: isSvg,
            src: isImg ? imageSource : null,
            alt: isImg ? el.getAttribute('alt') : null,
            href: tag === 'a' ? el.getAttribute('href') : null,
            markerColor: markerColor,
            isSvgDataUri: isSvgDataUri,
            children: []
        };

        // Mark inline SVGs for rasterization in the Python post-pass
        if (isSvg) {
            const svgId = 'pptx-svg-' + (_svgCounter++);
            el.setAttribute('data-pptx-id', svgId);
            data.svgId = svgId;
        } else if (isSvgDataUri) {
            const imageId = 'pptx-image-' + (_imageCounter++);
            el.setAttribute('data-pptx-id', imageId);
            data.imageId = imageId;
        }

        for (const child of el.children) {
            if (['script', 'style', 'link', 'meta'].includes(child.tagName.toLowerCase())) continue;
            const childData = measureElement(child, slideRect, depth + 1);
            if (childData) data.children.push(childData);
        }

        // Table cells remain one native OfficeCLI object.  Their block-level
        // children (most commonly <p>) must therefore be folded into the cell
        // paragraph DTO instead of becoming ignored child objects at the table
        // lowering seam.  Inline children are already represented by the
        // parent runs and must not be appended a second time.
        if (officecliMode && isTableCell) {
            const blockParagraphs = [];
            const collectBlockParagraphs = (node) => {
                if (node.paragraphs && node.paragraphs.length) {
                    blockParagraphs.push(...node.paragraphs);
                    return;
                }
                for (const nested of node.children || []) {
                    collectBlockParagraphs(nested);
                }
            };
            for (const childData of data.children) {
                if (String(childData.display || '').startsWith('inline')) continue;
                collectBlockParagraphs(childData);
            }
            if (blockParagraphs.length) {
                data.paragraphs = [...(data.paragraphs || []), ...blockParagraphs];
                data.text = data.paragraphs.map(paragraph => paragraph.text).join('\\n');
            }
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

        const hasTextContent = officecliMode
            ? (directText || hasChildElementText(el))
            : (directText && hasChildElementText(el));
        if (hasTextContent) {
            const runs = collectInlineRuns(el);
            if (runs.length > 0 && (!officecliMode || !hasNonInlineTextChild(el))) {
                if (markerPrefix && runs.length > 0) {
                    runs[0].text = markerPrefix + runs[0].text;
                }
                data.inlineRuns = runs;
                if (officecliMode) {
                    // Keep the flattened text field as a compatibility view
                    // for callers of the measurement DTO.  The compiler
                    // consumes ``inlineRuns``/``paragraphs`` for formatting,
                    // so exposing this summary does not flatten the object at
                    // the lowering seam.
                    data.text = runs.map(run => run.text).join('');
                    data.paragraphs = textParagraphs(el, runs, directText);
                } else {
                    data.text = '';
                }
            } else if (directText && officecliMode) {
                data.paragraphs = textParagraphs(el, [], markerPrefix + directText);
            }
        } else if (directText && officecliMode) {
            data.paragraphs = textParagraphs(el, [], markerPrefix + directText);
        }

        if (
            officecliMode &&
            data.inlineRuns &&
            data.inlineRuns.length > 0 &&
            !data.inlineRuns.some(run => String(run.text || '').includes('\\n')) &&
            !hasNonInlineTextChild(el) &&
            !['td', 'th'].includes(el.tagName.toLowerCase())
        ) {
            const lines = visualLineTexts(el);
            if (lines.length > 1) data.visualLines = lines;
        }

        const isContainer = !data.text && !isImg && !isSvg && !hasVisibleBg && !hasBorder &&
                           !isTableElement &&
                           data.backgroundImage === null && !data.inlineRuns;
        if (isContainer && data.children.length === 1 && depth > 0) {
            const child = data.children[0];
            // A pure wrapper is collapsed away, but its visual effects must be
            // folded into the surviving child, or they are silently lost:
            //  - opacity (e.g. a faint hero-image wrapper at opacity:0.18)
            //  - border-radius + overflow:hidden clipping (rounded image frames)
            if (data.opacity < 1) {
                child.opacity = (child.opacity == null ? 1 : child.opacity) * data.opacity;
            }
            const childHasRadius = child.borderRadius && child.borderRadius !== '0px'
                && child.borderRadius !== '0';
            if (!childHasRadius && data.borderRadius && data.borderRadius !== '0px'
                && data.borderRadius !== '0') {
                child.borderRadius = data.borderRadius;
            }
            return child;
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


# Default backdrop used when a slide has no resolvable background color.
_DEFAULT_BACKDROP = RGBColor(0xFF, 0xFF, 0xFF)


def _blend_over(color: RGBColor, alpha: float, backdrop: RGBColor) -> RGBColor:
    """Alpha-composite ``color`` at ``alpha`` over an opaque ``backdrop``.

    LibreOffice (and PowerPoint's PDF export) do not honor per-gradient-stop
    ``<a:alpha>`` and are unreliable with solid-fill / run-color alpha, so
    translucency is flattened to an equivalent opaque color at conversion time.
    This makes the PPTX render identically to the source HTML everywhere.
    """
    alpha = max(0.0, min(1.0, alpha))
    r = round(color[0] * alpha + backdrop[0] * (1 - alpha))
    g = round(color[1] * alpha + backdrop[1] * (1 - alpha))
    b = round(color[2] * alpha + backdrop[2] * (1 - alpha))
    return RGBColor(int(r), int(g), int(b))


def _resolve_backdrop(slide_data: dict) -> RGBColor:
    """Best-effort opaque backdrop color for a slide (for flattening alpha)."""
    grad = slide_data.get("backgroundImage", "")
    if grad:
        first = _first_gradient_color(grad)
        if first is not None:
            return first
    bg = _css_color_to_rgb(slide_data.get("backgroundColor", ""))
    if bg is not None:
        return bg[0]
    return _DEFAULT_BACKDROP


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
    # Only a single linear-gradient is representable. A radial/conic gradient, or
    # a multi-layered background (comma-separated gradients, e.g. a radial glow
    # over a base gradient), would otherwise have all its rgba stops scraped into
    # one bogus linear gradient — fall back to the solid background color instead.
    if "radial-gradient" in css_val or "conic-gradient" in css_val:
        return None
    if css_val.count("linear-gradient") > 1:
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


def _apply_gradient_fill(xml_ancestor, css_val: str, backdrop: RGBColor | None = None) -> bool:
    """Apply a CSS linear-gradient by manipulating OOXML directly.

    Args:
        xml_ancestor: The lxml element to search for <a:gradFill> —
            typically shape._element or slide.background._element.
        css_val: CSS linear-gradient string.
        backdrop: When given, translucent stops are alpha-composited over this
            opaque color and emitted opaque. LibreOffice ignores per-stop
            ``<a:alpha>``, so flattening is the only reliable way to reproduce a
            translucent gradient overlay (e.g. the faint orange quote card).
    """
    stops = _parse_css_gradient(css_val)
    if not stops:
        return False
    angle = _gradient_angle_emu(css_val)
    if backdrop is not None:
        stops = [
            (_blend_over(color, alpha, backdrop), pos, 1.0) if alpha < 0.99
            else (color, pos, alpha)
            for color, pos, alpha in stops
        ]

    # Find or create the <a:gradFill> element
    grad_fill = xml_ancestor.find(".//" + qn("a:gradFill"))
    if grad_fill is None:
        # Find the properties container (spPr for shapes, bgPr for backgrounds).
        # Use explicit "is not None" checks: lxml elements raise a FutureWarning
        # on truth-testing, and an empty element is falsy, so `or` is unsafe.
        props = xml_ancestor.find(qn("p:spPr"))
        if props is None:
            props = xml_ancestor.find(qn("p:bgPr"))
        if props is None:
            props = xml_ancestor.find(".//" + qn("a:spPr"))
        if props is None:
            props = xml_ancestor
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


def _resolve_font_color(el: dict, backdrop: RGBColor | None = None) -> RGBColor:
    """Determine the visible text color, handling gradient-text fallback.

    CSS gradient text uses -webkit-text-fill-color: transparent with a
    background-image gradient. PPTX can't do gradient text, so we use
    the first gradient stop color as a solid approximation.

    Translucent text (e.g. ``color: rgba(232,119,46,0.12)`` for a giant faint
    index number) is flattened over ``backdrop`` — run-color alpha is not
    honored by LibreOffice, so it would otherwise render fully opaque.
    """
    if el.get("isGradientText"):
        grad_color = _first_gradient_color(el.get("backgroundImage", ""))
        if grad_color:
            return grad_color

    result = _css_color_to_rgb(el.get("color", "rgb(255,255,255)"))
    if not result:
        return RGBColor(0xFF, 0xFF, 0xFF)
    color, alpha = result
    if alpha < 0.99 and backdrop is not None:
        return _blend_over(color, alpha, backdrop)
    return color


def _parse_font_family(css_font: str) -> str:
    """Extract the first font family name from a CSS font-family string."""
    first = css_font.split(",")[0].strip()
    return first.strip("'\"")


# Fonts that ship with Windows/Office (and are Microsoft-metric-compatible on
# macOS/LibreOffice), so we can rely on them rendering without substitution.
_SAFE_FONTS = {
    "arial", "arial black", "calibri", "cambria", "candara", "consolas",
    "constantia", "corbel", "courier new", "georgia", "times new roman",
    "trebuchet ms", "verdana", "segoe ui", "tahoma", "garamond",
    "book antiqua", "century gothic", "palatino linotype", "gill sans",
    "franklin gothic medium", "lucida sans", "impact",
}

# Explicit web-font -> metric/style-compatible safe equivalent. Grouped so the
# substitute stays in the SAME visual family (display-serif, humanist-sans,
# geometric-sans, monospace); keeping the family keeps glyph advance widths
# close, which stops headings from reflowing onto an extra line.
_FONT_EQUIVALENTS = {
    # ---- display / body serifs ----
    "playfair display": "Georgia",
    "playfair": "Georgia",
    "merriweather": "Georgia",
    "lora": "Georgia",
    "pt serif": "Georgia",
    "noto serif": "Georgia",
    "source serif pro": "Cambria",
    "source serif 4": "Cambria",
    "roboto slab": "Cambria",
    "dm serif display": "Georgia",
    "dm serif text": "Georgia",
    "cormorant": "Cambria",
    "cormorant garamond": "Cambria",
    "eb garamond": "Garamond",
    "crimson text": "Garamond",
    "crimson pro": "Garamond",
    "libre baskerville": "Georgia",
    "bitter": "Georgia",
    "spectral": "Cambria",
    "frank ruhl libre": "Georgia",
    # ---- humanist / grotesque sans ----
    "inter": "Segoe UI",
    "roboto": "Arial",
    "open sans": "Segoe UI",
    "lato": "Calibri",
    "noto sans": "Segoe UI",
    "source sans pro": "Segoe UI",
    "source sans 3": "Segoe UI",
    "work sans": "Segoe UI",
    "dm sans": "Segoe UI",
    "manrope": "Segoe UI",
    "ibm plex sans": "Segoe UI",
    "pt sans": "Segoe UI",
    "rubik": "Segoe UI",
    "karla": "Segoe UI",
    "mulish": "Segoe UI",
    "barlow": "Segoe UI",
    "titillium web": "Segoe UI",
    "figtree": "Segoe UI",
    "plus jakarta sans": "Segoe UI",
    "ubuntu": "Segoe UI",
    "helvetica": "Arial",
    "helvetica neue": "Arial",
    "nunito": "Calibri",
    "nunito sans": "Calibri",
    # ---- geometric sans ----
    "montserrat": "Century Gothic",
    "poppins": "Century Gothic",
    "raleway": "Century Gothic",
    "quicksand": "Century Gothic",
    "josefin sans": "Century Gothic",
    "comfortaa": "Century Gothic",
    # ---- monospace ----
    "jetbrains mono": "Consolas",
    "fira code": "Consolas",
    "fira mono": "Consolas",
    "source code pro": "Consolas",
    "roboto mono": "Consolas",
    "ibm plex mono": "Consolas",
    "space mono": "Consolas",
    "ubuntu mono": "Consolas",
    "inconsolata": "Consolas",
    "menlo": "Consolas",
    "monaco": "Consolas",
    "courier": "Courier New",
}

# CSS generic keyword -> concrete safe default (same family class).
_GENERIC_FALLBACK = {
    "serif": "Georgia",
    "sans-serif": "Calibri",
    "monospace": "Consolas",
    "cursive": "Segoe Script",
    "system-ui": "Segoe UI",
    "-apple-system": "Segoe UI",
    "blinkmacsystemfont": "Segoe UI",
    "ui-sans-serif": "Segoe UI",
    "ui-serif": "Georgia",
    "ui-monospace": "Consolas",
}


def _resolve_pptx_font(css_font: str) -> str:
    """Pick a rendering-safe font that stays in the source's visual family.

    Walks the CSS font-family stack in declared order and returns the first of:
      1. a family already known to be installed everywhere, else
      2. a known web font mapped to a metric-compatible safe equivalent, else
      3. the CSS generic keyword (serif/sans-serif/monospace) default.
    Falls back to Calibri. Staying in the same family keeps advance widths close
    so a substituted heading does not wrap onto an unwanted extra line.
    """
    if not css_font:
        return "Calibri"
    generic_seen: str | None = None
    for raw in css_font.split(","):
        name = raw.strip().strip("'\"")
        if not name:
            continue
        low = name.lower()
        if low in _SAFE_FONTS:
            return name
        if low in _FONT_EQUIVALENTS:
            return _FONT_EQUIVALENTS[low]
        if low in _GENERIC_FALLBACK and generic_seen is None:
            generic_seen = _GENERIC_FALLBACK[low]
    return generic_seen or "Calibri"


# ---------------------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------------------


def _apply_image_opacity(pic, opacity: float) -> None:
    """Make a picture translucent via ``<a:alphaModFix>`` in its blipFill.

    Used for faint background/hero images (e.g. an image wrapper at
    ``opacity: 0.18``) so overlaid text stays readable, matching the source.
    """
    if opacity >= 0.99:
        return
    blip = pic._element.find(".//" + qn("a:blip"))
    if blip is None:
        return
    for old in blip.findall(qn("a:alphaModFix")):
        blip.remove(old)
    amod = etree.SubElement(blip, qn("a:alphaModFix"))
    amod.set("amt", str(int(max(0.0, min(1.0, opacity)) * 100000)))


def _apply_object_fit_cover(pic, box_w_px: float, box_h_px: float,
                            nat_w: float, nat_h: float) -> None:
    """Emulate CSS ``object-fit: cover`` by cropping (never stretching).

    ``add_picture`` with explicit width+height stretches the image to the box,
    which distorts any image whose aspect ratio differs from the box (e.g. a
    square hero/product image placed in a wide frame). CSS ``cover`` instead
    scales to fill and crops the overflow, so we replicate that with a centered
    crop on the longer axis — the picture keeps the box geometry but is no longer
    distorted.
    """
    if nat_w <= 0 or nat_h <= 0 or box_w_px <= 0 or box_h_px <= 0:
        return
    box_ar = box_w_px / box_h_px
    img_ar = nat_w / nat_h
    if abs(img_ar - box_ar) < 1e-3:
        return
    if img_ar > box_ar:  # image too wide -> crop left/right
        crop = (1 - box_ar / img_ar) / 2
        pic.crop_left = crop
        pic.crop_right = crop
    else:  # image too tall -> crop top/bottom
        crop = (1 - img_ar / box_ar) / 2
        pic.crop_top = crop
        pic.crop_bottom = crop


def _add_image_from_data_uri(slide, data_uri: str, left, top, width, height,
                             border_radius_px: float = 0,
                             width_px: float = 0, height_px: float = 0,
                             opacity: float = 1.0,
                             object_fit: str | None = None,
                             natural_w: float = 0, natural_h: float = 0):
    """Decode a base64 data URI and add it as a picture shape.

    When border_radius_px > 0, clips the image to a rounded rectangle
    by swapping the shape geometry from 'rect' to 'roundRect'.
    When opacity < 1, the picture is made translucent to match the source.
    When object_fit == 'cover', the picture is cropped (not stretched) to fill.
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

        if object_fit == "cover":
            _apply_object_fit_cover(pic, width_px, height_px, natural_w, natural_h)

        if border_radius_px > 0 and width_px > 0 and height_px > 0:
            sp_pr = pic._element.find(qn("p:spPr"))
            if sp_pr is not None:
                prst_geom = sp_pr.find(qn("a:prstGeom"))
                if prst_geom is not None:
                    prst_geom.set("prst", "roundRect")
                    _set_corner_radius(pic, border_radius_px, width_px, height_px)

        _apply_image_opacity(pic, opacity)

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


def _strip_theme_effect(shape) -> None:
    """Neutralize the theme shape effect that python-pptx's ``add_shape`` injects.

    ``add_shape`` emits ``<p:style><a:effectRef idx="2"/>`` (the theme's "medium" effect, a
    soft drop shadow). CSS ``box-shadow`` is never authored, so autoshapes must not inherit a
    theme shadow — otherwise a hairline border renders with an unintended gray halo. An empty
    ``<a:effectLst/>`` overrides the ``effectRef``.
    """
    try:
        shape.shadow.inherit = False
    except Exception:  # pragma: no cover - textboxes/pictures have no ShadowFormat
        pass


def _resolve_alignment(
    el: dict, is_single_line: bool, has_visual_bg: bool,
):
    """Derive (horizontal PP_ALIGN, vertical MSO_ANCHOR) from the element's CSS.

    Generalizes text placement instead of special-casing element types:
      * Flex/grid containers with direct text place that text via
        ``justify-content`` (main axis) and ``align-items`` (cross axis) — e.g.
        a 60×60 logo tile centering "DT", or a centered hero badge.
      * Otherwise horizontal follows ``text-align``.
      * Vertical is MIDDLE for flex/grid center, for any element whose box only
        holds one line (chips, pills, buttons, stat tiles — their symmetric
        padding centers the single line), else TOP.
    """
    is_rtl = el.get("direction") == "rtl"
    text_align = el.get("textAlign", "right" if is_rtl else "left")
    h = {
        "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "left": PP_ALIGN.LEFT,
        "justify": PP_ALIGN.JUSTIFY,
        "start": PP_ALIGN.RIGHT if is_rtl else PP_ALIGN.LEFT,
        "end": PP_ALIGN.LEFT if is_rtl else PP_ALIGN.RIGHT,
    }.get(text_align, PP_ALIGN.RIGHT if is_rtl else PP_ALIGN.LEFT)

    display = el.get("display", "") or ""
    is_flex = "flex" in display or "grid" in display
    v = MSO_ANCHOR.TOP

    if is_flex:
        jc = el.get("justifyContent", "") or ""
        if "center" in jc or "space" in jc:
            h = PP_ALIGN.CENTER
        elif jc in ("flex-end", "end", "right"):
            h = PP_ALIGN.RIGHT
        elif jc in ("flex-start", "start", "left"):
            h = PP_ALIGN.LEFT
        ai = el.get("alignItems", "") or ""
        if "center" in ai:
            v = MSO_ANCHOR.MIDDLE
        elif ai in ("flex-end", "end"):
            v = MSO_ANCHOR.BOTTOM
    elif (
        has_visual_bg and is_single_line and text_align in ("start", "left", "")
        and el.get("tag") not in ("td", "th")
        and "table" not in display
    ):
        # A background chip whose box hugs its text (symmetric padding) reads
        # centered in the source even though text-align defaults to left. Table
        # cells also have a background but must keep their column alignment.
        h = PP_ALIGN.CENTER

    if v == MSO_ANCHOR.TOP and is_single_line:
        v = MSO_ANCHOR.MIDDLE
    return h, v


def _line_height_ratio(el: dict) -> float | None:
    """CSS line-height as a unitless multiple of the font size, or None.

    PowerPoint's default line spacing (~1.2) is looser than tight display
    line-heights (e.g. ``line-height: 0.92`` on a big headline), which makes a
    multi-line heading grow taller than its box and overlap the element below.
    Reproducing the CSS ratio keeps line count and vertical extent faithful.
    """
    lh = el.get("lineHeight", "normal")
    fs = el.get("fontSize", 0)
    if not fs or not lh or lh == "normal":
        return None
    try:
        px = float(str(lh).replace("px", "").strip())
    except ValueError:
        return None
    ratio = px / fs
    if 0.5 <= ratio <= 3.0:
        return ratio
    return None


def _apply_line_spacing(paragraph, el: dict) -> None:
    """Set exact line spacing (in points) to match the CSS line-height.

    A float ``line_spacing`` in PPTX multiplies the font's *natural* line height
    (~1.2×), not the font size, so passing the CSS ratio (e.g. 0.92) still comes
    out ~1.1× too tall and a multi-line heading creeps into the element below.
    Converting the measured px line-height to an absolute point value reproduces
    the CSS box exactly.
    """
    lh = el.get("lineHeight", "normal")
    fs = el.get("fontSize", 0)
    if not lh or lh == "normal":
        return
    try:
        px = float(str(lh).replace("px", "").strip())
    except ValueError:
        return
    ratio = px / fs if fs else 0
    if not (0.5 <= ratio <= 3.0):
        return
    pt = px * PIXELS_TO_INCHES_Y * 72.0
    if pt > 0:
        paragraph.line_spacing = Pt(pt)


# --- Single-line width fitting -------------------------------------------------
# A single-line element must never wrap or spill past its box. Because we can't
# embed the exact web font, a substituted font's advance widths differ slightly;
# we measure the rendered width (Pillow if available, else a per-family heuristic)
# and shrink the point size just enough to fit. This guarantees "one line stays
# one line AND fits" even when metrics don't match perfectly.
try:  # Pillow is optional; fall back to a heuristic estimator without it.
    from PIL import ImageFont as _PILImageFont
    _HAVE_PIL = True
except Exception:  # pragma: no cover
    _HAVE_PIL = False

_MAC_FONT_DIRS = [
    "/System/Library/Fonts/Supplemental",
    "/System/Library/Fonts",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
]

# Map a resolved PPTX family to a locally-available metric proxy for measurement.
_MEASURE_FONT_FILE = {
    ("georgia", False): "Georgia.ttf", ("georgia", True): "Georgia Bold.ttf",
    ("cambria", False): "Georgia.ttf", ("cambria", True): "Georgia Bold.ttf",
    ("garamond", False): "Georgia.ttf", ("garamond", True): "Georgia Bold.ttf",
    ("times new roman", False): "Times New Roman.ttf",
    ("times new roman", True): "Times New Roman Bold.ttf",
    ("arial", False): "Arial.ttf", ("arial", True): "Arial Bold.ttf",
    ("calibri", False): "Arial.ttf", ("calibri", True): "Arial Bold.ttf",
    ("segoe ui", False): "Arial.ttf", ("segoe ui", True): "Arial Bold.ttf",
    ("century gothic", False): "Arial.ttf", ("century gothic", True): "Arial Bold.ttf",
    ("verdana", False): "Verdana.ttf", ("verdana", True): "Verdana Bold.ttf",
    ("consolas", False): "Courier New.ttf", ("consolas", True): "Courier New Bold.ttf",
    ("courier new", False): "Courier New.ttf", ("courier new", True): "Courier New Bold.ttf",
}

# Fallback average glyph-advance as a fraction of em, by family class. Slightly
# generous so the estimate never under-shoots (which would allow an overflow).
_HEURISTIC_ADVANCE = {"serif": 0.52, "sans": 0.53, "mono": 0.60}
_font_path_cache: dict[tuple[str, bool], str | None] = {}
_pil_font_cache: dict[tuple[str, int], object] = {}


def _find_measure_font(family: str, bold: bool) -> str | None:
    key = (family.lower(), bold)
    if key in _font_path_cache:
        return _font_path_cache[key]
    fn = _MEASURE_FONT_FILE.get(key) or _MEASURE_FONT_FILE.get((family.lower(), False))
    candidates = [fn] if fn else []
    candidates.append("Arial Bold.ttf" if bold else "Arial.ttf")
    for name in candidates:
        for d in _MAC_FONT_DIRS:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                _font_path_cache[key] = p
                return p
    _font_path_cache[key] = None
    return None


def _family_class(family: str) -> str:
    low = family.lower()
    if low in ("consolas", "courier new", "menlo", "monaco"):
        return "mono"
    if low in ("georgia", "cambria", "garamond", "times new roman", "book antiqua"):
        return "serif"
    return "sans"


def _estimate_text_width_in(
    text: str, size_pt: float, family: str, bold: bool, letter_spacing_px: float,
) -> float | None:
    """Estimate rendered width (inches) of a single line at ``size_pt``."""
    if not text:
        return 0.0
    extra_pt = max(0, len(text) - 1) * letter_spacing_px  # px≈pt for width math
    if _HAVE_PIL:
        path = _find_measure_font(family, bold)
        if path:
            px = max(4, int(round(size_pt)))
            ck = (path, px)
            font = _pil_font_cache.get(ck)
            if font is None:
                try:
                    font = _PILImageFont.truetype(path, px)
                    _pil_font_cache[ck] = font
                except Exception:
                    font = None
            if font is not None:
                try:
                    w_px = font.getlength(text)
                    width_pt = w_px * (size_pt / px) + extra_pt
                    return width_pt / 72.0
                except Exception:
                    pass
    # Heuristic fallback
    adv = _HEURISTIC_ADVANCE[_family_class(family)]
    width_pt = len(text) * adv * size_pt + extra_pt
    return width_pt / 72.0


def _fit_font_size_single_line(
    text: str, size_pt: float, family: str, bold: bool,
    letter_spacing_px: float, avail_in: float,
) -> float:
    """Shrink ``size_pt`` so ``text`` fits ``avail_in`` on one line (never grows)."""
    if avail_in <= 0.05 or not text.strip():
        return size_pt
    width_in = _estimate_text_width_in(text, size_pt, family, bold, letter_spacing_px)
    if not width_in or width_in <= avail_in:
        return size_pt
    # 0.98 safety margin so rounding/kerning differences can't re-introduce overflow.
    scaled = size_pt * (avail_in / width_in) * 0.98
    return max(MIN_FONT_SIZE_PT, scaled)


def _apply_text_padding(tf, el: dict, extra_left_px: float = 0.0) -> None:
    """Match CSS padding by insetting the text inside its box.

    python-pptx text frames default to ~0.1in/0.05in internal margins; the
    element box we place is the CSS border box, so without this the text hugs the
    box edge (e.g. bulleted text overprints its ``::before`` dot, card labels
    touch the card edge). Setting the frame margins to the measured padding keeps
    the box geometry identical while placing the glyphs where the browser did.
    """
    left_px = max(el.get("paddingLeft", 0), extra_left_px)
    tf.margin_left = Inches(left_px * PIXELS_TO_INCHES_X)
    tf.margin_right = Inches(el.get("paddingRight", 0) * PIXELS_TO_INCHES_X)
    tf.margin_top = Inches(el.get("paddingTop", 0) * PIXELS_TO_INCHES_Y)
    tf.margin_bottom = Inches(el.get("paddingBottom", 0) * PIXELS_TO_INCHES_Y)


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


def _apply_rotation(shape, el: dict) -> None:
    """Rotate a shape/picture to match a CSS transform:rotate (degrees, CW)."""
    rot = el.get("rotation", 0) or 0
    if abs(rot) > 0.5:
        try:
            shape.rotation = float(rot)
        except Exception:
            pass


def _apply_vertical_text(tf, el: dict) -> None:
    """Map CSS writing-mode:vertical-* to a vertical PPTX text body."""
    wm = el.get("writingMode", "") or ""
    if not wm.startswith("vertical"):
        return
    try:
        bodyPr = tf._txBody.find(qn("a:bodyPr"))
        if bodyPr is not None:
            # vert270 = bottom-to-top (matches vertical-rl side labels / rotate180)
            bodyPr.set("vert", "vert270")
    except Exception:
        pass


def _conic_angle(tok: str) -> float | None:
    tok = tok.strip()
    try:
        if tok.endswith("%"):
            return float(tok[:-1]) * 3.6
        if tok.endswith("deg"):
            return float(tok[:-3])
        if tok.endswith("turn"):
            return float(tok[:-4]) * 360.0
        return float(tok)
    except ValueError:
        return None


def _parse_conic_gradient(css: str):
    """Parse a conic-gradient into [(RGBColor, start_deg, end_deg), ...]."""
    if not css or "conic-gradient" not in css:
        return None
    i = css.find("conic-gradient(") + len("conic-gradient(")
    depth, end = 1, len(css)
    for j in range(i, len(css)):
        if css[j] == "(":
            depth += 1
        elif css[j] == ")":
            depth -= 1
            if depth == 0:
                end = j
                break
    body = css[i:end]
    parts, buf, d = [], "", 0
    for ch in body:
        if ch == "(":
            d += 1
        elif ch == ")":
            d -= 1
        if ch == "," and d == 0:
            parts.append(buf); buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)

    segs: list[list] = []
    cursor = 0.0
    for part in parts:
        m = re.match(r"\s*(rgba?\([^)]*\)|#[0-9a-fA-F]{3,6})", part)
        if not m:
            continue
        cres = _css_color_to_rgb(m.group(1))
        if not cres:
            continue
        nums = [t for t in part[m.end():].split() if t]
        start = _conic_angle(nums[0]) if len(nums) >= 1 else cursor
        end_a = _conic_angle(nums[1]) if len(nums) >= 2 else None
        if start is None:
            start = cursor
        segs.append([cres[0], start, end_a])
        cursor = end_a if end_a is not None else start
    for k in range(len(segs)):
        if segs[k][2] is None or segs[k][2] <= segs[k][1]:
            segs[k][2] = segs[k + 1][1] if k + 1 < len(segs) else 360.0
    return segs or None


def _render_conic_gradient(slide, el: dict, x_in, y_in, w_in, h_in) -> bool:
    """Rasterize a conic-gradient (pie/donut ring) to a picture — OOXML has none."""
    if not _HAVE_PIL:
        return False
    segs = _parse_conic_gradient(el.get("backgroundImage", ""))
    if not segs:
        return False
    try:
        from io import BytesIO

        from PIL import Image, ImageDraw
    except Exception:
        return False
    S = 700
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for color, a0, a1 in segs:
        # PIL angles start at 3 o'clock; CSS conic starts at 12 o'clock → -90.
        d.pieslice([0, 0, S - 1, S - 1], a0 - 90, a1 - 90,
                   fill=(int(color[0]), int(color[1]), int(color[2]), 255))
    radius_px = _parse_border_radius_px(el)
    if radius_px > 0 and radius_px >= 0.5 * min(el.get("width", 0), el.get("height", 0)):
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, S - 1, S - 1], fill=255)
        img.putalpha(mask)
    buf = BytesIO()
    img.save(buf, "PNG")
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    _add_image_from_data_uri(
        slide, uri, Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in),
    )
    return True


def _find_top_accent(el: dict, radius_px: float) -> dict | None:
    """A thin, full-width, text-free colored child flush with the card's top edge
    (e.g. a ::before accent strip) — rendered specially so it inherits the card's
    rounded top corners instead of poking square corners past them."""
    ew, eh = el.get("width", 0), el.get("height", 0)
    if ew <= 0 or eh <= 0:
        return None
    ex, ey = el.get("x", 0), el.get("y", 0)
    for ch in el.get("children", []):
        if ch.get("_skip") or ch.get("children"):
            continue
        if ch.get("text", "").strip() or _any_descendant_has_text(ch):
            continue
        has_fill = (
            _css_color_to_rgb(ch.get("backgroundColor", "")) is not None
            or bool(_parse_css_gradient(ch.get("backgroundImage", "")))
        )
        if not has_fill:
            continue
        chh, cw = ch.get("height", 0), ch.get("width", 0)
        rel_x, rel_y = ch.get("x", 0) - ex, ch.get("y", 0) - ey
        if abs(rel_y) > 3 or chh > eh * 0.25 or chh > radius_px * 2 + 6:
            continue
        if cw < ew * 0.85 or rel_x > ew * 0.1:
            continue
        return ch
    return None


def _fill_accent(shape, el: dict, backdrop: RGBColor | None) -> None:
    """Fill a shape with an accent element's solid or gradient background."""
    if _parse_css_gradient(el.get("backgroundImage", "")):
        _apply_gradient_fill(shape._element, el["backgroundImage"], backdrop)
        return
    res = _css_color_to_rgb(el.get("backgroundColor", ""))
    if res:
        col, a = res
        shape.fill.solid()
        shape.fill.fore_color.rgb = (
            _blend_over(col, a, backdrop) if a < 0.99 and backdrop is not None else col
        )
    else:
        shape.fill.background()


def _render_bg_shape(
    slide,
    el: dict,
    x_in: float,
    y_in: float,
    w_in: float,
    h_in: float,
    opacity: float,
    backdrop: RGBColor | None = None,
) -> None:
    """Render a background/border rectangle (optionally rounded)."""
    bg_result = _css_color_to_rgb(el.get("backgroundColor", ""))
    has_fill = bg_result is not None
    has_gradient = bool(_parse_css_gradient(el.get("backgroundImage", "")))

    border_color_str = el.get("borderColor")
    border_width = el.get("borderWidth", 0)
    has_border = bool(border_color_str) and border_width > 0

    # A left-border accent (border-left: Npx solid <color>) is a common
    # decorative bar. On a rounded card a plain rectangle bar would poke square
    # corners past the rounded edge, so we reproduce it as a same-radius rounded
    # shape behind the card, with the card inset to the right so only the left
    # rounded sliver shows (the only way to get a rounded-left accent in PPTX).
    left_border_color = el.get("borderLeftColor")
    left_border_width = el.get("borderLeftWidth", 0)
    left_border_style = el.get("borderLeftStyle")
    left_result = _css_color_to_rgb(left_border_color) if left_border_color else None
    has_left_accent = bool(
        left_result
        and left_border_width > 0
        and left_border_style not in (None, "none")
    )

    if not has_fill and not has_border and not has_gradient and not has_left_accent:
        return

    radius_px = _parse_border_radius_px(el)
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius_px > 0 else MSO_SHAPE.RECTANGLE

    card_x, card_w = x_in, w_in
    card_y, card_h = y_in, h_in
    if has_left_accent:
        accent_color = left_result[0]
        if left_result[1] < 0.99 and backdrop is not None:
            accent_color = _blend_over(accent_color, left_result[1], backdrop)
        bar_w = max(left_border_width * PIXELS_TO_INCHES_X, 0.03)
        if radius_px > 0:
            # Rounded accent: full-size rounded rect underneath, card inset right.
            accent = slide.shapes.add_shape(
                shape_type, Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in),
            )
            _set_corner_radius(
                accent, radius_px, el.get("width", 100), el.get("height", 100),
            )
            _strip_theme_effect(accent)
            accent.fill.solid()
            accent.fill.fore_color.rgb = accent_color
            accent.line.fill.background()
            card_x = x_in + bar_w
            card_w = max(w_in - bar_w, 0.05)

    # A top accent bar (e.g. a ::before strip or a thin full-width child at the
    # card's top edge) drawn as a plain rectangle would poke square corners past
    # the card's rounded top. Reproduce it the same way as the left accent: a
    # same-radius rounded rect the full card size UNDER the card, with the card
    # pushed down by the bar height so only the rounded top sliver shows.
    if radius_px > 0:
        top_accent = _find_top_accent(el, radius_px)
        if top_accent is not None:
            bar_h = max(top_accent.get("height", 0) * PIXELS_TO_INCHES_Y, 0.03)
            acc = slide.shapes.add_shape(
                shape_type, Inches(card_x), Inches(y_in), Inches(card_w), Inches(h_in),
            )
            _set_corner_radius(acc, radius_px, el.get("width", 100), el.get("height", 100))
            _strip_theme_effect(acc)
            _fill_accent(acc, top_accent, backdrop)
            acc.line.fill.background()
            card_y = y_in + bar_h
            card_h = max(h_in - bar_h, 0.05)
            top_accent["_skip"] = True

    shape = slide.shapes.add_shape(
        shape_type,
        Inches(card_x), Inches(card_y),
        Inches(card_w), Inches(card_h),
    )

    if radius_px > 0:
        _set_corner_radius(
            shape, radius_px, el.get("width", 100), el.get("height", 100),
        )
    _strip_theme_effect(shape)

    if has_gradient:
        _apply_gradient_fill(shape._element, el["backgroundImage"], backdrop)
    elif has_fill:
        bg_color, bg_alpha = bg_result
        effective_alpha = bg_alpha * opacity
        shape.fill.solid()
        if effective_alpha < 0.99 and backdrop is not None:
            shape.fill.fore_color.rgb = _blend_over(bg_color, effective_alpha, backdrop)
        else:
            shape.fill.fore_color.rgb = bg_color
            if effective_alpha < 0.99:
                _apply_fill_alpha(shape, effective_alpha)
    else:
        shape.fill.background()

    if has_border:
        border_result = _css_color_to_rgb(border_color_str)
        if border_result and border_result[1] > 0.15:
            border_color = border_result[0]
            if border_result[1] < 0.99 and backdrop is not None:
                border_color = _blend_over(border_color, border_result[1], backdrop)
            shape.line.color.rgb = border_color
            shape.line.width = Pt(max(border_width * CSS_PX_TO_PT, 0.5))
        else:
            shape.line.fill.background()
    else:
        shape.line.fill.background()

    _apply_rotation(shape, el)

    # Square left accent bar (non-rounded cards): a thin filled rectangle on top.
    if has_left_accent and radius_px <= 0:
        bar_w = max(left_border_width * PIXELS_TO_INCHES_X, 0.03)
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(x_in), Inches(y_in),
            Inches(bar_w), Inches(h_in),
        )
        _strip_theme_effect(bar)
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent_color
        bar.line.fill.background()


def _apply_shape_bg(
    shape_or_txbox,
    el: dict,
    opacity: float,
    backdrop: RGBColor | None = None,
) -> None:
    """Apply background fill (solid or gradient) to a shape or textbox."""
    gradient_css = el.get("backgroundImage", "")
    is_gradient_text = el.get("isGradientText", False)

    # Don't apply gradient as bg fill when the gradient is for text coloring
    if not is_gradient_text and _parse_css_gradient(gradient_css):
        _apply_gradient_fill(shape_or_txbox._element, gradient_css, backdrop)
        return

    bg_result = _css_color_to_rgb(el.get("backgroundColor", ""))
    if bg_result:
        bg_color, bg_alpha = bg_result
        effective_alpha = bg_alpha * opacity
        shape_or_txbox.fill.solid()
        if effective_alpha < 0.99 and backdrop is not None:
            shape_or_txbox.fill.fore_color.rgb = _blend_over(
                bg_color, effective_alpha, backdrop,
            )
        else:
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
    backdrop: RGBColor | None = None,
    extra_left_px: float = 0.0,
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

    font_color = _resolve_font_color(el, backdrop)
    font_family = _resolve_pptx_font(el.get("fontFamily", "Calibri"))
    is_bold = el.get("fontWeight", "400") in ("bold", "600", "700", "800", "900")
    is_italic = el.get("fontStyle", "normal") == "italic"

    # Single line unless the CSS content box is tall enough for 2+ line boxes.
    # (Use content height, not border-box height, so padding doesn't misclassify
    # a padded pill/button as multi-line and let it wrap.)
    line_unit_px = (_line_height_ratio(el) or 1.3) * el.get("fontSize", 20)
    content_h_px = el.get("height", 0) - el.get("paddingTop", 0) - el.get("paddingBottom", 0)
    is_single_line = content_h_px <= line_unit_px * 1.6

    # A single line must fit its box: shrink the point size if the substituted
    # font is wider than the source font was.
    if is_single_line:
        pad_left_px = max(el.get("paddingLeft", 0), extra_left_px)
        avail_in = w_in - (pad_left_px + el.get("paddingRight", 0)) * PIXELS_TO_INCHES_X
        font_size_pt = _fit_font_size_single_line(
            text, font_size_pt, font_family, is_bold,
            el.get("letterSpacing", 0), avail_in,
        )

    min_text_height = font_size_pt * 1.5 / 72
    h_in = max(h_in, min_text_height)

    alignment, vertical_anchor = _resolve_alignment(el, is_single_line, has_visual_bg)

    radius_px = _parse_border_radius_px(el)
    has_border = bool(el.get("borderColor")) and el.get("borderWidth", 0) > 0
    box_holder = None

    if has_visual_bg or has_border:
        # Any text element that also paints a box (fill and/or border, e.g. a
        # bordered "stamp") is rendered as an autoshape so the border/fill and any
        # rotation apply to the same box the text lives in.
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE if radius_px > 0 else MSO_SHAPE.RECTANGLE,
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
        )
        _strip_theme_effect(shape)
        if radius_px > 0:
            _set_corner_radius(shape, radius_px, el.get("width", 100), el.get("height", 100))
        if has_visual_bg:
            _apply_shape_bg(shape, el, opacity, backdrop)
        else:
            shape.fill.background()
        if has_border:
            br = _css_color_to_rgb(el.get("borderColor", ""))
            if br and br[1] > 0.15:
                bc = _blend_over(br[0], br[1], backdrop) if br[1] < 0.99 and backdrop else br[0]
                shape.line.color.rgb = bc
                shape.line.width = Pt(max(el.get("borderWidth", 1) * CSS_PX_TO_PT, 0.5))
            else:
                shape.line.fill.background()
        else:
            shape.line.fill.background()
        box_holder = shape
        tf = shape.text_frame
    else:
        txbox = slide.shapes.add_textbox(
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
        )
        box_holder = txbox
        tf = txbox.text_frame

    # A single-line source element (height ~ one line box) must never wrap onto a
    # second line under a substituted font — that reflow is the most visible
    # conversion defect. Disable wrapping for it so a slightly-wider fallback
    # overhangs invisibly instead of breaking. Genuine multi-line blocks keep
    # wrapping. auto_size is left off so the authored point size is preserved.
    tf.word_wrap = not is_single_line
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = vertical_anchor
    _apply_text_padding(tf, el, extra_left_px)
    _apply_vertical_text(tf, el)
    _apply_rotation(box_holder, el)

    p = tf.paragraphs[0]
    _apply_line_spacing(p, el)

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

    # Real gradient text: LibreOffice and PowerPoint both render a run-level
    # <a:gradFill>, so reproduce the CSS gradient. _resolve_font_color already set
    # the first stop as a solid base for any viewer that ignores the gradient.
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
    backdrop: RGBColor | None = None,
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
        _strip_theme_effect(shape)
        _apply_shape_bg(shape, el, opacity, backdrop)
        shape.line.fill.background()
        box_holder = shape
        tf = shape.text_frame
    else:
        txbox = slide.shapes.add_textbox(
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
        )
        if has_bg:
            _apply_shape_bg(txbox, el, opacity, backdrop)
        box_holder = txbox
        tf = txbox.text_frame

    # Explicit <br> line breaks arrive as '\n' runs. When the author hard-broke
    # the lines, honor exactly those breaks and disable wrapping so a substituted
    # font can't add extra lines. A heading/logo that is one line in the source
    # (mixed inline color spans, no <br>) must also stay one line — treat it like
    # a single-line text leaf: no wrap + width-fit. Only genuine flowing
    # paragraphs (multiple lines, no breaks) keep wrapping.
    has_hard_breaks = any(rd.get("text") == "\n" for rd in runs_data)
    line_unit_px = (_line_height_ratio(el) or 1.3) * el.get("fontSize", 20)
    content_h_px = el.get("height", 0) - el.get("paddingTop", 0) - el.get("paddingBottom", 0)
    is_single_line = not has_hard_breaks and content_h_px <= line_unit_px * 1.6

    # Uniform shrink factor so a one-line mixed-run heading fits its box width.
    run_scale = 1.0
    if is_single_line:
        avail_in = w_in - (el.get("paddingLeft", 0) + el.get("paddingRight", 0)) * PIXELS_TO_INCHES_X
        total_in = 0.0
        for rd in runs_data:
            t = rd.get("text", "")
            if not t.strip():
                continue
            tr = rd.get("textTransform", "none")
            t = t.upper() if tr == "uppercase" else t.lower() if tr == "lowercase" else t.title() if tr == "capitalize" else t
            sz = max(MIN_FONT_SIZE_PT, min(rd.get("fontSize", el.get("fontSize", 20)) * CSS_PX_TO_PT, MAX_FONT_SIZE_PT))
            fam = _resolve_pptx_font(rd.get("fontFamily", el.get("fontFamily", "Calibri")))
            bold = rd.get("fontWeight", "400") in ("bold", "600", "700", "800", "900")
            est = _estimate_text_width_in(t, sz, fam, bold, el.get("letterSpacing", 0))
            total_in += est or 0.0
        if total_in > avail_in > 0.05:
            run_scale = (avail_in / total_in) * 0.98

    tf.word_wrap = not (has_hard_breaks or is_single_line)
    tf.auto_size = MSO_AUTO_SIZE.NONE
    _apply_text_padding(tf, el)
    _apply_vertical_text(tf, el)
    _apply_rotation(box_holder, el)

    p = tf.paragraphs[0]
    p.alignment = alignment
    _apply_line_spacing(p, el)

    for run_data in runs_data:
        text = run_data.get("text", "")
        if text == "\n":
            p = tf.add_paragraph()
            p.alignment = alignment
            _apply_line_spacing(p, el)
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
        run_size = max(MIN_FONT_SIZE_PT, min(run_size, MAX_FONT_SIZE_PT)) * run_scale
        run_size = max(MIN_FONT_SIZE_PT, run_size)

        run_is_gradient = run_data.get("isGradientText", False)
        run_bg_image = run_data.get("backgroundImage", "")

        color_result = _css_color_to_rgb(run_data.get("color", el.get("color", "rgb(255,255,255)")))
        if run_is_gradient and run_bg_image:
            run_color = _first_gradient_color(run_bg_image) or RGBColor(0xFF, 0xFF, 0xFF)
        elif color_result:
            run_color, run_alpha = color_result
            if run_alpha < 0.99 and backdrop is not None:
                run_color = _blend_over(run_color, run_alpha, backdrop)
        else:
            run_color = _resolve_font_color(el, backdrop)

        run_bold = run_data.get("fontWeight", "400") in ("bold", "600", "700", "800", "900")
        run_italic = run_data.get("fontStyle", "normal") == "italic"
        run_family = _resolve_pptx_font(run_data.get("fontFamily", el.get("fontFamily", "Calibri")))

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


def _render_measured_element(
    slide, el: dict, backdrop: RGBColor | None = None, inherited_opacity: float = 1.0,
) -> None:
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
    if el.get("_skip"):  # overlay baked into an underlying image
        return

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
    # A CSS parent opacity visually multiplies its descendants. Containers are
    # not always collapsed (e.g. a top-level faint image wrapper), so fold the
    # inherited opacity in here and pass it down, or it is silently dropped.
    opacity = el.get("opacity", 1.0) * inherited_opacity

    # Detect standalone left-border accents (common decorative pattern)
    has_left_accent = (
        el.get("borderLeftWidth", 0) > 0
        and el.get("borderLeftStyle") not in (None, "none")
        and bool(_css_color_to_rgb(el.get("borderLeftColor", "")))
    )

    # Backdrop handed to descendants for alpha flattening: an element with its own
    # background (e.g. a navy card on a cream slide) becomes the backdrop for its
    # children, so a translucent pill inside it flattens over navy, not the slide.
    child_backdrop = backdrop
    _bgc = _css_color_to_rgb(el.get("backgroundColor", ""))
    if _bgc is not None:
        _c, _a = _bgc
        eff = _a * opacity
        child_backdrop = (
            _c if eff >= 0.999 or backdrop is None
            else _blend_over(_c, eff, backdrop)
        )
    elif has_gradient:
        _gc = _first_gradient_color(el.get("backgroundImage", ""))
        if _gc is not None:
            child_backdrop = _gc

    if (is_image or el.get("isSvg")) and el.get("src", "").startswith("data:image/"):
        pic = _add_image_from_data_uri(
            slide, el["src"],
            Inches(x_in), Inches(y_in),
            Inches(w_in), Inches(h_in),
            border_radius_px=_parse_border_radius_px(el),
            width_px=el.get("width", 0),
            height_px=el.get("height", 0),
            opacity=opacity,
            object_fit=el.get("objectFit"),
            natural_w=el.get("naturalWidth", 0),
            natural_h=el.get("naturalHeight", 0),
        )
        if pic is not None:
            _apply_rotation(pic, el)
        return

    # Unreasterized SVGs: skip (no python-pptx SVG support)
    if el.get("isSvg"):
        return

    # conic-gradient (pie/donut) — rasterize to a picture, then draw children
    # (e.g. the center hole + label) on top.
    if "conic-gradient" in (el.get("backgroundImage") or ""):
        _render_conic_gradient(slide, el, x_in, y_in, w_in, h_in)
        for child in children:
            _render_measured_element(slide, child, child_backdrop, opacity)
        return

    if has_inline_runs:
        if has_visual_bg or has_border or has_left_accent:
            _render_bg_shape(slide, el, x_in, y_in, w_in, h_in, opacity, backdrop)
        _render_inline_runs(slide, el, x_in, y_in, w_in, h_in, has_visual_bg, opacity, backdrop)
        for child in children:
            if child.get("tag") not in (
                "span", "strong", "em", "b", "i", "a", "code", "mark",
                "sub", "sup", "small", "u", "s", "del",
            ):
                _render_measured_element(slide, child, child_backdrop, opacity)
        return

    is_text_leaf = has_text and not _any_descendant_has_text(el)
    if is_text_leaf:
        # A leading, in-flow decorative child (e.g. an inline flag dot before a
        # city name: <h4><span class="flag-dot"></span>Tokyo</h4>) occupies
        # horizontal space in the browser, so the text must start after it or the
        # dot overprints the first letter. Absolutely-positioned accents (bullet
        # ::before) sit in the padding and are handled by padding instead.
        extra_left_px = 0.0
        el_left = el.get("x", 0)
        el_mid_y = el.get("y", 0) + el.get("height", 0) / 2
        for child in children:
            if child.get("text", "").strip() or _any_descendant_has_text(child):
                continue
            if child.get("position") in ("absolute", "fixed"):
                continue
            cx = child.get("x", 0)
            cright = cx + child.get("width", 0)
            c_top, c_bot = child.get("y", 0), child.get("y", 0) + child.get("height", 0)
            near_left = cx <= el_left + el.get("width", 0) * 0.4
            vertically_on_line = c_top <= el_mid_y <= c_bot
            if near_left and cright > el_left and vertically_on_line:
                extra_left_px = max(extra_left_px, cright - el_left + 8)
        _render_text_element(
            slide, el, x_in, y_in, w_in, h_in, has_visual_bg, opacity, backdrop,
            extra_left_px,
        )
        # Render the decorative, text-free children themselves (e.g. bullet dots).
        for child in children:
            _render_measured_element(slide, child, child_backdrop, opacity)
        return

    if has_visual_bg or has_border or has_left_accent:
        _render_bg_shape(slide, el, x_in, y_in, w_in, h_in, opacity, backdrop)

    for child in children:
        _render_measured_element(slide, child, child_backdrop, opacity)


# ---------------------------------------------------------------------------
# Pipeline stages (public API)
# ---------------------------------------------------------------------------


def _walk_elements(elements: list[dict]):
    """Yield every element in a measurement tree (depth-first)."""
    for el in elements:
        yield el
        yield from _walk_elements(el.get("children", []))


async def _rasterize_inline_svgs(
    page,
    measurements: list[dict],
    *,
    include_picture_fallbacks: bool = False,
) -> None:
    """Prepare deterministic image fallbacks for SVG-backed measurements.

    Inline SVGs still become raster images for the legacy python-pptx path.
    SVG data-URI ``<img>`` nodes retain their original ``src`` for the
    OfficeCLI path and additionally receive a browser-rendered PNG fallback
    for OfficeCLI versions without direct SVG support. The screenshot is of
    the measured element, so CSS object-fit behavior is already included.
    """
    for i, slide_data in enumerate(measurements):
        svg_els = [e for e in _walk_elements(slide_data.get("elements", []))
                   if e.get("isSvg") and e.get("svgId")]
        image_els = []
        if include_picture_fallbacks:
            image_els = [
                e
                for e in _walk_elements(slide_data.get("elements", []))
                if e.get("isSvgDataUri") and e.get("imageId")
            ]
        if not svg_els and not image_els:
            continue

        await page.evaluate(f"""
            document.querySelectorAll('.slide').forEach((s, idx) => {{
                s.style.display = idx === {i} ? 'flex' : 'none';
                if (idx === {i}) s.classList.add('active');
                else s.classList.remove('active');
            }});
        """)
        await page.wait_for_timeout(200)

        for el in [*svg_els, *image_els]:
            element_id = el.get("svgId") or el.get("imageId")
            try:
                handle = await page.query_selector(
                    f'[data-pptx-id="{element_id}"]'
                )
                if not handle:
                    continue
                png_bytes = await handle.screenshot(type="png")
                encoded = base64.b64encode(png_bytes).decode()
                png_src = f"data:image/png;base64,{encoded}"
                if el.get("isSvg"):
                    el["isImage"] = True
                    el["isSvg"] = False
                    el["src"] = png_src
                    el["children"] = []
                else:
                    el["rasterFallbackSrc"] = png_src
            except Exception:
                logger.debug("Failed to rasterize SVG %s", element_id or "?")


async def extract_measurements(
    html_path: str,
    *,
    include_picture_fallbacks: bool = False,
    officecli_mode: bool = False,
) -> list[dict]:
    """Open an HTML slide deck in headless Chromium and measure every element.

    Args:
        html_path: Path to the HTML file.
        include_picture_fallbacks: Also capture browser-rendered PNG fallbacks
            for SVG data-URI ``<img>`` nodes. The legacy renderer leaves this
            disabled; the OfficeCLI compiler enables it when needed.
        officecli_mode: Enable the paragraph-preserving and blockified-child
            extraction needed by the OfficeCLI object compiler. The default
            keeps the legacy python-pptx measurement semantics unchanged.

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

        measurements = await page.evaluate(
            EXTRACTION_JS,
            {"officecliMode": officecli_mode},
        )

        await _rasterize_inline_svgs(
            page,
            measurements,
            include_picture_fallbacks=include_picture_fallbacks,
        )

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


def _overlay_paint(el: dict) -> tuple[int, int, int, float] | None:
    """If ``el`` is a translucent fill overlay (no text/image), return (r,g,b,a)."""
    if el.get("text", "").strip() or el.get("inlineRuns"):
        return None
    if el.get("isImage") or el.get("isSvg"):
        return None
    if not el.get("isGradientText"):
        grad = _parse_css_gradient(el.get("backgroundImage", ""))
        if grad:
            n = len(grad)
            r = sum(c[0] for c, _, _ in grad) // n
            g = sum(c[1] for c, _, _ in grad) // n
            b = sum(c[2] for c, _, _ in grad) // n
            a = sum(al for _, _, al in grad) / n
            return (r, g, b, a) if a < 0.985 else None
    bg = _css_color_to_rgb(el.get("backgroundColor", ""))
    if bg and bg[1] < 0.985:
        return (bg[0][0], bg[0][1], bg[0][2], bg[1])
    return None


def _rect_of(el: dict) -> tuple[float, float, float, float]:
    return (el.get("x", 0), el.get("y", 0), el.get("width", 0), el.get("height", 0))


def _coextensive(a, b, thresh: float = 0.9) -> bool:
    """True if rects a and b cover >= thresh of each other's area."""
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return False
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter >= thresh * aw * ah and inter >= thresh * bw * bh


def _bake_full_bleed_overlays(slide_data: dict) -> None:
    """Composite a full-bleed translucent overlay onto the image beneath it.

    A hero pattern is <img class="slide-bg">…<div class="scrim"> where the scrim
    is a translucent gradient that darkens the photo. Flattening the scrim to an
    opaque color would erase the photo, and LibreOffice ignores gradient-stop
    alpha, so instead we bake the overlay into the image pixels (Pillow) and skip
    drawing the overlay — reproducing the darkened photo in every viewer.
    """
    if not _HAVE_PIL:
        return
    try:
        from io import BytesIO

        from PIL import Image
    except Exception:
        return

    order = list(_walk_elements(slide_data.get("elements", [])))
    images = [e for e in order if e.get("isImage") and str(e.get("src", "")).startswith("data:image/")]
    if not images:
        return
    for i, el in enumerate(order):
        paint = _overlay_paint(el)
        if paint is None:
            continue
        ov_rect = _rect_of(el)
        # find an earlier-painted, ~coextensive image (drawn behind this overlay)
        target = None
        for img in images:
            if order.index(img) < i and _coextensive(_rect_of(img), ov_rect):
                target = img
        if target is None:
            continue
        m = re.match(r"data:image/(\w+);base64,(.*)", target["src"], re.DOTALL)
        if not m:
            continue
        try:
            base = Image.open(BytesIO(base64.b64decode(m.group(2)))).convert("RGBA")
            r, g, b, a = paint
            ov = Image.new("RGBA", base.size, (r, g, b, int(round(a * 255))))
            out = Image.alpha_composite(base, ov).convert("RGB")
            buf = BytesIO()
            out.save(buf, "JPEG", quality=88)
            target["src"] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            el["_skip"] = True
        except Exception:
            logger.debug("overlay bake failed", exc_info=True)


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

        _bake_full_bleed_overlays(slide_data)
        backdrop = _resolve_backdrop(slide_data)
        for el in slide_data.get("elements", []):
            _render_measured_element(slide, el, backdrop)

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


