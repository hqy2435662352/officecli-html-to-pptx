# Gate 3 — independent primary-agent visual review (V0.4.2 acceptance)

Status: **NOT COMPLETE — re-acceptance required.**
Reviewer: primary agent. Evidence bundle reviewed: `acceptance/v0.4.2/` as published
at commit `d5fc98d` (rebuilt deck `gate/rebuilt.pptx`, renders under `visual/`).

The machine gate returned `PASS_WITH_FINDINGS` with 0 material deltas. Gate 3 does
**not** agree. This file records what the independent visual review found and what
must happen before the V0.4.2 acceptance can be claimed.

## Method

Each of the ten pages was inspected as a before/after pair at the same
1280x720 render size, produced by the same OfficeCLI screenshot pipeline. A page
was failed when content present in the source page is absent, duplicated, or
misplaced in the rebuilt page. Visual review is an independent gate by the spec's
own decision; it is not a pixel-similarity threshold.

## Findings

### Major — page 1 (source page 2): three arrows lost their outline

`rightArrow` objects `/slide[2]/shape[@id=15]`, `[@id=16]`, `[@id=17]` carry
`line=#C00000` and no explicit `lineWidth`. The projector required
`line_width_pt > 0` before emitting a border, so it emitted no stroke at all; the
rebuilt deck read back `fill=none line=none`. All three arrows were invisible.

**Root cause fixed** in `author_projector._stroke_width_pt` +
`DEFAULT_LINE_WIDTH_PT`: a declared colour with no declared width now strokes at
PowerPoint's default 1pt. Re-verified: the rebuilt arrows read back
`line=#C00000 lineWidth=1pt`, and the re-rendered page shows all three.

### Major — pages 1, 3 and others: text proxies rendered a property value instead of the text

`IsolatedRenderer._rebuild_properties` reused the name `text` for a loop variable
holding a property value, so the object's own captured text was overwritten by
whichever property was read last. The page-1 subtitle proxy
(`/slide[2]/shape[@id=8]`) rendered the literal word **`rect`**; the page-3 title
proxy (`/slide[7]/shape[@id=2]`) rendered **`none`**. The caption text the proxy
exists to preserve was replaced by a placeholder, and the page-3 title was lost.

**Root cause fixed** in `pptx_reader._rebuild_properties` (renamed to
`value_text`, with a comment naming the failure) and the same shadowing removed
from `_member_properties`. Re-verified on both pages: the proxies now carry the
real words.

### Major — page 3 (source page 7): wrapped title replaced a no-wrap title

The title is authored with `wrap=False`, so the source paints one line that is
allowed to overflow its own box. The reconstruction used OfficeCLI's default
wrapping, re-broke the line, and the cropped proxy showed a clipped fragment.

**Root cause fixed**: `wrap` is now among `_TEXT_PROPERTIES`, so the
reconstruction keeps the object's own wrap setting. Re-verified: the proxy paints
the full title on one line.

### Major — page 4 (source page 12): number badges overlap the card titles

The rebuilt page paints the red number badges (`1`, `2`, `4`) on top of the card
headings, so "Key Meeting Takeaways" renders as "1ey Meeting Takeaways" and the
badge covers the first character. The source page places each badge clear of its
heading. This is a layout/z-order corruption of the kind criterion 16 names.

**Not yet fixed.**

### Not yet reviewed

Pages 5–10 were not reached in this pass; the review stopped once the page-1
defect showed the earlier machine-only evidence could not be trusted for these
pages. They remain **unreviewed**, not passed.

## Consequence

The published `acceptance-report.md` is **superseded**. Its `PASS_WITH_FINDINGS`
verdict and its "zero major projection defects" criterion are not supported: the
bundle it describes was produced by code with the three root causes above, and at
least one page-level defect (page 4) is still open.

The evidence bundle must be regenerated from the fixed code, the corpus re-gated,
and this review completed page by page before the acceptance outcome is restated.

## What this says about the machine gate

The delta gate and its adversarial verification both passed this corpus while
three content-destroying defects were live. The gate checks that objects exist,
that mapped text matches, that tables keep their shape and that proxies are
isolated — none of which notices a proxy that paints the wrong words or an
outline that strokes at zero width. The spec already treats visual review as a
mandatory independent gate for exactly this reason; this review is the evidence
that it is load-bearing rather than ceremonial.
