# The acceptance claim in this bundle is withdrawn

The V0.4.2 representative acceptance was claimed, reviewed, and **rejected**. The
claim is withdrawn; this bundle is evidence, not acceptance.

## Why

The review that rejected it, and the reasoning in full, is recorded in
`.scratch/v0.4.2/comment-18-withdrawal.md`. In short: the acceptance rested on a
gate that could not see the things it was supposed to be checking. The style
readback compared the projection with itself, the text comparison was
whitespace-blind, the table expectation was read from the artifact under test, and
the privacy guard was a manual step rather than a gate. A `PASS_WITH_FINDINGS`
reached through those checks is not evidence of anything.

## What has changed since

The finishing checklist has since closed, in this order: the privacy guard is wired
into the commit and push paths and proven on throwaway repositories; the style
readback is independent and now also judges paragraph spacing, shrink-to-fit and
alignment; the text and table rules are structure-preserving and published; the
publication step is an atomic claim and OfficeCLI reads are bounded and recorded;
the public surface is retracted to ADR 0030; the acceptance driver runs the three
opaque source slots with per-deck before/after hashes; and the adversarial mutation
suite covers twenty-four comparator faults plus an end-to-end deck mutation.

Every one of those changes made the gate **stricter**. None of them widened a
waiver or relaxed a tolerance.

## What is still open, as of the run this bundle records

This bundle's own verdict is `BLOCK`, and the blocking diagnostics belong to one
synthetic probe object, not to any of the eight real pages. Two product defects on
that object are recorded in `.scratch/v0.4.2/DRIVER-REPAIR-FINDINGS.md`:

* a projected body drops the source's paragraph spacing, because nothing in the
  current canonical paragraph orthography can carry one; and
* an empty paragraph's line box is sized from the previous paragraph's first run,
  which makes the rebuilt body taller than the source and materially worsens an
  overflow the source already has.

Neither is a check defect, and the check is right to block on both.

## How to read this bundle

Everything under `gate/` is the gate's own published evidence for the run this
bundle describes: the verdict document, the per-page records, the disposition
ledger, the finding sets, the isolation proofs and the artifact hashes. The report
at the top of the bundle is derived from that evidence and is not an independent
source. The commit this bundle was produced from and the run id that binds its
documents together are printed in the review package built beside it.

Do not read any verdict in this bundle as an acceptance while this file is present.
