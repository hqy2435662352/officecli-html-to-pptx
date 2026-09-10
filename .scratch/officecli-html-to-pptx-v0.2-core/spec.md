# `officecli-html-to-pptx` V0.2 Core Product Spec

**Status:** ready-for-agent

## Problem statement

The repository contains a proven V0.1 OfficeCLI compiler kernel, but it does
not yet contain the V0.2 Core Product consumed by `build-a-pptx-with-html`.
The current kernel can check an Author Contract and compile Author HTML through
Chromium measurement, PPT Object IR, and OfficeCLI into a validated PPTX. It is
still packaged as `html-to-pptx` `0.3.0`, exposes the Legacy Renderer CLI, and
offers the OfficeCLI compiler primarily through a profile-oriented Python API.

The missing layer is the independent product protocol:

```text
officecli-html-to-pptx capabilities
officecli-html-to-pptx doctor
officecli-html-to-pptx check
officecli-html-to-pptx build
officecli-html-to-pptx finalize
```

Without these commands, their shared result envelope, and the Artifact Pair /
Evidence Bundle implementation, the Skill can pass static and routing checks
but cannot complete its representative live integration run. The Skill must
remain thin; it must not imitate this missing Core behavior.

## Existing kernel to preserve

The implementation starts from working code rather than a rewrite:

- `contract.py` provides Contract v1, structured diagnostics, and
  `check_contract()` for the `author` profile.
- `officecli_compiler.py` provides `compile_officecli()`, Author HTML lowering,
  deterministic object identities, manifest generation, OfficeCLI batch and
  validation, temporary output, and non-overwrite delivery.
- `converter.py` contains the Chromium measurement implementation currently
  shared with the Legacy Renderer.
- `compare.py` contains HTML slide capture, PPTX rendering, and side-by-side
  comparison composition.
- `acceptance.py` contains reusable OfficeCLI readback, issues, screenshot, and
  review-normalization techniques mixed with Algeria-specific gate behavior.
- Existing compiler, Contract, Algeria, and round-trip tests prove the current
  object surface and failure boundaries.

Reuse the narrow helpers that serve the V0.2 path. Do not expose the old
Algeria acceptance state machine or its `PASS/PENDING/REGRESSION` vocabulary as
the new product protocol.

## Outcome

Deliver an independently installable Python distribution named
`officecli-html-to-pptx`, version `0.2.0`, with import namespace
`officecli_html_to_pptx`, one task-oriented command, a narrow Python
application API, and complete support for the Skill's normal public path:

```text
Candidate HTML
  -> check
  -> Author HTML
  -> build
  -> PPTX + Evidence Bundle
  -> Agent-authored Visual Review
  -> finalize
  -> PASS | PASS_WITH_FINDINGS | REVISION_REQUIRED
```

The first representative live run is the completion boundary for the baseline.
Capability deepening continues afterward as separate focused changes.

## Operating model

### Public protocol, internal kernel

The public surface speaks in user tasks: diagnose, discover capability, check,
build, and finalize. Profiles, OfficeCLI batches, Chromium capture mechanics,
and OfficeHTML parsing remain internal implementation details.

Implement one small application layer used by both the Python API and CLI.
Avoid a command framework, workflow engine, plugin loader, renderer registry,
or generic artifact graph. One result-envelope type plus five direct operation
handlers is sufficient.

### Contract-first

`check` is the only promotion gate from Candidate HTML to Author HTML. `build`
rechecks the exact input rather than trusting a previous report. Unsupported
visible content remains a blocking diagnostic with source context.

### Transactional pair

`build` treats `name.pptx` and `name.evidence/` as one logical result. It stages
all output, validates it, and publishes the pair only when every build-owned
artifact is complete. Controlled failures clean their staging state and never
replace either existing target.

## Product identity migration

Before exposing the new protocol:

1. Move the maintained package to `src/officecli_html_to_pptx` and update
   internal imports, tests, metadata, and documentation.
2. Change the distribution and command identity to `officecli-html-to-pptx`
   `0.2.0` without old package, namespace, or console-script aliases.
3. Extract Chromium measurement and the small shared font/style helpers needed
   by the Author compiler from `converter.py` into renderer-neutral modules.
4. Point the OfficeCLI compiler at those modules, then remove the Legacy
   Renderer, its CLI, its tests, and the `python-pptx` dependency.
5. Move OfficeHTML Import behind a clearly internal experimental module and
   keep only focused internal tests. It is absent from package exports, CLI,
   Capability Manifest, and Skill.
6. Remove the old public compare and Algeria acceptance console scripts. Reuse
   their suitable helpers internally and retain Algeria only as a Release
   Regression Asset.

Preserve Git history and MIT provenance. This is a breaking product identity
change, not a compatibility migration.

## Command Result Envelope

Every command with `--json` writes exactly one UTF-8 JSON document to stdout.
Progress and human diagnostics go to stderr so an Agent never has to scrape
mixed console prose.

The shared envelope has this minimum shape:

```json
{
  "schema_version": 1,
  "product": {
    "name": "officecli-html-to-pptx",
    "version": "0.2.0"
  },
  "command": "check",
  "status": "PASS",
  "diagnostics": [],
  "artifacts": {},
  "data": {}
}
```

Each diagnostic contains `code`, `severity`, `message`, and `blocking`, plus
only the available source slide, source object, operation, and remediation
fields. Each artifact entry contains an absolute path and, for persisted build
artifacts, a content hash.

Status is command-specific rather than one inflated global enum:

| Command | Successful or actionable statuses |
|---|---|
| `capabilities` | `PASS` |
| `doctor` | `PASS`, `BLOCK` |
| `check` | `PASS`, `BLOCK` |
| `build` | `VISUAL_REVIEW_REQUIRED` |
| `finalize` | `PASS`, `PASS_WITH_FINDINGS`, `REVISION_REQUIRED` |

Unexpected execution failures return `ERROR` with a structured diagnostic.
The JSON status remains the primary Agent decision signal. Use these exit
classes consistently:

- `0`: the command completed its defined operation successfully;
- `2`: a supported, actionable block or revision decision;
- `3`: invalid invocation or invalid input path/schema;
- `4`: unexpected runtime or external-tool execution failure.

`build` returns `0` with `VISUAL_REVIEW_REQUIRED` because producing the pending
Artifact Pair is its successful operation. `finalize` returns `2` for
`REVISION_REQUIRED`.

## Public command contracts

### `capabilities`

Return the installed product identity, Contract Version, supported platform,
required runtime compatibility, public commands, object kinds, and
accepted resource/property surface. Generate this data from the same code
authorities used by Contract checking and lowering; do not maintain a second
handwritten capability matrix.

This command is read-only and environment-independent. It describes formal
support, not what happens to be installed on the current machine.

**Completion criterion:** every formal support claim in the JSON can be traced
to one executable Contract or compiler authority, and no experimental profile
or legacy surface is reported.

### `doctor`

Read-only inspection reports required, discovered, and compatibility state for:

- the Windows platform;
- Python and Node.js tested ranges;
- OfficeCLI executable path and exact version;
- pinned Playwright package and Chromium revision/executable;
- writable temporary and requested output locations when supplied.

Return exact remediation and recheck instructions for each block. Never
install, upgrade, download, mutate PATH, or rewrite configuration. OfficeCLI
`1.0.147` is the minimum supported version; `1.0.147` and newer versions pass,
while older or malformed versions report `BLOCK`.

The current Playwright `1.62.0` / Chromium revision `1234` installation is a
candidate pair to validate, not an automatic support decision. Store the
accepted pair in one product authority after the formal environment is tested.

**Completion criterion:** mocked discovery covers absent, exact, mismatched,
and malformed tools, and a real run accurately reports the current machine
without changing it.

### `check`

Accept one Candidate HTML path and expose only the Author Contract. Wrap the
existing Contract report in the Command Result Envelope, preserve every
diagnostic and CSS classification needed for repair, and hide the public
profile selector.

**Completion criterion:** supported input returns `PASS`; each blocking fixture
returns `BLOCK` with stable source diagnostics; no output PPTX is created.

### `build`

Accept checked Author HTML and a requested `.pptx` output path. Internally:

1. verify that neither the PPTX nor its derived `.evidence/` target exists;
2. run the Author Contract again;
3. attest the formal runtime pair and stop before output on mismatch;
4. compile through the existing Author measurement and OfficeCLI kernel;
5. collect manifest, OfficeCLI validation, and issues readback;
6. render every Author HTML and PPTX slide, create one side-by-side Comparison
   Image per slide, and remove the separate screenshots;
7. seed the pending Visual Review record;
8. bind and publish the complete pair.

The Evidence Bundle contains:

```text
name.evidence/
  contract.json
  capabilities.json
  runtime.json
  manifest.json
  validate.json
  issues.json
  result.json
  visual-review.json
  comparisons/
    slide-001.png
    ...
```

`result.json` records the unique `build_id`, Product and Contract versions,
actual runtime versions, Author HTML hash, PPTX hash, slide count, comparison
inventory, and `VISUAL_REVIEW_REQUIRED` state. The review template records the
same build identity and immutable Comparison Image hashes.

**Completion criterion:** one public command produces an openable editable
PPTX and complete matching Evidence Bundle, while every pre-publication failure
leaves both requested targets absent.

### `finalize`

Accept one Evidence Bundle, derive its paired PPTX from `result.json`, and
validate:

- build identity and Author HTML/PPTX hashes;
- every Comparison Image path and hash;
- review schema and complete slide coverage;
- findings limited to `major` or `minor`;
- a visible location and factual description for every finding;
- an actionable revision instruction for every major finding.

Derive the outcome mechanically: no findings is `PASS`, only minor findings is
`PASS_WITH_FINDINGS`, and any major finding is `REVISION_REQUIRED`. Write a
finalization record without recompiling, rerendering, or performing pixel
analysis.

**Completion criterion:** tampered, incomplete, or mismatched evidence is
rejected; complete review records deterministically produce exactly one of the
three supported outcomes.

## Public Python API

Expose a narrow application API corresponding to the five public operations,
for example `get_capabilities`, `diagnose_environment`, `check_author_html`,
`build_author_html`, and `finalize_build`. CLI handlers call this layer instead
of reimplementing behavior. Export only supported Author-facing operations and
result types from the package root.

Keep profile selection, OfficeHTML Import, batch serialization, screenshot
staging, and Algeria acceptance helpers internal. Tests should favor the public
application and CLI seams over private helper layout.

## Dependency policy

Declare ordinary Python dependencies in package metadata. Pin the Playwright
package that owns the accepted Chromium revision. OfficeCLI and Node.js remain
external prerequisites verified by `doctor`; they are not installed by the
package, CLI, or Skill.

Move dependencies required for the normal build evidence path, including
comparison-image generation and PPTX rendering, into the normal installation
rather than an optional extra. Remove `python-pptx` after the Legacy Renderer
and its tests no longer import it.

## Testing strategy

Use focused public-seam tests for each slice, with fake runtime discovery and
OfficeCLI subprocesses where the external environment is not the behavior
under test. Retain existing Contract/compiler coverage while imports and
modules move.

Required focused coverage includes:

- envelope serialization, stdout/stderr separation, and exit classes;
- capabilities derived from the Contract/compiler authority;
- doctor missing/exact/mismatched runtime cases;
- Author-only check pass and blocking diagnostics;
- refusal when either Artifact Pair target exists;
- build staging cleanup and pair binding;
- complete comparison inventory and removal of intermediate screenshots;
- review schema, hash, build-id, and slide-coverage rejection;
- all three derived final outcomes;
- absence of old public commands, namespace exports, and profile selection.

The baseline integration test uses a small Author HTML fixture containing the
currently supported text, shape, picture, and native-table surface. It must
produce a real PPTX, pass OfficeCLI validation, retain independent editable
objects, create all comparison images, and finalize from a complete review.

The formal representative Skill run waits for OfficeCLI `>=1.0.147` plus the
accepted Playwright/Chromium pair. Do not substitute the old Python API, the
Legacy Renderer, or mocked evidence for that acceptance item.

## Vertical-slice implementation order

### 01 — Independent identity and renderer-neutral measurement

Move the package identity, extract Chromium measurement from the Legacy
Renderer, reconnect the Author compiler, and keep its public-seam tests green.
Do not delete the old renderer until the new compiler no longer imports it.

**Done:** the new namespace can Contract-check and compile the existing minimal
Author fixture without importing `python-pptx`.

### 02 — Agent protocol foundation

Add the result envelope and the direct `capabilities`, `doctor`, and `check`
application/CLI slices. Keep capability data generated and runtime discovery
read-only.

**Done:** the installed new command can answer capability and environment
questions and can promote/reject Candidate HTML through the public command
alone.

### 03 — Structural Artifact Pair

Add `build` through real Author compilation, manifest, runtime, validation,
issues, staged evidence, hashing, and non-overwrite pair delivery. Initially
omit visual comparison only within this incomplete slice.

**Done:** the slice produces a structurally complete staged pair under tests;
the public build is not declared complete until slice 04 lands.

### 04 — Comparison evidence and pending review

Integrate the existing capture/comparison techniques, persist only combined
images, seed `visual-review.json`, and return `VISUAL_REVIEW_REQUIRED`.

**Done:** every slide has one bound Comparison Image and no separate persisted
source/output screenshots.

### 05 — Finalization

Implement review validation and derived outcomes without rebuilding or pixel
analysis.

**Done:** complete and mutated review fixtures prove every association and
outcome rule through the public command.

### 06 — Public-surface pruning and Skill integration

Remove the Legacy Renderer, old commands, compatibility exports, and
`python-pptx`; internalize OfficeHTML Import; run the minimal development
release gate; then execute the Skill's representative live run on the formal
runtime pair.

**Done:** only the independent V0.2 surface is installable, the live Skill run
produces its real finalized Artifact Pair, and no acceptance claim relies on a
legacy or experimental path.

Blocking order:

```text
01 identity + measurement
  -> 02 protocol + doctor/check
    -> 03 structural pair
      -> 04 comparison evidence
        -> 05 finalize
          -> 06 prune + Skill live integration
```

## Capability development after the baseline

The baseline closes the real Skill workflow before expanding the object model.
Subsequent V0.2 capability slices deepen the supported surface in this order,
adjusted only by concrete user cases and OfficeCLI feasibility evidence:

1. native text and paragraph fidelity;
2. common shape geometry and styling;
3. reliable picture and SVG behavior;
4. native table merges and richer cell formatting;
5. slide backgrounds.

Each slice updates the existing Contract/compiler authority, focused
public-seam tests, and proportional real-PPTX evidence. Masters, layouts,
groups, bound connectors, native charts, SmartArt, animations, audio, and video
remain outside V0.2.

## Minimal release gate

Stop after:

- focused tests and the existing relevant suite pass;
- one representative Author HTML completes the five-command product path;
- the PPTX opens with editable supported objects and complete evidence;
- `compileall` and `git diff --check` pass.

Do not add a clean-install matrix, repeat every Skill input role, require the
full Algeria gate for every release, or block Windows V0.2 on WSL2 validation.

## Acceptance checklist

- Distribution, namespace, command, Plugin, and GitHub release identity align
  on `officecli-html-to-pptx` `0.2.0`.
- The new package imports no Legacy Renderer or `python-pptx` dependency.
- The five public commands share the versioned envelope and documented exit
  classes.
- `capabilities` reflects executable support authorities rather than copied
  prose.
- `doctor` is read-only and rejects the current mismatched OfficeCLI version.
- `check` exposes only the Author Contract and preserves repair diagnostics.
- `build` creates a non-overwriting, logically transactional Artifact Pair with
  all specified evidence and one Comparison Image per slide.
- `finalize` verifies exact association and derives only the three supported
  outcomes.
- OfficeHTML Import and Algeria remain internal; legacy public surfaces are
  absent.
- Focused tests, the relevant suite, `compileall`, and `git diff --check` pass.
- A formal-runtime representative run closes the Skill spec's final live
  integration item with a real editable PPTX and Evidence Bundle.

## Out of scope

- Existing-PPTX editing.
- A public profile selector or OfficeHTML command.
- Silent dependency installation or runtime upgrade.
- A renderer framework, workflow engine, MCP server, or custom UI.
- Automatic visual similarity scores or pixel thresholds.
- Cross-platform support claims before the later WSL2 validation track.
- Full master/layout/theme preservation or deferred complex object families.
