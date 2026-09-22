# Product 0.6.1 Workbench acceptance corpus

This tracked four-slide Candidate/Author corpus is the #44 integration fixture.
It is deliberately separate from the Product 0.5.3 public corpus, which remains
the regression gate for localized fallback semantics.

| Slide | Coverage |
| --- | --- |
| 1 | UTF-8 CJK text, inline CSS, and a deterministic `data:image` picture |
| 2 | Native text/table/shape objects and merged-cell topology |
| 3 | One atomic native chart with an inert `data-pptx-chart-spec`; the inline authoring-preview projector reads that same spec to draw the browser-side title, axes, labels, and bars |
| 4 | CJK text beside one explicit localized visual fallback |

The installed Workbench acceptance uses this source as the only draft/build
input. Preview markers, navigation scripts, diagnostics, and thumbnails are
ephemeral products and must not appear in the saved source or Artifact Pair. The
chart projector is visual-only: it never supplies compiler semantics, and the
isolated Workbench Preview regenerates its own ephemeral projection from the
same inert spec after stripping author scripts.
