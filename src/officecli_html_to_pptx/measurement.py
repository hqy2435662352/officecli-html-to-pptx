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
        // Direct text nodes with browser-equivalent whitespace collapsing applied
        // to the element's own inline flow (leading/trailing whitespace drops,
        // interior runs collapse to one space).  No source character is added or
        // dropped besides that CSS white-space:normal collapsing.
        let text = '';
        for (const node of el.childNodes) {
            if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
        }
        return text.replace(/\\s+/g, ' ').trim();
    }

    const LIST_TAGS = ['ul', 'ol'];
    function isListTag(node) {
        return !!node && LIST_TAGS.includes(node.tagName.toLowerCase());
    }
    // 0-based list nesting level: the number of enclosing <ul>/<ol> elements
    // including the element's own list, minus one.  A direct item of a
    // top-level list is level 0, which is the only level the initial list
    // surface lowers.
    function listLevel(node) {
        let count = isListTag(node) ? 1 : 0;
        for (let parent = node.parentElement; parent; parent = parent.parentElement) {
            if (isListTag(parent)) count += 1;
        }
        return Math.max(0, count - 1);
    }

    // Whitespace collapsing is a property of the whole inline flow, not of one
    // DOM node: a boundary space that one sibling owns must still survive next
    // to another.  Runs are therefore collected with their raw text and
    // collapsed once, after the whole flow is known.
    //
    // One segment is one browser line: an authored <br> ends the segment before
    // it and starts the next.  Within a segment:
    //  - whitespace runs collapse to exactly one space;
    //  - that space stays with the run that owns the source character, so a
    //    boundary space never migrates into a differently formatted run;
    //  - only the line-box edges drop whitespace: the start of the flow, the
    //    end of the flow, and a duplicate of a space the flow already owns.
    function collapseSegment(segment) {
        const collapsed = [];
        // A space whose owning run is already emitted, but whose fate is still
        // open: it survives unless the line ends here (line-box end edge) or
        // the next run starts with a space of its own (a duplicate).
        let pendingSpace = false;
        const flush = () => {
            if (pendingSpace && collapsed.length) {
                collapsed[collapsed.length - 1].text += ' ';
            }
            pendingSpace = false;
        };
        for (const run of segment) {
            const raw = String(run.text == null ? '' : run.text);
            if (!raw) continue;
            // The segment is one browser line, so a newline inside it is only
            // source formatting whitespace and collapses like any other space.
            const match = raw.match(/^(\\s*)([\\s\\S]*?)(\\s*)$/);
            const core = match[2].replace(/\\s+/g, ' ');
            if (!core) {
                // Whitespace-only source resolves to a boundary space of the
                // flow and carries no format of its own: at the flow start it
                // is the line leading space (dropped), otherwise it attaches to
                // the run emitted before it.
                if (collapsed.length) pendingSpace = true;
                continue;
            }
            // This run's own leading space stays inside this run, unless the
            // flow already owns a space at that boundary: then the earlier
            // space keeps the position and this duplicate is removed.  A space
            // left pending by the previous run of *this same* format is the
            // same boundary space, so it is claimed rather than duplicated.
            let text = core;
            if (match[1]) {
                const last = collapsed.length
                    ? collapsed[collapsed.length - 1]
                    : null;
                const format = inlineRunFormat(run);
                if (pendingSpace && last && last._format === format) {
                    // The boundary space the previous run left pending belongs
                    // to the run this text joins, so it moves inside the joined
                    // text rather than being appended after the merge.
                    text = ' ' + text;
                    pendingSpace = false;
                } else if (!pendingSpace && last && !last.text.endsWith(' ')) {
                    text = ' ' + text;
                }
            }
            flush();
            const format = inlineRunFormat(run);
            const last = collapsed.length ? collapsed[collapsed.length - 1] : null;
            if (last && last._format === format) {
                last.text += text;
            } else {
                collapsed.push({ ...run, text: text, _format: format });
            }
            if (match[3]) pendingSpace = true;
        }
        // The line ends here, so a space still pending is the line-box end edge
        // and is dropped rather than emitted.
        return collapsed;
    }

    // A run boundary is a formatting boundary, not a DOM node boundary.  Two
    // runs merge only inside one authored line and only with identical
    // resolved formatting, so a nested <strong> inside a <span> still wins and
    // a differently formatted neighbour is never absorbed.  The identity rides
    // on the run as a private '_format' key the compiler never reads.
    function inlineRunFormat(run) {
        return [
            run.color, run.fontSize, run.fontFamily, run.fontWeight,
            run.fontStyle, run.textTransform,
            run.textDecoration === undefined ? 'none' : run.textDecoration,
            run.href === undefined || run.href === null ? '' : run.href,
        ].join('\\u0000');
    }

    function collapseInlineRuns(runs) {
        const flow = [];
        let segment = [];
        let breakRun = null;
        const closeSegment = () => {
            flow.push(...collapseSegment(segment));
            if (breakRun) flow.push(breakRun);
            segment = [];
            breakRun = null;
        };
        for (const run of runs) {
            // Only an explicitly marked break closes a segment.  A newline is a
            // break where it was *authored* as one (a <br>, or a newline in
            // white-space:pre* text); a whitespace-only text node of ordinary
            // ``white-space: normal`` content is authored whitespace, so it
            // collapses to a boundary space like any other source newline.
            if (run.br === true) {
                // Keep the authored break marker: a trailing <br> is a real
                // empty paragraph, while a trailing source newline is not.  A
                // break that a nested inline element produced carries the same
                // ``br`` marker up through the recursion, so it closes the
                // segment of this flow too.
                breakRun = { ...run, text: '\\n', br: true };
                closeSegment();
                continue;
            }
            segment.push(run);
        }
        closeSegment();
        // A trailing source newline is the indentation that closes the flow, and
        // a whitespace run never becomes text of its own.
        const kept = flow.filter(item => item.text === '\\n' || /\\S/.test(item.text));
        while (kept.length && kept[kept.length - 1].text === '\\n' && kept[kept.length - 1].br !== true) {
            kept.pop();
        }
        for (const item of kept) {
            delete item.br;
            delete item._format;
        }
        return kept;
    }

    // Style fields of one resolved inline frame.  ``href`` carries the nearest
    // enclosing anchor target so a link inside a styled span stays supported;
    // it is null for every run that is not descended from an <a>.
    function inlineRunFields(style, text, href) {
        const bgImage = style.backgroundImage !== 'none' ? style.backgroundImage : null;
        const fillColor = style.webkitTextFillColor || '';
        const isGradientText = (fillColor === 'transparent' || fillColor === 'rgba(0, 0, 0, 0)') && bgImage && bgImage.includes('gradient');
        return {
            text: text,
            color: style.color,
            fontSize: parseFloat(style.fontSize),
            fontFamily: style.fontFamily,
            fontWeight: style.fontWeight,
            fontStyle: style.fontStyle,
            textTransform: style.textTransform,
            ...(officecliMode ? {textDecoration: style.textDecorationLine} : {}),
            href: href || null,
            isGradientText: isGradientText,
            backgroundImage: isGradientText ? bgImage : null,
        };
    }

    // ``topLevel`` marks the inline flow of the measured element.  Whitespace
    // collapsing is a property of the whole flow, so it runs exactly once, at
    // the top: a nested inline element contributes its raw runs and is folded
    // with the flow around it.  Collapsing a nested element on its own would
    // resolve its leading space against a line edge that does not exist and
    // drop a boundary space the authored line keeps (``Canonical: `` followed
    // by ``<span>North</span><span> Africa</span>``).
    //
    // ``href`` is the nearest enclosing anchor target: an <a> hands its own
    // target to the whole subtree it wraps, so a link's text keeps its
    // hyperlink even when it sits inside <strong>/<span>.
    function collectInlineRuns(el, style, topLevel, href) {
        const runs = [];
        const parentStyle = style || getComputedStyle(el);
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
                        if (si > 0) runs.push({ ...inlineRunFields(parentStyle, '\\n', href), textTransform: 'none', br: true });
                        if (segs[si].length) runs.push(inlineRunFields(parentStyle, segs[si], href));
                    }
                    continue;
                }
                if (!node.textContent) continue;
                runs.push(inlineRunFields(parentStyle, node.textContent, href));
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const tag = node.tagName.toLowerCase();
                if (['script','style','link','meta'].includes(tag)) continue;
                const cs = getComputedStyle(node);
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                if (tag === 'br') {
                    // The one place a break of ordinary content is declared, so
                    // it is the one place that marks one.
                    runs.push({ ...inlineRunFields(parentStyle, '\\n', href), textTransform: 'none', br: true });
                    continue;
                }
                // Only collect true inline-flow children as runs.  A tag such
                // as <b> or <small> can be a flex/grid item whose computed
                // display is blockified; treating it as an inline run loses
                // the layout gap/line break and concatenates sibling labels.
                const isInline = officecliMode
                    ? cs.display.startsWith('inline')
                    : cs.display.startsWith('inline') || INLINE_TAGS.has(tag);
                if (!isInline) continue;
                // Descend into the inline element instead of flattening it
                // through textContent: a <br> nested inside an inline element
                // is a real hard break, and every nested text node keeps the
                // computed style of its *nearest* inline element (<strong>
                // inside <span> still wins).  The nested runs stay separate
                // here: identical formatting is folded once, by the flow-level
                // collapse below.
                const childRuns = collectInlineRuns(
                    node,
                    cs,
                    false,
                    tag === 'a' ? (node.getAttribute('href') || href) : href,
                );
                for (const childRun of childRuns) {
                    runs.push(childRun);
                }
            }
        }
        if (!pre && topLevel) return collapseInlineRuns(runs);
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
        // List facts for the lowering seam.  The marker is never injected as
        // literal text: one supported top-level list becomes one Native List
        // Textbox and every direct item one Native List Paragraph whose bullet
        // or automatic number, level, and indentation are native PowerPoint
        // paragraph properties.
        let listFacts = null;
        let listItemFacts = null;
        if (tag === 'li') {
            const parent = el.parentElement;
            const parentTag = parent ? parent.tagName.toLowerCase() : '';
            listItemFacts = {
                kind: isListTag(parent) ? parentTag : '',
                level: listLevel(el),
                index: parent ? Array.from(parent.children).indexOf(el) + 1 : 1,
                // ``list-style-type: none`` stays unmarked, exactly as the
                // released literal-prefix measurement left it unmarked.
                marker: parentTag === 'ol'
                    ? 'numbered'
                    : (getComputedStyle(el).listStyleType === 'none' ? 'none' : 'bullet'),
            };
            try {
                const ms = getComputedStyle(el, '::marker');
                if (ms && ms.color) markerColor = ms.color;
            } catch(e) {}
        } else if (isListTag(el)) {
            listFacts = {
                kind: tag,
                level: listLevel(el),
                itemCount: Array.from(el.children)
                    .filter(child => child.tagName.toLowerCase() === 'li').length,
            };
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
            list: listFacts,
            listItem: listItemFacts,
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
            const runs = collectInlineRuns(el, null, true);
            if (runs.length > 0 && (!officecliMode || !hasNonInlineTextChild(el))) {
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
                data.paragraphs = textParagraphs(el, [], directText);
            }
        } else if (directText && officecliMode) {
            data.paragraphs = textParagraphs(el, [], directText);
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
                           !isTableElement && !data.list && !data.listItem &&
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
