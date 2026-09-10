# `build-a-pptx-with-html` Skill Creation Spec

**Status:** static implementation complete; live integration blocked on the
V0.2 Core Product baseline

## Outcome

Create the model-invoked `build-a-pptx-with-html` Skill for the V0.2
`officecli-html-to-pptx` Codex Plugin. The Skill must guide an Agent from
existing HTML, visual references, or a content brief to a checked Author HTML
workbench, a new editable PPTX, a complete Evidence Bundle, and a finalized
visual-review outcome.

The Skill is an Agent workflow over the Core Product. It must make the normal
path predictable without duplicating compiler logic, the Author Contract, the
Capability Manifest, or runtime version authorities.

## Core prerequisite and staged acceptance

This specification creates the workflow layer; it does not authorize the Skill
to manufacture missing product commands. The required Core implementation is
specified separately in
[`../officecli-html-to-pptx-v0.2-core/spec.md`](../officecli-html-to-pptx-v0.2-core/spec.md).

Accept the Skill in three stages:

1. **Static package acceptance** validates the Plugin manifest, Skill body,
   disclosed references, completion criteria, and absence of duplicated Core
   logic.
2. **Routing acceptance** validates the lightweight prompt fixtures without
   claiming that a PPTX was built.
3. **Live integration acceptance** runs one representative request only after
   the V0.2 public commands and formal Rendering Compatibility Pair are
   available.

Stages 1 and 2 may complete before the Core prerequisite. Stage 3 remains
explicitly blocked rather than falling back to the V0.1 namespace, Python API,
or legacy command surface.

## Product boundary

The Skill belongs to the same repository and Product Version as the Python
distribution and Codex Plugin. V0.2 ships a skills-only Plugin: no MCP server,
custom UI, or second compiler implementation.

The Core Product owns:

- `doctor`, `capabilities`, `check`, `build`, and `finalize`;
- the Author Contract and supported-capability data;
- Chromium measurement, PPT Object IR lowering, OfficeCLI rendering, and
  structural validation;
- Artifact Pair and Evidence Bundle schemas;
- deterministic diagnostics and result outcomes.

The Skill owns:

- choosing the primary starting artifact while retaining all auxiliary input;
- creating or remediating the Author HTML workbench;
- calling the Core Product in order;
- managing output names, collision-free revisions, and the three-cycle budget;
- arranging visual judgment and translating findings into the next action;
- presenting the finished artifacts and findings to the user.

## Package shape

The independent repository will contain:

```text
.codex-plugin/plugin.json
skills/
  build-a-pptx-with-html/
    SKILL.md
    references/
      author-html.md
      development-path.md
```

Add a template or helper script only when the implementation proves that a
plain Skill instruction plus the Core CLI cannot provide the same behavior.
The first version should not introduce a Skill-owned orchestration framework.

## Invocation

The Skill is model-invoked because an Agent must select it automatically when
a user requests a new editable PPTX through HTML, whether the user starts with
HTML, visual references, or only a content brief.

Draft description:

> Build a new editable PowerPoint deck through Author HTML and
> officecli-html-to-pptx. Use when the user supplies existing HTML, visual
> references, or a content brief for a new PPTX.

The final description must retain one trigger per genuine branch and omit
implementation identity already available in the Skill body. Existing-PPTX
editing is routed outside this Skill by positive scope wording in the body,
not by expanding the description into a catalog of exclusions.

Use **Contract-first** as the leading word for the execution path: every input
combination must produce checked Author HTML before build.

## Input roles

| Supplied input | Role |
|---|---|
| Existing HTML | Primary starting artifact and Candidate HTML; preserve it before any remediation. |
| Visual references | Auxiliary appearance constraints, or the basis for a new workbench when no HTML exists. |
| Content brief | Auxiliary content and composition constraints, or the basis for a new workbench when no HTML exists. |

Determine one primary starting artifact without forcing the user's inputs into
mutually exclusive branches. When usable HTML is supplied, it is the Candidate
HTML; references and briefs may additionally guide authoring and review. When
no Candidate HTML exists, create a `.author.html` workbench from the supplied
references, brief, or both.

References and briefs are authoring context rather than compiler inputs. Their
visible content must become independent authored objects rather than a
whole-slide screenshot substitute.

## Operating model

The Skill constrains artifacts and decision boundaries, not the Agent's
reasoning mechanics.

### Hard invariants

- Core Build receives only checked Author HTML.
- User inputs remain unchanged.
- Every intended visible item is represented or rejected explicitly.
- A PPTX and its Evidence Bundle remain one Artifact Pair.
- Product development begins only after explicit user authorization.

### Routing decisions

- Determine the primary starting artifact from all supplied inputs.
- Load `references/author-html.md` only for authoring or material remediation.
- Use `capabilities`, `doctor`, and command help when the current decision needs
  their authority.
- Load `references/development-path.md` only after Development Authorization.

### Agent judgment

- How much author-side inspection is useful before the first build.
- Whether a rejected Candidate HTML needs Focused Repair or Reconstruction.
- Which capability or environment diagnostic is needed for a concrete blocker.

## Normal sequence

### 1. Establish Candidate HTML

Apply all supplied context to one primary starting artifact. Existing HTML
remains unchanged. New or reconstructed work goes to a separately named
`.author.html` workbench. When creating or materially remediating HTML, load
`references/author-html.md` and consult `capabilities --json` when supported
boundaries affect the authoring decision.

**Completion criterion:** one browsable Candidate HTML workbench represents
every intended slide and visible content item without whole-slide flattening.

### 2. Reach Author HTML

Run `check --json` against Candidate HTML. A pass promotes it to Author HTML.
On failure, use Focused Repair when local changes preserve composition; use
Reconstruction when compliance requires material reauthoring. Preserve the
rejected input, use `capabilities --json` or command help only when the
diagnostic leaves a support decision unresolved, and re-run `check` after every
remediation.

A Contract failure never authorizes a Contract or source change. If the user
explicitly asks to develop a general missing capability, leave the normal path
through the Development Path escape hatch and load
`references/development-path.md`.

**Completion criterion:** the exact workbench passed the installed Author
Contract, or the normal path hands off through the explicitly authorized
Development Path escape hatch.

### 3. Build one Artifact Pair

Call `build --json` using the checked Author HTML and an Agent-managed output
name. Treat the requested PPTX and its derived same-stem `.evidence/` directory
as one pair. When a target already exists, allocate the next revision suffix;
never overwrite or ask the user to manage run directories.

Interpret result states and diagnostics from the Command Result Envelope. Do
not infer success from process exit alone. A structurally successful build
remains pending until visual review is finalized. The build records its actual
runtime attestation in the Evidence Bundle, so the Skill does not run a fixed
preflight ritual. Call `doctor --json` when environment state is unknown, a
runtime diagnostic requires it, or an authorized dependency remediation must
be rechecked. Any install or upgrade still requires explicit user permission.

**Completion criterion:** a new, matching PPTX and Evidence Bundle exist and
the Core Product reports that structural build stages passed.

### 4. Review and finalize

Keep visual judgment independent from the authoring pass; when independent
Subagent review is available, delegate the complete Comparison Image set.

Record slide coverage and `major` or `minor` findings in the seeded
`visual-review.json`, then call `finalize --json`. `finalize` derives `PASS`,
`PASS_WITH_FINDINGS`, or `REVISION_REQUIRED`; neither the Skill nor reviewer
invents another score, threshold, or severity.

**Completion criterion:** every Comparison Image is reviewed and `finalize`
returns a derived outcome for the exact Artifact Pair.

### 5. Revise or deliver

`PASS` and `PASS_WITH_FINDINGS` finish the workflow. Report minor findings
without reopening the deck for polish. `REVISION_REQUIRED` starts a new Author
HTML revision and Artifact Pair.

The initial build does not count as a revision. The Agent may run at most three
automatic repair, rebuild, and review cycles. If major findings remain after
the third, preserve the evidence, summarize progress and remaining blockers,
and ask the user before beginning a fourth. User confirmation grants another
budget of up to three cycles. This budget limits autonomous artifact-producing
iterations, not diagnostic reads, infrastructure retries, or reasoning steps.

**Completion criterion:** deliver a finalized Artifact Pair, or return a
specific user decision after the automatic revision budget is exhausted.

## Author HTML reference

`references/author-html.md` is disclosed only when the Agent creates,
reconstructs, or materially repairs HTML. It should contain practical authoring
instructions required to produce a good workbench, not a copied capability
matrix.

It must direct the Agent to:

- use the installed Contract and `check` output as the capability authority;
- keep a browsable slide workbench and independent authored objects;
- inspect every reference image when references are supplied;
- preserve visible content and use explicit diagnostics at unsupported
  boundaries;
- inspect the workbench enough to catch obvious authored defects and
  Contract-visible problems before the first build;
- use Comparison Images for Build-Driven Visual Discovery instead of delaying
  the first build for speculative polish;
- use native text, shapes, pictures, and tables within the reported capability
  surface.

Exact CSS rules, supported properties, object kinds, Contract Version, and
renderer versions stay in Core Product documentation or generated capability
data. The reference uses context pointers to those authorities instead of
duplicating them.

## Development Path reference

`references/development-path.md` is an escape hatch disclosed only after
explicit user authorization to change the Contract or product source. The
normal Skill carries only the authorization decision and this context pointer;
the reference owns regression method, source state, testing, and Experimental
Build identification. Experimental output does not expand the installed
product's formal support claim.

## Final response contract

On successful completion, lead with the result and provide:

- a clickable absolute path to the PPTX;
- a clickable absolute path to the Evidence Bundle;
- the derived outcome;
- a compact summary of any minor findings;
- an Experimental Build label and revision data when applicable.

When the three-cycle revision budget is exhausted, provide the latest Artifact
Pair, the remaining major findings, what changed across the three revisions,
and the concrete decision needed from the user.

## Single sources of truth

### Runtime authorities

| Meaning | Authority |
|---|---|
| Supported HTML and object capabilities | Installed Author Contract and `capabilities --json` |
| Candidate acceptance and remediation diagnostics | `check --json` |
| Runtime presence and compatibility | `doctor --json` |
| Build, evidence, and finalization behavior | Public Core Product commands and structured results |
| Skill sequence and routing decisions | `skills/build-a-pptx-with-html/SKILL.md` |
| Conditional authoring guidance | `references/author-html.md` |

### Development authorities

| Meaning | Authority |
|---|---|
| Product terminology and historical working context | `CONTEXT.md` |
| Product design decisions | Accepted ADRs under `docs/adr/` |
| Implementation behavior and regression evidence | Repository source and tests |
| Explicit product-development behavior | `references/development-path.md` |

`CONTEXT.md`, ADRs, repository source, and tests guide Skill development and
maintenance. The supported normal workflow must not require loading them. The
Skill holds runtime steps and precise context pointers instead of copying an
authority to make itself appear self-contained.

## Hard boundaries

- The supported path creates a new PPTX; it does not edit an existing PPTX.
- OfficeHTML Import is absent from the Skill.
- `write-a-html-ppt` is deprecated and is neither called nor used as fallback.
- The Skill does not install or upgrade runtimes without explicit permission.
- The Skill does not implement compilation, validation, comparison rendering,
  or finalization.
- The Skill does not silently omit visible content or replace a slide with a
  screenshot.
- V0.2 does not claim macOS, native Linux, or WSL2 formal support.

## Skill-writing quality bar

Before accepting the created Skill:

1. Verify that the description covers the three input roles without treating
   combined user inputs as mutually exclusive branches or padding them with
   synonyms.
2. Verify that every normal step ends with a checkable completion criterion.
3. Apply the no-op test sentence by sentence and remove instructions that do
   not change Agent behavior.
4. Keep each rule in one authority; replace duplicated Contract, version, and
   schema facts with precise context pointers.
5. Keep branch-only material behind its reference pointer and keep every-branch
   steps in `SKILL.md`.
6. Prefer positive target behavior; retain prohibitions only for genuine safety
   or product-boundary guardrails.
7. Confirm that Visual Review preserves judgment independent from the authoring
   pass without binding the Skill to an exact sentence or Subagent framework.

## Lightweight routing eval

Use five prompt fixtures to test the Skill's actual decision boundaries without
running five complete PPTX builds:

1. Existing HTML plus reference screenshots and a requested content addition:
   invoke the Skill, preserve the HTML, use it as Candidate HTML, and treat the
   other inputs as auxiliary context.
2. Reference screenshots without HTML: invoke the Skill and create a new
   `.author.html` workbench.
3. A content brief without HTML: invoke the Skill and create a new
   `.author.html` workbench.
4. A request to modify an existing PPTX: do not select this new-deck Skill.
5. Candidate HTML with an unsupported feature: preserve the current Contract;
   remediate or report the boundary, and enter the Development Path only after
   explicit authorization.

## Acceptance checklist

### Static package and routing

- The Plugin manifest and Skill use Product Version `0.2.0`.
- The Skill is model-invoked under the exact name `build-a-pptx-with-html`.
- Existing HTML, visual references, and briefs can be combined around one
  primary starting artifact and converge on checked Author HTML.
- Existing input is preserved and reconstructed work uses a separate
  `.author.html` file.
- Normal operation uses only public Core Product commands and structured
  results.
- Artifact Pair naming, visual review, finalization, and the three-cycle budget
  are represented without making the user operate the CLI protocol.
- Contract failures do not enter the Development Path without explicit user
  authorization.
- OfficeHTML Import, existing-PPTX editing, the Legacy Renderer, and the
  deprecated Skill do not appear as alternate paths.
- The Skill contains no duplicated capability matrix or pinned renderer value.
- The five lightweight routing fixtures produce the expected invocation and
  boundary decisions without requiring full builds.
- The created files pass the applicable Skill and Plugin validation plus
  `git diff --check`.

### Live integration

- The V0.2 Core public commands and formal Rendering Compatibility Pair are
  available.
- One representative live run produces an editable PPTX, complete Evidence
  Bundle, and final derived outcome.

## Implementation stopping point

Static Skill creation is complete when the package and routing stage is
evidenced. Record live integration as blocked until its Core prerequisite is
implemented; that blocker is not a reason to add compiler behavior to the
Skill. Operational acceptance is complete when the later representative live
run succeeds. Stop without expanding the first Plugin with an MCP server, UI,
helper framework, additional Skill, or platform matrix.
