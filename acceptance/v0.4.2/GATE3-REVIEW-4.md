# Gate 3 — fourth independent visual acceptance review (v0.4.2 projection, re-verification after the line-spacing fix)

**Verdict: PASS_WITH_FINDINGS — MAJOR 0 / MINOR 9 / pages reviewed 10/10.**

**The review-3 MAJOR is closed.** The hard-break block on rebuilt page 10 no longer paints a blank line:
the two lines are adjacent again at a 25 px pitch where review-3 measured 45 px and the source has 18 px,
and the first line now lands 1 px from the source's row (was 18 px). What remains is a metric residue —
the second line still sits 8 px low — which I class MINOR, not MAJOR.

**There is no regression.** Nineteen of the twenty renders in the regenerated bundle are byte-identical
(SHA-256) to the ones I reviewed in review-3, including all ten source renders and nine of the ten rebuilt
renders; only `p10-after.png` changed. So no page other than p10 can have changed visually, and the eight
MINOR findings I had on those pages reproduce to the pixel. This review also **withdraws one of my own
review-3 findings as a measurement error**: p03 has no positional difference at all.

I did not write this code. Method for this round, in order: hash every render in the regenerated bundle
against my review-3 record; re-read the changed pair in full and re-read p04 in full as a spot check;
re-measure every region of all ten pages numerically (ink-band positions, cross-correlation best-fit
offsets, orange-pixel censuses, corner profiles); then read the rebuilt and source XML and the page
records. Where the compiler's claim was about mechanism — that a pixel line height was being divided by the
wrong font size — I checked the produced XML rather than the claim.

---

## 1. The p10 hard break, re-verified

### 1.1 What the renders paint

Ink bands of the left-hand text column (window x 40–560), source against the two rebuilt revisions:

| element | source (p10-before) | rebuild, review-3 | rebuild, now | Δ now | Δ at review-3 |
|---|---|---|---|---|---|
| title "Mixed Latin 中文 run · 2026 · …" | y 47–69 | y 42–64 | y 42–64 | −5 | −5 |
| **"Hard break probe line"** | y 79–92 | y 97–110 | **y 80–93** | **+1** | +18 |
| **"second visual line"** | y 97–107 | y 142–152 | **y 105–115** | **+8** | +45 |
| bullet 1 "Level zero bullet item" | y 221–231 | y 231–241 | y 231–241 | +10 | +10 |
| bullet 2 "Second bullet item" | y 239–249 | y 248–258 | y 248–258 | +9 | +9 |
| "1. Numbered item one" | y 256–266 | y 266–276 | y 266–276 | +10 | +10 |
| "2. Numbered item two" | y 274–284 | y 284–294 | y 284–294 | +10 | +10 |
| "Theme resolved body 主题" | y 406–421 | — | y 401–416 | −5 | — |
| "Ungrouped sibling text" | y 568–581 | — | y 563–576 | −5 | — |

**Line pitch of the broken block: source 18 px → review-3 45 px → now 25 px.** The extra line the page had
gained is gone. At 3× zoom the two underlined lines read as two consecutive lines of one block with
slightly loose leading, not as a line separated by a blank line. **MAJOR closed.**

### 1.2 Why a residual remains — what the XML actually declares

| | source `rich-text-block` | rebuilt `slide-010-textbox-001` |
|---|---|---|
| paragraph 0 (title runs) | `lnSpc 140000` | `lnSpc 140000` |
| paragraph 1 | **no `lnSpc`; 1 `<a:br/>`**; runs 22 px; texts `['H','ard break probe line','second visual line']` | `lnSpc 140000`; **0 breaks**; texts `['H','ard break probe line']` |
| paragraph 2 | — | `lnSpc 140000`; **0 breaks**; texts `['second visual line']` |

The fix did what was described: the paragraph that carried the wrong `lnSpc 254500` now carries
`140000`, matching its own element's ratio, and the two fragments are spaced 25 px instead of 45 px.

The **structure still diverges**: the source has *one* paragraph containing one hard break; the rebuilt
deck has *two* paragraphs and no break at all. The visible symptom is gone, the mechanism is not. Two
consequences worth carrying forward:

* The residual 7 px (25 px against the source's 18 px) is what is left of that divergence: an in-paragraph
  break costs nothing, a paragraph break costs a line box. It will vary with each block's own line-height
  ratio, so the next hard break in another shape may land closer or further off. **Finding 8.**
* The gate still cannot see it: the p10 page record is unchanged (`rebuilt_issues = 0`, 8/8 text records
  `matched: true`, `style_matched: true`, `structure_lost: false`) and `expected_structure_text` still
  equals `rebuilt_structure_text`. Emitting `<a:br/>` rather than a new `<a:p>`, plus a paragraph/break
  count check, would close both the residue and the blind spot.

---

## 2. Regression scan, all ten pages

### 2.1 The nine pages the change did not touch

Every render in the regenerated bundle, SHA-256 prefix, against my review-3 record:

| page | `pNN-after.png` | vs review-3 | `pNN-before.png` | vs review-3 |
|---|---|---|---|---|
| p01 | `0b9bd31252f97616` | identical | `4a329ac5f0b79500` | identical |
| p02 | `c1c454ba5410d1fb` | identical | `98361f170633da7d` | identical |
| p03 | `a17e1574a3cc5683` | identical | `bb323b342fbaa4ab` | identical |
| p04 | `942b5cedea7e861b` | identical | `b2b1ec01af1bbca3` | identical |
| p05 | `b709b907680396f1` | identical | `a904e7602b76046a` | identical |
| p06 | `cdb29252d3e7326d` | identical | `55dc35aab7e09e6a` | identical |
| p07 | `45b452201bbdd85c` | identical | `5c0a22f726fb8fd9` | identical |
| p08 | `5846a44b0785a938` | identical | `e87330ebc36be1e0` | identical |
| p09 | `bb213075e45216ef` | identical | `e984b31a1ca9573e` | identical |
| **p10** | **`996d6b33b95fb708`** | **changed** (was `10df6d6033dac123`) | `8c73de73a38e2498` | identical |

Because the comparison pairs for p01–p09 are the same bytes I judged in review-3, "got worse" is
impossible on those pages; I re-ran the measurements anyway and they reproduce review-3 exactly:
p01 header-row word columns `[(169,209),(288,391),(538,744),(905,954)]` → `[(113,292),(512,717),(822,870)]`;
p02 band line left edges source 60/60/60/59 against rebuilt 70/71/71/70; p03 masthead ink y 67–90 against
67–89; p04 orange cores 839/635/981/475 against the source's 1420/1130/1473/763; p05 title/subtitle
91–115 + 124–135 against 77–101 + 128–139; p06 label column source two bands (234–242, 248–257) against
one (241–249); p07/p08 page numbers 12×9 px and 11×9 px at identical coordinates in both renders;
p08 outer frame top edge at y=187 spanning x 64–411 against x 111–365.

### 2.2 p10 — the page that changed

* Total differing pixels against the source: **22 377 → 22 394 (+0.08 %)**.
* The eleven largest difference blocks are **identical in count and coordinates** in both revisions —
  the clipped-overflow text (760 / 698 / 571) and the bullet list (667 / 658 / 644 / 632 / 598 / 562 /
  559 / 536). Nothing outside the probe block moved.
* The only region that changed is the probe block, and it changed towards the source (18 px error → 1 px,
  45 px → 8 px).
* The right-hand shapes are untouched: the blue rectangle y 53–132, the orange bar y 193–232, the crimson
  rectangle and diagonal line y 333–392 / 412–473, the ellipse and the grey rounded rectangle all at the
  same coordinates as the source.

### 2.3 The nine MINOR findings, each re-classified

| # | finding (review-3) | now |
|---|---|---|
| 1 | (src1, 30, `[@id=100132]`, `[@id=100125]`, `[@id=22]`, `[@id=41]`) proxied text: orange present but 4–7 px low and softer than the source's vector text | **unchanged** — cores `(197,87,0)`/`(199,87,4)`/`(198,86,3)`/`(197,88,3)` |
| 2 | (src1, 2, header row) 51–56 px left of the source | **unchanged** |
| 3 | (src1, 5, `[@id=100085]`) band text 10–11 px right | **unchanged** |
| 4 | (src1, 12, lower panels) ~12 px low | **WITHDRAWN — my error**, see §3 |
| 5 | (src1, 30, right column) `PREMIUM S7` ~10 px low, ~17 px right | **unchanged** — y 428–436/441–453/469–477/484–494 → 431–440/445–457/475–485/491–503 |
| 6 | (src2, 3, `[@id=100150]`, `[@id=100151]`) title/subtitle gap 9 → 27 px | **unchanged** |
| 7 | (src2, 9, `table[@id=100362]`) Dimension labels one line against the source's two | **unchanged** |
| 8 | (src3, 21, `[@id=100384]`, `[@id=100385]`, `[@id=100386]`) `roundRect` default adjustment | **unchanged** |
| 9 | (src5, 1, `[@id=100000]`, `[@id=100001]`, `[@id=100002]`, `[@id=100011]`) block 7–10 px left, 10–18 px low | **BETTER** — probe lines +18/+45 → +1/+8 px; title −5, bullets +10, x −7…−10 unchanged |

Nothing got worse. One finding improved; one of my own is withdrawn; one new MINOR appears below.

---

## 3. Correction to review-3: the p03 finding does not hold

Review-3 Finding 4 said that on p03 everything below the masthead sits ~12 px lower than the source. That
was a misreading on my part, not a change in the bundle — the p03 renders are byte-identical to the ones I
judged, so the page is exactly as it was and my measurement then was simply wrong. Measured directly now:

| p03 region | source | rebuilt | Δ |
|---|---|---|---|
| masthead "CONDOR FS PROJECT DISCUSSION" | y 67–90, x 30–581 | y 67–89, x 30–581 | 0 |
| panel-1 header "1 Key Meeting Takeaways" | y 115–148, x 32–300 | y 115–148, x 32–300 | 0 |
| panel-1 body (takeaways 1./2./3., five bands) | y 170–186 … 305–322 | identical rows and columns | 0 |
| panel-2 red table header bar | y 160–187 | y 160–187 | 0 |
| table body rows | y 200–289 | y 200–289 | 0 |
| "Priority recommendation" strip | y 320–364 | y 320–364 | 0 |
| panel-4 header "4 TCL Customized Solution Proposal" | y 424–457, x 637–1003 | y 424–457, x 637–1003 | 0 |
| "Next discussion needed" block | y 590–679 | y 590–679 | 0 |

A cross-correlation best-fit over each region returns (0, 0) for the panel bodies, the priority strip and
the table, and an A/B stack of the whole lower half at 2× shows the two panes superimposed. The 30 990
differing pixels on this page are sub-pixel glyph antialiasing spread over a text-dense page, plus the
rounded panels' corner rendering — not position. **p03 joins p09 as a page with no positional difference
at all.**

---

## 4. Findings (current)

Every entry gives `(slot, source page, source object path)`, its class, one line, and the disposition I
recommend. "Rebuilt page" is the projection's output order. **MAJOR: none.**

1. **(src1, 30, `[@id=100132]`, `[@id=100125]`, `[@id=22]`, `[@id=41]`) — MINOR** — the four cell pictures
   paint the source's orange feature lines (`(198,95,16)` present in the proxies and in the render) but
   4–7 px lower and with softer strokes than the source's crisp vector text. *Unchanged. Recommend:
   retain.*
2. **(src1, 2, header row — `[@id=11]`, `[@id=14]`, `[@id=10]`, `[@id=9]`) — MINOR** — the header row is
   51–56 px left of the source's columns. *Unchanged. Recommend: retain.*
3. **(src1, 5, `[@id=100085]`) — MINOR** — the pink band's five lines start 10–11 px right of the source's
   and render slightly heavier; no character is lost and no line is added or merged. *Unchanged.
   Recommend: retain.*
4. **(src1, 30, right column — `[@id=48]`, `[@id=55]` and the column's text) — MINOR** — "PREMIUM S7 GCC
   MODEL / R32 | Inverter| HP" and the "NEW T-MAX" block sit 3–10 px lower and ~17 px right; all text
   present in the source's line breaks. *Unchanged. Recommend: retain.*
5. **(src2, 3, `[@id=100150]` title, `[@id=100151]` subtitle) — MINOR** — title 14 px higher, subtitle
   4 px lower, so the gap grows from 9 px to 27 px. *Unchanged. Recommend: retain.*
6. **(src2, 9, `table[@id=100362]`) — MINOR** — the two "Dimension (W×D×H mm)" labels occupy one line
   against the source's two, inside identical row heights. *Unchanged; matches the gate's own
   `table_cell_whitespace_placement` retained finding. Recommend: retain.*
7. **(src3, 21, `[@id=100384]`, `[@id=100385]`, `[@id=100386]`) — MINOR** — the frames still declare the
   `roundRect` default adjustment, so their corners are rounder than the source's. *Unchanged.
   Recommend: retain.*
8. **(src5, 1, `[@id=100000]` — rebuilt `slide-010-textbox-001`) — MINOR** — the hard break now compiles
   to a correctly spaced paragraph break, so the visible blank line is gone; what remains is structural
   plus 7 px of extra leading: the source is one paragraph with one `<a:br/>` and an 18 px pitch, the
   rebuilt deck is two paragraphs with no `<a:br/>` and a 25 px pitch, and the second line still sits 8 px
   low. The block also sits 7–10 px left and the bullet list 10 px low (unchanged by this fix).
   *Recommend: the visible defect is closed, so this is no longer a blocker — but emit `<a:br/>` inside
   the paragraph to remove the residue and the per-block variability, and add a paragraph/break count
   check to the gate, which still reports `structure_lost: false` for this object.*
9. **(src5, 1, `[@id=100003]`) — MINOR, newly recorded** — the clipped-overflow text is painted 14 px
   higher than the source (source ink y 157–217, rebuilt y 143–201) with the same x extent and the same
   clip point at x 929; it is a proxied picture, so this fix could not have caused it (its difference
   blocks are identical to review-3's counts). I missed it in review-3 and record it now.
   *Recommend: retain as a minor placement difference.*

Also still open, unchanged and without visual consequence: the three src1 page-2 tables are listed
`canonical-editable` with emitted names, but built `slide1.xml` contains no table at all — their cells are
empty in the source, so no grid paints either way.

---

## 5. Machine-claim cross-check (this revision)

The gate report is unchanged from review-3: `accepted: true`, `material_deltas: 0`, `rebuilt_issues: 3`
(all three text-overflow conditions p03 already carries), `proxy_proofs_failed: 0`,
`blocking_diagnostics: 0`; all ten page records identical to review-3 in `rebuilt_issue_count`,
`material_deltas`, `retained_findings`, `proxies`, `text_readback` and `failures`; all 152 text records
still `matched: true`, `style_matched: true`, `structure_lost: false`,
`whitespace_only_difference: false`.

The p10 object therefore still reports a clean structure readback while the produced deck declares two
paragraphs where the source declares one — the readback compares normalised text, so a hard break turning
into a paragraph break is invisible to it, and it would have reported the same "clean" verdict for the
45 px version. The fix was found by a human-visible measurement, not by the gate; a paragraph-count and
break-count check on both sides would make this class of defect machine-detectable.

---

## Summary

**MAJOR 0 / MINOR 9 / pages reviewed 10/10.** The review-3 MAJOR is **closed**: rebuilt page 10 no longer
paints a blank line (pitch 45 px → 25 px against the source's 18 px, first line 18 px → 1 px from the
source's row). The fix introduced **no regression**: nineteen of the twenty renders are byte-identical to
the revision I reviewed, only p10 changed, its total difference against the source moved by +17 pixels out
of 22 377, and its eleven largest difference blocks are unchanged in count and position.

Relative to review-3: one finding improved (the p10 block), one of my own findings is withdrawn (the p03
shift was my measurement error — p03 has no positional difference), one is newly recorded (the
clipped-overflow picture on p10 paints 14 px high), and the other eight reproduce unchanged. No page is
missing text, no page paints content it should not, and no page is blocked.

The one thing I would still fix in the product is the mechanism behind finding 8 — emitting `<a:br/>`
instead of a new paragraph — because the residue it leaves (7 px here) depends on each block's line-height
ratio and the gate cannot see the difference either way.
