# OfficeCLI HTML-to-PPTX Compiler MVP — Working Context

## Language

**officecli-html-to-pptx**:
An independent product that compiles its Author Contract into a new editable
PowerPoint presentation. From V0.2 onward it is not a compatible backend or
release line of the original `html-to-pptx` product.
_Avoid_: OfficeCLI V0.2, html-to-pptx OfficeCLI backend

**Original html-to-pptx**:
The upstream-origin project from which browser measurement and other source
code were initially derived. Its product identity, compatibility promises, and
release sequence do not define `officecli-html-to-pptx` V0.2.
_Avoid_: legacy officecli-html-to-pptx

**Product Repository**:
The independent `officecli-html-to-pptx` GitHub repository that preserves the
existing commit ancestry without remaining in GitHub's fork network.
_Avoid_: MVP nested worktree, renamed GitHub fork

**Upstream Source**:
The original `Design-Arena/html-to-pptx` repository, retained as an optional
source of selected changes and as provenance for reused code. It does not set
the Product Repository's roadmap or compatibility contract.
_Avoid_: parent product, release upstream

**Product Distribution**:
The installable Python distribution named `officecli-html-to-pptx`. It belongs
to the independent product and does not continue the original distribution's
version or compatibility promises.
_Avoid_: html-to-pptx package, OfficeCLI package

**Product Version**:
The single SemVer shared by the Python distribution, Codex Plugin, and GitHub
release. The Authoring Skill ships with that Plugin version rather than having
an independent release sequence.
_Avoid_: capability-line version, Skill revision

**Contract Version**:
The compatibility version of the Author Contract, advanced only when the
accepted HTML language changes. It is independent of Product Version.
_Avoid_: product release, OfficeCLI version

**OfficeCLI Minimum Supported Version**:
The lowest OfficeCLI version accepted for rendering and validation. V0.2
requires OfficeCLI `>=1.0.147`; every build records the discovered version in
its evidence. It is an external-runtime floor, not a Product Version.
_Avoid_: OfficeCLI Compatibility Baseline, exact OfficeCLI pin, Contract version

**Rendering Compatibility Pair**:
The pinned Playwright version and its managed Chromium revision validated
together for a Product Version. A formal build must use this browser pair;
installed system Chrome and unverified browser revisions are not treated as
implicitly compatible. OfficeCLI, Python, and Node.js have separately
documented supported ranges.
_Avoid_: latest available tools, optimistic renderer range

**Supported Platform**:
Windows is the only formally supported V0.2 operating-system environment. The
product avoids unnecessary platform coupling, but it does not claim macOS or
Linux compatibility without end-to-end acceptance evidence.
_Avoid_: theoretically portable, cross-platform by dependency

**WSL2 Validation Track**:
The planned first Linux validation environment, using WSL2 on the current
Windows machine. It is a future acceptance track rather than a V0.2 support
claim; passing it does not automatically imply support for all Linux systems.
_Avoid_: current Linux support, generic Linux certification

**Product Namespace**:
The Python import namespace `officecli_html_to_pptx`, aligned with the Product
Distribution and intentionally not aliased through `html_to_pptx`.
_Avoid_: html_to_pptx compatibility namespace

**Product Command**:
The self-describing `officecli-html-to-pptx` command used primarily by agents
through the Authoring Skill. Its supported task vocabulary is `doctor`,
`capabilities`, `check`, `build`, and `finalize`; it must not be described as
an OfficeCLI command or version.
_Avoid_: html-to-pptx, OfficeCLI converter command

**Agent-First CLI**:
A deterministic execution interface whose help, diagnostics, examples, exit
codes, and structured output let an agent use the product without inspecting
repository source. It is the Authoring Skill's execution protocol, not the
product's primary conversational experience. Users express the desired
deliverable; the Skill and Agent manage command flags, collision handling,
revision names, and artifact association without requiring shell knowledge.
_Avoid_: human-only shell UI, source-discovery interface

**Environment Doctor**:
The read-only `doctor` command that reports required, discovered, and
compatible runtime prerequisites through the Command Result Envelope. It
provides exact remediation commands and a recheck instruction but never
installs, upgrades, downloads, or rewrites environment configuration.
_Avoid_: bootstrap command, automatic setup

**Dependency Remediation**:
A separately authorized environment change that installs or upgrades a missing
or incompatible prerequisite reported by the Environment Doctor. Neither a
build request nor a failed prerequisite check grants permission to perform it.
_Avoid_: transparent install, build-time download

**Capability Manifest**:
The machine-readable description returned by `capabilities --json`, generated
from the installed product's contract and version authorities. It tells an
agent what is supported without requiring source inspection.
_Avoid_: copied capability checklist, help-text contract

**Command Result Envelope**:
The versioned JSON shape shared by `doctor`, `capabilities`, `check`, `build`,
and `finalize`. Agents depend on its stable status, diagnostic, and artifact
fields rather than parsing human-readable messages.
_Avoid_: console-text scraping, ad hoc command JSON

**Visual Review**:
The Agent's slide-by-slide judgment of the persisted HTML/PPTX Comparison
Images. It records material deviations that require revision separately from
detail deviations that are reported without blocking delivery.
_Avoid_: pixel-perfect gate, screenshot generation

**Major Finding**:
A visual deviation that changes visible content, meaning, readability,
structure, editability, or the clearly perceived layout. Any Major Finding
requires a Revision Loop.
_Avoid_: blocker score, pixel threshold

**Minor Finding**:
A deliverable detail deviation that should be reported but does not materially
change content, meaning, readability, structure, editability, or layout. Minor
Findings never trigger an automatic Revision Loop.
_Avoid_: polish blocker, warning score

**PASS_WITH_FINDINGS**:
The completed outcome when every slide has been reviewed, no Major Finding
exists, and at least one Minor Finding is reported. It is a finished delivery,
not a pending revision.
_Avoid_: partial pass, soft failure

**REVISION_REQUIRED**:
The non-final outcome when at least one Major Finding exists. The Authoring
Skill must enter a Revision Loop instead of delivering the current build.
_Avoid_: low visual score, pass with major findings

**Revision Loop**:
A new Author HTML revision, build, comparison set, and Visual Review triggered
only by a material visual deviation. Detail deviations do not enter this loop.
After the initial build, the Authoring Skill may perform at most three automatic
revision cycles before it must pause and ask the user whether to continue.
_Avoid_: automatic retry, minor-polish loop

**Automatic Revision Budget**:
Three Agent-managed repair, rebuild, and Visual Review cycles after the initial
build. Infrastructure retries that do not create a new Author HTML revision do
not consume this budget. If major findings remain after the third cycle, the
Skill preserves the evidence and requests user confirmation before a fourth.
_Avoid_: unlimited self-repair, counting the initial build as a revision

**Development Release Gate**:
The deliberately small V0.2 release check: relevant tests and the existing
suite, one representative real Author HTML run through the complete product
path, an openable editable PPTX with complete evidence, `compileall`, and
`git diff --check`. It does not repeat a platform matrix, every Skill entry
mode, the full Algeria regression, or WSL2 validation.
_Avoid_: certification program, multi-layer release framework

**Finalization**:
A lightweight validation of the completed Visual Review record and its
association with one Evidence Bundle. It never recompiles, rerenders, performs
pixel comparison, or substitutes for visual judgment. The final outcome is
derived mechanically from complete slide coverage and finding severity rather
than asserted by the reviewing Agent.
_Avoid_: second build, automatic visual approval

**Evidence Bundle**:
The deterministic companion directory produced by `build`, containing the
Contract, manifest, validation, issues, result, visual-review record, and one
HTML/PPTX Comparison Image per slide.
_Avoid_: PPTX-only success, duplicate screenshot archive

**Artifact Pair**:
One non-overwriting PPTX and its same-stem `.evidence/` directory, bound by a
build identifier plus PPTX and Author HTML hashes. The pair is delivered as one
logical result and must never be assembled from different build attempts.
_Avoid_: replace-in-place output, detached evidence directory

**Revision Pair**:
A new Artifact Pair created by the Revision Loop under an Agent-managed
revision suffix such as `-r01`. Revision allocation is workflow bookkeeping,
not a filename decision imposed on the user.
_Avoid_: overwritten retry, user-managed run directory

**Comparison Image**:
A persisted side-by-side rendering of one Author HTML slide and the matching
generated PPTX slide. Separate source and PPTX screenshots are temporary build
inputs and are not retained in the Evidence Bundle.
_Avoid_: source screenshot, PPTX screenshot, representative sample

**Author Compiler**:
The V0.2 supported capability that compiles Author Contract HTML into a new
editable PowerPoint presentation.
_Avoid_: OfficeHTML compiler, legacy renderer

**Candidate HTML**:
Any HTML supplied by a user or produced during authoring before the current
Author Contract has accepted it. Its filename, source, appearance, or prior use
never implies compatibility.
_Avoid_: assumed Author HTML, trusted HTML

**Author HTML**:
Candidate HTML that has passed the current Author Contract and is eligible for
browser review and Author Compiler input.
_Avoid_: arbitrary HTML, unchecked deck HTML

**Contract Remediation**:
The Skill-guided work that turns rejected Candidate HTML into Author HTML by
either focused repair or reconstruction, followed by another Contract check.
_Avoid_: compiler fallback, bypass

**Focused Repair**:
Local, explainable changes that make Candidate HTML satisfy the current Author
Contract without redesigning its page composition.
_Avoid_: Contract relaxation, hidden content removal

**Reconstruction**:
Creation of a new Author HTML workbench when Candidate HTML cannot satisfy the
current Contract through Focused Repair without materially reauthoring its
layout. The original input remains unchanged.
_Avoid_: mechanical scaling, in-place rewrite

**Development Path**:
An experimental, explicitly user-authorized branch that may change the Author
Contract or product source to develop a general capability. It is never entered
automatically because Candidate HTML failed Contract Remediation.
_Avoid_: permissive mode, automatic Contract expansion

**Development Authorization**:
An explicit user instruction to change the product's Contract or source in
order to develop a capability. A request to build, fix, or make Candidate HTML
pass does not by itself grant this authorization.
_Avoid_: inferred permission, Contract failure

**Experimental Build**:
An artifact produced from un-released Contract or compiler changes in the
Development Path. It must remain labeled experimental and is not evidence that
the installed product version formally supports the capability.
_Avoid_: supported build, silent hotfix

**OfficeHTML Import**:
The constrained conversion of an OfficeCLI-exported HTML projection into a new
PPTX. In V0.2 its implementation and focused tests may remain in an explicitly
internal experimental area, but it is absent from the public API, Product
Command, Capability Manifest, and Authoring Skill. It is not a formally
supported product capability or an existing-presentation editing workflow.
_Avoid_: round-trip editor, PPTX edit mode

**Legacy Renderer**:
The inherited `python-pptx` conversion path and its compatibility-facing
entry points. It is excluded from the V0.2 Product Repository's maintained
code and public surface; preserved Git history is the recovery mechanism.
_Avoid_: alternate backend, compatibility mode

**Release Regression Asset**:
An internal fixture, test, or acceptance workflow used to protect a release
without becoming a public command, API, capability claim, or Skill workflow.
The Algeria deck is retained in this role.
_Avoid_: product example, user-facing acceptance command

**Public Product Surface**:
The installed interfaces and claims available to users and agents: the Python
API, Product Command, Capability Manifest, Author Contract, and Authoring
Skill. Internal experiments and release regression assets are not members of
this surface merely because their source remains in the repository.
_Avoid_: every importable module, every repository script

**build-a-pptx-with-html**:
The sole supported V0.2 Authoring Skill. It guides an agent from requirements,
visual references, or Candidate HTML through Author HTML iteration to a
validated, editable PPTX. It orchestrates the Core Product, does not implement
compilation itself, and does not call or depend on `write-a-html-ppt`.
_Avoid_: officecli-html-to-pptx-authoring, write-a-html-pptx

**Deprecated Authoring Skill**:
`write-a-html-ppt`, the predecessor workflow for the original
Design-Arena/html-to-pptx path. V0.2 supersedes it with
`build-a-pptx-with-html`; it is not a supported alternate route, dependency,
or fallback for the Product Plugin. It is hard-retired from maintained Skill
directories and catalogs without a same-name forwarding stub; an existing
user installation is reported as a conflict but never silently removed.
_Avoid_: legacy companion Skill, HTML-stage subskill

**Hard Retirement**:
Removal of a deprecated Skill from maintained distributions and active Skill
catalogs without retaining a triggerable redirect or warning stub. Source
history and migration notes remain available, while removal of a user's
existing installation requires a separate explicit action.
_Avoid_: forwarding alias, silent uninstall

**Core Product**:
The installable Python package, API, Product Command, Author Contract, and
deterministic evidence-producing compiler. It remains usable without Codex or
the Product Plugin.
_Avoid_: Plugin backend, Skill script compiler

**Product Plugin**:
The installable Codex distribution for the product's Agent-facing experience.
In V0.2 it contains workflow guidance only and has no MCP server or custom UI.
It does not bundle or silently install the Core Product, OfficeCLI, Chromium,
Node.js, or a Python environment.
_Avoid_: compiler plugin, OfficeCLI plugin

**Authoring Skill**:
The Product Plugin workflow that takes a user's content, requirements, or
reference visuals through Author HTML iteration, compilation, and evidence-backed
PPTX delivery. Its user-facing name is `build-a-pptx-with-html`.
_Avoid_: compiler implementation, OfficeHTML editing skill

## Current status

This repository worktree is reserved for the OfficeCLI HTML-to-PPTX compiler MVP.

- Worktree: `D:\Opencodeworkspace\html-to-pptx\officecli-html-to-pptx-mvp`
- Branch: `codex/officecli-html-to-pptx-mvp`
- Remote tracking branch: `fork/codex/officecli-html-to-pptx-mvp`
- Planning base commit: `098b4eba118e17894938ca901f002221790f8b0a`
- Base remote branch: `fork/fix/clear-theme-shape-effects`
- OfficeCLI minimum supported version: `1.0.147` (`>=1.0.147` accepted)
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

The code and test remediation is committed as `d864d47`; the tested follow-up
range is `355630f..d864d47` on `codex/officecli-html-to-pptx-mvp`.

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

Focused follow-up reacceptance (2026-09-08) fixed the remaining OfficeHTML
unitless line-height projection.  OfficeCLI 1.0.147 reports a 4/3 unitless
HTML ratio, so the reverse profile now restores that ratio before lowering;
the public seam regression covers `1.4 -> 1.050x` and `0.8 -> 0.600x`.

The follow-up code and test fix is committed as `cfb38d9`; the tested range is
`5c06c92..cfb38d9` on `codex/officecli-html-to-pptx-mvp`.  Evidence is under
`C:\TEMP\issue07-independent-reacceptance-20260908\post-fix`:

- the supplied manifest probe is `PASS` with `0` findings;
- post-fix PPTX B passes OfficeCLI validation and retains the expected
  `8 slides / 89 shapes / 154 textboxes / 18 pictures / 9 tables` structure;
- the three stable issue keys are unchanged, with slide-1 `need 120pt ->
  107pt` and slide-8 `29pt` / `43pt` unchanged from A to B;
- targeted B screenshots for slides 1 and 8 show no title overlap or new
  visual regression; no second full eight-slide visual replay was needed;
- the full regression suite is `75 passed`, with `compileall` and
  `git diff --check` passing.

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

## V0.1 historical working rules

The rules below governed the completed V0.1 MVP. For V0.2 implementation, the
accepted ADRs and `.scratch/officecli-html-to-pptx-v0.2-core/spec.md` supersede
them where product identity, public profiles, or Legacy Renderer treatment
differs.

1. Work only in this repository worktree and on `codex/officecli-html-to-pptx-mvp` unless the user explicitly changes the target.
2. Start from the next explicitly assigned ticket. Tickets 01–07 are complete for the current MVP; future work must remain within the deferred surface.
3. Read the full spec and the assigned ticket before changing code.
4. Preserve the old renderer and existing tests during the MVP.
5. Use installed OfficeCLI help as the authority for property names and capabilities; the minimum supported OfficeCLI version is 1.0.147.
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
- `.scratch/build-a-pptx-with-html/spec.md` — V0.2 Authoring Skill specification; static implementation is complete and live integration awaits the Core Product.
- `.scratch/officecli-html-to-pptx-v0.2-core/spec.md` — ready-for-agent V0.2 Core Product implementation specification.
