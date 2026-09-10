"""Chromium measurement shared by the Author compiler.

This module deliberately has no PowerPoint renderer dependency. It owns the
browser layout/measurement DTO and the small raster-fallback pass consumed by
the OfficeCLI renderer.
"""

from __future__ import annotations

import base64
import logging
import os

logger = logging.getLogger(__name__)

SLIDE_CANVAS_WIDTH_PX = 1920
SLIDE_CANVAS_HEIGHT_PX = 1080
MAX_HTML_SIZE_MB = 10
PLAYWRIGHT_TIMEOUT_MS = 30_000
FONT_LOAD_WAIT_MS = 1_000

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

def _count_elements(elements: list[dict]) -> int:
    """Count a measurement tree for diagnostic logging."""
    return sum(1 + _count_elements(element.get("children", [])) for element in elements)


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

    Inline SVGs are rasterized when the Author compiler needs a deterministic
    image fallback. SVG data-URI ``<img>`` nodes retain their original ``src``
    for OfficeCLI and additionally receive a browser-rendered PNG fallback for
    OfficeCLI versions without direct SVG support. The screenshot is of the
    measured element, so CSS object-fit behavior is already included.
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
            keeps the default measurement DTO semantics unchanged.

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
