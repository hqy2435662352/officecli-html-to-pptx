# V03-01 Rich Text and Paragraphs Acceptance Checklist

## Scope

Fixture: `tests/fixtures/v03_01_rich_text_paragraphs.html`

One Author HTML slide exercises one coherent capability slice: editable rich
text and paragraph fidelity. It intentionally reuses the existing
`inlineRuns`, `paragraphs`, `visualLines`, PPT Object IR, and OfficeCLI range
lowering path. It does not introduce a second rich-text model.

In scope:

- mixed runs in one textbox: font family, size, weight, style, color, underline;
- Chinese, English, numbers, and emoji/UTF-16 range boundaries;
- explicit paragraph breaks, one empty paragraph, and source order;
- Chromium-decided soft wrap without flattening the textbox;
- unordered and ordered Native List Paragraph markers, indentation, and
  paragraph boundaries;
- paragraph alignment, line height, and authored paragraph spacing where the
  source semantics require it.

Out of scope:

- nested lists, list-item hard breaks, multi-paragraph list items, vertical
  writing, bidirectional text, tabs, columns, autofit, or text effects;
- new shape geometry, pictures, tables, backgrounds, charts, or object families;
- screenshots or per-line textboxes as substitutes for one authored textbox;
- a new rich-text IR, renderer registry, or workflow command.

## Accepted Test Seam

Ticket completion is judged only through User-Path Acceptance:

```text
capabilities -> doctor -> check -> build -> visual review -> finalize
```

Internal Measurement DTO, PPT Object IR, and lowering tests may isolate a
failure. They are diagnostic evidence only and cannot complete the ticket.

## Fixture Coverage

- `#mixed-runs` supplies visibly distinct direct runs plus `2026` and `🚀`.
- `#mixed-runs [data-canonical-part]` supplies two adjacent source nodes with
  identical resolved formatting. Their second node owns the leading space, so
  canonical merging can be checked without permitting text mutation.
- `#paragraphs [data-run-across-br]` supplies one styled inline element that
  crosses a hard break, followed by a consecutive break representing an empty
  paragraph and mixed Chinese/English content.
- `#soft-wrap` supplies one source paragraph narrow enough for Chromium to form
  multiple visual lines.
- `#unordered-list` and `#ordered-list` supply two items each, including an
  emoji-bearing ordered item. Both lists are intentionally top-level and
  contain no nested `ul` or `ol`, `li` hard break, or multi-paragraph `li`.
- The fixture remains one 1920x1080 slide with reviewable browser navigation and
  no external resources.

## Acceptance Checklist

### Public preflight and capability authority

- [ ] `capabilities --json` declares the supported V03-01 text/paragraph surface
      from the same authority used by Contract checking and lowering.
- [ ] `doctor --json` passes on the accepted Windows runtime.
- [ ] `check <fixture> --json` returns `PASS` with no unsupported visible content.
- [ ] A neighboring negative fixture for each newly rejected boundary returns a
      stable `BLOCK` diagnostic with source context; no silent omission occurs.

### Build and native editability

- [ ] `build <fixture> <fresh-output> --json` produces a new one-slide Artifact
      Pair and returns `VISUAL_REVIEW_REQUIRED`.
- [ ] The PPTX opens and the authored text remains native PowerPoint text, not a
      page image, object screenshot, SVG text, or per-line textbox flattening.
- [ ] `#mixed-runs` maps to one native text-bearing object with independently
      editable runs whose family, size, bold, italic, color, and underline match
      the fixture.
- [ ] Hard-break paragraphs, the empty paragraph, and source order survive
      OfficeCLI readback.
- [ ] The soft-wrapped source paragraph remains one authored text object;
      Chromium's visual lines are preserved without materially changing its
      measured bounds or global font size.
- [ ] Unicode range writes remain aligned after `🚀` and `2️⃣`; later runs do not
      inherit the wrong formatting.
- [ ] Every native run is paragraph-local. A styled inline element crossing a
      `<br>` is split into one run per paragraph with the same resolved
      formatting; no normalized run contains `\n` and no range includes the
      paragraph separator.
- [ ] Adjacent runs in the same paragraph and list item with identical resolved
      formatting and supported semantic attributes normalize to one Canonical
      Run. The `North` + ` Africa` case reads back as exactly `North Africa`
      without a source-node boundary or whitespace mutation.
- [ ] Canonical Run normalization never crosses a paragraph, list-item, or
      `<br>` boundary and never merges formatting or supported semantic
      attribute differences.
- [ ] `<ul>` lowers to native PowerPoint bullet paragraphs and `<ol>` lowers to
      native automatic-number paragraphs; literal `•` or `1.` text prefixes do
      not satisfy this requirement.
- [ ] List level and indentation remain native paragraph properties and survive
      OfficeCLI readback.
- [ ] Each top-level HTML `ul` or `ol` maps to one Native List Textbox, and each
      direct `li` maps to one Native List Paragraph inside that textbox.
- [ ] No list item is emitted as a separate textbox.

### Structural evidence

- [ ] Manifest object identity, kind, bounds, text, paragraph count, run count,
      and key run/paragraph formatting agree with independent expected literals.
- [ ] OfficeCLI readback proves the native object, paragraph, run, marker, and
      indentation structure required by this ticket.
- [ ] `officecli validate` passes.
- [ ] `officecli view <pptx> issues` contains no unclassified severe issue.
- [ ] Existing V0.2 successful fixtures retain their output semantics.

### Visual Review and finalization

- [ ] The Evidence Bundle contains the single required Comparison Image and a
      review record associated with the same build id and hashes.
- [ ] Visual Review checks mixed-run appearance, hard/empty paragraphs,
      line-height/spacing, soft-wrap line placement, list markers, and indentation.
- [ ] No material clipping, overlap, missing content, reordered text, or visible
      line-placement regression exists.
- [ ] `finalize --json` mechanically returns `PASS` or `PASS_WITH_FINDINGS`; any
      Major Finding keeps the artifact at `REVISION_REQUIRED`.

### Proportional verification

- [ ] One red-to-green public-seam tracer bullet is completed at a time.
- [ ] Focused tests, the existing relevant suite, `compileall`, and
      `git diff --check` pass after implementation.
- [ ] A real fresh PPTX plus readback and visual evidence is retained as the
      ticket's acceptance artifact; an exit code alone is insufficient.

## Recorded Decision V03-01-003

Status: `APPROVED`

One top-level HTML `ul` or `ol` maps to one Native List Textbox. Every direct
`li` maps to one Native List Paragraph inside that textbox, using native bullet
or automatic-number properties, level, and indentation with paragraph
readback. Literal bullet characters, numbered prefixes, and a separate textbox
per `li` are explicit acceptance failures. Nested-list behavior is deferred and
excluded from the initial V03-01 fixture.

## Recorded Decision V03-01-004

Status: `APPROVED`

V03-01 preserves V0.2 newline semantics and the existing `visualLines`
behavior. A `<br>` creates a native paragraph boundary, consecutive `<br>`
elements retain an empty native paragraph, and soft wrapping remains
browser/layout behavior. V03-01 does not introduce a new soft-line-break model.
The initial list fixture excludes nested lists, list-item hard breaks, and
multi-paragraph list items; soft breaks inside a Native List Paragraph require
a separate future decision.

## Recorded Decision V03-01-005

Status: `APPROVED`

Every run is a Paragraph-local Run. A `<br>` terminates both the current
paragraph and the current run. When one styled inline element spans the break,
the compiler creates separate runs on both sides with identical resolved
formatting. OfficeCLI ranges may use the textbox-level range interface, but
each range covers only actual characters inside one paragraph; paragraph
separators are excluded and UTF-16 length is calculated from the resulting
paragraph/run structure.

## Recorded Decision V03-01-006

Status: `APPROVED`

Canonical Run normalization is enabled. Run identity is a formatting boundary,
not a DOM node boundary. Adjacent runs may merge only when they remain in the
same paragraph and list item and have identical resolved formatting and
supported semantic attributes. Merging is forbidden across paragraph,
list-item, or `<br>` boundaries, and whenever formatting or supported semantic
attributes differ. Normalization must not mutate text or whitespace.
Acceptance compares the Canonical Run structure rather than source HTML node
count.

## Baseline Observation

Before V03-01 implementation, the public `check` command already returns
`PASS` for this fixture with no diagnostics. This proves Contract syntax
acceptance only; it does not prove the required native text structure or visual
fidelity. Installed OfficeCLI `1.0.148` reports native paragraph properties for
`list`, `level`, `marginLeft`, and `indent`, including automatic numbered-list
schemes and readback.
