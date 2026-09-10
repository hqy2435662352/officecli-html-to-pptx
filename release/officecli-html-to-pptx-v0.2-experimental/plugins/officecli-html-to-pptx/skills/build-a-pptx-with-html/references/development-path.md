# Authorized Development Path

Read this reference only after the user explicitly authorizes a general
missing-capability change to the Author Contract or product source. A failed
Candidate-HTML check, a build failure, or a request to make one input pass does
not grant that authorization.

## Gate the change

State the proposed general capability, the affected Contract or product
surface, and why Focused Repair or Reconstruction cannot satisfy the request.
Keep the normal path paused until that scope is explicit. Preserve the user's
input and all rejected workbenches while investigating.

Read `CONTEXT.md`, the relevant accepted ADRs under `docs/adr/`, the current
implementation, and the focused tests. Use those as development authorities;
the installed `capabilities --json`, `check --json`, and command help remain
runtime authorities after the change.

## Implement and prove

Model a reusable capability rather than adding a one-off bypass. Extend the
public seam that owns the behavior, add focused regression coverage for the
accepted input and the relevant rejection or diagnostic, and preserve
unrelated behavior. Run the focused tests, the relevant full suite, and the
repository's applicable compile and diff checks. Use the repository's release
gate and source state as evidence instead of treating a successful local
experiment as support.

Record the source revision and whether the worktree was dirty when the
experimental result was produced. Mark any output that depends on the change
as an **Experimental Build**. Experimental evidence can guide further product
work, but it does not expand the installed product's formal capability claim.

## Return to the workflow

After the authorized source change is verified, regenerate or refresh the
capability authority, create a fresh `.author.html` if needed, and run the
normal Contract-first sequence from `check`. Keep the experimental label and
source-state data attached to every resulting Artifact Pair.

**Development completion criterion:** the authorized general capability has
focused public-seam regression evidence, the applicable repository checks pass,
the output is explicitly labeled Experimental Build with source revision and
dirty state, and the normal workflow can resume only through a fresh Contract
check.
