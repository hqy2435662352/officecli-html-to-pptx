# OfficeCLI HTML-to-PPTX Compiler MVP — Working Context

## Current status

This repository worktree is reserved for the OfficeCLI HTML-to-PPTX compiler MVP.

- Worktree: `D:\Opencodeworkspace\html-to-pptx\officecli-html-to-pptx-mvp`
- Branch: `codex/officecli-html-to-pptx-mvp`
- Remote tracking branch: `fork/codex/officecli-html-to-pptx-mvp`
- Planning base commit: `098b4eba118e17894938ca901f002221790f8b0a`
- Base remote branch: `fork/fix/clear-theme-shape-effects`
- OfficeCLI compatibility baseline: `1.0.147`
- Issue 07 remediation base: `a5d979e`.
- Issue 07 implementation commits: `0d8cba7`, `c766018`, `afd7945`, and `9ab8aba`.
- Implementation status: Tickets 01–07 are implemented in this worktree; the authoritative Issue 07 gate has completed.
- Acceptance status: `KNOWN_BASELINE_DIFFERENCE` with Gate 3 visual review PASS for all 8 slides; all non-baseline checks PASS.
- Ticket frontier: 01–07 are complete for the MVP; future work remains explicitly deferred below.

The approved planning documents are under `.scratch/officecli-html-to-pptx-mvp/`.

An earlier Codex-managed worktree exists at `C:\Users\Administrator\.codex\worktrees\742d\html-to-pptx`. It is not the canonical MVP workspace and no planning documents were intentionally published there. It has been left in place to avoid deleting copied untracked files without an explicit cleanup request.

## Goal agreed in the conversation

The MVP has one precise outcome:

> Compile the Algeria Author HTML from a blank presentation through Chromium measurement, a PPT Object IR, and OfficeCLI into a PPTX containing native text, native shapes, native pictures, and native tables; then project that PPTX through `officecli view html` and verify stable object-level round trips.

This work is no longer framed as an OfficeCLI feasibility investigation. OfficeCLI is the project's preferred Office layer. The question for the MVP is whether the smallest useful compiler contract can be implemented and verified, not whether OfficeCLI should be selected.

The original planning artifacts remain the contract for the MVP. Implementation was executed in this dedicated issue worktree after the assigned ticket was authorized, and Issue 07 records the end-to-end acceptance evidence.

## Architectural conclusion

The useful architecture is:

```text
Author HTML
  → Chromium Layout/Measurement
  → Measurement DTO
  → PPT Object Lowering
  → PPT Object IR
  → OfficeCLI Atomic Renderer
  → Native-object PPTX
  → OfficeCLI query / HTML / screenshot verification
```

The existing project's most valuable capability is the browser frontend, not its legacy renderer. Chromium already solves the hard HTML/CSS-to-geometry problem through final DOM bounds and computed styles. OfficeCLI does not replace the browser layout engine; it replaces the PowerPoint object-rendering backend.

The IR is intentionally a PPT Object IR, not a Slide Semantic IR. It represents concrete PowerPoint objects and formatting after browser layout. It does not model business meaning, slide intent, narrative, or automatic design decisions.

The legacy `python-pptx` path remains unchanged during the MVP. Do not build a generic renderer registry or plugin framework before the OfficeCLI path passes the golden acceptance gate.

## Why OfficeCLI HTML matters

Local testing with OfficeCLI 1.0.147 established that `officecli view <file> html` is not a page-image export for native-object PPTX files. It produces a fixed-coordinate object DOM:

- each slide is a `.slide` element;
- slide-owned shapes and text boxes are separate `.shape` elements;
- text is represented through shape text, paragraph, and run/span descendants;
- geometry is serialized as absolute `left`, `top`, `width`, and `height`, usually in points;
- source object identity is exposed through `data-path`;
- pictures are independent picture containers with image data;
- tables retain table and cell structure, including `data-cell-path`;
- charts may be represented visually through SVG rather than as a page screenshot.

This HTML is a decompiler projection optimized for visual fidelity and object tracing. It is not responsive HTML, a semantic web design, the compiler's internal IR, or an automatic write-back protocol.

If the source PPTX contains only one large image per slide, OfficeCLI can only project those picture objects. It cannot recover text, shapes, or charts that were already flattened before OfficeCLI received the file.

## Reversible OfficeHTML Contract conclusion

The earlier `write-a-html-ppt` skill and the proposed reversible OfficeHTML Contract follow the same core idea: constrain the HTML dialect so that AI-generated HTML has predictable downstream behavior.

The contract now needs clearer stage ownership:

1. **Authoring Runtime** — human-reviewable browser navigation and preview behavior.
2. **Chromium Measurement** — which DOM and CSS constructs can be measured reliably.
3. **PPT Object Lowering** — how measured/semantic HTML nodes become concrete object kinds.
4. **OfficeCLI Rendering** — which PPT object properties OfficeCLI creates and how failures are handled.
5. **Round-trip Validation** — what object-level equivalence means after PPTX → OfficeHTML → PPTX.

Restrictions caused only by the old `python-pptx` renderer must not remain universal Author HTML restrictions. Inline preview scripts remain valid when they only control the browser workbench and do not mutate slide content before measurement.

The OfficeHTML profile is explicit. It must not be inferred through complicated heuristics, and it must exclude viewer chrome and master/layout projections that have no slide-owned `data-path`.

## Golden triangle

The MVP uses three artifacts with different truth responsibilities. They are untracked workspace assets in the original checkout and are intentionally referenced by absolute path until the first implementation ticket decides what minimal fixture should enter version control.

### 1. Author HTML — compiler input and author intent

`D:\Opencodeworkspace\html-to-pptx\workspace\algeria\algeria\Algeria_AC_Product_Portfolio_20260906_v3_pptx.html`

Observed baseline:

- 8 slides;
- fixed 1920×1080 authoring canvas;
- shallow Flexbox/Grid layout;
- 9 HTML tables;
- 86 rows and 484 cells;
- 18 SVG data-URI images;
- preview runtime script;
- no merged cells.

This artifact is authoritative for visible content, CSS layout, picture presence, and authored style intent.

### 2. Native-table PPTX — editable object reference

`D:\Opencodeworkspace\html-to-pptx\workspace\algeria\algeria\Algeria_AC_Product_Portfolio_20260906_v3_nativetables.pptx`

Observed baseline:

- 8 slides;
- 261 slide-owned objects;
- 252 shape/text objects;
- 9 native PowerPoint tables;
- 86 table rows and 484 cells;
- OfficeCLI validation passes;
- 10 historical text-overflow findings from the reference renderer;
- 0 picture objects.

The zero-picture result is a defect of the old conversion path, not a target. The new MVP must restore the 18 pictures present in Author HTML.

The reference deck is authoritative for the existence and distribution of editable native tables, but not for renderer defects or un-authored theme effects.

### 3. OfficeCLI HTML — reverse-profile reference

`D:\Opencodeworkspace\html-to-pptx\workspace\algeria\algeria\Algeria_AC_Product_Portfolio_20260906_v3_nativetables.html`

Observed baseline:

- 8 slides;
- approximately 959.98pt × 540pt slide canvas;
- 261 `data-path` values;
- 252 shape paths and 9 table paths;
- 484 `data-cell-path` values;
- 16 additional master/layout visual projections without `data-path`;
- no merged table cells.

This artifact is authoritative for OfficeCLI's fixed-coordinate object DOM, object paths, cell paths, and reverse-profile parsing behavior. It is not the primary input for testing Chromium's layout work because its coordinates have already been resolved by PowerPoint.

## Golden-source precedence

When the three artifacts disagree:

1. Author HTML wins for content, pictures, CSS layout, and authored style.
2. Native-table PPTX wins for the target concept and distribution of native tables.
3. OfficeCLI HTML wins for decompiler path shape and reverse-profile parsing.

Do not mechanically reproduce known defects:

- restore the 18 pictures that the old renderer lost;
- do not add theme shadows that Author HTML did not request;
- classify the historical reference overflows as a baseline rather than deliberately reproducing them; the current compiler baseline is the three Issue 07 tuples recorded below;
- do not recreate the 16 pathless master/layout projections as slide-owned objects.

## MVP object surface

Supported:

- slide and slide background;
- rectangle and rounded rectangle;
- text box and text-bearing shape;
- paragraph and direct text run;
- picture, including SVG data URI with an object-local deterministic raster fallback when necessary;
- native table, row, column, and cell;
- basic fills, outlines, opacity, rotation, margins, text formatting, alignment, table dimensions, padding, and borders needed by the golden case.

Explicitly deferred:

- charts and chart-SVG recovery;
- connectors, groups, SmartArt, equations, media, animations, notes, comments, and complete hyperlink round trips;
- masters, layouts, and themes reconstruction;
- merged table cells;
- complex gradients, filters, clip paths, complex shadows, and arbitrary SVG-to-editable-path conversion;
- a semantic slide model;
- responsive or arbitrary websites;
- in-place patching of an existing PPTX through `data-path`;
- binary or OOXML relationship equality.

Unsupported visible content must fail explicitly. It must never disappear silently or degrade into a whole-slide screenshot.

## Highest-value test seam

There is one primary external seam:

```text
HTML + explicit profile + output destination
  → compiler operation
  → PPTX + structured diagnostics + optional normalized manifest
```

Acceptance observes the result through:

- `officecli validate`;
- OfficeCLI object and table queries;
- OfficeCLI text/issues views;
- `officecli view html`;
- per-slide screenshots;
- normalized manifest comparison.

Tests should not freeze private DTO class shapes, exact internal helper calls, or the textual ordering of OfficeCLI batch commands.

## Definition of object-level reversibility

The MVP round trip is:

```text
Author HTML → PPTX A → OfficeHTML A → PPTX B
```

PPTX A and PPTX B are equivalent when their normalized supported-object manifests agree on:

- slide count and size;
- object-kind counts;
- unique, alignable stable identities;
- text;
- picture count;
- table count, dimensions, and cell content;
- supported fills, outlines, fonts, and alignments;
- supported shape/text properties, paragraph boundaries, direct runs, and run formatting;
- picture identity/content fingerprints, intrinsic dimensions, and fitting semantics;
- native-table geometry, cell formatting, paragraph boundaries, and cell runs;
- geometry within the specified tolerances.

This does not require identical ZIP bytes, XML order, generated relationship identifiers, or internal object identifiers.

## Acceptance baselines

The complete candidate deck must have:

- 8 slides;
- 9 native tables;
- 86 table rows;
- 484 table cells;
- 18 independent picture objects;
- no whole-slide picture;
- no shape-per-cell fake tables;
- source-equivalent visible text and Unicode;
- unique deterministic object names;
- a valid OfficeCLI schema;
- no new structural or overflow issue outside an explicit baseline allowlist;
- side-by-side visual review for all slides.

Geometry tolerances agreed for the first contract:

- object and table bounds: at most 1pt per x/y/width/height field;
- column widths and row heights: at most 0.5pt per item;
- font size: at most 0.25pt;
- supported RGB colors, booleans, and alignment: exact;
- text: Unicode code-point equality, with only documented display-only OfficeHTML non-breaking-space normalization.

## Issue 07 authoritative acceptance and targeted reacceptance (2026-09-08)

The initial full replay and its durable review are preserved as historical
evidence in `.scratch/officecli-html-to-pptx-mvp/issues/07-authoritative-acceptance-remediation.md` and under:

`C:\TEMP\officecli-html-to-pptx-mvp-issue07-acceptance-17`

The independent reacceptance report
(`C:\TEMP\issue07-reacceptance-20260908\reacceptance-report.md`) correctly
reopened the ticket: the old PASS record missed the visible slide-1 and
slide-8 differences and the comparator probes exposed four false-pass
boundaries.  The targeted remediation is now complete.

Current evidence:

- final Author PPTX A:
  `C:\TEMP\issue07-reacceptance-fixed-20260908\algeria-a-final.pptx`;
- final OfficeHTML projection:
  `C:\TEMP\issue07-reacceptance-fixed-20260908\algeria-a-final.officehtml.html`;
- final round-trip PPTX B:
  `C:\TEMP\issue07-reacceptance-fixed-20260908\algeria-b-final.pptx`;
- fresh slide-1 and slide-8 comparisons:
  `C:\TEMP\issue07-reacceptance-fixed-20260908\final-visuals\side-by-side`;
- comparator probes:
  `C:\TEMP\issue07-reacceptance-20260908\comparator-probes.py`.

The final A and B artifacts both pass OfficeCLI validation and contain 8
slides, 89 shapes, 154 textboxes, 18 independent pictures, and 9 native
tables.  Their issue keys are identical and contain only the three approved
OfficeCLI 1.0.147 baseline tuples:

- `(1, slide-001-textbox-012, text_overflow)`;
- `(8, slide-008-textbox-024, text_overflow)`; and
- `(8, slide-008-textbox-028, text_overflow)`.

The B-minus-A issue subset is empty.  The final Author compiler manifest and
OfficeCLI readback compare strictly as `PASS` with zero findings.  The new
visual comparisons close the slide-1 title/card-label/model-range blocker and
the slide-8 number/card-04-wrap blocker.  The comparator now treats authored
paragraph spacing and Unicode strictly except at the explicit OfficeHTML
projection boundary, and only permits SVG-to-PNG picture fallback when its
intrinsic aspect ratio is preserved.  All five supplied probes return
`REGRESSION` for their deliberately invalid mutations.

Full regression testing passes with `73 passed`; the non-Algeria OfficeHTML
round-trip, Algeria round-trip, compiler, acceptance, contract, and legacy
paths are included.  `compileall` and `git diff --check` also pass.  Per the
reacceptance scope, the unchanged slides reuse acceptance-17 screenshots
instead of repeating the complete eight-page visual replay.

The table distribution is:

| Slide | Tables |
|---|---|
| 1 | none |
| 2 | 5×8, 8×8, 5×8, 5×8 |
| 3 | 15×4 |
| 4 | 13×5 |
| 5 | 13×5 |
| 6 | 13×5 |
| 7 | 9×5 |
| 8 | none |

## Ticket plan and blocking edges

```text
01 Shape/Text vertical slice
 ├── 02 Native Picture vertical slice
 └── 03 Native Table vertical slice
          │
02 + 03 ──┴──► 04 Full Algeria deck
                    ↓
               05 OfficeHTML round trip
                    ↓
               06 Contract + acceptance gate
                    ↓
               07 Authoritative acceptance remediation
```

The tickets are tracer bullets rather than horizontal component tickets. The Measurement DTO and PPT Object IR are introduced only as the complete shape/text, picture, and table paths need them. This avoids speculative schemas and guarantees that every completed ticket produces a PPTX that can be opened, queried, and validated.

## Working rules for future agents

1. Work only in this repository worktree and on `codex/officecli-html-to-pptx-mvp` unless the user explicitly changes the target.
2. Start from the next explicitly assigned ticket. Tickets 01–07 are complete for the current MVP; future work must remain within the deferred surface.
3. Read the full spec and the assigned ticket before changing code.
4. Preserve the old renderer and existing tests during the MVP.
5. Use installed OfficeCLI help as the authority for property names and capabilities; the MVP baseline is OfficeCLI 1.0.147.
6. Reuse the existing Chromium measurement rules instead of building a second HTML layout engine.
7. Do not introduce a renderer factory, plugin framework, semantic IR, or support for deferred object kinds.
8. Use atomic OfficeCLI batches and temporary output delivery semantics.
9. Treat every unsupported visible element as a compilation failure with source context.
10. Use OfficeCLI, not `python-pptx` internals, as the structural oracle for the new path.
11. Keep the golden artifacts external until the assigned ticket deliberately imports a minimal, reviewable fixture.
12. Do not copy the old PPTX's missing pictures or unintended theme effects into the new expected output.

## Planning artifacts

- `.scratch/officecli-html-to-pptx-mvp/spec.md` — approved feature specification.
- `.scratch/officecli-html-to-pptx-mvp/issues/01-shape-text-vertical-slice.md` — complete.
- `.scratch/officecli-html-to-pptx-mvp/issues/02-native-pictures.md` — complete.
- `.scratch/officecli-html-to-pptx-mvp/issues/03-native-table.md` — complete.
- `.scratch/officecli-html-to-pptx-mvp/issues/04-full-algeria-deck.md` — complete.
- `.scratch/officecli-html-to-pptx-mvp/issues/05-officehtml-roundtrip.md` — complete.
- `.scratch/officecli-html-to-pptx-mvp/issues/06-contract-and-acceptance-gate.md` — complete.
- `.scratch/officecli-html-to-pptx-mvp/issues/07-authoritative-acceptance-remediation.md` — completed authoritative gate and evidence.
