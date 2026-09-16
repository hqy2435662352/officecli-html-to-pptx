# Gate 3 — third independent visual acceptance review (v0.4.2 projection, 10 selected pages)

**Verdict: PASS_WITH_FINDINGS — MAJOR 1 / MINOR 9 / pages reviewed 10/10.**

Both findings that the second review raised as MAJOR are **fixed** and I confirmed it by measurement, not by
reading the implementation's reports: the two page numbers paint on one line again with ink boxes identical
to the source to the pixel, and the four cell pictures paint the source's orange feature lines again.
One new MAJOR appears, on **p10**, where a hard line break declared in the Canonical Author HTML is compiled
into a paragraph break, so the page gains a blank line the source does not have. Nine MINOR differences are
small metric offsets; six pages are visually clean.

I did not write this code and I did not read its reports first. Order of work: all twenty renders, then
numeric measurement of every difference I thought I saw, then each page's `pages[]` record and its ledger
entries, then the source decks where a difference looked like a renderer artefact. Every finding is located
by `(source slot, source page, source object path)` plus the rebuilt page order.

Page identity is confirmed from the artefacts themselves: each `pNN-author.html` slice carries
`data-source-key` / `data-source-slide` matching the table in the brief.

---

## p01 — src1, page 2 (rebuilt page 1)

Disposition mix: 33 canonical-editable / 6 locked-visual-proxy / 2 base-only-semantic (41). Every ledger
entry reconciles with what is on the page.

Differences I can see:

1. **The header row sits 51–56 px further left than the source.** Ink boxes, measured on the row
   "Year / FS/Split AC / Solar/LCAC/MultiSplit / +VRF": "Year" **169–209 → 113–151**, "FS/Split AC"
   **288–391 → 158–269**, "Solar/LCAC/MultiSplit" **538–744 → 512–717**, "+VRF" **905–954 → 822–870**.
   The words themselves are the same size (band heights 21 px in both); the objects have moved. MINOR
   (see Findings 2).
2. **`base-only-semantic` pictures** for `/slide[2]/shape[@id=8]` and `[@id=9]`: line 2
   ("From Algeria To Whole World") paints red in both renders; the previous review's fix holds.
3. The three objects `/slide[2]/shape[@id=61]` ("In 2017"), `[@id=71]` ("1.39 "), `[@id=80]`
   ("Billion USD") are still emitted as white text and are still **invisible in both renders**; the source
   declares `noFill` outline plus `prstClr white` and paints nothing at the same geometry.
   **NOT A DEFECT.**
4. `/slide[2]/picture[@id=48]` (the ">" chevron) against `[@id=46]` ("9.50"): in the rebuild the chevron
   renders with a **wider white gap** between the red box and the glyph (a separate light triangle is
   visible where the source only shows a cut arrowhead). The text is not overlapped and nothing is lost.
   **NOT A DEFECT** (the previous review's overlap concern is gone).
5. Connectors `[@id=88]` / `[@id=40]` ("1 year" rules) land on the same rows in both renders.
6. The inherited page number is absent and not duplicated anywhere. Out of scope.

**Structural note (not a visual defect):** the three source tables `/slide[2]/table[@id=100077]`,
`[@id=100083]`, `[@id=100089]` are `canonical-editable` and marked emitted in the ledger, but rebuilt
`slide1.xml` contains **no `<a:tbl>` and no `<p:graphicFrame>` at all**. The tables' cells are empty in the
source, so the page paints no grid in either render and a reader sees no difference — but the ledger claim
and the produced deck disagree.

## p02 — src1, page 5 (rebuilt page 2)

Disposition mix: 10 canonical-editable / 0 proxy / 1 base-only-semantic (11).

**The "Condor needs" block, decided: NOT A DEFECT, one MINOR retained.** The pink band is intact and
unclipped; "Condor" ends at x=198 and the neighbouring panel starts at x=199; no line is added, merged or
lost; the five line breaks are the source's. What is visible is that **the whole five-line block sits
10–11 px further right than the source** (`What`/`Condor`/`needs`/`For`/`export` left edges 71/72/71/72/72
against the source's 61/61/60/60/61), and the rebuilt glyphs render slightly heavier at the same nominal
size. MINOR — Finding 3.

Not a defect: the table (row rules and header fill identical), the three panels, the flag and icon images,
the X-PRO photo. The inherited header band ("AIR CONDITIONER", "COMFORT | RELIABILITY | INTELLIGENCE",
the brand lock-up) and the inherited page number are absent and not duplicated — out of scope.

## p03 — src1, page 12 (rebuilt page 3)

Disposition mix: 42 canonical-editable / 3 locked-visual-proxy (45); the three proxies are the gradient
header bands. **I could not see a content difference on this page.**

What I do measure: once past the masthead, every band on the lower two-thirds sits **~12 px lower** than
the source — panel 2's heading "Focus Models & Current Performance", the "Rated Cooling Capacity (W)"
header row, the "Priority recommendation" strip, panel 4's "TCL Customized Solution Proposal" and the
"Next discussion needed" block all move down by 12 px (e.g. "TCL 3 Years..."-band → panel-4 heading band
475–496 → 482–494 within the panel's own frame). The numbered takeaways 1./2./3., their two-line breaks,
the separator rules, the "Option 1 / Option 2" boxes and their bullets match. MINOR — Finding 4.

The three `rebuilt_issues` the gate reports for this page are text-overflow conditions the source already
carries; the page record's `retained_findings` lists eleven such source-carried conditions.

## p04 — src1, page 30 (rebuilt page 4)

Disposition mix: 32 canonical-editable / 10 locked-visual-proxy / 15 base-only-semantic (57).
Reconciled against the ledger: 3 brand-header cells + 4 vertical + 3 horizontal connector proxies,
15 cell text blocks (`text_base_only`, emitted as pictures), 32 editable objects.

Differences I can see:

1. **The four cell pictures now paint the source's orange feature lines.** Measured from the rebuilt
   render (see "The two previous majors" below): saturated orange cores `(197,87,0)` / `(199,87,4)` /
   `(198,86,3)` / `(197,88,3)` against the source's `(198,95,16)`, with 556–1071 orange-family pixels per
   cell against the source's 666–1249. **The second review's MAJOR A is fixed.** The residual difference
   is that the lines paint a few pixels lower and with softer strokes than the source, because these text
   cells are painted as pictures, not text — MINOR, Finding 1.
2. **The right-hand column reflows**: "PREMIUM S7 GCC MODEL / R32 | Inverter| HP" moves **~10 px down and
   ~17 px right**; the "NEW T-MAX" block and the "X-Smart R32 Inverter" cell shift by similar amounts.
   All text is present, in the source's line breaks. MINOR — Finding 5.
3. The dashed separators are present in both and now land on the same columns (vertical rules at
   x 346.5 / 580.5 / 810.5 / 1028.5 in the source against 348 / 582.5 / 811.5 / 1030 in the rebuild), but
   the rebuilt dash is shorter and the gaps tighter, so the grid reads as a finer dotted rule. MINOR.

Things I checked and cleared:

* **No missing, duplicated or mis-painted proxy paint.** All 37 proxy rasters decode with real content
  (alpha coverage 1.9 %–96.6 %), and the four cell pictures whose feature lines were black now decode
  `(198, 95, 16)` at 574–1297 px each. Region check of the HAIER HIGH cell: 4402 non-white px in the
  source against 5509 in the rebuild — the rebuild paints *more*, not less, so no proxy is blank and none
  is covered by a neighbour.
* **The apparent white gap over text I chased on the right-hand column is a renderer artefact, not paint.**
  Scanning the rebuilt PNG at gap ≥3 px finds no white box anywhere on the page; the "white box" I first
  saw in a tightly cropped pane was the pane edge, and the text it appeared to cover ("PREMIUM S7 GCC
  MODEL / R32 | Inverter| HP", "Plasma air purification") is complete in the rebuilt render.
  **NOT A DEFECT** — and I record it because the first thing it looked like was major.
* The peach brand-header fills `(252,230,213)` are present; the `C00000` red feature lines inside
  `/slide[30]/shape[@id=48]` and `[@id=55]` are present in both.
* The title, the "SPLIT-SYSTEM PLATFORM LINE-UP" band, the LINE / FRESH / TCL cells, the row labels and
  the product photos match.

## p05 — src2, page 3 (rebuilt page 5)

Disposition mix: 18 canonical-editable, no proxies. Reconciled exactly: title, subtitle, grey rule, three
cards (panel + name + sub-label + photo), three tables.

**I could not see a content difference.** What I measure: the title block sits 13 px higher and the
subtitle 4 px lower, so the title-to-subtitle gap grows from 9 px to 27 px (ink bands y 78–101 / 128–139
in the rebuild against 91–115 / 124–135 in the source). MINOR — Finding 6. Every table row, border, header
fill and red column head matches; the only missing paint is the inherited "PRODUCT LINE-UP" eyebrow and
the brand marks in the top band, which are layout/master paint, out of scope, and not duplicated.

## p06 — src2, page 9 (rebuilt page 6)

Disposition mix: 22 canonical-editable / 6 locked-visual-proxy (28); the six proxy entries are the two
product-photo groups plus their four container-owned children.

1. "IDU Dimension (W×D×H mm)" and "ODU Dimension (W×D×H mm)" each occupy **one line in the rebuild and
   two in the source**, so the two label cells' text sits higher inside identical row borders (the first
   label's ink band is y 479–489 in the rebuild against y 458–466 + 474–482 in the source).
   MINOR — Finding 7; this is the gate's own `table_cell_whitespace_placement` retained finding.
2. The lavender panel `(243,244,245)` is intact and both product photos sit on the panel, not on white
   boxes. The "SPECIFICATIONS" heading and its red underscore match. No missing or duplicated paint.

## p07 — src3, page 2 (rebuilt page 7)

Disposition mix: 26 canonical-editable, no proxies.

1. **The page number "02" paints on one line again — the second review's MAJOR is fixed.** Measurement in
   "The two previous majors". **NOT A DEFECT.**
2. Everything else matches: the three tables, the header row, the card panels, the labels, the
   "SOURCE ROWS" captions and the masthead. Ink bands agree within 3–4 px everywhere ("TPRO" panel and its
   caption, the "XPRO" panel, the "ELITE" panel, the three table header rows), which is sub-pixel
   rasterisation for a 2 px-per-point source render downscaled to 1280 px. **NOT A DEFECT.**

## p08 — src3, page 21 (rebuilt page 8)

Disposition mix: 12 canonical-editable, no proxies.

1. **The page number "19" paints on one line again — fixed.** Measurement below. **NOT A DEFECT.**
2. The three decorative frames still declare the PowerPoint `roundRect` default adjustment, so their
   corners are visibly rounder than the source's, and they sit a few px lower. MINOR — Finding 8.
3. The Chinese product-line cell "R32变频机种冷暖（阿尔及利亚）" wraps to three lines in the rebuild where
   the source uses two, inside an identical row border. MINOR.
4. The title, subtitle and the table's ten rows are otherwise aligned (ink-band starts agree within 1 px
   on every band except the page number).

## p09 — src4, page 1 (synthetic probe A) (rebuilt page 9)

Disposition mix: 7 canonical-editable, no proxies. Reconciled exactly: red box, three text lines, blue
ellipse, orange right arrow, "Continue" label.

**I could not see a difference.** This is the cleanest page in the set: only 2 158 differing pixels across
the whole 1280×720 pair (against 23 000–105 000 on the others), all of it the white text inside the red box
sitting 5 px higher and the "Continue" caption 6 px higher, with identical leading. The three filled shapes
have identical bounding boxes in both renders, the `rightArrow` has the same fill, the same sharp
arrowhead and **no outline in either**, and the ellipse's edge is clean in both — the rightArrow probe
passes. **NOT A DEFECT.**

## p10 — src5, page 1 (synthetic probe B) (rebuilt page 10)

Disposition mix: 8 canonical-editable / 3 locked-visual-proxy / 1 base-only-semantic (12).

1. **The hard line break is compiled into a paragraph break, so the page gains a blank line.**
   (src5, 1, `/slide[1]/shape[@id=100000]`, rebuilt `slide-010-textbox-001`) — *MAJOR*, Finding A below.
2. The list is right: four top-level items, "• Level zero bullet item / • Second bullet item /
   1. Numbered item one / 2. Numbered item two" — same markers, same ordinals, same indentation as the
   source. The previous MAJOR (a nested item rendering "2." where the source shows "1.") does not recur.
3. The whole left-hand text column sits 7–10 px further left and 10–18 px lower than the source (bullets
   at y 231–294 against 221–284; title at y 42–64 against 47–69). MINOR — Finding 9.
4. "Theme resolved body 主题" paints in the theme-resolved colour, the crimson rectangle, diagonal line,
   blue rectangle, grey rounded rectangle and orange bar all match, and the mixed-run title
   (Latin + CJK + italic + fixed decimals) is complete and unwrapped.

---

## The two previous majors

Both were re-measured independently from the two renders.

### (src3, page 2, `/slide[2]/shape[@id=100071]`) and (src3, page 21, `/slide[21]/shape[@id=100383]`) — the page numbers

Ink bounding box of the page-number region (window x 1160–1270, y 655–715), measured at three luminance
thresholds so the answer does not depend on one cut-off:

| page | render | ink box @thr 230 | @thr 200 | @thr 150 | ink rows |
|---|---|---|---|---|---|
| p07 (src3 p2) | source | x 1218–1229, y 687–695 | x 1218–1229, y 687–695 | x 1219–1229, y 687–695 | one band, y 687–695 |
| p07 (src3 p2) | rebuilt | x 1218–1229, y 687–695 | x 1218–1229, y 687–695 | x 1219–1229, y 687–695 | one band, y 687–695 |
| p08 (src3 p21) | source | x 1219–1229, y 687–695 | x 1219–1229, y 687–695 | x 1219–1229, y 687–695 | one band, y 687–695 |
| p08 (src3 p21) | rebuilt | x 1219–1229, y 687–695 | x 1219–1229, y 687–695 | x 1219–1229, y 687–695 | one band, y 687–695 |

**What the page numbers paint now:** a single-line "02" on rebuilt page 7 and a single-line "19" on
rebuilt page 8, each **12 px wide × 9 px tall** for "02" and **11 px × 9 px** for "19", at
**exactly the source's coordinates** — the row-run profile returns one band (y 687–695) in all four
renders, and at 4× zoom both digits sit side by side on one baseline. The two-stacked-digits defect is
gone. The second review's recommendation (stop the narrow box from wrapping) has taken effect.

### (src1, page 30, `/slide[30]/shape[@id=100132]`, `[@id=100125]`, `[@id=22]`, `[@id=41]`) — the four cell pictures

Measured from the rebuilt render inside each object's declared bounds (converted at the render's
1.333 px/pt), counting saturated orange cores (r−g > 50, r−b > 60) and the whole warm family:

| object | cell | source orange px (core / warm) | rebuilt orange px (core / warm) | most saturated rebuilt pixel | source pixel |
|---|---|---|---|---|---|
| `[@id=100132]` | HAIER HIGH | 715 / 983 | 931 / 608 | **(197, 87, 0)** | (198, 95, 16) |
| `[@id=100125]` | HAIER MID | 85 / 677 | 717 / 591 | **(199, 87, 4)** | (198, 95, 16) |
| `[@id=22]` | MIDEA MID | 0 / 931 | 1071 / 673 | **(198, 86, 3)** | (198, 95, 16) |
| `[@id=41]` | FRESH MID | 0 / 528 | 556 / 438 | **(197, 88, 3)** | (198, 95, 16) |

**What those cells paint now:** the orange feature lines are back on all four. The decoded proxy rasters
carry `(198, 95, 16)` at 574–1297 px each, which is the source's own orange, and the rendered page shows
that colour at the same lines the source colours — "High Air Circulation /IFD Air Purification",
"Haismart/UVC Feature/ECO", "AI Comfort Saving; / Smart Home Control; / Ice Circuit Tech",
"Plasma air purification". The rebuilt lines paint 4–7 px lower than the source's and with thinner
antialiased strokes (only 3–6 fully saturated pixels per line against the source's 237–536, because these
text cells are painted as pictures that get resampled on the page). That residue is Finding 1.

---

## Machine-claim cross-check

The gate report says `accepted: true`, `material_deltas: 0`, `rebuilt_issues: 3`,
`proxy_proofs_failed: 0`, `blocking_diagnostics: 0`; every page record carries
`rebuilt_issue_count = 0`, an empty `material_deltas`, and **all 152 text records across the ten pages
report `matched: true`, `style_matched: true`, `structure_lost: false`,
`whitespace_only_difference: false`**. Its three `rebuilt_issues` are text-overflow conditions on p03 that
the source already carries.

**The page where the machine says the text and structure readback passed but the page is visibly wrong:
p10.** `/slide[1]/shape[@id=100000]` reports `expected_structure_text` and `rebuilt_structure_text` both
equal to `"…1,234,567.89\nHard break probe line\nsecond visual line"` with `structure_lost: false` — yet
the rebuilt slide declares **two paragraphs where the source declares one paragraph containing one hard
break** (source `ppt/slides/slide1.xml`: 1 `<a:br/>`, paragraphs `['H','ard break probe line','second
visual line']`; rebuilt `ppt/slides/slide10.xml`: 0 `<a:br/>`, paragraphs `['H','ard break probe line']`
then `['second visual line']`). The readback compares normalised text and cannot see a break turn into a
paragraph, so the defect is invisible to it.

* **Proxy text is outside the readback entirely.** On p04 fifteen text-carrying objects are
  `base-only-semantic` pictures; the page's 16 readback records do not cover their runs at all, and every
  one of their proxy proofs reports `passed: true`. The second review's black-line defect lived exactly
  there.
* **Ledger reconciliation.** All 257 entries reconcile with the images, with the nuance both earlier
  reviews recorded: on p01 six and on p06 six entries are `locked-visual-proxy` although only two of each
  carry paint (the rest are container-owned children with `emitted_name = None`), so the per-page proxy
  counts are larger than the number of proxy pictures a reader would count.
* **One ledger/output disagreement, no visual consequence:** the three p01 tables are listed as
  `canonical-editable`, `emitted: true`, with emitted names, and the page record's `object_names` does not
  list them, while `rebuilt slide1.xml` contains no table at all. Their cells are empty in the source, so
  the page paints no grid either way.

### What I settled against the source files

* **The p10 hard break.** I read the Canonical Author HTML for the page, which is where the mechanism
  shows: `p10-author.html` emits the block as one `<div>` with `white-space: pre` containing
  `…<br><span …>H</span><span …>ard break probe line</span><br><span …>second visual line</span></div>` —
  the break *is* declared, as `<br>` inside one block. The compiler then writes two `<a:p>` elements
  instead of one paragraph containing `<a:br/>`. So this is not a projection-input loss: the HTML is
  correct and the HTML→PPTX step is where the blank line appears.
* **The page-number verdict is not a renderer artefact.** The ink boxes agree to the pixel at three
  thresholds and the row profile returns a single band in all four renders.
* **The p01 header-row shift is not a font substitution.** The rebuilt run declares
  `<a:latin typeface="微软雅黑"/>` at `sz="1495"`, byte-identical to the source run's typeface and size
  (both UTF-8 `e5 be ae e8 bd af e9 9b 85 e9 bb 91`), and the glyph shapes are the same in both renders —
  so the objects' placement, not the font, is what moved.
* **The apparent black-versus-orange question on p04 is answered in the pixels, not in the report:** the
  source's orange `(198, 95, 16)` is present in the rebuilt render at the same lines, so the colour
  expression now resolves. The earlier "no orange anywhere" reading does not hold for this revision.

---

## Findings

Every entry gives `(slot, source page, source object path)`, its class, one line, and the disposition I
recommend. "Rebuilt page" is the projection's output order.

**A. (src5, 1, `/slide[1]/shape[@id=100000]`, rebuilt `slide-010-textbox-001`) — MAJOR** — the source's hard
line break (`<a:br/>` inside one paragraph, and `<br>` in the Canonical Author HTML) is compiled into a
paragraph break, so rebuilt page 10 paints a blank line between "Hard break probe line" and
"second visual line" (line pitch 45 px against the source's 18 px). *Recommend: fix in the product —
emit `<a:br/>` for an in-block line break instead of starting a new `<a:p>`, and add a gate check that
compares paragraph counts and break counts, not just normalised text. This is the highest-value finding in
this review: it is the one visible defect on this revision that the text and structure readback calls
clean.*

1. **(src1, 30, `/slide[30]/shape[@id=100132]`, `[@id=100125]`, `[@id=22]`, `[@id=41]`) — MINOR** — the four
   cell pictures now paint the source's orange feature lines (confirmed: saturated cores `(197,87,0)`,
   `(199,87,4)`, `(198,86,3)`, `(197,88,3)` against the source's `(198,95,16)`), but 4–7 px lower and with
   visibly softer strokes than the source's crisp vector text, because the cells are painted as proxied
   pictures. *Recommend: retain as a minor finding; the previous MAJOR is fixed. If crisp text on this page
   matters, the proxied text cells are the place to start.*
2. **(src1, 2, the header row — `/slide[2]/shape[@id=11]`, `[@id=14]`, `[@id=10]`, `[@id=9]`) — MINOR** —
   the header row is aligned to columns that are 51–56 px left of the source's, and the words are ~15 %
   narrower in the rebuilt render at the same nominal 14.95 pt size, so "Year" sits against "FS/Split AC"
   where the source has a gap. *Recommend: retain; check the text-fit path for this object class.*
3. **(src1, 5, `/slide[5]/shape[@id=100085]`) — MINOR** — the pink band's five text lines start 10–11 px
   further right than the source and render slightly heavier. This is the whole of the "Condor needs" risk:
   no character is lost, no line is added or merged, and the band is intact and unclipped.
   *Recommend: retain as a minor finding; not a product defect on its own.*
4. **(src1, 12, the lower panels — `/slide[12]/shape[@id=100096]` … `[@id=100114]`) — MINOR** — everything
   below the masthead sits ~12 px lower than the source, so the second, fourth and "Next discussion"
   panels are not at the source's y. Content, breaks and numbering all match. *Recommend: retain.*
5. **(src1, 30, the right-hand column — `/slide[30]/shape[@id=48]`, `[@id=55]` and the column's text) —
   MINOR** — "PREMIUM S7 GCC MODEL / R32 | Inverter| HP" moves ~10 px down and ~17 px right, and the
   "NEW T-MAX" block and "X-Smart R32 Inverter" cell shift similarly. All text is present in the source's
   line breaks. *Recommend: retain.*
6. **(src2, 3, `/slide[3]/shape[@id=100150]` title and `[@id=100151]` subtitle) — MINOR** — the title sits 13 px higher and
   the subtitle 4 px lower, so the title-to-subtitle gap grows from 9 px to 27 px. *Recommend: retain.*
7. **(src2, 9, `/slide[9]/table[@id=100362]`) — MINOR** — the two "Dimension (W×D×H mm)" labels occupy one
   line in the rebuild and two in the source, inside identical row heights. *Recommend: keep the existing
   `table_cell_whitespace_placement` retained finding.*
8. **(src3, 21, `/slide[21]/shape[@id=100384]`, `[@id=100385]`, `[@id=100386]`) — MINOR** — the frames still
   declare the `roundRect` default adjustment, so their corners are rounder than the source's.
   *Recommend: retain, and check whether the default adjustment leaks into other rounded shapes.*
9. **(src5, 1, `/slide[1]/shape[@id=100000]`, `[@id=100001]`, `[@id=100002]`, `[@id=100011]`) — MINOR** —
   every text block starts 7–10 px further left and 10–18 px lower than the source, because the source's
   internal left inset is not carried. *Recommend: retain; likely systemic, worth one check across pages.*

## Summary

**MAJOR 1 / MINOR 9 / pages reviewed 10/10** (20 images read; the MAJOR is counted once for the p10 hard
break).

Pages judged visually clean: **p09 (src4 p1)** with only sub-pixel text offsets, and — no content
difference at all — **p03 (src1 p12)**, **p05 (src2 p3)**, **p06 (src2 p9)**, **p07 (src3 p2)** and
**p08 (src3 p21)**, each carrying one small metric offset. **p01 (src1 p2)** and **p02 (src1 p5)** carry one
offset each and no product defect. **p04 (src1 p30)** is visually correct now but carries the softened
proxy text and the right-column reflow. **p10 (src5 p1)** carries the one MAJOR.

Relative to the second review: **both of its MAJOR findings are fixed and independently confirmed** — the
page-number wrap (ink boxes now identical to the source at three thresholds on both pages) and the four
black cell pictures (the source's orange is present at all four). Three of its minor findings no longer
reproduce or are now smaller (the p04 ">" chevron no longer overlaps "9.50"; the p04 separator columns
line up; the p03 lower panels differ only by a uniform shift). One finding it did not carry — the hard
break — is the only MAJOR on this revision.

The single thing I would fix first is **A**: it is a blank line a reader sees on a page the machine gate
calls `rebuilt_issue_count = 0` with a passing text *and* structure readback, and the mechanism is visible
in the artefacts (the Canonical Author HTML declares `<br>`; the compiled slide declares a second `<a:p>`).
