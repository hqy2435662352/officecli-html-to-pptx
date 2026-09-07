# OfficeCLI HTML-to-PPTX Compiler MVP

**Status:** ready-for-agent

## Problem Statement

The project can already use Chromium to calculate the final layout of Author HTML, but the current conversion path couples DOM measurement directly to `python-pptx` object creation. This coupling makes renderer limitations look like HTML authoring limitations and prevents the measured document from being reused by a more capable backend.

The current user-visible consequences are:

- HTML tables are expanded into many rectangles and text boxes instead of editable native PowerPoint tables.
- SVG data-URI images in the Algeria Author HTML are silently omitted by the old path.
- Some generated shapes inherit theme effects that were not authored in HTML.
- Measurement results do not have a renderer-independent, observable PPT Object IR.
- The project cannot use OfficeCLI object queries and HTML projection to verify object-level round-trip stability.
- The Authoring Contract mixes browser, measurement, lowering, and old-renderer constraints.
- OfficeCLI can project native PPTX objects into fixed-coordinate HTML, but the project cannot yet compile that object DOM back into a structurally stable native-object PPTX.

The project needs an OfficeCLI-first HTML-to-PPTX compiler path that retains Chromium DOM layout, emits editable native PowerPoint objects, fails loudly on unsupported visible content, and has an executable definition of object-level reversibility.

## Solution

Build a minimal compiler path with one externally testable seam:

**HTML input + explicit input profile → Chromium measurement → Measurement DTO → PPT Object lowering → PPT Object IR → OfficeCLI atomic renderer → validated native-object PPTX + diagnostics/manifest**

The MVP supports two explicit input profiles:

1. `author` is the default profile for 1920×1080 Author HTML. Chromium resolves Flexbox, Grid, margins, padding, text wrapping, nesting, and final computed style.
2. `officehtml` accepts fixed-coordinate HTML produced by OfficeCLI 1.0.147. It recognizes slide-owned objects through `data-path` and table cells through `data-cell-path`, while excluding viewer chrome and unowned master/layout projections.

The supported PowerPoint object surface is deliberately small:

- slides and slide backgrounds;
- rectangles and rounded rectangles;
- text boxes and text-bearing shapes;
- paragraphs and direct text runs;
- pictures;
- native tables, rows, columns, and cells.

The Algeria deck is the golden acceptance case. Its Author HTML is the truth for content, layout, and style intent; its native-table PPTX is the structural reference for editable tables; and its OfficeCLI HTML projection is the reference for object paths and reverse parsing. The MVP must restore the 18 pictures lost by the old renderer and must not reproduce theme effects that were not authored.

The legacy `python-pptx` path remains available and unchanged during the MVP. The new path is explicit; it does not require a general renderer plugin framework or a default-backend migration.

## User Stories

1. As an AI slide author, I want to keep authoring 1920×1080 HTML slides, so that I can use a browser as a live preview workbench.
2. As an AI slide author, I want to use shallow Flexbox and Grid layouts, so that I do not have to calculate every PowerPoint coordinate manually.
3. As a developer, I want Chromium to calculate final element geometry, so that the OfficeCLI renderer does not need to implement a browser layout engine.
4. As a developer, I want measurement output to be independent of any PowerPoint library, so that it can feed OfficeCLI without carrying `python-pptx` types.
5. As a developer, I want Measurement DTOs and PPT Object IR to be separate, so that browser observations and PowerPoint creation intent remain distinct.
6. As a developer, I want one explicit OfficeCLI compiler entry point, so that callers do not have to orchestrate many OfficeCLI subcommands.
7. As an existing project user, I want the legacy `python-pptx` path to remain unchanged during the MVP, so that the experiment does not break current callers.
8. As a presentation author, I want HTML text to become native PowerPoint text, so that it remains editable.
9. As a presentation author, I want paragraphs, line breaks, and basic run formatting to survive conversion, so that typography is not flattened.
10. As a presentation author, I want HTML containers with backgrounds and borders to become native shapes, so that their fill, outline, and text remain editable.
11. As a presentation author, I want rounded rectangles to retain an equivalent corner treatment, so that card visuals remain faithful.
12. As a presentation author, I want each HTML image to become an independent PowerPoint picture, so that it can be moved, resized, and replaced.
13. As a presentation author, I want SVG data-URI images to be preserved, so that the 18 Algeria product images are no longer silently lost.
14. As a presentation author, I want each HTML table to become one native PowerPoint table, so that rows, columns, and cells remain editable.
15. As a presentation author, I want table column widths and row heights preserved, so that product specifications do not reflow unexpectedly.
16. As a presentation author, I want supported cell text and styling preserved, so that the native table remains visually close to the Author HTML.
17. As a developer, I want deterministic object names or identities, so that queries and regressions do not depend on unstable positional indexes.
18. As a developer, I want OfficeCLI writes to run as an atomic batch, so that one failed object cannot leave a misleading partial deck.
19. As a developer, I want compilation to use a temporary output until validation passes, so that a failure cannot overwrite a valid deliverable.
20. As a developer, I want unsupported visible content to produce explicit diagnostics, so that the compiler never silently drops authored content.
21. As a developer, I want diagnostics to identify the slide, source DOM object, and source path when available, so that failures are easy to locate.
22. As QA, I want to query output objects with OfficeCLI, so that I can prove tables did not degrade into fake cell shapes.
23. As QA, I want to compare measured input geometry with PPTX geometry read back through OfficeCLI, so that unit and coordinate drift is detectable.
24. As QA, I want source and output text compared character-for-character, so that Unicode, non-breaking spaces, and line breaks are not lost.
25. As QA, I want side-by-side screenshots of Author HTML and generated PPTX pages, so that visual failures not visible in manifests can be reviewed.
26. As QA, I want known reference issues reported separately from regressions, so that the MVP neither copies old defects nor hides new ones.
27. As a Contract maintainer, I want each rule assigned to Authoring, Measurement, Lowering, OfficeCLI Rendering, or Round-trip Validation, so that backend-specific limits are not presented as universal HTML limits.
28. As a Contract maintainer, I want the MVP pinned to OfficeCLI 1.0.147, so that an OfficeCLI upgrade can be verified by replaying the same acceptance case.
29. As an OfficeHTML user, I want to compile OfficeCLI's fixed-coordinate object DOM back into PPTX, so that object-level reversibility can be measured.
30. As an OfficeHTML user, I want viewer navigation, sidebars, scripts, and thumbnails excluded, so that only slide content becomes PowerPoint objects.
31. As an OfficeHTML user, I want unowned master/layout projections excluded, so that the slide-owned object count does not inflate.
32. As a developer, I want consecutive PPTX → OfficeHTML → PPTX passes to produce equivalent normalized manifests, so that “reversible” has an executable meaning.

## Implementation Decisions

### Golden-source precedence

The three Algeria artifacts have distinct responsibilities:

1. Author HTML is authoritative for authored content, CSS layout, images, and style intent.
2. The native-table PPTX is authoritative for the target concept of editable native tables and for the expected table distribution.
3. OfficeCLI HTML is authoritative for the shape of OfficeCLI's object projection, source paths, cell paths, and reverse-profile parsing.

When the artifacts disagree, the new compiler does not reproduce known defects of the old renderer. In particular, it restores all 18 Author HTML images, does not synthesize un-authored theme shadows, and treats the reference deck's overflow findings as a baseline to classify rather than a feature to reproduce.

### One external compiler seam

The MVP exposes one OfficeCLI compiler operation. Its required inputs are HTML, an explicit input profile, and an output destination. Its observable results are the PPTX, structured diagnostics, and an optional normalized manifest.

Chromium measurement, lowering, and OfficeCLI rendering remain internal compiler stages. They may have narrow internal contracts, but the primary acceptance suite does not lock their private type layout, helper calls, or batch command ordering.

### No generic renderer framework

The MVP adds a direct OfficeCLI path beside the existing path. It does not add a registry, factory, plugin loader, or speculative backend abstraction. Replacing the default renderer is a later decision made only after the OfficeCLI path satisfies the golden acceptance gate.

### Explicit profiles only

The supported profiles are `author` and `officehtml`. The compiler does not guess the profile with complex heuristics. A mismatched profile fails with an actionable diagnostic.

### Chromium remains the layout engine

The existing browser-based behavior is retained and adapted:

- discover slides through the `.slide` class rather than a required element tag;
- isolate slides for measurement;
- neutralize ancestor transforms that would corrupt geometry;
- measure slide-relative geometry with browser layout results;
- collect final computed style;
- exclude invisible and zero-area nodes;
- collect paragraph and direct-run text;
- collect image source, intrinsic size, and fitting behavior;
- preserve DOM paint order;
- allow Chromium to resolve Flexbox, Grid, margins, padding, and wrapping.

Measurement data contains no `python-pptx` object, enumeration, or OOXML helper.

### Geometry uses slide-relative points

The compiler normalizes every input against its measured slide rectangle. Author HTML's 1920×1080 CSS canvas and OfficeHTML's approximately 960pt×540pt canvas therefore map to the same standard widescreen slide without a profile-specific double scaling error.

PPT Object IR stores geometry in points only. Geometry conversion must not assume that every future input is exactly 1920 CSS pixels wide.

### Minimal PPT Object IR

The IR includes only presentation, slide, shape, picture, table, paragraph, run, table row, and table cell entities. It is a PowerPoint object AST, not a semantic model of the business narrative.

Every slide-owned object records its kind, deterministic stable name, optional source path, slide index, bounds, z-order, and kind-specific properties. Fields are added only when required by a supported Algeria object or an acceptance rule.

### Object recognition

For `officehtml`, object recognition uses the type encoded in `data-path` first, then the OfficeCLI object container classes. `data-cell-path` associates cells with a table.

For `author`, recognition uses explicit `data-pptx-kind` when present, then semantic elements such as `table` and `img`, then DOM/computed-style inference for shapes and text boxes. The existing Algeria Author HTML is not required to add explicit kind markers before the MVP can compile.

### OfficeHTML isolation

The reverse profile parses only slides and only slide-owned object projections. Viewer chrome, thumbnails, navigation, counters, scripts, and toolbars never enter the IR. Master/layout visual projections without `data-path` are excluded from the slide-owned manifest.

`data-path` is a source identity and debugging join key. It is not an automatic write-back protocol to the original PPTX.

### Native shapes and text

The MVP supports rectangles, rounded rectangles, solid and transparent fills, uniform outlines, outline width, opacity, basic rotation, shape text, text-only shapes, text margins, horizontal and vertical alignment, paragraphs, direct runs, font family, font size, bold, italic, underline, text color, and line spacing.

Unsupported authored effects produce diagnostics. They are not silently ignored.

### Native pictures

Data-URI images, including SVG data URIs, become independent picture objects. SVG is retained when supported by the installed OfficeCLI capability surface; otherwise the compiler uses a deterministic raster fallback for that picture only. The fallback preserves the picture box and fitting behavior and never flattens the slide.

Undecodable image data fails with slide and source-object context.

### Native tables

One HTML table lowers to one PPT Object IR table and one native PowerPoint table. Supported properties are overall bounds, column widths, row heights, cell text, fill, font family, font size, bold, italic, text color, horizontal and vertical alignment, padding, and four-sided borders.

Merged cells are intentionally unsupported in this MVP because the golden deck has none. A non-unit row or column span is an explicit compilation error and never falls back to shape-per-cell rendering.

The Algeria table baseline is:

| Slide | Native tables |
|---|---|
| 1 | 0 |
| 2 | 4: 5×8, 8×8, 5×8, 5×8 |
| 3 | 1: 15×4 |
| 4 | 1: 13×5 |
| 5 | 1: 13×5 |
| 6 | 1: 13×5 |
| 7 | 1: 9×5 |
| 8 | 0 |

The total baseline is 9 tables, 86 rows, and 484 cells.

### Deterministic identity

Objects compiled from Author HTML receive deterministic names. Objects rehydrated from OfficeHTML preserve a safe source identifier when possible and also receive deterministic names for manifest alignment. Tests do not depend on positional path indexes such as the third shape on a slide.

### Transactional rendering

The renderer translates the complete IR into one atomic OfficeCLI batch and stops on the first failure. It writes to a temporary PPTX, validates the result, and only then delivers the final destination.

Failure diagnostics include OfficeCLI error output, the failed operation, source slide, source object, and source path when available. User-authored text and cell content are passed as data rather than interpolated into shell command strings.

### Executable definition of reversibility

For this MVP, reversibility means:

**Author HTML → PPTX A → OfficeHTML A → PPTX B**

PPTX A and PPTX B must have equivalent normalized manifests for the supported surface:

- same slide count and slide size;
- same object-kind counts;
- unique and alignable stable names;
- identical text after the documented OfficeHTML non-breaking-space normalization;
- same picture count;
- same table count, dimensions, and cell content;
- geometry within the documented tolerance;
- equivalent supported fills, outlines, fonts, and alignments.

Binary OOXML identity, relationship identifiers, ZIP ordering, and XML ordering are not required.

### Contract evolution

The Authoring Contract is reorganized into five stages: Authoring Runtime, Chromium Measurement, PPT Object Lowering, OfficeCLI Rendering, and Round-trip Validation. Restrictions caused only by `python-pptx` are removed from the OfficeCLI profile or revalidated against OfficeCLI.

The first contract version is pinned to the current measurement baseline, OfficeCLI 1.0.147, and the Algeria golden triangle.

## Testing Decisions

### Highest-level seam

The primary tests call the complete compiler seam with HTML, profile, and output destination. They assert on the delivered PPTX, structured diagnostics, OfficeCLI validation, OfficeCLI object queries, OfficeCLI HTML projection, normalized manifests, and rendered screenshots.

Tests do not primarily assert private function calls, private IR class shapes, exact batch command serialization, or the ordering of CSS helper invocations.

### Normalized manifests

The test harness produces comparable manifests for both sides of the compiler. The Author HTML manifest comes from browser measurement plus lowering; the PPTX manifest comes from OfficeCLI query/get capabilities.

The manifest includes slide size and count, object-kind counts, stable identities, bounds, text, fills, outlines, paragraph/run formatting, picture information, table dimensions, column widths, row heights, and cell content/formatting.

### Tolerances

- Slide size matches the standard Office widescreen size.
- Object x, y, width, and height differ by no more than 1pt.
- Table bounds differ by no more than 1pt.
- Individual column widths and row heights differ by no more than 0.5pt.
- Font sizes differ by no more than 0.25pt.
- Supported RGB colors, booleans, and alignment values match exactly.
- Text matches by Unicode code point, except for a documented display-only non-breaking-space normalization in OfficeHTML.

### Algeria structural acceptance

The generated deck must have 8 slides, 9 native tables, 86 table rows, 484 cells, and 18 picture objects. It must contain no whole-slide picture, and table cells must not be implemented as shape explosions. All visible slide text must match the Author HTML, all stable names must be unique, and OfficeCLI validation must pass.

The reference PPTX's zero pictures are recorded as a defect of the old path rather than a target for the new output.

### Issue classification

The reference deck has 10 known text-overflow findings. The MVP does not intentionally reproduce them. Acceptance requires no schema issue, no off-slide object, no missing picture, no table-structure error, and no new overflow outside an explicit baseline allowlist keyed by slide, object identity, and issue subtype.

### Visual review

Every Algeria slide receives an Author HTML screenshot, a generated PPTX screenshot, and a side-by-side comparison. Review checks missing content, coordinate drift, line wrapping, image fitting, table geometry and alignment, unintended theme effects, and whole-slide flattening.

The MVP does not set an automatic SSIM or pixel-difference threshold because browser, font, and presentation renderer differences would make that gate noisy. Visual review is explicit and recorded.

### Round-trip test

The generated PPTX is projected to OfficeHTML and then compiled through the `officehtml` profile. The first and second PPTX manifests must be equivalent across all supported fields and within the stated geometry tolerances.

### Failure coverage

The external seam must cover at least these failures:

- no `.slide` element;
- incorrect input profile;
- unsupported object kind;
- invalid or non-rectangular table matrix;
- mismatched table row/column counts;
- unsupported merged cell;
- undecodable picture;
- OfficeCLI batch failure;
- OfficeCLI validation failure;
- attempted overwrite of an existing valid output;
- accidental inclusion of OfficeHTML viewer chrome;
- accidental duplication of unowned master/layout projections.

### Existing test precedent

Reuse the repository's Playwright measurement approach, minimal end-to-end browser tests, temporary outputs, slide/shape inventory checks, reopenability checks, and side-by-side HTML/PPTX comparison workflow. New OfficeCLI output assertions use OfficeCLI as the structural oracle rather than `python-pptx` internals.

## Out of Scope

- Making OfficeCLI the default renderer for all callers.
- Removing or refactoring away the legacy `python-pptx` implementation.
- A generic renderer plugin system.
- A full Slide Semantic IR or business-intent model.
- Automatic slide design or content planning.
- In-place editing of an existing source PPTX.
- Writing modified `data-path` HTML back into the original PPTX.
- Full reconstruction of masters, layouts, and themes.
- Rehydrating master/layout projections that do not have `data-path`.
- Native charts or recovering chart SVG as editable chart data.
- Connectors, groups, SmartArt, equations, media, animations, notes, comments, and full hyperlink round trips.
- Merged table cells.
- Complex gradients, arbitrary SVG-to-editable-path conversion, filters, clipping paths, and complex shadows.
- Arbitrary websites, responsive web layouts, or a general browser-to-PowerPoint engine.
- Binary PPTX equality, OOXML relationship equality, or XML ordering equality.
- Automated visual-similarity thresholds.
- Correcting the Algeria deck's content or design.
- Reproducing or explicitly fixing the reference deck's 10 known overflows, unless the new renderer naturally eliminates them.

## Further Notes

1. The initiative is named **OfficeCLI HTML-to-PPTX Compiler MVP**, not a backend feasibility study. OfficeCLI is the chosen strategic Office layer; this work validates the compiler contract and implementation slice rather than comparing renderer products.
2. The OfficeCLI HTML projection is a decompiler projection and verification oracle, not the internal IR and not a responsive or directly editable web design format.
3. The Algeria Author HTML is the primary compiler input because it exercises browser layout, text, shape-like containers, 18 pictures, 9 tables, and the preview runtime in one compact deck.
4. Existing table-measurement JSON and experimental OfficeCLI batches are useful prior art but are not production inputs and must not be hard-coded into the renderer.
5. OfficeCLI 1.0.147 is the MVP compatibility baseline. Upgrading OfficeCLI requires replaying the golden acceptance case before changing the contract version.
6. The approved work is split into six tracer-bullet tickets. There is no standalone horizontal “build the DTO/IR” ticket; the necessary DTO and IR are introduced only as each end-to-end slice needs them.
