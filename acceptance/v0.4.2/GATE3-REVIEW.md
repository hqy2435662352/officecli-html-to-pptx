# Gate 3 — independent visual acceptance review (v0.4.2 projection, 10 selected pages)

> **Publisher's note, added when the bundle was republished.** This document
> judged an **earlier revision** of the branch and is **historical**: its
> verdict and every count in it describe that revision's own run, whose page
> composition differed from the current one. It is kept because the history is
> part of the record -- this is the review that blocked, and later reviews exist
> because of it -- but it is not a statement about the current revision. The
> bundle's verdict is the latest review, `GATE3-REVIEW-4.md`.

**Verdict: BLOCK** — five of the ten rebuilt pages differ from their source pages in ways a reader
would see (missing text, a destroyed fill, missing table separators, lost accent colour, white
boxes over a coloured panel, a wrong list number) and two more differ in metrics, while the machine
gate reports all ten pages as `rebuilt_issue_count = 0`, `material_deltas = []`,
`proxy_proofs_failed = 0`, `accepted = true`.

## How this was done

I read all twenty renders (`p01`…`p10`, before and after) myself, then checked every difference I
thought I saw numerically: whole-page and per-band pixel differences, region crops at 2×–6× zoom,
row/column scans for lines and fills, bounding boxes for shapes and text lines, and colour-core
counts for text. I then read each page's slice of the Canonical Author HTML, the page's
`pages[]` record in the gate report, and the ledger entries for that `(source_key, source_page)`,
and decoded the proxy rasters out of the HTML and out of the rebuilt deck's media to separate
"the proxy is wrong" from "the render of the proxy is wrong".

Everything below is located by `(source slot, source page, source object path)` plus the rebuilt
page order. Where I could not see a difference I say so; where a detail is below the resolution of
a 1280×720 render I say that instead of guessing.

Per-page disposition mix (from the ledger, entries for that source page):

| rebuilt page | source | canonical-editable | locked-visual-proxy | base-only-semantic | entries |
|---|---|---|---|---|---|
| p01 | src1 p2 | 33 | 6 | 2 | 41 |
| p02 | src1 p5 | 10 | 0 | 1 | 11 |
| p03 | src1 p12 | 42 | 3 | 0 | 45 |
| p04 | src1 p30 | 32 | 10 | 15 | 57 |
| p05 | src2 p3 | 18 | 0 | 0 | 18 |
| p06 | src2 p9 | 22 | 6 | 0 | 28 |
| p07 | src3 p2 | 26 | 0 | 0 | 26 |
| p08 | src3 p21 | 12 | 0 | 0 | 12 |
| p09 | src4 p1 | 7 | 0 | 0 | 7 |
| p10 | src5 p1 | 8 | 3 | 1 | 12 |

No page has an `unsupported` or `unresolved` entry, and no page is blocked in the gate.

---

## p01 — src1, page 2 (rebuilt page 1)

Disposition mix: 33 canonical-editable / 6 locked-visual-proxy / 2 base-only-semantic (41).
Ledger reconciliation: the six proxy entries are two groups (`/slide[2]/group[@id=88]`,
`/slide[2]/group[@id=40]`) plus their four container-owned connectors (`emitted_name = None`), so
only two proxy rasters are actually emitted for them — the page record's four `proxy_objects` are
those two plus the two base-only-semantic pictures. I could reconcile every entry.

Differences I can see:

1. **The left-hand block "In 2017" / "1.39" / "Billion USD" is gone.** (src1, 2,
   `/slide[2]/shape[@id=61]`, `/slide[2]/shape[@id=71]`, `/slide[2]/shape[@id=80]`) — *MAJOR*.
   All three are emitted `canonical-editable` with `color: #FFFFFF` (confirmed in the rebuilt
   slide XML: `slide-001-textbox-018`, `-005`, `-006` all carry `FFFFFF`), i.e. white text on the
   white page. Ink-pixel counts in their own boxes: source 372 / 1527 / 476, rebuilt **0 / 0 / 0**.
2. **Both "1 year" connector arrows are reduced to a short diagonal stroke.** (src1, 2,
   `/slide[2]/group[@id=88]`, `/slide[2]/group[@id=40]`) — *MAJOR*. The source draws a horizontal
   shaft from x≈453 to x≈535 at y≈228 with an open arrowhead; the rebuilt page has no horizontal
   line at all on either connector (longest dark run at that row: source 78 px at x=453, rebuilt
   4 px). The proxy raster (121×19) contains the shaft only in its last row, so it is effectively a
   near-empty proxy that still passed the gate's `carries_paint` / `target_survived` checks.
3. **The two-line subtitle loses the red and the bold on its second line.** (src1, 2,
   `/slide[2]/shape[@id=8]`, `base-only-semantic`, reason `text_base_only`) — *MAJOR*. The source
   paints "From Algeria To Whole World" in bold red; the rebuilt page paints it regular black. I
   decoded the proxy raster itself: it is black/regular, so the picture is visually wrong, not the
   render.
4. The ">" chevron picture overlaps the "9.50" glyphs. (src1, 2, `/slide[2]/picture[@id=48]`
   against `/slide[2]/shape[@id=46]`) — *MINOR*. The ">" glyph image sits at x 290.6–317.8 while
   the "9.50" text box starts at x 307.8; the source has a clear gap. The line also sits 5 px
   higher and ends 10 px further left than the source.

Not a defect: the title, the circles, "Growth Rate > 100% / > 30%", "Million/USD", the red
outline arrows and the Year/2026/2027/2028 column match within 1–2 px (that residual is
sub-pixel text rasterisation). The source's page number "2" is absent from the rebuild — inherited
paint, out of scope for this projection, and not duplicated anywhere.

Risk checklist: wrap-off title intact and not re-wrapped; no two-line text collapsed; bullets/none
here; the arrowhead risk is the opposite of "missing outline" — the whole arrowhead plus shaft is
missing (finding 2); a proxy paints text where the source paints none (finding 1).

## p02 — src1, page 5 (rebuilt page 2)

Disposition mix: 10 canonical-editable / 0 proxy / 1 base-only-semantic (11). Reconciled: 10
editable objects (title, rule, X-PRO card, its label block, product photo, table, band, 3 panel
groups) plus the proxy for the band's text.

Differences I can see:

1. **The pink callout band is painted over by an opaque white rectangle.** (src1, 5,
   `/slide[5]/shape[@id=100085]` — `base-only-semantic`, reason `text_paragraph_layout_base_only`
   — composited over the band `/slide[5]/shape[@id=100084]`, fill `#FFF1F1`) — *MAJOR*. The proxy
   raster (192×309) has a white background, and in the rebuilt deck the picture is emitted after
   the band, so the band survives only as a pink sliver on the left/bottom. Pink fill pixels in the
   band's own box: source 23 936, rebuilt 8 570. This is the object the bundle's own note calls
   "the page stays faithful" — it is not faithful: a reader sees a white box with red text where
   the source has a solid pink band.
2. The band's text is drawn ~10 px further right than the source. (src1, 5,
   `/slide[5]/shape[@id=100085]`) — *MINOR*. Line left edges: source x=60/61/61/61/60, rebuilt
   x=70/71/72/72/71; line heights and the five line breaks match exactly.

**The "Condor needs" risk, decided:** what I can see around that phrase is a horizontal offset of
the whole five-line block (~10 px), not a wrap or a metric-driven re-flow — no character is lost,
no line is added or merged, and the word "Condor" is complete. I judge it a **minor retained
finding**, not a product defect worth blocking on and not a MAJOR. The defect on this page worth
fixing is finding 1 (the proxy's opaque background), which is what actually changes the page.

Also not a defect: the inherited header band and the page number "5" are absent (out of scope, not
duplicated); the table, the three panels, the flag/icon images and the X-PRO photo match.

## p03 — src1, page 12 (rebuilt page 3)

Disposition mix: 42 canonical-editable / 3 locked-visual-proxy (45). Reconciled: the three proxies
are the gradient header bands (`/slide[12]/shape[@id=100068]`, `[@id=100071]`, `[@id=100077]`,
reason `fill_not_solid`); they render as the source's pale grey gradient in both, so they are
visually faithful.

Difference I can see:

1. **The right-hand specification table's rows are ~20 % shorter.** (src1, 12,
   `/slide[12]/table[@id=100088]`) — *MINOR*. Source: header band y 160–196 and row borders at
   233 / 271 / 308 (≈38 px rows); rebuilt: header 160–188 and borders at 219 / 249 / 279 (≈30 px
   rows). All four rows, all cell text and the red header fill are correct; the table is simply
   29 px shorter, leaving a larger gap above the "Priority recommendation" band (which sits at
   y 320–355 in both).

No other difference: the numbered takeaways (1./2./3.), their two-line breaks, the separator
rules, the "Option 1 / Option 2" boxes, their bullets and the "Next discussion needed" band match
to within 1 px (I checked the separators and every text band numerically after an initial
impression of a shift turned out to be a mistake of mine, not of the rebuild). The inherited
header band and page number are absent (out of scope).

## p04 — src1, page 30 (rebuilt page 4)

Disposition mix: 32 canonical-editable / 10 locked-visual-proxy / 15 base-only-semantic (57).
Reconciled: the 10 proxies are 3 brand-header cells + 4 vertical connectors + 3 horizontal
connectors; the 15 base-only-semantic objects are the cell text blocks (`text_base_only`); the 32
editable objects are the band, titles, table labels, rules and product photos. Every visible
object is accounted for.

Differences I can see:

1. **The three horizontal dashed row separators are missing.** (src1, 30,
   `/slide[30]/connector[@id=52]`, `[@id=53]`, `[@id=54]`, `locked-visual-proxy`) — *MAJOR*. The
   source draws a dashed red line at y=302, y=460 and y=614 across the grid; the rebuilt page has
   no red pixels in those rows at all (accent-pixel count per line: source 719 / 744 / 701,
   rebuilt 12 / 16 / 16). The proxy rasters do contain the dashes, but only in their top row, so
   as placed they contribute nothing. Effect: the grid loses its row structure.
2. **The four vertical separators are solid where the source is dashed.** (src1, 30,
   `/slide[30]/connector[@id=10]`, `[@id=11]`, `[@id=15]`, `[@id=45]`) — *MAJOR*. Source red
   pixels per column over the grid height ≈245–250 (≈52 % coverage, clear dashes); rebuilt ≈430–440
   (≈91 %, effectively a continuous line).
3. **Accent-coloured, bold lines inside six cell text blocks are rebuilt plain black.** (src1, 30,
   `/slide[30]/shape[@id=48]` and `[@id=55]` — the right-hand column; `[@id=100132]` and
   `[@id=100125]` — the HAIER column; `[@id=22]` — the MIDEA column; `[@id=41]` — the FRESH column;
   all `base-only-semantic`, reason `text_base_only`) — *MAJOR*. In the source the feature lines are
   red or orange and bold: "AI Voice Control (Optional) … 5 Easy Upgrade" (shape 48), "GEN- Mode
   with Blue tooth / Super Tropical T3" (shape 55), "High Air Circulation /IFD Air Purification"
   (shape 100132), "Haismart/UVC Feature/ECO" (shape 100125), "AI Comfort Saving; …" (shape 22) and
   "Plasma air purification" (shape 41). In the rebuilt page all six are black and regular.
   Measured on the HAIER HIGH cell: the source's accent lines have 303 orange-core pixels and zero
   black-core pixels, the rebuilt page 12 and 93. I decoded the proxy rasters themselves: they are
   black, so the object-local picture is visually wrong. The other nine `base-only-semantic` blocks
   on this page (shape `[@id=9]`, `[@id=24]`, `[@id=28]`, `[@id=38]`, `[@id=42]`, `[@id=100024]`,
   `[@id=39]`, `[@id=40]`, `[@id=50]`) carry no accent colour in the source and are otherwise
   faithful — the only exception is shape `[@id=28]`, which drops a hyphen (difference 6 below).
4. **The three brand-header cells lose their peach fill.** (src1, 30,
   `/slide[30]/shape[@id=100111]`, `[@id=100112]`, `[@id=100113]`, `locked-visual-proxy`,
   reason `fill_not_solid`) — *MAJOR*. Source cell fill `(252,230,213)` on HAIER / CARRIER /
   MIDEA; rebuilt `(255,255,255)`. The proxy rasters carry the cell's light-grey border and its
   text but not the fill, so the brand header row loses its tint (the red FRESH and LINE headers
   are correct in both).
5. Text the source clipped at a column edge is painted in full. (src1, 30, `/slide[30]/shape[@id=22]`
   — "AI Comfort Savin[g;] / Smart Home Con[trol]" — and `[@id=41]` — "Plasma air puri[fication]")
   — *MINOR*. The source's overflow is covered by the neighbouring column's white-filled boxes;
   the rebuild has no such cover, so the complete words and their punctuation appear. Nothing looks
   broken in the rebuilt page; it simply is not what the source shows.
6. A hyphen is dropped in one cell. (src1, 30, `/slide[30]/shape[@id=28]`, "Cooling-only" →
   "Cooling only") — *MINOR*. Same character count elsewhere in the cell, and the phrase still
   reads; I did not find another dropped character on this page.

Not a defect: the titles, the "SPLIT-SYSTEM PLATFORM LINE-UP" band, the LINE / FRESH / TCL-with-
FRESH cells, the row labels (HIGH/MID/ENTRY SPLIT), the product photos and the TCL logo match.

## p05 — src2, page 3 (rebuilt page 5)

Disposition mix: 18 canonical-editable, no proxies (18). Reconciled exactly: title, subtitle, grey
rule, three cards (panel + name + sub-label + photo), three tables, = 18.

I could not see a difference on this page. The three tables (rows, borders, header fills, red
column heads), the card labels, the product photos and the title block all match; the only missing
paint is the inherited "PRODUCT LINE-UP" eyebrow and the brand marks in the top band, which are
layout/master paint and out of scope, and which are not duplicated anywhere.

## p06 — src2, page 9 (rebuilt page 6)

Disposition mix: 22 canonical-editable / 6 locked-visual-proxy (28). Reconciled: the six proxy
entries are the two product-photo groups (`/slide[9]/group[@id=100381]`,
`/slide[9]/group[@id=100383]`) plus their four container-owned children.

Differences I can see:

1. **Both product photos now sit on visible white rectangles.** (src2, 9,
   `/slide[9]/group[@id=100381]`, `/slide[9]/group[@id=100383]`) — *MAJOR*. The source photos blend
   into the lavender panel `(243,244,245)`; the rebuilt page paints an opaque white raster box
   under each unit. Panel sample points around and below the units: source `(243,244,245)`
   everywhere, rebuilt `(255,255,255)` below and left of each unit. Same defect class as finding
   p02-1: the object-local proxy is rasterised on white and then composited over coloured paint.
2. The "IDU/ODU Dimension (W×D×H mm)" cells no longer wrap. (src2, 9,
   `/slide[9]/table[@id=100362]`) — *MINOR*. Source: two lines ("…(W×D×H" / "mm)"), rebuild: one
   line. The table's row borders are identical in both
   (185 / 226 / 266 / 306 / 347 / 387 / 428 / 468 / 509), so no row height or alignment changed —
   this is a wrap difference inside the cell only, and the gate already keeps a
   `table_cell_whitespace_placement` retained finding for this table.

Not a defect: the title, the "SPECIFICATIONS" heading and its red underline (identical rows
159–161, x 555–589 in both), the WHITE/BLACK labels, the R32 / CON+EVA / RIGHT-SIDE-VIEW strip and
the table contents match. Inherited band and page number absent, out of scope.

## p07 — src3, page 2 (rebuilt page 7)

Disposition mix: 26 canonical-editable, no proxies (26). Reconciled exactly: the band and page
number are *slide-owned* on this deck (they are ledger entries here, unlike src1/src2), plus
title, subtitle, rule, footer and three cards with five objects each.

I could not see a difference. The three tables, the header row, the card panels, labels, "SOURCE
ROWS" captions, page number "02" and the masthead all match; the whole-page difference is
distributed sub-pixel text antialiasing (mean absolute difference ≈ 2.9/255 with no localised
blob), and the TPRO product image's ink bounding box is pixel-identical (8 852 ink pixels in both).

## p08 — src3, page 21 (rebuilt page 8)

Disposition mix: 12 canonical-editable, no proxies (12). Reconciled: band (3), title, subtitle,
rule, footer, page number, the three panel frames and the table.

Difference I can see:

1. **The two inner placeholder frames have much larger corner radii than the source.** (src3, 21,
   `/slide[21]/shape[@id=100385]`, `/slide[21]/shape[@id=100386]`, and the outer
   `/slide[21]/shape[@id=100384]`) — *MINOR, but systemic*. The canonical HTML declares
   `border-radius: 95px` on the 570×708 outer frame and `47.7px` on the 500×286 inner frames —
   exactly the PowerPoint `roundRect` **default** adjustment (1/6 of the short side) — where the
   source's corners are visibly tighter (≈20 px in the render, ≈30 px in slide units). Measured on
   the render: the source's inner frame reaches its straight left edge by y=225, the rebuild only
   by y≈250. Nothing is lost or misplaced; the frames just look noticeably rounder. Because the
   value looks like a default rather than a read-back, I would check whether other rounded shapes
   in the corpus are affected.

Not a defect: the title, the Chinese product-line cells (including their different wrap point),
the table's ten rows and the page number match. This page's masthead and page number are
slide-owned and present in both.

## p09 — src4, page 1 (synthetic probe A) (rebuilt page 9)

Disposition mix: 7 canonical-editable, no proxies (7). Reconciled exactly: red box, three text
lines, blue ellipse, orange right arrow, "Continue" label.

I could not see a difference. All three filled shapes have pixel-identical bounding boxes in source
and rebuild (red box x 133–479 / y 267–426; ellipse x 667–879 / y 267–386; arrow x 667–905 /
y 481–572), the arrow's shaft rows and colours are identical (`(238,130,47)`), and the arrowhead is
present. There is no outline on the arrow in either render, so no outline is missing. The only
differing pixels on the whole page (1 752 above threshold 40) are inside the three text lines and
are sub-pixel rasterisation. **The rightArrow probe passes.**

## p10 — src5, page 1 (synthetic probe B) (rebuilt page 10)

Disposition mix: 8 canonical-editable / 3 locked-visual-proxy / 1 base-only-semantic (12).
Reconciled: the proxies are the crimson rectangle + diagonal line group
(`/slide[1]/group[@id=100008]` plus two container-owned children) and the clipped-overflow text
block (`/slide[1]/shape[@id=100003]`, `base-only-semantic`, reason `text_base_only`).

Differences I can see:

1. **The nested numbered item is numbered "2." where the source shows "1."** (src5, 1,
   `/slide[1]/shape[@id=100001]`) — *MAJOR*. The canonical HTML flattens the four items into one
   `<ul>` with per-item `list-style-type` and indents the nested items with `margin-left` only, so
   the second-level number continues the first level's counter instead of restarting. The bullet
   items are correct (disc then circle) and the indentation is visually right; the ordinal is not.
2. **The hard-break probe's second line sits far lower than the source's.** (src5, 1,
   `/slide[1]/shape[@id=100000]`) — *MINOR*. Both lines survive (the break is not collapsed), but
   the leading goes from 17 px to ~43 px, so the two lines read as two paragraphs instead of one
   broken line.
3. **The clipped-overflow proxy's three lines are drawn ~20 px too high.** (src5, 1,
   `/slide[1]/shape[@id=100003]`, `base-only-semantic`) — *MINOR*. Source lines occupy y 163–182 /
   186–205 / 206–223, the proxy's occupy y 143–162 / 166–184 / 184–201. Same text, same three
   lines, same size; only the position inside the picture differs. Because the block moved up, the
   third line escapes the ellipse's cover, so "probe line" is legible where the source shows
   "probe lin".
4. **Every text block starts ~7–10 px further left than the source.** (src5, 1,
   `/slide[1]/shape[@id=100000]`, `[@id=100001]`, `[@id=100002]`, `[@id=100011]`) — *MINOR,
   systemic*. The rebuilt objects are emitted with `lIns = 0`, so the source's internal left inset
   is gone: title x 77→67, list x 87→80, "Theme resolved body 主题" x 77→68, "Ungrouped sibling
   text" x 78→68. The list block as a whole also sits 10 px lower (220/237/254/271 →
   230/247/264/281) and the title 4 px higher.

Not a defect: the crimson rectangle and the diagonal line (within 2 px), the blue rectangle, the
grey rounded rectangle, the orange bar and the theme-resolved body text's colour all match; the
mixed-run title (Latin + CJK + italic + fixed decimals) is complete and unwrapped.

---

## Risk checklist (explicit answers)

- **rightArrow outline / arrowhead** — p09 passes: the arrow is flat `(238,130,47)` in both, with
  no outline in either, and the arrowhead is present with an identical bounding box. p01 and p04
  are the opposite failure: an arrowhead reduced to one barb (p01) and dashed connectors that lose
  their dashes or their whole line (p04).
- **Text rendered as a picture (proxy)** — several proxies are visually wrong, not merely
  uneditable: p01 `/slide[2]/group[@id=88]`+`[@id=40]` (near-empty: shaft and arrowhead gone),
  p01 `/slide[2]/shape[@id=8]` (red+bold lost), p02 `/slide[5]/shape[@id=100085]` (white background
  over the pink band), p04's fifteen cell blocks (accent colour and bold lost) and its three header
  cells (peach fill lost), p06's two photo groups (white background over the lavender panel), p10
  `/slide[1]/shape[@id=100003]` (text 20 px high). No proxy I inspected is blank overall, and the
  only place a proxy paints text the source does not paint is p04's clipped-overflow cells.
- **wrap=False titles** — every text object in all ten slices is authored with `white-space: pre`.
  No title re-wrapped and no title lost characters at the end (checked on all ten pages, including
  the long p01, p04, p05 and p08 titles).
- **List markers, numbering, indentation, level** — p03's four numbered intro lines are present and
  unchanged; p10's four list items keep the correct bullet kinds and indentation but the nested
  numbered item is numbered "2." instead of "1." (finding p10-1). No duplicate markers anywhere.
- **Hard line breaks and paragraph boundaries** — nothing was collapsed into one line on any page.
  p10's two-line hard-break probe keeps both lines but with ~2.5× the leading (finding p10-2); p06's
  table cell loses an automatic wrap (finding p06-2); p04's clipped cell text gains the glyphs the
  source hid (finding p04-5).
- **Empty paragraphs** — p01 `/slide[2]/shape[@id=9]` is the object proxied for exactly this reason
  (`text_paragraph_layout_base_only`); its rendered picture is faithful ("Solar/LCAC/MultiSplit",
  correct size and position, and its white background hides nothing because the arrows are painted
  after it). p02 `/slide[5]/shape[@id=100085]` is the other one, and its picture is *not* faithful
  (finding p02-1). I saw no blank line missing or noticeably taller/shorter on the other pages.
- **p02 "Condor needs"** — a ~10 px horizontal offset of the block; minor retained finding, not a
  product defect on its own (see the p02 section).
- **Inherited bands and page numbers** — p01–p06 (src1/src2) are missing the inherited masthead and
  page number; that is declared out of scope, and no inherited paint is duplicated. p07 and p08
  (src3) carry the masthead and page number as slide-owned objects and both are present in the
  rebuild.

## Machine-claim cross-check

The gate's verdict document says `PASS_WITH_FINDINGS`, `accepted: true`,
`material_deltas: 0`, `rebuilt_issues: 3`, `proxy_proofs_failed: 0`, `blocking_diagnostics: 0`,
and **every** page record carries `rebuilt_issue_count = 0` and an empty `material_deltas` array.
I can see differences on six of those ten pages, so the gate's "no material delta" is not the same
claim as "the page looks like the source":

- **Text/style readback passed where the page is visibly wrong.** The clearest case is p01's
  `/slide[2]/shape[@id=61]`, `[@id=71]`, `[@id=80]`: the readback records `matched: true`,
  `style_matched: true`, `structure_lost: false` — and the rebuilt page paints nothing, because the
  emitted colour is white. The readback compares the projection with itself, so an emitted value
  that is not the source's visible appearance reads as a match. The same holds for the p02 proxy:
  its record reports `carries_paint: true`, `background_rgb: [255,255,255]`, `passed: true` while
  that white background is exactly what destroys the band underneath it.
- **Proxy proofs test isolation, not fidelity.** Every proxy on p01, p02, p04, p06 and p10 reports
  `passed: true`, `target_survived: true`, `guard_band_ok: true`, `contamination_ok: true` — and
  several of those rasters are visibly wrong (missing shaft, missing dash line, wrong background,
  missing accent colour, missing cell fill, displaced text). Nothing in the record compares the
  raster's content with the source region it replaces.
- **A ledger rule applied inconsistently.** `/slide[2]/shape[@id=8]` is classified
  `base-only-semantic` with the reason "the object's visible text appearance depends on a value the
  slide does not own: color". Three objects on the same page (`[@id=61]`, `[@id=71]`, `[@id=80]`)
  are in the same condition — their colour is not owned by the slide — but carry **no reason code**
  and were emitted editable with a resolved white. That single inconsistency produces the largest
  visible loss on the page.
- **Ledger reconciliation.** I could reconcile all 257 entries with the images, with one nuance
  worth recording: six p01 entries and six p06 entries are counted as `locked-visual-proxy` even
  though only two of each carry paint (the rest are container-owned children with
  `emitted_name = None`). The per-page numbers are therefore larger than the number of proxy
  pictures a reader would count.

## Findings

Every entry gives the identity as `(slot, source page, source object path)`, its class, one line,
and the disposition I recommend. "Rebuilt page" is the projection's output order.

1. **(src1, 2, `/slide[2]/shape[@id=61]`, `[@id=71]`, `[@id=80]`) — MAJOR** — "In 2017", "1.39" and
   "Billion USD" are emitted as white editable text on a white page, so the whole left-hand block
   is invisible. *Recommend: fix in the product (resolve the inherited colour as the base-only path
   already does, or classify these three like `/slide[2]/shape[@id=8]`); re-run the page.*
2. **(src1, 2, `/slide[2]/group[@id=88]`, `[@id=40]`) — MAJOR** — both "1 year" connectors lose their
   horizontal shaft and arrowhead; only a diagonal stub renders. *Recommend: fix the proxy's raster
   extent so the line is inside the picture, not on its boundary; re-check every thin-line proxy.*
3. **(src1, 2, `/slide[2]/shape[@id=8]`) — MAJOR** — the `base-only-semantic` picture for the
   two-line subtitle paints line 2 black/regular where the source is bold red. *Recommend: fix the
   proxy raster's run colour and weight; the picture is wrong, so the "base-only" classification
   does not save it.*
4. **(src1, 2, `/slide[2]/picture[@id=48]` against `/slide[2]/shape[@id=46]`) — MINOR** — the ">"
   chevron picture collides with the "9.50" glyphs where the source has a gap. *Recommend: retain
   as a minor finding.*
5. **(src1, 5, `/slide[5]/shape[@id=100085]` over `/slide[5]/shape[@id=100084]`) — MAJOR** — the
   `base-only-semantic` proxy is an opaque white raster composited over the pink callout band,
   reducing the band to a frame. *Recommend: fix in the product (transparent proxy background, or
   crop the proxy from the source region); this is the page's real defect.*
6. **(src1, 5, `/slide[5]/shape[@id=100085]`) — MINOR** — the band's five text lines start ~10 px
   further right than the source. *Recommend: retain as a minor finding; the "Condor needs" risk is
   this offset, and it is not a blocker by itself.*
7. **(src1, 12, `/slide[12]/table[@id=100088]`) — MINOR** — the specification table's rows are
   38 px in the source and 30 px in the rebuild (table 29 px shorter). *Recommend: retain.*
8. **(src1, 30, `/slide[30]/connector[@id=52]`, `[@id=53]`, `[@id=54]`) — MAJOR** — the three
   horizontal dashed row separators do not render. *Recommend: fix (same root cause as finding 2).*
9. **(src1, 30, `/slide[30]/connector[@id=10]`, `[@id=11]`, `[@id=15]`, `[@id=45]`) — MAJOR** — the
   four vertical separators render solid where the source is dashed. *Recommend: fix; the dash
   pattern is part of what the page shows.*
10. **(src1, 30, `/slide[30]/shape[@id=48]`, `[@id=55]`, `[@id=100132]`, `[@id=100125]`, `[@id=22]`,
    `[@id=41]`) — MAJOR** — these six `base-only-semantic` cell pictures drop run colour and bold, so
    the source's red/orange feature lines are plain black. *Recommend: fix the proxy rasteriser's
    run styling; this is the page's largest visible loss.*
11. **(src1, 30, `/slide[30]/shape[@id=100111]`, `[@id=100112]`, `[@id=100113]`) — MAJOR** — the
    HAIER / CARRIER / MIDEA header cells lose their peach fill (`(252,230,213)` → white). *Recommend:
    fix; a cell fill the source owns must survive into the proxy.*
12. **(src1, 30, `/slide[30]/shape[@id=22]`, `[@id=41]`) — MINOR** — text the source clipped at the
    column edge is painted in full in the rebuild. *Recommend: retain; the rebuild reads better but
    does not match.*
13. **(src1, 30, `/slide[30]/shape[@id=28]`) — MINOR** — "Cooling-only" is rebuilt as "Cooling only";
    the hyphen is dropped in the object-local picture. *Recommend: retain; one dropped character in
    a non-critical phrase, but it shows the proxy raster's text is re-rendered, not copied.*
14. **(src2, 9, `/slide[9]/group[@id=100381]`, `[@id=100383]`) — MAJOR** — both product photos sit on
    opaque white rectangles over the source's lavender panel. *Recommend: fix (same class as finding
    5); two visible white boxes.*
15. **(src2, 9, `/slide[9]/table[@id=100362]`) — MINOR** — "IDU/ODU Dimension (W×D×H mm)" wrap to two
    lines in the source and one line in the rebuild, with identical row heights. *Recommend: keep the
    existing `table_cell_whitespace_placement` retained finding.*
16. **(src3, 21, `/slide[21]/shape[@id=100384]`, `[@id=100385]`, `[@id=100386]`) — MINOR** — the three
    frames use the PowerPoint `roundRect` *default* corner radius, so the inner frames' corners are
    roughly three times rounder than the source's. *Recommend: retain, and check whether the default
    adjustment is leaking into other rounded shapes in the corpus.*
17. **(src5, 1, `/slide[1]/shape[@id=100001]`) — MAJOR** — the nested numbered list item renders "2."
    where the source shows "1.", because the canonical list is flattened into one `<ul>` with
    per-item `list-style-type`. *Recommend: fix in the product (carry list level, or restart
    numbering at each nested level); the probe exists to catch exactly this.*
18. **(src5, 1, `/slide[1]/shape[@id=100000]`) — MINOR** — the hard-break probe keeps both lines but
    with ~43 px leading where the source has 17 px. *Recommend: retain.*
19. **(src5, 1, `/slide[1]/shape[@id=100003]`) — MINOR** — the `base-only-semantic` clipped-overflow
    picture draws its three lines ~20 px higher than the source region. *Recommend: retain as a
    proxy-fidelity finding.*
20. **(src5, 1, `/slide[1]/shape[@id=100000]`, `[@id=100001]`, `[@id=100002]`, `[@id=100011]`) —
    MINOR** — every text block starts ~7–10 px further left because the source's internal left inset
    is not carried (`lIns = 0`). *Recommend: retain; likely systemic, worth one check across pages.*

## Summary

**MAJOR 10 / MINOR 10 / pages reviewed 10/10** (20 images read; five pages carry at least one
MAJOR — p01, p02, p04, p06, p10 — and p04 alone carries six findings; p03 and p08 differ only in
metrics).

Pages I judged visually clean: **p05 (src2 p3), p07 (src3 p2), p09 (src4 p1)**; **p03 (src1 p12)**
and **p08 (src3 p21)** differ only in metrics (table row heights, frame corner radii).

The three findings I would rank first are: p01-1 (three objects painted white on white — invisible
content on a page the gate calls clean), p02-1 (the `base-only-semantic` proxy whose opaque white
background destroys the pink band the bundle's own note calls faithful) and p04-10 / p04-11 (the
cell proxies losing the accent colour and the header fill). All three are cases where the gate's
checks pass by construction while the page a reader opens is visibly not the source page.
