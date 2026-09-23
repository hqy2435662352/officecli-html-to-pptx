---
status: accepted
---

# Add source-patched Visual Inspector in Product 0.6.2

Product 0.6.2 adds bounded object-property editing to the source-authoritative
Workbench, while keeping the saved Author HTML and the existing compiler as
the only authoring and build authorities.

## Decision

- Retain Author Contract 1.3 and the existing OfficeCLI `>=1.0.151` floor.
- Build Inspector operations on the Workbench session and in-memory Draft.
  Preview markers, computed styles, source maps, selection state, and chart
  projection DOM remain derived and never enter saved Author HTML or compiler
  input.
- Offer edits only for reliable source mappings: one simple text leaf/run,
  supported Shape fields, bounded data-image Picture replacement, a merged
  Table anchor cell, or the unique inert ChartSpec for a native chart.
- Preserve a visible distinction between computed value and source/origin.
  Editing a class-derived value writes an inline object-local override and
  reports that scope; the shared class rule remains unchanged.
- Make unsafe, ambiguous, unsupported, or covered-cell content read-only.
  Never expand property controls from a browser `rendered` classification
  alone.
- Use the sole ChartSpec as the chart semantic source. Preview may use a
  canonical semantic projection, but it must expose the current chart type,
  categories, series, values, and supported presentation fields and make no
  pixel-equivalence claim.
- Require compare-and-swap of both monotonic Draft revision and Draft SHA for
  every mutation. Selection edits also require the current Preview revision.
  Preserve explicit Save, exact-saved-SHA Contract PASS, ordinary Build
  Revision, independent readback, Evidence, Gate 3, and Finalization.
- Keep the released Python API as the existing compiler API. The Inspector
  capability summary is published under the existing `capabilities` command;
  there is no public patch JSON protocol or second editor model.

## Consequences

Simple repairs no longer require locating HTML/CSS/ChartSpec tokens by hand.
Editors remain source-first and auditable. Complex rich text, shared class
rules, structural table/chart edits, arbitrary CSS/JSON, and existing-PPTX
editing remain source-editing or later-version work. A semantic chart Preview
can differ visually from PowerPoint rendering; Gate 3 reviews actual
comparisons and records real findings without rewriting build status.
