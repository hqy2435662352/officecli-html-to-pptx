# Gate 3 — independent primary-agent visual review (V0.4.2 acceptance)

Status: **COMPLETE — PASS_WITH_FINDINGS.**
Reviewer: primary agent (not the implementing subagents).
Evidence bundle: `acceptance/v0.4.2/`, regenerated from the final code.

The machine gate returned `PASS_WITH_FINDINGS` with 0 material deltas and 0
blocking diagnostics, which on its own is not acceptance. This review is the
independent gate the spec requires, and it is the reason the bundle published
earlier could not be accepted.

## Method

Every page was read as a before/after pair rendered at the same size by the same
OfficeCLI screenshot pipeline, with zoomed crops and pixel-level measurements of
any suspicious region. A page fails when content visible in the source is absent,
duplicated, clipped or misplaced in the rebuilt page, and also when text is
corrupted even though every character is still present somewhere.

## Defects found by this review, and their resolution

The machine gate and an adversarial verification pass both accepted a bundle in
which all seven of these were live. Each is now fixed except where noted.

| # | Page | Defect | Resolution |
|---|---|---|---|
| F1 | 1 | All three `rightArrow` shapes invisible: a `line` colour declared with no `lineWidth` stroked at zero width | Fixed — `_stroke_width_pt` + `DEFAULT_LINE_WIDTH_PT`; rebuilt arrows read back `line=#C00000 lineWidth=1pt` |
| F2 | 1, 3 | Text proxies painted a property value instead of the text — the page-1 subtitle painted the literal word `rect`, the page-3 title painted `none` | Fixed — `_rebuild_properties` renamed its shadowing loop variable to `value_text`; same shadowing removed from `_member_properties` |
| F3 | 3 | A `wrap=False` title was reconstructed with wrapping on and cropped mid-word | Fixed — `wrap` added to `_TEXT_PROPERTIES` |
| F4 | 4 | Badges appeared to paint over the card headings | **Withdrawn** — the overlap was F2's placeholder text painting inside the badge rectangles. A pixel-level bar-map comparison of the regenerated renders shows badge and heading columns now match the source exactly |
| F5 | 8, 10 | Text proxies were cropped to the object's declared rectangle, and reconstructed at OfficeCLI's default size rather than the painted size, so overflowing text was sliced | Fixed — proxies cover the measured painted extent, and the reconstruction carries the painted size (`painted_text_size`), `lineSpacing`, `valign` and `autoFit`. Page 8's ten clipped blocks now render complete |
| F6 | 10 | List markers lost: four list paragraphs rebuilt as four plain lines | Fixed — a list object is emitted as one `<ul>` with one `<li>` per paragraph, `list-style-type` per item and the item's indent |
| F7 | 10 | A hard break merged into its paragraph: `Hard break probe linesecond visual line` | Fixed — the reader restores `<a:br/>` from the slide part, and paragraphs now join with `<br>` |

Two acceptance tests had encoded F6 and F7 as expected behaviour
(`test_the_probe_b_hard_break_is_emitted_and_the_rebuild_merges_it`,
`test_the_probe_b_list_declaration_is_present_in_the_source_and_absent_from_the_rebuilt_deck`).
Both were rewritten to assert the correct native structure. That corrects a
defect in the earlier tests; it does not bless a limit.

## Page-by-page result

| Page | Source page | Gate 3 | Notes |
|---|---|---|---|
| 1 | 2 | PASS | Arrows, subtitle and all text restored; three ellipses native; two groups one locked proxy each |
| 2 | 5 | PASS | Table, cards, flags and pictures faithful |
| 3 | 7 | PASS | Title restored on one line; 11x6 native table intact |
| 4 | 12 | PASS | Badges and headings correct; gradient fills carry locked proxies |
| 5 | 14 | PASS | All three native tables and the reading-guide band faithful |
| 6 | 19 | PASS | Proxies measured faithful to within 1.5pt against the source's own ink bands |
| 7 | 25 | PASS | Headline, three year-columns, arrows and product photos faithful |
| 8 | 30 | PASS | Every product block renders complete after F5 |
| 9 | probe A | PASS | Overlay wording present exactly once; ellipse and rightArrow native; no raster payload |
| 10 | probe B | PASS | Bullets, numbering, nesting and the hard break all native; overflow probe covered |

## Known findings — accepted, not defects

These are visible in the rebuilt pages and are reported as scope evidence by the
gate rather than repaired. They are not slide-owned projection loss.

- **Inherited master/layout paint is not reconstructed.** The `AIR CONDITIONER`
  band, the `COMFORT | RELIABILITY | INTELLIGENCE` strip, the TCL mark, the
  Olympic rings and the page numbers come from the master and layout and are
  absent from every rebuilt page. The spec places master/layout/theme
  reconstruction explicitly out of scope; the omission is recorded per page as
  `slide_field_not_evaluated` scope evidence and as `inherited_paint_omission`.
- **Source-inherent overflow is retained.** 29 `text_overflow` findings and 2
  `table_cell_whitespace_placement` findings exist in the source pages and are
  listed as retained findings. The rebuilt-minus-source material issue set is
  empty, so none of them is a regression and none is counted as repaired.
- **Up to ~10% residual on mixed-size heading lines.** A reconstruction carries
  one body-level size, so a body whose runs declare several sizes can render its
  heading line slightly smaller than the source. Measured at ≤10% on the affected
  page-8 headings, with the body's last line landing within 0.75pt of the
  source's. Exact per-run fidelity would need a per-paragraph reconstruction.
- **Run-level bold can be lost the same way.** Where runs disagree on bold, the
  reconstruction cannot carry one body-level value, so some heading lines render
  lighter than the source. Cosmetic.
- **Nested list items keep their indent but not their `lvl`.** The declared list
  surface is top-level only (`LIST_LEVELS = (0,)`), so a nested item is indented
  but not marked as a deeper level.

## Verdict

`PASS_WITH_FINDINGS`. Ten of ten pages projected, `unsupported=0`,
`unresolved=0`, zero material deltas, all proxy isolation proofs passed, the
unchanged `author` Contract passes, and no page carries a major projection
defect. The known findings above are scope evidence and residuals, all recorded
in the bundle rather than waived.

No waiver was widened and no tolerance was relaxed to reach this verdict: the
seven defects above were repaired, and two tests that had documented two of them
as expected behaviour were corrected.
