# officecli-html-to-pptx 0.5.2

V0.5.2 promotes explicitly authored native charts to the public Author
Compiler surface. The existing five-command workflow and non-overwriting
Artifact Pair remain unchanged while the Author Contract advances to 1.2.

## Runtime and public authority

- Product version: `0.5.2`.
- Author Contract: `1.2`.
- Minimum OfficeCLI: `1.0.151` (`>=1.0.151`).
- Public commands: `capabilities`, `doctor`, `check`, `build`, and `finalize`.
- The actual OfficeCLI runtime is recorded by `capabilities` attestation,
  `doctor`, `runtime.json`, and `native-evidence.json`.

The runtime floor is global and fixed. A lower runtime blocks before Chromium
measurement or output creation; Contract behavior is never branched by the
discovered runtime. The clean OfficeCLI `1.0.151` property-matrix probe is the
release gate for all five chart types and the closed presentation surface.

## Explicit native chart protocol

One chart is authored as one atomic container carrying `data-pptx-chart` and
exactly one inert `script type="application/json"` with
`data-pptx-chart-spec`. The JSON spec is the only source of chart type,
categories, series, values, and supported presentation semantics. The measured
outer container supplies geometry. A browser preview is optional, and the
entire descendant subtree is excluded from generic shape/text/picture/table
lowering. Nested chart containers, missing or multiple specs, hidden or
zero-sized containers, and invalid strict JSON are blocking diagnostics.

The five case-sensitive chart types are `column`, `bar`, `line`, `pie`, and
`doughnut`. Category charts accept 1–3 ordered series and 1–12 ordered
categories. Pie and doughnut charts accept one series, 2–6 ordered categories,
finite non-negative values, and a positive total. Category labels may repeat;
category order, series order, names, and values remain material. Series names
are unique after trimming. Values are finite JSON numbers and are never
coerced from strings, booleans, or nulls.

The public presentation surface is deliberately closed:

- optional plain non-empty title;
- legend `none`, `top`, `bottom`, `left`, or `right` (default `none`);
- labels `none`, `value`, or `percent` (default `none`), with `percent` only
  for pie and doughnut;
- optional plain category/value axis titles on column, bar, and line only;
- semantic value-axis number formats `general`, `integer`, `integer-group`,
  `decimal1`, `decimal1-group`, `percent0`, and `percent1`;
- optional six-digit `#RRGGBB` series colors, normalized to uppercase; an
  omitted color is authored `auto`, while Office-selected RGB remains
  informational; and
- one private canonical doughnut hole-size default of `50`.

Unknown fields are rejected recursively. Authored `holeSize`, arbitrary
Office/Excel format strings, advanced chart families, chart fallback, and a
chart-specific command are outside the release. OfficeCLI paths, command
syntax, canonical backend tokens, and format strings remain private to the
adapter behind the typed `ChartSpec`/`ChartReadback` seam.

## Evidence and verdicts

Every public build produces one matching PPTX and `.evidence/` directory. The
bundle contains the existing Contract, capability, runtime, manifest,
validation, issue, result, visual-review, and Comparison Image documents plus
independent chart-aware readback:

- `manifest.json` records each authored chart as one `kind: "chart"` object
  with normalized type, ordered categories, ordered series, values, bounds,
  presentation semantics, and source identity;
- `readback.json` independently reads the published PPTX and proves native
  chart kind, type, geometry, ordered data, colors, labels, titles, axes, and
  normalized number-format tokens;
- `native-evidence.json` records compiled/readback chart structures and counts,
  runtime attestation, validation/issues evidence, diagnostics, material delta,
  and Gate 3 state; and
- `visual-review.json` retains one Comparison Image review for every slide.

Chart count, native kind, chart family, geometry, category/series/value order,
explicit colors, and supported presentation differences are material. A
successful release gate requires authored/compiled/readback counts to agree,
OfficeCLI validation PASS, zero issues, `unsupported=0`, `unresolved=0`, and
`material_delta=0`. Gate 3 uses semantic visual review: charts must be
readable, unclipped, and faithful in family, data relationships, colors,
legends, labels, and titles; pixel equality for Office font metrics and chart
padding is not required. `PASS_WITH_FINDINGS` remains available only for
classified non-material findings. General localized fallback remains reserved
for V0.6.

## Public four-slide corpus

`tests/fixtures/v05_02_public_corpus.html` is the tracked Author corpus:

1. column and bar categorical comparisons with ordered multi-series data;
2. a multi-series line trend with axis titles and a semantic number format;
3. pie and doughnut part-to-whole charts with value/percent labels; and
4. an integrated business page combining Contract 1.2 text, a merged table, a
   native shape, and an explicit chart.

The corpus contains six authored charts and is expected to produce exactly six
compiled and six independently read-back native chart objects. The V0.5.1
four-slide corpus remains a regression fixture for text, merged tables, and
shape geometry; it does not contribute to the V0.5.2 chart gate.

The public acceptance sequence is:

```text
capabilities -> doctor -> check -> fresh build -> independent readback
  -> validate/issues -> semantic Gate 3 review of all four slides -> finalize
```

The release does not add a command, alter the existing V0.5.1 object behavior,
or claim PPTX-to-Author-HTML chart round trips or existing-PPTX chart editing.
