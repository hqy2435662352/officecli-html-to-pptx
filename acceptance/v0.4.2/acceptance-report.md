# V0.4.2 representative acceptance — WITHDRAWN

> **The acceptance claim in this report is withdrawn.** See `ACCEPTANCE-WITHDRAWN.md` for the review that rejected it and for what has to happen before the claim can be restated.
>
> The machine evidence below is the evidence of the run that was measured and is unchanged. It is not acceptance evidence.


Authoritative acceptance of the V0.4.2 representative-projection slice (ticket #18), run over the frozen ten-page corpus through the one selected-page seam (`gate_projected_author_html`).

## 1. Verdict and its evidence basis

~~**BLOCK** (gate outcome `BLOCK`, `published=True`, `accepted=False`), reached in 376.1s.~~ **withdrawn — see `ACCEPTANCE-WITHDRAWN.md`**

| binding | value |
|---|---|
| commit | `81981da1acd5017272bdf0b422500b0f5d7c8613 (working tree dirty)` |
| run id (gate report sha256) | `db8d512bc6cdc36ef07de9dda5c7e2700323377ceefeefcb9eaf185073569072` |

The report, the source map, the artifact manifest and the review package all belong to the run id above: it is the digest of the gate's own verdict document, so a reader can check that they describe one run without a registry to consult. The commit is the revision the verdict is about.

The verdict is the gate's own derived outcome. It is *not* inferred from a process exit code, from the Author Contract status, from OfficeCLI validation, or from the screenshots below. The evidence set that produced it is:

| evidence | value |
|---|---|
| selected pages | 10 |
| projected pages | 10 |
| blocked pages | 0 |
| source objects with one disposition | 257 |
| canonical-editable | 212 |
| locked-visual-proxy | 28 |
| base-only-semantic | 17 |
| unsupported | 0 |
| unresolved | 0 |
| material deltas | 1 |
| retained findings | 27 |
| scope evidence | 31 |
| proxy isolation proofs passed | 35 |
| proxy isolation proofs failed | 0 |
| blocking diagnostics | 3 |
| hashed artifacts (gate) | 83 |
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
| 1 | source-a:2 | 2 | 41 | 34 | 6 | 1 | 0 | 0 | 3 | 0 | 30 | 0 | 3 | — |
| 2 | source-a:5 | 5 | 11 | 11 | 0 | 0 | 0 | 0 | 6 | 1 | 8 | 1 | 0 | — |
| 3 | source-a:12 | 12 | 45 | 42 | 3 | 0 | 0 | 0 | 13 | 3 | 41 | 1 | 3 | — |
| 4 | source-a:30 | 30 | 57 | 32 | 10 | 15 | 0 | 0 | 5 | 0 | 16 | 0 | 25 | — |
| 5 | source-b:3 | 3 | 18 | 18 | 0 | 0 | 0 | 0 | 4 | 0 | 12 | 3 | 0 | — |
| 6 | source-b:9 | 9 | 28 | 22 | 6 | 0 | 0 | 0 | 8 | 0 | 21 | 1 | 2 | — |
| 7 | source-c:2 | 2 | 26 | 26 | 0 | 0 | 0 | 0 | 0 | 0 | 20 | 3 | 0 | — |
| 8 | source-c:21 | 21 | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 11 | 1 | 0 | — |
| 9 | probe-a | 1 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 7 | 0 | 0 | — |
| 10 | probe-b | 1 | 12 | 8 | 3 | 1 | 0 | 0 | 2 | 1 | 8 | 0 | 2 | — |

### Disposition ledger summary (per page)

The complete ledger — one row per slide-owned source object with its source identity, ownership, disposition, reason code and evidence — is `gate/disposition-ledger.json`. Its per-page totals:

| out | page | source objects | canonical-editable | locked-visual-proxy | base-only-semantic | container-owned | unsupported | unresolved |
|---|---|---|---|---|---|---|---|---|
| 1 | source-a:2 | 41 | 34 | 6 | 1 | 4 | 0 | 0 |
| 2 | source-a:5 | 11 | 11 | 0 | 0 | 0 | 0 | 0 |
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

**1 material delta(s):**

- `the same condition is materially worsened: pressure ratio 1.1301 -> 1.2231 exceeds both the absolute tolerance 0.02 and the relative tolerance 0.05` out p10 `/slide[1]/shape[@id=100000]` `text_overflow`

## 6. Retained findings (source-inherent, not repaired)

27 retained finding(s). Each one is a condition the **source** object already carries; the gate lists them explicitly instead of counting them as repaired. The complete set is `gate/retained-findings.json`.

| condition | count |
|---|---|
| `table_cell_whitespace_placement` | 1 |
| `text_overflow` | 26 |

- out p1 `/slide[2]/shape[@id=49]` `text_overflow` → `slide-001-textbox-014`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p2 `/slide[5]/shape[@id=100085]` `text_overflow` → `slide-002-textbox-011`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
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

31 scope-evidence record(s). These are findings and omissions about values the slide does not own; they are never reported as repaired slide-owned objects.

| condition | count | mapped |
|---|---|---|
| `inherited_paint_omission` | 17 | 17 |
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
| `slide-003-picture-004` | `/slide[12]/shape[@id=100068]` | locked-visual-proxy | 886x69 | 2.00096 | 2 | 0.000000 | True |
| `slide-003-picture-007` | `/slide[12]/shape[@id=100071]` | locked-visual-proxy | 937x69 | 2.00086 | 2 | 0.000000 | True |
| `slide-003-picture-010` | `/slide[12]/shape[@id=100077]` | locked-visual-proxy | 937x69 | 2.00086 | 2 | 0.000000 | True |
| `slide-004-picture-011` | `/slide[30]/shape[@id=100111]` | locked-visual-proxy | 301x46 | 2.00135 | 2 | 0.000000 | True |
| `slide-004-picture-012` | `/slide[30]/shape[@id=100112]` | locked-visual-proxy | 301x46 | 2.00135 | 2 | 0.062319 | True |
| `slide-004-picture-013` | `/slide[30]/shape[@id=100113]` | locked-visual-proxy | 301x46 | 2.00135 | 2 | 0.000000 | True |
| `slide-004-picture-018` | `/slide[30]/shape[@id=100125]` | base-only-semantic | 320x207 | 2.00317 | 2 | 0.000000 | True |
| `slide-004-picture-022` | `/slide[30]/shape[@id=100132]` | base-only-semantic | 308x207 | 2.00000 | 2 | 0.000000 | True |
| `slide-004-picture-024` | `/slide[30]/shape[@id=100024]` | base-only-semantic | 1177x36 | 2.00017 | 2 | 0.000000 | True |
| `slide-004-picture-027` | `/slide[30]/shape[@id=9]` | base-only-semantic | 270x207 | 1.99625 | 2 | 0.000000 | True |
| `slide-004-picture-028` | `/slide[30]/connector[@id=10]` | locked-visual-proxy | 4x710 | 1.99972 | 2 | 0.000000 | True |
| `slide-004-picture-029` | `/slide[30]/connector[@id=11]` | locked-visual-proxy | 4x681 | 1.99911 | 2 | 0.000000 | True |
| `slide-004-picture-030` | `/slide[30]/connector[@id=15]` | locked-visual-proxy | 4x683 | 2.00088 | 2 | 0.000000 | True |
| `slide-004-picture-032` | `/slide[30]/shape[@id=22]` | base-only-semantic | 276x207 | 1.99926 | 2 | 0.000000 | True |
| `slide-004-picture-034` | `/slide[30]/shape[@id=24]` | base-only-semantic | 293x207 | 2.00277 | 2 | 0.000000 | True |
| `slide-004-picture-037` | `/slide[30]/shape[@id=28]` | base-only-semantic | 211x207 | 2.00097 | 2 | 0.000000 | True |
| `slide-004-picture-040` | `/slide[30]/shape[@id=38]` | base-only-semantic | 270x207 | 1.99625 | 2 | 0.000000 | True |
| `slide-004-picture-042` | `/slide[30]/shape[@id=39]` | base-only-semantic | 118x62 | 1.99825 | 2 | 0.000000 | True |
| `slide-004-picture-043` | `/slide[30]/shape[@id=40]` | base-only-semantic | 118x62 | 1.99825 | 2 | 0.000000 | True |
| `slide-004-picture-044` | `/slide[30]/shape[@id=41]` | base-only-semantic | 276x207 | 1.99926 | 2 | 0.000000 | True |
| `slide-004-picture-045` | `/slide[30]/shape[@id=42]` | base-only-semantic | 293x207 | 2.00277 | 2 | 0.000000 | True |
| `slide-004-picture-048` | `/slide[30]/connector[@id=45]` | locked-visual-proxy | 4x688 | 1.99942 | 2 | 0.000000 | True |
| `slide-004-picture-050` | `/slide[30]/shape[@id=48]` | base-only-semantic | 316x267 | 2.00321 | 2 | 0.000000 | True |
| `slide-004-picture-052` | `/slide[30]/shape[@id=50]` | base-only-semantic | 118x62 | 1.99825 | 2 | 0.000000 | True |
| `slide-004-picture-053` | `/slide[30]/connector[@id=52]` | locked-visual-proxy | 1389x5 | 2.00014 | 2 | 0.000718 | True |
| `slide-004-picture-054` | `/slide[30]/connector[@id=53]` | locked-visual-proxy | 1371x5 | 2.00029 | 2 | 0.378093 | True |
| `slide-004-picture-055` | `/slide[30]/connector[@id=54]` | locked-visual-proxy | 1372x6 | 1.99971 | 2 | 0.286701 | True |
| `slide-004-picture-056` | `/slide[30]/shape[@id=55]` | base-only-semantic | 316x267 | 2.00321 | 2 | 0.000000 | True |
| `slide-006-picture-023` | `/slide[9]/group[@id=100381]` | locked-visual-proxy | 296x180 | 2.00233 | 2 | 0.000000 | True |
| `slide-006-picture-024` | `/slide[9]/group[@id=100383]` | locked-visual-proxy | 296x180 | 2.00233 | 2 | 0.000000 | True |
| `slide-010-picture-004` | `/slide[1]/shape[@id=100003]` | base-only-semantic | 244x89 | 2.00000 | 2 | 0.207692 | True |
| `slide-010-picture-009` | `/slide[1]/group[@id=100008]` | locked-visual-proxy | 444x304 | 2.00000 | 2 | 0.000000 | True |

35 proof(s), 35 passed. Every locked proxy carries the gate's five isolation facts: target survival, raster density, guard band, target bounds and contamination.

**4 of 35 proof(s) are of a proxy whose raster is nothing but its own background** (`paint_fraction` 0.0, so no paint of the locked object was measured in the crop): `slide-004-picture-028`, `slide-004-picture-029`, `slide-004-picture-030`, `slide-004-picture-048`. The gate's isolation facts are satisfied for these proxies -- density, guard band, bounds and contamination are measured and correct -- but they do not establish that the locked object's own pixels survived, and this report does not claim that they did. Whether those objects are blank in the source is a Gate 3 question, not a structural one.

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

174 independent OfficeCLI readback(s) of canonical-editable objects; 0 disagree with the source text.


## 11. OfficeCLI validation and issue records

Source deck reads:

- `src1` validate: Validation passed: no errors found.; issues: 238
- `src2` validate: Validation passed: no errors found.; issues: 110
- `src3` validate: Validation passed: no errors found.; issues: 0
- `src4` validate: Validation passed: no errors found.; issues: 0
- `src5` validate: Validation passed: no errors found.; issues: 2

Rebuilt deck reads:

- `rebuilt` `rebuilt.pptx`: Validation passed: no errors found.

- rebuilt issues: 5

## 12. Artifact manifest

The gate published 83 hashed artifacts; `gate/gate-report.json` lists every one with its sha256 and size, and `artifact-manifest.json` lists every file in this bundle the same way. Both can be re-checked against disk independently:

```powershell
Get-FileHash acceptance/v0.4.2/gate/rebuilt.pptx -Algorithm SHA256
$m = Get-Content acceptance/v0.4.2/artifact-manifest.json | ConvertFrom-Json
$m.artifacts | ForEach-Object { $h = (Get-FileHash "acceptance/v0.4.2/$($_.name)" -Algorithm SHA256).Hash.ToLower(); if ($h -ne $_.sha256) { "MISMATCH $($_.name)" } }
```

The gate's artifact list, with the hash recorded in its own report (`gate/gate-report.json` carries the same values, and re-hashing any of these files from disk must reproduce them):

| artifact | sha256 | size |
|---|---|---|
| `canonical-author.html` | `72aec5c8e8ff23371c213a7e6118c2f84f65d38c86e67bc5e399980a5d22f637` | 42503414 |
| `disposition-ledger.json` | `b4bf035c0ea872d2ecf1acc80db728747676972bc810081c877a5c5bbfa4c764` | 250681 |
| `material-deltas.json` | `b91085126fa30af42804740afdafbbd668b4e9a386ff8ddb82a60f17cc5ff45a` | 2429 |
| `pages.json` | `ee7500f74f52bd618992ffc10cbfc154035f749a5f2508d9ba00d0e5b2ee8d2b` | 513669 |
| `projection/canonical-author.html` | `72aec5c8e8ff23371c213a7e6118c2f84f65d38c86e67bc5e399980a5d22f637` | 42503414 |
| `projection/projection-report.json` | `10026c11fd8421b9082cf58432b9b4e60563a70c10b588d1b2b8459c436b931b` | 668963 |
| `projection/proxy-src1-slide-002-007.png` | `a46d3062d6aac0d510a4b4d9d195bf7a4252a16593a6b7aa6969258df227384d` | 426 |
| `projection/proxy-src1-slide-002-010.png` | `a46d3062d6aac0d510a4b4d9d195bf7a4252a16593a6b7aa6969258df227384d` | 426 |
| `projection/proxy-src1-slide-002-028.png` | `1ffcd35808112b4cc26a51e24e5d3680be918843ac2ee2cd6dd1d1e7e7c008d0` | 13212 |
| `projection/proxy-src1-slide-012-004.png` | `aaf745a4f113a4f8eca3e2ccecef0af028e7062c83d11d6d0c26adcf47baf852` | 437 |
| `projection/proxy-src1-slide-012-007.png` | `da76ef444fc31185b8859169be85dd8f656168a6ad4a5a5197d105235af6d9aa` | 447 |
| `projection/proxy-src1-slide-012-010.png` | `f861b7b48052b510a5803f37125352ea330fb14449ec40aed510babfaf2e0077` | 465 |
| `projection/proxy-src1-slide-030-011.png` | `398cc0ba8a4898080f55cc0f11c963270e0714419cda6afd3c97d119594175f2` | 1036 |
| `projection/proxy-src1-slide-030-012.png` | `1d62bf44a02b13eb02edf3b139383e1ffcbf7db1930a794261b9b555c592405c` | 1238 |
| `projection/proxy-src1-slide-030-013.png` | `8c23f0cd3cfbea17a387cfcba83c4755179d36e1638a4365c364f91c68e92604` | 1168 |
| `projection/proxy-src1-slide-030-018.png` | `584c9ea1a1f64484a927463eb79ddd08d1f6be0a3e5eeb2d5540895ab52beae2` | 4973 |
| `projection/proxy-src1-slide-030-022.png` | `38e9cc8c7b760e73a0a2e8d6300a1703c7753c895abce8a7e6708a45035c71cc` | 4592 |
| `projection/proxy-src1-slide-030-024.png` | `39cc36e7e8b75d1cb9d4bc6d6d3a856c080b1d27e87abe58f0a880db817b041a` | 6006 |
| `projection/proxy-src1-slide-030-027.png` | `41b5fd1e238eec442412b3de58ed86732fac22c97431a277f2d6e33a41429a07` | 4849 |
| `projection/proxy-src1-slide-030-028.png` | `9444c4806e916d63676318d8ae5af403e594f07e6bae8e49cd9f51368ccc8235` | 200 |
| `projection/proxy-src1-slide-030-029.png` | `134a8c24f521660915a1f2f0ccfb90871ecdf7b1b8056b78d89a548de94e5b3b` | 213 |
| `projection/proxy-src1-slide-030-030.png` | `2bb676834cab308c9b3c7d49f92bf875386a8b051564401e87cadac8e007a6d7` | 205 |
| `projection/proxy-src1-slide-030-032.png` | `9230ac0d5de0a5289eb4a96bf580768c787b07f276d09c35dd3fffb222d8caa0` | 4835 |
| `projection/proxy-src1-slide-030-034.png` | `3e1ef9301eb569ab4cc023c1532e6fc0540bf4e932d2bab88312ce2eb5546e06` | 3285 |
| `projection/proxy-src1-slide-030-037.png` | `8aa5e908e23a1799633a7249e7530157f0d27007f1621547d5786ab9319018d6` | 3506 |
| `projection/proxy-src1-slide-030-040.png` | `02d6116c4456194244eb0519cf5295c836a91807db65276c0a96e7b552050ac4` | 3540 |
| `projection/proxy-src1-slide-030-042.png` | `2c2d21d20957a75c2f109de59ad57d3f1ba715ef47a473c61387d3a4258df9a8` | 494 |
| `projection/proxy-src1-slide-030-043.png` | `6de1dd533a0dab08f00e199f523c88e61d7fa0afad23bdc0d87dfee162399c68` | 497 |
| `projection/proxy-src1-slide-030-044.png` | `55624e4086c97ce2774b0ff7c8c2fa7e39e1b156da17e9b55df1f78d2fed6f99` | 3596 |
| `projection/proxy-src1-slide-030-045.png` | `b9caf06d23dcbcbba17a7e29dc87335df6355021b78b62cc64039582cd069635` | 3548 |
| `projection/proxy-src1-slide-030-048.png` | `b3c23ec655d91cb1ab1e1769d86f1740073a8ac4bf7c59eb4bee9482a58d94f2` | 205 |
| `projection/proxy-src1-slide-030-050.png` | `be1c7802b035dccd24e6a84a20ce84371c2ab829a94625db02eafafd02f40016` | 6600 |
| `projection/proxy-src1-slide-030-052.png` | `95db3ef2b5551f4a564c2725b997e96a675df2519569b9a02fe9b7873c395a2e` | 494 |
| `projection/proxy-src1-slide-030-053.png` | `af0c6035da0bc5eeaea187f30b78daa6f9ec903acd50a1ab76bd08ad14835708` | 261 |
| `projection/proxy-src1-slide-030-054.png` | `3cc5a273124636cb27ad705bbfcca2a0c9338ebdfda71ba605d6f34db2b9723c` | 297 |
| `projection/proxy-src1-slide-030-055.png` | `48720bcbebb1e488b21bbef6c9afed424a5f8a9dbe773185ab75e0b229365b2a` | 297 |
| `projection/proxy-src1-slide-030-056.png` | `53140e20c9407e985c070276d1d9cf726aeffc1714681d49ac6537511552ca01` | 4624 |
| `projection/proxy-src2-slide-009-023.png` | `0b7f3688557e9d597006379103f48c95f383f7cc2e130cb1851f68aa451a4b60` | 13116 |
| `projection/proxy-src2-slide-009-024.png` | `1955f0a4566644ad752027813a39c0a217aa513c33aeee668da435fc7e839852` | 18475 |
| `projection/proxy-src5-slide-001-004.png` | `49c4fa98d502e99fc0920a31d5862fabbb5a9c0732e7918f85d0d4be8f53fa90` | 7905 |
| `projection/proxy-src5-slide-001-009.png` | `992fee4860fa846f6cbeaf7e4df07e13b5953222625577936c3915f1ffb7d29a` | 2278 |
| `projection/source-map.json` | `0108e12d6d952e278719f170ca96fbed6bc396437738f564f457527b31f63233` | 610627 |
| `projection-report.json` | `10026c11fd8421b9082cf58432b9b4e60563a70c10b588d1b2b8459c436b931b` | 668963 |
| `proxies/proxy-src1-slide-002-007.png` | `a46d3062d6aac0d510a4b4d9d195bf7a4252a16593a6b7aa6969258df227384d` | 426 |
| `proxies/proxy-src1-slide-002-010.png` | `a46d3062d6aac0d510a4b4d9d195bf7a4252a16593a6b7aa6969258df227384d` | 426 |
| `proxies/proxy-src1-slide-002-028.png` | `1ffcd35808112b4cc26a51e24e5d3680be918843ac2ee2cd6dd1d1e7e7c008d0` | 13212 |
| `proxies/proxy-src1-slide-012-004.png` | `aaf745a4f113a4f8eca3e2ccecef0af028e7062c83d11d6d0c26adcf47baf852` | 437 |
| `proxies/proxy-src1-slide-012-007.png` | `da76ef444fc31185b8859169be85dd8f656168a6ad4a5a5197d105235af6d9aa` | 447 |
| `proxies/proxy-src1-slide-012-010.png` | `f861b7b48052b510a5803f37125352ea330fb14449ec40aed510babfaf2e0077` | 465 |
| `proxies/proxy-src1-slide-030-011.png` | `398cc0ba8a4898080f55cc0f11c963270e0714419cda6afd3c97d119594175f2` | 1036 |
| `proxies/proxy-src1-slide-030-012.png` | `1d62bf44a02b13eb02edf3b139383e1ffcbf7db1930a794261b9b555c592405c` | 1238 |
| `proxies/proxy-src1-slide-030-013.png` | `8c23f0cd3cfbea17a387cfcba83c4755179d36e1638a4365c364f91c68e92604` | 1168 |
| `proxies/proxy-src1-slide-030-018.png` | `584c9ea1a1f64484a927463eb79ddd08d1f6be0a3e5eeb2d5540895ab52beae2` | 4973 |
| `proxies/proxy-src1-slide-030-022.png` | `38e9cc8c7b760e73a0a2e8d6300a1703c7753c895abce8a7e6708a45035c71cc` | 4592 |
| `proxies/proxy-src1-slide-030-024.png` | `39cc36e7e8b75d1cb9d4bc6d6d3a856c080b1d27e87abe58f0a880db817b041a` | 6006 |
| `proxies/proxy-src1-slide-030-027.png` | `41b5fd1e238eec442412b3de58ed86732fac22c97431a277f2d6e33a41429a07` | 4849 |
| `proxies/proxy-src1-slide-030-028.png` | `9444c4806e916d63676318d8ae5af403e594f07e6bae8e49cd9f51368ccc8235` | 200 |
| `proxies/proxy-src1-slide-030-029.png` | `134a8c24f521660915a1f2f0ccfb90871ecdf7b1b8056b78d89a548de94e5b3b` | 213 |
| `proxies/proxy-src1-slide-030-030.png` | `2bb676834cab308c9b3c7d49f92bf875386a8b051564401e87cadac8e007a6d7` | 205 |
| `proxies/proxy-src1-slide-030-032.png` | `9230ac0d5de0a5289eb4a96bf580768c787b07f276d09c35dd3fffb222d8caa0` | 4835 |
| `proxies/proxy-src1-slide-030-034.png` | `3e1ef9301eb569ab4cc023c1532e6fc0540bf4e932d2bab88312ce2eb5546e06` | 3285 |
| `proxies/proxy-src1-slide-030-037.png` | `8aa5e908e23a1799633a7249e7530157f0d27007f1621547d5786ab9319018d6` | 3506 |
| `proxies/proxy-src1-slide-030-040.png` | `02d6116c4456194244eb0519cf5295c836a91807db65276c0a96e7b552050ac4` | 3540 |
| `proxies/proxy-src1-slide-030-042.png` | `2c2d21d20957a75c2f109de59ad57d3f1ba715ef47a473c61387d3a4258df9a8` | 494 |
| `proxies/proxy-src1-slide-030-043.png` | `6de1dd533a0dab08f00e199f523c88e61d7fa0afad23bdc0d87dfee162399c68` | 497 |
| `proxies/proxy-src1-slide-030-044.png` | `55624e4086c97ce2774b0ff7c8c2fa7e39e1b156da17e9b55df1f78d2fed6f99` | 3596 |
| `proxies/proxy-src1-slide-030-045.png` | `b9caf06d23dcbcbba17a7e29dc87335df6355021b78b62cc64039582cd069635` | 3548 |
| `proxies/proxy-src1-slide-030-048.png` | `b3c23ec655d91cb1ab1e1769d86f1740073a8ac4bf7c59eb4bee9482a58d94f2` | 205 |
| `proxies/proxy-src1-slide-030-050.png` | `be1c7802b035dccd24e6a84a20ce84371c2ab829a94625db02eafafd02f40016` | 6600 |
| `proxies/proxy-src1-slide-030-052.png` | `95db3ef2b5551f4a564c2725b997e96a675df2519569b9a02fe9b7873c395a2e` | 494 |
| `proxies/proxy-src1-slide-030-053.png` | `af0c6035da0bc5eeaea187f30b78daa6f9ec903acd50a1ab76bd08ad14835708` | 261 |
| `proxies/proxy-src1-slide-030-054.png` | `3cc5a273124636cb27ad705bbfcca2a0c9338ebdfda71ba605d6f34db2b9723c` | 297 |
| `proxies/proxy-src1-slide-030-055.png` | `48720bcbebb1e488b21bbef6c9afed424a5f8a9dbe773185ab75e0b229365b2a` | 297 |
| `proxies/proxy-src1-slide-030-056.png` | `53140e20c9407e985c070276d1d9cf726aeffc1714681d49ac6537511552ca01` | 4624 |
| `proxies/proxy-src2-slide-009-023.png` | `0b7f3688557e9d597006379103f48c95f383f7cc2e130cb1851f68aa451a4b60` | 13116 |
| `proxies/proxy-src2-slide-009-024.png` | `1955f0a4566644ad752027813a39c0a217aa513c33aeee668da435fc7e839852` | 18475 |
| `proxies/proxy-src5-slide-001-004.png` | `49c4fa98d502e99fc0920a31d5862fabbb5a9c0732e7918f85d0d4be8f53fa90` | 7905 |
| `proxies/proxy-src5-slide-001-009.png` | `992fee4860fa846f6cbeaf7e4df07e13b5953222625577936c3915f1ffb7d29a` | 2278 |
| `proxy-isolation.json` | `fc7800d82b6cf21584759ab5a1bbd8d95109d8263c5c9af37cb325f3b9d7045e` | 52322 |
| `rebuilt.pptx` | `fd8dffe0a5594cb3d05f92cead7c4aec016ef929c8fe4975494b8003837bc68f` | 31253634 |
| `retained-findings.json` | `9c20a42cae602e78d181863080433f4694a98336c2fd5b1e3ab6894c1fc98a0e` | 42109 |
| `scope-evidence.json` | `643a366a5bd789edb1e78cbb1c2f3bbd7a8369d14926bcb1db3e4964d99b29b0` | 20857 |
| `source-map.json` | `0108e12d6d952e278719f170ca96fbed6bc396437738f564f457527b31f63233` | 610627 |

`gate/gate-report.json` and `gate/gate-report.md` are excluded from that list because a document cannot contain its own hash; the bundle's `artifact-manifest.json` covers them instead, except for itself.

## 13. Visual records

Every page has three records: the source page render, the rebuilt page render (both through OfficeCLI's HTML render path at 1600px, so they are directly comparable), and that page's Canonical Author HTML.

| # | page | source page | before | after | author html | before px | after px | before non-background | after non-background |
|---|---|---|---|---|---|---|---|---|---|
| 1 | source-a:2 | 2 | `visual/p01-before.png` | `visual/p01-after.png` | `visual/p01-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 2 | source-a:5 | 5 | `visual/p02-before.png` | `visual/p02-after.png` | `visual/p02-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 3 | source-a:12 | 12 | `visual/p03-before.png` | `visual/p03-after.png` | `visual/p03-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 4 | source-a:30 | 30 | `visual/p04-before.png` | `visual/p04-after.png` | `visual/p04-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 5 | source-b:3 | 3 | `visual/p05-before.png` | `visual/p05-after.png` | `visual/p05-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 6 | source-b:9 | 9 | `visual/p06-before.png` | `visual/p06-after.png` | `visual/p06-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 7 | source-c:2 | 2 | `visual/p07-before.png` | `visual/p07-after.png` | `visual/p07-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 8 | source-c:21 | 21 | `visual/p08-before.png` | `visual/p08-after.png` | `visual/p08-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 9 | probe-a | 1 | `visual/p09-before.png` | `visual/p09-after.png` | `visual/p09-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 10 | probe-b | 1 | `visual/p10-before.png` | `visual/p10-after.png` | `visual/p10-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |

These are mechanical facts about the images (size, distinct colours, non-background fraction). They are **not** a visual verdict.

## 14. Gate 3 — independent review

> **This section is intentionally empty. It is filled in by the independent reviewer (the primary agent).**
>
> Ticket #18 requires the page-by-page visual verdict to be independent, so the agent that produced this bundle does **not** record one and does not claim zero major projection defects. Per page, the reviewer opens `visual/pNN-before.png`, `visual/pNN-after.png` and `visual/pNN-author.html` and records a verdict against: missing content, duplicate paint, proxy contamination, image distortion, lost arrowheads, severe clipping, table displacement, and z-order corruption.
>
> ```
> page 1 (source page 2):   [ ] no major defect  [ ] defect: ...
> page 2 (source page 5):   [ ] no major defect  [ ] defect: ...
> ...
> ```

## 15. Known findings, scope differences and limitations

1. **Master/layout/header/footer omissions are scope evidence, not slide-owned loss.** 14 inherited cached-field finding(s) name the slide (master|layout) rather than a slide-owned object and carry no `source_object`; they are never mapped onto a rebuilt object. Inherited branding is not reconstructed, so a rebuilt page is painted on a blank layout.
2. **Source-inherent overlap/overflow is retained, not repaired.** 27 retained finding(s); the projection does not rewrite private source layout to reach an artificial zero-issue count, and none of them enters the material delta set.
3. **Locked proxies are excluded from native-equivalence claims.** 212 of 257 source object(s) are canonical-editable; 28 are locked visual proxies and 17 are base-only, and they are reported separately rather than folded into a native round-trip count.
4. **The gate's material-delta comparison is a text comparison.** It compares canonical characters and supported style declarations read back from the rebuilt deck; it does not compare per-run paragraph formatting, so a run-level formatting difference that preserves every character and every declared style is not a material delta. The synthetic rich-text probe records one such difference explicitly (see the pytest module's `test_the_probe_b_run_declarations_are_not_the_source_run_declarations`).
5. **A hard break inside a projected paragraph is not rebuilt as a break.** The projection emits it as a `<br>` in the Canonical Author document, and `br` is not part of the declared inline-element surface, so the New Deck path rebuilds the two sides as one paragraph with no character lost. Recorded by the pytest module's `test_the_probe_b_hard_break_is_emitted_and_the_rebuild_merges_it`.
6. **A source list's native marker is not reconstructed.** OfficeCLI reads the synthetic probe's list block back with `list=bullet` and a native `a:buChar` marker; the rebuilt deck's object is plain paragraphs, because the Canonical Author surface has no list element. The item text round-trips; the marker does not. Recorded by the pytest module's `test_the_probe_b_list_declaration_is_present_in_the_source_and_absent_from_the_rebuilt_deck`.
7. **A theme expression on a directly-declared run is not classified base-only by this projection.** The synthetic probe's theme run declares `accent1` in the source slide part and OfficeCLI reads the token back as `color: accent1`, but OfficeCLI reports no `effective.color.src` for a directly-declared scheme colour, so the gate's base-only rule never fires for it and no base-only entry is produced. The token is preserved in the source and in the projection's evidence; the projection does not claim a semantic token round trip, and this report does not either.
8. **Proxy target survival is asserted from the rebuilt deck, not measured from the proxy's pixels.** The isolation proof establishes that a picture object with the proxy's own name exists in the rebuilt deck and that its raster has the right density, bounds, guard band and contamination; it does not establish that the locked object's own paint is in that raster. 4 of 35 proof(s) here are of a raster that is nothing but its own background. Section 8 names them. This is the same limitation the independent verification report records for the gate.
9. **A manifest cannot contain its own hash.** `artifact-manifest.json` is excluded from its own inventory and records `acceptance-report.md`'s hash in `report_sha256` instead; the manifest's own hash is printed by the driver that wrote it and is not part of the bundle.

## 16. How to reproduce

```powershell
# from the repository root
& .\.venv\Scripts\python.exe -m pytest tests/test_v042_acceptance.py -q
& .\.venv\Scripts\python.exe .scratch/tools/run_v042_acceptance.py
```

The pytest module always runs the synthetic half. The real half is opt-in: set `HTML_TO_PPTX_V042_REAL_CORPUS=1` with the private deck present, or run this driver, which runs the full ten pages.
