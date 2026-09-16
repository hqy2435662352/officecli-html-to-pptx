# The acceptance claim in this bundle is withdrawn

The V0.4.2 representative acceptance was claimed, reviewed, and **rejected**. The
claim is withdrawn; this bundle is evidence, not acceptance.

## Why

The review that rejected it found that the acceptance rested on a gate that could
not see the things it was supposed to be checking. The style readback compared the
projection with itself, the text comparison was whitespace-blind, the table
expectation was read from the artifact under test, and the privacy guard was a
manual step rather than a gate. A `PASS_WITH_FINDINGS` reached through those checks
is not evidence of anything.

This file is the public statement of the withdrawal and stays with the bundle, so no
reader can take the bundle's own words as acceptance evidence without meeting it.
The working session kept a longer local record of the review and of each fix; it is
a development note and is not published.

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

## What the run this bundle records found

This bundle's verdict is `PASS_WITH_FINDINGS`, with zero blocking diagnostics and
zero material deltas — and it is still not an acceptance, because a machine verdict
is not a review.

The rules closed by the checklist are what produced it, and two of them found real
product defects that had been invisible: a body whose source colour is a theme
token was rebuilt black, and a body whose source declares a paragraph layout the
canonical surface cannot write — an inter-paragraph spacing, or an empty paragraph
whose line the rebuild sizes from the previous paragraph's first run — was rebuilt
with the text painted where the source does not paint it. The first is fixed where
the value lives: the reader resolves a plain scheme token from the deck's own
colour scheme. The second is answered by classification rather than by a silent
comparison against a representative value: such a body is `base-only-semantic`,
represented by its own object-local paint, with the reason code
`text_paragraph_layout_base_only` in the ledger. On this corpus that is two real
objects, on `src1` page 2 and `src1` page 5, plus the probe's own rich-text block —
the page stays faithful, the object stops being editable, and the ledger says which
and why.

What remains before the claim can be restated is the independent review the
checklist's section K asks for: a page-by-page comparison of the source, the
Canonical Author HTML and the rebuilt deck, with the disposition ledger checked on
every page and no machine `PASS` accepted as a substitute for looking.


## How to read this bundle

Everything under `gate/` is the gate's own published evidence for the run this
bundle describes: the verdict document, the per-page records, the disposition
ledger, the finding sets, the isolation proofs and the artifact hashes. The report
at the top of the bundle is derived from that evidence and is not an independent
source. The commit this bundle was produced from and the run id that binds its
documents together are printed in the review package built beside it.

Do not read any verdict in this bundle as an acceptance while this file is present.
