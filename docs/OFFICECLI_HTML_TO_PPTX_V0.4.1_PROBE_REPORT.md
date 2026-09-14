# V0.4.1 — PPTX-to-Canonical-Author-HTML three-slide feasibility probe

**Revision 3.** Supersedes revisions 1 and 2, both of which claimed more for the
locked visual proxy than the mechanism delivered. Revision 2 rendered a proxy by
removing the slide's siblings from a *copy of the deck*; that copy still renders the
slide's layout and master, so layout paint inside the target's rectangle was baked into
the proxy, and a proxy for an object with no paint of its own came out as pure layout
paint. Revision 2's counts were inflated as a result: a container was reported as a
`locked-visual-proxy` when nothing of it was actually represented. Revision 3 rebuilds
each proxied object alone in a fresh deck, and where that is impossible the object is
reported `unsupported`. See §6 and §7.

- Spec: [GitHub #8](https://github.com/hqy2435662352/officecli-html-to-pptx/issues/8) (`ready-for-agent`)
- Implementation: branch `codex/v0.4.1-probe` — the projection seam, the OfficeCLI
  object-capture reader, the seam tests, ADR 0030, this report, and the supporting fixes
  described in §4.5
- Product version: unchanged at `0.2.0`; `V0.4.1` names this development probe only
- Contract version: `1.0`, unchanged
- OfficeCLI discovered: `1.0.148`
- Probe run: source PPTX + selected slides **2, 5, 10** → Canonical Author HTML + source map
  + projection report + structured diagnostics

The frozen flow is `Existing PPTX → PowerPoint Object Capture → Canonical Author HTML`.
`PPTX → OfficeHTML → Canonical Author HTML` is not used: no OfficeCLI HTML projection is
read, written, required, or referenced by the projection seam, and the probe runs from the
raw PPTX alone.

## 1. Verdict

**`proceed` — with a named object-surface narrowing.**

The acceptance seam works end to end on all three deliberately different slides. Every
supported object became its own canonical Author object and survived the existing New Deck
compiler with its declared semantics intact; every unsupported object was classified
explicitly instead of being faked, duplicated, or dropped; the source deck was not modified.

The narrowing is about **which source objects count as supported**. On this deck the current
Author object surface cannot reproduce three things natively, and the probe refuses to
pretend otherwise:

1. **Non-rectangular geometry presets** — `ellipse` and `rightArrow`.
2. **Container objects** — `group` (and therefore its owned `connector`s).
3. **Theme-token text color** — a text body whose resolved color is a theme expression such
   as `text1+lumMod65+lumOff35` rather than a plain color.

Those 13 of 63 objects are reported as `locked-visual-proxy` (9), `base-only-semantic` (2)
or `unsupported` (2), are excluded from every native round-trip count, and each carries a
machine-readable reason. A broader V0.4 should decide whether to deepen the Author object
surface for these three, or to accept a locked proxy for them permanently -- noting that one of
the three (a container with no paint of its own) cannot be proxied at all under the isolation
rule this report holds to.

One non-blocking `view issues` entry remains on the rebuilt deck and is waived explicitly in
§6 (finding F3). Every **structural and readback** gate is green except that waived entry. The
visual findings in F1, F4 and F8 remain documented: this probe does not claim pixel equivalence
between the source deck and either the Canonical Author HTML or the rebuilt deck, and the
Canonical Author HTML still shows visible metric differences (F10).

## 2. What was measured

| Measure | Value |
|---|---|
| Source objects on slides 2/5/10 | **63** |
| `canonical-editable` | **50** |
| `locked-visual-proxy` | **9** |
| `base-only-semantic` | **2** |
| `unsupported` / `unresolved` | **2 / 0** |
| Canonical claims verified against OfficeCLI readback | **50 / 50** |
| Text-free proxies checked for foreign paint | **6 / 6 clean** |
| Source-map mappings | **63 / 63**, one-to-one, no duplicates |
| Existing `author` Contract | **PASS**, 0 diagnostics, 736 CSS classifications |
| New Deck build (`build_author_html`) | `VISUAL_REVIEW_REQUIRED`, 3 slides published |
| `officecli validate` on the rebuilt deck | *Validation passed: no errors found.* |
| `view issues` on the rebuilt deck | 1 entry, **waived** (F3) |
| Source PPTX SHA-256 before / after | **identical** |
| Rebuilt deck, top-level objects | **61** = 43 text objects + 1 native table + 17 pictures |

The rebuilt deck's own kind accounting, read from `officecli view stats`: 44 shapes (43 text
boxes and 1 table) plus 17 pictures — 61 top-level objects. That is two fewer than the 63
projected source objects precisely because the two `unsupported` containers emit nothing, which
is the honest accounting: they are classified and diagnosed rather than represented. The two
counts describe the same set from different angles and must not be read as 44 objects that also
contain 17 pictures.

Per slide:

| Source slide | Objects | Canonical | Locked proxy | Base-only | Unsupported | What the slide probes |
|---|---|---|---|---|---|---|
| 2 | 37 | 28 | 6 | 1 | 2 | Shape/text forward probe + complex-object boundary |
| 5 | 11 | **11** | 0 | 0 | 0 | Picture/table mixed probe (fully supported) |
| 10 | 15 | 11 | 3 | 1 | 0 | Shape/text positive probe |

Slide 5 is the strongest result: **every** object on it — two pictures with source-rectangle
crops, a 6×4 native table, five filled/bordered shapes — projected canonically and verified.

## 3. Acceptance seam

One experimental high-level seam, and that is the whole interface:

```python
project_pptx_to_author_html(
    source_pptx,                 # the only required presentation input
    source_slide_numbers,        # explicit selection, e.g. [2, 5, 10]
    output_html,                 # must not already exist
    proxy_dir=...,               # where object-local locked proxies are written
) -> ProjectionResult            # HTML + source map + projection report + diagnostics
```

Everything about *how* the result is produced stays behind it. OfficeCLI `get`
(`/`, `/slide[N]`, `/slide[N]/<element>`) is used for object capture and for building the
derived working deck that object-isolated proxies are rendered from, and the source package's
own `_rels`/media parts provide picture sources. A caller never issues an OfficeCLI command,
never sees a `data-path`, and is never asked to run `view html`.

## 4. Evidence

All artifacts are task-local and outside the repository (the real deck and its large derived
artifacts are not committed). Hashes and paths are listed in the run's `artifact-manifest.json`.

```
canonical-author.html                    5,189,492 B  0e19ccc463a7eeafc54d2d4758d82ff7bef36d92eca39c8799955438887ca3d8
canonical-author.source-map.json            69,819 B  461013faa2a20b3c915f854a409a9acbe2e53380d93b24d674aad18d85f4b9b0
canonical-author.projection-report.json     78,654 B  40d2df3718caf48a777c59362455f6ce27fbadd5e90f6ca3b95fb9b871d1dd0a
rebuilt-three-slide.pptx                 3,714,621 B  f2bc9a1414e638bd1a9c2b6ef0c15a732f7ddb6e5bb798607bc081d53f33b50c
harness-evidence.json                       25,790 B  2c881ab28e8791c183a6c71762177d1d348739ea0dfd8bf30db1b46764ff37ee
artifact-manifest.json
OFFICECLI_HTML_TO_PPTX_V0.4.1_PROBE_REPORT.md
visuals/
  slide-002-00-three-way.png  01-source-pptx.png  02-canonical-author-html.png  03-rebuilt-pptx.png
  slide-005-00-three-way.png  01-source-pptx.png  02-canonical-author-html.png  03-rebuilt-pptx.png
  slide-010-00-three-way.png  01-source-pptx.png  02-canonical-author-html.png  03-rebuilt-pptx.png
```

The published `canonical-author.html` re-hashes to exactly the value the projection report
records, the source map's source hash matches the manifest, and the artifact copies are
byte-for-byte (so no line-ending translation invalidates a recorded hash). The manifest also
records the run conditions — the OfficeCLI health pre-flight and the build attempt count — so a
reviewer can see the runtime state the evidence was produced under.

The HTML hash is identical to revision 1's: the duplicate rendering was entirely inside the
proxy image bytes, so the document itself was already correct. That is precisely why the
character readback could not detect the defect.

Source identity. The acceptance input is a machine-local private PPTX fixture. Its filename,
path, exact byte size, content hash, and any other identifying metadata are deliberately
**not** recorded here, and the evidence bundle's `source-fixture/` copy must not be published.

| | |
|---|---|
| Input | a machine-local private PPTX fixture |
| Slide size | `960pt × 540pt` |
| Slides in the deck | 33 (3 selected for this probe) |
| Source-PPTX integrity | verified identical before and after the run (hash recorded in the bundle manifest) |

### 4.1 Canonical Author HTML

- **Canvas**: `1920px × 1080px`, exactly one `.slide` per selected source slide, each keeping
  its original slide number in `data-slide-number`.
- **Normalization**: the pixel-per-point factor is derived from the PPTX's own slide bounds —
  `1920px / 960pt = 2px/pt`. CSS physical-unit conversion (`96/72 = 1.3333…`) is not used
  anywhere; a PowerPoint point is not a CSS inch.
- **DOM**: clean fixed-position Author HTML. One `<div>`/`<img>`/`<table>` per source object,
  positioned at its source rectangle, with nested inline runs. No OfficeCLI viewer wrapper,
  sidebar, thumbnail rail, import map, or script from the OfficeCLI projection.
- **Paint order**: source `zorder`, verified by DOM position order.
- **Text**: paragraphs become `<br>`-separated lines; runs become canonical inline elements
  (`<strong>`, `<em>`, `<u>`) or styled `<span>`s; CJK, Latin, digits, and supplementary-plane
  characters (`🚀`) are preserved verbatim.
- **`white-space: pre`** on every text body: the source rectangle already encodes the authored
  line breaks, and a browser re-wrap would silently repartition a paragraph into extra native
  paragraphs. It is deliberately *not* clipped, because PowerPoint paints an oversized
  `noAutofit` line outside its shape.
- **Source metadata**: every emitted object carries `data-source-slide`, `data-source-object`,
  `data-source-kind`, `data-projection-disposition`, `data-projection-id`, and — for a locked
  proxy — `data-projection-locked` plus `data-projection-reason`. These do not change ordinary
  New Deck compilation semantics.

### 4.2 Locked visual proxies are object-isolated

A locked proxy is an `<img>` whose source is a data URI produced by **rebuilding the object
alone**: a fresh deck, one blank slide, and the target object re-created from the properties
OfficeCLI read back for it, then cropped to that object's own rectangle. The working deck is a
separate file in the caller's scratch directory and is deleted after each render; the source
deck is never opened for writing.

Two cheaper mechanisms are rejected, and the second is the one revision 2 got wrong:

- **Cropping the composited slide raster.** Any sibling painted inside the target's rectangle is
  captured with it. On slide 2 that meant the three filled ellipses
  (`/slide[2]/shape[@id=35,67,70]`) carried the `In 2026/2027/2028`, `9.50/19.00/24.70`, and
  `Million/USD` textboxes, which were *also* emitted as their own canonical text objects, so the
  deck painted those words twice.
- **Culling the slide's siblings from a copy of the deck.** This is subtler and was revision 2's
  design. The copy still renders the slide's layout and master, and this deck's 105 layout and
  master parts each carry four to ten painted shapes, so a layout graphic inside the target's
  rectangle is baked into the proxy exactly as a sibling would be. For an object with no paint of
  its own the result was a proxy made *entirely* of layout paint -- the opposite of
  object-local, while still reporting as a represented proxy.

Rebuilding removes the class of error rather than narrowing it: nothing else exists in the deck
being rendered, so nothing else can contribute.

Every text-free proxy is verified to contain only its own fill, the slide background, and a
one-pixel antialiased rim:

| Proxy | Source object | Geometry | Size | Enclosed foreign pixels |
|---|---|---|---|---|
| `proxy-slide-002-002.png` | `/slide[2]/shape[@id=67]` | ellipse | 245×245 | **0** |
| `proxy-slide-002-004.png` | `/slide[2]/shape[@id=70]` | ellipse | 245×245 | **0** |
| `proxy-slide-002-011.png` | `/slide[2]/shape[@id=35]` | ellipse | 293×293 | **0** |
| `proxy-slide-010-005.png` | `/slide[10]/shape[@id=100054]` | ellipse | 16×16 | **0** |
| `proxy-slide-010-009.png` | `/slide[10]/shape[@id=4]` | ellipse | 16×16 | **0** |
| `proxy-slide-010-013.png` | `/slide[10]/shape[@id=8]` | ellipse | 16×16 | **0** |

The discriminator is *enclosure*, not color distance: a foreign glyph inside a filled shape
produces a horizontal run of non-fill pixels with the fill on both sides, whereas the slide
background never is, because it lies outside the object. Against the rejected artifacts the
same check reports 6,359–7,000 enclosed foreign pixels per ellipse with pure `#FFFFFF` as the
dominant foreign color.

If an object cannot be rendered in isolation the projection does not fall back to a composited
crop: it classifies the object as `unsupported` with a blocking diagnostic
(`proxy_isolation_unavailable`) and publishes no result that could be mistaken for a complete
projection.

#### 4.2.1 Proxy density is gated on the canvas density

The DOM draws a proxy at the object's rectangle **in Author canvas pixels**, so the render must
reach the canvas density or the proxy would be enlarged and softened. The gate compares the
render's measured density against the required one:

```text
factor = raster_width / slide_width_pt
require factor + PROXY_DENSITY_TOLERANCE >= pixels_per_point
```

`PROXY_DENSITY_TOLERANCE` is `0.01`, which absorbs only whole-pixel rounding of the raster. For
this deck `pixels_per_point` is exactly `1920 / 960 = 2.0`, and the gate behaves as documented:

| Render width | Density | Gate |
|---|---|---|
| 1920px | 2.0000 px/pt | accepted |
| 1921px | 2.0010 px/pt | accepted |
| 1919px | 1.9990 px/pt | accepted (rounding only) |
| 1536px | 1.6000 px/pt | **blocked** |
| 1280px | 1.3333 px/pt | **blocked** (OfficeCLI's default) |

The two blocked rows are the point of the gate. An earlier revision used a fixed `1.6 px/pt`
floor while claiming the render met the canvas density; at 1.6–2.0 px/pt that floor would have
accepted a proxy the DOM then enlarged by 5–25%. That contradiction is removed: the required
density is now the caller's actual `pixels_per_point`, and no raster that merely clears a lower
floor is published. `tests/test_v041_projection_seam.py` pins all five rows.

#### 4.2.2 The evidence bundle is self-contained

The bundle is re-runnable and independently checkable after every scratch directory is
deleted. It carries:

| Item | Purpose |
|---|---|
| `proxies/` (13 PNGs) | the proxy assets themselves, byte-identical to the run's |
| `proxies/original-shape-identity.json` | each proxy's source slide, source object, geometry, fill, and whether it is text-free |
| `proxies/verify_proxy_isolation.py` | a runnable re-verification, including the discriminator's self-check |
| `source-fixture/source.pptx` | the acceptance input, identity-verified against the hash the run recorded |
| `artifact-manifest.json` | byte size and SHA-256 of every artifact, visual, and proxy |

Two repointing steps make the bundle describe itself rather than the run directory it came
from, and both are recorded in the manifest under `proxy_evidence.repointing`:

- `proxy_asset` in the projection report and the source map, and
  `run_path_at_projection_time` in the proxy identity record, were rewritten from the scratch
  run's absolute paths to the bundled copies. Without this, every path a bundled document
  records would die with the run directory. The manifest records the hash before and after each
  rewrite, so the change is auditable rather than silent.
- The fixture copy's identity was verified against the source hash the projection recorded
  before it was packaged; a mismatch refuses the packaging rather than shipping the wrong deck.

The only paths that still name the scratch run are its own historical provenance — the source
path in the projection report and the run directory in `harness-evidence.json` — which is what
those fields record. Two checks confirm the packaging:

```powershell
python proxies/verify_proxy_isolation.py     # 6 text-free proxies, enclosed foreign = 0
python -c "..."                              # every artifact, visual, and proxy hash vs the manifest
```

Both were run against the packaged bundle and against a copy of it placed in a different
directory, so the result does not depend on where the bundle sits.

### 4.3 Source map

Bound to the exact source SHA-256 above. 63 entries, one per selected-slide source object,
each recording source slide, source object path, source kind/name, source fingerprint, emitted
`html_id` and selector, emitted ordinal and the exact compiler object name, projected kind,
disposition, capability flags, source bounds in points, emitted bounds in pixels, and any
base-only claim or proxy reason. Verified: one-to-one, no duplicates, unique `html_id`s, every
object exactly one disposition.

### 4.4 Projection report

Records the canvas and its `canvas_source: pptx-slide-bounds`, the OfficeCLI version, the
selected slides, the disposition counts, `whole_slide_screenshot_fallback: false`, the HTML
hash, per-slide object lists, and the structured diagnostics. `native_round_trip: 50` and
`excluded_from_native_round_trip: 13` are separate numbers precisely so a proxy can never be
counted as native.

### 4.5 What was verified, and how

Verification compares the projection's **captured source semantics** against the
**independent OfficeCLI readback of the rebuilt deck**, object by object. The rebuilt object is
located by the projection's own recorded identity (`slide-NNN-<kind>-<ordinal>`, which is
exactly how the compiler names objects) — never by geometry proximity, ordinal similarity, or
visual guesswork.

Compared per canonical object: object text, bounds within the Contract's `1pt` tolerance,
paragraph count and text, paragraph alignment, and — for every character — font size, bold,
italic, color, and **typeface**. Result: **50/50 pass, 0 failures.**

Four real defects were found and fixed by this harness across the two revisions:

1. **Silent typeface substitution.** `styles.resolve_pptx_font` rewrote any typeface outside a
   Latin allowlist to `Calibri`. The deck's `微软雅黑` bodies came back as `Calibri`, which
   changes CJK line-breaking for the whole deck. Fixed: a font stack's own first concrete
   family is now treated as a request for that typeface; only a *generic* keyword
   (`sans-serif`) is a request for the environment to choose. The rebuilt deck now reads back
   `微软雅黑 ×42, Arial ×6`, matching the source.
2. **Hash mismatch on Windows.** `Path.write_text` rewrites `\n` to `\r\n`, so the recorded
   `author_html_sha256` did not match the published file. Fixed by writing the hashed artifact
   without newline translation.
3. **Proxy clipping.** A locked proxy was cropped exactly to the object's rectangle, which cut
   the antialiased edge off a 6.24pt bullet dot and rendered it as a fragment. Fixed with a
   2px guard band plus a matching negative offset, so the visible rectangle is still exactly
   the source bounds.
4. **Proxy contamination** (revision 2). A proxy was cropped from the composited slide raster
   and captured overlapping sibling objects, causing duplicate rendering. Fixed by rendering
   the target object alone in a derived deck, as described in §4.2.

## 5. Classification rules (auditable)

| Disposition | Rule |
|---|---|
| `canonical-editable` | Supported kind; geometry is `rect`/`roundRect`; fill and outline are plain solids the slide declares; rotation 0; and no *rendered* property resolves from outside the slide. |
| `locked-visual-proxy` | A container kind (`group`, `connector`, `chart`, `diagram`, …), a non-canonical geometry preset, or a non-solid fill/outline. Emitted as one object-isolated raster at 2px/pt, carrying source identity and a reason. |
| `base-only-semantic` | Every rendered property is representable, but a *visible* text property (color/font/size/bold/italic/underline) resolves from `/master`, `/layout`, or `/theme`. |
| `unsupported` | A structurally unsupported case, e.g. merged table cells, or an object that cannot be rendered in isolation. |
| `unresolved` | Missing, ambiguous, or unusable source evidence — an identity or a picture source that cannot be established. Always a blocking diagnostic. |

Two deliberate, documented narrowings of the `base-only` rule:

- **Master paragraph-layout defaults are not base-only.** `effective.lineSpacing` /
  `spaceBefore` / `spaceAfter` resolved from `/master[N]/bodyStyle/lvl1pPr` are emitted as an
  explicit CSS `line-height` when the slide declares a spacing, which the compiler lowers back
  onto the native paragraph, so the value is *preserved*, not reconstructed. Treating them as
  base-only would have classified 61 of the 63 objects and destroyed the probe's signal.
- **A text-free shape never paints a text property**, so its inherited text defaults are not a
  base-only claim.

What remains as base-only is exactly the theme-token case: the two slide-2/10 text bodies whose
resolved color is `text1+lumMod65+lumOff35` — a theme expression that is not a plain color and
is not reconstructible without rebuilding the theme.

## 6. Findings

| # | Finding | Severity | Where |
|---|---|---|---|
| F1 | **Corrected.** The top brand band (a slide-title strip and a brand logo lockup) and the page number are **not slide-owned content on either slide**: slide 5's own 11 objects are two large pictures (a compound body graphic at `95.3,270 854.9×230.25pt` and a product image at `44.4,176.55 101.8×71.1pt`) plus a table and five shapes. The band comes from the slide's master/layout in the source deck, and it is **absent from both the Canonical Author HTML and the rebuilt PPTX**. The `11/11` result for slide 5 refers to those 11 slide-owned objects only. Masters, layouts, and themes are explicitly out of scope for V0.4.1 and are not restored on any slide. | expected, not a defect | slides 5, 10 |
| F2 | A locked group's owned connectors are recorded as `nested_container_object` diagnostics and are represented by the group's own isolated proxy — never emitted a second time on top of it. | by design | slide 2 |
| F3 | **Corrected and waived.** `officecli view issues` reports one *advisory* overflow on the rebuilt deck: `/slide[3]/shape[@id=100057]`, "text overflow: 8 lines at 16.0pt need 154pt, usable 142pt". The correct source mapping is `slide-003-textbox-010` → **`/slide[10]/shape[@id=5]` (`S2_Bullet1_0`, the "How\`s the selling" card body: `Market preference; / STOCK / How about another 10K?`)**, not the first card as the previous report stated. The source object has the same `141.6pt` box, the same paragraph structure, and `autoFit: none`, so the condition is inherent to the source deck and is not introduced by the projection. The rebuilt object reads back at the identical box and the three slides' visual evidence shows the text fully visible, not clipped. **Accepted as an approved non-blocking exception** for V0.4.1; a V0.4 delivery gate that requires zero issues must either reconstruct the source's line-spacing metric or accept reflow, which is a product decision, not a projection-probe decision. | minor, waived | rebuilt slide 3 |
| F4 | Intra-paragraph hard breaks (`<a:br/>`) are re-partitioned into paragraph boundaries, because one separator is the only orthography the current Author Contract has. The visible line and its run formatting are both preserved; only the paragraph count changes. | normalization | slide 2, `Growth Rate / ＞100%` |
| F5 | Adjacent source runs that resolve to identical formatting merge into one Canonical Run. This is the Contract's own Canonical Run policy; verification is character-exact rather than run-count-exact so the normalization is proven not to lose any character's formatting. | normalization | slides 2, 5, 10 |
| F6 | A picture's `srcRect` crop is baked into the emitted media, because the canonical Author picture surface has no source-rectangle property. The visible framing is preserved; the rebuilt picture carries no `srcRect`. Recorded as `source_rect_handling: baked-into-emitted-media` in the evidence. | limitation | slide 2 |
| F7 | The rebuilt deck is validation evidence only. It is a *new* three-slide deck on a blank master, not an edit of the source, and not a claim of lossless reconstruction. No write-back through source identities is implemented. | scope | — |
| F8 | **Corrected.** The slide-2 visual defect in the previous evidence was **not** a renderer font/metric artifact: the locked proxies themselves contained the sibling textboxes' glyphs, so the deck painted those words twice. The `50/50` character readback could not see it because the duplicate existed inside image bytes. Revision 2 fixes the cause (§4.2) and adds a regression that fails red on it (§8). The remaining differences between the Canonical Author HTML panel and the source are text-metric drift on the Arial-set number labels, not duplication. | fixed | slide 2 |
| F9 | OfficeCLI intermittently exits `1` with **no output at all** on a 63 MB deck when the machine is loaded (measured at roughly two in five invocations). This is a runtime property of the shared environment, not of the projection: the identical command succeeds unchanged moments later. The reader retries with backoff, the harness gates expensive steps on a health pre-flight, and the evidence records how many attempts were needed. | environmental | whole run |
| F10 | **Accepted visual difference, not a defect.** The Canonical Author HTML shows text-metric drift against the source on slide 2 (`Growth Rate ＞100%` / `＞30%` still crowd the neighbouring circles) and on slide 5 (one two-word label still reaches into the first icon's column). In both cases the *source object has the same box, the same font size, and `autoFit: none`*, and the source deck's own render overflows its box too; the browser simply advances Arial and `微软雅黑` slightly wider than the source renderer did. The rebuilt deck re-wraps and is readable. Slide 10's three red bullet dots are also slightly softer in the rebuilt deck because a 6.24pt ellipse is only ~16px at canvas density. None of this is object loss, duplication, or misclassification, and **none of it is a claim of pixel equivalence**. | accepted visual finding | slides 2, 5, 10 |
| F11 | **Superseded by F12.** |
| F12 | **A container with no paint of its own cannot be proxied, and is not.** Slide 2's two groups are `group` shapes whose `sp` carries no geometry, fill, or line: everything visible about them belongs to two child connectors, and OfficeCLI reports those children in the group's own child coordinate space (values far outside the group's rectangle, with a `childOffset`/`childExtent` that do not map back without the DrawingML group transform). A rebuild of the container alone therefore renders nothing. Revision 2 published that empty render as a proxy and counted it as represented; revision 3 classifies both `unsupported` with a reason. The consequence is visible and must be stated plainly: **the two connector arrows are absent from the Canonical Author HTML on slide 2**, and they are therefore absent from the rebuilt deck. | capability boundary | slide 2 |
| F13 | **Review-driven, fixed.** Two independent review passes over revision 2 found: the seam published HTML labelled "Canonical Author HTML" without checking the Contract itself; a non-16:9 deck had its canvas silently snapped to 1920×1080 while the scale factors stayed derived from the deck, placing objects off-canvas; the stale-fingerprint test compared a value against itself; `resolve_pptx_font` could emit a CSS-wide keyword or a `var()` as a typeface, restoring the silent-substitution class it was meant to remove; and the contamination discriminator was quiet about layout paint. All five are fixed and covered by tests; see §7. | fixed | whole change |

## 7. Revision record

Revision 1 was rejected: *"locked proxy visual isolation: FAIL"*. The reviewer's diagnosis was
correct and is reproduced here in its own terms.

| Revision 1 claim | Revision 2 position |
|---|---|
| "The rebuilt-deck panel looks worse than it is; the readback is character-exact." | Wrong. The proxy *was* the duplicate; character readback cannot see text inside an image. Finding F8 corrected. |
| "Slide 5's brand band is slide-owned, so it survives." | Wrong. Slide 5's own objects are elsewhere on the page; the band is layout-derived and absent from both the HTML and the rebuilt deck. Finding F1 corrected. |
| "`/slide[3]/shape[@id=100057]` is the first card's body." | Wrong. It is `/slide[10]/shape[@id=5]`, the middle card's body. Finding F3 corrected. |
| "The rebuilt deck has one advisory issue; everything else is green." | Correct, but the previous report did not label it a waiver. Now explicit in F3. |

What revision 2 changed, and what revision 3 changed on top of it:

| Area | Revision 2 | Revision 3 |
|---|---|---|
| Proxy mechanism | cull the slide's siblings from a copy of the deck | rebuild the object alone in a fresh deck |
| Layout/master paint in a proxy | present, undetected | impossible by construction |
| A paint-less container | reported `locked-visual-proxy` (empty render) | reported `unsupported`, with the reason |
| Contract check | left to the caller | the seam checks it before publishing |
| Non-16:9 deck | canvas silently snapped to 1920×1080 | refused, naming the mismatch |
| Proxy density gate | a 1.6 px/pt floor | the caller's actual `pixels_per_point` |
| Degenerate font values | passed through as a typeface | CSS-wide keywords and `var()` fall back |
| Stale-fingerprint test | compared a value against itself | projects two decks and compares bindings |
| Counts | 50 / 11 / 2 / 0 | 50 / 9 / 2 / 2 |

Revision 3's fixes came from two independent review passes over revision 2 — one on documented
standards, one adversarial on correctness — plus a spec-conformance pass. The stored-output
defects they found are recorded as F13.

The two review passes also produced items that were examined and **not** actioned, recorded here
so the decision is visible rather than silent:

- a claim that the seam must hard-code slides 2/5/10. Rejected: the seam's parameter is the
  selection by design, and the spec's fixed selection constrains the probe's configuration, not
  the seam's signature.
- a claim that the report's real-deck numbers are unsupported because the harness is not
  committed. Accepted as a limitation, not a defect: the spec requires the real artifacts to be
  exercised while also forbidding the deck and its derived content from the repository, so the
  harness and bundle are task-local by design, and the bundle carries the fixture and a runnable
  re-verification so the numbers can be re-derived.
- reported code smells left in place: the OfficeCLI subprocess runner now exists in three
  places, and the projector's capability vocabulary is parallel to `contract.py`'s object-kind
  declaration. Both are real duplication and both are follow-up work; neither affects this
  probe's correctness, and folding them in here would mean refactoring the compiler's shared
  runner on a merge-bound branch.

Two files edited by revision 1 (`styles.py`, `__init__.py`) were found reverted in the shared
working tree, because a concurrent task switched that tree's branch while this work was in
progress. Both revisions were re-applied from the parked commit that held them, and all five
files were then verified byte-identical to the validated state before the final run. Revision 2
was developed in a git worktree at the frozen base commit so the concurrent task could not
affect it.

Not changed: the seam signature, the classification model, the source map, the projection
report schema, the Contract, the package version, the public command surface.

## 8. Regression coverage

The fixture is a minimal synthetic deck built through OfficeCLI itself, so the real 63 MB
acceptance deck is never committed. It now contains an explicit overlay probe:

```text
one text-free filled ellipse (40,200 120x120pt, #D96666)
+ three independent textboxes painted inside its rectangle
    In 2026 / 9.50 / Million/USD
```

Required assertions, all implemented:

- the ellipse's proxy contains **no enclosed foreign pixels** — the exact check that fails on
  the rejected artifacts;
- the enclosure discriminator **fires on a synthetic contaminated image** and reports zero on
  a flat fill, so a green result cannot come from a discriminator that never fires;
- the proxy's size is the object's own rectangle at the canvas factor plus the guard band, so
  it is provably not a crop of something larger;
- each sibling textbox is projected as its own `canonical-editable` object carrying its text;
- every canonical object's text is present in the DOM's real text content.

| Suite | Result |
|---|---|
| `tests/test_v041_projection_seam.py` (27 tests) | **27 passed** |
| Every other test module, run individually | **178 passed**, see below |

### 8.1 Test-suite runtime instability (and why it is not a regression)

Running every module in **one** pytest session on this machine leaves the OfficeCLI-backed
V03-01 modules failing: those tests call `officecli` through `subprocess.run(..., check=True)`
with no retry, and OfficeCLI intermittently exits `1` with no output at all once many
invocations have accumulated in one process tree. The same modules pass when run on their own,
one session each:

| Module | Alone |
|---|---|
| `test_v03_01_soft_wrap.py` | 12 passed |
| `test_v03_01_hard_breaks.py` | 14 passed |
| `test_v03_01_rich_text_runs.py` | 8 passed |
| `test_v03_01_run_identity.py` | 14 passed |
| `test_v03_01_acceptance.py` | 29 passed |
| `test_officecli_compiler.py` | 17 passed |
| `test_acceptance.py` | 18 passed |
| `test_application.py` | 11 passed |
| `test_runtime.py` | 6 passed |
| `test_contract_checker.py` | 14 passed |
| `test_measurement.py` | 2 passed |
| `test_officehtml_roundtrip.py` | 10 passed |
| `test_pptx_screenshot_render.py` | 3 passed |
| Everything except the OfficeCLI-heavy V03-01 modules, in one session | 108 passed |

This is the same runtime property recorded as F9, and it is worth stating plainly: the
projection seam retries it, the probe harness waits for a healthy runtime, but the pre-existing
V03-01 tests do not, so their batch result on a loaded machine is not a dependable signal.
Revision 1 hit and fixed the same class of failure inside the fixture builder; making every
OfficeCLI call in the repository retry is a separate change and is not part of V0.4.1.

## 9. What V0.4.1 did not do

All 33 slides; any modification or patch of the source PPTX; the Existing Deck Delta Compiler;
source-identity write-back; recovery of the original Flex/Grid or semantic layout; restoration
of masters, layouts, themes, placeholders, native charts, groups, or bound connectors; merged
table reconstruction; treating raster proxies as native editable objects; whole-slide
screenshot fallback; widening the Author Contract; a new public command; release packaging; a
package-version bump; and committing the real deck or its derived content to the repository.
The package version remains `0.2.0`.

## 10. Reproduction

The probe harness is task-local; the projection seam and its tests are in the repository.

```powershell
Set-Location '<repository root>'

# 1. The projection seam's own tests (synthetic fixture, no customer content).
.\.venv\Scripts\python.exe -m pytest tests\test_v041_projection_seam.py -q

# 2. The existing suite must still pass unchanged. The full-deck golden-case
#    regression is excluded here only because it needs its own large fixture.
.\.venv\Scripts\python.exe -m pytest tests -q --ignore=tests/test_algeria_full_deck.py

# 3. The real three-slide probe (harness lives in the run's scratch directory).
.\.venv\Scripts\python.exe .scratch\v041\harness.py `
  --source '.scratch\v041\source.pptx' `
  --run-dir '.scratch\v041\run-final'
```

The seam's tests need no OfficeCLI: on a machine without it they skip rather than fail, so the
repository's CI collects them and reports `skipped`. The three-slide probe above does need
OfficeCLI, a copy of the private fixture, and the harness scripts, none of which belong in the
repository.

## 11. Recommendation

**Proceed to the broader V0.4 compiler, narrowed to the verified object surface.**

- The seam, the honest classification model, the isolated-proxy representation, the source map,
  and the build/evidence path are proven on real artifacts and should be kept as they are.
- Generalize across the remaining 30 slides **behind a supported-object gate** that reports its
  disposition ledger per slide, so an operator sees the canonical/locked/base-only mix before
  trusting a whole-deck projection.
- Treat the three named boundaries — non-rectangular presets, `group`/`connector` containers,
  and theme-token text color — as the explicit V0.4 object-surface decision. Deepening any of
  them into the Author Contract is a Contract change and belongs in its own spec with its own
  round-trip evidence, not in a projection probe.
- Resolve F3 as a product decision before any delivery gate that requires zero `view issues`
  entries, and keep F1 explicit: master/layout content is not restored.
- Keep the current verification style: compare declared semantics against an independent
  readback, count locked proxies on the excluded side of every native-equivalence number, and
  prove every representation is object-isolated before calling it a proxy.
