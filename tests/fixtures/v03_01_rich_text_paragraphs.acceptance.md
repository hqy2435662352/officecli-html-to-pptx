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
- `tests/fixtures/v03_01_negative/` supplies the neighbouring negative fixture
  for every rejection code the executable list authority declares
  (`nested_list`, `list_item_hard_break`, `multi_paragraph_list_item`). Each is
  one small deterministic 1920x1080 one-slide Author input with no external
  resource, and `tests/test_v03_01_acceptance.py` fails if a declared rejection
  code has no fixture.

## Acceptance Checklist

### Public preflight and capability authority

- [x] `capabilities --json` declares the supported V03-01 text/paragraph surface
      from the same authority used by Contract checking and lowering.
      Evidence: `capabilities --json` → `PASS`; `data.contract` is byte-for-byte
      `author_capability_manifest()` and carries `mixed_run_surface`,
      `paragraph_layout_surface` (including `soft_wrap`) and `list_surface`.
      The declaration is the consumed one: `mixed_run_surface.inline_elements`
      equals `SUPPORTED_INLINE_ELEMENTS` equals the lowering's inline tag set;
      `paragraph_layout_surface()` is the exported function the checker and the
      lowering's `_resolve_text_alignment` use; `list_surface()` publishes the
      marker presets, levels, `paragraph_properties`
      (`indent/level/list/marginLeft`) and the three rejection codes the checker
      enforces. `tests/test_v03_01_acceptance.py::
      test_the_declared_surfaces_are_the_ones_checking_and_lowering_consume`.
- [x] `doctor --json` passes on the accepted Windows runtime.
      Evidence: `doctor --json` → `PASS`, no diagnostics; platform `Windows`,
      Playwright `1.62.0`, Chromium revision `1234`,
      `officecli.discovered_version = 1.0.148` (`>=1.0.147`), `compatible: true`.
- [x] `check <fixture> --json` returns `PASS` with no unsupported visible content.
      Evidence: `check` → `PASS`, `diagnostics: []`, no CSS classification is
      `unsupported`.
- [x] A neighboring negative fixture for each newly rejected boundary returns a
      stable `BLOCK` diagnostic with source context; no silent omission occurs.
      Evidence: three committed fixtures, one stable code each, with the
      offending DOM node as `source_object` (table below); `check` and `build`
      both return exit class 2 and publish nothing.

### Build and native editability

- [x] `build <fixture> <fresh-output> --json` produces a new one-slide Artifact
      Pair and returns `VISUAL_REVIEW_REQUIRED`.
      Evidence: build id `141bbcab-de13-47f0-b411-dfdb64b826e7`,
      `.scratch/v03-01/ticket-06/v03.pptx` +
      `.scratch/v03-01/ticket-06/v03.evidence/`, 1 slide, 8 evidence JSON files
      and one Comparison Image; a second `build` to the same target returns
      `BLOCK`/`artifact_exists` and leaves every byte of the first pair
      unchanged.
- [x] The PPTX opens and the authored text remains native PowerPoint text, not a
      page image, object screenshot, SVG text, or per-line textbox flattening.
      Evidence: `officecli get <pptx> /slide[1] --depth 6 --json` reports only
      `slide`, `textbox`, `shape`, `paragraph`, `run` nodes; the PPTX has no
      `ppt/media/*` part and `ppt/slides/slide1.xml` has no `<p:pic`/`<a:blip`;
      object kind counts are `{"textbox": 6, "shape": 4}` for 10 authored
      elements (6 text blocks + 4 cards).
- [x] `#mixed-runs` maps to one native text-bearing object with independently
      editable runs whose family, size, bold, italic, color, and underline match
      the fixture. Evidence: `slide-001-textbox-003`, bounds
      `[85.0, 125.0, 350.0, 117.5]` pt, paragraph 1 = 7 runs
      `['常规 Regular · ', '粗体 Bold', ' · ', '斜体 Italic', ' · ', '下划线 Underline', ' · 数字 2026 · emoji 🚀']`
      read back with Georgia/17pt/bold, 14pt/italic, single underline and the
      authored colors `#0F6B78`, `#9A3412`, `#4338CA`.
- [x] Hard-break paragraphs, the empty paragraph, and source order survive
      OfficeCLI readback. Evidence: `slide-001-textbox-005` = 5 paragraphs
      `['跨段样式 A', 'Cross-break style B', '', 'Second paragraph after an empty paragraph.', '第三段：显式换行后仍可编辑。']`,
      object text `跨段样式 A\nCross-break style B\n\nSecond paragraph after an empty paragraph.\n第三段：显式换行后仍可编辑。`,
      read back in the same order.
- [x] The soft-wrapped source paragraph remains one authored text object;
      Chromium's visual lines are preserved without materially changing its
      measured bounds or global font size. Evidence: `slide-001-textbox-007`,
      bounds `[85.0, 320.0, 325.0, 110.0]` pt, `15.5pt`, 3 paragraphs equal to
      the 3 measured visual lines, and re-joining them reproduces the authored
      paragraph text exactly.
- [x] Unicode range writes remain aligned after `🚀` and `2️⃣`; later runs do not
      inherit the wrong formatting. Evidence: the emoji run is exactly
      `' · 数字 2026 · emoji 🚀'` (21 UTF-16 code units) and the ordered item is
      exactly `'第二步 2️⃣'` (7 units); a focused input with a bold run after the
      keycap reads back as `['第二步 2️⃣ ', '加粗 Bold']` with bold
      `[False, True]` and colors `['#24324A', '#B91C1C']` (the formatted run
      starts at UTF-16 offset 8).
- [x] Every native run is paragraph-local. A styled inline element crossing a
      `<br>` is split into one run per paragraph with the same resolved
      formatting; no normalized run contains `\n` and no range includes the
      paragraph separator. Evidence: `slide-001-textbox-005` paragraphs 1 and 2
      are each one bold `#9A3412` run; the empty paragraph carries no run; across
      the whole slide no run text contains `\n` and each paragraph's run UTF-16
      lengths sum to its own text length.
- [x] Adjacent runs in the same paragraph and list item with identical resolved
      formatting and supported semantic attributes normalize to one Canonical
      Run. The `North` + ` Africa` case reads back as exactly `North Africa`
      without a source-node boundary or whitespace mutation. Evidence:
      `slide-001-textbox-003` paragraph 2 = 2 runs
      `['Canonical: ', 'North Africa']` with Georgia/15pt/bold `#0F6B78`.
- [x] Canonical Run normalization never crosses a paragraph, list-item, or
      `<br>` boundary and never merges formatting or supported semantic
      attribute differences. Evidence: declared `forbidden_across` is
      `["paragraph", "list_item", "hard_break"]`; `#unordered-list` and
      `#ordered-list` each keep two identically formatted items as two
      paragraphs with one run each.
- [x] `<ul>` lowers to native PowerPoint bullet paragraphs and `<ol>` lowers to
      native automatic-number paragraphs; literal `•` or `1.` text prefixes do
      not satisfy this requirement. Evidence: readback
      `list=bullet` with `a:buChar char="•"` and `list=numbered` with
      `a:buAutoNum type="arabicPeriod"`; no `U+2022` appears in any object or run
      text.
- [x] List level and indentation remain native paragraph properties and survive
      OfficeCLI readback. Evidence: every item reads back
      `level=0`, `marginLeft=21pt`, `indent=-13.5pt`; item 1 also carries the
      authored `margin-bottom: 14px` as native `spaceAfter=7pt`.
- [x] Each top-level HTML `ul` or `ol` maps to one Native List Textbox, and each
      direct `li` maps to one Native List Paragraph inside that textbox.
      Evidence: `slide-001-textbox-009` (`slide[1]/ul[9]`, bounds
      `[540.0, 317.5, 150.0, 43.4375]`) with 2 paragraphs
      `['原生项目符号', '缩进与段落边界']`, and `slide-001-textbox-010`
      (`slide[1]/ol[10]`, bounds `[725.0, 317.5, 135.0, 43.4375]`) with 2
      paragraphs `['First step', '第二步 2️⃣']`.
- [x] No list item is emitted as a separate textbox. Evidence: the manifest
      object inventory is exactly ten objects — one per authored element — and no
      object has a `source_object` below a list source path.

### Structural evidence

- [x] Manifest object identity, kind, bounds, text, paragraph count, run count,
      and key run/paragraph formatting agree with independent expected literals.
      Evidence: 10/10 objects agree on name, kind, source identity, bounds and
      text; 19 native paragraphs and 21 Canonical Runs
      (`1 + 1 + 2 + 1 + 5 + 1 + 3 + 1 + 2 + 2` paragraphs,
      `1 + 0 + 9 + 0 + 4 + 0 + 3 + 0 + 2 + 2` runs); each native `lineSpacing`
      equals the authored CSS `line-height x 0.75`
      (`0.863x`, `1.087x`, `1.012x`, `1.013x`) within the declared `0.001x`
      precision.
- [x] OfficeCLI readback proves the native object, paragraph, run, marker, and
      indentation structure required by this ticket. Evidence: readback of all
      ten objects agrees with the manifest on kind, bounds and text; paragraph
      and run texts, run formatting, `list`, `bulletRaw`, `level`, `marginLeft`
      and `indent` agree with the independent literals.
- [x] `officecli validate` passes. Evidence:
      `Validation passed: no errors found.` (`success: true`).
- [x] `officecli view <pptx> issues` contains no unclassified severe issue.
      Evidence: `{"count": 0, "issues": []}` and the published `issues.json`
      contains only `Found 0 issue(s):` — no severe, structural or schema line.
- [x] Existing V0.2 successful fixtures retain their output semantics. Evidence:
      the full suite (including `tests/test_algeria_full_deck.py`, which really
      compiles the external Algeria deck on this machine) passes unchanged; no
      V0.2 test was edited and no product behaviour changed for this ticket.

### Visual Review and finalization

- [x] The Evidence Bundle contains the single required Comparison Image and a
      review record associated with the same build id and hashes. Evidence:
      `comparisons/slide-001.png` only (sha256
      `a0fd3eb8d3fa05adcf6912f56b1f65279d52637135394e812c6d875550397091`), and
      `visual-review.json` binds `build_id`
      `141bbcab-de13-47f0-b411-dfdb64b826e7` with Author HTML
      `25061c706aa6ee59501e529753dd20748d48293d1725cd0ff9bce9a670ac8d9d` and
      PPTX `1e3d08c96e991fea9344825c54988e8a18cb4c53c0bbd5d8d7799dcc88d64f4b`,
      identical to the hashes in `result.json`.
- [x] Visual Review checks mixed-run appearance, hard/empty paragraphs,
      line-height/spacing, soft-wrap line placement, list markers, and indentation.
      Evidence: measurement-based review of the one Comparison Image — whole
      panel 48x27 tile diff `1.0622` ink ratio with `0 html-only / 0 pptx-only`
      tiles, per-object region probe for all six authored regions, horizontal
      marker-column probe for both lists, plus the structural readback above.
- [x] No material clipping, overlap, missing content, reordered text, or visible
      line-placement regression exists. Evidence: `0 html-only / 0 pptx-only`
      tiles; every region's ink ratio and vertical ink centroid is identical to
      the accepted V03-01-04 measurement; markers and item text edges are within
      1 px of the browser; the only recorded finding is minor (the released V0.2
      line-spacing projection of the 13.5pt list items) and no finding carries a
      material category.
- [x] `finalize --json` mechanically returns `PASS` or `PASS_WITH_FINDINGS`; any
      Major Finding keeps the artifact at `REVISION_REQUIRED`. Evidence:
      `finalize` → `PASS_WITH_FINDINGS` for the authored record (0 major / 1
      minor, exit 0, `finalization.json` written); the same bundle with a Major
      finding authored in a relocated copy → `REVISION_REQUIRED` with a blocking
      `review_major_finding` (exit 2), while the published pair stays accepted.

### Proportional verification

- [x] One red-to-green public-seam tracer bullet is completed at a time.
      Evidence: the four slice tickets landed as separate commits
      (`5dfce7c`, `3f17701`, `ef68723`, `b7125ea`); this integration ticket adds
      only the negative fixtures, the unified acceptance module, and the
      committed evidence.
- [x] Focused tests, the existing relevant suite, `compileall`, and
      `git diff --check` pass after implementation. Evidence:
      `tests/test_v03_01_acceptance.py` 28 passed;
      `.\.venv\Scripts\python.exe -m pytest -q` 155 passed;
      `.\.venv\Scripts\python.exe -m compileall -q src` clean;
      `git diff --check` clean.
- [x] A real fresh PPTX plus readback and visual evidence is retained as the
      ticket's acceptance artifact; an exit code alone is insufficient.
      Evidence: `.scratch/v03-01/ticket-06/` retains the raw
      `capabilities`/`doctor`/`check`/`build`/`finalize` envelopes, the fresh
      `v03.pptx` and `v03.evidence/`, `slide1.json` (OfficeCLI readback),
      `validate.json`, `issues.json`, the authored `visual-review.json`,
      `finalization.json`, the measurement-based `visual_review.py` output, the
      `region_probe.json` comparison against V03-01-04, the marker-column probe,
      and `REPORT.md`. `.scratch/` is gitignored, so this checklist is the
      committed record of those measurements.

## Acceptance Evidence (V03-01-05, one fresh build)

Commands, exactly as run (installed CLI in `.venv`, OfficeCLI `1.0.148`):

```text
.\.venv\Scripts\officecli-html-to-pptx.exe capabilities --json
.\.venv\Scripts\officecli-html-to-pptx.exe doctor --json
.\.venv\Scripts\officecli-html-to-pptx.exe check  tests\fixtures\v03_01_rich_text_paragraphs.html --json
.\.venv\Scripts\officecli-html-to-pptx.exe check  tests\fixtures\v03_01_negative\<code>.html --json
.\.venv\Scripts\officecli-html-to-pptx.exe build  tests\fixtures\v03_01_rich_text_paragraphs.html .scratch\v03-01\ticket-06\v03.pptx --json
.\.venv\Scripts\officecli-html-to-pptx.exe build  tests\fixtures\v03_01_negative\<code>.html .scratch\v03-01\ticket-06\blocked_<code>.pptx --json
officecli get      .scratch\v03-01\ticket-06\v03.pptx "/slide[1]" --depth 6 --json
officecli validate .scratch\v03-01\ticket-06\v03.pptx --json
officecli view     .scratch\v03-01\ticket-06\v03.pptx issues --json
.\.venv\Scripts\officecli-html-to-pptx.exe finalize .scratch\v03-01\ticket-06\v03.evidence --json
```

Object inventory (`officecli get` readback, `--depth 6`):

| object | source | kind | bounds (pt) | paragraphs | runs |
| --- | --- | --- | --- | --- | --- |
| `slide-001-textbox-001` | `slide[1]/div[1]` | textbox | 60, 35, 840, 45 | 1 | 1 |
| `slide-001-shape-002` | `slide[1]/div[2]` | shape | 60, 100, 400, 170 | 1 (native empty body) | 0 |
| `slide-001-textbox-003` | `slide[1]/div[3]` | textbox | 85, 125, 350, 117.5 | 2 | 7 + 2 |
| `slide-001-shape-004` | `slide[1]/div[4]` | shape | 500, 100, 400, 170 | 1 (native empty body) | 0 |
| `slide-001-textbox-005` | `slide[1]/div[5]` | textbox | 525, 122.5, 350, 122.5 | 5 | 1 + 1 + 0 + 1 + 1 |
| `slide-001-shape-006` | `slide[1]/div[6]` | shape | 60, 295, 400, 180 | 1 (native empty body) | 0 |
| `slide-001-textbox-007` | `slide[1]/div[7]` | textbox | 85, 320, 325, 110 | 3 (visual lines) | 3 |
| `slide-001-shape-008` | `slide[1]/div[8]` | shape | 500, 295, 400, 180 | 1 (native empty body) | 0 |
| `slide-001-textbox-009` | `slide[1]/ul[9]` | textbox | 540, 317.5, 150, 43.4375 | 2 | 2 |
| `slide-001-textbox-010` | `slide[1]/ol[10]` | textbox | 725, 317.5, 135, 43.4375 | 2 | 2 |

Native list properties (readback, both items of each list):

| object | marker property | native marker | level | marginLeft | indent | spaceAfter | lineSpacing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `slide-001-textbox-009` | `list=bullet` | `a:buChar char="•"` | 0 | 21pt | -13.5pt | 7pt / none | 1.013x |
| `slide-001-textbox-010` | `list=numbered` | `a:buAutoNum type="arabicPeriod"` | 0 | 21pt | -13.5pt | 7pt / none | 1.013x |

Negative fixtures (neighbouring one-slide Author inputs):

| code | fixture | `source_object` | `check` | `build` |
| --- | --- | --- | --- | --- |
| `nested_list` | `tests/fixtures/v03_01_negative/nested_list.html` | `/html/body/main/section/ul/li/ul` | `BLOCK` (exit 2) | `BLOCK`, no `.pptx`, no `.evidence`, no staging directory |
| `list_item_hard_break` | `tests/fixtures/v03_01_negative/list_item_hard_break.html` | `/html/body/main/section/ul/li/br` | `BLOCK` (exit 2) | `BLOCK`, no `.pptx`, no `.evidence`, no staging directory |
| `multi_paragraph_list_item` | `tests/fixtures/v03_01_negative/multi_paragraph_list_item.html` | `/html/body/main/section/ul/li/p[1]` | `BLOCK` (exit 2) | `BLOCK`, no `.pptx`, no `.evidence`, no staging directory |

Measurement-based Visual Review of the one Comparison Image (this build vs the
accepted V03-01-04 numbers in `.scratch/v03-01/verify-05/region_probe.json`):

| region | ink ratio | vertical centroid delta (px) | V03-01-04 ratio / delta |
| --- | --- | --- | --- |
| title | 0.919 | -5.04 | 0.919 / -5.04 |
| `#mixed-runs` | 1.166 | -1.85 | 1.166 / -1.85 |
| `#paragraphs` | 1.132 | -4.63 | 1.132 / -4.63 |
| `#soft-wrap` | 1.007 | -10.89 | 1.007 / -10.89 |
| `#unordered-list` | 0.945 | -4.34 | 0.945 / -4.34 |
| `#ordered-list` | 0.860 | -10.46 | 0.860 / -10.46 |

Whole-panel 48x27 tile diff: ink ratio `1.0622`, `0` html-only tiles, `0`
pptx-only tiles. Marker columns: browser bullet `1096-1105` vs native
`1096-1104` with item text at `1122` vs `1123`; browser number
`1467-1473`/`1480-1483` vs native `1467-1475`/`1480-1484` with item text at
`1494` vs `1494`.

Artifact Pair and finalization:

| item | value |
| --- | --- |
| build id | `141bbcab-de13-47f0-b411-dfdb64b826e7` |
| Author HTML sha256 | `25061c706aa6ee59501e529753dd20748d48293d1725cd0ff9bce9a670ac8d9d` |
| PPTX sha256 | `1e3d08c96e991fea9344825c54988e8a18cb4c53c0bbd5d8d7799dcc88d64f4b` |
| Comparison Image sha256 | `a0fd3eb8d3fa05adcf6912f56b1f65279d52637135394e812c6d875550397091` |
| `validate` | `PASS` — `Validation passed: no errors found.` |
| `view … issues` | `count = 0`, `issues = []` |
| `finalize` | `PASS_WITH_FINDINGS` (0 major / 1 minor, exit 0) |
| Major probe (relocated copy) | `REVISION_REQUIRED`, blocking `review_major_finding`, exit 2 |

## Verification

```text
.\.venv\Scripts\python.exe -m pytest -q                                  155 passed
.\.venv\Scripts\python.exe -m compileall -q src                          clean
git diff --check                                                         clean
.\.venv\Scripts\python.exe -m pytest tests\test_v03_01_acceptance.py -q   28 passed
```

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
