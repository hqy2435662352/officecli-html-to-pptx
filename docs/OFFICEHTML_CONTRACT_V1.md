# Reversible OfficeHTML Contract v1

This document is the machine-backed contract for the OfficeCLI-first compiler
path in this repository. It is the capability source for the `author` and
`officehtml` profiles; the legacy `python-pptx` renderer has a separate input
contract and must not silently redefine this one.

| Field | Value |
|---|---|
| Contract version | `1.0` |
| OfficeCLI compatibility baseline | `1.0.147` |
| Public compiler seam | `compile_officecli(input_html, profile, output_pptx)` |
| Contract checker | `html-to-pptx-contract <html> --profile author\|officehtml` |
| Acceptance entry | `html-to-pptx-algeria-acceptance --input <author.html> --output-dir <empty-dir>` |

The executable constants are exported from `html_to_pptx.contract` as
`CONTRACT_VERSION` and `OFFICECLI_COMPATIBILITY_BASELINE`. An OfficeCLI upgrade
requires replaying the Algeria gate before changing this version.

## Stage ownership

The contract assigns each rule to the stage that owns it. A limitation at one
stage is not automatically a limitation at another stage.

### 1. Authoring Runtime

Author HTML is a human-reviewable workbench. It may contain an inline preview
controller, slide counter, thumbnails, navigation buttons, and similar
preview-only DOM. These nodes are ignored by compilation when they are outside
the slide or carry an explicit preview token such as `slide-counter`,
`thumbnails`, `toolbar`, `sidebar`, `controls`, or `preview-only`.

The runtime may change which slide is displayed, but must not rewrite visible
slide content, geometry, or image sources before measurement. External scripts,
stylesheets, and fonts are not deterministic compiler inputs.

### 2. Chromium Measurement

The `author` profile uses Chromium to resolve the final layout of
`.slide` elements. Each author slide is a `1920px × 1080px` CSS canvas. The
measurement stage owns Flexbox/Grid resolution, margins, padding, wrapping,
computed styles, image intrinsic dimensions, and paint order.

The `officehtml` profile does not run a second browser layout for object
geometry. It reads the fixed-coordinate point geometry emitted by OfficeCLI
1.0.147. OfficeHTML slide bounds may be any positive point-based equivalent of
the standard widescreen canvas; the parser must not apply the author 1920px
scale a second time.

### 3. PPT Object Lowering

The lowering stage converts measured visible nodes into the concrete PPT Object
IR. The IR is an object AST, not a semantic slide model. Supported object kinds
are:

- slide and solid slide background;
- rectangle and rounded rectangle shape;
- text box and text-bearing shape, including paragraphs and direct text runs;
- native picture, including `data:image/svg+xml` when OfficeCLI supports it or
  an object-local deterministic raster fallback;
- native table, row, column, and cell.

Every slide-owned object receives a deterministic stable name, source slide,
optional source identity, point bounds, and its kind-specific fields.

The supported CSS/property surface for Contract v1 is intentionally small:

- geometry: `left`, `top`, `width`, `height`, rotation, and slide-relative
  bounds;
- fills: solid `background`/`background-color` and opacity flattened against
  the known backdrop;
- outlines: uniform `solid`/`none` borders, color, width, and border radius;
- text: `font-family`, `font-size`, `font-weight`, `font-style`, text color,
  `line-height`, `text-align`, `vertical-align`, direction, margins, and
  padding;
- tables: fixed row/column dimensions, cell text, cell fill, cell text
  formatting, alignment, padding, and four-sided uniform borders;
- pictures: explicit box geometry, data URI source, and `object-fit` behavior
  supported by the compiler.

Visible content outside this surface is a blocking diagnostic. It is never
silently dropped and never converted into a whole-slide screenshot.

### 4. OfficeCLI Rendering

The renderer creates a blank widescreen presentation, applies one atomic batch,
validates the temporary PPTX, and only then moves it to the requested output.
OfficeCLI is the structural oracle for this path. Acceptance uses `officecli
get`, `query`, `validate`, `view ... issues`, `view ... html`, and `view ...
screenshot`; it does not inspect output with `python-pptx` internals.

Text and cell content are passed as batch data. Diagnostics identify the
operation and, where available, the source slide and source object. A failed
batch or validation leaves no new final deliverable.

### 5. Round-trip Validation

The reversible path is:

```text
Author HTML → PPTX A → OfficeHTML A → PPTX B
```

PPTX A and PPTX B are equivalent when their normalized supported-object
manifests agree on slide count and size, kind counts, stable names, text,
pictures, tables, cell content, supported formatting, and geometry within the
tolerances below. ZIP bytes, relationship identifiers, XML order, and private
OfficeCLI object IDs are not part of the contract.

| Field | Tolerance |
|---|---:|
| object/table x, y, width, height | `1pt` per field |
| table column widths and row heights | `0.5pt` per item |
| font size | `0.25pt` |
| supported RGB colors, booleans, alignment | exact |
| text | Unicode code-point equality, except display-only NBSP normalization in OfficeHTML |

## Explicit profiles

### `author`

The input is Author HTML on the 1920×1080 canvas. It must contain at least one
`.slide`, use data URI images, and use non-merged tables. Inline preview
runtime tags (`script`, `style`, `link`, `meta`) and explicitly named preview
chrome are ignored. Unsupported visible tags (`canvas`, `video`, `audio`,
`iframe`, `object`, and `embed`), unsupported picture sources, unsupported
effects, and merged cells are blocking findings.

The profile is explicit. The checker does not infer `officehtml` from the
presence of a few CSS declarations or `data-path` attributes.

### `officehtml`

The input is an OfficeCLI 1.0.147 `view ... html` projection. A slide-owned
object is recognized only when its `data-path` contains
`/slide[N]/shape[...]`, `/slide[N]/picture[...]`, or
`/slide[N]/table[...]`. Cells are joined through `data-cell-path`.

The following are explicit ignore rules:

- viewer chrome outside a `.slide`, including sidebars, toolbars, thumbnails,
  buttons, scripts, counters, and navigation;
- slide descendants without a slide-owned `data-path`, which are treated as
  unowned master/layout projections;
- pathless decorative projections that do not identify a supported object.

An owned chart, connector, group, SmartArt, media, or another deferred object
kind is not ignored: it is a blocking `unsupported_object_kind` diagnostic.
An owned picture without a data image source, an owned table with a missing
cell path, and a merged cell are also blocking diagnostics.

`data-path` is a source identity and debugging join key. It is not an automatic
write-back protocol to the original PPTX.

## Non-goals

Contract v1 does not promise:

- merged table cells;
- charts or chart-SVG recovery as editable charts;
- reconstruction of masters, layouts, or themes;
- connectors, groups, SmartArt, equations, media, animations, notes,
  comments, or complete hyperlink round trips;
- complex gradients, filters, clipping paths, complex shadows, or arbitrary
  SVG-to-editable-path conversion;
- responsive websites, arbitrary HTML, a semantic slide model, or automatic
  slide design;
- in-place patching of an existing PPTX through `data-path`;
- binary PPTX or OOXML relationship equality;
- an automatic pixel/SSIM visual threshold.

## Legacy-renderer boundary

The old renderer is intentionally preserved and has its own historical
constraints. They are not universal restrictions of the OfficeCLI profile.

| Legacy observation | Contract v1 interpretation |
|---|---|
| `python-pptx` tables expand into cell shapes | not an OfficeCLI limitation; Contract v1 requires native tables |
| SVG pictures were omitted by the old path | not a target; OfficeCLI preserves each picture or uses an object-local fallback |
| autoshapes inherited an unintended theme shadow | not an OfficeCLI capability rule; the new acceptance gate checks for it separately |
| legacy checker warns that tables are not native | that warning belongs to the legacy profile and must not appear for `officehtml` |
| legacy renderer silently skipped unsupported nodes | Contract v1 changes this at the OfficeCLI seam: visible unsupported content blocks |

The `write-a-html-ppt` authoring skill should link to this document when the
OfficeCLI-first profile is selected. It should not copy this capability matrix
into its legacy input rules.

## Acceptance report and issue classification

`html-to-pptx-algeria-acceptance` writes JSON and Markdown reports alongside
PPTX A, OfficeHTML A, PPTX B, OfficeCLI issue text, and screenshots. The gate
has four report statuses:

- `PASS`: all contract, compile, validation, inventory, round-trip, and
  screenshot steps passed and no OfficeCLI issue was observed;
- `KNOWN_BASELINE_DIFFERENCE`: only an allowlisted OfficeCLI issue was found;
- `UNSUPPORTED_INPUT`: the contract or compiler rejected visible unsupported
  input, with source context;
- `REGRESSION`: a new structural, OfficeCLI, round-trip, or visual-artifact
  failure occurred.

Known overflow findings are represented as a triple, never only as a count:

```json
{"slide": 8, "object": "slide-008-textbox-028", "subtype": "text_overflow"}
```

The acceptance gate runs these steps in order:

1. check the Author HTML with the `author` profile;
2. compile PPTX A and explicitly run OfficeCLI validation;
3. collect the normalized structural manifest through OfficeCLI queries;
4. classify OfficeCLI issues by slide, stable object name, and subtype;
5. project PPTX A to OfficeHTML A;
6. compile OfficeHTML A to PPTX B, validate it, and compare its normalized
   manifest to PPTX A;
7. render every Author HTML and PPTX A slide, then create side-by-side images
   for human review.

The visual images are evidence, not a noisy automatic similarity score. A
missing screenshot is a regression because the acceptance artifact is
incomplete.

## Commands

From the repository root, with the package environment active:

```powershell
html-to-pptx-contract `
  'D:\Opencodeworkspace\html-to-pptx\workspace\algeria\algeria\Algeria_AC_Product_Portfolio_20260906_v3_pptx.html' `
  --profile author

html-to-pptx-algeria-acceptance `
  --input 'D:\Opencodeworkspace\html-to-pptx\workspace\algeria\algeria\Algeria_AC_Product_Portfolio_20260906_v3_pptx.html' `
  --output-dir 'acceptance-output\algeria'
```

The output directory should be empty for a fresh run. The compiler refuses to
overwrite an existing PPTX, which preserves a valid prior deliverable when a
later run fails.
