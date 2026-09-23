# officecli-html-to-pptx 0.6.2

Product 0.6.2 adds a source-patched Visual Inspector to the installed Author
Workbench. It retains Author Contract 1.3, OfficeCLI `>=1.0.151`, the ordinary
compiler/build pipeline, and the existing Artifact Pair, Evidence, Gate 3, and
Finalization authorities.

## Public support

- Product version: `0.6.2`.
- Author Contract: `1.3` (unchanged).
- Minimum OfficeCLI: `1.0.151` (unchanged).
- Public commands: `capabilities`, `doctor`, `check`, `build`, `finalize`, and
  `workbench`.
- Workbench edits the one saved UTF-8 Author HTML document. Preview and
  Inspector state are derived, non-authoritative products.
- Text Inspector edits one unambiguous simple leaf/run and the supported
  Contract 1.3 text fields. Mixed runs and complex parents stay read-only.
- Shape Inspector edits the closed geometry-token set, solid fill, border,
  opacity, and one simple text leaf when each source mapping is reliable.
- Picture Inspector accepts supported `data:image` replacement files up to
  10 MiB of decoded image bytes and the `fill`, `contain`, and `cover` fit
  values.
- Table Inspector edits text and solid fill on a merged region's anchor cell.
  Covered coordinates select that anchor only when ownership is unambiguous;
  otherwise they are read-only.
- Chart Inspector edits the unique inert `data-pptx-chart-spec`. It supports
  `column`, `bar`, and `line` with one to three series, and `pie` and
  `doughnut` with one series. Its Preview is a semantic projection from that
  same spec, not a claim of PowerPoint pixel parity.
- Computed values are shown beside source/origin. Inline edits of class-derived
  fields are labelled as local overrides; shared class rules are not changed.
- Every Draft mutation compares both monotonic `draft_revision` and Draft
  SHA-256. Preview selections also compare `preview_revision`. Save stays
  explicit and Build Revision still requires exact-saved-SHA Contract PASS.

The Inspector does not add mixed-run replacement, table/chart structure
changes, shared class editing, existing-PPTX editing, arbitrary CSS/JSON
editing, canvas gestures, or whole-slide raster fallback.

## Installed acceptance

The tracked public corpus is
`tests/fixtures/v06_02_inspector_corpus.html`. Acceptance starts from a fresh
wheel install and the public `workbench` command, then records exact source
diffs, explicit Save, exact-SHA Check, ordinary Build Revision, independent
native readback, `validate`/`issues`, the Artifact Pair, each comparison image,
per-slide Gate 3 findings, and Finalization. The reproducible commands and
review notes are in
`tests/fixtures/v06_02_inspector_corpus.acceptance.md`; the 0.6.1 full-suite
failure/error identity baseline is frozen in
`tests/fixtures/v06_01_full_suite_baseline.json`.

The final full test suite is run once at the release integration boundary and
compared by failing/error test identity and cause with that baseline. Counts
alone do not waive new failures or errors. Historical 0.6.1 failures are not
silently repaired by changing assertions, Contract semantics, or the
OfficeCLI compatibility floor.
