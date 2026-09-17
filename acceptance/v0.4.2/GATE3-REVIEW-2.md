# Gate 3 — second independent visual acceptance review (v0.4.2 projection, 10 selected pages)

> **Publisher's note, added when the bundle was republished.** This document
> judged an **earlier revision** of the branch and is **historical**: its
> verdict and every count in it describe that revision's own run, whose page
> composition differed from the current one. It is kept because the history is
> part of the record -- this is the review that blocked, and later reviews exist
> because of it -- but it is not a statement about the current revision. The
> bundle's verdict is the latest review, `GATE3-REVIEW-4.md`.

**Verdict: PASS_WITH_FINDINGS — MAJOR 2 / MINOR 8 / pages reviewed 10/10.**
Eight of the ten rebuilt pages are visually faithful to their source pages. Every claimed fix holds
except one; three findings from the previous revision do not survive this revision's evidence at
all. The two MAJOR differences are (A) the page number on p07 and p08 wraps to two stacked digits,
and (1) four cell pictures on p04 still paint the source's `accent2`-derived accent colour as black.
No page is missing text, no page is blocked, and both MAJORs sit on pages the machine gate reports
as `rebuilt_issue_count = 0` with a passing text readback.

I did not write this code and I did not read its reports first. The order was: all twenty renders,
then numeric measurement of every difference I thought I saw, then the page's `pages[]` record and
its ledger entries, then the source files where a difference looked like a renderer artefact.
Every finding is located by `(source slot, source page, source object path)` plus the rebuilt page
order.

The stated page identity is confirmed from the artefacts themselves, not assumed: each
`pNN-author.html` slice carries `data-source-key` / `data-source-slide` matching the table in the
brief, and each `pNN-before.png` / `pNN-after.png` is **byte-identical** to my own
`officecli view … screenshot --render native` of the corresponding source page and rebuilt page
(all four checked pairs hash equal), so the acceptance pair really is PowerPoint's own rendering.

---

## p01 — src1, page 2 (rebuilt page 1)

Disposition mix: 33 canonical-editable / 6 locked-visual-proxy / 2 base-only-semantic (41).
Reconciled: the six proxy entries are two groups plus their four container-owned connectors
(`emitted_name = None`), so only two proxy rasters are emitted for them; the two `base-only`
entries are `/slide[2]/shape[@id=8]` and `[@id=9]`. The four `proxy_objects` in the page record are
those two plus the two `base-only` pictures. Every ledger entry is accounted for.

Differences I can see: **none that change what the page communicates.**

* The three objects `/slide[2]/shape[@id=61]` ("In 2017"), `[@id=71]` ("1.39 "), `[@id=80]`
  ("Billion USD") are emitted as white editable text and are **invisible in both renders** — the
  source's own runs declare `a:ln/a:noFill` + `prstClr white`, and the source page paints them on
  the white page just off the left circle (their boxes are x 180–265 at y 175–200, entirely outside
  the circle, which begins at x≈282). Pixel histogram of that box in both renders: **2125/2125
  pixels exactly `(255,255,255)`, zero non-white**. The three objects are also stacked under a
  second set ("In 2026", "9.50", "Million/USD") that the reader actually sees. This is the finding
  the previous audit disproved, and the renders confirm the audit: **NOT A DEFECT**.
* Both `group[@id=88]` / `[@id=40]` connectors: the horizontal shaft is present in the rebuilt
  render at rows 229–230 (94 and 93 dark px of the same x-range) against the source's rows 227–228
  (93, 93). A 2 px vertical shift, no lost line. **NOT A DEFECT.**
* `base-only-semantic` picture for `/slide[2]/shape[@id=8]`: line 2 ("From Algeria To Whole World")
  measures 2232 red-core px in the source and 2195 in the rebuilt page — the red is back.
  **NOT A DEFECT** (was MAJOR in the previous review).
* Title, circles, "Growth Rate > 100% / > 30%", "Million/USD", the red outline arrows and the
  Year/2026/2027/2028 column match; the rebuilt title box is (318,57)-(992,92) against the source's
  (318,56)-(992,91) — same width, 1 px lower. Sub-pixel rasterisation.
* The inherited page number is absent and is not duplicated anywhere. Out of scope.

Residual MINOR: see Findings 2 and 3.

## p02 — src1, page 5 (rebuilt page 2)

Disposition mix: 10 canonical-editable / 0 proxy / 1 base-only-semantic (11). Reconciled: the
`base-only` entry is `/slide[5]/shape[@id=100085]` (reason `text_paragraph_layout_base_only`), the
one proxy picture in the page record.

Differences I can see:

1. The band's five text lines start 10–11 px further right than the source (line left edges
   x=71/72/71/72/72 against x=61/61/60/60/61). MINOR — see Finding 3.

**The "Condor needs" risk, decided: NOT A DEFECT.** The pink band is intact (Finding 1 below), the
word "Condor" is complete (its ink ends at x=198, the neighbouring panel begins at x=199), no line
is added, merged or lost, and the five line breaks are the source's. What the previous review read
as a clipped or re-flowed block is a uniform ~11 px horizontal offset of the whole text object,
present in the source too (the source's "For"/"export" also run past the band's right edge). I
judge it a **minor retained finding**, not a product defect and not a MAJOR.

Not a defect: the table, the three panels, the flag and icon images and the X-PRO photo match; the
inherited header band and page number are absent and not duplicated (out of scope).

## p03 — src1, page 12 (rebuilt page 3)

Disposition mix: 42 canonical-editable / 3 locked-visual-proxy (45). Reconciled: the three proxies
are the gradient header bands `[@id=100068]`, `[@id=100071]`, `[@id=100077]`; they render as the
source's pale grey gradient in both.

**I could not see a difference on this page.** The table's row rules are at y=188/218/248/278 in
*both* renders with 591 grey pixels per rule — identical row heights. The numbered takeaways
(1./2./3.), their two-line breaks, the separator rules, the "Option 1 / Option 2" boxes and their
bullets, and the "Next discussion needed" band all match. The only gate findings for this page are
text-overflow conditions the source already carries (`rebuilt_issue_count = 3`, all mapped to
same-condition source issues).

**Correction to the previous review:** its finding "the specification table's rows are ~20 %
shorter (38 px vs 30 px)" does not hold in this revision — the rows measure 30 px in both. That
finding is fixed or was a measurement error; either way it is gone.

## p04 — src1, page 30 (rebuilt page 4)

Disposition mix: 32 canonical-editable / 10 locked-visual-proxy / 15 base-only-semantic (57).
Reconciled exactly against the ledger: 3 brand-header cells + 4 vertical + 3 horizontal connector
proxies, 15 cell text blocks (`text_base_only`), and 32 editable objects.

Differences I can see:

1. **Four cell pictures still paint the source's `accent2`-derived accent colour as black.**
   (src1, 30, `/slide[30]/shape[@id=100132]`, `[@id=100125]`, `[@id=22]`, `[@id=41]`) — *MAJOR*,
   see Finding A below and Claimed fix 4.
2. The connector separators are dashed in both, but with a different dash pattern — 8 px dash / 5 px
   gap in the source against 3–4 px dash / 3 px gap in the rebuild. MINOR — see Finding 4.
3. The right-most column reflows: "NEW T-MAX" and everything under it sits ~3–5 px lower in the
   rebuild, and the vertical text block of the "X-Smart R32 Inverter" cell is 86 px tall in the
   source against 72 px in the rebuild. All the text is present and the line breaks are the
   source's; this is a metrics difference. MINOR.

Not a defect: the title, the "SPLIT-SYSTEM PLATFORM LINE-UP" band, the LINE / FRESH / TCL cells,
the row labels, the product photos and the TCL logo. The peach brand-header fills are back
(`(252,230,213)`, 73 % of each header box against the source's 85 %). The `C00000` red feature
lines inside `/slide[30]/shape[@id=48]` and `[@id=55]` are present in both renders (red-core ink per
row within 10 %), so the previous "all six cells lose their accent colour" is now precisely **four**
cells, not six — the two that declare a plain `srgbClr` survive. The previous review's
"Cooling only" dropped-hyphen finding does not hold either: the rebuild paints "Cooling-only"
(measured at 2× zoom).

## p05 — src2, page 3 (rebuilt page 5)

Disposition mix: 18 canonical-editable, no proxies. Reconciled exactly: title, subtitle, grey rule,
three cards (panel + name + sub-label + photo), three tables = 18.

**I could not see a difference.** Ink-band profile: the title block sits at y 78–101/128–139 in the
rebuild against 91–115/124–135 in the source — the rebuilt title is ~13 px higher and its subtitle
~4 px lower, i.e. the title-to-subtitle gap grew from 9 px to 27 px. Every table row, border, header
fill and red column head matches; the only missing paint is the inherited "PRODUCT LINE-UP" eyebrow
and the brand marks in the top band, which are layout/master paint, out of scope, and not duplicated.

## p06 — src2, page 9 (rebuilt page 6)

Disposition mix: 22 canonical-editable / 6 locked-visual-proxy (28). Reconciled: the six proxy
entries are the two product-photo groups plus their four container-owned children.

Differences I can see:

1. "IDU/ODU Dimension (W×D×H mm)" occupies one line in the rebuild and two in the source, with row
   borders identical in both (the cell's text band is y 242–251 in the rebuild against y 234–242 +
   250–257 in the source). MINOR — Finding 6.

Not a defect: the lavender panel `(243,244,245)` is intact — 89 569 panel-grey pixels against the
source's 90 200, with 38 759 white pixels against 38 792 (all of them inside the product units, not
painted over the panel). Both product photos sit on the panel, not on white boxes. The title matches
(bbox (48,125)-(600,175) against (48,124)-(600,175)).

## p07 — src3, page 2 (rebuilt page 7)

Disposition mix: 26 canonical-editable, no proxies. Reconciled exactly: the band and page number are
slide-owned on this deck (they are ledger entries here, unlike src1/src2), plus title, subtitle,
rule, footer and three cards with five objects each.

Differences I can see:

1. **The page number "02" is painted as two lines, "0" above "2".**
   (src3, 2, `/slide[2]/shape[@id=100071]`) — *MAJOR*, Finding A.

Not a defect: the three tables, the header row, the card panels, the labels, the "SOURCE ROWS"
captions and the masthead match. Removing the page number, everything else differs only by sub-pixel
rasterisation (ink-band starts agree within 1 px on every remaining band).

## p08 — src3, page 21 (rebuilt page 8)

Disposition mix: 12 canonical-editable, no proxies. Reconciled: band (3), title, subtitle, rule,
footer, page number, three frames, the table.

Differences I can see:

1. **The page number "19" is painted as two lines, "1" above "9".**
   (src3, 21, `/slide[21]/shape[@id=100383]`) — *MAJOR*, Finding A.

Not a defect: the title, the subtitle, the Chinese product-line cells (including their wrap point)
and the table's ten rows are pixel-aligned (ink-band starts agree within 1 px on every band except
the page number).

## p09 — src4, page 1 (synthetic probe A) (rebuilt page 9)

Disposition mix: 7 canonical-editable, no proxies. Reconciled exactly: red box, three text lines,
blue ellipse, orange right arrow, "Continue" label.

**I could not see a difference.** The three filled shapes have identical bounding boxes in source
and rebuild (red box x 133–479 / y 267–426; ellipse x 667–879 / y 385; arrow x 667–905 / y 481–572),
the arrow's fill is `(238,130,47)` in both, and it declares no outline in either, so no outline is
missing. The white text inside the red box occupies the same three rows in both, 5 px higher in the
rebuild (y 291–301 / 331–341 / 371–381 against 296–306 / 336–346 / 376–386) with the same leading.
**The rightArrow probe passes.**

## p10 — src5, page 1 (synthetic probe B) (rebuilt page 10)

Disposition mix: 8 canonical-editable / 3 locked-visual-proxy / 1 base-only-semantic (12).
Reconciled: the proxies are the crimson rectangle + diagonal line group plus two container-owned
children, and the clipped-overflow text block `[@id=100003]` (`base_only`, `text_base_only`).

**I could not see a difference.** The list now declares four **top-level** items by design
(`list-style-type: disc` ×2 then `decimal` ×2, all `margin-left: 0px`), and the render shows "• Level
zero bullet item / • Second bullet item / 1. Numbered item one / 2. Numbered item two" — the same
markers, the same ordinals and the same indentation as the source. The previous MAJOR (a nested item
rendering "2." where the source shows "1.") is gone because the source's list no longer declares a
nested level; the refusal path is the documented resolution.

The hard-break probe now has the source's leading: line 1 at y 221–231 and line 2 at y 239–249 in
the source against 231–241 and 248–258 in the rebuild — 17–18 px pitch in both. The whole block sits
10 px lower and 7 px further left. MINOR, Finding 7. The crimson rectangle, the diagonal line, the
blue rectangle, the grey rounded rectangle, the orange bar and the theme-resolved body text's colour
all match; the mixed-run title (Latin + CJK + italic + fixed decimals) is complete and unwrapped.

---

## Claimed fixes — verified one by one

| Claim | Holds? | Measurement |
|---|---|---|
| **Pink callout band, p02** | **YES** | Exact `(255,241,241)` pixels inside the band's box: **21 360 → 21 536** in the render, source 22 466 → rebuilt 22 388 over the band's full box. The band is a solid round-rect again (scan of row 428 shows the identical pink run in both); the band is emitted *before* the text picture, and the picture's background is now keyed transparent. The previous "opaque white rectangle over the band" is gone; 8 570 → 22 474 in the audit's own numbers is consistent with mine. |
| **Lavender panel, p06** | **YES** | Panel region: panel-grey pixels **89 569 rebuilt vs 90 200 source**, white pixels **38 759 vs 38 792** — the same white, and all of it is inside the product units. No white box sits on the panel. |
| **Dashed separators, p04** | **YES (pattern differs — Finding 4)** | Horizontal rules, dominant row: source **487 red px of 851 columns with 8 px dash / 5 px gap (61 runs)**; rebuilt **367 px with 3 px dash / 4 px gap (122 runs)**. Vertical rules: source 8 px / 5 px (33 runs over 416 rows); rebuilt 4 px / 3 px (64 runs). Both are dashed; the rebuilt pattern is denser. The dashes now live inside the proxy rasters (`proxy-…-053` decodes as 6–7 px runs with 6 px gaps), and the rebuilt slide declares no `prstDash` at all because the separators are pictures. |
| **Brand header fill, p04** | **YES** | HAIER/CARRIER/MIDEA header cells now sample exactly `(252,230,213)`: peach pixels **1 693 / 1 588 / 1 659 source** vs **1 709 / 1 567 / 1 676 rebuilt** (73 % of each box against the source's 85 %). The theme expression resolves. |
| **Red/orange feature lines in the cell pictures, p04** | **NO — half fixed** | Plain `srgbClr C00000` red survives (the "5 Easy Upgrade" / "AI Voice Control" / "GEN- Mode" lines are red in both renders), but the four cells whose runs declare `accent2 lumMod="75000"` are rebuilt black. Orange-core pixels: HAIER HIGH `715 → 10`, MIDEA MID `85 → 0`, HAIER MID `0 → 9`, FRESH MID `0 → 0`. The proxy raster for `[@id=100132]` decodes to 932 pure-black and 1744 `(34,34,34)` pixels with no orange anywhere. **Finding A, still open.** |
| **Nested numbered list item, p10** | **YES (by design)** | The source's list now declares only top-level items; the emitted markup is one `<ul>` of four `<li>`, all `margin-left: 0px`, and the render reads "1. Numbered item one / 2. Numbered item two" in both source and rebuild. The nesting defect cannot recur on this probe, which is the documented resolution (the level is refused rather than emitted flat). |

## Machine-claim cross-check

The gate report says `PASS_WITH_FINDINGS`, `accepted: true`, `material_deltas: 0`,
`rebuilt_issues: 3`, `proxy_proofs_failed: 0`, `blocking_diagnostics: 0`; **every** page record
carries `rebuilt_issue_count = 0` and an empty `material_deltas`. Its three `rebuilt_issues` are
text-overflow conditions on p03 that the source already carries.

* **The page where the machine says text readback passed and the page is visibly wrong: p07 and
  p08.** Both page-number objects carry `matched: true`, `style_matched: true`,
  `structure_lost: false`, `whitespace_only_difference: false` — the compact text is "02" / "19" —
  and both render as two stacked digits. All 152 text records across the ten pages are clean:
  0 failed, 0 whitespace-only. So the whole visible defect set on this revision is invisible to the
  text readback, because the readback compares the projection with itself and wrapping is not part
  of what it compares. (For the record, the same is true of the four black cell pictures on p04:
  they are `base-only-semantic`, so the readback does not cover their runs at all, and every one of
  their proxy proofs reports `passed: true`, `carries_paint: true`, `target_survived: true`.)
* **Ledger reconciliation.** All 257 entries reconcile with the images, with the same nuance the
  previous review recorded: six p01 entries and six p06 entries are `locked-visual-proxy` although
  only two of each carry paint (the rest are container-owned children with `emitted_name = None`),
  so the per-page proxy counts are larger than the number of proxy pictures a reader would count.
  The page-number objects on p07/p08 **are** in the ledger (`canonical-editable`, emitted as
  `slide-007-textbox-008` / `slide-008-textbox-008`), which lets the defect be located exactly.
* **Two previous findings I could not reproduce** and therefore do not carry forward: the p03 table
  row heights (identical in this revision) and the p04 "Cooling only" dropped hyphen (the rebuild
  paints "Cooling-only"). I report them here so the record is not left claiming defects that are
  not there.

### What I settled against the source files

* **The `In 2017` / `1.39` / `Billion USD` objects.** The source slide does declare both sets of
  text ("In 2017", "1.39 ", "Billion USD" *and* "In 2026", "9.50", "Million/USD"). Measuring the
  three boxes at their declared geometry in both renders gives **zero non-white pixels in either**,
  so the source paints white text on the white page exactly as the rebuild does. The finding is
  disproved, and I confirmed the previous audit's reading rather than trusting it.
* **The page-number wrap is a real difference in the produced deck, not a renderer artefact.**
  `/slide[2]/shape[@id=100071]` and its rebuilt counterpart `slide-007-textbox-008` are the same
  object to the byte: same `a:off`/`a:ext` (12 3229 vs 12 3130 EMU wide — 0.008 pt apart), same
  `lIns/tIns/rIns/bIns = 0`, same `anchor="t"`, same `<a:normAutofit/>`, same `sz="900"`, same
  `Segoe UI`, same `747B81`; the theme part and the slide master are identical to the byte, and the
  empty slide layout differs only in an xmlns attribute order. The rebuilt picture nevertheless
  renders "0" at y 687–696 and "2" at y 702–710 where the source renders one 9-px-tall "02". The
  box is 9.7 pt wide and the 9 pt text needs more, so the source's own box is at the wrap threshold;
  the rebuild falls on the other side of it. Since the declared XML is identical, I report this as a
  difference a reader sees on the rebuilt page (MAJOR) with the caveat that the mechanism is not in
  the object's own declaration — it needs the implementation's own diagnosis.
* **Verification of the render pair itself.** `p07-before/after` and `p08-before/after` are
  byte-identical to fresh `officecli view … screenshot --render native` renders of the source page
  and of `gate/rebuilt.pptx`. The pair is therefore PowerPoint's own rendering, not one HTML
  screenshot path's opinion, and the wrap is visible in both.

## Findings

Every entry gives `(slot, source page, source object path)`, its class, one line, and the
disposition I recommend. "Rebuilt page" is the projection's output order.

**A. (src3, 2, `/slide[2]/shape[@id=100071]`) and (src3, 21, `/slide[21]/shape[@id=100383]`) —
MAJOR** — the page number is painted as two stacked digits ("0"/"2" on rebuilt page 7, "1"/"9" on
rebuilt page 8) where the source paints "02" / "19" on one line, because the 9.7 pt-wide text box
sits exactly at the wrap threshold for its 9 pt text. *Recommend: fix in the product — emit the
page-number box with wrapping off (`wrap="none"`), or widen it to its measured text width; both
objects render on one line in the source. Re-check every narrow text box across the corpus, since
this class of object (a two-digit page number in a ~10 pt box) is present on every slide of this
deck. This is the highest-value finding in this review: it is a visible defect on two pages that
the text readback calls clean.*

1. **(src1, 30, `/slide[30]/shape[@id=100132]`, `[@id=100125]`, `[@id=22]`, `[@id=41]`) — MAJOR** —
   four `base-only-semantic` cell pictures drop the run colour declared as
   `schemeClr accent2 lumMod="75000"`, so the source's orange feature lines paint black. *Recommend:
   fix in the product (the same run-styling pass the audit already scoped for the `srgbClr` case);
   the `C00000` cells prove the mechanism works when the colour is a plain srgb value.*
2. **(src1, 2, `/slide[2]/picture[@id=48]` against `/slide[2]/shape[@id=46]`) — MINOR** — the ">"
   chevron picture ends at x=317.8 in slide units while the "9.50" text box starts at x=307.8, so
   the glyphs overlap by ~6 px of render where the source has a gap. *Recommend: retain as a minor
   finding (picture placement vs text box placement).*
3. **(src1, 5, `/slide[5]/shape[@id=100085]`) — MINOR** — the band's five text lines start 10–11 px
   further right than the source (this is the whole of the "Condor needs" risk; no character is
   lost, no line is added or merged). *Recommend: retain as a minor finding; not a product defect on
   its own.*
4. **(src1, 30, `/slide[30]/connector[@id=52]`, `[@id=53]`, `[@id=54]`, `[@id=10]`, `[@id=11]`,
   `[@id=15]`, `[@id=45]`) — MINOR** — the separators are dashed in both, but the rebuilt dash
   pattern is denser (3–4 px dash / 3 px gap against the source's 8 px dash / 5 px gap), so the grid
   reads as a finer dotted rule. *Recommend: retain as a minor finding; the previous "solid, not
   dashed" MAJOR is genuinely fixed.*
5. **(src3, 21, `/slide[21]/shape[@id=100384]`, `[@id=100385]`, `[@id=100386]`) — MINOR** — the
   frames still declare the PowerPoint `roundRect` default adjustment (`adj val 16667`), so the
   inner frames' corners are rounder than the source's. *Recommend: retain, and check whether the
   default adjustment leaks into other rounded shapes.*
6. **(src2, 9, `/slide[9]/table[@id=100362]`) — MINOR** — "IDU/ODU Dimension (W×D×H mm)" wraps to
   two lines in the source and one in the rebuild, with identical row heights. *Recommend: keep the
   existing `table_cell_whitespace_placement` retained finding.*
7. **(src5, 1, `/slide[1]/shape[@id=100000]`, `[@id=100001]`, `[@id=100002]`, `[@id=100011]`) —
   MINOR** — every text block starts ~7 px further left and ~10 px lower than the source, because
   the source's internal left inset is not carried. *Recommend: retain; likely systemic, worth one
   check across pages.*
8. **(src1, 30, `/slide[30]/shape[@id=22]` and the right-most column) — MINOR** — the column reflows
   slightly (the "NEW T-MAX" block ~3–5 px lower; the "X-Smart R32 Inverter" text block 86 px tall
   in the source against 72 px in the rebuild). All text is present and the line breaks are the
   source's. *Recommend: retain.*

## Summary

**MAJOR 2 / MINOR 8 / pages reviewed 10/10** (20 images read; the two MAJOR findings are the
page-number wrap on p07 and p08, counted once, and the four black cell pictures on p04, counted
once).

Pages judged visually clean: **p01 (src1 p2), p03 (src1 p12), p05 (src2 p3), p06 (src2 p9),
p09 (src4 p1), p10 (src5 p1)** — six of ten. **p02 (src1 p5)** carries one minor offset and no
product defect; **p04 (src1 p30)** carries the one remaining MAJOR plus minor reflow; **p07** and
**p08** (src3 p2, p21) carry the page-number MAJOR and nothing else.

Relative to the previous revision this is a large improvement: eight of the ten previously reported
MAJOR findings are measurably fixed (the pink band, the lavender panel, the two connector-dash
findings, the theme-expression fill, the subtitle's red, the nested list level, the table row
heights), and three previously reported findings do not survive this revision's evidence at all
(the white-text objects, the "Cooling only" hyphen, the p03 table rows) — one of those was already
disproved by the source files, and I confirmed that independently.

The single thing I would fix first is **A**: it is the only defect on this revision that a reader
sees on a page the machine gate calls `rebuilt_issue_count = 0` with a passing text readback, and
the object class it belongs to (a narrow two-digit page number) appears on every slide of that deck.
