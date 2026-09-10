---
name: build-a-pptx-with-html
description: Build a new editable PowerPoint deck through Author HTML and officecli-html-to-pptx. Use when the user supplies existing HTML, visual references, or a content brief for a new PPTX.
---

# Contract-first new-deck workflow

Use this Skill for a new editable PowerPoint deck that starts from one or more
of these inputs:

- Existing HTML is the Candidate HTML and the primary starting artifact when
  it is usable.
- Visual references constrain appearance and may guide authoring or review.
- A content brief constrains content and composition and may guide authoring or
  review.

These inputs can be combined. References and briefs remain authoring context;
the compiler receives only checked Author HTML. Every visible item intended by
the user becomes an independent authored object or receives an explicit
unsupported-input diagnostic. A whole-slide screenshot is not an authored
substitute.

The workflow produces one new editable PPTX, its matching Evidence Bundle, and
a derived visual-review outcome. The Core Product owns the Author Contract,
capability data, measurement, lowering, rendering, validation, evidence
schemas, and result semantics. Use its public commands and structured results;
keep compiler and validation logic out of this Skill.

## Boundaries

This is the Product Version `0.2.0` new-deck workflow. Begin with HTML,
references, or a brief and create a new PPTX. A task that starts by editing an
existing PPTX belongs to the separate presentation-editing workflow.

Preserve all user-supplied inputs. Write new or reconstructed HTML to a
separately named `.author.html` workbench. Keep the PPTX and its same-stem
`.evidence/` directory as one Artifact Pair. The formal V0.2 product target is
Windows; do not make a broader platform-support claim from an individual run.

Use the installed Core Product as the authority for supported HTML, object
kinds, runtime compatibility, diagnostics, artifact schemas, and outcomes. Do
not install or upgrade a runtime without explicit user permission. A failed
Contract check is a remediation signal, not authorization to change the
Contract or product source.

## Contract-first sequence

### 1. Establish Candidate HTML

Choose one primary starting artifact while retaining every supplied input.
When usable HTML exists, preserve it byte-for-byte before inspection and use it
as Candidate HTML. Apply references and the brief as context for authoring and
later review. When no HTML exists, create a separately named `.author.html`
workbench from the references, brief, or both.

When creating, reconstructing, or materially repairing HTML, read
[references/author-html.md](references/author-html.md). Consult
`capabilities --json` when a support boundary affects an authoring decision;
otherwise let the installed Contract and `check` output remain the authority.

**Completion criterion:** one browsable Candidate HTML workbench represents
every intended slide and visible content item with independent authored text,
shapes, pictures, or tables, or records an explicit unsupported boundary for
each item it cannot represent.

### 2. Reach Author HTML

Run the Core Product's `check --json` against the Candidate HTML. A passing
report promotes that exact workbench to Author HTML. On failure, preserve the
rejected input and choose the smallest repair that preserves the intended
composition:

- Use Focused Repair when local edits can preserve the composition.
- Use Reconstruction when Contract compliance requires material reauthoring.

Write either result to a separate `.author.html` workbench and rerun `check`
after every remediation. Inspect the workbench and the diagnostic source
locations enough to resolve authored defects before building. If the user
explicitly authorizes development of a general missing capability, stop the
normal remediation path and read
[references/development-path.md](references/development-path.md).

**Completion criterion:** the exact workbench passed the installed Author
Contract, or the explicitly authorized Development Path has taken ownership of
the request; no unchecked HTML is sent to Build.

### 3. Build one Artifact Pair

Call the Core Product's `build --json` with only the checked Author HTML and an
Agent-managed output name. Treat the requested PPTX and the derived same-stem
`.evidence/` directory as one pair. If either target exists, allocate the next
free revision suffix (for example, `name-r01.pptx` and
`name-r01.evidence/`) without overwriting or asking the user to manage run
directories. Keep the initial build unsuffixed when its pair is free.

Interpret the Command Result Envelope rather than process exit text. A
structurally successful build remains pending until Visual Review and
Finalization. The Evidence Bundle records the runtime attestation, so call
`doctor --json` when environment state is unknown, a runtime diagnostic
requires it, or an authorized dependency remediation needs a recheck; do not
turn Doctor into a fixed ritual. Use command help only when the current
decision needs an otherwise unknown flag or artifact rule.

**Completion criterion:** a new matching PPTX and Evidence Bundle exist, and
the Core Product reports that the structural build stages passed for that
Artifact Pair.

### 4. Review and finalize

Keep visual judgment independent from the authoring pass. When an independent
reviewer is available, delegate the complete Comparison Image set rather than
having the authoring pass approve its own work. Review every Comparison Image
slide by slide and update the seeded `visual-review.json` with complete slide
coverage and only `major` or `minor` findings. A `major` finding must state a
visible location, factual deviation, and actionable revision instruction.

Call `finalize --json` for the exact Artifact Pair. Let Finalization derive the
only supported outcomes: `PASS`, `PASS_WITH_FINDINGS`, or
`REVISION_REQUIRED`. Do not invent a score, threshold, or replacement outcome.

**Completion criterion:** every Comparison Image is represented in the review
record and `finalize --json` returns a derived outcome for the matching PPTX,
Author HTML, and Evidence Bundle.

### 5. Revise or deliver

`PASS` and `PASS_WITH_FINDINGS` finish the workflow. Report minor findings as
delivery notes without reopening the deck for polish. For
`REVISION_REQUIRED`, create a new Author HTML revision, a new Artifact Pair,
and a new complete Visual Review. The initial build does not consume the
revision budget; allow at most three automatic repair, rebuild, and review
cycles after it. Diagnostic reads and infrastructure retries that do not
create a new Author HTML revision do not consume that budget.

If major findings remain after the third automatic cycle, preserve every
Artifact Pair and its evidence, summarize what changed and what remains, and
ask the user before beginning another bounded set of cycles. A user decision
to continue grants up to three more automatic cycles.

**Completion criterion:** deliver a finalized Artifact Pair with its derived
outcome, or return the latest pair, remaining major findings, revision history,
and the specific user decision required after the automatic budget is
exhausted.

## Final response

On successful completion, lead with:

- a clickable absolute path to the PPTX;
- a clickable absolute path to the Evidence Bundle;
- the derived outcome;
- a compact summary of minor findings, if any; and
- the Experimental Build label and revision data when the Development Path was
  used.

When the revision budget is exhausted, provide the latest Artifact Pair, the
remaining major findings, what changed across the completed revisions, and the
concrete decision needed from the user.
