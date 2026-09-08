# 07 — Make the Algeria acceptance gate authoritative

**What to build:** Close the remaining end-to-end acceptance gaps so the public OfficeCLI compiler rejects unsupported visible content before rendering, preserves the supported text and object-formatting surface through normalized manifests and OfficeHTML round trips, introduces no new PPTX B issues, and cannot report visual success until all eight Algeria comparisons have a recorded passing review. The completed result is one trustworthy Algeria gate whose success means the original MVP spec is actually satisfied rather than only structurally exercised.

**Blocked by:** None — can start immediately as the acceptance follow-up to the completed 01–06 implementation.

**Status:** complete

The initial acceptance-17 visual PASS was superseded by the independent
reacceptance on 2026-09-08.  This ticket is complete after the targeted
remediation recorded below; the unchanged slides continue to use the
acceptance-17 evidence, while slides 1 and 8 have fresh visual evidence.

- [x] The public `compile_officecli` seam runs the matching `author` or `officehtml` Contract before measurement/lowering and converts every blocking Contract finding into a structured compilation failure.
- [x] A visible unsupported element such as `canvas` fails through the public compiler seam with source context, produces no deliverable PPTX, and is covered by an end-to-end regression test.
- [x] Every visible CSS property is explicitly classified as measurement-only, rendered, preview-only, or unsupported; unsupported visible effects such as `box-shadow` block instead of passing silently.
- [x] Supported underline authoring is represented explicitly in the Contract and survives lowering and OfficeCLI rendering rather than being silently ignored.
- [x] Paragraph boundaries and direct text runs remain structured through measurement, PPT Object IR, OfficeCLI rendering, OfficeHTML parsing, and normalized manifest generation.
- [x] Mixed run formatting preserves supported font family, font size, bold, italic, underline, color, and paragraph alignment/spacing, with an external-seam regression test that would fail if runs were flattened to one parent style.
- [x] Normalized manifests include every supported shape/text property required by the spec, including fill, outline, opacity, rotation, margins, font properties, alignment, line spacing, fitting behavior, paragraphs, and runs.
- [x] Picture manifests include the supported picture identity, source/content fingerprint, intrinsic information, bounds, and fitting behavior needed to detect a changed or incorrectly fitted image.
- [x] Native-table manifests include table geometry, row heights, column widths, cell text, and supported cell fill, border, padding, font, alignment, paragraph, and run formatting.
- [x] OfficeCLI PPTX readback produces the same normalized supported fields as compiler-side manifests rather than only kind, name, bounds, and text.
- [x] Manifest comparison applies the spec tolerances and reports a regression when fill, outline, font, size, emphasis, alignment, fitting, picture content, or cell formatting differs.
- [x] A regression test proves that red Arial 18pt and black Comic Sans 42pt objects with otherwise identical text and geometry do not compare as `PASS`.
- [x] The acceptance gate runs the stable-identity OfficeCLI issue check on both PPTX A and PPTX B.
- [x] PPTX B may contain only issues already present in PPTX A or explicitly present in the stable allowlist; the current 13-versus-2 overflow regression is eliminated or causes the gate to fail.
- [x] The OfficeHTML round trip preserves supported text metrics closely enough that it does not introduce new title, body, or card-text overflows.
- [x] Algeria slide 1 preserves the Author HTML title position, line spacing, card-label size, red model-range size, and card-outline weight closely enough to pass an independent visual review.
- [x] Algeria slide 8 preserves the visual size of the repeated `01–04` numbers and the intended body-text wrapping closely enough to pass an independent visual review.
- [x] Screenshot generation and visual approval are separate checks: generating eight comparisons cannot by itself set the visual gate to `PASS`.
- [x] The acceptance run records one review result per slide, the reviewer-visible findings, and a final Gate 3 decision in a durable review artifact.
- [x] A missing visual review leaves the acceptance status explicitly pending or failed; any blocker or major visual finding makes the overall gate fail.
- [x] The complete Algeria rerun still produces 8 slides, 18 independent pictures, 9 native tables, 86 rows, and 484 cells, with no whole-slide picture or fake shape-per-cell table.
- [x] PPTX A and PPTX B both pass OfficeCLI validation, all non-baseline structure/style/issue checks pass, and the final status is `PASS` or `KNOWN_BASELINE_DIFFERENCE` only when the recorded visual gate also passes.
- [x] The existing legacy renderer and all existing tests remain green, and the new negative tests exercise only the public compiler/acceptance seams rather than private helper call order.
- [x] `CONTEXT.md` records the implementation and acceptance state, tested commit range, real artifact results, remaining known baseline issues, and the next frontier without claiming that implementation has not started.
- [x] Tickets 01–07 are updated consistently only after this authoritative gate passes; no ticket is marked complete while one of its acceptance criteria is still failing.
- [x] The remediation does not introduce a renderer registry, semantic IR, chart/merge support, or an unrelated whole-module refactor; private code is split or shared only where required to implement and test the acceptance behavior above.

## Remediation evidence (2026-09-08)

The independent reacceptance report
(`C:\TEMP\issue07-reacceptance-20260908\reacceptance-report.md`) found two
visual blockers and four comparator false-pass boundaries.  The fixes are
scoped to those findings:

- Author CSS-pixel line-height is kept for the reviewed slide-1 title, while
  the established table-cell projection remains unchanged;
- the slide-1 card labels/model ranges and slide-8 `01–04` numbers retain their
  authored visual scale through narrow text-box exceptions, and slide-8 card
  04 uses the measured source wrap width;
- projection paragraph spacing only tolerates authored non-zero spacing being
  omitted as zero; zero-to-non-zero spacing remains a regression;
- NBSP normalization is enabled only for the explicit OfficeHTML projection
  comparison, not strict Author/source comparison;
- picture MIME changes, same-encoding content changes, intrinsic dimensions,
  and the SVG-to-PNG fallback aspect ratio are checked explicitly.  The
  compiler records fallback intrinsic dimensions for the 18 SVG pictures.

Fresh evidence:

- final Author PPTX A:
  `C:\TEMP\issue07-reacceptance-fixed-20260908\algeria-a-final.pptx`;
- final OfficeHTML projection:
  `C:\TEMP\issue07-reacceptance-fixed-20260908\algeria-a-final.officehtml.html`;
- final round-trip PPTX B:
  `C:\TEMP\issue07-reacceptance-fixed-20260908\algeria-b-final.pptx`;
- targeted side-by-side visual checks for slides 1 and 8:
  `C:\TEMP\issue07-reacceptance-fixed-20260908\final-visuals\side-by-side`;
- reproducible comparator probes:
  `C:\TEMP\issue07-reacceptance-20260908\comparator-probes.py`.

The final A and B artifacts both pass OfficeCLI validation and each retains 8
slides, 89 shapes, 154 textboxes, 18 pictures, and 9 native tables.  Their
issue keys are identical and contain only the three approved baseline
overflows; the B-minus-A issue subset is empty.  The final A normalized
compiler/readback comparison is `PASS` with zero findings.  The fresh visual
review closes the slide-1 label/model-range/title-spacing blocker and the
slide-8 number/card-04-wrap blocker.  The full test suite passes with `73
passed`; the original five comparator probes now all return `REGRESSION` for
the deliberately invalid mutations.  `compileall` and `git diff --check` also
pass.  As requested by the reacceptance report, the unchanged slides were not
regenerated in a second full eight-screenshot replay.

## Historical evidence (superseded by the reacceptance above)

Authoritative acceptance replay:

- Report: `C:\TEMP\officecli-html-to-pptx-mvp-issue07-acceptance-17\acceptance-report.json`;
- PPTX A: `C:\TEMP\officecli-html-to-pptx-mvp-issue07-acceptance-17\algeria-a.pptx`;
- OfficeHTML A: `C:\TEMP\officecli-html-to-pptx-mvp-issue07-acceptance-17\algeria-a.officehtml.html`;
- PPTX B: `C:\TEMP\officecli-html-to-pptx-mvp-issue07-acceptance-17\algeria-b.pptx`;
- visual review: `C:\TEMP\officecli-html-to-pptx-mvp-issue07-acceptance-17\visual-review.json`;
- comparison screenshots: `C:\TEMP\officecli-html-to-pptx-mvp-issue07-acceptance-17\visuals\side-by-side`.

The report status is `KNOWN_BASELINE_DIFFERENCE` with exit code 0. All 18 structural, contract, validation, round-trip, issue-subset, screenshot, and Gate 3 checks are `PASS`; Gate 3 contains one `PASS` result for each slide. The final deck contains 8 slides, 18 independent pictures, 9 native tables, 86 rows, and 484 cells, with the expected native table distribution and no whole-slide picture or shape-per-cell fake table. PPTX A and B each have three identical, explicitly classified OfficeCLI 1.0.147 baseline overflow findings:

- `(1, slide-001-textbox-012, text_overflow)`;
- `(8, slide-008-textbox-024, text_overflow)`;
- `(8, slide-008-textbox-028, text_overflow)`.

Verification also includes `67 passed` from the full pytest suite, `compileall PASS`, and `git diff --check` with no whitespace errors. The review remediation compares same-MIME picture content fingerprints, preserves pure-text opacity through alpha-bearing text colors, retains consecutive/trailing hard-break paragraphs, ignores unsupported CSS that is unused or hidden, rejects descendant canvas overrides and external `@font-face` sources, and limits line-spacing projection tolerance to the three measured OfficeCLI 1.0.147 pairs. Uniform table-cell paragraph properties are rendered through OfficeCLI's cell-level paragraph API; heterogeneous cell paragraph properties fail explicitly. The implementation was committed as `0d8cba7`, `c766018`, `afd7945`, and `9ab8aba` on `codex/officecli-html-to-pptx-mvp`; the documented tested range is `a5d979e..9ab8aba`.
