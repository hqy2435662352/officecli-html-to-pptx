# V0.4.2 representative acceptance — PASS_WITH_FINDINGS (independent review)

> **The independent Gate 3 review reached `PASS_WITH_FINDINGS`** and it is the bundle's verdict; the machine verdict is struck below. See `GATE3-REVIEW-4.md` and the reviews beside it: they name every difference against the source page, located by `(source slot, source page, source object)`.
>
> The machine evidence below is the evidence of the run that was measured and is unchanged.


Authoritative acceptance of the V0.4.2 representative-projection slice (ticket #18), run over the frozen ten-page corpus through the one selected-page seam (`gate_projected_author_html`).

## 1. Verdict and its evidence basis

~~**PASS_WITH_FINDINGS** (gate outcome `PASS_WITH_FINDINGS`, `published=True`, `accepted=True`), reached in 400.0s.~~ **superseded by the independent review — see `GATE3-REVIEW-4.md`**

| binding | value |
|---|---|
| commit | `f5fd4e8ac8a285ed222e37782dd8b31e526ced80 (working tree dirty: cceptance/v0.4.2/acceptance-report.md, scripts/run_v042_acceptance.py)` |
| run id (gate report sha256) | `43753269658f235b89fb9ce7d8cb9e1be78ed2d03472383400b53eeeebbdb1db` |

The report, the source map, the artifact manifest and the review package all belong to the run id above: it is the digest of the gate's own verdict document, so a reader can check that they describe one run without a registry to consult. The commit is the revision the verdict is about.

The verdict is the gate's own derived outcome. It is *not* inferred from a process exit code, from the Author Contract status, from OfficeCLI validation, or from the screenshots below. The evidence set that produced it is:

| evidence | value |
|---|---|
| selected pages | 10 |
| projected pages | 10 |
| blocked pages | 0 |
| source objects with one disposition | 257 |
| canonical-editable | 210 |
| locked-visual-proxy | 28 |
| base-only-semantic | 19 |
| unsupported | 0 |
| unresolved | 0 |
| material deltas | 0 |
| retained findings | 27 |
| scope evidence | 33 |
| proxy isolation proofs passed | 37 |
| proxy isolation proofs failed | 0 |
| text readbacks matched | 172 / 172 |
| style readbacks matched | 172 / 172 |
| native tables passed | 10 / 10 |
| blocking diagnostics | 0 |
| hashed artifacts (gate) | 87 |
| Author Contract (`author`) | PASS |

The unchanged `author` Contract reports **PASS** with 0 diagnostic(s). It is corroboration, not the verdict.

## 2. Corpus, selection order and coverage purpose

The frozen selection order is exactly `source-a:2, source-a:5, source-a:12, source-a:30, source-b:3, source-b:9, source-c:2, source-c:21, probe-a, probe-b`. The eight real pages are drawn from three private source decks, each named by an opaque slot (`source-a pages [2, 5, 12, 30]`, `source-b pages [3, 9]`, `source-c pages [2, 21]`); the two synthetic probes follow and are not real pages. `probe-a` contributes one page.

| # | page | source page | composition | coverage purpose |
|---|---|---|---|---|
| 1 | source-a page 2 | 2 | 25 textbox, 6 shape (3 ellipse, 3 rightArrow), 2 group, 4 connector, 4 picture; 1 source overflow | groups with owned connectors, native ellipse/rightArrow, overlay KPI text over a filled shape, source-inherent overflow |
| 2 | source-a page 5 | 5 | 2 picture, 8 shape, 1 table | cropped picture (srcRect), compound product picture, native 6x4 table |
| 3 | source-a page 12 | 12 | 44 shape, 1 table; 13 source issues | text-dense control page: paragraphs, numbered options, font metrics, gradient fills, many source-inherent overflows |
| 4 | source-a page 30 | 30 | 16 picture, 30 shape, 7 connector, 4 textbox; highest object count | high object density, many pictures, top-level connectors, repeated brand matrix |
| 5 | source-b page 3 | 3 | 3 picture, 12 shape, 3 table | three repeated cards with transparent pictures and three native 6x5 tables on one page |
| 6 | source-b page 9 | 9 | 2 group, 21 shape, 1 table | picture group against an opaque panel, native 8x5 table |
| 7 | source-c page 2 | 2 | 3 picture, 4 shape, 3 table, 16 textbox | the negative control: structural issues read clean while the source picture already shows a title overlap |
| 8 | source-c page 21 | 21 | 2 picture, 8 shape, 2 table | wide native 10x5 table isolated from picture noise, shape container |
| 9 | synthetic probe A | 1 | 1 slide: a text-free filled rect with three independent sibling textboxes painted inside its rectangle, one text-free ellipse, and one text-free rightArrow with one independent sibling textbox painted inside it | proxy/overlay isolation: no sibling text may be embedded in any raster payload, and no wording may appear twice in the rebuilt deck |
| 10 | synthetic probe B | 1 | 2 slides: mixed runs, a hard break, an empty paragraph, nested bullet and numbering paragraphs, explicit Latin/CJK fonts, theme-token text, rect/roundRect/ellipse/rightArrow; one group owning a shape and a connector | rich text semantics and the locked container boundary: mixed runs, hard break, empty paragraph, bullet nesting, numbering, Latin/CJK fonts, theme-token evidence, fixed numeric strings, and one group with a bound connector represented exactly once |

### Page-level scope notes

- **source-a page 2**: The two groups are locked container boundaries: their children and the four connectors they own are represented inside the container proxy and are never emitted again as siblings. The KPI text painted over the filled ellipse is the V0.4.1 proxy-isolation risk and must stay independent. The one text overflow is the source's own condition and stays a retained finding.
- **source-a page 5**: Inherited master/layout branding is not reconstructed, so the rebuilt page is painted on a blank layout; that omission is page-level scope evidence, never slide-owned projection loss. The cropped picture's source rectangle is baked into the emitted media, which is recorded.
- **source-a page 12**: This page carries the corpus's highest source-issue count and its gradient fills, and it is the only selected page not dominated by pictures. Every issue is the source's own; none is introduced by the projection. Gradient-filled objects are not canonical-editable and keep their locked or base-only disposition.
- **source-a page 30**: The densest page in the corpus. Every connector has exactly one disposition in the ledger, and the repeated brand cells exercise identity collision between near-identical objects.
- **source-b page 3**: Three tables on one page exercise per-table identity and independent row/column and cell-text readback. The transparent pictures must keep their transparency rather than being flattened onto a panel colour.
- **source-b page 9**: The group is a locked container boundary. This page differs from source-a page 5 in what it tests: that page exercises a cropped picture, this one exercises a container, and the two must not be conflated.
- **source-c page 2**: This page exists to stop the machine gate being read as visual acceptance: OfficeCLI reports no issue on it, yet the source page itself shows an overlapping title. A structural PASS here is not evidence of visual fidelity.
- **source-c page 21**: The wide table isolates the table path from picture interference, so a table regression cannot be masked by an unrelated picture difference.
- **synthetic probe A**: Every object on this probe is canonical-editable and no proxy is emitted, so the rebuilt deck must contain no raster payload for this page at all. The overlay wording is asserted to appear exactly once in the rebuilt deck; if the rect, the ellipse or the arrow were ever replaced by a picture, this probe's unaccounted picture count would show it.
- **synthetic probe B**: OfficeCLI reports no inheritance source for the theme run's colour, so the gate classifies it canonical-editable and the projection emits it without a colour declaration; the theme token is preserved in the source and in the projection's evidence, and no semantic token round trip is claimed. The group is one locked container boundary whose child shape and connector are represented once inside it and never emitted again as siblings.

## 3. Source immutability

- each private source deck was hashed **separately**, before capture and again after the run.

| source slot | pages | before vs after |
|---|---|---|
| `source-a` | [2, 5, 12, 30] | **identical** |
| `source-b` | [3, 9] | **identical** |
| `source-c` | [2, 21] | **identical** |

Every source deck's own before/after pair is compared on its own: **3/3 identical**. One combined verdict would not have shown which deck, if any, moved.
- the hash values themselves are **withheld**: a private deck's hash is private material under the spec, so this report records the verification verdict rather than the digest. The local-only record `acceptance/v0.4.2/local/source-verification.json` (gitignored) holds the values for a reviewer working on this machine.
- the run targets the source decks with **zero** OfficeCLI write operations: they are read with `get`, `view` and `issues` only, and the gate re-hashes each of them after publication.

## 4. Per-page results

`rebuilt issues` is the count of OfficeCLI issue records the rebuilt deck reports for that page.

| out | page | source page | objects | canonical | locked | base-only | unsup | unres | src issues | rebuilt issues | text readbacks | tables | proxies | failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | source-a:2 | 2 | 41 | 33 | 6 | 2 | 0 | 0 | 3 | 0 | 29 | 0 | 4 | — |
| 2 | source-a:5 | 5 | 11 | 10 | 0 | 1 | 0 | 0 | 6 | 0 | 7 | 1 | 1 | — |
| 3 | source-a:12 | 12 | 45 | 42 | 3 | 0 | 0 | 0 | 13 | 3 | 41 | 1 | 3 | — |
| 4 | source-a:30 | 30 | 57 | 32 | 10 | 15 | 0 | 0 | 5 | 0 | 16 | 0 | 25 | — |
| 5 | source-b:3 | 3 | 18 | 18 | 0 | 0 | 0 | 0 | 4 | 0 | 12 | 3 | 0 | — |
| 6 | source-b:9 | 9 | 28 | 22 | 6 | 0 | 0 | 0 | 8 | 0 | 21 | 1 | 2 | — |
| 7 | source-c:2 | 2 | 26 | 26 | 0 | 0 | 0 | 0 | 0 | 0 | 20 | 3 | 0 | — |
| 8 | source-c:21 | 21 | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 11 | 1 | 0 | — |
| 9 | probe-a | 1 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 7 | 0 | 0 | — |
| 10 | probe-b | 1 | 12 | 8 | 3 | 1 | 0 | 0 | 1 | 0 | 8 | 0 | 2 | — |

### Disposition ledger summary (per page)

The complete ledger — one row per slide-owned source object with its source identity, ownership, disposition, reason code and evidence — is `gate/disposition-ledger.json`. Its per-page totals:

| out | page | source objects | canonical-editable | locked-visual-proxy | base-only-semantic | container-owned | unsupported | unresolved |
|---|---|---|---|---|---|---|---|---|
| 1 | source-a:2 | 41 | 33 | 6 | 2 | 4 | 0 | 0 |
| 2 | source-a:5 | 11 | 10 | 0 | 1 | 0 | 0 | 0 |
| 3 | source-a:12 | 45 | 42 | 3 | 0 | 0 | 0 | 0 |
| 4 | source-a:30 | 57 | 32 | 10 | 15 | 0 | 0 | 0 |
| 5 | source-b:3 | 18 | 18 | 0 | 0 | 0 | 0 | 0 |
| 6 | source-b:9 | 28 | 22 | 6 | 0 | 4 | 0 | 0 |
| 7 | source-c:2 | 26 | 26 | 0 | 0 | 0 | 0 | 0 |
| 8 | source-c:21 | 12 | 12 | 0 | 0 | 0 | 0 | 0 |
| 9 | probe-a | 7 | 7 | 0 | 0 | 0 | 0 | 0 |
| 10 | probe-b | 12 | 8 | 3 | 1 | 2 | 0 | 0 |

Every source object has exactly one disposition, and every emitted object maps to exactly one source object: 257 unique source identit(ies) over 257 ledger entr(ies), 247 emitted, 10 represented by a container instead of emitted.

## 5. Material deltas

**Zero material deltas.** The rebuilt-minus-source material issue set is empty, so no rebuilt-only or materially worsened condition was found on any selected page.

## 6. Retained findings (source-inherent, not repaired)

27 retained finding(s). Each one is a condition the **source** object already carries; the gate lists them explicitly instead of counting them as repaired. The complete set is `gate/retained-findings.json`.

| condition | count |
|---|---|
| `table_cell_whitespace_placement` | 1 |
| `text_overflow` | 26 |

- out p1 `/slide[2]/shape[@id=49]` `text_overflow` → `slide-001-textbox-014`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p2 `/slide[5]/shape[@id=100085]` `text_overflow` → `slide-002-picture-011`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p2 `/slide[5]/shape[@id=100106]` `text_overflow` → `slide-002-textbox-008`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p3 `/slide[12]/shape[@id=100084]` `text_overflow` → `slide-003-textbox-017`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p3 `/slide[12]/shape[@id=100096]` `text_overflow` → `slide-003-textbox-026`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p3 `/slide[12]/shape[@id=100097]` `text_overflow` → `slide-003-textbox-027`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p3 `/slide[12]/shape[@id=100103]` `text_overflow` → `slide-003-textbox-033`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p3 `/slide[12]/shape[@id=100104]` `text_overflow` → `slide-003-textbox-034`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p3 `/slide[12]/shape[@id=100107]` `text_overflow` → `slide-003-textbox-037`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p3 `/slide[12]/shape[@id=100109]` `text_overflow` → `slide-003-textbox-039`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p3 `/slide[12]/shape[@id=100113]` `text_overflow` → `slide-003-textbox-043`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p3 `/slide[12]/shape[@id=100114]` `text_overflow` → `slide-003-textbox-044`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p4 `/slide[30]/shape[@id=100109]` `text_overflow` → `slide-004-shape-009`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p5 `/slide[3]/shape[@id=100151]` `text_overflow` → `slide-005-textbox-002`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p5 `/slide[3]/shape[@id=100155]` `text_overflow` → `slide-005-textbox-006`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p5 `/slide[3]/shape[@id=100161]` `text_overflow` → `slide-005-textbox-011`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p5 `/slide[3]/shape[@id=100167]` `text_overflow` → `slide-005-textbox-016`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[9]/shape[@id=100350]` `text_overflow` → `slide-006-textbox-003`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[9]/shape[@id=100359]` `text_overflow` → `slide-006-textbox-010`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[9]/shape[@id=100364]` `text_overflow` → `slide-006-textbox-015`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[9]/shape[@id=100365]` `text_overflow` → `slide-006-textbox-016`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[9]/shape[@id=100367]` `text_overflow` → `slide-006-textbox-018`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[9]/shape[@id=100368]` `text_overflow` → `slide-006-textbox-019`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[9]/shape[@id=100370]` `text_overflow` → `slide-006-textbox-021`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[9]/shape[@id=100371]` `text_overflow` → `slide-006-textbox-022`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p10 `/slide[1]/shape[@id=100003]` `text_overflow` → `slide-010-picture-004`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[9]/table[@id=100362]` `table_cell_whitespace_placement` → `slide-006-table-013`: 2 table cell(s) carry the same characters and the same line structure but place their spaces differently; the difference is reported here and does not block acceptance

## 7. Scope evidence (master/layout/inherited paint)

33 scope-evidence record(s). These are findings and omissions about values the slide does not own; they are never reported as repaired slide-owned objects.

| condition | count | mapped |
|---|---|---|
| `inherited_paint_omission` | 19 | 19 |
| `slide_field_not_evaluated` | 14 | 0 |

The complete set is `gate/scope-evidence.json`. A representative record of each condition:

- `slide_field_not_evaluated` (mapped=False) `—` on source page 2: the finding names the slide (master) rather than a slide-owned object, so it is inherited or slide-level scope evidence and is never mapped onto a rebuilt object
- `inherited_paint_omission` (mapped=True) `—` on source page None: the source object's visible appearance depends on a value the slide does not own, so the rebuilt deck legitimately omits that inherited paint; the object is reported as base-only scope evidence and never as a repaired slide-owned object

## 8. Proxy isolation proofs

| proxy | source object | disposition | raster | density | guard band | paint fraction | passed |
|---|---|---|---|---|---|---|---|
| `slide-001-picture-007` | `/slide[2]/group[@id=88]` | locked-visual-proxy | 121x19 | 2.00475 | 2 | 0.018116 | True |
| `slide-001-picture-010` | `/slide[2]/group[@id=40]` | locked-visual-proxy | 121x19 | 2.00475 | 2 | 0.018116 | True |
| `slide-001-picture-028` | `/slide[2]/shape[@id=8]` | base-only-semantic | 1705x123 | 2.00034 | 2 | 0.000000 | True |
| `slide-001-picture-029` | `/slide[2]/shape[@id=9]` | base-only-semantic | 426x127 | 2.00047 | 2 | 0.000000 | True |
| `slide-002-picture-011` | `/slide[5]/shape[@id=100085]` | base-only-semantic | 192x309 | 2.00066 | 2 | 0.000000 | True |
| `slide-003-picture-004` | `/slide[12]/shape[@id=100068]` | locked-visual-proxy | 886x69 | 2.00096 | 2 | 0.000000 | True |
| `slide-003-picture-007` | `/slide[12]/shape[@id=100071]` | locked-visual-proxy | 937x69 | 2.00086 | 2 | 0.000000 | True |
| `slide-003-picture-010` | `/slide[12]/shape[@id=100077]` | locked-visual-proxy | 937x69 | 2.00086 | 2 | 0.000000 | True |
| `slide-004-picture-011` | `/slide[30]/shape[@id=100111]` | locked-visual-proxy | 301x46 | 2.00135 | 2 | 0.000000 | True |
| `slide-004-picture-012` | `/slide[30]/shape[@id=100112]` | locked-visual-proxy | 301x46 | 2.00135 | 2 | 0.062319 | True |
| `slide-004-picture-013` | `/slide[30]/shape[@id=100113]` | locked-visual-proxy | 301x46 | 2.00135 | 2 | 0.000000 | True |
| `slide-004-picture-018` | `/slide[30]/shape[@id=100125]` | base-only-semantic | 320x207 | 2.00317 | 2 | 0.000000 | True |
| `slide-004-picture-022` | `/slide[30]/shape[@id=100132]` | base-only-semantic | 308x207 | 2.00000 | 2 | 0.000000 | True |
| `slide-004-picture-024` | `/slide[30]/shape[@id=100024]` | base-only-semantic | 1177x36 | 2.00017 | 2 | 0.000000 | True |
| `slide-004-picture-027` | `/slide[30]/shape[@id=9]` | base-only-semantic | 270x207 | 2.00375 | 2 | 0.000000 | True |
| `slide-004-picture-028` | `/slide[30]/connector[@id=10]` | locked-visual-proxy | 4x710 | 1.99972 | 2 | 0.000000 | True |
| `slide-004-picture-029` | `/slide[30]/connector[@id=11]` | locked-visual-proxy | 4x681 | 1.99911 | 2 | 0.000000 | True |
| `slide-004-picture-030` | `/slide[30]/connector[@id=15]` | locked-visual-proxy | 4x683 | 2.00088 | 2 | 0.000000 | True |
| `slide-004-picture-032` | `/slide[30]/shape[@id=22]` | base-only-semantic | 276x207 | 1.99926 | 2 | 0.000000 | True |
| `slide-004-picture-034` | `/slide[30]/shape[@id=24]` | base-only-semantic | 293x207 | 2.00277 | 2 | 0.000000 | True |
| `slide-004-picture-037` | `/slide[30]/shape[@id=28]` | base-only-semantic | 211x207 | 2.00097 | 2 | 0.000000 | True |
| `slide-004-picture-040` | `/slide[30]/shape[@id=38]` | base-only-semantic | 270x207 | 2.00375 | 2 | 0.000000 | True |
| `slide-004-picture-042` | `/slide[30]/shape[@id=39]` | base-only-semantic | 118x62 | 1.99825 | 2 | 0.000000 | True |
| `slide-004-picture-043` | `/slide[30]/shape[@id=40]` | base-only-semantic | 118x62 | 1.99825 | 2 | 0.000000 | True |
| `slide-004-picture-044` | `/slide[30]/shape[@id=41]` | base-only-semantic | 276x207 | 1.99926 | 2 | 0.000000 | True |
| `slide-004-picture-045` | `/slide[30]/shape[@id=42]` | base-only-semantic | 293x207 | 2.00277 | 2 | 0.000000 | True |
| `slide-004-picture-048` | `/slide[30]/connector[@id=45]` | locked-visual-proxy | 4x688 | 1.99942 | 2 | 0.000000 | True |
| `slide-004-picture-050` | `/slide[30]/shape[@id=48]` | base-only-semantic | 316x267 | 2.00321 | 2 | 0.000000 | True |
| `slide-004-picture-052` | `/slide[30]/shape[@id=50]` | base-only-semantic | 118x62 | 1.99825 | 2 | 0.000000 | True |
| `slide-004-picture-053` | `/slide[30]/connector[@id=52]` | locked-visual-proxy | 1389x5 | 2.00014 | 2 | 0.000718 | True |
| `slide-004-picture-054` | `/slide[30]/connector[@id=53]` | locked-visual-proxy | 1371x5 | 2.00029 | 2 | 0.196143 | True |
| `slide-004-picture-055` | `/slide[30]/connector[@id=54]` | locked-visual-proxy | 1372x6 | 1.99971 | 2 | 0.153706 | True |
| `slide-004-picture-056` | `/slide[30]/shape[@id=55]` | base-only-semantic | 316x267 | 2.00321 | 2 | 0.000000 | True |
| `slide-006-picture-023` | `/slide[9]/group[@id=100381]` | locked-visual-proxy | 296x180 | 2.00233 | 2 | 0.000000 | True |
| `slide-006-picture-024` | `/slide[9]/group[@id=100383]` | locked-visual-proxy | 296x180 | 2.00233 | 2 | 0.000000 | True |
| `slide-010-picture-004` | `/slide[1]/shape[@id=100003]` | base-only-semantic | 244x89 | 2.00000 | 2 | 0.207692 | True |
| `slide-010-picture-009` | `/slide[1]/group[@id=100008]` | locked-visual-proxy | 444x304 | 2.00000 | 2 | 0.000000 | True |

37 proof(s), 37 passed. Every locked proxy carries the gate's five isolation facts: target survival, raster density, guard band, target bounds and contamination.

**4 of 37 proof(s) are of a proxy whose raster is nothing but its own background** (`paint_fraction` 0.0, so no paint of the locked object was measured in the crop): `slide-004-picture-028`, `slide-004-picture-029`, `slide-004-picture-030`, `slide-004-picture-048`. The gate's isolation facts are satisfied for these proxies -- density, guard band, bounds and contamination are measured and correct -- but they do not establish that the locked object's own pixels survived, and this report does not claim that they did. Whether those objects are blank in the source is a Gate 3 question, not a structural one.

## 9. Native table checks

| page | source object | emitted | source rows×cols | rebuilt rows×cols | cells | whitespace-only cells | failures |
|---|---|---|---|---|---|---|---|
| 5 | `/slide[5]/table[@id=100190]` | `slide-002-table-007` | 6×4 | 6×4 | 24 | — | — |
| 12 | `/slide[12]/table[@id=100088]` | `slide-003-table-021` | 4×3 | 4×3 | 12 | — | — |
| 3 | `/slide[3]/table[@id=100158]` | `slide-005-table-008` | 6×5 | 6×5 | 30 | — | — |
| 3 | `/slide[3]/table[@id=100164]` | `slide-005-table-013` | 6×5 | 6×5 | 30 | — | — |
| 3 | `/slide[3]/table[@id=100170]` | `slide-005-table-018` | 6×5 | 6×5 | 30 | — | — |
| 9 | `/slide[9]/table[@id=100362]` | `slide-006-table-013` | 8×5 | 8×5 | 40 | — | — |
| 2 | `/slide[2]/table[@id=100077]` | `slide-007-table-014` | 5×7 | 5×7 | 35 | — | — |
| 2 | `/slide[2]/table[@id=100083]` | `slide-007-table-020` | 5×7 | 5×7 | 35 | — | — |
| 2 | `/slide[2]/table[@id=100089]` | `slide-007-table-026` | 5×7 | 5×7 | 35 | — | — |
| 21 | `/slide[21]/table[@id=100387]` | `slide-008-table-012` | 10×5 | 10×5 | 50 | — | — |

## 10. Text and style readback

172 independent OfficeCLI readback(s) of canonical-editable objects; 0 disagree with the source text.


## 11. OfficeCLI validation and issue records

Source deck reads:

- `src1` validate: Validation passed: no errors found.; issues: 238
- `src2` validate: Validation passed: no errors found.; issues: 110
- `src3` validate: Validation passed: no errors found.; issues: 0
- `src4` validate: Validation passed: no errors found.; issues: 0
- `src5` validate: Validation passed: no errors found.; issues: 1

Rebuilt deck reads:

- `rebuilt` `rebuilt.pptx`: Validation passed: no errors found.

- rebuilt issues: 3

## 12. Artifact manifest

The gate published 87 hashed artifacts; `gate/gate-report.json` lists every one with its sha256 and size, and `artifact-manifest.json` lists every file in this bundle the same way. Both can be re-checked against disk independently:

```powershell
Get-FileHash acceptance/v0.4.2/gate/rebuilt.pptx -Algorithm SHA256
$m = Get-Content acceptance/v0.4.2/artifact-manifest.json | ConvertFrom-Json
$m.artifacts | ForEach-Object { $h = (Get-FileHash "acceptance/v0.4.2/$($_.name)" -Algorithm SHA256).Hash.ToLower(); if ($h -ne $_.sha256) { "MISMATCH $($_.name)" } }
```

The gate's artifact list, with the hash recorded in its own report (`gate/gate-report.json` carries the same values, and re-hashing any of these files from disk must reproduce them):

| artifact | sha256 | size |
|---|---|---|
| `canonical-author.html` | `3beaebe12fafa17acbddeb60b0ebc160b51bfe140ec445ec4ce96158cb2620a4` | 42639867 |
| `disposition-ledger.json` | `0ea9869e67d78665f78898750fcc3dcad47c52bcab045e647cb39c11d9f96e1b` | 251447 |
| `material-deltas.json` | `d4990d01e9de41f6d7bce97cb1d079aff18ce0c5fc576a2117e92b9b1cfd5d3a` | 31 |
| `pages.json` | `62245ce64f375861f420027a9e6185b57b4f0bb3d14335829fbed87ca287d05c` | 509849 |
| `projection/canonical-author.html` | `3beaebe12fafa17acbddeb60b0ebc160b51bfe140ec445ec4ce96158cb2620a4` | 42639867 |
| `projection/projection-report.json` | `149b8582b2a90e9dbd4da010d96e6a1dbd282f19618ca643547f5772926403c6` | 671566 |
| `projection/proxy-src1-slide-002-007.png` | `f90ad850862b35a6655a6f64846266058e9f78fde04c01f9e87a8cf26b0e0ef0` | 487 |
| `projection/proxy-src1-slide-002-010.png` | `f90ad850862b35a6655a6f64846266058e9f78fde04c01f9e87a8cf26b0e0ef0` | 487 |
| `projection/proxy-src1-slide-002-028.png` | `90da3b87ff2ffc129d81d7e725731c353e2c6bfdf2087d6831fbd09eabfb53a5` | 21259 |
| `projection/proxy-src1-slide-002-029.png` | `4496df52e84c4b8817f35493d03043be55c24aaa821e7935eb7208d996c3d5e7` | 5631 |
| `projection/proxy-src1-slide-005-011.png` | `bf16c05721d2321183a96aa704ac36f2218b67a0685bddc44e29118a47067ef4` | 9054 |
| `projection/proxy-src1-slide-012-004.png` | `45781f35837ca0876e29cbae9e2b9da745e548fa6fff4db1911e95545776f8a2` | 502 |
| `projection/proxy-src1-slide-012-007.png` | `864aa5d97e8c3ca65f971bf48963d359cc7c7fe8e03151ea4aea17112726472a` | 519 |
| `projection/proxy-src1-slide-012-010.png` | `e114bcbc6fc4f959f301ce72aa64c250c3396bb203691438ef77df4a43eb9e62` | 535 |
| `projection/proxy-src1-slide-030-011.png` | `fa42c3b14e6629a34b84425bbc3b1781156e6a7d5d639f00f716f7ca096850eb` | 1356 |
| `projection/proxy-src1-slide-030-012.png` | `dccbd0aea3935032d56b2f6989905842c38c403b372fa37492ae3339dca1a318` | 1671 |
| `projection/proxy-src1-slide-030-013.png` | `04a64039d9773baee6076dc52ab5101911fdf2ba0f18bce1aa36e462da3ec0bc` | 1612 |
| `projection/proxy-src1-slide-030-018.png` | `6446926cd0193ce17eb5d38e751e4b31d452efecf425f3e22b9bddba35c7f6c2` | 12652 |
| `projection/proxy-src1-slide-030-022.png` | `c816f1ae9aabc0816abd897e9f88990180259a78e7fca9b915ae134763dcf698` | 14789 |
| `projection/proxy-src1-slide-030-024.png` | `6201c30542dd1e70d7a09a62d20d21114a60b11aa6f4525c863b853fcb4a7404` | 8128 |
| `projection/proxy-src1-slide-030-027.png` | `98483daf6f2970640fa4120ae792aa1447ee53155a35e541228ce0a75228755b` | 11283 |
| `projection/proxy-src1-slide-030-028.png` | `1b776c5266d61294d8af5b0a61908e66c94ac5d051e1c405c68ba2464e5f6dae` | 290 |
| `projection/proxy-src1-slide-030-029.png` | `1e049c004091d93d7c7b07c320a625d49a026635553233e308938ea4f6092c38` | 319 |
| `projection/proxy-src1-slide-030-030.png` | `75336da6e353a2dfd599db783a8e9b19a69bbdf965f1ac52ddcad67797b9f26d` | 284 |
| `projection/proxy-src1-slide-030-032.png` | `c8c76ebf78152b46258e1379d6df4b041300604d94d2035b5510a5d1ce145b9c` | 14781 |
| `projection/proxy-src1-slide-030-034.png` | `53bcb33e4258ac0587abc975711985b37ab4103ae1768428e3f5803900171d22` | 5688 |
| `projection/proxy-src1-slide-030-037.png` | `4d167bdb2f3478179aa045ef4be6419ea092aa2924c512bc657409b5f20d6bb7` | 6166 |
| `projection/proxy-src1-slide-030-040.png` | `026a8a0ca27de2b0cb8a208710249c7aa5251d4131d2f3fa2d7590552b44df3c` | 6649 |
| `projection/proxy-src1-slide-030-042.png` | `0c121e40b2e805d76b5f2b1f4000a3d6c4419a2dd563b43e81ea68dfde39ba19` | 576 |
| `projection/proxy-src1-slide-030-043.png` | `ec451dfed1ffa2ee82434977ba393d26e411b609955e1f4cf0640227ef019d2a` | 573 |
| `projection/proxy-src1-slide-030-044.png` | `2e8e2e82fc097430aaa880949f0657985796c24ca30cdf752e33e47fbf51558c` | 10064 |
| `projection/proxy-src1-slide-030-045.png` | `55b9c07892fd278b374b5eaa8056b56374920be7aae5acac42f386d72e65f141` | 6334 |
| `projection/proxy-src1-slide-030-048.png` | `da7fdd38735b92809955f9fe38c7f7e331666c0680283cb9d574dba39fad005c` | 293 |
| `projection/proxy-src1-slide-030-050.png` | `68b77f24656b52978eb5d5e007daa3f10ee1d243e4a4a234c13ea5bb4c193713` | 19572 |
| `projection/proxy-src1-slide-030-052.png` | `f2eb3807b6970b8895149098f6cc1be32373edfa856be1e690b7eabc4bc0099e` | 576 |
| `projection/proxy-src1-slide-030-053.png` | `0e3ad3e0caf7d5b5ae86ee31dce11ad6400614c993dffe76461ac6964c6e741e` | 685 |
| `projection/proxy-src1-slide-030-054.png` | `d99d247a4c86b0e49cb98b7c19e87fca65aacf20985f5e4d0651d826a435428e` | 761 |
| `projection/proxy-src1-slide-030-055.png` | `2f756780f76b040509dcd9e6e9158dbbde4b2b5e1c0007cc1c58a3e4c10c2f87` | 843 |
| `projection/proxy-src1-slide-030-056.png` | `5187bb3d179e0c9833cc491d2910dd72282a91ae8446ad4a6b967bee55fc2f50` | 12289 |
| `projection/proxy-src2-slide-009-023.png` | `fb99c8431a611b963e450ffb95c9855dbb69e9eddb73aff0680899ddb111ebf8` | 12936 |
| `projection/proxy-src2-slide-009-024.png` | `8f1b189665eecf0061d556edc09e2566f36522a45ca07c5d01cc55f3dbbfa3c8` | 18586 |
| `projection/proxy-src5-slide-001-004.png` | `bcea1a3055b82a799a06ded6c66db21b0311f2715ce59c553b9c24f9d2a82a01` | 8881 |
| `projection/proxy-src5-slide-001-009.png` | `0c1eeb7f5a662e4a421203c92d4341596326618fd0e6e13c63de7ddd0378c3c7` | 2420 |
| `projection/source-map.json` | `5bb2f6dda9c1cd2c173e9504a7785daffe1caaaa6b945fafaa29264e236f292e` | 612106 |
| `projection-report.json` | `149b8582b2a90e9dbd4da010d96e6a1dbd282f19618ca643547f5772926403c6` | 671566 |
| `proxies/proxy-src1-slide-002-007.png` | `f90ad850862b35a6655a6f64846266058e9f78fde04c01f9e87a8cf26b0e0ef0` | 487 |
| `proxies/proxy-src1-slide-002-010.png` | `f90ad850862b35a6655a6f64846266058e9f78fde04c01f9e87a8cf26b0e0ef0` | 487 |
| `proxies/proxy-src1-slide-002-028.png` | `90da3b87ff2ffc129d81d7e725731c353e2c6bfdf2087d6831fbd09eabfb53a5` | 21259 |
| `proxies/proxy-src1-slide-002-029.png` | `4496df52e84c4b8817f35493d03043be55c24aaa821e7935eb7208d996c3d5e7` | 5631 |
| `proxies/proxy-src1-slide-005-011.png` | `bf16c05721d2321183a96aa704ac36f2218b67a0685bddc44e29118a47067ef4` | 9054 |
| `proxies/proxy-src1-slide-012-004.png` | `45781f35837ca0876e29cbae9e2b9da745e548fa6fff4db1911e95545776f8a2` | 502 |
| `proxies/proxy-src1-slide-012-007.png` | `864aa5d97e8c3ca65f971bf48963d359cc7c7fe8e03151ea4aea17112726472a` | 519 |
| `proxies/proxy-src1-slide-012-010.png` | `e114bcbc6fc4f959f301ce72aa64c250c3396bb203691438ef77df4a43eb9e62` | 535 |
| `proxies/proxy-src1-slide-030-011.png` | `fa42c3b14e6629a34b84425bbc3b1781156e6a7d5d639f00f716f7ca096850eb` | 1356 |
| `proxies/proxy-src1-slide-030-012.png` | `dccbd0aea3935032d56b2f6989905842c38c403b372fa37492ae3339dca1a318` | 1671 |
| `proxies/proxy-src1-slide-030-013.png` | `04a64039d9773baee6076dc52ab5101911fdf2ba0f18bce1aa36e462da3ec0bc` | 1612 |
| `proxies/proxy-src1-slide-030-018.png` | `6446926cd0193ce17eb5d38e751e4b31d452efecf425f3e22b9bddba35c7f6c2` | 12652 |
| `proxies/proxy-src1-slide-030-022.png` | `c816f1ae9aabc0816abd897e9f88990180259a78e7fca9b915ae134763dcf698` | 14789 |
| `proxies/proxy-src1-slide-030-024.png` | `6201c30542dd1e70d7a09a62d20d21114a60b11aa6f4525c863b853fcb4a7404` | 8128 |
| `proxies/proxy-src1-slide-030-027.png` | `98483daf6f2970640fa4120ae792aa1447ee53155a35e541228ce0a75228755b` | 11283 |
| `proxies/proxy-src1-slide-030-028.png` | `1b776c5266d61294d8af5b0a61908e66c94ac5d051e1c405c68ba2464e5f6dae` | 290 |
| `proxies/proxy-src1-slide-030-029.png` | `1e049c004091d93d7c7b07c320a625d49a026635553233e308938ea4f6092c38` | 319 |
| `proxies/proxy-src1-slide-030-030.png` | `75336da6e353a2dfd599db783a8e9b19a69bbdf965f1ac52ddcad67797b9f26d` | 284 |
| `proxies/proxy-src1-slide-030-032.png` | `c8c76ebf78152b46258e1379d6df4b041300604d94d2035b5510a5d1ce145b9c` | 14781 |
| `proxies/proxy-src1-slide-030-034.png` | `53bcb33e4258ac0587abc975711985b37ab4103ae1768428e3f5803900171d22` | 5688 |
| `proxies/proxy-src1-slide-030-037.png` | `4d167bdb2f3478179aa045ef4be6419ea092aa2924c512bc657409b5f20d6bb7` | 6166 |
| `proxies/proxy-src1-slide-030-040.png` | `026a8a0ca27de2b0cb8a208710249c7aa5251d4131d2f3fa2d7590552b44df3c` | 6649 |
| `proxies/proxy-src1-slide-030-042.png` | `0c121e40b2e805d76b5f2b1f4000a3d6c4419a2dd563b43e81ea68dfde39ba19` | 576 |
| `proxies/proxy-src1-slide-030-043.png` | `ec451dfed1ffa2ee82434977ba393d26e411b609955e1f4cf0640227ef019d2a` | 573 |
| `proxies/proxy-src1-slide-030-044.png` | `2e8e2e82fc097430aaa880949f0657985796c24ca30cdf752e33e47fbf51558c` | 10064 |
| `proxies/proxy-src1-slide-030-045.png` | `55b9c07892fd278b374b5eaa8056b56374920be7aae5acac42f386d72e65f141` | 6334 |
| `proxies/proxy-src1-slide-030-048.png` | `da7fdd38735b92809955f9fe38c7f7e331666c0680283cb9d574dba39fad005c` | 293 |
| `proxies/proxy-src1-slide-030-050.png` | `68b77f24656b52978eb5d5e007daa3f10ee1d243e4a4a234c13ea5bb4c193713` | 19572 |
| `proxies/proxy-src1-slide-030-052.png` | `f2eb3807b6970b8895149098f6cc1be32373edfa856be1e690b7eabc4bc0099e` | 576 |
| `proxies/proxy-src1-slide-030-053.png` | `0e3ad3e0caf7d5b5ae86ee31dce11ad6400614c993dffe76461ac6964c6e741e` | 685 |
| `proxies/proxy-src1-slide-030-054.png` | `d99d247a4c86b0e49cb98b7c19e87fca65aacf20985f5e4d0651d826a435428e` | 761 |
| `proxies/proxy-src1-slide-030-055.png` | `2f756780f76b040509dcd9e6e9158dbbde4b2b5e1c0007cc1c58a3e4c10c2f87` | 843 |
| `proxies/proxy-src1-slide-030-056.png` | `5187bb3d179e0c9833cc491d2910dd72282a91ae8446ad4a6b967bee55fc2f50` | 12289 |
| `proxies/proxy-src2-slide-009-023.png` | `fb99c8431a611b963e450ffb95c9855dbb69e9eddb73aff0680899ddb111ebf8` | 12936 |
| `proxies/proxy-src2-slide-009-024.png` | `8f1b189665eecf0061d556edc09e2566f36522a45ca07c5d01cc55f3dbbfa3c8` | 18586 |
| `proxies/proxy-src5-slide-001-004.png` | `bcea1a3055b82a799a06ded6c66db21b0311f2715ce59c553b9c24f9d2a82a01` | 8881 |
| `proxies/proxy-src5-slide-001-009.png` | `0c1eeb7f5a662e4a421203c92d4341596326618fd0e6e13c63de7ddd0378c3c7` | 2420 |
| `proxy-isolation.json` | `5b1d651f048ef48422f48374e103f39ce5eba57508b32a853c98aae12e0bb041` | 55309 |
| `rebuilt.pptx` | `77d034b940d5c72b7def7ce5b19c6676fd9d25ab01bb8407400c274bc3b28b7b` | 31352175 |
| `retained-findings.json` | `3ab74f6274f2fa0382c999e55811d1493872a461da3e24b0e17a0cccc33d9b69` | 41174 |
| `scope-evidence.json` | `73586ba9de0a57672f271fc9fe84f25637c6248ea6177d2cbd5e818c3c4266e1` | 22398 |
| `source-map.json` | `5bb2f6dda9c1cd2c173e9504a7785daffe1caaaa6b945fafaa29264e236f292e` | 612106 |

`gate/gate-report.json` and `gate/gate-report.md` are excluded from that list because a document cannot contain its own hash; the bundle's `artifact-manifest.json` covers them instead, except for itself.

## 13. Visual records

Every page has three records: the source page render, the rebuilt page render (both through OfficeCLI's HTML render path at 1600px, so they are directly comparable), and that page's Canonical Author HTML.

| # | page | source page | before | after | author html | before px | after px | before non-background | after non-background |
|---|---|---|---|---|---|---|---|---|---|
| 1 | source-a:2 | 2 | `visual/p01-before.png` | `visual/p01-after.png` | `visual/p01-author.html` | 1280x720 | 1280x720 | 0.1108 | 0.1128 |
| 2 | source-a:5 | 5 | `visual/p02-before.png` | `visual/p02-after.png` | `visual/p02-author.html` | 1280x720 | 1280x720 | 0.5587 | 0.5311 |
| 3 | source-a:12 | 12 | `visual/p03-before.png` | `visual/p03-after.png` | `visual/p03-author.html` | 1280x720 | 1280x720 | 0.3247 | 0.3163 |
| 4 | source-a:30 | 30 | `visual/p04-before.png` | `visual/p04-after.png` | `visual/p04-author.html` | 1280x720 | 1280x720 | 0.9253 | 0.9316 |
| 5 | source-b:3 | 3 | `visual/p05-before.png` | `visual/p05-after.png` | `visual/p05-author.html` | 1280x720 | 1280x720 | 0.3845 | 0.3783 |
| 6 | source-b:9 | 9 | `visual/p06-before.png` | `visual/p06-after.png` | `visual/p06-author.html` | 1280x720 | 1280x720 | 0.3156 | 0.3097 |
| 7 | source-c:2 | 2 | `visual/p07-before.png` | `visual/p07-after.png` | `visual/p07-author.html` | 1280x720 | 1280x720 | 0.3574 | 0.3595 |
| 8 | source-c:21 | 21 | `visual/p08-before.png` | `visual/p08-after.png` | `visual/p08-author.html` | 1280x720 | 1280x720 | 0.4143 | 0.4116 |
| 9 | probe-a | 1 | `visual/p09-before.png` | `visual/p09-after.png` | `visual/p09-author.html` | 1280x720 | 1280x720 | 0.0945 | 0.0945 |
| 10 | probe-b | 1 | `visual/p10-before.png` | `visual/p10-after.png` | `visual/p10-author.html` | 1280x720 | 1280x720 | 0.0681 | 0.0695 |

These are mechanical facts about the images (size, distinct colours, non-background fraction). They are **not** a visual verdict.

## 14. Gate 3 — independent review

> **The latest independent review is `GATE3-REVIEW-4.md`: `PASS_WITH_FINDINGS`, MAJOR 0.** It is the bundle's verdict and the reviews beside it are the record: each finding is located by `(source slot, source page, source object)`.
>
> The other review document(s) in this bundle -- `GATE3-REVIEW-2.md`, `GATE3-REVIEW-3.md`, `GATE3-REVIEW.md` -- are **historical**: they judged earlier revisions and their verdicts are superseded. A verdict of `PASS_WITH_FINDINGS` in one of them is a reading of *that* revision's page renders, not a statement that the revision met the delivery bar; the earlier revisions did not, which is why the reviews continue.

## 15. Known findings, scope differences and limitations

1. **Master/layout/header/footer omissions are scope evidence, not slide-owned loss.** 14 inherited cached-field finding(s) name the slide (master|layout) rather than a slide-owned object and carry no `source_object`; they are never mapped onto a rebuilt object. Inherited branding is not reconstructed, so a rebuilt page is painted on a blank layout.
2. **Source-inherent overlap/overflow is retained, not repaired.** 27 retained finding(s); the projection does not rewrite private source layout to reach an artificial zero-issue count, and none of them enters the material delta set.
3. **Locked proxies are excluded from native-equivalence claims.** 210 of 257 source object(s) are canonical-editable; 28 are locked visual proxies and 19 are base-only, and they are reported separately rather than folded into a native round-trip count.
4. **The gate's material-delta comparison is a text comparison.** It compares canonical characters and supported style declarations read back from the rebuilt deck; it does not compare per-run paragraph formatting, so a run-level formatting difference that preserves every character and every declared style is not a material delta. The synthetic rich-text probe records one such difference explicitly (see the pytest module's `test_the_probe_b_run_declarations_are_not_the_source_run_declarations`).
5. **A hard break becomes a paragraph boundary, and the machine cannot see it.** The Canonical Author paragraph orthography has one separator -- the paragraph boundary, spelled `<br>` -- and no spelling for a soft line break, so a source body whose paragraph contains one is re-partitioned: the synthetic probe's block is one paragraph with one `a:br` in the source and two paragraphs with none in the rebuild. The characters and the line count survive, and the third independent review measured the lines adjacent again after a leading defect was fixed (pitch 45px -> 25px against the source's 18px, a residual 7px it classes MINOR). Two things are recorded rather than claimed away: the residue varies with a block's line-height ratio, and the gate's text readback reports this object `structure_lost: false` with identical structure text -- a normalised comparison of characters cannot tell a line break from a paragraph boundary. The durable fix is to carry the break through the IR and emit `a:br` plus a paragraph/break-count check in the gate; until then the difference is visible only to a reader, which is why the independent visual review is a required gate.
6. **A list is rebuilt on the declared top-level surface only.** OfficeCLI reads the synthetic probe's list block back as native list paragraphs -- two `a:buChar` bullets and two `a:buAutoNum` numbers -- and the rebuilt deck carries the same marker kinds, because the Author list surface declares one list per object, one direct item per paragraph, and `contract.LIST_LEVELS` is `(0,)`. An item at a level the surface does not declare is **refused** (`unsupported`, `list_level_not_supported`) rather than emitted flat: a flat item keeps its indent and loses its level, and PowerPoint then continues an automatic number at level 0, which changes content rather than position. The probe's list therefore declares the four top-level items the surface has, and the refusal is covered by its own unit tests.
7. **A theme expression on a directly-declared run is not classified base-only by this projection.** The synthetic probe's theme run declares `accent1` in the source slide part and OfficeCLI reads the token back as `color: accent1`, but OfficeCLI reports no `effective.color.src` for a directly-declared scheme colour, so the gate's base-only rule never fires for it and no base-only entry is produced. The token is preserved in the source and in the projection's evidence; the projection does not claim a semantic token round trip, and this report does not either.
8. **Proxy target survival is measured from the proxy's own pixels, and a zero-extent object has no background to sample.** The isolation proof reads the published raster: it requires the object's paint to differ from the background the crop was taken out of, and for an object whose declared rectangle has no extent on either axis -- a vertical connector, whose raster is nothing but its guard band -- it requires the raster not to be the reconstruction's own background, because there is no other sample point. A uniformly blank proxy therefore blocks. What the proof still cannot see is *fidelity*: a proxy that paints the wrong words passes all five facts, which is why the independent visual review is a required gate and not a formality. 4 of 37 proof(s) here are of a raster that is nothing but its own background. Section 8 names them.
9. **A manifest cannot contain its own hash.** `artifact-manifest.json` is excluded from its own inventory and records `acceptance-report.md`'s hash in `report_sha256` instead; the manifest's own hash is printed by the driver that wrote it and is not part of the bundle.

## 16. How to reproduce

```powershell
# from the repository root
& .\.venv\Scripts\python.exe -m pytest tests/test_v042_acceptance.py -q
& .\.venv\Scripts\python.exe scripts/run_v042_acceptance.py
```

The pytest module always runs the synthetic half. The real half is opt-in: set `HTML_TO_PPTX_V042_REAL_CORPUS=1` with the private deck present, or run this driver, which runs the full ten pages.
