# V0.4.2 representative acceptance — PASS_WITH_FINDINGS

Authoritative acceptance of the V0.4.2 representative-projection slice (ticket #18), run over the frozen ten-page corpus through the one selected-page seam (`gate_projected_author_html`).

## 1. Verdict and its evidence basis

**PASS_WITH_FINDINGS** (gate outcome `PASS_WITH_FINDINGS`, `published=True`, `accepted=True`), reached in 499.3s.

The verdict is the gate's own derived outcome. It is *not* inferred from a process exit code, from the Author Contract status, from OfficeCLI validation, or from the screenshots below. The evidence set that produced it is:

| evidence | value |
|---|---|
| selected pages | 10 |
| projected pages | 10 |
| blocked pages | 0 |
| source objects with one disposition | 239 |
| canonical-editable | 193 |
| locked-visual-proxy | 24 |
| base-only-semantic | 22 |
| unsupported | 0 |
| unresolved | 0 |
| material deltas | 0 |
| retained findings | 31 |
| scope evidence | 52 |
| proxy isolation proofs passed | 0 |
| proxy isolation proofs failed | 0 |
| blocking diagnostics | 0 |
| hashed artifacts (gate) | 93 |
| Author Contract (`author`) | PASS |

The unchanged `author` Contract reports **PASS** with 0 diagnostic(s). It is corroboration, not the verdict.

## 2. Corpus, selection order and coverage purpose

The frozen selection order is exactly `real:2, real:5, real:7, real:12, real:14, real:19, real:25, real:30, probe-a, probe-b`. The eight real pages are `2, 5, 7, 12, 14, 19, 25, 30` of the private source deck; the synthetic probes follow. `probe-a` contributes two pages (its isolation page and its arrow page).

| # | page | source page | composition | coverage purpose |
|---|---|---|---|---|
| 1 | source page 2 | 2 | 25 textbox, 6 shape (3 ellipse, 3 rightArrow), 2 group, 4 connector, 4 picture; 1 source overflow | groups + bound connectors, native ellipse/rightArrow, pictures, text density, repeated cards, source-inherent overflow |
| 2 | source page 5 | 5 | 2 picture, 8 shape, 1 table | native table, roundRect, transparent/cropped pictures |
| 3 | source page 7 | 7 | 1 shape, 1 table, 1 textbox | large native table (11x6) with whitespace-placement cell findings |
| 4 | source page 12 | 12 | 44 shape, 1 table; 13 source issues | high object density, gradient fills, many source-inherent overflows |
| 5 | source page 14 | 14 | 5 shape, 3 table | compound/multi-table page |
| 6 | source page 19 | 19 | 7 shape, 1 table, 6 picture, 1 textbox | the most picture-heavy page; source-inherent overflow |
| 7 | source page 25 | 25 | 7 shape, 19 textbox, 13 picture, 2 connector | mixed density with a standalone connector |
| 8 | source page 30 | 30 | 30 shape, 16 picture, 7 connector, 4 textbox | highest object count (57); connector-heavy |
| 9 | synthetic probe A | 1 | 1 slide: a text-free filled rect with three independent sibling textboxes painted inside its rectangle, one text-free ellipse, and one text-free rightArrow with one independent sibling textbox painted inside it | proxy/overlay isolation: no sibling text may be embedded in any raster payload, and no wording may appear twice in the rebuilt deck |
| 10 | synthetic probe B | 1 | 2 slides: mixed runs, a hard break, an empty paragraph, nested bullet and numbering paragraphs, explicit Latin/CJK fonts, theme-token text, rect/roundRect/ellipse/rightArrow; one group owning a shape and a connector | rich text semantics and the locked container boundary: mixed runs, hard break, empty paragraph, bullet nesting, numbering, Latin/CJK fonts, theme-token evidence, fixed numeric strings, and one group with a bound connector represented exactly once |

### Page-level scope notes

- **source page 2**: The two groups are locked container boundaries: their children and the four connectors they own are represented inside the container proxy and are never emitted again as siblings. The one text overflow is the source's own condition and stays a retained finding.
- **source page 5**: Inherited master/layout branding is not reconstructed, so the rebuilt page is painted on a blank layout; that omission is page-level scope evidence, never slide-owned projection loss.
- **source page 7**: Two table cells differ from the source in whitespace placement only; the condition is retained and reported, never repaired and never counted as a material delta. One shape's text colour is a theme expression, so it is base-only-semantic.
- **source page 12**: This page carries the corpus's highest source-issue count and its gradient fills. Every issue is the source's own; none is introduced by the projection. Gradient-filled objects are not canonical-editable and keep their locked or base-only disposition.
- **source page 14**: Three native tables on one page exercise per-table identity and independent row/column and cell-text readback.
- **source page 19**: Six picture objects exercise the picture surface and the one table exercises native table readback alongside them. The overflow is the source's own condition.
- **source page 25**: A standalone connector is locked, not reconstructed natively: the current Contract has no editable connector object. It is one locked proxy or one retained finding, never a silently dropped object.
- **source page 30**: The densest page in the corpus. Connector-heavy composition is what exercises the container/locked boundary at scale: every connector has exactly one disposition in the ledger.
- **synthetic probe A**: Every object on this probe is canonical-editable and no proxy is emitted, so the rebuilt deck must contain no raster payload for this page at all. The overlay wording is asserted to appear exactly once in the rebuilt deck; if the rect, the ellipse or the arrow were ever replaced by a picture, this probe's unaccounted picture count would show it.
- **synthetic probe B**: OfficeCLI reports no inheritance source for the theme run's colour, so the gate classifies it canonical-editable and the projection emits it without a colour declaration; the theme token is preserved in the source and in the projection's evidence, and no semantic token round trip is claimed. The group is one locked container boundary whose child shape and connector are represented once inside it and never emitted again as siblings.

## 3. Source immutability

- sha256 before the run: `dcdf6d2c86809fdca6ca7c206ffd02e42d11b0f408b58a619e3015c9ebb64de5`
- sha256 after the run: `dcdf6d2c86809fdca6ca7c206ffd02e42d11b0f408b58a619e3015c9ebb64de5`
- identical: **True**; first 12 hex: `dcdf6d2c8680`
- the run targets the source deck with **zero** OfficeCLI write operations: it is read with `get`, `view` and `issues` only, and the gate re-hashes it after publication.

## 4. Per-page results

`rebuilt issues` is the count of OfficeCLI issue records the rebuilt deck reports for that page.

| out | page | source page | objects | canonical | locked | base-only | unsup | unres | src issues | rebuilt issues | text readbacks | tables | proxies | failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | real:2 | 2 | 41 | 34 | 6 | 1 | 0 | 0 | 3 | 0 | 30 | 0 | 3 | — |
| 2 | real:5 | 5 | 11 | 11 | 0 | 0 | 0 | 0 | 6 | 0 | 8 | 1 | 0 | — |
| 3 | real:7 | 7 | 3 | 2 | 0 | 1 | 0 | 0 | 6 | 0 | 1 | 1 | 1 | — |
| 4 | real:12 | 12 | 45 | 42 | 3 | 0 | 0 | 0 | 13 | 3 | 41 | 1 | 3 | — |
| 5 | real:14 | 14 | 8 | 8 | 0 | 0 | 0 | 0 | 7 | 1 | 5 | 3 | 0 | — |
| 6 | real:19 | 19 | 15 | 10 | 0 | 5 | 0 | 0 | 10 | 0 | 3 | 1 | 5 | — |
| 7 | real:25 | 25 | 41 | 39 | 2 | 0 | 0 | 0 | 8 | 4 | 26 | 0 | 2 | — |
| 8 | real:30 | 30 | 57 | 32 | 10 | 15 | 0 | 0 | 5 | 0 | 16 | 0 | 25 | — |
| 9 | probe-a | 1 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 7 | 0 | 0 | — |
| 10 | probe-b | 1 | 11 | 8 | 3 | 0 | 0 | 0 | 1 | 0 | 8 | 0 | 1 | — |

### Disposition ledger summary (per page)

The complete ledger — one row per slide-owned source object with its source identity, ownership, disposition, reason code and evidence — is `gate/disposition-ledger.json`. Its per-page totals:

| out | page | source objects | canonical-editable | locked-visual-proxy | base-only-semantic | container-owned | unsupported | unresolved |
|---|---|---|---|---|---|---|---|---|
| 1 | real:2 | 41 | 34 | 6 | 1 | 4 | 0 | 0 |
| 2 | real:5 | 11 | 11 | 0 | 0 | 0 | 0 | 0 |
| 3 | real:7 | 3 | 2 | 0 | 1 | 0 | 0 | 0 |
| 4 | real:12 | 45 | 42 | 3 | 0 | 0 | 0 | 0 |
| 5 | real:14 | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| 6 | real:19 | 15 | 10 | 0 | 5 | 0 | 0 | 0 |
| 7 | real:25 | 41 | 39 | 2 | 0 | 0 | 0 | 0 |
| 8 | real:30 | 57 | 32 | 10 | 15 | 0 | 0 | 0 |
| 9 | probe-a | 7 | 7 | 0 | 0 | 0 | 0 | 0 |
| 10 | probe-b | 11 | 8 | 3 | 0 | 2 | 0 | 0 |

Every source object has exactly one disposition, and every emitted object maps to exactly one source object: 239 unique source identit(ies) over 239 ledger entr(ies), 233 emitted, 6 represented by a container instead of emitted.

## 5. Material deltas

**Zero material deltas.** The rebuilt-minus-source material issue set is empty, so no rebuilt-only or materially worsened condition was found on any selected page.

## 6. Retained findings (source-inherent, not repaired)

31 retained finding(s). Each one is a condition the **source** object already carries; the gate lists them explicitly instead of counting them as repaired. The complete set is `gate/retained-findings.json`.

| condition | count |
|---|---|
| `table_cell_whitespace_placement` | 2 |
| `text_overflow` | 29 |

- out p1 `/slide[2]/shape[@id=49]` `text_overflow` → `slide-001-textbox-014`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p2 `/slide[5]/shape[@id=100085]` `text_overflow` → `slide-002-textbox-011`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p2 `/slide[5]/shape[@id=100106]` `text_overflow` → `slide-002-textbox-008`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p3 `/slide[7]/shape[@id=2]` `text_overflow` → `slide-003-picture-001`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p3 `/slide[7]/shape[@id=3]` `text_overflow` → `slide-003-textbox-003`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p4 `/slide[12]/shape[@id=100084]` `text_overflow` → `slide-004-textbox-017`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p4 `/slide[12]/shape[@id=100096]` `text_overflow` → `slide-004-textbox-026`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p4 `/slide[12]/shape[@id=100097]` `text_overflow` → `slide-004-textbox-027`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p4 `/slide[12]/shape[@id=100103]` `text_overflow` → `slide-004-textbox-033`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p4 `/slide[12]/shape[@id=100104]` `text_overflow` → `slide-004-textbox-034`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p4 `/slide[12]/shape[@id=100107]` `text_overflow` → `slide-004-textbox-037`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p4 `/slide[12]/shape[@id=100109]` `text_overflow` → `slide-004-textbox-039`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p4 `/slide[12]/shape[@id=100113]` `text_overflow` → `slide-004-textbox-043`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p4 `/slide[12]/shape[@id=100114]` `text_overflow` → `slide-004-textbox-044`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p5 `/slide[14]/shape[@id=100005]` `text_overflow` → `slide-005-textbox-001`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p5 `/slide[14]/shape[@id=100011]` `text_overflow` → `slide-005-textbox-007`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p5 `/slide[14]/shape[@id=100012]` `text_overflow` → `slide-005-textbox-008`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p6 `/slide[19]/shape[@id=11]` `text_overflow` → `slide-006-textbox-011`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[19]/shape[@id=2]` `text_overflow` → `slide-006-picture-012`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[19]/shape[@id=334]` `text_overflow` → `slide-006-textbox-002`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[19]/shape[@id=336]` `text_overflow` → `slide-006-textbox-010`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[19]/shape[@id=6]` `text_overflow` → `slide-006-picture-014`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p6 `/slide[19]/shape[@id=8]` `text_overflow` → `slide-006-picture-015`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p7 `/slide[25]/shape[@id=100002]` `text_overflow` → `slide-007-textbox-003`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p7 `/slide[25]/shape[@id=136]` `text_overflow` → `slide-007-textbox-024`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p7 `/slide[25]/shape[@id=142]` `text_overflow` → `slide-007-textbox-025`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p7 `/slide[25]/shape[@id=22]` `text_overflow` → `slide-007-textbox-034`: the source object already carries this condition and the rebuilt object reproduces it without materially worsening its measured pressure
- out p8 `/slide[30]/shape[@id=100109]` `text_overflow` → `slide-008-shape-009`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p10 `/slide[1]/shape[@id=100000]` `text_overflow` → `slide-010-textbox-001`: the source object carries this condition and the rebuilt object does not report it; it stays visible as a source-inherent finding rather than being claimed as repaired
- out p3 `/slide[7]/table[@id=5]` `table_cell_whitespace_placement` → `slide-003-table-002`: 2 table cell(s) carry the same characters but place their whitespace differently; the difference is reported here and does not block acceptance
- out p6 `/slide[19]/table[@id=330]` `table_cell_whitespace_placement` → `slide-006-table-003`: 1 table cell(s) carry the same characters but place their whitespace differently; the difference is reported here and does not block acceptance

## 7. Scope evidence (master/layout/inherited paint)

52 scope-evidence record(s). These are findings and omissions about values the slide does not own; they are never reported as repaired slide-owned objects.

| condition | count | mapped |
|---|---|---|
| `inherited_paint_omission` | 22 | 22 |
| `slide_field_not_evaluated` | 30 | 0 |

The complete set is `gate/scope-evidence.json`. A representative record of each condition:

- `slide_field_not_evaluated` (mapped=False) `—` on source page 2: the finding names the slide (master) rather than a slide-owned object, so it is inherited or slide-level scope evidence and is never mapped onto a rebuilt object
- `inherited_paint_omission` (mapped=True) `—` on source page None: the source object's visible appearance depends on a value the slide does not own, so the rebuilt deck legitimately omits that inherited paint; the object is reported as base-only scope evidence and never as a repaired slide-owned object

## 8. Proxy isolation proofs

| proxy | source object | disposition | raster | density | guard band | paint fraction | passed |
|---|---|---|---|---|---|---|---|
| `slide-001-picture-007` | `/slide[2]/group[@id=88]` | locked-visual-proxy | 121x19 | 2.00475 | 2 | 0.432143 | True |
| `slide-001-picture-010` | `/slide[2]/group[@id=40]` | locked-visual-proxy | 121x19 | 2.00475 | 2 | 0.432143 | True |
| `slide-001-picture-028` | `/slide[2]/shape[@id=8]` | base-only-semantic | 1705x123 | 2.00034 | 2 | 0.000000 | True |
| `slide-003-picture-001` | `/slide[7]/shape[@id=2]` | base-only-semantic | 684x59 | 1.99941 | 2 | 0.000000 | True |
| `slide-004-picture-004` | `/slide[12]/shape[@id=100068]` | locked-visual-proxy | 886x69 | 2.00096 | 2 | 0.230628 | True |
| `slide-004-picture-007` | `/slide[12]/shape[@id=100071]` | locked-visual-proxy | 937x69 | 2.00086 | 2 | 0.231362 | True |
| `slide-004-picture-010` | `/slide[12]/shape[@id=100077]` | locked-visual-proxy | 937x69 | 2.00086 | 2 | 0.000000 | True |
| `slide-006-picture-001` | `/slide[19]/shape[@id=3]` | base-only-semantic | 1363x73 | 2.00015 | 2 | 0.000000 | True |
| `slide-006-picture-012` | `/slide[19]/shape[@id=2]` | base-only-semantic | 812x66 | 2.00099 | 2 | 0.000000 | True |
| `slide-006-picture-013` | `/slide[19]/shape[@id=4]` | base-only-semantic | 768x64 | 2.00000 | 2 | 0.018029 | True |
| `slide-006-picture-014` | `/slide[19]/shape[@id=6]` | base-only-semantic | 815x64 | 2.00000 | 2 | 0.247440 | True |
| `slide-006-picture-015` | `/slide[19]/shape[@id=8]` | base-only-semantic | 806x64 | 1.99975 | 2 | 0.478736 | True |
| `slide-007-picture-035` | `/slide[25]/connector[@id=95]` | locked-visual-proxy | 4x537 | 2.00113 | 2 | 0.000000 | True |
| `slide-007-picture-036` | `/slide[25]/connector[@id=23]` | locked-visual-proxy | 4x537 | 2.00113 | 2 | 0.000000 | True |
| `slide-008-picture-011` | `/slide[30]/shape[@id=100111]` | locked-visual-proxy | 301x46 | 2.00135 | 2 | 0.213977 | True |
| `slide-008-picture-012` | `/slide[30]/shape[@id=100112]` | locked-visual-proxy | 301x46 | 2.00135 | 2 | 0.245677 | True |
| `slide-008-picture-013` | `/slide[30]/shape[@id=100113]` | locked-visual-proxy | 301x46 | 2.00135 | 2 | 0.213977 | True |
| `slide-008-picture-018` | `/slide[30]/shape[@id=100125]` | base-only-semantic | 320x207 | 2.00317 | 2 | 0.000000 | True |
| `slide-008-picture-022` | `/slide[30]/shape[@id=100132]` | base-only-semantic | 308x207 | 2.00000 | 2 | 0.000000 | True |
| `slide-008-picture-024` | `/slide[30]/shape[@id=100024]` | base-only-semantic | 1177x36 | 2.00017 | 2 | 0.000000 | True |
| `slide-008-picture-027` | `/slide[30]/shape[@id=9]` | base-only-semantic | 270x207 | 1.99625 | 2 | 0.000000 | True |
| `slide-008-picture-028` | `/slide[30]/connector[@id=10]` | locked-visual-proxy | 4x710 | 1.99972 | 2 | 0.000000 | True |
| `slide-008-picture-029` | `/slide[30]/connector[@id=11]` | locked-visual-proxy | 4x681 | 1.99911 | 2 | 0.000000 | True |
| `slide-008-picture-030` | `/slide[30]/connector[@id=15]` | locked-visual-proxy | 4x683 | 2.00088 | 2 | 0.000000 | True |
| `slide-008-picture-032` | `/slide[30]/shape[@id=22]` | base-only-semantic | 276x207 | 1.99926 | 2 | 0.000000 | True |
| `slide-008-picture-034` | `/slide[30]/shape[@id=24]` | base-only-semantic | 293x207 | 2.00277 | 2 | 0.000000 | True |
| `slide-008-picture-037` | `/slide[30]/shape[@id=28]` | base-only-semantic | 211x207 | 2.00097 | 2 | 0.000000 | True |
| `slide-008-picture-040` | `/slide[30]/shape[@id=38]` | base-only-semantic | 270x207 | 1.99625 | 2 | 0.000000 | True |
| `slide-008-picture-042` | `/slide[30]/shape[@id=39]` | base-only-semantic | 118x62 | 1.99825 | 2 | 0.000000 | True |
| `slide-008-picture-043` | `/slide[30]/shape[@id=40]` | base-only-semantic | 118x62 | 1.99825 | 2 | 0.000000 | True |
| `slide-008-picture-044` | `/slide[30]/shape[@id=41]` | base-only-semantic | 276x207 | 1.99926 | 2 | 0.000000 | True |
| `slide-008-picture-045` | `/slide[30]/shape[@id=42]` | base-only-semantic | 293x207 | 2.00277 | 2 | 0.000000 | True |
| `slide-008-picture-048` | `/slide[30]/connector[@id=45]` | locked-visual-proxy | 4x688 | 1.99942 | 2 | 0.000000 | True |
| `slide-008-picture-050` | `/slide[30]/shape[@id=48]` | base-only-semantic | 316x267 | 2.00321 | 2 | 0.000000 | True |
| `slide-008-picture-052` | `/slide[30]/shape[@id=50]` | base-only-semantic | 118x62 | 1.99825 | 2 | 0.000000 | True |
| `slide-008-picture-053` | `/slide[30]/connector[@id=52]` | locked-visual-proxy | 1389x5 | 2.00014 | 2 | 0.480452 | True |
| `slide-008-picture-054` | `/slide[30]/connector[@id=53]` | locked-visual-proxy | 1371x5 | 2.00029 | 2 | 0.473837 | True |
| `slide-008-picture-055` | `/slide[30]/connector[@id=54]` | locked-visual-proxy | 1372x6 | 1.99971 | 2 | 0.241473 | True |
| `slide-008-picture-056` | `/slide[30]/shape[@id=55]` | base-only-semantic | 316x267 | 2.00321 | 2 | 0.000000 | True |
| `slide-010-picture-008` | `/slide[1]/group[@id=100007]` | locked-visual-proxy | 444x304 | 2.00000 | 2 | 0.000000 | True |

40 proof(s), 40 passed. Every locked proxy carries the gate's five isolation facts: target survival, raster density, guard band, target bounds and contamination.

**6 of 40 proof(s) are of a proxy whose raster is nothing but its own background** (`paint_fraction` 0.0, so no paint of the locked object was measured in the crop): `slide-007-picture-035`, `slide-007-picture-036`, `slide-008-picture-028`, `slide-008-picture-029`, `slide-008-picture-030`, `slide-008-picture-048`. The gate's isolation facts are satisfied for these proxies -- density, guard band, bounds and contamination are measured and correct -- but they do not establish that the locked object's own pixels survived, and this report does not claim that they did. Whether those objects are blank in the source is a Gate 3 question, not a structural one.

## 9. Native table checks

| page | source object | emitted | source rows×cols | rebuilt rows×cols | cells | whitespace-only cells | failures |
|---|---|---|---|---|---|---|---|
| 5 | `/slide[5]/table[@id=100190]` | `slide-002-table-007` | 6×4 | 6×4 | 24 | — | — |
| 7 | `/slide[7]/table[@id=5]` | `slide-003-table-002` | 11×6 | 11×6 | 66 | [32, 58] | — |
| 12 | `/slide[12]/table[@id=100088]` | `slide-004-table-021` | 4×3 | 4×3 | 12 | — | — |
| 14 | `/slide[14]/table[@id=100007]` | `slide-005-table-003` | 20×2 | 20×2 | 40 | — | — |
| 14 | `/slide[14]/table[@id=100008]` | `slide-005-table-004` | 5×3 | 5×3 | 15 | — | — |
| 14 | `/slide[14]/table[@id=100009]` | `slide-005-table-005` | 6×2 | 6×2 | 12 | — | — |
| 19 | `/slide[19]/table[@id=330]` | `slide-006-table-003` | 1×2 | 1×2 | 2 | [1] | — |

## 10. Text and style readback

145 independent OfficeCLI readback(s) of canonical-editable objects; 0 disagree with the source text.


## 11. OfficeCLI validation and issue records

Source deck reads:

- `_baseline_input.pptx` validate: Validation passed: no errors found.; issues: 238
- `v042-probe-a-overlay.pptx` validate: Validation passed: no errors found.; issues: 0
- `v042-probe-b-richtext.pptx` validate: Validation passed: no errors found.; issues: 1

Rebuilt deck reads:

- `rebuilt` `rebuilt.pptx`: Validation passed: no errors found.

- rebuilt issues: 8

## 12. Artifact manifest

The gate published 93 hashed artifacts; `gate/gate-report.json` lists every one with its sha256 and size, and `artifact-manifest.json` lists every file in this bundle the same way. Both can be re-checked against disk independently:

```powershell
Get-FileHash acceptance/v0.4.2/gate/rebuilt.pptx -Algorithm SHA256
$m = Get-Content acceptance/v0.4.2/artifact-manifest.json | ConvertFrom-Json
$m.artifacts | ForEach-Object { $h = (Get-FileHash "acceptance/v0.4.2/$($_.name)" -Algorithm SHA256).Hash.ToLower(); if ($h -ne $_.sha256) { "MISMATCH $($_.name)" } }
```

The gate's artifact list, with the hash recorded in its own report (`gate/gate-report.json` carries the same values, and re-hashing any of these files from disk must reproduce them):

| artifact | sha256 | size |
|---|---|---|
| `canonical-author.html` | `00ec4b4ab94683e2cfa830322d16ecd7245cfb634009bc70bc6517d31b01b26d` | 82346009 |
| `disposition-ledger.json` | `e44279296d458e2da6ad07f4450aebc90bcda4ca815235091ec4b5b573ac6c90` | 228367 |
| `material-deltas.json` | `d4990d01e9de41f6d7bce97cb1d079aff18ce0c5fc576a2117e92b9b1cfd5d3a` | 31 |
| `pages.json` | `102331a129875d0b352516bfda45f85fee5b4abece33c40c2a6815325a49de8e` | 348576 |
| `projection/canonical-author.html` | `00ec4b4ab94683e2cfa830322d16ecd7245cfb634009bc70bc6517d31b01b26d` | 82346009 |
| `projection/projection-report.json` | `47ea31fc8556b10544261d0142c24bea8200c26b02c0e187eb7b1e63a49ad197` | 605280 |
| `projection/proxy-src1-slide-002-007.png` | `a46d3062d6aac0d510a4b4d9d195bf7a4252a16593a6b7aa6969258df227384d` | 426 |
| `projection/proxy-src1-slide-002-010.png` | `a46d3062d6aac0d510a4b4d9d195bf7a4252a16593a6b7aa6969258df227384d` | 426 |
| `projection/proxy-src1-slide-002-028.png` | `d02f5059dd6bb952407c394e9f90d0f3de7e5e4cd3f53f107201cd6340e4e3b8` | 2163 |
| `projection/proxy-src1-slide-007-001.png` | `268c5f0d48e63c16a1b3f53cfb412cc784221257fc2783715427f15f7a772df3` | 1594 |
| `projection/proxy-src1-slide-012-004.png` | `8b95be3130cca2f1803f472b9a66aa8a11b27624aca835b149418f47f1d300bc` | 1958 |
| `projection/proxy-src1-slide-012-007.png` | `4d5222705e737a903a4f91fe5eb982b7f2eba1478ccf9f7046fd4a4240954067` | 1810 |
| `projection/proxy-src1-slide-012-010.png` | `e7be84e6cea803a18656da7461a12734dc06361261fe4a2c4d8a452896953e53` | 1833 |
| `projection/proxy-src1-slide-019-001.png` | `3232f4c5b2993f5ab87b387a70b13e6debe7de2e34329fe7f17590f3e2832e5e` | 2300 |
| `projection/proxy-src1-slide-019-012.png` | `ce6d78c1c07536ad6d8f9bb3bc2e5221f52134536f4d7ecb92a05219620eec5f` | 606 |
| `projection/proxy-src1-slide-019-013.png` | `5d8a0a35b7b8f09531e779f24c0f00463710548cdd170b052394226966be6247` | 579 |
| `projection/proxy-src1-slide-019-014.png` | `2626e018a266b9eb0dba6b570df423471787143901219b53a5171aae9bcb9501` | 608 |
| `projection/proxy-src1-slide-019-015.png` | `0a9daed5235a159c55ca24c8093d249bab16db37c9c7d2314298ee3d3b6f51a0` | 598 |
| `projection/proxy-src1-slide-025-035.png` | `885bc57b68d9a9cda6dcb4ed41d8220989619689cb1c01989ab53da862614de6` | 206 |
| `projection/proxy-src1-slide-025-036.png` | `f1fbfd8b611a6d5302c56c3ee4eb9f61ad6838750d3fa77ce608073e7a1f1452` | 194 |
| `projection/proxy-src1-slide-030-011.png` | `302e01b20091f7701e945636092c1684c244a58cdd666977bb154cb8ee6b6977` | 1421 |
| `projection/proxy-src1-slide-030-012.png` | `55497945d8cb54b36d7e129e86e884003c365466735942247891c2acd33a5812` | 1337 |
| `projection/proxy-src1-slide-030-013.png` | `cb015bffd26806368b7d5271086120c8bf5f246ab5378046106fd167bb481745` | 1618 |
| `projection/proxy-src1-slide-030-018.png` | `ed7f90f230bec7a20a99ca51c412d2b6f9a7ebe12d5a94afdb11dd4cfb2d4087` | 1786 |
| `projection/proxy-src1-slide-030-022.png` | `5e8e7c102917e38db45ba158909e2bc292888890fa0569e78fce4e7a7790dcc4` | 1800 |
| `projection/proxy-src1-slide-030-024.png` | `17338be77c28f0e80a128a0837baee172673fa9ed80a0f3051eb51864591e4e5` | 1195 |
| `projection/proxy-src1-slide-030-027.png` | `130d7022c5e057ecb8ae3747c2730bbc5974e698854ce2b67d4b17d7f2a855ed` | 1900 |
| `projection/proxy-src1-slide-030-028.png` | `9444c4806e916d63676318d8ae5af403e594f07e6bae8e49cd9f51368ccc8235` | 200 |
| `projection/proxy-src1-slide-030-029.png` | `134a8c24f521660915a1f2f0ccfb90871ecdf7b1b8056b78d89a548de94e5b3b` | 213 |
| `projection/proxy-src1-slide-030-030.png` | `2bb676834cab308c9b3c7d49f92bf875386a8b051564401e87cadac8e007a6d7` | 205 |
| `projection/proxy-src1-slide-030-032.png` | `1d259a9cf563760380ad278099ce20d3883ab45d49648ce6237c8c58c3409d45` | 1774 |
| `projection/proxy-src1-slide-030-034.png` | `ffae5af9da94d33e201689dfe1a88cf280fc0d6479dc6fc9460631e30827d23d` | 1930 |
| `projection/proxy-src1-slide-030-037.png` | `1a4d72c3e0dfa9a04e283311c5e7a9bfda69379e6857de114ff9a1f2d04033d0` | 1825 |
| `projection/proxy-src1-slide-030-040.png` | `130d7022c5e057ecb8ae3747c2730bbc5974e698854ce2b67d4b17d7f2a855ed` | 1900 |
| `projection/proxy-src1-slide-030-042.png` | `57afa8641928beaea1b143cc1293f142ac18f47e03d6062e9483f14634249819` | 1125 |
| `projection/proxy-src1-slide-030-043.png` | `8204ddf6486ab41ca42887fcf8b177c7b655baf698f9ee437af0a152cb1e12de` | 1011 |
| `projection/proxy-src1-slide-030-044.png` | `1d259a9cf563760380ad278099ce20d3883ab45d49648ce6237c8c58c3409d45` | 1774 |
| `projection/proxy-src1-slide-030-045.png` | `282ca97f483e5d5a348657e673c2b75813f280a92b668a2ec19c32dbc190bc70` | 1936 |
| `projection/proxy-src1-slide-030-048.png` | `b3c23ec655d91cb1ab1e1769d86f1740073a8ac4bf7c59eb4bee9482a58d94f2` | 205 |
| `projection/proxy-src1-slide-030-050.png` | `7f9cca56cceebdabbb3de668e37936bba750781ab17d1aaee595c0385857f039` | 1988 |
| `projection/proxy-src1-slide-030-052.png` | `1a34bcf5560d64594a6b7e1a211be1ada7a8fc916638e06aaa5ceacbb51f8c8f` | 1014 |
| `projection/proxy-src1-slide-030-053.png` | `af0c6035da0bc5eeaea187f30b78daa6f9ec903acd50a1ab76bd08ad14835708` | 261 |
| `projection/proxy-src1-slide-030-054.png` | `3cc5a273124636cb27ad705bbfcca2a0c9338ebdfda71ba605d6f34db2b9723c` | 297 |
| `projection/proxy-src1-slide-030-055.png` | `48720bcbebb1e488b21bbef6c9afed424a5f8a9dbe773185ab75e0b229365b2a` | 297 |
| `projection/proxy-src1-slide-030-056.png` | `469ad3d7df039f19c0d8d6a8be0b3d02f7e5b6836d065b5f3d6003256d9eeca8` | 1211 |
| `projection/proxy-src3-slide-001-008.png` | `992fee4860fa846f6cbeaf7e4df07e13b5953222625577936c3915f1ffb7d29a` | 2278 |
| `projection/source-map.json` | `feca16eaf57bae6157197d407bd9d2cabee649dd98b2c5d2d4f720b921604815` | 564200 |
| `projection-report.json` | `47ea31fc8556b10544261d0142c24bea8200c26b02c0e187eb7b1e63a49ad197` | 605280 |
| `proxies/proxy-src1-slide-002-007.png` | `a46d3062d6aac0d510a4b4d9d195bf7a4252a16593a6b7aa6969258df227384d` | 426 |
| `proxies/proxy-src1-slide-002-010.png` | `a46d3062d6aac0d510a4b4d9d195bf7a4252a16593a6b7aa6969258df227384d` | 426 |
| `proxies/proxy-src1-slide-002-028.png` | `d02f5059dd6bb952407c394e9f90d0f3de7e5e4cd3f53f107201cd6340e4e3b8` | 2163 |
| `proxies/proxy-src1-slide-007-001.png` | `268c5f0d48e63c16a1b3f53cfb412cc784221257fc2783715427f15f7a772df3` | 1594 |
| `proxies/proxy-src1-slide-012-004.png` | `8b95be3130cca2f1803f472b9a66aa8a11b27624aca835b149418f47f1d300bc` | 1958 |
| `proxies/proxy-src1-slide-012-007.png` | `4d5222705e737a903a4f91fe5eb982b7f2eba1478ccf9f7046fd4a4240954067` | 1810 |
| `proxies/proxy-src1-slide-012-010.png` | `e7be84e6cea803a18656da7461a12734dc06361261fe4a2c4d8a452896953e53` | 1833 |
| `proxies/proxy-src1-slide-019-001.png` | `3232f4c5b2993f5ab87b387a70b13e6debe7de2e34329fe7f17590f3e2832e5e` | 2300 |
| `proxies/proxy-src1-slide-019-012.png` | `ce6d78c1c07536ad6d8f9bb3bc2e5221f52134536f4d7ecb92a05219620eec5f` | 606 |
| `proxies/proxy-src1-slide-019-013.png` | `5d8a0a35b7b8f09531e779f24c0f00463710548cdd170b052394226966be6247` | 579 |
| `proxies/proxy-src1-slide-019-014.png` | `2626e018a266b9eb0dba6b570df423471787143901219b53a5171aae9bcb9501` | 608 |
| `proxies/proxy-src1-slide-019-015.png` | `0a9daed5235a159c55ca24c8093d249bab16db37c9c7d2314298ee3d3b6f51a0` | 598 |
| `proxies/proxy-src1-slide-025-035.png` | `885bc57b68d9a9cda6dcb4ed41d8220989619689cb1c01989ab53da862614de6` | 206 |
| `proxies/proxy-src1-slide-025-036.png` | `f1fbfd8b611a6d5302c56c3ee4eb9f61ad6838750d3fa77ce608073e7a1f1452` | 194 |
| `proxies/proxy-src1-slide-030-011.png` | `302e01b20091f7701e945636092c1684c244a58cdd666977bb154cb8ee6b6977` | 1421 |
| `proxies/proxy-src1-slide-030-012.png` | `55497945d8cb54b36d7e129e86e884003c365466735942247891c2acd33a5812` | 1337 |
| `proxies/proxy-src1-slide-030-013.png` | `cb015bffd26806368b7d5271086120c8bf5f246ab5378046106fd167bb481745` | 1618 |
| `proxies/proxy-src1-slide-030-018.png` | `ed7f90f230bec7a20a99ca51c412d2b6f9a7ebe12d5a94afdb11dd4cfb2d4087` | 1786 |
| `proxies/proxy-src1-slide-030-022.png` | `5e8e7c102917e38db45ba158909e2bc292888890fa0569e78fce4e7a7790dcc4` | 1800 |
| `proxies/proxy-src1-slide-030-024.png` | `17338be77c28f0e80a128a0837baee172673fa9ed80a0f3051eb51864591e4e5` | 1195 |
| `proxies/proxy-src1-slide-030-027.png` | `130d7022c5e057ecb8ae3747c2730bbc5974e698854ce2b67d4b17d7f2a855ed` | 1900 |
| `proxies/proxy-src1-slide-030-028.png` | `9444c4806e916d63676318d8ae5af403e594f07e6bae8e49cd9f51368ccc8235` | 200 |
| `proxies/proxy-src1-slide-030-029.png` | `134a8c24f521660915a1f2f0ccfb90871ecdf7b1b8056b78d89a548de94e5b3b` | 213 |
| `proxies/proxy-src1-slide-030-030.png` | `2bb676834cab308c9b3c7d49f92bf875386a8b051564401e87cadac8e007a6d7` | 205 |
| `proxies/proxy-src1-slide-030-032.png` | `1d259a9cf563760380ad278099ce20d3883ab45d49648ce6237c8c58c3409d45` | 1774 |
| `proxies/proxy-src1-slide-030-034.png` | `ffae5af9da94d33e201689dfe1a88cf280fc0d6479dc6fc9460631e30827d23d` | 1930 |
| `proxies/proxy-src1-slide-030-037.png` | `1a4d72c3e0dfa9a04e283311c5e7a9bfda69379e6857de114ff9a1f2d04033d0` | 1825 |
| `proxies/proxy-src1-slide-030-040.png` | `130d7022c5e057ecb8ae3747c2730bbc5974e698854ce2b67d4b17d7f2a855ed` | 1900 |
| `proxies/proxy-src1-slide-030-042.png` | `57afa8641928beaea1b143cc1293f142ac18f47e03d6062e9483f14634249819` | 1125 |
| `proxies/proxy-src1-slide-030-043.png` | `8204ddf6486ab41ca42887fcf8b177c7b655baf698f9ee437af0a152cb1e12de` | 1011 |
| `proxies/proxy-src1-slide-030-044.png` | `1d259a9cf563760380ad278099ce20d3883ab45d49648ce6237c8c58c3409d45` | 1774 |
| `proxies/proxy-src1-slide-030-045.png` | `282ca97f483e5d5a348657e673c2b75813f280a92b668a2ec19c32dbc190bc70` | 1936 |
| `proxies/proxy-src1-slide-030-048.png` | `b3c23ec655d91cb1ab1e1769d86f1740073a8ac4bf7c59eb4bee9482a58d94f2` | 205 |
| `proxies/proxy-src1-slide-030-050.png` | `7f9cca56cceebdabbb3de668e37936bba750781ab17d1aaee595c0385857f039` | 1988 |
| `proxies/proxy-src1-slide-030-052.png` | `1a34bcf5560d64594a6b7e1a211be1ada7a8fc916638e06aaa5ceacbb51f8c8f` | 1014 |
| `proxies/proxy-src1-slide-030-053.png` | `af0c6035da0bc5eeaea187f30b78daa6f9ec903acd50a1ab76bd08ad14835708` | 261 |
| `proxies/proxy-src1-slide-030-054.png` | `3cc5a273124636cb27ad705bbfcca2a0c9338ebdfda71ba605d6f34db2b9723c` | 297 |
| `proxies/proxy-src1-slide-030-055.png` | `48720bcbebb1e488b21bbef6c9afed424a5f8a9dbe773185ab75e0b229365b2a` | 297 |
| `proxies/proxy-src1-slide-030-056.png` | `469ad3d7df039f19c0d8d6a8be0b3d02f7e5b6836d065b5f3d6003256d9eeca8` | 1211 |
| `proxies/proxy-src3-slide-001-008.png` | `992fee4860fa846f6cbeaf7e4df07e13b5953222625577936c3915f1ffb7d29a` | 2278 |
| `proxy-isolation.json` | `87733434c24fca92fc3e4dbfcf7a4a8bf185d4da4c9144ce39b14521c2c256cb` | 58383 |
| `rebuilt.pptx` | `1138b9a79c2d1719b1ff7c7a4b91f320dc82536b6c2383be34e75b2ed618648a` | 60596529 |
| `retained-findings.json` | `6c62ca8d4d10764d81a5f13d5d33deb4af03c27fc84ae7816ad1e0561b06a8e6` | 50860 |
| `scope-evidence.json` | `88337898326e9fbdd61a82fa0dd0c80556f56627fd9ce27d4da0771c6b6680dd` | 35425 |
| `source-map.json` | `feca16eaf57bae6157197d407bd9d2cabee649dd98b2c5d2d4f720b921604815` | 564200 |

`gate/gate-report.json` and `gate/gate-report.md` are excluded from that list because a document cannot contain its own hash; the bundle's `artifact-manifest.json` covers them instead, except for itself.

## 13. Visual records

Every page has three records: the source page render, the rebuilt page render (both through OfficeCLI's HTML render path at 1600px, so they are directly comparable), and that page's Canonical Author HTML.

| # | page | source page | before | after | author html | before px | after px | before non-background | after non-background |
|---|---|---|---|---|---|---|---|---|---|
| 1 | real:2 | 2 | `visual/p01-before.png` | `visual/p01-after.png` | `visual/p01-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 2 | real:5 | 5 | `visual/p02-before.png` | `visual/p02-after.png` | `visual/p02-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 3 | real:7 | 7 | `visual/p03-before.png` | `visual/p03-after.png` | `visual/p03-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 4 | real:12 | 12 | `visual/p04-before.png` | `visual/p04-after.png` | `visual/p04-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 5 | real:14 | 14 | `visual/p05-before.png` | `visual/p05-after.png` | `visual/p05-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 6 | real:19 | 19 | `visual/p06-before.png` | `visual/p06-after.png` | `visual/p06-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 7 | real:25 | 25 | `visual/p07-before.png` | `visual/p07-after.png` | `visual/p07-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
| 8 | real:30 | 30 | `visual/p08-before.png` | `visual/p08-after.png` | `visual/p08-author.html` | 1280x720 | 1280x720 | 1.0000 | 1.0000 |
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

1. **Master/layout/header/footer omissions are scope evidence, not slide-owned loss.** 30 inherited cached-field finding(s) name the slide (master|layout) rather than a slide-owned object and carry no `source_object`; they are never mapped onto a rebuilt object. Inherited branding is not reconstructed, so a rebuilt page is painted on a blank layout.
2. **Source-inherent overlap/overflow is retained, not repaired.** 31 retained finding(s); the projection does not rewrite private source layout to reach an artificial zero-issue count, and none of them enters the material delta set.
3. **Locked proxies are excluded from native-equivalence claims.** 193 of 239 source object(s) are canonical-editable; 24 are locked visual proxies and 22 are base-only, and they are reported separately rather than folded into a native round-trip count.
4. **The gate's material-delta comparison is a text comparison.** It compares canonical characters and supported style declarations read back from the rebuilt deck; it does not compare per-run paragraph formatting, so a run-level formatting difference that preserves every character and every declared style is not a material delta. The synthetic rich-text probe records one such difference explicitly (see the pytest module's `test_the_probe_b_run_declarations_are_not_the_source_run_declarations`).
5. **A hard break inside a projected paragraph is not rebuilt as a break.** The projection emits it as a `<br>` in the Canonical Author document, and `br` is not part of the declared inline-element surface, so the New Deck path rebuilds the two sides as one paragraph with no character lost. Recorded by the pytest module's `test_the_probe_b_hard_break_is_emitted_and_the_rebuild_merges_it`.
6. **A source list's native marker is not reconstructed.** OfficeCLI reads the synthetic probe's list block back with `list=bullet` and a native `a:buChar` marker; the rebuilt deck's object is plain paragraphs, because the Canonical Author surface has no list element. The item text round-trips; the marker does not. Recorded by the pytest module's `test_the_probe_b_list_declaration_is_present_in_the_source_and_absent_from_the_rebuilt_deck`.
7. **A theme expression on a directly-declared run is not classified base-only by this projection.** The synthetic probe's theme run declares `accent1` in the source slide part and OfficeCLI reads the token back as `color: accent1`, but OfficeCLI reports no `effective.color.src` for a directly-declared scheme colour, so the gate's base-only rule never fires for it and no base-only entry is produced. The token is preserved in the source and in the projection's evidence; the projection does not claim a semantic token round trip, and this report does not either.
8. **Proxy target survival is asserted from the rebuilt deck, not measured from the proxy's pixels.** The isolation proof establishes that a picture object with the proxy's own name exists in the rebuilt deck and that its raster has the right density, bounds, guard band and contamination; it does not establish that the locked object's own paint is in that raster. 6 of 40 proof(s) here are of a raster that is nothing but its own background. Section 8 names them. This is the same limitation the independent verification report records for the gate.
9. **A manifest cannot contain its own hash.** `artifact-manifest.json` is excluded from its own inventory and records `acceptance-report.md`'s hash in `report_sha256` instead; the manifest's own hash is printed by the driver that wrote it and is not part of the bundle.

## 16. How to reproduce

```powershell
cd C:\Users\Administrator\Desktop\Shirley冷年汇报\officecli-html-to-pptx
& .\.venv\Scripts\python.exe -m pytest tests/test_v042_acceptance.py -q
& .\.venv\Scripts\python.exe .scratch/tools/run_v042_acceptance.py
```

The pytest module always runs the synthetic half. The real half is opt-in: set `HTML_TO_PPTX_V042_REAL_CORPUS=1` with the private deck present, or run this driver, which runs the full ten pages.
