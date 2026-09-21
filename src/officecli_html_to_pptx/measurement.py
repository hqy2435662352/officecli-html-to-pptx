"""Chromium measurement shared by the Author compiler.

This module deliberately has no PowerPoint renderer dependency. It owns the
browser layout/measurement DTO and the small raster-fallback pass consumed by
the OfficeCLI renderer.
"""

from __future__ import annotations

import base64
from io import BytesIO
import hashlib
from html import escape as _html_escape
import logging
import math
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

from PIL import Image

from ._internal.localized_capture import (
    LocalizedRegion,
    audit_localized_capture,
    validate_localized_geometry,
    validate_localized_region_overlap,
)

logger = logging.getLogger(__name__)

SLIDE_CANVAS_WIDTH_PX = 1920
SLIDE_CANVAS_HEIGHT_PX = 1080
PLAYWRIGHT_TIMEOUT_MS = 30_000
FONT_LOAD_WAIT_MS = 1_000

EXTRACTION_JS = """
({ officecliMode = false } = {}) => {
    const slides = document.querySelectorAll('.slide');
    const results = [];
    let _svgCounter = 0;
    let _imageCounter = 0;
    let _localizedCounter = 0;
    function authoredSourcePath(slideNumber, slide, element) {
        const parts = [];
        let current = element;
        while (current && current !== slide) {
            const parent = current.parentElement;
            if (!parent) break;
            const position = Array.from(parent.children).indexOf(current) + 1;
            parts.unshift(`${current.tagName.toLowerCase()}[${position}]`);
            current = parent;
        }
        return `slide[${slideNumber}]` + (parts.length ? '/' + parts.join('/') : '');
    }

    function hasPositiveCssTime(value) {
        return String(value || '').split(',').some(item => {
            const match = item.trim().match(/^(-?(?:\\d*\\.\\d+|\\d+))(ms|s)?$/i);
            if (!match) return false;
            return parseFloat(match[1]) > 0;
        });
    }

    function localizedComputedSafetyFacts(el, slide, slideNumber) {
        const animationNodes = [];
        const transitionNodes = [];
        const resourceStates = [];
        const imageStates = [];
        const nodes = [el, ...Array.from(el.querySelectorAll('*'))];
        const resourceProperties = [
            'backgroundImage', 'maskImage', 'webkitMaskImage',
            'listStyleImage', 'content',
        ];
        for (const node of nodes) {
            const style = getComputedStyle(node);
            const sourcePath = authoredSourcePath(slideNumber, slide, node);
            const animationName = String(style.animationName || '').trim();
            if (animationName && animationName !== 'none') {
                animationNodes.push({
                    sourcePath: sourcePath,
                    animationName: animationName,
                    animationDuration: String(style.animationDuration || ''),
                    animationPlayState: String(style.animationPlayState || ''),
                });
            }
            const transitionProperty = String(style.transitionProperty || '').trim();
            if (
                transitionProperty
                && transitionProperty !== 'none'
                && hasPositiveCssTime(style.transitionDuration)
            ) {
                transitionNodes.push({
                    sourcePath: sourcePath,
                    transitionProperty: transitionProperty,
                    transitionDuration: String(style.transitionDuration || ''),
                });
            }
            for (const property of resourceProperties) {
                const value = String(style[property] || '').trim();
                if (/url\\s*\\(/i.test(value)) {
                    resourceStates.push({
                        sourcePath: sourcePath,
                        property: property,
                        value: value,
                    });
                }
            }
            if (node.tagName && node.tagName.toLowerCase() === 'img') {
                imageStates.push({
                    sourcePath: sourcePath,
                    currentSrc: String(node.currentSrc || node.getAttribute('src') || ''),
                    complete: Boolean(node.complete),
                    naturalWidth: Number(node.naturalWidth || 0),
                    naturalHeight: Number(node.naturalHeight || 0),
                });
            }
        }
        return {
            animationNodes: animationNodes,
            transitionNodes: transitionNodes,
            resourceStates: resourceStates,
            imageStates: imageStates,
        };
    }
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
    // A numbered marker is written ``a:buAutoNum`` and a bullet ``a:buChar``, and
    // which one an item gets is decided here rather than by literal marker text
    // or by one list object per marker.  An item of an <ol> is numbered, and so
    // is an item of a <ul> that declares its own numbering with an explicit
    // ``list-style-type`` -- ``list-style-type`` is how any item states its own
    // marker, so one list can carry both a bullet item and a numbered item
    // exactly as a source deck's own list object can.  Everything else that is
    // not ``none`` stays a bullet.
    function listMarker(node, parentTag) {
        const styleType = String(getComputedStyle(node).listStyleType || '').trim().toLowerCase();
        if (styleType === 'none') return 'none';
        if (parentTag === 'ol') return 'numbered';
        return /decimal|roman|alpha|cjk|numeric|armenian|georgian|hebrew/.test(styleType)
            ? 'numbered'
            : 'bullet';
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
    //
    // Collapsing is formatting-free: which adjacent runs are one Canonical Run
    // is a lowering decision, so the one Canonical Run identity lives in the
    // compiler and is never restated here.
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
            // space keeps the position and this duplicate is removed.
            let text = core;
            if (match[1]) {
                const last = collapsed.length
                    ? collapsed[collapsed.length - 1]
                    : null;
                if (!pendingSpace && last && !last.text.endsWith(' ')) {
                    text = ' ' + text;
                }
            }
            flush();
            collapsed.push({ ...run, text: text });
            if (match[3]) pendingSpace = true;
        }
        // The line ends here, so a space still pending is the line-box end edge
        // and is dropped rather than emitted.
        return collapsed;
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
    // the top: a nested inline element contributes its raw runs and is
    // collapsed with the flow around it.  Collapsing a nested element on its
    // own would resolve its leading space against a line edge that does not
    // exist and drop a boundary space the authored line keeps
    // (``Canonical: `` followed by ``<span>North</span><span> Africa</span>``).
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
                // here: which adjacent runs are one Canonical Run is resolved
                // by the lowering pass, which owns that identity.
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
        // Block-level/authored paragraph boundaries are represented by the
        // element that owns this call.  An explicit <br> stays in this same
        // paragraph as a marked hard-break run; the compiler lowers it to
        // OfficeCLI's native vertical-tab control character.
        paragraphs.push({
            text: sourceRuns.map(run => String(run.text || '')).join(''),
            align: style.textAlign,
            lineHeight: style.lineHeight,
            spaceBefore: parseFloat(style.marginTop) || 0,
            spaceAfter: parseFloat(style.marginBottom) || 0,
            direction: style.direction,
            runs: sourceRuns.map(run => ({ ...run })),
        });
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

    // Capture browser soft-wrap rows for measurement/evidence only.  The
    // OfficeCLI lowering keeps authored paragraph boundaries and native hard
    // breaks; these rows never become native paragraph separators.
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

    function measureElement(el, slide, slideRect, depth, slideNumber) {
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

        // A localized fallback is one authored object. Measure its own
        // border box, retain only the source facts needed by the capture and
        // lower it as an atomic node; descendants are intentionally not
        // visited by the generic object discovery below.
        const localizedToken = el.getAttribute('data-pptx-rasterize');
        if (localizedToken !== null) {
            const localizedId = 'pptx-localized-' + (_localizedCounter++);
            el.setAttribute('data-pptx-localized-id', localizedId);
            const sourcePath = authoredSourcePath(slideNumber, slide, el);
            const explicitId = (el.getAttribute('id') || '').trim();
            return {
                tag: el.tagName.toLowerCase(),
                x: relX,
                y: relY,
                width: rect.width,
                height: rect.height,
                text: '',
                children: [],
                localizedId: localizedId,
                localizedFallback: {
                    token: localizedToken,
                    sourceIdentity: explicitId || sourcePath,
                    sourcePath: sourcePath,
                    excludedDescendantCount: el.querySelectorAll('*').length,
                    isolated: false,
                    computedSafety: localizedComputedSafetyFacts(
                        el,
                        slide,
                        slideNumber,
                    ),
                },
            };
        }

        if (rect.width < 1 || rect.height < 1) {
            if (el.hasAttribute('data-pptx-chart')) {
                const zeroSizeSpecNodes = Array.from(
                    el.querySelectorAll('script[data-pptx-chart-spec]')
                );
                return {
                    tag: el.tagName.toLowerCase(),
                    x: relX,
                    y: relY,
                    width: rect.width,
                    height: rect.height,
                    isChart: true,
                    chartSpecText: zeroSizeSpecNodes.length === 1
                        ? (zeroSizeSpecNodes[0].textContent || '')
                        : null,
                    chartSpecCount: zeroSizeSpecNodes.length,
                    chartSourceIdentity: (el.getAttribute('id') || '').trim() || null,
                    children: []
                };
            }
            return null;
        }
        if (relX + rect.width <= 0 || relY + rect.height <= 0) return null;
        if (relX >= slideRect.width || relY >= slideRect.height) return null;

        let directText = getDirectText(el);
        const tag = el.tagName.toLowerCase();
        const isChart = el.hasAttribute('data-pptx-chart');
        const chartSpecNodes = isChart
            ? Array.from(el.querySelectorAll('script[data-pptx-chart-spec]'))
            : [];
        const chartSpecText = chartSpecNodes.length === 1
            ? (chartSpecNodes[0].textContent || '')
            : null;
        const chartSourceIdentity = isChart
            ? ((el.getAttribute('id') || '').trim() || null)
            : null;

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
                marker: listMarker(el, parentTag),
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
            // A preset geometry the Contract 1.2 Author shape surface keeps as
            // a PowerPoint preset rather than inferring from CSS.  Public
            // Author HTML uses the namespaced annotation.  The private legacy
            // spelling remains a fallback solely for the hidden projection
            // seam, whose emitted nodes carry data-projection-id.
            shapeGeometry: el.getAttribute('data-pptx-shape-geometry') ||
                           el.getAttribute('data-shape-geometry'),
            // Present exactly when this element came from the V0.4.x
            // PPTX-to-Author-HTML projection.  A projected object's text
            // formatting is a reading of a source deck the product was asked to
            // reproduce, which the lowering treats differently from a value an
            // author wrote by hand.
            projectedFrom: el.getAttribute('data-projection-id'),
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
            isChart: isChart,
            chartSpecText: chartSpecText,
            chartSpecCount: chartSpecNodes.length,
            chartSourceIdentity: chartSourceIdentity,
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

        if (!isChart) {
            for (const child of el.children) {
                if (['script', 'style', 'link', 'meta'].includes(child.tagName.toLowerCase())) continue;
                const childData = measureElement(
                    child,
                    slide,
                    slideRect,
                    depth + 1,
                    slideNumber,
                );
                if (childData) data.children.push(childData);
            }
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

        // A text container whose direct children are authored <p> elements is
        // one native textbox with one native paragraph per source <p>.  Build
        // this list from the DOM rather than only from measured child boxes so
        // zero-height empty paragraphs retain their exact source cardinality.
        if (officecliMode) {
            const childElements = Array.from(el.children);
            const paragraphChildren = childElements.filter(child => {
                const childStyle = getComputedStyle(child);
                return child.tagName.toLowerCase() === 'p'
                    && childStyle.display !== 'none'
                    && childStyle.visibility !== 'hidden';
            });
            // Only a pure paragraph flow is folded.  A decorated container
            // that also owns headings, cards, or other block children must
            // keep those children as independent native objects; folding its
            // <p> descendants into the container would duplicate text and can
            // make the containing shape overflow.
            const onlyParagraphChildren = childElements.every(child => {
                const childStyle = getComputedStyle(child);
                return child.tagName.toLowerCase() === 'p'
                    && childStyle.display !== 'none'
                    && childStyle.visibility !== 'hidden';
            });
            if (paragraphChildren.length && onlyParagraphChildren) {
                const authoredParagraphs = [];
                for (const paragraphElement of paragraphChildren) {
                    const paragraphStyle = getComputedStyle(paragraphElement);
                    const paragraphRuns = collectInlineRuns(
                        paragraphElement, paragraphStyle, true,
                    );
                    authoredParagraphs.push(
                        ...textParagraphs(
                            paragraphElement,
                            paragraphRuns,
                            getDirectText(paragraphElement),
                        ),
                    );
                }
                data.paragraphs = authoredParagraphs;
                data.text = authoredParagraphs
                    .map(paragraph => paragraph.text)
                    .join('\\n');
                data.paragraphsFromChildren = true;
            }
        }

        // Measure ::before and ::after pseudo-elements as synthetic children
        for (const pseudo of isChart ? [] : ['::before', '::after']) {
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

        const isContainer = !isChart && !data.text && !data.paragraphs && !isImg && !isSvg && !hasVisibleBg && !hasBorder &&
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
            const measured = measureElement(
                child,
                slide,
                slideRect,
                0,
                slideIndex + 1,
            );
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


def _localized_elements(elements: list[dict]) -> list[dict]:
    """Return localized roots without entering their excluded descendants."""
    return [
        element
        for element in _walk_elements(elements)
        if element.get("localizedFallback") and element.get("localizedId")
    ]


_LOCALIZED_COMPUTED_URL_RE = re.compile(
    r"url\(\s*(?:\"(?P<double>.*?)\"|'(?P<single>.*?)'|(?P<bare>[^)]*))\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_ISOLATION_STRUCTURAL_KEYS = (
    "target_id_match",
    "authored_top_level_target",
    "no_authored_siblings",
    "no_master_layout_background",
    "transparent_cleared_container",
)


def _empty_isolation_evidence() -> dict[str, object]:
    return {
        "capture_document": "fresh-page-single-region",
        "target_id_match": False,
        "authored_top_level_target_count": 0,
        "authored_top_level_target": False,
        "authored_sibling_count": 0,
        "no_authored_siblings": False,
        "master_layout_background_count": 0,
        "no_master_layout_background": False,
        "transparent_cleared_container": False,
        "outside_paint_pixels": None,
        "outside_pixel_count": None,
        "outside_paint_fraction": None,
        "pixel_outside_wrapper_zero": False,
        "passed": False,
    }


def _isolation_contamination_fraction(evidence: dict[str, object]) -> float:
    """Turn failed capture-document facts into a derived contamination signal."""
    failed = sum(
        1 for key in _ISOLATION_STRUCTURAL_KEYS if evidence.get(key) is not True
    )
    return failed / len(_ISOLATION_STRUCTURAL_KEYS)


def _capture_resource_allowed(value: str, source_base_url: str | None) -> bool:
    value = str(value or "").strip().strip("\"'")
    if not value:
        return True
    if value.lower().startswith("data:image/"):
        return True
    parsed = urlparse(value)
    if parsed.scheme.lower() != "file":
        return False
    if not source_base_url:
        return False

    def file_url_path(url: str) -> Path:
        parsed_url = urlparse(url)
        raw_path = unquote(parsed_url.path)
        if os.name == "nt":
            # ``file:///C:/...`` parses as ``/C:/...``.  Keeping that leading
            # slash makes pathlib treat the drive as a relative path, which
            # would reject a local asset that the source Contract permits.
            if parsed_url.netloc and parsed_url.netloc.lower() != "localhost":
                return Path("\\\\" + parsed_url.netloc + raw_path.replace("/", "\\"))
            return Path(raw_path.lstrip("/"))
        return Path(raw_path)

    try:
        root = file_url_path(source_base_url).resolve()
        candidate = file_url_path(value).resolve()
        return candidate.is_file() and candidate.is_relative_to(root)
    except (OSError, ValueError):
        return False


def _localized_computed_policy_failures(
    computed: object,
    *,
    source_base_url: str | None,
) -> list[str]:
    """Apply only Chromium-resolved safety facts; no selector matching here."""
    if not isinstance(computed, dict):
        return []
    failures: list[str] = []
    if computed.get("animationNodes"):
        failures.append("localized_animation")
    if computed.get("transitionNodes"):
        failures.append("localized_animation")
    for item in computed.get("resourceStates") or ():
        if not isinstance(item, dict):
            continue
        values = _LOCALIZED_COMPUTED_URL_RE.findall(str(item.get("value") or ""))
        urls = [next((part for part in match if part), "") for match in values]
        if any(not _capture_resource_allowed(url, source_base_url) for url in urls):
            failures.append("localized_external_resource")
    for item in computed.get("imageStates") or ():
        if not isinstance(item, dict):
            continue
        source = str(item.get("currentSrc") or "")
        if source and not _capture_resource_allowed(source, source_base_url):
            failures.append("localized_external_resource")
        if source and (
            item.get("complete") is not True
            or float(item.get("naturalWidth") or 0) <= 0
            or float(item.get("naturalHeight") or 0) <= 0
        ):
            failures.append("localized_external_resource")
    return list(dict.fromkeys(failures))


def _inspect_isolated_frame(
    frame_png: bytes | None,
    capture_payload: dict[str, object],
    device_scale: float,
) -> dict[str, object]:
    """Measure alpha paint outside the target border box in the fresh page."""
    evidence: dict[str, object] = {
        "outside_paint_pixels": None,
        "outside_pixel_count": None,
        "outside_paint_fraction": None,
        "pixel_outside_wrapper_zero": False,
    }
    if not frame_png:
        return evidence
    try:
        with Image.open(BytesIO(frame_png)) as frame:
            frame.load()
            frame_width, frame_height = frame.size
            alpha = frame.convert("RGBA").getchannel("A")
            left = max(
                0,
                min(
                    frame_width,
                    math.floor(float(capture_payload.get("x") or 0.0) * device_scale),
                ),
            )
            top = max(
                0,
                min(
                    frame_height,
                    math.floor(float(capture_payload.get("y") or 0.0) * device_scale),
                ),
            )
            right = max(
                left,
                min(
                    frame_width,
                    math.ceil(
                        (
                            float(capture_payload.get("x") or 0.0)
                            + float(capture_payload.get("width") or 0.0)
                        )
                        * device_scale
                    ),
                ),
            )
            bottom = max(
                top,
                min(
                    frame_height,
                    math.ceil(
                        (
                            float(capture_payload.get("y") or 0.0)
                            + float(capture_payload.get("height") or 0.0)
                        )
                        * device_scale
                    ),
                ),
            )

            def painted_outside(box: tuple[int, int, int, int]) -> int:
                histogram = alpha.crop(box).histogram()
                return sum(histogram[1:])

            outside = 0
            if top:
                outside += painted_outside((0, 0, frame_width, top))
            if bottom < frame_height:
                outside += painted_outside((0, bottom, frame_width, frame_height))
            if left:
                outside += painted_outside((0, top, left, bottom))
            if right < frame_width:
                outside += painted_outside((right, top, frame_width, bottom))
            wrapper_pixels = max(0, right - left) * max(0, bottom - top)
            outside_pixels = max(0, frame_width * frame_height - wrapper_pixels)
            evidence.update(
                {
                    "outside_paint_pixels": outside,
                    "outside_pixel_count": outside_pixels,
                    "outside_paint_fraction": (
                        outside / outside_pixels if outside_pixels else 0.0
                    ),
                    "pixel_outside_wrapper_zero": outside == 0,
                }
            )
    except Exception:
        logger.debug("Failed to inspect localized capture frame")
    return evidence


async def _rasterize_localized_fallbacks(
    browser,
    page,
    measurements: list[dict],
    *,
    source_base_url: str | None = None,
) -> None:
    """Capture each opted-in region in a page containing only that region."""
    for slide_index, slide_data in enumerate(measurements):
        localized = _localized_elements(slide_data.get("elements", []))
        if not localized:
            continue

        payload = await page.evaluate(
            """(index) => {
                const slides = Array.from(document.querySelectorAll('.slide'));
                const slide = slides[index];
                if (!slide) return null;
                const rect = slide.getBoundingClientRect();
                return {
                    width: rect.width,
                    height: rect.height,
                    styles: Array.from(document.querySelectorAll('style'))
                        .map(style => style.textContent || ''),
                };
            }""",
            slide_index,
        )
        if not payload:
            continue

        slide_width = float(payload.get("width") or 0)
        slide_height = float(payload.get("height") or 0)
        if slide_width <= 0 or slide_height <= 0:
            continue
        # Author canvases normalize to 960pt x 540pt. Choose the browser
        # device scale that produces exactly 2 pixels per point for both
        # accepted 1920px and legacy 960px canvases.
        css_pixels_per_point = slide_width / 960.0
        device_scale = 2.0 / css_pixels_per_point

        # Geometry and overlap are checked from the same measured border boxes
        # that drive the eventual PowerPoint picture bounds.  This is before
        # any browser capture, so a whole-slide, cross-slide, or overlapping
        # region cannot produce a misleading asset first.
        slide_bounds_pt = (0.0, 0.0, 960.0, slide_height / css_pixels_per_point)
        capture_facts: dict[str, dict[str, object]] = {}
        regions: list[LocalizedRegion] = []
        for element in localized:
            localized_id = str(element.get("localizedId") or "")
            fallback = element.setdefault("localizedFallback", {})
            source_object = str(
                fallback.get("sourcePath")
                or fallback.get("sourceIdentity")
                or localized_id
                or "localized"
            )
            fallback["sourcePath"] = source_object
            bounds_pt = (
                float(element.get("x") or 0.0) / css_pixels_per_point,
                float(element.get("y") or 0.0) / css_pixels_per_point,
                float(element.get("width") or 0.0) / css_pixels_per_point,
                float(element.get("height") or 0.0) / css_pixels_per_point,
            )
            geometry_findings = validate_localized_geometry(
                source_object,
                bounds_pt,
                slide_bounds_pt,
            )
            computed_failures = _localized_computed_policy_failures(
                fallback.get("computedSafety"),
                source_base_url=source_base_url,
            )
            fallback["computedSafetyFailureCodes"] = computed_failures
            capture_facts[localized_id] = {
                "source_object": source_object,
                "bounds_pt": bounds_pt,
                "preflight_codes": [finding.code for finding in geometry_findings]
                + computed_failures,
            }
            regions.append(
                LocalizedRegion(
                    source_object=source_object,
                    slide=slide_index + 1,
                    bounds_pt=bounds_pt,
                )
            )
        for finding in validate_localized_region_overlap(regions):
            for fact in capture_facts.values():
                if fact.get("source_object") == finding.source_object:
                    codes = fact.setdefault("preflight_codes", [])
                    if finding.code not in codes:
                        codes.append(finding.code)

        base_tag = (
            f'<base href="{_html_escape(source_base_url, quote=True)}">'
            if source_base_url
            else ""
        )

        for element in localized:
            localized_id = str(element.get("localizedId"))
            fallback = element.setdefault("localizedFallback", {})
            facts = capture_facts.get(localized_id, {})
            source_object = str(facts.get("source_object") or localized_id)
            bounds_pt = tuple(facts.get("bounds_pt") or (0.0, 0.0, 0.0, 0.0))
            preflight_codes = list(facts.get("preflight_codes") or [])
            capture_payload = await page.evaluate(
                """(value) => {
                    const node = document.querySelector(
                        '[data-pptx-localized-id="' + value + '"]'
                    );
                    if (!node) return null;
                    const slide = node.closest('.slide');
                    if (!slide) return null;
                    const rect = node.getBoundingClientRect();
                    const slideRect = slide.getBoundingClientRect();
                    return {
                        outerHTML: node.outerHTML,
                        x: rect.left - slideRect.left,
                        y: rect.top - slideRect.top,
                        width: rect.width,
                        height: rect.height,
                    };
                }""",
                localized_id,
            )
            if not capture_payload:
                isolation_evidence = _empty_isolation_evidence()
                audit = audit_localized_capture(
                    None,
                    bounds_pt=bounds_pt,
                    source_object=source_object,
                    contamination_fraction=_isolation_contamination_fraction(
                        isolation_evidence
                    ),
                    isolated=False,
                    excluded_descendants=int(
                        fallback.get("excludedDescendantCount") or 0
                    ),
                    isolation_evidence=isolation_evidence,
                )
                fallback.update(
                    {
                        "isolationEvidence": isolation_evidence,
                        "captureAudit": audit.as_dict(),
                        "captureFailureCodes": [
                            *preflight_codes,
                            *audit.failure_codes,
                        ],
                    }
                )
                continue

            outer_html = str(capture_payload.get("outerHTML") or "")
            # A script would execute if copied into the capture page. Keep the
            # capture inert; the Contract/failure seam reports the missing asset.
            capture_allowed = "<script" not in outer_html.lower()
            styles = "\n".join(str(value) for value in payload.get("styles", []))
            markup = f"""<!doctype html>
<html><head><meta charset="utf-8">{base_tag}<style>{styles}</style></head>
<body style="margin:0;overflow:hidden;background:transparent !important">
<section class="slide active" style="display:block !important;position:relative;width:{slide_width}px;height:{slide_height}px;background:transparent !important;background-image:none !important;border:0 !important;"
         data-pptx-localized-capture="true">
  {outer_html}
</section>
</body></html>"""

            context = await browser.new_context(
                viewport={
                    "width": max(1, round(slide_width)),
                    "height": max(1, round(slide_height)),
                },
                device_scale_factor=device_scale,
            )
            png_bytes: bytes | None = None
            frame_png: bytes | None = None
            isolation_evidence = _empty_isolation_evidence()
            try:
                if capture_allowed and not preflight_codes:
                    capture_page = await context.new_page()
                    await capture_page.set_content(markup, wait_until="load")
                    await capture_page.wait_for_function(
                        """() => Array.from(document.images).every(image =>
                            image.complete && image.naturalWidth > 0)""",
                        timeout=PLAYWRIGHT_TIMEOUT_MS,
                    )
                    document_facts = await capture_page.evaluate(
                        """(value) => {
                            const container = document.querySelector(
                                '[data-pptx-localized-capture="true"]'
                            );
                            if (!container) return null;
                            const matches = Array.from(
                                container.querySelectorAll('[data-pptx-localized-id]')
                            ).filter(
                                node => node.getAttribute('data-pptx-localized-id') === value
                            );
                            const target = matches.length === 1 ? matches[0] : null;
                            const topLevel = Array.from(container.children);
                            const siblings = topLevel.filter(node => node !== target);
                            const outsideScaffold = Array.from(document.body.children)
                                .filter(node => node !== container);
                            const forbidden = Array.from(document.querySelectorAll(
                                '[data-pptx-master], [data-pptx-layout], [data-pptx-background], .master, .layout, .master-slide, .layout-slide, .slide-background, .master-background, .layout-background'
                            )).filter(
                                node => !target || (node !== target && !target.contains(node))
                            );
                            const transparent = node => {
                                const style = getComputedStyle(node);
                                const color = String(style.backgroundColor || '').toLowerCase();
                                return (
                                    (color === 'transparent' || /,\\s*0\\)?$/.test(color))
                                    && style.backgroundImage === 'none'
                                );
                            };
                            return {
                                target_id_match: matches.length === 1
                                    && target !== null
                                    && target.parentElement === container,
                                authored_top_level_target_count: topLevel.filter(
                                    node => node === target
                                ).length,
                                authored_top_level_target: topLevel.length === 1
                                    && target !== null
                                    && target.parentElement === container,
                                authored_sibling_count: siblings.length + outsideScaffold.length,
                                no_authored_siblings: siblings.length === 0
                                    && outsideScaffold.length === 0,
                                master_layout_background_count: forbidden.length,
                                no_master_layout_background: forbidden.length === 0,
                                transparent_cleared_container: transparent(container)
                                    && transparent(document.body)
                                    && transparent(document.documentElement),
                            };
                        }""",
                        localized_id,
                    )
                    if isinstance(document_facts, dict):
                        isolation_evidence.update(document_facts)
                    target = capture_page.locator(
                        f'[data-pptx-localized-id="{localized_id}"]'
                    ).first
                    png_bytes = await target.screenshot(
                        type="png",
                        animations="disabled",
                        omit_background=True,
                    )
                    # This is still a fresh page containing only the target,
                    # not a crop of the source slide.  The frame is used solely
                    # to prove that visual paint did not escape the authored
                    # CSS border box.
                    frame_png = await capture_page.screenshot(
                        type="png",
                        animations="disabled",
                        omit_background=True,
                    )
            except Exception:
                logger.debug(
                    "Failed to rasterize localized fallback %s",
                    localized_id,
                    exc_info=True,
                )
            finally:
                await context.close()

            pixel_evidence = _inspect_isolated_frame(
                frame_png,
                capture_payload,
                device_scale,
            )
            isolation_evidence.update(pixel_evidence)
            isolation_evidence["passed"] = bool(
                all(
                    isolation_evidence.get(key) is True
                    for key in _ISOLATION_STRUCTURAL_KEYS
                )
                and isolation_evidence.get("pixel_outside_wrapper_zero") is True
            )
            overflow = bool(
                isolation_evidence.get("outside_paint_pixels") is not None
                and isolation_evidence.get("pixel_outside_wrapper_zero") is False
            )
            contamination_fraction = _isolation_contamination_fraction(
                isolation_evidence
            )
            isolated = isolation_evidence["passed"] is True

            audit = audit_localized_capture(
                png_bytes,
                bounds_pt=bounds_pt,
                source_object=source_object,
                contamination_fraction=contamination_fraction,
                overflow=overflow,
                isolated=isolated,
                excluded_descendants=int(
                    fallback.get("excludedDescendantCount") or 0
                ),
                isolation_evidence=isolation_evidence,
            )
            failure_codes = [*preflight_codes, *audit.failure_codes]
            fallback.update(
                {
                    "isolationEvidence": isolation_evidence,
                    "captureAudit": audit.as_dict(),
                    "captureFailureCodes": list(dict.fromkeys(failure_codes)),
                    "effectivelyTransparent": audit.effectively_transparent,
                    "paintFraction": audit.paint_fraction,
                    "overflow": audit.overflow,
                    "contaminationFraction": audit.contamination_fraction,
                }
            )
            if failure_codes:
                continue

            pixel_width = audit.pixel_width
            pixel_height = audit.pixel_height
            encoded = base64.b64encode(png_bytes).decode("ascii")
            element["src"] = "data:image/png;base64," + encoded
            element["isImage"] = True
            element["objectFit"] = "fill"
            element["naturalWidth"] = pixel_width
            element["naturalHeight"] = pixel_height
            element["localizedFallback"].update(
                {
                    "assetMime": "image/png",
                    "assetSha256": hashlib.sha256(png_bytes).hexdigest(),
                    "pixelWidth": pixel_width,
                    "pixelHeight": pixel_height,
                    "density": 2.0,
                    "nonblank": audit.nonblank,
                    "densityVerified": True,
                    "isolated": audit.isolated,
                    "isolation": str(
                        isolation_evidence.get("capture_document")
                        or "fresh-page-single-region"
                    ),
                    "optInReason": "explicit-author-opt-in",
                }
            )


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
        ValueError: If the file contains no slides.
        ImportError: If Playwright is not installed.
    """
    from playwright.async_api import async_playwright

    abs_path = os.path.abspath(html_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"HTML file not found: {abs_path}")

    logger.info(
        "Loading %s (%.1f MB)",
        abs_path,
        os.path.getsize(abs_path) / (1024 * 1024),
    )

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

        await _rasterize_localized_fallbacks(
            browser,
            page,
            measurements,
            source_base_url=Path(abs_path).parent.as_uri() + "/",
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
